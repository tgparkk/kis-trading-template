import json

import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.shape_events import (
    LOOKBACK_BARS,
    W_COLS,
    build_event_row,
    compute_separation,
    compute_stats,
    find_first_event_idx,
    zscore_rows,
)


def _bars(closes, highs=None, lows=None):
    n = len(closes)
    highs = highs if highs is not None else closes
    lows = lows if lows is not None else closes
    return pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="3min"),
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1] * n,
        "amount": [1] * n,
        "bar_count": [3] * n,
    })


# ---------------------------------------------------------------------------
# zscore_rows
# ---------------------------------------------------------------------------

def test_zscore_rows_mean_zero_sd_one_per_row():
    rng = np.random.default_rng(0)
    matrix = rng.normal(size=(50, LOOKBACK_BARS))
    z = zscore_rows(matrix)
    assert z.shape == matrix.shape
    np.testing.assert_allclose(z.mean(axis=1), 0.0, atol=1e-9)
    np.testing.assert_allclose(z.std(axis=1), 1.0, atol=1e-9)


def test_zscore_rows_flat_row_is_all_zeros_no_nan():
    matrix = np.array([
        [5.0] * LOOKBACK_BARS,
        [1.0, 2.0, 3.0] + [4.0] * (LOOKBACK_BARS - 3),
    ])
    z = zscore_rows(matrix)
    assert not np.isnan(z).any()
    np.testing.assert_allclose(z[0], np.zeros(LOOKBACK_BARS))
    # non-flat row must NOT collapse to zero.
    assert not np.allclose(z[1], np.zeros(LOOKBACK_BARS))


# ---------------------------------------------------------------------------
# find_first_event_idx: one event per stock-day
# ---------------------------------------------------------------------------

def test_one_event_per_stock_day_only_first_qualifying_bar_returned():
    # Bars 0-19 flat at 100 (establishes prior_high=100 for the 20-bar
    # rolling window). Bars 20, 21, 22 each independently qualify as a
    # >=6% drop off that same prior_high (window still dominated by the
    # flat-100 bars). Only the FIRST (idx=20) must be picked.
    n = 25
    closes = [100.0] * 20 + [90.0, 80.0, 70.0] + [70.0] * (n - 23)
    bars = _bars(closes)

    idx = find_first_event_idx(bars)
    assert idx == 20


def test_idx_below_lookback_bars_is_skipped_entire_stock_day_dropped():
    # A qualifying drop happens at idx=5 (only 5 bars of history -> partial
    # lookback, lookback_bars_used=5 != 20) -> must be excluded. Price then
    # recovers back to 100 and stays flat, so no idx>=20 bar ever qualifies
    # either -> the whole stock-day yields no event (None).
    n = 25
    closes = [100.0] * 5 + [90.0] + [100.0] * (n - 6)
    bars = _bars(closes)

    idx = find_first_event_idx(bars)
    assert idx is None


def test_no_forward_bar_left_is_excluded():
    # Bars 0-19 flat at 100; bar 20 (the LAST bar, n=21) drops 10% but has
    # zero forward bars left (idx == n-1) -> must not qualify.
    closes = [100.0] * 20 + [90.0]
    bars = _bars(closes)

    idx = find_first_event_idx(bars)
    assert idx is None


# ---------------------------------------------------------------------------
# build_event_row / pre_vol: hand-computed known series
# ---------------------------------------------------------------------------

def test_pre_vol_matches_hand_computed_value():
    # 20 log-returns alternating +0.05 / -0.05 (mean=0) -> population std =
    # 0.05 exactly -> pre_vol = 5.0 (percent). Build the 21 closes (idx-20..idx)
    # that produce exactly these returns, then wrap them into a full bars
    # frame long enough to also qualify as an event (so build_event_row's
    # window slicing is exercised end-to-end, not just the formula).
    returns = np.array([0.05, -0.05] * 10)
    log_prices = np.log(100.0) + np.concatenate([[0.0], np.cumsum(returns)])
    window_closes = np.exp(log_prices)  # 21 values: w0..w19 + entry_close

    # Prepend 4 more flat bars so min_periods=5 lookback logic has enough
    # history before idx=20 is even reachable is irrelevant here -- we only
    # call build_event_row directly with a hand-picked idx, bypassing
    # find_first_event_idx. Need >= idx+2 bars total for a valid frame and
    # at least one bar after idx.
    closes = list(window_closes) + [float(window_closes[-1])]  # 22 bars total
    bars = _bars(closes)
    idx = LOOKBACK_BARS  # 20: the last of the 21 window_closes values

    row = build_event_row(bars, idx, trade_date="20260601", stock_code="000001")

    assert row["pre_vol"] == pytest.approx(5.0, abs=1e-6)
    assert row["entry_close"] == pytest.approx(float(window_closes[-1]))
    for i in range(LOOKBACK_BARS):
        assert row[f"w{i}"] == pytest.approx(float(window_closes[i]))


