"""종목 소속 시장 조회 + 급락게이트 판정 지수 해석.

급락게이트(`check_market_direction`)는 캐시 키가 `regime_index` 문자열이라
종목코드를 넘기면 조용히 오염된다. 그래서 **호출 전에** 여기서 해석해
기존 시그니처가 받는 문자열로 바꿔 넘긴다.

⚠️ `stock_list.json`·`stock_sector` 의 market 필드는 전부 "KOSPI" 로 오염돼
   있으므로 폴백으로도 쓰지 않는다(2026-08-03 실측). 소스는 `stock_market` 뿐.

캐시 수명 규약(2026-08-03 활성화 선행조건 ①②):
  - **성공 + 비어있지 않음** → 무기한 캐시. EOD 수집 성공 직후의
    `reset_cache()`(collectors/eod_collection.py:44-45)로만 갱신된다.
  - **성공했으나 0행** 또는 **조회 예외** → TTL 음성 캐시 + WARNING.
    TTL 만료 후 1회 재시도한다.

  음성 캐시가 닫는 것 2가지:
  ① 빈 매핑을 확정 캐시로 굳혀 테이블이 채워져도 영영 다시 안 읽던 문제.
     진짜 위험은 폴백 자체가 아니라(전부 "both" = 보호 과잉) **「auto 가
     정상 동작 중」과 「auto 가 켜졌는데 매핑이 비어 사실상 아무것도 안 하는
     중」이 로그로 구분되지 않던 것**이다.
  ② 조회 실패 시 캐시가 비어 **매수 평가마다** 동기 재접속하던 문제
     (2026-08-03 기준 평가 2,909회 × 이중 해석).

  ⚠️ 이 모듈의 어떤 실패 경로도 무방비를 만들지 않는다 —
     `resolve_regime_index` 가 전부 "both"(양쪽 지수 검사)로 흡수한다.
"""
import time
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger(__name__)

VALID_MARKETS = ("KOSPI", "KOSDAQ")

# 음성 캐시 TTL. 근거는 약하다(관리자 확정 필요) — 두 요구가 부딪히는 지점을
# 잡은 값이다: (a) 매수 평가 2,909회에 대해 DB 재접속을 장중 최대 ~78회로
# 묶고, (b) DB/테이블이 복구되면 사람 개입 없이 5분 안에 스스로 회복한다.
# 재시도 비용은 SELECT 1회(2,763행)뿐이라 더 짧아도 무해하지만, 그만큼
# 「auto 인데 매핑 0종목」WARNING 이 자주 찍힌다.
_NEGATIVE_TTL_SEC = 300

# 시계 주입 지점(테스트에서 교체). 벽시계가 아니라 단조시계를 쓴다 — NTP
# 보정이 뒤로 튀면 TTL 이 영영 안 끝날 수 있다.
_now = time.monotonic

# 확정 캐시. **비어있지 않은 성공 결과만** 담긴다(None 또는 비지 않은 dict).
_cache: Optional[dict] = None
# 음성 캐시 만료 시각(_now() 기준). 0.0 이면 음성 캐시 없음.
_negative_until: float = 0.0


def reset_cache() -> None:
    """캐시 무효화 — 매핑 재적재 후/테스트에서 사용.

    ⚠️ 음성 캐시도 **반드시 함께** 지운다. 남겨두면 EOD 수집이 성공했는데도
       TTL 이 끝날 때까지 빈 매핑을 계속 반환한다(「고쳤는데 안 고쳐진」 상태).
    """
    global _cache, _negative_until
    _cache = None
    _negative_until = 0.0


def _remember_failure(reason: str) -> None:
    """실패/공백을 TTL 동안 기억하고 WARNING 을 1회 남긴다.

    WARNING 은 여기서만 찍힌다 ⇒ 상태가 지속되는 동안 **TTL 단위로 정확히
    1회씩** 남는다. 매수 평가마다 찍으면 2,909줄이 되고, 기동 시 1줄만
    찍으면 몇 시간 뒤엔 아무 신호도 남지 않는다.
    """
    global _negative_until
    _negative_until = _now() + _NEGATIVE_TTL_SEC
    logger.warning(
        f"[시장매핑] {reason} — regime_index=\"auto\" 전략이 전 종목 both 폴백으로 "
        f"동작한다(시장별 급락판정 무효). {_NEGATIVE_TTL_SEC}초 후 1회 재시도."
    )


def _fetch_mapping() -> dict:
    """stock_market 전체를 dict 로 읽는다. 예외는 호출측이 처리한다."""
    from db.kis_db_connection import KisDbConnection

    mapping = {}
    with KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, market FROM stock_market")
            for code, market in cur.fetchall():
                mapping[str(code)] = str(market)
    return mapping


def _load_cache() -> dict:
    """매핑을 반환한다. 실패해도 예외를 내지 않고 빈 dict 를 준다."""
    global _cache
    if _cache is not None:
        return _cache
    if _now() < _negative_until:
        return {}  # 음성 캐시 유효 — DB 재접속하지 않는다

    try:
        mapping = _fetch_mapping()
    except Exception as e:  # noqa: BLE001 — 매수 경로를 죽이지 않는다
        _remember_failure(f"매핑 조회 실패({e})")
        return {}

    if not mapping:
        _remember_failure("stock_market 테이블이 비어 있음(0종목)")
        return {}

    _cache = mapping
    logger.info(f"시장 매핑 캐시 로드: {len(mapping)}종목")
    return _cache


def preload_market_mapping(auto_active: bool = False) -> int:
    """기동 시 1회 매핑 프리로드. 적재된 종목 수를 반환한다.

    Args:
        auto_active: `regime_index == "auto"` 인 전략이 하나라도 있는가.
            False 면 **DB 를 아예 건드리지 않는다** — non-auto 는
            `resolve_regime_index` 첫 줄에서 반환되어 매핑을 조회하지 않으므로
            프리로드도 무의미하고, 활성화 전에 무해해야 하기 때문이다.
    """
    if not auto_active:
        logger.info("[시장매핑] 프리로드 생략 — regime_index=\"auto\" 전략 없음")
        return 0

    size = len(_load_cache())
    if size == 0:
        # _remember_failure 가 이미 WARNING 을 냈지만, 그건 「조회가 실패/공백」
        # 이라는 사실뿐이다. 여기서는 **설정과 데이터가 어긋났다**는 별개
        # 사실을 기동 로그에 못박는다 — auto 를 켠 사람이 바로 알아야 한다.
        logger.warning(
            "[시장매핑] regime_index=\"auto\" 전략이 있는데 매핑이 0종목이다 — "
            "급락게이트가 전 종목 both 로 동작한다(보호 과잉, 무방비 아님). "
            "collectors.stock_market_collector 를 먼저 돌릴 것."
        )
    return size


def get_stock_market(stock_code: str) -> Optional[str]:
    """종목의 소속 시장. 매핑이 없거나 조회 실패면 None."""
    try:
        return _load_cache().get(str(stock_code))
    except Exception as e:  # noqa: BLE001 — _load_cache 는 이미 흡수하지만 2중 방어
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
