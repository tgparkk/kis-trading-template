"""종목 소속 시장 조회 + 급락게이트 판정 지수 해석.

급락게이트(`check_market_direction`)는 캐시 키가 `regime_index` 문자열이라
종목코드를 넘기면 조용히 오염된다. 그래서 **호출 전에** 여기서 해석해
기존 시그니처가 받는 문자열로 바꿔 넘긴다.

⚠️ `stock_list.json`·`stock_sector` 의 market 필드는 전부 "KOSPI" 로 오염돼
   있으므로 폴백으로도 쓰지 않는다(2026-08-03 실측). 소스는 `stock_market` 뿐.
"""
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger(__name__)

VALID_MARKETS = ("KOSPI", "KOSDAQ")
_cache: Optional[dict] = None


def reset_cache() -> None:
    """캐시 무효화 — 매핑 재적재 후/테스트에서 사용."""
    global _cache
    _cache = None


def _load_cache() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    from db.kis_db_connection import KisDbConnection

    mapping = {}
    with KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, market FROM stock_market")
            for code, market in cur.fetchall():
                mapping[str(code)] = str(market)
    _cache = mapping
    logger.info(f"시장 매핑 캐시 로드: {len(mapping)}종목")
    return _cache


def get_stock_market(stock_code: str) -> Optional[str]:
    """종목의 소속 시장. 매핑이 없거나 조회 실패면 None."""
    try:
        return _load_cache().get(str(stock_code))
    except Exception as e:
        logger.warning(f"[시장매핑] 조회 실패(both 폴백): {e}")
        return None


def resolve_regime_index(configured: str, stock_code: str, market_lookup=None) -> str:
    """급락게이트에 넘길 지수 문자열을 정한다.

    configured != "auto"  → 그대로 통과 (기존 동작 100% 보존, 매핑 미조회)
    configured == "auto"  → 종목 소속 시장. 결측/불명이면 "both"

    "both" 는 KOSPI·KOSDAQ 을 모두 검사하므로 결측은 **보호 과잉 쪽으로만**
    실패한다. 무방비 구간이 생기지 않는다.
    """
    cfg = configured or "both"
    if cfg != "auto":
        return cfg

    lookup = market_lookup or get_stock_market
    try:
        market = lookup(stock_code)
    except Exception as e:
        logger.warning(f"[시장매핑] {stock_code} 조회 예외(both 폴백): {e}")
        return "both"

    return market if market in VALID_MARKETS else "both"
