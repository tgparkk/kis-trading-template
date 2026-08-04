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
    current_market_counts,
    fdr_df_to_market_rows,
    upsert_market_rows,
)
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)
MARKETS = ("KOSPI", "KOSDAQ")

# 규모 하한 — 새 수집분이 기존 행수의 이 비율 미만이면 한 행도 쓰지 않는다.
# ⚠️ 이 숫자의 근거는 확정적이지 않다(관리자 확정 필요). 근거로 삼은 실측:
#   · 이탈률 0.272%/월 (kis_template.daily_prices, 2026-07-01~10 대비
#     07-28~08-03 에 사라진 종목 7/2,578) ⇒ 연 환산 약 3.2%.
#     상장목록이 아니라 수집 유니버스 기준이라 상폐 외 필터 이탈까지 섞여
#     있어 순수 상폐율의 **상한**이다.
#   · 20% 감소는 그 상한으로도 6년 이상 걸린다 = 자연 감소로는 도달 불가.
# 반대쪽(너무 느슨한가)은 실측하지 못했다 — FDR 부분응답의 실제 분포 표본이
# 없다. 943건 중 754건까지는 여전히 통과하므로 부분응답 전부를 막지는 못한다.
MIN_SCALE_RATIO = 0.8


def _default_listing(market: str):
    import FinanceDataReader as fdr
    return fdr.StockListing(market)


def _check_scale_floor(existing: dict, collected: dict) -> None:
    """시장별 규모 하한 검증. 미달이면 RuntimeError(쓰기 전에 호출할 것).

    ⚠️ 하한은 **시장별**로 건다. 합계로 걸면 한쪽이 통째로 붕괴해도 다른 쪽이
       가려준다(KOSPI 100 + KOSDAQ 2,600 = 합계 97.7% 로 통과해버린다).

    기존 행수가 0인 시장은 최초 수집이므로 면제한다 — 아니면 첫 수집이
    영원히 불가능해진다.

    알려진 한계 2건(2026-08-04 검증에서 식별, 의도적으로 미수정):
    · **면제 조건의 사각지대** — 한 시장의 기존 행수가 0이면 그 시장은 규모를
      전혀 검사하지 않으므로, 부트스트랩이 한쪽만 커밋된 상태에서 다음 수집이
      돌면 빈 쪽은 20건짜리 부분응답도 그대로 통과한다. 현재는 양 시장 모두
      적재돼(KOSPI 943 · KOSDAQ 1,820) 도달 불가라 그대로 둔다.
    · **하한 래칭** — 기준값 `current_market_counts` 는 테이블 행수이고 UPSERT 는
      상폐 종목을 지우지 않는다(`stock_market_writer._UPSERT`). 즉 기준선은 단조
      증가하는 최고수위선인데 FDR 상장목록은 상폐만큼 줄어들어, 이탈률 3.2%/년
      기준 약 6년 뒤에는 정상 수집도 영구 거부된다. 다만 조용히 틀리는 게 아니라
      RuntimeError 로 매번 소리를 내므로 그때 기준을 다시 잡으면 된다.
    """
    shortfalls = []
    for market in MARKETS:
        prev = existing.get(market, 0)
        if prev <= 0:
            continue  # 최초 수집 — 비교 기준이 없다
        floor = prev * MIN_SCALE_RATIO
        n = len(collected[market])
        if n < floor:
            shortfalls.append(
                f"{market} {n}건 < 기존 {prev}건의 {MIN_SCALE_RATIO:.0%}({floor:.0f}건)"
            )
    if shortfalls:
        raise RuntimeError(
            "시장 매핑 규모 하한 미달 — 한 행도 쓰지 않음(기존 매핑 보존): "
            + " · ".join(shortfalls)
        )


def _validate_and_write(conn, collected: dict) -> dict:
    """규모 하한 검증 후 UPSERT. 검증은 반드시 첫 쓰기보다 먼저다."""
    _check_scale_floor(current_market_counts(conn), collected)
    return {m: upsert_market_rows(conn, rs) for m, rs in collected.items()}


def collect_stock_market(listing_fn=None, conn=None) -> dict:
    """FDR 로 KOSPI/KOSDAQ 상장목록을 받아 stock_market 에 UPSERT.

    검증을 통과하지 못하면 **한 행도 쓰지 않고** RuntimeError 를 낸다.
    부분 수집으로 기존 매핑을 오염시키지 않기 위해서다.

    검증 3층 — 0건 / 교집합 / 규모 하한. 앞 둘은 같은 실행 안에서만 판정하고,
    규모 하한만 **기존 적재분과 대조**한다. FDR 이 943건 대신 20건을 줘도
    0건이 아니라 성공으로 기록되고 그중 오라벨이 정상 라벨을 덮어쓰기 때문이다.
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
        result = _validate_and_write(conn, collected)
    else:
        with KisDbConnection.get_connection() as c:
            result = _validate_and_write(c, collected)

    result["overlap"] = 0
    logger.info(
        f"시장 매핑 수집 완료: KOSPI {result['KOSPI']}종목 · KOSDAQ {result['KOSDAQ']}종목"
    )
    return result


if __name__ == "__main__":
    print(collect_stock_market())
