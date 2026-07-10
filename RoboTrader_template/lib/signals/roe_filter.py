"""
ROE Quintile Filter — PIT-safe Stage A Universe Filter (F-11)
=============================================================

대원칙
------
① No Look-Ahead: scan_date T 시점에 이미 발표(report_date ≤ scan_date)된
   재무 데이터만 사용.
② 추측 금지: 임계값·분위 수는 호출자가 지정. 기본값만 카탈로그 기준.

데이터 소스
-----------
- robotrader_quant.financial_statements (report_date, stock_code, roe)
  report_date는 'YYYY-MM-DD' 문자열 또는 date.
  연간 결산 기준 (12월/11월/6월 등 다양한 결산월).

PIT 처리 방식
-------------
- scan_date 이전에 발표된(report_date <= scan_date) 레코드만 허용.
- 종목별로 가장 최근 report_date의 ROE 한 건만 사용 (중복 방지).
- yearly_fundamentals 사용 시 scan_date.year >= roe_year + 1 제약 적용
  (당해연도 연간 재무는 익년 발표가 보수적 PIT 가정).

함수 시그니처
-------------
- roe_pit(scan_date, stock_codes) -> pd.Series[float]
  종목별 PIT-safe 최신 ROE. index=stock_code.
- roe_quintile(scan_date, stock_codes, n_buckets) -> pd.Series[int]
  종목별 ROE 분위(1=최하위, n_buckets=최상위). NaN은 제외 후 분위 배정 → NaN 반환.
- roe_filter(scan_date, stock_codes, min_quintile) -> list[str]
  ROE 분위 >= min_quintile인 종목 코드 목록.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB 연결 헬퍼
# ---------------------------------------------------------------------------

def _get_connection():
    """robotrader_quant DB 연결 반환. 호출자가 close() 책임."""
    try:
        import psycopg2
        return psycopg2.connect(
            host="127.0.0.1",
            port=5433,
            dbname="robotrader_quant",
            user="robotrader",
            password="1234",
        )
    except ImportError as e:
        raise ImportError("psycopg2 not installed. pip install psycopg2-binary") from e


# ---------------------------------------------------------------------------
# roe_pit — PIT-safe 종목별 최신 ROE 조회
# ---------------------------------------------------------------------------

def roe_pit(
    scan_date: date,
    stock_codes: list[str],
    *,
    conn=None,
) -> pd.Series:
    """scan_date T 시점에 알려진 종목별 가장 최신 ROE (PIT-safe).

    Parameters
    ----------
    scan_date : date
        기준 날짜. 이 날짜 이전(≤)에 report_date가 있는 레코드만 사용.
    stock_codes : list[str]
        조회 대상 종목 코드 목록.
    conn : psycopg2 connection, optional
        외부에서 주입할 DB 연결. None이면 내부 연결 생성.

    Returns
    -------
    pd.Series
        index=stock_code, values=ROE (float). 데이터 없는 종목은 NaN.
        name="roe".

    Notes
    -----
    - report_date <= scan_date 조건으로 미래 데이터 차단 (No Look-Ahead).
    - 종목별 최신 report_date 1건만 사용.
    - roe IS NOT NULL 조건으로 결측 행 제외 후 조회.
    """
    if not stock_codes:
        return pd.Series(dtype=float, name="roe")

    scan_date_str = scan_date.isoformat()

    _own_conn = conn is None
    if _own_conn:
        conn = _get_connection()

    try:
        placeholders = ",".join(["%s"] * len(stock_codes))
        sql = f"""
            SELECT DISTINCT ON (stock_code)
                stock_code,
                roe
            FROM financial_statements
            WHERE stock_code IN ({placeholders})
              AND report_date <= %s
              AND roe IS NOT NULL
            ORDER BY stock_code, report_date DESC
        """
        params = list(stock_codes) + [scan_date_str]

        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        if _own_conn:
            conn.close()

    if not rows:
        return pd.Series(
            [float("nan")] * len(stock_codes),
            index=stock_codes,
            name="roe",
        )

    result = pd.Series(
        {row[0]: float(row[1]) for row in rows},
        name="roe",
    )

    # 요청한 전체 종목 index로 reindex (누락 종목 → NaN)
    result = result.reindex(stock_codes)
    result.index.name = "stock_code"
    return result


# ---------------------------------------------------------------------------
# roe_quintile — cross-section 분위 계산
# ---------------------------------------------------------------------------

def roe_quintile(
    scan_date: date,
    stock_codes: list[str],
    n_buckets: int = 5,
    *,
    conn=None,
) -> pd.Series:
    """종목별 ROE 분위 (1=최하위, n_buckets=최상위).

    Parameters
    ----------
    scan_date : date
        기준 날짜 (PIT 컷오프).
    stock_codes : list[str]
        분위 계산 대상 종목 코드 목록.
    n_buckets : int, optional
        분위 수. 기본값 5 (quintile). 최소 2.
    conn : psycopg2 connection, optional
        외부 DB 연결 주입용.

    Returns
    -------
    pd.Series
        index=stock_code, values=int(1~n_buckets) 또는 NaN.
        - ROE 데이터 없는 종목 → NaN.
        - ROE 있는 종목 수가 n_buckets 미만이면 경고 후 최선 분위 계산
          (가용 종목 수가 1이면 전부 분위 1).
        name="roe_quintile".

    Notes
    -----
    - 분위 계산은 scan_date T 시점 cross-section에서만 수행 (PIT 강제).
    - pd.qcut duplicate_bins='drop' + labels=False 활용.
    """
    if n_buckets < 2:
        raise ValueError(f"n_buckets must be >= 2, got {n_buckets}")

    roe_series = roe_pit(scan_date, stock_codes, conn=conn)

    valid = roe_series.dropna()
    n_valid = len(valid)

    result = pd.Series(
        [float("nan")] * len(stock_codes),
        index=stock_codes,
        name="roe_quintile",
    )
    result.index.name = "stock_code"

    if n_valid == 0:
        logger.warning(
            "roe_quintile: scan_date=%s — ROE 데이터 있는 종목 없음. "
            "전체 NaN 반환.",
            scan_date,
        )
        return result

    if n_valid < n_buckets:
        logger.warning(
            "roe_quintile: scan_date=%s — ROE 있는 종목 %d개 < n_buckets=%d. "
            "실제 분위 수 축소됨.",
            scan_date,
            n_valid,
            n_buckets,
        )

    if n_valid == 1:
        # 단일 종목: 분위 1 할당
        result.loc[valid.index[0]] = 1
        return result

    # pd.qcut: duplicate 경계 허용, labels 1~n_buckets
    effective_buckets = min(n_buckets, n_valid)
    labels = list(range(1, effective_buckets + 1))

    try:
        quintiles = pd.qcut(
            valid,
            q=effective_buckets,
            labels=labels,
            duplicates="drop",
        )
    except ValueError:
        # 모든 값이 동일한 극단적 케이스 → 분위 1
        logger.warning(
            "roe_quintile: scan_date=%s — ROE 값이 모두 동일하여 qcut 실패. "
            "전체 분위 1 할당.",
            scan_date,
        )
        result.loc[valid.index] = 1
        return result

    result.loc[valid.index] = quintiles.astype("Int64").astype(float)
    return result


# ---------------------------------------------------------------------------
# roe_filter — Stage A universe filter
# ---------------------------------------------------------------------------

def roe_filter(
    scan_date: date,
    stock_codes: list[str],
    min_quintile: int = 4,
    n_buckets: int = 5,
    *,
    conn=None,
) -> list[str]:
    """ROE 분위 >= min_quintile인 종목만 반환 (Stage A universe filter).

    Parameters
    ----------
    scan_date : date
        기준 날짜 (PIT 컷오프).
    stock_codes : list[str]
        필터 대상 종목 코드 목록.
    min_quintile : int, optional
        최소 분위 임계값. 기본값 4 (Q4 이상 유지 = 상위 40%).
        Q1 제외만 원하면 min_quintile=2.
    n_buckets : int, optional
        분위 수. 기본값 5.
    conn : psycopg2 connection, optional
        외부 DB 연결 주입용.

    Returns
    -------
    list[str]
        ROE 분위 >= min_quintile인 종목 코드 목록.
        ROE 데이터 없는 종목(NaN)은 제외.

    Notes
    -----
    Stage A 사용 예:
        universe = roe_filter(scan_date, candidates, min_quintile=4)
        # → ROE 상위 40% 종목만 universe에 유지
    """
    if min_quintile < 1 or min_quintile > n_buckets:
        raise ValueError(
            f"min_quintile={min_quintile} must be in [1, n_buckets={n_buckets}]"
        )

    quintiles = roe_quintile(
        scan_date, stock_codes, n_buckets=n_buckets, conn=conn
    )

    passed = quintiles[quintiles >= min_quintile].dropna()
    return list(passed.index)
