"""
Framework Broker Tests
======================

Tests for framework/broker.py - KISBroker tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from framework.broker import (
    Position,
    AccountInfo,
    BaseBroker,
    KISBroker,
    FundManager,
)


# ============================================================================
# Test: Position Dataclass
# ============================================================================

class TestPosition:
    """Tests for Position dataclass."""

    def test_position_creation(self):
        """Test creating Position."""
        position = Position(
            stock_code="005930",
            stock_name="Samsung Electronics",
            quantity=10,
            avg_price=70000
        )

        assert position.stock_code == "005930"
        assert position.stock_name == "Samsung Electronics"
        assert position.quantity == 10
        assert position.avg_price == 70000
        assert position.current_price == 0.0
        assert position.profit_loss == 0.0
        assert position.profit_loss_rate == 0.0

    def test_position_update_price(self):
        """Test Position.update_price method."""
        position = Position(
            stock_code="005930",
            stock_name="Samsung",
            quantity=10,
            avg_price=70000
        )

        position.update_price(72000)

        assert position.current_price == 72000
        assert position.profit_loss == 20000  # (72000 - 70000) * 10
        assert position.profit_loss_rate == pytest.approx(0.0286, rel=0.01)  # 2.86%

    def test_position_update_price_loss(self):
        """Test Position.update_price with loss."""
        position = Position(
            stock_code="005930",
            stock_name="Samsung",
            quantity=10,
            avg_price=70000
        )

        position.update_price(68000)

        assert position.current_price == 68000
        assert position.profit_loss == -20000
        assert position.profit_loss_rate == pytest.approx(-0.0286, rel=0.01)


# ============================================================================
# Test: AccountInfo Dataclass
# ============================================================================

class TestAccountInfo:
    """Tests for AccountInfo dataclass."""

    def test_account_info_creation(self):
        """Test creating AccountInfo."""
        account = AccountInfo(
            account_no="12345678-01",
            total_balance=10000000,
            available_cash=8000000,
            invested_amount=2000000
        )

        assert account.account_no == "12345678-01"
        assert account.total_balance == 10000000
        assert account.available_cash == 8000000
        assert account.invested_amount == 2000000
        assert account.positions == []

    def test_account_info_position_count(self):
        """Test AccountInfo.position_count property."""
        position1 = Position("005930", "Samsung", 10, 70000)
        position2 = Position("000660", "SK Hynix", 5, 150000)

        account = AccountInfo(
            account_no="12345678-01",
            total_balance=10000000,
            available_cash=5000000,
            invested_amount=5000000,
            positions=[position1, position2]
        )

        assert account.position_count == 2

    def test_account_info_utilization_rate(self):
        """Test AccountInfo.utilization_rate property."""
        account = AccountInfo(
            account_no="12345678-01",
            total_balance=10000000,
            available_cash=7000000,
            invested_amount=3000000
        )

        assert account.utilization_rate == pytest.approx(0.3, rel=0.01)

    def test_account_info_utilization_rate_zero_balance(self):
        """Test utilization_rate with zero balance."""
        account = AccountInfo(
            account_no="12345678-01",
            total_balance=0,
            available_cash=0,
            invested_amount=0
        )

        assert account.utilization_rate == 0.0


# ============================================================================
# Test: KISBroker
# ============================================================================

class TestKISBroker:
    """Tests for KISBroker class."""

    def test_kis_broker_creation(self):
        """Test KISBroker creation."""
        broker = KISBroker()

        assert broker is not None
        assert broker._connected is False
        assert broker.is_connected is False

    def test_kis_broker_creation_with_config(self):
        """Test KISBroker creation with config."""
        config = {
            'app_key': 'test_key',
            'app_secret': 'test_secret',
            'account_no': '12345678-01'
        }
        broker = KISBroker(config)

        assert broker.config == config

    def test_kis_broker_get_account_balance_not_connected(self):
        """Test get_account_balance when not connected."""
        broker = KISBroker()

        result = broker.get_account_balance()

        assert result == {}

    def test_kis_broker_get_holdings_not_connected(self):
        """Test get_holdings when not connected."""
        broker = KISBroker()

        result = broker.get_holdings()

        assert result == []

    def test_kis_broker_get_available_cash_not_connected(self):
        """Test get_available_cash when not connected."""
        broker = KISBroker()

        result = broker.get_available_cash()

        assert result == 0.0

    def test_kis_broker_get_current_price_not_connected(self):
        """Test get_current_price when not connected."""
        broker = KISBroker()

        result = broker.get_current_price("005930")

        assert result is None


# ============================================================================
# Test: FundManager
# ============================================================================

class TestFundManager:
    """Tests for FundManager class."""

    @pytest.fixture
    def fund_manager(self):
        """Create FundManager instance."""
        return FundManager(initial_funds=10000000)

    def test_fund_manager_creation(self, fund_manager):
        """Test FundManager creation."""
        assert fund_manager.total_funds == 10000000
        assert fund_manager.available_funds == 10000000
        assert fund_manager.reserved_funds == 0.0
        assert fund_manager.invested_funds == 0.0

    def test_fund_manager_update_total_funds(self, fund_manager):
        """Test update_total_funds method."""
        fund_manager.update_total_funds(12000000)

        assert fund_manager.total_funds == 12000000
        assert fund_manager.available_funds == 12000000

    def test_fund_manager_get_max_buy_amount(self, fund_manager):
        """Test get_max_buy_amount method."""
        max_amount = fund_manager.get_max_buy_amount("005930")

        # Default max_position_ratio is 0.09 (9%)
        expected = 10000000 * 0.09
        assert max_amount == expected

    def test_fund_manager_reserve_funds(self, fund_manager):
        """Test reserve_funds method."""
        result = fund_manager.reserve_funds("ORD001", 500000)

        assert result is True
        assert fund_manager.available_funds == 9500000
        assert fund_manager.reserved_funds == 500000

    def test_fund_manager_reserve_funds_insufficient(self, fund_manager):
        """Test reserve_funds fails with insufficient funds."""
        result = fund_manager.reserve_funds("ORD001", 15000000)

        assert result is False
        assert fund_manager.available_funds == 10000000

    def test_fund_manager_reserve_funds_duplicate(self, fund_manager):
        """Test reserve_funds fails for duplicate order."""
        fund_manager.reserve_funds("ORD001", 500000)
        result = fund_manager.reserve_funds("ORD001", 500000)

        assert result is False

    def test_fund_manager_confirm_order(self, fund_manager):
        """Test confirm_order method."""
        fund_manager.reserve_funds("ORD001", 500000)
        fund_manager.confirm_order("ORD001", 495000)

        assert fund_manager.invested_funds == 495000
        assert fund_manager.reserved_funds == 0
        assert fund_manager.available_funds == 9505000  # 9500000 + 5000 refund

    def test_fund_manager_cancel_order(self, fund_manager):
        """Test cancel_order method."""
        fund_manager.reserve_funds("ORD001", 500000)
        fund_manager.cancel_order("ORD001")

        assert fund_manager.available_funds == 10000000
        assert fund_manager.reserved_funds == 0

    def test_fund_manager_release_investment(self, fund_manager):
        """Test release_investment method."""
        fund_manager.reserve_funds("ORD001", 500000)
        fund_manager.confirm_order("ORD001", 500000)
        fund_manager.release_investment(500000)

        assert fund_manager.invested_funds == 0
        assert fund_manager.available_funds == 10000000

    def test_fund_manager_get_status(self, fund_manager):
        """Test get_status method."""
        fund_manager.reserve_funds("ORD001", 500000)
        fund_manager.confirm_order("ORD001", 500000)

        status = fund_manager.get_status()

        assert status['total_funds'] == 10000000
        assert status['available_funds'] == 9500000
        assert status['invested_funds'] == 500000
        assert status['reserved_funds'] == 0
        assert 'utilization_rate' in status


# ============================================================================
# Test: KISBroker New Methods (not-connected guard)
# ============================================================================

class TestKISBrokerNewMethods:
    """Tests for newly added KISBroker methods (not-connected guard)."""

    def test_get_current_prices_not_connected(self):
        broker = KISBroker()
        assert broker.get_current_prices(["005930", "000660"]) == {}

    def test_get_ohlcv_data_not_connected(self):
        broker = KISBroker()
        assert broker.get_ohlcv_data("005930") is None

    def test_get_index_data_not_connected(self):
        broker = KISBroker()
        assert broker.get_index_data() is None

    def test_get_investor_flow_data_not_connected(self):
        broker = KISBroker()
        assert broker.get_investor_flow_data() is None

    def test_place_buy_order_not_connected(self):
        broker = KISBroker()
        result = broker.place_buy_order("005930", 1, 70000)
        assert result["success"] is False

    def test_place_sell_order_not_connected(self):
        broker = KISBroker()
        result = broker.place_sell_order("005930", 1, 70000)
        assert result["success"] is False

    def test_cancel_order_not_connected(self):
        broker = KISBroker()
        result = broker.cancel_order("12345")
        assert result["success"] is False

    def test_get_order_status_not_connected(self):
        broker = KISBroker()
        assert broker.get_order_status("12345") is None

    def test_health_check_not_connected(self):
        broker = KISBroker()
        assert broker.health_check() is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
