import numpy as np
import pandas as pd

from backtest.concept_axes.dtflow_shadow import candidates as C


def _df(closes, highs=None, vols=None, opens=None):
    n = len(closes)
    return pd.DataFrame({"date": pd.date_range("2026-08-01", periods=n), "open": opens or [c * 0.99 for c in closes],
                         "high": highs or closes, "low": closes, "close": closes, "volume": vols or [1000.0] * n})


def test_sql_keeps_adj_factor_on_one_line():
    for sql in (C.UNIVERSE_SQL, C.DAILY_SQL):
        assert any("volume * COALESCE(adj_factor, 1)" in line for line in sql.splitlines())


def test_base_filter_live_rules():
    rows = [("1", 4.9e11, 2e9), ("2", 5e11, 2e9), ("3", 0.0, 2e9), ("4", 1e11, 9.9e8)]
    assert [r[0] for r in C.base_filter(rows)] == ["1"]


def test_match_breakout_volume_bullish():
    closes = [100.0] * 30 + [110.0]
    vols = [1000.0] * 30 + [2500.0]
    s = C.match(_df(closes, vols=vols))
    assert s is not None and abs(s - 2.5) < 1e-12


def test_match_rejects_short_window_no_volume_or_bearish():
    assert C.match(_df([100.0] * 16)) is None
    assert C.match(_df([100.0] * 30 + [110.0], vols=[1000.0] * 30 + [1500.0])) is None
    closes = [100.0] * 30 + [110.0]
    assert C.match(_df(closes, vols=[1000.0] * 30 + [2500.0], opens=[99.0] * 30 + [111.0])) is None


def test_impossible_drop():
    assert C.impossible(_df([100.0, 60.0, 61.0]))
    assert not C.impossible(_df([100.0, 70.0, 71.0]))


def test_rank_stable_desc():
    r = C.rank([("a", 2.0), ("b", 3.0), ("c", 2.0)])
    assert [(x.stock_code, x.rank) for x in r] == [("b", 1), ("a", 2), ("c", 3)]


def test_compare_exact_and_mismatch():
    mine = C.rank([("a", 3.0), ("b", 2.0)])
    assert C.compare(mine, [("a", 1, 3.0), ("b", 2, 2.0)])["match"]
    m = C.compare(mine, [("a", 1, 3.0)])
    assert not m["match"] and m["only_mine"] == ["b"]
    assert not C.compare(mine, [("a", 1, 3.0), ("b", 2, 2.1)])["match"]
