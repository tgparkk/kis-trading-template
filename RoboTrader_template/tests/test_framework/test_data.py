"""
Framework Data Tests
====================

Tests for framework/data.py - DataProvider tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
import pandas as pd
import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from framework.data import (
    OHLCV,
    PriceQuote,
    DataProvider,
    MarketData,
    merge_ohlcv_dataframes,
    resample_ohlcv,
    dataframe_to_ohlcv_list,
)


# ============================================================================
# Test: OHLCV Dataclass
# ============================================================================

class TestOHLCV:
    """Tests for OHLCV dataclass."""

    def test_ohlcv_creation(self):
        """Test creating OHLCV."""
        kst = timezone(timedelta(hours=9))
        dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst)

        ohlcv = OHLCV(
            datetime=dt,
            open=70000,
            high=71000,
            low=69000,
            close=70500,
            volume=10000
        )

        assert ohlcv.open == 70000
        assert ohlcv.high == 71000
        assert ohlcv.low == 69000
        assert ohlcv.close == 70500
        assert ohlcv.volume == 10000

    def test_ohlcv_range(self):
        """Test OHLCV.range property."""
        kst = timezone(timedelta(hours=9))
        ohlcv = OHLCV(
            datetime=datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst),
            open=70000,
            high=71000,
            low=69000,
            close=70500,
            volume=10000
        )

        assert ohlcv.range == 2000  # 71000 - 69000

    def test_ohlcv_body(self):
        """Test OHLCV.body property."""
        kst = timezone(timedelta(hours=9))
        ohlcv = OHLCV(
            datetime=datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst),
            open=70000,
            high=71000,
            low=69000,
            close=70500,
            volume=10000
        )

        assert ohlcv.body == 500  # abs(70500 - 70000)

    def test_ohlcv_is_bullish(self):
        """Test OHLCV.is_bullish property."""
        kst = timezone(timedelta(hours=9))

        bullish = OHLCV(
            datetime=datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst),
            open=70000,
            high=71000,
            low=69000,
            close=70500,  # close > open
            volume=10000
        )
        assert bullish.is_bullish is True

        bearish = OHLCV(
            datetime=datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst),
            open=70500,
            high=71000,
            low=69000,
            close=70000,  # close < open
            volume=10000
        )
        assert bearish.is_bullish is False

    def test_ohlcv_to_dict(self):
        """Test OHLCV.to_dict method."""
        kst = timezone(timedelta(hours=9))
        dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=kst)

        ohlcv = OHLCV(
            datetime=dt,
            open=70000,
            high=71000,
            low=69000,
            close=70500,
            volume=10000
        )

        d = ohlcv.to_dict()

        assert d['open'] == 70000
        assert d['high'] == 71000
        assert d['low'] == 69000
        assert d['close'] == 70500
        assert d['volume'] == 10000


# ============================================================================
# Test: PriceQuote Dataclass
# ============================================================================

class TestPriceQuote:
    """Tests for PriceQuote dataclass."""

    def test_price_quote_creation(self):
        """Test creating PriceQuote."""
        quote = PriceQuote(
            stock_code="005930",
            current_price=70000,
            change=1000,
            change_rate=0.0145,
            volume=1000000
        )

        assert quote.stock_code == "005930"
        assert quote.current_price == 70000
        assert quote.change == 1000
        assert quote.change_rate == 0.0145
        assert quote.volume == 1000000

    def test_price_quote_default_timestamp(self):
        """Test PriceQuote sets default timestamp."""
        quote = PriceQuote(
            stock_code="005930",
            current_price=70000
        )

        assert quote.timestamp is not None


# ============================================================================
# Test: DataProvider
# ============================================================================

class TestDataProvider:
    """Tests for DataProvider class."""

    @pytest.fixture
    def provider(self, mock_broker):
        """Create DataProvider instance."""
        return DataProvider(mock_broker)

    def test_provider_creation(self, mock_broker):
        """Test DataProvider creation."""
        provider = DataProvider(mock_broker)

        assert provider is not None
        assert provider.broker == mock_broker

    def test_provider_cache_management(self, provider):
        """Test cache clear."""
        provider.clear_cache()
        # Should not raise

    def test_provider_set_cache_ttl(self, provider):
        """Test setting cache TTL."""
        provider.set_cache_ttl(120)
        assert provider._cache.default_ttl == 120

    def test_provider_subscribe(self, provider):
        """Test subscribe to real-time data."""
        callback = Mock()
        result = provider.subscribe("005930", callback)

        assert result is True
        assert "005930" in provider.get_subscribed_stocks()

    def test_provider_subscribe_duplicate(self, provider):
        """Test duplicate subscribe."""
        callback = Mock()
        provider.subscribe("005930", callback)
        result = provider.subscribe("005930", callback)

        assert result is False  # Already subscribed

    def test_provider_unsubscribe(self, provider):
        """Test unsubscribe."""
        callback = Mock()
        provider.subscribe("005930", callback)
        result = provider.unsubscribe("005930")

        assert result is True
        assert "005930" not in provider.get_subscribed_stocks()

    def test_provider_unsubscribe_not_subscribed(self, provider):
        """Test unsubscribe when not subscribed."""
        result = provider.unsubscribe("NOTSUBSCRIBED")
        assert result is False

    def test_provider_shutdown(self, provider):
        """Test shutdown."""
        provider.shutdown()
        # Should not raise


# ============================================================================
# Test: MarketData (Legacy)
# ============================================================================

class TestMarketData:
    """Tests for MarketData class (legacy compatibility)."""

    @pytest.fixture
    def market_data(self, mock_broker):
        """Create MarketData instance."""
        return MarketData(mock_broker)

    def test_market_data_creation(self, mock_broker):
        """Test MarketData creation."""
        market_data = MarketData(mock_broker)

        assert market_data is not None
        assert market_data.broker == mock_broker

    def test_market_data_clear_cache(self, market_data):
        """Test clear_cache method."""
        market_data.clear_cache()
        # Should not raise


# ============================================================================
# Test: Utility Functions
# ============================================================================

class TestDataUtilityFunctions:
    """Tests for data utility functions."""

    def test_merge_ohlcv_dataframes_empty(self):
        """Test merging when one df is empty."""
        df1 = pd.DataFrame()
        df2 = pd.DataFrame({
            'datetime': pd.date_range('2024-01-15 09:00', periods=5, freq='1min'),
            'close': [100, 101, 102, 103, 104]
        })

        result = merge_ohlcv_dataframes(df1, df2)

        assert len(result) == 5

    def test_merge_ohlcv_dataframes_both_empty(self):
        """Test merging two empty dataframes."""
        df1 = pd.DataFrame()
        df2 = None

        result = merge_ohlcv_dataframes(df1, df2)

        assert result.empty

    def test_merge_ohlcv_dataframes_removes_duplicates(self):
        """Test merging removes duplicates."""
        dates1 = pd.date_range('2024-01-15 09:00', periods=5, freq='1min')
        dates2 = pd.date_range('2024-01-15 09:03', periods=5, freq='1min')  # Overlaps

        df1 = pd.DataFrame({
            'datetime': dates1,
            'close': [100, 101, 102, 103, 104]
        })
        df2 = pd.DataFrame({
            'datetime': dates2,
            'close': [200, 201, 202, 203, 204]  # Different values
        })

        result = merge_ohlcv_dataframes(df1, df2)

        # Should have unique datetimes
        assert len(result) == 8  # 5 + 5 - 2 overlap

    def test_resample_ohlcv(self):
        """Test OHLCV resampling."""
        dates = pd.date_range('2024-01-15 09:00', periods=10, freq='1min')

        df = pd.DataFrame({
            'datetime': dates,
            'open': [100] * 10,
            'high': [105] * 10,
            'low': [95] * 10,
            'close': [102] * 10,
            'volume': [1000] * 10
        })

        result = resample_ohlcv(df, '3min')

        # 10 minutes / 3 = 3-4 candles
        assert len(result) <= 4

    def test_resample_ohlcv_empty(self):
        """Test resampling empty dataframe."""
        df = pd.DataFrame()

        result = resample_ohlcv(df, '3min')

        assert result.empty

    def test_dataframe_to_ohlcv_list(self, sample_ohlcv_data):
        """Test converting DataFrame to OHLCV list."""
        result = dataframe_to_ohlcv_list(sample_ohlcv_data)

        assert isinstance(result, list)
        assert len(result) == len(sample_ohlcv_data)
        assert all(isinstance(o, OHLCV) for o in result)

    def test_dataframe_to_ohlcv_list_empty(self):
        """Test converting empty DataFrame."""
        df = pd.DataFrame()

        result = dataframe_to_ohlcv_list(df)

        assert result == []


# ============================================================================
# Test: Async Methods
# ============================================================================

class TestDataProviderAsync:
    """Tests for DataProvider async methods."""

    @pytest.fixture
    def provider(self, mock_broker):
        """Create DataProvider instance."""
        return DataProvider(mock_broker)

    @pytest.mark.asyncio
    async def test_get_minute_data(self, provider):
        """Test async get_minute_data."""
        # Will return empty due to mock
        result = await provider.get_minute_data("005930", minutes=30)

        assert isinstance(result, pd.DataFrame)

    @pytest.mark.asyncio
    async def test_get_daily_data(self, provider):
        """Test async get_daily_data."""
        result = await provider.get_daily_data("005930", days=20)

        assert isinstance(result, pd.DataFrame)

    @pytest.mark.asyncio
    async def test_get_current_price(self, provider):
        """Test async get_current_price."""
        result = await provider.get_current_price("005930")

        assert isinstance(result, (int, float))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
