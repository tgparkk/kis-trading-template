"""
한국 공휴일 캘린더 테스트
=========================
- holidays 라이브러리 백엔드 동작 검증
- 근로자의 날(5/1) 수동 보완 검증
- 음력 공휴일(설날, 추석) 식별 검증
- 영업일 수 계산 정확성 검증
- holidays 미설치 시 graceful fallback 검증
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from datetime import datetime, date
from unittest.mock import patch


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def dt(year, month, day) -> datetime:
    return datetime(year, month, day)


# ---------------------------------------------------------------------------
# 기본 공휴일 식별
# ---------------------------------------------------------------------------

class TestKRHolidayBasic:
    """기본 공휴일 식별 테스트"""

    def test_weekend_saturday(self):
        from utils.korean_holidays import is_holiday, is_weekend
        # 2026-05-02 토요일
        d = dt(2026, 5, 2)
        assert is_weekend(d)
        assert is_holiday(d)

    def test_weekend_sunday(self):
        from utils.korean_holidays import is_holiday, is_weekend
        # 2026-05-03 일요일
        d = dt(2026, 5, 3)
        assert is_weekend(d)
        assert is_holiday(d)

    def test_weekday_not_holiday(self):
        from utils.korean_holidays import is_holiday
        # 2026-04-27 월요일 (평일)
        assert not is_holiday(dt(2026, 4, 27))

    def test_new_year(self):
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2026, 1, 1))

    def test_independence_movement_day(self):
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2026, 3, 1))

    def test_childrens_day(self):
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2026, 5, 5))

    def test_christmas(self):
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2026, 12, 25))


# ---------------------------------------------------------------------------
# 근로자의 날 (결재 #4 — 오늘 즉시 fix)
# ---------------------------------------------------------------------------

class TestLaborDay:
    """근로자의 날 테스트"""

    def test_labor_day_2026(self):
        """2026-05-01 근로자의 날은 공휴일이어야 한다"""
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2026, 5, 1)), "근로자의 날(2026-05-01)이 공휴일로 인식되지 않음"

    def test_labor_day_2025(self):
        """2025-05-01 근로자의 날도 공휴일"""
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2025, 5, 1))

    def test_labor_day_name(self):
        """근로자의 날 이름이 반환되어야 한다"""
        from utils.korean_holidays import get_holiday_name
        name = get_holiday_name(dt(2026, 5, 1))
        assert "근로자" in name or name != "", f"근로자의 날 이름 미반환: '{name}'"

    def test_is_fixed_holiday_labor_day(self):
        """is_fixed_holiday()도 근로자의 날을 True 반환"""
        from utils.korean_holidays import is_fixed_holiday
        assert is_fixed_holiday(dt(2026, 5, 1))


# ---------------------------------------------------------------------------
# 음력 공휴일 (설날, 추석)
# ---------------------------------------------------------------------------

class TestLunarHolidays:
    """음력 공휴일 테스트"""

    def test_lunar_new_year_2026(self):
        """2026-02-17 설날은 공휴일이어야 한다"""
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2026, 2, 17)), "2026년 설날(02-17)이 공휴일로 인식되지 않음"

    def test_lunar_new_year_eve_2026(self):
        """2026-02-16 설날 전날도 공휴일"""
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2026, 2, 16))

    def test_lunar_new_year_after_2026(self):
        """2026-02-18 설날 다음날도 공휴일"""
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2026, 2, 18))

    def test_chuseok_2026(self):
        """2026-09-25 추석은 공휴일이어야 한다"""
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2026, 9, 25))

    def test_lunar_new_year_2025(self):
        """2025-01-29 설날"""
        from utils.korean_holidays import is_holiday
        assert is_holiday(dt(2025, 1, 29))


# ---------------------------------------------------------------------------
# 영업일 수 계산
# ---------------------------------------------------------------------------

class TestCountTradingDays:
    """영업일 수 계산 테스트"""

    def test_count_trading_days_excluding_holidays(self):
        """설 연휴 포함 기간의 영업일 수 정확성 (2026-02-13 ~ 2026-02-20)

        2026-02-13(금), 14(토), 15(일), 16(월 설전날), 17(화 설날), 18(수 설다음날), 19(목), 20(금)
        주말: 14, 15 = 2일
        공휴일: 16, 17, 18 = 3일
        영업일: 13, 19, 20 = 3일
        """
        from utils.korean_holidays import count_trading_days_between
        start = dt(2026, 2, 13)
        end = dt(2026, 2, 20)
        result = count_trading_days_between(start, end)
        assert result == 3, f"설 연휴 포함 기간 영업일 수: 기대 3, 실제 {result}"

    def test_count_single_trading_day(self):
        """단일 평일 = 영업일 1"""
        from utils.korean_holidays import count_trading_days_between
        # 2026-04-27 월요일 (평일)
        d = dt(2026, 4, 27)
        assert count_trading_days_between(d, d) == 1

    def test_count_single_holiday(self):
        """단일 공휴일 = 영업일 0"""
        from utils.korean_holidays import count_trading_days_between
        # 2026-05-01 근로자의 날
        d = dt(2026, 5, 1)
        assert count_trading_days_between(d, d) == 0

    def test_count_week_with_weekend(self):
        """일주일(월~일) 중 영업일 = 5 (공휴일 없는 주)"""
        from utils.korean_holidays import count_trading_days_between
        # 2026-04-20(월) ~ 2026-04-26(일) — 이 주에 공휴일 없음
        start = dt(2026, 4, 20)
        end = dt(2026, 4, 26)
        result = count_trading_days_between(start, end)
        assert result == 5, f"평범한 1주 영업일: 기대 5, 실제 {result}"

    def test_count_labor_day_excluded(self):
        """근로자의 날 포함 주의 영업일 = 4 (5/1 제외)"""
        from utils.korean_holidays import count_trading_days_between
        # 2026-04-27(월) ~ 2026-05-01(금, 근로자의날)
        start = dt(2026, 4, 27)
        end = dt(2026, 5, 1)
        result = count_trading_days_between(start, end)
        assert result == 4, f"근로자의날 포함 주 영업일: 기대 4, 실제 {result}"


# ---------------------------------------------------------------------------
# 이전/다음 영업일
# ---------------------------------------------------------------------------

class TestTradingDayNavigation:
    """이전/다음 영업일 탐색 테스트"""

    def test_get_previous_trading_day_from_monday(self):
        """월요일의 이전 영업일 = 직전 금요일 (공휴일 없는 경우)"""
        from utils.korean_holidays import get_previous_trading_day
        # 2026-04-27 월요일 → 이전 영업일 2026-04-24 금요일
        result = get_previous_trading_day(dt(2026, 4, 27))
        assert result.strftime("%Y-%m-%d") == "2026-04-24"

    def test_get_next_trading_day_from_friday(self):
        """금요일의 다음 영업일 = 다음 월요일 (공휴일 없는 경우)"""
        from utils.korean_holidays import get_next_trading_day
        # 2026-04-24 금요일 → 다음 영업일 2026-04-27 월요일
        result = get_next_trading_day(dt(2026, 4, 24))
        assert result.strftime("%Y-%m-%d") == "2026-04-27"

    def test_get_previous_trading_day_skips_holiday(self):
        """설날 연휴를 건너뛰어 이전 영업일 반환"""
        from utils.korean_holidays import get_previous_trading_day
        # 2026-02-19(목) → 이전 영업일: 2026-02-13(금, 설 전주 금요일)
        result = get_previous_trading_day(dt(2026, 2, 19))
        assert result.strftime("%Y-%m-%d") == "2026-02-13"


# ---------------------------------------------------------------------------
# Fallback 테스트 (holidays 미설치 시)
# ---------------------------------------------------------------------------

class TestHolidaysFallback:
    """holidays 라이브러리 미설치 시 graceful fallback 테스트"""

    def test_fallback_when_import_fails(self):
        """holidays import 실패 시 수동 캘린더로 fallback — 크래시 없어야 한다"""
        import utils.korean_holidays as kh_module
        original = kh_module._HOLIDAYS_AVAILABLE
        try:
            kh_module._HOLIDAYS_AVAILABLE = False
            # fallback 경로에서도 기본 고정 공휴일은 식별되어야 함
            from utils.korean_holidays import is_holiday, is_fixed_holiday
            # 신정
            assert is_holiday(dt(2026, 1, 1))
            # 삼일절
            assert is_fixed_holiday(dt(2026, 3, 1))
            # 근로자의 날 (fallback 수동 캘린더에도 포함됨)
            assert is_fixed_holiday(dt(2026, 5, 1)), "fallback에서 근로자의 날 누락"
            # 평일 false
            assert not is_holiday(dt(2026, 4, 27))
        finally:
            kh_module._HOLIDAYS_AVAILABLE = original

    def test_fallback_lunar_holidays(self):
        """fallback 시 음력 공휴일(설날)도 식별"""
        import utils.korean_holidays as kh_module
        original = kh_module._HOLIDAYS_AVAILABLE
        try:
            kh_module._HOLIDAYS_AVAILABLE = False
            from utils.korean_holidays import is_holiday
            assert is_holiday(dt(2026, 2, 17)), "fallback에서 설날 누락"
        finally:
            kh_module._HOLIDAYS_AVAILABLE = original

    def test_fallback_count_trading_days(self):
        """fallback 시 count_trading_days_between도 정상 동작"""
        import utils.korean_holidays as kh_module
        original = kh_module._HOLIDAYS_AVAILABLE
        try:
            kh_module._HOLIDAYS_AVAILABLE = False
            from utils.korean_holidays import count_trading_days_between
            # 단순 평일 5일 체크 (공휴일 없는 주)
            start = dt(2026, 4, 27)
            end = dt(2026, 5, 1)
            # fallback에서도 근로자의 날 제외되어 4일
            result = count_trading_days_between(start, end)
            assert result == 4, f"fallback 영업일 수: 기대 4, 실제 {result}"
        finally:
            kh_module._HOLIDAYS_AVAILABLE = original


# ---------------------------------------------------------------------------
# get_holiday_name
# ---------------------------------------------------------------------------

class TestHolidayName:
    """공휴일 이름 반환 테스트"""

    def test_name_saturday(self):
        from utils.korean_holidays import get_holiday_name
        name = get_holiday_name(dt(2026, 5, 2))  # 토요일
        assert "토" in name

    def test_name_sunday(self):
        from utils.korean_holidays import get_holiday_name
        name = get_holiday_name(dt(2026, 5, 3))  # 일요일
        assert "일" in name

    def test_name_non_holiday(self):
        from utils.korean_holidays import get_holiday_name
        assert get_holiday_name(dt(2026, 4, 27)) == ""
