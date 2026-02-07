"""
Data Providers Package
======================

This package contains refactored components from framework/data.py,
organized by single responsibility principle.

Modules:
- models: Data classes (OHLCV, PriceQuote)
- data_standardizer: DataFrame standardization utilities
- cache_manager: Cache management for market data
- subscription_manager: Real-time subscription handling
- data_provider: Main async DataProvider class
- realtime_collector: Real-time data collection
- market_data_legacy: Legacy synchronous MarketData class
- utils: Utility functions for OHLCV data manipulation
"""

from .models import OHLCV, PriceQuote
from .data_standardizer import DataStandardizer
from .cache_manager import CacheManager
from .subscription_manager import SubscriptionManager
from .data_provider import DataProvider
from .realtime_collector import RealtimeDataCollector
from .market_data_legacy import MarketData
from .utils import (
    merge_ohlcv_dataframes,
    resample_ohlcv,
    dataframe_to_ohlcv_list
)

__all__ = [
    # Data classes
    'OHLCV',
    'PriceQuote',

    # Core classes
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
