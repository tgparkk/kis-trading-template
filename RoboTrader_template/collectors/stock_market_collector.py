"""종목→시장(KOSPI/KOSDAQ) 매핑 수집 — FDR StockListing → stock_market.

usage:
  python -m collectors.stock_market_collector

⚠️ KIS API 를 쓰지 않는다. 앱키당 토큰이 1개라 봇 가동 중 KIS 호출은 라이브
   토큰을 무효화한다. FDR 은 KIS 와 무관하므로 장중에도 안전하다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.stock_market_writer import (  # noqa: E402
    fdr_df_to_market_rows,
    upsert_market_rows,
)
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)
MARKETS = ("KOSPI", "KOSDAQ")


def _default_listing(market: str):
    import FinanceDataReader as fdr
    return fdr.StockListing(market)


def collect_stock_market(listing_fn=None, conn=None) -> dict:
    """FDR 로 KOSPI/KOSDAQ 상장목록을 받아 stock_market 에 UPSERT.

    검증을 통과하지 못하면 **한 행도 쓰지 않고** RuntimeError 를 낸다.
    부분 수집으로 기존 매핑을 오염시키지 않기 위해서다.
    """
    fn = listing_fn or _default_listing

    collected = {}
    for market in MARKETS:
        rows = fdr_df_to_market_rows(market, fn(market))
        if not rows:
            raise RuntimeError(f"시장 매핑 수집 실패: {market} 0건 (기존 매핑 보존)")
        collected[market] = rows

    codes = {m: {r["stock_code"] for r in rs} for m, rs in collected.items()}
    overlap = codes["KOSPI"] & codes["KOSDAQ"]
    if overlap:
        raise RuntimeError(
            f"시장 매핑 교집합 {len(overlap)}건 — 라벨 모순이라 쓰지 않음: "
            f"{sorted(overlap)[:5]}"
        )

    if conn is not None:
        result = {m: upsert_market_rows(conn, rs) for m, rs in collected.items()}
    else:
        with KisDbConnection.get_connection() as c:
            result = {m: upsert_market_rows(c, rs) for m, rs in collected.items()}

    result["overlap"] = 0
    logger.info(
        f"시장 매핑 수집 완료: KOSPI {result['KOSPI']}종목 · KOSDAQ {result['KOSDAQ']}종목"
    )
    return result


if __name__ == "__main__":
    print(collect_stock_market())
