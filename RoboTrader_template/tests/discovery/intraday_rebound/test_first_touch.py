import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.first_touch import _aggregate, first_touch_outcome


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


def test_up_when_high_crosses_and_low_stays_above_down_barrier():
    # entry = close[0] = 100, theta=3% -> up target 103, down target 97
    # j=1: no touch. j=2: high touches up (103.5), low stays above 97 (98).
    bars = _bars(closes=[100, 100, 100, 100],
                highs=[100, 101, 103.5, 100],
                lows=[100, 99, 98, 100])
    outcome, ret = first_touch_outcome(bars, close_idx=0, forward_bars=3, theta=0.03)
    assert outcome == "up"
    assert ret == pytest.approx(bars["close"].iloc[3] / 100.0 - 1.0)


def test_down_when_low_crosses_and_high_stays_below_up_barrier():
    # symmetric to the "up" case.
    bars = _bars(closes=[100, 100, 100, 100],
                highs=[100, 101, 102, 100],
                lows=[100, 99, 96.5, 100])
    outcome, ret = first_touch_outcome(bars, close_idx=0, forward_bars=3, theta=0.03)
    assert outcome == "down"
    assert ret == pytest.approx(bars["close"].iloc[3] / 100.0 - 1.0)


def test_ambiguous_when_first_touching_bar_hits_both_barriers():
    # j=1's own high/low spans both the up and down barrier.
    bars = _bars(closes=[100, 100, 100],
                highs=[100, 104, 100],
                lows=[100, 96, 100])
    outcome, ret = first_touch_outcome(bars, close_idx=0, forward_bars=2, theta=0.03)
    assert outcome == "ambiguous"


def test_first_touch_wins_a_down_bar_then_an_up_bar_returns_down():
    # j=1 touches down only; j=2 touches up only. First touch (down) must win.
    bars = _bars(closes=[100, 100, 100],
                highs=[100, 100, 104],
                lows=[100, 96, 100])
    outcome, ret = first_touch_outcome(bars, close_idx=0, forward_bars=2, theta=0.03)
    assert outcome == "down"


def test_bar_beyond_forward_window_is_ignored():
    # forward_bars=1 -> only j=1 is scanned; the huge move at j=2 must be ignored.
    bars = _bars(closes=[100, 100, 200],
                highs=[100, 100, 200],
                lows=[100, 100, 200])
    outcome, ret = first_touch_outcome(bars, close_idx=0, forward_bars=1, theta=0.03)
    assert outcome == "none"
    assert ret == pytest.approx(bars["close"].iloc[1] / 100.0 - 1.0)


def test_none_when_neither_barrier_touched():
    bars = _bars(closes=[100, 100, 101, 99],
                highs=[100, 100, 101, 99],
                lows=[100, 100, 101, 99])
    outcome, ret = first_touch_outcome(bars, close_idx=0, forward_bars=3, theta=0.03)
    assert outcome == "none"
    assert ret == pytest.approx(bars["close"].iloc[3] / 100.0 - 1.0)


def test_window_truncated_at_last_bar_when_forward_bars_exceeds_available():
    # only 2 bars actually exist after close_idx even though forward_bars=10 is requested.
    bars = _bars(closes=[100, 100, 100],
                highs=[100, 100, 104],
                lows=[100, 100, 100])
    outcome, ret = first_touch_outcome(bars, close_idx=0, forward_bars=10, theta=0.03)
    assert outcome == "up"
    assert ret == pytest.approx(bars["close"].iloc[2] / 100.0 - 1.0)


def test_aggregate_percentages_sum_to_100():
    # 3/7 up, 2/7 down, 1/7 ambiguous, 1/7 none -> naive independent rounding of all
    # four (42.86 + 28.57 + 14.29 + 14.29 = 100.01) would NOT sum to 100.
    df = pd.DataFrame({
        "segment": ["full"] * 7,
        "outcome": ["up", "up", "up", "down", "down", "ambiguous", "none"],
        "terminal_ret": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.01],
    })
    out = _aggregate(df, theta=0.03)
    assert len(out) == 1
    row = out.iloc[0]
    total = row["pct_up"] + row["pct_down"] + row["pct_ambiguous"] + row["pct_none"]
    assert total == pytest.approx(100.0, abs=1e-9)
    assert row["n"] == 7
    assert row["mean_terminal_none"] == pytest.approx(-1.0)  # -0.01 -> -1.00%


