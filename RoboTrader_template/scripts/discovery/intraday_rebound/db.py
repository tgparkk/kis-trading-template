# scripts/discovery/intraday_rebound/db.py
"""읽기 전용 DB 커넥터. dbname을 명시적으로 받는다.

라이브 db.connection.DatabaseConnection은 TIMESCALE_DB env를 따라가므로
이 연구에서는 사용하지 않는다.

2026-07-10: 분봉 히스토리가 kis_template으로 이관됨 — `(stock_code, trade_date,
datetime)` 기준 중복제거, 잉여 행은 kis_template.minute_candles_dupes에 보존.
robotrader는 decommission 예정. 옛 DB 대비 비교 실행이 필요할 경우를 위해
REBOUND_MINUTE_DB/REBOUND_DAILY_DB env로 오버라이드 가능하게 유지한다.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pandas as pd
import psycopg2

DB_HOST = os.getenv("REBOUND_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("REBOUND_DB_PORT", "5433"))
DB_USER = os.getenv("REBOUND_DB_USER", "robotrader")
DB_PASSWORD = os.getenv("REBOUND_DB_PASSWORD", "1234")

MINUTE_DB = os.getenv("REBOUND_MINUTE_DB", "kis_template")
DAILY_DB = os.getenv("REBOUND_DAILY_DB", "kis_template")


@contextmanager
def connect(dbname: str):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=dbname,
    )
    try:
        conn.set_session(readonly=True, autocommit=True)
        yield conn
    finally:
        conn.close()


def read_sql(sql: str, params: tuple, dbname: str) -> pd.DataFrame:
    """SELECT 실행 후 DataFrame 반환. 쓰기 불가 세션."""
    with connect(dbname) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        cur.close()
    return pd.DataFrame(rows, columns=cols)
