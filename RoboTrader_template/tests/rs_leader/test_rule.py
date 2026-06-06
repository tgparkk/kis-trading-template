import numpy as np
import pandas as pd
import pytest

from scripts.rs_leader.rule import RSLeaderRule
from strategies.base import SignalType


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def test_uptrend_emits_buy():
    closes = list(np.linspace(100, 200, 80))
    rule = RSLeaderRule()
    sig = rule.generate_signal("000001", _df(closes), "daily")
    assert sig is not None and sig.signal_type == SignalType.BUY


def test_downtrend_no_signal():
    closes = list(np.linspace(200, 100, 80))
    rule = RSLeaderRule()
    assert rule.generate_signal("000001", _df(closes), "daily") is None


def test_too_short_no_signal():
    closes = list(np.linspace(100, 110, 40))
    rule = RSLeaderRule()
    assert rule.generate_signal("000001", _df(closes), "daily") is None


def test_no_lookahead_truncation_invariance():
    closes = list(np.linspace(100, 200, 80)) + list(np.linspace(200, 50, 40))
    full = _df(closes)
    rule = RSLeaderRule()
    sig_trunc = rule.generate_signal("000001", full.iloc[:80], "daily")
    sig_again = rule.generate_signal("000001", full.iloc[:80].copy(), "daily")
    assert (sig_trunc is None) == (sig_again is None)
    if sig_trunc is not None:
        assert sig_trunc.signal_type == sig_again.signal_type == SignalType.BUY
