"""
test_phase5_tom.py — TOM (Turn-of-Month) 시그널 단위 테스트
============================================================

테스트 목록
-----------
TestNoLookAhead:
  - test_no_future_days_in_calendar       : 캘린더 도출 시 미래 영업일 사용 안 함
  - test_truncation_invariant             : 마지막 N행 절단해도 직전 결과 불변

TestIsтомWindow (TestIsTomWindow):
  - test_month_end_n_days                 : 월말 마지막 N영업일 판정 정확성
  - test_month_start_m_days               : 월초 첫 M영업일 판정 정확성
  - test_non_tom_mid_month                : 월 중간 Non-TOM 정확성
  - test_various_nm_params                : 다양한 (N, M) 파라미터 대응
  - test_calendar_none_raises             : calendar=None → ValueError
  - test_non_business_day_returns_false   : 비영업일(캘린더 미포함)은 False

TestKoreanHoliday:
  - test_long_holiday_first_bday          : 긴 연휴 후 첫 영업일 = 월초 TOM

TestTomSignal:
  - test_signal_dtype_bool                : 반환 시리즈 dtype=bool
  - test_signal_index_matches_scan_dates  : index == scan_dates
  - test_signal_count_in_window           : TOM 윈도우 날짜 수 (N+M)검증
  - test_signal_calendar_none_fallback    : calendar=None → scan_dates 자체 사용

TestFixture2024Q1:
  - test_2024_jan_tom_window              : 2024년 1월 실제 TOM 윈도우 날짜 확인
  - test_2024_feb_tom_window              : 2024년 2월 실제 TOM 윈도우 날짜 확인
"""

from __future__ import annotations

import sys
import os
from datetime import date, timedelta

import pandas as pd
import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.signals.calendar_tom import is_tom_window, tom_signal, _build_month_windows


# ---------------------------------------------------------------------------
# 픽스처: 한국 영업일 목록 (2024-01 ~ 2024-03)
# KRX 실제 휴장일 기반으로 수동 구성 (테스트 목적)
# ---------------------------------------------------------------------------

def _make_business_days(start: date, end: date, holidays: set[date] = None) -> list[date]:
    """주말 + 지정 휴일 제외 영업일 목록 생성."""
    if holidays is None:
        holidays = set()
    days = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and cur not in holidays:  # 0=Mon, 4=Fri
            days.append(cur)
        cur += timedelta(days=1)
    return days


# 2024년 1~3월 한국 공휴일 (실제 KRX 휴장일)
_KR_HOLIDAYS_2024Q1 = {
    date(2024, 1, 1),   # 신정
    date(2024, 2, 9),   # 설날 연휴
    date(2024, 2, 12),  # 설날 대체공휴일
    date(2024, 3, 1),   # 삼일절
}

