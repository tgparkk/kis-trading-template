"""KRX 일봉 → 날짜별 시장 대비 초과수익(스펙 §4-1 1~2).

가격은 `replayer.loader.load_prices` 그대로 쓴다(원장과 같은 규칙 — `adj_factor` 를 가격에 곱하지 않는다).
U_D 제외 = 패딩봉(거래 없는 평탄봉) ∨ 가짜 절벽. 잠김봉(상·하한가)은 «튄 종목»일 수 있으므로 빼지 않는다.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from backtest.concept_axes.theme_rank.snapshot import norm_code


def bad_rows(px: pd.DataFrame) -> np.ndarray:
    from backtest.concept_axes.replayer import flags as FL
    fl = FL.compute_bar_flags(px)
    return np.asarray(fl["flag_padding"], bool) | np.asarray(fl["flag_cliff"], bool)


def daily_returns(px: pd.DataFrame, cal: Sequence[date], drop: Optional[np.ndarray] = None) -> pd.DataFrame:
    """열 = stock_code, date(date), r. D 와 «달력상 D−1» 종가가 모두 있는 행만(정지 뒤 첫날은 없음)."""
    df = px[["stock_code", "date", "close"]].copy()
    if drop is not None:
        df = df.loc[~np.asarray(drop, bool)]
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["stock_code"] = df["stock_code"].map(norm_code)
    df = df.sort_values(["stock_code", "date"], kind="mergesort").reset_index(drop=True)
    prev_of = {cal[i]: cal[i - 1] for i in range(1, len(cal))}
    g = df.groupby("stock_code", sort=False)
    prev_date = g["date"].shift(1)
    prev_close = g["close"].shift(1).astype(float)
    want = df["date"].map(prev_of)
    ok = (prev_date == want) & (prev_close > 0) & (df["close"].astype(float) > 0)
    out = df.loc[ok, ["stock_code", "date"]].copy()
    out["r"] = df.loc[ok, "close"].astype(float) / prev_close[ok] - 1.0
    return out.reset_index(drop=True)


def excess_by_day(rets: pd.DataFrame) -> Dict[date, Dict[str, float]]:
    out: Dict[date, Dict[str, float]] = {}
    for d, g in rets.groupby("date", sort=True):
        r = g["r"].astype(float)
        out[d] = dict(zip(g["stock_code"], (r - r.mean()).tolist()))
    return out


def raw_by_day(rets: pd.DataFrame) -> Dict[date, Dict[str, float]]:
    return {d: dict(zip(g["stock_code"], g["r"].astype(float).tolist())) for d, g in rets.groupby("date", sort=True)}
