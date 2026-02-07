"""
Base Strategy Tests
===================

Tests for strategy/base.py interface.

Test Requirements:
- test_signal_type_enum(): SignalType enum value tests
- test_signal_dataclass(): Signal dataclass tests
- test_base_strategy_abstract(): Abstract class inheritance tests
"""

import pytest
from typing import Dict, Any, Optional
import pandas as pd
from datetime import datetime, timezone, timedelta
from abc import ABC

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from strategies.base import (
    BaseStrategy,
    Signal,
    SignalType,
    OrderInfo,
)


# ============================================================================
# Mock Strategy for Testing
# ============================================================================

class MockStrategy(BaseStrategy):
    """Mock strategy for testing base class."""

    name = "MockStrategy"
    version = "1.0.0"
    description = "Mock strategy for testing"
    author = "Test"

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor
        self._is_initialized = True
        return True

    def on_market_open(self) -> None:
        pass

    def generate_signal(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        # Return buy signal if data shows price increase
        if data is not None and len(data) >= 2:
            if data['close'].iloc[-1] > data['close'].iloc[-2]:
                return Signal(
                    signal_type=SignalType.BUY,
                    stock_code=stock_code,
                    confidence=80.0,
                    target_price=data['close'].iloc[-1] * 1.03,
                    stop_loss=data['close'].iloc[-1] * 0.98,
                    reasons=["Price increased"]
                )
        return None

    def on_order_filled(self, order: OrderInfo) -> None:
        pass

    def on_market_close(self) -> None:
        pass


# ============================================================================
# Test: test_signal_type_enum()
# ============================================================================

class TestSignalTypeEnum:
    """Tests for SignalType enum - test_signal_type_enum()."""

    def test_signal_type_values(self):
        """Test SignalType enum has correct values."""
        assert SignalType.STRONG_BUY.value == "strong_buy"
        assert SignalType.BUY.value == "buy"
        assert SignalType.HOLD.value == "hold"
        assert SignalType.SELL.value == "sell"
        assert SignalType.STRONG_SELL.value == "strong_sell"

    def test_signal_type_all_members(self):
        """Test all SignalType members exist."""
        members = list(SignalType)
        assert len(members) == 5

        member_names = [m.name for m in members]
        assert 'STRONG_BUY' in member_names
        assert 'BUY' in member_names
        assert 'HOLD' in member_names
        assert 'SELL' in member_names
        assert 'STRONG_SELL' in member_names

    def test_signal_type_comparison(self):
        """Test SignalType comparison."""
        assert SignalType.BUY == SignalType.BUY
        assert SignalType.BUY != SignalType.SELL

    def test_signal_type_string_conversion(self):
        """Test SignalType to string conversion."""
        assert str(SignalType.BUY.value) == "buy"
        assert str(SignalType.STRONG_BUY.value) == "strong_buy"


# ============================================================================
# Test: test_signal_dataclass()
# ============================================================================

class TestSignalDataclass:
    """Tests for Signal dataclass - test_signal_dataclass()."""

    def test_signal_creation_basic(self):
        """Test creating a basic Signal."""
        signal = Signal(
            signal_type=SignalType.BUY,
            stock_code="005930",
            confidence=80.0
        )

        assert signal.signal_type == SignalType.BUY
        assert signal.stock_code == "005930"
        assert signal.confidence == 80.0
        assert signal.target_price is None
        assert signal.stop_loss is None
        assert signal.reasons == []
        assert signal.metadata == {}

    def test_signal_creation_full(self):
        """Test creating a Signal with all fields."""
        signal = Signal(
            signal_type=SignalType.STRONG_BUY,
            stock_code="005930",
            confidence=90.0,
            target_price=75000,
            stop_loss=68000,
            reasons=["Golden cross", "Volume surge"],
            metadata={"volume_ratio": 1.5, "bisector_status": "HOLDING"}
        )

        assert signal.signal_type == SignalType.STRONG_BUY
        assert signal.stock_code == "005930"
        assert signal.confidence == 90.0
        assert signal.target_price == 75000
        assert signal.stop_loss == 68000
        assert len(signal.reasons) == 2
        assert "Golden cross" in signal.reasons
        assert signal.metadata["volume_ratio"] == 1.5

    def test_signal_is_buy_property(self):
        """Test Signal.is_buy property."""
        buy_signal = Signal(
            signal_type=SignalType.BUY,
            stock_code="005930"
        )
        strong_buy_signal = Signal(
            signal_type=SignalType.STRONG_BUY,
            stock_code="005930"
        )
        hold_signal = Signal(
            signal_type=SignalType.HOLD,
            stock_code="005930"
        )
        sell_signal = Signal(
            signal_type=SignalType.SELL,
            stock_code="005930"
        )

        assert buy_signal.is_buy is True
        assert strong_buy_signal.is_buy is True
        assert hold_signal.is_buy is False
        assert sell_signal.is_buy is False

    def test_signal_is_sell_property(self):
        """Test Signal.is_sell property."""
        sell_signal = Signal(
            signal_type=SignalType.SELL,
            stock_code="005930"
        )
        strong_sell_signal = Signal(
            signal_type=SignalType.STRONG_SELL,
            stock_code="005930"
        )
        buy_signal = Signal(
            signal_type=SignalType.BUY,
            stock_code="005930"
        )

        assert sell_signal.is_sell is True
        assert strong_sell_signal.is_sell is True
        assert buy_signal.is_sell is False

    def test_signal_is_strong_property(self):
        """Test Signal.is_strong property."""
        strong_buy = Signal(signal_type=SignalType.STRONG_BUY, stock_code="005930")
        strong_sell = Signal(signal_type=SignalType.STRONG_SELL, stock_code="005930")
        buy = Signal(signal_type=SignalType.BUY, stock_code="005930")
        sell = Signal(signal_type=SignalType.SELL, stock_code="005930")

        assert strong_buy.is_strong is True
        assert strong_sell.is_strong is True
        assert buy.is_strong is False
        assert sell.is_strong is False

    def test_signal_to_dict(self):
        """Test Signal.to_dict method."""
        signal = Signal(
            signal_type=SignalType.BUY,
            stock_code="005930",
            confidence=85.0,
            target_price=75000,
            stop_loss=68000,
            reasons=["Test reason"],
            metadata={"key": "value"}
        )

        d = signal.to_dict()

        assert d['signal_type'] == 'buy'
        assert d['stock_code'] == '005930'
        assert d['confidence'] == 85.0
        assert d['target_price'] == 75000
        assert d['stop_loss'] == 68000
        assert d['reasons'] == ["Test reason"]
        assert d['metadata'] == {"key": "value"}

    def test_signal_default_values(self):
        """Test Signal default values."""
        signal = Signal(
            signal_type=SignalType.HOLD,
            stock_code="005930"
        )

        assert signal.confidence == 0.0
        assert signal.target_price is None
        assert signal.stop_loss is None
        assert signal.reasons == []
        assert signal.metadata == {}


# ============================================================================
# Test: OrderInfo Dataclass
# ============================================================================

class TestOrderInfo:
    """Tests for OrderInfo dataclass."""

    def test_order_info_creation(self):
        """Test creating OrderInfo."""
        kst = timezone(timedelta(hours=9))
        filled_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst)

        order = OrderInfo(
            order_id="ORD202401150001",
            stock_code="005930",
            side="buy",
            quantity=10,
            price=72000,
            filled_at=filled_time
        )

        assert order.order_id == "ORD202401150001"
        assert order.stock_code == "005930"
        assert order.side == "buy"
        assert order.quantity == 10
        assert order.price == 72000
        assert order.filled_at == filled_time

    def test_order_info_is_buy(self):
        """Test OrderInfo.is_buy property."""
        kst = timezone(timedelta(hours=9))
        filled_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst)

        buy_order = OrderInfo(
            order_id="ORD001",
            stock_code="005930",
            side="buy",
            quantity=10,
            price=72000,
            filled_at=filled_time
        )
        sell_order = OrderInfo(
            order_id="ORD002",
            stock_code="005930",
            side="sell",
            quantity=10,
            price=74000,
            filled_at=filled_time
        )

        assert buy_order.is_buy is True
        assert buy_order.is_sell is False
        assert sell_order.is_buy is False
        assert sell_order.is_sell is True

    def test_order_info_total_amount(self):
        """Test OrderInfo.total_amount property."""
        kst = timezone(timedelta(hours=9))
        filled_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst)

        order = OrderInfo(
            order_id="ORD001",
            stock_code="005930",
            side="buy",
            quantity=10,
            price=72000,
            filled_at=filled_time
        )

        assert order.total_amount == 720000

    def test_order_info_to_dict(self):
        """Test OrderInfo.to_dict method."""
        kst = timezone(timedelta(hours=9))
        filled_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst)

        order = OrderInfo(
            order_id="ORD001",
            stock_code="005930",
            side="buy",
            quantity=10,
            price=72000,
            filled_at=filled_time
        )

        d = order.to_dict()

        assert d['order_id'] == "ORD001"
        assert d['stock_code'] == "005930"
        assert d['side'] == "buy"
        assert d['quantity'] == 10
        assert d['price'] == 72000


