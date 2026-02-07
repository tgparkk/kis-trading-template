"""
Pytest Configuration and Fixtures
=================================

Common fixtures for testing the trading template system.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, AsyncMock
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


# ============================================================================
# Timezone Fixture
# ============================================================================

@pytest.fixture
def kst():
    """Korean Standard Time timezone."""
    return timezone(timedelta(hours=9))


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_ohlcv_data():
    """
    Create sample OHLCV data for testing.

    Returns 30 minutes of sample data with an uptrend pattern.
    """
    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    periods = 30

    # Generate uptrending price data
    np.random.seed(42)  # For reproducibility
    base_price = 50000

    # Create prices with uptrend and some noise
    closes = []
    for i in range(periods):
        trend = base_price * (1 + 0.001 * i)  # 0.1% per candle uptrend
        noise = np.random.uniform(-0.001, 0.001) * base_price
        closes.append(trend + noise)

    # Generate OHLCV data
    opens = [c * np.random.uniform(0.998, 1.001) for c in closes]
    highs = [max(o, c) * np.random.uniform(1.001, 1.003) for o, c in zip(opens, closes)]
    lows = [min(o, c) * np.random.uniform(0.997, 0.999) for o, c in zip(opens, closes)]

    # Volume with variation (higher at start, lower in middle, recovery at end)
    volumes = []
    for i in range(periods):
        if i < 10:
            vol = np.random.randint(80000, 120000)  # High volume start
        elif i < 20:
            vol = np.random.randint(20000, 40000)  # Low volume pullback
        else:
            vol = np.random.randint(50000, 80000)  # Volume recovery
        volumes.append(vol)

    return pd.DataFrame({
        'datetime': [base_time + timedelta(minutes=i) for i in range(periods)],
        'date': ['20240115'] * periods,
        'time': [f'{9 + i // 60:02d}{i % 60:02d}00' for i in range(periods)],
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


@pytest.fixture
def sample_pullback_data():
    """
    Create sample data with pullback pattern.

    Pattern:
    1. Initial uptrend (candles 0-14)
    2. Low volume pullback (candles 15-24)
    3. Volume recovery (candles 25-29)
    """
    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    periods = 30
    np.random.seed(42)

    base_price = 50000
    closes = []
    volumes = []

    for i in range(periods):
        if i < 15:
            # Phase 1: Strong uptrend with high volume
            price = base_price * (1 + 0.003 * i)  # 0.3% per candle
            vol = np.random.randint(80000, 120000)
        elif i < 25:
            # Phase 2: Pullback with low volume
            max_price = base_price * (1 + 0.003 * 14)
            price = max_price * (1 - 0.001 * (i - 14))  # Small decline
            vol = np.random.randint(15000, 30000)
        else:
            # Phase 3: Recovery with volume
            recovery_base = base_price * (1 + 0.003 * 14) * (1 - 0.001 * 10)
            price = recovery_base * (1 + 0.002 * (i - 24))
            vol = np.random.randint(60000, 90000)

        closes.append(price)
        volumes.append(vol)

    opens = [c * np.random.uniform(0.998, 1.001) for c in closes]
    highs = [max(o, c) * np.random.uniform(1.001, 1.005) for o, c in zip(opens, closes)]
    lows = [min(o, c) * np.random.uniform(0.995, 0.999) for o, c in zip(opens, closes)]

    return pd.DataFrame({
        'datetime': [base_time + timedelta(minutes=i) for i in range(periods)],
        'date': ['20240115'] * periods,
        'time': [f'{9 + i // 60:02d}{i % 60:02d}00' for i in range(periods)],
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


@pytest.fixture
def sample_downtrend_data():
    """Create sample data with downtrend."""
    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    periods = 30
    np.random.seed(42)

    base_price = 50000
    closes = [base_price * (1 - 0.002 * i) for i in range(periods)]
    opens = [c * 1.002 for c in closes]
    highs = [o * 1.001 for o in opens]
    lows = [c * 0.999 for c in closes]
    volumes = [np.random.randint(50000, 80000) for _ in range(periods)]

    return pd.DataFrame({
        'datetime': [base_time + timedelta(minutes=i) for i in range(periods)],
        'date': ['20240115'] * periods,
        'time': [f'{9 + i // 60:02d}{i % 60:02d}00' for i in range(periods)],
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


# ============================================================================
# Mock Broker Fixture
# ============================================================================

@dataclass
class MockAccountInfo:
    """Mock account information."""
    account_no: str = "12345678-01"
    total_balance: float = 10000000
    available_cash: float = 8000000
    invested_amount: float = 2000000
    positions: List = None

    def __post_init__(self):
        if self.positions is None:
            self.positions = []


@dataclass
class MockPosition:
    """Mock position information."""
    stock_code: str
    stock_name: str
    quantity: int
    avg_price: float
    current_price: float = 0.0
    profit_loss: float = 0.0
    profit_loss_rate: float = 0.0


@pytest.fixture
def mock_broker():
    """
    Create mock broker for testing.

    Returns a Mock object with commonly used broker methods.
    """
    broker = Mock()

    # Mock account info
    account = MockAccountInfo()
    broker.get_account_info.return_value = account
    broker.get_account_balance.return_value = {
        'total_balance': account.total_balance,
        'available_cash': account.available_cash,
        'invested_amount': account.invested_amount,
        'total_profit_loss': 0,
        'total_profit_loss_rate': 0
    }

    # Mock holdings
    broker.get_holdings.return_value = []

    # Mock available cash
    broker.get_available_cash.return_value = account.available_cash

    # Mock current price
    broker.get_current_price.return_value = 50000

    # Mock connection status
    broker.is_connected = True

    return broker


@pytest.fixture
def mock_broker_with_position():
    """Create mock broker with existing position."""
    broker = Mock()

    position = MockPosition(
        stock_code="005930",
        stock_name="Samsung Electronics",
        quantity=10,
        avg_price=70000,
        current_price=72000,
        profit_loss=20000,
        profit_loss_rate=0.0286
    )

    account = MockAccountInfo(
        total_balance=10000000,
        available_cash=7300000,
        invested_amount=700000,
        positions=[position]
    )

    broker.get_account_info.return_value = account
    broker.get_holdings.return_value = [
        {
            'stock_code': position.stock_code,
            'stock_name': position.stock_name,
            'quantity': position.quantity,
            'avg_price': position.avg_price,
            'current_price': position.current_price,
            'profit_loss': position.profit_loss,
            'profit_loss_rate': position.profit_loss_rate
        }
    ]
    broker.is_connected = True

    return broker


# ============================================================================
# Mock Data Provider Fixture
# ============================================================================

@pytest.fixture
def mock_data_provider(sample_ohlcv_data):
    """Create mock data provider for testing."""
    provider = Mock()

    # Sync methods
    provider.get_minute_data.return_value = sample_ohlcv_data
    provider.get_daily_data.return_value = sample_ohlcv_data
    provider.get_current_price.return_value = 50500

    # Async methods
    async_provider = AsyncMock()
    async_provider.get_minute_data.return_value = sample_ohlcv_data
    async_provider.get_daily_data.return_value = sample_ohlcv_data
    async_provider.get_current_price.return_value = 50500

    provider.async_provider = async_provider

    return provider


# ============================================================================
# Mock Executor Fixture
# ============================================================================

@pytest.fixture
def mock_executor():
    """Create mock order executor for testing."""
    executor = Mock()

    # Mock buy order
    executor.buy.return_value = Mock(
        order_id="ORD202401150001",
        stock_code="005930",
        side="buy",
        order_type="limit",
        quantity=10,
        price=50000,
        status="pending"
    )

    # Mock sell order
    executor.sell.return_value = Mock(
        order_id="ORD202401150002",
        stock_code="005930",
        side="sell",
        order_type="limit",
        quantity=10,
        price=51500,
        status="pending"
    )

    # Mock cancel
    executor.cancel.return_value = True

    # Mock pending orders
    executor.get_pending_orders.return_value = []

    return executor


# ============================================================================
# Pullback Strategy Config Fixture
# ============================================================================

@pytest.fixture
def pullback_config():
    """
    Create pullback strategy configuration for testing.

    Returns configuration dictionary matching config.yaml structure.
    """
    return {
        'strategy': {
            'name': 'pullback',
            'timeframe': '3min'
        },
        'parameters': {
            'uptrend_min_gain': 0.03,
            'decline_min_pct': 0.005,
            'support_volume_threshold': 0.25,
            'support_volatility_threshold': 0.015,
            'prior_uptrend': {
                'min_gain_from_first': 0.04,
                'min_gain': 0.03,
                'lookback_period': 20,
                'max_high_volume_declines': 1
            },
            'volume': {
                'low_volume_threshold': 0.25,
                'moderate_volume_threshold': 0.50,
                'recovery_threshold': 0.50,
                'min_low_volume_candles': 2,
                'surge_multiplier': 1.5
            },
            'bisector': {
                'support_tolerance': 0.005,
                'breakout_tolerance': 0.003
            },
            'candle': {
                'min_body_pct': 0.5,
                'lookback_period': 10
            },
            'signal': {
                'recovery_candle_score': 20,
                'volume_recovery_score': 25,
                'low_volume_retrace_score': 15,
                'bisector_holding_score': 20,
                'bisector_near_score': 10,
                'bisector_breakout_score': 15,
                'volume_surge_score': 10,
                'overhead_supply_penalty': 15,
                'bisector_broken_penalty': 35
            }
        },
        'signals': {
            'strong_buy_threshold': 85,
            'buy_threshold': 70,
            'wait_threshold': 40
        },
        'risk_management': {
            'target_profit_rate': 0.025,
            'stop_loss_rate': 0.015,
            'max_position_ratio': 0.09,
            'max_total_investment': 0.90,
            'trailing_stop': False,
            'trailing_stop_trigger': 0.02,
            'trailing_stop_distance': 0.01
        },
        'trading_hours': {
            'entry_start': '090500',
            'entry_end': '150000',
            'exit_deadline': '152000'
        },
        'filters': {
            'min_price': 1000,
            'max_price': 500000,
            'min_daily_volume': 100000,
            'max_gap_up': 0.10,
            'max_gap_down': 0.05
        }
    }


# ============================================================================
# Strategy Test Fixtures
# ============================================================================

@pytest.fixture
def minimal_strategy_config():
    """Create minimal strategy configuration."""
    return {
        'name': 'test_strategy',
        'description': 'Test strategy for unit tests',
        'enabled': True
    }


@pytest.fixture
def temp_strategy_dir(tmp_path):
    """Create temporary strategy directory structure."""
    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()

    test_strategy_dir = strategies_dir / "test_strategy"
    test_strategy_dir.mkdir()

    # Create config.yaml
    config_content = """
