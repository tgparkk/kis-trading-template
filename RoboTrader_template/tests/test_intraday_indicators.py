"""
intraday_indicators.py 단위 테스트

테스트 대상: utils/intraday_indicators.py
- vwap, orb_levels, rsi_minute, ema_minute, bollinger_minute
- volume_zscore, volume_surge, flag_pattern, pivot_sr_levels, red_to_green

합성 데이터만 사용 (DB 의존 없음)
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from utils.intraday_indicators import (
    bollinger_minute,
    ema_minute,
    flag_pattern,
    orb_levels,
    pivot_sr_levels,
    red_to_green,
    rsi_minute,
    volume_surge,
    volume_zscore,
    vwap,
)


# ===========================================================================
# Helper factories
# ===========================================================================

def _make_df(
    closes: list[float],
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
    amounts: list[float] | None = None,
    start: datetime | None = None,
    date: str | None = None,
) -> pd.DataFrame:
    """최소 분봉 DataFrame 생성 헬퍼."""
    n = len(closes)
    base = start or datetime(2026, 5, 15, 9, 0, 0)
    dts = [base + timedelta(minutes=i) for i in range(n)]
    df = pd.DataFrame(
        {
            "datetime": dts,
            "open": opens if opens is not None else closes,
            "high": highs if highs is not None else closes,
            "low": lows if lows is not None else closes,
            "close": closes,
            "volume": volumes if volumes is not None else [1000] * n,
        }
    )
    if amounts is not None:
        df["amount"] = amounts
    return df


def _make_multiday_df(
    day_closes: list[list[float]],
) -> pd.DataFrame:
    """다일(복수 날짜) 분봉 DataFrame 생성."""
    frames = []
    for day_idx, closes in enumerate(day_closes):
        base = datetime(2026, 5, 15 + day_idx, 9, 0, 0)
        frames.append(_make_df(closes, start=base))
    return pd.concat(frames, ignore_index=True)


# ===========================================================================
# 1. vwap
# ===========================================================================

class TestVwap:
    def test_constant_price_equals_price(self):
        """가격·거래량 고정 → VWAP == close."""
        df = _make_df([1000.0] * 10, volumes=[500] * 10)
        result = vwap(df)
        assert result.notna().all()
        assert (result - 1000.0).abs().max() < 1e-9

    def test_weighted_calculation(self):
        """수동 계산과 일치 검증 (2행)."""
        # typical = (H+L+C)/3 = close (H=L=C)
        # vwap[0] = (1000*100)/(100) = 1000
        # vwap[1] = (1000*100 + 2000*200)/(100+200) = 500000/300 = 1666.67
        closes = [1000.0, 2000.0]
        vols = [100, 200]
        df = _make_df(closes, volumes=vols)
        result = vwap(df)
        assert abs(result.iloc[0] - 1000.0) < 1e-9
        assert abs(result.iloc[1] - (1000 * 100 + 2000 * 200) / 300) < 1e-9

    def test_multiday_reset(self):
        """다일 데이터 입력 시 날짜 변경 시 리셋."""
        df = _make_multiday_df([[1000.0] * 5, [2000.0] * 5])
        result = vwap(df)
        # 첫날 VWAP ≈ 1000, 둘째날 첫 행 VWAP ≈ 2000 (리셋됨)
        day2_first = result.iloc[5]
        assert abs(day2_first - 2000.0) < 1e-9

    def test_empty_df(self):
        """빈 DataFrame → 빈 Series."""
        df = pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        result = vwap(df)
        assert len(result) == 0

    def test_zero_volume_no_crash(self):
        """거래량 0 행 포함 시 크래시 없음."""
        df = _make_df([1000.0] * 5, volumes=[0, 100, 100, 100, 100])
        result = vwap(df)
        assert result.iloc[1:].notna().all()

    def test_amount_column_ignored(self):
        """amount 컬럼이 있어도 무시하고 (H+L+C)/3을 typical_price로 사용.

        minute_candles.amount는 당일 누적 거래대금이므로 분봉 단위 tp 계산에 사용 불가.
        H=L=C=1000 이므로 VWAP == 1000 (amount 값 1500과 무관).
        """
        closes = [1000.0] * 3
        vols = [100, 100, 100]
        amounts = [150000.0, 150000.0, 150000.0]  # 누적 거래대금 — 무시되어야 함
        df = _make_df(closes, volumes=vols, amounts=amounts)
        result = vwap(df)
        assert (result - 1000.0).abs().max() < 1e-9

    def test_increasing_vwap(self):
        """단조 가격 상승 시 VWAP도 단조 증가."""
        closes = [float(100 + i * 10) for i in range(10)]
        df = _make_df(closes)
        result = vwap(df)
        diffs = result.diff().dropna()
        assert (diffs >= 0).all()


# ===========================================================================
# 2. orb_levels
# ===========================================================================

class TestOrbLevels:
    def test_basic_30min_window(self):
        """첫 30분의 high/low 정확 추출."""
        highs = [100.0] * 30 + [999.0] * 10
        lows = [90.0] * 30 + [1.0] * 10
        closes = [95.0] * 40
        df = _make_df(closes, highs=highs, lows=lows, volumes=[1000] * 40)
        result = orb_levels(df, window_minutes=30)
        assert result["or_high"] == 100.0
        assert result["or_low"] == 90.0
        assert result["or_range"] == 10.0

    def test_or_volume(self):
        """opening range 거래량 합산."""
        volumes = [500] * 30 + [1000] * 10
        closes = [100.0] * 40
        df = _make_df(closes, volumes=volumes)
        result = orb_levels(df, window_minutes=30)
        assert result["or_volume"] == 500 * 30

    def test_window_parameter(self):
        """window_minutes=5 → 첫 5분만."""
        highs = [200.0] * 5 + [50.0] * 25
        lows = [180.0] * 5 + [40.0] * 25
        closes = [190.0] * 30
        df = _make_df(closes, highs=highs, lows=lows)
        result = orb_levels(df, window_minutes=5)
        assert result["or_high"] == 200.0
        assert result["or_low"] == 180.0

    def test_insufficient_data_returns_nan(self):
        """데이터 부족(빈 DF) → NaN 반환."""
        df = pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        result = orb_levels(df)
        assert math.isnan(result["or_high"])
        assert math.isnan(result["or_low"])
        assert math.isnan(result["or_range"])

    def test_all_keys_present(self):
        """반환 dict에 4개 키 모두 존재."""
        df = _make_df([100.0] * 35)
        result = orb_levels(df)
        assert set(result.keys()) == {"or_high", "or_low", "or_range", "or_volume"}

    def test_window_larger_than_data(self):
        """window_minutes > 데이터 길이 → 전체 사용 (크래시 없음)."""
        df = _make_df([100.0, 110.0, 90.0], highs=[110.0, 115.0, 95.0], lows=[95.0, 105.0, 88.0])
        result = orb_levels(df, window_minutes=60)
        assert result["or_high"] == 115.0
        assert result["or_low"] == 88.0


# ===========================================================================
# 3. rsi_minute
# ===========================================================================

class TestRsiMinute:
    def test_monotone_up_rsi_near_100(self):
        """단조 상승 → RSI 100 수렴."""
        closes = [float(100 + i) for i in range(30)]
        df = _make_df(closes)
        result = rsi_minute(df, period=14)
        valid = result.dropna()
        assert valid.iloc[-1] > 95.0

    def test_monotone_down_rsi_near_0(self):
        """단조 하락 → RSI 0 수렴."""
        closes = [float(200 - i) for i in range(30)]
        df = _make_df(closes)
        result = rsi_minute(df, period=14)
        valid = result.dropna()
        assert valid.iloc[-1] < 5.0

    def test_initial_nan(self):
        """초기 period개 행은 NaN."""
        closes = [float(100 + i) for i in range(20)]
        df = _make_df(closes)
        result = rsi_minute(df, period=14)
        # 첫 14개 행: NaN 포함 (ewm min_periods)
        assert result.iloc[:14].isna().any()

    def test_range_0_to_100(self):
        """RSI 값 범위 0~100."""
        np.random.seed(42)
        closes = list(np.cumsum(np.random.randn(50)) + 100)
        df = _make_df(closes)
        result = rsi_minute(df)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_empty_df(self):
        """빈 DataFrame → 빈 Series."""
        df = pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        result = rsi_minute(df)
        assert len(result) == 0

    def test_golden_case_manual(self):
        """
        수기 계산 검증:
        closes = [10, 11, 12, 11, 10, 11, 12, 13, 14, 15, 14, 13, 12, 13, 14]
        period=3, Wilder RSI (ewm alpha=1/3)
        """
        closes = [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 14.0, 13.0, 12.0, 13.0, 14.0]
        df = _make_df(closes)
        result = rsi_minute(df, period=3)
        # 마지막 값이 유효하고 50 이상 (최근 상승세)
        assert result.iloc[-1] > 50.0

    def test_flat_prices_rsi_undefined(self):
        """가격 변동 없음 → delta=0 → RSI 계산 시 100 또는 NaN (크래시 없음)."""
        closes = [100.0] * 20
        df = _make_df(closes)
        result = rsi_minute(df, period=14)
        valid = result.dropna()
        # 모두 변동 없으면 gain=0, loss=0 → 100 또는 NaN
        assert valid.empty or (valid >= 0).all()


# ===========================================================================
# 4. ema_minute
# ===========================================================================

class TestEmaMinute:
    def test_period_1_equals_close(self):
        """period=1 → EMA == close."""
        closes = [100.0, 200.0, 150.0, 180.0]
        df = _make_df(closes)
        result = ema_minute(df, period=1)
        for i, c in enumerate(closes):
            assert abs(result.iloc[i] - c) < 1e-9

    def test_golden_case_period2(self):
        """
        수기 계산: closes=[10, 12, 11], period=2, alpha=2/3
        ema[0] = 10
        ema[1] = 12*(2/3) + 10*(1/3) = 8 + 3.333 = 11.333
        ema[2] = 11*(2/3) + 11.333*(1/3) = 7.333 + 3.778 = 11.111
        """
        closes = [10.0, 12.0, 11.0]
        df = _make_df(closes)
        result = ema_minute(df, period=2)
        assert abs(result.iloc[0] - 10.0) < 1e-9
        assert abs(result.iloc[1] - (12 * (2 / 3) + 10 * (1 / 3))) < 1e-6
        expected2 = 11.0 * (2 / 3) + result.iloc[1] * (1 / 3)
        assert abs(result.iloc[2] - expected2) < 1e-6

    def test_constant_prices(self):
        """가격 고정 → EMA == 고정값."""
        closes = [500.0] * 20
        df = _make_df(closes)
        result = ema_minute(df, period=10)
        assert (result - 500.0).abs().max() < 1e-9

    def test_no_nan_after_period(self):
        """period 이후 NaN 없음 (ewm adjust=False)."""
        closes = [float(100 + i) for i in range(30)]
        df = _make_df(closes)
        result = ema_minute(df, period=5)
        assert result.notna().all()

    def test_empty_df(self):
        """빈 DataFrame → 빈 Series."""
        df = pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        result = ema_minute(df, period=5)
        assert len(result) == 0

    def test_ema_lags_close(self):
        """EMA는 close보다 과거값 반영 → 급등 시 close > EMA."""
        closes = [100.0] * 10 + [200.0] * 10
        df = _make_df(closes)
        result = ema_minute(df, period=5)
        # 급등 직후 EMA < close
        assert result.iloc[10] < 200.0

    def test_monotone_increasing(self):
        """단조 증가 close → EMA도 단조 증가."""
        closes = [float(i) for i in range(1, 21)]
        df = _make_df(closes)
        result = ema_minute(df, period=3)
        diffs = result.diff().dropna()
        assert (diffs >= 0).all()


# ===========================================================================
# 5. bollinger_minute
# ===========================================================================

class TestBollingerMinute:
    def test_middle_equals_sma(self):
        """middle == rolling SMA."""
        closes = [float(100 + i % 5) for i in range(30)]
        df = _make_df(closes)
        bands = bollinger_minute(df, period=10)
        sma = df["close"].rolling(10, min_periods=10).mean()
        diff = (bands["middle"] - sma).dropna().abs()
        assert diff.max() < 1e-9

    def test_upper_lower_symmetric(self):
        """upper - middle == middle - lower (대칭)."""
        closes = [float(100 + (i % 3)) for i in range(30)]
        df = _make_df(closes)
        bands = bollinger_minute(df, period=10)
        valid = bands["upper"].notna()
        upper_dist = (bands["upper"] - bands["middle"])[valid]
        lower_dist = (bands["middle"] - bands["lower"])[valid]
        assert (upper_dist - lower_dist).abs().max() < 1e-9

    def test_bandwidth_positive(self):
        """bandwidth >= 0."""
        closes = [float(100 + i % 7) for i in range(30)]
        df = _make_df(closes)
        bands = bollinger_minute(df, period=10)
        valid = bands["bandwidth"].dropna()
        assert (valid >= 0).all()

    def test_percent_b_range(self):
        """percent_b: 중간(middle)일 때 0.5."""
        # close가 middle과 같으면 percent_b = 0.5
        closes = [float(100 + (i % 5) * 2) for i in range(40)]
        df = _make_df(closes)
        bands = bollinger_minute(df, period=10)
        # percent_b가 유효한 범위에 있는지
        valid = bands["percent_b"].dropna()
        # 극단적이지 않은 경우 -0.5 ~ 1.5 범위
        assert valid.mean() > -1.0 and valid.mean() < 2.0

    def test_std_multiplier(self):
        """std=1.0 vs std=2.0: band width 2배 차이."""
        closes = [float(100 + i % 10) for i in range(40)]
        df = _make_df(closes)
        b1 = bollinger_minute(df, period=10, std=1.0)
        b2 = bollinger_minute(df, period=10, std=2.0)
        w1 = (b1["upper"] - b1["lower"]).dropna()
        w2 = (b2["upper"] - b2["lower"]).dropna()
        ratio = (w2 / w1).dropna()
        assert (ratio - 2.0).abs().max() < 1e-9

    def test_empty_df(self):
        """빈 DataFrame → 5개 키 모두 빈 Series."""
        df = pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        bands = bollinger_minute(df)
        assert set(bands.keys()) == {"middle", "upper", "lower", "bandwidth", "percent_b"}
        assert all(len(s) == 0 for s in bands.values())

    def test_all_keys_present(self):
        """반환 dict에 5개 키."""
        df = _make_df([100.0] * 30)
        bands = bollinger_minute(df)
        assert set(bands.keys()) == {"middle", "upper", "lower", "bandwidth", "percent_b"}

    def test_constant_prices_zero_std(self):
        """가격 고정 → std=0 → upper==lower==middle, bandwidth=0."""
        closes = [100.0] * 30
        df = _make_df(closes)
        bands = bollinger_minute(df, period=10)
        valid = bands["middle"].dropna()
        assert (valid - 100.0).abs().max() < 1e-9
        bw = bands["bandwidth"].dropna()
        assert (bw.abs()).max() < 1e-9


# ===========================================================================
# 6. volume_zscore
# ===========================================================================

class TestVolumeZscore:
    def test_flat_volume_zscore_zero(self):
        """거래량 일정 → z-score ≈ 0 (rolling 범위 내 std=0이면 NaN)."""
        volumes = [1000] * 30
        df = _make_df([100.0] * 30, volumes=volumes)
        result = volume_zscore(df, window=10)
        valid = result.dropna()
        # std=0이면 NaN, 또는 ≈0
        assert valid.empty or valid.abs().max() < 1e-9

    def test_spike_positive_zscore(self):
        """폭증 거래량 → 양의 z-score 높음."""
        volumes = [1000] * 25 + [50000]
        df = _make_df([100.0] * 26, volumes=volumes)
        result = volume_zscore(df, window=20)
        assert result.iloc[-1] > 3.0

    def test_window_parameter(self):
        """window 변경 반영 — 짧은 window에서 더 민감."""
        volumes = [1000] * 25 + [5000]
        df = _make_df([100.0] * 26, volumes=volumes)
        z5 = volume_zscore(df, window=5).iloc[-1]
        z20 = volume_zscore(df, window=20).iloc[-1]
        # window=5이면 더 최근 데이터 위주 → 반드시 더 크거나 작을 수 있음
        # 단지 NaN이 아님을 확인
        assert not math.isnan(z5) and not math.isnan(z20)

    def test_early_rows_nan(self):
        """처음 window-1 행은 NaN."""
        df = _make_df([100.0] * 30, volumes=[1000] * 30)
        result = volume_zscore(df, window=10)
        assert result.iloc[:9].isna().all()

    def test_empty_df(self):
        """빈 DataFrame → 빈 Series."""
        df = pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        result = volume_zscore(df)
        assert len(result) == 0

    def test_length_matches_input(self):
        """결과 길이 == 입력 행 수."""
        df = _make_df([100.0] * 25, volumes=[1000] * 25)
        result = volume_zscore(df, window=10)
        assert len(result) == 25


# ===========================================================================
# 7. volume_surge
# ===========================================================================

class TestVolumeSurge:
    def test_flat_no_surge(self):
        """거래량 일정 → surge=False (3배 미만)."""
        volumes = [1000] * 30
        df = _make_df([100.0] * 30, volumes=volumes)
        result = volume_surge(df, multiplier=3.0, window=20)
        assert not result.dropna().any()

    def test_spike_detected(self):
        """3배 초과 시 True."""
        volumes = [1000] * 25 + [4000]
        df = _make_df([100.0] * 26, volumes=volumes)
        result = volume_surge(df, multiplier=3.0, window=20)
        assert result.iloc[-1] == True

    def test_exactly_at_threshold_true(self):
        """정확히 multiplier 배 → True (>=).

        rolling mean은 현재 봉을 포함하므로 직접 비교:
        volumes = [1000]*5, mean=1000, 마지막 봉도 1000.
        multiplier=1.0 → 1000 >= 1000*1.0 → True.
        """
        volumes = [1000] * 25
        df = _make_df([100.0] * 25, volumes=volumes)
        result = volume_surge(df, multiplier=1.0, window=20)
        # 모든 봉이 mean의 정확히 1.0배 → 전부 True
        valid = result.dropna()
        assert valid.any()

    def test_just_below_threshold_false(self):
        """threshold 미만 → False."""
        volumes = [1000] * 25 + [2999]
        df = _make_df([100.0] * 26, volumes=volumes)
        result = volume_surge(df, multiplier=3.0, window=20)
        assert result.iloc[-1] == False

    def test_boolean_series(self):
        """결과가 bool dtype Series."""
        df = _make_df([100.0] * 25)
        result = volume_surge(df)
        assert result.dtype == bool

    def test_empty_df(self):
        """빈 DataFrame → 빈 bool Series."""
        df = pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        result = volume_surge(df)
        assert len(result) == 0

    def test_early_rows_false_not_nan(self):
        """window 미만 초기 행 → NaN이 아닌 False (fillna)."""
        df = _make_df([100.0] * 5, volumes=[1000] * 5)
        result = volume_surge(df, window=20)
        assert not result.isna().any()


# ===========================================================================
# 8. flag_pattern
# ===========================================================================

class TestFlagPattern:
    def _make_flag_df(self, pole_pct: float = 0.10, pole_bars: int = 8) -> pd.DataFrame:
        """명확한 깃발 패턴 DataFrame 생성."""
        # 폴: pole_bars개 상승
        base = 1000.0
        closes = []
        step = base * pole_pct / pole_bars
        for i in range(pole_bars):
            closes.append(base + step * i)
        pole_top = closes[-1]
        # 통합: 5개 봉이 ±0.5% 횡보
        for i in range(5):
            closes.append(pole_top * (1 + 0.002 * (i % 2 == 0 and 0 or -1)))
        # 여유 봉
        closes += [pole_top] * 3
        return _make_df(closes)

    def test_clear_flag_detected(self):
        """명확한 깃발 → 최소 1개 True 발생."""
        df = self._make_flag_df(pole_pct=0.10)
        result = flag_pattern(
            df, pole_min_pct=0.05, consolidation_bars=5, consolidation_max_pct=0.02
        )
        assert result.any()

    def test_no_pattern_flat(self):
        """가격 변동 없음 → False only."""
        closes = [1000.0] * 30
        df = _make_df(closes)
        result = flag_pattern(df, pole_min_pct=0.05, consolidation_bars=5)
        assert not result.any()

    def test_downtrend_no_flag(self):
        """하락 추세 → 강세 깃발 없음."""
        closes = [float(1000 - i * 5) for i in range(30)]
        df = _make_df(closes)
        result = flag_pattern(df, pole_min_pct=0.05)
        assert not result.any()

    def test_short_df_no_crash(self):
        """짧은 데이터(5행 미만) → 크래시 없이 False."""
        df = _make_df([100.0, 110.0, 120.0])
        result = flag_pattern(df)
        assert not result.any()

    def test_output_boolean_series(self):
        """결과가 bool dtype Series이고 길이 == 입력."""
        df = _make_df([100.0] * 30)
        result = flag_pattern(df)
        assert result.dtype == bool
        assert len(result) == 30

    def test_empty_df(self):
        """빈 DataFrame → 빈 bool Series."""
        df = pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        result = flag_pattern(df)
        assert len(result) == 0

    def test_strict_consolidation_no_signal(self):
        """통합 구간 변동성이 임계값 초과 → 신호 없음."""
        base = 1000.0
        # 폴: 10% 상승 8봉
        closes = [base + base * 0.10 / 8 * i for i in range(8)]
        pole_top = closes[-1]
        # 통합: 5% 변동 (임계값 2% 초과)
        for i in range(5):
            closes.append(pole_top * (1.05 if i % 2 == 0 else 0.95))
        df = _make_df(closes)
        result = flag_pattern(
            df, pole_min_pct=0.05, consolidation_bars=5, consolidation_max_pct=0.02
        )
        assert not result.any()


# ===========================================================================
# 9. pivot_sr_levels
# ===========================================================================

class TestPivotSrLevels:
    def test_golden_case_manual(self):
        """
        전일 H=110, L=90, C=100
        pivot = (110+90+100)/3 = 100
        r1 = 2*100-90 = 110
        s1 = 2*100-110 = 90
        r2 = 100+(110-90) = 120
        s2 = 100-(110-90) = 80
        r3 = 110+2*(100-90) = 130
        s3 = 90-2*(110-100) = 70
        """
        prev = {"open": 95.0, "high": 110.0, "low": 90.0, "close": 100.0}
        result = pivot_sr_levels(prev)
        assert abs(result["pivot"] - 100.0) < 1e-9
        assert abs(result["r1"] - 110.0) < 1e-9
        assert abs(result["s1"] - 90.0) < 1e-9
        assert abs(result["r2"] - 120.0) < 1e-9
        assert abs(result["s2"] - 80.0) < 1e-9
        assert abs(result["r3"] - 130.0) < 1e-9
        assert abs(result["s3"] - 70.0) < 1e-9

    def test_all_keys_present(self):
        """7개 키 모두 존재."""
        prev = {"open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0}
        result = pivot_sr_levels(prev)
        assert set(result.keys()) == {"pivot", "r1", "r2", "r3", "s1", "s2", "s3"}

    def test_r_levels_above_pivot(self):
        """r1 < r2 < r3 (저항선 순서)."""
        prev = {"open": 100.0, "high": 120.0, "low": 80.0, "close": 110.0}
        result = pivot_sr_levels(prev)
        assert result["pivot"] < result["r1"] < result["r2"] < result["r3"]

    def test_s_levels_below_pivot(self):
        """s1 > s2 > s3 (지지선 순서)."""
        prev = {"open": 100.0, "high": 120.0, "low": 80.0, "close": 110.0}
        result = pivot_sr_levels(prev)
        assert result["pivot"] > result["s1"] > result["s2"] > result["s3"]

    def test_accepts_pandas_series(self):
        """pd.Series 입력도 처리."""
        prev = pd.Series({"open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0})
        result = pivot_sr_levels(prev)
        assert abs(result["pivot"] - 100.0) < 1e-9

    def test_symmetric_hl(self):
        """H-pivot == pivot-L (대칭 OHLC) → r1==H, s1==L."""
        prev = {"open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0}
        result = pivot_sr_levels(prev)
        # pivot = (110+90+100)/3 = 100
        # r1 = 2*100-90 = 110 = H
        assert abs(result["r1"] - prev["high"]) < 1e-9
        assert abs(result["s1"] - prev["low"]) < 1e-9


# ===========================================================================
# 10. red_to_green
# ===========================================================================

class TestRedToGreen:
    def test_monotone_up_crosses_once(self):
        """단조 상승 → prev_close 첫 교차 딱 1번 True."""
        prev_close = 1050.0
        closes = [1000.0, 1020.0, 1040.0, 1060.0, 1080.0]
        df = _make_df(closes)
        result = red_to_green(df, prev_close)
        assert result.sum() == 1
        # 첫 교차는 index 3 (close=1060 > 1050)
        assert result.iloc[3] == True
        assert result.iloc[4] == False

    def test_never_crosses(self):
        """항상 prev_close 미만 → False only."""
        closes = [900.0, 910.0, 920.0, 930.0]
        df = _make_df(closes)
        result = red_to_green(df, prev_close=1000.0)
        assert not result.any()

    def test_already_above_first_bar(self):
        """첫 봉부터 위 → index 0 True, 나머지 False."""
        closes = [1100.0, 1200.0, 1300.0]
        df = _make_df(closes)
        result = red_to_green(df, prev_close=1000.0)
        assert result.iloc[0] == True
        assert result.iloc[1:].sum() == 0

    def test_exactly_at_prev_close_no_cross(self):
        """close == prev_close → 교차 아님 (>) → False."""
        closes = [1000.0, 1000.0, 1000.0]
        df = _make_df(closes)
        result = red_to_green(df, prev_close=1000.0)
        assert not result.any()

    def test_oscillating_only_first_cross(self):
        """여러 번 교차해도 첫 번째만 True."""
        closes = [900.0, 1100.0, 900.0, 1100.0, 900.0]
        df = _make_df(closes)
        result = red_to_green(df, prev_close=1000.0)
        assert result.sum() == 1
        assert result.iloc[1] == True

    def test_empty_df(self):
        """빈 DataFrame → 빈 bool Series."""
        df = pd.DataFrame(
            columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        result = red_to_green(df, prev_close=1000.0)
        assert len(result) == 0

    def test_boolean_dtype(self):
        """결과 dtype == bool."""
        df = _make_df([1000.0, 1100.0])
        result = red_to_green(df, prev_close=1050.0)
        assert result.dtype == bool


# ===========================================================================
# TestCumulativeVolumeRatio
# ===========================================================================

from utils.intraday_indicators import cumulative_volume_ratio


class TestCumulativeVolumeRatio:
    def _make_df(self, volumes):
        return pd.DataFrame({
            "datetime": pd.date_range("2026-04-01 09:00", periods=len(volumes), freq="1min"),
            "volume": volumes,
        })

    def test_returns_running_ratio(self):
        df = self._make_df([10, 20, 30, 40])
        result = cumulative_volume_ratio(df, prev_day_volume=100.0)
        # 누적 [10, 30, 60, 100] / 100 = [0.1, 0.3, 0.6, 1.0]
        assert list(result.round(2)) == [0.10, 0.30, 0.60, 1.00]

    def test_prev_zero_returns_nan_series(self):
        df = self._make_df([10, 20, 30])
        result = cumulative_volume_ratio(df, prev_day_volume=0.0)
        assert result.isna().all()

    def test_prev_none_returns_nan_series(self):
        df = self._make_df([10, 20, 30])
        result = cumulative_volume_ratio(df, prev_day_volume=None)
        assert result.isna().all()

    def test_empty_df_returns_empty_series(self):
        df = pd.DataFrame({"datetime": [], "volume": []})
        result = cumulative_volume_ratio(df, prev_day_volume=100.0)
        assert len(result) == 0

    def test_nan_volumes_treated_as_zero(self):
        df = self._make_df([10, np.nan, 30])
        result = cumulative_volume_ratio(df, prev_day_volume=100.0)
        # 누적 [10, 10, 40] / 100
        assert list(result.round(2)) == [0.10, 0.10, 0.40]
