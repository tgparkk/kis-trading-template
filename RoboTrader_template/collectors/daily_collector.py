# collectors/daily_collector.py
"""일봉 수집 오케스트레이터 — KIS fetch → kis_template UPSERT → 파생 → adj.

usage:
  python -m collectors.daily_collector --limit 5            # 소수 dry-ish 수집
  python -m collectors.daily_collector                      # 전종목 수집

2026-08-17: `reconcile_daily`/`reconcile_verdict` 제거. 「새 DB vs 레거시
  robotrader_quant」 당일 대조였는데, 레거시는 2026-07-10 동결이라 이미 휴면이었고
  `KIS_DATA_SOURCE=legacy` 게이트 폐지 + `robotrader` DB 삭제로 도달 불가가 됐다.
  (기록 테이블 `collection_reconciliation` 자체는 과거 이력이므로 남겨 둔다.)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.daily_writer import parse_kis_daily_row, upsert_daily_rows  # noqa: E402
from collectors.daily_derived import update_returns_volatility  # noqa: E402
from collectors.split_factor_infer import infer_and_stamp_split_factors  # noqa: E402
from collectors.daily_adj import update_adj_factors  # noqa: E402
from collectors.corp_action_watch import scan_and_queue  # noqa: E402
from api import kis_market_api  # noqa: E402
from config.constants import SQL_STOCK_ONLY  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


_UNIVERSE_SQL = (
    "SELECT stock_code FROM stock_market WHERE " + SQL_STOCK_ONLY
    + " UNION "
    + "SELECT stock_code FROM daily_prices WHERE " + SQL_STOCK_ONLY
    + " ORDER BY 1"
)


def load_universe(conn) -> list:
    """수집 대상 = 상장목록(`stock_market`) ∪ 일봉 보유 종목(`daily_prices`).

    🔴 `daily_prices` 단독으로 읽으면 안 된다 — **자기충족적 순환**이 생긴다.
       일봉이 없는 종목은 대상에 못 들어가고, 대상이 아니니 계속 일봉이 안 생긴다.
       한 번 빠지면 스스로 복구되지 않는다.
       실측(2026-08-12): FDR 상장목록 2,764 중 **185종목이 일봉 0행**이었다.

    🔴 `stock_market` 단독으로도 안 된다 — 상장목록에서 빠졌지만 일봉이 있는 종목이
       **27개** 있다(상폐 등). 합집합이라야 어느 쪽도 잃지 않는다.

    ⚠️ 술어는 `config.constants.SQL_STOCK_ONLY`(숫자5+영숫자1) 하나만 쓴다.
       숫자 6자리로 좁히면 신형우선주 10종이 배제된다 — 그 결함으로 `00088K` 등이
       2024-02-29 이후 2년 5개월간 수집되지 않았다.

    ⚠️ 이 함수는 `collectors/foreign_flow_collector.py` 도 import 한다(수집기 2개 공유).
    """
    with conn.cursor() as cur:
        cur.execute(_UNIVERSE_SQL)
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
        # split_factor 스탬프는 반드시 update_adj_factors 이전 — 새로 확정된 권리락
        # 배수를 daily_adj 가 같은 밤에 adj_factor 로 반영하도록.
        stamped = infer_and_stamp_split_factors(conn)
        adj = update_adj_factors(conn)
        # 기업행위 미조정 이력 탐지 → 재수집 '대상 목록'만 적재(재수집 실행 안 함).
        # lookback_days=7 창으로는 정지 구간(중앙값 15봉)을 넘을 수 없어 증분 수집이
        # 과거를 영영 못 고친다 — corp_action_watch 주석 참조.
        # 예외 격리: 이 훅이 죽어도 일봉 수집은 이미 끝났으므로 EOD 를 막지 않는다.
        try:
            watch = scan_and_queue(conn)
        except Exception as e:  # noqa: BLE001 — 탐지 실패가 수집을 멈추면 안 된다
            logger.error("기업행위 탐지 훅 실패(수집은 정상 완료): %s", e)
            watch = {"error": str(e)}
    return {"codes": len(codes), "rows": total, "adj": adj,
            "split_factor_stamped": stamped, "corp_action_watch": watch}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--date", default=None)
    args = ap.parse_args()
    print(collect_daily(args.date, args.limit))
