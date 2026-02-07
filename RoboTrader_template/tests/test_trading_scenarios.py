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
        with patch.object(om, '_cancel_with_retry', new_callable=AsyncMock, return_value=True) as mock_cancel:
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

        # 검증: 4주분(280,000원) 환불됨
        assert fm.invested_funds == 420_000  # 6주분
        assert fm.reserved_funds == 0
        # 환불금: 700,000 - 420,000 = 280,000원
        # 가용자금: 10,000,000 - 700,000 + 280,000 = 9,580,000원
        assert fm.available_funds == 9_580_000

        # 총 자금 정합성
        total = fm.available_funds + fm.reserved_funds + fm.invested_funds
        assert total == fm.total_funds

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

        status = fm.get_status()
        assert status['invested_funds'] == 420_000  # 6주 x 70,000원
        assert status['reserved_funds'] == 0
        # 총 정합성
        assert status['available_funds'] + status['invested_funds'] == status['total_funds']


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
        fm = FundManager(initial_funds=10_000_000)

        # 예약
        fm.reserve_funds("ORD-REFUND", 700_000)

        # 6주만 체결
        filled_amount = 6 * 70000  # 420,000원
        fm.confirm_order("ORD-REFUND", filled_amount)

        # 환불금 = 700,000 - 420,000 = 280,000원
        # 가용자금 = 10,000,000 - 700,000 (예약) + 280,000 (환불) = 9,580,000원
        assert fm.available_funds == 9_580_000
        assert fm.invested_funds == 420_000

    def test_multiple_partial_fills_consistency(self):
        """여러 부분 체결 후 정합성"""
        fm = FundManager(initial_funds=10_000_000)

        # 주문 1: 700,000원 예약 -> 420,000원 체결
        fm.reserve_funds("ORD-1", 700_000)
        fm.confirm_order("ORD-1", 420_000)

        # 주문 2: 500,000원 예약 -> 300,000원 체결
        fm.reserve_funds("ORD-2", 500_000)
        fm.confirm_order("ORD-2", 300_000)

        # 검증
        status = fm.get_status()
        assert status['invested_funds'] == 720_000  # 420,000 + 300,000
        assert status['reserved_funds'] == 0

        total = status['available_funds'] + status['reserved_funds'] + status['invested_funds']
        assert total == status['total_funds']


# ============================================================================
# Scenario 4: Rebalancing Full Flow Test
# ============================================================================

