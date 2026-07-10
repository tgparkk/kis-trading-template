import numpy as np
import pandas as pd
import pytest
from sklearn.cluster import KMeans

from scripts.discovery.intraday_rebound.shape_events import (
    FORWARD_BARS,
    LOOKBACK_BARS,
    build_event_row,
)
from scripts.discovery.intraday_rebound.shape_samples import (
    DN_TARGET,
    N_SAMPLE_PER_CLASS,
    UP_TARGET,
    WINDOWS,
    _compute_vol_ref,
    _finalize_event,
    _find_touch_offset,
    _round_vol,
    build_eligible_record,
    sample_events,
    stratified_sample,
)


def _ohlc_bars(closes, volumes=None):
    n = len(closes)
    if volumes is None:
        volumes = [1] * n
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


def _trivial_kmeans(k=1):
    km = KMeans(n_clusters=k, random_state=0, n_init=3)
    km.fit(np.zeros((5, LOOKBACK_BARS)))
    return km


def _synthetic_record(outcome, window, code, date, rng):
    entry_close = 100.0 + float(rng.uniform(-5, 5))
    pre_ohlc = np.tile([entry_close, entry_close, entry_close, entry_close],
                       (LOOKBACK_BARS, 1))
    entry_ohlc = np.array([entry_close, entry_close, entry_close, entry_close])
    post_ohlc = np.tile([entry_close, entry_close, entry_close, entry_close],
                        (FORWARD_BARS, 1))
    touch_at = int(rng.integers(1, FORWARD_BARS + 1))
    if outcome == "up":
        post_ohlc[touch_at - 1, 1] = entry_close * 1.05
    else:
        post_ohlc[touch_at - 1, 2] = entry_close * 0.95
    return {
        "code": code, "date": date, "entry_time": "09:30", "window": window,
        "outcome": outcome, "drop_pct": -0.06, "pre_vol": 1.0,
        "w": [entry_close] * LOOKBACK_BARS,
        "entry_close": entry_close,
        "pre_ohlc": pre_ohlc, "entry_ohlc": entry_ohlc, "post_ohlc": post_ohlc,
        "pre_vols": [1.0] * LOOKBACK_BARS,
        "entry_vol": 1.0,
        "post_vols": [1.0] * FORWARD_BARS,
    }


def _build_synthetic_pool(rng, per_cell=40):
    records = []
    i = 0
    for outcome in ("up", "down"):
        for window in WINDOWS:
            for _ in range(per_cell):
                records.append(_synthetic_record(outcome, window, f"{i:06d}",
                                                  "2026-06-01", rng))
                i += 1
    return records


# ---------------------------------------------------------------------------
# price normalization
# ---------------------------------------------------------------------------

def test_finalize_event_entry_close_is_exactly_100_and_ratios_preserved():
    entry_close = 200.0
    pre_ohlc = np.array([[200.0, 205.0, 195.0, 200.0]] * LOOKBACK_BARS)
    entry_ohlc = np.array([210.0, 210.0, 195.0, 200.0])
    post_ohlc = np.tile([200.0, 200.0, 200.0, 200.0], (FORWARD_BARS, 1))
    post_ohlc[4] = [200.0, 208.0, 200.0, 200.0]  # +4% high at 1-based offset 5

    record = {
        "code": "000001", "date": "2026-06-01", "entry_time": "09:30",
        "window": "W1", "outcome": "up", "drop_pct": -0.06, "pre_vol": 1.2345,
        "w": [entry_close] * LOOKBACK_BARS,
        "entry_close": entry_close,
        "pre_ohlc": pre_ohlc, "entry_ohlc": entry_ohlc, "post_ohlc": post_ohlc,
        "pre_vols": [1000.0] * LOOKBACK_BARS,
        "entry_vol": 12345.0,
        "post_vols": [2000.0] * FORWARD_BARS,
    }
    km = _trivial_kmeans()

    event = _finalize_event(record, km, "E001")

    assert event["entry"][3] == 100.0
    assert event["entry"] == [105.0, 105.0, 97.5, 100.0]
    raw_ratio = 200.0 / 205.0
    norm_ratio = event["pre"][0][0] / event["pre"][0][1]
    assert norm_ratio == pytest.approx(raw_ratio, abs=1e-6)
    assert event["touch_offset"] == 5


