"""강세 깃발(Bull Flag) 패턴 분봉 진입 전략."""
from typing import Any, Dict, Optional

import pandas as pd

from strategies.base import Signal
from strategies.intraday._base_intraday import IntradayBaseStrategy
from utils.intraday_indicators import flag_pattern


class BullFlagStrategy(IntradayBaseStrategy):
    """강세 깃발 패턴(폴 + 통합) 마지막 봉 신호 시 진입."""

    name = "BullFlag"
    version = "1.0.0"
    description = "강세 깃발 패턴(폴 + 통합) 분봉 진입"

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        cfg = self.config if isinstance(self.config, dict) else {}
        params = cfg.get("parameters", {})
        self._pole_min_pct = float(params.get("pole_min_pct", 0.03))
        self._consolidation_bars = int(params.get("consolidation_bars", 5))
        self._consolidation_max_pct = float(params.get("consolidation_max_pct", 0.015))

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

        signals = flag_pattern(
            data,
            pole_min_pct=self._pole_min_pct,
            consolidation_bars=self._consolidation_bars,
            consolidation_max_pct=self._consolidation_max_pct,
        )
        if bool(signals.iloc[-1]):
            return self._make_buy_signal(
                stock_code,
                float(data["close"].iloc[-1]),
                reason="Bull flag breakout",
            )
        return None
