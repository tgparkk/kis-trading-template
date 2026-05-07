"""spike_features 단위 테스트 — 합성 일봉 30행 fixture 기반."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from RoboTrader_template.multiverse.composable.features.spike_features import (
    atr_ratio,
    box_squeeze,
    compute_all_features,
    ma20_dist,
    vol_trend,
    vol_zscore_20,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

def _make_df(
    n: int = 30,
    close_start: float = 10_000.0,
    close_step: float = 100.0,
    volume_base: int = 1_000_000,
    volume_spike: float = 1.0,  # 마지막 행 거래량 배수
) -> pd.DataFrame:
    """n행 합성 일봉 DataFrame.

    - close: close_start + i * close_step (단조 증가)
    - high:  close + 200
    - low:   close - 200
    - open:  close - 50
    - volume: volume_base (단, 마지막 행은 volume_base * volume_spike)
    """
    rows = []
    for i in range(n):
        c = close_start + i * close_step
        vol = int(volume_base * volume_spike) if i == n - 1 else volume_base
        rows.append({
            "date": f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": c - 50,
            "high": c + 200,
            "low": c - 200,
            "close": c,
            "volume": vol,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def df30() -> pd.DataFrame:
    """기본 30행 합성 일봉."""
    return _make_df(n=30)


@pytest.fixture
def df20() -> pd.DataFrame:
    """정확히 20행 — 일부 피처 경계값."""
    return _make_df(n=20)


@pytest.fixture
def df15() -> pd.DataFrame:
    """15행 — 21행 미만 → vol_zscore_20 None."""
    return _make_df(n=15)


# ──────────────────────────────────────────────────────────────────────────────
# vol_zscore_20
# ──────────────────────────────────────────────────────────────────────────────

class TestVolZscore20:
    def test_normal_returns_float(self, df30):
        result = vol_zscore_20(df30)
        assert result is not None
        assert isinstance(result, float)
        assert not math.isnan(result)

    def test_less_than_21_rows_returns_none(self, df15):
        assert vol_zscore_20(df15) is None

    def test_exactly_21_rows(self):
        """정확히 21행 — 경계값, None이 아니어야 함."""
        df = _make_df(n=21)
        result = vol_zscore_20(df)
        assert result is not None

    def test_volume_std_zero_returns_zero(self):
        """모든 거래량이 동일 → std=0 → 0.0 반환."""
        df = _make_df(n=30, volume_base=500_000, volume_spike=1.0)
        # 모든 행의 volume이 동일 → std=0
        result = vol_zscore_20(df)
        assert result == 0.0

    def test_spike_volume_positive_zscore(self):
        """window(직전 20행) 내 거래량 변동이 있고 D-1이 평균보다 높으면 z-score > 0.

        _make_df의 volume_spike는 마지막 행(D-1)만 변경하므로,
        window(iloc[-21:-1] = 행 9~28)은 모두 volume_base로 동일 → std=0 → 0.0.
        의미있는 양수 z-score를 확인하려면 window 내 분산이 있어야 한다.
        여기서는 행 9~19=1M, 행 20~28=2M, 행 29(D-1)=3M 구조를 사용.
        """
        rows = []
        for i in range(30):
            if i < 20:
                vol = 1_000_000
            elif i < 29:
                vol = 2_000_000
            else:
                vol = 3_000_000  # D-1
            c = 10_000.0 + i * 100
            rows.append({"date": f"2025-01-{i+1:02d}", "open": c - 50,
                         "high": c + 200, "low": c - 200, "close": c, "volume": vol})
        df = pd.DataFrame(rows)
        result = vol_zscore_20(df)
        assert result is not None
        assert result > 0.0

    def test_exact_value(self):
        """직접 계산값과 비교.

        vol_base=1_000_000 (29행), 마지막(D-1) = 3_000_000.
        window = iloc[-21:-1] = 20행, 모두 1_000_000.
        mean=1_000_000, std=0 (직전 20행 동일).
        → std=0 → 0.0.

        다른 검증: volume_spike=3, base=1M, 직전 20행이 1M.
        행 0..8은 1M, 행 9..28은 2M, 행 29(D-1)=3M.
        window = iloc[-21:-1] = 행 9~28 (20행) = 2M 각각.
        mean=2M, std=0 → 0.0.

        의미있는 std: 행 0..19=1M, 행 20..28=2M(9행), 행 29=3M.
        window=iloc[-21:-1]=행 9~28: 행 9~19(11행)=1M, 행 20~28(9행)=2M.
        mean = (11*1M + 9*2M)/20 = 29M/20 = 1.45M
        variance = [11*(1M-1.45M)^2 + 9*(2M-1.45M)^2] / 19
               = [11*0.2025T + 9*0.3025T] / 19
               = [2.2275T + 2.7225T] / 19
               = 4.95T / 19 = 0.2605263T
        std = sqrt(0.2605263T) ≈ 510,418
        z = (3M - 1.45M) / 510418 ≈ 3.036
        """
        rows = []
        for i in range(30):
            if i < 20:
                vol = 1_000_000
            elif i < 29:
                vol = 2_000_000
            else:
                vol = 3_000_000  # D-1
            c = 10_000.0 + i * 100
            rows.append({"date": f"2025-01-{i+1:02d}", "open": c - 50,
                         "high": c + 200, "low": c - 200, "close": c, "volume": vol})
        df = pd.DataFrame(rows)

        result = vol_zscore_20(df)
        assert result is not None

        # 직접 계산
        window_vols = [1_000_000] * 11 + [2_000_000] * 9  # 행 9~28 (20행)
        mean = sum(window_vols) / 20
        variance = sum((v - mean) ** 2 for v in window_vols) / 19  # ddof=1
        std = math.sqrt(variance)
        expected = (3_000_000 - mean) / std

        assert abs(result - expected) < 1e-6, f"expected={expected}, actual={result}"

    def test_no_volume_column_returns_none(self):
        df = pd.DataFrame({"close": range(30), "high": range(30), "low": range(30)})
        assert vol_zscore_20(df) is None


# ──────────────────────────────────────────────────────────────────────────────
# ma20_dist
# ──────────────────────────────────────────────────────────────────────────────

class TestMa20Dist:
    def test_normal_returns_float(self, df30):
        result = ma20_dist(df30)
        assert result is not None
        assert isinstance(result, float)
        assert not math.isnan(result)

    def test_less_than_20_rows_returns_none(self, df15):
        assert ma20_dist(df15) is None

    def test_exactly_20_rows(self, df20):
        result = ma20_dist(df20)
        assert result is not None

    def test_exact_value(self):
        """close = [100, 110, 120, ..., 290] (20행, step=10).
        MA20 = mean(100..290) = 195.
        D-1 close = 290.
        dist = (290 - 195) / 195 = 95/195 ≈ 0.487179...
        """
        closes = [100.0 + i * 10 for i in range(20)]
        df = pd.DataFrame({
            "date": [f"2025-01-{i+1:02d}" for i in range(20)],
            "open": [c - 5 for c in closes],
            "high": [c + 10 for c in closes],
            "low": [c - 10 for c in closes],
            "close": closes,
            "volume": [1_000_000] * 20,
        })
        result = ma20_dist(df)
        ma20 = sum(closes) / 20
        expected = (closes[-1] - ma20) / ma20
        assert result is not None
        assert abs(result - expected) < 1e-9, f"expected={expected}, actual={result}"

    def test_flat_close_zero_dist(self):
        """모든 close가 동일 → dist = 0.0."""
        df = _make_df(n=25, close_start=10_000.0, close_step=0.0)
        result = ma20_dist(df)
        assert result is not None
        assert abs(result) < 1e-9

    def test_no_close_column_returns_none(self):
        df = pd.DataFrame({"volume": range(25)})
        assert ma20_dist(df) is None


# ──────────────────────────────────────────────────────────────────────────────
# atr_ratio
# ──────────────────────────────────────────────────────────────────────────────

class TestAtrRatio:
    def test_normal_returns_float(self, df30):
        result = atr_ratio(df30)
        assert result is not None
        assert isinstance(result, float)
        assert not math.isnan(result)
        assert result > 0.0

    def test_insufficient_data_returns_none(self):
        """14+1=15행 미만."""
        df = _make_df(n=14)
        assert atr_ratio(df) is None

    def test_exactly_15_rows(self):
        df = _make_df(n=15)
        result = atr_ratio(df)
        assert result is not None

    def test_exact_value(self):
        """flat 가격: close=10000, high=10200, low=9800 (모든 행 동일).
        TR = max(400, |10200-10000|, |9800-10000|) = max(400,200,200) = 400.
        ATR = 400.
        atr_ratio = 400/10000 = 0.04.
        """
        n = 20
        rows = [{"date": f"2025-01-{i+1:02d}", "open": 9950,
                 "high": 10200, "low": 9800, "close": 10000, "volume": 1_000_000}
                for i in range(n)]
        df = pd.DataFrame(rows)
        result = atr_ratio(df)
        assert result is not None
        assert abs(result - 0.04) < 1e-9, f"expected=0.04, actual={result}"

    def test_custom_period(self, df30):
        result = atr_ratio(df30, period=7)
        assert result is not None

    def test_no_high_column_returns_none(self):
        df = pd.DataFrame({"close": range(20), "low": range(20), "volume": range(20)})
        assert atr_ratio(df) is None


# ──────────────────────────────────────────────────────────────────────────────
# box_squeeze
# ──────────────────────────────────────────────────────────────────────────────

class TestBoxSqueeze:
    def test_normal_returns_float(self, df30):
        result = box_squeeze(df30)
        assert result is not None
        assert isinstance(result, float)
        assert not math.isnan(result)
        assert result >= 0.0

    def test_insufficient_data_returns_none(self):
        df = _make_df(n=9)
        assert box_squeeze(df) is None

    def test_exactly_10_rows(self):
        df = _make_df(n=10)
        result = box_squeeze(df)
        assert result is not None

    def test_exact_value(self):
        """10행: high=10200 (균일), low=9800 (균일), close(D-1)=10000.
        box = (10200 - 9800) / 10000 = 400/10000 = 0.04.
        """
        n = 10
        rows = [{"date": f"2025-01-{i+1:02d}", "open": 9950,
                 "high": 10200, "low": 9800, "close": 10000, "volume": 1_000_000}
                for i in range(n)]
        df = pd.DataFrame(rows)
        result = box_squeeze(df)
        assert result is not None
        assert abs(result - 0.04) < 1e-9, f"expected=0.04, actual={result}"

    def test_wide_range_large_value(self, df30):
        """단조 증가 일봉: 마지막 10행의 high.max - low.min이 close보다 작음."""
        result = box_squeeze(df30)
        assert result is not None
        assert result > 0.0

    def test_custom_window(self, df30):
        result = box_squeeze(df30, window=5)
        assert result is not None

    def test_no_high_column_returns_none(self):
        df = pd.DataFrame({"close": range(15), "low": range(15), "volume": range(15)})
        assert box_squeeze(df) is None


# ──────────────────────────────────────────────────────────────────────────────
# vol_trend
# ──────────────────────────────────────────────────────────────────────────────

class TestVolTrend:
    def test_normal_returns_float(self, df30):
        result = vol_trend(df30)
        assert result is not None
        assert isinstance(result, float)
        assert not math.isnan(result)

    def test_insufficient_data_returns_none(self):
        """20행 미만."""
        df = _make_df(n=19)
        assert vol_trend(df) is None

    def test_exactly_20_rows(self, df20):
        result = vol_trend(df20)
        assert result is not None

    def test_flat_volume_returns_one(self):
        """모든 거래량이 동일 → short_mean / long_mean = 1.0."""
        df = _make_df(n=25, volume_spike=1.0)
        result = vol_trend(df)
        assert result is not None
        assert abs(result - 1.0) < 1e-9, f"flat volume → 1.0, actual={result}"

    def test_increasing_volume_returns_above_one(self):
        """마지막 5행 거래량이 앞보다 높으면 > 1.0."""
        rows = []
        for i in range(30):
            vol = 2_000_000 if i >= 25 else 1_000_000
            c = 10_000.0 + i * 100
            rows.append({"date": f"2025-01-{i+1:02d}", "open": c - 50,
                         "high": c + 200, "low": c - 200, "close": c, "volume": vol})
        df = pd.DataFrame(rows)
        result = vol_trend(df)
        assert result is not None
        assert result > 1.0

    def test_exact_value(self):
        """vol 0..24=1M, 25..29=2M.
        short_mean(5일) = 2M.
        long_mean(20일) = (15*1M + 5*2M)/20 = 25M/20 = 1.25M.
        ratio = 2M / 1.25M = 1.6.
        """
        rows = []
        for i in range(30):
            vol = 2_000_000 if i >= 25 else 1_000_000
            c = 10_000.0 + i * 100
            rows.append({"date": f"2025-01-{i+1:02d}", "open": c - 50,
                         "high": c + 200, "low": c - 200, "close": c, "volume": vol})
        df = pd.DataFrame(rows)
        result = vol_trend(df)
        expected = 2_000_000 / 1_250_000
        assert result is not None
        assert abs(result - expected) < 1e-9, f"expected={expected}, actual={result}"

    def test_custom_periods(self, df30):
        result = vol_trend(df30, short=3, long=10)
        assert result is not None

    def test_no_volume_column_returns_none(self):
        df = pd.DataFrame({"close": range(25)})
        assert vol_trend(df) is None


# ──────────────────────────────────────────────────────────────────────────────
# compute_all_features
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeAllFeatures:
    def test_returns_dict_with_five_keys(self, df30):
        result = compute_all_features(df30)
        assert isinstance(result, dict)
        assert set(result.keys()) == {
            "vol_zscore_20", "ma20_dist", "atr_ratio", "box_squeeze", "vol_trend"
        }

    def test_all_floats_on_sufficient_data(self, df30):
        result = compute_all_features(df30)
        for key, val in result.items():
            assert val is not None, f"{key} should not be None with 30 rows"
            assert isinstance(val, float), f"{key} should be float"
            assert not math.isnan(val), f"{key} should not be NaN"

    def test_none_on_insufficient_data(self):
        """15행 — vol_zscore_20, vol_trend, ma20_dist 모두 None 또는 일부 None."""
        df = _make_df(n=15)
        result = compute_all_features(df)
        # vol_zscore_20: 21행 미만 → None
        assert result["vol_zscore_20"] is None
        # vol_trend: 20행 미만 → None
        assert result["vol_trend"] is None

    def test_no_nan_propagation(self, df30):
        """NaN이 결과에 없어야 함."""
        result = compute_all_features(df30)
        for key, val in result.items():
            if val is not None:
                assert not math.isnan(val), f"{key} has NaN"

    def test_21_rows_partial_none(self):
        """21행: vol_zscore_20 통과, vol_trend 통과(20행 충족), atr_ratio 통과."""
        df = _make_df(n=21)
        result = compute_all_features(df)
        assert result["vol_zscore_20"] is not None
        assert result["ma20_dist"] is not None
        assert result["atr_ratio"] is not None
        assert result["vol_trend"] is not None
        assert result["box_squeeze"] is not None
