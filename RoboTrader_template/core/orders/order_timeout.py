"""
주문 타임아웃 처리 모듈
- 5분 시간 기반 타임아웃
- 3분봉 4개 기반 타임아웃 (매수 주문)
- 부분 체결 타임아웃 처리
- 취소 재시도
"""
import asyncio
from typing import TYPE_CHECKING

from ..models import OrderType, OrderStatus
from utils.korean_time import now_kst
from utils.async_helpers import run_with_timeout
from config.constants import ORDER_CANCEL_MAX_RETRIES, ORDER_CANCEL_RETRY_INTERVAL

if TYPE_CHECKING:
    from .order_base import OrderManagerBase


class OrderTimeoutMixin:
    """주문 타임아웃 처리 관련 메서드들을 모아둔 Mixin 클래스"""

    async def _handle_timeout(self: 'OrderManagerBase', order_id: str) -> None:
        """타임아웃 처리 (5분 기준)"""
        try:
            if order_id not in self.pending_orders:
                self.logger.warning(f"타임아웃 처리할 주문이 없음: {order_id}")
                return

            order = self.pending_orders[order_id]
            elapsed_time = (now_kst() - order.timestamp).total_seconds()
            self.logger.warning(f"5분 타임아웃 처리: {order_id} ({order.stock_code}) "
                              f"- 경과시간: {elapsed_time:.0f}초")

            # 취소 전 최종 상태 확인 (부분 체결 확인)
            await self._check_order_status(order_id)

            # 이미 완전 체결되었으면 타임아웃 처리 불필요
            if order_id not in self.pending_orders:
                self.logger.info(f"타임아웃 처리 중 완전 체결 확인: {order_id}")
                return

            # 부분 체결 확인
            order = self.pending_orders[order_id]
            filled_qty = getattr(order, 'filled_quantity', 0) or 0
            if filled_qty > 0 and filled_qty < order.quantity:
                self.logger.info(f"부분 체결 상태에서 타임아웃: {order_id} ({order.stock_code}) "
                               f"- {filled_qty}/{order.quantity}주 체결")
                await self._handle_partial_fill_timeout(order_id, order, filled_qty)
                return

            # 타임아웃 텔레그램 알림
            if self.telegram:
                order_type_str = "매수" if order.order_type == OrderType.BUY else "매도"
                await self.telegram.notify_system_status(
                    f"주문 타임아웃: {order.stock_code} {order_type_str} {order.quantity}주 @{order.price:,.0f}원 ({elapsed_time:.0f}초 경과)"
                )

            # 취소 전에 order 참조 저장 (_cancel이 pending_orders에서 제거할 수 있음)
            saved_order = order

            # 미체결 주문 취소 (재시도 포함)
            cancel_success = await self._cancel_with_retry(order_id)

            if cancel_success:
                self.logger.info(f"타임아웃 취소 성공: {order_id}")
            else:
                self.logger.error(f"타임아웃 취소 최종 실패: {order_id}")
                # 취소 최종 실패 시 API 재확인
                await self._check_order_status(order_id)
                if order_id in self.pending_orders:
                    # 여전히 미체결이면 강제 정리 + 수동 확인 알림
                    await self._force_timeout_cleanup(order_id)
                    if self.telegram:
                        await self.telegram.notify_system_status(
                            f"주문 취소 실패 - 수동 확인 필요: {saved_order.stock_code} 주문 {order_id}"
                        )

            # 취소 성공한 경우도 TradingStockManager에 알림 (상태 동기화)
            if cancel_success:
                await self._notify_trading_manager_timeout_with_order(saved_order)

        except Exception as e:
            self.logger.error(f"타임아웃 처리 실패 {order_id}: {e}")
            # 예외 발생 시에도 강제로 상태 정리
            await self._force_timeout_cleanup_safe(order_id)

    async def _handle_4candle_timeout(self: 'OrderManagerBase', order_id: str) -> None:
        """3분봉 기준 타임아웃 처리 (매수 주문 후 4봉 지나면 취소)"""
        try:
            if order_id not in self.pending_orders:
                return

            order = self.pending_orders[order_id]
            current_candle = self._get_current_3min_candle_time()

            self.logger.warning(f"매수 주문 4봉 타임아웃: {order_id} ({order.stock_code}) "
                              f"주문봉: {order.order_3min_candle_time.strftime('%H:%M') if order.order_3min_candle_time else 'N/A'} "
                              f"현재봉: {current_candle.strftime('%H:%M')}")

            # 취소 전 최종 상태 확인 (부분 체결 확인)
            await self._check_order_status(order_id)

            # 이미 완전 체결되었으면 타임아웃 처리 불필요
            if order_id not in self.pending_orders:
                self.logger.info(f"4봉 타임아웃 처리 중 완전 체결 확인: {order_id}")
                return

            # 부분 체결 확인
            order = self.pending_orders[order_id]
            filled_qty = getattr(order, 'filled_quantity', 0) or 0
            if filled_qty > 0 and filled_qty < order.quantity:
                self.logger.info(f"부분 체결 상태에서 4봉 타임아웃: {order_id} ({order.stock_code}) "
                               f"- {filled_qty}/{order.quantity}주 체결")
                await self._handle_partial_fill_timeout(order_id, order, filled_qty)
                return

            # 취소 전에 order 참조 저장 (_cancel이 pending_orders에서 제거할 수 있음)
            saved_order = order

            # 미체결 주문 취소 (재시도 포함)
            cancel_success = await self._cancel_with_retry(order_id)

            if cancel_success:
                # 텔레그램 알림 (기존 cancel_order에서 이미 알림이 발송되므로 추가 정보만 포함)
                if self.telegram:
                    await self.telegram.notify_order_cancelled({
                        'stock_code': saved_order.stock_code,
                        'stock_name': f'Stock_{saved_order.stock_code}',
                        'order_type': saved_order.order_type.value
                    }, "3분봉 4개 경과")
            else:
                # 4분봉 타임아웃 취소 최종 실패 시 API 재확인
                self.logger.error(f"4봉 타임아웃 취소 최종 실패: {order_id}")
                await self._check_order_status(order_id)
                if order_id in self.pending_orders:
                    await self._force_4candle_timeout_cleanup(order_id)
                    if self.telegram:
                        await self.telegram.notify_system_status(
                            f"주문 취소 실패 - 수동 확인 필요: {saved_order.stock_code} 주문 {order_id}"
                        )

            # 3분봉 타임아웃 취소 성공한 경우도 TradingStockManager에 알림
            if cancel_success:
                await self._notify_trading_manager_timeout_with_order(saved_order)

        except Exception as e:
            self.logger.error(f"3분봉 타임아웃 처리 실패 {order_id}: {e}")
            # 예외 발생 시에도 강제로 상태 정리
            await self._force_timeout_cleanup_safe(order_id)

    async def _cancel_with_retry(self: 'OrderManagerBase', order_id: str, max_retries: int = ORDER_CANCEL_MAX_RETRIES) -> bool:
        """재시도가 포함된 주문 취소"""
        for attempt in range(max_retries):
            cancel_success = await self.cancel_order(order_id)
            if cancel_success:
                return True
            self.logger.warning(f"주문 취소 재시도 {attempt + 1}/{max_retries}: {order_id}")
            await asyncio.sleep(ORDER_CANCEL_RETRY_INTERVAL)
        return False

    async def _cancel_remaining_only(self: 'OrderManagerBase', order_id: str) -> bool:
        """잔여 주문 취소 API만 호출 (pending_orders 상태 변경 없이)

        _cancel_with_retry()는 내부적으로 cancel_order()를 호출하고,
        cancel_order()가 성공하면 _move_to_completed()로 pending_orders에서 제거합니다.
        부분 체결 타임아웃 처리에서는 이후에 직접 _move_to_completed()를 호출해야 하므로,
        이 메서드는 순수하게 broker API를 통한 잔여 수량 취소만 수행합니다.
        ORDER_CANCEL_MAX_RETRIES 횟수만큼 재시도합니다.
        """
        for attempt in range(ORDER_CANCEL_MAX_RETRIES):
            try:
                order = self.pending_orders.get(order_id)
                if not order:
                    return False
                order_dvsn = "01" if order.price == 0 else "00"
                result = await run_with_timeout(
                    self.executor, self.broker.cancel_order,
                    order_id, order.stock_code, order_dvsn,
                    timeout_seconds=35, default=None
                )
                if result and result.success:
                    self.logger.info(f"잔여 주문 취소 API 성공: {order_id} (시도 {attempt + 1}/{ORDER_CANCEL_MAX_RETRIES})")
                    return True
                elif result:
                    self.logger.warning(f"잔여 주문 취소 API 실패: {order_id} (시도 {attempt + 1}/{ORDER_CANCEL_MAX_RETRIES}) - {result.message}")
                else:
                    self.logger.warning(f"잔여 주문 취소 API 타임아웃: {order_id} (시도 {attempt + 1}/{ORDER_CANCEL_MAX_RETRIES})")
            except Exception as e:
                self.logger.warning(f"잔여 주문 취소 API 예외: {order_id} (시도 {attempt + 1}/{ORDER_CANCEL_MAX_RETRIES}) - {e}")
            if attempt < ORDER_CANCEL_MAX_RETRIES - 1:
                await asyncio.sleep(ORDER_CANCEL_RETRY_INTERVAL)
        return False

    async def _handle_partial_fill_timeout(self: 'OrderManagerBase', order_id: str, order, filled_qty: int) -> None:
        """부분 체결 상태에서 타임아웃 처리"""
        # 1. 잔여 주문 취소 (pending_orders 상태 변경 없이 API만 호출, 재시도 포함)
        # _cancel_with_retry 대신 _cancel_remaining_only 사용:
        # _cancel_with_retry → cancel_order → _move_to_completed 로 pending_orders에서 제거되어
        # 이후 _move_to_completed 재호출 시 order가 없어지는 이중 호출 버그 방지
        cancel_success = await self._cancel_remaining_only(order_id)

        filled_price = getattr(order, 'filled_price', None) or order.price

        # 매도 부분 체결은 별도 경로로 처리
        if order.order_type == OrderType.SELL:
            self.logger.info(f"매도 부분 체결 타임아웃: {order.stock_code} {filled_qty}주 @{filled_price:,.0f}원")
            # FundManager: 매도 부분 체결분 자금 회수 (매수원가 기준 + 손익 반영)
            if self.fund_manager:
                try:
                    # 매수원가 조회 (fallback: 매도 주문가)
                    buy_cost_per_share = order.price
                    if self.trading_manager:
                        try:
                            ts = self.trading_manager.get_trading_stock(order.stock_code)
                            if ts and ts.position and ts.position.avg_price > 0:
                                buy_cost_per_share = ts.position.avg_price
                        except Exception:
                            pass
                    buy_cost = buy_cost_per_share * filled_qty
                    sell_amount = filled_price * filled_qty
                    self.fund_manager.release_investment(buy_cost, stock_code=order.stock_code)
                    # 매매 손익을 total_funds와 available_funds에 반영
                    pnl = sell_amount - buy_cost
                    if pnl != 0:
                        self.fund_manager.adjust_pnl(pnl)
                    self.logger.info(f"FundManager 매도 부분 체결 자금 회수: {order.stock_code} - 매수원가: {buy_cost:,.0f}원, 매도금: {sell_amount:,.0f}원, 손익: {pnl:+,.0f}원")
                except Exception as e:
                    self.logger.warning(f"FundManager 매도 부분 체결 자금 처리 실패: {order.stock_code} - {e}")
            if self.trading_manager and hasattr(self.trading_manager, 'on_sell_partial_fill_timeout'):
                try:
                    await self.trading_manager.on_sell_partial_fill_timeout(order, filled_qty, filled_price)
                except Exception as e:
                    self.logger.error(f"매도 부분 체결 처리 실패: {e}")

            # DB 기록 및 완료 처리
            original_qty = order.quantity
            order.original_quantity = order.quantity
            order.quantity = filled_qty
            order.filled_quantity = filled_qty
            order.status = OrderStatus.FILLED
            self._move_to_completed(order_id)
            await self._save_real_trade_to_db(order, filled_price)

            if self.telegram:
                await self.telegram.notify_system_status(
                    f"매도 부분 체결 타임아웃: {order.stock_code} "
                    f"{filled_qty}/{original_qty}주 매도, 잔여 취소"
                )
            return

        # 매수 부분 체결 처리
        # 2. 잔여 취소 성공 여부에 따라 FundManager 처리를 분기
        #    - 취소 실패 시: 잔여 주문이 나중에 체결될 수 있으므로 예약자금을 그대로 유지 (이중 처리 방지)
        #    - 취소 성공 시: 부분 체결 금액만 확정, 나머지 예약자금 환불
        if not cancel_success:
            # 취소 실패: 예약자금 유지, 수동 확인 필요 알림
            order_obj = self.pending_orders.get(order_id) or order
            msg = (
                f"매수 부분체결 잔여취소 실패 - 수동 확인 필요, 예약자금 유지: "
                f"주문 {order_id} 종목 {order_obj.stock_code} "
                f"체결 {filled_qty}주 / 전체 {order_obj.quantity}주"
            )
            self.logger.critical(msg)
            if self.telegram:
                try:
                    await self.telegram.notify_system_status(msg)
                except Exception:
                    pass
            # 예약자금 유지 상태로 pending에서만 제거 (FundManager 처리 건너뜀)
            order.original_quantity = order.quantity
            order.quantity = filled_qty
            order.filled_quantity = filled_qty
            order.status = OrderStatus.FILLED
            self._move_to_completed(order_id)
            await self._save_real_trade_to_db(order, filled_price)
            return

        if self.fund_manager:
            try:
                actual_amount = filled_price * filled_qty
                self.fund_manager.confirm_order(order_id, actual_amount)
                self.fund_manager.add_position(order.stock_code)
                self.logger.info(f"FundManager 매수 부분 체결 확정: {order_id} - {actual_amount:,.0f}원 ({filled_qty}주)")
            except Exception as e:
                # 자금 확정 실패: 루프 중단을 막기 위해 raise 하지 않고 CRITICAL 알림
                msg = f"FundManager 매수 부분 체결 확정 실패 - 수동 확인 필요: {order_id} 종목 {order.stock_code} - {e}"
                self.logger.critical(msg)
                if self.telegram:
                    try:
                        await self.telegram.notify_system_status(msg)
                    except Exception:
                        pass

        self.logger.info(f"부분 체결 포지션 등록: {order.stock_code} {filled_qty}주 @{filled_price:,.0f}원")

        if self.trading_manager and hasattr(self.trading_manager, 'on_partial_fill_timeout'):
            try:
                await self.trading_manager.on_partial_fill_timeout(order, filled_qty, filled_price)
            except Exception as e:
                self.logger.error(f"부분 체결 포지션 등록 실패: {e}")

        # 3. DB 기록
        original_qty = order.quantity
        order.original_quantity = order.quantity
        order.quantity = filled_qty
        order.filled_quantity = filled_qty
        order.status = OrderStatus.FILLED
        self._move_to_completed(order_id)
        await self._save_real_trade_to_db(order, filled_price)

        # 4. 텔레그램 알림
        if self.telegram:
            await self.telegram.notify_system_status(
                f"매수 부분 체결 타임아웃: {order.stock_code} "
                f"{filled_qty}/{original_qty}주 체결, 잔여 취소"
            )

    async def _force_timeout_cleanup(self: 'OrderManagerBase', order_id: str) -> None:
        """타임아웃 시 강제 상태 정리 (체결 재확인 후 처리)"""
        if order_id in self.pending_orders:
            order = self.pending_orders[order_id]

            # C2 fix: TIMEOUT 처리 전 체결 여부 한 번 더 확인
            try:
                await self._check_order_status(order_id)
                if order_id not in self.pending_orders:
                    self.logger.info(f"강제정리 전 체결 확인됨: {order_id} ({order.stock_code})")
                    return
            except Exception as check_err:
                self.logger.warning(
                    f"⚠️ 강제정리 전 체결 재확인 실패: {order_id} ({order.stock_code}) - {check_err}. "
                    f"증권사에서 실제 체결되었을 수 있음! "
                    f"종목={order.stock_code}, 수량={order.quantity}주, "
                    f"유형={'매수' if order.order_type == OrderType.BUY else '매도'} "
                    f"→ 다음 장 시작 시 잔고 동기화로 확인 필요"
                )

            order.status = OrderStatus.TIMEOUT  # 타임아웃 상태로 변경
            self._move_to_completed(order_id)
            self.logger.warning(
                f"타임아웃으로 인한 강제 상태 정리: {order_id} (PENDING -> TIMEOUT) "
                f"종목={order.stock_code}, 수량={order.quantity}주"
            )

            # TradingStockManager에 타임아웃 상황 알림
            if self.trading_manager and hasattr(self.trading_manager, 'handle_order_timeout'):
                try:
                    await self.trading_manager.handle_order_timeout(order)
                    self.logger.info(f"TradingStockManager 타임아웃 처리 완료: {order_id}")
                except Exception as notify_error:
                    self.logger.error(f"TradingStockManager 타임아웃 처리 실패: {notify_error}")

    async def _force_4candle_timeout_cleanup(self: 'OrderManagerBase', order_id: str) -> None:
        """3분봉 타임아웃 시 강제 상태 정리 (체결 재확인 후 처리)"""
        if order_id in self.pending_orders:
            order = self.pending_orders[order_id]

            # C2 fix: TIMEOUT 처리 전 체결 여부 한 번 더 확인
            try:
                await self._check_order_status(order_id)
                if order_id not in self.pending_orders:
                    self.logger.info(f"3분봉 강제정리 전 체결 확인됨: {order_id} ({order.stock_code})")
                    return
            except Exception as check_err:
                self.logger.warning(
                    f"⚠️ 3분봉 강제정리 전 체결 재확인 실패: {order_id} ({order.stock_code}) - {check_err}. "
                    f"증권사에서 실제 체결되었을 수 있음! "
                    f"종목={order.stock_code}, 수량={order.quantity}주, "
                    f"유형={'매수' if order.order_type == OrderType.BUY else '매도'} "
                    f"→ 다음 장 시작 시 잔고 동기화로 확인 필요"
                )

            order.status = OrderStatus.TIMEOUT
            self._move_to_completed(order_id)
            self.logger.warning(
                f"3분봉 타임아웃으로 인한 강제 상태 정리: {order_id} (PENDING -> TIMEOUT) "
                f"종목={order.stock_code}, 수량={order.quantity}주"
            )

            # TradingStockManager에 3분봉 타임아웃 상황 알림
            if self.trading_manager and hasattr(self.trading_manager, 'handle_order_timeout'):
                try:
                    await self.trading_manager.handle_order_timeout(order)
                    self.logger.info(f"TradingStockManager 3분봉 타임아웃 처리 완료: {order_id}")
                except Exception as notify_error:
                    self.logger.error(f"TradingStockManager 3분봉 타임아웃 처리 실패: {notify_error}")

    async def _force_timeout_cleanup_safe(self: 'OrderManagerBase', order_id: str) -> None:
        """예외 발생 시 안전한 강제 상태 정리"""
        try:
            if order_id in self.pending_orders:
                order = self.pending_orders[order_id]
                order.status = OrderStatus.TIMEOUT
                self._move_to_completed(order_id)
                self.logger.warning(f"예외 발생으로 인한 강제 상태 정리: {order_id}")
                # TradingStockManager에도 알림 시도 (BUY_PENDING/SELL_PENDING 고착 방지)
                if self.trading_manager and hasattr(self.trading_manager, 'handle_order_timeout'):
                    try:
                        await self.trading_manager.handle_order_timeout(order)
                    except Exception as inner_e:
                        self.logger.warning(
                            f"강제 정리 시 TradingStockManager 알림 실패: {inner_e}"
                        )
        except Exception as e:
            self.logger.debug(f"강제 상태 정리 중 오류: {order_id} - {e}")

    async def _notify_trading_manager_timeout_with_order(self: 'OrderManagerBase', order) -> None:
        """TradingStockManager에 타임아웃 알림 (order 객체 직접 전달)"""
        if self.trading_manager and hasattr(self.trading_manager, 'handle_order_timeout'):
            try:
                await self.trading_manager.handle_order_timeout(order)
                self.logger.info(f"TradingStockManager 취소 처리 완료: {order.stock_code}")
            except Exception as notify_error:
                self.logger.error(f"TradingStockManager 취소 처리 실패: {notify_error}")

    async def _notify_trading_manager_timeout(self: 'OrderManagerBase', order_id: str) -> None:
        """TradingStockManager에 타임아웃 알림"""
        if self.trading_manager and hasattr(self.trading_manager, 'handle_order_timeout'):
            try:
                order = self.pending_orders.get(order_id)
                if order:
                    await self.trading_manager.handle_order_timeout(order)
                    self.logger.info(f"TradingStockManager 취소 처리 완료: {order_id}")
            except Exception as notify_error:
                self.logger.error(f"TradingStockManager 취소 처리 실패: {notify_error}")

    async def _notify_trading_manager_4candle_timeout(self: 'OrderManagerBase', order_id: str) -> None:
        """TradingStockManager에 3분봉 타임아웃 알림"""
        if self.trading_manager and hasattr(self.trading_manager, 'handle_order_timeout'):
            try:
                order = self.pending_orders.get(order_id)
                if order:
                    await self.trading_manager.handle_order_timeout(order)
                    self.logger.info(f"TradingStockManager 3분봉 취소 처리 완료: {order_id}")
            except Exception as notify_error:
                self.logger.error(f"TradingStockManager 3분봉 취소 처리 실패: {notify_error}")
