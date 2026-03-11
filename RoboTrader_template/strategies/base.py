"""
Base Strategy Interface
=======================

Abstract base class that all trading strategies must inherit from.

The strategy lifecycle is:
1. __init__() - Strategy instantiation with config
2. on_init() - Initialize with broker/data/executor (called once)
3. on_market_open() - Called at market open (09:00)
4. generate_signal() - Called periodically to generate trading signals
5. on_order_filled() - Called when an order is filled
6. on_market_close() - Called at market close (15:30)

Example:
    class MyStrategy(BaseStrategy):
        name = "MyStrategy"
        version = "1.0.0"
        description = "My custom trading strategy"
        author = "Developer"

        def on_init(self, broker, data_provider, executor):
            self._broker = broker
            self._data_provider = data_provider
            self._executor = executor
            self._is_initialized = True
            return True

        def generate_signal(self, stock_code, data):
            if should_buy(data):
                return Signal(
                    signal_type=SignalType.BUY,
                    stock_code=stock_code,
                    confidence=80,
                    reasons=["Buy signal detected"]
                )
            return None
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd


# ============================================================================
# Enums
# ============================================================================

class SignalType(Enum):
    """
    Trading signal types.

    Attributes:
        STRONG_BUY: Strong buy signal (high confidence)
        BUY: Buy signal
        HOLD: Hold current position
        SELL: Sell signal
        STRONG_SELL: Strong sell signal (high confidence)
    """
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Signal:
    """
    Trading signal returned by generate_signal().

    Attributes:
        signal_type: Signal type (STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL)
        stock_code: Stock ticker code (6 digits)
        confidence: Confidence level (0-100)
        target_price: Target price for take-profit
        stop_loss: Stop-loss price
        reasons: List of reasons for the signal
        metadata: Additional strategy-specific data

    Example:
        signal = Signal(
            signal_type=SignalType.BUY,
            stock_code="005930",
            confidence=85.0,
            target_price=75000,
            stop_loss=68000,
            reasons=["Golden cross detected", "Volume breakout"]
        )
    """
    signal_type: SignalType
    stock_code: str
    confidence: float = 0.0
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate and set defaults after initialization."""
        if self.reasons is None:
            self.reasons = []
        if self.metadata is None:
            self.metadata = {}

    @property
    def is_buy(self) -> bool:
        """Check if this is a buy signal (BUY or STRONG_BUY)."""
        return self.signal_type in (SignalType.BUY, SignalType.STRONG_BUY)

    @property
    def is_sell(self) -> bool:
        """Check if this is a sell signal (SELL or STRONG_SELL)."""
        return self.signal_type in (SignalType.SELL, SignalType.STRONG_SELL)

    @property
    def is_strong(self) -> bool:
        """Check if this is a strong signal."""
        return self.signal_type in (SignalType.STRONG_BUY, SignalType.STRONG_SELL)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dict containing all signal attributes.
        """
        return {
            'signal_type': self.signal_type.value,
            'stock_code': self.stock_code,
            'confidence': self.confidence,
            'target_price': self.target_price,
            'stop_loss': self.stop_loss,
            'reasons': self.reasons,
            'metadata': self.metadata
        }


@dataclass
class OrderInfo:
    """
    Order fill information passed to on_order_filled().

    Attributes:
        order_id: Unique order identifier
        stock_code: Stock ticker code
        side: Order side ('buy' or 'sell')
        quantity: Number of shares filled
        price: Fill price
        filled_at: Fill timestamp

    Example:
        order = OrderInfo(
            order_id="ORD123456",
            stock_code="005930",
            side="buy",
            quantity=10,
            price=72000,
            filled_at=datetime.now()
        )
    """
    order_id: str
    stock_code: str
    side: str  # "buy" or "sell"
    quantity: int
    price: float
    filled_at: datetime

    @property
    def is_buy(self) -> bool:
        """Check if this is a buy order."""
        return self.side.lower() == "buy"

    @property
    def is_sell(self) -> bool:
        """Check if this is a sell order."""
        return self.side.lower() == "sell"

    @property
    def total_amount(self) -> float:
        """Calculate total order amount."""
        return self.quantity * self.price

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dict containing all order attributes.
        """
        return {
            'order_id': self.order_id,
            'stock_code': self.stock_code,
            'side': self.side,
            'quantity': self.quantity,
            'price': self.price,
            'filled_at': self.filled_at.isoformat() if self.filled_at else None
        }


