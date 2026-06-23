"""robotrader_quant.daily_prices 읽기 전용 리더 (스크리너 유니버스·일봉용).

kis-template 기본 DB(robotrader)와 별개로, 전 종목·매일 갱신되는
robotrader_quant 에서 일봉/유니버스를 읽는다. 같은 5433 서버, dbname만 다름.
DB의 date 컬럼은 text('YYYY-MM-DD')라 ISO 문자열 비교로 필터/정렬하지만,
반환 DataFrame의 date는 datetime64로 변환된다.
유니버스에 종목명 소스가 없어 CandidateStock.name=종목코드로 채움
(기존 _fetch_candidates_for_strategy 와 동일).
"""
import os
import threading
from contextlib import contextmanager

import pandas as pd
import psycopg2
from psycopg2 import pool

from utils.logger import setup_logger
from config.constants import resolve_daily_source_db

logger = setup_logger(__name__)


class QuantDailyReader:
    _pool = None
    _lock = threading.Lock()

    @classmethod
    def _get_pool(cls):
        if cls._pool is None:
            with cls._lock:
                if cls._pool is None:
                    cfg = {
                        "host": os.getenv("TIMESCALE_HOST", "localhost"),
                        "port": int(os.getenv("TIMESCALE_PORT", 5433)),
                        "database": resolve_daily_source_db(),
                        "user": os.getenv("TIMESCALE_USER", "robotrader"),
                        "password": os.getenv("TIMESCALE_PASSWORD", "1234"),
                    }
                    cls._pool = pool.ThreadedConnectionPool(1, 5, **cfg)
                    logger.info("QuantDailyReader 풀 초기화: %s/%s", cfg["host"], cfg["database"])
        return cls._pool

    @contextmanager
    def _conn(self):
        p = self._get_pool()
        c = p.getconn()
        try:
            yield c
        finally:
            p.putconn(c)

    def get_universe_snapshot(self, scan_date) -> list:
        """scan_date(date 또는 'YYYY-MM-DD') 이하 '최신 거래일'의 (stock_code, market_cap, trading_value).

        정확매칭(date = scan_date) 대신 ``date <= scan_date`` 중 최대일을 사용하는 방어적 조회.
        EOD 스크리너가 quant 적재(~15:35) 전에 돌거나, scan_date 가 휴장/미적재일이어도
        직전 거래일 유니버스로 폴백해 빈 유니버스가 되지 않게 한다(타이밍 무관).
        """
        d = scan_date if isinstance(scan_date, str) else scan_date.strftime("%Y-%m-%d")
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT stock_code, COALESCE(market_cap,0), "
                        "COALESCE(NULLIF(trading_value,0), (close*volume)::numeric, 0) "
                        "FROM daily_prices "
                        "WHERE date = (SELECT max(date) FROM daily_prices WHERE date <= %s)",
                        (d,),
                    )
                    rows = cur.fetchall()
            return [
                {"stock_code": str(c), "market_cap": float(m or 0), "trading_value": float(t or 0)}
                for c, m, t in rows
            ]
        except (psycopg2.OperationalError, psycopg2.ProgrammingError) as e:
            logger.error("quant 연결/스키마 오류 (%s): %s", d, e)
            raise
        except psycopg2.Error as e:
            logger.warning("quant get_universe_snapshot 실패 (%s): %s", d, e)
            return []

    def get_daily_prices(self, stock_code: str, end_date=None, days: int = 120) -> pd.DataFrame:
        """stock_code 의 일봉 최근 days행(end_date 이하). 오름차순 DataFrame.

        DB의 date 컬럼은 text('YYYY-MM-DD')이지만,
        반환 DataFrame의 date는 datetime64로 변환된다.
        """
        end = None
        if end_date is not None:
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y-%m-%d")
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    if end:
                        cur.execute(
                            "SELECT date, open, high, low, close, volume FROM daily_prices "
                            "WHERE stock_code = %s AND date <= %s ORDER BY date DESC LIMIT %s",
                            (stock_code, end, int(days)),
                        )
                    else:
                        cur.execute(
                            "SELECT date, open, high, low, close, volume FROM daily_prices "
                            "WHERE stock_code = %s ORDER BY date DESC LIMIT %s",
                            (stock_code, int(days)),
                        )
                    rows = cur.fetchall()
        except (psycopg2.OperationalError, psycopg2.ProgrammingError) as e:
            logger.error("quant 연결/스키마 오류 (%s): %s", stock_code, e)
            raise
        except psycopg2.Error as e:
            logger.warning("quant get_daily_prices 실패 (%s): %s", stock_code, e)
            return pd.DataFrame()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
        df = df.dropna(subset=["date"])
        return df.sort_values("date").reset_index(drop=True)
