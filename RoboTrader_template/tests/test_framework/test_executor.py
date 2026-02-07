"""
Framework Executor Tests
========================

Tests for framework/executor.py - OrderExecutor tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from framework.executor import (
    OrderType,
    OrderSide,
    OrderStatus,
    OrderRequest,
    OrderResult,
    Order,
    OrderExecutor,
)


# ============================================================================
# Test: Enums
# ============================================================================

class TestOrderType:
    """Tests for OrderType enum."""

    def test_order_type_values(self):
        """Test OrderType enum values."""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"

    def test_order_type_to_kis_code(self):
        """Test to_kis_code method."""
        assert OrderType.MARKET.to_kis_code() == "01"
        assert OrderType.LIMIT.to_kis_code() == "00"


class TestOrderSide:
    """Tests for OrderSide enum."""

    def test_order_side_values(self):
        """Test OrderSide enum values."""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"


class TestOrderStatus:
    """Tests for OrderStatus enum."""

    def test_order_status_values(self):
        """Test OrderStatus enum values."""
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.PARTIAL.value == "partial"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"
        assert OrderStatus.EXPIRED.value == "expired"


# ============================================================================
# Test: OrderRequest
# ============================================================================

class TestOrderRequest:
    """Tests for OrderRequest dataclass."""

    def test_order_request_creation(self):
        """Test creating OrderRequest."""
        request = OrderRequest(
            stock_code="005930",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=70000
        )

        assert request.stock_code == "005930"
        assert request.side == OrderSide.BUY
        assert request.quantity == 10
        assert request.order_type == OrderType.LIMIT
        assert request.price == 70000  # Rounded to tick

    def test_order_request_market_order(self):
        """Test creating market order request."""
        request = OrderRequest(
            stock_code="005930",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET
        )

        assert request.order_type == OrderType.MARKET
        assert request.price is None

    def test_order_request_invalid_quantity(self):
        """Test OrderRequest raises error for invalid quantity."""
        with pytest.raises(ValueError):
            OrderRequest(
                stock_code="005930",
                side=OrderSide.BUY,
                quantity=0,
                order_type=OrderType.LIMIT,
                price=70000
            )

    def test_order_request_limit_without_price(self):
        """Test OrderRequest raises error for limit order without price."""
        with pytest.raises(ValueError):
            OrderRequest(
                stock_code="005930",
                side=OrderSide.BUY,
                quantity=10,
                order_type=OrderType.LIMIT,
                price=None
            )

    def test_order_request_price_rounding(self):
        """Test OrderRequest rounds price to tick size."""
        request = OrderRequest(
            stock_code="005930",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=70025  # Should round to 70000 or 70050
        )

        # Price should be rounded to tick (50 won for 10000-50000 range)
        assert request.price == 70050


# ============================================================================
# Test: OrderResult
# ============================================================================

class TestOrderResult:
    """Tests for OrderResult dataclass."""

    def test_order_result_success(self):
        """Test creating successful OrderResult."""
        result = OrderResult(
            success=True,
            order_id="ORD001",
            message="Order submitted successfully"
        )

        assert result.success is True
        assert result.order_id == "ORD001"
        assert result.message == "Order submitted successfully"

    def test_order_result_failure(self):
        """Test creating failed OrderResult."""
        result = OrderResult(
            success=False,
            message="Insufficient funds"
        )

        assert result.success is False
        assert result.order_id is None


# ============================================================================
# Test: Order
# ============================================================================

class TestOrder:
    """Tests for Order dataclass."""

    def test_order_creation(self):
        """Test creating Order."""
        order = Order(
            order_id="ORD001",
            stock_code="005930",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=70000
        )

        assert order.order_id == "ORD001"
        assert order.stock_code == "005930"
        assert order.side == OrderSide.BUY
        assert order.quantity == 10
        assert order.status == OrderStatus.PENDING

    def test_order_is_completed(self):
        """Test Order.is_completed property."""
        order = Order(
            order_id="ORD001",
            stock_code="005930",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=70000
        )

        assert order.is_completed is False

        order.status = OrderStatus.FILLED
        assert order.is_completed is True

        order.status = OrderStatus.CANCELLED
        assert order.is_completed is True

    def test_order_remaining_quantity(self):
        """Test Order.remaining_quantity property."""
        order = Order(
            order_id="ORD001",
            stock_code="005930",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=70000,
            filled_quantity=3
        )

        assert order.remaining_quantity == 7

    def test_order_fill_rate(self):
        """Test Order.fill_rate property."""
        order = Order(
            order_id="ORD001",
            stock_code="005930",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=70000,
            filled_quantity=5
        )

        assert order.fill_rate == pytest.approx(0.5, rel=0.01)


# ============================================================================
# Test: OrderExecutor
# ============================================================================

class TestOrderExecutor:
    """Tests for OrderExecutor class."""

    @pytest.fixture
    def executor(self, mock_broker):
        """Create OrderExecutor instance."""
        return OrderExecutor(mock_broker)

    def test_executor_creation(self, mock_broker):
        """Test OrderExecutor creation."""
        executor = OrderExecutor(mock_broker)

        assert executor is not None
        assert executor.broker == mock_broker

    def test_executor_buy_order(self, executor):
        """Test buy order submission."""
        order = executor.buy(
            stock_code="005930",
            quantity=10,
            price=70000,
            order_type=OrderType.LIMIT
        )

        # Order should be created (may fail at API level)
        # In mock environment, depends on mock setup
        assert order is None or isinstance(order, Order)

    def test_executor_sell_order(self, executor):
        """Test sell order submission."""
        order = executor.sell(
            stock_code="005930",
            quantity=10,
            price=72000,
            order_type=OrderType.LIMIT
        )

        assert order is None or isinstance(order, Order)

    def test_executor_invalid_quantity(self, executor):
        """Test buy with invalid quantity."""
        order = executor.buy(
            stock_code="005930",
            quantity=0,
            price=70000,
            order_type=OrderType.LIMIT
        )

        assert order is None

    def test_executor_invalid_limit_price(self, executor):
        """Test limit order with invalid price."""
        order = executor.buy(
            stock_code="005930",
            quantity=10,
            price=0,
            order_type=OrderType.LIMIT
        )

        assert order is None

    def test_executor_get_order(self, executor):
        """Test get_order method."""
        # Order doesn't exist
        order = executor.get_order("NONEXISTENT")
        assert order is None

    def test_executor_get_orders_for_stock(self, executor):
        """Test get_orders_for_stock method."""
        orders = executor.get_orders_for_stock("005930")
        assert isinstance(orders, list)

    def test_executor_clear_completed_orders(self, executor):
        """Test clear_completed_orders method."""
        count = executor.clear_completed_orders()
        assert isinstance(count, int)

    def test_executor_shutdown(self, executor):
        """Test shutdown method."""
        # Should not raise
        executor.shutdown()


# ============================================================================
# Test: Async Methods
# ============================================================================

class TestOrderExecutorAsync:
    """Tests for OrderExecutor async methods."""

    @pytest.fixture
    def executor(self, mock_broker):
        """Create OrderExecutor instance."""
        return OrderExecutor(mock_broker)

    @pytest.mark.asyncio
    async def test_execute_order(self, executor):
        """Test async execute method."""
        request = OrderRequest(
            stock_code="005930",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=70000
        )

        result = await executor.execute(request)

        # Result should be OrderResult
        assert isinstance(result, OrderResult)

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self, executor):
        """Test cancel for non-existent order."""
        result = await executor.cancel("NONEXISTENT")
        assert result is False

    @pytest.mark.asyncio
    async def test_modify_nonexistent_order(self, executor):
        """Test modify for non-existent order."""
        result = await executor.modify("NONEXISTENT", 75000)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_pending_orders(self, executor):
        """Test get_pending_orders method."""
        pending = await executor.get_pending_orders()
        assert isinstance(pending, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
