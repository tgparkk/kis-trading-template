"""PIT(Point-In-Time) 데이터 어댑터.

모든 read 함수는 as_of_date 파라미터 필수.
미입력 시 TypeError raise — 실수로 미래 데이터 노출 원천 차단.

설계 원칙:
  - as_of_date 당일/미래 데이터 절대 반환 금지 (date < as_of_date)
  - adj_factor 보정 적용 (daily_prices 컬럼 없으면 1.0 기본값)
  - 공시 lag 60일: quant_financial_ratio.statement_ym + 60일 이전만 반환
  - 두 DB(robotrader, robotrader_quant) 모두 psycopg2 직접 연결
"""
from __future__ import annotations

import logging
import os
from datetime import date, time, datetime
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
)

# robotrader_quant DB는 별도 유저 환경변수 지원.
# GRANT 미부여 환경에서는 TIMESCALE_QUANT_USER=postgres,
# TIMESCALE_QUANT_PASSWORD=postgres 로 덮어쓸 수 있다.
_QUANT_DB_DEFAULTS = dict(
    host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    port=int(os.getenv("TIMESCALE_PORT", "5433")),
    user=os.getenv("TIMESCALE_QUANT_USER", os.getenv("TIMESCALE_USER", "robotrader")),
    password=os.getenv(
        "TIMESCALE_QUANT_PASSWORD", os.getenv("TIMESCALE_PASSWORD", "1234")
    ),
)

_ROBOTRADER_DB = os.getenv("TIMESCALE_DB", "robotrader")
_QUANT_DB = os.getenv("TIMESCALE_QUANT_DB", "robotrader_quant")


@contextmanager
def _conn(db: str):
    """robotrader DB 연결 — 트랜잭션 자동 커밋/롤백."""
    conn = psycopg2.connect(**_DB_DEFAULTS, database=db)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _conn_quant():
    """robotrader_quant DB 연결 — 별도 유저 환경변수 사용."""
    conn = psycopg2.connect(**_QUANT_DB_DEFAULTS, database=_QUANT_DB)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# 연결 재사용 컨텍스트 — 백테스트 루프용
# ------------------------------------------------------------------ #

# 스레드-로컬 재사용 연결 저장소.
# ThreadPoolExecutor 8 workers 환경에서 각 워커가 독립적으로 연결을 보유한다.
import threading as _threading

_local = _threading.local()


@contextmanager
def backtest_session():
    """백테스트 루프 전체를 단일 DB 연결로 감싸는 컨텍스트 매니저.

    with backtest_session():
        # 이 블록 안의 read_open / read_high_low / read_daily 호출은
        # 모두 동일한 psycopg2 connection을 재사용한다.
        # connect() 비용(~220ms/call)을 루프 진입 1회로 줄인다.

    중첩 호출 안전: 이미 세션이 열려 있으면 그냥 통과(no-op).
    """
    already_open = getattr(_local, "conn", None) is not None
    if already_open:
        yield
        return

    # 멀티버스 daily_prices 메인 테이블은 robotrader_quant (plan 결정 6번)
    conn = psycopg2.connect(**_QUANT_DB_DEFAULTS, database=_QUANT_DB)
    # _has_adj_factor 캐시도 이 시점에 워밍
    with conn.cursor() as cur:
        _has_adj_factor(cur)
    _local.conn = conn
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        _local.conn = None


def _get_reuse_conn():
    """현재 스레드에 재사용 연결이 열려 있으면 반환, 없으면 None."""
    return getattr(_local, "conn", None)


# ------------------------------------------------------------------ #
# 내부 헬퍼
# ------------------------------------------------------------------ #

# adj_factor 컬럼 존재 여부 — 프로세스 기동 시 1회만 조회, 이후 캐시 재사용.
# information_schema.columns 조회는 ~160ms/call로 매우 느리므로
# 매 read_open / read_high_low / read_daily 호출마다 실행하면
# 단일 셀(17,654호출)에서 48분 낭비가 발생한다.
_ADJ_FACTOR_CACHE: bool | None = None


