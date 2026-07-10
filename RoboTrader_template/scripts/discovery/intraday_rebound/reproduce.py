# scripts/discovery/intraday_rebound/reproduce.py
"""스펙 2.2절 표를 정식 파이프라인(TimeFrameConverter)으로 재현한다.

임시 SQL(floor(epoch/180))과 결과가 어긋나면 스펙의 결론부터 재검토해야 한다.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from .db import MINUTE_DB, read_sql
from .labeler import LabelParams, compute_labels
from .resample import resample_ohlcv
from .universe import load_frozen_universe

_DAYS_SQL = """
SELECT DISTINCT trade_date FROM minute_candles
WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date
"""

_BARS_SQL = """
SELECT stock_code, datetime, open, high, low, close, volume, amount
FROM minute_candles
WHERE trade_date = %s AND stock_code = ANY(%s)
ORDER BY stock_code, datetime
"""

REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()


def _filter_regular_session(df: pd.DataFrame) -> pd.DataFrame:
    t = df["datetime"].dt.time
    return df[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]


def _bucket(drop: float) -> str:
    if np.isnan(drop):
        return "na"
    if drop <= -0.04:
        return ">=4.0%"
    if drop <= -0.025:
        return "2.5-4.0%"
    if drop <= -0.015:
        return "1.5-2.5%"
    return "no_drop"


def reproduce_spec_table(start: str = "20260601", end: str = "20260630") -> pd.DataFrame:
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    params = LabelParams(timeframe_minutes=3, lookback_min=60, drop_pct=0.0,
                         forward_min=60, theta=0.03, min_lookback_min=15)

    frames = []
    for day in days:
        raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
        if raw.empty:
            continue
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        raw = _filter_regular_session(raw)

        for code, g in raw.groupby("stock_code", sort=False):
            bars = resample_ohlcv(g, params.timeframe_minutes)
            if len(bars) < params.min_lookback_bars + 2:
                continue
            lab = compute_labels(bars, params)
            lab = lab[lab["is_valid"] & (lab["forward_bars"] > 0)]
            frames.append(lab[["drop_pct_actual", "hit_up", "hit_down",
                               "is_full_lookback"]])

    all_lab = pd.concat(frames, ignore_index=True)
    all_lab["bucket"] = all_lab["drop_pct_actual"].map(_bucket)
    all_lab["segment"] = np.where(all_lab["is_full_lookback"], "full", "partial")

    agg = all_lab.groupby(["segment", "bucket"]).agg(
        n=("hit_up", "size"),
        up_mean=("hit_up", "mean"),
        dn_mean=("hit_down", "mean"),
    ).reset_index()

    # 비율은 반올림 전 원 평균으로. 반올림된 백분율끼리 나누면 오차가 생긴다.
    agg["up_over_dn"] = (agg["up_mean"] / agg["dn_mean"].replace(0, np.nan)).round(3)
    agg["pct_up"] = (agg["up_mean"] * 100).round(2)
    agg["pct_dn"] = (agg["dn_mean"] * 100).round(2)

    cols = ["segment", "bucket", "n", "pct_up", "pct_dn", "up_over_dn"]
    return agg[cols].sort_values(["segment", "bucket"]).reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260601")
    ap.add_argument("--end", default="20260630")
    args = ap.parse_args()
    print(reproduce_spec_table(args.start, args.end).to_string(index=False))
