"""외국인 수급 피처 (foreign_flow). PIT: shift(1) 로 T-1 참조."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_flow_features(daily: pd.DataFrame, flow: pd.DataFrame) -> pd.DataFrame:
    d = daily[["date", "volume"]].copy()
    d["date"] = pd.to_datetime(d["date"])
    f = flow.copy()
    if len(f):
        f["date"] = pd.to_datetime(f["date"])
        f = f[["date", "foreign_net_vol"]]
    else:
        f = pd.DataFrame({"date": pd.to_datetime([]), "foreign_net_vol": []})
    m = d.merge(f, on="date", how="left")
    net = m["foreign_net_vol"].fillna(0.0).astype(float)
    net_lag = net.shift(1).fillna(0.0)

    avg_vol = m["volume"].astype(float).shift(1).rolling(20).mean()
    out = pd.DataFrame(index=daily.index)
    out["date"] = m["date"].values
    out["flow_norm"] = (net_lag / avg_vol.replace(0, np.nan)).fillna(0.0)
    out["flow_cum5"] = net_lag.rolling(5).sum().fillna(0.0)
    out["flow_cum20"] = net_lag.rolling(20).sum().fillna(0.0)

    sign = (net_lag > 0).astype(int)
    grp = (sign == 0).cumsum()
    out["flow_streak"] = sign.groupby(grp).cumsum().astype(float).values
    return out
