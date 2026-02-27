"""
주문 실행 로직 모듈
- 매수/매도 주문 실행
- 주문 취소
- 가격 정정
"""
from datetime import timedelta
from typing import Optional, TYPE_CHECKING

from ..models import Order, OrderType, OrderStatus
from utils.korean_time import now_kst
from utils.async_helpers import run_with_timeout

if TYPE_CHECKING:
    from .order_base import OrderManagerBase


class OrderExecutorMixin:
    """주문 실행 관련 메서드들을 모아둔 Mixin 클래스"""

    async def place_buy_order(self: 'OrderManagerBase', stock_code: str, quantity: int, price: float,
                             timeout_seconds: int = None,
                             target_profit_rate: float = None,
                             stop_loss_rate: float = None) -> Optional[str]:
        """매수 주문 실행"""
        try:
            timeout_seconds = timeout_seconds or self.config.order_management.buy_timeout_seconds

            self.logger.info(f"매수 주문 시도: {stock_code} {quantity}주 @{price:,.0f}원 (타임아웃: {timeout_seconds}초)")

            # 장 시간 체크: 동시호가 등 주문 불가 시간대 차단
            from config.market_hours import MarketHours
            if not MarketHours.can_place_order():
                phase = MarketHours.get_market_phase()
                self.logger.warning(f"매수 주문 차단: 주문 불가 시간대 ({phase.value if hasattr(phase, 'value') else phase}) - {stock_code}")
                return None

            # VI/서킷브레이커 체크: 시장 전체 거래 중단 또는 종목별 VI 발동 시 주문 차단
            from config.market_hours import get_circuit_breaker_state
            cb_state = get_circuit_breaker_state()
            if cb_state.is_market_halted():
                self.logger.warning(f"매수 주문 차단: 시장 전체 서킷브레이커 발동 중 ({stock_code})")
                return None
            if cb_state.is_vi_active(stock_code):
                self.logger.warning(f"매수 주문 차단: {stock_code} VI 발동 중")
                return None

            # 중복 주문 방지: 동일 종목 매수 주문이 이미 진행 중인지 확인
            if self.has_active_buy_order(stock_code):
                existing_order_id = self._active_buy_stocks.get(stock_code)
                self.logger.warning(f"중복 매수 주문 방지: {stock_code} (기존 주문: {existing_order_id})")
                return None

            # FundManager 자금 예약 (실전 매매 시)
            if not getattr(self.config, "paper_trading", False) and self.fund_manager:
                reserve_amount = price * quantity
                # H4 fix: TradingAnalyzer에서 이미 stock_code로 예약한 경우 중복 예약 방지
                already_reserved = self.fund_manager.order_reservations.get(stock_code, 0) > 0
                if already_reserved:
                    self.logger.debug(f"자금 이미 예약됨 (by TradingAnalyzer): {stock_code}")
                    self._temp_reserve_ids[stock_code] = stock_code
                else:
                    # 임시 order_id로 예약 (실제 order_id는 API 응답 후 알 수 있음)
                    temp_reserve_id = f"RESERVE-{stock_code}-{int(now_kst().timestamp())}"
                    if not self.fund_manager.reserve_funds(temp_reserve_id, reserve_amount):
                        self.logger.warning(f"자금 부족으로 매수 주문 거부: {stock_code} (필요: {reserve_amount:,.0f}원)")
                        return None
                    # 임시 예약 ID를 나중에 실제 order_id로 교체하기 위해 저장
                    self._temp_reserve_ids[stock_code] = temp_reserve_id

            # 가상매매 모드: 즉시 체결로 시뮬레이션
            if getattr(self.config, "paper_trading", False):
                return await self._execute_paper_buy_order(
                    stock_code, quantity, price,
                    target_profit_rate, stop_loss_rate
                )

            # 실전 매매 모드: API 호출
            return await self._execute_real_buy_order(
                stock_code, quantity, price, timeout_seconds,
                target_profit_rate, stop_loss_rate
            )

        except Exception as e:
            self.logger.error(f"매수 주문 예외: {e}")
            return None

    async def _execute_paper_buy_order(self: 'OrderManagerBase', stock_code: str, quantity: int,
                                       price: float, target_profit_rate: float,
                                       stop_loss_rate: float) -> Optional[str]:
        """가상매매 매수 주문 처리"""
        fake_order_id = f"VT-BUY-{stock_code}-{int(now_kst().timestamp())}"
        order = Order(
            order_id=fake_order_id,
            stock_code=stock_code,
            order_type=OrderType.BUY,
            price=price,
            quantity=quantity,
            timestamp=now_kst(),
            status=OrderStatus.FILLED,
            remaining_quantity=0,
            order_3min_candle_time=self._get_current_3min_candle_time()
        )
        self.completed_orders.append(order)
        self.logger.info(f"(가상) 매수 체결: {fake_order_id} - {stock_code} {quantity}주 @{price:,.0f}원")

        # DB에 가상매매 기록 저장
        await self._save_paper_buy_to_db(stock_code, quantity, price, target_profit_rate, stop_loss_rate)

        # 알림 및 콜백
        await self._notify_order_filled(order)
        await self._trigger_order_filled_callback(order)

        return fake_order_id

    async def _execute_real_buy_order(self: 'OrderManagerBase', stock_code: str, quantity: int,
                                      price: float, timeout_seconds: int,
                                      target_profit_rate: float,
                                      stop_loss_rate: float) -> Optional[str]:
        """실전 매수 주문 처리"""
        from api.kis_api_manager import OrderResult

        # API 호출을 별도 스레드에서 실행 (타임아웃 20초)
        from utils.price_utils import round_to_tick
        order_price = int(round_to_tick(price))
        result: OrderResult = await run_with_timeout(
            self.executor,
            self.broker.place_buy_order,
            stock_code, quantity, order_price,
            timeout_seconds=35, default=None
        )

        if not result:
            self.logger.error(f"매수 주문 API 타임아웃: {stock_code}")
            # FundManager 예약 해제
            self._release_temp_reserve(stock_code)
            return None

        if result.success:
            # 종목명 조회
            stock_name = self._get_stock_name(stock_code)

            order = Order(
                order_id=result.order_id,
                stock_code=stock_code,
                order_type=OrderType.BUY,
                price=price,
                quantity=quantity,
                timestamp=now_kst(),
                status=OrderStatus.PENDING,
                remaining_quantity=quantity,
                order_3min_candle_time=self._get_current_3min_candle_time(),
                target_profit_rate=target_profit_rate,
                stop_loss_rate=stop_loss_rate,
                stock_name=stock_name
            )

            # 미체결 관리에 추가
            timeout_time = now_kst() + timedelta(seconds=timeout_seconds)
            self.pending_orders[result.order_id] = order
            self.order_timeouts[result.order_id] = timeout_time

            # 중복 주문 방지 맵에 등록
            self._register_active_order(stock_code, result.order_id, OrderType.BUY)

            # FundManager: 임시 예약을 실제 order_id로 교체
            self._transfer_temp_reserve(stock_code, result.order_id)

            self.logger.info(f"매수 주문 성공: {result.order_id} - {stock_code}({stock_name}) {quantity}주 @{price:,.0f}원")
            self.logger.info(f"타임아웃 설정: {timeout_seconds}초 후 ({timeout_time.strftime('%H:%M:%S')}에 취소)")

            # 텔레그램 알림
            if self.telegram:
                await self.telegram.notify_order_placed({
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'order_type': 'buy',
                    'quantity': quantity,
                    'price': price,
                    'order_id': result.order_id
                })

            return result.order_id
        else:
            self.logger.error(f"매수 주문 실패: {result.message}")
            # FundManager 예약 해제
            self._release_temp_reserve(stock_code)
            return None

    def _release_temp_reserve(self: 'OrderManagerBase', stock_code: str) -> None:
        """임시 FundManager 예약 해제 (종목별)"""
        temp_id = self._temp_reserve_ids.pop(stock_code, None)
        if temp_id and self.fund_manager:
            try:
                self.fund_manager.cancel_order(temp_id)
                self.logger.debug(f"임시 자금 예약 해제: {temp_id} ({stock_code})")
            except Exception as e:
                self.logger.warning(f"임시 자금 예약 해제 실패: {e}")

    def _transfer_temp_reserve(self: 'OrderManagerBase', stock_code: str, real_order_id: str) -> None:
        """임시 예약을 실제 order_id로 교체 (종목별)"""
        temp_id = self._temp_reserve_ids.pop(stock_code, None)
        if temp_id and self.fund_manager:
            try:
                # 임시 예약의 금액을 가져와서 실제 order_id로 재등록
                reserved_amount = self.fund_manager.order_reservations.get(temp_id, 0)
                if reserved_amount > 0:
                    self.fund_manager.cancel_order(temp_id)
                    self.fund_manager.reserve_funds(real_order_id, reserved_amount)
                    self.logger.debug(f"자금 예약 이전: {temp_id} -> {real_order_id} ({stock_code})")
            except Exception as e:
                self.logger.warning(f"자금 예약 이전 실패: {e}")

    async def place_sell_order(self: 'OrderManagerBase', stock_code: str, quantity: int, price: float,
                              timeout_seconds: int = None, market: bool = False,
                              force: bool = False) -> Optional[str]:
        """매도 주문 실행

        Args:
            force: True이면 시간대 검사를 건너뜀 (EOD 청산 등)
        """
        try:
            timeout_seconds = timeout_seconds or self.config.order_management.sell_timeout_seconds

            self.logger.info(f"매도 주문 시도: {stock_code} {quantity}주 @{price:,.0f}원 (타임아웃: {timeout_seconds}초, 시장가: {market}, force: {force})")

            # 장 시간 체크: 동시호가 등 주문 불가 시간대 차단 (force=True이면 건너뛰기 — EOD 청산 등)
            if not force:
                from config.market_hours import MarketHours
                if not MarketHours.can_place_order():
                    phase = MarketHours.get_market_phase()
                    self.logger.warning(f"매도 주문 차단: 주문 불가 시간대 ({phase.value if hasattr(phase, 'value') else phase}) - {stock_code}")
                    return None

            # VI/서킷브레이커 체크: 시장 전체 거래 중단 시 주문 차단
            # (종목 VI 시 매도는 허용 — 보유 포지션 청산 기회를 막으면 안 됨)
            from config.market_hours import get_circuit_breaker_state
            cb_state = get_circuit_breaker_state()
            if cb_state.is_market_halted():
                self.logger.warning(f"매도 주문 차단: 시장 전체 서킷브레이커 발동 중 ({stock_code})")
                return None

            # 중복 주문 방지: 동일 종목 매도 주문이 이미 진행 중인지 확인
            if self.has_active_sell_order(stock_code):
                existing_order_id = self._active_sell_stocks.get(stock_code)
                self.logger.warning(f"중복 매도 주문 방지: {stock_code} (기존 주문: {existing_order_id})")
                return None

            # 가상매매 모드: 즉시 체결로 시뮬레이션
            if getattr(self.config, "paper_trading", False):
                return await self._execute_paper_sell_order(stock_code, quantity, price, market)

            # 실전 매매 모드: API 호출
            return await self._execute_real_sell_order(stock_code, quantity, price, timeout_seconds, market)

        except Exception as e:
            self.logger.error(f"매도 주문 예외: {e}")
            return None

    async def _execute_paper_sell_order(self: 'OrderManagerBase', stock_code: str, quantity: int,
                                        price: float, market: bool) -> Optional[str]:
        """가상매매 매도 주문 처리"""
        fake_order_id = f"VT-SELL-{stock_code}-{int(now_kst().timestamp())}"
        order = Order(
            order_id=fake_order_id,
            stock_code=stock_code,
            order_type=OrderType.SELL,
            price=price,
            quantity=quantity,
            timestamp=now_kst(),
            status=OrderStatus.FILLED,
            remaining_quantity=0
        )
        self.completed_orders.append(order)
        order_type_str = '시장가' if market else '지정가'
        self.logger.info(f"(가상) 매도 체결: {fake_order_id} - {stock_code} {quantity}주 @{price:,.0f}원 ({order_type_str})")

        # DB에 가상매매 기록 저장 (매도)
        await self._save_paper_sell_to_db(stock_code, quantity, price)

        # 알림 및 콜백
        await self._notify_order_filled(order)
        await self._trigger_order_filled_callback(order)

        return fake_order_id

    async def _execute_real_sell_order(self: 'OrderManagerBase', stock_code: str, quantity: int,
                                       price: float, timeout_seconds: int, market: bool) -> Optional[str]:
        """실전 매도 주문 처리"""
        from api.kis_api_manager import OrderResult
        from utils.price_utils import round_to_tick

        # API 호출을 별도 스레드에서 실행 (타임아웃 20초)
        result: OrderResult = await run_with_timeout(
            self.executor,
            self.broker.place_sell_order,
            stock_code, quantity, int(round_to_tick(price)) if not market else 0, ("01" if market else "00"),
            timeout_seconds=35, default=None
        )

        if not result:
            self.logger.error(f"매도 주문 API 타임아웃: {stock_code}")
            return None

        if result.success:
            # 종목명 조회
            stock_name = self._get_stock_name(stock_code)

            order = Order(
                order_id=result.order_id,
                stock_code=stock_code,
                order_type=OrderType.SELL,
                price=price,
                quantity=quantity,
                timestamp=now_kst(),
                status=OrderStatus.PENDING,
                remaining_quantity=quantity,
                stock_name=stock_name
            )

            # 미체결 관리에 추가
            self.pending_orders[result.order_id] = order
            self.order_timeouts[result.order_id] = now_kst() + timedelta(seconds=timeout_seconds)

            # 중복 주문 방지 맵에 등록
            self._register_active_order(stock_code, result.order_id, OrderType.SELL)

            order_type_str = '시장가' if market else '지정가'
            self.logger.info(f"매도 주문 성공: {result.order_id} - {stock_code}({stock_name}) {quantity}주 @{price:,.0f}원 ({order_type_str})")

            # 텔레그램 알림
            if self.telegram:
                await self.telegram.notify_order_placed({
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'order_type': 'sell_market' if market else 'sell',
                    'quantity': quantity,
                    'price': price,
                    'order_id': result.order_id
                })

            return result.order_id
        else:
            self.logger.error(f"매도 주문 실패: {result.message}")
            return None

    async def cancel_order(self: 'OrderManagerBase', order_id: str) -> bool:
        """주문 취소"""
        try:
            if order_id not in self.pending_orders:
                self.logger.warning(f"취소할 주문을 찾을 수 없음: {order_id}")
                return False

            order = self.pending_orders[order_id]
            self.logger.info(f"주문 취소 시도: {order_id} ({order.stock_code})")

            from api.kis_api_manager import OrderResult

            # 원주문의 주문구분 전달 (시장가 "01", 지정가 "00")
            order_dvsn = "00"  # 기본 지정가
            if order.price == 0:  # price=0이면 시장가로 추정
                order_dvsn = "01"

            # API 호출을 별도 스레드에서 실행 (타임아웃 20초)
            result: OrderResult = await run_with_timeout(
                self.executor,
                self.broker.cancel_order,
                order_id, order.stock_code, order_dvsn,
                timeout_seconds=35, default=None
            )

            if not result:
                self.logger.error(f"주문 취소 API 타임아웃: {order_id}")
                return False

            if result.success:
                order.status = OrderStatus.CANCELLED
                self._move_to_completed(order_id)
                self.logger.info(f"주문 취소 성공: {order_id}")

                # 텔레그램 알림
                if self.telegram:
                    await self.telegram.notify_order_cancelled({
                        'stock_code': order.stock_code,
                        'stock_name': f'Stock_{order.stock_code}',
                        'order_type': order.order_type.value
                    }, "사용자 요청")

                return True
            else:
                self.logger.error(f"주문 취소 실패: {order_id} - {result.message}")
                return False

        except Exception as e:
            self.logger.error(f"주문 취소 예외: {order_id} - {e}")
            return False

    async def _check_price_adjustment(self: 'OrderManagerBase', order_id: str) -> None:
        """가격 정정 검토"""
        try:
            if order_id not in self.pending_orders:
                return

            order = self.pending_orders[order_id]

            # 최대 정정 횟수 체크
            if order.adjustment_count >= self.config.order_management.max_adjustments:
                return

            # 현재가 조회 (타임아웃 20초)
            price_data = await run_with_timeout(
                self.executor,
                self.broker.get_current_price,
                order.stock_code,
                timeout_seconds=35, default=None
            )

            if not price_data:
                return

            current_price = price_data.current_price

            # 정정 로직
            should_adjust = False
            new_price = order.price

            if order.order_type == OrderType.BUY:
                # 매수: 현재가가 주문가보다 0.5% 이상 높으면 정정
                if current_price > order.price * 1.005:
                    new_price = current_price * 1.001  # 현재가 + 0.1%
                    should_adjust = True
            else:  # SELL
                # 매도: 현재가가 주문가보다 0.5% 이상 낮으면 정정
                if current_price < order.price * 0.995:
                    new_price = current_price * 0.999  # 현재가 - 0.1%
                    should_adjust = True

            if should_adjust:
                await self._adjust_order_price(order_id, new_price)

        except Exception as e:
            self.logger.error(f"가격 정정 검토 실패 {order_id}: {e}")

    async def _adjust_order_price(self: 'OrderManagerBase', order_id: str, new_price: float) -> None:
        """주문 가격 정정"""
        try:
            if order_id not in self.pending_orders:
                return

            order = self.pending_orders[order_id]
            old_price = order.price

            self.logger.info(f"가격 정정 시도: {order_id} {old_price:,.0f}원 -> {new_price:,.0f}원")

            # 기존 주문 취소 후 새 주문 생성 방식
            # (KIS API는 정정 API가 복잡하므로 취소 후 재주문으로 구현)
            cancel_success = await self.cancel_order(order_id)

            if cancel_success:
                # 새 주문 생성
                if order.order_type == OrderType.BUY:
                    new_order_id = await self.place_buy_order(
                        order.stock_code,
                        order.remaining_quantity,
                        new_price
                    )
                else:
                    new_order_id = await self.place_sell_order(
                        order.stock_code,
                        order.remaining_quantity,
                        new_price
                    )

                if new_order_id:
                    # 정정 횟수 증가
                    new_order = self.pending_orders[new_order_id]
                    new_order.adjustment_count = order.adjustment_count + 1
                    self.logger.info(f"가격 정정 완료: {new_order_id}")
                    # TradingStockManager의 현재 주문ID를 신규 주문ID로 동기화
                    try:
                        if self.trading_manager is not None:
                            self.trading_manager.update_current_order(order.stock_code, new_order_id)
                    except Exception as sync_err:
                        self.logger.warning(f"주문ID 동기화 실패({order.stock_code}): {sync_err}")

        except Exception as e:
            self.logger.error(f"가격 정정 실패 {order_id}: {e}")

    # ==================== 헬퍼 메서드 ====================

    def _get_stock_name(self: 'OrderManagerBase', stock_code: str) -> str:
        """종목명 조회"""
        stock_name = f'Stock_{stock_code}'
        if self.trading_manager:
            trading_stock = self.trading_manager.get_trading_stock(stock_code)
            if trading_stock:
                stock_name = trading_stock.stock_name
        return stock_name

    async def _save_paper_buy_to_db(self: 'OrderManagerBase', stock_code: str, quantity: int,
                                    price: float, target_profit_rate: float,
                                    stop_loss_rate: float) -> None:
        """가상매매 매수 DB 저장"""
        if not self.db_manager:
            return

        try:
            stock_name = self._get_stock_name(stock_code)

            # 목표 익절/손절률 조회 (파라미터 우선, 없으면 trading_stock에서 조회)
            if target_profit_rate is None or stop_loss_rate is None:
                if self.trading_manager:
                    trading_stock = self.trading_manager.get_trading_stock(stock_code)
                    if trading_stock:
                        if target_profit_rate is None:
                            target_profit_rate = trading_stock.target_profit_rate
                        if stop_loss_rate is None:
                            stop_loss_rate = trading_stock.stop_loss_rate

            buy_record_id = self.db_manager.save_virtual_buy(
                stock_code=stock_code,
                stock_name=stock_name,
                price=price,
                quantity=quantity,
                strategy="리밸런싱",
                reason="퀀트 포트폴리오",
                target_profit_rate=target_profit_rate,
                stop_loss_rate=stop_loss_rate
            )
            if buy_record_id:
                self.logger.info(f"가상매매 기록 저장 완료: {stock_code} (ID: {buy_record_id})")
            else:
                self.logger.warning(f"가상매매 기록 저장 실패: {stock_code}")
        except Exception as db_err:
            self.logger.error(f"가상매매 DB 저장 오류: {db_err}")

    async def _save_paper_sell_to_db(self: 'OrderManagerBase', stock_code: str, quantity: int, price: float) -> None:
        """가상매매 매도 DB 저장"""
        if not self.db_manager:
            return

        try:
            stock_name = self._get_stock_name(stock_code)

            # 매수 기록 ID 조회 (손익 계산용)
            buy_record_id = None
            if self.trading_manager:
                trading_stock = self.trading_manager.get_trading_stock(stock_code)
                if trading_stock and hasattr(trading_stock, '_virtual_buy_record_id'):
                    buy_record_id = trading_stock._virtual_buy_record_id

            # buy_record_id가 없으면 DB에서 조회
            if not buy_record_id and self.db_manager:
                buy_record_id = self.db_manager.get_last_open_virtual_buy(stock_code, quantity)
                if buy_record_id:
                    self.logger.debug(f"{stock_code} 매수 기록 ID 조회: {buy_record_id}")

            success = self.db_manager.save_virtual_sell(
                stock_code=stock_code,
                stock_name=stock_name,
                price=price,
                quantity=quantity,
                strategy="리밸런싱",
                reason="포트폴리오 조정",
                buy_record_id=buy_record_id
            )
            if success:
                self.logger.info(f"가상매도 기록 저장 완료: {stock_code}")
            else:
                self.logger.warning(f"가상매도 기록 저장 실패: {stock_code}")
        except Exception as db_err:
            self.logger.error(f"가상매도 DB 저장 오류: {db_err}")

    async def _notify_order_filled(self: 'OrderManagerBase', order: Order) -> None:
        """체결 알림 전송"""
        if self.telegram:
            await self.telegram.notify_order_filled({
                'stock_code': order.stock_code,
                'stock_name': f'Stock_{order.stock_code}',
                'order_type': order.order_type.value,
                'quantity': order.quantity,
                'price': order.price
            })

    async def _trigger_order_filled_callback(self: 'OrderManagerBase', order: Order) -> None:
        """TradingStockManager에 체결 콜백 전달"""
        if self.trading_manager:
            try:
                await self.trading_manager.on_order_filled(order)
            except Exception as callback_err:
                self.logger.error(f"(가상) 체결 콜백 오류: {callback_err}")
