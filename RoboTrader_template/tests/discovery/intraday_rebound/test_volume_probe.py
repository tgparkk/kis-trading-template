import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.shape_compare import omnibus_test
from scripts.discovery.intraday_rebound.shape_events import FORWARD_BARS, LOOKBACK_BARS
from scripts.discovery.intraday_rebound.volume_probe import (
    _log1p_zscore,
    _relocate_event_volumes,
    assert_same_ids_and_outcomes,
    build_event_row_with_volume,
    build_price_volume_matrix,
    compute_vol_slope,
    slope_quintile_buckets,
)


def _bars(closes, volumes=None):
    n = len(closes)
    volumes = volumes if volumes is not None else [100] * n
    return pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="3min"),
        "open": closes,
        "high": closes,
        "low": closes,
        "close": closes,
        "volume": volumes,
        "amount": [1] * n,
        "bar_count": [3] * n,
    })


def _entry_time_at(idx: int) -> str:
    return (pd.Timestamp("2026-06-01 09:00") + pd.Timedelta(minutes=3 * idx)).strftime("%H:%M")


# ---------------------------------------------------------------------------
# log1p + row z-normalization of volume
# ---------------------------------------------------------------------------

def test_log1p_zscore_row_mean_zero_sd_one():
    rng = np.random.default_rng(0)
    matrix = rng.integers(0, 100_000, size=(30, LOOKBACK_BARS)).astype(float)
    z = _log1p_zscore(matrix)
    assert z.shape == matrix.shape
    np.testing.assert_allclose(z.mean(axis=1), 0.0, atol=1e-9)
    np.testing.assert_allclose(z.std(axis=1), 1.0, atol=1e-9)


def test_log1p_zscore_all_zero_volume_row_is_zeros_no_nan():
    matrix = np.zeros((2, LOOKBACK_BARS))
    matrix[1] = np.arange(LOOKBACK_BARS, dtype=float)  # non-flat row for contrast
    z = _log1p_zscore(matrix)
    assert not np.isnan(z).any()
    np.testing.assert_allclose(z[0], np.zeros(LOOKBACK_BARS))
    assert not np.allclose(z[1], np.zeros(LOOKBACK_BARS))


# ---------------------------------------------------------------------------
# PV construction: (n,40) shape, P/V blocks contribute equal total variance
# ---------------------------------------------------------------------------

def test_price_volume_matrix_shape_and_equal_block_contribution():
    rng = np.random.default_rng(1)
    n = 40
    P = rng.normal(size=(n, LOOKBACK_BARS))
    P = (P - P.mean(axis=1, keepdims=True)) / P.std(axis=1, keepdims=True)
    V = rng.normal(size=(n, LOOKBACK_BARS))
    V = (V - V.mean(axis=1, keepdims=True)) / V.std(axis=1, keepdims=True)

    PV = build_price_volume_matrix(P, V)

    assert PV.shape == (n, 2 * LOOKBACK_BARS)
    p_block_energy = np.sum(PV[:, :LOOKBACK_BARS] ** 2, axis=1)
    v_block_energy = np.sum(PV[:, LOOKBACK_BARS:] ** 2, axis=1)
    np.testing.assert_allclose(p_block_energy, v_block_energy, rtol=1e-9)
    # each z-normalized 20-dim row has sum-of-squares == LOOKBACK_BARS (population
    # var=1); after the 1/sqrt(2) scale each block contributes LOOKBACK_BARS/2.
    np.testing.assert_allclose(p_block_energy, LOOKBACK_BARS / 2.0, rtol=1e-6)


# ---------------------------------------------------------------------------
# vol_slope
# ---------------------------------------------------------------------------

def test_vol_slope_increasing_series_is_positive():
    v = np.tile(np.exp(np.linspace(0, 3, LOOKBACK_BARS)), (3, 1))
    slope = compute_vol_slope(v)
    assert np.all(slope > 0)


def test_vol_slope_decreasing_series_is_negative():
    v = np.tile(np.exp(np.linspace(3, 0, LOOKBACK_BARS)), (3, 1))
    slope = compute_vol_slope(v)
    assert np.all(slope < 0)


def test_vol_slope_matches_hand_computed_linear_case():
    # log1p(v) exactly linear in bar index -> slope must match the known
    # per-step increment.
    x = np.arange(LOOKBACK_BARS, dtype=float)
    log_v = 2.0 + 0.1 * x
    v = np.expm1(log_v).reshape(1, -1)
    slope = compute_vol_slope(v)
    assert slope[0] == pytest.approx(0.1, abs=1e-6)


def test_slope_quintile_buckets_covers_0_to_4_for_varied_input():
    rng = np.random.default_rng(2)
    slope = rng.normal(size=500)
    buckets = slope_quintile_buckets(slope)
    assert buckets.min() == 0
    assert buckets.max() == 4
    assert len(buckets) == 500


# ---------------------------------------------------------------------------
# build_event_row_with_volume: reuses build_event_row + adds v0..v19/v_entry
# ---------------------------------------------------------------------------

def test_build_event_row_with_volume_matches_bars_window():
    closes = [100.0] * LOOKBACK_BARS + [90.0, 90.0]
    volumes = list(range(1, LOOKBACK_BARS + 3))  # strictly increasing, 1-based
    bars = _bars(closes, volumes)
    idx = LOOKBACK_BARS

    row = build_event_row_with_volume(bars, idx, trade_date="20260601",
                                      stock_code="000001")

    assert row["outcome"] in {"up", "down", "ambiguous", "none"}
    for i in range(LOOKBACK_BARS):
        assert row[f"v{i}"] == pytest.approx(float(volumes[i]))
    assert row["v_entry"] == pytest.approx(float(volumes[idx]))
    # base columns from build_event_row (reused, not reimplemented) must
    # still be present.
    assert row["entry_close"] == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# scorer reuse: same omnibus_test wired into volume_probe.score_all
