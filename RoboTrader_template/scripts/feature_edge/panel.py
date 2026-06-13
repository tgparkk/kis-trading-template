"""피처 패널 어셈블러. 종목별 피처 + 횡단면 집계 → long DataFrame."""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from scripts.feature_edge.price_features import compute_price_features
from scripts.feature_edge.market_features import compute_index_features
from scripts.feature_edge.flow_features import compute_flow_features
from scripts.feature_edge.event_features import compute_event_flags


def assemble_panel(stock_codes: List[str],
                   daily_supplier: Dict[str, pd.DataFrame],
                   index_df: pd.DataFrame,
                   flow_supplier: Dict[str, pd.DataFrame],
                   event_supplier: Dict[str, list]) -> pd.DataFrame:
    mkt = compute_index_features(index_df)

    parts = []
    for code in stock_codes:
        df = daily_supplier.get(code)
        if df is None or len(df) < 21:
            continue
        df = df.reset_index(drop=True)

        feat = compute_price_features(df)
        flow = compute_flow_features(df, flow_supplier.get(code, pd.DataFrame(
            {"date": [], "foreign_net_vol": []})))
        ev = compute_event_flags(df, event_supplier.get(code, []))

        # All three are built from the same df with identical row count;
        # align by position (reset_index) to avoid index mismatch.
        feat = feat.reset_index(drop=True)
        flow = flow.reset_index(drop=True)
        ev = ev.reset_index(drop=True)

        flow_cols = [c for c in flow.columns if c != "date"]
        ev_cols = [c for c in ev.columns if c != "date"]

        m = pd.concat([feat, flow[flow_cols], ev[ev_cols]], axis=1)
        m["stock_code"] = code
        parts.append(m)

    if not parts:
        return pd.DataFrame()

    panel = pd.concat(parts, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    mkt["date"] = pd.to_datetime(mkt["date"])
    panel = panel.merge(mkt, on="date", how="left")

    panel["rel_strength"] = panel["returns_20d"] - panel["mkt_ret20"]

    panel["breadth"] = panel.groupby("date")["ma20_dist"].transform(
        lambda s: (s > 0).mean())
    panel["dispersion"] = panel.groupby("date")["returns_20d"].transform("std")
    panel["vol_xs_pct"] = panel.groupby("date")["vol_20d"].rank(pct=True)

    return panel
