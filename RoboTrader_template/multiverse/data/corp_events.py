"""corp_events 테이블 접근 레이어.

한국 시장 특수 이벤트(관리종목/거래정지/액면분할 등) PIT 조회.
corp_events 테이블이 비어 있어도 모든 함수는 정상 동작:
  - 빈 결과 → False / [] / 1.0

테이블 스키마 (02-multiverse.sql):
  corp_events(stock_code TEXT, event_type TEXT, event_date DATE, meta JSONB)
  event_type ∈ {split, rights_issue, bonus_issue, dividend_ex,
                administrative, caution, warning, halt}
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional

import pandas as pd
import psycopg2
import psycopg2.extras
import psycopg2.extensions
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# NUMERIC → float 자동 변환
# ------------------------------------------------------------------ #
DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(DEC2FLOAT)

# ------------------------------------------------------------------ #
# 연결 설정
# ------------------------------------------------------------------ #
_DB_DEFAULTS = dict(
    host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    port=int(os.getenv("TIMESCALE_PORT", "5433")),
    user=os.getenv("TIMESCALE_USER", "robotrader"),
    password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    database=os.getenv("TIMESCALE_DB", "robotrader"),
)

# Universe 필터에서 제외할 이벤트 타입
_EXCLUSION_TYPES = ("administrative", "caution", "warning", "halt")


@contextmanager
def _conn():
    conn = psycopg2.connect(**_DB_DEFAULTS)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# 공개 API
# ------------------------------------------------------------------ #

def read_events(
    stock_code: str,
    as_of_date: date,
    event_types: Optional[list[str]] = None,
) -> pd.DataFrame:
    """corp_events 조회 — event_date <= as_of_date 인 이벤트만.

    Parameters
    ----------
    stock_code:
        종목코드
    as_of_date:
        기준일 (이 날짜 이하 이벤트만 반환)
    event_types:
        필터할 이벤트 타입 목록. None이면 전체 반환.

    Returns
    -------
    pd.DataFrame: columns = [stock_code, event_type, event_date, meta]
    """
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if event_types:
                sql = """
                    SELECT stock_code, event_type, event_date, meta
                    FROM corp_events
                    WHERE stock_code = %(stock_code)s
                      AND event_date <= %(as_of_date)s
                      AND event_type = ANY(%(event_types)s)
                    ORDER BY event_date
                """
                cur.execute(
                    sql,
                    dict(
                        stock_code=stock_code,
                        as_of_date=as_of_date,
                        event_types=event_types,
                    ),
                )
            else:
                sql = """
                    SELECT stock_code, event_type, event_date, meta
                    FROM corp_events
                    WHERE stock_code = %(stock_code)s
                      AND event_date <= %(as_of_date)s
                    ORDER BY event_date
                """
                cur.execute(sql, dict(stock_code=stock_code, as_of_date=as_of_date))

            rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(
            columns=["stock_code", "event_type", "event_date", "meta"]
        )

    df = pd.DataFrame(rows)
    df["event_date"] = pd.to_datetime(df["event_date"]).dt.date
    return df


def is_administrative(stock_code: str, as_of_date: date) -> bool:
    """관리종목 편입(administrative) 이벤트 존재 여부.

    end_date IS NULL(미해제) 또는 end_date > as_of_date(아직 유효)인 경우만 True.

    Returns
    -------
    bool: as_of_date 시점 관리종목 편입 상태이면 True
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM corp_events
                WHERE stock_code = %(stock_code)s
                  AND event_type = 'administrative'
                  AND event_date <= %(as_of_date)s
                  AND (end_date IS NULL OR end_date > %(as_of_date)s)
                LIMIT 1
                """,
                dict(stock_code=stock_code, as_of_date=as_of_date),
            )
            return cur.fetchone() is not None


def is_halted(stock_code: str, as_of_date: date) -> bool:
    """거래정지(halt) 이벤트 존재 여부.

    end_date IS NULL(미해제) 또는 end_date > as_of_date(아직 유효)인 경우만 True.

    Returns
    -------
    bool: as_of_date 시점 거래정지 상태이면 True
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM corp_events
                WHERE stock_code = %(stock_code)s
                  AND event_type = 'halt'
                  AND event_date <= %(as_of_date)s
                  AND (end_date IS NULL OR end_date > %(as_of_date)s)
                LIMIT 1
                """,
                dict(stock_code=stock_code, as_of_date=as_of_date),
            )
            return cur.fetchone() is not None


def get_adj_factor(stock_code: str, as_of_date: date) -> float:
    """as_of_date 시점 누적 수정주가 배수.

    daily_prices.adj_factor 컬럼이 있으면 해당 값 사용.
    없으면 corp_events의 split/rights_issue/bonus_issue 누적으로 계산.
    이벤트도 없으면 1.0 반환.

    Returns
    -------
    float: 누적 수정 배수 (이벤트 없으면 1.0)
    """
    # 1순위: daily_prices.adj_factor 컬럼 조회
    try:
        import psycopg2 as _pg
        conn = _pg.connect(**_DB_DEFAULTS)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # adj_factor 컬럼 존재 확인
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'daily_prices'
                      AND column_name = 'adj_factor'
                    LIMIT 1
                    """
                )
                if cur.fetchone() is not None:
                    # 기준일 직전 가장 최근 adj_factor 반환
                    cur.execute(
                        """
                        SELECT COALESCE(adj_factor, 1.0) AS adj_factor
                        FROM daily_prices
                        WHERE stock_code = %(stock_code)s
                          AND date < %(as_of_date)s
                        ORDER BY date DESC
                        LIMIT 1
                        """,
                        dict(stock_code=stock_code, as_of_date=as_of_date),
                    )
                    row = cur.fetchone()
                    if row is not None:
                        return float(row["adj_factor"])
        finally:
            conn.close()
    except Exception as e:
        logger.debug("adj_factor DB 조회 실패, corp_events fallback: %s", e)

    # 2순위: corp_events split/rights_issue/bonus_issue 누적
    df = read_events(
        stock_code,
        as_of_date,
        event_types=["split", "rights_issue", "bonus_issue"],
    )

    if df.empty:
        return 1.0

    factor = 1.0
    for _, row in df.iterrows():
        meta = row.get("meta") or {}
        ratio = meta.get("ratio", 1.0) if isinstance(meta, dict) else 1.0
        if ratio and ratio > 0:
            factor *= float(ratio)

    return factor if factor > 0 else 1.0


