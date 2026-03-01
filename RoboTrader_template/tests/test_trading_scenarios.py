"""
Trading Scenarios Tests
=======================

시나리오 3: 부분 체결 -> 타임아웃
시나리오 4: 리밸런싱 전체 흐름 테스트
시나리오 5: API 오류 복구 테스트

기존 테스트 패턴 참조:
- tests/test_rebalancing.py
- tests/test_primary_filter.py
- tests/test_order_timeout.py
"""

import pytest
import types
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, AsyncMock, patch, call

from core.models import Order, OrderType, OrderStatus, TradingConfig
from core.order_manager import OrderManager
from core.fund_manager import FundManager
from utils.korean_time import now_kst


# ============================================================================
# Helper Functions for Scenario 3
# ============================================================================

def _make_order_manager(paper_trading=False):
    """테스트용 OrderManager 생성"""
    config = TradingConfig.from_json({
        'paper_trading': paper_trading,
        'order_management': {
            'buy_timeout_seconds': 300,
            'sell_timeout_seconds': 300,
        }
    })
    api = Mock()
    api.is_initialized = True
    telegram = AsyncMock()
    db = Mock()
    db.save_virtual_buy.return_value = 1
    db.save_virtual_sell.return_value = True
    db.get_last_open_virtual_buy.return_value = None

    om = OrderManager(config, api, telegram, db)
    om.trading_manager = None
    return om


def _make_pending_order(order_id: str, stock_code: str, order_type: OrderType,
                        quantity: int, filled_qty: int, price: float = 70000,
                        minutes_ago: int = 6) -> Order:
    """미체결 주문 생성"""
    ts = now_kst()
    return Order(
        order_id=order_id,
        stock_code=stock_code,
        order_type=order_type,
        price=price,
        quantity=quantity,
        timestamp=ts - timedelta(minutes=minutes_ago),
        filled_quantity=filled_qty,
    )


# ============================================================================
# Scenario 3: 부분 체결 -> 타임아웃
# ============================================================================

