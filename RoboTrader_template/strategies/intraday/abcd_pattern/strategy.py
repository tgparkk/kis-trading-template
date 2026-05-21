"""ABCD 4점 변곡점 패턴 분봉 진입 전략."""
from typing import Any, Dict, Optional

import pandas as pd

from strategies.base import Signal
from strategies.intraday._base_intraday import IntradayBaseStrategy


class AbcdPatternStrategy(IntradayBaseStrategy):
    """ABCD 4점 변곡점 패턴 진입.

    A(저점) -> B(고점) -> C(되돌림 저점, B의 38~62% 되돌림) -> D 돌파(C 위 + B 갱신).
    단순화: rolling-window pivot high/low 검출.
    """

    name = "ABCDPattern"
    version = "1.0.0"
    description = "ABCD 4점 변곡점 패턴 분봉 진입"

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        cfg = self.config if isinstance(self.config, dict) else {}
        params = cfg.get("parameters", {})
        self._pivot_window = int(params.get("pivot_window", 5))
        self._retr_min = float(params.get("retr_min", 0.38))
        self._retr_max = float(params.get("retr_max", 0.62))
        self._min_bars = int(params.get("min_bars", 40))

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = "minute",
    ) -> Optional[Signal]:
        if timeframe != "minute":
            return None
        if not isinstance(data, pd.DataFrame) or len(data) < self._min_bars:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        win = self._pivot_window
        # center=True rolling max/min 으로 pivot 검출
        highs = data["high"].rolling(window=win, center=True).max()
        lows = data["low"].rolling(window=win, center=True).min()
        pivot_high = data["high"] == highs
        pivot_low = data["low"] == lows

        # 마지막 30봉에서 ABCD 후보 탐색
        recent = data.iloc[-30:].copy()
        ph_idx = recent.index[pivot_high.loc[recent.index].fillna(False)]
        pl_idx = recent.index[pivot_low.loc[recent.index].fillna(False)]
        if len(ph_idx) < 1 or len(pl_idx) < 2:
            return None

        # A: 첫 pivot_low, B: A 이후 첫 pivot_high, C: B 이후 첫 pivot_low
        try:
            a_idx = pl_idx[0]
            b_candidates = ph_idx[ph_idx > a_idx]
            if len(b_candidates) == 0:
                return None
            b_idx = b_candidates[0]
            c_candidates = pl_idx[pl_idx > b_idx]
            if len(c_candidates) == 0:
                return None
            c_idx = c_candidates[0]
        except Exception:
            return None

        a = float(data["low"].loc[a_idx])
        b = float(data["high"].loc[b_idx])
        c = float(data["low"].loc[c_idx])
        last_close = float(data["close"].iloc[-1])

        ab = b - a
        if ab <= 0:
            return None

        retr = (b - c) / ab
        if not (self._retr_min <= retr <= self._retr_max):
            return None

        # D 돌파: last_close > B
        if last_close > b:
            return self._make_buy_signal(
                stock_code,
                last_close,
                reason="ABCD D-breakout",
                a=a,
                b=b,
                c=c,
                retracement=round(retr, 3),
            )
        return None
