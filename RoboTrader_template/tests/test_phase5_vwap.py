"""
tests/test_phase5_vwap.py — VWAP 시그널 단위 테스트
=====================================================

카탈로그: reports/10pct_strategy/phase5_signals/03_trendlines_sr.md (F-01)
          reports/10pct_strategy/phase5_signals/04_flow.md (F-32/F-33)

테스트 목록:
  [기본 계산]
  - test_intraday_vwap_single_day_basic           : 3분봉 수동 계산 정확성
  - test_intraday_vwap_first_bar_equals_typical   : 첫 분봉 vwap == typical_price
  - test_intraday_vwap_close_only                 : high/low 없이 close만으로 계산

  [No Look-Ahead]
  - test_no_lookahead_truncation_invariant        : 마지막 N분봉 잘라내도 직전 값 불변

  [점심 시간]
  - test_lunch_time_zero_volume_no_change         : volume=0 행 VWAP 불변 확인

  [다일 리셋]
  - test_multiday_reset                           : 일자 변경 시 cumsum 독립 리셋
  - test_multiday_no_cross_contamination          : 전일 분봉이 익일 VWAP에 영향 없음

  [vwap_position]
  - test_vwap_position_above_below_equal          : +1/-1/0 반환 검증
  - test_vwap_position_all_above                  : 전체 close > vwap → 전부 +1

  [vwap_bands]
  - test_vwap_bands_symmetric                     : upper/lower 대칭 확인
  - test_vwap_bands_first_bar_zero_std            : 첫 분봉 std=0 → upper==lower==vwap
  - test_vwap_bands_n_sigma_scaling               : n_sigma 2배 → 밴드 폭 2배

  [anchored_vwap]
  - test_anchored_vwap_before_anchor_is_nan       : anchor_dt 이전 행 NaN
  - test_anchored_vwap_after_anchor_accumulates   : anchor 이후 누적 계산
  - test_anchored_vwap_all_before_returns_nan     : 모든 행이 anchor 이전 → 전부 NaN

  [엣지 케이스]
  - test_empty_dataframe                          : 빈 DataFrame → 빈 Series
  - test_single_row                               : 1행 데이터
  - test_zero_volume_entire_day                   : 하루 전체 volume=0 → NaN
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.signals.vwap import (
    anchored_vwap,
    intraday_vwap,
    vwap_bands,
    vwap_position,
)


# ============================================================================
# 픽스처 헬퍼
# ============================================================================

def _make_minute_df(
    minutes: list[str],
    closes: list[float],
    volumes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
    """테스트용 분봉 DataFrame 생성."""
    dts = pd.to_datetime(minutes)
    data = {"dt": dts, "close": closes, "volume": volumes}
    if highs is not None:
        data["high"] = highs
    if lows is not None:
        data["low"] = lows
    return pd.DataFrame(data)


def _typical(h: float, l: float, c: float) -> float:
    return (h + l + c) / 3.0


# ============================================================================
# 기본 계산 테스트
# ============================================================================

class TestIntradayVwapBasic:

    def test_single_day_basic(self):
        """3분봉 수동 계산과 일치해야 한다."""
        # 09:00: H=101, L=99, C=100, V=1000  → tp=100.0
        # 09:01: H=103, L=101, C=102, V=2000 → tp=102.0
        # 09:02: H=105, L=103, C=104, V=1500 → tp=104.0
        df = _make_minute_df(
            ["2024-01-02 09:00", "2024-01-02 09:01", "2024-01-02 09:02"],
            closes=[100.0, 102.0, 104.0],
            volumes=[1000, 2000, 1500],
            highs=[101.0, 103.0, 105.0],
            lows=[99.0, 101.0, 103.0],
        )
        vwap = intraday_vwap(df)

        # 수동 계산
        tp0, tp1, tp2 = 100.0, 102.0, 104.0
        v0, v1, v2 = 1000, 2000, 1500
        expected_0 = (tp0 * v0) / v0
        expected_1 = (tp0 * v0 + tp1 * v1) / (v0 + v1)
        expected_2 = (tp0 * v0 + tp1 * v1 + tp2 * v2) / (v0 + v1 + v2)

        assert vwap[0] == pytest.approx(expected_0, rel=1e-9)
        assert vwap[1] == pytest.approx(expected_1, rel=1e-9)
        assert vwap[2] == pytest.approx(expected_2, rel=1e-9)

    def test_first_bar_equals_typical_price(self):
        """첫 분봉: vwap == typical_price."""
        df = _make_minute_df(
            ["2024-01-02 09:00"],
            closes=[100.0],
            volumes=[5000],
            highs=[105.0],
            lows=[95.0],
        )
        vwap = intraday_vwap(df)
        expected_tp = _typical(105.0, 95.0, 100.0)
        assert vwap.iloc[0] == pytest.approx(expected_tp, rel=1e-9)

    def test_close_only_no_high_low(self):
        """high/low 컬럼 없으면 close=typical_price로 계산해야 한다."""
        df = pd.DataFrame({
            "dt": pd.to_datetime(["2024-01-02 09:00", "2024-01-02 09:01"]),
            "close": [100.0, 200.0],
            "volume": [1000, 1000],
        })
        vwap = intraday_vwap(df)
        expected_0 = 100.0
        expected_1 = (100.0 * 1000 + 200.0 * 1000) / 2000
        assert vwap.iloc[0] == pytest.approx(expected_0)
        assert vwap.iloc[1] == pytest.approx(expected_1)


# ============================================================================
# No Look-Ahead (PIT-safe) 테스트
# ============================================================================

class TestNoLookAhead:

    def test_truncation_invariant(self):
        """마지막 N분봉 잘라내도 직전 분 VWAP 불변 — No Look-Ahead 핵심 검증."""
        # 10분봉 생성
        minutes = [f"2024-01-02 09:{i:02d}" for i in range(10)]
        closes  = [100.0 + i for i in range(10)]
        volumes = [1000 + i * 100 for i in range(10)]
        highs   = [c + 1 for c in closes]
        lows    = [c - 1 for c in closes]

        df_full = _make_minute_df(minutes, closes, volumes, highs, lows)
        vwap_full = intraday_vwap(df_full)

        # 마지막 3행 잘라서 재계산
        df_cut = df_full.iloc[:-3].copy()
        vwap_cut = intraday_vwap(df_cut)

        # 잘라낸 이전 행들은 완전히 동일해야 한다
        for idx in range(len(df_cut)):
            assert vwap_cut.iloc[idx] == pytest.approx(
                vwap_full.iloc[idx], rel=1e-9
            ), f"행 {idx}: 풀={vwap_full.iloc[idx]:.6f}, 컷={vwap_cut.iloc[idx]:.6f}"

    def test_no_lookahead_multiday(self):
        """다일 데이터에서도 잘라내기 불변 — 일자 경계 검증."""
        # 2일 × 5분봉
        minutes = (
            [f"2024-01-02 09:0{i}" for i in range(5)]
            + [f"2024-01-03 09:0{i}" for i in range(5)]
        )
        closes  = list(range(100, 110))
        volumes = [1000] * 10
        highs   = [c + 2 for c in closes]
        lows    = [c - 2 for c in closes]

        df_full = _make_minute_df(minutes, closes, volumes, highs, lows)
        vwap_full = intraday_vwap(df_full)

        df_cut = df_full.iloc[:-2].copy()
        vwap_cut = intraday_vwap(df_cut)

        for idx in range(len(df_cut)):
            assert vwap_cut.iloc[idx] == pytest.approx(vwap_full.iloc[idx], rel=1e-9)


# ============================================================================
# 점심 시간 처리 테스트
# ============================================================================

class TestLunchTime:

    def test_zero_volume_bars_do_not_change_vwap(self):
        """점심 시간(volume=0) 행에서 VWAP가 변하지 않아야 한다."""
        df = _make_minute_df(
            [
                "2024-01-02 11:59",  # 점심 직전
                "2024-01-02 12:00",  # 점심 (volume=0)
                "2024-01-02 12:30",  # 점심 (volume=0)
                "2024-01-02 13:01",  # 점심 후 재개
            ],
            closes=[100.0, 99.0, 98.0, 102.0],
            volumes=[2000, 0, 0, 3000],
            highs=[101.0, 100.0, 99.0, 103.0],
            lows=[99.0, 98.0, 97.0, 101.0],
        )
        vwap = intraday_vwap(df)

        # 점심 전 VWAP
        vwap_before_lunch = vwap.iloc[0]

        # 점심 중 VWAP는 이전과 동일해야 한다 (volume=0 기여 없음)
        assert vwap.iloc[1] == pytest.approx(vwap_before_lunch, rel=1e-9), \
            "12:00 volume=0 행에서 VWAP가 변했음"
        assert vwap.iloc[2] == pytest.approx(vwap_before_lunch, rel=1e-9), \
            "12:30 volume=0 행에서 VWAP가 변했음"

        # 점심 후 거래 재개 시 VWAP 변동
        assert vwap.iloc[3] != pytest.approx(vwap_before_lunch, rel=1e-2), \
            "13:01 거래 재개 후에도 VWAP가 변하지 않음"

    def test_zero_volume_entire_day(self):
        """하루 전체 volume=0이면 VWAP는 NaN."""
        df = _make_minute_df(
            ["2024-01-02 09:00", "2024-01-02 09:01"],
            closes=[100.0, 101.0],
            volumes=[0, 0],
        )
        vwap = intraday_vwap(df)
        assert vwap.isna().all(), "전체 volume=0인데 NaN이 아닌 값이 있음"


# ============================================================================
# 다일 리셋 테스트
# ============================================================================

class TestMultidayReset:

    def test_daily_reset(self):
        """일자 변경 시 cumsum이 독립 리셋되어야 한다."""
        # 1일차: 09:00 high=200, low=200, close=200, volume=1
        # 2일차: 09:00 high=100, low=100, close=100, volume=1
        # 2일차 VWAP는 100 (전일 값 200이 누적되면 안됨)
        df = _make_minute_df(
            ["2024-01-02 09:00", "2024-01-03 09:00"],
            closes=[200.0, 100.0],
            volumes=[1, 1],
            highs=[200.0, 100.0],
            lows=[200.0, 100.0],
        )
        vwap = intraday_vwap(df)

        assert vwap.iloc[0] == pytest.approx(200.0, rel=1e-9), "1일차 VWAP 오류"
        assert vwap.iloc[1] == pytest.approx(100.0, rel=1e-9), \
            f"2일차 VWAP가 전일 값을 누적함: {vwap.iloc[1]}"

    def test_multiday_no_cross_contamination(self):
        """전일 분봉의 가격/거래량이 익일 VWAP에 영향을 주지 않아야 한다."""
        # 1일차: 3분봉 (가격 1000)
        # 2일차: 3분봉 (가격 500)
        day1 = [f"2024-01-02 09:0{i}" for i in range(3)]
        day2 = [f"2024-01-03 09:0{i}" for i in range(3)]

        df = _make_minute_df(
            day1 + day2,
            closes=[1000.0] * 3 + [500.0] * 3,
            volumes=[10000] * 3 + [10000] * 3,
            highs=[1010.0] * 3 + [510.0] * 3,
            lows=[990.0] * 3 + [490.0] * 3,
        )
        vwap = intraday_vwap(df)

        # 2일차 VWAP는 모두 ~500이어야 한다 (1000 누적 없음)
        for i in [3, 4, 5]:
            assert vwap.iloc[i] == pytest.approx(500.0, abs=1.0), \
                f"2일차 {i}번째 행 VWAP={vwap.iloc[i]:.2f} — 전일 오염 의심"


# ============================================================================
# vwap_position 테스트
# ============================================================================

class TestVwapPosition:

    def test_above_below_equal(self):
        """close > vwap → +1, close < vwap → -1, close == vwap → 0."""
        # 첫 분봉: close=100, tp=100 → vwap=100, pos=0
        # 두 번째: close=110, tp=100 이후 높은 tp로 vwap는 100~110 사이
        # 설계: high=low=close=100으로 tp=close, vwap=close → 첫 행은 항상 0
        df = _make_minute_df(
            ["2024-01-02 09:00", "2024-01-02 09:01", "2024-01-02 09:02"],
            closes=[100.0, 200.0, 50.0],
            volumes=[1000, 1000, 1000],
            highs=[100.0, 200.0, 50.0],
            lows=[100.0, 200.0, 50.0],
        )
        # 수동 계산: tp=close (high==low==close)
        # vwap[0] = 100 → close=100 → pos=0
        # vwap[1] = (100*1000+200*1000)/2000 = 150 → close=200 > 150 → +1
        # vwap[2] = (100*1000+200*1000+50*1000)/3000 = 116.67 → close=50 < 116.67 → -1
        pos = vwap_position(df)
        assert pos.iloc[0] == 0
        assert pos.iloc[1] == 1
        assert pos.iloc[2] == -1

    def test_all_above_vwap(self):
        """close가 항상 vwap보다 높은 데이터 → 모두 +1 (첫 행 제외 0)."""
        # 첫 분봉은 항상 vwap==close → pos=0
        df = _make_minute_df(
            ["2024-01-02 09:00", "2024-01-02 09:01", "2024-01-02 09:02"],
            closes=[100.0, 1000.0, 1000.0],  # 첫 행 이후 close >> vwap
            volumes=[1, 10000, 10000],
            highs=[100.0, 1000.0, 1000.0],
            lows=[100.0, 1000.0, 1000.0],
        )
        pos = vwap_position(df)
        # 행 1, 2는 +1이어야 함
        assert pos.iloc[1] == 1
        assert pos.iloc[2] == 1


# ============================================================================
# vwap_bands 테스트
# ============================================================================

class TestVwapBands:

    def test_bands_symmetric_around_vwap(self):
        """upper - vwap == vwap - lower (대칭)."""
        df = _make_minute_df(
            [f"2024-01-02 09:{i:02d}" for i in range(5)],
            closes=[100.0, 102.0, 98.0, 105.0, 97.0],
            volumes=[1000, 1500, 800, 2000, 600],
            highs=[102.0, 104.0, 100.0, 107.0, 99.0],
            lows=[98.0, 100.0, 96.0, 103.0, 95.0],
        )
        upper, lower = vwap_bands(df, n_sigma=1.0)
        vwap = intraday_vwap(df)

        valid = vwap.notna() & upper.notna() & lower.notna()
        diff_upper = (upper[valid] - vwap[valid]).round(9)
        diff_lower = (vwap[valid] - lower[valid]).round(9)
        pd.testing.assert_series_equal(diff_upper, diff_lower, check_names=False)

    def test_first_bar_zero_std(self):
        """첫 분봉 std=0 → upper == lower == vwap."""
        df = _make_minute_df(
            ["2024-01-02 09:00"],
            closes=[100.0],
            volumes=[1000],
            highs=[105.0],
            lows=[95.0],
        )
        upper, lower = vwap_bands(df, n_sigma=1.0)
        vwap = intraday_vwap(df)
        assert upper.iloc[0] == pytest.approx(vwap.iloc[0], rel=1e-9)
        assert lower.iloc[0] == pytest.approx(vwap.iloc[0], rel=1e-9)

    def test_n_sigma_scaling(self):
        """n_sigma=2 → 밴드 폭이 n_sigma=1의 2배."""
        df = _make_minute_df(
            [f"2024-01-02 09:{i:02d}" for i in range(6)],
            closes=[100.0, 105.0, 95.0, 110.0, 90.0, 100.0],
            volumes=[1000] * 6,
            highs=[106.0, 111.0, 101.0, 116.0, 96.0, 106.0],
            lows=[94.0, 99.0, 89.0, 104.0, 84.0, 94.0],
        )
        upper1, lower1 = vwap_bands(df, n_sigma=1.0)
        upper2, lower2 = vwap_bands(df, n_sigma=2.0)

        vwap = intraday_vwap(df)
        valid = vwap.notna() & upper1.notna() & upper2.notna()

        width1 = (upper1[valid] - lower1[valid]).values
        width2 = (upper2[valid] - lower2[valid]).values

        # 2σ 폭은 1σ 폭의 2배
        np.testing.assert_allclose(width2, width1 * 2, rtol=1e-9)


# ============================================================================
# anchored_vwap 테스트
# ============================================================================

class TestAnchoredVwap:

    def test_before_anchor_is_nan(self):
        """anchor_dt 이전 행은 NaN이어야 한다."""
        df = _make_minute_df(
            ["2024-01-02 09:00", "2024-01-02 09:30", "2024-01-02 10:00"],
            closes=[100.0, 110.0, 120.0],
            volumes=[1000, 2000, 1500],
        )
        anchor = pd.Timestamp("2024-01-02 09:30")
        avwap = anchored_vwap(df, anchor_dt=anchor)

        assert np.isnan(avwap.iloc[0]), "anchor 이전 행이 NaN이 아님"
        assert avwap.iloc[1] == pytest.approx(110.0, rel=1e-9), \
            "anchor 시점 첫 행 VWAP 오류"

    def test_after_anchor_accumulates(self):
        """anchor 이후 분봉은 anchor 기준 누적 VWAP을 가져야 한다."""
        df = _make_minute_df(
            ["2024-01-02 09:00", "2024-01-02 09:01", "2024-01-02 09:02"],
            closes=[100.0, 200.0, 300.0],
            volumes=[1000, 1000, 1000],
            highs=[100.0, 200.0, 300.0],
            lows=[100.0, 200.0, 300.0],
        )
        # anchor = 09:01 (두 번째 분봉부터)
        anchor = pd.Timestamp("2024-01-02 09:01")
        avwap = anchored_vwap(df, anchor_dt=anchor)

        assert np.isnan(avwap.iloc[0]), "anchor 이전 행이 NaN이 아님"
        # 09:01: avwap = 200
        assert avwap.iloc[1] == pytest.approx(200.0, rel=1e-9)
        # 09:02: avwap = (200*1000+300*1000)/2000 = 250
        assert avwap.iloc[2] == pytest.approx(250.0, rel=1e-9)

    def test_all_before_anchor_returns_all_nan(self):
        """모든 행이 anchor_dt 이전이면 전부 NaN."""
        df = _make_minute_df(
            ["2024-01-02 09:00", "2024-01-02 09:01"],
            closes=[100.0, 101.0],
            volumes=[1000, 1000],
        )
        future_anchor = pd.Timestamp("2099-01-01 09:00")
        avwap = anchored_vwap(df, anchor_dt=future_anchor)
        assert avwap.isna().all(), "먼 미래 anchor인데 NaN이 아닌 값이 있음"


# ============================================================================
# 엣지 케이스
# ============================================================================

class TestEdgeCases:

    def test_empty_dataframe(self):
        """빈 DataFrame → 빈 Series 반환."""
        df = pd.DataFrame(columns=["dt", "high", "low", "close", "volume"])
        vwap = intraday_vwap(df)
        assert len(vwap) == 0

    def test_single_row(self):
        """1행 데이터는 vwap = typical_price."""
        df = _make_minute_df(
            ["2024-01-02 09:00"],
            closes=[150.0],
            volumes=[500],
            highs=[155.0],
            lows=[145.0],
        )
        vwap = intraday_vwap(df)
        expected = _typical(155.0, 145.0, 150.0)
        assert len(vwap) == 1
        assert vwap.iloc[0] == pytest.approx(expected, rel=1e-9)

    def test_missing_required_column_raises(self):
        """필수 컬럼(close 또는 volume) 없으면 ValueError."""
        df = pd.DataFrame({"dt": pd.to_datetime(["2024-01-02 09:00"]), "close": [100.0]})
        with pytest.raises(ValueError, match="필수 컬럼 누락"):
            intraday_vwap(df)

    def test_index_preserved(self):
        """반환 Series의 index가 입력 DataFrame index와 동일해야 한다."""
        df = _make_minute_df(
            ["2024-01-02 09:00", "2024-01-02 09:01"],
            closes=[100.0, 101.0],
            volumes=[1000, 1000],
        )
        df.index = [10, 20]  # 비표준 index
        vwap = intraday_vwap(df)
        assert list(vwap.index) == [10, 20]