strategy:
  name: test_strategy
  timeframe: 1min

parameters:
  threshold: 0.02

risk_management:
  take_profit_ratio: 0.03
  stop_loss_ratio: 0.02
"""
    (test_strategy_dir / "config.yaml").write_text(config_content)

    # Create strategy.py
    strategy_content = '''
from strategies.base import BaseStrategy, Signal, SignalType, OrderInfo
import pandas as pd
from typing import Optional

class TestStrategy(BaseStrategy):
    name = "TestStrategy"
    version = "1.0.0"

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor
        self._is_initialized = True
        return True

    def on_market_open(self) -> None:
        pass

    def generate_signal(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        return None

    def on_order_filled(self, order: OrderInfo) -> None:
        pass

    def on_market_close(self) -> None:
        pass
'''
    (test_strategy_dir / "strategy.py").write_text(strategy_content)
    (test_strategy_dir / "__init__.py").write_text("")

    return strategies_dir


# ============================================================================
# Helper Functions for Tests
# ============================================================================

def create_ohlcv_data(
    periods: int = 30,
    start_price: float = 50000,
    trend: str = 'up',
    volume_base: int = 50000,
    seed: int = None
) -> pd.DataFrame:
    """
    Helper function to create OHLCV data with specified characteristics.

    Args:
        periods: Number of candles
        start_price: Starting price
        trend: 'up', 'down', or 'flat'
        volume_base: Base volume level
        seed: Random seed for reproducibility

    Returns:
        pd.DataFrame with OHLCV data
    """
    if seed is not None:
        np.random.seed(seed)

    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))

    if trend == 'up':
        closes = [start_price * (1 + 0.001 * i) for i in range(periods)]
    elif trend == 'down':
        closes = [start_price * (1 - 0.001 * i) for i in range(periods)]
    else:
        closes = [start_price * (1 + np.random.uniform(-0.001, 0.001)) for _ in range(periods)]

    opens = [c * np.random.uniform(0.998, 1.002) for c in closes]
    highs = [max(o, c) * np.random.uniform(1.001, 1.003) for o, c in zip(opens, closes)]
    lows = [min(o, c) * np.random.uniform(0.997, 0.999) for o, c in zip(opens, closes)]
    volumes = [int(volume_base * np.random.uniform(0.7, 1.3)) for _ in range(periods)]

    return pd.DataFrame({
        'datetime': [base_time + timedelta(minutes=i) for i in range(periods)],
        'date': ['20240115'] * periods,
        'time': [f'{9 + i // 60:02d}{i % 60:02d}00' for i in range(periods)],
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


# Make helper function available as fixture
@pytest.fixture
def ohlcv_factory():
    """Factory fixture for creating custom OHLCV data."""
    return create_ohlcv_data


# ============================================================================
# RoboTrader Core Fixtures
# ============================================================================

@pytest.fixture
def mock_api_manager():
    """KISAPIManager Mock (조회 전용)"""
    api = Mock()
    api.is_initialized = True

    # 현재가 조회
    price_info = Mock()
    price_info.current_price = 70000
    price_info.change_amount = 500
    price_info.change_rate = 0.72
    price_info.volume = 10000000
    price_info.stock_code = "005930"
    api.get_current_price.return_value = price_info

    # 계좌 잔고
    balance_info = Mock()
    balance_info.account_balance = 10000000
    balance_info.available_amount = 8000000
    api.get_account_balance.return_value = balance_info

    # 주문 API (OrderResult)
    order_result = Mock()
    order_result.success = True
    order_result.order_id = "ORD-TEST-001"
    order_result.message = ""
    api.place_buy_order.return_value = order_result
    api.place_sell_order.return_value = order_result
    api.cancel_order.return_value = order_result

    return api


@pytest.fixture
def mock_db_manager():
    """DatabaseManager Mock"""
    db = Mock()
    db.save_virtual_buy.return_value = 1
    db.save_virtual_sell.return_value = True
    db.get_virtual_open_positions.return_value = pd.DataFrame()
    db.get_last_open_virtual_buy.return_value = None
    return db


@pytest.fixture
def mock_telegram():
    """Telegram AsyncMock"""
    tg = AsyncMock()
    tg.notify_order_placed = AsyncMock()
    tg.notify_order_filled = AsyncMock()
    tg.notify_order_cancelled = AsyncMock()
    tg.notify_system_status = AsyncMock()
    return tg


@pytest.fixture
def sample_order():
    """Order(BUY, 005930, 70000원, 10주)"""
    from core.models import Order, OrderType, OrderStatus
    return Order(
        order_id="TEST001",
        stock_code="005930",
        order_type=OrderType.BUY,
        price=70000,
        quantity=10,
        timestamp=datetime.now()
    )


@pytest.fixture
def sample_trading_stock():
    """TradingStock(005930, target=17%, stop=9%)"""
    from core.models import TradingStock, StockState
    stock = TradingStock(
        stock_code="005930",
        stock_name="삼성전자",
        state=StockState.SELECTED,
        selected_time=datetime.now()
    )
    stock.target_profit_rate = 0.17
    stock.stop_loss_rate = 0.09
    return stock


@pytest.fixture
def trading_config():
    """TradingConfig 기본 설정"""
    from core.models import TradingConfig
    return TradingConfig.from_json({
        'paper_trading': True,
        'order_management': {
            'buy_timeout_seconds': 180,
            'sell_timeout_seconds': 180,
        }
    })
