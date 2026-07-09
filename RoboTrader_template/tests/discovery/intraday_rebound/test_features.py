import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.features import FEATURE_NAMES, compute_features


DAILY_CTX = {
    "gap_pct": -0.01, "ret_5d": -0.05, "ret_20d": 0.02,
    "dev_ma20": -0.08, "atr14_pct": 0.03,
    "market_cap": 1e12, "amount_rank": 0.7,
}


def _bars(n=20, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = close + rng.normal(0, 0.3, n)
    return pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="3min"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.integers(1, 100, n).astype(float),
        "amount": rng.integers(100, 10000, n).astype(float),
        "bar_count": [3] * n,
    })


def _ctx(bars):
    prior_high = bars["high"].rolling(20, min_periods=20).max().shift(1)
    market_ret = pd.Series(np.linspace(-0.01, 0.01, len(bars)))
    return prior_high, market_ret


def test_returns_all_feature_columns_with_matching_length():
    bars = _bars()
    prior_high, market_ret = _ctx(bars)
    out = compute_features(bars, prior_high, DAILY_CTX, market_ret, lookback_bars=20)
    assert list(out.columns) == FEATURE_NAMES
    assert len(out) == len(bars)


def test_time_truncation_no_lookahead():
    """t 이후 데이터를 NaN으로 지워도 t행의 특징이 바뀌면 안 된다."""
    bars = _bars(n=30)
    prior_high, market_ret = _ctx(bars)
    full = compute_features(bars, prior_high, DAILY_CTX, market_ret, lookback_bars=20)

    for t in (10, 20, 29):
        truncated = bars.copy()
        cols = ["open", "high", "low", "close", "volume", "amount"]
        truncated.loc[t + 1:, cols] = np.nan
        ph_trunc = prior_high.copy()
        ph_trunc.loc[t + 1:] = np.nan
        mr_trunc = market_ret.copy()
        mr_trunc.loc[t + 1:] = np.nan

        partial = compute_features(truncated, ph_trunc, DAILY_CTX, mr_trunc,
                                   lookback_bars=20)
        pd.testing.assert_series_equal(
            full.iloc[t], partial.iloc[t], check_names=False,
            obj=f"row {t} changed when future was erased",
        )


def test_rel_drop_is_drop_minus_market_return():
    bars = _bars()
    prior_high, market_ret = _ctx(bars)
    out = compute_features(bars, prior_high, DAILY_CTX, market_ret, lookback_bars=20)
    np.testing.assert_allclose(
        out["rel_drop"].to_numpy(),
        (out["drop_pct"] - out["market_ret"]).to_numpy(),
        equal_nan=True,
    )


def test_lower_wick_ratio_bounds():
    bars = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=1, freq="3min"),
        "open": [100.0], "high": [110.0], "low": [90.0], "close": [95.0],
        "volume": [1.0], "amount": [1.0], "bar_count": [3],
    })
    prior_high = pd.Series([np.nan])
    market_ret = pd.Series([0.0])
    out = compute_features(bars, prior_high, DAILY_CTX, market_ret, lookback_bars=1)
    # (close - low) / (high - low) = (95-90)/(110-90) = 0.25
    assert out.loc[0, "lower_wick_ratio"] == pytest.approx(0.25)


def test_zero_range_bar_does_not_divide_by_zero():
    bars = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=1, freq="3min"),
        "open": [100.0], "high": [100.0], "low": [100.0], "close": [100.0],
        "volume": [1.0], "amount": [1.0], "bar_count": [3],
    })
    out = compute_features(bars, pd.Series([np.nan]), DAILY_CTX,
                           pd.Series([0.0]), lookback_bars=1)
    assert np.isnan(out.loc[0, "lower_wick_ratio"])
    assert np.isnan(out.loc[0, "body_ratio"])


def test_bars_since_prior_high_ignores_the_shift_induced_nan():
    """high.shift(1) 의 NaN 을 argmax 가 최대값으로 고르면 drop_speed 가 t 의 함수가 된다."""
    highs = [1.0, 2.0, 3.0, 2.0, 1.0, 4.0, 3.0, 2.0]
    n = len(highs)
    bars = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="3min"),
        "open": highs, "high": highs, "low": highs, "close": highs,
        "volume": [1.0] * n, "amount": [1.0] * n, "bar_count": [3] * n,
    })
    prior_high = pd.Series(highs).shift(1)
    out = compute_features(bars, prior_high, DAILY_CTX, pd.Series([0.0] * n),
                           lookback_bars=20)

    # drop_speed = drop_pct / bars_since. drop_pct 를 알고 있으므로 bars_since 를 역산한다.
    bars_since = (out["drop_pct"] / out["drop_speed"]).to_numpy()
    expected = [np.nan, 1, 1, 1, 2, 3, 1, 2]
    np.testing.assert_allclose(bars_since[1:], expected[1:], rtol=1e-9)
    assert np.isnan(bars_since[0])


def test_drop_speed_is_not_a_ramp_in_t():
    """수정 전에는 bars_since 가 [nan,2,3,4,...] 로 t 를 그대로 따라갔다."""
    highs = [1.0, 2.0, 3.0, 2.0, 1.0, 4.0, 3.0, 2.0]
    n = len(highs)
    bars = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="3min"),
        "open": highs, "high": highs, "low": highs, "close": highs,
        "volume": [1.0] * n, "amount": [1.0] * n, "bar_count": [3] * n,
    })
    prior_high = pd.Series(highs).shift(1)
    out = compute_features(bars, prior_high, DAILY_CTX, pd.Series([0.0] * n),
                           lookback_bars=20)
    bars_since = (out["drop_pct"] / out["drop_speed"]).to_numpy()
    ramp = np.arange(1, n + 1, dtype=float)
    assert not np.allclose(bars_since[1:], ramp[1:], equal_nan=True)


def test_consec_down_counts_consecutive_bearish_bars():
    bars = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=4, freq="3min"),
        "open": [100.0, 100.0, 100.0, 100.0],
        "high": [101.0, 101.0, 101.0, 101.0],
        "low": [98.0, 98.0, 98.0, 98.0],
        "close": [99.0, 98.0, 99.5, 98.0],   # down, down, up, down
        "volume": [1.0] * 4, "amount": [1.0] * 4, "bar_count": [3] * 4,
    })
    out = compute_features(bars, pd.Series([np.nan] * 4), DAILY_CTX,
                           pd.Series([0.0] * 4), lookback_bars=1)
    assert out["consec_down"].tolist() == [1.0, 2.0, 0.0, 1.0]
