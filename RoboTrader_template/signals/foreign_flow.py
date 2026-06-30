"""
외국인 5일 누적 순매매량 시그널 (F-06)
=======================================

PIT 보장:
  - trade_date T일 장 마감 후 네이버 금융(frgn.naver) 발표 (T+0 저녁)
  - T+1 시초가 의사결정에 T일 데이터만 사용 (No Look-Ahead)
  - end_date 파라미터는 반드시 scan_date - 1 영업일 이하로 설정

데이터 소스:
  - DB: kis_template.foreign_flow.foreign_net_vol (네이버 순매매량, shares)
        — collectors/foreign_flow_collector.py 가 EOD 자동 수집.
  - 부호 의미 보존: 5일 누적 > 0 이면 외국인 순매수(매수 우위). 거래대금이 아닌
    순매매'량'(주식수) 기준이나 부호(매수/매도)는 동일하므로 시그널 의미 불변.
  - Fallback: 없음 (DB 미적재 시 NaN 반환 → 시그널 False).
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import psycopg2

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DB 연결 설정 — 신규 kis_template DB (KIS_DB_* env, KisDbConnection 과 동일 기본값)
# ─────────────────────────────────────────────────────────────────────────────
_DB_DEFAULTS = dict(
    host=os.getenv("KIS_DB_HOST", "localhost"),
    port=int(os.getenv("KIS_DB_PORT", "5433")),
    user=os.getenv("KIS_DB_USER", "robotrader"),
    password=os.getenv("KIS_DB_PASSWORD", "1234"),
    database=os.getenv("KIS_DB_NAME", "kis_template"),
)


def _get_conn():
    return psycopg2.connect(**_DB_DEFAULTS)


# ─────────────────────────────────────────────────────────────────────────────
# 핵심 함수
# ─────────────────────────────────────────────────────────────────────────────

def foreign_net_buy_5d_cum(stock_code: str, end_date: date) -> float:
    """end_date 포함 이전 5영업일 외국인 순매매량(주) 합산 반환.

    PIT 보장: end_date는 반드시 scan_date - 1 영업일 이하여야 함.
    즉, T+1 시초가 의사결정 시 end_date = T일 (어제).

    Parameters
    ----------
    stock_code : str
        종목코드 (6자리)
    end_date : date
        기준일 (T일). T+1 의사결정에 사용 가능한 마지막 날.

    Returns
    -------
    float
        5영업일 누적 순매매량 (주). 양수면 외국인 순매수 우위. 데이터 없으면 float('nan').
    """
    # 여유있게 end_date 기준 10일 전부터 조회해 영업일 5일 확보
    lookback_from = end_date - timedelta(days=14)

    sql = """
        SELECT date, foreign_net_vol
        FROM foreign_flow
        WHERE stock_code = %s
          AND date BETWEEN %s AND %s
        ORDER BY date DESC
        LIMIT 5
    """
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (stock_code, lookback_from, end_date))
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[ForeignFlow] DB 조회 실패 %s %s: %s", stock_code, end_date, exc)
        return float("nan")

    if not rows:
        logger.debug("[ForeignFlow] 데이터 없음 %s ~ %s %s", lookback_from, end_date, stock_code)
        return float("nan")

    total = sum(row[1] for row in rows if row[1] is not None)
    logger.debug(
        "[ForeignFlow] %s 5일 누적 순매매량 %.0f주 (%d일치)", stock_code, total, len(rows)
    )
    return float(total)


def foreign_flow_signal(
    stock_codes: list[str],
    scan_date: date,
    threshold_pct: float = 1.0,
) -> pd.Series:
    """종목 리스트에 대해 외국인 5일 누적 순매매량 시그널 계산.

    PIT 보장: scan_date는 의사결정일 (T+1). end_date = scan_date - 1 영업일.
    즉, 오늘 장 개시 전에 호출할 때 scan_date=오늘, end_date=어제.

    Parameters
    ----------
    stock_codes : list[str]
        대상 종목코드 리스트
    scan_date : date
        의사결정일 (T+1 = 오늘 장 개시 시점)
    threshold_pct : float
        시그널 임계값. 5일 누적 순매매량이 양수인 종목만 True.
        기본 1.0 (순매매량이 양수면 True, 임계값은 향후 확장용 예비 파라미터).

    Returns
    -------
    pd.Series
        index = stock_code, values = bool (True = 외국인 5일 누적 순매매량 양수)
    """
    # PIT: 의사결정일(scan_date)에서 1일 전 = T일 데이터 사용
    end_date = scan_date - timedelta(days=1)

    results: dict[str, bool] = {}
    for code in stock_codes:
        val = foreign_net_buy_5d_cum(code, end_date)
        if pd.isna(val):
            results[code] = False
        else:
            results[code] = val > 0

    return pd.Series(results, dtype=bool)
