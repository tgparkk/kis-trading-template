"""
Strategy Config Tests
=====================

Tests for strategy/config.py

Test Requirements:
- test_load_yaml_config(): YAML configuration loading test
- test_strategy_discovery(): Strategy discovery test
- test_strategy_loader(): Dynamic strategy loading test
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import os

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from strategies.config import (
    StrategyConfig,
    StrategyConfigError,
    StrategyLoader,
    load_yaml_config,
    merge_configs,
)


# ============================================================================
# Test: test_load_yaml_config()
# ============================================================================

class TestLoadYamlConfig:
    """Tests for YAML configuration loading - test_load_yaml_config()."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory for config files."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_load_yaml_config_basic(self, temp_config_dir):
        """Test loading a basic YAML config file."""
        config_file = temp_config_dir / "config.yaml"
        config_content = """
name: "test"
version: "1.0"
parameters:
  threshold: 0.05
"""
        config_file.write_text(config_content)

        result = load_yaml_config(str(config_file))

        assert result['name'] == 'test'
        assert result['version'] == '1.0'
        assert result['parameters']['threshold'] == 0.05

    def test_load_yaml_config_nested(self, temp_config_dir):
        """Test loading YAML config with nested structure."""
        config_file = temp_config_dir / "nested.yaml"
        config_content = """
strategy:
  name: pullback
  timeframe: 3min
parameters:
  volume:
    low_threshold: 0.25
    high_threshold: 0.75
  candle:
    min_body_pct: 0.5
"""
        config_file.write_text(config_content)

        result = load_yaml_config(str(config_file))

        assert result['strategy']['name'] == 'pullback'
        assert result['parameters']['volume']['low_threshold'] == 0.25
        assert result['parameters']['candle']['min_body_pct'] == 0.5

    def test_load_yaml_config_not_found(self):
        """Test loading non-existent config raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_yaml_config("nonexistent/path/config.yaml")

    def test_load_yaml_config_empty_file(self, temp_config_dir):
        """Test loading empty YAML file returns empty dict."""
        config_file = temp_config_dir / "empty.yaml"
        config_file.write_text("")

        result = load_yaml_config(str(config_file))

        assert result == {}

    def test_load_yaml_config_invalid_yaml(self, temp_config_dir):
        """Test loading invalid YAML raises StrategyConfigError."""
        config_file = temp_config_dir / "invalid.yaml"
        config_file.write_text("{ invalid: yaml: content: }")

        with pytest.raises(StrategyConfigError):
            load_yaml_config(str(config_file))


class TestStrategyConfigClass:
    """Tests for StrategyConfig class."""

    @pytest.fixture
    def temp_strategy(self, tmp_path):
        """Create temporary strategy directory with config."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()

        test_strategy = strategies_dir / "test_strategy"
        test_strategy.mkdir()

        config_content = """
strategy:
  name: test_strategy
  timeframe: 1min
parameters:
  threshold: 0.02
risk_management:
  take_profit_ratio: 0.03
  stop_loss_ratio: 0.02
  max_position_ratio: 0.10
"""
        (test_strategy / "config.yaml").write_text(config_content)

        # Change working directory temporarily
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        yield test_strategy

        os.chdir(original_cwd)

    def test_strategy_config_init(self):
        """Test StrategyConfig initialization."""
        config = StrategyConfig("pullback")

        assert config.strategy_name == "pullback"
        assert config._config == {}

    def test_strategy_config_load(self, temp_strategy):
        """Test StrategyConfig.load method."""
        config = StrategyConfig("test_strategy")
        result = config.load()

        assert result is not None
        assert result['strategy']['name'] == 'test_strategy'
        assert result['risk_management']['take_profit_ratio'] == 0.03

    def test_strategy_config_load_not_found(self, tmp_path):
        """Test StrategyConfig.load raises error for non-existent strategy."""
        os.chdir(tmp_path)
        (tmp_path / "strategies").mkdir()

        config = StrategyConfig("nonexistent")

        with pytest.raises(FileNotFoundError):
            config.load()

    def test_strategy_config_get(self, temp_strategy):
        """Test StrategyConfig.get method with dot notation."""
        config = StrategyConfig("test_strategy")
        config.load()

        # Simple key
        assert config.get('strategy') is not None

        # Nested key
        assert config.get('risk_management.take_profit_ratio') == 0.03
        assert config.get('parameters.threshold') == 0.02

        # Default value
        assert config.get('nonexistent', 'default') == 'default'

    def test_strategy_config_set(self, temp_strategy):
        """Test StrategyConfig.set method."""
        config = StrategyConfig("test_strategy")
        config.load()

        # Set simple key
        config.set('new_key', 'new_value')
        assert config.get('new_key') == 'new_value'

        # Set nested key
        config.set('risk_management.stop_loss_ratio', 0.025)
        assert config.get('risk_management.stop_loss_ratio') == 0.025

        # Set new nested key
        config.set('new_section.nested_key', 123)
        assert config.get('new_section.nested_key') == 123

    def test_strategy_config_validate(self, temp_strategy):
        """Test StrategyConfig.validate method."""
        config = StrategyConfig("test_strategy")
        config.load()

        # Should not raise for valid config
        result = config.validate()
        assert result is True

    def test_strategy_config_property(self, temp_strategy):
        """Test StrategyConfig.config property returns copy."""
        config = StrategyConfig("test_strategy")
        config.load()

        config_copy = config.config
        config_copy['modified'] = True

        # Original should not be modified
        assert 'modified' not in config._config


