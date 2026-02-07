"""
Data Models Module
==================

Contains data classes for market data representation.

Classes:
- OHLCV: Open, High, Low, Close, Volume data point
- PriceQuote: Current price quote with change information
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime

from ..utils import now_kst


@dataclass
class OHLCV:
    """
    OHLCV (Open, High, Low, Close, Volume) data point.

    Attributes:
        datetime: Candle datetime
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Trading volume
    """
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    @property
    def range(self) -> float:
        """Price range (high - low)."""
        return self.high - self.low

    @property
    def body(self) -> float:
        """Candle body size (abs(close - open))."""
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        """Is bullish candle (close > open)."""
        return self.close > self.open

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'datetime': self.datetime,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }


@dataclass
class PriceQuote:
    """
    Current price quote.

    Attributes:
        stock_code: Stock ticker
        current_price: Current price
        change: Price change from previous close
        change_rate: Change percentage
        volume: Accumulated volume
        timestamp: Quote timestamp
    """
    stock_code: str
    current_price: float
    change: float = 0.0
    change_rate: float = 0.0
    volume: int = 0
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = now_kst()
