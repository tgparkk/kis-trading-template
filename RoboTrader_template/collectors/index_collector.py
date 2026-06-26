"""지수 일봉 수집 — FDR KS11/KQ11 → index_daily.

usage:
  python -m collectors.index_collector
  python -m collectors.index_collector --start 2026-06-01
  python -m collectors.index_collector --reconcile-only 2026-06-26
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.index_writer import fdr_df_to_index_rows, upsert_index_rows  # noqa: E402
from collectors.daily_collector import reconcile_verdict  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)
INDEX_TICKERS = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}
# 레거시 종목코드 → 새 DB index_code 매핑
_LEGACY_CODE_MAP = {"KS11": "KOSPI", "KQ11": "KOSDAQ"}


def collect_index(start: str = None) -> dict:
    import FinanceDataReader as fdr
    if start is None:
        start = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
    result = {}
    with KisDbConnection.get_connection() as conn:
        for name, ticker in INDEX_TICKERS.items():
            df = fdr.DataReader(ticker, start)
            rows = fdr_df_to_index_rows(name, df)
            result[name] = upsert_index_rows(conn, rows)
    return result


def reconcile_index(trade_date: str) -> dict:
    """새 DB(index_daily) vs 레거시(robotrader_quant.daily_prices) 당일 지수 비교 + collection_reconciliation 기록.

    지수 허용오차: 상대오차 1% 이내(FDR 잠정치가 T일 장마감 직후 레거시와 미세 차이를 허용,
    다음날 수렴). new_rows=0이면 반드시 FAIL — FDR 미설치 등 조용한 수집 실패를 탐지.
    """
    legacy = psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"), port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname="robotrader_quant", user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "robotrader_secure_pw_2024"))
    try:
        # 레거시 KS11/KQ11 close → {KOSPI: close, KOSDAQ: close}
        legacy_closes = {}
        with legacy.cursor() as lc:
            lc.execute(
                "SELECT stock_code, close FROM daily_prices "
                "WHERE stock_code IN ('KS11','KQ11') AND date = %s",
                (trade_date,))
            for sc, close in lc.fetchall():
                idx = _LEGACY_CODE_MAP.get(sc)
                if idx and close is not None:
                    legacy_closes[idx] = float(close)
        real_rows = len(legacy_closes)

        with KisDbConnection.get_connection() as conn:
            # 새 DB index_daily KOSPI/KOSDAQ close
            new_closes = {}
            with conn.cursor() as nc:
                nc.execute(
                    "SELECT index_code, close FROM index_daily "
                    "WHERE index_code IN ('KOSPI','KOSDAQ') AND date = %s",
                    (trade_date,))
                for idx, close in nc.fetchall():
                    if close is not None:
                        new_closes[idx] = float(close)
            new_rows = len(new_closes)

            # 상대오차 1% 이내 일치 수 (일봉과 달리 지수는 잠정치 허용)
            value_match = 0
            for idx, new_close in new_closes.items():
                old_close = legacy_closes.get(idx)
                if old_close is not None and old_close != 0:
                    if abs(new_close - old_close) / old_close <= 0.01:
                        value_match += 1

            v = reconcile_verdict(real_rows, new_rows, value_match)

            with conn.cursor() as nc:
                nc.execute(
                    "INSERT INTO collection_reconciliation "
                    "(trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict) "
                    "VALUES (%s,'index',%s,%s,%s,%s,%s,%s) "
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
    ap.add_argument("--start", default=None)
    ap.add_argument("--reconcile-only", default=None)
    args = ap.parse_args()
    if args.reconcile_only:
        print(reconcile_index(args.reconcile_only))
    else:
        print(collect_index(args.start))
