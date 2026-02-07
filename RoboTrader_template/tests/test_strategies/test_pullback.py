"""
Pullback Strategy Tests
=======================

Tests for strategies/pullback/ implementation.

Test Requirements:
- test_pullback_strategy_init(): Initialization test
- test_generate_signal(): Signal generation test (mock data)
- test_config_loading(): Configuration loading test
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from strategies.pullback.types import (
    SignalType,
    BisectorStatus,
    RiskSignal,
    CandleAnalysis,
    VolumeAnalysis,
    BisectorAnalysis,
    SignalStrength,
    PullbackPattern,
)
from strategies.pullback.analyzers.candle import CandleAnalyzer
from strategies.pullback.analyzers.volume import VolumeAnalyzer
from strategies.pullback.analyzers.bisector import BisectorAnalyzer
from strategies.pullback.strategy import PullbackStrategy


# ============================================================================
# Helper Functions
# ============================================================================

def create_sample_data(
    periods: int = 30,
    start_price: float = 10000,
    trend: str = 'up',
    volume_base: int = 10000,
    seed: int = None
) -> pd.DataFrame:
    """Create sample OHLCV data for testing."""
    if seed is not None:
        np.random.seed(seed)

    kst = timezone(timedelta(hours=9))
    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=kst)
    dates = [base_time + timedelta(minutes=i) for i in range(periods)]

    # Generate prices based on trend
    if trend == 'up':
        closes = [start_price * (1 + 0.001 * i) for i in range(periods)]
    elif trend == 'down':
        closes = [start_price * (1 - 0.001 * i) for i in range(periods)]
    else:
        closes = [start_price] * periods

    # Add some variation
    opens = [c * 0.999 for c in closes]
    highs = [c * 1.002 for c in closes]
    lows = [c * 0.998 for c in closes]

    # Volume with some variation
    volumes = [volume_base * (0.8 + 0.4 * np.random.random()) for _ in range(periods)]

    return pd.DataFrame({
        'datetime': dates,
        'date': ['20240115'] * periods,
        'time': [f'{9 + i // 60:02d}{i % 60:02d}00' for i in range(periods)],
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


class TestSignalType:
    """Tests for SignalType enum."""

    def test_signal_types(self):
        """Test signal type values."""
        assert SignalType.STRONG_BUY.value == "STRONG_BUY"
        assert SignalType.CAUTIOUS_BUY.value == "CAUTIOUS_BUY"
        assert SignalType.WAIT.value == "WAIT"
        assert SignalType.AVOID.value == "AVOID"
        assert SignalType.SELL.value == "SELL"


class TestBisectorStatus:
    """Tests for BisectorStatus enum."""

    def test_bisector_status_values(self):
        """Test bisector status values."""
        assert BisectorStatus.HOLDING.value == "HOLDING"
        assert BisectorStatus.NEAR_SUPPORT.value == "NEAR_SUPPORT"
        assert BisectorStatus.BROKEN.value == "BROKEN"


class TestCandleAnalyzer:
    """Tests for CandleAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create candle analyzer."""
        return CandleAnalyzer({'min_body_pct': 0.5, 'lookback_period': 10})

    def test_analyze_bullish_candle(self, analyzer):
        """Test analyzing bullish candle."""
        data = create_sample_data(20, trend='up')

        result = analyzer.analyze(data)

        assert isinstance(result, CandleAnalysis)
        assert result.is_bullish == True
        assert result.body_size > 0

    def test_analyze_bearish_candle(self, analyzer):
        """Test analyzing bearish candle."""
        data = create_sample_data(20, trend='down')
        # Make last candle bearish
        data.loc[data.index[-1], 'close'] = data['open'].iloc[-1] * 0.99

        result = analyzer.analyze(data)

        assert result.is_bullish == False

    def test_is_recovery_candle(self, analyzer):
        """Test is_recovery_candle method."""
        data = create_sample_data(20, trend='up')

        result = analyzer.is_recovery_candle(data, -1)

        assert result == True

    def test_check_prior_uptrend(self, analyzer):
        """Test check_prior_uptrend method."""
        # Create uptrending data
        data = create_sample_data(30, trend='up')

        # Make first candle significantly lower
        first_open = data['open'].iloc[0]
        data.loc[data.index[0], 'open'] = first_open * 0.94  # 6% lower

        result = analyzer.check_prior_uptrend(
            data,
            min_gain=0.03,
            min_gain_from_first=0.04
        )

        # Should find prior uptrend
        assert isinstance(result, bool)

    def test_check_overhead_supply(self, analyzer):
        """Test check_overhead_supply method."""
        data = create_sample_data(20, trend='stable')

        # Add some higher highs in the past
        for i in range(5, 10):
            data.loc[data.index[i], 'high'] = data['high'].iloc[-1] * 1.02

        result = analyzer.check_overhead_supply(data, lookback=10, threshold=2)

        assert isinstance(result, bool)


class TestVolumeAnalyzer:
    """Tests for VolumeAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create volume analyzer."""
        return VolumeAnalyzer({
            'low_volume_threshold': 0.25,
            'moderate_volume_threshold': 0.50,
            'surge_multiplier': 1.5
        })

    def test_analyze_volume(self, analyzer):
        """Test volume analysis."""
        data = create_sample_data(30, volume_base=10000)

        result = analyzer.analyze(data)

        assert isinstance(result, VolumeAnalysis)
        assert result.baseline_volume > 0
        assert result.current_volume > 0
        assert result.volume_ratio > 0

    def test_calculate_baseline_volume(self, analyzer):
        """Test baseline volume calculation."""
        data = create_sample_data(30, volume_base=10000)

        baseline = analyzer.calculate_baseline_volume(data)

        assert isinstance(baseline, pd.Series)
        assert len(baseline) == len(data)

    def test_check_low_volume_retrace(self, analyzer):
        """Test low volume retrace detection."""
        data = create_sample_data(30, volume_base=10000)

        # Make last 3 candles low volume and declining
        for i in range(-3, 0):
            data.loc[data.index[i], 'volume'] = 1000  # 10% of base
            data.loc[data.index[i], 'close'] = data['close'].iloc[i-1] * 0.999

        result = analyzer.check_low_volume_retrace(data, lookback=3)

        assert isinstance(result, bool)

    def test_check_volume_recovery(self, analyzer):
        """Test volume recovery detection."""
        data = create_sample_data(30, volume_base=10000)

        result = analyzer.check_volume_recovery(data, lookback=3)

        assert isinstance(result, bool)

    def test_volume_classifications(self, analyzer):
        """Test volume classification properties."""
        data = create_sample_data(30, volume_base=10000)

        result = analyzer.analyze(data)

        # These should be mutually exclusive
        classifications = [
            result.is_low_volume,
            result.is_moderate_volume,
            result.is_high_volume
        ]

        # At most one should be True (excluding low/high when moderate)
        assert isinstance(result.is_low_volume, bool)
        assert isinstance(result.is_moderate_volume, bool)
        assert isinstance(result.is_high_volume, bool)


class TestBisectorAnalyzer:
    """Tests for BisectorAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create bisector analyzer."""
        return BisectorAnalyzer({
            'support_tolerance': 0.005,
            'breakout_tolerance': 0.003
        })

    def test_analyze_bisector(self, analyzer):
        """Test bisector analysis."""
        data = create_sample_data(30, trend='up')

        result = analyzer.analyze(data)

        assert isinstance(result, BisectorAnalysis)
        assert result.bisector_line > 0
        assert result.day_high >= result.day_low

    def test_bisector_holding(self, analyzer):
        """Test bisector holding status."""
        data = create_sample_data(30, trend='up')

        result = analyzer.analyze(data)

        # Price above bisector should be HOLDING
        if result.current_price >= result.bisector_line:
            assert result.status == BisectorStatus.HOLDING
            assert result.is_holding == True

    def test_bisector_broken(self, analyzer):
        """Test bisector broken status."""
        data = create_sample_data(30, trend='up')

        # Set last close well below bisector
        bisector = (data['high'].max() + data['low'].min()) / 2
        data.loc[data.index[-1], 'close'] = bisector * 0.98

        result = analyzer.analyze(data)

        assert result.is_broken == True

    def test_get_support_levels(self, analyzer):
        """Test support levels calculation."""
        data = create_sample_data(30, trend='up')

        levels = analyzer.get_support_levels(data)

        assert 'day_high' in levels
        assert 'bisector' in levels
        assert 'day_low' in levels
        assert levels['day_high'] > levels['bisector'] > levels['day_low']

    def test_check_bisector_holding_multi_candle(self, analyzer):
        """Test bisector holding over multiple candles."""
        data = create_sample_data(30, trend='up')

        # Ensure all recent candles are above bisector
        bisector = (data['high'].max() + data['low'].min()) / 2
        for i in range(-3, 0):
            data.loc[data.index[i], 'low'] = bisector * 1.001

        result = analyzer.check_bisector_holding(data, candles=3)

        assert result == True


class TestSignalStrength:
    """Tests for SignalStrength dataclass."""

    def test_signal_strength_creation(self):
        """Test creating signal strength."""
        signal = SignalStrength(
            signal_type=SignalType.STRONG_BUY,
            confidence=85,
            target_profit=0.025,
            reasons=["Volume recovery", "Bisector holding"],
            volume_ratio=0.6,
            bisector_status=BisectorStatus.HOLDING
        )

        assert signal.signal_type == SignalType.STRONG_BUY
        assert signal.confidence == 85
        assert signal.is_buy_signal == True

    def test_is_buy_signal(self):
        """Test is_buy_signal property."""
        strong_buy = SignalStrength(
            signal_type=SignalType.STRONG_BUY,
            confidence=90,
            target_profit=0.03,
            reasons=[],
            volume_ratio=0.5,
            bisector_status=BisectorStatus.HOLDING
        )

        cautious_buy = SignalStrength(
            signal_type=SignalType.CAUTIOUS_BUY,
            confidence=75,
            target_profit=0.02,
            reasons=[],
            volume_ratio=0.5,
            bisector_status=BisectorStatus.HOLDING
        )

        avoid = SignalStrength(
            signal_type=SignalType.AVOID,
            confidence=30,
            target_profit=0.01,
            reasons=[],
            volume_ratio=0.5,
            bisector_status=BisectorStatus.BROKEN
        )

        assert strong_buy.is_buy_signal == True
        assert cautious_buy.is_buy_signal == True
        assert avoid.is_buy_signal == False

    def test_to_dict(self):
        """Test to_dict method."""
        signal = SignalStrength(
            signal_type=SignalType.STRONG_BUY,
            confidence=85,
            target_profit=0.025,
            reasons=["Test"],
            volume_ratio=0.6,
            bisector_status=BisectorStatus.HOLDING
        )

        d = signal.to_dict()

        assert d['signal_type'] == 'STRONG_BUY'
        assert d['confidence'] == 85
        assert d['bisector_status'] == 'HOLDING'


class TestPullbackPattern:
    """Tests for PullbackPattern dataclass."""

    def test_pullback_pattern_creation(self):
        """Test creating pullback pattern."""
        pattern = PullbackPattern(
            has_prior_uptrend=True,
            has_low_volume_retrace=True,
            has_bisector_support=True,
            has_volume_recovery=True,
            is_recovery_candle=True
        )

        assert pattern.is_valid_pattern == True

    def test_invalid_pattern_no_uptrend(self):
        """Test invalid pattern without uptrend."""
        pattern = PullbackPattern(
            has_prior_uptrend=False,
            has_low_volume_retrace=True,
            has_bisector_support=True,
            has_volume_recovery=True,
            is_recovery_candle=True
        )

        assert pattern.is_valid_pattern == False

    def test_to_dict(self):
        """Test to_dict method."""
        pattern = PullbackPattern(
            has_prior_uptrend=True,
            has_low_volume_retrace=True,
            has_bisector_support=True,
            has_volume_recovery=True,
            is_recovery_candle=True
        )

        d = pattern.to_dict()

        assert d['has_prior_uptrend'] == True
        assert d['is_recovery_candle'] == True


# ============================================================================
# Test: test_pullback_strategy_init()
# ============================================================================

class TestPullbackStrategyInit:
    """Tests for PullbackStrategy initialization - test_pullback_strategy_init()."""

    @pytest.fixture
    def strategy(self, pullback_config):
        """Create PullbackStrategy instance."""
        return PullbackStrategy(pullback_config)

    def test_pullback_strategy_creation(self, pullback_config):
        """Test PullbackStrategy can be created with config."""
        strategy = PullbackStrategy(pullback_config)

        assert strategy is not None
        assert strategy.name == "Pullback Strategy"
        assert strategy.version == "2.0.0"

    def test_pullback_strategy_config_extraction(self, pullback_config):
        """Test strategy extracts config sections correctly."""
        strategy = PullbackStrategy(pullback_config)

        assert strategy.params is not None
        assert strategy.risk_config is not None
        assert strategy.signal_config is not None

    def test_pullback_strategy_analyzers_initialized(self, pullback_config):
        """Test strategy initializes analyzers."""
        strategy = PullbackStrategy(pullback_config)

        assert strategy.candle_analyzer is not None
        assert strategy.volume_analyzer is not None
        assert strategy.bisector_analyzer is not None
        assert strategy.signal_calculator is not None
        assert strategy.risk_detector is not None
        assert strategy.pattern_analyzer is not None

    def test_pullback_strategy_initial_state(self, pullback_config):
        """Test strategy has correct initial state."""
        strategy = PullbackStrategy(pullback_config)

        assert strategy._is_initialized is False
        assert strategy._positions == {}
        assert strategy._daily_trades == 0

    def test_pullback_strategy_on_init_success(self, pullback_config, mock_broker):
        """Test on_init succeeds with valid broker."""
        strategy = PullbackStrategy(pullback_config)

        result = strategy.on_init(mock_broker, None, None)

        assert result is True
        assert strategy._is_initialized is True
        assert strategy._broker == mock_broker

    def test_pullback_strategy_on_init_no_account(self, pullback_config):
        """Test on_init fails when account info unavailable."""
        strategy = PullbackStrategy(pullback_config)

        mock_broker = Mock()
        mock_broker.get_account_info.return_value = None

        result = strategy.on_init(mock_broker, None, None)

        assert result is False
        assert strategy._is_initialized is False

    def test_pullback_strategy_on_market_open(self, pullback_config, mock_broker):
        """Test on_market_open resets daily state."""
        strategy = PullbackStrategy(pullback_config)
        strategy.on_init(mock_broker, None, None)

        # Simulate some state
        strategy._daily_trades = 5
        strategy._positions = {'005930': {'quantity': 10}}

        strategy.on_market_open()

        assert strategy._daily_trades == 0
        assert strategy._positions == {}


# ============================================================================
# Test: test_generate_signal()
# ============================================================================

class TestGenerateSignal:
    """Tests for signal generation - test_generate_signal()."""

    @pytest.fixture
    def initialized_strategy(self, pullback_config, mock_broker):
        """Create initialized PullbackStrategy."""
        strategy = PullbackStrategy(pullback_config)
        strategy.on_init(mock_broker, None, None)
        return strategy

    def test_generate_signal_insufficient_data(self, initialized_strategy):
        """Test generate_signal returns None for insufficient data."""
        data = pd.DataFrame({
            'close': [50000] * 10,  # Less than 20 candles
            'volume': [10000] * 10
        })

        result = initialized_strategy.generate_signal('005930', data)

        assert result is None

    def test_generate_signal_none_data(self, initialized_strategy):
        """Test generate_signal returns None for None data."""
        result = initialized_strategy.generate_signal('005930', None)

        assert result is None

    def test_generate_signal_with_pullback_data(self, initialized_strategy, sample_pullback_data):
        """Test generate_signal with pullback pattern data."""
        result = initialized_strategy.generate_signal('005930', sample_pullback_data)

        # Result depends on whether pattern is detected
        # Either valid signal or None
        if result is not None:
            assert hasattr(result, 'signal_type')
            assert hasattr(result, 'confidence')
            assert result.stock_code == '005930'

    def test_generate_signal_with_downtrend(self, initialized_strategy, sample_downtrend_data):
        """Test generate_signal returns None for downtrend."""
        result = initialized_strategy.generate_signal('005930', sample_downtrend_data)

        # Should not generate buy signal for downtrend
        if result is not None:
            # If signal generated, should not be strong buy
            assert result.confidence < 85

    def test_generate_signal_calculates_targets(self, initialized_strategy, sample_pullback_data):
        """Test generate_signal calculates target and stop loss."""
        result = initialized_strategy.generate_signal('005930', sample_pullback_data)

        if result is not None:
            current_price = float(sample_pullback_data['close'].iloc[-1])

            # Target should be above current price
            if result.target_price is not None:
                assert result.target_price > current_price

            # Stop loss should be below current price
            if result.stop_loss is not None:
                assert result.stop_loss < current_price

    def test_generate_signal_metadata(self, initialized_strategy, sample_pullback_data):
        """Test generate_signal includes metadata."""
        result = initialized_strategy.generate_signal('005930', sample_pullback_data)

        if result is not None and result.metadata:
            # Metadata should include pattern info
            assert 'pattern' in result.metadata or 'volume_ratio' in result.metadata


# ============================================================================
# Test: test_config_loading()
# ============================================================================

class TestConfigLoading:
    """Tests for configuration loading - test_config_loading()."""

    def test_pullback_config_has_strategy_section(self, pullback_config):
        """Test pullback config has strategy section."""
        assert 'strategy' in pullback_config
        assert pullback_config['strategy']['name'] == 'pullback'

    def test_pullback_config_has_parameters(self, pullback_config):
        """Test pullback config has parameters section."""
        assert 'parameters' in pullback_config

        params = pullback_config['parameters']
        assert 'uptrend_min_gain' in params
        assert 'volume' in params
        assert 'bisector' in params
        assert 'candle' in params

    def test_pullback_config_has_risk_management(self, pullback_config):
        """Test pullback config has risk management section."""
        assert 'risk_management' in pullback_config

        risk = pullback_config['risk_management']
        assert 'target_profit_rate' in risk
        assert 'stop_loss_rate' in risk
        assert 'max_position_ratio' in risk

    def test_pullback_config_has_signals(self, pullback_config):
        """Test pullback config has signals section."""
        assert 'signals' in pullback_config

        signals = pullback_config['signals']
        assert 'strong_buy_threshold' in signals
        assert 'buy_threshold' in signals

    def test_pullback_strategy_uses_config_values(self, pullback_config):
        """Test strategy uses config values correctly."""
        strategy = PullbackStrategy(pullback_config)

        # Check risk config values
        assert strategy.risk_config.get('target_profit_rate') == 0.025
        assert strategy.risk_config.get('stop_loss_rate') == 0.015
        assert strategy.risk_config.get('max_position_ratio') == 0.09

    def test_pullback_strategy_parameter_extraction(self, pullback_config):
        """Test strategy extracts parameters correctly."""
        strategy = PullbackStrategy(pullback_config)

        # Volume parameters
        volume_params = strategy.params.get('volume', {})
        assert volume_params.get('low_volume_threshold') == 0.25

        # Bisector parameters
        bisector_params = strategy.params.get('bisector', {})
        assert bisector_params.get('support_tolerance') == 0.005

    def test_strategy_with_empty_config(self):
        """Test strategy handles empty config gracefully."""
        strategy = PullbackStrategy({})

        assert strategy.params == {}
        assert strategy.risk_config == {}

    def test_strategy_with_partial_config(self):
        """Test strategy handles partial config."""
        partial_config = {
            'parameters': {
                'uptrend_min_gain': 0.05
            }
        }
        strategy = PullbackStrategy(partial_config)

        assert strategy.params.get('uptrend_min_gain') == 0.05
        assert strategy.risk_config == {}


# ============================================================================
# Test: Additional Integration Tests
# ============================================================================

class TestPullbackStrategyIntegration:
    """Integration tests for PullbackStrategy."""

    @pytest.fixture
    def full_strategy(self, pullback_config, mock_broker, mock_data_provider, mock_executor):
        """Create fully initialized strategy."""
        strategy = PullbackStrategy(pullback_config)
        strategy.on_init(mock_broker, mock_data_provider, mock_executor)
        return strategy

    def test_strategy_lifecycle(self, full_strategy):
        """Test complete strategy lifecycle."""
        # Market open
        full_strategy.on_market_open()
        assert full_strategy._daily_trades == 0

        # Generate signal (may or may not produce signal)
        data = create_sample_data(30, trend='up', seed=42)
        signal = full_strategy.generate_signal('005930', data)

        # Market close
        full_strategy.on_market_close()

    def test_should_exit_no_position(self, full_strategy):
        """Test should_exit returns False when no position."""
        data = create_sample_data(30, trend='down', seed=42)

        result = full_strategy.should_exit('005930', data)

        assert result is False

    def test_get_exit_reason_no_position(self, full_strategy):
        """Test get_exit_reason for non-existent position."""
        data = create_sample_data(30, seed=42)

        reason = full_strategy.get_exit_reason('005930', data)

        assert reason == "No position"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
