"""시장(지수) 파생피처. breadth/dispersion 은 패널 어셈블러에서 횡단면 계산."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_index_features(idx: pd.DataFrame) -> pd.DataFrame:
    c = idx["close"].astype(float)
    out = pd.DataFrame(index=idx.index)
    out["date"] = pd.to_datetime(idx["date"]).values
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    out["mkt_above_ma20"] = (c > ma20).astype(int)
    out["mkt_above_ma60"] = (c > ma60).astype(int)
    out["mkt_ret20"] = c / c.shift(20) - 1.0
    rv = c.pct_change().rolling(20).std()
    out["mkt_vol_pct"] = rv.rolling(252, min_periods=60).apply(
        lambda w: (w.iloc[-1] >= w).mean(), raw=False)
    return out
