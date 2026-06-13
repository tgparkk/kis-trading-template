"""매도 타이밍 룰. rule(intraday, entry_price, params) -> IntradayExit|None.

각 룰은 당일 분봉에서 가장 먼저 트리거되는 봉의 청산을 반환(없으면 None).
PIT: 봉 t 판정은 t까지의 정보만 사용.
"""
from __future__ import annotations

from collections import namedtuple
from typing import Optional

import pandas as pd

from scripts.feature_edge.timing.intraday_features import vwap

IntradayExit = namedtuple("IntradayExit", ["price", "bar_idx", "reason"])


def vwap_break_exit(intraday: pd.DataFrame, entry_price: float, params: dict) -> Optional[IntradayExit]:
    w = vwap(intraday)
    for i in range(len(intraday)):
        if float(intraday["close"].iloc[i]) < float(w.iloc[i]):
            return IntradayExit(price=float(intraday["close"].iloc[i]), bar_idx=i, reason="vwap_break")
    return None


def intraday_trail(intraday: pd.DataFrame, entry_price: float, params: dict) -> Optional[IntradayExit]:
    k = params.get("trail_pct", 0.03)
    run_high = float("-inf")
    for i in range(len(intraday)):
        run_high = max(run_high, float(intraday["high"].iloc[i]))
        if float(intraday["low"].iloc[i]) <= run_high * (1 - k):
            return IntradayExit(price=float(run_high * (1 - k)), bar_idx=i, reason="intraday_trail")
    return None


def time_exit(intraday: pd.DataFrame, entry_price: float, params: dict) -> Optional[IntradayExit]:
    cutoff = params.get("time_exit", "1430")
    for i in range(len(intraday)):
        if str(intraday["time"].iloc[i]) >= cutoff:
            return IntradayExit(price=float(intraday["close"].iloc[i]), bar_idx=i, reason="time_exit")
    return None


def intraday_momentum_loss(intraday: pd.DataFrame, entry_price: float, params: dict) -> Optional[IntradayExit]:
    n = params.get("mom_min", 30)
    c = intraday["close"].astype(float).reset_index(drop=True)
    for i in range(n, len(c)):
        if c.iloc[i] < c.iloc[i - n]:
            return IntradayExit(price=float(c.iloc[i]), bar_idx=i, reason="mom_loss")
    return None