def test_build_event_row_outcome_is_one_of_known_labels():
    closes = [100.0] * LOOKBACK_BARS + [90.0, 90.0]
    bars = _bars(closes)
    row = build_event_row(bars, LOOKBACK_BARS, trade_date="20250601",
                          stock_code="000001")
    assert row["outcome"] in {"up", "down", "ambiguous", "none"}
    assert row["window"] == "W1"


# ---------------------------------------------------------------------------
# compute_separation: hand-built two-group fixture
# ---------------------------------------------------------------------------

def test_separation_gap_last_bar_in_sd_hand_computed():
    # 2 "up" events with z-vector = [0]*19 + [1]; 2 "down" events with
    # z-vector = [0]*19 + [-1]. By hand:
    #   median_up  = [0]*19 + [1]
    #   median_down= [0]*19 + [-1]
    #   median_abs_gap = mean(|0-0|*19 + |1-(-1)|) / 20 = 2/20 = 0.1
    #   pooled_sd_last_bar = population std of [1,1,-1,-1] = 1.0
    #   gap_last_bar_in_sd = |1-(-1)| / 1.0 = 2.0
    up_row = np.array([0.0] * 19 + [1.0])
    down_row = np.array([0.0] * 19 + [-1.0])
    z = np.array([up_row, up_row, down_row, down_row])
    outcomes = np.array(["up", "up", "down", "down"])

    sep = compute_separation(z, outcomes)

    assert sep["median_abs_gap"] == pytest.approx(0.1)
    assert sep["pooled_sd_last_bar"] == pytest.approx(1.0)
    assert sep["gap_last_bar_in_sd"] == pytest.approx(2.0)


def test_separation_is_nan_when_one_group_missing():
    z = np.zeros((3, LOOKBACK_BARS))
    outcomes = np.array(["up", "up", "none"])
    sep = compute_separation(z, outcomes)
    assert np.isnan(sep["median_abs_gap"])
    assert np.isnan(sep["gap_last_bar_in_sd"])


# ---------------------------------------------------------------------------
# compute_stats: end-to-end smoke on a fabricated events table (no DB)
# ---------------------------------------------------------------------------

def _fake_events(n=48, seed=3):
    rng = np.random.default_rng(seed)
    outcomes = rng.choice(["up", "down", "ambiguous", "none"], n,
                          p=[0.35, 0.35, 0.1, 0.2])
    data = {"trade_date": [f"2026060{1 + (i % 5)}" for i in range(n)],
           "stock_code": [f"{i % 10:06d}" for i in range(n)],
           "outcome": outcomes}
    for col in W_COLS:
        data[col] = rng.normal(100, 2, n)
    data["entry_close"] = rng.normal(100, 2, n)
    data["pre_vol"] = rng.uniform(0.5, 3.0, n)
    data["close_pos_in_day"] = rng.uniform(0, 1, n)
    data["lower_wick_ratio"] = rng.uniform(0, 1, n)
    data["window"] = ["W1"] * n
    return pd.DataFrame(data)


def test_compute_stats_smoke_end_to_end_and_json_serializable():
    events = _fake_events()
    stats = compute_stats(events, cluster_k=8, seed=42)

    assert stats["n_total"] == len(events)
    assert stats["n_dates"] == events["trade_date"].nunique()
    assert set(stats["counts"].keys()) == {"up", "down", "ambiguous", "none"}
    assert sum(stats["counts"].values()) == len(events)
    assert stats["bar_index"] == list(range(LOOKBACK_BARS))
    assert stats["cluster_k"] == 8
    assert len(stats["clusters"]) == 8
    assert sum(c["n"] for c in stats["clusters"]) == len(events)

    # must round-trip through json without error (ensure_ascii=False path).
    encoded = json.dumps(stats, ensure_ascii=False)
    assert json.loads(encoded)["n_total"] == len(events)
