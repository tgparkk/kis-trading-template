"""분봉 RSI 과매도 반등 전략."""
from typing import Any, Dict, Optional

import pandas as pd

from strategies.base import Signal
from strategies.intraday._base_intraday import IntradayBaseStrategy
from utils.intraday_indicators import rsi_minute


class ReversalRsiStrategy(IntradayBaseStrategy):
    """분봉 RSI(14) < 30 후 반등(close > 직전 close)에 진입."""

    name = "ReversalRSI"
    version = "1.0.0"
    description = "분봉 RSI 과매도 반등 진입"

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        cfg = self.config if isinstance(self.config, dict) else {}
        params = cfg.get("parameters", {})
        self._rsi_period = int(params.get("rsi_period", 14))
        self._rsi_threshold = float(params.get("rsi_threshold", 30.0))

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = "minute",
    ) -> Optional[Signal]:
        if timeframe != "minute":
            return None
        if not isinstance(data, pd.DataFrame) or len(data) < 20:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        rsi = rsi_minute(data, period=self._rsi_period)
        if pd.isna(rsi.iloc[-1]) or pd.isna(rsi.iloc[-2]):
            return None

        oversold = float(rsi.iloc[-2]) < self._rsi_threshold
        rebounded = float(data["close"].iloc[-1]) > float(data["close"].iloc[-2])
        if oversold and rebounded:
            return self._make_buy_signal(
                stock_code,
                float(data["close"].iloc[-1]),
                reason=f"RSI oversold rebound (rsi[-2]={rsi.iloc[-2]:.1f})",
                rsi_prev=round(float(rsi.iloc[-2]), 2),
                rsi_cur=round(float(rsi.iloc[-1]), 2),
            )
        return None
