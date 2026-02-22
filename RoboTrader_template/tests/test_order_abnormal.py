"""
주문 비정상 상황 테스트
- 중복 주문 방지
- FundManager 연동 (예약→확정→취소)
- 부분 체결 처리
- 주문 거부 시 자금 복구
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

from utils.korean_time import now_kst
from core.models import (
    Order, OrderType, OrderStatus, TradingConfig,
    OrderManagementConfig, DataCollectionConfig,
    RiskManagementConfig, StrategyConfig, LoggingConfig
)
from core.order_manager import OrderManager
from core.fund_manager import FundManager


@pytest.fixture(autouse=True)
def _mock_market_hours():
    """장 시간 체크를 우회하여 테스트 시간에 관계없이 주문 가능하게 함"""
    with patch('config.market_hours.MarketHours.can_place_order', return_value=True):
        yield


def make_config(paper_trading=False):
    return TradingConfig(
        data_collection=DataCollectionConfig(),
        order_management=OrderManagementConfig(
            buy_timeout_seconds=180,
            sell_timeout_seconds=180,
            max_adjustments=3,
        ),
        risk_management=RiskManagementConfig(),
        strategy=StrategyConfig(),
        logging=LoggingConfig(),
        paper_trading=paper_trading,
    )


def make_broker_mock():
    broker = MagicMock()
    broker.get_current_price = MagicMock(return_value=None)
    broker.get_order_status = MagicMock(return_value=None)
    broker.cancel_order = MagicMock()
    return broker


class MockOrderResult:
    def __init__(self, success=True, order_id="ORD-001", message=""):
        self.success = success
        self.order_id = order_id
        self.message = message


class TestDuplicateOrderPrevention:
    """중복 주문 방지 테스트"""

    def test_has_active_buy_order_initially_false(self):
        om = OrderManager(make_config(), make_broker_mock())
        assert om.has_active_buy_order("005930") is False

    def test_register_and_check_active_buy(self):
        om = OrderManager(make_config(), make_broker_mock())
        om._register_active_order("005930", "ORD-001", OrderType.BUY)
        assert om.has_active_buy_order("005930") is True
        assert om.has_active_buy_order("035720") is False

    def test_unregister_active_buy(self):
        om = OrderManager(make_config(), make_broker_mock())
        om._register_active_order("005930", "ORD-001", OrderType.BUY)
        om._unregister_active_order("005930", OrderType.BUY)
        assert om.has_active_buy_order("005930") is False

    def test_register_sell_does_not_affect_buy(self):
        om = OrderManager(make_config(), make_broker_mock())
        om._register_active_order("005930", "ORD-001", OrderType.SELL)
        assert om.has_active_buy_order("005930") is False
        assert om.has_active_sell_order("005930") is True

    @pytest.mark.asyncio
    async def test_duplicate_buy_order_rejected(self):
        """동일 종목 매수 주문이 진행 중이면 새 매수 주문 거부"""
        broker = make_broker_mock()
        om = OrderManager(make_config(paper_trading=False), broker)
        # 수동으로 active 등록
        om._register_active_order("005930", "ORD-001", OrderType.BUY)

        result = await om.place_buy_order("005930", 10, 70000)
        assert result is None  # 거부됨

    @pytest.mark.asyncio
    async def test_duplicate_sell_order_rejected(self):
        """동일 종목 매도 주문이 진행 중이면 새 매도 주문 거부"""
        broker = make_broker_mock()
        om = OrderManager(make_config(paper_trading=False), broker)
        om._register_active_order("005930", "ORD-001", OrderType.SELL)

        result = await om.place_sell_order("005930", 10, 70000)
        assert result is None


class TestFundManagerIntegration:
    """FundManager 연동 테스트"""

    def test_set_fund_manager(self):
        om = OrderManager(make_config(), make_broker_mock())
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)
        assert om.fund_manager is fm

    @pytest.mark.asyncio
    async def test_buy_order_reserves_funds(self):
        """매수 주문 시 자금 예약"""
        broker = make_broker_mock()
        broker.place_buy_order = MagicMock(
            return_value=MockOrderResult(success=True, order_id="ORD-100")
        )
        om = OrderManager(make_config(paper_trading=False), broker)
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock_timeout:
            mock_timeout.return_value = MockOrderResult(success=True, order_id="ORD-100")

            result = await om.place_buy_order("005930", 10, 70000)

        assert result == "ORD-100"
        # 자금이 예약되어야 함 (700,000원)
        assert "ORD-100" in fm.order_reservations
        assert fm.order_reservations["ORD-100"] == 700_000

    @pytest.mark.asyncio
    async def test_buy_order_insufficient_funds_rejected(self):
        """자금 부족 시 매수 주문 거부"""
        broker = make_broker_mock()
        om = OrderManager(make_config(paper_trading=False), broker)
        fm = FundManager(initial_funds=100_000)  # 10만원만
        om.set_fund_manager(fm)

        result = await om.place_buy_order("005930", 10, 70000)  # 70만원 필요
        assert result is None
        assert fm.available_funds == 100_000  # 변동 없음

    @pytest.mark.asyncio
    async def test_buy_order_api_failure_releases_reserve(self):
        """API 실패 시 예약 해제"""
        broker = make_broker_mock()
        om = OrderManager(make_config(paper_trading=False), broker)
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock_timeout:
            mock_timeout.return_value = MockOrderResult(success=False, message="잔고 부족")

            result = await om.place_buy_order("005930", 10, 70000)

        assert result is None
        # 자금 예약이 해제되어야 함
        assert fm.available_funds == 10_000_000
        assert fm.reserved_funds == 0

    @pytest.mark.asyncio
    async def test_buy_order_api_timeout_releases_reserve(self):
        """API 타임아웃 시 예약 해제"""
        broker = make_broker_mock()
        om = OrderManager(make_config(paper_trading=False), broker)
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock_timeout:
            mock_timeout.return_value = None  # 타임아웃

            result = await om.place_buy_order("005930", 10, 70000)

        assert result is None
        assert fm.available_funds == 10_000_000
        assert fm.reserved_funds == 0


class TestMoveToCompletedFundManager:
    """_move_to_completed에서 FundManager 연동 테스트"""

    def test_cancelled_order_releases_fund_reservation(self):
        """취소된 주문의 자금 예약 해제"""
        om = OrderManager(make_config(), make_broker_mock())
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)

        # 자금 예약
        fm.reserve_funds("ORD-001", 700_000)
        assert fm.reserved_funds == 700_000

        # 주문 등록
        order = Order(
            order_id="ORD-001", stock_code="005930",
            order_type=OrderType.BUY, price=70000, quantity=10,
            timestamp=now_kst(), status=OrderStatus.CANCELLED,
        )
        om.pending_orders["ORD-001"] = order
        om.order_timeouts["ORD-001"] = datetime.now()

        # 완료 처리
        om._move_to_completed("ORD-001")

        # 예약이 해제되어야 함
        assert fm.reserved_funds == 0
        assert fm.available_funds == 10_000_000

    def test_timeout_order_releases_fund_reservation(self):
        """타임아웃 주문의 자금 예약 해제"""
        om = OrderManager(make_config(), make_broker_mock())
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)

        fm.reserve_funds("ORD-002", 500_000)

        order = Order(
            order_id="ORD-002", stock_code="035720",
            order_type=OrderType.BUY, price=50000, quantity=10,
            timestamp=now_kst(), status=OrderStatus.TIMEOUT,
        )
        om.pending_orders["ORD-002"] = order
        om.order_timeouts["ORD-002"] = datetime.now()

        om._move_to_completed("ORD-002")

        assert fm.reserved_funds == 0
        assert fm.available_funds == 10_000_000

    def test_filled_order_does_not_cancel_reservation(self):
        """체결된 주문은 cancel_order를 호출하지 않음 (confirm_order가 별도로 호출)"""
        om = OrderManager(make_config(), make_broker_mock())
        fm = FundManager(initial_funds=10_000_000)
        om.set_fund_manager(fm)

        fm.reserve_funds("ORD-003", 700_000)
        # confirm을 먼저 호출 (체결 시)
        fm.confirm_order("ORD-003", 700_000)

        order = Order(
            order_id="ORD-003", stock_code="005930",
            order_type=OrderType.BUY, price=70000, quantity=10,
            timestamp=now_kst(), status=OrderStatus.FILLED,
        )
        om.pending_orders["ORD-003"] = order
        om.order_timeouts["ORD-003"] = datetime.now()

        om._move_to_completed("ORD-003")

        # FILLED 상태이므로 cancel_order 호출 안됨
        assert fm.invested_funds == 700_000
        assert fm.reserved_funds == 0


class TestActiveOrderCleanupOnCompletion:
    """주문 완료 시 중복 방지 맵 정리 테스트"""

    def test_completed_buy_order_clears_active_map(self):
        om = OrderManager(make_config(), make_broker_mock())
        om._register_active_order("005930", "ORD-001", OrderType.BUY)
        assert om.has_active_buy_order("005930") is True

        order = Order(
            order_id="ORD-001", stock_code="005930",
            order_type=OrderType.BUY, price=70000, quantity=10,
            timestamp=now_kst(), status=OrderStatus.FILLED,
        )
        om.pending_orders["ORD-001"] = order
        om.order_timeouts["ORD-001"] = datetime.now()

        om._move_to_completed("ORD-001")
        assert om.has_active_buy_order("005930") is False

    def test_cancelled_sell_order_clears_active_map(self):
        om = OrderManager(make_config(), make_broker_mock())
        om._register_active_order("005930", "ORD-002", OrderType.SELL)
        assert om.has_active_sell_order("005930") is True

        order = Order(
            order_id="ORD-002", stock_code="005930",
            order_type=OrderType.SELL, price=70000, quantity=10,
            timestamp=now_kst(), status=OrderStatus.CANCELLED,
        )
        om.pending_orders["ORD-002"] = order
        om.order_timeouts["ORD-002"] = datetime.now()

        om._move_to_completed("ORD-002")
        assert om.has_active_sell_order("005930") is False


class TestPartialFillFundManager:
    """부분 체결 시 FundManager 연동 테스트"""

    def test_partial_fill_fund_manager_confirm(self):
        """부분 체결 타임아웃 시 체결 수량만 확정"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD-PF", 700_000)  # 10주 * 70000원

        # 부분 체결: 3주만 체결
        actual_amount = 70000 * 3  # 210,000원
        fm.confirm_order("ORD-PF", actual_amount)

        # 예약 해제, 투자 확정
        assert fm.reserved_funds == 0
        assert fm.invested_funds == 210_000
        # 환불: 700K - 210K = 490K
        assert fm.available_funds == 10_000_000 - 700_000 + 490_000


class TestPaperTradingBypassesFundCheck:
    """가상매매 모드에서는 FundManager 체크 안 함"""

    @pytest.mark.asyncio
    async def test_paper_trading_ignores_fund_manager(self):
        broker = make_broker_mock()
        om = OrderManager(make_config(paper_trading=True), broker)
        fm = FundManager(initial_funds=0)  # 자금 0
        om.set_fund_manager(fm)

        # 가상매매는 FundManager 체크를 안 하므로 성공해야 함
        result = await om.place_buy_order("005930", 10, 70000)
        assert result is not None  # 가상매매이므로 성공