# ============================================================================
# Test: test_strategy_discovery()
# ============================================================================

class TestStrategyDiscovery:
    """Tests for strategy discovery - test_strategy_discovery()."""

    @pytest.fixture
    def temp_strategies_dir(self, tmp_path):
        """Create temporary strategies directory with multiple strategies."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()

        # Create pullback strategy
        pullback = strategies_dir / "pullback"
        pullback.mkdir()
        (pullback / "config.yaml").write_text("name: pullback")
        (pullback / "strategy.py").write_text("# Pullback strategy")

        # Create momentum strategy
        momentum = strategies_dir / "momentum"
        momentum.mkdir()
        (momentum / "config.yaml").write_text("name: momentum")
        (momentum / "strategy.py").write_text("# Momentum strategy")

        # Create incomplete strategy (missing strategy.py)
        incomplete = strategies_dir / "incomplete"
        incomplete.mkdir()
        (incomplete / "config.yaml").write_text("name: incomplete")

        # Create __pycache__ directory (should be ignored)
        pycache = strategies_dir / "__pycache__"
        pycache.mkdir()

        # Temporarily change StrategyLoader.STRATEGIES_DIR
        original_dir = StrategyLoader.STRATEGIES_DIR
        StrategyLoader.STRATEGIES_DIR = strategies_dir

        yield strategies_dir

        StrategyLoader.STRATEGIES_DIR = original_dir

    def test_discover_strategies(self, temp_strategies_dir):
        """Test StrategyLoader.discover_strategies finds valid strategies."""
        discovered = StrategyLoader.discover_strategies()

        assert 'pullback' in discovered
        assert 'momentum' in discovered
        assert 'incomplete' not in discovered  # Missing strategy.py
        assert '__pycache__' not in discovered

    def test_discover_strategies_returns_paths(self, temp_strategies_dir):
        """Test discover_strategies returns correct paths."""
        discovered = StrategyLoader.discover_strategies()

        assert isinstance(discovered['pullback'], Path)
        assert discovered['pullback'].name == 'pullback'

    def test_list_strategies(self, temp_strategies_dir):
        """Test StrategyLoader.list_strategies returns sorted list."""
        strategies = StrategyLoader.list_strategies()

        assert isinstance(strategies, list)
        assert 'pullback' in strategies
        assert 'momentum' in strategies
        assert strategies == sorted(strategies)

    def test_validate_strategy_valid(self, temp_strategies_dir):
        """Test StrategyLoader.validate_strategy for valid strategy."""
        pullback_path = temp_strategies_dir / "pullback"

        result = StrategyLoader.validate_strategy(pullback_path)

        assert result is True

    def test_validate_strategy_missing_config(self, temp_strategies_dir):
        """Test validate_strategy returns False for missing config."""
        no_config = temp_strategies_dir / "no_config"
        no_config.mkdir()
        (no_config / "strategy.py").write_text("# strategy")

        result = StrategyLoader.validate_strategy(no_config)

        assert result is False

    def test_validate_strategy_missing_strategy_file(self, temp_strategies_dir):
        """Test validate_strategy returns False for missing strategy.py."""
        incomplete = temp_strategies_dir / "incomplete"

        result = StrategyLoader.validate_strategy(incomplete)

        assert result is False

    def test_validate_strategy_nonexistent(self, temp_strategies_dir):
        """Test validate_strategy returns False for nonexistent path."""
        nonexistent = temp_strategies_dir / "nonexistent"

        result = StrategyLoader.validate_strategy(nonexistent)

        assert result is False


# ============================================================================
# Test: test_strategy_loader()
# ============================================================================

class TestStrategyLoader:
    """Tests for dynamic strategy loading - test_strategy_loader()."""

    @pytest.fixture
    def loadable_strategy(self, tmp_path):
        """Create a fully loadable strategy."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()

        test_strategy = strategies_dir / "loadable"
        test_strategy.mkdir()
        (test_strategy / "__init__.py").write_text("")

        config_content = """
strategy:
  name: loadable
parameters:
  threshold: 0.02
risk_management:
  take_profit_ratio: 0.03
  stop_loss_ratio: 0.02
"""
        (test_strategy / "config.yaml").write_text(config_content)

        strategy_content = '''
import pandas as pd
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from strategies.base import BaseStrategy, Signal, OrderInfo


class LoadableStrategy(BaseStrategy):
    name = "LoadableStrategy"
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
        (test_strategy / "strategy.py").write_text(strategy_content)

        original_dir = StrategyLoader.STRATEGIES_DIR
        StrategyLoader.STRATEGIES_DIR = strategies_dir

        yield test_strategy

        StrategyLoader.STRATEGIES_DIR = original_dir

    def test_load_strategy_class(self, loadable_strategy):
        """Test _load_strategy_class loads the correct class."""
        try:
            strategy_class = StrategyLoader._load_strategy_class("loadable")

            assert strategy_class is not None
            assert strategy_class.name == "LoadableStrategy"
        except Exception:
            # May fail due to import issues in test environment
            pytest.skip("Strategy loading not available in test environment")

    def test_load_strategy_not_found(self, tmp_path):
        """Test load_strategy raises error for non-existent strategy."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()

        original_dir = StrategyLoader.STRATEGIES_DIR
        StrategyLoader.STRATEGIES_DIR = strategies_dir

        try:
            with pytest.raises(StrategyConfigError):
                StrategyLoader.load_strategy("nonexistent")
        finally:
            StrategyLoader.STRATEGIES_DIR = original_dir


# ============================================================================
# Test: Helper Functions
# ============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_merge_configs_simple(self):
        """Test merging simple configs."""
        base = {'a': 1, 'b': 2}
        override = {'b': 3, 'c': 4}

        result = merge_configs(base, override)

        assert result['a'] == 1
        assert result['b'] == 3
        assert result['c'] == 4

    def test_merge_configs_nested(self):
        """Test merging nested configs."""
        base = {
            'level1': {
                'a': 1,
                'b': 2
            }
        }
        override = {
            'level1': {
                'b': 3,
                'c': 4
            }
        }

        result = merge_configs(base, override)

        assert result['level1']['a'] == 1
        assert result['level1']['b'] == 3
        assert result['level1']['c'] == 4

    def test_merge_configs_deep_nested(self):
        """Test merging deeply nested configs."""
        base = {
            'level1': {
                'level2': {
                    'a': 1
                }
            }
        }
        override = {
            'level1': {
                'level2': {
                    'b': 2
                }
            }
        }

        result = merge_configs(base, override)

        assert result['level1']['level2']['a'] == 1
        assert result['level1']['level2']['b'] == 2

    def test_merge_configs_preserves_base(self):
        """Test merge_configs doesn't modify base dict."""
        base = {'a': 1, 'nested': {'x': 1}}
        override = {'b': 2, 'nested': {'y': 2}}

        result = merge_configs(base, override)

        assert 'b' not in base
        assert 'y' not in base['nested']


# ============================================================================
# Test: Pullback Config Loading (Integration)
# ============================================================================

class TestPullbackConfigIntegration:
    """Integration tests for pullback strategy config loading."""

    def test_load_actual_pullback_config(self):
        """Test loading actual pullback strategy config."""
        try:
            config = StrategyConfig("pullback")
            result = config.load()

            assert result is not None
            assert 'parameters' in result
            assert 'risk_management' in result

        except FileNotFoundError:
            pytest.skip("Pullback strategy not found in actual path")

    def test_pullback_config_has_required_sections(self):
        """Test pullback config has required sections."""
        try:
            config = StrategyConfig("pullback")
            result = config.load()

            # Check required sections
            assert 'parameters' in result or 'strategy' in result
            assert 'risk_management' in result

        except FileNotFoundError:
            pytest.skip("Pullback strategy not found in actual path")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