# ---------------------------------------------------------------------------

def _fake_events(n=800, seed=11, n_dates=20):
    rng = np.random.default_rng(seed)
    trade_date = rng.integers(0, n_dates, size=n).astype(str)
    pre_vol = rng.uniform(0.3, 3.0, size=n)
    return trade_date, pre_vol, rng


def test_omnibus_test_perfectly_associated_labels_give_large_T():
    trade_date, pre_vol, rng = _fake_events(seed=21)
    k = 8
    true_type = rng.integers(0, k, size=len(trade_date))
    p_up_by_type = np.linspace(0.15, 0.85, k)
    outcomes = np.array([
        "up" if rng.random() < p_up_by_type[t] else "down" for t in true_type
    ])

    result, _, _ = omnibus_test(true_type, outcomes, pre_vol, k=k, B=400, seed=13)
    assert result["T_obs"] > result["null_p95"]
    assert result["p"] < 0.05


def test_omnibus_test_random_labels_give_T_near_null_median():
    trade_date, pre_vol, rng = _fake_events(seed=22)
    k = 8
    outcomes = rng.choice(["up", "down"], size=len(trade_date), p=[0.4, 0.6])
    random_labels = rng.integers(0, k, size=len(trade_date))

    result, _, _ = omnibus_test(random_labels, outcomes, pre_vol, k=k, B=400, seed=13)
    lo = 0.2 * result["null_median"]
    hi = result["null_p95"] * 1.5
    assert lo <= result["T_obs"] <= hi


# ---------------------------------------------------------------------------
# sample regeneration: id order + outcome preserved (small fake pair of frames)
# ---------------------------------------------------------------------------

def test_assert_same_ids_and_outcomes_passes_on_matching_payloads():
    original = {"events": [
        {"id": "E001", "outcome": "up"},
        {"id": "E002", "outcome": "down"},
    ]}
    regenerated = {"events": [
        {"id": "E001", "outcome": "up", "pre_vol_bars": [1.0]},
        {"id": "E002", "outcome": "down", "pre_vol_bars": [2.0]},
    ]}
    assert_same_ids_and_outcomes(original, regenerated)  # must not raise


def test_assert_same_ids_and_outcomes_detects_reordering():
    original = {"events": [
        {"id": "E001", "outcome": "up"},
        {"id": "E002", "outcome": "down"},
    ]}
    reordered = {"events": [
        {"id": "E002", "outcome": "down"},
        {"id": "E001", "outcome": "up"},
    ]}
    with pytest.raises(AssertionError):
        assert_same_ids_and_outcomes(original, reordered)


def test_assert_same_ids_and_outcomes_detects_outcome_drift():
    original = {"events": [{"id": "E001", "outcome": "up"}]}
    drifted = {"events": [{"id": "E001", "outcome": "down"}]}
    with pytest.raises(AssertionError):
        assert_same_ids_and_outcomes(original, drifted)


# ---------------------------------------------------------------------------
# _relocate_event_volumes: pre/entry/post volumes + vol_ref fallback rules
# ---------------------------------------------------------------------------

def test_relocate_event_volumes_extracts_windows_and_vol_ref_is_median():
    closes = [100.0] * LOOKBACK_BARS + [90.0] + [90.0] * FORWARD_BARS
    volumes = list(range(1, LOOKBACK_BARS + 2 + FORWARD_BARS))
    bars = _bars(closes, volumes)
    idx = LOOKBACK_BARS

    result = _relocate_event_volumes(bars, entry_time=_entry_time_at(idx))

    assert result["pre_vol_bars"] == [float(x) for x in volumes[:LOOKBACK_BARS]]
    assert result["entry_vol"] == pytest.approx(float(volumes[idx]))
    assert result["post_vol_bars"] == [
        float(x) for x in volumes[idx + 1: idx + 1 + FORWARD_BARS]]
    assert result["vol_ref"] == pytest.approx(
        float(np.median(volumes[:LOOKBACK_BARS])))


def test_relocate_event_volumes_vol_ref_falls_back_to_mean_when_median_zero():
    closes = [100.0] * LOOKBACK_BARS + [90.0] + [90.0] * FORWARD_BARS
    pre = [0] * LOOKBACK_BARS
    pre[0] = 4  # median stays 0 (19 zeros dominate), mean > 0 -> mean branch
    volumes = pre + list(range(1, 2 + FORWARD_BARS))
    bars = _bars(closes, volumes)

    result = _relocate_event_volumes(bars, entry_time=_entry_time_at(LOOKBACK_BARS))
    assert np.median(pre) == 0
    assert result["vol_ref"] == pytest.approx(float(np.mean(pre)))


def test_relocate_event_volumes_vol_ref_falls_back_to_one_when_all_pre_zero():
    closes = [100.0] * LOOKBACK_BARS + [90.0] + [90.0] * FORWARD_BARS
    volumes = [0] * LOOKBACK_BARS + list(range(1, 2 + FORWARD_BARS))
    bars = _bars(closes, volumes)

    result = _relocate_event_volumes(bars, entry_time=_entry_time_at(LOOKBACK_BARS))
    assert result["vol_ref"] == pytest.approx(1.0)


def test_relocate_event_volumes_raises_on_entry_time_mismatch():
    closes = [100.0] * LOOKBACK_BARS + [90.0] + [90.0] * FORWARD_BARS
    bars = _bars(closes)
    with pytest.raises(ValueError):
        _relocate_event_volumes(bars, entry_time="99:99")
