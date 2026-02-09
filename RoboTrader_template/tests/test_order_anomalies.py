"""
주문 비정상 상황 테스트
======================
시나리오2 개발자B: 주문 비정상 상황에 대한 검증 테스트

테스트 시나리오:
1. 부분 체결 시 잔여 수량 처리
2. 중복 매수 시도 방지
3. 주문 거부 후 상태 복구
4. 미체결 타임아웃 → 자동 취소 → 자금 해제
5. 매도 중 에러 → 포지션 유지
"""
import tests._mock_modules  # noqa: F401

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from core.models import Order, OrderType, OrderStatus, TradingConfig
from core.order_manager import OrderManager
from core.fund_manager import FundManager
from utils.korean_time import now_kst


# ============================================================================
# 헬퍼
# ============================================================================

def _make_order_manager(paper_trading=False, api_manager=None, telegram=None, db_manager=None):
    """OrderManager 생성 헬퍼"""
    config = TradingConfig.from_json({
        'paper_trading': paper_trading,
        'order_management': {
            'buy_timeout_seconds': 180,
            'sell_timeout_seconds': 180,
        }
    })
    if api_manager is None:
        api_manager = Mock()
        api_manager.is_initialized = True
    if telegram is None:
        telegram = AsyncMock()
    if db_manager is None:
        db_manager = Mock()
        db_manager.save_virtual_buy.return_value = 1
        db_manager.save_virtual_sell.return_value = True
        db_manager.get_last_open_virtual_buy.return_value = None

    return OrderManager(config, api_manager, telegram, db_manager)


def _make_order_result(success=True, order_id="ORD-001", message=""):
    """OrderResult Mock"""
    r = Mock()
    r.success = success
    r.order_id = order_id
    r.message = message
    return r


def _inject_pending_order(om, order_id="ORD-001", stock_code="005930",
                           order_type=OrderType.BUY, price=70000, quantity=10,
                           timeout_seconds=180):
    """pending_orders에 주문 직접 주입"""
    ts = now_kst()
    order = Order(
        order_id=order_id,
        stock_code=stock_code,
        order_type=order_type,
        price=price,
        quantity=quantity,
        timestamp=ts,
        status=OrderStatus.PENDING,
        remaining_quantity=quantity,
    )
    om.pending_orders[order_id] = order
    om.order_timeouts[order_id] = ts + timedelta(seconds=timeout_seconds)
    return order


# ============================================================================
# 1. 부분 체결 시 잔여 수량 처리
# ============================================================================

class TestPartialFill:
    """부분 체결 시나리오"""

    @pytest.mark.asyncio
    async def test_partial_fill_updates_quantities(self):
        """부분 체결 시 filled_quantity, remaining_quantity가 정확히 업데이트 되는지"""
        om = _make_order_manager()
        order = _inject_pending_order(om, quantity=10)

        # 부분 체결 상태 데이터 (3/10 체결)
        status_data = {
            'tot_ccld_qty': '3',
            'rmn_qty': '7',
            'ord_qty': '10',
            'cncl_yn': 'N',
        }
        await om._process_order_status("ORD-001", order, status_data)

        assert order.status == OrderStatus.PARTIAL
        assert order.filled_quantity == 3
        assert order.remaining_quantity == 7

    @pytest.mark.asyncio
    async def test_partial_fill_stays_in_pending(self):
        """부분 체결 주문은 pending_orders에 남아야 함"""
        om = _make_order_manager()
        order = _inject_pending_order(om, quantity=10)

        status_data = {
            'tot_ccld_qty': '5',
            'rmn_qty': '5',
            'ord_qty': '10',
            'cncl_yn': 'N',
        }
        await om._process_order_status("ORD-001", order, status_data)

        assert "ORD-001" in om.pending_orders
        assert len(om.completed_orders) == 0

    @pytest.mark.asyncio
    async def test_partial_fill_timeout_registers_filled_portion(self):
        """부분 체결 + 타임아웃 시 체결 수량으로 포지션 등록되어야 함"""
        api = Mock()
        cancel_result = _make_order_result(success=True, order_id="ORD-001")
        api.cancel_order.return_value = cancel_result
        # get_order_status 반환: 부분 체결 상태
        api.get_order_status.return_value = {
            'tot_ccld_qty': '4',
            'rmn_qty': '6',
            'ord_qty': '10',
            'cncl_yn': 'N',
        }

        om = _make_order_manager(api_manager=api)
        order = _inject_pending_order(om, quantity=10, timeout_seconds=0)
        order.filled_quantity = 4
        order.remaining_quantity = 6
        order.status = OrderStatus.PARTIAL

        # trading_manager Mock
        tm = AsyncMock()
        tm.on_partial_fill_timeout = AsyncMock()
        om.trading_manager = tm

        await om._handle_partial_fill_timeout("ORD-001", order, 4)

        # 체결된 수량으로 완료 처리
        assert order.quantity == 4
        assert order.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_partial_fill_quantity_mismatch_warning(self):
        """체결+잔여 != 주문 수량이면 경고 (상태 변경 없음)"""
        om = _make_order_manager()
        order = _inject_pending_order(om, quantity=10)

        # 수량 불일치
        status_data = {
            'tot_ccld_qty': '3',
            'rmn_qty': '5',  # 3+5=8 != 10
            'ord_qty': '10',
            'cncl_yn': 'N',
        }
        await om._process_order_status("ORD-001", order, status_data)

        # 상태가 변경되지 않아야 함 (PENDING 유지)
        assert order.status == OrderStatus.PENDING


