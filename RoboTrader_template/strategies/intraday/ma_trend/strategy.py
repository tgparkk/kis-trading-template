"""분봉 EMA 골든크로스 추세 추종 전략."""
from typing import Any, Dict, Optional

import pandas as pd

from strategies.base import Signal
from strategies.intraday._base_intraday import IntradayBaseStrategy
from utils.intraday_indicators import ema_minute


class MaTrendStrategy(IntradayBaseStrategy):
    """EMA(fast) > EMA(slow) 골든크로스 시점에 진입."""

    name = "MATrend"
    version = "1.0.0"
    description = "분봉 EMA 골든크로스 추세 추종 진입"

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        cfg = self.config if isinstance(self.config, dict) else {}
        params = cfg.get("parameters", {})
        self._fast_period = int(params.get("fast_period", 5))
        self._slow_period = int(params.get("slow_period", 20))

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = "minute",
    ) -> Optional[Signal]:
        if timeframe != "minute":
            return None
        min_bars = self._slow_period + 5
        if not isinstance(data, pd.DataFrame) or len(data) < min_bars:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        e_fast = ema_minute(data, period=self._fast_period)
        e_slow = ema_minute(data, period=self._slow_period)

        if pd.isna(e_slow.iloc[-1]) or pd.isna(e_slow.iloc[-2]):
            return None

        # 골든크로스: 직전 봉에서 fast <= slow 였다가 현재 봉에서 fast > slow
        crossed = (
            float(e_fast.iloc[-2]) <= float(e_slow.iloc[-2])
            and float(e_fast.iloc[-1]) > float(e_slow.iloc[-1])
        )
        if crossed:
            return self._make_buy_signal(
                stock_code,
                float(data["close"].iloc[-1]),
                reason=f"EMA({self._fast_period},{self._slow_period}) golden cross",
                ema_fast=round(float(e_fast.iloc[-1]), 2),
                ema_slow=round(float(e_slow.iloc[-1]), 2),
            )
        return None
