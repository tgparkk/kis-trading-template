"""
OrderCompletionHandler 유닛 테스트
- 매수/매도 체결 처리
- 전략 콜백
- 레이스 컨디션 방지
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
from core.models import (
    TradingStock, StockState, Order, OrderType, OrderStatus, Position
)


@pytest.fixture
def state_manager():
    with patch('core.trading.stock_state_manager.setup_logger'):
        from core.trading.stock_state_manager import StockStateManager
        mgr = StockStateManager()
    return mgr


@pytest.fixture
def order_manager_mock():
    om = Mock()
    om.get_completed_orders.return_value = []
    return om


@pytest.fixture
def handler(state_manager, order_manager_mock):
    with patch('core.trading.order_completion_handler.setup_logger'):
        from core.trading.order_completion_handler import OrderCompletionHandler
        h = OrderCompletionHandler(state_manager, order_manager_mock)
    return h


def make_stock(code="005930", state=StockState.BUY_PENDING):
    return TradingStock(
        stock_code=code, stock_name="삼성전자",
        state=state, selected_time=datetime.now(),
        selection_reason="테스트"
    )


def make_order(code="005930", otype=OrderType.BUY, status=OrderStatus.FILLED,
               order_id="ORD001", price=70000, qty=10):
    return Order(
        order_id=order_id, stock_code=code, order_type=otype,
        price=price, quantity=qty, timestamp=datetime.now(), status=status
    )


class TestBuyFillCallback:
    def test_buy_fill_sets_position(self, handler, state_manager):
        stock = make_stock()
        stock.current_order_id = "ORD001"
        state_manager.register_stock(stock)

        order = make_order()
        with patch.object(handler, '_set_virtual_buy_info'), \
             patch.object(handler, '_save_real_buy_record'):
            handler._process_buy_fill_callback(stock, order)

        assert stock.state == StockState.POSITIONED
        assert stock.position is not None
        assert stock.position.quantity == 10
        assert stock.order_processed is True

    def test_buy_fill_wrong_state(self, handler, state_manager):
        stock = make_stock(state=StockState.POSITIONED)
        state_manager.register_stock(stock)
        order = make_order()
        # Should log warning but not crash
        handler._process_buy_fill_callback(stock, order)
        # State unchanged
        assert stock.state == StockState.POSITIONED


class TestSellFillCallback:
    def test_sell_fill_clears_position(self, handler, state_manager):
        stock = make_stock(state=StockState.SELL_PENDING)
        stock.position = Position(stock_code="005930", quantity=10, avg_price=70000)
        stock.current_order_id = "ORD002"
        state_manager.register_stock(stock)

        order = make_order(otype=OrderType.SELL, order_id="ORD002")
        with patch.object(handler, '_save_real_sell_record', return_value=1.5):
            handler._process_sell_fill_callback(stock, order)

        assert stock.state == StockState.COMPLETED
        assert stock.position is None


class TestStrategyCallback:
    def test_notify_strategy(self, handler):
        strategy = Mock()
        strategy.on_order_filled = Mock()
        handler.set_strategy(strategy)

        order = make_order()
        with patch('core.trading.order_completion_handler.now_kst', return_value=datetime.now()):
            handler._notify_strategy_order_filled(order)
        strategy.on_order_filled.assert_called_once()

    def test_no_strategy(self, handler):
        order = make_order()
        # Should not raise
        handler._notify_strategy_order_filled(order)


class TestRaceCondition:
    def test_duplicate_callback_prevented(self, handler, state_manager):
        stock = make_stock()
        stock.current_order_id = "ORD001"
        state_manager.register_stock(stock)

        order = make_order()

        with patch.object(handler, '_set_virtual_buy_info'), \
             patch.object(handler, '_save_real_buy_record'):
            # First call
            asyncio.get_event_loop().run_until_complete(
                handler.on_order_filled(order)
            )
        assert stock.order_processed is True

        # Second call - should be skipped
        old_state = stock.state
        asyncio.get_event_loop().run_until_complete(
            handler.on_order_filled(order)
        )
        assert stock.state == old_state


class TestCheckOrderCompletions:
    def test_buy_order_filled(self, handler, state_manager, order_manager_mock):
        stock = make_stock()
        stock.current_order_id = "ORD001"
        state_manager.register_stock(stock)

        filled_order = make_order(status=OrderStatus.FILLED)
        order_manager_mock.get_completed_orders.return_value = [filled_order]

        with patch.object(handler, '_set_virtual_buy_info'), \
             patch.object(handler, '_save_real_buy_record'):
            asyncio.get_event_loop().run_until_complete(
                handler.check_order_completions()
            )

        assert stock.state == StockState.POSITIONED

    def test_buy_order_cancelled(self, handler, state_manager, order_manager_mock):
        """
        매수 주문이 취소되면 SELECTED 상태로 복귀해야 함.
        (OrderStatus.FAILED enum 추가로 버그 수정 완료)
        """
        stock = make_stock()
        stock.current_order_id = "ORD001"
        state_manager.register_stock(stock)

        cancelled_order = make_order(status=OrderStatus.CANCELLED)
        order_manager_mock.get_completed_orders.return_value = [cancelled_order]

        asyncio.get_event_loop().run_until_complete(
            handler.check_order_completions()
        )

        # 버그 수정 후: 취소된 주문은 SELECTED 상태로 정상 복귀
        assert stock.state == StockState.SELECTED
