"""
Strategy Config Validation Tests
=================================

Tests for:
- All strategies load and pass validation
- risk_management ratio/pct/size values are within 0-1
- Invalid values are rejected
"""

import os
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.config import StrategyConfig, StrategyConfigError, StrategyLoader
from strategies.base import BaseStrategy


# ============================================================================
# Setup: ensure working directory is RoboTrader_template
# ============================================================================

@pytest.fixture(autouse=True)
def chdir_to_project():
    """Ensure CWD is RoboTrader_template for strategy discovery."""
    original = os.getcwd()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    yield
    os.chdir(original)


# ============================================================================
# Test: All strategies load and pass validation
# ============================================================================

class TestAllStrategiesLoadAndValidate:
    """All strategies must load and pass config validation."""

    def test_discover_all_strategies(self):
        """At least one strategy must be discoverable."""
        strategies = StrategyLoader.discover_strategies()
        assert len(strategies) > 0

    @pytest.mark.parametrize("strategy_name", [
        "sample", "momentum", "mean_reversion", "volume_breakout",
    ])
    def test_load_strategy_passes_validation(self, strategy_name):
        """Strategy loads successfully (includes validate + validate_config)."""
        strategy = StrategyLoader.load_strategy(strategy_name)
        assert isinstance(strategy, BaseStrategy)

    @pytest.mark.parametrize("strategy_name", [
        "sample", "momentum", "mean_reversion", "volume_breakout",
    ])
    def test_strategy_config_validate_standalone(self, strategy_name):
        """StrategyConfig.validate() passes for each strategy."""
        config = StrategyConfig(strategy_name)
        config.load()
        assert config.validate() is True


# ============================================================================
# Test: risk_management ratio value ranges
# ============================================================================

class TestRiskManagementRanges:
    """risk_management _pct/_ratio/_size keys must be in 0-1 range."""

    @pytest.mark.parametrize("strategy_name", [
        "sample", "momentum", "mean_reversion", "volume_breakout",
    ])
    def test_ratio_keys_within_range(self, strategy_name):
        """All _pct/_ratio/_size keys in risk_management are 0-1."""
        config = StrategyConfig(strategy_name)
        data = config.load()
        risk = data.get('risk_management', {})

        for key, value in risk.items():
            if not isinstance(value, (int, float)):
                continue
            if key.endswith(('_pct', '_ratio', '_size')):
                assert 0 <= value <= 1, (
                    f"{strategy_name}: risk_management.{key}={value} out of 0-1"
                )

    @pytest.mark.parametrize("strategy_name", [
        "sample", "momentum", "mean_reversion", "volume_breakout",
    ])
    def test_max_keys_non_negative(self, strategy_name):
        """All max_ integer keys in risk_management are non-negative."""
        config = StrategyConfig(strategy_name)
        data = config.load()
        risk = data.get('risk_management', {})

        for key, value in risk.items():
            if key.startswith('max_') and isinstance(value, int):
                assert value >= 0, (
                    f"{strategy_name}: risk_management.{key}={value} is negative"
                )


# ============================================================================
# Test: Invalid values are rejected
# ============================================================================

class TestInvalidConfigRejection:
    """Invalid config values must raise StrategyConfigError."""

    def _make_config(self, tmp_path, risk_management):
        """Helper to create a temp strategy config with given risk_management."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir(exist_ok=True)
        strat_dir = strategies_dir / "bad_test"
        strat_dir.mkdir(exist_ok=True)

        import yaml
        config_data = {
            'name': 'bad_test',
            'risk_management': risk_management,
        }
        (strat_dir / "config.yaml").write_text(
            yaml.dump(config_data, default_flow_style=False)
        )

        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = StrategyConfig("bad_test")
            config.load()
            return config
        finally:
            os.chdir(original)

    def test_reject_pct_above_one(self, tmp_path):
        """_pct value > 1 must be rejected."""
        config = self._make_config(tmp_path, {'stop_loss_pct': 5.0})
        with pytest.raises(StrategyConfigError, match="stop_loss_pct"):
            config.validate()

    def test_reject_ratio_negative(self, tmp_path):
        """_ratio value < 0 must be rejected."""
        config = self._make_config(tmp_path, {'take_profit_ratio': -0.1})
        with pytest.raises(StrategyConfigError, match="take_profit_ratio"):
            config.validate()

    def test_reject_size_above_one(self, tmp_path):
        """_size value > 1 must be rejected."""
        config = self._make_config(tmp_path, {'max_position_size': 1.5})
        with pytest.raises(StrategyConfigError, match="max_position_size"):
            config.validate()

    def test_reject_negative_max_integer(self, tmp_path):
        """max_ integer < 0 must be rejected."""
        config = self._make_config(tmp_path, {'max_daily_trades': -1})
        with pytest.raises(StrategyConfigError, match="max_daily_trades"):
            config.validate()

    def test_accept_valid_values(self, tmp_path):
        """Valid risk_management values must pass."""
        config = self._make_config(tmp_path, {
            'stop_loss_pct': 0.05,
            'take_profit_ratio': 0.10,
            'max_position_size': 0.20,
            'max_daily_trades': 5,
        })
        assert config.validate() is True

    def test_accept_boundary_zero(self, tmp_path):
        """Value of 0 for _pct/_ratio/_size must pass."""
        config = self._make_config(tmp_path, {'stop_loss_pct': 0.0})
        assert config.validate() is True

    def test_accept_boundary_one(self, tmp_path):
        """Value of 1 for _pct/_ratio/_size must pass."""
        config = self._make_config(tmp_path, {'take_profit_pct': 1.0})
        assert config.validate() is True

    def test_accept_max_zero(self, tmp_path):
        """max_ integer of 0 must pass."""
        config = self._make_config(tmp_path, {'max_positions': 0})
        assert config.validate() is True


# ============================================================================
# Test: validate_config on strategy instance
# ============================================================================

class TestStrategyValidateConfig:
    """BaseStrategy.validate_config() integration."""

    def test_base_validate_config_returns_true(self):
        """BaseStrategy.validate_config() defaults to True."""
        from strategies.sample.strategy import SampleStrategy
        s = SampleStrategy({'name': 'test'})
        assert s.validate_config() is True

    def test_load_strategy_calls_validate_config(self, tmp_path):
        """load_strategy rejects strategy whose validate_config returns False."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()
        strat_dir = strategies_dir / "failing_vc"
        strat_dir.mkdir()
        (strat_dir / "__init__.py").write_text("")

        config_content = "name: failing_vc\n"
        (strat_dir / "config.yaml").write_text(config_content)

        strategy_content = '''
import pandas as pd
from typing import Optional
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from strategies.base import BaseStrategy, Signal, OrderInfo

class FailingVCStrategy(BaseStrategy):
    name = "FailingVCStrategy"
    version = "1.0.0"

    def generate_signal(self, stock_code, data, timeframe='daily'):
        return None

    def validate_config(self):
        return False
'''
        (strat_dir / "strategy.py").write_text(strategy_content)

        original_dir = StrategyLoader.STRATEGIES_DIR
        original_cwd = os.getcwd()
        StrategyLoader.STRATEGIES_DIR = strategies_dir
        os.chdir(tmp_path)
        try:
            with pytest.raises(StrategyConfigError, match="validate_config"):
                StrategyLoader.load_strategy("failing_vc")
        finally:
            StrategyLoader.STRATEGIES_DIR = original_dir
            os.chdir(original_cwd)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
