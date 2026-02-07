"""
Market Data Module (Facade)
===========================

Market data provider for:
- Minute-level OHLCV data
- Daily OHLCV data
- Current price quotes
- Real-time data subscription

Integrates with:
- api/kis_chart_api.py (chart data)
- api/kis_market_api.py (current price, daily data)
- core/data_collector.py (real-time collection)
- core/realtime_candle_builder.py (candle builder)

This module serves as a facade for backward compatibility.
The actual implementations are in the data_providers subpackage:
- data_providers/models.py: OHLCV, PriceQuote data classes
- data_providers/data_standardizer.py: DataFrame standardization
- data_providers/cache_manager.py: Cache management
- data_providers/subscription_manager.py: Real-time subscriptions
- data_providers/data_provider.py: Main async DataProvider
- data_providers/realtime_collector.py: RealtimeDataCollector
- data_providers/market_data_legacy.py: Legacy MarketData class
- data_providers/utils.py: Utility functions
"""

# ============================================================================
# Import from refactored modules for backward compatibility
# ============================================================================

# Data classes
from .data_providers.models import OHLCV, PriceQuote

# Main provider classes
from .data_providers.data_provider import DataProvider
from .data_providers.realtime_collector import RealtimeDataCollector
from .data_providers.market_data_legacy import MarketData

# Support classes (for advanced usage)
from .data_providers.data_standardizer import DataStandardizer
from .data_providers.cache_manager import CacheManager
from .data_providers.subscription_manager import SubscriptionManager

# Utility functions
from .data_providers.utils import (
    merge_ohlcv_dataframes,
    resample_ohlcv,
    dataframe_to_ohlcv_list
)

# ============================================================================
# Public API - All exports for backward compatibility
# ============================================================================

__all__ = [
    # Data classes
    'OHLCV',
    'PriceQuote',

    # Main provider classes
    'DataProvider',
    'RealtimeDataCollector',
    'MarketData',

    # Support classes
    'DataStandardizer',
    'CacheManager',
    'SubscriptionManager',

    # Utility functions
    'merge_ohlcv_dataframes',
    'resample_ohlcv',
    'dataframe_to_ohlcv_list',
]
