"""KOSPI200 PIT(Point-In-Time) 종목 리스트 인프라.

시총 상위 200 근사 방식으로 as_of_date 기준 KOSPI200 구성 종목을 반환한다.
DB: robotrader_quant.daily_prices.market_cap

설계 원칙:
  - 캐시 우선: {CACHE_DIR}/{YYYY-MM}.json 에 월 단위 캐시
  - as_of_date가 거래일이 아니면 직전 거래일로 fallback (DB 실제 데이터 기준)
  - 종목코드는 항상 6자리 zero-padded 문자열
  - market_cap IS NOT NULL 종목만 포함
"""
from __future__ import annotations

import json
import logging
import os
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras

from RoboTrader_template.multiverse.data.pit_reader import _conn_quant

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# 상수
# ------------------------------------------------------------------ #
KOSPI200_TOP_N = 200

# 캐시 위치 — 환경변수 오버라이드 가능
_DEFAULT_CACHE_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent  # kis-trading-template/
    / "RoboTrader_template"
    / "cache"
    / "kospi200_pit"
)
CACHE_DIR = Path(os.getenv("KOSPI200_PIT_CACHE_DIR", str(_DEFAULT_CACHE_DIR)))


# ------------------------------------------------------------------ #
# 내부 헬퍼
# ------------------------------------------------------------------ #

def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(as_of_date: date) -> Path:
    """월 단위 캐시 파일 경로 반환."""
    return CACHE_DIR / f"{as_of_date.strftime('%Y-%m')}.json"


def _load_cache(as_of_date: date) -> Optional[list[str]]:
    """캐시 파일에서 종목 리스트 로드. 없으면 None."""
    path = _cache_path(as_of_date)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        stocks = data.get("stocks", [])
        if stocks:
            logger.debug("캐시 hit: %s (%d 종목)", path.name, len(stocks))
            return stocks
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("캐시 파일 읽기 실패 (%s): %s", path, exc)
    return None


def _save_cache(as_of_date: date, stocks: list[str]) -> None:
    """종목 리스트를 캐시 파일에 저장."""
    _ensure_cache_dir()
    path = _cache_path(as_of_date)
    payload = {
        "as_of_date": as_of_date.isoformat(),
        "stocks": stocks,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.debug("캐시 저장: %s (%d 종목)", path.name, len(stocks))


def _find_nearest_trading_date(as_of_date: date) -> Optional[date]:
    """DB에서 as_of_date 이하의 가장 가까운 거래일 반환. 데이터 없으면 None.

    date 컬럼이 text 타입이므로 ISO 형식 문자열로 비교.
    """
    with _conn_quant() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(date)
                FROM daily_prices
                WHERE date <= %(as_of_date)s
                  AND market_cap IS NOT NULL
                """,
                {"as_of_date": as_of_date.isoformat()},
            )
            row = cur.fetchone()
    if row and row[0]:
        return date.fromisoformat(row[0])
    return None


def _query_top_n(trading_date: date) -> list[str]:
    """trading_date 기준 시총 상위 KOSPI200_TOP_N 종목 코드 리스트 반환.

    date 컬럼이 text 타입이므로 ISO 형식 문자열로 비교.
    """
    with _conn_quant() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stock_code
                FROM daily_prices
                WHERE date = %(trading_date)s
                  AND market_cap IS NOT NULL
                ORDER BY market_cap DESC
                LIMIT %(top_n)s
                """,
                {"trading_date": trading_date.isoformat(), "top_n": KOSPI200_TOP_N},
            )
            rows = cur.fetchall()
    # 종목 코드는 항상 6자리 zero-padded
    return [str(r[0]).zfill(6) for r in rows]


def _last_trading_day_of_month(year: int, month: int) -> Optional[date]:
    """해당 월의 마지막 거래일 (DB에 있는 마지막 date) 반환.

    date 컬럼이 text 타입이므로 ISO 형식 문자열로 비교.
    """
    _, last_day = monthrange(year, month)
    month_end = date(year, month, last_day)
    month_start = date(year, month, 1)

    with _conn_quant() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(date)
                FROM daily_prices
                WHERE date BETWEEN %(m_start)s AND %(m_end)s
                  AND market_cap IS NOT NULL
                """,
                {"m_start": month_start.isoformat(), "m_end": month_end.isoformat()},
            )
            row = cur.fetchone()
    if row and row[0]:
        return date.fromisoformat(row[0])
    return None


def _last_trading_day_of_week(ref_date: date) -> Optional[date]:
    """ref_date가 속한 주의 마지막 거래일 (금요일 또는 이전 거래일) 반환.

    DB 실제 데이터 기준으로 해당 주 월요일~일요일 내 MAX(date).
    date 컬럼이 text 타입이므로 ISO 형식 문자열로 비교.
    """
    # 해당 주의 월요일
    monday = ref_date - timedelta(days=ref_date.weekday())
    sunday = monday + timedelta(days=6)

    with _conn_quant() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(date)
                FROM daily_prices
                WHERE date BETWEEN %(monday)s AND %(sunday)s
                  AND market_cap IS NOT NULL
                """,
                {"monday": monday.isoformat(), "sunday": sunday.isoformat()},
            )
            row = cur.fetchone()
    if row and row[0]:
        return date.fromisoformat(row[0])
    return None


