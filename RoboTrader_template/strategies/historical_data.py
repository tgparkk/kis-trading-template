"""
외부 DB 조회용 헬퍼 함수 모음 (stateless).
kis_template DB에서 과거 데이터를 읽는다 (2026-08-16 DB 통합 이후).
접속 실패 시 warning 로그 + 빈 DataFrame 반환 (raise 금지).

2026-08-16 DB 통합 — 이 모듈이 읽는 5개 소스의 이력
-----------------------------------------------------
  | 함수                          | 테이블                | 통합 전            |
  | get_sectors                   | stock_sector          | strategy_analysis  |
  | get_fundamentals_at           | yearly_fundamentals   | strategy_analysis  |
  | get_quarterly_fundamentals_at | financial_statements  | robotrader_quant   |
  | get_daily_candles_range       | daily_prices          | strategy_analysis.daily_candles |
  | get_trading_value_at          | daily_prices          | strategy_analysis.daily_candles |

앞 3개는 테이블이 그대로 kis_template 으로 이관됐다(컬럼 동일 → 쿼리 무변경).
뒤 2개는 **이관 대상이 아니었다** — `daily_candles` 대신 kis 의 `daily_prices` 를
쓰도록 쿼리를 재작성했다(컬럼명·날짜타입·단위 규약이 모두 다르다. 각 함수 참조).

⚠️ resolve_daily_source_db() 를 쓰지 않는 이유:
   가격 resolver 는 KIS_DATA_SOURCE=legacy 일 때 robotrader_quant 를 가리키는데,
   그 DB 엔 `stock_sector`·`yearly_fundamentals` 가 **없다**. resolver 를 태우면
   롤백 시 5개 함수 중 3개가 "relation 없음" 으로 죽는다. 이 모듈은 통합 원칙
   「DB 는 kis_template 하나」를 그대로 따른다.
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

# 이 모듈이 읽는 5개 테이블은 2026-08-16 통합으로 전부 kis_template 에 있다.
EXT_DB_NAME = "kis_template"

# 외부 DB 기본 접속 파라미터 (환경변수로 override 가능)
#
# user 가 postgres → robotrader 로 바뀐 이유(2026-08-16):
#   통합 전 소스였던 `strategy_analysis` 는 robotrader 롤이 **읽을 수 없다**
#   (실측: "daily_candles 테이블에 대한 접근 권한 없음"). superuser 인 postgres 를
#   기본값으로 둔 것은 그 제약 때문이었다. kis_template 의 대상 테이블은 전부
#   소유자가 robotrader 이므로 superuser 가 더 이상 필요 없다
#   (실측: robotrader 로 stock_sector/daily_prices/yearly_fundamentals/
#    financial_statements 4개 모두 조회 성공).
DEFAULT_EXT_DB = {
    "host": os.getenv("EXTERNAL_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("EXTERNAL_DB_PORT", "5433")),
    "user": os.getenv("EXTERNAL_DB_USER", "robotrader"),
    "password": os.getenv("EXTERNAL_DB_PASSWORD", "1234"),
}


def _to_iso(d) -> str:
    """date/datetime/str → 'YYYY-MM-DD'.

    `daily_prices.date` 는 **text 컬럼**이라 date 객체를 그대로 바인딩하면
    text↔date 비교가 되어 버린다. 문자열로 넘겨 사전식 비교(ISO 라 순서 동일)를 쓴다.
    """
    if isinstance(d, str):
        return d
    return d.strftime("%Y-%m-%d")


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
    """kis_template.stock_sector 조회 (2026-08-16 이전: strategy_analysis).

    테이블이 통째로 이관돼 컬럼 구성이 같다 → 쿼리 무변경, DB명만 교체.
    target_sectors 는 sector_name LIKE 키워드 목록 (None 이면 전 섹터).
    stock_codes 가 주어지면 해당 종목만 반환.
    반환: DataFrame[stock_code, stock_name, sector_code, sector_name, market]
    """
    conn = _connect(EXT_DB_NAME)
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
    """kis_template.daily_prices 에서 기간별 일봉 로드.

    반환: {stock_code: DataFrame[date, open, high, low, close, volume, trading_value]}
    컬럼명은 BacktestEngine 호환으로 open/high/low/close 로 rename.

    2026-08-16 소스 교체 — strategy_analysis.daily_candles → kis_template.daily_prices
    ------------------------------------------------------------------------------
    `daily_candles` 는 **이관 대상이 아니었다**(kis `daily_prices` 3,147,227행이
    2,393,580행을 덮는다는 판정). 같은 테이블이 아니므로 3가지를 맞춰야 한다:

    🔴 단 「상위집합」은 **전수 확인 결과 정확히는 틀리다**(실측 2026-08-16):
       `daily_candles` 에만 있는 (종목,날짜) 키가 **50,953개 / 285종목** 있다
       (대부분 2024-03-04~2026-02-10 연속 구간). 즉 이 구간에서는 전환 후 반환
       행수가 **줄어든다**. 이는 기존 「일봉 결손 복구」 백로그와 같은 사안이며,
       복구 소스로 `strategy_analysis.daily_candles` 가 살아 있다는 뜻이기도 하다
       (`scripts/backfill_daily_prices_fundamental.py` 가 그 소스를 읽는다).

    1) 컬럼명: trade_date/open_price/... → date/open/high/low/close
    2) 날짜타입: `daily_candles.trade_date` 는 date 였지만 `daily_prices.date` 는
       **text('YYYY-MM-DD')** 다 → `_to_iso()` 로 문자열 바인딩(사전식 비교).
       반환 DataFrame 의 date 는 기존 계약을 지키려고 datetime.date 로 되돌린다.
    3) 단위 규약 — 🔑 **가격과 수량의 방향이 정반대다**:
       · `close/open/high/low` 는 **이미 분할조정된 연속시세**다 → adj_factor 를
         곱하면 분할일 가짜 절벽이 생긴다(카카오 −78.5%). **곱하지 않는다.**
       · `volume` 은 **원본 그대로** 저장돼 close 와 단위가 어긋난다 →
         `volume × COALESCE(adj_factor,1)` 로 맞춘다.
       이 모듈은 읽기 계층(db/quant_daily_reader.py·db/repositories/price.py)을
       거치지 않고 생 SQL 로 읽으므로 여기서 직접 맞춘다(이중조정 아님).
       상세·회귀가드 → tests/test_adj_factor_volume_units.py

    ⚠️ trading_value 를 저장 컬럼이 아니라 `close×volume×adj_factor` 로 **계산**하는 이유:
       `daily_prices.trading_value` 는 유래가 섞여 있다 — 과거 백필분은
       `조정close × 원본volume`(= 분할 전 구간이 adj_factor 배 과소평가)이고
       최근 수집분은 KIS 가 준 실제 거래대금이다(실측: 3,142,957행 중 저장값이
       close×volume 과 일치하는 행 1,458,651 = 46%). 저장값에 adj_factor 를 곱하면
       실측 27,841행(adj_factor≠1 이면서 실제 거래대금인 행)이 과대평가된다.
       ⇒ 유래에 무관하게 일관된 `close×volume×adj_factor` 를 쓴다
         (db/quant_daily_reader.py:89 와 동일 규약).
    """
    if not stock_codes:
        return {}

    conn = _connect(EXT_DB_NAME)
    if conn is None:
        return {}

    placeholders = ",".join(["%s"] * len(stock_codes))
    query = f"""
        SELECT stock_code, date,
               open, high, low, close,
               (volume * COALESCE(adj_factor, 1))::double precision AS volume,
               (close * (volume * COALESCE(adj_factor, 1)))::double precision
                   AS trading_value
        FROM daily_prices
        WHERE stock_code IN ({placeholders})
          AND date BETWEEN %s AND %s
        ORDER BY stock_code, date
    """
    params = stock_codes + [_to_iso(start_date), _to_iso(end_date)]

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
    # `daily_prices.date` 는 text 라 그대로면 str 이 된다. 이전 소스
    # (`daily_candles.trade_date` = date 컬럼)와 같은 계약을 유지하려고 date 로 되돌린다.
    df_all["date"] = pd.to_datetime(df_all["date"]).dt.date
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

    2026-08-16 소스 교체 — strategy_analysis.daily_candles → kis_template.daily_prices.
    거래대금은 저장 컬럼 대신 `close × volume × COALESCE(adj_factor,1)` 로 계산한다
    (이유는 get_daily_candles_range docstring 의 ⚠️ 절 참조).
    """
    if not stock_codes:
        return pd.DataFrame(columns=["stock_code", "avg_trading_value"])

    conn = _connect(EXT_DB_NAME)
    if conn is None:
        return pd.DataFrame(columns=["stock_code", "avg_trading_value"])

    placeholders = ",".join(["%s"] * len(stock_codes))
    # 직전 N일 행을 ROW_NUMBER 로 제한 (date < scan_date)
    query = f"""
        SELECT stock_code, AVG(trading_value) AS avg_trading_value
        FROM (
            SELECT stock_code,
                   (close * (volume * COALESCE(adj_factor, 1)))::double precision
                       AS trading_value,
                   ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY date DESC) AS rn
            FROM daily_prices
            WHERE stock_code IN ({placeholders})
              AND date < %s
        ) sub
        WHERE rn <= %s
        GROUP BY stock_code
    """
    params = stock_codes + [_to_iso(scan_date), lookback_days]

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
    """kis_template.yearly_fundamentals 에서 scan_date 기준 가장 최근 연도 재무 조회.

    (2026-08-16 이전: strategy_analysis. 테이블 통째 이관 → 쿼리 무변경, DB명만 교체.)
    당해년도 미공시 가능성 때문에 scan_date.year - 1 이하 연도를 우선 사용.
    반환: DataFrame[stock_code, year, per, pbr, roe, op_margin, debt_ratio,
                    revenue_growth, market_cap_won]
    """
    conn = _connect(EXT_DB_NAME)
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
    """kis_template.financial_statements 에서 report_date <= scan_date 최신 분기 조회.

    (2026-08-16 이전: robotrader_quant. 테이블 통째 이관 → 쿼리 무변경, DB명만 교체.)
    PEG 근사 등 보조 지표용.
    반환: DataFrame[stock_code, report_date, per, pbr, roe, debt_ratio,
                    operating_margin, net_margin, revenue, net_income]
    """
    if not stock_codes:
        return pd.DataFrame()

    conn = _connect(EXT_DB_NAME)
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