# ============================================================================
# 2. 중복 매수 시도 방지
# ============================================================================

class TestDuplicateBuyPrevention:
    """중복 매수 방지 테스트"""

    @pytest.mark.asyncio
    async def test_fund_manager_prevents_double_reservation(self):
        """FundManager: 같은 order_id로 이중 예약 방지"""
        fm = FundManager(initial_funds=10_000_000)
        assert fm.reserve_funds("ORD-001", 700_000) is True
        assert fm.reserve_funds("ORD-001", 700_000) is False  # 중복 예약 거부

    @pytest.mark.asyncio
    async def test_fund_manager_insufficient_funds(self):
        """FundManager: 가용 자금 부족 시 예약 거부"""
        fm = FundManager(initial_funds=500_000)
        assert fm.reserve_funds("ORD-001", 700_000) is False

    @pytest.mark.asyncio
    async def test_concurrent_buy_orders_exhaust_funds(self):
        """동시 매수 주문이 자금을 초과하면 두 번째 주문 거부"""
        fm = FundManager(initial_funds=1_000_000)
        fm.max_position_ratio = 1.0  # 제한 해제
        fm.max_total_investment_ratio = 1.0

        assert fm.reserve_funds("ORD-001", 600_000) is True
        assert fm.reserve_funds("ORD-002", 600_000) is False  # 잔여 400K < 600K

    @pytest.mark.asyncio
    async def test_pending_buy_blocks_same_stock_via_fund_reservation(self):
        """이미 자금이 예약된 상태에서 추가 매수 자금 부족"""
        fm = FundManager(initial_funds=1_000_000)
        fm.max_position_ratio = 0.09  # 90K 한도

        fm.reserve_funds("ORD-001", 90_000)
        # 같은 종목에 대해 추가 90K → 가용자금은 충분하지만
        # 실제로는 trading_manager에서 상태(BUY_PENDING)로 차단해야 함
        # FundManager 레벨에서는 자금 가용 여부만 체크
        assert fm.reserve_funds("ORD-002", 90_000) is True  # 자금은 충분
        # → 실제 중복 매수 방지는 StockState 레벨에서 해야 함 (취약점)


# ============================================================================
# 3. 주문 거부 후 상태 복구
# ============================================================================