def _iter_months(start: date, end: date):
    """start~end 기간의 (year, month) 순차 생성."""
    cur_year, cur_month = start.year, start.month
    while (cur_year, cur_month) <= (end.year, end.month):
        yield cur_year, cur_month
        if cur_month == 12:
            cur_year += 1
            cur_month = 1
        else:
            cur_month += 1


def _iter_weeks(start: date, end: date):
    """start~end 기간의 매주 금요일 날짜 순차 생성."""
    # start가 속한 주의 금요일부터 시작
    days_to_friday = (4 - start.weekday()) % 7  # 4 = 금요일
    first_friday = start + timedelta(days=days_to_friday)
    cur = first_friday
    while cur <= end:
        yield cur
        cur += timedelta(days=7)


def _iter_biweeks(start: date, end: date):
    """start~end 기간의 격주 금요일 날짜 순차 생성."""
    fridays = list(_iter_weeks(start, end))
    for i, friday in enumerate(fridays):
        if i % 2 == 0:
            yield friday


# ------------------------------------------------------------------ #
# 공개 API
# ------------------------------------------------------------------ #

def get_kospi200_pit(as_of_date: date) -> list[str]:
    """as_of_date 시점의 KOSPI200 종목 코드 리스트 반환 (시총 상위 200 근사).

    캐시 우선 조회. 없으면 DB에서 계산 후 캐시 영속.

    Args:
        as_of_date: 기준일 (해당 일자 또는 이전 가장 가까운 영업일의 시총 상위)

    Returns:
        list[str]: 종목 코드 200개 이하 (시총 내림차순). 데이터 부족 시 200개 미만 가능.
    """
    # 1) 캐시 조회 (월 단위 캐시 — 같은 달이면 동일 캐시 사용)
    cached = _load_cache(as_of_date)
    if cached is not None:
        return cached

    # 2) DB에서 가장 가까운 거래일 탐색
    trading_date = _find_nearest_trading_date(as_of_date)
    if trading_date is None:
        logger.warning(
            "get_kospi200_pit: %s 이전 데이터가 DB에 없습니다.", as_of_date
        )
        return []

    if trading_date != as_of_date:
        logger.debug(
            "get_kospi200_pit: %s → fallback %s (비거래일)", as_of_date, trading_date
        )

    # 3) 시총 상위 200 조회
    stocks = _query_top_n(trading_date)

    if not stocks:
        logger.warning(
            "get_kospi200_pit: %s 기준 종목 조회 결과 없음", trading_date
        )
        return []

    # 4) 캐시 저장 (as_of_date 기준으로 저장 — 월 단위)
    _save_cache(as_of_date, stocks)
    logger.info(
        "get_kospi200_pit: %s → %s, %d 종목 반환 (캐시 신규 저장)",
        as_of_date,
        trading_date,
        len(stocks),
    )
    return stocks


def get_kospi200_rebalance_calendar(
    start: date,
    end: date,
    freq: str = "monthly",
) -> dict[date, list[str]]:
    """start~end 기간의 리밸런싱 캘린더 반환.

    Args:
        start: 시작일
        end: 종료일
        freq: "monthly" (월말) | "weekly" (금요일) | "biweekly" (격주 금요일)

    Returns:
        dict[date, list[str]]: 리밸런싱일 → 종목 코드 200개 이하
    """
    if freq not in ("monthly", "weekly", "biweekly"):
        raise ValueError(f"freq는 'monthly', 'weekly', 'biweekly' 중 하나여야 합니다: {freq!r}")

    calendar: dict[date, list[str]] = {}

    if freq == "monthly":
        for year, month in _iter_months(start, end):
            trading_day = _last_trading_day_of_month(year, month)
            if trading_day is None:
                continue
            if not (start <= trading_day <= end):
                continue
            stocks = get_kospi200_pit(trading_day)
            if stocks:
                calendar[trading_day] = stocks

    elif freq == "weekly":
        for friday in _iter_weeks(start, end):
            trading_day = _last_trading_day_of_week(friday)
            if trading_day is None:
                continue
            if not (start <= trading_day <= end):
                continue
            stocks = get_kospi200_pit(trading_day)
            if stocks:
                calendar[trading_day] = stocks

    else:  # biweekly
        for friday in _iter_biweeks(start, end):
            trading_day = _last_trading_day_of_week(friday)
            if trading_day is None:
                continue
            if not (start <= trading_day <= end):
                continue
            stocks = get_kospi200_pit(trading_day)
            if stocks:
                calendar[trading_day] = stocks

    return calendar


def warm_cache(start: date, end: date, freq: str = "monthly") -> int:
    """캐시 워밍업 — 기간 내 모든 리밸런싱일을 사전 계산해 디스크에 저장.

    Returns: 새로 캐시된 리밸런싱일 수
    """
    _ensure_cache_dir()
    calendar = get_kospi200_rebalance_calendar(start, end, freq)
    count = len(calendar)
    logger.info("warm_cache: %s~%s (%s) — %d 리밸런싱일 캐시 완료", start, end, freq, count)
    return count


def clear_cache() -> int:
    """캐시 디렉토리의 JSON 파일 전부 삭제.

    Returns: 삭제된 파일 수
    """
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    logger.info("clear_cache: %d 파일 삭제 완료 (%s)", count, CACHE_DIR)
    return count
