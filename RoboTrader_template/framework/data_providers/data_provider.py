"""
Data Provider Module
====================

Main market data provider for:
- Minute-level OHLCV data
- Daily OHLCV data
- Current price quotes
- Real-time data subscription

Integrates with:
- api/kis_chart_api.py (chart data)
- api/kis_market_api.py (current price, daily data)
"""

from typing import Optional, List, Callable, TYPE_CHECKING
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import asyncio
import pandas as pd

from ..utils import setup_logger, now_kst
from .models import OHLCV
from .data_standardizer import DataStandardizer
from .cache_manager import CacheManager
from .subscription_manager import SubscriptionManager

if TYPE_CHECKING:
    from ..broker import KISBroker


class DataProvider:
    """
    Market data provider.

    Provides unified interface for market data access:
    - Minute chart data (1min, 3min, etc.)
    - Daily chart data
    - Current price quotes
    - Today's OHLCV data
    - Real-time subscription

    Usage:
        provider = DataProvider(broker)
        df = await provider.get_minute_data("005930", minutes=30)
        price = await provider.get_current_price("005930")
        ohlcv = await provider.get_today_ohlcv("005930")

        # Real-time subscription
        provider.subscribe("005930", my_callback)
        provider.unsubscribe("005930")
    """

    def __init__(self, broker: 'KISBroker'):
        """
        Initialize data provider.

        Args:
            broker: KISBroker instance for API access
        """
        self.broker = broker
        self.logger = setup_logger(__name__)

        # Components
        self._cache = CacheManager(default_ttl=60)
        self._subscription_manager = SubscriptionManager()
        self._standardizer = DataStandardizer()

        # Thread pool for sync API calls
        self._executor = ThreadPoolExecutor(max_workers=4)

        self.logger.info("DataProvider initialized")

    # ========================================================================
    # Async Data Methods
    # ========================================================================

    async def get_minute_data(
        self,
        stock_code: str,
        minutes: int = 30,
        date: str = None,
        end_time: str = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Get minute-level OHLCV data.

        Args:
            stock_code: Stock ticker (6 digits)
            minutes: Number of minutes to retrieve (default: 30)
            date: Target date (YYYYMMDD, default: today)
            end_time: End time (HHMMSS, default: current time)
            use_cache: Use cached data if available (default: True)

        Returns:
            DataFrame with standardized columns:
                ['datetime', 'date', 'time', 'open', 'high', 'low', 'close', 'volume']
        """
        try:
            # Set defaults
            if date is None:
                date = now_kst().strftime("%Y%m%d")
            if end_time is None:
                end_time = now_kst().strftime("%H%M%S")

            # Check cache
            cache_key = f"minute_{stock_code}_{date}_{end_time}_{minutes}"
            if use_cache:
                cached = self._cache.get(cache_key)
                if cached is not None:
                    return cached

            # Execute API call in thread pool
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                self._executor,
                self._get_minute_data_sync,
                stock_code, date, end_time, minutes
            )

            if df is not None and not df.empty:
                self._cache.set(cache_key, df)

            return df if df is not None else pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Failed to get minute data for {stock_code}: {e}")
            return pd.DataFrame()

    async def get_daily_data(
        self,
        stock_code: str,
        days: int = 20,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Get daily OHLCV data.

        Args:
            stock_code: Stock ticker (6 digits)
            days: Number of days to retrieve (default: 20)
            use_cache: Use cached data if available (default: True)

        Returns:
            DataFrame with standardized columns:
                ['date', 'open', 'high', 'low', 'close', 'volume']
        """
        try:
            # Check cache
            cache_key = f"daily_{stock_code}_{days}"
            if use_cache:
                cached = self._cache.get(cache_key)
                if cached is not None:
                    return cached

            # Execute API call in thread pool
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                self._executor,
                self._get_daily_data_sync,
                stock_code, days
            )

            if df is not None and not df.empty:
                # Cache daily data for longer (5 minutes)
                self._cache.set(cache_key, df, ttl=300)

            return df if df is not None else pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Failed to get daily data for {stock_code}: {e}")
            return pd.DataFrame()

    async def get_current_price(self, stock_code: str) -> float:
        """
        Get current price for a stock.

        Args:
            stock_code: Stock ticker (6 digits)

        Returns:
            float: Current price or 0.0 if failed
        """
        try:
            # Check cache (very short TTL for current price)
            cache_key = f"price_{stock_code}"
            cached = self._cache.get(cache_key, ttl_override=5)
            if cached is not None:
                return cached

            # Execute API call in thread pool
            loop = asyncio.get_event_loop()
            price = await loop.run_in_executor(
                self._executor,
                self._get_current_price_sync,
                stock_code
            )

            if price and price > 0:
                self._cache.set(cache_key, price, ttl=5)
                return price

            return 0.0

        except Exception as e:
            self.logger.error(f"Failed to get current price for {stock_code}: {e}")
            return 0.0

    async def get_today_ohlcv(self, stock_code: str) -> Optional[OHLCV]:
        """
        Get today's OHLCV data.

        Args:
            stock_code: Stock ticker (6 digits)

        Returns:
            OHLCV: Today's OHLCV or None if failed
        """
        try:
            # Check cache
            cache_key = f"today_ohlcv_{stock_code}"
            cached = self._cache.get(cache_key, ttl_override=30)
            if cached is not None:
                return cached

            # Execute API call in thread pool
            loop = asyncio.get_event_loop()
            ohlcv = await loop.run_in_executor(
                self._executor,
                self._get_today_ohlcv_sync,
                stock_code
            )

            if ohlcv is not None:
                self._cache.set(cache_key, ohlcv, ttl=30)

            return ohlcv

        except Exception as e:
            self.logger.error(f"Failed to get today OHLCV for {stock_code}: {e}")
            return None

    async def get_intraday_data(
        self,
        stock_code: str,
        start_time: str = None,
        end_time: str = None
    ) -> pd.DataFrame:
        """
        Get all intraday data from market open to specified time.

        Args:
            stock_code: Stock ticker
            start_time: Start time (HHMMSS, default: market open)
            end_time: End time (HHMMSS, default: current time)

        Returns:
            DataFrame: Intraday OHLCV data
        """
        try:
            if end_time is None:
                end_time = now_kst().strftime("%H%M%S")

            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                self._executor,
                self._get_intraday_data_sync,
                stock_code, start_time, end_time
            )

            return df if df is not None else pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Failed to get intraday data for {stock_code}: {e}")
            return pd.DataFrame()

    # ========================================================================
    # Real-time Subscription Methods
    # ========================================================================

    def subscribe(self, stock_code: str, callback: Callable[[str, OHLCV], None]) -> bool:
        """
        Subscribe to real-time data updates for a stock.

        Args:
            stock_code: Stock ticker (6 digits)
            callback: Callback function(stock_code, ohlcv_data)

        Returns:
            bool: True if subscription successful
        """
        return self._subscription_manager.subscribe(stock_code, callback)

    def unsubscribe(self, stock_code: str, callback: Callable = None) -> bool:
        """
        Unsubscribe from real-time data updates.

        Args:
            stock_code: Stock ticker (6 digits)
            callback: Specific callback to remove (None = remove all)

        Returns:
            bool: True if unsubscription successful
        """
        return self._subscription_manager.unsubscribe(stock_code, callback)

    def _notify_subscribers(self, stock_code: str, ohlcv: OHLCV) -> None:
        """Notify all subscribers for a stock."""
        self._subscription_manager.notify(stock_code, ohlcv)

    def get_subscribed_stocks(self) -> List[str]:
        """Get list of subscribed stock codes."""
        return self._subscription_manager.get_subscribed_stocks()

    # ========================================================================
    # Synchronous Internal Methods
    # ========================================================================

    def _get_minute_data_sync(
        self,
        stock_code: str,
        date: str,
        end_time: str,
        minutes: int
    ) -> Optional[pd.DataFrame]:
        """Get minute data synchronously (internal)."""
        try:
            from api.kis_chart_api import get_stock_data_with_fallback

            result = get_stock_data_with_fallback(
                stock_code=stock_code,
                input_date=date,
                input_hour=end_time,
                past_data_yn="Y"
            )

            if result is None:
                self.logger.warning(f"No minute data for {stock_code}")
                return None

            summary_df, chart_df = result

            if chart_df.empty:
                return None

            # Standardize column names
            df = DataStandardizer.standardize_minute_data(chart_df)

            # Limit to requested minutes
            if len(df) > minutes:
                df = df.tail(minutes)

            return df.reset_index(drop=True)

        except ImportError:
            self.logger.error("KIS chart API not available")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get minute data for {stock_code}: {e}")
            return None

    def _get_daily_data_sync(self, stock_code: str, days: int) -> Optional[pd.DataFrame]:
        """Get daily data synchronously (internal)."""
        try:
            from api.kis_market_api import get_inquire_daily_itemchartprice_extended

            # Calculate start date (extra days for holidays)
            end_date = now_kst().strftime("%Y%m%d")
            start_date = (now_kst() - timedelta(days=days * 2)).strftime("%Y%m%d")

            df = get_inquire_daily_itemchartprice_extended(
                itm_no=stock_code,
                inqr_strt_dt=start_date,
                inqr_end_dt=end_date,
                period_code="D",
                max_count=days
            )

            if df is None or df.empty:
                self.logger.warning(f"No daily data for {stock_code}")
                return None

            # Standardize column names for daily data
            df = DataStandardizer.standardize_daily_data(df)

            # Limit to requested days
            if len(df) > days:
                df = df.tail(days)

            return df.reset_index(drop=True)

        except ImportError:
            self.logger.error("KIS market API not available")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get daily data for {stock_code}: {e}")
            return None

    def _get_current_price_sync(self, stock_code: str) -> Optional[float]:
        """Get current price synchronously (internal)."""
        try:
            from api.kis_market_api import get_inquire_price

            df = get_inquire_price(itm_no=stock_code)

            if df is None or df.empty:
                return None

            # Extract current price
            price_str = df.iloc[0].get('stck_prpr', '0')
            try:
                price = float(str(price_str).replace(',', ''))
                return price if price > 0 else None
            except (ValueError, TypeError):
                return None

        except ImportError:
            self.logger.error("KIS market API not available")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get current price for {stock_code}: {e}")
            return None

    def _get_today_ohlcv_sync(self, stock_code: str) -> Optional[OHLCV]:
        """Get today's OHLCV synchronously (internal)."""
        try:
            from api.kis_market_api import get_inquire_price

            df = get_inquire_price(itm_no=stock_code)

            if df is None or df.empty:
                return None

            row = df.iloc[0]

            def safe_float(value, default=0.0):
                if value is None or value == '':
                    return default
                try:
                    return float(str(value).replace(',', ''))
                except (ValueError, TypeError):
                    return default

            def safe_int(value, default=0):
                if value is None or value == '':
                    return default
                try:
                    return int(float(str(value).replace(',', '')))
                except (ValueError, TypeError):
                    return default

            return OHLCV(
                datetime=now_kst(),
                open=safe_float(row.get('stck_oprc', 0)),      # Today's open
                high=safe_float(row.get('stck_hgpr', 0)),      # Today's high
                low=safe_float(row.get('stck_lwpr', 0)),       # Today's low
                close=safe_float(row.get('stck_prpr', 0)),     # Current price
                volume=safe_int(row.get('acml_vol', 0))        # Accumulated volume
            )

        except ImportError:
            self.logger.error("KIS market API not available")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get today OHLCV for {stock_code}: {e}")
            return None

    def _get_intraday_data_sync(
        self,
        stock_code: str,
        start_time: str,
        end_time: str
    ) -> Optional[pd.DataFrame]:
        """Get intraday data synchronously (internal)."""
        try:
            from api.kis_chart_api import get_full_trading_day_data

            df = get_full_trading_day_data(
                stock_code=stock_code,
                selected_time=end_time
            )

            if df is None or df.empty:
                return None

            df = DataStandardizer.standardize_minute_data(df)

            # Filter by start_time if provided
            if start_time and 'time' in df.columns:
                df = df[df['time'].astype(str).str.zfill(6) >= start_time]

            return df

        except ImportError:
            self.logger.error("KIS chart API not available")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get intraday data for {stock_code}: {e}")
            return None

    # ========================================================================
    # Cache Management
    # ========================================================================

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self.logger.info("Data cache cleared")

    def set_cache_ttl(self, ttl: int) -> None:
        """Set default cache TTL in seconds."""
        self._cache.default_ttl = ttl
        self.logger.info(f"Cache TTL set to {ttl} seconds")

    # ========================================================================
    # Cleanup
    # ========================================================================

    def shutdown(self) -> None:
        """Clean up resources."""
        try:
            self._executor.shutdown(wait=False)
            self.clear_cache()
            self._subscription_manager.clear_all()
            self.logger.info("DataProvider shutdown complete")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")

    def __del__(self):
        """Destructor."""
        try:
            if hasattr(self, '_executor'):
                self._executor.shutdown(wait=False)
        except Exception:
            pass
