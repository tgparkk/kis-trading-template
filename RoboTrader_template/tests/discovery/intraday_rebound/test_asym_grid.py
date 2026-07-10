import pandas as pd
import pytest

from scripts.discovery.intraday_rebound import asym_grid as a
from scripts.discovery.intraday_rebound.asym_grid import (
    FILTER_CLOSE_POS_MAX,
    FILTER_LOWER_WICK_MAX,
    ROUND_TRIP_COST,
    ROWS_COLUMNS,
    _aggregate_grid,
)


def _hand_mix_rows(theta_up=0.03, theta_dn=0.015):
    # 10 up, 5 down, 2 ambiguous, 3 none (terminal_ret -0.01, 0.00, +0.01 -> mean 0.0).
    # n=20 -> p_up=.5, p_down=.25, p_amb=.10, p_none=.15.
    rows = (
        [{"outcome": "up", "terminal_ret": 0.0}] * 10
        + [{"outcome": "down", "terminal_ret": 0.0}] * 5
        + [{"outcome": "ambiguous", "terminal_ret": 0.0}] * 2
        + [{"outcome": "none", "terminal_ret": r} for r in (-0.01, 0.00, 0.01)]
    )
    df = pd.DataFrame(rows)
    df["theta_up"] = theta_up
    df["theta_dn"] = theta_dn
    df["segment"] = "s"
    df["trade_date"] = "20260601"
    # comfortably inside both thresholds -> "all" and "filtered" buckets identical.
    df["close_pos_in_day"] = 0.0
    df["lower_wick_ratio"] = 0.0
    return df[ROWS_COLUMNS]


# ---------------------------------------------------------------------------
# hand-computed gross/net/rr (spec Step 3, exact numbers)
# ---------------------------------------------------------------------------

def test_aggregate_grid_hand_computed_gross_and_net_match_spec():
    # gross = .5*.03 - .25*.015 - .10*.015 + 0 = .015 - .00375 - .0015 = .00975
    # gross_pct = 0.975 ; net_pct = round((.00975 - 0.0021)*100, 3) = 0.765
    df = _hand_mix_rows(theta_up=0.03, theta_dn=0.015)
    out = _aggregate_grid(df)
    row = out[out["filt"] == "all"].iloc[0]

    assert row["n"] == 20
    assert row["gross_pct"] == 0.975
    assert row["net_pct"] == 0.765


def test_aggregate_grid_rr_is_theta_up_over_theta_dn():
    df = _hand_mix_rows(theta_up=0.03, theta_dn=0.015)
    out = _aggregate_grid(df)
    row = out[out["filt"] == "all"].iloc[0]
    assert row["rr"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# ambiguous must be charged at theta_dn, never theta_up
# ---------------------------------------------------------------------------

def test_aggregate_grid_charges_ambiguous_at_theta_dn_not_theta_up():
    theta_up, theta_dn = 0.03, 0.015
    df = _hand_mix_rows(theta_up=theta_up, theta_dn=theta_dn)
    out = _aggregate_grid(df)
    row = out[out["filt"] == "all"].iloc[0]

    p_up, p_down, p_amb, p_none = 10 / 20, 5 / 20, 2 / 20, 3 / 20
    correct_gross_pct = round(
        (p_up * theta_up - p_down * theta_dn - p_amb * theta_dn + p_none * 0.0) * 100, 3)
    # mutation: if ambiguous were (wrongly) charged at theta_up instead of theta_dn.
    wrong_gross_pct = round(
        (p_up * theta_up - p_down * theta_dn - p_amb * theta_up + p_none * 0.0) * 100, 3)

    assert wrong_gross_pct != correct_gross_pct, "test mix must actually discriminate"
    assert row["gross_pct"] == correct_gross_pct
    assert row["gross_pct"] != wrong_gross_pct


# ---------------------------------------------------------------------------
# filtered subset never contains a row failing either threshold
# ---------------------------------------------------------------------------

def test_aggregate_grid_filtered_subset_never_exceeds_threshold():
    # (close_pos_in_day, lower_wick_ratio, passes_filter)
    specs = [
        (0.01, 0.01, True),
        (0.05, 0.01, False),                       # close_pos fails
        (0.01, 0.09, False),                       # lower_wick fails
        (FILTER_CLOSE_POS_MAX, FILTER_LOWER_WICK_MAX, True),  # boundary inclusive
        (0.05, 0.09, False),                       # both fail
    ]
    rows = [{
        "theta_up": 0.03, "theta_dn": 0.015, "segment": "s",
        "trade_date": "20260601", "close_pos_in_day": close_pos,
        "lower_wick_ratio": wick, "outcome": "none", "terminal_ret": 0.0,
    } for close_pos, wick, _passes in specs]
    df = pd.DataFrame(rows)[ROWS_COLUMNS]

    out = _aggregate_grid(df)
    expected_n_filtered = sum(1 for _, _, passes in specs if passes)

    all_row = out[out["filt"] == "all"].iloc[0]
    filtered_row = out[out["filt"] == "filtered"].iloc[0]
    assert all_row["n"] == len(specs)
    assert filtered_row["n"] == expected_n_filtered


# ---------------------------------------------------------------------------
# analyze_single: exactly one (theta_up, theta_dn) pair, no grid, no DB
# ---------------------------------------------------------------------------

def test_analyze_single_returns_exactly_one_theta_pair(monkeypatch):
    captured = {}

    def _fake_build_grid_rows(start, end, theta_ups, theta_dns, tf, lookback_min,
                              drop_pct, forward_min):
        captured["theta_ups"] = theta_ups
        captured["theta_dns"] = theta_dns
        rows = [
            {"theta_up": theta_ups[0], "theta_dn": theta_dns[0], "segment": "full",
             "trade_date": "20260601", "close_pos_in_day": 0.0, "lower_wick_ratio": 0.0,
             "outcome": "up", "terminal_ret": 0.0},
            {"theta_up": theta_ups[0], "theta_dn": theta_dns[0], "segment": "full",
             "trade_date": "20260602", "close_pos_in_day": 0.0, "lower_wick_ratio": 0.0,
             "outcome": "down", "terminal_ret": 0.0},
        ]
        return pd.DataFrame(rows, columns=ROWS_COLUMNS)

    monkeypatch.setattr(a, "_build_grid_rows", _fake_build_grid_rows)

    out = a.analyze_single("20260601", "20260602", theta_up=0.025, theta_dn=0.012)

    # exactly one grid cell was requested from the (mocked) DB-backed builder.
    assert captured["theta_ups"] == (0.025,)
    assert captured["theta_dns"] == (0.012,)
    # and the resulting frame reflects exactly one (theta_up, theta_dn) pair.
    assert out["theta_up"].nunique() == 1
    assert out["theta_dn"].nunique() == 1
    assert set(zip(out["theta_up"], out["theta_dn"])) == {(0.025, 0.012)}


# ---------------------------------------------------------------------------
# module-level constants sanity (guards against accidental edits)
# ---------------------------------------------------------------------------

def test_module_constants():
    assert ROUND_TRIP_COST == 0.0021
    assert FILTER_CLOSE_POS_MAX == 0.043
    assert FILTER_LOWER_WICK_MAX == 0.083
