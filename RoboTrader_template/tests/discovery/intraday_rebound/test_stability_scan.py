import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.stability_scan import (
    DS,
    MS,
    NS,
    TFS,
    THETA,
    WINDOWS,
    _build_row,
    _scan_stock_day,
    classify_outcomes,
    compute_first_touch_offsets,
    summarize,
)


def _bars(close, high=None, low=None):
    n = len(close)
    high = high if high is not None else close
    low = low if low is not None else close
    return pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="3min"),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": [1] * n,
        "amount": [1] * n,
        "bar_count": [1] * n,
    })


# ---------------------------------------------------------------------------
# compute_first_touch_offsets: correct offsets, -1 when never touched,
# clipping at the last bar of the session.
# ---------------------------------------------------------------------------

def test_first_up_off_is_smallest_k_touching_up_target():
    # entry = close[0] = 100, theta=3% -> up target 103. j=1: no touch (101).
    # j=2: high touches up (103.5).
    bars = _bars(close=[100, 100, 100, 100],
                high=[100, 101, 103.5, 100],
                low=[100, 99, 98, 100])
    up_off, dn_off = compute_first_touch_offsets(bars, theta=0.03, f_max=3)
    assert up_off[0] == 2
    assert dn_off[0] == -1


def test_first_dn_off_is_smallest_k_touching_down_target():
    # symmetric to the "up" case: down target 97.
    bars = _bars(close=[100, 100, 100, 100],
                high=[100, 101, 102, 100],
                low=[100, 99, 96.5, 100])
    up_off, dn_off = compute_first_touch_offsets(bars, theta=0.03, f_max=3)
    assert dn_off[0] == 2
    assert up_off[0] == -1


def test_offset_is_minus1_when_neither_barrier_ever_touched():
    bars = _bars(close=[100, 100, 101, 99],
                high=[100, 100, 101, 99],
                low=[100, 100, 101, 99])
    up_off, dn_off = compute_first_touch_offsets(bars, theta=0.03, f_max=3)
    assert up_off[0] == -1
    assert dn_off[0] == -1


def test_offset_scan_clipped_at_last_bar_of_session():
    # only 2 bars exist after t=0 even though f_max=10 is requested. The touch
    # at k=2 is still found (it exists), but a bar that would need k=3+ cannot
    # be found because the session ends at index 2.
    bars = _bars(close=[100, 100, 100],
                high=[100, 100, 104],
                low=[100, 100, 100])
    up_off, dn_off = compute_first_touch_offsets(bars, theta=0.03, f_max=10)
    assert up_off[0] == 2
    # the last bar (index 2) has no bars after it in the session -> always -1,
    # no matter how large f_max is.
    assert up_off[2] == -1
    assert dn_off[2] == -1


def test_offset_respects_f_max_even_when_more_bars_exist():
    # touch happens at k=3, but f_max=2 -> must not be found.
    bars = _bars(close=[100, 100, 100, 100],
                high=[100, 100, 100, 104],
                low=[100, 100, 100, 100])
    up_off, dn_off = compute_first_touch_offsets(bars, theta=0.03, f_max=2)
    assert up_off[0] == -1


# ---------------------------------------------------------------------------
# classify_outcomes: ambiguous when the same bar touches both, otherwise the
# earlier offset wins.
# ---------------------------------------------------------------------------

def test_classify_outcomes_ambiguous_when_same_offset_touches_both():
    up_off = np.array([2, 5])
    dn_off = np.array([2, 5])
    out = classify_outcomes(up_off, dn_off, f=10)
    assert list(out) == ["ambiguous", "ambiguous"]


def test_classify_outcomes_earlier_offset_wins():
    up_off = np.array([2, 5])
    dn_off = np.array([4, 3])
    out = classify_outcomes(up_off, dn_off, f=10)
    assert list(out) == ["up", "down"]


def test_classify_outcomes_only_one_side_touched():
    up_off = np.array([2, -1])
    dn_off = np.array([-1, 3])
    out = classify_outcomes(up_off, dn_off, f=10)
    assert list(out) == ["up", "down"]


def test_classify_outcomes_none_when_neither_in_window():
    up_off = np.array([-1, 8])
    dn_off = np.array([-1, 9])
    out = classify_outcomes(up_off, dn_off, f=5)
    assert list(out) == ["none", "none"]