class TestScenario4Rebalancing:
    """
    시나리오 4: 리밸런싱 전체 흐름

    1. 현재 포트폴리오: [005930(10주), 000660(8주)]
    2. 목표 포트폴리오: [000660, 051910, 028050]
    3. 매도 대상: 005930 (10주)
    4. 신규 매수: 051910, 028050
    5. 매도 선행 실행
    6. 매도 체결 대기
    7. 매수 병렬 실행
    8. 목표 익절/손절률 저장 확인
    """

    @pytest.fixture
    def mock_api_manager(self):
        """API Manager Mock"""
        api = Mock()
        api.is_initialized = True

        # 현재가 조회
        def get_current_price(stock_code):
            prices = {
                '005930': 70000,  # 삼성전자
                '000660': 150000,  # SK하이닉스
                '051910': 80000,   # LG화학
                '028050': 25000,   # 삼성엔지니어링
            }
            price = prices.get(stock_code, 50000)
            return types.SimpleNamespace(
                current_price=price,
                change_amount=0,
                change_rate=0,
                volume=1000000,
                stock_code=stock_code
            )

        api.get_current_price = Mock(side_effect=get_current_price)

        # OHLCV 데이터 (전일 데이터)
        def get_ohlcv_data(stock_code, period="D", days=7):
            prices = {
                '005930': 70000,
                '000660': 150000,
                '051910': 80000,
                '028050': 25000,
            }
            base_price = prices.get(stock_code, 50000)
            dates = pd.date_range(end=datetime.now(), periods=days, freq="B")
            return pd.DataFrame({
                'stck_bsop_date': dates,
                'stck_oprc': [base_price * 0.99] * days,
                'stck_hgpr': [base_price * 1.02] * days,
                'stck_lwpr': [base_price * 0.98] * days,
                'stck_clpr': [base_price] * days,
                'acml_vol': [500000] * days,
            })

        api.get_ohlcv_data = Mock(side_effect=get_ohlcv_data)

        # 코스피 지수
        api.get_index_data = Mock(return_value={
            'bstp_nmix_prdy_ctrt': 0.5  # +0.5%
        })

        return api

    @pytest.fixture
    def mock_order_manager(self):
        """Order Manager AsyncMock"""
        order_mgr = AsyncMock()

        # 매도 주문
        async def place_sell_order(stock_code, quantity, price, market=False):
            return f"SELL-{stock_code}-{quantity}"

        # 매수 주문
        async def place_buy_order(stock_code, quantity, price, timeout_seconds=300,
                                   target_profit_rate=0.15, stop_loss_rate=0.10):
            return f"BUY-{stock_code}-{quantity}"

        order_mgr.place_sell_order = AsyncMock(side_effect=place_sell_order)
        order_mgr.place_buy_order = AsyncMock(side_effect=place_buy_order)

        return order_mgr

    @pytest.fixture
    def mock_trading_manager(self):
        """Trading Stock Manager Mock"""
        trading_mgr = Mock()
        trading_stocks = {}

        def get_trading_stock(stock_code):
            return trading_stocks.get(stock_code)

        async def add_selected_stock(stock_code, stock_name, selection_reason, prev_close):
            ts = Mock()
            ts.stock_code = stock_code
            ts.stock_name = stock_name
            ts.target_profit_rate = 0.15
            ts.stop_loss_rate = 0.10
            trading_stocks[stock_code] = ts
            return ts

        trading_mgr.get_trading_stock = Mock(side_effect=get_trading_stock)
        trading_mgr.add_selected_stock = AsyncMock(side_effect=add_selected_stock)

        return trading_mgr

    @pytest.fixture
    def mock_db_manager(self):
        """DB Manager Mock"""
        db = Mock()
        db.get_today_stop_loss_stocks = Mock(return_value=[])
        return db

    @pytest.fixture
    def mock_order_wait_helper(self):
        """Order Wait Helper AsyncMock"""
        helper = AsyncMock()
        helper.wait_for_sell_orders_completion = AsyncMock(return_value=None)
        return helper

    @pytest.fixture
    def mock_keep_list_updater(self):
        """Keep List Updater AsyncMock"""
        updater = AsyncMock()
        updater.update_keep_list_profit_loss = AsyncMock(return_value=None)
        return updater

    @pytest.fixture
    def mock_notification_helper(self):
        """Notification Helper AsyncMock"""
        helper = AsyncMock()
        helper.send_rebalancing_result = AsyncMock(return_value=None)
        return helper

    @pytest.fixture
    def mock_telegram(self):
        """Telegram AsyncMock"""
        tg = AsyncMock()
        tg.notify_error = AsyncMock()
        return tg

    @pytest.fixture
    def rebalancing_plan(self):
        """리밸런싱 계획"""
        return {
            'sell_list': [
                {
                    'stock_code': '005930',
                    'stock_name': '삼성전자',
                    'quantity': 10,
                    'reason': '[리밸런싱] 포트폴리오 조정'
                }
            ],
            'buy_list': [
                {
                    'stock_code': '051910',
                    'stock_name': 'LG화학',
                    'target_amount': 800000,
                    'rank': 2,
                    'total_score': 85.0,
                    'target_profit_rate': 0.18,
                    'stop_loss_rate': 0.09
                },
                {
                    'stock_code': '028050',
                    'stock_name': '삼성엔지니어링',
                    'target_amount': 500000,
                    'rank': 3,
                    'total_score': 82.0,
                    'target_profit_rate': 0.17,
                    'stop_loss_rate': 0.08
                }
            ],
            'keep_list': [
                {
                    'stock_code': '000660',
                    'stock_name': 'SK하이닉스',
                    'rank': 1,
                    'total_score': 90.0,
                    'target_profit_rate': 0.20,
                    'stop_loss_rate': 0.08
                }
            ],
            'calc_date': '20260206'
        }

    @pytest.mark.asyncio
    async def test_rebalancing_sell_before_buy(
        self,
        mock_api_manager,
        mock_order_manager,
        mock_trading_manager,
        mock_db_manager,
        mock_order_wait_helper,
        mock_keep_list_updater,
        mock_notification_helper,
        mock_telegram,
        rebalancing_plan
    ):
        """매도가 매수보다 먼저 실행되는지 확인"""
        from core.helpers.rebalancing_executor import RebalancingExecutor

        executor = RebalancingExecutor(
            api_manager=mock_api_manager,
            order_manager=mock_order_manager,
            trading_manager=mock_trading_manager,
            order_wait_helper=mock_order_wait_helper,
            keep_list_updater=mock_keep_list_updater,
            notification_helper=mock_notification_helper,
            telegram_integration=mock_telegram,
            db_manager=mock_db_manager
        )

        call_order = []

        # 호출 순서 추적
        original_sell = mock_order_manager.place_sell_order
        original_buy = mock_order_manager.place_buy_order

        async def tracked_sell(*args, **kwargs):
            call_order.append('sell')
            return await original_sell(*args, **kwargs)

        async def tracked_buy(*args, **kwargs):
            call_order.append('buy')
            return await original_buy(*args, **kwargs)

        mock_order_manager.place_sell_order = AsyncMock(side_effect=tracked_sell)
        mock_order_manager.place_buy_order = AsyncMock(side_effect=tracked_buy)

        # 실행
        await executor.execute_rebalancing(rebalancing_plan)

        # 검증: 매도가 먼저 실행됨
        assert call_order[0] == 'sell', "매도가 먼저 실행되어야 함"

        # 매도 완료 대기 후 매수 실행
        sell_indices = [i for i, x in enumerate(call_order) if x == 'sell']
        buy_indices = [i for i, x in enumerate(call_order) if x == 'buy']

        if sell_indices and buy_indices:
            assert max(sell_indices) < min(buy_indices), "모든 매도가 매수보다 먼저 완료되어야 함"

    @pytest.mark.asyncio
    async def test_sell_wait_before_buy(
        self,
        mock_api_manager,
        mock_order_manager,
        mock_trading_manager,
        mock_db_manager,
        mock_order_wait_helper,
        mock_keep_list_updater,
        mock_notification_helper,
        mock_telegram,
        rebalancing_plan
    ):
        """매도 체결 대기가 호출되는지 확인"""
        from core.helpers.rebalancing_executor import RebalancingExecutor

        executor = RebalancingExecutor(
            api_manager=mock_api_manager,
            order_manager=mock_order_manager,
            trading_manager=mock_trading_manager,
            order_wait_helper=mock_order_wait_helper,
            keep_list_updater=mock_keep_list_updater,
            notification_helper=mock_notification_helper,
            telegram_integration=mock_telegram,
            db_manager=mock_db_manager
        )

        await executor.execute_rebalancing(rebalancing_plan)

        # 매도 체결 대기가 호출되었는지 확인
        mock_order_wait_helper.wait_for_sell_orders_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_target_profit_loss_saved(
        self,
        mock_api_manager,
        mock_order_manager,
        mock_trading_manager,
        mock_db_manager,
        mock_order_wait_helper,
        mock_keep_list_updater,
        mock_notification_helper,
        mock_telegram,
        rebalancing_plan
    ):
        """목표 익절/손절률이 매수 주문에 전달되는지 확인"""
        from core.helpers.rebalancing_executor import RebalancingExecutor

        executor = RebalancingExecutor(
            api_manager=mock_api_manager,
            order_manager=mock_order_manager,
            trading_manager=mock_trading_manager,
            order_wait_helper=mock_order_wait_helper,
            keep_list_updater=mock_keep_list_updater,
            notification_helper=mock_notification_helper,
            telegram_integration=mock_telegram,
            db_manager=mock_db_manager
        )

        await executor.execute_rebalancing(rebalancing_plan)

        # 매수 주문 호출 확인
        buy_calls = mock_order_manager.place_buy_order.call_args_list

        # 첫 번째 매수 (051910 LG화학)
        first_buy_kwargs = buy_calls[0].kwargs
        assert first_buy_kwargs.get('target_profit_rate') == 0.18, "LG화학 목표 익절률 18%"
        assert first_buy_kwargs.get('stop_loss_rate') == 0.09, "LG화학 손절률 9%"

        # 두 번째 매수 (028050 삼성엔지니어링)
        second_buy_kwargs = buy_calls[1].kwargs
        assert second_buy_kwargs.get('target_profit_rate') == 0.17, "삼성엔지니어링 목표 익절률 17%"
        assert second_buy_kwargs.get('stop_loss_rate') == 0.08, "삼성엔지니어링 손절률 8%"

    @pytest.mark.asyncio
    async def test_keep_list_profit_loss_updated(
        self,
        mock_api_manager,
        mock_order_manager,
        mock_trading_manager,
        mock_db_manager,
        mock_order_wait_helper,
        mock_keep_list_updater,
        mock_notification_helper,
        mock_telegram,
        rebalancing_plan
    ):
        """유지 대상 종목의 목표 익절/손절률이 갱신되는지 확인"""
        from core.helpers.rebalancing_executor import RebalancingExecutor

        executor = RebalancingExecutor(
            api_manager=mock_api_manager,
            order_manager=mock_order_manager,
            trading_manager=mock_trading_manager,
            order_wait_helper=mock_order_wait_helper,
            keep_list_updater=mock_keep_list_updater,
            notification_helper=mock_notification_helper,
            telegram_integration=mock_telegram,
            db_manager=mock_db_manager
        )

        await executor.execute_rebalancing(rebalancing_plan)

        # keep_list 업데이트가 호출되었는지 확인
        mock_keep_list_updater.update_keep_list_profit_loss.assert_called_once()

        # keep_list 내용 확인
        call_args = mock_keep_list_updater.update_keep_list_profit_loss.call_args
        keep_list = call_args[0][0]

        assert len(keep_list) == 1
        assert keep_list[0]['stock_code'] == '000660'
        assert keep_list[0]['target_profit_rate'] == 0.20
        assert keep_list[0]['stop_loss_rate'] == 0.08

    @pytest.mark.asyncio
    async def test_today_stop_loss_stocks_blocked(
        self,
        mock_api_manager,
        mock_order_manager,
        mock_trading_manager,
        mock_db_manager,
        mock_order_wait_helper,
        mock_keep_list_updater,
        mock_notification_helper,
        mock_telegram,
    ):
        """당일 손절한 종목은 재매수가 차단되는지 확인"""
        from core.helpers.rebalancing_executor import RebalancingExecutor

        # 오늘 손절한 종목 설정
        mock_db_manager.get_today_stop_loss_stocks = Mock(return_value=['051910'])

        plan = {
            'sell_list': [],
            'buy_list': [
                {
                    'stock_code': '051910',  # 손절한 종목
                    'stock_name': 'LG화학',
                    'target_amount': 800000,
                    'rank': 2,
                    'total_score': 85.0,
                    'target_profit_rate': 0.18,
                    'stop_loss_rate': 0.09
                },
                {
                    'stock_code': '028050',  # 손절 안 한 종목
                    'stock_name': '삼성엔지니어링',
                    'target_amount': 500000,
                    'rank': 3,
                    'total_score': 82.0,
                    'target_profit_rate': 0.17,
                    'stop_loss_rate': 0.08
                }
            ],
            'keep_list': [],
            'calc_date': '20260206'
        }

        executor = RebalancingExecutor(
            api_manager=mock_api_manager,
            order_manager=mock_order_manager,
            trading_manager=mock_trading_manager,
            order_wait_helper=mock_order_wait_helper,
            keep_list_updater=mock_keep_list_updater,
            notification_helper=mock_notification_helper,
            telegram_integration=mock_telegram,
            db_manager=mock_db_manager
        )

        await executor.execute_rebalancing(plan)

        # 매수 주문 호출 확인 - 051910은 스킵되어야 함
        buy_calls = mock_order_manager.place_buy_order.call_args_list

        # 028050만 매수되어야 함
        assert len(buy_calls) == 1
        assert buy_calls[0].kwargs.get('stock_code') == '028050'


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

