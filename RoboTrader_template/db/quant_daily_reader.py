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
        """scan_date(date 또는 'YYYY-MM-DD') 이하 '완전한 퀀트 유니버스'가 있는 최신일의 (stock_code, market_cap, trading_value).

        정확매칭(date = scan_date) 대신 ``date <= scan_date`` 중 최대일을 쓰는 방어적 조회로,
        EOD 스크리너가 quant 적재(~15:35) 전에 돌거나 scan_date 가 휴장/미적재일이어도
        직전 거래일 유니버스로 폴백해 빈 유니버스가 되지 않게 한다(타이밍 무관).

        추가로 ``market_cap IS NOT NULL`` 판별을 건다(DB 컷오버 KIS_DATA_SOURCE=new 대비):
        운영 현재가 쓰기(price.save_daily_prices_batch)는 OHLCV/volume 만 채우고
        market_cap 등 퀀트 메타는 NULL로 남긴다. 반면 퀀트 유니버스 행(수집기/이관분)만
        market_cap 이 채워진다. 병합 DB(kis_template)에서는 보유 종목 몇 개만 오늘자로
        UPSERT 되면 max(date)=오늘이 되어 전종목 유니버스가 그 몇 종목으로 붕괴한다.
        따라서 (1) 서브쿼리에서 market_cap 채워진 행이 있는 최신일만 고르고(부분 운영일 건너뜀),
        (2) 바깥 조회에서도 market_cap 채워진 행만 반환해 운영 전용 스트래글러·지수 유사행
        (KOSPI/KOSDAQ, market_cap NULL)을 유니버스에서 배제한다 → 레거시(분리 DB)의
        '순수 퀀트 유니버스' 의미를 복원한다. (룩어헤드는 여전히 ``date <= scan_date`` 로 차단.)
        """
        d = scan_date if isinstance(scan_date, str) else scan_date.strftime("%Y-%m-%d")
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT stock_code, COALESCE(market_cap,0), "
                        "COALESCE(NULLIF(trading_value,0), (close*volume)::numeric, 0) "
                        "FROM daily_prices "
                        "WHERE date = (SELECT max(date) FROM daily_prices "
                        "              WHERE date <= %s AND market_cap IS NOT NULL) "
                        "AND market_cap IS NOT NULL",
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
