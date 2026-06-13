"""결과 라벨러. 진입 = T+1 시가. (피처와 분리된 미래 outcome.)"""
from __future__ import annotations

import numpy as np
import pandas as pd


def label_forward_returns(df: pd.DataFrame, horizons=(5, 10, 20)) -> pd.DataFrame:
    o = df["open"].astype(float)
    c = df["close"].astype(float)
    entry = o.shift(-1)
    out = pd.DataFrame(index=df.index)
    out["date"] = df["date"].values
    for h in horizons:
        exit_c = c.shift(-(1 + h))
        out[f"fwd_{h}d"] = exit_c / entry - 1.0
    return out


def label_triple_barrier(df: pd.DataFrame, up: float, down: float,
                         horizon: int) -> pd.DataFrame:
    o = df["open"].astype(float).values
    hi = df["high"].astype(float).values
    lo = df["low"].astype(float).values
    n = len(df)
    col = f"tb_up{up}_dn{down}_h{horizon}"
    res = np.full(n, np.nan)
    for t in range(n):
        e = t + 1
        if e >= n:
            continue
        entry = o[e]
        up_px, dn_px = entry * (1 + up), entry * (1 - down)
        label = np.nan
        end = min(e + horizon, n - 1)
        for j in range(e, end + 1):
            hit_up = hi[j] >= up_px
            hit_dn = lo[j] <= dn_px
            if hit_up and hit_dn:
                label = 0
                break
            if hit_up:
                label = 1
                break
            if hit_dn:
                label = 0
                break
        res[t] = label
    out = pd.DataFrame({"date": df["date"].values, col: res})
    return out
