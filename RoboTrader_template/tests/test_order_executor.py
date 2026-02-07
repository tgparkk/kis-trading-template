"""
OrderExecutor 유닛 테스트
- 가상매매/실전 매수/매도 주문
- API 타임아웃 처리
- 주문 취소
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from core.models import Order, OrderType, OrderStatus, TradingConfig
from core.order_manager import OrderManager
from utils.korean_time import now_kst


def _make_order_manager(paper_trading=True, api_manager=None, telegram=None, db_manager=None):
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

    om = OrderManager(config, api_manager, telegram, db_manager)
    return om


class TestPaperBuyOrder:
    """가상매매 매수 주문"""

    @pytest.mark.asyncio
    async def test_paper_buy_success(self):
        om = _make_order_manager(paper_trading=True)
        order_id = await om.place_buy_order("005930", 10, 70000)

        assert order_id is not None
        assert order_id.startswith("VT-BUY-005930")
        assert len(om.completed_orders) == 1
        assert om.completed_orders[0].status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_paper_buy_saves_db(self):
        db = Mock()
        db.save_virtual_buy.return_value = 1
        om = _make_order_manager(paper_trading=True, db_manager=db)
        om.trading_manager = None

        await om.place_buy_order("005930", 10, 70000,
                                 target_profit_rate=0.17,
                                 stop_loss_rate=0.09)

        db.save_virtual_buy.assert_called_once()
        call_kwargs = db.save_virtual_buy.call_args
        assert call_kwargs[1]['stock_code'] == "005930"
        assert call_kwargs[1]['quantity'] == 10


class TestRealBuyOrder:
    """실전 매수 주문"""

    @pytest.mark.asyncio
    async def test_real_buy_success(self):
        api = Mock()
        order_result = Mock()
        order_result.success = True
        order_result.order_id = "REAL-ORD-001"
        order_result.message = ""

        om = _make_order_manager(paper_trading=False, api_manager=api)
        om.trading_manager = None

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock_timeout:
            mock_timeout.return_value = order_result
            order_id = await om.place_buy_order("005930", 10, 70000)

        assert order_id == "REAL-ORD-001"
        assert "REAL-ORD-001" in om.pending_orders
        assert om.pending_orders["REAL-ORD-001"].status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_real_buy_api_fail(self):
        api = Mock()
        order_result = Mock()
        order_result.success = False
        order_result.message = "잔고부족"

        om = _make_order_manager(paper_trading=False, api_manager=api)

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock_timeout:
            mock_timeout.return_value = order_result
            order_id = await om.place_buy_order("005930", 10, 70000)

        assert order_id is None
        assert len(om.pending_orders) == 0

    @pytest.mark.asyncio
    async def test_real_buy_timeout(self):
        """안전성 이슈 #1: API 타임아웃 후 주문ID 손실"""
        api = Mock()
        om = _make_order_manager(paper_trading=False, api_manager=api)

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock_timeout:
            mock_timeout.return_value = None  # 타임아웃
            order_id = await om.place_buy_order("005930", 10, 70000)

        assert order_id is None
        assert len(om.pending_orders) == 0


class TestPaperSellOrder:
    """가상매매 매도 주문"""

    @pytest.mark.asyncio
    async def test_paper_sell_success(self):
        om = _make_order_manager(paper_trading=True)
        order_id = await om.place_sell_order("005930", 10, 72000)

        assert order_id is not None
        assert order_id.startswith("VT-SELL-005930")
        assert len(om.completed_orders) == 1


class TestRealSellOrder:
    """실전 매도 주문"""

    @pytest.mark.asyncio
    async def test_real_sell_market(self):
        api = Mock()
        order_result = Mock()
        order_result.success = True
        order_result.order_id = "SELL-ORD-001"
        order_result.message = ""

        om = _make_order_manager(paper_trading=False, api_manager=api)
        om.trading_manager = None

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock_timeout:
            mock_timeout.return_value = order_result
            order_id = await om.place_sell_order("005930", 10, 72000, market=True)

        assert order_id == "SELL-ORD-001"
        call_args = mock_timeout.call_args
        assert call_args[0][2] == "005930"
        assert "01" in str(call_args)

    @pytest.mark.asyncio
    async def test_real_sell_limit(self):
        api = Mock()
        order_result = Mock()
        order_result.success = True
        order_result.order_id = "SELL-ORD-002"
        order_result.message = ""

        om = _make_order_manager(paper_trading=False, api_manager=api)
        om.trading_manager = None

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock_timeout:
            mock_timeout.return_value = order_result
            order_id = await om.place_sell_order("005930", 10, 72000, market=False)

        assert order_id == "SELL-ORD-002"
        assert "00" in str(mock_timeout.call_args)


class TestCancelOrder:
    """주문 취소"""

    @pytest.mark.asyncio
    async def test_cancel_existing(self):
        om = _make_order_manager(paper_trading=False)
        ts = now_kst()
        order = Order(
            order_id="ORD-CANCEL-001",
            stock_code="005930",
            order_type=OrderType.BUY,
            price=70000,
            quantity=10,
            timestamp=ts
        )
        om.pending_orders["ORD-CANCEL-001"] = order
        om.order_timeouts["ORD-CANCEL-001"] = ts

        cancel_result = Mock()
        cancel_result.success = True
        cancel_result.message = ""

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock_timeout:
            mock_timeout.return_value = cancel_result
            result = await om.cancel_order("ORD-CANCEL-001")

        assert result is True
        assert "ORD-CANCEL-001" not in om.pending_orders
        assert len(om.completed_orders) == 1
        assert om.completed_orders[0].status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self):
        om = _make_order_manager(paper_trading=False)
        result = await om.cancel_order("NON-EXIST")
        assert result is False
