"""운영 데이터 이관(멱등): robotrader → kis_template. 우리 행만, PK 보존, DELETE 없음.

- virtual_trading_records: WHERE source='kis_template' 만.
- real_trading_records / real_trading_{instance}: 우리 인스턴스 테이블만.
- paper_trading_state · candidate_stocks · screener_snapshots: 전량(우리 봇 소유).
UPSERT/ON CONFLICT DO NOTHING 로 재실행 안전. 복사 후 SERIAL 시퀀스를 setval 로 올려
봇의 다음 INSERT 가 이관된 id 와 충돌하지 않게 한다.

usage: python -m scripts.kis_db.migrate_operational_data            # dry-run
       python -m scripts.kis_db.migrate_operational_data --apply    # 실제 복사
"""
import argparse
import json
import os
import sys

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from scripts.kis_db import schema  # noqa: E402

BATCH = 5000
SOURCE_DB = "robotrader"

VTR_COLUMNS = [
    "id", "stock_code", "stock_name", "action", "quantity", "price",
    "timestamp", "strategy", "reason", "is_test", "profit_loss",
    "profit_rate", "buy_record_id", "target_profit_rate", "stop_loss_rate",
    "created_at", "source",
]
REAL_COLUMNS = [
    "id", "stock_code", "stock_name", "action", "quantity", "price",
    "timestamp", "strategy", "reason", "profit_loss", "profit_rate",
    "buy_record_id", "created_at",
]
CANDIDATE_COLUMNS = [
    "id", "stock_code", "stock_name", "selection_date", "score",
    "reasons", "status", "created_at",
]
SCREENER_COLUMNS = [
    "id", "strategy", "scan_date", "params_hash", "params_json",
    "stock_code", "stock_name", "rank_in_snapshot", "score", "metadata",
    "created_at",
]
PAPER_STATE_COLUMNS = ["trade_date", "eod_balance", "updated_at"]

# screener_snapshots 의 jsonb 컬럼 위치 (params_json=4, metadata=9)
_SCREENER_JSON_IDX = (4, 9)
# execute_values 템플릿: params_json/metadata 를 ::jsonb 로 캐스팅
_SCREENER_TEMPLATE = (
    "(%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s)"
)


def _source_conn():
    return psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"),
        port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname=SOURCE_DB,
        user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "1234"),
    )


def build_vtr_select() -> str:
    cols = ", ".join(VTR_COLUMNS)
    return (
        f"SELECT {cols} FROM virtual_trading_records "
        f"WHERE source = 'kis_template' ORDER BY id"
    )


def build_screener_rows(legacy_rows):
    """params_json/metadata dict 컬럼을 JSON 문자열로 직렬화(psycopg2 jsonb 적응)."""
    out = []
    for row in legacy_rows:
        row = list(row)
        for i in _SCREENER_JSON_IDX:
            if isinstance(row[i], (dict, list)):
                row[i] = json.dumps(row[i], ensure_ascii=False)
        out.append(tuple(row))
    return out


def _passthrough(rows):
    return list(rows)


