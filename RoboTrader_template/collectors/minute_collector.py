# collectors/minute_collector.py
"""분봉 수집 오케스트레이터 — top300 → 당일 분봉 fetch → minute_candles → 교차비교.

usage:
  python -m collectors.minute_collector --limit 5
  python -m collectors.minute_collector
  python -m collectors.minute_collector --reconcile-only 20260623
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.minute_universe import select_top_volume  # noqa: E402
from collectors.minute_writer import df_to_minute_rows, replace_minute_day  # noqa: E402
from api import kis_chart_api  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


def collect_minute(target_date: str = None, top_n: int = 300, limit: int = None) -> dict:
    codes = select_top_volume(top_n)
    if limit:
        codes = codes[:limit]
    total = 0
    with KisDbConnection.get_connection() as conn:
        for code in codes:
            df = kis_chart_api.get_full_trading_day_data(code, target_date or "", "153000")
            if df is None or len(df) == 0:
                continue
            rows = df_to_minute_rows(code, df)
            if rows:
                total += replace_minute_day(conn, code, rows[0]["trade_date"], rows)
    return {"codes": len(codes), "rows": total}


def _load_bars(conn, trade_date: str) -> dict:
    """{stock_code: {(time, close), ...}} for trade_date."""
    out = {}
    with conn.cursor() as cur:
        cur.execute("SELECT stock_code, time, close FROM minute_candles WHERE trade_date=%s", (trade_date,))
        for sc, t, c in cur.fetchall():
            out.setdefault(sc, set()).add((str(t), float(c) if c is not None else None))
    return out


def minute_match_rate(new: dict, legacy: dict):
    """교집합 종목의 바(time,close) 일치율. 반환 (rate, overlap_stock_count)."""
    inter = set(new) & set(legacy)
    if not inter:
        return 0.0, 0
    matched_bars = total_bars = 0
    for sc in inter:
        nb, lb = new[sc], legacy[sc]
        total_bars += len(lb)
        matched_bars += len(nb & lb)
    rate = (matched_bars / total_bars) if total_bars else 0.0
    return rate, len(inter)


def reconcile_minute(trade_date: str) -> dict:
    legacy = psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"), port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname="robotrader", user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "robotrader_secure_pw_2024"))
    try:
        legacy_bars = _load_bars(legacy, trade_date)
        with KisDbConnection.get_connection() as conn:
            new_bars = _load_bars(conn, trade_date)
            rate, overlap = minute_match_rate(new_bars, legacy_bars)
            real_rows = sum(len(v) for v in legacy_bars.values())
            new_rows = sum(len(v) for v in new_bars.values())
            coverage = (len(new_bars) / len(legacy_bars)) if legacy_bars else (1.0 if not new_bars else 0.0)
            verdict = "PASS" if (coverage >= 0.9 and rate >= 0.95 and overlap > 0) else (
                "EMPTY" if real_rows == 0 and new_rows == 0 else "FAIL")
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO collection_reconciliation "
                    "(trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict) "
                    "VALUES (%s,'minute',%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (trade_date, dataset) DO UPDATE SET "
                    "real_rows=EXCLUDED.real_rows, new_rows=EXCLUDED.new_rows, overlap=EXCLUDED.overlap, "
                    "value_match_rate=EXCLUDED.value_match_rate, coverage=EXCLUDED.coverage, verdict=EXCLUDED.verdict",
                    (trade_date, real_rows, new_rows, overlap, rate, coverage, verdict))
            conn.commit()
        return {"trade_date": trade_date, "real_rows": real_rows, "new_rows": new_rows,
                "overlap": overlap, "value_match_rate": rate, "coverage": coverage, "verdict": verdict}
    finally:
        legacy.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--reconcile-only", default=None)
    args = ap.parse_args()
    if args.reconcile_only:
        print(reconcile_minute(args.reconcile_only))
    else:
        print(collect_minute(args.date, limit=args.limit))
