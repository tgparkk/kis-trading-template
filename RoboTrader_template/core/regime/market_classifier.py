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

해석 집계(2026-08-04 활성화 선행조건 — 양성 증거):
  auto 를 켠 뒤 "잘 돌아간다"의 근거가 「WARNING 이 안 뜬다」뿐이면 안 된다.
  **경보의 침묵은 증거가 아니다.** 그래서 해석 결과를 (전략, configured,
  resolved) 별로 세어 EOD 에 한 줄로 남긴다(`log_resolution_summary`).
  카운터는 호출부가 아니라 이 함수 **안에** 둔다 — 호출부가 2곳이라 안에 두면
  둘 다 자동으로 덮이고 유지보수 지점이 하나로 남는다.
"""
import time
from typing import Dict, List, Optional, Tuple

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


def resolve_regime_index(configured: str, stock_code: str, market_lookup=None,
                         strategy_name: str = None) -> str:
    """급락게이트에 넘길 지수 문자열을 정한다.

    configured != "auto"  → 그대로 통과 (기존 동작 100% 보존, 매핑 미조회)
    configured == "auto"  → 종목 소속 시장. 결측/불명이면 "both"

    "both" 는 KOSPI·KOSDAQ 을 모두 검사하므로 결측은 **보호 과잉 쪽으로만**
    실패한다. 무방비 구간이 생기지 않는다.

    Args:
        strategy_name: 집계 귀속용 전략 폴더키. **선택**(기본 None) — 기존
            호출부·테스트가 안 깨진다. 못 넘겨도 (configured, resolved) 축만으로
            핵심 질문(auto 가 실제로 시장별로 갈리는가)은 답해진다.

    반환값·의미는 집계 도입 전과 동일하다. 집계는 어떤 경우에도 반환에
    개입하지 않는다(`_count_resolution` 이 예외를 밖으로 내지 않는다).
    """
    cfg = configured or "both"
    resolved = cfg
    if cfg == "auto":
        lookup = market_lookup or get_stock_market
        try:
            market = lookup(stock_code)
        except Exception as e:
            logger.warning(f"[시장매핑] {stock_code} 조회 예외(both 폴백): {e}")
            market = None
        resolved = market if market in VALID_MARKETS else "both"

    _count_resolution(strategy_name, cfg, resolved)
    return resolved


# =========================================================================
# 해석 집계 — auto 활성화 판정용 양성 증거
# =========================================================================
# 이 블록이 답해야 하는 것:
#   - configured="auto" 인 건이 KOSPI/KOSDAQ/both 로 각각 몇 건 갈렸는가
#   - both 비율은 얼마인가 (높으면 매핑이 안 붙는다 = 보호 과잉이라 위험하진
#     않으나 **auto 가 사실상 안 도는 상태**다)
#   - non-auto 건은 configured == resolved 인가 (아니면 그 자체가 결함)
#
# 🔑 `both비율` 기대치 = **0.0%** (관리자 실측 2026-08-04)
#     오늘 유니버스(daily_prices, 구조적 종목 술어)  2,569종목
#     그중 stock_market 매핑됨                        2,569  (100%)
#     미매핑                                          0
#     오늘 실제 거래 19종목                            전부 매핑됨
#     stock_market 총                                 2,763
#   ⇒ 활성화 후 `both` 가 0 이 아니면 **그 자체가 신호**다. 셋 중 하나다:
#     ① 신규상장 직후 — 다음 EOD 수집 전이라 아직 매핑에 없다(정상, 소수)
#     ② 매핑 stale  — 수집기가 며칠 안 돌아 신규분이 누락됐다
#     ③ 조회 실패   — 위 `_remember_failure` WARNING 이 함께 떠 있어야 한다
#   ⚠️ 문턱이 아니라 **기대치**다. 임계값으로 굳혀 자동 차단하지 말 것 —
#      both 는 보호 과잉 쪽 실패라 그 자체로는 위험하지 않고, 여기서 원하는 건
#      「기대와 다르면 사람이 원인을 셋 중에서 고르게 하는 것」이다.
#
# ⚠️ 집계 단위는 「매수 평가」가 아니라 「해석 호출」이다. 매수 1건이 게이트를
#    통과하면 TradingContext.buy → TradingAnalyzer → TradingDecisionEngine 로
#    이어져 해석이 2회 일어난다(차단되면 1회). 건수를 평가 횟수로 읽지 말 것.

RESOLUTION_LOG_TAG = "[게이트지수해석]"

# 전략명 자리에 예상 밖 값(예: 종목코드)이 들어와도 메모리가 무한 증식하지
# 않게 상한을 둔다. 이 모듈은 이미 「종목코드를 키로 넣어 캐시를 오염시킨」
# 사고의 현장이다. 상한 초과분은 버리지 않고 넘침 버킷에 합산한다 —
# 총 건수를 잃으면 「집계가 멈춘 것」과 구분되지 않는다.
_MAX_RESOLUTION_KEYS = 200
# 🔴 넘침 시 뭉개는 축은 **전략명 하나뿐**이다. configured/resolved 까지 뭉개면
#    요약부의 `if cfg == "auto"` 분기를 절대 안 타서 **auto 해석이 non-auto 로
#    계상**된다 — 총 건수는 보존되므로 아무도 못 알아채고, 헤드라인만
#    `auto 0건` 이라고 거짓말한다(이 기능이 없애려던 바로 그 오독이다).
_OVERFLOW_STRATEGY = "(키상한초과)"
# configured 축까지 무한 증식하는 극단에 대비한 최종 버킷. 실전에서 configured
# 는 설정값(전략 수만큼)이라 유계지만, 카디널리티 상한이 **다른 인자가 얌전하다는
# 가정**에 의존하면 안 된다. 이 상수 덕에 키 수는 무조건 유계다.
_HARD_MAX_RESOLUTION_KEYS = _MAX_RESOLUTION_KEYS + 64
_OVERFLOW_KEY = (_OVERFLOW_STRATEGY, "(기타)", "(기타)")
# 키가 unhashable 이거나 dict 가 터진 경우의 최후 버킷. 축은 잃어도 총 건수는
# 지킨다 — 잃으면 「집계가 멈춘 것」과 구분되지 않는다.
_UNCOUNTABLE_KEY = ("(집계불가)", "(기타)", "(기타)")
_UNKNOWN_STRATEGY = "(미상)"

# (전략, configured, resolved) → 건수. 프로세스 메모리에만 산다.
_resolution_counts: Dict[Tuple[str, str, str], int] = {}
# 집계 창 시작 표기(문자열). None 이면 아직 한 건도 안 셌다.
_resolution_window_started: Optional[str] = None


def _wall_now() -> str:
    """집계 창 표기용 벽시계(KST). 테스트에서 교체 가능.

    캐시 TTL 의 `_now`(단조시계)와 용도가 다르다 — 저건 시간 간격 계산용이라
    벽시계를 쓰면 NTP 보정에 깨지고, 이건 사람이 읽을 시각이라 그 반대다.
    """
    from utils.korean_time import now_kst
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")


def _safe_wall_now() -> str:
    """시계가 터져도 요약 한 줄은 나와야 한다 — 시각만 포기한다."""
    try:
        return _wall_now()
    except Exception:  # noqa: BLE001
        return "?"


def _count_resolution(strategy_name, configured: str, resolved: str) -> None:
    """O(1) dict 증가. **호출당 로깅하지 않는다**(2,909회 = 2,909줄).

    🔴 어떤 예외도 밖으로 내지 않는다 — 집계 실패가 매수 판단을 죽이면
       주객이 전도된다. 증거를 남기려다 거래를 멈추는 건 최악이다.
    """
    global _resolution_window_started
    try:
        if _resolution_window_started is None:
            # 🔴 `_wall_now()` 를 그대로 쓰면 안 된다 — 시계가 터지면 바깥
            #    except 가 삼켜 **증가에 도달하지 못하고**, 그날 모든 호출이
            #    통째로 미집계된다. 반환값은 정상이라 아무도 모르고, EOD 는
            #    `총 0건` = 「auto 가 안 돈다」로 읽히는 **거짓 음성**이 된다.
            #    시각은 포기해도(`"?"`) 집계는 죽이지 않는다.
            _resolution_window_started = _safe_wall_now()
        key = (strategy_name or _UNKNOWN_STRATEGY, configured, resolved)
        if key not in _resolution_counts and len(_resolution_counts) >= _MAX_RESOLUTION_KEYS:
            # 전략 축만 뭉갠다 — configured/resolved 는 살려야 auto 가 auto 로 센다.
            key = (_OVERFLOW_STRATEGY, configured, resolved)
            if (key not in _resolution_counts
                    and len(_resolution_counts) >= _HARD_MAX_RESOLUTION_KEYS):
                key = _OVERFLOW_KEY
        _resolution_counts[key] = _resolution_counts.get(key, 0) + 1
    except Exception:  # noqa: BLE001 — 집계는 절대 매수 경로를 막지 않는다
        # 여기 오는 건 키가 unhashable 한 경우다(dict 자체가 터졌으면 아래도 터진다).
        # 축은 잃어도 총 건수는 지킨다 — 조용한 0건을 만들지 않는다.
        try:
            _resolution_counts[_UNCOUNTABLE_KEY] = (
                _resolution_counts.get(_UNCOUNTABLE_KEY, 0) + 1
            )
        except Exception:  # noqa: BLE001 — 두 번 실패하면 조용히 포기한다
            pass


def reset_resolution_counts() -> None:
    """집계와 창을 비운다. `reset_cache()`(매핑 캐시)와는 별개다.

    ⚠️ 매핑 캐시 리셋에 얹지 말 것 — `eod_collection` 이 수집 성공 직후
       `reset_cache()` 를 부르므로, 얹으면 그날 증거가 출력 전에 증발한다.
    """
    global _resolution_counts, _resolution_window_started
    _resolution_counts = {}
    _resolution_window_started = None


def get_resolution_counts() -> Dict[Tuple[str, str, str], int]:
    """집계 사본. 원본을 주면 호출측 변이가 핫패스 상태를 오염시킨다."""
    return dict(_resolution_counts)


def format_resolution_summary() -> List[Tuple[str, str]]:
    """(level, message) 목록. 순수 함수 — 리셋하지 않는다.

    건수가 0이어도 반드시 한 줄은 낸다. 「0건이라 안 찍음」은 「배선이 끊겨
    안 찍힘」과 로그상 구분되지 않는다.
    """
    counts = dict(_resolution_counts)
    auto_by_market = {"KOSPI": 0, "KOSDAQ": 0, "both": 0, "기타": 0}
    auto_total = 0
    non_auto_total = 0
    mismatched: List[Tuple[Tuple[str, str, str], int]] = []

    for key, n in counts.items():
        _strategy, cfg, res = key
        if cfg == "auto":
            auto_total += n
            auto_by_market[res if res in auto_by_market else "기타"] += n
        else:
            non_auto_total += n
            if cfg != res:
                mismatched.append((key, n))

    mismatch_total = sum(n for _, n in mismatched)
    if auto_total > 0:
        both_ratio = f"both비율 {auto_by_market['both'] / auto_total * 100:.1f}%"
    else:
        # auto 0건에 "0.0%" 를 찍으면 「매핑 완벽」으로 오독된다.
        both_ratio = "both비율 n/a(auto 0건)"
    etc = f"/기타 {auto_by_market['기타']}" if auto_by_market["기타"] else ""

    started = _resolution_window_started or "(집계 없음)"
    headline = (
        # 🔴 「무엇을 세는지」가 줄 안에 있어야 한다. 이 수는 평가 횟수도 매수
        #    건수도 아닌 **해석 호출** 수다(차단 1× + 통과매수 2×의 혼합량).
        #    라벨이 없으면 EOD 를 grep 하는 사람이 「매수 평가 2,909회」와
        #    나란히 놓고 반드시 오독한다 — 주석·docstring 은 로그에 안 찍힌다.
        f"{RESOLUTION_LOG_TAG} 총 {auto_total + non_auto_total}건"
        f"(해석호출 기준 · 통과매수는 2회 계상) · "
        f"auto {auto_total}건(KOSPI {auto_by_market['KOSPI']}"
        f"/KOSDAQ {auto_by_market['KOSDAQ']}"
        f"/both {auto_by_market['both']}{etc}, {both_ratio}) · "
        f"non-auto {non_auto_total}건(configured≠resolved {mismatch_total}건) · "
        f"전략 {len({k[0] for k in counts})}개 · "
        f"집계창 {started}~{_safe_wall_now()} "
        f"(프로세스 메모리 — 장중 재기동 시 0부터 다시 센다)"
    )

    lines: List[Tuple[str, str]] = [("info", headline)]
    for (strategy, cfg, res), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(("info", f"{RESOLUTION_LOG_TAG} 상세 {strategy}: {cfg}→{res} {n}건"))

    if mismatched:
        detail = ", ".join(f"{s} {c}→{r} {n}건" for (s, c, r), n in mismatched)
        lines.append(("warning", (
            f"{RESOLUTION_LOG_TAG} 🔴 non-auto 인데 configured≠resolved "
            f"{mismatch_total}건 — 해석 규칙 결함이다: {detail}"
        )))
    return lines


def log_resolution_summary(log=None) -> Dict[Tuple[str, str, str], int]:
    """EOD 1회 출력 + 리셋. 출력 직전 스냅샷을 반환한다(호출측 검증용).

    리셋을 **출력 시점**에 두는 이유: 소유자가 하나뿐이라 유지보수 지점이
    갈리지 않고, 출력된 줄이 정확히 창 [시작~지금] 과 일치한다. 거래일 시작에
    리셋하면 훅이 하나 더 늘고 순서 의존이 생긴다. 출력이 아예 안 도는 날은
    건수가 이월되지만, 창 시작 시각이 줄에 찍히므로 조용히 섞이지 않는다.
    """
    _log = log or logger
    snapshot = dict(_resolution_counts)
    try:
        for level, message in format_resolution_summary():
            getattr(_log, level, _log.info)(message)
    except Exception as e:  # noqa: BLE001 — EOD 흐름을 막지 않는다
        try:
            _log.error(f"{RESOLUTION_LOG_TAG} 집계 출력 실패: {e}")
        except Exception:  # noqa: BLE001
            pass
    finally:
        # 출력이 실패해도 리셋한다 — 안 그러면 실패한 날의 건수가 계속 이월돼
        # 다음날 줄이 조용히 부풀어 오른다.
        reset_resolution_counts()
    return snapshot
