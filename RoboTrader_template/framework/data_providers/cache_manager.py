"""
Cache Manager Module
====================

Provides thread-safe cache management for market data.

Features:
- TTL (Time-To-Live) based expiration
- Thread-safe access with locks
- Configurable default TTL
"""

import threading
from typing import Any, Optional, Dict, Tuple
from datetime import datetime

from ..utils import now_kst


class CacheManager:
    """
    Thread-safe cache manager with TTL support.

    Stores values with timestamps and automatically expires
    entries based on configurable TTL.
    """

    def __init__(self, default_ttl: int = 60):
        """
        Initialize cache manager.

        Args:
            default_ttl: Default time-to-live in seconds (default: 60)
        """
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    @property
    def default_ttl(self) -> int:
        """Get default TTL in seconds."""
        return self._default_ttl

    @default_ttl.setter
    def default_ttl(self, value: int) -> None:
        """Set default TTL in seconds."""
        self._default_ttl = value

    def get(self, key: str, ttl_override: Optional[int] = None) -> Optional[Any]:
        """
        Get value from cache if not expired.

        Args:
            key: Cache key
            ttl_override: Override default TTL for this check

        Returns:
            Cached value if valid, None if expired or not found
        """
        with self._lock:
            if key not in self._cache:
                return None

            value, timestamp = self._cache[key]
            ttl = ttl_override if ttl_override is not None else self._default_ttl

            if (now_kst() - timestamp).total_seconds() > ttl:
                del self._cache[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL for this entry (not currently used for storage,
                 but could be extended for per-entry TTL)
        """
        with self._lock:
            self._cache[key] = (value, now_kst())

    def delete(self, key: str) -> bool:
        """
        Delete a key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()

    def keys(self) -> list:
        """Get list of cache keys."""
        with self._lock:
            return list(self._cache.keys())

    def size(self) -> int:
        """Get number of entries in cache."""
        with self._lock:
            return len(self._cache)

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from cache.

        Returns:
            Number of entries removed
        """
        removed = 0
        current_time = now_kst()

        with self._lock:
            expired_keys = []
            for key, (value, timestamp) in self._cache.items():
                if (current_time - timestamp).total_seconds() > self._default_ttl:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]
                removed += 1

        return removed