# ---------------------------------------------------------------------------
# per-bar volume fields (raw, not normalized)
# ---------------------------------------------------------------------------

def test_finalize_event_volumes_are_raw_not_scaled():
    entry_close = 200.0
    pre_ohlc = np.array([[200.0, 205.0, 195.0, 200.0]] * LOOKBACK_BARS)
    entry_ohlc = np.array([210.0, 210.0, 195.0, 200.0])
    post_ohlc = np.tile([200.0, 200.0, 200.0, 200.0], (FORWARD_BARS, 1))
    post_ohlc[4] = [200.0, 208.0, 200.0, 200.0]

    record = {
        "code": "000001", "date": "2026-06-01", "entry_time": "09:30",
        "window": "W1", "outcome": "up", "drop_pct": -0.06, "pre_vol": 1.2345,
        "w": [entry_close] * LOOKBACK_BARS,
        "entry_close": entry_close,
        "pre_ohlc": pre_ohlc, "entry_ohlc": entry_ohlc, "post_ohlc": post_ohlc,
        "pre_vols": [1000.0] * LOOKBACK_BARS,
        "entry_vol": 12345.0,
        "post_vols": [2000.0] * FORWARD_BARS,
    }
    km = _trivial_kmeans()

    event = _finalize_event(record, km, "E001")

    # raw, unscaled -- not divided/multiplied by entry_close like OHLC is.
    assert event["entry_vol"] == 12345
    assert event["pre_vols"] == [1000] * LOOKBACK_BARS
    assert event["post_vols"] == [2000] * FORWARD_BARS
    assert len(event["pre_vols"]) == LOOKBACK_BARS
    assert len(event["post_vols"]) == FORWARD_BARS
    assert event["vol_ref"] == 1000  # median of pre_vols (all 1000)
    # pre_vol (the volatility scalar) must remain untouched, unconfused
    # with the new volume fields.
    assert event["pre_vol"] == 1.2345


def test_round_vol_whole_numbers_become_int_others_2dp():
    assert _round_vol(12345.0) == 12345
    assert isinstance(_round_vol(12345.0), int)
    assert _round_vol(1234.567) == 1234.57
    assert isinstance(_round_vol(1234.567), float)


def test_compute_vol_ref_falls_back_to_mean_when_median_is_zero():
    pre_vols = [0.0] * 15 + [100.0] * 5  # median=0, mean=25
    ref = _compute_vol_ref(pre_vols)
    assert ref == pytest.approx(25.0)


def test_compute_vol_ref_falls_back_to_one_when_median_and_mean_are_zero():
    pre_vols = [0.0] * LOOKBACK_BARS
    ref = _compute_vol_ref(pre_vols)
    assert ref == 1.0


def test_compute_vol_ref_uses_median_when_nonzero():
    pre_vols = [10.0, 20.0, 30.0, 40.0, 50.0]
    ref = _compute_vol_ref(pre_vols)
    assert ref == 30.0


# ---------------------------------------------------------------------------
# build_eligible_record: raw volume slices attached to the record
# ---------------------------------------------------------------------------

def test_build_eligible_record_attaches_pre_entry_post_volumes():
    closes = [100.0] * 20 + [90.0, 95.0] + [90.0] * 19
    volumes = [float(v) for v in range(1, len(closes) + 1)]
    bars = _ohlc_bars(closes, volumes=volumes)
    idx = LOOKBACK_BARS
    row = build_event_row(bars, idx, trade_date="20260601", stock_code="000001")

    record = build_eligible_record(bars, idx, row)

    assert record is not None
    assert len(record["pre_vols"]) == LOOKBACK_BARS
    assert len(record["post_vols"]) == FORWARD_BARS
    assert record["entry_vol"] == volumes[idx]
    assert not isinstance(record["entry_vol"], list)
    assert list(record["pre_vols"]) == volumes[idx - LOOKBACK_BARS: idx]
    assert list(record["post_vols"]) == volumes[idx + 1: idx + 1 + FORWARD_BARS]


