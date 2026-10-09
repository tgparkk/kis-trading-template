"""
주문 타임아웃 처리 모듈
- 5분 시간 기반 타임아웃
- 3분봉 4개 기반 타임아웃 (매수 주문)
- 부분 체결 타임아웃 처리
- 취소 재시도
"""
import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from ..models import OrderType, OrderStatus
from utils.korean_time import now_kst
from utils.async_helpers import run_with_timeout
from config.constants import (
    ORDER_CANCEL_MAX_RETRIES, ORDER_CANCEL_RETRY_INTERVAL,
    ORDER_TIMEOUT_DEFER_SECONDS, ORDER_TIMEOUT_DEFER_MAX, ORDER_CANCEL_SETTLE_WAIT_SECONDS,
    COMMISSION_RATE, SECURITIES_TAX_RATE,
)
from .order_executor import coerce_order_result

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

            # 취소는 접수됐지만 체결수량을 못 본 주문(리뷰 중요2) — 재조회로만 종결한다
            if order_id in self._cancel_confirmed_ids:
                await self._resolve_cancel_confirmed(order_id)
                return

            order = self.pending_orders[order_id]
            elapsed_time = (now_kst() - order.timestamp).total_seconds()
            # 취소 성공 시 cancel_order 의 _move_to_completed 가 연기 횟수를 지우므로 미리 잡아 둔다(N3)
            prior_defers = self._timeout_defer_counts.get(order_id, 0)
            deferred_before = prior_defers > 0
            self.logger.warning(f"5분 타임아웃 처리: {order_id} ({order.stock_code}) "
                              f"- 경과시간: {elapsed_time:.0f}초"
                              f"{' (종결 연기 뒤 재처리)' if deferred_before else ''}")

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

            # 타임아웃 텔레그램 알림 (종결 연기 뒤 재처리면 반복 발송하지 않음)
            if self.telegram and not deferred_before:
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
                # 사전 조회~취소 사이 일부 체결(B5 경합)·재조회 실패 처리(리뷰 중요2)
                if await self._account_fill_after_cancel(saved_order, prior_defers):
                    return
            else:
                self.logger.error(f"타임아웃 취소 최종 실패: {order_id}")
                # 취소 최종 실패 시 API 재확인
                await self._check_order_status(order_id)
                if order_id in self.pending_orders:
                    # 여전히 미체결이면 강제 정리 + 수동 확인 알림.
                    # 재확인 조회가 «실패»면 강제 정리는 닫지 않고 연기한다(리뷰 중요1) → 경보는 닫을 때만.
                    closed = await self._force_timeout_cleanup(order_id)
                    if closed and self.telegram:
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
            # 종결 연기 중·취소 접수 확인 주문은 시간 타임아웃 경로가 맡는다(4봉 조건은 계속
            # 참이라 여기서 매 루프 취소를 다시 시도하지 않게 — 리뷰 중요1·2)
            if order_id in self._cancel_confirmed_ids or self._timeout_defer_counts.get(order_id):
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
                # 사전 조회~취소 사이 일부 체결(B5 경합)·재조회 실패 처리(리뷰 중요2)
                if await self._account_fill_after_cancel(saved_order):
                    return
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
                    closed = await self._force_4candle_timeout_cleanup(order_id)
                    if closed and self.telegram:
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
        if order_id in getattr(self, '_cancel_confirmed_ids', ()):
            return True  # 이미 KIS 가 취소를 접수한 주문(체결수량 재조회 대기 중)
        for attempt in range(max_retries):
            cancel_success = await self.cancel_order(order_id)
            if cancel_success:
                return True
            self.logger.warning(f"주문 취소 재시도 {attempt + 1}/{max_retries}: {order_id}")
            await asyncio.sleep(ORDER_CANCEL_RETRY_INTERVAL)
        return False

    async def _cancel_remaining_only(self: 'OrderManagerBase', order_id: str,
                                     attempts: int = ORDER_CANCEL_MAX_RETRIES) -> bool:
        """잔여 주문 취소 API만 호출 (pending_orders 상태 변경 없이)

        _cancel_with_retry()는 내부적으로 cancel_order()를 호출하고,
        cancel_order()가 성공하면 _move_to_completed()로 pending_orders에서 제거합니다.
        부분 체결 타임아웃 처리에서는 이후에 직접 _move_to_completed()를 호출해야 하므로,
        이 메서드는 순수하게 broker API를 통한 잔여 수량 취소만 수행합니다.
        attempts(기본 ORDER_CANCEL_MAX_RETRIES) 횟수만큼 시도합니다(I1 재전송은 1).
        """
        for attempt in range(attempts):
            try:
                order = self.pending_orders.get(order_id)
                if not order:
                    return False
                order_dvsn = "01" if order.price == 0 else "00"
                result = coerce_order_result(await run_with_timeout(
                    self.executor, self.broker.cancel_order,
                    order_id, order.stock_code, order_dvsn,
                    timeout_seconds=35, default=None
                ))
                if result and result.success:
                    self.logger.info(f"잔여 주문 취소 API 성공: {order_id} (시도 {attempt + 1}/{attempts})")
                    return True
                elif result:
                    self.logger.warning(f"잔여 주문 취소 API 실패: {order_id} (시도 {attempt + 1}/{attempts}) - {result.message}")
                else:
                    self.logger.warning(f"잔여 주문 취소 API 타임아웃: {order_id} (시도 {attempt + 1}/{attempts})")
            except Exception as e:
                self.logger.warning(f"잔여 주문 취소 API 예외: {order_id} (시도 {attempt + 1}/{attempts}) - {e}")
            if attempt < attempts - 1:
                await asyncio.sleep(ORDER_CANCEL_RETRY_INTERVAL)
        return False

    async def _handle_partial_fill_timeout(self: 'OrderManagerBase', order_id: str, order, filled_qty: int,
                                           cancel_done: bool = False) -> None:
        """부분 체결 상태에서 타임아웃 처리

        cancel_done: 잔량 취소가 이미 KIS 에 접수된 경우(취소 성공 뒤 재조회로 체결분을
            발견 — 리뷰 중요2). 취소 API 를 다시 부르지 않고 «취소 성공» 으로 회계한다.
        """
        # 1. 잔여 주문 취소 (pending_orders 상태 변경 없이 API만 호출, 재시도 포함)
        # _cancel_with_retry 대신 _cancel_remaining_only 사용:
        # _cancel_with_retry → cancel_order → _move_to_completed 로 pending_orders에서 제거되어
        # 이후 _move_to_completed 재호출 시 order가 없어지는 이중 호출 버그 방지
        cancel_success = True if cancel_done else await self._cancel_remaining_only(order_id)

        if cancel_success and not cancel_done:
            # N1·N2(2026-10-08): 잔량 취소 접수 직후 수량은 «최종»이 아니다 — 사전조회~취소 사이 추가
            # 체결분까지 확정 재조회로 보고 max(사전조회, 확정 체결수)로 회계한다. 확정 전이면 확인 표식 +
            # 연기(이후 _resolve_cancel_confirmed 가 취소 API 재호출 없이 이어받는다).
            self._cancel_confirmed_ids.add(order_id)
            settled, status = await self._settle_after_cancel(order_id, just_cancelled=True)
            if settled is None:
                await self._defer_or_close_unsettled(order, status, "잔량 취소 접수 뒤 체결수량 미확정")
                if order_id in self.pending_orders and order_id not in self._cancel_held_ids:
                    # I2 작은 보호책(REVIEW_RF7 · 2026-10-09): 확정 대기(연기) 동안 아는 체결분은 장부·손절 밖이다 —
                    # 회계는 건드리지 않고 사람이 그 창을 알게 텔레그램 1회(이 분기는 주문당 1번만 온다)
                    known = max(filled_qty, self._cancel_seen_fill.get(order_id, 0))
                    msg = (f"부분체결 {known}/{order.quantity}주 확정 대기(최대 약 4분) — 그동안 장부·손절 밖 · "
                           f"급변 시 HTS: {order.stock_code} 주문 {order_id}")
                    self.logger.warning(f"⏸ {msg}")
                    if self.telegram:
                        try:
                            await self.telegram.notify_system_status(msg)
                        except Exception:
                            pass
                return
            self._cancel_confirmed_ids.discard(order_id)
            if settled > filled_qty:
                self.logger.warning(
                    f"⚠️ 잔량 취소 직전 추가 체결 감지: {order_id} ({order.stock_code}) "
                    f"사전조회 {filled_qty}주 → 확정 {settled}주"
                )
            await self._close_cancelled_with_fill(order, max(filled_qty, settled), status)
            return

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
                    # 매매 손익을 total_funds와 available_funds에 반영 (수수료/세금 포함 —
                    # 전량 체결 경로와 동일 산식. 누락 시 equity 과대계상. 사전-실전 감사 #12)
                    buy_commission = buy_cost * COMMISSION_RATE
                    sell_commission = sell_amount * COMMISSION_RATE
                    sell_tax = sell_amount * SECURITIES_TAX_RATE
                    pnl = sell_amount - buy_cost - buy_commission - sell_commission - sell_tax
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

        # 보유 레지스트리·슬롯 갱신에 쓸 owner — 완전 체결 경로(order_monitor
        # _handle_full_fill)와 같은 원천(«체결 시점 소유 슬롯»의 owner_strategy_name).
        # 종전엔 owner 없이 add_position 해 (code, None) 엔트리가 생겼고, 이후 매도의
        # owner 지정 제거와 짝이 안 맞아 엔트리가 잔류했다(NEW-B1 동반 · F5, 2026-10-04).
        # B1(취소 성공 오판) 때문에 이 분기는 지금까지 도달 0 이었다 — B1 수정으로 처음 산다.
        _owner_slot = self._get_owned_trading_stock(order)
        order_owner = (
            getattr(_owner_slot, 'owner_strategy_name', '') or ''
        ).strip() or None

        if self.fund_manager:
            try:
                actual_amount = filled_price * filled_qty
                self.fund_manager.confirm_order(order_id, actual_amount)
                self.fund_manager.add_position(order.stock_code, order_owner)
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
                # strategy=슬롯 owner — 종목코드 단독 조회로 남의 슬롯을 집지 않게(F5).
                await self.trading_manager.on_partial_fill_timeout(
                    order, filled_qty, filled_price, strategy=order_owner)
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

    async def _force_timeout_cleanup(self: 'OrderManagerBase', order_id: str) -> bool:
        """타임아웃 시 강제 상태 정리 (체결 재확인 후 처리).

        Returns:
            True = TIMEOUT 으로 닫았다(호출자가 「수동 확인 필요」 경보) ·
            False = 닫지 않았다(그새 체결 확인 · 또는 재확인 조회 실패로 종결 연기).
        """
        if order_id in self.pending_orders:
            order = self.pending_orders[order_id]

            # C2 fix: TIMEOUT 처리 전 체결 여부 한 번 더 확인
            checked = True
            try:
                checked = await self._check_order_status(order_id)
                if order_id not in self.pending_orders:
                    self.logger.info(f"강제정리 전 체결 확인됨: {order_id} ({order.stock_code})")
                    return False
            except Exception as check_err:
                checked = False
                self.logger.warning(
                    f"⚠️ 강제정리 전 체결 재확인 실패: {order_id} ({order.stock_code}) - {check_err}. "
                    f"증권사에서 실제 체결되었을 수 있음! "
                    f"종목={order.stock_code}, 수량={order.quantity}주, "
                    f"유형={'매수' if order.order_type == OrderType.BUY else '매도'} "
                    f"→ 다음 장 시작 시 잔고 동기화로 확인 필요"
                )

            # 리뷰 중요1(2026-10-04): 재확인 조회가 «실패»(CB OPEN 중 체결조회 차단 등)면
            # 체결 여부를 모르는 채 닫지 않는다 — 닫으면 체결된 주문이 손절 없는 고아가 된다.
            if checked is False and self._defer_timeout_close(order_id, "강제정리 전 체결 재확인 조회 실패"):
                return False
            if checked is False:
                self._log_defer_exhausted(order_id, order)

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
            return True
        return False

    async def _force_4candle_timeout_cleanup(self: 'OrderManagerBase', order_id: str) -> bool:
        """3분봉 타임아웃 시 강제 상태 정리 (체결 재확인 후 처리) — 반환값은 _force_timeout_cleanup 과 같다."""
        if order_id in self.pending_orders:
            order = self.pending_orders[order_id]

            # C2 fix: TIMEOUT 처리 전 체결 여부 한 번 더 확인
            checked = True
            try:
                checked = await self._check_order_status(order_id)
                if order_id not in self.pending_orders:
                    self.logger.info(f"3분봉 강제정리 전 체결 확인됨: {order_id} ({order.stock_code})")
                    return False
            except Exception as check_err:
                checked = False
                self.logger.warning(
                    f"⚠️ 3분봉 강제정리 전 체결 재확인 실패: {order_id} ({order.stock_code}) - {check_err}. "
                    f"증권사에서 실제 체결되었을 수 있음! "
                    f"종목={order.stock_code}, 수량={order.quantity}주, "
                    f"유형={'매수' if order.order_type == OrderType.BUY else '매도'} "
                    f"→ 다음 장 시작 시 잔고 동기화로 확인 필요"
                )

            # 리뷰 중요1: 재확인 조회 실패면 닫지 않고 연기(이후는 시간 타임아웃 경로가 맡는다)
            if checked is False and self._defer_timeout_close(order_id, "3분봉 강제정리 전 체결 재확인 조회 실패"):
                return False
            if checked is False:
                self._log_defer_exhausted(order_id, order)

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
            return True
        return False

    # ==================== 종결 연기 · 취소 후 체결 재조회 (2026-10-04 리뷰 중요1·2) ====================

    def _defer_timeout_close(self: 'OrderManagerBase', order_id: str, reason: str) -> bool:
        """체결 여부를 모르는 주문의 종결을 연기한다. 연기했으면 True, 상한을 넘었으면 False."""
        count = self._timeout_defer_counts.get(order_id, 0)
        if count >= ORDER_TIMEOUT_DEFER_MAX:
            return False
        self._timeout_defer_counts[order_id] = count + 1
        self.order_timeouts[order_id] = now_kst() + timedelta(seconds=ORDER_TIMEOUT_DEFER_SECONDS)
        self.logger.warning(
            f"⏸ 주문 종결 연기 {count + 1}/{ORDER_TIMEOUT_DEFER_MAX}: {order_id} — {reason} · "
            f"{ORDER_TIMEOUT_DEFER_SECONDS}초 뒤 재확인(체결 여부를 모르는 채 닫지 않음)"
        )
        return True

    def _log_defer_exhausted(self: 'OrderManagerBase', order_id: str, order) -> None:
        self.logger.error(
            f"🚨 주문 종결 연기 {ORDER_TIMEOUT_DEFER_MAX}회 소진 — 체결 여부 확인 불가 상태로 종결: "
            f"{order_id} ({order.stock_code} {order.quantity}주) · HTS 수동 확인 필요"
        )

    @staticmethod
    def _parse_int(value) -> int:
        try:
            return int(str(value).replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            return 0

    async def _query_order_status_once(self: 'OrderManagerBase', order_id: str):
        """체결 재조회 1회 — dict(조회 성공) 또는 None(조회 실패·타임아웃·예외)."""
        try:
            return await run_with_timeout(
                self.executor, self.broker.get_order_status, order_id,
                timeout_seconds=10, default=None
            )
        except Exception as e:
            self.logger.warning(f"취소 후 체결 재조회 예외 {order_id}: {e}")
            return None

    def _reopen_after_cancel(self: 'OrderManagerBase', order, prior_defers: int = 0) -> bool:
        """cancel_order 가 CANCELLED 로 닫은 주문을 pending 으로 되돌린다(예약도 복원).

        취소 직후 재조회에서 체결분을 발견했거나(→ 부분체결 회계) 체결수량이 확정되지 않았을 때
        (→ 종결 연기) 쓴다. 매수 예약은 cancel_order 의 _move_to_completed 가 이미 풀었으므로
        같은 금액(주문가×주문수량)으로 다시 잡는다 — 이후 confirm_order 가 체결분만 투자로 옮긴다.
        prior_defers: 취소 전 경로 A(조회 실패) 연기 횟수 — _move_to_completed 가 지운 것을
            이어받아 합산 상한(ORDER_TIMEOUT_DEFER_MAX)을 지킨다(N3 · 2026-10-08).

        Returns:
            False = 매수 예약 복원 실패(호출자가 텔레그램 경보 — N5/m5 · 2026-10-09) · 그 밖엔 True.
        """
        order_id = order.order_id
        reserve_ok = True
        if order_id not in self.pending_orders:
            if order in self.completed_orders:
                self.completed_orders.remove(order)
            order.status = OrderStatus.PENDING
            self.pending_orders[order_id] = order
            self._register_active_order(order.stock_code, order_id, order.order_type)
            if (order.order_type == OrderType.BUY and self.fund_manager
                    and not self.fund_manager.has_reservation(order_id)):
                if not self.fund_manager.reserve_funds(order_id, order.price * order.quantity):
                    reserve_ok = False
                    self.logger.critical(
                        f"🚨 취소 후 재개 주문 예약 복원 실패: {order_id} ({order.stock_code}) — "
                        f"자금 장부 수동 확인 필요"
                    )
        # N3: 경로 A 연기 횟수를 이어받는다(취소 성공이 횟수를 1부터 다시 세게 만들지 않게)
        if prior_defers > self._timeout_defer_counts.get(order_id, 0):
            self._timeout_defer_counts[order_id] = prior_defers
        self.order_timeouts[order_id] = now_kst() + timedelta(seconds=ORDER_TIMEOUT_DEFER_SECONDS)
        return reserve_ok

    async def _alert_reserve_restore_failed(self: 'OrderManagerBase', order) -> None:
        """N5/m5(2026-10-09): 재개 주문 예약 복원 실패 텔레그램 — 주문당 1회(N4 「경보 1회」와 같은 방식).

        예약이 없으면 이후 confirm_order 가 「예약되지 않은 주문」으로 아무것도 안 해 투자금이 과소·가용이
        과대로 남는다(장부 자동 보정 없음 — 사람이 대조).
        """
        order_id = order.order_id
        if order_id in self._reserve_restore_alerted_ids:
            return
        self._reserve_restore_alerted_ids.add(order_id)
        if self.telegram:
            try:
                await self.telegram.notify_system_status(
                    f"취소 후 재개 주문 예약 복원 실패 - 자금 장부 수동 확인 필요: {order.stock_code} 주문 "
                    f"{order_id} · {order.price * order.quantity:,.0f}원(체결분 투자금이 장부에 안 잡힐 수 있음)"
                )
            except Exception:
                pass

    def _settled_fill_candidate(self: 'OrderManagerBase', status):
        """취소 접수 뒤 조회 1회가 «확정 후보»면 그 체결수(tot_ccld_qty), 아니면 None (N2·N6 · 2026-10-08).

        후보 = 8036R(정정취소가능)에 없음 ∧ 0081R 원주문 행 rmn_qty == 0 — broker 가 _status='executed'
        로 준 행. 조회 실패(None)·불명(status_unknown, B3: 불명 ≠ 미체결)·8036R 잔존(_status='pending',
        취소 미반영)·rmn_qty>0(잔량이 남아 보임 · 중요3 꼴)은 후보가 아니다.
        cncl_yn·cncl_cfrm_qty 는 보지 않는다 — 10-08 실측: 취소 접수 +2초에 ''·'0'(채워지는 시점 모름).
        """
        if not isinstance(status, dict) or status.get('status_unknown'):
            return None
        if status.get('_status') != 'executed':
            return None
        if self._parse_int(status.get('rmn_qty', 0)) > 0:
            return None
        return self._parse_int(status.get('tot_ccld_qty', 0))

    async def _settle_after_cancel(self: 'OrderManagerBase', order_id: str, just_cancelled: bool):
        """취소 접수 뒤 체결수량 «확정» 판정 (N2 · 2026-10-08).

        확정 = 확정 후보(_settled_fill_candidate)가 연속 2회(간격 ≥ ORDER_CANCEL_SETTLE_WAIT_SECONDS)
        같은 체결수를 줄 때. 취소 직후(just_cancelled)면 첫 조회 전에도 기다린다(실측: 0~2초 미관측).
        직전 연기 때 본 후보가 있으면 그것을 첫 회로 센다(연기 폭 45초 ≥ 대기). 후보가 아닌 조회가
        끼면 연속이 끊긴다.

        Returns:
            (확정 체결수 | None, 마지막 조회 결과) — None 이면 미확정(호출자가 연기).
        """
        prev = self._cancel_settle_obs.pop(order_id, None)
        status = None
        for i in range(1 if prev is not None else 2):
            if just_cancelled or i > 0:
                await asyncio.sleep(ORDER_CANCEL_SETTLE_WAIT_SECONDS)
            status = await self._query_order_status_once(order_id)
            if self._still_cancellable(status):
                self._cancel_lingering_seen_ids.add(order_id)   # N-1: 취소 접수 뒤 8036R 관측
            if isinstance(status, dict) and not status.get('status_unknown'):
                fill = self._parse_int(status.get('tot_ccld_qty', 0))   # s-2: 8036R·0081R 행 체결수 기억
                if fill > self._cancel_seen_fill.get(order_id, 0):
                    self._cancel_seen_fill[order_id] = fill
            seen = self._settled_fill_candidate(status)
            if seen is None:
                return None, status
            if prev is not None and seen == prev:
                return seen, status
            prev = seen
        self._cancel_settle_obs[order_id] = prev
        return None, status

    async def _account_fill_after_cancel(self: 'OrderManagerBase', order, prior_defers: int = 0) -> bool:
        """취소 «성공» 직후 체결수량 확정 재조회(리뷰 중요2 · N2 · B1 수정으로 생긴 «경보 없는 고아» 차단).

        사전 조회(체결 0)~취소 사이 1~2초에 일부가 체결되면, 종전엔 CANCELLED·예약 전액
        해제·슬롯 COMPLETED 로 닫혀 체결 주식이 장부·손절 밖에 남았다.

        Returns:
            True  = 이 함수가 주문을 맡았다(체결분 회계로 전환 · 또는 체결수량 미확정으로 종결 연기)
                    → 호출자는 «미체결 취소» 후처리(슬롯 COMPLETED)를 하지 않는다.
            False = 체결 0 확정(연속 2회) → 종전 취소 후처리 그대로.
        """
        order_id = order.order_id
        settled, status = await self._settle_after_cancel(order_id, just_cancelled=True)
        if settled == 0:
            return False
        if not self._reopen_after_cancel(order, prior_defers):
            await self._alert_reserve_restore_failed(order)
        if settled is None:
            await self._defer_or_close_unsettled(order, status, "취소 접수 뒤 체결수량 미확정")
            return True
        self.logger.warning(
            f"⚠️ 취소 직전 일부 체결 감지: {order_id} ({order.stock_code}) {settled}/{order.quantity}주 "
            f"— 체결분 회계로 전환"
        )
        await self._account_cancelled_fill(order, settled, status)
        return True

    async def _account_cancelled_fill(self: 'OrderManagerBase', order, filled: int, status) -> None:
        """취소가 접수된 주문의 체결분을 부분체결 타임아웃 회계로 처리한다(취소 API 재호출 없음)."""
        order.filled_quantity = filled
        raw_avg = status.get('avg_prvs', '') if isinstance(status, dict) else ''
        try:
            avg = float(str(raw_avg or 0).replace(',', '').strip() or 0)
        except (ValueError, TypeError, AttributeError):
            avg = 0.0
        if avg > 0:
            order.filled_price = avg
        await self._handle_partial_fill_timeout(order.order_id, order, filled, cancel_done=True)

    async def _close_cancelled_with_fill(self: 'OrderManagerBase', order, filled: int, status) -> None:
        """취소 접수 주문을 종결한다 — 체결분이 있으면 부분체결 회계, 없으면 CANCELLED + 슬롯 통보."""
        if filled > 0:
            await self._account_cancelled_fill(order, filled, status)
            return
        order.status = OrderStatus.CANCELLED
        self._move_to_completed(order.order_id)
        self.logger.info(f"취소 접수 주문 종결(체결 0): {order.order_id} ({order.stock_code})")
        await self._notify_trading_manager_timeout_with_order(order)

    @staticmethod
    def _still_cancellable(status) -> bool:
        """조회 결과가 8036R(정정취소가능) 행 = 취소가 아직 반영되지 않은 주문(I1 · 2026-10-08)."""
        return (isinstance(status, dict) and not status.get('status_unknown')
                and status.get('_status') == 'pending')

    @staticmethod
    def _executed_row_still_open(status) -> bool:
        """0081R 행(_status='executed')인데 잔량>0 — 8036R «조회 실패»일 수 있는 꼴(W-1 · 2026-10-09).

        broker.get_order_status 는 8036R 조회만 실패하고 0081R 이 성공하면 None 이 아니라 0081R 행을
        _status='executed' 로 준다(framework/broker.py) — «8036R 에 없음»과 «8036R 조회 실패»가 갈리지 않는다.
        체결수는 보지 않는다(F3): 보류(lingering)는 호출자가 «아는 체결 0»을 따로 요구하고, 체결>0 이면 m-c
        «잔량 취소 미반영» 문구로 간다.
        """
        if not isinstance(status, dict) or status.get('status_unknown') or status.get('_status') != 'executed':
            return False
        return OrderTimeoutMixin._parse_int(status.get('rmn_qty', 0)) > 0

    async def _defer_or_close_unsettled(self: 'OrderManagerBase', order, status, reason: str) -> None:
        """체결수량 미확정 — 확인 표식 + 연기. 상한 소진이면 「수동 확인」 경보와 함께 아는 만큼으로 종결
        (B3: 불명 ≠ 미체결 — 경보 없이 체결 0 으로 닫지 않는다).

        I1(2026-10-08): 소진 때 아는 체결 0 인데 마지막 조회가 여전히 8036R 행이면 매수는 CANCELLED 로 닫지 않는다 —
        예약·슬롯·확인 표식을 둔 채 자동 처리를 멈추고(시한 제거 · 재취소 없음 · 종료 시 미체결 일괄
        취소 대상으로 남음) 「수동 확인」 경보 1회. 아는 체결분이 있으면 회계는 종전 그대로.
        B(2026-10-09): 보류 주문은 «상태 조회만» 계속한다(_cancel_held_ids → _recheck_held_order).
        델타 리뷰 A: 보류는 매수만 — 매도는 종전처럼 닫아 슬롯을 «보유 중»으로 돌린다(손절·장마감 청산 대상
        유지) + 「매도 취소 미반영」 경보 1회. m-a: 취소 재전송 전이면 곧장 보류·종결하지 않고 상한 예외로
        연기 1회 더 — 다음 재처리(_resolve_cancel_confirmed)가 재전송 1회를 보낸다(예외는 별도 표식으로 주문당 1회).
        N-1: 취소 접수 뒤 8036R 에서 본 적 있는 주문은 이번 조회가 실패(None)여도 «8036R 잔존»으로 취급한다
        (조회 실패 ≠ 체결 0 확정 · 아는 체결분이 있으면 종전 회계 그대로).
        W-1(2026-10-09): 같은 주문이 8036R 조회만 실패하고 0081R 행(체결 0 ∧ 잔량>0)으로 와도 None 과 같이 취급한다.
        """
        order_id = order.order_id
        self._cancel_confirmed_ids.add(order_id)
        if self._defer_timeout_close(order_id, reason):
            return
        seen = self._parse_int(status.get('tot_ccld_qty', 0)) if isinstance(status, dict) else 0
        # s-2(2026-10-09): 취소 뒤 조회에서 본 최대 체결수(8036R 행 포함)도 «아는 체결»이다 — 마지막 조회가
        # 실패(None)여도 잊지 않는다.
        known = max(getattr(order, 'filled_quantity', 0) or 0, seen,
                    self._cancel_settle_obs.pop(order_id, 0),
                    self._cancel_seen_fill.get(order_id, 0))
        seen_lingering = order_id in self._cancel_lingering_seen_ids
        remainder_open = self._still_cancellable(status) or (seen_lingering and (
            status is None or self._executed_row_still_open(status)))
        lingering = known == 0 and remainder_open
        basis = ("8036R 잔존" if self._still_cancellable(status)
                 else "8036R 관측 뒤 조회 실패" if status is None
                 else "8036R 관측 뒤 0081R 잔량 잔존")
        if (lingering and order_id not in self._cancel_resent_ids
                and order_id not in self._defer_extra_used_ids):
            self._defer_extra_used_ids.add(order_id)
            self.order_timeouts[order_id] = now_kst() + timedelta(seconds=ORDER_TIMEOUT_DEFER_SECONDS)
            self.logger.warning(
                f"⏸ 주문 종결 연기 상한 예외 1회: {order_id} ({order.stock_code}) — {basis} · 취소 재전송 전 · "
                f"{ORDER_TIMEOUT_DEFER_SECONDS}초 뒤 재처리에서 재전송 1회"
            )
            return
        hold = lingering and order.order_type == OrderType.BUY
        spent = f"연기 {ORDER_TIMEOUT_DEFER_MAX}회 소진" + (
            "(+예외 1)" if order_id in self._defer_extra_used_ids else "")
        if hold:
            self.order_timeouts.pop(order_id, None)
            # B(2026-10-09): 보류 주문은 취소·연기 없이 «상태 조회만» 계속한다 → 체결·소멸 발견 시 종결
            self._cancel_held_ids.add(order_id)
            self.logger.error(
                f"🚨 주문 종결 {spent} — 취소 미반영({basis}): {order_id} "
                f"({order.stock_code} {order.quantity}주) · 종결하지 않고 예약·슬롯 유지 · "
                f"상태 재조회 계속(체결·소멸 발견 시 종결) · HTS 수동 확인 필요"
            )
            # s-1: 텔레그램에도 근거(8036R 잔존 | 관측 뒤 조회 실패 | 관측 뒤 0081R 잔량 잔존)를 싣는다
            # N5: 재개 때 예약 복원이 실패했으면 «예약 유지»가 아니다
            kept = self.fund_manager is None or self.fund_manager.has_reservation(order_id)
            alert = (f"주문 취소 미반영({basis}) - 수동 확인 필요 · "
                     f"{'예약 유지' if kept else '예약 없음(복원 실패)'}: {order.stock_code} 주문 {order_id}")
        elif lingering:
            self.logger.error(
                f"🚨 주문 종결 {spent} — 매도 취소 미반영({basis}): {order_id} "
                f"({order.stock_code} {order.quantity}주) · 종결하고 슬롯 «보유 중» 복귀 · HTS 확인 필요"
            )
            alert = f"매도 취소 미반영({basis}) — HTS 확인: {order.stock_code} 주문 {order_id}"
        elif remainder_open:
            # m-c: 아는 체결분은 회계하지만 잔량 취소가 반영되지 않은 꼴 — 일반 「확인 불가」 문구와 가른다
            self.logger.error(
                f"🚨 주문 종결 {spent} — 잔량 취소 미반영({basis}): {order_id} "
                f"({order.stock_code} 체결 {known}/{order.quantity}주) · 아는 체결분 회계 · HTS 수동 확인 필요"
            )
            alert = (f"잔량 취소 미반영({basis}) - 수동 확인 필요 · 체결 {known}주 회계: "
                     f"{order.stock_code} 주문 {order_id}")
        else:
            self._log_defer_exhausted(order_id, order)
            alert = f"주문 취소 후 체결수량 확인 불가 - 수동 확인 필요: {order.stock_code} 주문 {order_id}"
        if self.telegram:
            try:
                await self.telegram.notify_system_status(alert)
            except Exception:
                pass
        if hold:
            return
        self._cancel_confirmed_ids.discard(order_id)
        await self._close_cancelled_with_fill(order, known, status)

    async def _resolve_cancel_confirmed(self: 'OrderManagerBase', order_id: str) -> None:
        """취소는 접수됐지만 체결수량이 확정되지 않은 주문 — 확정 재조회로 종결(미확정이면 연기,
        상한 소진 시 경보 후 종결). 체결수 = max(사전조회 체결수, 확정 체결수)(N1)."""
        order = self.pending_orders.get(order_id)
        if order is None:
            self._cancel_confirmed_ids.discard(order_id)
            return
        settled, status = await self._settle_after_cancel(order_id, just_cancelled=False)
        if (settled is None and self._still_cancellable(status)
                and order_id not in self._cancel_resent_ids):
            # I1(🔒 사장님 10-08): 연기 뒤에도 8036R 에 살아 있다 — 확인 표식을 풀고 취소를 딱 1회 재전송
            # (주문당 1회 · 실패해도 다시 안 보냄) → 접수되면 다시 대기 + 연속 2회 규칙. 연기 합산 상한은 그대로.
            self._cancel_resent_ids.add(order_id)
            self._cancel_confirmed_ids.discard(order_id)
            resent = await self._cancel_remaining_only(order_id, attempts=1)
            self.logger.warning(
                f"🔁 취소 미반영(8036R 잔존) — 취소 재전송 1회 {'접수' if resent else '실패'}: "
                f"{order_id} ({order.stock_code})"
            )
            if resent:
                settled, status = await self._settle_after_cancel(order_id, just_cancelled=True)
        if settled is None:
            await self._defer_or_close_unsettled(order, status, "취소 접수 뒤 체결수량 미확정")
            return
        filled = max(getattr(order, 'filled_quantity', 0) or 0, settled)
        if (filled < order.quantity and order.order_type == OrderType.BUY
                and order_id in self._cancel_lingering_seen_ids):
            # F1(2026-10-09 · W-1 과 같은 뿌리): 취소 뒤 8036R 에서 본 매수는 «0081R 잔량 0» 만으로 닫지 않는다 —
            # 8036R 단독 조회로 부재를 확인한 뒤에만 예약을 푼다(조회 실패·목록 잔존이면 미확정으로 연기).
            absent, row = await self._confirm_absent_from_8036r(order_id)
            if not absent:
                await self._defer_or_close_unsettled(
                    order, row, f"8036R 단독 확인 {'실패' if row is None else '잔존'} — 체결수량 미확정")
                return
        self._cancel_confirmed_ids.discard(order_id)
        await self._close_cancelled_with_fill(order, filled, status)

    async def _confirm_absent_from_8036r(self: 'OrderManagerBase', order_id: str):
        """«8036R(정정취소가능)에 그 주문이 없다»를 8036R 단독 조회(broker.get_pending_orders)로 적극 확인 — F1(2026-10-09).

        broker.get_order_status 는 8036R 조회가 «실패»해도 0081R 행이 있으면 _status='executed' 로 준다
        (framework/broker.py) — «8036R 에 없음»과 «8036R 조회 실패»가 같은 모양이다. 살아 있는 주문의 0081R
        rmn_qty 값은 미실측(PROBE_RESULT_1008)이라, 예약을 푸는 종결 직전에만 1콜로 다시 확인한다.

        Returns:
            (True, None)  = 목록 조회 성공 ∧ 그 ODNO 없음 → 종결해도 된다
            (False, row)  = 목록에 그 ODNO 가 있다(row = 그 행 + _status='pending')
            (False, None) = 목록 조회 실패(None·예외·목록 아님)
        """
        try:
            rows = await run_with_timeout(
                self.executor, self.broker.get_pending_orders, timeout_seconds=10, default=None)
        except Exception as e:
            self.logger.warning(f"8036R 단독 확인 예외 {order_id}: {e}")
            rows = None
        if not isinstance(rows, list):
            self.logger.warning(f"⏸ 8036R 단독 확인 실패 — 종결 보류: {order_id}")
            return False, None
        for r in rows:
            if isinstance(r, dict) and str(r.get('odno', '')).strip() == str(order_id).strip():
                row = dict(r)
                row['_status'] = 'pending'
                self.logger.warning(f"⏸ 8036R 단독 확인 — 아직 정정취소가능 목록에 있음 · 종결 보류: {order_id}")
                return False, row
        return True, None

    async def _alert_held_fill_once(self: 'OrderManagerBase', order) -> None:
        """보류 주문에 체결이 보이는데(취소 뒤 본 체결수 > 0) 아직 회계하지 못할 때 「보류 주문에 체결」 경보 — 주문당 1회."""
        order_id = order.order_id
        live_fill = self._cancel_seen_fill.get(order_id, 0)
        if live_fill <= 0 or order_id in self._held_fill_alerted_ids:
            return
        self._held_fill_alerted_ids.add(order_id)
        msg = (f"보류 주문에 체결 {live_fill}/{order.quantity}주 보임(미확정) — 체결분 장부·손절 밖 · "
               f"HTS 확인: {order.stock_code} 주문 {order_id}")
        self.logger.error(f"🚨 {msg}")
        if self.telegram:
            try:
                await self.telegram.notify_system_status(msg)
            except Exception:
                pass

    async def _recheck_held_order(self: 'OrderManagerBase', order_id: str) -> None:
        """보류 주문(취소 미반영으로 예약·슬롯을 둔 매수) 상태 재조회 — 델타 리뷰 B(2026-10-09).

        보류 = 취소·재전송·연기를 멈춘 상태다. 여기서도 취소는 다시 보내지 않고 «상태 조회만» 한다
        (메인 루프 1회당 조회 1회 · 확정 후보가 보이면 연속 2회 규칙 = _settle_after_cancel).
        - 확정(8036R 부재 ∧ 0081R 잔량 0 이 연속 2회 같은 체결수) → 종결 + 「보류 주문 해소」 텔레그램 1회:
          전량 체결 = 정상 완전 체결 경로(_handle_full_fill: 예약→투자 · 보유 등록 · 전략 콜백 · 손절/익절 감시 ·
          DB · 체결 알림) · 일부 체결 = 부분체결 회계(체결분 포지션 · 나머지 예약 해제) · 체결 0 = CANCELLED ·
          예약 해제 · 슬롯 COMPLETED.
        - 미확정(8036R 잔존 · 조회 실패 · 불명 · 잔량>0 · 불일치 · 확정 후보지만 8036R 부재 미확인) → 보류 유지.
          그 사이 체결이 보이면 「보류 주문에 체결」 경보 1회(주문이 끝나지 않아 회계하지 않는다 — 체결분은 아직
          장부·손절 밖).
        - F1: 전량 체결이 아닌 종결(예약 해제가 따르는 것)은 8036R 단독 조회로 부재를 확인한 뒤에만.
        """
        order = self.pending_orders.get(order_id)
        if order is None:
            self._cancel_held_ids.discard(order_id)
            return
        settled, status = await self._settle_after_cancel(order_id, just_cancelled=False)
        if settled is None:
            await self._alert_held_fill_once(order)
            return
        filled = max(getattr(order, 'filled_quantity', 0) or 0, settled)
        if filled < order.quantity:
            # F1(2026-10-09): 보류 주문은 «취소 뒤에도 살아 있었다»는 증거가 있는 주문이다 — 0081R «잔량 0» 연속
            # 2회만으로 예약을 풀지 않고 8036R 단독 조회로 부재를 확인한다(실패·잔존이면 보류 유지).
            absent, row = await self._confirm_absent_from_8036r(order_id)
            if not absent:
                if row is not None:
                    fill = self._parse_int(row.get('tot_ccld_qty', 0))
                    if fill > self._cancel_seen_fill.get(order_id, 0):
                        self._cancel_seen_fill[order_id] = fill
                # F2: 이번 확정 후보를 남겨 다음 루프는 조회 1회·대기 0 으로 다시 본다(매 루프 2초 정지 반복 방지)
                self._cancel_settle_obs[order_id] = settled
                # D1: 확정 후보로 처음 보인 부분 체결도 8036R 부재 미확인이면 아직 장부·손절 밖 — 같은 경보 1회
                await self._alert_held_fill_once(order)
                return
        self._cancel_held_ids.discard(order_id)
        self._cancel_confirmed_ids.discard(order_id)
        if filled >= order.quantity:
            await self._handle_full_fill(order_id, order, status, order.quantity)
            if order_id in self.pending_orders:
                # 완전 체결 판정 보류(체결가 0 등) — 보류로 되돌려 다음 루프에 다시 본다(시간·4봉 타임아웃의
                # 재취소 경로로 빠지지 않게)
                self._cancel_held_ids.add(order_id)
                self._cancel_confirmed_ids.add(order_id)
                self._cancel_settle_obs[order_id] = settled   # F2: 다음 루프 조회 1회·대기 0
                return
            outcome = f"전량 체결 {order.quantity}주 회계"
        else:
            await self._close_cancelled_with_fill(order, filled, status)
            outcome = f"체결 {filled}주 회계 · 나머지 예약 해제" if filled else "체결 0 · 예약 해제"
        note = ""
        if filled > 0:
            # F7(2026-10-09): 장마감 일괄청산 시각 뒤에 체결로 풀리면 그날 청산을 지나 밤을 넘길 수 있다 — 경보에 적는다
            try:
                from config.market_hours import MarketHours
                if MarketHours.is_eod_liquidation_time('KRX', now_kst()):
                    note = (" · ⚠️ 장마감 일괄청산 시각 뒤 체결 — 이 보유는 밤을 넘길 수 있음 · "
                            "다음 날 장 시작 매도·손절 확인")
            except Exception:
                pass
        msg = f"보류 주문 해소({outcome}): {order.stock_code} 주문 {order_id}{note}"
        self.logger.warning(f"✅ {msg}")
        if self.telegram:
            try:
                await self.telegram.notify_system_status(msg)
            except Exception:
                pass

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
