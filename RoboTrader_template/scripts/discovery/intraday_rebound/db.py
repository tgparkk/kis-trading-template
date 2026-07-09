# scripts/discovery/intraday_rebound/db.py
"""읽기 전용 DB 커넥터. dbname을 명시적으로 받는다.

라이브 db.connection.DatabaseConnection은 TIMESCALE_DB env를 따라가므로
이 연구에서는 사용하지 않는다 (분봉 SSOT는 robotrader, 일봉은 kis_template).
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

MINUTE_DB = "robotrader"
DAILY_DB = "kis_template"


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