def test_aggregate_expectancy_numbers_match_hand_computation():
    # Hand-built mix, n=20: 10 up, 5 down, 2 ambiguous, 3 none.
    # none terminal_ret = [-0.01, 0.00, +0.01] -> mean_terminal_none = 0.0.
    # theta = 0.03.
    # p_up=10/20=0.50, p_down=5/20=0.25, p_amb=2/20=0.10, p_none=3/20=0.15.
    #
    # conservative (ambiguous = loss):
    #   gross = p_up*theta - (p_down + p_amb)*theta + p_none*mean_terminal_none
    #         = 0.50*0.03 - (0.25+0.10)*0.03 + 0.15*0.0
    #         = 0.015 - 0.0105 + 0.0
    #         = 0.0045
    #   gross_expectancy_pct = 0.0045 * 100 = 0.45
    #
    # optimistic (ambiguous = win):
    #   gross_optimistic = (p_up+p_amb)*theta - p_down*theta + p_none*mean_terminal_none
    #                     = (0.50+0.10)*0.03 - 0.25*0.03 + 0.0
    #                     = 0.018 - 0.0075 + 0.0
    #                     = 0.0105
    #   gross_expectancy_optimistic_pct = 0.0105 * 100 = 1.05
    #
    # breakeven_cost_pct = gross_expectancy_pct (since conservative gross > 0) = 0.45
    rows = (
        [{"segment": "s", "outcome": "up", "terminal_ret": 0.0}] * 10
        + [{"segment": "s", "outcome": "down", "terminal_ret": 0.0}] * 5
        + [{"segment": "s", "outcome": "ambiguous", "terminal_ret": 0.0}] * 2
        + [{"segment": "s", "outcome": "none", "terminal_ret": r}
           for r in (-0.01, 0.00, 0.01)]
    )
    df = pd.DataFrame(rows)
    out = _aggregate(df, theta=0.03)
    assert len(out) == 1
    row = out.iloc[0]

    assert row["n"] == 20
    assert row["n_ambiguous"] == 2
    assert row["mean_terminal_none"] == pytest.approx(0.0)
    assert row["gross_expectancy_pct"] == pytest.approx(0.45)
    assert row["gross_expectancy_optimistic_pct"] == pytest.approx(1.05)
    assert row["breakeven_cost_pct"] == pytest.approx(0.45)

    # ambiguous-sign contract: optimistic must be strictly greater than
    # conservative whenever p_amb > 0 (ambiguous counted as win, not loss).
    assert row["gross_expectancy_optimistic_pct"] > row["gross_expectancy_pct"]


def test_aggregate_breakeven_cost_is_nan_when_conservative_gross_not_positive():
    # All "down" -> conservative gross = 0*theta - (1.0+0)*theta + 0 = -theta < 0.
    df = pd.DataFrame({
        "segment": ["s"] * 4,
        "outcome": ["down"] * 4,
        "terminal_ret": [0.0] * 4,
    })
    out = _aggregate(df, theta=0.03)
    row = out.iloc[0]
    assert row["gross_expectancy_pct"] <= 0
    assert np.isnan(row["breakeven_cost_pct"])


def test_aggregate_optimistic_equals_conservative_when_no_ambiguous():
    # p_amb == 0 -> the ambiguous term drops out of both formulas, so the two
    # expectancy numbers must be exactly equal (not just bounded).
    df = pd.DataFrame({
        "segment": ["s"] * 4,
        "outcome": ["up", "up", "down", "none"],
        "terminal_ret": [0.0, 0.0, 0.0, 0.0],
    })
    out = _aggregate(df, theta=0.03)
    row = out.iloc[0]
    assert row["n_ambiguous"] == 0
    assert row["gross_expectancy_optimistic_pct"] == row["gross_expectancy_pct"]


def test_aggregate_rejects_unknown_outcome_label():
    df = pd.DataFrame({
        "segment": ["s"],
        "outcome": ["bogus"],
        "terminal_ret": [0.0],
    })
    with pytest.raises(AssertionError):
        _aggregate(df, theta=0.03)


def test_first_touch_outcome_rejects_non_rangeindex_bars():
    bars = _bars(closes=[100, 100, 100],
                highs=[100, 101, 102],
                lows=[100, 99, 98])
    bars.index = [10, 11, 12]
    with pytest.raises(AssertionError):
        first_touch_outcome(bars, close_idx=0, forward_bars=2, theta=0.03)
