"""
Market Data Legacy Module
=========================

Provides synchronous interface for backward compatibility.

For new code, use DataProvider with async methods.
This class is maintained for legacy code that requires
synchronous API access.
"""

from typing import Optional, Any, Dict
from datetime import timedelta
import pandas as pd

from ..utils import setup_logger, now_kst
from .models import PriceQuote
from .data_standardizer import DataStandardizer


class MarketData:
    """
    Market data provider (legacy compatibility).

    Provides synchronous interface for backward compatibility.
    For new code, use DataProvider with async methods.
    """

    def __init__(self, broker):
        """
        Initialize market data provider.

        Args:
            broker: Broker instance for API access
        """
        self.broker = broker
        self.logger = setup_logger(__name__)
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 60

    def get_minute_data(
        self,
        stock_code: str,
        date: str = None,
        minutes: int = 30,
        end_time: str = None
    ) -> Optional[pd.DataFrame]:
        """Get minute-level OHLCV data (synchronous)."""
        try:
            if date is None:
                date = now_kst().strftime("%Y%m%d")
            if end_time is None:
                end_time = now_kst().strftime("%H%M%S")

            from api.kis_chart_api import get_stock_data_with_fallback

            result = get_stock_data_with_fallback(
                stock_code=stock_code,
                input_date=date,
                input_hour=end_time,
                past_data_yn="Y"
            )

            if result is None:
                return None

            summary_df, chart_df = result

            if chart_df.empty:
                return None

            df = DataStandardizer.standardize_minute_data(chart_df)

            if len(df) > minutes:
                df = df.tail(minutes)

            return df.reset_index(drop=True)

        except Exception as e:
            self.logger.error(f"Failed to get minute data for {stock_code}: {e}")
            return None

    def get_daily_data(self, stock_code: str, days: int = 100) -> Optional[pd.DataFrame]:
        """Get daily OHLCV data (synchronous)."""
        try:
            from api.kis_market_api import get_inquire_daily_itemchartprice_extended

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
                return None

            return DataStandardizer.standardize_daily_data(df)

        except Exception as e:
            self.logger.error(f"Failed to get daily data for {stock_code}: {e}")
            return None

    def get_current_price(self, stock_code: str) -> Optional[float]:
        """Get current price for a stock."""
        quote = self.get_quote(stock_code)
        return quote.current_price if quote else None

    def get_quote(self, stock_code: str) -> Optional[PriceQuote]:
        """Get current price quote."""
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

            return PriceQuote(
                stock_code=stock_code,
                current_price=safe_float(row.get('stck_prpr', 0)),
                change=safe_float(row.get('prdy_vrss', 0)),
                change_rate=safe_float(row.get('prdy_ctrt', 0)),
                volume=safe_int(row.get('acml_vol', 0)),
                timestamp=now_kst()
            )

        except Exception as e:
            self.logger.error(f"Failed to get quote for {stock_code}: {e}")
            return None

    def get_intraday_data(
        self,
        stock_code: str,
        start_time: str = "090000",
        end_time: str = None
    ) -> Optional[pd.DataFrame]:
        """Get all intraday data from market open to specified time."""
        try:
            if end_time is None:
                end_time = now_kst().strftime("%H%M%S")

            from api.kis_chart_api import get_full_trading_day_data

            df = get_full_trading_day_data(
                stock_code=stock_code,
                selected_time=end_time
            )

            if df is None or df.empty:
                return None

            return DataStandardizer.standardize_minute_data(df)

        except Exception as e:
            self.logger.error(f"Failed to get intraday data for {stock_code}: {e}")
            return None

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return None
        value, timestamp = self._cache[key]
        if (now_kst() - timestamp).total_seconds() > self._cache_ttl:
            del self._cache[key]
            return None
        return value

    def _set_cache(self, key: str, value: Any) -> None:
        """Set value in cache."""
        self._cache[key] = (value, now_kst())

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