def discover_real_tables(conn):
    """robotrader 소스에서 real_trading_* 테이블명을 오름차순으로 반환(base+instances)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name LIKE 'real_trading_%' "
            "ORDER BY table_name"
        )
        return [r[0] for r in cur.fetchall()]


def migrate_table(src_conn, select_sql, table, columns, conflict_target,
                  apply=False, row_builder=None, template=None) -> dict:
    """멱등 스트리밍 복사. apply=False 면 source_rows 만 카운트(쓰기 없음)."""
    if row_builder is None:
        row_builder = _passthrough
    cols_csv = ", ".join(columns)
    conflict = f"ON CONFLICT {conflict_target} DO NOTHING" if conflict_target else "ON CONFLICT DO NOTHING"
    upsert = f"INSERT INTO {table} ({cols_csv}) VALUES %s {conflict}"
    copied = 0
    source_rows = 0
    with src_conn.cursor(name=f"mig_{table}") as scur:
        scur.itersize = BATCH
        scur.execute(select_sql)
        dst_cm = KisDbConnection.get_connection() if apply else None
        dst = dst_cm.__enter__() if dst_cm else None
        try:
            while True:
                rows = scur.fetchmany(BATCH)
                if not rows:
                    break
                source_rows += len(rows)
                if apply:
                    with dst.cursor() as dcur:
                        execute_values(dcur, upsert, row_builder(rows), template=template)
                    dst.commit()
                    copied += len(rows)
        finally:
            if dst_cm:
                dst_cm.__exit__(None, None, None)
    return {"table": table, "source_rows": source_rows, "copied": copied}


def bump_serial_sequence(dst_conn, table, id_col="id") -> None:
    """복사한 명시적 id 이후로 SERIAL 시퀀스를 올린다(봇 다음 INSERT 충돌 방지). 멱등."""
    with dst_conn.cursor() as cur:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence(%s, %s), "
            f"COALESCE((SELECT MAX({id_col}) FROM {table}), 1))",
            (table, id_col),
        )
    dst_conn.commit()


def run(apply=False, extra_instances=None) -> dict:
    results = {}
    # 대상 스키마 보장(멱등)
    if apply:
        with KisDbConnection.get_connection() as conn:
            schema.create_all(conn)
    src = _source_conn()
    real_tables = []
    try:
        # 1) virtual_trading_records (우리 source 만)
        results["virtual_trading_records"] = migrate_table(
            src, build_vtr_select(), "virtual_trading_records",
            VTR_COLUMNS, "(id)", apply)
        # 2) candidate_stocks (전량)
        results["candidate_stocks"] = migrate_table(
            src, f"SELECT {', '.join(CANDIDATE_COLUMNS)} FROM candidate_stocks ORDER BY id",
            "candidate_stocks", CANDIDATE_COLUMNS, "(id)", apply)
        # 3) screener_snapshots (전량, jsonb 직렬화)
        results["screener_snapshots"] = migrate_table(
            src, f"SELECT {', '.join(SCREENER_COLUMNS)} FROM screener_snapshots ORDER BY id",
            "screener_snapshots", SCREENER_COLUMNS, "(id)", apply,
            row_builder=build_screener_rows, template=_SCREENER_TEMPLATE)
        # 4) paper_trading_state (전량, PK=trade_date)
        results["paper_trading_state"] = migrate_table(
            src, f"SELECT {', '.join(PAPER_STATE_COLUMNS)} FROM paper_trading_state ORDER BY trade_date",
            "paper_trading_state", PAPER_STATE_COLUMNS, "(trade_date)", apply)
        # 5) real_trading_* (우리 인스턴스 테이블들)
        real_tables = discover_real_tables(src)
        for name in (extra_instances or []):
            if name not in real_tables:
                real_tables.append(name)
        for rt in real_tables:
            if apply:
                # 대상에 인스턴스 테이블 보장(base LIKE)
                with KisDbConnection.get_connection() as conn:
                    with conn.cursor() as c:
                        c.execute(
                            f"CREATE TABLE IF NOT EXISTS {rt} "
                            f"(LIKE real_trading_records INCLUDING ALL)")
                    conn.commit()
            results[rt] = migrate_table(
                src, f"SELECT {', '.join(REAL_COLUMNS)} FROM {rt} ORDER BY id",
                rt, REAL_COLUMNS, "(id)", apply)
    finally:
        src.close()
    # 시퀀스 bump (apply 시에만) — 위에서 캡처한 real_tables 재사용(src 는 이미 close)
    if apply:
        with KisDbConnection.get_connection() as conn:
            for t in ["virtual_trading_records", "candidate_stocks", "screener_snapshots"]:
                bump_serial_sequence(conn, t)
            for rt in real_tables:
                bump_serial_sequence(conn, rt)
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="운영 데이터 robotrader→kis_template 이관(멱등)")
    ap.add_argument("--apply", action="store_true", help="실제 복사(미지정=dry-run)")
    ap.add_argument("--instance", action="append", default=None,
                    help="추가 real_trading_{instance} 테이블명(반복 가능)")
    args = ap.parse_args(argv)
    results = run(apply=args.apply, extra_instances=args.instance)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] 운영 데이터 이관 결과:")
    for table, r in results.items():
        print(f"  {table:28s} source={r['source_rows']:>7} copied={r['copied']:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