class TestOrderRejectionRecovery:
    """주문 거부 시 상태 복구"""

    @pytest.mark.asyncio
    async def test_buy_order_api_failure_returns_none(self):
        """매수 API 실패 시 None 반환 (pending에 추가 안 됨)"""
        api = Mock()
        fail_result = _make_order_result(success=False, message="주문 거부")
        api.place_buy_order.return_value = fail_result

        om = _make_order_manager(api_manager=api)
        om.trading_manager = None

        with patch('core.orders.order_executor.run_with_timeout', return_value=fail_result):
            order_id = await om.place_buy_order("005930", 10, 70000)

        assert order_id is None
        assert len(om.pending_orders) == 0

    @pytest.mark.asyncio
    async def test_buy_order_api_timeout_returns_none(self):
        """매수 API 타임아웃 시 None 반환"""
        api = Mock()
        om = _make_order_manager(api_manager=api)
        om.trading_manager = None

        with patch('core.orders.order_executor.run_with_timeout', return_value=None):
            order_id = await om.place_buy_order("005930", 10, 70000)

        assert order_id is None
        assert len(om.pending_orders) == 0

    @pytest.mark.asyncio
    async def test_sell_order_api_failure_returns_none(self):
        """매도 API 실패 시 None 반환"""
        api = Mock()
        fail_result = _make_order_result(success=False, message="매도 거부")
        api.place_sell_order.return_value = fail_result

        om = _make_order_manager(api_manager=api)
        om.trading_manager = None

        with patch('core.orders.order_executor.run_with_timeout', return_value=fail_result):
            order_id = await om.place_sell_order("005930", 10, 70000)

        assert order_id is None
        assert len(om.pending_orders) == 0

    @pytest.mark.asyncio
    async def test_fund_released_on_order_cancel(self):
        """주문 취소 시 FundManager 자금 해제"""
        fm = FundManager(initial_funds=1_000_000)
        fm.reserve_funds("ORD-001", 700_000)
        assert fm.available_funds == 300_000

        fm.cancel_order("ORD-001")
        assert fm.available_funds == 1_000_000
        assert fm.reserved_funds == 0

    @pytest.mark.asyncio
    async def test_order_exception_returns_none(self):
        """place_buy_order 내부 예외 시 None 반환 (상태 오염 없음)"""
        api = Mock()
        om = _make_order_manager(api_manager=api)
        om.trading_manager = None

        with patch('core.orders.order_executor.run_with_timeout', side_effect=Exception("네트워크 에러")):
            order_id = await om.place_buy_order("005930", 10, 70000)

        assert order_id is None
        assert len(om.pending_orders) == 0


# ============================================================================
# 4. 미체결 타임아웃 → 자동 취소 → 자금 해제
# ============================================================================

