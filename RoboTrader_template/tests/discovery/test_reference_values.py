import numpy as np
import pandas as pd
import pytest
from scripts.discovery.reference_values import compute_reference

def _df():
    high = [10,11,12,11,10, 13,12,11,12,13]
    low  = [ 9, 9,10, 9, 8, 10,10, 9,10,11]
    close= [ 9,10,11,10, 9, 12,11,10,11,12]
    return pd.DataFrame({
        "datetime": pd.date_range("2023-01-01", periods=10, freq="D").astype(str),
        "open": close, "high": high, "low": low, "close": close,
        "volume": [1000]*10})

def test_box_uses_only_past_bars():
    df = _df()
    ref = compute_reference(df, 4, "box", n=5)   # high[0:5]=12, low[0:5]=8
    assert ref["box_low"] == 8.0
    assert ref["box_height"] == 4.0

def test_box_no_lookahead_changes_with_i():
    df = _df()
    ref = compute_reference(df, 9, "box", n=5)   # high[5:10]=13, low[5:10]=9
    assert ref["box_low"] == 9.0
    assert ref["box_height"] == 4.0

def test_atr_positive_and_pit():
    df = _df()
    ref = compute_reference(df, 9, "atr", n=5)
    assert ref["atr"] > 0

def test_bollinger_width_positive():
    df = _df()
    ref = compute_reference(df, 9, "bollinger", n=5, bb_k=2.0)
    assert ref["bb_width"] > 0

def test_insufficient_warmup_returns_none():
    df = _df()
    assert compute_reference(df, 2, "box", n=5) is None  # i+1 < n
