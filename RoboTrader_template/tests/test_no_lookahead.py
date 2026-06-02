"""
No Look-Ahead 회귀 테스트 (Phase 0-P0-3)
==========================================

사장님 대원칙 ① PIT 강제 — "마지막 N행을 잘라내도 직전 행까지의 결과가
동일해야 함" 원칙을 코드로 잠급니다.

테스트 목록
-----------
- test_safe_lag_no_leak          : safe_lag — 마지막 50행 절단 후 재계산 시 결과 불변
- test_safe_lag_negative_raises  : safe_lag(n<0) → ValueError 즉시
- test_safe_lag_zero             : safe_lag(n=0) → 당일 값 그대로 (shift(0))
- test_safe_lag_multigroup       : 종목 경계에서 lag 가 다른 종목으로 넘어가지 않음
- test_pit_quantile_no_leak      : pit_quantile — 미래 행이 과거 분위에 영향 없음
- test_pit_quantile_cross_section: 같은 날짜 내 분위가 정확히 1~n_bins 범위
- test_forward_return_warning    : forward_return 호출 시 FutureLeakWarning 발생
- test_forward_return_correct    : forward_return 수치 정확성 (n=2 → 2일 후 수익률)
- test_forward_return_bad_n      : n_days < 1 → ValueError
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

# 테스트 대상 모듈
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.pit_helpers import FutureLeakWarning, forward_return, pit_quantile, safe_lag


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

def _make_ts(n_rows: int = 1000, n_stocks: int = 5, seed: int = 42) -> pd.DataFrame:
    """가짜 시계열 DataFrame 생성.

    columns: stock_code, date, close, volume, market_cap
    날짜 오름차순 정렬, 종목별 n_rows//n_stocks 행.
    """
    rng = np.random.default_rng(seed)
    rows_per_stock = n_rows // n_stocks

    records = []
    base_date = pd.Timestamp("2023-01-01")
    for s in range(n_stocks):
        code = f"S{s:03d}"
        prices = 10_000 + rng.normal(0, 200, rows_per_stock).cumsum()
        prices = np.abs(prices) + 5_000  # 음수 방지
        volumes = rng.integers(100_000, 1_000_000, rows_per_stock)
        caps = prices * rng.integers(1_000_000, 10_000_000, rows_per_stock)
        dates = [base_date + pd.Timedelta(days=i) for i in range(rows_per_stock)]
        for i in range(rows_per_stock):
            records.append(
                {
                    "stock_code": code,
                    "date": dates[i],
                    "close": prices[i],
                    "volume": int(volumes[i]),
                    "market_cap": float(caps[i]),
                }
            )

    df = pd.DataFrame(records).sort_values(["date", "stock_code"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# safe_lag 테스트
# ---------------------------------------------------------------------------

class TestSafeLag:
    """safe_lag 함수 테스트."""

    def test_safe_lag_no_leak(self):
        """핵심 회귀 테스트: 마지막 50행 절단 후 재계산해도 앞 행 결과 불변."""
        df = _make_ts(n_rows=1000)
        n_cut = 50

        # 전체 계산
        lag_full = safe_lag(df, "close", n=1)

        # 마지막 50행 제거 후 계산
        df_cut = df.iloc[:-n_cut].copy().reset_index(drop=True)
        lag_cut = safe_lag(df_cut, "close", n=1)

        # 잘라내기 전 앞 (1000-50=950)행과 일치해야 함
        expected = lag_full.iloc[:-n_cut].reset_index(drop=True)
        assert_series_equal(
            lag_cut,
            expected,
            check_names=False,
            check_dtype=False,
        )

    def test_safe_lag_negative_raises(self):
        """n < 0이면 ValueError를 즉시 발생시켜야 함."""
        df = _make_ts(n_rows=100)
        with pytest.raises(ValueError, match="n=-1 < 0 is NOT allowed"):
            safe_lag(df, "close", n=-1)

    def test_safe_lag_zero(self):
        """n=0이면 당일 값 그대로 반환 (shift(0) = identity)."""
        df = _make_ts(n_rows=100)
        lag0 = safe_lag(df, "close", n=0)
        assert_series_equal(lag0, df["close"], check_names=False)

    def test_safe_lag_multigroup_boundary(self):
        """종목 경계에서 lag가 다른 종목으로 넘어가지 않아야 함.

        S000의 마지막 행 다음이 S001의 첫 행이더라도
        S001의 lag(1) 첫 값은 NaN이어야 함.
        """
        df = _make_ts(n_rows=200, n_stocks=4)
        lag1 = safe_lag(df, "close", n=1)

        # 각 종목의 첫 행 index에서 lag=1 은 NaN이어야 함
        first_indices = df.groupby("stock_code").head(1).index
        assert lag1.loc[first_indices].isna().all(), (
            "Each stock's first row must be NaN after lag(1)"
        )

    def test_safe_lag_n2(self):
        """n=2 lag — 종목별 2행 앞 값과 일치."""
        df = _make_ts(n_rows=200, n_stocks=2)
        lag2 = safe_lag(df, "close", n=2)
        manual = df.groupby("stock_code", sort=False)["close"].shift(2)
        assert_series_equal(lag2, manual, check_names=False)


# ---------------------------------------------------------------------------
# pit_quantile 테스트
# ---------------------------------------------------------------------------

class TestPitQuantile:
    """pit_quantile 함수 테스트."""

    def test_pit_quantile_no_leak(self):
        """핵심 회귀 테스트: 미래 행 추가해도 과거 날짜 분위 불변."""
        df = _make_ts(n_rows=500)

        # 날짜 기준 상위 절반만 사용 (과거 절반)
        unique_dates = sorted(df["date"].unique())
        cutoff = unique_dates[len(unique_dates) // 2]
        df_past = df[df["date"] < cutoff].copy().reset_index(drop=True)

        # 전체 df로 계산
        q_full = pit_quantile(df, "market_cap", "date", n_bins=5)
        # 과거 절반만으로 계산
        q_past = pit_quantile(df_past, "market_cap", "date", n_bins=5)

        # 과거 날짜 구간에서 두 결과가 일치해야 함
        mask = df["date"] < cutoff
        full_past_portion = q_full[mask].reset_index(drop=True)
        assert_series_equal(
            q_past,
            full_past_portion,
            check_names=False,
            check_dtype=False,
        )

    def test_pit_quantile_cross_section_range(self):
        """각 날짜의 분위 값이 1 ~ n_bins 범위 안에 있어야 함."""
        df = _make_ts(n_rows=500)
        n_bins = 5
        q = pit_quantile(df, "market_cap", "date", n_bins=n_bins)

        valid = q.dropna()
        assert valid.min() >= 1, f"분위 최소값이 1 미만: {valid.min()}"
        assert valid.max() <= n_bins, f"분위 최대값이 {n_bins} 초과: {valid.max()}"

    def test_pit_quantile_no_future_influence(self):
        """미래 날짜의 시총이 과거 날짜 분위에 영향을 주지 않아야 함.

        마지막 날짜를 극단적으로 큰 값으로 바꿔도
        그 이전 날짜의 분위는 변하지 않아야 함.
        """
        df = _make_ts(n_rows=300, n_stocks=5)
        df2 = df.copy()

        last_date = df2["date"].max()
        # 마지막 날짜 종목들의 시총을 극단적으로 크게 변경
        df2.loc[df2["date"] == last_date, "market_cap"] = 1e15

        q_orig = pit_quantile(df, "market_cap", "date", n_bins=5)
        q_modified = pit_quantile(df2, "market_cap", "date", n_bins=5)

        # 마지막 날짜 이전의 분위는 동일해야 함
        mask_prev = df["date"] < last_date
        assert_series_equal(
            q_orig[mask_prev].reset_index(drop=True),
            q_modified[mask_prev].reset_index(drop=True),
            check_names=False,
            check_dtype=False,
        )


# ---------------------------------------------------------------------------
# forward_return 테스트
# ---------------------------------------------------------------------------

class TestForwardReturn:
    """forward_return 함수 테스트."""

    def test_forward_return_warning(self):
        """forward_return 호출 시 반드시 FutureLeakWarning이 발생해야 함.

        이 경고는 시그널 모듈에서 잘못 import 했을 때 조기 감지 역할.
        """
        df = _make_ts(n_rows=100, n_stocks=2)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _ = forward_return(df, "close", n_days=5)

        warning_types = [w.category for w in caught]
        assert FutureLeakWarning in warning_types, (
            "forward_return must emit FutureLeakWarning to signal its forbidden use "
            "in signal/filter modules."
        )

    def test_forward_return_correct(self):
        """n_days=2 → 2일 후 종가 기준 수익률 정확성 검증."""
        # 단순 단일 종목 DataFrame
        prices = [100.0, 110.0, 121.0, 133.1, 146.4]
        df_single = pd.DataFrame(
            {
                "stock_code": ["A"] * 5,
                "date": pd.date_range("2023-01-01", periods=5),
                "close": prices,
            }
        )

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            fwd = forward_return(df_single, "close", n_days=2)

        # 인덱스 0: close=100, 2일후=121 → (121/100)-1 = 0.21
        assert abs(fwd.iloc[0] - 0.21) < 1e-9, f"Expected 0.21, got {fwd.iloc[0]}"
        # 인덱스 1: close=110, 2일후=133.1 → (133.1/110)-1 ≈ 0.21
        assert abs(fwd.iloc[1] - (133.1 / 110.0 - 1.0)) < 1e-9
        # 마지막 2행은 NaN (미래 없음)
        assert pd.isna(fwd.iloc[-1])
        assert pd.isna(fwd.iloc[-2])

    def test_forward_return_bad_n(self):
        """n_days < 1이면 ValueError."""
        df = _make_ts(n_rows=50)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with pytest.raises(ValueError, match="n_days=0 < 1"):
                forward_return(df, "close", n_days=0)

    def test_forward_return_group_boundary(self):
        """종목 경계에서 forward return이 다른 종목 가격으로 넘어가지 않아야 함."""
        df = _make_ts(n_rows=200, n_stocks=4)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            fwd = forward_return(df, "close", n_days=3)

        # 각 종목의 마지막 3행은 NaN이어야 함
        last_indices = df.groupby("stock_code").tail(3).index
        assert fwd.loc[last_indices].isna().all(), (
            "Last 3 rows of each stock must be NaN in forward_return(n=3)"
        )
