import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound import walkforward as wf


def _bars(closes, highs=None, lows=None, tf=3):
    n = len(closes)
    highs = highs if highs is not None else closes
    lows = lows if lows is not None else closes
    return pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq=f"{tf}min"),
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1] * n,
        "amount": [1] * n,
        "bar_count": [tf] * n,
    })


# ---------------------------------------------------------------------------
# outcome_from_path
# ---------------------------------------------------------------------------

def test_outcome_from_path_up_when_high_crosses_and_low_stays_above():
    fh = [100, 101, 103.5, 100]
    fl = [100, 99, 98.5, 100]
    fc = [100, 100, 100, 100]
    outcome, ret = wf.outcome_from_path(fh, fl, fc, entry=100.0,
                                        theta_up=0.03, theta_dn=0.02, F=4)
    assert outcome == "up"
    assert ret == pytest.approx(fc[3] / 100.0 - 1.0)


def test_outcome_from_path_down_when_low_crosses_and_high_stays_below():
    fh = [100, 101, 102, 100]
    fl = [100, 99, 97.5, 100]
    fc = [100, 100, 100, 100]
    outcome, ret = wf.outcome_from_path(fh, fl, fc, entry=100.0,
                                        theta_up=0.03, theta_dn=0.02, F=4)
    assert outcome == "down"
    assert ret == pytest.approx(fc[3] / 100.0 - 1.0)


def test_outcome_from_path_ambiguous_when_same_bar_hits_both():
    fh = [104, 100]
    fl = [96, 100]
    fc = [100, 100]
    outcome, ret = wf.outcome_from_path(fh, fl, fc, entry=100.0,
                                        theta_up=0.03, theta_dn=0.03, F=2)
    assert outcome == "ambiguous"


def test_outcome_from_path_none_when_neither_barrier_touched():
    fh = [100, 101, 101]
    fl = [100, 99, 99]
    fc = [100, 100, 99]
    outcome, ret = wf.outcome_from_path(fh, fl, fc, entry=100.0,
                                        theta_up=0.03, theta_dn=0.03, F=3)
    assert outcome == "none"
    assert ret == pytest.approx(fc[2] / 100.0 - 1.0)


def test_outcome_from_path_first_touch_ordering_down_before_up_wins():
    # bar0 touches down only; bar1 touches up only. First touch (down) decides.
    fh = [100, 104]
    fl = [97, 100]
    fc = [100, 100]
    outcome, ret = wf.outcome_from_path(fh, fl, fc, entry=100.0,
                                        theta_up=0.03, theta_dn=0.03, F=2)
    assert outcome == "down"


def test_outcome_from_path_truncated_at_F_ignores_later_bars():
    # F=2 -> only bars 0,1 are scanned; bar 2's huge move must be ignored.
    fh = [100, 100, 200]
    fl = [100, 100, 200]
    fc = [100, 100, 200]
    outcome, ret = wf.outcome_from_path(fh, fl, fc, entry=100.0,
                                        theta_up=0.03, theta_dn=0.03, F=2)
    assert outcome == "none"
    assert ret == pytest.approx(fc[1] / 100.0 - 1.0)


# ---------------------------------------------------------------------------
# expectancy
# ---------------------------------------------------------------------------

def test_expectancy_hand_computed_exact():
    # 10 up, 5 down, 2 ambiguous, 3 none (terminal_rets mean 0), n=20.
    # theta_up=0.03, theta_dn=0.015.
    # p_up=0.5, p_down=0.25, p_amb=0.10, p_none=0.15
    # gross = 0.5*0.03 - (0.25+0.10)*0.015 + 0.15*0.0 = 0.015 - 0.00525 = 0.00975
    # net = 0.00975 - 0.0021 = 0.00765
    outcomes = (["up"] * 10 + ["down"] * 5 + ["ambiguous"] * 2 + ["none"] * 3)
    terminal_rets = [0.0] * 17 + [-0.01, 0.00, 0.01]

    exp = wf.expectancy(outcomes, terminal_rets, theta_up=0.03, theta_dn=0.015)

    assert exp["n"] == 20
    assert exp["gross"] == pytest.approx(0.00975, abs=1e-12)
    assert exp["net"] == pytest.approx(0.00765, abs=1e-12)