# ============================================================================
# Base Strategy
# ============================================================================

class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    All trading strategies must inherit from this class and implement
    the required abstract methods.

    Class Attributes:
        name: Strategy name (default: "BaseStrategy")
        version: Strategy version (default: "1.0.0")
        description: Strategy description
        author: Strategy author

    Instance Attributes:
        config: Strategy configuration dictionary
        _broker: Broker instance for account info and positions
        _data_provider: Data provider for market data
        _executor: Order executor for placing orders
        _is_initialized: Initialization status flag

    Lifecycle:
        1. __init__(config) - Create strategy instance
        2. on_init(broker, data_provider, executor) - Initialize (once)
        3. on_market_open() - At market open
        4. generate_signal(stock_code, data) - Periodically
        5. on_order_filled(order) - When orders fill
        6. on_market_close() - At market close

    Example:
        class MyCustomStrategy(BaseStrategy):
            name = "MyCustomStrategy"
            version = "1.0.0"
            description = "Custom trading strategy"
            author = "Developer"

            def on_init(self, broker, data_provider, executor):
                self._broker = broker
                self._data_provider = data_provider
                self._executor = executor
                self._is_initialized = True
                return True

            def on_market_open(self):
                self.logger.info("Market opened, starting analysis")

            def generate_signal(self, stock_code, data):
                if self._check_buy_condition(data):
                    return Signal(
                        signal_type=SignalType.BUY,
                        stock_code=stock_code,
                        confidence=80,
                        target_price=data['close'].iloc[-1] * 1.03,
                        stop_loss=data['close'].iloc[-1] * 0.98,
                        reasons=["Buy condition detected"]
                    )
                return None

            def on_order_filled(self, order):
                if order.is_buy:
                    self.logger.info(f"Bought {order.quantity} of {order.stock_code}")

            def on_market_close(self):
                self.logger.info("Market closed")
    """

    # Strategy meta information (class-level defaults)
    name: str = "BaseStrategy"
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    holding_period: str = "intraday"

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize strategy with configuration.

        Args:
            config: Strategy configuration dictionary (from config.yaml).
                   If None, an empty dict is used.
        """
        self.config = config or {}

        # Components (set in on_init)
        self._broker = None
        self._data_provider = None
        self._executor = None

        # State
        self._is_initialized = False

        # Logger (will be set up if framework utils available)
        self.logger = None
        try:
            from framework.utils import setup_logger
            self.logger = setup_logger(f"strategy.{self.name}")
        except ImportError:
            import logging
            self.logger = logging.getLogger(f"strategy.{self.name}")

    # ========================================================================
    # Abstract Methods (MUST implement)
    # ========================================================================

    def on_init(self, broker, data_provider, executor) -> bool:
        """
        Initialize strategy with framework components.

        Called once after API connection is established.
        Use this to load historical data, initialize indicators, etc.

        Args:
            broker: Broker instance for account info and positions
            data_provider: Data provider for market data
            executor: Order executor for placing orders

        Returns:
            bool: True if initialization successful, False otherwise

        Example:
            def on_init(self, broker, data_provider, executor):
                self._broker = broker
                self._data_provider = data_provider
                self._executor = executor

                # Load historical data
                self.historical_data = data_provider.get_daily_ohlcv("005930", days=60)

                self._is_initialized = True
                return True
        """
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor
        self._is_initialized = True
        return True

    def on_market_open(self) -> None:
        """
        Called when market opens (09:00 KST).

        Use this to:
        - Load overnight data
        - Reset daily counters
        - Prepare watchlist
        - Initialize daily state

        Example:
            def on_market_open(self):
                self.daily_trades = 0
                self.watchlist = self._scan_for_candidates()
                self.logger.info("Market opened, watching %d stocks", len(self.watchlist))
        """
        pass

    @abstractmethod
    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = 'daily',
    ) -> Optional[Signal]:
        """
        Generate trading signal for a stock.

        Called periodically during market hours.
        Return None if no signal, or Signal if signal detected.

        Args:
            stock_code: Stock ticker code (6 digits, e.g., "005930")
            data: OHLCV DataFrame with columns:
                  ['datetime', 'open', 'high', 'low', 'close', 'volume']
                  Index should be datetime or the DataFrame should have
                  a 'datetime' column.
            timeframe: Data timeframe - 'daily' for buy decisions,
                      'intraday' for sell decisions. Strategies can use
                      this to adjust their logic accordingly.

        Returns:
            Signal: Trading signal object, or None if no signal

        Example:
            def generate_signal(self, stock_code, data, timeframe='daily'):
                if len(data) < 20:
                    return None

                # Simple moving average crossover
                sma_short = data['close'].rolling(5).mean()
                sma_long = data['close'].rolling(20).mean()

                if sma_short.iloc[-1] > sma_long.iloc[-1] and sma_short.iloc[-2] <= sma_long.iloc[-2]:
                    return Signal(
                        signal_type=SignalType.BUY,
                        stock_code=stock_code,
                        confidence=75,
                        reasons=["Golden cross detected"]
                    )

                return None
        """
        pass

    def on_order_filled(self, order: OrderInfo) -> None:
        """
        Called when an order is filled.

        Use this to:
        - Update position tracking
        - Record statistics
        - Adjust strategy state
        - Log trade information

        Args:
            order: Filled order information (OrderInfo object)

        Example:
            def on_order_filled(self, order):
                if order.is_buy:
                    self.positions[order.stock_code] = {
                        'quantity': order.quantity,
                        'entry_price': order.price,
                        'entry_time': order.filled_at
                    }
                    self.logger.info(f"Entered position: {order.stock_code} @ {order.price}")
                else:
                    if order.stock_code in self.positions:
                        entry_price = self.positions[order.stock_code]['entry_price']
                        profit = (order.price - entry_price) / entry_price * 100
                        self.logger.info(f"Exited position: {order.stock_code}, P&L: {profit:.2f}%")
                        del self.positions[order.stock_code]
        """
        pass

    def on_market_close(self) -> None:
        """
        Called when market closes (15:30 KST).

        Use this to:
        - Generate daily reports
        - Save statistics
        - Clean up state
        - Persist important data

        Example:
            def on_market_close(self):
                self.logger.info(f"Daily trades: {self.daily_trades}")
                self._save_daily_report()
                self._cleanup_temp_data()
        """
        pass

    # ========================================================================
    # on_tick (Phase 1: Strategy-owns-the-loop)
    # ========================================================================

    async def on_tick(self, ctx: 'TradingContext'):
        """
        Framework calls this every cycle. Default: generate_signal-based behavior.

        Override this method in your strategy to implement custom loop logic.
        The default implementation replicates the existing generate_signal() flow:
        - Iterates SELECTED stocks for buy signals (daily data)
        - Iterates POSITIONED stocks for sell signals (intraday data)

        Args:
            ctx: TradingContext providing safe access to market data,
                 orders, funds, and other framework components.
        """
        # Buy decisions
        buy_checked = 0
        buy_skipped = 0
        buy_signals = 0
        for stock in ctx.get_selected_stocks():
            buy_checked += 1
            data = await ctx.get_daily_data(stock.stock_code)
            if data is None or len(data) < 20:
                buy_skipped += 1
                if data is None:
                    self.logger.debug(f"스킵: {stock.stock_code} - 일봉 데이터 없음")
                else:
                    self.logger.debug(f"스킵: {stock.stock_code} - 일봉 {len(data)}건 < 20")
                continue
            signal = self.generate_signal(stock.stock_code, data, timeframe='daily')
            if not signal:
                self.logger.debug(f"스킵: {stock.stock_code} - generate_signal 반환 None (일봉 {len(data)}건)")
            if signal and signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                buy_signals += 1
                reasons_str = ', '.join(signal.reasons) if signal.reasons else '-'
                self.logger.info(
                    f"[on_tick] 매수신호: {stock.stock_code}({signal.signal_type.name}, "
                    f"신뢰도 {signal.confidence}, 이유: {reasons_str})"
                )
                await ctx.buy(stock.stock_code, signal=signal)

        # Sell decisions
        sell_checked = 0
        sell_signals = 0
        for stock in ctx.get_positions():
            sell_checked += 1
            data = await ctx.get_intraday_data(stock.stock_code)
            if data is not None and len(data) > 0:
                signal = self.generate_signal(stock.stock_code, data, timeframe='intraday')
                if signal and signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
                    sell_signals += 1
                    reasons_str = ', '.join(signal.reasons) if signal.reasons else '-'
                    self.logger.info(
                        f"[on_tick] 매도신호: {stock.stock_code}({signal.signal_type.name}, "
                        f"신뢰도 {signal.confidence}, 이유: {reasons_str})"
                    )
                    await ctx.sell(
                        stock.stock_code,
                        reason=', '.join(signal.reasons) if signal.reasons else self.name
                    )

        self.logger.info(
            f"[on_tick] 매수검토 {buy_checked}종목(스킵 {buy_skipped}), 신호 {buy_signals}건 | "
            f"매도검토 {sell_checked}종목, 신호 {sell_signals}건"
        )

    # ========================================================================
    # EOD Liquidation
    # ========================================================================

    def should_liquidate_eod(self, stock_code: str) -> bool:
        """
        Determine whether a position should be liquidated at end of day.

        Override this to implement custom EOD liquidation logic.
        Default: liquidate if holding_period is "intraday".

        Args:
            stock_code: Stock ticker code (6 digits)

        Returns:
            bool: True if the position should be liquidated at EOD.
        """
        return self.holding_period == "intraday"

    # ========================================================================
    # Configuration Methods
    # ========================================================================

    def get_config(self) -> Dict[str, Any]:
        """
        Get strategy configuration.

        Returns:
            Dict: Copy of strategy configuration dictionary.
        """
        return self.config.copy() if self.config else {}

    def get_target_stocks(self) -> List[str]:
        """
        Get target stock list from configuration.

        Override this method if you need custom stock selection logic.

        Returns:
            List[str]: List of stock codes to monitor.

        Example:
            def get_target_stocks(self):
                # Custom implementation
                base_stocks = super().get_target_stocks()
                if self.use_dynamic_selection:
                    return self._scan_market_for_stocks()
                return base_stocks
        """
        return self.config.get('target_stocks', [])

    def validate_config(self) -> bool:
        """
        Validate strategy configuration.

        Override this method to add custom validation logic.

        Returns:
            bool: True if configuration is valid, False otherwise.

        Example:
            def validate_config(self):
                if not super().validate_config():
                    return False

                if 'stop_loss_pct' not in self.config:
                    self.logger.error("Missing required config: stop_loss_pct")
                    return False

                if self.config['stop_loss_pct'] < 0 or self.config['stop_loss_pct'] > 1:
                    self.logger.error("stop_loss_pct must be between 0 and 1")
                    return False

                return True
        """
        return True

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def get_param(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration parameter.

        Supports nested keys with dot notation (e.g., 'risk.stop_loss').

        Args:
            key: Parameter key (supports dot notation for nested access)
            default: Default value if not found

        Returns:
            Parameter value or default

        Example:
            stop_loss = self.get_param('risk.stop_loss', 0.02)
            max_positions = self.get_param('max_positions', 5)
        """
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    @property
    def is_initialized(self) -> bool:
        """Check if strategy is initialized."""
        return self._is_initialized

    def __repr__(self) -> str:
        """String representation."""
        return f"<{self.__class__.__name__}(name='{self.name}', version='{self.version}')>"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.name} v{self.version}"
