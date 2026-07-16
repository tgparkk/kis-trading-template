"""PIT(Point-In-Time) 데이터 어댑터.

모든 read 함수는 as_of_date 파라미터 필수.
미입력 시 TypeError raise — 실수로 미래 데이터 노출 원천 차단.

설계 원칙:
  - as_of_date 당일/미래 데이터 절대 반환 금지 (date < as_of_date)
  - ★ adj_factor 를 곱하지 않는다 (아래 규약 참조)
  - 공시 lag 60일: quant_financial_ratio.statement_ym + 60일 이전만 반환

데이터 소스 (2026-07-16 연구 소스 통일):
  - 가격(daily_prices) = resolve_daily_source_db() → 기본 kis_template
  - 재무(quant_financial_ratio) = robotrader_quant **의도된 예외**
    kis_template 엔 재무 테이블 자체가 없다(실측: relation 없음).
  - 운영(screener_snapshots) = TIMESCALE_DB (라이브 .env 에서 kis_template)

★ adj_factor 곱셈 금지 규약 (불변):
  daily_prices.close 는 **이미 분할조정된 연속 시세**다. adj_factor(계단형 역조정
  메타, 1~50)를 또 곱하면 이중조정되어 분할일에 가짜 절벽이 생긴다.
  실측(kis_template): 035720 2021-04-14 close=112,000 adj_factor=5 → 곱하면
  560,000 이 되어 분할일(04-15, close=120,500)에 -78.5% 가짜 폭락 발생
  (한국 가격제한 ±30% 초과 = 물리적으로 불가능). 이 곱셈이 과거 Minervini
  MaxDD 를 거짓 99% 로 부풀렸다. 회귀 가드: tests/test_research_data_source.py.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date, time, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2
import psycopg2.extras
import psycopg2.extensions
from contextlib import contextmanager

# config.constants(가격 소스 resolver) import — 이 모듈은 `multiverse.data.pit_reader`
# 와 `RoboTrader_template.multiverse.data.pit_reader` 두 경로로 모두 import 되므로,
# 어느 쪽이든 RoboTrader_template 루트가 sys.path 에 있도록 보정한다
# (collectors/eod_collection.py 와 동일 패턴).
_TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
if str(_TEMPLATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEMPLATE_ROOT))

from config.constants import resolve_daily_source_db  # noqa: E402

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

# 재무 전용 DB — **의도된 예외**로 kis_template 통일 대상에서 제외한다.
# quant_financial_ratio / quant_balance_sheet / quant_income_statement /
# financial_statements 는 robotrader_quant 에만 존재하며 kis_template 엔 테이블
# 자체가 없다(실측 2026-07-16: kis_template 에서 조회 시 "릴레이션이 없습니다").
# 따라서 가격 resolver 를 태우면 안 된다. 재무를 kis_template 으로 옮기려면 먼저
# 테이블·적재 파이프라인이 있어야 한다(별건).
_FINANCIAL_DB = os.getenv("QUANT_FINANCIAL_DB", "robotrader_quant")


@contextmanager
def _conn(db: str):
    """지정 DB 연결 — 트랜잭션 자동 커밋/롤백."""
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
def _conn_daily():
    """가격(daily_prices) 소스 연결 — resolver 경유(기본 kis_template).

    KIS_DATA_SOURCE=legacy 로 robotrader_quant 롤백 가능.
    """
    conn = psycopg2.connect(**_QUANT_DB_DEFAULTS, database=resolve_daily_source_db())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _conn_financial():
    """재무 소스 연결 — robotrader_quant 고정(의도된 예외). 별도 유저 환경변수 사용."""
    conn = psycopg2.connect(**_QUANT_DB_DEFAULTS, database=_FINANCIAL_DB)
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
    """백테스트 루프를 재사용 DB 연결로 감싸는 컨텍스트 매니저.

    with backtest_session():
        # 이 블록 안의 read_open / read_high_low / read_daily 호출은
        # 모두 동일한 psycopg2 connection을 재사용한다.
        # connect() 비용(~220ms/call)을 루프 진입 1회로 줄인다.

    가격(kis_template)과 재무(robotrader_quant)가 서로 다른 DB 이므로 연결을 둘로
    나눠 각각 재사용한다(단일 연결로는 한쪽 테이블을 찾지 못한다). 재무 연결은
    read_financial_ratio 가 실제로 호출될 때까지 열지 않는다(지연 생성) — 재무를
    안 쓰는 페르소나가 불필요한 connect 비용을 물지 않게 한다.

    중첩 호출 안전: 이미 세션이 열려 있으면 그냥 통과(no-op).
    """
    already_open = getattr(_local, "conn", None) is not None
    if already_open:
        yield
        return

    conn = psycopg2.connect(**_QUANT_DB_DEFAULTS, database=resolve_daily_source_db())
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
        fin = getattr(_local, "financial_conn", None)
        if fin is not None:
            fin.close()
            _local.financial_conn = None


def _get_reuse_conn():
    """현재 스레드에 재사용 가격 연결이 열려 있으면 반환, 없으면 None."""
    return getattr(_local, "conn", None)


def _get_reuse_financial_conn():
    """재무 재사용 연결. 세션 안이면 지연 생성 후 재사용, 세션 밖이면 None.

    가격 연결(_local.conn)과 생명주기를 함께한다 — 세션 종료 시 같이 닫힌다.
    """
    if getattr(_local, "conn", None) is None:
        return None
    fin = getattr(_local, "financial_conn", None)
    if fin is None:
        fin = psycopg2.connect(**_QUANT_DB_DEFAULTS, database=_FINANCIAL_DB)
        _local.financial_conn = fin
    return fin


# ------------------------------------------------------------------ #
# 내부 헬퍼
# ------------------------------------------------------------------ #
#
# (제거됨) _has_adj_factor / _ADJ_FACTOR_CACHE
#   adj_factor 컬럼 유무를 information_schema 로 탐지해 "있으면 곱하고 없으면 raw"
#   로 분기하던 캐시였다. 곱셈 규약 폐기(★ 모듈 docstring 참조)로 두 분기가 모두
#   raw 조회가 되어 분기 자체가 사라졌다 → 탐지도 캐시도 불필요.
#   부수효과: information_schema 조회(~160ms) 와 세션 워밍이 통째로 없어졌다.


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
    ★ adj_factor 를 곱하지 않는다 — close 는 이미 분할조정된 연속 시세다
      (모듈 docstring 의 곱셈 금지 규약 참조).
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
    sql = r"""
        SELECT date, open, high, low, close, volume
        FROM daily_prices
        WHERE stock_code = %(symbol)s
          AND date < %(as_of_date)s
          AND date::text ~ '^\d{4}-\d{2}-\d{2}$'
        ORDER BY date DESC
        LIMIT %(limit)s
    """
    params = dict(symbol=symbol, as_of_date=as_of_date.isoformat(), limit=lookback_days)

    reuse = _get_reuse_conn()
    if reuse is not None:
        with reuse.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    else:
        with _conn_daily() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
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
    ★ adj_factor 를 곱하지 않는다 (모듈 docstring 의 곱셈 금지 규약 참조).

    backtest_session() 컨텍스트 안에서 호출되면 기존 연결을 재사용해
    connect() 비용(~220ms)을 절감한다.
    """
    sql = """
        SELECT open
        FROM daily_prices
        WHERE stock_code = %(symbol)s
          AND date = %(date)s
        LIMIT 1
    """
    params = dict(symbol=symbol, date=date.isoformat())

    reuse = _get_reuse_conn()
    if reuse is not None:
        with reuse.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    else:
        with _conn_daily() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()

    if row is None:
        return None
    return float(row["open"]) if row["open"] is not None else None


