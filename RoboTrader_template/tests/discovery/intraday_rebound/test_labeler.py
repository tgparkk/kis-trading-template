import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.labeler import LabelParams, compute_labels


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


P = LabelParams(timeframe_minutes=3, lookback_min=6, drop_pct=0.025,
                forward_min=6, theta=0.03, min_lookback_min=6)
# L = 2 bars, F = 2 bars, min_lookback_bars = 2 (== L, restores old behavior)


def test_prior_high_excludes_current_bar():
    bars = _bars([100, 110, 100, 100, 100])
    out = compute_labels(bars, P)
    # t=2 의 prior_high 는 t=0,1 의 high 최대 = 110
    assert out.loc[2, "prior_high"] == 110
    # t=0 은 룩백 없음
    assert np.isnan(out.loc[0, "prior_high"])


def test_candidate_requires_drop_below_threshold():
    # prior_high=110, close=107.25 → drop 2.5% 정확히 → 후보 (<=)
    bars = _bars([100, 110, 107.25, 100, 100])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "is_candidate"]) is True

    # close=108 → drop 1.8% → 후보 아님
    bars2 = _bars([100, 110, 108, 100, 100])
    out2 = compute_labels(bars2, P)
    assert bool(out2.loc[2, "is_candidate"]) is False


def test_hit_up_uses_forward_high_within_window():
    # t=2 close=100, theta=3% → target 103
    # t=3 high=103 → hit_up True
    bars = _bars(closes=[100, 110, 100, 101, 101],
                 highs=[100, 110, 100, 103, 101],
                 lows=[100, 110, 100, 101, 101])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "hit_up"]) is True


def test_hit_up_false_when_touch_is_outside_window():
    # F=2 → t=2 의 창은 t=3, t=4. t=5 의 고가는 무시돼야 한다.
    bars = _bars(closes=[100, 110, 100, 101, 101, 101],
                 highs=[100, 110, 100, 101, 101, 200],
                 lows=[100, 110, 100, 101, 101, 101])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "hit_up"]) is False


def test_hit_down_measured_independently_of_hit_up():
    # t=2 close=100. t=3 low=96 (-4% → hit_down), t=4 high=104 (+4% → hit_up)
    bars = _bars(closes=[100, 110, 100, 100, 100],
                 highs=[100, 110, 100, 100, 104],
                 lows=[100, 110, 100, 96, 100])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "hit_up"]) is True
    assert bool(out.loc[2, "hit_down"]) is True


def test_mae_stops_at_the_bar_that_hits_up():
    # t=2 close=100. t=3: low=98 (mae -2%), high=103 → hit. t=4 low=50 는 무시.
    bars = _bars(closes=[100, 110, 100, 100, 100],
                 highs=[100, 110, 100, 103, 100],
                 lows=[100, 110, 100, 98, 50])
    out = compute_labels(bars, P)
    assert out.loc[2, "hit_up"]
    assert out.loc[2, "mae"] == pytest.approx(-0.02)


def test_mae_uses_full_window_when_never_hits():
    bars = _bars(closes=[100, 110, 100, 100, 100],
                 highs=[100, 110, 100, 100, 100],
                 lows=[100, 110, 100, 99, 97])
    out = compute_labels(bars, P)
    assert not out.loc[2, "hit_up"]
    assert out.loc[2, "mae"] == pytest.approx(-0.03)


def test_hit_close_uses_bar_at_t_plus_F():
    # F=2 → t=2 의 hit_close 는 close[4] 로 판정. close[4]=103 → True
    bars = _bars([100, 110, 100, 200, 103])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "hit_close"]) is True


def test_truncated_window_at_session_end_sets_hit_close_nan():
    # 마지막 봉 t=4 는 앞으로 봉이 없다
    bars = _bars([100, 110, 100, 100, 100])
    out = compute_labels(bars, P)
    assert out.loc[4, "forward_bars"] == 0
    assert np.isnan(out.loc[4, "hit_close"])
    assert bool(out.loc[4, "hit_up"]) is False


def test_no_window_crosses_session_boundary_because_input_is_one_day():
    """계약 확인: compute_labels 는 한 종목-일만 받는다. 길이 보존."""
    bars = _bars([100] * 10)
    out = compute_labels(bars, P)
    assert len(out) == len(bars)


def test_min_lookback_bars_derived_from_timeframe():
    p = LabelParams(timeframe_minutes=3, lookback_min=60, drop_pct=0.04,
                    forward_min=60, theta=0.03)
    assert p.lookback_bars == 20
    assert p.min_lookback_bars == 5          # 15분 // 3분

    p15 = LabelParams(timeframe_minutes=15, lookback_min=60, drop_pct=0.04,
                      forward_min=60, theta=0.03)
    assert p15.min_lookback_bars == 1        # max(1, 15 // 15)


def test_prior_high_uses_partial_window_after_min_lookback():
    """min_lookback_bars 이후에는 앞 봉이 L개 미만이어도 prior_high 를 낸다."""
    p = LabelParams(timeframe_minutes=3, lookback_min=30, drop_pct=0.025,
                    forward_min=6, theta=0.03, min_lookback_min=6)
    # L = 10 bars, min_lookback = 2 bars
    bars = _bars([100, 110, 105, 100, 100, 100])
    out = compute_labels(bars, p)

    assert np.isnan(out.loc[0, "prior_high"])       # 앞 봉 0개
    assert np.isnan(out.loc[1, "prior_high"])       # 앞 봉 1개 < min 2
    assert out.loc[2, "prior_high"] == 110          # 앞 봉 2개, 부분 룩백
    assert out.loc[3, "prior_high"] == 110          # 앞 봉 3개


def test_lookback_bars_used_counts_actual_preceding_bars():
    p = LabelParams(timeframe_minutes=3, lookback_min=9, drop_pct=0.025,
                    forward_min=6, theta=0.03, min_lookback_min=3)
    # L = 3 bars
    bars = _bars([100] * 6)
    out = compute_labels(bars, p)
    assert out["lookback_bars_used"].tolist() == [0, 1, 2, 3, 3, 3]


def test_is_full_lookback_true_only_when_window_is_complete():
    p = LabelParams(timeframe_minutes=3, lookback_min=9, drop_pct=0.025,
                    forward_min=6, theta=0.03, min_lookback_min=3)
    bars = _bars([100] * 6)
    out = compute_labels(bars, p)
    assert out["is_full_lookback"].tolist() == [False, False, False, True, True, True]


def test_partial_lookback_bar_can_be_a_candidate():
    """개장 직후 급락이 후보로 살아남아야 한다 (46% 데이터 손실 방지)."""
    p = LabelParams(timeframe_minutes=3, lookback_min=60, drop_pct=0.04,
                    forward_min=6, theta=0.03)      # L=20, min=5
    closes = [100, 100, 100, 100, 100, 95, 95, 95]  # t=5 에서 -5%
    bars = _bars(closes)
    out = compute_labels(bars, p)

    assert bool(out.loc[5, "is_candidate"]) is True
    assert bool(out.loc[5, "is_full_lookback"]) is False
    assert out.loc[5, "lookback_bars_used"] == 5