# ---------------------------------------------------------------------------
# touch_offset + sanity assertion
# ---------------------------------------------------------------------------

def test_find_touch_offset_locates_first_barrier_touch_up():
    post = ([[100.0, 100.0, 100.0, 100.0]] * 4
           + [[100.0, 103.5, 99.0, 100.0]]
           + [[100.0, 100.0, 100.0, 100.0]] * 15)
    offset = _find_touch_offset(post, "up")
    assert offset == 5
    assert max(bar[1] for bar in post[:offset]) >= UP_TARGET - 1e-6


def test_find_touch_offset_locates_first_barrier_touch_down():
    post = ([[100.0, 100.0, 100.0, 100.0]] * 2
           + [[100.0, 100.5, 96.5, 99.0]]
           + [[100.0, 100.0, 100.0, 100.0]] * 17)
    offset = _find_touch_offset(post, "down")
    assert offset == 3
    assert min(bar[2] for bar in post[:offset]) <= DN_TARGET + 1e-6


# ---------------------------------------------------------------------------
# forward-bar-count eligibility gate
# ---------------------------------------------------------------------------

def test_build_eligible_record_excludes_when_fewer_than_20_forward_bars():
    # entry at idx=20 (drop -10%), a big up-spike at idx+1 resolves outcome
    # to "up" well before the window would close, but only 19 bars remain
    # after idx -> must still be excluded (the forward-bar-count gate is
    # independent of outcome).
    closes_short = [100.0] * 20 + [90.0, 95.0] + [90.0] * 18
    bars_short = _ohlc_bars(closes_short)
    idx = LOOKBACK_BARS
    row_short = build_event_row(bars_short, idx, trade_date="20260601",
                                stock_code="000001")
    assert row_short["outcome"] == "up"
    assert build_eligible_record(bars_short, idx, row_short) is None

    # identical shape but one more trailing bar -> exactly 20 forward bars
    # remain -> included.
    closes_full = [100.0] * 20 + [90.0, 95.0] + [90.0] * 19
    bars_full = _ohlc_bars(closes_full)
    row_full = build_event_row(bars_full, idx, trade_date="20260601",
                               stock_code="000001")
    assert row_full["outcome"] == "up"
    record = build_eligible_record(bars_full, idx, row_full)
    assert record is not None
    assert record["outcome"] == "up"
    assert record["post_ohlc"].shape == (FORWARD_BARS, 4)


# ---------------------------------------------------------------------------
# sample_events: balanced classes, shuffled order
# ---------------------------------------------------------------------------

def test_sample_events_60_up_60_down_and_shuffled_not_sorted_by_class():
    rng_pool = np.random.default_rng(1)
    pool = _build_synthetic_pool(rng_pool)
    km = _trivial_kmeans()
    rng = np.random.default_rng(42)

    events = sample_events(pool, km, rng)

    assert len(events) == 120
    up_count = sum(1 for e in events if e["outcome"] == "up")
    down_count = sum(1 for e in events if e["outcome"] == "down")
    assert up_count == 60
    assert down_count == 60

    first_20_outcomes = {e["outcome"] for e in events[:20]}
    assert len(first_20_outcomes) > 1


# ---------------------------------------------------------------------------
# stratified_sample: no window dominates a class
# ---------------------------------------------------------------------------

def test_stratified_sample_no_window_exceeds_60_percent_of_class():
    rng_pool = np.random.default_rng(2)
    counts = {"W1": 5, "W2": 30, "W3": 30, "W4": 30}
    records = []
    i = 0
    for window, n in counts.items():
        for _ in range(n):
            records.append(_synthetic_record("up", window, f"{i:06d}",
                                              "2026-06-01", rng_pool))
            i += 1

    rng = np.random.default_rng(42)
    sampled = stratified_sample(records, N_SAMPLE_PER_CLASS, rng)

    assert len(sampled) == N_SAMPLE_PER_CLASS
    by_window: dict[str, int] = {}
    for r in sampled:
        by_window[r["window"]] = by_window.get(r["window"], 0) + 1
    for w, n in by_window.items():
        assert n <= 0.6 * N_SAMPLE_PER_CLASS, f"{w} contributes {n}/{N_SAMPLE_PER_CLASS}"
