"""종목별 일봉 파생피처 (PIT: 각 행은 자기 행까지만 사용)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_price_features(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    out = pd.DataFrame(index=df.index)
    out["date"] = df["date"].values

    out["returns_5d"] = c / c.shift(5) - 1.0
    out["returns_20d"] = c / c.shift(20) - 1.0
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    out["ma20_dist"] = c / ma20 - 1.0
    out["ma60_dist"] = c / ma60 - 1.0
    out["ma_align"] = ma20 / ma60 - 1.0
    out["mom_accel"] = out["returns_5d"] - out["returns_20d"] / 4.0
    out["high_proximity"] = c / c.rolling(60).max()

    daily_ret = c.pct_change()
    out["vol_20d"] = daily_ret.rolling(20).std()
    out["vol_trend"] = daily_ret.rolling(5).std() / daily_ret.rolling(20).std()
    out["vol_surge"] = v / v.shift(1).rolling(20).mean()
    tv = c * v
    out["amihud"] = daily_ret.abs() / tv.replace(0, np.nan)
    out["tv_trend"] = tv.rolling(5).mean() / tv.rolling(20).mean()
    return out
