"""
BB Mean Reversion Strategy
==========================

Bollinger Band mean reversion for sideways markets.
Targets low-volatility sectors (bank, utility, food, etc.)
Buy at BB lower band, sell at BB middle band (SMA20).

Buy conditions (all must be met):
  1. Price <= BB lower band (20-day, 2 sigma)
  2. RSI(14) < 40
  3. ADX(14) < 20 (sideways confirmation)
  4. Volume > 20-day avg * 1.2

Sell conditions (any one triggers):
  1. Price >= BB middle (SMA20) -- target exit
  2. Take profit: +5%
  3. Stop loss: -3%
  4. Max holding: 15 days
  5. ADX > 30 -- trend started, exit immediately
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from ..base import BaseStrategy, OrderInfo, Signal, SignalType
from utils.indicators import calculate_rsi
from utils.korean_time import now_kst

try:
    from config.market_hours import MarketHours
except ImportError:
    MarketHours = None


class BBReversionStrategy(BaseStrategy):
    """Bollinger Band mean reversion strategy for sideways markets."""

    name: str = "BBReversionStrategy"
    version: str = "1.0.0"
    description: str = "BB lower band buy, BB middle sell in sideways (ADX<20) markets"
    author: str = "Template"

    # ------------------------------------------------------------------
    # Static evaluation methods (single-source for live + simulation)
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_buy_conditions(
        current_price: float,
        bb_lower: float,
        bb_middle: float,
        rsi_value: float,
        adx_value: float,
        volume_ratio: float,
        rsi_oversold: float = 40.0,
        adx_max: float = 20.0,
        volume_ratio_min: float = 1.2,
    ) -> Optional[List[str]]:
        """
        Evaluate buy conditions. Returns list of reasons if all met, else None.

        Args:
            current_price: Current close price
            bb_lower: Bollinger Band lower value
            bb_middle: Bollinger Band middle (SMA) value
            rsi_value: RSI(14) value
            adx_value: ADX(14) value
            volume_ratio: current volume / 20-day avg volume
            rsi_oversold: RSI threshold (default 40)
            adx_max: ADX max for sideways (default 20)
            volume_ratio_min: Min volume ratio (default 1.2)

        Returns:
            List of reason strings if all conditions met, None otherwise.
        """
        if pd.isna(rsi_value) or pd.isna(adx_value) or pd.isna(bb_lower):
            return None

        reasons = []

        # 1. Price <= BB lower
        if current_price > bb_lower:
            return None
        reasons.append(
            f"Price {current_price:,.0f} <= BB_lower {bb_lower:,.0f}"
        )

        # 2. RSI < oversold threshold
        if rsi_value >= rsi_oversold:
            return None
        reasons.append(f"RSI({rsi_value:.1f}) < {rsi_oversold}")

        # 3. ADX < max (sideways)
        if adx_value >= adx_max:
            return None
        reasons.append(f"ADX({adx_value:.1f}) < {adx_max}")

        # 4. Volume ratio
        if volume_ratio < volume_ratio_min:
            return None
        reasons.append(f"Volume ratio {volume_ratio:.2f}x >= {volume_ratio_min}x")

        return reasons

    @staticmethod
    def evaluate_sell_conditions(
        current_price: float,
        entry_price: float,
        hold_days: int,
        bb_middle: float,
        adx_value: float,
        take_profit_pct: float = 0.05,
        stop_loss_pct: float = 0.03,
        max_holding_days: int = 15,
        adx_exit: float = 30.0,
    ) -> Optional[List[str]]:
        """
        Evaluate sell conditions. Returns list of reasons if any met, else None.

        Args:
            current_price: Current close price
            entry_price: Position entry price
            hold_days: Days held
            bb_middle: Bollinger Band middle (SMA) value
            adx_value: Current ADX value
            take_profit_pct: Take profit percentage (default 0.05)
            stop_loss_pct: Stop loss percentage (default 0.03)
            max_holding_days: Max days to hold (default 15)
            adx_exit: ADX threshold to exit (default 30)

        Returns:
            List of reason strings if any condition met, None otherwise.
        """
        pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
        reasons = []

        # 1. BB middle reached (primary target)
        if not pd.isna(bb_middle) and current_price >= bb_middle:
            reasons.append(
                f"BB middle reached: {current_price:,.0f} >= {bb_middle:,.0f}"
            )

        # 2. Take profit
        if pnl_pct >= take_profit_pct:
            reasons.append(f"Take profit: {pnl_pct * 100:+.1f}%")

        # 3. Stop loss
        if pnl_pct <= -stop_loss_pct:
            reasons.append(f"Stop loss: {pnl_pct * 100:+.1f}%")

        # 4. Max holding days
        if hold_days >= max_holding_days:
            reasons.append(f"Max holding exceeded: {hold_days} days")

        # 5. ADX breakout (trend started)
        if not pd.isna(adx_value) and adx_value > adx_exit:
            reasons.append(f"ADX breakout: {adx_value:.1f} > {adx_exit}")

        return reasons if reasons else None

    # ------------------------------------------------------------------
    # Indicator helpers
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_bollinger_bands(
        close: pd.Series, period: int = 20, std_mult: float = 2.0
    ) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands."""
        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper = middle + std_mult * std
        lower = middle - std_mult * std
        return {"upper": upper, "middle": middle, "lower": lower}

    @staticmethod
    def calculate_adx(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> pd.Series:
        """Calculate ADX using ta library or manual fallback."""
        try:
            from ta.trend import ADXIndicator
            adx_indicator = ADXIndicator(
                high=high, low=low, close=close, window=period
            )
            return adx_indicator.adx()
        except ImportError:
            pass

        # Manual ADX calculation
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr)

        dx = (plus_di - minus_di).abs() / (plus_di + minus_di) * 100
        adx = dx.ewm(alpha=1 / period, min_periods=period).mean()
        return adx

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._bb_period = params.get("bb_period", 20)
        self._bb_std = params.get("bb_std", 2.0)
        self._rsi_period = params.get("rsi_period", 14)
        self._rsi_oversold = params.get("rsi_oversold", 40)
        self._adx_period = params.get("adx_period", 14)
        self._adx_max = params.get("adx_max", 20)
        self._adx_exit = params.get("adx_exit", 30)
        self._vol_ratio_min = params.get("volume_ratio_min", 1.2)
        self._vol_ma_period = params.get("volume_ma_period", 20)

        risk = self.config.get("risk_management", {})
        self._stop_loss_pct = risk.get("stop_loss_pct", 0.03)
        self._take_profit_pct = risk.get("take_profit_pct", 0.05)
        self._max_hold_days = risk.get("max_holding_days", 15)
        self._max_positions = risk.get("max_positions", 5)
        self._max_daily_trades = risk.get("max_daily_trades", 10)

        self._paper_trading = self.config.get("paper_trading", True)

        # State
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0

        self._is_initialized = True
        self.logger.info(
            "%s v%s initialized (BB(%d, %.1f), RSI<%d, ADX<%d, vol>=%.1fx)",
            self.name, self.version,
            self._bb_period, self._bb_std,
            self._rsi_oversold, self._adx_max, self._vol_ratio_min,
        )
        if self._paper_trading:
            self.logger.info("Paper Trading mode enabled")
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0
        self._run_screening()

    def _run_screening(self) -> None:
        """Screen sector stocks and update target_stocks."""
        try:
            from .screener import BBReversionScreener

            screening_cfg = self.config.get("screening", {})
            db_cfg = self.config.get("database", {})
            screener = BBReversionScreener(
                host=db_cfg.get("host", "172.23.208.1"),
                port=db_cfg.get("port", 5433),
                user=db_cfg.get("user", "postgres"),
                password=db_cfg.get("password", "1234"),
                dbname=db_cfg.get("dbname", "strategy_analysis"),
            )

            target_sectors = screening_cfg.get("target_sectors", [])
            stocks = screener.get_sector_stocks(target_sectors)

            if stocks:
                new_codes = [s["stock_code"] for s in stocks]
                existing = set(self.config.get("target_stocks", []))
                combined = list(existing | set(new_codes))
                self.config["target_stocks"] = combined
                self.logger.info(
                    "BB screener: %d sector stocks -> %d target stocks",
                    len(stocks), len(combined),
                )
            else:
                self.logger.info("BB screener: no sector stocks found")
        except Exception as e:
            self.logger.error("BB screening failed: %s", e)

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = "daily",
    ) -> Optional[Signal]:
        if MarketHours is not None and not MarketHours.is_market_open("KRX"):
            return None

        min_len = max(self._bb_period, self._vol_ma_period, self._rsi_period, self._adx_period) + 5
        if data is None or len(data) < min_len:
            return None

        if self.daily_trades >= self._max_daily_trades:
            return None

        close = data["close"]
        high = data["high"]
        low = data["low"]
        volume = data["volume"]
        current_price = float(close.iloc[-1])

        # Calculate indicators
        bb = self.calculate_bollinger_bands(close, self._bb_period, self._bb_std)
        bb_lower = float(bb["lower"].iloc[-1])
        bb_middle = float(bb["middle"].iloc[-1])
        adx_series = self.calculate_adx(high, low, close, self._adx_period)
        adx_value = float(adx_series.iloc[-1]) if not pd.isna(adx_series.iloc[-1]) else 50.0
        rsi_series = calculate_rsi(close, self._rsi_period)
        rsi_value = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

        vol_ma = float(volume.iloc[-self._vol_ma_period:].mean())
        current_vol = float(volume.iloc[-1])
        volume_ratio = current_vol / vol_ma if vol_ma > 0 else 0.0

        # Held position -> check sell
        if stock_code in self.positions:
            return self._check_sell(stock_code, current_price, bb_middle, adx_value)

        # Max positions check
        if len(self.positions) >= self._max_positions:
            return None

        # Buy check (daily timeframe only)
        if timeframe == "daily":
            return self._check_buy(
                stock_code, current_price,
                bb_lower, bb_middle, rsi_value, adx_value, volume_ratio,
            )

        return None

    def _check_buy(
        self,
        stock_code: str,
        current_price: float,
        bb_lower: float,
        bb_middle: float,
        rsi_value: float,
        adx_value: float,
        volume_ratio: float,
    ) -> Optional[Signal]:
        reasons = self.evaluate_buy_conditions(
            current_price=current_price,
            bb_lower=bb_lower,
            bb_middle=bb_middle,
            rsi_value=rsi_value,
            adx_value=adx_value,
            volume_ratio=volume_ratio,
            rsi_oversold=self._rsi_oversold,
            adx_max=self._adx_max,
            volume_ratio_min=self._vol_ratio_min,
        )
        if reasons is None:
            return None

        target = bb_middle  # Primary target: BB middle
        stop = current_price * (1 - self._stop_loss_pct)

        if self._paper_trading:
            self.logger.info(
                "[PAPER] BUY signal: %s @ %s | %s",
                stock_code, f"{current_price:,.0f}", " | ".join(reasons),
            )

        metadata = {
            "bb_lower": bb_lower,
            "bb_middle": bb_middle,
            "rsi": rsi_value,
            "adx": adx_value,
            "volume_ratio": volume_ratio,
        }
        if self._paper_trading:
            metadata["paper_only"] = True

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=min(90.0, 50.0 + (bb_lower - current_price) / current_price * 1000),
            target_price=target,
            stop_loss=stop,
            reasons=reasons,
            metadata=metadata,
        )

    def _check_sell(
        self,
        stock_code: str,
        current_price: float,
        bb_middle: float,
        adx_value: float,
    ) -> Optional[Signal]:
        pos = self.positions[stock_code]
        entry_price = pos["entry_price"]
        hold_days = (now_kst() - pos["entry_time"]).days

        reasons = self.evaluate_sell_conditions(
            current_price=current_price,
            entry_price=entry_price,
            hold_days=hold_days,
            bb_middle=bb_middle,
            adx_value=adx_value,
            take_profit_pct=self._take_profit_pct,
            stop_loss_pct=self._stop_loss_pct,
            max_holding_days=self._max_hold_days,
            adx_exit=self._adx_exit,
        )
        if reasons is None:
            return None

        pnl_pct = (current_price - entry_price) / entry_price * 100

        if self._paper_trading:
            self.logger.info(
                "[PAPER] SELL signal: %s @ %s (PnL %+.1f%%) | %s",
                stock_code, f"{current_price:,.0f}", pnl_pct, " | ".join(reasons),
            )

        metadata = {
            "entry_price": entry_price,
            "pnl_pct": pnl_pct,
            "hold_days": hold_days,
            "adx": adx_value,
            "bb_middle": bb_middle,
        }
        if self._paper_trading:
            metadata["paper_only"] = True

        return Signal(
            signal_type=SignalType.SELL,
            stock_code=stock_code,
            confidence=min(95.0, 60.0 + len(reasons) * 15),
            reasons=reasons,
            metadata=metadata,
        )

    def on_order_filled(self, order: OrderInfo) -> None:
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {
                "entry_price": order.price,
                "entry_time": order.filled_at,
            }
            self.logger.info(
                "BUY filled: %s @ %s x %d",
                order.stock_code, f"{order.price:,.0f}", order.quantity,
            )
        elif order.stock_code in self.positions:
            pos = self.positions.pop(order.stock_code)
            pnl_pct = (order.price - pos["entry_price"]) / pos["entry_price"] * 100
            prefix = "[PAPER] " if self._paper_trading else ""
            self.logger.info(
                "%sSELL filled: %s @ %s (PnL %+.1f%%)",
                prefix, order.stock_code, f"{order.price:,.0f}", pnl_pct,
            )

    def on_market_close(self) -> None:
        self.logger.info(
            "Market close -- trades: %d, positions: %d",
            self.daily_trades, len(self.positions),
        )
        for code, pos in self.positions.items():
            hold_days = (now_kst() - pos["entry_time"]).days
            self.logger.info(
                "  %s: entry %s, held %d days",
                code, f"{pos['entry_price']:,.0f}", hold_days,
            )
