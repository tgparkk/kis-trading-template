"""외국인 순매매량 수집 — 네이버 금융 frgn.naver → foreign_flow.

usage:
  python -m collectors.foreign_flow_collector
  python -m collectors.foreign_flow_collector --limit 5
  python -m collectors.foreign_flow_collector --reconcile-only 2026-06-30
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.foreign_flow_writer import naver_df_to_rows, upsert_foreign_rows  # noqa: E402
from collectors.daily_collector import load_universe, reconcile_verdict  # noqa: E402
from collectors.foreign_flow_fetcher import fetch_foreign_naver  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


def collect_foreign_flow(target_date: str = None, limit: int = None) -> dict:
    """daily_prices 유니버스 종목별 네이버 외국인 순매매량 fetch → 새 DB UPSERT.

    target_date 는 EOD 오케스트레이션 시그니처 정합용(증분 fetch 가 최근 ~40일을
    포괄하므로 별도 분기 불필요). 반환 {"codes": n, "rows": total}.
    """
    total = 0
    with KisDbConnection.get_connection() as conn:
        codes = load_universe(conn)
        if limit:
            codes = codes[:limit]
        for code in codes:
            # EOD 증분: 2페이지(~40일)면 당일 포함 충분
            df = fetch_foreign_naver(code, max_pages=2)
            rows = naver_df_to_rows(code, df)
            if rows:
                total += upsert_foreign_rows(conn, rows)
    return {"codes": len(codes), "rows": total}


def reconcile_foreign_flow(trade_date: str) -> dict:
    """새 DB(foreign_flow) vs 레거시(robotrader_quant.foreign_flow) 당일 비교 + 기록.

    레거시 foreign_flow 는 2026-06-12 이후 동결(수동 백필만) → 교차검증 불가.
      - new_rows==0 → FAIL (네이버 차단·스크래핑 실패 탐지).
      - real_rows==0 and new_rows>0 → PASS(no-legacy), value_match_rate=1.0, coverage=1.0.
      - 둘 다 있으면 foreign_net_vol 정확일치 교집합으로 일반 verdict.
    """
    legacy = psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"), port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname="robotrader_quant", user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "1234"))
    try:
        legacy_vols = {}
        with legacy.cursor() as lc:
            lc.execute(
                "SELECT stock_code, foreign_net_vol FROM foreign_flow WHERE date = %s",
                (trade_date,))
            for sc, vol in lc.fetchall():
                if vol is not None:
                    legacy_vols[sc] = int(vol)
        real_rows = len(legacy_vols)

        with KisDbConnection.get_connection() as conn:
            new_vols = {}
            with conn.cursor() as nc:
                nc.execute(
                    "SELECT stock_code, foreign_net_vol FROM foreign_flow WHERE date = %s",
                    (trade_date,))
                for sc, vol in nc.fetchall():
                    if vol is not None:
                        new_vols[sc] = int(vol)
            new_rows = len(new_vols)

            if new_rows == 0:
                # 수집 실패가 최우선 — 레거시 유무와 무관하게 FAIL
                value_match = 0
                v = {"coverage": 0.0, "value_match_rate": 0.0, "verdict": "FAIL"}
            elif real_rows == 0:
                # 레거시 동결 → 교차검증 불가, 오늘 수집 성공만 확인(no-legacy PASS)
                value_match = 0
                v = {"coverage": 1.0, "value_match_rate": 1.0, "verdict": "PASS"}
            else:
                value_match = 0
                for sc, new_v in new_vols.items():
                    old_v = legacy_vols.get(sc)
                    if old_v is not None and old_v == new_v:
                        value_match += 1
                v = reconcile_verdict(real_rows, new_rows, value_match)

            with conn.cursor() as nc:
                nc.execute(
                    "INSERT INTO collection_reconciliation "
                    "(trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict) "
                    "VALUES (%s,'foreign_flow',%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (trade_date, dataset) DO UPDATE SET "
                    "real_rows=EXCLUDED.real_rows, new_rows=EXCLUDED.new_rows, overlap=EXCLUDED.overlap, "
                    "value_match_rate=EXCLUDED.value_match_rate, coverage=EXCLUDED.coverage, verdict=EXCLUDED.verdict",
                    (trade_date, real_rows, new_rows, value_match,
                     v["value_match_rate"], v["coverage"], v["verdict"]))
            conn.commit()

        v.update({"trade_date": trade_date, "real_rows": real_rows,
                  "new_rows": new_rows, "value_match": value_match})
        return v
    finally:
        legacy.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--reconcile-only", default=None)
    args = ap.parse_args()
    if args.reconcile_only:
        print(reconcile_foreign_flow(args.reconcile_only))
    else:
        print(collect_foreign_flow(limit=args.limit))
