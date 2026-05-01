"""
한국 공휴일 캘린더

주식 시장 휴장일을 판단하기 위한 유틸리티입니다.

백엔드: `holidays` 라이브러리 (holidays.KR) + 수동 보완
  - holidays.KR이 누락하는 근로자의 날(5/1)을 수동으로 추가합니다.
  - 라이브러리 import 실패 시 기존 수동 캘린더로 graceful fallback합니다.
"""
from datetime import datetime, timedelta, date as _date

# ---------------------------------------------------------------------------
# holidays 라이브러리 로드 (없으면 fallback)
# ---------------------------------------------------------------------------
_HOLIDAYS_AVAILABLE = False
_KR_HOLIDAYS_CACHE: dict = {}   # {year: holidays.KR(...)}

try:
    import holidays as _holidays_lib
    _HOLIDAYS_AVAILABLE = True
except ImportError:
    _holidays_lib = None  # type: ignore


def _get_kr_holidays(year: int):
    """연도별 holidays.KR 인스턴스 반환 (LRU 캐싱)"""
    if year not in _KR_HOLIDAYS_CACHE:
        obj = _holidays_lib.KR(years=year)  # type: ignore[union-attr]
        _KR_HOLIDAYS_CACHE[year] = obj
    return _KR_HOLIDAYS_CACHE[year]


# ---------------------------------------------------------------------------
# Fallback: 수동 캘린더 (holidays 미설치 시 사용)
# ---------------------------------------------------------------------------

# 고정 공휴일 (매년 동일)
_FIXED_HOLIDAYS = {
    (1, 1): "신정",
    (3, 1): "삼일절",
    (5, 1): "근로자의 날",
    (5, 5): "어린이날",
    (6, 6): "현충일",
    (8, 15): "광복절",
    (10, 3): "개천절",
    (10, 9): "한글날",
    (12, 25): "크리스마스",
}

# 음력 공휴일 (설날, 추석) — 2024-2030
_LUNAR_HOLIDAYS = {
    "2024-02-09": "설날 전날",
    "2024-02-10": "설날",
    "2024-02-11": "설날 다음날",
    "2024-02-12": "설날 대체공휴일",
    "2024-09-16": "추석 전날",
    "2024-09-17": "추석",
    "2024-09-18": "추석 다음날",
    "2025-01-28": "설날 전날",
    "2025-01-29": "설날",
    "2025-01-30": "설날 다음날",
    "2025-10-05": "추석 전날",
    "2025-10-06": "추석",
    "2025-10-07": "추석 다음날",
    "2025-10-08": "추석 대체공휴일",
    "2026-02-16": "설날 전날",
    "2026-02-17": "설날",
    "2026-02-18": "설날 다음날",
    "2026-09-24": "추석 전날",
    "2026-09-25": "추석",
    "2026-09-26": "추석 다음날",
    "2026-09-28": "추석 대체공휴일",
    "2027-02-06": "설날 전날",
    "2027-02-07": "설날",
    "2027-02-08": "설날 다음날",
    "2027-09-14": "추석 전날",
    "2027-09-15": "추석",
    "2027-09-16": "추석 다음날",
    "2028-01-26": "설날 전날",
    "2028-01-27": "설날",
    "2028-01-28": "설날 다음날",
    "2028-10-02": "추석 전날",
    "2028-10-03": "추석",
    "2028-10-04": "추석 다음날",
    "2029-02-12": "설날 전날",
    "2029-02-13": "설날",
    "2029-02-14": "설날 다음날",
    "2029-09-21": "추석 전날",
    "2029-09-22": "추석",
    "2029-09-23": "추석 다음날",
    "2029-09-24": "추석 대체공휴일",
    "2030-02-02": "설날 전날",
    "2030-02-03": "설날",
    "2030-02-04": "설날 다음날",
    "2030-09-11": "추석 전날",
    "2030-09-12": "추석",
    "2030-09-13": "추석 다음날",
}

# 임시 공휴일 (선거일 등)
_SPECIAL_HOLIDAYS = {
    "2024-04-10": "제22대 국회의원 선거",
    "2026-06-03": "지방선거",
}


# ---------------------------------------------------------------------------
# 공개 API — holidays 라이브러리 백엔드 우선, 없으면 수동 fallback
# ---------------------------------------------------------------------------

def _to_date(d) -> _date:
    """datetime / date / str → date 변환"""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, _date):
        return d
    return _date.fromisoformat(str(d))


def is_weekend(date: datetime) -> bool:
    """주말 여부 확인 (토요일=5, 일요일=6)"""
    return date.weekday() >= 5


def is_fixed_holiday(date: datetime) -> bool:
    """고정 공휴일 여부 확인 (근로자의 날 포함)"""
    if _HOLIDAYS_AVAILABLE:
        d = _to_date(date)
        kr = _get_kr_holidays(d.year)
        if d in kr:
            return True
        # holidays.KR이 누락하는 근로자의 날(5/1) 수동 보완
        if (d.month, d.day) == (5, 1):
            return True
        return False
    # fallback
    return (date.month, date.day) in _FIXED_HOLIDAYS