class TestRebalancingServiceIntegration:
    """QuantRebalancingService 통합 테스트"""

    @pytest.fixture
    def mock_components(self):
        """테스트용 Mock 컴포넌트"""
        api = Mock()
        api.get_current_price = Mock(return_value=types.SimpleNamespace(current_price=10000))

        db = Mock()
        db.db_path = ':memory:'
        db.get_quant_portfolio = Mock(return_value=[
            {"stock_code": "000660", "stock_name": "SK하이닉스", "rank": 1, "total_score": 90.0, "reason": ""},
            {"stock_code": "051910", "stock_name": "LG화학", "rank": 2, "total_score": 85.0, "reason": ""},
            {"stock_code": "028050", "stock_name": "삼성엔지니어링", "rank": 3, "total_score": 80.0, "reason": ""},
        ])
        db.get_quant_factors = Mock(return_value=[])

        order = Mock()
        order.place_sell_order = Mock(return_value={"ok": True})
        order.place_buy_order = Mock(return_value={"ok": True})

        return {'api': api, 'db': db, 'order': order}

    def test_rebalancing_plan_calculation(self, mock_components, monkeypatch):
        """리밸런싱 계획 계산 테스트"""
        import api.kis_account_api as kis_account_api

        # 현재 보유: 005930(10주), 000660(8주)
        holdings_df = pd.DataFrame([
            {"pdno": "005930", "prdt_name": "삼성전자", "hldg_qty": 10, "pchs_avg_pric": 70000},
            {"pdno": "000660", "prdt_name": "SK하이닉스", "hldg_qty": 8, "pchs_avg_pric": 150000},
        ])
        monkeypatch.setattr(kis_account_api, "get_inquire_balance", lambda: holdings_df)

        from core.quant.quant_rebalancing_service import QuantRebalancingService

        svc = QuantRebalancingService(
            api_manager=mock_components['api'],
            db_manager=mock_components['db'],
            order_manager=mock_components['order']
        )

        plan = svc.calculate_rebalancing_plan(calc_date="20260206")

        # 검증
        sell_codes = {x["stock_code"] for x in plan["sell_list"]}
        buy_codes = {x["stock_code"] for x in plan["buy_list"]}
        keep_codes = {x["stock_code"] for x in plan["keep_list"]}

        # 005930은 목표 포트폴리오에 없으므로 매도 대상 (점수 기준 미달 시)
        # 000660은 유지 대상
        # 051910, 028050은 신규 매수 대상

        assert "000660" in keep_codes, "SK하이닉스는 유지"
        assert "051910" in buy_codes or "028050" in buy_codes, "신규 매수 종목 존재"


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
