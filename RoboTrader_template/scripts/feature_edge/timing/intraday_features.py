"""분봉 파생피처 (PIT: 각 봉은 그 봉까지의 누적/창만 사용)."""
from __future__ import annotations

import pandas as pd


def vwap(intraday: pd.DataFrame) -> pd.Series:
    """누적 VWAP = Σamount / Σvolume (각 봉 t까지). amount=거래대금."""
    cum_amt = intraday["amount"].astype(float).cumsum()
    cum_vol = intraday["volume"].astype(float).cumsum().replace(0, pd.NA)
    return (cum_amt / cum_vol).astype(float)


def opening_range(intraday: pd.DataFrame, n: int):
    """첫 n봉(=n분)의 (고가, 저가)."""
    head = intraday.iloc[:n]
    return float(head["high"].astype(float).max()), float(head["low"].astype(float).min())


def gap_pct(d1_open: float, prev_close: float) -> float:
    """D+1 시가 갭 = d1_open/prev_close - 1."""
    if prev_close <= 0:
        return 0.0
    return d1_open / prev_close - 1.0
