"""라벨/대조/MAE 계산. 입력은 반드시 한 종목-일의 봉이다.

세션 경계 누수는 입력 계약으로 막는다 (한 종목-일만 받으므로 창이 넘어갈 수 없다).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

OUT_COLUMNS = [
    "prior_high", "drop_pct_actual", "is_candidate",
    "hit_up", "hit_down", "hit_close", "mae", "forward_bars",
]


@dataclass(frozen=True)
class LabelParams:
    timeframe_minutes: int
    lookback_min: int
    drop_pct: float
    forward_min: int
    theta: float

    @property
    def lookback_bars(self) -> int:
        return max(1, self.lookback_min // self.timeframe_minutes)

    @property
    def forward_bars(self) -> int:
        return max(1, self.forward_min // self.timeframe_minutes)


def compute_labels(bars: pd.DataFrame, params: LabelParams) -> pd.DataFrame:
    n = len(bars)
    if n == 0:
        return pd.DataFrame(columns=OUT_COLUMNS)

    L = params.lookback_bars
    F = params.forward_bars
    theta = params.theta

    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)

    prior_high = (
        pd.Series(high).rolling(L, min_periods=L).max().shift(1).to_numpy()
    )

    with np.errstate(invalid="ignore", divide="ignore"):
        drop_actual = close / prior_high - 1.0
    is_candidate = drop_actual <= -params.drop_pct

    hit_up = np.zeros(n, dtype=bool)
    hit_down = np.zeros(n, dtype=bool)
    hit_close = np.full(n, np.nan)
    mae = np.full(n, np.nan)
    fwd_bars = np.zeros(n, dtype=int)

    for t in range(n):
        end = min(t + F, n - 1)
        fwd_bars[t] = end - t
        if end <= t:
            continue

        up_target = close[t] * (1.0 + theta)
        dn_target = close[t] * (1.0 - theta)

        running_min = np.inf
        hit_idx = -1
        for j in range(t + 1, end + 1):
            running_min = min(running_min, low[j])
            if high[j] >= up_target:
                hit_idx = j
                break

        if hit_idx >= 0:
            hit_up[t] = True
            mae[t] = running_min / close[t] - 1.0
        else:
            mae[t] = np.min(low[t + 1:end + 1]) / close[t] - 1.0

        hit_down[t] = bool(np.min(low[t + 1:end + 1]) <= dn_target)

        if t + F <= n - 1:
            hit_close[t] = float(close[t + F] >= up_target)

    return pd.DataFrame({
        "prior_high": prior_high,
        "drop_pct_actual": drop_actual,
        "is_candidate": is_candidate,
        "hit_up": hit_up,
        "hit_down": hit_down,
        "hit_close": hit_close,
        "mae": mae,
        "forward_bars": fwd_bars,
    })
