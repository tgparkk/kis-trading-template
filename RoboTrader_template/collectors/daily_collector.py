# collectors/daily_collector.py
"""일봉 수집 오케스트레이터 — KIS fetch → kis_template UPSERT → 파생 → adj → 교차비교.

usage:
  python -m collectors.daily_collector --limit 5            # 소수 dry-ish 수집
  python -m collectors.daily_collector                      # 전종목 수집
  python -m collectors.daily_collector --reconcile-only 2026-06-23
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.daily_writer import parse_kis_daily_row, upsert_daily_rows  # noqa: E402
from collectors.daily_derived import update_returns_volatility  # noqa: E402
from collectors.daily_adj import update_adj_factors  # noqa: E402
from api import kis_market_api  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)
COVERAGE_MIN = 0.99
VALUE_MATCH_MIN = 0.99


def load_universe(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT stock_code FROM daily_prices WHERE stock_code ~ '^[0-9]{6}$' ORDER BY stock_code")
        return [r[0] for r in cur.fetchall()]


def collect_one(code: str, lookback_days: int = 7) -> list:
    """한 종목 최근 일봉 fetch+파싱 (market_cap 1회 조회 재사용)."""
    df = kis_market_api.get_inquire_daily_itemchartprice(output_dv="2", div_code="J", itm_no=code)
    if df is None or df.empty:
        return []
    mc = kis_market_api.get_stock_market_cap(code)
    market_cap = None
    if mc and mc.get("current_price"):
        shares = mc["market_cap"] / mc["current_price"] if mc["current_price"] else 0
        # per-row market_cap은 close*shares 로 daily_collector가 보정(여기선 shares 전달용)
        market_cap = shares
    rows = []
    for _, item in df.iterrows():
        parsed = parse_kis_daily_row(dict(item), market_cap=None)
        if parsed is None:
            continue
        parsed["stock_code"] = code
        parsed["market_cap"] = (parsed["close"] * market_cap) if market_cap else None
        rows.append(parsed)
    # KIS 일봉 output2는 정렬 보장이 없다(보통 최신일 우선=내림차순). 날짜 오름차순으로
    # 정렬한 뒤 최신 lookback_days 개를 취해야 '가장 최근 바'(당일 포함)가 반영된다.
    # (이전엔 rows[-N:]가 오름차순을 가정 → 내림차순 응답에선 가장 오래된 바를 적재하던 버그)
    rows.sort(key=lambda r: r["date"])
    return rows[-lookback_days:] if lookback_days else rows


def collect_daily(target_date: str = None, limit: int = None) -> dict:
    with KisDbConnection.get_connection() as conn:
        codes = load_universe(conn)
        if limit:
            codes = codes[:limit]
        total = 0
        for code in codes:
            rows = collect_one(code)
            if rows:
                total += upsert_daily_rows(conn, rows)
        update_returns_volatility(conn)
        adj = update_adj_factors(conn)
    return {"codes": len(codes), "rows": total, "adj": adj}


def reconcile_verdict(real_rows: int, new_rows: int, value_match: int) -> dict:
    if real_rows == 0 and new_rows == 0:
        return {"coverage": 1.0, "value_match_rate": 1.0, "verdict": "EMPTY"}
    coverage = new_rows / real_rows if real_rows else 0.0
    value_match_rate = value_match / new_rows if new_rows else 0.0
    verdict = "PASS" if coverage >= COVERAGE_MIN and value_match_rate >= VALUE_MATCH_MIN else "FAIL"
    return {"coverage": coverage, "value_match_rate": value_match_rate, "verdict": verdict}


def reconcile_daily(trade_date: str) -> dict:
    """새 DB vs 레거시(robotrader_quant) 당일 일봉 비교 + collection_reconciliation 기록."""
    legacy = psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"), port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname="robotrader_quant", user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "robotrader_secure_pw_2024"))
    try:
        with legacy.cursor() as lc:
            lc.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (trade_date,))
            real_rows = lc.fetchone()[0]
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as nc:
                nc.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (trade_date,))
                new_rows = nc.fetchone()[0]
            # 교집합 종가 일치 수 (cross-DB라 새DB 행을 끌어와 레거시와 대조)
            with conn.cursor() as nc:
                nc.execute("SELECT stock_code, close FROM daily_prices WHERE date = %s", (trade_date,))
                new_closes = dict(nc.fetchall())
            value_match = 0
            with legacy.cursor() as lc:
                lc.execute("SELECT stock_code, close FROM daily_prices WHERE date = %s", (trade_date,))
                for sc, close in lc.fetchall():
                    if sc in new_closes and new_closes[sc] is not None and close is not None \
                       and abs(float(new_closes[sc]) - float(close)) < 0.5:
                        value_match += 1
            v = reconcile_verdict(real_rows, new_rows, value_match)
            with conn.cursor() as nc:
                nc.execute(
                    "INSERT INTO collection_reconciliation "
                    "(trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict) "
                    "VALUES (%s,'daily',%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (trade_date, dataset) DO UPDATE SET "
                    "real_rows=EXCLUDED.real_rows, new_rows=EXCLUDED.new_rows, overlap=EXCLUDED.overlap, "
                    "value_match_rate=EXCLUDED.value_match_rate, coverage=EXCLUDED.coverage, verdict=EXCLUDED.verdict",
                    (trade_date, real_rows, new_rows, value_match, v["value_match_rate"], v["coverage"], v["verdict"]))
            conn.commit()
        v.update({"trade_date": trade_date, "real_rows": real_rows, "new_rows": new_rows, "value_match": value_match})
        return v
    finally:
        legacy.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--reconcile-only", default=None)
    args = ap.parse_args()
    if args.reconcile_only:
        print(reconcile_daily(args.reconcile_only))
    else:
        print(collect_daily(args.date, args.limit))
