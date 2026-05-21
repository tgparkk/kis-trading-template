"""분봉 VWAP 이탈 후 재돌파 반전 전략."""
from typing import Any, Dict, Optional

import pandas as pd

from strategies.base import Signal
from strategies.intraday._base_intraday import IntradayBaseStrategy
from utils.intraday_indicators import vwap


class ReversalVwapStrategy(IntradayBaseStrategy):
    """close가 VWAP * (1 - deviation_pct) 이하로 이탈 후 VWAP 재돌파 시 진입."""

    name = "ReversalVWAP"
    version = "1.0.0"
    description = "분봉 VWAP 이탈 후 재돌파 반전 진입"

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        cfg = self.config if isinstance(self.config, dict) else {}
        params = cfg.get("parameters", {})
        self._deviation_pct = float(params.get("deviation_pct", 0.01))

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = "minute",
    ) -> Optional[Signal]:
        if timeframe != "minute":
            return None
        if not isinstance(data, pd.DataFrame) or len(data) < 15:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        v = vwap(data)
        if pd.isna(v.iloc[-1]):
            return None

        # 직전 5봉 중 VWAP * (1 - deviation_pct) 이하로 이탈한 봉이 있는지 확인
        last5_close = data["close"].iloc[-6:-1]
        last5_vwap = v.iloc[-6:-1]
        threshold = 1.0 - self._deviation_pct
        deviated = (last5_close.values <= last5_vwap.values * threshold).any()

        # 현재 봉이 VWAP 위로 회복
        recovered = float(data["close"].iloc[-1]) > float(v.iloc[-1])

        if deviated and recovered:
            return self._make_buy_signal(
                stock_code,
                float(data["close"].iloc[-1]),
                reason="VWAP reversion",
                vwap_cur=round(float(v.iloc[-1]), 2),
            )
        return None
