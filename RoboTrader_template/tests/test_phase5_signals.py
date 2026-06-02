"""
test_phase5_signals.py — Phase 5 시그널 단위 테스트
====================================================

테스트 대상:
- lib/signals/flow.py: obv(), cmf()
- lib/signals/trend.py: ma_alignment_score()

테스트 목록:
  [OBV]
  - test_obv_no_lookahead       : 마지막 N행 절단 후 직전 행 결과 불변
  - test_obv_basic              : 상승/하락일 +/-volume 누적 기본 동작
  - test_obv_flat               : 종가 보합일 OBV 변화 없음
  - test_obv_nan_handling       : NaN 포함 시 누적값 전파
  - test_obv_multistock_boundary: 종목 경계에서 OBV 누출 없음

  [CMF]
  - test_cmf_no_lookahead       : 마지막 N행 절단 후 직전 행 결과 불변
  - test_cmf_basic_range        : CMF 값 범위 -1 ~ +1
  - test_cmf_initial_nan        : window 미만 초기 구간 NaN
  - test_cmf_positive_signal    : 완전 상승 봉 → CMF 양수
  - test_cmf_negative_signal    : 완전 하락 봉 → CMF 음수
  - test_cmf_high_low_equal     : high==low 시 MFM=0 처리 (NaN 없음)
  - test_cmf_multistock_boundary: 종목 경계 누출 없음
  - test_cmf_window_param       : window 파라미터 커스텀 (10일)
  - test_cmf_invalid_window     : window < 1 → ValueError

  [MA Alignment Score]
  - test_ma_score_no_lookahead  : 마지막 N행 절단 후 직전 행 결과 불변
  - test_ma_score_perfect_bull  : 완만한 상승 추세 → 완전 정배열 score=1.0
  - test_ma_score_perfect_bear  : 완만한 하락 추세 → 완전 역배열 score=0.0
  - test_ma_score_partial       : 부분 정배열 score 0<score<1
  - test_ma_score_initial_nan   : max(mas)일 미만 초기 구간 NaN
  - test_ma_score_custom_mas    : 커스텀 mas=[5,20,60] 작동
  - test_ma_score_invalid_mas   : mas 1개 → ValueError
  - test_ma_score_multistock    : 종목별 독립 계산
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.signals.flow import cmf, obv
from lib.signals.trend import ma_alignment_score


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

def _make_ohlcv(
    n_rows: int = 100,
    n_stocks: int = 3,
    trend: float = 0.5,
    seed: int = 42,
) -> pd.DataFrame:
    """OHLCV 가짜 시계열 DataFrame.

    columns: stock_code, date, open, high, low, close, volume
    날짜 오름차순 정렬, 종목별 n_rows행.

    Parameters
    ----------
    trend : float
        양수이면 상승 추세, 음수이면 하락 추세. 0이면 횡보.
    """
    rng = np.random.default_rng(seed)
    records = []
    base_date = pd.Timestamp("2023-01-01")

    for s in range(n_stocks):
        code = f"S{s:03d}"
        # 추세를 가진 종가 생성
        noise = rng.normal(0, 1.0, n_rows)
        close_vals = 10_000 + np.cumsum(noise + trend)
        close_vals = np.abs(close_vals) + 5_000  # 음수 방지

        for i in range(n_rows):
            c = close_vals[i]
            spread = abs(rng.normal(0, 50))
            h = c + spread
            l = max(c - spread, 1.0)
            o = rng.uniform(l, h)
            vol = int(rng.integers(100_000, 1_000_000))
            records.append({
                "stock_code": code,
                "date": base_date + pd.Timedelta(days=i),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": vol,
            })

    df = pd.DataFrame(records).sort_values(["stock_code", "date"]).reset_index(drop=True)
    return df


def _make_simple_ohlcv(closes: list[float], highs: list[float] = None,
                        lows: list[float] = None, volumes: list[int] = None) -> pd.DataFrame:
    """단일 종목 간단 OHLCV DataFrame 생성 헬퍼."""
    n = len(closes)
    if highs is None:
        highs = [c + 10 for c in closes]
    if lows is None:
        lows = [max(c - 10, 1) for c in closes]
    if volumes is None:
        volumes = [1000] * n

    return pd.DataFrame({
        "stock_code": ["A"] * n,
        "date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


# =============================================================================
# OBV 테스트
# =============================================================================

class TestOBV:
    """obv() 함수 단위 테스트."""

    def test_obv_no_lookahead(self):
        """핵심 회귀 테스트: 마지막 50행 절단 후 직전 행 결과 불변."""
        df = _make_ohlcv(n_rows=200, n_stocks=3)
        n_cut = 50

        result_full = obv(df)

        df_cut = df.iloc[:-n_cut].copy().reset_index(drop=True)
        result_cut = obv(df_cut)

        # 절단 전 앞 부분과 일치해야 함
        expected = result_full.iloc[:-n_cut].reset_index(drop=True)
        assert_series_equal(
            result_cut,
            expected,
            check_names=False,
            check_dtype=False,
            atol=1e-6,
        )

    def test_obv_basic(self):
        """상승일 +volume, 하락일 -volume 기본 누적 검증."""
        # close: 100 → 110 (상승) → 105 (하락) → 105 (보합)
        df = _make_simple_ohlcv(
            closes=[100.0, 110.0, 105.0, 105.0],
            volumes=[1000, 2000, 1500, 500],
        )
        result = obv(df)

        assert result.iloc[0] == 0.0,    "첫 행은 0 (기준값)"
        assert result.iloc[1] == 2000.0, "상승일: +2000"
        assert result.iloc[2] == 500.0,  "하락일: 2000 - 1500 = 500"
        assert result.iloc[3] == 500.0,  "보합일: 변화 없음"

    def test_obv_flat(self):
        """종가 보합(전일과 동일) 시 OBV 변화 없음."""
        df = _make_simple_ohlcv(
            closes=[100.0, 100.0, 100.0, 100.0],
            volumes=[1000, 2000, 3000, 4000],
        )
        result = obv(df)
        assert (result == 0.0).all(), "보합 연속 시 OBV = 0 유지"

    def test_obv_nan_handling(self):
        """NaN 종가/거래량 시 이전 OBV 값 전파.

        row 0: close=100, OBV=0 (기준)
        row 1: close=NaN → 이전 OBV(0) 전파
        row 2: close=110, prev_close=NaN → 비교 불가 → 이전 OBV(0) 전파
        (NaN과의 비교는 항상 False — 방어적 처리)
        """
        df = _make_simple_ohlcv(
            closes=[100.0, np.nan, 110.0],
            volumes=[1000, 2000, 3000],
        )
        result = obv(df)
        assert result.iloc[0] == 0.0
        assert result.iloc[1] == 0.0, "NaN close → 이전 OBV 전파"
        # row 2: prev_close=NaN → isnan(prev_c) 조건 → 이전 값(0) 전파
        assert result.iloc[2] == 0.0, "prev_close=NaN → OBV 이전값 전파"

    def test_obv_multistock_boundary(self):
        """종목 경계에서 OBV가 다른 종목으로 누출되지 않음."""
        df = _make_ohlcv(n_rows=50, n_stocks=3, seed=7)

        result = obv(df)

        # 각 종목의 첫 행은 OBV = 0이어야 함 (기준값)
        first_rows = df.groupby("stock_code").head(1).index
        assert (result.loc[first_rows] == 0.0).all(), \
            "각 종목 첫 행 OBV는 0 (기준값)"


# =============================================================================
# CMF 테스트
# =============================================================================

class TestCMF:
    """cmf() 함수 단위 테스트."""

    def test_cmf_no_lookahead(self):
        """핵심 회귀 테스트: 마지막 50행 절단 후 직전 행 결과 불변."""
        df = _make_ohlcv(n_rows=200, n_stocks=3)
        n_cut = 50
        window = 20

        result_full = cmf(df, window=window)

        df_cut = df.iloc[:-n_cut].copy().reset_index(drop=True)
        result_cut = cmf(df_cut, window=window)

        expected = result_full.iloc[:-n_cut].reset_index(drop=True)
        assert_series_equal(
            result_cut,
            expected,
            check_names=False,
            check_dtype=False,
            atol=1e-9,
        )

    def test_cmf_basic_range(self):
        """CMF 값이 항상 -1 ~ +1 범위 내에 있어야 함."""
        df = _make_ohlcv(n_rows=200, n_stocks=2)
        result = cmf(df, window=20)
        valid = result.dropna()
        assert (valid >= -1.0).all(), f"CMF 최솟값 {valid.min():.4f} < -1"
        assert (valid <= 1.0).all(),  f"CMF 최댓값 {valid.max():.4f} > 1"

    def test_cmf_initial_nan(self):
        """초기 window-1 행은 NaN이어야 함."""
        window = 10
        n = 30
        df = _make_simple_ohlcv(
            closes=[100.0 + i for i in range(n)],
            highs=[102.0 + i for i in range(n)],
            lows=[98.0 + i for i in range(n)],
        )
        result = cmf(df, window=window)

        # 앞 (window-1)행은 NaN
        assert result.iloc[:window - 1].isna().all(), \
            f"초기 {window-1}행이 NaN이어야 함"
        # window번째 행부터는 값이 있어야 함
        assert pd.notna(result.iloc[window - 1]), \
            f"행 {window-1}은 NaN이 아니어야 함"

    def test_cmf_positive_signal(self):
        """종가가 고가와 동일 (완전 상승 봉) → MFM = 1 → CMF 양수."""
        # MFM = (2*close - high - low) / (high - low)
        # close = high이면: (2*high - high - low)/(high-low) = (high-low)/(high-low) = 1
        n = 30
        closes = [100.0 + i for i in range(n)]
        highs = closes  # close == high
        lows = [c - 10 for c in closes]
        volumes = [1000] * n

        df = _make_simple_ohlcv(closes=closes, highs=highs, lows=lows, volumes=volumes)
        result = cmf(df, window=20)

        valid = result.dropna()
        assert (valid > 0).all(), f"완전 상승 봉 → CMF > 0, got min={valid.min():.4f}"

    def test_cmf_negative_signal(self):
        """종가가 저가와 동일 (완전 하락 봉) → MFM = -1 → CMF 음수."""
        # close = low이면: (2*low - high - low)/(high-low) = (low-high)/(high-low) = -1
        n = 30
        lows = [100.0 + i for i in range(n)]
        closes = lows  # close == low
        highs = [c + 10 for c in lows]
        volumes = [1000] * n

        df = _make_simple_ohlcv(closes=closes, highs=highs, lows=lows, volumes=volumes)
        result = cmf(df, window=20)

        valid = result.dropna()
        assert (valid < 0).all(), f"완전 하락 봉 → CMF < 0, got max={valid.max():.4f}"

    def test_cmf_high_low_equal(self):
        """high == low (데이터 이상) 시 NaN 없이 0으로 처리."""
        n = 25
        c = 100.0
        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2024-01-01", periods=n),
            "open": [c] * n,
            "high": [c] * n,  # high == low == close
            "low":  [c] * n,
            "close": [c] * n,
            "volume": [1000] * n,
        })
        result = cmf(df, window=20)

        # window 이상 구간에서 NaN 없어야 함 (0으로 처리됨)
        valid = result.iloc[19:]
        assert not valid.isna().any(), "high==low 구간에서 NaN 없어야 함"
        assert (valid == 0.0).all(), "MFM=0이므로 CMF=0"

    def test_cmf_multistock_boundary(self):
        """종목 경계에서 CMF가 다른 종목으로 누출되지 않음."""
        # 두 종목 완전 반대 특성
        n = 30
        # 종목 A: 완전 상승 봉 → CMF 양수
        df_a = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2024-01-01", periods=n),
            "open": [100.0] * n,
            "high": [110.0 + i for i in range(n)],
            "low":  [90.0 + i for i in range(n)],
            "close": [110.0 + i for i in range(n)],  # close == high
            "volume": [1000] * n,
        })
        # 종목 B: 완전 하락 봉 → CMF 음수
        df_b = pd.DataFrame({
            "stock_code": ["B"] * n,
            "date": pd.date_range("2024-01-01", periods=n),
            "open": [100.0] * n,
            "high": [110.0 + i for i in range(n)],
            "low":  [90.0 + i for i in range(n)],
            "close": [90.0 + i for i in range(n)],   # close == low
            "volume": [1000] * n,
        })
        df = pd.concat([df_a, df_b], ignore_index=True)
        df = df.sort_values(["stock_code", "date"]).reset_index(drop=True)

        result = cmf(df, window=20)

        a_vals = result[df["stock_code"] == "A"].dropna()
        b_vals = result[df["stock_code"] == "B"].dropna()

        assert (a_vals > 0).all(), "종목 A (상승 봉) → CMF > 0"
        assert (b_vals < 0).all(), "종목 B (하락 봉) → CMF < 0"

    def test_cmf_window_param(self):
        """window=10 커스텀 파라미터 — 앞 9행 NaN, 10번째부터 값."""
        df = _make_ohlcv(n_rows=50, n_stocks=1)
        result = cmf(df, window=10)
        assert result.iloc[:9].isna().all(), "window=10: 앞 9행 NaN"
        assert pd.notna(result.iloc[9]),     "window=10: 10번째 행 값 존재"

    def test_cmf_invalid_window(self):
        """window < 1 → ValueError."""
        df = _make_ohlcv(n_rows=30, n_stocks=1)
        with pytest.raises(ValueError, match="window=0 < 1"):
            cmf(df, window=0)


# =============================================================================
# MA Alignment Score 테스트
# =============================================================================

class TestMAAlignmentScore:
    """ma_alignment_score() 함수 단위 테스트."""

    def test_ma_score_no_lookahead(self):
        """핵심 회귀 테스트: 마지막 50행 절단 후 직전 행 결과 불변."""
        # max(mas)=120 이상의 데이터 필요
        n = 300
        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2022-01-01", periods=n, freq="B"),
            "close": [100 + i * 0.2 for i in range(n)],  # 완만한 상승
        })
        n_cut = 50
        mas = [5, 20, 60, 120]  # 240 대신 120으로 데이터 절약

        result_full = ma_alignment_score(df, mas=mas)

        df_cut = df.iloc[:-n_cut].copy().reset_index(drop=True)
        result_cut = ma_alignment_score(df_cut, mas=mas)

        expected = result_full.iloc[:-n_cut].reset_index(drop=True)
        assert_series_equal(
            result_cut,
            expected,
            check_names=False,
            check_dtype=False,
            atol=1e-9,
        )

    def test_ma_score_perfect_bull(self):
        """완만한 상승 추세 → 충분한 시간 경과 후 완전 정배열 score=1.0."""
        n = 350
        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2022-01-01", periods=n, freq="B"),
            "close": [100 + i * 0.5 for i in range(n)],  # 강한 상승 추세
        })
        score = ma_alignment_score(df, mas=[5, 20, 60, 120, 240])

        # 240일 데이터가 쌓인 후 최근 행들은 완전 정배열이어야 함
        recent = score.iloc[-10:].dropna()
        assert (recent == 1.0).all(), \
            f"강한 상승 추세 후 score=1.0 기대, got min={recent.min():.3f}"

    def test_ma_score_perfect_bear(self):
        """강한 하락 추세 → 충분한 시간 경과 후 완전 역배열 score=0.0."""
        n = 350
        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2022-01-01", periods=n, freq="B"),
            "close": [50_000 - i * 20 for i in range(n)],  # 강한 하락
        })
        score = ma_alignment_score(df, mas=[5, 20, 60, 120, 240])

        recent = score.iloc[-10:].dropna()
        assert (recent == 0.0).all(), \
            f"강한 하락 추세 후 score=0.0 기대, got max={recent.max():.3f}"

    def test_ma_score_partial(self):
        """부분 정배열: 0 < score < 1.

        MA3개(5,20,60) → 2쌍: (5>20), (20>60).
        시나리오: 완만한 상승 추세 + 마지막 5일 소폭 조정.
        충분히 짧은 조정이므로 MA5만 MA20 아래로 살짝 역전,
        MA20은 MA60 위 유지 → score = 0.5.
        """
        # 검증된 시나리오: 수동으로 MAs 계산 후 score 확인
        # 방법: 긴 상승 후 딱 5일 소폭 하락 → MA5 역전만 유도
        n = 120
        # 기본 상승 115일, 마지막 5일 소폭 하락
        trend_up  = [1000 + i * 10.0 for i in range(115)]
        # 마지막 5일: 작은 하락으로 MA5를 MA20 아래로
        last_close = trend_up[-1]  # 2140
        trend_down = [last_close - i * 50.0 for i in range(1, 6)]
        closes = trend_up + trend_down

        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2022-01-01", periods=n, freq="B"),
            "close": closes,
        })
        score = ma_alignment_score(df, mas=[5, 20, 60])

        last = score.dropna().iloc[-1]
        # MA5 역전 여부를 직접 확인
        g = df.groupby("stock_code")
        ma5  = g["close"].transform(lambda x: x.rolling(5,  min_periods=5).mean()).iloc[-1]
        ma20 = g["close"].transform(lambda x: x.rolling(20, min_periods=20).mean()).iloc[-1]
        ma60 = g["close"].transform(lambda x: x.rolling(60, min_periods=60).mean()).iloc[-1]
        ma5_reversed = ma5 < ma20
        ma20_above60 = ma20 > ma60
        assert ma5_reversed,   f"MA5 역전 안됨: MA5={ma5:.1f}, MA20={ma20:.1f}"
        assert ma20_above60,   f"MA20이 MA60 아래: MA20={ma20:.1f}, MA60={ma60:.1f}"
        assert 0.0 < last < 1.0, \
            f"부분 정배열이어야 함: 0 < score < 1, got {last:.3f}"

    def test_ma_score_initial_nan(self):
        """max(mas)일 미만 초기 구간은 NaN이어야 함.

        NaN 엄격 전파(skipna=False): 가장 긴 MA(max_ma)가 충족되지 않으면
        해당 쌍이 NaN → 전체 score NaN.
        따라서 앞 max_ma-1 행이 NaN이어야 함.
        """
        mas = [5, 20, 60]
        max_ma = max(mas)  # 60
        n = max_ma + 10    # 70행

        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2023-01-01", periods=n, freq="D"),
            "close": [100 + i for i in range(n)],
        })
        score = ma_alignment_score(df, mas=mas)

        # 앞 max_ma-1 = 59행은 NaN (max MA rolling min_periods 미충족)
        assert score.iloc[:max_ma - 1].isna().all(), \
            f"앞 {max_ma - 1}행이 NaN이어야 함, got:\n{score.iloc[:max_ma - 1]}"
        # max_ma-1 번째 행 (0-indexed: 59)부터 값이 있어야 함
        assert pd.notna(score.iloc[max_ma - 1]), \
            f"행 {max_ma - 1}은 값이 있어야 함, got {score.iloc[max_ma - 1]}"

    def test_ma_score_custom_mas(self):
        """커스텀 mas=[5, 20, 60] → 2쌍 검사, 정상 작동."""
        n = 100
        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2023-01-01", periods=n, freq="B"),
            "close": [100 + i * 0.5 for i in range(n)],
        })
        score = ma_alignment_score(df, mas=[5, 20, 60])

        valid = score.dropna()
        assert not valid.empty, "커스텀 mas 결과가 비어있음"
        assert (valid >= 0.0).all() and (valid <= 1.0).all(), \
            "score 범위 [0, 1] 위반"

    def test_ma_score_invalid_mas(self):
        """mas에 1개만 지정 → ValueError."""
        df = pd.DataFrame({
            "stock_code": ["A"] * 50,
            "date": pd.date_range("2023-01-01", periods=50),
            "close": [100.0] * 50,
        })
        with pytest.raises(ValueError, match="최소 2개 기간"):
            ma_alignment_score(df, mas=[5])

    def test_ma_score_multistock(self):
        """두 종목이 독립적으로 계산됨."""
        n = 300
        # 종목 A: 상승 추세
        df_a = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2022-01-01", periods=n, freq="B"),
            "close": [100 + i * 0.5 for i in range(n)],
        })
        # 종목 B: 하락 추세
        df_b = pd.DataFrame({
            "stock_code": ["B"] * n,
            "date": pd.date_range("2022-01-01", periods=n, freq="B"),
            "close": [50_000 - i * 10 for i in range(n)],
        })
        df = pd.concat([df_a, df_b], ignore_index=True)

        score = ma_alignment_score(df, mas=[5, 20, 60, 120])

        a_recent = score[df["stock_code"] == "A"].dropna().iloc[-5:]
        b_recent = score[df["stock_code"] == "B"].dropna().iloc[-5:]

        assert (a_recent == 1.0).all(), f"종목 A (상승): score=1.0 기대"
        assert (b_recent == 0.0).all(), f"종목 B (하락): score=0.0 기대"

    def test_ma_score_no_group_col(self):
        """group_col 없는 단일 시리즈 DataFrame도 처리 가능."""
        n = 100
        df = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=n, freq="B"),
            "close": [100 + i for i in range(n)],
        })
        # group_col 없으면 전체를 하나의 그룹으로 처리
        score = ma_alignment_score(df, mas=[5, 20, 60], group_col="stock_code")
        # group_col 없어도 에러 없이 작동해야 함
        assert isinstance(score, pd.Series)
