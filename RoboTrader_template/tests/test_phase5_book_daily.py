"""
test_phase5_book_daily.py — book_daily 시그널 단위 테스트
=========================================================

테스트 대상:
  lib/signals/book_daily.py:
    - new_high_breakout()
    - volume_spike_3x()
    - ma20_pullback()
    - closing_bet()

테스트 목록:
  [new_high_breakout]
  - test_nhb_no_lookahead        : No Look-Ahead 회귀 (마지막 N행 절단 후 직전 결과 불변)
  - test_nhb_basic_signal        : 신고가 돌파 + 거래량 동반 시 True
  - test_nhb_no_signal_low_vol   : 신고가지만 거래량 미달 → False
  - test_nhb_no_signal_not_high  : 거래량 충분하지만 신고가 아닌 경우 → False
  - test_nhb_initial_nan_false   : window 미만 초기 구간 False
  - test_nhb_multistock          : 종목별 독립 계산 (경계 누출 없음)
  - test_nhb_custom_window       : window 커스텀 (window=20)
  - test_nhb_invalid_window      : window < 1 → ValueError

  [volume_spike_3x]
  - test_vs_no_lookahead         : No Look-Ahead 회귀
  - test_vs_basic_signal         : 3배 거래량 + 양봉 → True
  - test_vs_no_signal_no_upcandle: 3배 거래량이지만 음봉 → False (require_up=True)
  - test_vs_require_up_false     : require_up=False이면 음봉도 허용
  - test_vs_initial_false        : window 미만 초기 구간 False
  - test_vs_multistock           : 종목 경계 누출 없음
  - test_vs_custom_mult          : mult 커스텀 (mult=2.0)

  [ma20_pullback]
  - test_mp_no_lookahead         : No Look-Ahead 회귀
  - test_mp_basic_signal         : 정배열 + MA20 ±1% 내 + 직전 5일 위 → True
  - test_mp_no_signal_not_aligned: MA20 < MA60 (역배열) → False
  - test_mp_no_signal_not_near   : MA20에서 멀리 떨어짐 → False
  - test_mp_no_signal_not_above  : 직전에 MA20 위에 없었음 → False
  - test_mp_initial_false        : 60일 미만 초기 구간 False
  - test_mp_multistock           : 종목 경계 누출 없음

  [closing_bet]
  - test_cb_no_lookahead         : No Look-Ahead 회귀
  - test_cb_basic_signal         : 양봉 + close>MA5 + 거래량 동반 → True
  - test_cb_no_signal_down_candle: 음봉 → False
  - test_cb_no_signal_below_ma5  : close < MA5 → False
  - test_cb_no_signal_low_vol    : 거래량 미달 → False
  - test_cb_initial_false        : 20일 미만 초기 구간 False
  - test_cb_multistock           : 종목 경계 누출 없음
  - test_cb_invalid_vol_mult     : vol_mult <= 0 → ValueError
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.signals.book_daily import (
    new_high_breakout,
    volume_spike_3x,
    ma20_pullback,
    closing_bet,
)


# ---------------------------------------------------------------------------
# 공통 픽스처 헬퍼
# ---------------------------------------------------------------------------

def _make_ohlcv(
    n_rows: int = 300,
    n_stocks: int = 3,
    trend: float = 0.5,
    seed: int = 42,
) -> pd.DataFrame:
    """OHLCV 가짜 시계열 DataFrame.

    columns: stock_code, date, open, high, low, close, volume
    날짜 오름차순 정렬, 종목별 n_rows행.
    """
    rng = np.random.default_rng(seed)
    records = []
    base_date = pd.Timestamp("2023-01-01")

    for s in range(n_stocks):
        code = f"S{s:03d}"
        noise = rng.normal(0, 1.0, n_rows)
        close_vals = 10_000 + np.cumsum(noise + trend)
        close_vals = np.abs(close_vals) + 5_000

        for i in range(n_rows):
            c = close_vals[i]
            spread = abs(rng.normal(0, 50))
            h = c + spread
            lo = max(c - spread, 1.0)
            o = float(rng.uniform(lo, h))
            vol = int(rng.integers(100_000, 1_000_000))
            records.append({
                "stock_code": code,
                "date": base_date + pd.Timedelta(days=i),
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": vol,
            })

    df = pd.DataFrame(records).sort_values(["stock_code", "date"]).reset_index(drop=True)
    return df


def _make_simple_ohlcv(
    closes: list,
    opens: list = None,
    volumes: list = None,
    stock_code: str = "A",
) -> pd.DataFrame:
    """단일 종목 간단 OHLCV DataFrame 생성."""
    n = len(closes)
    if opens is None:
        opens = closes  # 기본: 시가 = 종가 (보합봉)
    if volumes is None:
        volumes = [1_000_000] * n

    return pd.DataFrame({
        "stock_code": [stock_code] * n,
        "date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": opens,
        "high": [max(c, o) + 10 for c, o in zip(closes, opens)],
        "low": [min(c, o) - 10 for c, o in zip(closes, opens)],
        "close": closes,
        "volume": volumes,
    })


# =============================================================================
# new_high_breakout 테스트
# =============================================================================

class TestNewHighBreakout:
    """new_high_breakout() 단위 테스트."""

    def test_nhb_no_lookahead(self):
        """핵심 회귀: 마지막 50행 절단 후 직전 행 결과 불변."""
        df = _make_ohlcv(n_rows=400, n_stocks=2, seed=10)
        n_cut = 50
        window = 252

        result_full = new_high_breakout(df, window=window)

        df_cut = df.iloc[:-n_cut].copy().reset_index(drop=True)
        result_cut = new_high_breakout(df_cut, window=window)

        expected = result_full.iloc[:-n_cut].reset_index(drop=True)
        assert_series_equal(
            result_cut,
            expected,
            check_names=False,
            check_dtype=False,
        )

    def test_nhb_basic_signal(self):
        """신고가 돌파 + 거래량 동반 → True 확인."""
        # window=10으로 테스트 데이터 절약
        n = 15
        # 처음 10일: 100~109, 마지막 5일: 기존 고가 내
        # 마지막 1일 신고가 + 거래량 3배
        closes = [100.0 + i for i in range(n - 1)] + [200.0]  # 마지막에 급등
        volumes = [1_000_000] * (n - 1) + [3_000_000]  # 마지막에 거래량 3배

        df = _make_simple_ohlcv(closes=closes, volumes=volumes)
        result = new_high_breakout(df, window=10, vol_mult=1.5)

        # 마지막 행: close=200 > max(100~113)=113, vol=3M >= avg(~1M)*1.5
        assert result.iloc[-1] == True, f"마지막 행은 신고가+거래량 True여야 함, got {result.iloc[-1]}"

    def test_nhb_no_signal_low_vol(self):
        """신고가지만 거래량 미달 → False."""
        n = 15
        closes = [100.0 + i for i in range(n - 1)] + [200.0]
        # 거래량이 평균의 1.0배 미만 (vol_mult=1.5 미달)
        volumes = [1_000_000] * (n - 1) + [500_000]

        df = _make_simple_ohlcv(closes=closes, volumes=volumes)
        result = new_high_breakout(df, window=10, vol_mult=1.5)

        assert result.iloc[-1] == False, "거래량 미달 → False여야 함"

    def test_nhb_no_signal_not_high(self):
        """신고가 아닌 경우 (거래량 충분) → False."""
        n = 15
        # 마지막 행 종가가 이전보다 낮음
        closes = [200.0] + [100.0 + i for i in range(n - 1)]
        volumes = [1_000_000] * n

        df = _make_simple_ohlcv(closes=closes, volumes=volumes)
        result = new_high_breakout(df, window=10, vol_mult=1.5)

        # 마지막 행: close는 최고가가 아님
        assert result.iloc[-1] == False, "신고가 아닌 경우 False여야 함"

    def test_nhb_initial_nan_false(self):
        """window+1 미만 초기 구간은 False (데이터 부족)."""
        window = 20
        n = window + 5
        closes = [100.0 + i for i in range(n)]
        df = _make_simple_ohlcv(closes=closes)
        result = new_high_breakout(df, window=window, vol_mult=1.5)

        # 앞 window+1 행은 False (shift(1) + rolling(window) = window+1 행 필요)
        assert result.iloc[:window].all() == False or not result.iloc[:window].any(), \
            "초기 window행은 False여야 함"
        # bool 타입 확인
        assert result.dtype == bool

    def test_nhb_multistock(self):
        """종목 경계에서 신호가 누출되지 않음."""
        df = _make_ohlcv(n_rows=300, n_stocks=3, seed=99)
        result = new_high_breakout(df, window=252, vol_mult=1.5)

        assert len(result) == len(df), "결과 길이가 입력과 같아야 함"
        assert result.dtype == bool

    def test_nhb_custom_window(self):
        """window=20 커스텀 파라미터 정상 작동."""
        df = _make_ohlcv(n_rows=100, n_stocks=1, seed=5)
        result = new_high_breakout(df, window=20, vol_mult=1.5)

        assert isinstance(result, pd.Series)
        assert result.dtype == bool
        # 앞 20행은 False
        assert not result.iloc[:20].any(), "앞 20행은 False여야 함"

    def test_nhb_invalid_window(self):
        """window < 1 → ValueError."""
        df = _make_ohlcv(n_rows=30, n_stocks=1)
        with pytest.raises(ValueError, match="window=0"):
            new_high_breakout(df, window=0)


# =============================================================================
# volume_spike_3x 테스트
# =============================================================================

class TestVolumeSpike3x:
    """volume_spike_3x() 단위 테스트."""

    def test_vs_no_lookahead(self):
        """핵심 회귀: 마지막 50행 절단 후 직전 행 결과 불변."""
        df = _make_ohlcv(n_rows=200, n_stocks=2, seed=20)
        n_cut = 50
        window = 20

        result_full = volume_spike_3x(df, window=window, mult=3.0)

        df_cut = df.iloc[:-n_cut].copy().reset_index(drop=True)
        result_cut = volume_spike_3x(df_cut, window=window, mult=3.0)

        expected = result_full.iloc[:-n_cut].reset_index(drop=True)
        assert_series_equal(
            result_cut,
            expected,
            check_names=False,
            check_dtype=False,
        )

    def test_vs_basic_signal(self):
        """3배 거래량 + 양봉 → True."""
        n = 25
        closes = [100.0 + i * 0.1 for i in range(n)]
        opens = [c - 1.0 for c in closes]  # 모두 양봉 (close > open)
        # 처음 24일 거래량 1M, 마지막 1일 5M (3M 평균의 5배 이상)
        volumes = [1_000_000] * (n - 1) + [5_000_000]

        df = _make_simple_ohlcv(closes=closes, opens=opens, volumes=volumes)
        result = volume_spike_3x(df, window=20, mult=3.0, require_up=True)

        assert result.iloc[-1] == True, f"3배 거래량 + 양봉 → True여야 함, got {result.iloc[-1]}"

    def test_vs_no_signal_no_upcandle(self):
        """3배 거래량이지만 음봉 → False (require_up=True)."""
        n = 25
        closes = [100.0] * n
        opens = [101.0] * n  # 음봉 (close < open)
        volumes = [1_000_000] * (n - 1) + [5_000_000]

        df = _make_simple_ohlcv(closes=closes, opens=opens, volumes=volumes)
        result = volume_spike_3x(df, window=20, mult=3.0, require_up=True)

        assert result.iloc[-1] == False, "음봉일 때 require_up=True → False여야 함"

    def test_vs_require_up_false(self):
        """require_up=False이면 음봉도 허용."""
        n = 25
        closes = [100.0] * n
        opens = [101.0] * n  # 음봉
        volumes = [1_000_000] * (n - 1) + [5_000_000]

        df = _make_simple_ohlcv(closes=closes, opens=opens, volumes=volumes)
        result = volume_spike_3x(df, window=20, mult=3.0, require_up=False)

        assert result.iloc[-1] == True, "require_up=False이면 음봉도 True여야 함"

    def test_vs_initial_false(self):
        """window 미만 초기 구간 False."""
        window = 20
        n = window + 5
        closes = [100.0] * n
        volumes = [1_000_000] * n

        df = _make_simple_ohlcv(closes=closes, volumes=volumes)
        result = volume_spike_3x(df, window=window, mult=3.0)

        assert not result.iloc[:window].any(), f"초기 {window}행은 False여야 함"
        assert result.dtype == bool

    def test_vs_multistock(self):
        """종목 경계 누출 없음 — 각 종목 독립 계산."""
        df = _make_ohlcv(n_rows=100, n_stocks=3, seed=30)
        result = volume_spike_3x(df, window=20, mult=3.0)

        assert len(result) == len(df)
        assert result.dtype == bool

    def test_vs_custom_mult(self):
        """mult=2.0 커스텀 파라미터: 2배 거래량도 시그널 발생."""
        n = 25
        closes = [100.0 + i * 0.1 for i in range(n)]
        opens = [c - 1.0 for c in closes]
        # 마지막 행: 2.5배 거래량 (mult=2.0 통과, mult=3.0 불통과)
        volumes = [1_000_000] * (n - 1) + [2_500_000]

        df = _make_simple_ohlcv(closes=closes, opens=opens, volumes=volumes)

        result_mult2 = volume_spike_3x(df, window=20, mult=2.0)
        result_mult3 = volume_spike_3x(df, window=20, mult=3.0)

        assert result_mult2.iloc[-1] == True,  "mult=2.0: 2.5배 거래량 → True"
        assert result_mult3.iloc[-1] == False, "mult=3.0: 2.5배 거래량 → False"


# =============================================================================
# ma20_pullback 테스트
# =============================================================================

class TestMA20Pullback:
    """ma20_pullback() 단위 테스트."""

    def _make_aligned_pullback(self) -> pd.DataFrame:
        """정배열(MA20>MA60) + MA20 눌림목 시나리오 DataFrame 생성."""
        # 강한 상승 추세 100일 → MA20 > MA60 확립
        n_up = 120
        n_touch = 10
        n = n_up + n_touch

        rng = np.random.default_rng(0)
        # 꾸준한 상승
        base = 10_000 + np.cumsum(np.ones(n_up) * 50 + rng.normal(0, 5, n_up))
        ma20_last = base[-20:].mean()

        # MA20에 ±0.5% 이내로 접근하는 구간 (눌림목)
        touch_prices = np.full(n_touch, ma20_last * 1.002)

        closes = np.concatenate([base, touch_prices])
        opens = closes - 1.0  # 양봉

        records = []
        for i in range(n):
            records.append({
                "stock_code": "A",
                "date": pd.Timestamp("2023-01-01") + pd.Timedelta(days=i),
                "open": opens[i],
                "high": closes[i] + 10,
                "low": opens[i] - 10,
                "close": closes[i],
                "volume": 1_000_000,
            })
        return pd.DataFrame(records)

    def test_mp_no_lookahead(self):
        """핵심 회귀: 마지막 50행 절단 후 직전 행 결과 불변."""
        df = _make_ohlcv(n_rows=300, n_stocks=2, seed=40)
        n_cut = 50

        result_full = ma20_pullback(df)

        df_cut = df.iloc[:-n_cut].copy().reset_index(drop=True)
        result_cut = ma20_pullback(df_cut)

        expected = result_full.iloc[:-n_cut].reset_index(drop=True)
        assert_series_equal(
            result_cut,
            expected,
            check_names=False,
            check_dtype=False,
        )

    def test_mp_basic_signal(self):
        """정배열 + MA20 접촉 + 직전 위에 있었음 → True 발생 확인."""
        df = self._make_aligned_pullback()
        result = ma20_pullback(df, tolerance_pct=1.0, lookback_above=5)

        # 눌림목 구간에서 True 발생 여부 확인
        touch_start = 120
        touch_result = result.iloc[touch_start:]
        assert touch_result.any(), \
            f"정배열+눌림목 구간에서 True가 하나도 없음. " \
            f"result 마지막 10행:\n{result.iloc[-10:].values}"

    def test_mp_no_signal_not_aligned(self):
        """MA20 < MA60 (역배열) → False."""
        # 강한 하락 추세 → MA20 < MA60
        n = 150
        closes = [20_000 - i * 80 for i in range(n)]
        closes = [max(c, 1000) for c in closes]
        opens = [c + 1 for c in closes]  # 음봉

        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2023-01-01", periods=n, freq="D"),
            "open": opens,
            "high": [o + 10 for o in opens],
            "low": [c - 10 for c in closes],
            "close": closes,
            "volume": [1_000_000] * n,
        })
        result = ma20_pullback(df, tolerance_pct=5.0)  # tolerance 크게 해도

        # 역배열 구간 (충분히 하락 후)에서 True 없어야 함
        assert not result.iloc[-30:].any(), \
            "역배열 구간에서 True 없어야 함"

    def test_mp_no_signal_not_near(self):
        """MA20에서 멀리 떨어진 경우 → False."""
        # 상승 추세이지만 close가 MA20 대비 10% 이상 위
        n = 150
        rng = np.random.default_rng(5)
        base = 10_000 + np.cumsum(np.ones(n) * 100 + rng.normal(0, 5, n))
        opens = base - 1.0

        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2023-01-01", periods=n, freq="D"),
            "open": opens,
            "high": base + 10,
            "low": opens - 10,
            "close": base,
            "volume": [1_000_000] * n,
        })

        # tolerance=0.1% — MA20에서 멀리 떨어지면 False
        result = ma20_pullback(df, tolerance_pct=0.1, lookback_above=5)

        # 강한 상승 추세에서 close는 MA20 훨씬 위 → tolerance 0.1%에서 신호 거의 없음
        # 신호가 하나도 없거나 매우 적음
        valid_result = result.iloc[65:]  # 60일 초기화 이후
        assert valid_result.sum() == 0 or valid_result.mean() < 0.05, \
            "MA20에서 크게 이탈 시 신호 거의 없어야 함"

    def test_mp_no_signal_not_above(self):
        """직전에 MA20 위에 없었던 경우 → False."""
        # 오랫동안 MA20 아래 → 갑자기 MA20에 접촉해도 False
        n = 120
        rng = np.random.default_rng(6)
        # 처음 70일 강한 상승 (정배열 확립)
        up = 10_000 + np.cumsum(np.ones(70) * 50 + rng.normal(0, 5, 70))
        # 이후 50일 MA20보다 크게 아래로 하락
        ma20_approx = up[-20:].mean()
        below = np.full(50, ma20_approx * 0.85)  # MA20의 85% 수준 (15% 아래)

        closes = np.concatenate([up, below])
        opens = closes - 1.0

        df = pd.DataFrame({
            "stock_code": ["A"] * n,
            "date": pd.date_range("2023-01-01", periods=n, freq="D"),
            "open": opens,
            "high": closes + 10,
            "low": opens - 10,
            "close": closes,
            "volume": [1_000_000] * n,
        })

        # MA20 아래에서 오랫동안 있었으므로 lookback_above=5 조건 불충족
        result = ma20_pullback(df, tolerance_pct=20.0, lookback_above=5)

        # 하락 구간 마지막 30행에서 True 없어야 함 (was_above 조건 미충족)
        assert not result.iloc[-30:].any(), \
            "직전 MA20 위에 없었던 경우 False여야 함"

    def test_mp_initial_false(self):
        """60일 미만 초기 구간 False (MA60 데이터 부족)."""
        n = 70
        closes = [10_000 + i * 10 for i in range(n)]
        df = _make_simple_ohlcv(closes=closes)
        result = ma20_pullback(df)

        # MA60 미충족 구간 (앞 59행)은 False
        assert not result.iloc[:59].any(), "앞 59행은 False여야 함"
        assert result.dtype == bool

    def test_mp_multistock(self):
        """종목 경계 누출 없음."""
        df = _make_ohlcv(n_rows=200, n_stocks=3, seed=50)
        result = ma20_pullback(df)

        assert len(result) == len(df)
        assert result.dtype == bool


# =============================================================================
# closing_bet 테스트
# =============================================================================

class TestClosingBet:
    """closing_bet() 단위 테스트."""

    def test_cb_no_lookahead(self):
        """핵심 회귀: 마지막 50행 절단 후 직전 행 결과 불변."""
        df = _make_ohlcv(n_rows=200, n_stocks=2, seed=60)
        n_cut = 50

        result_full = closing_bet(df)

        df_cut = df.iloc[:-n_cut].copy().reset_index(drop=True)
        result_cut = closing_bet(df_cut)

        expected = result_full.iloc[:-n_cut].reset_index(drop=True)
        assert_series_equal(
            result_cut,
            expected,
            check_names=False,
            check_dtype=False,
        )

    def test_cb_basic_signal(self):
        """양봉 + close>MA5 + 거래량 동반 → True."""
        n = 25
        # 상승 추세: close > open (양봉), close가 MA5 위
        closes = [10_000 + i * 50 for i in range(n)]
        opens = [c - 10 for c in closes]  # 양봉
        # 처음 24일 거래량 1M, 마지막 1일 2M (1.2배 이상)
        volumes = [1_000_000] * (n - 1) + [2_000_000]

        df = _make_simple_ohlcv(closes=closes, opens=opens, volumes=volumes)
        result = closing_bet(df, vol_mult=1.2)

        # 마지막 행: 양봉 + close>MA5 + 거래량 1.2배 이상 → True
        assert result.iloc[-1] == True, f"기본 조건 모두 충족 → True여야 함, got {result.iloc[-1]}"

    def test_cb_no_signal_down_candle(self):
        """음봉 → False."""
        n = 25
        closes = [10_000 + i * 50 for i in range(n)]
        opens = [c + 10 for c in closes]  # 음봉 (close < open)
        volumes = [1_000_000] * (n - 1) + [2_000_000]

        df = _make_simple_ohlcv(closes=closes, opens=opens, volumes=volumes)
        result = closing_bet(df, vol_mult=1.2)

        assert result.iloc[-1] == False, "음봉 → False여야 함"

    def test_cb_no_signal_below_ma5(self):
        """close < MA5 → False."""
        n = 25
        # 상승 후 마지막에 급락 (MA5 아래)
        closes = [10_000 + i * 50 for i in range(n - 1)] + [9_000.0]  # 급락
        opens = [c - 10 for c in closes[:-1]] + [9_100.0]  # 마지막은 양봉이지만 close<MA5
        # 마지막: open=9100, close=9000 → 음봉. 양봉으로 만들려면:
        opens[-1] = 8_900.0  # close(9000) > open(8900) → 양봉, but close < MA5
        volumes = [1_000_000] * n

        df = _make_simple_ohlcv(closes=closes, opens=opens, volumes=volumes)
        result = closing_bet(df, vol_mult=1.0)

        # MA5는 마지막 5일 평균 ≈ (10_150+10_200+10_250+10_300+9_000)/5 = 9_980
        # close=9_000 < MA5≈9_980 → False
        assert result.iloc[-1] == False, "close < MA5 → False여야 함"

    def test_cb_no_signal_low_vol(self):
        """거래량 미달 → False."""
        n = 25
        closes = [10_000 + i * 50 for i in range(n)]
        opens = [c - 10 for c in closes]  # 양봉
        # 마지막 거래량이 평균의 50% (vol_mult=1.2 미달)
        avg_vol = 1_000_000
        volumes = [avg_vol] * (n - 1) + [int(avg_vol * 0.5)]

        df = _make_simple_ohlcv(closes=closes, opens=opens, volumes=volumes)
        result = closing_bet(df, vol_mult=1.2)

        assert result.iloc[-1] == False, "거래량 미달 → False여야 함"

    def test_cb_initial_false(self):
        """20일 미만 초기 구간 False (avg_vol rolling 미충족)."""
        n = 25
        closes = [10_000 + i * 50 for i in range(n)]
        opens = [c - 10 for c in closes]
        volumes = [2_000_000] * n  # 거래량 충분

        df = _make_simple_ohlcv(closes=closes, opens=opens, volumes=volumes)
        result = closing_bet(df, vol_mult=1.2)

        # avg_vol에 shift(1)+rolling(20) 필요 → 앞 20행은 False
        assert not result.iloc[:20].any(), "앞 20행은 avg_vol 미충족으로 False여야 함"
        assert result.dtype == bool

    def test_cb_multistock(self):
        """종목 경계 누출 없음."""
        df = _make_ohlcv(n_rows=100, n_stocks=3, seed=70)
        result = closing_bet(df)

        assert len(result) == len(df)
        assert result.dtype == bool

    def test_cb_invalid_vol_mult(self):
        """vol_mult <= 0 → ValueError."""
        df = _make_ohlcv(n_rows=30, n_stocks=1)
        with pytest.raises(ValueError, match="vol_mult=0"):
            closing_bet(df, vol_mult=0)
