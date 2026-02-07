"""
Real-time Data Collector Module
===============================

Provides real-time data collection during market hours.

Features:
- Continuous data collection during market hours
- Callback-based notification for subscribed stocks
- Integration with RealtimeCandleBuilder
"""

import threading
import asyncio
from typing import Optional, List, Dict, Any

from ..utils import setup_logger, now_kst
from .models import OHLCV
from .data_provider import DataProvider


class RealtimeDataCollector:
    """
    Real-time data collector.

    Integrates with core/data_collector.py for real-time OHLCV data collection.
    Provides:
    - Continuous data collection during market hours
    - Callback-based notification for subscribed stocks
    - Integration with RealtimeCandleBuilder

    Usage:
        collector = RealtimeDataCollector(data_provider)
        collector.add_stock("005930", "Samsung")
        await collector.start()
        ...
        collector.stop()
    """

    def __init__(
        self,
        data_provider: DataProvider,
        interval_seconds: int = 60
    ):
        """
        Initialize real-time data collector.

        Args:
            data_provider: DataProvider instance
            interval_seconds: Collection interval in seconds (default: 60)
        """
        self.data_provider = data_provider
        self.interval = interval_seconds
        self.logger = setup_logger(__name__)

        # Tracking
        self._stocks: Dict[str, Dict[str, Any]] = {}  # stock_code -> {name, last_ohlcv, ...}
        self._is_running = False
        self._lock = threading.Lock()

        # Candle builder (lazy load)
        self._candle_builder = None

        self.logger.info(f"RealtimeDataCollector initialized (interval: {interval_seconds}s)")

    def add_stock(self, stock_code: str, stock_name: str = None) -> None:
        """
        Add a stock to collection.

        Args:
            stock_code: Stock ticker (6 digits)
            stock_name: Stock name (optional)
        """
        with self._lock:
            if stock_code not in self._stocks:
                self._stocks[stock_code] = {
                    'name': stock_name or f"Stock_{stock_code}",
                    'last_ohlcv': None,
                    'last_update': None
                }
                self.logger.info(f"Added stock for collection: {stock_code}")

    def remove_stock(self, stock_code: str) -> None:
        """
        Remove a stock from collection.

        Args:
            stock_code: Stock ticker
        """
        with self._lock:
            if stock_code in self._stocks:
                del self._stocks[stock_code]
                self.logger.info(f"Removed stock from collection: {stock_code}")

    def get_stocks(self) -> List[str]:
        """Get list of stocks being collected."""
        with self._lock:
            return list(self._stocks.keys())

    def get_last_ohlcv(self, stock_code: str) -> Optional[OHLCV]:
        """Get last collected OHLCV for a stock."""
        with self._lock:
            if stock_code in self._stocks:
                return self._stocks[stock_code].get('last_ohlcv')
            return None

    async def start(self) -> None:
        """Start real-time data collection."""
        if self._is_running:
            self.logger.warning("Collector already running")
            return

        self._is_running = True
        self.logger.info("Starting real-time data collection")

        while self._is_running:
            try:
                # Check market hours
                from ..utils import is_market_open
                if not is_market_open():
                    await asyncio.sleep(60)  # Wait 1 minute during off hours
                    continue

                # Collect data for all stocks
                await self._collect_all_stocks()

                # Wait for next interval
                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Collection error: {e}")
                await asyncio.sleep(10)  # Wait 10 seconds on error

    def stop(self) -> None:
        """Stop real-time data collection."""
        self._is_running = False
        self.logger.info("Stopped real-time data collection")

    async def _collect_all_stocks(self) -> None:
        """Collect data for all tracked stocks."""
        stocks = self.get_stocks()

        tasks = [self._collect_stock_data(code) for code in stocks]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _collect_stock_data(self, stock_code: str) -> None:
        """Collect data for a single stock."""
        try:
            ohlcv = await self.data_provider.get_today_ohlcv(stock_code)

            if ohlcv is not None:
                with self._lock:
                    if stock_code in self._stocks:
                        self._stocks[stock_code]['last_ohlcv'] = ohlcv
                        self._stocks[stock_code]['last_update'] = now_kst()

                # Notify subscribers
                self.data_provider._notify_subscribers(stock_code, ohlcv)

        except Exception as e:
            self.logger.error(f"Failed to collect data for {stock_code}: {e}")

    def get_candle_builder(self):
        """Get or create RealtimeCandleBuilder instance."""
        if self._candle_builder is None:
            try:
                from core.realtime_candle_builder import get_realtime_candle_builder
                self._candle_builder = get_realtime_candle_builder()
            except ImportError:
                self.logger.warning("RealtimeCandleBuilder not available")

        return self._candle_builder

    @property
    def is_running(self) -> bool:
        """Check if collector is running."""
        return self._is_running

    def get_stock_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information for a tracked stock.

        Args:
            stock_code: Stock ticker

        Returns:
            Dictionary with stock information or None if not tracked
        """
        with self._lock:
            if stock_code in self._stocks:
                return self._stocks[stock_code].copy()
            return None

    def get_all_stock_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information for all tracked stocks.

        Returns:
            Dictionary mapping stock codes to their information
        """
        with self._lock:
            return {code: info.copy() for code, info in self._stocks.items()}
