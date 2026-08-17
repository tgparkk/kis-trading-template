"""지수 일봉 수집 — FDR KS11/KQ11 → index_daily.

usage:
  python -m collectors.index_collector
  python -m collectors.index_collector --start 2026-06-01

2026-08-17: `reconcile_index` 제거. 「새 DB index_daily vs 레거시
  robotrader_quant.daily_prices(KS11/KQ11)」 당일 대조였는데, 레거시는 2026-07-10
  동결이라 이미 휴면이었고 `KIS_DATA_SOURCE=legacy` 게이트 폐지 + `robotrader` DB
  삭제로 도달 불가가 됐다. (`collection_reconciliation` 표는 과거 이력이므로 유지.)
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.index_writer import fdr_df_to_index_rows, upsert_index_rows  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)
INDEX_TICKERS = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}


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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    args = ap.parse_args()
    print(collect_index(args.start))
