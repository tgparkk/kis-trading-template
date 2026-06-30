"""레거시 → kis_template 시딩(멱등). 일봉(robotrader_quant)·corp_events(robotrader) 1회 복사.

usage: python -m scripts.kis_db.seed_from_legacy            # dry-run(소스 행수만)
       python -m scripts.kis_db.seed_from_legacy --apply    # 실제 복사
"""
import argparse
import os
import sys

import json

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402

DAILY_COLUMNS = [
    "stock_code", "date", "open", "high", "low", "close",
    "volume", "trading_value", "market_cap",
    "returns_1d", "returns_5d", "returns_20d", "volatility_20d", "adj_factor",
]
CORP_COLUMNS = ["stock_code", "event_type", "event_date", "end_date", "meta"]
FOREIGN_COLUMNS = ["stock_code", "date", "foreign_net_vol", "source"]
BATCH = 5000


def _legacy_conn(dbname: str):
    return psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"),
        port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname=dbname,
        user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "1234"),
    )


def build_daily_insert_rows(legacy_rows):
    """레거시 daily_prices 행(DAILY_COLUMNS 순서 SELECT 결과)을 그대로 반환(컬럼 동일)."""
    return list(legacy_rows)


def build_corp_insert_rows(legacy_rows):
    """corp_events 행의 meta(dict) 컬럼을 JSON 문자열로 직렬화 (psycopg2 jsonb 적응)."""
    result = []
    for row in legacy_rows:
        row = list(row)
        # meta는 마지막 컬럼(인덱스 4): dict → JSON 문자열
        if isinstance(row[4], dict):
            row[4] = json.dumps(row[4], ensure_ascii=False)
        result.append(tuple(row))
    return result


def _copy(src_dbname, select_sql, table, columns, apply: bool, row_builder=None) -> dict:
    if row_builder is None:
        row_builder = build_daily_insert_rows
    src = _legacy_conn(src_dbname)
    copied = 0
    source_rows = 0
    cols_csv = ", ".join(columns)
    # PK 충돌 시 스킵(멱등). 시딩은 1회성이라 DO NOTHING으로 충분.
    upsert = f"INSERT INTO {table} ({cols_csv}) VALUES %s ON CONFLICT DO NOTHING"
    try:
        with src.cursor(name=f"seed_{table}") as scur:  # 서버사이드 커서(스트리밍)
            scur.itersize = BATCH
            scur.execute(select_sql)
            with KisDbConnection.get_connection() as dst:
                while True:
                    rows = scur.fetchmany(BATCH)
                    if not rows:
                        break
                    source_rows += len(rows)
                    if apply:
                        with dst.cursor() as dcur:
                            execute_values(dcur, upsert, row_builder(rows))
                        dst.commit()
                        copied += len(rows)
    finally:
        src.close()
    return {"copied": copied, "source_rows": source_rows}


def seed_daily_prices(apply: bool = False) -> dict:
    sel = f"SELECT {', '.join(DAILY_COLUMNS)} FROM daily_prices"
    return _copy("robotrader_quant", sel, "daily_prices", DAILY_COLUMNS, apply)


def seed_corp_events(apply: bool = False) -> dict:
    sel = f"SELECT {', '.join(CORP_COLUMNS)} FROM corp_events"
    return _copy("robotrader", sel, "corp_events", CORP_COLUMNS, apply, row_builder=build_corp_insert_rows)


def seed_foreign_flow(apply: bool = False) -> dict:
    sel = f"SELECT {', '.join(FOREIGN_COLUMNS)} FROM foreign_flow"
    return _copy("robotrader_quant", sel, "foreign_flow", FOREIGN_COLUMNS, apply)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    d = seed_daily_prices(args.apply)
    e = seed_corp_events(args.apply)
    f = seed_foreign_flow(args.apply)
    print(f"daily_prices:  {d}")
    print(f"corp_events:   {e}")
    print(f"foreign_flow:  {f}")
