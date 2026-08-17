"""외국인 순매매량 수집 — 네이버 금융 frgn.naver → foreign_flow.

usage:
  python -m collectors.foreign_flow_collector
  python -m collectors.foreign_flow_collector --limit 5

2026-08-17: `reconcile_foreign_flow`(+`_prev_trading_day`) 제거. 「새 DB vs 레거시
  robotrader_quant.foreign_flow」 대조였는데, 레거시 foreign_flow 는 2026-06-12 이후,
  레거시 DB 전체는 2026-07-10 동결이라 이미 교차검증 불가(no-legacy PASS)였다.
  `KIS_DATA_SOURCE=legacy` 게이트 폐지 + `robotrader` DB 삭제로 도달 불가가 됐다.
  (`collection_reconciliation` 표는 과거 이력이므로 유지.)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.foreign_flow_writer import naver_df_to_rows, upsert_foreign_rows  # noqa: E402
from collectors.daily_collector import load_universe  # noqa: E402
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    print(collect_foreign_flow(limit=args.limit))
