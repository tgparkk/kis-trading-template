# collectors/minute_collector.py
"""분봉 수집 오케스트레이터 — top300 → 당일 분봉 fetch → minute_candles.

usage:
  python -m collectors.minute_collector --limit 5
  python -m collectors.minute_collector

2026-08-17: `reconcile_minute`(+`_load_bars`/`minute_match_rate`) 제거. 「새 DB vs
  레거시 robotrader」 당일 분봉 대조였는데, 레거시는 2026-07-10 동결이라 이미
  휴면이었고 `KIS_DATA_SOURCE=legacy` 게이트 폐지 + `robotrader` DB 삭제로 도달
  불가가 됐다. (기록 테이블 `collection_reconciliation` 은 과거 이력이므로 유지.)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--date", default=None)
    args = ap.parse_args()
    print(collect_minute(args.date, limit=args.limit))