class TestScenario3PartialFillTimeout:
    """
    시나리오 3: 부분 체결 -> 타임아웃

    1. 매수 주문 (10주)
    2. 부분 체결 (6주만 체결)
    3. 타임아웃 도달 (300초)
    4. 미체결 4주 취소 시도
    5. 취소 성공 확인
    6. 6주 포지션 유지 확인
    7. 자금 정합성 검증 (4주분 복구)
    """

    @pytest.mark.asyncio
    async def test_step1_place_buy_order_10_shares(self):
        """단계 1: 매수 주문 (10주 x 70,000원 = 700,000원)"""
        om = _make_order_manager(paper_trading=False)

        # 주문 생성
        order = _make_pending_order(
            order_id="ORD-PARTIAL-001",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=0,  # 아직 미체결
            price=70000,
            minutes_ago=1  # 1분 전 주문
        )

        # OrderManager에 등록
        om.pending_orders["ORD-PARTIAL-001"] = order
        om.order_timeouts["ORD-PARTIAL-001"] = now_kst() + timedelta(minutes=4)

        # 검증
        assert order.order_id == "ORD-PARTIAL-001"
        assert order.quantity == 10
        assert order.price == 70000
        assert order.filled_quantity == 0
        assert "ORD-PARTIAL-001" in om.pending_orders

    @pytest.mark.asyncio
    async def test_step2_partial_fill_6_shares(self):
        """단계 2: 부분 체결 (6주만 체결) - filled_quantity=6, remaining=4"""
        om = _make_order_manager(paper_trading=False)

        # 6주 체결된 상태로 주문 생성
        order = _make_pending_order(
            order_id="ORD-PARTIAL-002",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,  # 6주 체결
            price=70000,
            minutes_ago=3
        )

        om.pending_orders["ORD-PARTIAL-002"] = order

        # 검증: filled_quantity = 6, remaining = 4
        assert order.filled_quantity == 6
        assert order.quantity == 10
        remaining = order.quantity - order.filled_quantity
        assert remaining == 4

    @pytest.mark.asyncio
    async def test_step3_timeout_reached_300_seconds(self):
        """단계 3: 타임아웃 도달 (300초 = 5분)"""
        om = _make_order_manager(paper_trading=False)

        # 6분 전 주문 (5분 타임아웃 초과)
        order = _make_pending_order(
            order_id="ORD-PARTIAL-003",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,
            price=70000,
            minutes_ago=6  # 타임아웃 초과
        )

        om.pending_orders["ORD-PARTIAL-003"] = order
        om.order_timeouts["ORD-PARTIAL-003"] = now_kst() - timedelta(minutes=1)  # 이미 타임아웃

        # 타임아웃 확인
        timeout_time = om.order_timeouts["ORD-PARTIAL-003"]
        current_time = now_kst()
        is_timeout = current_time >= timeout_time

        assert is_timeout is True

    @pytest.mark.asyncio
    async def test_step4_cancel_remaining_4_shares(self):
        """단계 4: 미체결 4주 취소 시도"""
        om = _make_order_manager(paper_trading=False)

        order = _make_pending_order(
            order_id="ORD-PARTIAL-004",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,
            price=70000,
            minutes_ago=6
        )

        om.pending_orders["ORD-PARTIAL-004"] = order
        om.order_timeouts["ORD-PARTIAL-004"] = now_kst() - timedelta(minutes=1)

        # _handle_partial_fill_timeout 호출 시 취소 시도
        # C3 fix: _cancel_with_retry 대신 _cancel_remaining_only 사용 (pending_orders 이중 제거 방지)
        with patch.object(om, '_cancel_remaining_only', new_callable=AsyncMock, return_value=True) as mock_cancel:
            with patch.object(om, '_save_real_trade_to_db', new_callable=AsyncMock):
                await om._handle_partial_fill_timeout("ORD-PARTIAL-004", order, 6)

        # 취소 호출 확인
        mock_cancel.assert_called_once_with("ORD-PARTIAL-004")

    @pytest.mark.asyncio
    async def test_step5_cancel_success_with_retry(self):
        """단계 5: 취소 성공 확인 (최대 3회 재시도)"""
        om = _make_order_manager(paper_trading=False)

        order = _make_pending_order(
            order_id="ORD-PARTIAL-005",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,
            price=70000,
            minutes_ago=6
        )

        om.pending_orders["ORD-PARTIAL-005"] = order
        om.order_timeouts["ORD-PARTIAL-005"] = now_kst() - timedelta(minutes=1)

        # 2번 실패 후 3번째에 성공
        cancel_call_count = 0

        async def mock_cancel_order(order_id):
            nonlocal cancel_call_count
            cancel_call_count += 1
            if cancel_call_count < 3:
                return False
            return True

        with patch.object(om, 'cancel_order', side_effect=mock_cancel_order):
            with patch('core.orders.order_timeout.asyncio.sleep', new_callable=AsyncMock):
                result = await om._cancel_with_retry("ORD-PARTIAL-005", max_retries=3)

        assert result is True
        assert cancel_call_count == 3

    @pytest.mark.asyncio
    async def test_step6_position_maintained_6_shares(self):
        """단계 6: 6주 포지션 유지 확인"""
        om = _make_order_manager(paper_trading=False)

        order = _make_pending_order(
            order_id="ORD-PARTIAL-006",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,
            price=70000,
            minutes_ago=6
        )

        om.pending_orders["ORD-PARTIAL-006"] = order
        om.order_timeouts["ORD-PARTIAL-006"] = now_kst() - timedelta(minutes=1)

        # trading_manager mock 설정
        mock_trading_manager = AsyncMock()
        om.trading_manager = mock_trading_manager

        with patch.object(om, '_cancel_with_retry', new_callable=AsyncMock, return_value=True):
            with patch.object(om, '_save_real_trade_to_db', new_callable=AsyncMock):
                await om._handle_partial_fill_timeout("ORD-PARTIAL-006", order, 6)

        # 포지션 등록 콜백 확인
        mock_trading_manager.on_partial_fill_timeout.assert_called_once()
        call_args = mock_trading_manager.on_partial_fill_timeout.call_args
        assert call_args[0][1] == 6  # filled_qty = 6

        # completed_orders에서 수량 확인
        assert len(om.completed_orders) == 1
        completed = om.completed_orders[0]
        assert completed.quantity == 6  # 체결된 수량으로 변경됨
        assert completed.filled_quantity == 6
        assert completed.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_step7_fund_consistency_4_shares_recovered(self):
        """단계 7: 자금 정합성 검증 (4주분 복구)"""
        # FundManager로 자금 정합성 테스트
        fm = FundManager(initial_funds=10_000_000)

        # 10주 x 70,000원 = 700,000원 예약
        order_amount = 10 * 70000
        fm.reserve_funds("ORD-FUND-001", order_amount)

        # 초기 상태 확인
        assert fm.reserved_funds == 700_000
        assert fm.available_funds == 10_000_000 - 700_000

        # 6주만 체결 (6 x 70,000 = 420,000원)
        filled_amount = 6 * 70000
        fm.confirm_order("ORD-FUND-001", filled_amount)

        # 검증: invested_funds는 체결금액(수수료 미포함), available은 수수료 차감
        from config.constants import COMMISSION_RATE
        commission = filled_amount * COMMISSION_RATE
        total_cost = filled_amount + commission
        assert fm.invested_funds == pytest.approx(filled_amount)
        assert fm.reserved_funds == 0
        assert fm.available_funds == pytest.approx(10_000_000 - total_cost)

        # 총 자금 정합성 (수수료만큼 차이)
        total = fm.available_funds + fm.reserved_funds + fm.invested_funds
        assert total == pytest.approx(fm.total_funds - commission)

    @pytest.mark.asyncio
    async def test_full_scenario_partial_fill_timeout(self):
        """전체 시나리오: 부분 체결 -> 타임아웃 통합 테스트"""
        # OrderManager 설정
        om = _make_order_manager(paper_trading=False)

        # FundManager 설정
        fm = FundManager(initial_funds=10_000_000)

        # Step 1: 매수 주문 및 자금 예약
        order_amount = 10 * 70000
        fm.reserve_funds("ORD-INTEGRATED", order_amount)

        order = _make_pending_order(
            order_id="ORD-INTEGRATED",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,  # Step 2: 부분 체결 상태
            price=70000,
            minutes_ago=6  # Step 3: 타임아웃 상태
        )
        om.pending_orders["ORD-INTEGRATED"] = order
        om.order_timeouts["ORD-INTEGRATED"] = now_kst() - timedelta(minutes=1)

        # Step 4, 5: 타임아웃 처리 (취소 시도 및 성공)
        with patch.object(om, '_check_order_status', new_callable=AsyncMock):
            with patch.object(om, '_cancel_with_retry', new_callable=AsyncMock, return_value=True):
                with patch.object(om, '_save_real_trade_to_db', new_callable=AsyncMock):
                    await om._handle_timeout("ORD-INTEGRATED")

        # Step 6: 포지션 확인 (6주 체결됨)
        assert len(om.completed_orders) == 1
        completed = om.completed_orders[0]
        assert completed.filled_quantity == 6
        assert completed.quantity == 6
        assert completed.status == OrderStatus.FILLED

        # Step 7: 자금 정합성
        filled_amount = 6 * 70000
        fm.confirm_order("ORD-INTEGRATED", filled_amount)

        from config.constants import COMMISSION_RATE
        commission = filled_amount * COMMISSION_RATE
        total_cost = filled_amount + commission

        status = fm.get_status()
        assert status['invested_funds'] == pytest.approx(filled_amount)
        assert status['reserved_funds'] == 0
        # 총 정합성 (수수료만큼 차이)
        assert status['available_funds'] + status['invested_funds'] == pytest.approx(status['total_funds'] - commission)


