"""
lib/signals/calendar_tom.py — Turn-of-Month (TOM) 캘린더 효과 시그널 (PIT-safe)
=================================================================================

출처: 07_calendar.md #3 Turn-of-Month Effect
학술 근거:
  - Lee & Kim (2022) Pacific-Basin Finance Journal — KOSPI/KOSDAQ 양쪽 유의
  - Lakonishok & Smidt (1988) JF — 원전: 월말 4영업일 + 월초 3영업일
  - Yun & Kim (2014), Hong et al. (2014) — 한국 복수 검증

정의:
  TOM 윈도우 = 해당 월 마지막 N영업일 + 다음 달 첫 M영업일
  기본 파라미터: N=4 (월말), M=3 (월초) — Lakonishok-Smidt 원전값

PIT 강제:
  - 캘린더는 daily_prices.date DISTINCT로 한국 실제 영업일 추출 (미래 영업일 미포함)
  - 백테스트 시뮬레이션에서 스캔 날짜를 순차적으로 처리하면
    scan_dates 내의 날짜까지만 캘린더가 필요하므로 look-ahead 없음
  - 실운영 주의: 실제 운영에서는 KRX 공식 휴장일 캘린더 인터페이스를
    사용해야 함 (미래 영업일은 KRX 공식 발표 기준으로만 파악 가능)
    인터페이스: get_trading_calendar(start, end, source='daily_prices')

사용 예시:
-----------
>>> from datetime import date
>>> from lib.signals.calendar_tom import get_trading_calendar, is_tom_window, tom_signal
>>>
>>> # 1) DB에서 한국 영업일 캘린더 조회 (PIT: start~end 범위만)
>>> cal = get_trading_calendar(date(2021, 1, 1), date(2026, 5, 22))
>>>
>>> # 2) 특정 날짜가 TOM 윈도우인지 판정
>>> is_tom_window(date(2024, 1, 30), n_end=4, m_start=3, calendar=cal)
True
>>>
>>> # 3) 날짜 목록에 대한 True/False 시리즈
>>> import pandas as pd
>>> scan_dates = pd.bdate_range('2024-01-01', '2024-03-31').date.tolist()
>>> signal = tom_signal(scan_dates, n_end=4, m_start=3, calendar=cal)
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

# config.constants(일봉 소스 resolver) import — CWD·import 경로와 무관하게
# RoboTrader_template 루트를 sys.path 에 보정한다(pit_reader 와 동일 패턴).
_TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
if str(_TEMPLATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEMPLATE_ROOT))

from config.constants import resolve_daily_source_db  # noqa: E402

# ---------------------------------------------------------------------------
# 운영 환경 인터페이스 명시 (KRX 공식 캘린더)
# ---------------------------------------------------------------------------
# 실운영 시 아래 인터페이스를 KRX 공식 휴장일 캘린더로 교체해야 합니다.
# 현재 구현은 daily_prices의 distinct date를 한국 영업일로 사용합니다.
# KRX 공식: https://data.krx.co.kr/ → 기본통계 → 기타 → 휴장일
_KRX_CALENDAR_SOURCE = "daily_prices"  # 'daily_prices' | 'krx_official'


# ---------------------------------------------------------------------------
# get_trading_calendar
# ---------------------------------------------------------------------------

def get_trading_calendar(
    start: date,
    end: date,
    host: str = "127.0.0.1",
    port: int = 5433,
    database: str | None = None,
    user: str = "robotrader",
    password: str = "1234",
) -> list[date]:
    """한국 영업일 캘린더를 daily_prices.date DISTINCT로 추출.

    PIT 강제:
        start~end 범위만 조회하므로 미래 영업일 포함 없음.
        백테스트에서 scan_dates 최대 날짜를 end로 설정하면 완전 PIT-safe.

    실운영 주의:
        미래 영업일(공휴일 포함)은 KRX 공식 휴장일 캘린더를 사용해야 합니다.
        현재 구현은 daily_prices에 이미 수집된 과거 영업일만 반환합니다.

    Parameters
    ----------
    start : date
        조회 시작일 (inclusive).
    end : date
        조회 종료일 (inclusive).
    host, port, database, user, password : str / int
        DB 접속 정보. 환경변수 TIMESCALE_* 를 우선 적용.

    Returns
    -------
    list[date]
        오름차순 정렬된 영업일 date 목록.

    Raises
    ------
    RuntimeError
        DB 조회 실패 시.
    """
    # 환경변수 우선 적용 (DB connection.py와 동일 패턴)
    _host = os.getenv("TIMESCALE_HOST", host)
    _port = int(os.getenv("TIMESCALE_PORT", str(port)))
    _user = os.getenv("TIMESCALE_USER", user)
    _pw   = os.getenv("TIMESCALE_PASSWORD", password)
    # daily_prices 를 읽으므로 일봉 SSOT resolver 를 따른다(기본 kis_template).
    # 과거엔 database 기본값이 robotrader_quant 하드코딩 + TIMESCALE_DB(운영 DB) 로
    # override 되는 구조라, 가격 소스와 운영 DB 가 뒤섞이고 .env 없는 연구에서는
    # 동결된 레거시를 읽었다. 호출자가 database 를 명시하면 그 값이 최우선.
    _db = database if database is not None else resolve_daily_source_db()

    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "get_trading_calendar requires psycopg2. "
            "Install with: pip install psycopg2-binary"
        ) from exc

    sql = """
        SELECT DISTINCT date::text
        FROM daily_prices
        WHERE date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          AND date >= %s AND date <= %s
        ORDER BY date
    """
    try:
        conn = psycopg2.connect(
            host=_host, port=_port, database=_db, user=_user, password=_pw
        )
        cur = conn.cursor()
        cur.execute(sql, (start.isoformat(), end.isoformat()))
        rows = cur.fetchall()
        conn.close()
    except Exception as exc:
        raise RuntimeError(f"get_trading_calendar DB 조회 실패: {exc}") from exc

    return [date.fromisoformat(r[0]) for r in rows]


# ---------------------------------------------------------------------------
# _build_month_windows
# ---------------------------------------------------------------------------

def _build_month_windows(
    calendar: list[date],
    n_end: int,
    m_start: int,
) -> dict[date, bool]:
    """캘린더에서 TOM 윈도우 날짜 집합을 사전 계산.

    월별로 영업일을 그룹핑한 후:
      - 각 월의 마지막 n_end 영업일 → TOM
      - 각 월의 첫 m_start 영업일  → TOM

    Parameters
    ----------
    calendar : list[date]
        오름차순 영업일 목록.
    n_end : int
        월말 TOM 영업일 수.
    m_start : int
        월초 TOM 영업일 수.

    Returns
    -------
    dict[date, bool]
        날짜 → True/False 맵핑.
    """
    # 월별 영업일 그룹핑 (year, month) → sorted list[date]
    month_days: dict[tuple[int, int], list[date]] = defaultdict(list)
    for d in sorted(calendar):
        month_days[(d.year, d.month)].append(d)

    tom_set: set[date] = set()

    for days in month_days.values():
        # 월말 마지막 n_end 영업일
        for d in days[-n_end:]:
            tom_set.add(d)
        # 월초 첫 m_start 영업일
        for d in days[:m_start]:
            tom_set.add(d)

    return {d: (d in tom_set) for d in calendar}


# ---------------------------------------------------------------------------
# is_tom_window
# ---------------------------------------------------------------------------

def is_tom_window(
    target_date: date,
    n_end: int = 4,
    m_start: int = 3,
    calendar: Optional[list[date]] = None,
) -> bool:
    """단일 날짜가 TOM 윈도우 안인지 판정.

    TOM 윈도우 = 해당 월 마지막 n_end 영업일 OR 다음 달 첫 m_start 영업일.

    PIT 강제:
        calendar는 target_date 이전까지의 영업일만 포함해야 합니다.
        실운영에서는 KRX 공식 휴장 캘린더를 calendar로 전달하세요.

    Parameters
    ----------
    target_date : date
        판정할 날짜.
    n_end : int
        월말 TOM 영업일 수 (기본값 4, Lakonishok-Smidt 원전).
    m_start : int
        월초 TOM 영업일 수 (기본값 3, Lakonishok-Smidt 원전).
    calendar : list[date] | None
        한국 영업일 목록 (오름차순). None이면 ValueError.

    Returns
    -------
    bool
        True = TOM 윈도우 안, False = Non-TOM.

    Raises
    ------
    ValueError
        calendar가 None이거나 target_date가 calendar에 없을 때.
    """
    if calendar is None:
        raise ValueError(
            "is_tom_window: calendar 파라미터가 필요합니다. "
            "get_trading_calendar()로 한국 영업일 목록을 먼저 조회하세요."
        )
    if not calendar:
        raise ValueError("is_tom_window: calendar가 비어 있습니다.")

    # 월별 그룹핑 → TOM 집합
    window_map = _build_month_windows(calendar, n_end, m_start)

    if target_date not in window_map:
        # 비영업일(휴일/주말)이면 False 반환 (TOM 윈도우가 아님)
        return False

    return window_map[target_date]


# ---------------------------------------------------------------------------
# tom_signal
# ---------------------------------------------------------------------------

def tom_signal(
    scan_dates: list[date],
    n_end: int = 4,
    m_start: int = 3,
    calendar: Optional[list[date]] = None,
) -> pd.Series:
    """날짜 목록에 대한 TOM 시그널 True/False 시리즈.

    각 scan_date가 TOM 윈도우(월말 n_end 영업일 + 월초 m_start 영업일) 안이면 True.

    PIT 강제:
        calendar는 scan_dates의 최대 날짜 이내까지만 포함해야 합니다.
        백테스트에서 scan_dates 순서대로 처리하면 미래 영업일 참조 없음.

    Parameters
    ----------
    scan_dates : list[date]
        시그널 판정할 날짜 목록.
    n_end : int
        월말 TOM 영업일 수 (기본값 4).
    m_start : int
        월초 TOM 영업일 수 (기본값 3).
    calendar : list[date] | None
        한국 영업일 목록. None이면 scan_dates 자체를 캘린더로 사용
        (백테스트 헬퍼 — PIT 조건: scan_dates가 이미 완전 영업일 목록인 경우만).

    Returns
    -------
    pd.Series
        index=scan_dates, dtype=bool, name='tom_signal'.

    Notes
    -----
    Stage 매핑: Stage A (진입 필터 오버레이) / Stage B (신호 강도 가중치)
    버킷: swing (2~5일 보유)
    """
    if calendar is None:
        # scan_dates 자체를 캘린더로 사용 (백테스트 전용 헬퍼)
        calendar = sorted(set(scan_dates))

    window_map = _build_month_windows(calendar, n_end, m_start)

    values = [window_map.get(d, False) for d in scan_dates]
    return pd.Series(values, index=scan_dates, dtype=bool, name="tom_signal")
