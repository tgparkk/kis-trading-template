"""
Subscription Manager Module
===========================

Provides thread-safe subscription management for real-time data.

Features:
- Multiple callbacks per stock
- Thread-safe subscription/unsubscription
- Callback notification with error handling
"""

import threading
from typing import Callable, List, Dict, Any

from ..utils import setup_logger
from .models import OHLCV


class SubscriptionManager:
    """
    Thread-safe subscription manager for real-time data.

    Manages callbacks for stock code subscriptions and provides
    safe notification mechanism.
    """

    def __init__(self):
        """Initialize subscription manager."""
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self.logger = setup_logger(__name__)

    def subscribe(
        self,
        stock_code: str,
        callback: Callable[[str, OHLCV], None]
    ) -> bool:
        """
        Subscribe to real-time data updates for a stock.

        Args:
            stock_code: Stock ticker (6 digits)
            callback: Callback function(stock_code, ohlcv_data)

        Returns:
            bool: True if subscription successful, False if already subscribed
        """
        try:
            with self._lock:
                if stock_code not in self._subscriptions:
                    self._subscriptions[stock_code] = []

                if callback not in self._subscriptions[stock_code]:
                    self._subscriptions[stock_code].append(callback)
                    self.logger.info(f"Subscribed to real-time data: {stock_code}")
                    return True
                else:
                    self.logger.warning(f"Callback already subscribed: {stock_code}")
                    return False

        except Exception as e:
            self.logger.error(f"Failed to subscribe {stock_code}: {e}")
            return False

    def unsubscribe(
        self,
        stock_code: str,
        callback: Callable = None
    ) -> bool:
        """
        Unsubscribe from real-time data updates.

        Args:
            stock_code: Stock ticker (6 digits)
            callback: Specific callback to remove (None = remove all)

        Returns:
            bool: True if unsubscription successful
        """
        try:
            with self._lock:
                if stock_code not in self._subscriptions:
                    return False

                if callback is None:
                    # Remove all callbacks for this stock
                    del self._subscriptions[stock_code]
                    self.logger.info(f"Unsubscribed all callbacks: {stock_code}")
                else:
                    # Remove specific callback
                    if callback in self._subscriptions[stock_code]:
                        self._subscriptions[stock_code].remove(callback)
                        if not self._subscriptions[stock_code]:
                            del self._subscriptions[stock_code]
                        self.logger.info(f"Unsubscribed callback: {stock_code}")

                return True

        except Exception as e:
            self.logger.error(f"Failed to unsubscribe {stock_code}: {e}")
            return False

    def notify(self, stock_code: str, ohlcv: OHLCV) -> None:
        """
        Notify all subscribers for a stock.

        Catches and logs exceptions from individual callbacks
        to prevent one failing callback from affecting others.

        Args:
            stock_code: Stock ticker
            ohlcv: OHLCV data to send to subscribers
        """
        with self._lock:
            if stock_code in self._subscriptions:
                for callback in self._subscriptions[stock_code]:
                    try:
                        callback(stock_code, ohlcv)
                    except Exception as e:
                        self.logger.error(f"Subscriber callback error: {e}")

    def get_subscribed_stocks(self) -> List[str]:
        """
        Get list of subscribed stock codes.

        Returns:
            List of stock codes with active subscriptions
        """
        with self._lock:
            return list(self._subscriptions.keys())

    def get_subscriber_count(self, stock_code: str) -> int:
        """
        Get number of subscribers for a stock.

        Args:
            stock_code: Stock ticker

        Returns:
            Number of callbacks registered for the stock
        """
        with self._lock:
            if stock_code in self._subscriptions:
                return len(self._subscriptions[stock_code])
            return 0

    def clear_all(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            self._subscriptions.clear()
        self.logger.info("All subscriptions cleared")