CALENDAR_2024Q1 = _make_business_days(
    date(2024, 1, 2), date(2024, 3, 29), holidays=_KR_HOLIDAYS_2024Q1
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _month_bdays(calendar: list[date], year: int, month: int) -> list[date]:
    """캘린더에서 특정 연월의 영업일 목록 반환."""
    return [d for d in calendar if d.year == year and d.month == month]


# ---------------------------------------------------------------------------
# TestNoLookAhead
# ---------------------------------------------------------------------------

class TestNoLookAhead:
    """No Look-Ahead 검증."""

    def test_no_future_days_in_calendar(self):
        """캘린더에 scan_date 이후 날짜가 포함되어도 판정에 영향 없어야 함.

        TOM 판정은 같은 월 영업일 그룹에서만 이루어지므로
        미래 달의 영업일이 추가되어도 과거 달의 판정은 불변.
        """
        # 1월 캘린더만으로 판정
        cal_jan_only = [d for d in CALENDAR_2024Q1 if d.month == 1]
        result_jan = {d: is_tom_window(d, n_end=4, m_start=3, calendar=cal_jan_only)
                      for d in cal_jan_only}

        # 1~3월 전체 캘린더로 판정
        result_full = {d: is_tom_window(d, n_end=4, m_start=3, calendar=CALENDAR_2024Q1)
                       for d in cal_jan_only}

        assert result_jan == result_full, (
            "1월 판정은 미래(2~3월) 영업일 추가 여부와 무관해야 함"
        )

    def test_truncation_invariant(self):
        """마지막 20영업일 절단 후 재계산해도 공통 구간 결과 불변."""
        n_cut = 20
        full_cal = CALENDAR_2024Q1
        cut_cal = full_cal[:-n_cut]

        # 공통 구간 = cut_cal의 날짜들 (단, 월 경계 변화 없는 날짜만)
        # 잘린 캘린더의 마지막 달(월말 영업일 수가 달라질 수 있으므로)의 이전 달까지 비교
        if not cut_cal:
            return
        last_month_cut = (cut_cal[-1].year, cut_cal[-1].month)
        # 마지막 달 이전 날짜만 비교 (월말 영업일 수가 동일한 구간)
        compare_dates = [d for d in cut_cal
                         if (d.year, d.month) < last_month_cut]

        for d in compare_dates:
            r_full = is_tom_window(d, n_end=4, m_start=3, calendar=full_cal)
            r_cut  = is_tom_window(d, n_end=4, m_start=3, calendar=cut_cal)
            assert r_full == r_cut, (
                f"{d}: full={r_full}, cut={r_cut} — 결과가 달라졌음 (look-ahead 의심)"
            )


# ---------------------------------------------------------------------------
# TestIsTomWindow
# ---------------------------------------------------------------------------

class TestIsTomWindow:
    """is_tom_window 함수 정확성 테스트."""

    def test_month_end_n_days(self):
        """월말 마지막 N영업일이 TOM으로 판정되어야 함."""
        jan_days = _month_bdays(CALENDAR_2024Q1, 2024, 1)
        n_end = 4

        # 마지막 4영업일: TOM
        for d in jan_days[-n_end:]:
            assert is_tom_window(d, n_end=n_end, m_start=3, calendar=CALENDAR_2024Q1), (
                f"{d} 는 1월 마지막 {n_end}영업일이므로 TOM이어야 함"
            )

        # 마지막 5번째 영업일: Non-TOM (month 중간)
        if len(jan_days) > n_end:
            non_tom = jan_days[-(n_end + 1)]
            assert not is_tom_window(non_tom, n_end=n_end, m_start=3, calendar=CALENDAR_2024Q1), (
                f"{non_tom} 는 1월 마지막 {n_end+1}번째 영업일이므로 Non-TOM이어야 함"
            )

    def test_month_start_m_days(self):
        """월초 첫 M영업일이 TOM으로 판정되어야 함."""
        feb_days = _month_bdays(CALENDAR_2024Q1, 2024, 2)
        m_start = 3

        # 첫 3영업일: TOM
        for d in feb_days[:m_start]:
            assert is_tom_window(d, n_end=4, m_start=m_start, calendar=CALENDAR_2024Q1), (
                f"{d} 는 2월 첫 {m_start}영업일이므로 TOM이어야 함"
            )

        # 4번째 영업일: Non-TOM (월말 n_end 범위 확인 필요)
        if len(feb_days) > m_start:
            candidate = feb_days[m_start]
            # 2월이 짧아서 월말 n_end 범위 포함 여부 확인
            n_end = 4
            in_month_end = candidate in feb_days[-n_end:]
            expected = in_month_end  # 월말 범위에 해당하면 TOM
            result = is_tom_window(candidate, n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1)
            assert result == expected, (
                f"{candidate}: expected={expected}, got={result}"
            )

    def test_non_tom_mid_month(self):
        """월 중간 날짜는 Non-TOM이어야 함."""
        jan_days = _month_bdays(CALENDAR_2024Q1, 2024, 1)
        n_end, m_start = 4, 3

        # 월 중간: 첫 m_start와 마지막 n_end를 제외한 구간
        mid_days = jan_days[m_start:-n_end]
        assert mid_days, "1월 중간 영업일이 존재해야 함"

        for d in mid_days:
            assert not is_tom_window(d, n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1), (
                f"{d} 는 1월 중간이므로 Non-TOM이어야 함"
            )

    def test_various_nm_params(self):
        """다양한 (N, M) 파라미터 대응 — 윈도우 크기 변화 확인."""
        jan_days = _month_bdays(CALENDAR_2024Q1, 2024, 1)

        for n_end, m_start in [(1, 1), (2, 2), (5, 5), (4, 3)]:
            # 월말 마지막 n_end일
            for d in jan_days[-n_end:]:
                assert is_tom_window(d, n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1), (
                    f"(n={n_end}, m={m_start}): {d} 는 TOM이어야 함"
                )
            # 월 중간 (n_end + m_start 경계 밖)
            mid_days = jan_days[m_start:-n_end]
            for d in mid_days:
                assert not is_tom_window(d, n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1), (
                    f"(n={n_end}, m={m_start}): {d} 는 Non-TOM이어야 함"
                )

    def test_calendar_none_raises(self):
        """calendar=None이면 ValueError."""
        with pytest.raises(ValueError, match="calendar 파라미터가 필요합니다"):
            is_tom_window(date(2024, 1, 31), calendar=None)

    def test_non_business_day_returns_false(self):
        """캘린더에 없는 날짜(휴일/주말)은 False 반환."""
        # 2024-01-01 = 신정 (공휴일, 캘린더 미포함)
        result = is_tom_window(date(2024, 1, 1), calendar=CALENDAR_2024Q1)
        assert result is False, "신정(비영업일)은 TOM이 아님"

        # 2024-01-06 = 토요일 (주말)
        result = is_tom_window(date(2024, 1, 6), calendar=CALENDAR_2024Q1)
        assert result is False, "토요일(주말)은 TOM이 아님"


# ---------------------------------------------------------------------------
# TestKoreanHoliday
# ---------------------------------------------------------------------------

class TestKoreanHoliday:
    """한국 공휴일/긴 연휴 처리."""

    def test_long_holiday_first_bday(self):
        """설날 연휴(2024-02-09~12) 후 첫 영업일이 월초 TOM이어야 함.

        2024년 2월 설날 연휴: 2/9(금)~2/12(월) 휴장
        → 2월 첫 영업일: 2/1(목)
        → 연휴 후 첫 영업일: 2/13(화) (2월 m_start=3 기준: 2/1, 2/2, 2/5 = 첫 3영업일)
        설날 연휴 자체가 TOM 윈도우 바깥이 되지 않음을 확인.
        """
        feb_days = _month_bdays(CALENDAR_2024Q1, 2024, 2)
        # 2월 첫 3영업일이 TOM
        m_start = 3
        for d in feb_days[:m_start]:
            result = is_tom_window(d, n_end=4, m_start=m_start, calendar=CALENDAR_2024Q1)
            assert result, f"2월 첫 {m_start}영업일 중 {d}가 TOM이 아님 (설날 연휴 처리 오류)"

        # 2/9~2/12 휴장 기간은 캘린더에 없으므로 False
        for holiday in [date(2024, 2, 9), date(2024, 2, 12)]:
            result = is_tom_window(holiday, calendar=CALENDAR_2024Q1)
            assert result is False, f"설날 연휴 {holiday}는 TOM이 아님"

    def test_short_month_window_overlap(self):
        """2월처럼 짧은 달에서 월말 n_end + 월초 m_start가 전체 영업일 초과시 처리.

        2024년 2월: 설날 연휴 포함 약 19영업일
        n_end=10, m_start=10이면 전체 영업일이 윈도우 안 (모두 TOM).
        """
        feb_days = _month_bdays(CALENDAR_2024Q1, 2024, 2)
        n_end, m_start = 10, 10

        # 모든 2월 영업일이 TOM
        for d in feb_days:
            result = is_tom_window(d, n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1)
            assert result, f"(n=10, m=10): 2월 {d}은 TOM이어야 함 (짧은 달 처리)"


# ---------------------------------------------------------------------------
# TestTomSignal
# ---------------------------------------------------------------------------

class TestTomSignal:
    """tom_signal 함수 테스트."""

    def test_signal_dtype_bool(self):
        """반환 시리즈 dtype이 bool이어야 함."""
        jan_days = _month_bdays(CALENDAR_2024Q1, 2024, 1)
        sig = tom_signal(jan_days, calendar=CALENDAR_2024Q1)
        assert sig.dtype == bool, f"dtype={sig.dtype}, bool이어야 함"

    def test_signal_index_matches_scan_dates(self):
        """반환 시리즈 index가 scan_dates와 일치해야 함."""
        scan = CALENDAR_2024Q1[:20]
        sig = tom_signal(scan, calendar=CALENDAR_2024Q1)
        assert list(sig.index) == scan, "index가 scan_dates와 다름"

    def test_signal_name(self):
        """시리즈 name이 'tom_signal'이어야 함."""
        sig = tom_signal(CALENDAR_2024Q1[:5], calendar=CALENDAR_2024Q1)
        assert sig.name == "tom_signal"

    def test_signal_count_in_window(self):
        """1월 TOM 윈도우 날짜 수 = n_end (월말) + m_start (월초) 이하.

        1월 첫 m_start + 1월 마지막 n_end.
        단, 짧은 달에서는 중복이 없음.
        """
        n_end, m_start = 4, 3
        jan_days = _month_bdays(CALENDAR_2024Q1, 2024, 1)
        sig = tom_signal(jan_days, n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1)
        tom_count = sig.sum()
        expected = min(n_end + m_start, len(jan_days))
        assert tom_count == expected, (
            f"1월 TOM 날짜 수: got={tom_count}, expected={expected}"
        )

    def test_signal_calendar_none_fallback(self):
        """calendar=None이면 scan_dates 자체를 캘린더로 사용.

        scan_dates 자체가 캘린더이므로, scan_dates만으로 월별 영업일을 판정.
        예: scan_dates가 1월 전체 영업일 목록이면 1월 기준으로만 TOM 판정.
        """
        # 1월만 사용 — scan_dates가 완전한 월 단위이면 full calendar와 동일 결과
        scan = _month_bdays(CALENDAR_2024Q1, 2024, 1)
        sig_with_cal = tom_signal(scan, calendar=CALENDAR_2024Q1)
        sig_none_cal = tom_signal(scan, calendar=None)
        pd.testing.assert_series_equal(sig_with_cal, sig_none_cal)

    def test_signal_all_false_empty_calendar(self):
        """빈 scan_dates → 빈 시리즈."""
        sig = tom_signal([], calendar=CALENDAR_2024Q1)
        assert len(sig) == 0

    def test_signal_consistent_with_is_tom_window(self):
        """tom_signal 결과가 is_tom_window 결과와 일치해야 함."""
        scan = CALENDAR_2024Q1
        sig = tom_signal(scan, calendar=CALENDAR_2024Q1)
        for d, val in sig.items():
            expected = is_tom_window(d, calendar=CALENDAR_2024Q1)
            assert val == expected, f"{d}: signal={val}, is_tom_window={expected}"


# ---------------------------------------------------------------------------
# TestFixture2024Q1 — 실제 날짜 기반 구체 검증
# ---------------------------------------------------------------------------

class TestFixture2024Q1:
    """2024년 1~3월 실제 TOM 윈도우 날짜 확인."""

    def test_2024_jan_tom_window(self):
        """2024년 1월 TOM 윈도우 구체 날짜 확인.

        2024-01-02(화)~2024-01-31(수), 공휴일: 1/1(신정)
        영업일: 1/2, 1/3, 1/4, 1/5, 1/8, ...
        월초 TOM (m_start=3): 1/2, 1/3, 1/4
        월말 TOM (n_end=4): 1/26, 1/29, 1/30, 1/31
        """
        jan_days = _month_bdays(CALENDAR_2024Q1, 2024, 1)
        n_end, m_start = 4, 3

        expected_tom_start = jan_days[:m_start]
        expected_tom_end = jan_days[-n_end:]

        for d in expected_tom_start:
            assert is_tom_window(d, n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1), (
                f"{d} 는 1월 월초 TOM이어야 함"
            )
        for d in expected_tom_end:
            assert is_tom_window(d, n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1), (
                f"{d} 는 1월 월말 TOM이어야 함"
            )

        # 1월 2일(첫 영업일)이 TOM이어야 함 (월초 m_start=3 범위)
        assert is_tom_window(date(2024, 1, 2), n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1)
        # 1월 31일(마지막 영업일)이 TOM이어야 함 (월말 n_end=4 범위)
        assert is_tom_window(date(2024, 1, 31), n_end=n_end, m_start=m_start, calendar=CALENDAR_2024Q1)

    def test_2024_feb_tom_window(self):
        """2024년 2월 TOM 윈도우 (설날 연휴 포함).

        설날 연휴: 2/9(금), 2/12(월) 휴장
        2월 첫 영업일: 2/1(목)
        월초 TOM (m_start=3): 2/1, 2/2, 2/5
        """
        feb_days = _month_bdays(CALENDAR_2024Q1, 2024, 2)
        m_start = 3
        expected_start = feb_days[:m_start]

        # 2월 1일, 2일, 5일이 월초 TOM
        assert date(2024, 2, 1) in expected_start, "2/1이 2월 첫 영업일이어야 함"
        assert date(2024, 2, 2) in expected_start, "2/2이 2월 두번째 영업일이어야 함"
        assert date(2024, 2, 5) in expected_start, "2/5이 2월 세번째 영업일이어야 함"

        for d in expected_start:
            assert is_tom_window(d, n_end=4, m_start=m_start, calendar=CALENDAR_2024Q1), (
                f"{d} 는 2월 월초 TOM이어야 함"
            )

    def test_2024_mar_first_bday_tom(self):
        """2024년 3월 1일 = 삼일절(공휴일) → 첫 영업일이 3/4(월)이어야 함."""
        mar_days = _month_bdays(CALENDAR_2024Q1, 2024, 3)
        assert mar_days[0] == date(2024, 3, 4), (
            f"3월 첫 영업일: got={mar_days[0]}, expected=2024-03-04 (삼일절 이후)"
        )
        # 3/1(삼일절)은 비영업일이므로 False
        assert not is_tom_window(date(2024, 3, 1), calendar=CALENDAR_2024Q1)
        # 3/4(월)는 월초 TOM
        assert is_tom_window(date(2024, 3, 4), calendar=CALENDAR_2024Q1)
