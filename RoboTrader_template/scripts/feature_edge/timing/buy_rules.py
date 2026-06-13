"""매수 타이밍 룰. rule(intraday, baseline_open, params) -> EntryFill|None (None=스킵)."""
from __future__ import annotations

from collections import namedtuple
from typing import Optional

import pandas as pd

from scripts.feature_edge.timing.intraday_features import vwap, opening_range, gap_pct

EntryFill = namedtuple("EntryFill", ["price", "bar_idx", "reason"])


def vwap_entry(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    if intraday is None or len(intraday) == 0:
        return None
    w = vwap(intraday)
    return EntryFill(price=float(w.iloc[0]), bar_idx=0, reason="vwap_entry")


def gap_skip(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    g = gap_pct(baseline_open, params.get("prev_close", baseline_open))
    if g > params.get("gap_skip_pct", 0.05):
        return None
    return EntryFill(price=float(baseline_open), bar_idx=0, reason="gap_ok")


def opening_range_breakout(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    if intraday is None or len(intraday) == 0:
        return None
    n = params.get("or_min", 30)
    hi, _ = opening_range(intraday, n)
    after = intraday.iloc[n:]
    for idx, row in after.iterrows():
        if float(row["high"]) >= hi:
            return EntryFill(price=float(hi), bar_idx=int(idx), reason="or_breakout")
    return None


def pullback_to_vwap(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    if intraday is None or len(intraday) == 0:
        return None
    w = vwap(intraday)
    for i in range(len(intraday)):
        if float(intraday["low"].iloc[i]) <= float(w.iloc[i]):
            return EntryFill(price=float(w.iloc[i]), bar_idx=i, reason="pullback_vwap")
    return None


def first30_strength(intraday: pd.DataFrame, baseline_open: float, params: dict) -> Optional[EntryFill]:
    if intraday is None or len(intraday) == 0:
        return None
    n = params.get("or_min", 30)
    head = intraday.iloc[:n]
    if float(head["close"].iloc[-1]) > float(head["open"].iloc[0]):
        return EntryFill(price=float(head["close"].iloc[-1]), bar_idx=min(n, len(intraday)) - 1,
                         reason="first30_strong")
    return None
