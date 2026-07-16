# scripts/discovery/intraday_rebound/db.py
"""읽기 전용 DB 커넥터. dbname을 명시적으로 받는다.

라이브 db.connection.DatabaseConnection은 TIMESCALE_DB env(운영 DB)를 따라가므로
이 연구에서는 사용하지 않는다.

2026-07-10: 분봉 히스토리가 kis_template으로 이관됨 — `(stock_code, trade_date,
datetime)` 기준 중복제거, 잉여 행은 kis_template.minute_candles_dupes에 보존.

2026-07-16(연구 소스 통일): 자체 env(REBOUND_MINUTE_DB/REBOUND_DAILY_DB)로
kis_template을 개별 지정하던 것을 **공용 resolver로 수렴**했다. 같은 기본값
(kis_template)을 유지하면서, 롤백 스위치가 프로젝트 전체에 하나(KIS_DATA_SOURCE)만
남도록 한다 — 소스가 여러 env로 갈라지면 일부 경로만 레거시로 새는 사고가 난다.
옛 DB 대비 비교 실행은 `KIS_DATA_SOURCE=legacy`로 수행한다.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import psycopg2

_TEMPLATE_ROOT = Path(__file__).resolve().parents[3]
if str(_TEMPLATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEMPLATE_ROOT))

from config.constants import (  # noqa: E402
    resolve_daily_source_db,
    resolve_minute_source_db,
)

DB_HOST = os.getenv("REBOUND_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("REBOUND_DB_PORT", "5433"))
DB_USER = os.getenv("REBOUND_DB_USER", "robotrader")
DB_PASSWORD = os.getenv("REBOUND_DB_PASSWORD", "1234")

MINUTE_DB = resolve_minute_source_db()
DAILY_DB = resolve_daily_source_db()


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