def read_high_low(symbol: str, date: date) -> Optional[tuple[float, float]]:
    """일중 TP/SL 시뮬 전용 — 해당 일자 고가/저가.

    의사결정 입력에 사용 금지 (별도 함수로 분리).
    ★ adj_factor 를 곱하지 않는다 (모듈 docstring 의 곱셈 금지 규약 참조).
    반환: (high, low) 또는 None

    backtest_session() 컨텍스트 안에서 호출되면 기존 연결을 재사용한다.
    """
    sql = """
        SELECT high, low
        FROM daily_prices
        WHERE stock_code = %(symbol)s
          AND date = %(date)s
        LIMIT 1
    """
    params = dict(symbol=symbol, date=date.isoformat())

    reuse = _get_reuse_conn()
    if reuse is not None:
        with reuse.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    else:
        with _conn_daily() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
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

    ⚠️ 현재 죽은 경로 — 소스 통일(resolve_minute_source_db) 대상이 아니다.
      이 함수는 `minute_prices` 테이블을 읽는데 그 테이블은 **어느 DB 에도 없다**
      (실측 2026-07-16: robotrader/kis_template/robotrader_quant 전부 부재.
       실제 분봉 테이블명은 `minute_candles`). 즉 호출하면 어느 소스를 가리키든
      실패하므로, DB 만 바꿔도 고쳐지지 않는다(테이블명·스키마 정합이 선행돼야 함).
      되살릴 때는 minute_candles 로 교정하면서 resolve_minute_source_db() 를 태울 것.
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
    # 재무는 robotrader_quant 고정(의도된 예외) — 가격 재사용 연결(kis_template)을
    # 쓰면 quant_financial_ratio 를 찾지 못한다.
    params = dict(symbol=symbol, lag_cutoff=lag_cutoff)
    reuse = _get_reuse_financial_conn()
    if reuse is not None:
        with reuse.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    else:
        with _conn_financial() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
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
    """screener_snapshots — 해당 시점 후보풀 반환.

    반환: 종목코드 문자열 리스트

    소스는 TIMESCALE_DB(운영 DB) — 가격 데이터가 아니라 **운영 산출물**이라
    가격 resolver 대상이 아니다. 라이브 .env 는 TIMESCALE_DB=kis_template.
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