def test_expectancy_empty_input_is_nan_safe():
    exp = wf.expectancy([], [], theta_up=0.03, theta_dn=0.02)
    assert exp["n"] == 0
    assert np.isnan(exp["gross"])
    assert np.isnan(exp["net"])


# ---------------------------------------------------------------------------
# make_folds
# ---------------------------------------------------------------------------

def test_make_folds_contiguous_near_equal_covering_all_days_no_overlap():
    days = np.array([f"202504{d:02d}" for d in range(1, 31)])  # 30 unique days
    folds = wf.make_folds(days, n_folds=8)

    assert len(folds) == 8
    sizes = [len(f) for f in folds]
    assert max(sizes) - min(sizes) <= 1
    assert sum(sizes) == len(days)

    concatenated = np.concatenate(folds)
    assert len(set(concatenated.tolist())) == len(concatenated)  # no overlap
    assert concatenated.tolist() == sorted(days.tolist())  # contiguous & covers all


# ---------------------------------------------------------------------------
# leakage: quantile thresholds are computed on train only
# ---------------------------------------------------------------------------

def test_quantile_threshold_computed_on_train_only_never_recomputed_on_test():
    train = pd.DataFrame({
        "close_pos_in_day": np.linspace(0.0, 0.3, 50),
        "lower_wick_ratio": np.linspace(0.0, 0.3, 50),
    })
    # test distribution is shifted much higher than train.
    test = pd.DataFrame({
        "close_pos_in_day": np.linspace(0.7, 1.0, 50),
        "lower_wick_ratio": np.linspace(0.7, 1.0, 50),
    })

    filters = wf._quantile_filters(train)
    cpid_filter = next(f for f in filters
                       if f["type"] == "close_pos_in_day" and f["q"] == 0.2)

    train_threshold = cpid_filter["threshold"]
    assert train_threshold == pytest.approx(float(train["close_pos_in_day"].quantile(0.2)))

    test_quantile = float(test["close_pos_in_day"].quantile(0.2))
    assert train_threshold != pytest.approx(test_quantile)

    mask = wf._apply_filter_mask(test, cpid_filter)
    # Correct (leak-free) behavior: every shifted test value exceeds the TRAIN
    # threshold, so nothing passes. A re-quantile-on-test bug would instead
    # keep ~20% of the test rows (whatever its OWN low quantile is).
    assert mask.sum() == 0
    np.testing.assert_array_equal(
        mask, test["close_pos_in_day"].to_numpy() <= train_threshold)


# ---------------------------------------------------------------------------
# leakage: KMeans is fit on train only; test-time assignment never refits
# ---------------------------------------------------------------------------

