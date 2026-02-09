"""
Framework Utilities Module
==========================

Common utility functions for the trading system:
- Logging setup
- Korean time handling (timezone aware)
- KRX tick size calculation
- Market hours checking
- Price formatting utilities
- Configuration loading
"""

import math
import json
import logging
import sys
import time as time_module
from datetime import datetime, time, timezone, timedelta
from pathlib import Path
from typing import Optional, Union, Dict, Any


# ============================================================================
# Time Utilities
# ============================================================================

# Korean Standard Time (UTC+9)
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """
    Get current time in Korean Standard Time (KST).

    Returns:
        datetime: Current KST datetime with timezone info
    """
    return datetime.now(KST)


def is_market_open(dt: Optional[datetime] = None) -> bool:
    """
    Check if the Korean stock market is open.

    Args:
        dt: Datetime to check (default: current KST time)

    Returns:
        bool: True if market is open
    """
    if dt is None:
        dt = now_kst()

    # Ensure timezone awareness
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)

    # Weekend check
    if dt.weekday() >= 5:
        return False

    # Market hours: 09:00 ~ 15:30 KST
    market_open = get_market_open_time()
    market_close = get_market_close_time()
    current_time = dt.time()

    return market_open <= current_time <= market_close


def get_market_open_time() -> time:
    """
    Get market open time.

    Returns:
        time: Market open time (09:00)
    """
    return time(9, 0)


def get_market_close_time() -> time:
    """
    Get market close time.

    Returns:
        time: Market close time (15:30)
    """
    return time(15, 30)


def get_market_status(dt: Optional[datetime] = None) -> str:
    """
    Get market status description.

    Args:
        dt: Datetime to check (default: current KST time)

    Returns:
        str: Market status ('OPEN', 'CLOSED', 'PRE_MARKET', 'POST_MARKET')
    """
    if dt is None:
        dt = now_kst()

    # Ensure timezone awareness
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)

    # Weekend
    if dt.weekday() >= 5:
        return 'CLOSED'

    current_time = dt.time()
    market_open = get_market_open_time()
    market_close = get_market_close_time()

    if current_time < market_open:
        return 'PRE_MARKET'
    elif current_time <= market_close:
        return 'OPEN'
    else:
        return 'POST_MARKET'


# ============================================================================
# Price Utilities
# ============================================================================

def get_tick_size(price: float) -> int:
    """
    Get KRX tick size for given price.

    KRX Tick Size Table:
    - < 1,000: 1 won
    - < 5,000: 5 won
    - < 10,000: 10 won
    - < 50,000: 50 won
    - < 100,000: 100 won
    - < 500,000: 500 won
    - >= 500,000: 1,000 won

    Args:
        price: Price to check

    Returns:
        int: Tick size for the price level
    """
    if price < 1000:
        return 1
    elif price < 5000:
        return 5
    elif price < 10000:
        return 10
    elif price < 50000:
        return 50
    elif price < 100000:
        return 100
    elif price < 500000:
        return 500
    else:
        return 1000


def round_to_tick(price: float) -> int:
    """
    Round price to KRX tick size.

    Args:
        price: Price to round

    Returns:
        int: Rounded price aligned to tick size
    """
    if price <= 0:
        return 0

    tick = get_tick_size(price)
    return int(math.floor(price / tick + 0.5)) * tick


def validate_tick(price: float) -> bool:
    """
    Validate if price is aligned to KRX tick size.

    Args:
        price: Price to validate

    Returns:
        bool: True if valid (aligned to tick size)
    """
    if price <= 0:
        return False

    tick = get_tick_size(price)
    return int(price) % tick == 0


def calculate_change_rate(current: float, base: float) -> float:
    """
    Calculate change rate (percentage).

    Args:
        current: Current price
        base: Base price (reference)

    Returns:
        float: Change rate as decimal (0.05 = 5%)
    """
    if base == 0:
        return 0.0
    return (current - base) / base


def format_price(price: float) -> str:
    """
    Format price with thousands separator (comma).

    Args:
        price: Price to format

    Returns:
        str: Formatted price string (e.g., "1,234,567")
    """
    return f"{int(price):,}"


def format_quantity(qty: int) -> str:
    """
    Format quantity with thousands separator.

    Args:
        qty: Quantity to format

    Returns:
        str: Formatted quantity string (e.g., "1,234")
    """
    return f"{qty:,}"


def format_currency(amount: float, symbol: str = '') -> str:
    """
    Format currency with thousands separator.

    Args:
        amount: Amount to format
        symbol: Currency symbol (default: empty)

    Returns:
        str: Formatted currency string
    """
    if symbol:
        return f"{amount:,.0f}{symbol}"
    return f"{amount:,.0f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Format percentage value.

    Args:
        value: Decimal value (0.05 = 5%)
        decimals: Decimal places

    Returns:
        str: Formatted percentage string (e.g., "5.00%")
    """
    return f"{value * 100:.{decimals}f}%"


# ============================================================================
# Logging Utilities
# ============================================================================

def setup_logger(
    name: str,
    level: int = logging.INFO,
    file_path: Optional[Union[str, Path]] = None,
    use_kst: bool = True,
) -> logging.Logger:
    """
    Setup and configure a logger.

    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)
        file_path: Log file path (default: logs/trading_YYYYMMDD.log)
        use_kst: Use KST timestamps (default: True)

    Returns:
        logging.Logger: Configured logger
    """
    # Log directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Log file path
    if file_path is None:
        today = now_kst().strftime("%Y%m%d")
        log_file = log_dir / f"trading_{today}.log"
    else:
        log_file = Path(file_path)
        if not log_file.parent.exists():
            log_file.parent.mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # Clear existing handlers
    if logger.handlers:
        logger.handlers.clear()

    # Formatter (clean format without emojis)
    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # KST timestamp converter
    if use_kst:
        def kst_converter(secs: float):
            try:
                return datetime.fromtimestamp(secs, KST).timetuple()
            except Exception:
                return time_module.localtime(secs)
        formatter.converter = kst_converter

    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# ============================================================================
# Configuration Utilities
# ============================================================================

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to configuration file

    Returns:
        dict: Configuration dictionary

    Raises:
        FileNotFoundError: If config file does not exist
        json.JSONDecodeError: If config file is not valid JSON
    """
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================================
# Backward Compatibility Aliases
# ============================================================================

# Alias for validate_tick (backward compatibility)
validate_tick_size = validate_tick