# ============================================================================
# Test: test_base_strategy_abstract()
# ============================================================================

class TestBaseStrategyAbstract:
    """Tests for BaseStrategy abstract class - test_base_strategy_abstract()."""

    def test_base_strategy_is_abstract(self):
        """Test that BaseStrategy is an abstract class."""
        assert issubclass(BaseStrategy, ABC)

    def test_base_strategy_cannot_instantiate(self):
        """Test that BaseStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseStrategy({})

    def test_base_strategy_requires_abstract_methods(self):
        """Test that subclass must implement all abstract methods."""
        # This should fail because IncompleteStrategy doesn't implement all methods
        class IncompleteStrategy(BaseStrategy):
            def on_init(self, broker, data_provider, executor) -> bool:
                return True

        with pytest.raises(TypeError):
            IncompleteStrategy({})

    def test_mock_strategy_can_be_instantiated(self):
        """Test that MockStrategy (complete implementation) can be instantiated."""
        strategy = MockStrategy({'name': 'test'})
        assert strategy is not None
        assert isinstance(strategy, BaseStrategy)

    def test_base_strategy_class_attributes(self):
        """Test BaseStrategy class attributes."""
        assert hasattr(BaseStrategy, 'name')
        assert hasattr(BaseStrategy, 'version')
        assert hasattr(BaseStrategy, 'description')
        assert hasattr(BaseStrategy, 'author')

    def test_mock_strategy_attributes(self):
        """Test MockStrategy class attributes."""
        assert MockStrategy.name == "MockStrategy"
        assert MockStrategy.version == "1.0.0"
        assert MockStrategy.description == "Mock strategy for testing"
        assert MockStrategy.author == "Test"


# ============================================================================
# Test: BaseStrategy Methods
# ============================================================================

class TestBaseStrategyMethods:
    """Tests for BaseStrategy instance methods."""

    @pytest.fixture
    def strategy(self):
        """Create mock strategy instance."""
        config = {
            'name': 'test_strategy',
            'description': 'Test strategy',
            'risk_management': {
                'take_profit_ratio': 0.03,
                'stop_loss_ratio': 0.02
            },
            'parameters': {
                'threshold': 0.05
            }
        }
        return MockStrategy(config)

    def test_strategy_initialization(self, strategy):
        """Test strategy initialization with config."""
        assert strategy.config is not None
        assert strategy._is_initialized is False

    def test_strategy_on_init(self, strategy):
        """Test on_init method."""
        result = strategy.on_init(None, None, None)
        assert result is True
        assert strategy.is_initialized is True

    def test_get_config(self, strategy):
        """Test get_config method returns config copy."""
        config = strategy.get_config()

        assert config is not None
        assert isinstance(config, dict)
        assert 'name' in config
        assert 'risk_management' in config

        # Verify it's a copy
        config['modified'] = True
        assert 'modified' not in strategy.config

    def test_get_param_simple_key(self, strategy):
        """Test get_param with simple key."""
        result = strategy.get_param('name')
        assert result == 'test_strategy'

    def test_get_param_nested_key(self, strategy):
        """Test get_param with nested key (dot notation)."""
        result = strategy.get_param('risk_management.take_profit_ratio')
        assert result == 0.03

        result = strategy.get_param('parameters.threshold')
        assert result == 0.05

    def test_get_param_default_value(self, strategy):
        """Test get_param returns default for non-existent key."""
        result = strategy.get_param('non_existent', 'default_value')
        assert result == 'default_value'

        result = strategy.get_param('risk_management.non_existent', 0.01)
        assert result == 0.01

    def test_is_initialized_property(self, strategy):
        """Test is_initialized property."""
        assert strategy.is_initialized is False

        strategy.on_init(None, None, None)
        assert strategy.is_initialized is True

    def test_strategy_repr(self, strategy):
        """Test strategy __repr__ method."""
        repr_str = repr(strategy)
        assert 'MockStrategy' in repr_str
        assert '1.0.0' in repr_str

    def test_strategy_str(self, strategy):
        """Test strategy __str__ method."""
        str_repr = str(strategy)
        assert 'MockStrategy' in str_repr


# ============================================================================
# Test: generate_signal Integration
# ============================================================================

class TestGenerateSignal:
    """Tests for generate_signal method."""

    @pytest.fixture
    def strategy(self):
        """Create mock strategy instance."""
        return MockStrategy({'name': 'test'})

    def test_generate_signal_returns_buy(self, strategy, sample_ohlcv_data):
        """Test generate_signal returns BUY for uptrend."""
        # Ensure last candle closes higher than previous
        sample_ohlcv_data.loc[sample_ohlcv_data.index[-1], 'close'] = sample_ohlcv_data['close'].iloc[-2] + 100

        result = strategy.generate_signal('005930', sample_ohlcv_data)

        assert result is not None
        assert result.signal_type == SignalType.BUY
        assert result.confidence == 80.0

    def test_generate_signal_returns_none_for_downtrend(self, strategy, sample_downtrend_data):
        """Test generate_signal returns None for downtrend."""
        result = strategy.generate_signal('005930', sample_downtrend_data)

        # MockStrategy returns None for decreasing price
        assert result is None

    def test_generate_signal_with_insufficient_data(self, strategy):
        """Test generate_signal with insufficient data."""
        data = pd.DataFrame({
            'close': [50000]  # Only one data point
        })

        result = strategy.generate_signal('005930', data)
        assert result is None

    def test_generate_signal_with_none_data(self, strategy):
        """Test generate_signal with None data."""
        result = strategy.generate_signal('005930', None)
        assert result is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