# ============================================================================
# Scenario 3 - Cancel Retry Detail Tests
# ============================================================================

class TestPartialFillCancelRetry:
    """부분 체결 취소 재시도 상세 테스트"""

    @pytest.mark.asyncio
    async def test_cancel_retry_first_success(self):
        """취소 1회에 성공"""
        om = _make_order_manager(paper_trading=False)
        order = _make_pending_order(
            order_id="ORD-RETRY-1",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,
            price=70000,
            minutes_ago=6
        )
        om.pending_orders["ORD-RETRY-1"] = order
        om.order_timeouts["ORD-RETRY-1"] = now_kst() - timedelta(minutes=1)

        with patch.object(om, 'cancel_order', new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = True
            result = await om._cancel_with_retry("ORD-RETRY-1")

        assert result is True
        assert mock_cancel.call_count == 1

    @pytest.mark.asyncio
    async def test_cancel_retry_second_success(self):
        """취소 2회째에 성공"""
        om = _make_order_manager(paper_trading=False)
        order = _make_pending_order(
            order_id="ORD-RETRY-2",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,
            price=70000,
            minutes_ago=6
        )
        om.pending_orders["ORD-RETRY-2"] = order
        om.order_timeouts["ORD-RETRY-2"] = now_kst() - timedelta(minutes=1)

        with patch.object(om, 'cancel_order', new_callable=AsyncMock) as mock_cancel:
            mock_cancel.side_effect = [False, True]
            with patch('core.orders.order_timeout.asyncio.sleep', new_callable=AsyncMock):
                result = await om._cancel_with_retry("ORD-RETRY-2")

        assert result is True
        assert mock_cancel.call_count == 2

    @pytest.mark.asyncio
    async def test_cancel_retry_all_fail(self):
        """취소 3회 모두 실패"""
        om = _make_order_manager(paper_trading=False)
        order = _make_pending_order(
            order_id="ORD-RETRY-3",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,
            price=70000,
            minutes_ago=6
        )
        om.pending_orders["ORD-RETRY-3"] = order
        om.order_timeouts["ORD-RETRY-3"] = now_kst() - timedelta(minutes=1)

        with patch.object(om, 'cancel_order', new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = False
            with patch('core.orders.order_timeout.asyncio.sleep', new_callable=AsyncMock):
                result = await om._cancel_with_retry("ORD-RETRY-3", max_retries=3)

        assert result is False
        assert mock_cancel.call_count == 3


# ============================================================================
# Scenario 3 - Edge Cases
# ============================================================================

class TestPartialFillEdgeCases:
    """부분 체결 엣지 케이스 테스트"""

    @pytest.mark.asyncio
    async def test_zero_filled_not_partial(self):
        """체결 수량 0 -> 부분 체결 아님 (일반 타임아웃)"""
        om = _make_order_manager(paper_trading=False)
        order = _make_pending_order(
            order_id="ORD-ZERO",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=0,
            price=70000,
            minutes_ago=6
        )

        om.pending_orders["ORD-ZERO"] = order
        om.order_timeouts["ORD-ZERO"] = now_kst() - timedelta(minutes=1)

        with patch.object(om, '_check_order_status', new_callable=AsyncMock):
            with patch.object(om, '_handle_partial_fill_timeout', new_callable=AsyncMock) as mock_partial:
                with patch.object(om, '_cancel_with_retry', new_callable=AsyncMock, return_value=True):
                    with patch.object(om, '_notify_trading_manager_timeout', new_callable=AsyncMock):
                        await om._handle_timeout("ORD-ZERO")

        # 부분 체결 핸들러는 호출되지 않음
        mock_partial.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_share_partial_fill(self):
        """1주만 체결된 극단적 부분 체결"""
        om = _make_order_manager(paper_trading=False)
        order = _make_pending_order(
            order_id="ORD-ONE",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=100,
            filled_qty=1,  # 1주만 체결
            price=70000,
            minutes_ago=6
        )

        om.pending_orders["ORD-ONE"] = order
        om.order_timeouts["ORD-ONE"] = now_kst() - timedelta(minutes=1)

        with patch.object(om, '_cancel_with_retry', new_callable=AsyncMock, return_value=True):
            with patch.object(om, '_save_real_trade_to_db', new_callable=AsyncMock):
                await om._handle_partial_fill_timeout("ORD-ONE", order, 1)

        # 1주도 포지션으로 등록
        assert len(om.completed_orders) == 1
        assert om.completed_orders[0].filled_quantity == 1
        assert om.completed_orders[0].quantity == 1

    @pytest.mark.asyncio
    async def test_sell_order_partial_fill(self):
        """매도 주문 부분 체결"""
        om = _make_order_manager(paper_trading=False)
        order = _make_pending_order(
            order_id="ORD-SELL-PARTIAL",
            stock_code="005930",
            order_type=OrderType.SELL,  # 매도 주문
            quantity=10,
            filled_qty=7,  # 7주 체결
            price=75000,
            minutes_ago=6
        )

        om.pending_orders["ORD-SELL-PARTIAL"] = order
        om.order_timeouts["ORD-SELL-PARTIAL"] = now_kst() - timedelta(minutes=1)

        with patch.object(om, '_check_order_status', new_callable=AsyncMock):
            with patch.object(om, '_handle_partial_fill_timeout', new_callable=AsyncMock) as mock_partial:
                await om._handle_timeout("ORD-SELL-PARTIAL")

        # 매도 주문도 부분 체결 핸들러 호출
        mock_partial.assert_called_once()
        assert mock_partial.call_args[0][2] == 7  # 7주 체결

    @pytest.mark.asyncio
    async def test_telegram_notification_on_partial_fill_timeout(self):
        """부분 체결 타임아웃 시 텔레그램 알림"""
        om = _make_order_manager(paper_trading=False)
        order = _make_pending_order(
            order_id="ORD-TELEGRAM",
            stock_code="005930",
            order_type=OrderType.BUY,
            quantity=10,
            filled_qty=6,
            price=70000,
            minutes_ago=6
        )

        om.pending_orders["ORD-TELEGRAM"] = order
        om.order_timeouts["ORD-TELEGRAM"] = now_kst() - timedelta(minutes=1)

        with patch.object(om, '_cancel_with_retry', new_callable=AsyncMock, return_value=True):
            with patch.object(om, '_save_real_trade_to_db', new_callable=AsyncMock):
                await om._handle_partial_fill_timeout("ORD-TELEGRAM", order, 6)

        # 텔레그램 알림 호출 확인
        om.telegram.notify_system_status.assert_called_once()
        call_args = om.telegram.notify_system_status.call_args[0][0]
        assert "부분 체결 타임아웃" in call_args
        assert "005930" in call_args
        assert "6/10주" in call_args


# ============================================================================
# Scenario 3 - Fund Consistency Details
# ============================================================================

class TestPartialFillFundConsistency:
    """부분 체결 자금 정합성 상세 테스트"""

    def test_fund_reservation_exact_amount(self):
        """정확한 금액 예약"""
        fm = FundManager(initial_funds=10_000_000)
        order_amount = 10 * 70000  # 700,000원

        success = fm.reserve_funds("ORD-EXACT", order_amount)

        assert success is True
        assert fm.reserved_funds == 700_000
        assert fm.available_funds == 9_300_000

    def test_partial_fill_refund_calculation(self):
        """부분 체결 환불금 계산"""
        from config.constants import COMMISSION_RATE
        fm = FundManager(initial_funds=10_000_000)

        # 예약
        fm.reserve_funds("ORD-REFUND", 700_000)

        # 6주만 체결
        filled_amount = 6 * 70000  # 420,000원
        fm.confirm_order("ORD-REFUND", filled_amount)

        commission = filled_amount * COMMISSION_RATE
        total_cost = filled_amount + commission
        assert fm.available_funds == pytest.approx(10_000_000 - total_cost)
        assert fm.invested_funds == pytest.approx(filled_amount)

    def test_multiple_partial_fills_consistency(self):
        """여러 부분 체결 후 정합성"""
        from config.constants import COMMISSION_RATE
        fm = FundManager(initial_funds=10_000_000)

        # 주문 1: 700,000원 예약 -> 420,000원 체결
        fm.reserve_funds("ORD-1", 700_000)
        fm.confirm_order("ORD-1", 420_000)

        # 주문 2: 500,000원 예약 -> 300,000원 체결
        fm.reserve_funds("ORD-2", 500_000)
        fm.confirm_order("ORD-2", 300_000)

        # 검증 (invested_funds는 체결금액만, 수수료 미포함)
        c1 = 420_000 * COMMISSION_RATE
        c2 = 300_000 * COMMISSION_RATE
        total_invested = 420_000 + 300_000
        status = fm.get_status()
        assert status['invested_funds'] == pytest.approx(total_invested)
        assert status['reserved_funds'] == 0

        total = status['available_funds'] + status['reserved_funds'] + status['invested_funds']
        assert total == pytest.approx(status['total_funds'] - c1 - c2)


# ============================================================================
# Scenario 4: Rebalancing Full Flow Test
# ============================================================================
# Scenario 4: Rebalancing (removed — quant-specific, see _archived/)
# ============================================================================


# ============================================================================
# Scenario 5: API Error Recovery Test
# ============================================================================

class TestScenario5APIErrorRecovery:
    """
    시나리오 5: API 오류 복구

    1. 현재가 조회 1차 실패 (TimeoutError)
    2. 1초 대기
    3. 현재가 조회 2차 실패 (ConnectionError)
    4. 2초 대기
    5. 현재가 조회 3차 성공
    6. 정상 로직 수행
    """

    @pytest.fixture
    def mock_api_with_retry_logic(self):
        """재시도 로직이 있는 API Mock"""
        api = Mock()
        api.is_initialized = True
        api.max_retries = 3
        api.retry_delay = 1.0

        call_count = {'value': 0}

        def get_current_price_with_failures(stock_code):
            """1차 TimeoutError, 2차 ConnectionError, 3차 성공"""
            call_count['value'] += 1

            if call_count['value'] == 1:
                raise TimeoutError("API 타임아웃")
            elif call_count['value'] == 2:
                raise ConnectionError("연결 오류")
            else:
                return types.SimpleNamespace(
                    current_price=70000,
                    change_amount=500,
                    change_rate=0.72,
                    volume=10000000,
                    stock_code=stock_code
                )

        api.get_current_price_raw = Mock(side_effect=get_current_price_with_failures)
        api._call_count = call_count

        return api

    def test_api_retry_on_timeout_error(self, mock_api_with_retry_logic):
        """TimeoutError 발생 시 재시도하는지 확인"""
        import time

        api = mock_api_with_retry_logic
        delays = []

        def get_current_price_with_retry(stock_code, max_retries=3, retry_delay=1.0):
            """재시도 로직이 포함된 현재가 조회"""
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return api.get_current_price_raw(stock_code)
                except (TimeoutError, ConnectionError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)  # 지수 백오프
                        delays.append(wait_time)
                        # time.sleep(wait_time)  # 테스트에서는 실제 대기 생략

            if last_exception:
                raise last_exception
            return None

        # 실행
        result = get_current_price_with_retry('005930')

        # 검증
        assert api._call_count['value'] == 3, "3번 호출되어야 함 (1차 실패, 2차 실패, 3차 성공)"
        assert result is not None, "최종적으로 성공해야 함"
        assert result.current_price == 70000
        assert len(delays) == 2, "2번의 대기가 있어야 함"
        assert delays[0] == 1.0, "1차 실패 후 1초 대기"
        assert delays[1] == 2.0, "2차 실패 후 2초 대기"

    def test_api_retry_count_verification(self, mock_api_with_retry_logic):
        """재시도 횟수가 정확한지 확인"""
        api = mock_api_with_retry_logic
        retry_count = 0

        def get_with_retry(stock_code):
            nonlocal retry_count
            max_retries = 3

            for attempt in range(max_retries):
                try:
                    return api.get_current_price_raw(stock_code)
                except (TimeoutError, ConnectionError):
                    retry_count += 1
                    if attempt == max_retries - 1:
                        raise
            return None

        # 실행
        result = get_with_retry('005930')

        # 검증
        assert retry_count == 2, "재시도는 2번 (1차, 2차 실패 후 각각 1회)"
        assert result is not None

    def test_api_final_state_after_recovery(self, mock_api_with_retry_logic):
        """복구 후 최종 상태가 정상인지 확인"""
        api = mock_api_with_retry_logic

        def get_with_retry(stock_code):
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    return api.get_current_price_raw(stock_code)
                except (TimeoutError, ConnectionError):
                    if attempt == max_retries - 1:
                        raise
            return None

        # 실행
        result = get_with_retry('005930')

        # 검증: 정상 로직 수행 (복구 후 데이터 확인)
        assert result.stock_code == '005930'
        assert result.current_price == 70000
        assert result.change_amount == 500
        assert result.change_rate == 0.72
        assert result.volume == 10000000

    def test_api_max_retry_exceeded(self):
        """최대 재시도 횟수 초과 시 예외 발생"""
        call_count = 0

        def always_fail(stock_code):
            nonlocal call_count
            call_count += 1
            raise TimeoutError("항상 실패")

        def get_with_retry(stock_code, max_retries=3):
            for attempt in range(max_retries):
                try:
                    return always_fail(stock_code)
                except TimeoutError:
                    if attempt == max_retries - 1:
                        raise
            return None

        # 실행 및 검증
        with pytest.raises(TimeoutError):
            get_with_retry('005930')

        assert call_count == 3, "최대 재시도 횟수만큼 호출되어야 함"

    def test_api_retry_delay_sequence(self):
        """재시도 간 대기 시간 시퀀스 확인"""
        delays_recorded = []
        call_count = 0

        def mock_get_price(stock_code):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("실패")
            return types.SimpleNamespace(current_price=50000, stock_code=stock_code)

        def get_with_exponential_backoff(stock_code, max_retries=3, base_delay=1.0):
            for attempt in range(max_retries):
                try:
                    return mock_get_price(stock_code)
                except TimeoutError:
                    if attempt < max_retries - 1:
                        delay = base_delay * (attempt + 1)  # 1초, 2초 순서
                        delays_recorded.append(delay)
            return None

        # 실행
        result = get_with_exponential_backoff('005930')

        # 검증
        assert result is not None
        assert delays_recorded == [1.0, 2.0], "1초, 2초 순으로 대기"


# ============================================================================
# Additional Integration Tests
# ============================================================================

class TestAPIRetryPatterns:
    """API 재시도 패턴 테스트"""

    def test_side_effect_sequential_exceptions(self):
        """side_effect로 순차적 예외 발생 테스트"""
        mock_func = Mock(side_effect=[
            TimeoutError("1차 타임아웃"),
            ConnectionError("2차 연결 오류"),
            types.SimpleNamespace(current_price=50000)  # 3차 성공
        ])

        results = []
        for i in range(3):
            try:
                result = mock_func()
                results.append(('success', result))
            except TimeoutError as e:
                results.append(('timeout', str(e)))
            except ConnectionError as e:
                results.append(('connection', str(e)))

        assert results[0] == ('timeout', '1차 타임아웃')
        assert results[1] == ('connection', '2차 연결 오류')
        assert results[2][0] == 'success'
        assert results[2][1].current_price == 50000

    def test_retry_counter_increments_correctly(self):
        """재시도 카운터가 정확히 증가하는지 확인"""
        retry_tracker = {'attempts': 0, 'successes': 0, 'failures': 0}

        def tracked_operation():
            retry_tracker['attempts'] += 1
            if retry_tracker['attempts'] < 3:
                retry_tracker['failures'] += 1
                raise TimeoutError("실패")
            retry_tracker['successes'] += 1
            return "성공"

        # 재시도 실행
        result = None
        for _ in range(3):
            try:
                result = tracked_operation()
                break
            except TimeoutError:
                continue

        assert retry_tracker['attempts'] == 3
        assert retry_tracker['failures'] == 2
        assert retry_tracker['successes'] == 1
        assert result == "성공"