def _p_df(rows: list[list[float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=wf.P_COLS)


def test_fit_kmeans_centroids_come_from_train_subset():
    rng = np.random.default_rng(3)
    base_a = np.linspace(1.0, -1.0, wf.PRE_BARS)
    base_b = np.linspace(-1.0, 1.0, wf.PRE_BARS)
    rows = [
        (base_a + rng.normal(0, 0.01, wf.PRE_BARS)).tolist() for _ in range(20)
    ] + [
        (base_b + rng.normal(0, 0.01, wf.PRE_BARS)).tolist() for _ in range(20)
    ]
    train = _p_df(rows)

    labels, centroids = wf._fit_kmeans(train, k=2, seed=42)

    from sklearn.cluster import KMeans as SKKMeans
    z = wf.zscore_rows(train[wf.P_COLS].to_numpy(dtype=float))
    km = SKKMeans(n_clusters=2, random_state=42, n_init=10)
    expected_labels = km.fit_predict(z)

    np.testing.assert_array_equal(labels, expected_labels)
    np.testing.assert_allclose(centroids, km.cluster_centers_)


def test_apply_filter_mask_cluster_branch_never_calls_kmeans_fit():
    centroids = np.array([[1.0] * wf.PRE_BARS, [-1.0] * wf.PRE_BARS])
    filt = {"type": "cluster", "k": 2, "seed": 42,
           "centroids": centroids.tolist(), "accepted": [0, 1]}
    test_df = _p_df([[float(i)] * wf.PRE_BARS for i in range(5)])

    with patch("sklearn.cluster.KMeans.fit") as mock_fit, \
        patch("sklearn.cluster.KMeans.fit_predict") as mock_fit_predict:
        mask = wf._apply_filter_mask(test_df, filt)

    mock_fit.assert_not_called()
    mock_fit_predict.assert_not_called()
    assert mask.shape == (5,)


def test_apply_filter_mask_cluster_assigns_nearest_centroid_not_refit():
    # Two well-separated SHAPE centroids (constant rows z-normalize to all
    # zeros -- shape, not level, is what clustering keys on). Only centroid 0
    # is accepted; a test row matching centroid 1's shape must be excluded.
    pattern_desc = np.linspace(1.0, -1.0, wf.PRE_BARS)
    pattern_asc = np.linspace(-1.0, 1.0, wf.PRE_BARS)
    centroids = np.array([
        wf.zscore_rows(pattern_desc.reshape(1, -1))[0],
        wf.zscore_rows(pattern_asc.reshape(1, -1))[0],
    ])
    filt = {"type": "cluster", "k": 2, "seed": 42,
           "centroids": centroids.tolist(), "accepted": [0]}
    test_df = _p_df([pattern_desc.tolist(), pattern_asc.tolist()])

    mask = wf._apply_filter_mask(test_df, filt)
    np.testing.assert_array_equal(mask, [True, False])


# ---------------------------------------------------------------------------
# leakage + search_config: end-to-end cluster config, centroids from train
# ---------------------------------------------------------------------------

def _synthetic_cluster_train_df() -> pd.DataFrame:
    """40 events, tf=3, drop_pct=-5% (only D=0.04 grid cell is nonempty).

    Group A: straight-line pre-window shape, forward path guarantees "up"
    for every (theta_up, theta_dn) in the search grid (fh jumps far above any
    up target on bar 0; fl never approaches any down target).
    Group B: convex pre-window shape, forward path guarantees "down"
    symmetrically. close_pos_in_day / lower_wick_ratio are constant (0.5) for
    every event so the quantile/both filters degenerate to "keep everything"
    (same as "none") and can never outperform the cluster filter -- only the
    KMeans shape split can isolate the pure-"up" group.
    """
    n_per_group = 20
    rng = np.random.default_rng(7)
    base_a = np.linspace(105.0, 95.0, wf.PRE_BARS)          # straight line
    base_b = 100.0 - (np.arange(wf.PRE_BARS) ** 1.7) * 0.3  # convex curve

    date_strs = pd.date_range("2025-04-01", periods=n_per_group * 2,
                              freq="D").strftime("%Y%m%d").tolist()

    rows = []
    for group, base, fh_val, fl_val, fc_val in (
        ("A", base_a, 110.0, 105.0, 108.0),
        ("B", base_b, 95.0, 90.0, 92.0),
    ):
        for i in range(n_per_group):
            p = base + rng.normal(0, 0.02, wf.PRE_BARS)
            row = {
                "tf": 3,
                "stock_code": f"{group}{i:04d}",
                "trade_date": date_strs[len(rows)],
                "entry_time": pd.Timestamp("2025-04-01 10:00"),
                "entry_close": 100.0,
                "drop_pct": -0.05,
                "close_pos_in_day": 0.5,
                "lower_wick_ratio": 0.5,
                "pre_vol": 1.0,
            }
            for j in range(wf.PRE_BARS):
                row[f"p{j}"] = float(p[j])
            for j in range(wf.FWD_BARS):
                row[f"fh{j}"] = fh_val
                row[f"fl{j}"] = fl_val
                row[f"fc{j}"] = fc_val
            rows.append(row)
    return pd.DataFrame(rows, columns=wf.EVENT_COLUMNS)


def test_search_config_cluster_filter_centroids_come_from_train():
    train = _synthetic_cluster_train_df()

    result = wf.search_config(train, seed=42)

    assert result["constraint_met"] is True
    assert result["filter"]["type"] == "cluster"
    # the accepted cluster(s) must isolate exactly the "up"-only group.
    assert result["n_trades"] == 20
    assert result["p_up"] == pytest.approx(1.0)
    assert result["p_down"] == pytest.approx(0.0)

    # independently recompute the fit search_config must have used internally
    # on the exact same training subset (tf=3, D=0.04 -- the only nonempty cell).
    sub_d = train[(train["tf"] == result["tf"])
                  & (train["drop_pct"] <= -result["D"])]
    k = result["filter"]["k"]
    seed = result["filter"]["seed"]
    _, expected_centroids = wf._fit_kmeans(sub_d, k, seed)
    np.testing.assert_allclose(result["filter"]["centroids"], expected_centroids)


def test_search_config_deterministic_for_fixed_seed():
    train = _synthetic_cluster_train_df()
    r1 = wf.search_config(train, seed=42)
    r2 = wf.search_config(train, seed=42)
    # NaN != NaN under plain dict equality (mean_terminal_none is NaN here --
    # no "none" outcomes ever occur in this fixture); compare via JSON so
    # matching NaNs at matching positions count as equal.
    assert (json.dumps(r1, sort_keys=True, default=str)
           == json.dumps(r2, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# extraction helpers (find_first_event_idx / build_event_row): no DB
# ---------------------------------------------------------------------------

def test_find_first_event_idx_requires_idx_ge_pre_bars():
    # bars 0..19 flat at 100 (full lookback for tf=3, L=20); bar 20 drops 10%
    # and stays there -> idx=20 is the first (and only) qualifying bar.
    n = 45
    closes = [100.0] * 20 + [90.0] * (n - 20)
    bars = _bars(closes, tf=3)
    idx = wf.find_first_event_idx(bars, tf=3)
    assert idx == 20


def test_find_first_event_idx_early_drop_before_pre_bars_is_excluded():
    # Qualifying drop at idx=5 (< PRE_BARS=20) must be excluded. Price then
    # recovers to 100 and stays flat forever -> no idx>=20 candidate either.
    n = 45
    closes = [100.0] * 5 + [90.0] + [100.0] * (n - 6)
    bars = _bars(closes, tf=3)
    idx = wf.find_first_event_idx(bars, tf=3)
    assert idx is None


def test_find_first_event_idx_requires_20_forward_bars():
    # n=40 -> idx=20 qualifies on drop/lookback but only 19 forward bars
    # remain (39-20) -- and it's the earliest any idx>=20 could occur, so
    # every later idx suffers the same forward-bar shortfall.
    n = 40
    closes = [100.0] * 20 + [90.0] * (n - 20)
    bars = _bars(closes, tf=3)
    idx = wf.find_first_event_idx(bars, tf=3)
    assert idx is None


def test_build_event_row_windows_and_features():
    n = 45
    closes = [100.0] * 20 + [90.0] * (n - 20)
    bars = _bars(closes, tf=3)
    idx = wf.find_first_event_idx(bars, tf=3)
    row = wf.build_event_row(bars, idx, tf=3, trade_date="20260601",
                             stock_code="000001")

    assert row["tf"] == 3
    assert row["stock_code"] == "000001"
    assert row["trade_date"] == "20260601"
    assert row["entry_close"] == pytest.approx(90.0)
    assert row["drop_pct"] == pytest.approx(90.0 / 100.0 - 1.0)
    for i in range(wf.PRE_BARS):
        assert row[f"p{i}"] == pytest.approx(100.0)
    for i in range(wf.FWD_BARS):
        assert row[f"fh{i}"] == pytest.approx(90.0)
        assert row[f"fl{i}"] == pytest.approx(90.0)
        assert row[f"fc{i}"] == pytest.approx(90.0)