def filter_universe(
    stock_codes: list[str],
    as_of_date: date,
) -> list[str]:
    """관리종목/투자경고/거래정지/투자주의 자동 제외.

    corp_events 테이블이 비어 있으면 입력 리스트 그대로 반환.

    Parameters
    ----------
    stock_codes:
        필터링할 종목코드 목록
    as_of_date:
        기준일

    Returns
    -------
    list[str]: 제외 대상 종목이 빠진 종목코드 목록
    """
    if not stock_codes:
        return []

    with _conn() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT DISTINCT stock_code
                FROM corp_events
                WHERE stock_code = ANY(%(codes)s)
                  AND event_date <= %(as_of_date)s
                  AND event_type = ANY(%(exclusion_types)s)
                  AND (end_date IS NULL OR end_date > %(as_of_date)s)
            """
            cur.execute(
                sql,
                dict(
                    codes=stock_codes,
                    as_of_date=as_of_date,
                    exclusion_types=list(_EXCLUSION_TYPES),
                ),
            )
            excluded = {r[0] for r in cur.fetchall()}

    if excluded:
        logger.info(
            "[corp_events] %s — %d종목 Universe 제외: %s",
            as_of_date,
            len(excluded),
            sorted(excluded),
        )

    return [c for c in stock_codes if c not in excluded]