class TestTimeoutAutoCancelFundRelease:
    """미체결 타임아웃 → 자동 취소 → 자금 해제"""

    @pytest.mark.asyncio
    async def test_timeout_triggers_cancel(self):
        """타임아웃 시 cancel_order 호출"""
        api = Mock()
        cancel_result = _make_order_result(success=True, order_id="ORD-001")
        api.cancel_order.return_value = cancel_result
        api.get_order_status.return_value = {
            'tot_ccld_qty': '0',
            'rmn_qty': '10',
            'ord_qty': '10',
            'cncl_yn': 'N',
            'actual_unfilled': True,
        }

        om = _make_order_manager(api_manager=api)
        order = _inject_pending_order(om, timeout_seconds=-1)  # 이미 만료

        with patch('core.orders.order_executor.run_with_timeout', return_value=cancel_result):
            await om._handle_timeout("ORD-001")

        # pending에서 제거되어야 함
        assert "ORD-001" not in om.pending_orders

    @pytest.mark.asyncio
    async def test_timeout_moves_to_completed(self):
        """타임아웃 후 주문이 completed_orders로 이동"""
        api = Mock()
        cancel_result = _make_order_result(success=True)
        api.cancel_order.return_value = cancel_result
        api.get_order_status.return_value = {
            'tot_ccld_qty': '0', 'rmn_qty': '10', 'ord_qty': '10',
            'cncl_yn': 'N', 'actual_unfilled': True,
        }

        om = _make_order_manager(api_manager=api)
        _inject_pending_order(om, timeout_seconds=-1)

        with patch('core.orders.order_executor.run_with_timeout', return_value=cancel_result):
            await om._handle_timeout("ORD-001")

        completed_ids = [o.order_id for o in om.completed_orders]
        assert "ORD-001" in completed_ids

    @pytest.mark.asyncio
    async def test_fund_manager_cancel_releases_funds(self):
        """FundManager: 취소 시 예약 자금이 가용으로 복귀"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD-001", 700_000)

        assert fm.available_funds == 9_300_000
        assert fm.reserved_funds == 700_000

        fm.cancel_order("ORD-001")

        assert fm.available_funds == 10_000_000
        assert fm.reserved_funds == 0
        assert "ORD-001" not in fm.order_reservations

    @pytest.mark.asyncio
    async def test_force_timeout_cleanup_on_cancel_failure(self):
        """취소 실패 시 강제 TIMEOUT 상태로 정리"""
        api = Mock()
        cancel_result = _make_order_result(success=False, message="취소 실패")
        api.cancel_order.return_value = cancel_result
        # 상태 확인도 미체결
        api.get_order_status.return_value = {
            'tot_ccld_qty': '0', 'rmn_qty': '10', 'ord_qty': '10',
            'cncl_yn': 'N', 'actual_unfilled': True,
        }

        om = _make_order_manager(api_manager=api)
        order = _inject_pending_order(om, timeout_seconds=-1)

        with patch('core.orders.order_executor.run_with_timeout', return_value=cancel_result):
            with patch('core.orders.order_timeout.ORDER_CANCEL_MAX_RETRIES', 1):
                with patch('core.orders.order_timeout.ORDER_CANCEL_RETRY_INTERVAL', 0):
                    await om._handle_timeout("ORD-001")

        # 강제 정리로 completed에 이동
        assert "ORD-001" not in om.pending_orders
        completed = [o for o in om.completed_orders if o.order_id == "ORD-001"]
        assert len(completed) == 1
        assert completed[0].status == OrderStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_4candle_timeout_cancels_buy(self):
        """3분봉 4개 경과 시 매수 주문 취소"""
        api = Mock()
        cancel_result = _make_order_result(success=True)
        api.cancel_order.return_value = cancel_result
        api.get_order_status.return_value = {
            'tot_ccld_qty': '0', 'rmn_qty': '10', 'ord_qty': '10',
            'cncl_yn': 'N', 'actual_unfilled': True,
        }

        om = _make_order_manager(api_manager=api)
        order = _inject_pending_order(om, timeout_seconds=600)
        order.order_3min_candle_time = now_kst() - timedelta(minutes=15)  # 4봉 이상 경과

        with patch('core.orders.order_executor.run_with_timeout', return_value=cancel_result):
            await om._handle_4candle_timeout("ORD-001")

        assert "ORD-001" not in om.pending_orders


# ============================================================================
# 5. 매도 중 에러 → 포지션 유지
# ============================================================================

class TestSellErrorPositionRetained:
    """매도 주문 에러 시 포지션 유지"""

    @pytest.mark.asyncio
    async def test_sell_api_timeout_no_position_change(self):
        """매도 API 타임아웃 → 포지션(pending_orders, completed_orders) 변동 없음"""
        api = Mock()
        om = _make_order_manager(api_manager=api)
        om.trading_manager = None

        initial_pending = len(om.pending_orders)
        initial_completed = len(om.completed_orders)

        with patch('core.orders.order_executor.run_with_timeout', return_value=None):
            order_id = await om.place_sell_order("005930", 10, 70000)

        assert order_id is None
        assert len(om.pending_orders) == initial_pending
        assert len(om.completed_orders) == initial_completed

    @pytest.mark.asyncio
    async def test_sell_api_failure_no_position_change(self):
        """매도 API 실패 → 포지션 유지"""
        api = Mock()
        fail_result = _make_order_result(success=False, message="매도 거부")

        om = _make_order_manager(api_manager=api)
        om.trading_manager = None

        with patch('core.orders.order_executor.run_with_timeout', return_value=fail_result):
            order_id = await om.place_sell_order("005930", 10, 70000)

        assert order_id is None
        # 포지션 관련 상태에 영향 없음
        assert len(om.pending_orders) == 0

    @pytest.mark.asyncio
    async def test_sell_exception_no_position_change(self):
        """매도 중 예외 → 포지션 유지"""
        api = Mock()
        om = _make_order_manager(api_manager=api)
        om.trading_manager = None

        with patch('core.orders.order_executor.run_with_timeout', side_effect=Exception("서버 에러")):
            order_id = await om.place_sell_order("005930", 10, 70000)

        assert order_id is None
        assert len(om.pending_orders) == 0
        assert len(om.completed_orders) == 0

    @pytest.mark.asyncio
    async def test_sell_cancel_failure_keeps_pending(self):
        """매도 주문 취소 실패 시 pending에 유지"""
        api = Mock()
        cancel_result = _make_order_result(success=False, message="취소 실패")

        om = _make_order_manager(api_manager=api)
        order = _inject_pending_order(om, order_type=OrderType.SELL,
                                       order_id="SELL-001", quantity=10)

        with patch('core.orders.order_executor.run_with_timeout', return_value=cancel_result):
            result = await om.cancel_order("SELL-001")

        assert result is False
        assert "SELL-001" in om.pending_orders


# ============================================================================
# 6. 엣지 케이스 및 상태 일관성
# ============================================================================

class TestEdgeCases:
    """엣지 케이스"""

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self):
        """존재하지 않는 주문 취소 시 False 반환"""
        om = _make_order_manager()
        result = await om.cancel_order("NONEXISTENT")
        assert result is False

    @pytest.mark.asyncio
    async def test_move_to_completed_cleans_timeout(self):
        """_move_to_completed가 order_timeouts에서도 제거"""
        om = _make_order_manager()
        _inject_pending_order(om)

        om._move_to_completed("ORD-001")

        assert "ORD-001" not in om.pending_orders
        assert "ORD-001" not in om.order_timeouts
        assert len(om.completed_orders) == 1

    @pytest.mark.asyncio
    async def test_completed_orders_memory_cap(self):
        """completed_orders가 MAX_COMPLETED_ORDERS 초과 시 자동 정리"""
        om = _make_order_manager()

        # 201개 주문 완료 처리
        for i in range(201):
            oid = f"ORD-{i:04d}"
            _inject_pending_order(om, order_id=oid)
            om._move_to_completed(oid)

        assert len(om.completed_orders) <= 200

    @pytest.mark.asyncio
    async def test_full_fill_with_slippage(self):
        """완전 체결 시 슬리피지 반영 (filled_price != order price)"""
        om = _make_order_manager()
        order = _inject_pending_order(om, price=70000, quantity=10)

        status_data = {
            'tot_ccld_qty': '10',
            'rmn_qty': '0',
            'ord_qty': '10',
            'cncl_yn': 'N',
            'avg_prvs': '70500',  # 슬리피지 +500원
        }

        # DB 저장 mock
        om.db_manager = Mock()
        om.trading_manager = None

        await om._process_order_status("ORD-001", order, status_data)

        assert order.status == OrderStatus.FILLED
        assert order.filled_price == 70500.0

    @pytest.mark.asyncio
    async def test_status_unknown_under_5min_deferred(self):
        """상태 불명 5분 미만이면 판정 유보 (pending 유지)"""
        om = _make_order_manager()
        order = _inject_pending_order(om)
        order.timestamp = now_kst() - timedelta(seconds=120)  # 2분 경과

        status_data = {
            'tot_ccld_qty': '0', 'rmn_qty': '0', 'ord_qty': '10',
            'cncl_yn': 'N', 'status_unknown': True,
        }
        await om._process_order_status("ORD-001", order, status_data)

        assert "ORD-001" in om.pending_orders  # 아직 pending

    @pytest.mark.asyncio
    async def test_status_unknown_over_5min_timeout(self):
        """상태 불명 5분 이상이면 TIMEOUT 처리"""
        om = _make_order_manager()
        order = _inject_pending_order(om)
        order.timestamp = now_kst() - timedelta(seconds=400)  # 6분+ 경과

        status_data = {
            'tot_ccld_qty': '0', 'rmn_qty': '0', 'ord_qty': '10',
            'cncl_yn': 'N', 'status_unknown': True,
        }
        await om._process_order_status("ORD-001", order, status_data)

        assert "ORD-001" not in om.pending_orders
        completed = [o for o in om.completed_orders if o.order_id == "ORD-001"]
        assert completed[0].status == OrderStatus.TIMEOUT
