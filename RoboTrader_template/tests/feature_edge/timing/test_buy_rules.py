import numpy as np
import pandas as pd
from scripts.feature_edge.timing.buy_rules import (
    vwap_entry, gap_skip, opening_range_breakout, pullback_to_vwap, first30_strength)


def _intra(o, h, l, c, v=None, a=None):
    n = len(c)
    v = v or [1]*n
    a = a or [o[i]*v[i] for i in range(n)]
    return pd.DataFrame({"time": [f"{900+i:04d}" for i in range(n)],
                         "open": o, "high": h, "low": l, "close": c,
                         "volume": v, "amount": a})


def test_vwap_entry_returns_first_vwap_price():
    df = _intra([10,10,10],[10,10,10],[10,10,10],[10,10,10])
    fill = vwap_entry(df, baseline_open=10.0, params={})
    assert fill is not None and np.isclose(fill.price, 10.0)


def test_gap_skip_blocks_when_gap_exceeds():
    df = _intra([11]*3,[11]*3,[11]*3,[11]*3)
    assert gap_skip(df, baseline_open=11.0, params={"prev_close": 10.0, "gap_skip_pct": 0.05}) is None
    assert gap_skip(df, baseline_open=10.2, params={"prev_close": 10.0, "gap_skip_pct": 0.05}) is not None


def test_opening_range_breakout_enters_on_break():
    df = _intra(o=[10,10,10,10,10], h=[11,12,11,13,10], l=[9]*5, c=[10]*5)
    fill = opening_range_breakout(df, baseline_open=10.0, params={"or_min": 3})
    assert fill is not None and fill.price >= 12


def test_opening_range_breakout_skips_if_no_break():
    df = _intra(o=[10]*5, h=[11,12,11,11,10], l=[9]*5, c=[10]*5)
    assert opening_range_breakout(df, baseline_open=10.0, params={"or_min": 3}) is None


def test_first30_strength_skip_when_weak():
    df = _intra(o=[10,10,10,10], h=[10]*4, l=[9]*4, c=[9,9,9,9])
    assert first30_strength(df, baseline_open=10.0, params={"or_min": 3}) is None