# ---------------------------------------------------------------------------
# The test that matters: a slow, independent reference (direct per-bar
# scanning, not sharing any code with the fast path) must agree with
# _scan_stock_day on every candidate bar, across N/D/M combinations.
# ---------------------------------------------------------------------------

def test_fast_path_matches_brute_force_reference_on_random_series():
    rng = np.random.default_rng(20260701)
    n = 40
    close = 100.0 + np.cumsum(rng.normal(0, 1.0, n))
    close = np.clip(close, 50.0, None)
    high = close + rng.uniform(0.0, 3.0, n)
    low = np.clip(close - rng.uniform(0.0, 3.0, n), 1.0, None)
    # occasionally push high/low further out so barriers actually get touched.
    spike = rng.uniform(0, 1, n) < 0.3
    high = np.where(spike, high + rng.uniform(0, 4.0, n), high)
    low = np.where(spike, np.clip(low - rng.uniform(0, 4.0, n), 1.0, None), low)

    bars = _bars(close=close.tolist(), high=high.tolist(), low=low.tolist())
    tf = 3
    theta = THETA

    per_cell = _scan_stock_day(bars, tf)

    checked_any = False
    for n_lookback in NS:
        L = max(1, n_lookback // tf)
        for drop_pct in DS:
            for m_forward in MS:
                F = max(1, m_forward // tf)

                # --- slow reference: direct per-bar scanning, independent of
                # any production helper (labeler.py / first_touch.py / the
                # fast-path functions under test). ---
                expected: dict[int, str] = {}
                for t in range(n):
                    if t < L:
                        continue
                    prior_high = max(high[t - L:t])
                    drop = close[t] / prior_high - 1.0
                    if drop > -drop_pct:
                        continue

                    end = min(t + F, n - 1)
                    outcome = "none"
                    if end > t:
                        up_target = close[t] * (1.0 + theta)
                        dn_target = close[t] * (1.0 - theta)
                        for j in range(t + 1, end + 1):
                            up_touch = high[j] >= up_target
                            dn_touch = low[j] <= dn_target
                            if up_touch and dn_touch:
                                outcome = "ambiguous"
                            elif up_touch:
                                outcome = "up"
                            elif dn_touch:
                                outcome = "down"
                            else:
                                continue
                            break
                    expected[t] = outcome

                actual = per_cell[(n_lookback, drop_pct, m_forward)]
                expected_seq = [expected[t] for t in sorted(expected)]

                assert len(actual) == len(expected_seq), (
                    f"candidate count mismatch at N={n_lookback} D={drop_pct} "
                    f"M={m_forward}: fast={len(actual)} brute={len(expected_seq)}")
                assert list(actual) == expected_seq, (
                    f"outcome mismatch at N={n_lookback} D={drop_pct} M={m_forward}")
                if expected_seq:
                    checked_any = True

    # sanity: the random series must have produced at least one candidate
    # bar somewhere in the grid, otherwise this test would pass vacuously.
    assert checked_any


# ---------------------------------------------------------------------------
# _build_row: pure aggregation (no DB).
# ---------------------------------------------------------------------------

def test_build_row_edge_pp_equals_pct_up_minus_pct_down():
    counts = {"up": 12, "down": 5, "ambiguous": 1, "none": 22}
    row = _build_row("W1", 3, 60, 0.04, 60, n=40, n_dates=7, counts=counts)
    assert row["edge_pp"] == pytest.approx(row["pct_up"] - row["pct_down"])
    assert row["n"] == 40
    assert row["n_dates"] == 7


def test_build_row_pct_columns_sum_to_100_when_n_positive():
    counts = {"up": 3, "down": 2, "ambiguous": 1, "none": 1}
    row = _build_row("W1", 3, 60, 0.04, 60, n=7, n_dates=2, counts=counts)
    total = row["pct_up"] + row["pct_down"] + row["pct_ambiguous"] + row["pct_none"]
    assert total == pytest.approx(100.0, abs=1e-9)


def test_build_row_handles_zero_n_as_nan():
    row = _build_row("W1", 3, 60, 0.04, 60, n=0, n_dates=0, counts={})
    assert np.isnan(row["edge_pp"])
    assert np.isnan(row["pct_up"])
    assert row["n"] == 0


# ---------------------------------------------------------------------------
# summarize: hand-built 2-window frame -> stable_positive / stable_negative /
# flipped classification.
# ---------------------------------------------------------------------------

def _row(window, tf, n_lookback, drop_pct, m_forward, n, n_dates, pct_up, pct_down,
        pct_ambiguous, pct_none, edge_pp):
    return {
        "window": window, "tf": tf, "n_lookback": n_lookback, "drop_pct": drop_pct,
        "m_forward": m_forward, "n": n, "n_dates": n_dates, "pct_up": pct_up,
        "pct_down": pct_down, "pct_ambiguous": pct_ambiguous, "pct_none": pct_none,
        "edge_pp": edge_pp,
    }


def test_summarize_classifies_cells_correctly():
    rows = [
        # cell A: positive edge in both windows -> stable_positive.
        _row("W1", 3, 60, 0.04, 60, 100, 10, 20.0, 10.0, 1.0, 69.0, 10.0),
        _row("W2", 3, 60, 0.04, 60, 50, 5, 15.0, 5.0, 0.0, 80.0, 10.0),
        # cell B: negative edge in both windows -> stable_negative.
        _row("W1", 5, 30, 0.06, 30, 80, 8, 5.0, 15.0, 0.0, 80.0, -10.0),
        _row("W2", 5, 30, 0.06, 30, 40, 4, 4.0, 20.0, 0.0, 76.0, -16.0),
        # cell C: flips sign between windows -> flipped.
        _row("W1", 15, 120, 0.08, 120, 60, 6, 30.0, 10.0, 0.0, 60.0, 20.0),
        _row("W2", 15, 120, 0.08, 120, 30, 3, 5.0, 25.0, 0.0, 70.0, -20.0),
    ]
    df = pd.DataFrame(rows)

    result = summarize(df)

    cell_a = {"tf": 3, "n_lookback": 60, "drop_pct": 0.04, "m_forward": 60}
    cell_b = {"tf": 5, "n_lookback": 30, "drop_pct": 0.06, "m_forward": 30}
    cell_c = {"tf": 15, "n_lookback": 120, "drop_pct": 0.08, "m_forward": 120}

    def _strip(cells, keys):
        return [{k: c[k] for k in keys} for c in cells]

    assert cell_a in _strip(result["stable_positive"], cell_a.keys())
    assert cell_b in _strip(result["stable_negative"], cell_b.keys())
    assert cell_c in _strip(result["flipped"], cell_c.keys())
    assert len(result["stable_positive"]) == 1
    assert len(result["stable_negative"]) == 1
    assert len(result["flipped"]) == 1

    # per_window_median_edge: median of [10, -10, 20] = 10 for W1;
    # median of [10, -16, -20] = -16 for W2.
    assert result["per_window_median_edge"]["W1"] == pytest.approx(10.0)
    assert result["per_window_median_edge"]["W2"] == pytest.approx(-16.0)

    # min_n_across_windows: cell A -> min(100, 50) = 50, discoverable both via
    # the top-level lookup and embedded in the returned cell dict.
    key_a = (3, 60, 0.04, 60)
    assert result["min_n_across_windows"][key_a] == 50
    stable_a = next(c for c in result["stable_positive"]
                    if c["tf"] == 3 and c["n_lookback"] == 60)
    assert stable_a["min_n_across_windows"] == 50


def test_summarize_treats_missing_data_window_as_flipped_not_stable():
    # W2 has n=0 for this cell (edge_pp NaN) -> cannot be called stable
    # despite a positive edge in W1.
    rows = [
        _row("W1", 3, 30, 0.025, 30, 100, 10, 20.0, 5.0, 0.0, 75.0, 15.0),
        _row("W2", 3, 30, 0.025, 30, 0, 0, float("nan"), float("nan"),
            float("nan"), float("nan"), float("nan")),
    ]
    df = pd.DataFrame(rows)
    result = summarize(df)

    assert len(result["stable_positive"]) == 0
    assert len(result["stable_negative"]) == 0
    assert len(result["flipped"]) == 1


# ---------------------------------------------------------------------------
# module-level constants sanity (guards against accidental edits changing the
# grid shape used by the real scan).
# ---------------------------------------------------------------------------

def test_module_constants():
    assert TFS == (3, 5, 15)
    assert NS == (30, 60, 120)
    assert DS == (0.025, 0.04, 0.06, 0.08)
    assert MS == (30, 60, 120)
    assert THETA == 0.03
    assert len(WINDOWS) == 4
    assert len(TFS) * len(NS) * len(DS) * len(MS) == 108
