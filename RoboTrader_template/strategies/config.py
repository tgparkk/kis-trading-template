"""
Strategy Configuration Loader
=============================

Loads strategy configuration from YAML files and
dynamically imports strategy classes.

Usage:
    # Load strategy configuration
    config = StrategyConfig('my_strategy')
    config.load()

    # Get configuration values
    take_profit = config.get('risk_management.take_profit_ratio', 0.03)

    # Discover and load strategies
    strategies = StrategyLoader.discover_strategies()
    strategy = StrategyLoader.load_strategy('my_strategy')
"""

from pathlib import Path
from typing import Dict, Any, Optional, Type, TYPE_CHECKING
import importlib
import importlib.util
import sys

import yaml

if TYPE_CHECKING:
    from .base import BaseStrategy


class StrategyConfigError(Exception):
    """Exception raised for strategy configuration errors."""
    pass


class StrategyConfig:
    """
    Strategy configuration manager.

    Handles:
    - Loading YAML configuration files
    - Configuration value access (with nested key support)
    - Configuration validation
    - Configuration saving

    Example:
        config = StrategyConfig('my_strategy')
        config.load()

        # Access values
        tp_ratio = config.get('risk_management.take_profit_ratio', 0.03)

        # Modify and save
        config.set('risk_management.stop_loss_ratio', 0.02)
        config.save()
    """

    def __init__(self, strategy_name: str):
        """
        Initialize strategy configuration.

        Args:
            strategy_name: Strategy name (folder name under strategies/)
        """
        self.strategy_name = strategy_name
        self._config: Dict[str, Any] = {}
        self._config_path: Optional[Path] = None

    def load(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to configuration file.
                         If None, uses default path: strategies/{strategy_name}/config.yaml

        Returns:
            Dict[str, Any]: Loaded configuration dictionary

        Raises:
            StrategyConfigError: If config file not found or invalid YAML
            FileNotFoundError: If the config file does not exist
        """
        if config_path:
            self._config_path = Path(config_path)
        else:
            self._config_path = self.get_default_config_path(self.strategy_name)

        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self._config_path}\n"
                f"Expected at: strategies/{self.strategy_name}/config.yaml"
            )

        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                loaded_config = yaml.safe_load(f)

            # Handle empty YAML files
            if loaded_config is None:
                loaded_config = {}

            self._config = loaded_config

            # Set default name if not provided
            if 'name' not in self._config:
                self._config['name'] = self.strategy_name

            return self._config

        except yaml.YAMLError as e:
            raise StrategyConfigError(
                f"Invalid YAML in {self._config_path}: {e}"
            )
        except IOError as e:
            raise StrategyConfigError(
                f"Failed to read config file {self._config_path}: {e}"
            )

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Supports nested keys using dot notation.

        Args:
            key: Configuration key (e.g., 'risk_management.stop_loss_ratio')
            default: Default value if key not found

        Returns:
            Any: Configuration value or default

        Example:
            config.get('name')  # -> 'my_strategy'
            config.get('risk_management.take_profit_ratio', 0.03)  # -> 0.03
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value by key.

        Supports nested keys using dot notation.
        Creates intermediate dictionaries if they don't exist.

        Args:
            key: Configuration key (e.g., 'risk_management.stop_loss_ratio')
            value: Value to set

        Example:
            config.set('risk_management.stop_loss_ratio', 0.025)
        """
        keys = key.split('.')
        current = self._config

        # Navigate to the parent of the final key
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            elif not isinstance(current[k], dict):
                # Overwrite non-dict value with dict
                current[k] = {}
            current = current[k]

        # Set the final key
        current[keys[-1]] = value

    def validate(self, schema: Optional[Dict[str, type]] = None) -> bool:
        """
        Validate configuration against a schema.

        Args:
            schema: Dictionary mapping keys to expected types.
                    If None, performs basic validation only.

        Returns:
            bool: True if validation passes

        Raises:
            StrategyConfigError: If validation fails

        Example:
            schema = {
                'name': str,
                'enabled': bool,
                'risk_management.take_profit_ratio': float,
            }
            config.validate(schema)
        """
        # Basic validation: check for required fields
        if not self._config.get('name'):
            raise StrategyConfigError("Configuration must have a 'name' field")

        if schema is None:
            # Default schema for basic validation
            schema = {
                'name': str,
            }

        for key, expected_type in schema.items():
            value = self.get(key)

            if value is None:
                continue  # Skip None values (optional fields)

            if not isinstance(value, expected_type):
                raise StrategyConfigError(
                    f"Invalid type for '{key}': expected {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )

        # Validate risk management ratios if present
        risk_config = self.get('risk_management', {})
        if risk_config:
            for ratio_key in ['take_profit_ratio', 'stop_loss_ratio', 'max_position_ratio']:
                ratio_value = risk_config.get(ratio_key)
                if ratio_value is not None:
                    if not isinstance(ratio_value, (int, float)):
                        raise StrategyConfigError(
                            f"'{ratio_key}' must be a number, got {type(ratio_value).__name__}"
                        )
                    if not (0 < ratio_value <= 1):
                        raise StrategyConfigError(
                            f"'{ratio_key}' must be between 0 and 1 (exclusive), got {ratio_value}"
                        )

        return True

    def save(self, config_path: Optional[str] = None) -> bool:
        """
        Save configuration to YAML file.

        Args:
            config_path: Path to save configuration.
                         If None, uses the path from load() or default path.

        Returns:
            bool: True if save successful

        Raises:
            StrategyConfigError: If save fails
        """
        if config_path:
            save_path = Path(config_path)
        elif self._config_path:
            save_path = self._config_path
        else:
            save_path = self.get_default_config_path(self.strategy_name)

        try:
            # Ensure parent directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    self._config,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False
                )

            self._config_path = save_path
            return True

        except IOError as e:
            raise StrategyConfigError(
                f"Failed to save config to {save_path}: {e}"
            )

    @staticmethod
    def get_default_config_path(strategy_name: str) -> Path:
        """
        Get default configuration file path for a strategy.

        Args:
            strategy_name: Strategy name (folder name)

        Returns:
            Path: Default path to config.yaml
        """
        return Path(f"strategies/{strategy_name}/config.yaml")

    @property
    def config(self) -> Dict[str, Any]:
        """Get the full configuration dictionary."""
        return self._config.copy()

    def __repr__(self) -> str:
        """String representation."""
        return f"<StrategyConfig(strategy='{self.strategy_name}', loaded={bool(self._config)})>"


class StrategyLoader:
    """
    Strategy dynamic loader.

    Handles:
    - Discovering available strategies
    - Dynamic strategy class loading
    - Strategy structure validation

    Example:
        # Discover all strategies
        strategies = StrategyLoader.discover_strategies()
        # -> {'my_strategy': Path('strategies/my_strategy'), ...}

        # Load a specific strategy
        strategy = StrategyLoader.load_strategy('my_strategy')
    """

    # Default strategies directory
    STRATEGIES_DIR = Path("strategies")

    @staticmethod
    def discover_strategies() -> Dict[str, Path]:
        """
        Discover available strategies in the strategies directory.

        Scans the strategies/ directory for valid strategy folders.
        A valid strategy folder must contain:
        - config.yaml: Strategy configuration
        - strategy.py: Strategy implementation

        Returns:
            Dict[str, Path]: Dictionary mapping strategy names to their paths

        Example:
            strategies = StrategyLoader.discover_strategies()
            # -> {'my_strategy': Path('strategies/my_strategy'),
            #     'momentum': Path('strategies/momentum')}
        """
        strategies_dir = StrategyLoader.STRATEGIES_DIR
        discovered: Dict[str, Path] = {}

        if not strategies_dir.exists():
            return discovered

        for path in strategies_dir.iterdir():
            if path.is_dir() and not path.name.startswith('_'):
                if StrategyLoader.validate_strategy(path):
                    discovered[path.name] = path

        return discovered

    @staticmethod
    def load_strategy(strategy_name: str) -> 'BaseStrategy':
        """
        Dynamically load and instantiate a strategy.

        Loads the strategy module from strategies/{strategy_name}/strategy.py,
        finds the strategy class (subclass of BaseStrategy),
        loads its configuration, and returns an instance.

        Args:
            strategy_name: Strategy name (folder name under strategies/)

        Returns:
            BaseStrategy: Instantiated strategy with loaded configuration

        Raises:
            StrategyConfigError: If strategy cannot be loaded
            FileNotFoundError: If strategy files not found

        Example:
            strategy = StrategyLoader.load_strategy('my_strategy')
            strategy.on_init(broker, data_provider, executor)
        """
        strategy_path = StrategyLoader.STRATEGIES_DIR / strategy_name

        if not StrategyLoader.validate_strategy(strategy_path):
            raise StrategyConfigError(
                f"Invalid strategy structure at {strategy_path}. "
                f"Strategy must have config.yaml and strategy.py"
            )

        # Load configuration
        config_loader = StrategyConfig(strategy_name)
        config = config_loader.load()

        # Load strategy class
        strategy_class = StrategyLoader._load_strategy_class(strategy_name)

        # Instantiate and return
        return strategy_class(config)

    @staticmethod
    def _load_strategy_class(strategy_name: str) -> Type['BaseStrategy']:
        """
        Dynamically load a strategy class from module.

        Args:
            strategy_name: Strategy name (folder name)

        Returns:
            Type[BaseStrategy]: Strategy class

        Raises:
            StrategyConfigError: If module or class not found
        """
        module_name = f"strategies.{strategy_name}.strategy"

        try:
            # Try importing as a package module first
            module = importlib.import_module(module_name)
        except ImportError:
            # Fall back to loading from file path
            strategy_file = StrategyLoader.STRATEGIES_DIR / strategy_name / "strategy.py"

            if not strategy_file.exists():
                raise StrategyConfigError(
                    f"Strategy module not found: {strategy_file}"
                )

            try:
                spec = importlib.util.spec_from_file_location(
                    module_name, strategy_file
                )
                if spec is None or spec.loader is None:
                    raise StrategyConfigError(
                        f"Failed to load module spec from {strategy_file}"
                    )

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

            except Exception as e:
                raise StrategyConfigError(
                    f"Failed to load strategy module {strategy_file}: {e}"
                )

        # Find strategy class in module
        strategy_class = None

        # Import BaseStrategy for type checking
        from .base import BaseStrategy

        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue

            attr = getattr(module, attr_name)

            # Check if it's a class that ends with 'Strategy'
            if (isinstance(attr, type) and
                attr_name.endswith('Strategy') and
                attr_name != 'BaseStrategy'):

                # Verify it's a subclass of BaseStrategy
                if issubclass(attr, BaseStrategy) and attr is not BaseStrategy:
                    strategy_class = attr
                    break

        if strategy_class is None:
            raise StrategyConfigError(
                f"No Strategy class found in {module_name}. "
                f"Ensure your class name ends with 'Strategy' and inherits from BaseStrategy."
            )

        return strategy_class

    @staticmethod
    def validate_strategy(strategy_path: Path) -> bool:
        """
        Validate strategy folder structure.

        A valid strategy must have:
        - config.yaml: Configuration file
        - strategy.py: Strategy implementation

        Args:
            strategy_path: Path to strategy folder

        Returns:
            bool: True if valid, False otherwise

        Example:
            if StrategyLoader.validate_strategy(Path('strategies/my_strategy')):
                strategy = StrategyLoader.load_strategy('my_strategy')
        """
        if not strategy_path.exists():
            return False

        if not strategy_path.is_dir():
            return False

        # Check for required files
        config_file = strategy_path / "config.yaml"
        strategy_file = strategy_path / "strategy.py"

        return config_file.exists() and strategy_file.exists()

    @staticmethod
    def list_strategies() -> list:
        """
        List all available strategy names.

        Returns:
            list: Sorted list of strategy names
        """
        return sorted(StrategyLoader.discover_strategies().keys())


# ============================================================================
# Helper Functions
# ============================================================================

def load_yaml_config(file_path: str) -> Dict[str, Any]:
    """
    Load a YAML configuration file.

    Args:
        file_path: Path to YAML file

    Returns:
        Dict: Parsed configuration

    Raises:
        FileNotFoundError: If file doesn't exist
        StrategyConfigError: If YAML is invalid
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config if config is not None else {}
    except yaml.YAMLError as e:
        raise StrategyConfigError(f"Invalid YAML in {path}: {e}")


def merge_configs(
    base: Dict[str, Any],
    override: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Deep merge two configuration dictionaries.

    Values in override take precedence over base.
    Nested dictionaries are merged recursively.

    Args:
        base: Base configuration
        override: Override configuration (takes precedence)

    Returns:
        Dict: Merged configuration

    Example:
        base = {'a': 1, 'b': {'c': 2, 'd': 3}}
        override = {'b': {'c': 4}}
        result = merge_configs(base, override)
        # -> {'a': 1, 'b': {'c': 4, 'd': 3}}
    """
    result = base.copy()

    for key, value in override.items():
        if (key in result and
            isinstance(result[key], dict) and
            isinstance(value, dict)):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value

    return result


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    'StrategyConfig',
    'StrategyLoader',
    'StrategyConfigError',
    'load_yaml_config',
    'merge_configs',
]
