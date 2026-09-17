"""거래일 달력 헬퍼 — 순수 함수(DB 없음).

달력 SSOT = `daily_prices` 의 의사티커 `KOSPI` 날짜(재현기 `replayer/loader.py::CALENDAR_TICKER` 와 같다).
DB 에서 달력을 읽는 쪽은 `sources.load_calendar()` 이고, 이 파일은 받은 목록만 다룬다.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date
from typing import List, Optional, Sequence


def _sorted(cal: Sequence[date]) -> List[date]:
    return sorted(set(cal))


def prev_trading_day(cal: Sequence[date], d: date) -> Optional[date]:
    """`d` «직전» 거래일(엄격히 `< d`). 휴장 다음 날이면 휴장 전 마지막 거래일.

    라이브 대응: `core/candidate_selector.py::_fetch_candidates_for_strategy` 가
    `get_previous_trading_day(now_kst())` 로 D-1 스냅샷을 조회한다.
    """
    cs = _sorted(cal)
    i = bisect_left(cs, d)
    return cs[i - 1] if i > 0 else None


def days_in_range(cal: Sequence[date], start: date, end: date) -> List[date]:
    cs = _sorted(cal)
    return cs[bisect_left(cs, start):bisect_right(cs, end)]


def last_n_days(cal: Sequence[date], end: date, n: int) -> List[date]:
    """`end` 이하 마지막 n 거래일(오름차순)."""
    cs = _sorted(cal)
    j = bisect_right(cs, end)
    return cs[max(0, j - n):j]


def days_after(cal: Sequence[date], d: date, n: Optional[int] = None) -> List[date]:
    """`d` «이후»(엄격히 `> d`) 거래일. n 이 주어지면 최대 n 개."""
    cs = _sorted(cal)
    out = cs[bisect_right(cs, d):]
    return out if n is None else out[:n]
