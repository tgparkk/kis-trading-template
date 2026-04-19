"""
외부 DB 조회용 헬퍼 함수 모음 (stateless).
strategy_analysis / robotrader_quant DB에서 과거 데이터를 읽는다.
접속 실패 시 warning 로그 + 빈 DataFrame 반환 (raise 금지).
"""

import logging
import os
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

try:
    import psycopg2
except ImportError:
    psycopg2 = None

logger = logging.getLogger(__name__)

# 외부 DB 기본 접속 파라미터 (환경변수로 override 가능)
DEFAULT_EXT_DB = {
    "host": os.getenv("EXTERNAL_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("EXTERNAL_DB_PORT", "5433")),
    "user": os.getenv("EXTERNAL_DB_USER", "postgres"),
    "password": os.getenv("EXTERNAL_DB_PASSWORD", "1234"),
}


def _connect(dbname: str):
    """psycopg2 접속 헬퍼. psycopg2 없거나 접속 실패 시 None 반환."""
    if psycopg2 is None:
        logger.warning("psycopg2 not installed — external DB unavailable")
        return None
    try:
        return psycopg2.connect(dbname=dbname, **DEFAULT_EXT_DB)
    except Exception as exc:
        logger.warning("External DB connection failed (%s): %s", dbname, exc)
        return None


def get_sectors(
    stock_codes: Optional[List[str]] = None,
    target_sectors: Optional[List[str]] = None,
) -> pd.DataFrame:
    """strategy_analysis.stock_sector 조회.

    target_sectors 는 sector_name LIKE 키워드 목록 (None 이면 전 섹터).
    stock_codes 가 주어지면 해당 종목만 반환.
    반환: DataFrame[stock_code, stock_name, sector_code, sector_name, market]
    """
    conn = _connect("strategy_analysis")
    if conn is None:
        return pd.DataFrame()

    conditions: List[str] = []
    params: List = []

    if stock_codes:
        placeholders = ",".join(["%s"] * len(stock_codes))
        conditions.append(f"stock_code IN ({placeholders})")
        params.extend(stock_codes)

    if target_sectors:
        like_clauses = " OR ".join(["sector_name LIKE %s"] * len(target_sectors))
        conditions.append(f"({like_clauses})")
        params.extend(f"%{kw}%" for kw in target_sectors)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT stock_code, stock_name, sector_code, sector_name, market
        FROM stock_sector
        {where}
        ORDER BY stock_code
    """

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return pd.DataFrame(
            rows,
            columns=["stock_code", "stock_name", "sector_code", "sector_name", "market"],
        )
    except Exception as exc:
        logger.warning("get_sectors query failed: %s", exc)
        return pd.DataFrame()
    finally:
        conn.close()


def get_daily_candles_range(
    stock_codes: List[str],
    start_date: date,
    end_date: date,
) -> Dict[str, pd.DataFrame]:
    """strategy_analysis.daily_candles 에서 기간별 일봉 로드.

    반환: {stock_code: DataFrame[date, open, high, low, close, volume, trading_value]}
    컬럼명은 BacktestEngine 호환으로 open/high/low/close 로 rename.
    """
    if not stock_codes:
        return {}

    conn = _connect("strategy_analysis")
    if conn is None:
        return {}

    placeholders = ",".join(["%s"] * len(stock_codes))
    query = f"""
        SELECT stock_code, trade_date,
               open_price, high_price, low_price, close_price,
               volume, trading_value
        FROM daily_candles
        WHERE stock_code IN ({placeholders})
          AND trade_date BETWEEN %s AND %s
        ORDER BY stock_code, trade_date
    """
    params = stock_codes + [start_date, end_date]

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
    except Exception as exc:
        logger.warning("get_daily_candles_range query failed: %s", exc)
        return {}
    finally:
        conn.close()

    if not rows:
        return {}

    df_all = pd.DataFrame(
        rows,
        columns=["stock_code", "date", "open", "high", "low", "close", "volume", "trading_value"],
    )
    result: Dict[str, pd.DataFrame] = {}
    for code, grp in df_all.groupby("stock_code"):
        result[code] = grp.drop(columns="stock_code").reset_index(drop=True)
    return result


def get_trading_value_at(
    stock_codes: List[str],
    scan_date: date,
    lookback_days: int = 20,
) -> pd.DataFrame:
    """특정일 직전 N영업일(캘린더 기준 lookback_days 배수) 평균 거래대금 조회.

    반환: DataFrame[stock_code, avg_trading_value]
    """
    if not stock_codes:
        return pd.DataFrame(columns=["stock_code", "avg_trading_value"])

    conn = _connect("strategy_analysis")
    if conn is None:
        return pd.DataFrame(columns=["stock_code", "avg_trading_value"])

    placeholders = ",".join(["%s"] * len(stock_codes))
    # 직전 N일 행을 ROW_NUMBER 로 제한 (trade_date < scan_date)
    query = f"""
        SELECT stock_code, AVG(trading_value) AS avg_trading_value
        FROM (
            SELECT stock_code, trading_value,
                   ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
            FROM daily_candles
            WHERE stock_code IN ({placeholders})
              AND trade_date < %s
        ) sub
        WHERE rn <= %s
        GROUP BY stock_code
    """
    params = stock_codes + [scan_date, lookback_days]

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return pd.DataFrame(rows, columns=["stock_code", "avg_trading_value"])
    except Exception as exc:
        logger.warning("get_trading_value_at query failed: %s", exc)
        return pd.DataFrame(columns=["stock_code", "avg_trading_value"])
    finally:
        conn.close()


def get_fundamentals_at(
    stock_codes: Optional[List[str]],
    scan_date: date,
) -> pd.DataFrame:
    """yearly_fundamentals 에서 scan_date 기준 가장 최근 연도 재무 조회.

    당해년도 미공시 가능성 때문에 scan_date.year - 1 이하 연도를 우선 사용.
    반환: DataFrame[stock_code, year, per, pbr, roe, op_margin, debt_ratio,
                    revenue_growth, market_cap_won]
    """
    conn = _connect("strategy_analysis")
    if conn is None:
        return pd.DataFrame()

    # scan_date.year - 1 까지를 기준으로 가장 최신 연도 선택
    max_year = scan_date.year - 1

    conditions: List[str] = ["year <= %s"]
    params: List = [max_year]

    if stock_codes:
        placeholders = ",".join(["%s"] * len(stock_codes))
        conditions.append(f"stock_code IN ({placeholders})")
        params.extend(stock_codes)

    where = "WHERE " + " AND ".join(conditions)
    query = f"""
        SELECT DISTINCT ON (stock_code)
               stock_code, year, per, pbr, roe,
               op_margin, debt_ratio, revenue_growth, market_cap_won
        FROM yearly_fundamentals
        {where}
        ORDER BY stock_code, year DESC
    """

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return pd.DataFrame(
            rows,
            columns=[
                "stock_code", "year", "per", "pbr", "roe",
                "op_margin", "debt_ratio", "revenue_growth", "market_cap_won",
            ],
        )
    except Exception as exc:
        logger.warning("get_fundamentals_at query failed: %s", exc)
        return pd.DataFrame()
    finally:
        conn.close()


def get_quarterly_fundamentals_at(
    stock_codes: List[str],
    scan_date: date,
) -> pd.DataFrame:
    """robotrader_quant.financial_statements 에서 report_date <= scan_date 최신 분기 조회.

    PEG 근사 등 보조 지표용.
    반환: DataFrame[stock_code, report_date, per, pbr, roe, debt_ratio,
                    operating_margin, net_margin, revenue, net_income]
    """
    if not stock_codes:
        return pd.DataFrame()

    conn = _connect("robotrader_quant")
    if conn is None:
        return pd.DataFrame()

    scan_str = scan_date.strftime("%Y-%m-%d")
    placeholders = ",".join(["%s"] * len(stock_codes))
    # report_date 는 text 컬럼이므로 문자열 비교 (YYYY-MM-DD 형식 전제)
    query = f"""
        SELECT DISTINCT ON (stock_code)
               stock_code, report_date, per, pbr, roe,
               debt_ratio, operating_margin, net_margin, revenue, net_income
        FROM financial_statements
        WHERE stock_code IN ({placeholders})
          AND report_date <= %s
        ORDER BY stock_code, report_date DESC
    """
    params = stock_codes + [scan_str]

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return pd.DataFrame(
            rows,
            columns=[
                "stock_code", "report_date", "per", "pbr", "roe",
                "debt_ratio", "operating_margin", "net_margin", "revenue", "net_income",
            ],
        )
    except Exception as exc:
        logger.warning("get_quarterly_fundamentals_at query failed: %s", exc)
        return pd.DataFrame()
    finally:
        conn.close()