def _has_adj_factor(cur) -> bool:
    """daily_prices 테이블에 adj_factor 컬럼이 존재하는지 확인.

    최초 호출 시 DB 조회 후 모듈 레벨 변수에 캐시.
    이후 호출은 캐시 값을 즉시 반환 (0ms).
    """
    global _ADJ_FACTOR_CACHE
    if _ADJ_FACTOR_CACHE is not None:
        return _ADJ_FACTOR_CACHE
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'daily_prices'
          AND column_name = 'adj_factor'
        LIMIT 1
        """
    )
    _ADJ_FACTOR_CACHE = cur.fetchone() is not None
    return _ADJ_FACTOR_CACHE


# ------------------------------------------------------------------ #
# 공개 API
# ------------------------------------------------------------------ #

def read_daily(
    symbol: str,
    as_of_date: date,
    lookback_days: int = 252,
) -> pd.DataFrame:
    """T-1 종가까지의 일봉 OHLCV 반환.

    as_of_date 당일/미래 데이터 절대 노출 금지.
    adj_factor 보정 적용 (컬럼 없으면 1.0 기본값).
    반환 컬럼: date, open, high, low, close, volume

    backtest_session() 컨텍스트 안에서 호출되면 기존 연결을 재사용해
    connect() 비용(~220ms)을 절감한다.

    Parameters
    ----------
    symbol:
        종목코드 (예: '005930')
    as_of_date:
        기준일 — 이 날짜 미만(date < as_of_date) 데이터만 반환
    lookback_days:
        최대 조회 일수 (기본 252거래일)
    """
    has_adj = _ADJ_FACTOR_CACHE if _ADJ_FACTOR_CACHE is not None else True

    if has_adj:
        sql = r"""
            SELECT
                date,
                open  * COALESCE(adj_factor, 1.0) AS open,
                high  * COALESCE(adj_factor, 1.0) AS high,
                low   * COALESCE(adj_factor, 1.0) AS low,
                close * COALESCE(adj_factor, 1.0) AS close,
                volume
            FROM daily_prices
            WHERE stock_code = %(symbol)s
              AND date < %(as_of_date)s
              AND date::text ~ '^\d{4}-\d{2}-\d{2}$'
            ORDER BY date DESC
            LIMIT %(limit)s
        """
    else:
        # adj_factor 컬럼 없음 — 보정 없이 raw 값 반환
        sql = r"""
            SELECT date, open, high, low, close, volume
            FROM daily_prices
            WHERE stock_code = %(symbol)s
              AND date < %(as_of_date)s
              AND date::text ~ '^\d{4}-\d{2}-\d{2}$'
            ORDER BY date DESC
            LIMIT %(limit)s
        """

    reuse = _get_reuse_conn()
    if reuse is not None:
        with reuse.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if _ADJ_FACTOR_CACHE is None:
                has_adj = _has_adj_factor(cur)
                # sql 재선택 (캐시 미스 첫 호출 시)
                if has_adj:
                    sql = r"""
                        SELECT
                            date,
                            open  * COALESCE(adj_factor, 1.0) AS open,
                            high  * COALESCE(adj_factor, 1.0) AS high,
                            low   * COALESCE(adj_factor, 1.0) AS low,
                            close * COALESCE(adj_factor, 1.0) AS close,
                            volume
                        FROM daily_prices
                        WHERE stock_code = %(symbol)s
                          AND date < %(as_of_date)s
                          AND date::text ~ '^\d{4}-\d{2}-\d{2}$'
                        ORDER BY date DESC
                        LIMIT %(limit)s
                    """
                else:
                    sql = r"""
                        SELECT date, open, high, low, close, volume
                        FROM daily_prices
                        WHERE stock_code = %(symbol)s
                          AND date < %(as_of_date)s
                          AND date::text ~ '^\d{4}-\d{2}-\d{2}$'
                        ORDER BY date DESC
                        LIMIT %(limit)s
                    """
            cur.execute(sql, dict(symbol=symbol, as_of_date=as_of_date.isoformat(), limit=lookback_days))
            rows = cur.fetchall()
    else:
        with _conn_quant() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                has_adj = _has_adj_factor(cur)

                if has_adj:
                    sql = r"""
                        SELECT
                            date,
                            open  * COALESCE(adj_factor, 1.0) AS open,
                            high  * COALESCE(adj_factor, 1.0) AS high,
                            low   * COALESCE(adj_factor, 1.0) AS low,
                            close * COALESCE(adj_factor, 1.0) AS close,
                            volume
                        FROM daily_prices
                        WHERE stock_code = %(symbol)s
                          AND date < %(as_of_date)s
                          AND date::text ~ '^\d{4}-\d{2}-\d{2}$'
                        ORDER BY date DESC
                        LIMIT %(limit)s
                    """
                else:
                    sql = r"""
                        SELECT date, open, high, low, close, volume
                        FROM daily_prices
                        WHERE stock_code = %(symbol)s
                          AND date < %(as_of_date)s
                          AND date::text ~ '^\d{4}-\d{2}-\d{2}$'
                        ORDER BY date DESC
                        LIMIT %(limit)s
                    """

                cur.execute(sql, dict(symbol=symbol, as_of_date=as_of_date.isoformat(), limit=lookback_days))
                rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)

    # OHLC 위반 보정 — 틱 반올림 아티팩트(0.77% 발생) 수정
    # high < max(open,close) 또는 low > min(open,close) 케이스를 보정
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)

    return df


def read_open(symbol: str, date: date) -> Optional[float]:
    """체결 전용 — 해당 일자 시가만 반환.

    의사결정 입력에 사용 금지 (별도 함수로 분리).
    adj_factor 보정 적용.

    backtest_session() 컨텍스트 안에서 호출되면 기존 연결을 재사용해
    connect() 비용(~220ms)을 절감한다.
    """
    reuse = _get_reuse_conn()
    has_adj = _ADJ_FACTOR_CACHE if _ADJ_FACTOR_CACHE is not None else True

    if has_adj:
        sql = """
            SELECT open * COALESCE(adj_factor, 1.0) AS open
            FROM daily_prices
            WHERE stock_code = %(symbol)s
              AND date = %(date)s
            LIMIT 1
        """
    else:
        sql = """
            SELECT open
            FROM daily_prices
            WHERE stock_code = %(symbol)s
              AND date = %(date)s
            LIMIT 1
        """

    if reuse is not None:
        with reuse.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, dict(symbol=symbol, date=date.isoformat()))
            row = cur.fetchone()
    else:
        with _conn_quant() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                has_adj = _has_adj_factor(cur)
                if has_adj:
                    sql = """
                        SELECT open * COALESCE(adj_factor, 1.0) AS open
                        FROM daily_prices
                        WHERE stock_code = %(symbol)s
                          AND date = %(date)s
                        LIMIT 1
                    """
                else:
                    sql = """
                        SELECT open
                        FROM daily_prices
                        WHERE stock_code = %(symbol)s
                          AND date = %(date)s
                        LIMIT 1
                    """
                cur.execute(sql, dict(symbol=symbol, date=date.isoformat()))
                row = cur.fetchone()

    if row is None:
        return None
    return float(row["open"]) if row["open"] is not None else None


def read_high_low(symbol: str, date: date) -> Optional[tuple[float, float]]:
    """일중 TP/SL 시뮬 전용 — 해당 일자 고가/저가.

    의사결정 입력에 사용 금지 (별도 함수로 분리).
    반환: (high, low) 또는 None

    backtest_session() 컨텍스트 안에서 호출되면 기존 연결을 재사용한다.
    """
    reuse = _get_reuse_conn()
    has_adj = _ADJ_FACTOR_CACHE if _ADJ_FACTOR_CACHE is not None else True

    if has_adj:
        sql = """
            SELECT
                high * COALESCE(adj_factor, 1.0) AS high,
                low  * COALESCE(adj_factor, 1.0) AS low
            FROM daily_prices
            WHERE stock_code = %(symbol)s
              AND date = %(date)s
            LIMIT 1
        """
    else:
        sql = """
            SELECT high, low
            FROM daily_prices
            WHERE stock_code = %(symbol)s
              AND date = %(date)s
            LIMIT 1
        """

    if reuse is not None:
        with reuse.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, dict(symbol=symbol, date=date.isoformat()))
            row = cur.fetchone()
    else:
        with _conn_quant() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                has_adj = _has_adj_factor(cur)
                if has_adj:
                    sql = """
                        SELECT
                            high * COALESCE(adj_factor, 1.0) AS high,
                            low  * COALESCE(adj_factor, 1.0) AS low
                        FROM daily_prices
                        WHERE stock_code = %(symbol)s
                          AND date = %(date)s
                        LIMIT 1
                    """
                else:
                    sql = """
                        SELECT high, low
                        FROM daily_prices
                        WHERE stock_code = %(symbol)s
                          AND date = %(date)s
                        LIMIT 1
                    """
                cur.execute(sql, dict(symbol=symbol, date=date.isoformat()))
                row = cur.fetchone()

    if row is None:
        return None
    if row["high"] is None or row["low"] is None:
        return None
    return (float(row["high"]), float(row["low"]))


def read_minute(
    symbol: str,
    as_of_date: date,
    as_of_time: time,
    lookback_minutes: int = 390,
) -> pd.DataFrame:
    """T일 as_of_time 직전 분봉까지.

    09:00 결정 = T-1 분봉까지, 09:01 결정 = 09:00 분봉까지.
    반환 컬럼: date, time, open, high, low, close, volume
    """
    with _conn(_ROBOTRADER_DB) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # minute_prices 컬럼 확인 (date/time 분리 vs datetime 통합)
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'minute_prices'
                ORDER BY ordinal_position
                """
            )
            cols = [r["column_name"] for r in cur.fetchall()]

            if "time" in cols:
                # date + time 분리 스키마
                sql = """
                    SELECT date, time, open, high, low, close, volume
                    FROM minute_prices
                    WHERE stock_code = %(symbol)s
                      AND (
                          date < %(as_of_date)s
                          OR (date = %(as_of_date)s AND time < %(as_of_time)s)
                      )
                    ORDER BY date DESC, time DESC
                    LIMIT %(limit)s
                """
                cur.execute(
                    sql,
                    dict(
                        symbol=symbol,
                        as_of_date=as_of_date,
                        as_of_time=as_of_time,
                        limit=lookback_minutes,
                    ),
                )
            else:
                # datetime 통합 스키마 (컬럼명 추정: datetime 또는 trade_time)
                dt_col = "datetime" if "datetime" in cols else cols[1]
                as_of_dt = datetime.combine(as_of_date, as_of_time)
                sql = f"""
                    SELECT
                        {dt_col}::date AS date,
                        {dt_col}::time AS time,
                        open, high, low, close, volume
                    FROM minute_prices
                    WHERE stock_code = %(symbol)s
                      AND {dt_col} < %(as_of_dt)s
                    ORDER BY {dt_col} DESC
                    LIMIT %(limit)s
                """
                cur.execute(sql, dict(symbol=symbol, as_of_dt=as_of_dt, limit=lookback_minutes))

            rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=["date", "time", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    # time 컬럼: timedelta 또는 datetime.time 모두 처리
    if pd.api.types.is_timedelta64_dtype(df["time"]):
        df["time"] = df["time"].apply(
            lambda td: (datetime.min + td).time() if pd.notna(td) else None
        )
    df = df.sort_values(["date", "time"]).reset_index(drop=True)
    return df


def read_financial_ratio(
    symbol: str,
    as_of_date: date,
) -> Optional[dict]:
    """분기재무비율 + 공시 lag 60일 적용.

    as_of_date - 60일 이전 공시분(statement_ym 기준)만 반환.
    statement_ym은 'YYYYMM' 형식이므로 해당 월 말일을 기준일로 사용.

    반환 키: roe, liability_ratio, eps, bps, sales_growth,
             operating_income_growth, net_income_growth, statement_ym, disclosure_date
    데이터 없으면 None.
    """
    from datetime import timedelta

    # 공시 lag 60일 적용: as_of_date - 60일 이전에 공시된 재무만 허용
    lag_cutoff = as_of_date - timedelta(days=60)

    # statement_ym 'YYYYMM' → 해당 월 말일로 변환해 비교
    # 예: '202412' → 2024-12-31 이전이어야 lag_cutoff 통과
    # 보수적 처리: statement_ym의 다음 달 1일 - 1일 = 해당 월 말일
    # lag_cutoff보다 작거나 같은 statement_ym만 허용
    # 즉, TO_DATE(statement_ym || '01', 'YYYYMMDD') + INTERVAL '1 month' - 1 <= lag_cutoff

    sql = """
        SELECT
            stock_code,
            statement_ym,
            sales_growth,
            operating_income_growth,
            net_income_growth,
            roe_value         AS roe,
            eps,
            sps,
            bps,
            reserve_ratio,
            liability_ratio,
            fetched_at
        FROM quant_financial_ratio
        WHERE stock_code = %(symbol)s
          AND (
              TO_DATE(statement_ym || '01', 'YYYYMMDD')
              + INTERVAL '1 month'
              - INTERVAL '1 day'
          ) <= %(lag_cutoff)s
        ORDER BY statement_ym DESC
        LIMIT 1
    """
    reuse = _get_reuse_conn()
    if reuse is not None:
        with reuse.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, dict(symbol=symbol, lag_cutoff=lag_cutoff))
            row = cur.fetchone()
    else:
        with _conn_quant() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, dict(symbol=symbol, lag_cutoff=lag_cutoff))
                row = cur.fetchone()

    if row is None:
        return None

    result = dict(row)
    # 공시일 추정: statement_ym 해당 월 말일 (실제 disclosure_date 컬럼 없음)
    ym = result["statement_ym"]  # 'YYYYMM'
    year, month = int(ym[:4]), int(ym[4:6])
    # 다음 달 1일 - 1일 = 해당 월 말일
    if month == 12:
        end_of_month = date(year + 1, 1, 1).__class__(year + 1, 1, 1)
        from datetime import timedelta as _td
        end_of_month = date(year, 12, 31)
    else:
        from datetime import timedelta as _td
        end_of_month = date(year, month + 1, 1) - _td(days=1)

    result["disclosure_date"] = end_of_month
    return result


