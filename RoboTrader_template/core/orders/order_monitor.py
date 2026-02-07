"""
주문 모니터링 로직 모듈
- 미체결 주문 상태 확인
- 체결 확인 및 처리
- 오탐지 복구
"""
import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from ..models import OrderType, OrderStatus
from utils.korean_time import now_kst, is_market_open
from utils.async_helpers import run_with_timeout
from config.constants import MARKET_CLOSED_WAIT_INTERVAL, ORDER_MONITOR_INTERVAL, ORDER_MONITOR_ERROR_INTERVAL

if TYPE_CHECKING:
    from .order_base import OrderManagerBase


class OrderMonitorMixin:
    """주문 모니터링 관련 메서드들을 모아둔 Mixin 클래스"""

    async def start_monitoring(self: 'OrderManagerBase'):
        """미체결 주문 모니터링 시작"""
        self.is_monitoring = True
        self.logger.info("주문 모니터링 시작")

        while self.is_monitoring:
            try:
                if not is_market_open():
                    await asyncio.sleep(MARKET_CLOSED_WAIT_INTERVAL)  # 장 마감 시 1분 대기
                    continue

                await self._monitor_pending_orders()
                await asyncio.sleep(ORDER_MONITOR_INTERVAL)  # 3초마다 체크 (체결 빠른 확인)

            except Exception as e:
                self.logger.error(f"주문 모니터링 중 오류: {e}")
                await asyncio.sleep(ORDER_MONITOR_ERROR_INTERVAL)

    async def _monitor_pending_orders(self: 'OrderManagerBase'):
        """미체결 주문 모니터링"""
        current_time = now_kst()
        orders_to_process = list(self.pending_orders.keys())

        if orders_to_process:
            self.logger.debug(f"미체결 주문 모니터링: {len(orders_to_process)}건 처리 중 ({current_time.strftime('%H:%M:%S')})")

        # 오탐지 복구: 최근 완료된 주문 중 실제 미체결인 것 확인
        await self._check_false_positive_filled_orders(current_time)

        for order_id in orders_to_process:
            try:
                order = self.pending_orders[order_id]
                timeout_time = self.order_timeouts.get(order_id)

                # 주문 상세 정보 로깅 (디버깅용)
                elapsed_seconds = (current_time - order.timestamp).total_seconds()
                remaining_seconds = (timeout_time - current_time).total_seconds() if timeout_time else 0
                self.logger.debug(f"주문 {order_id} ({order.stock_code}): "
                                f"경과 {elapsed_seconds:.0f}초, 남은시간 {remaining_seconds:.0f}초")

                # 1. 체결 상태 확인
                await self._check_order_status(order_id)

                # 주문이 처리되었으면 더 이상 확인하지 않음
                if order_id not in self.pending_orders:
                    continue

                # 2. 타임아웃 체크 (5분 기준)
                if timeout_time and current_time > timeout_time:
                    self.logger.info(f"시간 기반 타임아웃 감지: {order_id} ({order.stock_code}) "
                                   f"- 경과시간: {(current_time - order.timestamp).total_seconds():.0f}초")
                    await self._handle_timeout(order_id)
                    continue  # 취소된 주문은 더 이상 처리하지 않음

                # 2-1. 매수 주문의 4분봉 체크 (4봉 후 취소)
                if order.order_type == OrderType.BUY and order.order_3min_candle_time:
                    if self._has_4_candles_passed(order.order_3min_candle_time):
                        await self._handle_4candle_timeout(order_id)
                        continue  # 취소된 주문은 더 이상 처리하지 않음

                # 3. 가격 변동 시 정정 검토 (비활성화)
                # await self._check_price_adjustment(order_id)

            except Exception as e:
                self.logger.error(f"주문 모니터링 중 오류 {order_id}: {e}")

    async def _check_false_positive_filled_orders(self: 'OrderManagerBase', current_time):
        """오탐지된 체결 주문 복구 (매수 30분, 매도 10분 이내 완료된 주문 확인)"""
        try:
            if not self.completed_orders:
                return

            # 30초 주기 제한 (API 부하 방지)
            if hasattr(self, '_last_false_positive_check') and self._last_false_positive_check:
                if (current_time - self._last_false_positive_check).total_seconds() < 30:
                    return
            self._last_false_positive_check = current_time

            # 최근 20건, 매수는 30분/매도는 10분 이내 완료된 주문 확인
            recent_completed = [
                order for order in self.completed_orders[-20:]
                if order.status == OrderStatus.FILLED
                and (
                    (order.order_type == OrderType.BUY and
                     (current_time - order.timestamp).total_seconds() <= 1800)
                    or
                    (order.order_type == OrderType.SELL and
                     (current_time - order.timestamp).total_seconds() <= 600)
                )
            ]

            if not recent_completed:
                return

            self.logger.debug(f"오탐지 복구 체크: 최근 완료된 {len(recent_completed)}건 확인")

            for order in recent_completed:
                # API에서 실제 상태 재확인 (타임아웃 10초)
                status_data = await run_with_timeout(
                    self.executor,
                    self.api_manager.get_order_status,
                    order.order_id,
                    timeout_seconds=10, default=None
                )

                if status_data:
                    # 실제로는 미체결인지 확인
                    try:
                        filled_qty = int(str(status_data.get('tot_ccld_qty', 0)).replace(',', '').strip() or 0)
                        remaining_qty = int(str(status_data.get('rmn_qty', 0)).replace(',', '').strip() or 0)
                        is_actual_unfilled = bool(status_data.get('actual_unfilled', False))
                        cancelled = status_data.get('cncl_yn', 'N')

                        # 오탐지 감지: 체결로 처리했지만 실제로는 미체결
                        if (filled_qty == 0 or remaining_qty > 0 or is_actual_unfilled) and cancelled != 'Y':
                            self.logger.warning(f"체결 오탐지 감지: {order.order_id} ({order.stock_code})")
                            self.logger.warning(f"   - 실제 상태: 체결={filled_qty}, 잔여={remaining_qty}, 미체결={is_actual_unfilled}")

                            # pending_orders로 복구
                            await self._restore_false_positive_order(order, current_time)

                    except Exception as parse_err:
                        self.logger.debug(f"오탐지 체크 파싱 오류 {order.order_id}: {parse_err}")

        except Exception as e:
            self.logger.error(f"오탐지 복구 체크 오류: {e}")

    async def _restore_false_positive_order(self: 'OrderManagerBase', order, current_time):
        """오탐지된 주문을 pending_orders로 복구"""
        try:
            # completed_orders에서 제거
            if order in self.completed_orders:
                self.completed_orders.remove(order)

            # pending_orders로 복구
            order.status = OrderStatus.PENDING
            self.pending_orders[order.order_id] = order

            # 타임아웃 재설정 (남은 시간 계산)
            elapsed_seconds = (current_time - order.timestamp).total_seconds()
            remaining_timeout = max(30, 180 - elapsed_seconds)  # 최소 30초는 남겨둠
            self.order_timeouts[order.order_id] = current_time + timedelta(seconds=remaining_timeout)

            self.logger.warning(f"오탐지 주문 복구: {order.order_id} ({order.stock_code}) "
                              f"- 남은 타임아웃: {remaining_timeout:.0f}초")

            # 텔레그램 알림
            if self.telegram:
                await self.telegram.notify_system_status(
                    f"오탐지 복구: {order.stock_code} 주문 {order.order_id} 복구됨"
                )

        except Exception as e:
            self.logger.error(f"오탐지 주문 복구 실패 {order.order_id}: {e}")

    async def _check_order_status(self: 'OrderManagerBase', order_id: str):
        """주문 상태 확인"""
        try:
            if order_id not in self.pending_orders:
                return

            order = self.pending_orders[order_id]

            # API 호출을 별도 스레드에서 실행 (타임아웃 10초)
            status_data = await run_with_timeout(
                self.executor,
                self.api_manager.get_order_status,
                order_id,
                timeout_seconds=10, default=None
            )

            if status_data:
                # 원본 데이터 로깅 (체결 판단 오류 디버깅용)
                self.logger.info(f"주문 상태 원본 데이터 [{order_id}]:\n"
                               f"  - tot_ccld_qty(체결수량): {status_data.get('tot_ccld_qty')}\n"
                               f"  - rmn_qty(잔여수량): {status_data.get('rmn_qty')}\n"
                               f"  - ord_qty(주문수량): {status_data.get('ord_qty')}\n"
                               f"  - cncl_yn(취소여부): {status_data.get('cncl_yn')}\n"
                               f"  - actual_unfilled: {status_data.get('actual_unfilled')}\n"
                               f"  - status_unknown: {status_data.get('status_unknown')}")

                await self._process_order_status(order_id, order, status_data)

        except Exception as e:
            self.logger.error(f"주문 상태 확인 실패 {order_id}: {e}")

    async def _process_order_status(self: 'OrderManagerBase', order_id: str, order, status_data: dict):
        """주문 상태 데이터 처리"""
        # 방어적 파싱 (쉼표/공백 등 제거)
        try:
            filled_qty = int(str(status_data.get('tot_ccld_qty', 0)).replace(',', '').strip() or 0)
        except Exception:
            filled_qty = 0
        try:
            remaining_qty = int(str(status_data.get('rmn_qty', 0)).replace(',', '').strip() or 0)
        except Exception:
            remaining_qty = 0
        cancelled = status_data.get('cncl_yn', 'N')
        is_actual_unfilled = bool(status_data.get('actual_unfilled', False))
        is_status_unknown = bool(status_data.get('status_unknown', False))

        self.logger.info(f"파싱 결과 [{order_id}]: "
                       f"filled={filled_qty}, remaining={remaining_qty}, "
                       f"order_qty={order.quantity}, cancelled={cancelled}")

        # 상태 업데이트
        order.filled_quantity = filled_qty
        order.remaining_quantity = remaining_qty

        if cancelled == 'Y':
            order.status = OrderStatus.CANCELLED
            self._move_to_completed(order_id)
            self.logger.info(f"주문 취소 확인: {order_id}")
        elif is_status_unknown:
            # 상태 불명이 5분 이상 지속되면 타임아웃 처리
            elapsed_time = (now_kst() - order.timestamp).total_seconds()
            if elapsed_time > 300:  # 5분 = 300초
                self.logger.warning(f"주문 상태 불명 5분 초과로 타임아웃 처리: {order_id} - 경과: {elapsed_time:.0f}초")
                order.status = OrderStatus.TIMEOUT
                self._move_to_completed(order_id)
            else:
                # 5분 미만이면 판정 유보
                self.logger.warning(f"주문 상태 불명, 판정 유보: {order_id} - 경과: {elapsed_time:.0f}초 (5분 초과 시 타임아웃)")
        elif is_actual_unfilled:
            # 실제 미체결 플래그가 명시된 경우 대기 유지
            self.logger.debug(f"실제 미체결 상태: {order_id} - 잔여 {remaining_qty}")
        elif remaining_qty == 0 and filled_qty == order.quantity and filled_qty > 0:
            # 완전 체결 확인
            await self._handle_full_fill(order_id, order, status_data, filled_qty)
        elif filled_qty > 0 and remaining_qty > 0:
            # 부분 체결 확인
            await self._handle_partial_fill(order_id, order, status_data, filled_qty, remaining_qty)
        else:
            # 그 외의 경우는 모두 미체결로 처리
            self.logger.debug(f"주문 대기 (미체결): {order_id} - 체결 {filled_qty}, 잔여 {remaining_qty}")

    async def _handle_full_fill(self: 'OrderManagerBase', order_id: str, order, status_data: dict, filled_qty: int):
        """완전 체결 처리"""
        # 초엄격 체결 확인 조건 (오탐지 방지 강화)
        # 1. 잔여수량 정확히 0
        # 2. 체결수량이 주문수량과 정확히 일치
        # 3. 체결수량이 0보다 큼
        # 4. actual_unfilled 플래그가 없음
        # 5. API 주문수량 일치 확인
        # 6. 취소 여부 재확인

        # 기본 검증
        if filled_qty != order.quantity:
            self.logger.warning(f"체결수량 불일치로 체결 판정 보류: 주문 {order.quantity}주, 체결 {filled_qty}주")
            return

        # API 응답의 주문수량 확인
        api_ord_qty = 0
        try:
            api_ord_qty = int(str(status_data.get('ord_qty', 0)).replace(',', '').strip() or 0)
        except (ValueError, TypeError) as e:
            self.logger.debug(f"API 주문수량 파싱 실패: {e}")

        if api_ord_qty > 0 and api_ord_qty != order.quantity:
            self.logger.warning(f"API 주문수량 불일치로 체결 판정 보류: 로컬 {order.quantity}주, API {api_ord_qty}주")
            return

        # 추가 안전 검증: 취소 여부 재확인
        cancelled = status_data.get('cncl_yn', 'N')
        if cancelled == 'Y':
            self.logger.warning(f"취소된 주문으로 체결 판정 보류: {order_id}")
            return

        # 추가 안전 검증: 실제 미체결 플래그 재확인
        is_actual_unfilled = bool(status_data.get('actual_unfilled', False))
        if is_actual_unfilled:
            self.logger.warning(f"실제 미체결 플래그로 체결 판정 보류: {order_id}")
            return

        # 실제 체결가 추출 (실전 매매용)
        filled_price = order.price  # 기본값: 주문가
        try:
            # avg_prvs(평균체결가) 또는 ccld_unpr(체결단가) 확인
            avg_prvs = status_data.get('avg_prvs', status_data.get('ccld_unpr', ''))
            if avg_prvs and str(avg_prvs).replace(',', '').strip():
                filled_price = float(str(avg_prvs).replace(',', '').strip())
                if filled_price != order.price:
                    slippage = filled_price - order.price
                    slippage_pct = (slippage / order.price) * 100
                    self.logger.info(f"실제 체결가: {filled_price:,.0f}원 (주문가 {order.price:,.0f}원, 슬리피지 {slippage:+,.0f}원/{slippage_pct:+.2f}%)")
        except (ValueError, TypeError) as e:
            self.logger.warning(f"체결가 파싱 오류: {e}, 주문가 사용")
            filled_price = order.price

        order.filled_price = filled_price
        order.status = OrderStatus.FILLED
        self._move_to_completed(order_id)
        self.logger.info(f"주문 완전 체결 확정: {order_id} ({order.stock_code}) - {filled_qty}주 @{filled_price:,.0f}원")

        # 실전 매매 시 DB에 거래 기록 저장
        await self._save_real_trade_to_db(order, filled_price)

        # TradingStockManager에 즉시 알림 (콜백)
        if self.trading_manager:
            try:
                self.logger.info(f"TradingStockManager에 체결 알림: {order_id}")
                await self.trading_manager.on_order_filled(order)
            except Exception as callback_err:
                self.logger.error(f"체결 콜백 오류: {callback_err}")

        # 텔레그램 체결 알림
        if self.telegram:
            await self.telegram.notify_order_filled({
                'stock_code': order.stock_code,
                'stock_name': order.stock_name or f'Stock_{order.stock_code}',
                'order_type': order.order_type.value,
                'quantity': order.quantity,
                'price': filled_price  # 실제 체결가 사용
            })

    async def _handle_partial_fill(self: 'OrderManagerBase', order_id: str, order, status_data: dict,
                                   filled_qty: int, remaining_qty: int):
        """부분 체결 처리"""
        if filled_qty + remaining_qty == order.quantity:
            order.status = OrderStatus.PARTIAL
            order.filled_quantity = filled_qty
            order.remaining_quantity = remaining_qty

            # 부분 체결가 추출
            partial_filled_price = order.price
            try:
                avg_prvs = status_data.get('avg_prvs', status_data.get('ccld_unpr', ''))
                if avg_prvs and str(avg_prvs).replace(',', '').strip():
                    partial_filled_price = float(str(avg_prvs).replace(',', '').strip())
            except (ValueError, TypeError):
                partial_filled_price = order.price

            self.logger.info(f"주문 부분 체결: {order_id} ({order.stock_code}) - "
                           f"{filled_qty}/{order.quantity}주 @{partial_filled_price:,.0f}원 (잔여 {remaining_qty}주)")

            # 부분 체결 시 텔레그램 알림
            if self.telegram:
                await self.telegram.notify_system_status(
                    f"부분 체결: {order.stock_code} {filled_qty}/{order.quantity}주 체결, {remaining_qty}주 미체결"
                )
        else:
            self.logger.warning(f"수량 불일치: 체결({filled_qty}) + 잔여({remaining_qty}) != 주문({order.quantity})")