def is_lunar_holiday(date: datetime) -> bool:
    """음력 공휴일 여부 확인 (설날, 추석 등)

    holidays 백엔드 사용 시 is_fixed_holiday()가 이미 포함하므로 항상 False 반환.
    fallback 시 수동 캘린더에서 확인.
    """
    if _HOLIDAYS_AVAILABLE:
        # holidays.KR 백엔드가 음력 공휴일을 포함하므로 is_fixed_holiday에서 처리됨
        return False
    date_str = date.strftime("%Y-%m-%d")
    return date_str in _LUNAR_HOLIDAYS


def is_special_holiday(date: datetime) -> bool:
    """임시 공휴일 여부 확인 (선거일, 임시 공휴일 등)

    holidays 백엔드 사용 시: 라이브러리가 반영하는 것은 is_fixed_holiday에서 처리됨.
    _SPECIAL_HOLIDAYS 수동 목록도 추가로 체크 (라이브러리가 누락할 수 있는 경우 대비).
    """
    date_str = date.strftime("%Y-%m-%d")
    return date_str in _SPECIAL_HOLIDAYS


def is_holiday(date: datetime) -> bool:
    """
    공휴일 여부 확인 (주말 포함)

    Args:
        date: 확인할 날짜

    Returns:
        bool: 공휴일이면 True
    """
    return (
        is_weekend(date)
        or is_fixed_holiday(date)
        or is_lunar_holiday(date)
        or is_special_holiday(date)
    )


def get_holiday_name(date: datetime) -> str:
    """
    공휴일 이름 반환

    Args:
        date: 확인할 날짜

    Returns:
        str: 공휴일 이름 (공휴일이 아니면 빈 문자열)
    """
    if is_weekend(date):
        return "일요일" if date.weekday() == 6 else "토요일"

    if _HOLIDAYS_AVAILABLE:
        d = _to_date(date)
        kr = _get_kr_holidays(d.year)
        name = kr.get(d, "")
        if name:
            return str(name)
        # 근로자의 날 수동 보완
        if (d.month, d.day) == (5, 1):
            return "근로자의 날"
    else:
        key = (date.month, date.day)
        if key in _FIXED_HOLIDAYS:
            return _FIXED_HOLIDAYS[key]

    date_str = date.strftime("%Y-%m-%d")
    if not _HOLIDAYS_AVAILABLE and date_str in _LUNAR_HOLIDAYS:
        return _LUNAR_HOLIDAYS[date_str]

    if date_str in _SPECIAL_HOLIDAYS:
        return _SPECIAL_HOLIDAYS[date_str]

    return ""


def get_previous_trading_day(date: datetime = None, max_lookback_days: int = 10) -> datetime:
    """
    이전 영업일 반환 (주말 및 공휴일 자동 건너뛰기)

    Args:
        date: 기준 날짜 (None이면 오늘)
        max_lookback_days: 최대 조회일수 (기본 10일)

    Returns:
        datetime: 이전 영업일
    """
    if date is None:
        from utils.korean_time import now_kst
        date = now_kst()

    current = date - timedelta(days=1)

    for _ in range(max_lookback_days):
        if not is_holiday(current):
            return current
        current -= timedelta(days=1)

    return date - timedelta(days=1)


def get_next_trading_day(date: datetime = None, max_lookforward_days: int = 10) -> datetime:
    """
    다음 영업일 반환 (주말 및 공휴일 자동 건너뛰기)

    Args:
        date: 기준 날짜 (None이면 오늘)
        max_lookforward_days: 최대 조회일수 (기본 10일)

    Returns:
        datetime: 다음 영업일
    """
    if date is None:
        from utils.korean_time import now_kst
        date = now_kst()

    current = date + timedelta(days=1)

    for _ in range(max_lookforward_days):
        if not is_holiday(current):
            return current
        current += timedelta(days=1)

    return date + timedelta(days=1)


def count_trading_days_between(start_date: datetime, end_date: datetime) -> int:
    """
    두 날짜 사이의 영업일 수 계산 (start_date 포함, end_date 포함)

    Args:
        start_date: 시작 날짜
        end_date: 종료 날짜

    Returns:
        int: 영업일 수
    """
    count = 0
    current = start_date

    while current <= end_date:
        if not is_holiday(current):
            count += 1
        current += timedelta(days=1)

    return count


if __name__ == "__main__":
    from utils.korean_time import now_kst

    backend = "holidays 라이브러리" if _HOLIDAYS_AVAILABLE else "수동 캘린더 (fallback)"
    print(f"공휴일 백엔드: {backend}")
    print("=" * 80)

    today = now_kst()
    print(f"오늘: {today.strftime('%Y-%m-%d')} ({today.strftime('%A')})")
    print(f"  공휴일 여부: {is_holiday(today)}")
    if is_holiday(today):
        print(f"  공휴일 이름: {get_holiday_name(today)}")

    prev_trading = get_previous_trading_day(today)
    print(f"이전 영업일: {prev_trading.strftime('%Y-%m-%d')}")
    next_trading = get_next_trading_day(today)
    print(f"다음 영업일: {next_trading.strftime('%Y-%m-%d')}")

    print("\n2026년 주요 공휴일:")
    for month in range(1, 13):
        for day in range(1, 32):
            try:
                test_date = datetime(2026, month, day)
                if is_holiday(test_date) and not is_weekend(test_date):
                    print(f"  {test_date.strftime('%Y-%m-%d')}: {get_holiday_name(test_date)}")
            except ValueError:
                continue
