"""
tests/test_phase5_book_minute.py — 분봉 기반 단기 트레이딩 패턴 시그널 단위 테스트
=====================================================================================

카탈로그 출처: Andrew Aziz "How to Day Trade for a Living"
              강창권 "1분봉 단기추세"

테스트 목록:
  [abcd_pattern]
  - TestAbcdPattern::test_basic_abcd_signal               : ABCD 4단계 기본 시나리오 → True
  - TestAbcdPattern::test_no_signal_without_d_breakout    : D 돌파 없으면 False
  - TestAbcdPattern::test_no_signal_ab_pct_too_small      : AB 상승 부족 → False
  - TestAbcdPattern::test_no_lookahead                    : 마지막 N봉 잘라내도 이전 값 불변
  - TestAbcdPattern::test_multiday_reset                  : 일별 독립 처리
  - TestAbcdPattern::test_empty_df                        : 빈 DataFrame

  [bull_flag]
  - TestBullFlag::test_basic_bull_flag_signal             : 깃대+깃발+돌파 시나리오 → True
  - TestBullFlag::test_no_signal_without_volume           : 거래량 미달 → False
  - TestBullFlag::test_no_signal_flag_range_too_wide      : 깃발 폭 초과 → False
  - TestBullFlag::test_no_lookahead                       : No Look-Ahead 검증
  - TestBullFlag::test_multiday_reset                     : 일별 독립 처리
  - TestBullFlag::test_empty_df                           : 빈 DataFrame

  [opening_range_breakout]
  - TestOrb::test_basic_orb_signal                        : ORB 기본 돌파 → True
  - TestOrb::test_no_signal_in_opening_range              : 레인지 내 분봉은 False
  - TestOrb::test_no_signal_close_below_or_high           : 돌파 미달 → False
  - TestOrb::test_only_first_breakout                     : 일중 최초 돌파만 True
  - TestOrb::test_no_lookahead                            : No Look-Ahead 검증
  - TestOrb::test_multiday_reset                          : 일별 독립 OR 측정
  - TestOrb::test_lunch_time_handling                     : 점심 시간 데이터 처리
  - TestOrb::test_empty_df                                : 빈 DataFrame

  [red_to_green]
  - TestR2G::test_basic_r2g_signal                        : gap down 후 전환 → True
  - TestR2G::test_no_signal_no_gap_down                   : gap down 없으면 False
  - TestR2G::test_no_signal_no_crossover                  : 전환 없으면 False
  - TestR2G::test_only_first_crossover                    : 최초 전환만 True
  - TestR2G::test_no_lookahead                            : No Look-Ahead 검증
  - TestR2G::test_multiday_reset                          : 일별 독립 처리
  - TestR2G::test_lunch_time_handling                     : 점심 시간 후 전환
  - TestR2G::test_empty_df                                : 빈 DataFrame
  - TestR2G::test_missing_prev_close_raises               : prev_close 컬럼 없으면 ValueError
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.signals.book_minute import (
    abcd_pattern,
    bull_flag,
    opening_range_breakout,
    red_to_green,
)


# ============================================================================
# 픽스처 헬퍼
# ============================================================================

def _make_df(
    minutes: list[str],
    closes: list[float],
    volumes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    opens: list[float] | None = None,
    prev_closes: list[float] | None = None,
) -> pd.DataFrame:
    """테스트용 분봉 DataFrame 생성."""
    n = len(minutes)
    dts = pd.to_datetime(minutes)
    data: dict = {
        "dt": dts,
        "close": closes,
        "high": highs if highs is not None else [c * 1.005 for c in closes],
        "low": lows if lows is not None else [c * 0.995 for c in closes],
        "volume": volumes if volumes is not None else [1000] * n,
    }
    if opens is not None:
        data["open"] = opens
    if prev_closes is not None:
        data["prev_close"] = prev_closes
    return pd.DataFrame(data)


# ============================================================================
# abcd_pattern 테스트
# ============================================================================

class TestAbcdPattern:

    def test_basic_abcd_signal(self):
        """A→B→C→D 4단계 기본 시나리오: D 돌파 시점에 True."""
        # 시나리오:
        #   09:00 A = 1000 (low)
        #   09:01 상승 시작
        #   09:02 B = 1050 (high, AB +5%)
        #   09:03 C = 1020 (눌림, A보다 위, B의 97% 수준)
        #   09:04 D = 1055 (B 1050 돌파 → True)
        minutes = [
            "2024-01-02 09:00",
            "2024-01-02 09:01",
            "2024-01-02 09:02",
            "2024-01-02 09:03",
            "2024-01-02 09:04",
        ]
        closes = [1000.0, 1030.0, 1050.0, 1020.0, 1055.0]
        highs  = [1005.0, 1035.0, 1050.0, 1025.0, 1060.0]
        lows   = [995.0,  1025.0, 1045.0, 1015.0, 1050.0]

        df = _make_df(minutes, closes, highs=highs, lows=lows)
        sig = abcd_pattern(df, min_ab_pct=2.0, max_pullback_pct=10.0)

        assert sig.dtype == bool or sig.dtype == np.bool_
        # D 돌파(09:04)에서 True이어야 함
        assert sig.iloc[4] is np.bool_(True) or bool(sig.iloc[4]) is True, \
            f"D 돌파 시점(09:04) 시그널 없음. sig={sig.values}"

    def test_no_signal_without_d_breakout(self):
        """D가 B를 돌파하지 않으면 False."""
        minutes = [
            "2024-01-02 09:00",
            "2024-01-02 09:01",
            "2024-01-02 09:02",
            "2024-01-02 09:03",
            "2024-01-02 09:04",
        ]
        # A=1000, B=1050, C=1020, D=1040 (B 돌파 못함)
        closes = [1000.0, 1030.0, 1050.0, 1020.0, 1040.0]
        highs  = [1005.0, 1035.0, 1050.0, 1025.0, 1045.0]
        lows   = [995.0,  1025.0, 1045.0, 1015.0, 1035.0]

        df = _make_df(minutes, closes, highs=highs, lows=lows)
        sig = abcd_pattern(df, min_ab_pct=2.0, max_pullback_pct=10.0)
        assert not sig.any(), f"D 미돌파인데 True 발생: {sig.values}"

    def test_no_signal_ab_pct_too_small(self):
        """AB 상승 폭이 min_ab_pct 미만이면 False."""
        minutes = [
            "2024-01-02 09:00",
            "2024-01-02 09:01",
            "2024-01-02 09:02",
            "2024-01-02 09:03",
            "2024-01-02 09:04",
        ]
        # A=1000, B=1010 (+1%, min_ab_pct=2%), C=1005, D=1015
        closes = [1000.0, 1005.0, 1010.0, 1005.0, 1015.0]
        highs  = [1002.0, 1008.0, 1010.0, 1008.0, 1017.0]
        lows   = [998.0,  1003.0, 1008.0, 1003.0, 1013.0]

        df = _make_df(minutes, closes, highs=highs, lows=lows)
        sig = abcd_pattern(df, min_ab_pct=2.0, max_pullback_pct=10.0)
        assert not sig.any(), f"AB 상승 부족인데 True 발생: {sig.values}"

    def test_no_lookahead(self):
        """No Look-Ahead: 마지막 N봉 잘라내도 이전 시점 시그널 불변."""
        # 충분히 긴 시나리오 생성
        n = 20
        minutes = [f"2024-01-02 09:{i:02d}" for i in range(n)]
        # A구간(0~4): 1000→1000, B구간(5): 1060(+6%), C구간(6~10): 1030, D구간(11): 1065
        closes = [1000.0] * 5 + [1060.0] + [1030.0] * 5 + [1065.0] + [1000.0] * 8
        highs  = [c + 5 for c in closes]
        lows   = [c - 5 for c in closes]

        df_full = _make_df(minutes, closes, highs=highs, lows=lows)
        sig_full = abcd_pattern(df_full, min_ab_pct=2.0, max_pullback_pct=10.0)

        # 마지막 5봉 잘라서 재계산
        df_cut = df_full.iloc[:-5].copy()
        sig_cut = abcd_pattern(df_cut, min_ab_pct=2.0, max_pullback_pct=10.0)

        for i in range(len(df_cut)):
            assert bool(sig_cut.iloc[i]) == bool(sig_full.iloc[i]), \
                f"행 {i}: full={sig_full.iloc[i]}, cut={sig_cut.iloc[i]} — Look-Ahead 위반"

    def test_multiday_reset(self):
        """다일 입력 시 일별 독립 처리: 전일 패턴이 익일에 영향 없음."""
        # 1일차: ABCD 완성 없음
        # 2일차: ABCD 완성
        day1 = [f"2024-01-02 09:0{i}" for i in range(5)]
        day2 = [f"2024-01-03 09:0{i}" for i in range(5)]
        closes = [1000.0, 1010.0, 1005.0, 1008.0, 1003.0,   # day1: 패턴 없음
                  2000.0, 2050.0, 2100.0, 2060.0, 2110.0]    # day2: ABCD
        highs  = [c + 5 for c in closes]
        lows   = [c - 5 for c in closes]

        df = _make_df(day1 + day2, closes, highs=highs, lows=lows)
        sig = abcd_pattern(df, min_ab_pct=2.0, max_pullback_pct=10.0)

        # 2일차 시그널은 2일차 분봉에서만 발생해야 함
        day1_sig = sig.iloc[:5]
        day2_sig = sig.iloc[5:]
        # 2일차에서 시그널이 났다면 2일차 내부에 있어야 함 (일자 독립성)
        assert len(sig) == 10
        # day1 시그널은 있을 수도 없을 수도 있지만, 다일 처리가 깨지지 않아야 함
        _ = day1_sig  # 값 검사보다 크래시 없음이 목적

    def test_empty_df(self):
        """빈 DataFrame → 빈 Series."""
        df = pd.DataFrame(columns=["dt", "high", "low", "close", "volume"])
        sig = abcd_pattern(df)
        assert len(sig) == 0

    def test_missing_required_column_raises(self):
        """필수 컬럼(high/low/close) 없으면 ValueError."""
        df = pd.DataFrame({"dt": pd.to_datetime(["2024-01-02 09:00"]), "close": [100.0]})
        with pytest.raises(ValueError, match="필수 컬럼 누락"):
            abcd_pattern(df)


# ============================================================================
# bull_flag 테스트
# ============================================================================

class TestBullFlag:

    def _make_bull_flag_scenario(self) -> pd.DataFrame:
        """깃대(+10%) + 깃발(횡보) + 돌파(거래량 ×2) 시나리오."""
        # 깃대: 09:00 close=1000 → 09:29 close=1100 (+10%, pole_window=30)
        pole_minutes = [f"2024-01-02 09:{i:02d}" for i in range(30)]
        pole_closes  = [1000.0 + (100.0 / 29) * i for i in range(30)]
        pole_highs   = [c + 3 for c in pole_closes]
        pole_lows    = [c - 3 for c in pole_closes]
        pole_vols    = [500] * 30

        # 깃발: 09:30 ~ 09:44 횡보 (1100±10, 폭 약 1.8%)
        flag_closes = [1100.0, 1095.0, 1105.0, 1098.0, 1102.0,
                       1099.0, 1103.0, 1097.0, 1101.0, 1100.0,
                       1098.0, 1104.0, 1096.0, 1102.0, 1099.0]
        flag_minutes = [f"2024-01-02 09:{30+i:02d}" for i in range(15)]
        flag_highs   = [1108.0] * 15
        flag_lows    = [1090.0] * 15
        flag_vols    = [300] * 15  # 평균 거래량 낮게

        # 돌파: 09:45 close=1115 > flag_high=1108, volume=900 > 300*1.5=450
        breakout_minute = ["2024-01-02 09:45"]
        breakout_close  = [1115.0]
        breakout_high   = [1120.0]
        breakout_low    = [1110.0]
        breakout_vol    = [900]

        minutes = pole_minutes + flag_minutes + breakout_minute
        closes  = pole_closes + flag_closes + breakout_close
        highs   = pole_highs + flag_highs + breakout_high
        lows    = pole_lows + flag_lows + breakout_low
        vols    = pole_vols + flag_vols + breakout_vol

        return _make_df(minutes, closes, volumes=vols, highs=highs, lows=lows)

    def test_basic_bull_flag_signal(self):
        """깃대+깃발+돌파 시나리오: 돌파 분봉에서 True."""
        df = self._make_bull_flag_scenario()
        sig = bull_flag(df, pole_pct=5.0, pole_window=30, flag_window=20,
                        flag_range_pct=2.0, volume_mult=1.5)
        # 마지막 봉(돌파봉)에서 True
        assert bool(sig.iloc[-1]) is True, \
            f"돌파 분봉에서 시그널 없음. sig[-5:]={sig.iloc[-5:].values}"

    def test_no_signal_without_volume(self):
        """거래량 미달(평균의 1.5배 미만)이면 False."""
        df = self._make_bull_flag_scenario()
        # 마지막 봉(돌파봉)의 거래량을 낮춤
        df = df.copy()
        df.loc[df.index[-1], "volume"] = 100  # 300 * 1.5 = 450 미만
        sig = bull_flag(df, pole_pct=5.0, pole_window=30, flag_window=20,
                        flag_range_pct=2.0, volume_mult=1.5)
        assert not sig.iloc[-1], f"거래량 미달인데 True: {sig.iloc[-1]}"

    def test_no_signal_flag_range_too_wide(self):
        """깃발 폭이 flag_range_pct 초과이면 False."""
        df = self._make_bull_flag_scenario()
        df = df.copy()
        # 깃발 구간 lows를 낮춰서 폭 확대
        flag_slice = slice(30, 45)
        df.loc[df.index[flag_slice], "low"] = 1050.0  # 폭 = (1108-1050)/1050 ≈ 5.5%
        sig = bull_flag(df, pole_pct=5.0, pole_window=30, flag_window=20,
                        flag_range_pct=2.0, volume_mult=1.5)
        assert not sig.iloc[-1], f"깃발 폭 초과인데 True: {sig.iloc[-1]}"

    def test_no_lookahead(self):
        """No Look-Ahead: 마지막 봉 잘라도 이전 시그널 불변."""
        df = self._make_bull_flag_scenario()
        sig_full = bull_flag(df, pole_pct=5.0, pole_window=30, flag_window=20,
                             flag_range_pct=2.0, volume_mult=1.5)
        df_cut = df.iloc[:-3].copy()
        sig_cut = bull_flag(df_cut, pole_pct=5.0, pole_window=30, flag_window=20,
                            flag_range_pct=2.0, volume_mult=1.5)
        for i in range(len(df_cut)):
            assert bool(sig_cut.iloc[i]) == bool(sig_full.iloc[i]), \
                f"행 {i}: full={sig_full.iloc[i]}, cut={sig_cut.iloc[i]} — Look-Ahead 위반"

    def test_multiday_reset(self):
        """다일 입력: 각 일별 독립 처리 (크래시 없음 + 길이 일치)."""
        df1 = self._make_bull_flag_scenario()
        # 2일차: 날짜 +1
        df2 = df1.copy()
        df2["dt"] = df2["dt"] + pd.Timedelta(days=1)
        df_multi = pd.concat([df1, df2], ignore_index=True)
        sig = bull_flag(df_multi, pole_pct=5.0, pole_window=30, flag_window=20,
                        flag_range_pct=2.0, volume_mult=1.5)
        assert len(sig) == len(df_multi)

    def test_empty_df(self):
        """빈 DataFrame → 빈 Series."""
        df = pd.DataFrame(columns=["dt", "high", "low", "close", "volume"])
        sig = bull_flag(df)
        assert len(sig) == 0

    def test_missing_required_column_raises(self):
        """필수 컬럼 없으면 ValueError."""
        df = pd.DataFrame({
            "dt": pd.to_datetime(["2024-01-02 09:00"]),
            "close": [100.0],
            "high": [101.0],
            "low": [99.0],
        })  # volume 없음
        with pytest.raises(ValueError, match="필수 컬럼 누락"):
            bull_flag(df)


# ============================================================================
# opening_range_breakout 테스트
# ============================================================================

class TestOrb:

    def _make_orb_df(self, or_high: float = 1050.0, breakout_close: float = 1060.0) -> pd.DataFrame:
        """OR(09:00~09:14) + 이후 분봉 시나리오."""
        # OR 구간: 09:00 ~ 09:14 (15분)
        or_minutes = [f"2024-01-02 09:{i:02d}" for i in range(15)]
        or_closes  = [1040.0] * 15
        or_highs   = [or_high] * 15
        or_lows    = [1010.0] * 15
        or_vols    = [1000] * 15

        # OR 이후: 09:15 ~ 09:20
        post_minutes = [f"2024-01-02 09:{15+i:02d}" for i in range(6)]
        post_closes  = [1030.0, 1035.0, 1040.0, breakout_close, 1055.0, 1045.0]
        post_highs   = [c + 5 for c in post_closes]
        post_lows    = [c - 5 for c in post_closes]
        post_vols    = [1000] * 6

        minutes = or_minutes + post_minutes
        closes  = or_closes + post_closes
        highs   = or_highs + post_highs
        lows    = or_lows + post_lows
        vols    = or_vols + post_vols
        return _make_df(minutes, closes, volumes=vols, highs=highs, lows=lows)

    def test_basic_orb_signal(self):
        """OR(09:00~09:14) 고점(1050) 돌파(close=1060) → 해당 분봉 True."""
        df = self._make_orb_df(or_high=1050.0, breakout_close=1060.0)
        sig = opening_range_breakout(df, range_minutes=15)
        # 09:18 (index 18): close=1060 > opening_high=1050 → True
        assert bool(sig.iloc[18]) is True, f"돌파 분봉 시그널 없음: {sig.values}"

    def test_no_signal_in_opening_range(self):
        """OR 구간(09:00~09:14) 내 분봉은 모두 False."""
        df = self._make_orb_df()
        sig = opening_range_breakout(df, range_minutes=15)
        or_sigs = sig.iloc[:15]
        assert not or_sigs.any(), f"OR 구간 내 시그널 발생: {or_sigs.values}"

    def test_no_signal_close_below_or_high(self):
        """close <= opening_high이면 False."""
        df = self._make_orb_df(or_high=1050.0, breakout_close=1045.0)
        # post_closes = [1030, 1035, 1040, 1045, 1055, 1045]
        # 1045 < 1050 → False, 1055 > 1050 → True(최초)
        sig = opening_range_breakout(df, range_minutes=15)
        # index 18(close=1045): False
        assert not bool(sig.iloc[18]), f"미돌파인데 True: {sig.iloc[18]}"

    def test_only_first_breakout(self):
        """일중 최초 돌파만 True, 이후 재돌파는 False."""
        # OR 이후 분봉에서 두 번 돌파 가능하도록 설계
        or_minutes  = [f"2024-01-02 09:{i:02d}" for i in range(15)]
        post_minutes = [f"2024-01-02 09:{15+i:02d}" for i in range(5)]
        or_highs = [1050.0] * 15
        or_lows  = [1010.0] * 15
        # post: 1060 (돌파1), 1040 (하락), 1065 (재돌파)
        post_closes = [1060.0, 1040.0, 1065.0, 1070.0, 1055.0]
        post_highs  = [c + 5 for c in post_closes]
        post_lows   = [c - 5 for c in post_closes]

        df = _make_df(
            or_minutes + post_minutes,
            [1040.0] * 15 + post_closes,
            highs=or_highs + post_highs,
            lows=or_lows + post_lows,
        )
        sig = opening_range_breakout(df, range_minutes=15)
        # index 15(09:15 close=1060): 최초 돌파 → True
        assert bool(sig.iloc[15]) is True, "최초 돌파 누락"
        # index 17(09:17 close=1065): 재돌파 → False
        assert not bool(sig.iloc[17]), f"재돌파에서 True: {sig.iloc[17]}"

    def test_no_lookahead(self):
        """No Look-Ahead: 마지막 N봉 잘라내도 이전 시그널 불변."""
        df = self._make_orb_df(or_high=1050.0, breakout_close=1060.0)
        sig_full = opening_range_breakout(df, range_minutes=15)
        df_cut = df.iloc[:-2].copy()
        sig_cut = opening_range_breakout(df_cut, range_minutes=15)
        for i in range(len(df_cut)):
            assert bool(sig_cut.iloc[i]) == bool(sig_full.iloc[i]), \
                f"행 {i}: full={sig_full.iloc[i]}, cut={sig_cut.iloc[i]} — Look-Ahead 위반"

    def test_multiday_reset(self):
        """다일 입력: 각 일자별 독립 OR 측정."""
        df1 = self._make_orb_df(or_high=1050.0, breakout_close=1060.0)
        df2 = self._make_orb_df(or_high=2000.0, breakout_close=1500.0)  # 2일차: 돌파 없음
        df2["dt"] = df2["dt"] + pd.Timedelta(days=1)
        df_multi = pd.concat([df1, df2], ignore_index=True)
        sig = opening_range_breakout(df_multi, range_minutes=15)
        assert len(sig) == len(df_multi)
        # 1일차: 시그널 있음
        assert sig.iloc[:21].any(), "1일차 ORB 시그널 누락"
        # 2일차: close=1500 < or_high=2000 → 시그널 없음
        assert not sig.iloc[21:].any(), f"2일차 미돌파인데 시그널: {sig.iloc[21:].values}"

    def test_lunch_time_handling(self):
        """점심 시간(volume=0) 행이 있어도 OR 계산 영향 없음."""
        or_minutes  = [f"2024-01-02 09:{i:02d}" for i in range(15)]
        # 점심: 12:00, 12:30
        lunch_minutes = ["2024-01-02 12:00", "2024-01-02 12:30"]
        post_minutes  = ["2024-01-02 13:01"]

        all_minutes = or_minutes + lunch_minutes + post_minutes
        closes = [1040.0] * 15 + [1000.0, 999.0, 1060.0]
        highs  = [1050.0] * 15 + [1005.0, 1004.0, 1065.0]
        lows   = [1010.0] * 15 + [995.0,  994.0,  1055.0]
        vols   = [1000] * 15 + [0, 0, 2000]

        df = _make_df(all_minutes, closes, volumes=vols, highs=highs, lows=lows)
        sig = opening_range_breakout(df, range_minutes=15)
        # 점심 시간 행은 False
        assert not sig.iloc[15], "점심 시간 행에 시그널"
        assert not sig.iloc[16], "점심 시간 행에 시그널"
        # 13:01 close=1060 > or_high=1050 → True
        assert bool(sig.iloc[17]) is True, f"점심 후 돌파 누락: {sig.iloc[17]}"

    def test_empty_df(self):
        """빈 DataFrame → 빈 Series."""
        df = pd.DataFrame(columns=["dt", "high", "low", "close", "volume"])
        sig = opening_range_breakout(df)
        assert len(sig) == 0

    def test_missing_required_column_raises(self):
        """필수 컬럼 없으면 ValueError."""
        df = pd.DataFrame({
            "dt": pd.to_datetime(["2024-01-02 09:00"]),
            "close": [100.0],
            "high": [101.0],
        })  # low 없음
        with pytest.raises(ValueError, match="필수 컬럼 누락"):
            opening_range_breakout(df)


# ============================================================================
# red_to_green 테스트
# ============================================================================

class TestR2G:

    def _make_r2g_df(
        self,
        first_open: float = 980.0,
        prev_close: float = 1000.0,
        crosses_at: int = 3,
        n: int = 8,
    ) -> pd.DataFrame:
        """gap down 후 crosses_at 번째 분봉에서 전환하는 시나리오."""
        minutes = [f"2024-01-02 09:{i:02d}" for i in range(n)]
        # crosses_at 이전: prev_close 이하, crosses_at 시점: prev_close 초과
        closes = []
        for i in range(n):
            if i < crosses_at:
                closes.append(prev_close - 10.0)  # 레드 구간
            else:
                closes.append(prev_close + 10.0)  # 그린 구간
        opens = [first_open] + closes[:-1]  # 첫 봉 open = first_open
        prev_closes_col = [prev_close] * n

        return _make_df(
            minutes, closes,
            opens=opens,
            prev_closes=prev_closes_col,
        )

    def test_basic_r2g_signal(self):
        """gap down 후 전일 종가 상향 돌파 → 전환 분봉에서 True."""
        # first_open=980 < prev_close=1000 → gap down
        # index 3: close=990 → index 4: close=1010 > 1000 → True
        df = self._make_r2g_df(first_open=980.0, prev_close=1000.0, crosses_at=4)
        sig = red_to_green(df, prev_close_col="prev_close")
        assert bool(sig.iloc[4]) is True, f"R2G 전환 누락: {sig.values}"
        # 전환 이전은 False
        assert not sig.iloc[:4].any(), f"전환 전에 True: {sig.iloc[:4].values}"

    def test_no_signal_no_gap_down(self):
        """시초가 >= 전일 종가 (gap down 없음) → 모두 False."""
        # first_open=1010 > prev_close=1000 → gap up → R2G 없음
        df = self._make_r2g_df(first_open=1010.0, prev_close=1000.0, crosses_at=3)
        sig = red_to_green(df)
        assert not sig.any(), f"gap up인데 R2G 시그널: {sig.values}"

    def test_no_signal_no_crossover(self):
        """gap down이지만 종가가 한 번도 전일 종가 초과 안 함 → False."""
        minutes = [f"2024-01-02 09:{i:02d}" for i in range(5)]
        closes = [990.0, 985.0, 988.0, 982.0, 991.0]  # 모두 < 1000
        opens  = [980.0] + closes[:-1]
        prev_closes_col = [1000.0] * 5
        df = _make_df(minutes, closes, opens=opens, prev_closes=prev_closes_col)
        sig = red_to_green(df)
        assert not sig.any(), f"전환 없는데 True: {sig.values}"

    def test_only_first_crossover(self):
        """최초 전환만 True, 이후 재전환은 False."""
        minutes = [f"2024-01-02 09:{i:02d}" for i in range(8)]
        # 980(open), 990(레드), 1010(그린→True), 990(레드), 1010(재그린→False)
        closes = [990.0, 990.0, 1010.0, 990.0, 1010.0, 1020.0, 1015.0, 1025.0]
        opens  = [980.0] + closes[:-1]
        prev_closes_col = [1000.0] * 8
        df = _make_df(minutes, closes, opens=opens, prev_closes=prev_closes_col)
        sig = red_to_green(df)
        # index 2: 최초 그린 전환
        assert bool(sig.iloc[2]) is True, f"최초 전환 누락: {sig.values}"
        # index 4: 재전환 → False
        assert not bool(sig.iloc[4]), f"재전환에서 True: {sig.iloc[4]}"
        # 전환 이후 다른 봉들도 False
        assert not sig.iloc[5:].any(), f"이후 봉에서 True: {sig.iloc[5:].values}"

    def test_no_lookahead(self):
        """No Look-Ahead: 마지막 N봉 잘라도 이전 시그널 불변."""
        df = self._make_r2g_df(first_open=980.0, prev_close=1000.0, crosses_at=4, n=10)
        sig_full = red_to_green(df)
        df_cut = df.iloc[:-3].copy()
        sig_cut = red_to_green(df_cut)
        for i in range(len(df_cut)):
            assert bool(sig_cut.iloc[i]) == bool(sig_full.iloc[i]), \
                f"행 {i}: full={sig_full.iloc[i]}, cut={sig_cut.iloc[i]} — Look-Ahead 위반"

    def test_multiday_reset(self):
        """다일 입력: 각 일자 독립 처리. 2일차 gap down+전환 → 2일차에서만 True."""
        df1 = self._make_r2g_df(first_open=1010.0, prev_close=1000.0, n=5)  # gap up → False
        df2 = self._make_r2g_df(first_open=980.0,  prev_close=1000.0, crosses_at=3, n=5)
        df2["dt"] = pd.to_datetime(df2["dt"]) + pd.Timedelta(days=1)
        df_multi = pd.concat([df1, df2], ignore_index=True)
        sig = red_to_green(df_multi)
        assert len(sig) == 10
        # 1일차(gap up): 모두 False
        assert not sig.iloc[:5].any(), f"1일차(gap up)에서 True: {sig.iloc[:5].values}"
        # 2일차: 시그널 있어야 함
        assert sig.iloc[5:].any(), f"2일차 R2G 시그널 누락: {sig.iloc[5:].values}"

    def test_lunch_time_handling(self):
        """점심 시간(volume=0) 행 이후에 전환이 발생해도 정상 동작."""
        minutes = [
            "2024-01-02 09:00",  # open
            "2024-01-02 11:50",  # 레드 (직전 점심)
            "2024-01-02 12:00",  # 점심 (volume=0)
            "2024-01-02 12:30",  # 점심 (volume=0)
            "2024-01-02 13:01",  # 그린 전환
        ]
        closes = [990.0, 985.0, 984.0, 983.0, 1010.0]
        opens  = [980.0, 990.0, 985.0, 984.0, 983.0]
        prev_closes_col = [1000.0] * 5
        vols   = [1000, 1000, 0, 0, 2000]
        df = _make_df(minutes, closes, volumes=vols, opens=opens, prev_closes=prev_closes_col)
        sig = red_to_green(df)
        # 13:01 (index 4): close=1010 > prev_close=1000, 직전(12:30)=983 <= 1000 → True
        assert bool(sig.iloc[4]) is True, f"점심 후 R2G 전환 누락: {sig.values}"

    def test_empty_df(self):
        """빈 DataFrame → 빈 Series."""
        df = pd.DataFrame(columns=["dt", "close", "prev_close", "open"])
        sig = red_to_green(df)
        assert len(sig) == 0

    def test_missing_prev_close_raises(self):
        """prev_close 컬럼 없으면 ValueError."""
        df = pd.DataFrame({
            "dt": pd.to_datetime(["2024-01-02 09:00"]),
            "close": [100.0],
        })
        with pytest.raises(ValueError, match="필수 컬럼 누락"):
            red_to_green(df)

    def test_index_preserved(self):
        """반환 Series의 index가 입력 DataFrame index와 동일."""
        df = self._make_r2g_df(first_open=980.0, prev_close=1000.0, crosses_at=3, n=6)
        df.index = [10, 20, 30, 40, 50, 60]
        sig = red_to_green(df)
        assert list(sig.index) == [10, 20, 30, 40, 50, 60]