def read_screener_snapshot(snapshot_date: date) -> list[str]:
    """robotrader.screener_snapshots — 해당 시점 후보풀 반환.

    반환: 종목코드 문자열 리스트
    """
    with _conn(_ROBOTRADER_DB) as conn:
        with conn.cursor() as cur:
            # screener_snapshots 컬럼 구조 확인
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'screener_snapshots'
                ORDER BY ordinal_position
                """
            )
            cols = [r[0] for r in cur.fetchall()]

            if not cols:
                logger.warning("screener_snapshots 테이블이 비어 있거나 존재하지 않습니다.")
                return []

            # stock_code 컬럼 탐색
            code_col = None
            for candidate in ("stock_code", "symbol", "code"):
                if candidate in cols:
                    code_col = candidate
                    break

            if code_col is None:
                logger.warning(
                    "screener_snapshots에서 종목코드 컬럼을 찾을 수 없습니다. 컬럼: %s", cols
                )
                return []

            # snapshot_date 컬럼 탐색
            date_col = None
            for candidate in ("snapshot_date", "date", "created_at", "as_of_date"):
                if candidate in cols:
                    date_col = candidate
                    break

            if date_col is None:
                logger.warning(
                    "screener_snapshots에서 날짜 컬럼을 찾을 수 없습니다. 컬럼: %s", cols
                )
                return []

            sql = f"""
                SELECT DISTINCT {code_col}
                FROM screener_snapshots
                WHERE {date_col}::date = %(snapshot_date)s
                ORDER BY {code_col}
            """
            cur.execute(sql, dict(snapshot_date=snapshot_date))
            rows = cur.fetchall()

    return [r[0] for r in rows]
