"""
봇 초기화 모듈
시스템 초기화 및 설정 관련 로직을 담당합니다.
"""
import json
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from utils.logger import setup_logger
from utils.korean_time import now_kst, get_market_status
from utils.price_utils import check_duplicate_process, load_config
from config.market_hours import MarketHours
from config.constants import VIRTUAL_CAPITAL_PER_STRATEGY

if TYPE_CHECKING:
    from main import DayTradingBot


# =========================================================================
# 설정파일 ↔ 전략 인스턴스 `regime_index` 대조 (2026-08-04, 활성화 선행조건 A′)
# =========================================================================
# 닫으려는 결함은 **자기참조**다. auto 활성 여부를 말하는 신호가 둘 있는데
# 둘 다 같은 곳(전략 인스턴스 속성)을 읽는다:
#   · 기동 로그  `_preload_market_mapping` 의 `auto_active`
#   · EOD 카운터 `market_classifier.resolve_regime_index(configured=...)`
#
# 그런데 인스턴스에 값이 심기는 곳은 **조건부**다
# (strategies/config.py:449-450 — `if "regime_index" in spec`).
# 설정파일이 `"auto"` 라고 선언했는데 그 spec 이 인스턴스에 안 닿으면
# 인스턴스는 클래스 기본값 `"both"` 를 조용히 유지하고,
# 🔴 **두 신호가 나란히 "non-auto" 라고 일치하면서 함께 틀린다.**
#
# 이 프로젝트가 반복해서 데인 클래스다 — 「경보가 조용함」은 증거가 아니다.
# 유일한 탈출구는 설정파일을 **독립적으로 읽어** 대조하는 것뿐이다.
#
# -------------------------------------------------------------------------
# ⚠️ **이 검사의 실제 사정거리** (2026-08-04 정정)
# -------------------------------------------------------------------------
# 이전 판본은 대상 실패모드로 `JSON 구조 변경` 을 그냥 나열했는데, 실제로는
# **조건부로만** 잡는다. 주석이 구현보다 넓게 적혀 있으면 그 주석 자체가 또
# 하나의 거짓 안심이다 — 「고쳤다고 적은 것」과 「고친 것」의 차이다. 그래서
# 무엇을 잡고 무엇을 못 잡는지 여기에 정확히 적는다.
#
#   ✅ 전략명 불일치 / `enabled:true` 인데 인스턴스 없음  → 「로드실패」 WARNING
#   ✅ 선언값 != 인스턴스 실효값                          → 「미반영」 WARNING
#   ✅ 선언·실효가 **나란히 같은 오타**거나 JSON `null`   → 「인식불가」 WARNING
#   ✅ 설정파일 부재 · JSON 파손                          → 대조 실패 WARNING
#        (`read_declared_strategy_specs` 가 예외를 **일부러 밖으로 낸다** —
#         삼키면 부재·파손이 🟡레거시 INFO 로 둔갑한다)
#   ✅ 항목이 dict 가 아니거나 name 부재                  → 「구조이상」 WARNING
#
#   🟡 JSON 구조 변경(`strategies` 배열 자체가 사라짐) → **조건부**다.
#      배열이 없으면 선언값이 통째로 없어 **대조가 성립하지 않는다**. 그래서
#      `결함 0건`(= 「대조했더니 결함이 없다」로 읽힌다) 대신 `결함 판정불가` 를
#      찍고, 아래 둘 중 하나라도 걸리면 WARNING 으로 승격한다:
#        · 조건A  로더가 파일을 **정상 파싱**했는데(load_ok=True) 배열이 없다
#        · 조건B  전략 인스턴스가 **2개 이상**인데 배열이 없다
#                 (다중 전략은 그 배열에서만 나온다 — main.py:166-186)
#      둘 다 아니면 INFO 로 남긴다. 진짜 레거시 단일전략 배포에서 매 기동
#      경보를 내면 **사람이 무시하게 되고 그게 가드를 무력화**하기 때문이다.
#      ⚠️ 이 WARNING 은 「구조가 깨졌다」는 단정이 아니라 「배열을 못 읽었다」는
#         사실 통보다 — 판정 재료(읽은 파일·load_ok·인스턴스 수와 이름)를 함께
#         찍어 읽는 사람이 결정하게 한다.
#
#   ❌ `enabled:false` 전략의 선언값 오타는 **판정 대상이 아니다**. 로더가
#      건너뛰므로 게이트에 도달할 수 없다. 그 전략을 켜는 순간(= 문제가 실제로
#      생기는 순간) 다음 기동에서 잡힌다 — 한 기동 늦는 것을 감수한 설계다.
#   ❌ 전략 클래스 로드가 왜 실패했는지(모듈 부재·import 오류 등)는 구분하지
#      않는다. 인스턴스가 없다는 사실만 「로드실패」로 드러낸다.
CONFIG_CROSSCHECK_LOG_TAG = "[게이트설정대조]"

# `BaseStrategy.regime_index` 클래스 기본값(strategies/base.py:322)과 같아야 한다.
# 여기서 다른 값을 쓰면 「파일 미선언」건의 실효값을 잘못 보고한다.
_CLASS_DEFAULT_REGIME_INDEX = "both"

# 하류 소비자가 **실제로 분기하는** 값의 전체 집합. 하나라도 이 밖이면 「인식 불가」다.
#
# 🔴 근거는 소비자 코드를 직접 읽어 확정했다(2026-08-04). 값을 아는 곳은 둘이고
#    서로 다른 값을 안다 — 그래서 이 집합은 두 곳의 **합집합**이다:
#   · "auto"                          core/regime/market_classifier.py:177
#       `if cfg == "auto":` — 종목 소속 시장으로 해석한다. 급락게이트는 이 값을
#       모른다(해석이 게이트 호출 **전에** 끝나기 때문).
#   · "none"                          core/trading_decision_engine.py:153
#       `if idx == "none": return False, ""` — 급락게이트 면제.
#   · "both"/"KOSPI"/"KOSDAQ"         core/trading_decision_engine.py:158
#       `if idx not in ("both","KOSPI","KOSDAQ"):` — 이 밖이면 WARNING + both 폴백.
#       "both" 는 strategies/base.py:322 의 클래스 기본값이기도 하다.
#
# 값이 인스턴스에 심기는 곳은 strategies/config.py:450 `str(spec["regime_index"])`
# 하나뿐이다 ⇒ JSON `null` 은 문자열 `"None"` 으로 심긴다. 선언측도 같은 식으로
# 문자열화되므로 **양쪽이 일치해 정상으로 보인다** — 이 집합 검사가 그걸 잡는다.
#
# ⚠️ 값을 늘리려면 위 소비자 중 어디가 그 값을 분기하는지 먼저 확인할 것.
#    여기에만 추가하면 「대조는 통과하는데 게이트는 모르는 값」이 생긴다.
KNOWN_REGIME_INDEX_VALUES = ("auto", "KOSPI", "KOSDAQ", "both", "none")


def effective_regime_index(strategy) -> str:
    """전략 인스턴스에 **실제로 심긴** 판정 지수.

    속성 부재·None·"" 를 전부 클래스 기본값으로 흡수한다. 이 식이 곧
    `_preload_market_mapping` 의 auto 판정식이다 — 두 곳이 갈리면
    「프리로드는 돌았는데 대조는 안 돌았다」 같은 설명 불가능한 상태가 생기므로
    **함수 하나만 둔다**.
    """
    return (getattr(strategy, "regime_index", _CLASS_DEFAULT_REGIME_INDEX)
            or _CLASS_DEFAULT_REGIME_INDEX)


def compute_effective_auto_count(strategies) -> int:
    """실효 기준 auto 전략 수(= 인스턴스에 진짜 심긴 값 기준)."""
    return sum(1 for s in (strategies or {}).values()
               if effective_regime_index(s) == "auto")


def read_declared_strategy_specs() -> Tuple[Optional[List[Any]], str, Optional[bool]]:
    """**로더가 실제로 읽은** trading_config.json 을 다시 읽어 선언값을 얻는다.

    Returns:
        (strategies 배열 또는 None, 출처 표기 문자열, 로더 파싱 성공 여부)

        세 번째 값 `load_ok` 는 `True`/`False`/`None`(= 로더 미실행이라 말할 수
        없음)이다. 🔴 이 값을 호출측이 settings 에서 **따로 읽으면 안 된다** —
        「어느 파일을 봤는가」와 「그 파일 파싱이 성공했는가」가 갈리는 순간
        이 검사가 정확히 자기가 잡으려던 종류의 거짓말을 하게 된다. 그래서
        같은 자리에서 함께 확정해 함께 돌려준다.

    🔴 경로를 새로 하드코딩하면 안 된다. 로더와 **다른 파일**을 대조하면 검사가
       거짓 경보나 거짓 안심을 내고, 그 순간 이 기능은 무의미해진다. 그래서
       `config.settings.load_trading_config()` 이 열었던 경로를 그대로 따라간다
       (`LAST_LOADED_TRADING_CONFIG_PATH`). 이 경로는 인스턴스 분리
       (`KIS_INSTANCE_DIR`)까지 이미 반영된 값이라 별도 처리가 필요 없다.

    로더가 아직 안 돈 경우에만 모듈 상수로 폴백하고, **어느 쪽을 썼는지 출처를
    로그에 밝힌다** — 거짓 경보가 떴을 때 원인을 가릴 수 있어야 한다.
    """
    from config import settings

    recorded = getattr(settings, "LAST_LOADED_TRADING_CONFIG_PATH", None)
    if recorded is not None:
        path = Path(recorded)
        load_ok = bool(getattr(settings, "LAST_TRADING_CONFIG_LOAD_OK", False))
        # load_ok=False = 파일은 지정됐는데 못 읽었다 ⇒ 로더는 기본 설정
        # (strategies 없음)으로 갔다. 아래 대조가 전건 "로드실패"로 드러낸다.
        origin = f"로더기록·load_ok={load_ok}"
    else:
        path = Path(settings.TRADING_CONFIG_FILE)
        # 로더가 안 돌았다 = 파싱 성공 여부를 말할 수 없다. False 로 뭉개면
        # 「파싱 실패」와 「미실행」이 섞여 조건A 판정이 조용히 틀어진다.
        load_ok = None
        origin = "모듈상수(로더 미실행)"

    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    specs = raw.get('strategies') if isinstance(raw, dict) else None
    return specs, f"{path} ({origin})", load_ok


def format_regime_config_crosscheck(declared_specs, strategies, source: str,
                                    load_ok: Optional[bool] = None
                                    ) -> List[Tuple[str, str]]:
    """선언값 ↔ 실효값 대조 결과를 (level, message) 목록으로. 순수 함수.

    여섯 갈래:
      🟢 정상          선언 == 실효 **이고 값이 알려진 값**
      🔴 미반영        선언 != 실효 — **이게 잡으려는 결함이다**
      🔴 로드실패      파일이 enabled 로 선언했는데 인스턴스가 없다
      🔴 인식불가      선언·실효 중 하나라도 `KNOWN_REGIME_INDEX_VALUES` 밖 (F1)
      🟡 파일미선언    파일에 키가 없어 클래스 기본값 유지(의도된 하위호환)
      🟡 인스턴스에만  인스턴스에 있는데 파일엔 없다(레거시 단일전략 경로 등)

    🔴 **인식불가가 없으면 이 검사는 거짓 안심의 자리만 옮긴다**(F1).
       활성화 행위 자체가 바로 이 값을 편집하는 것이므로, 활성화가 만들 가장
       흔한 실수(대소문자 오타 `"Auto"`·JSON `null`)는 **선언과 실효가 나란히
       같은 오타**가 되어 「정상」으로 계상된다. 하류 안전망이 비대칭이라
       이게 치명적이다 — 급락게이트는 WARNING + both 폴백(보호 과잉, 안전)이지만
       일봉 국면게이트(trading_decision_engine.py:234)는 **무음으로 KOSPI 를
       강제**한다.

    ⚠️ 인식불가 판정 범위는 **enabled 선언값 + 전 인스턴스 실효값**이다.
       `enabled:false` 의 선언값은 게이트에 도달할 수 없으므로 제외한다 —
       활성화하는 순간(= 문제가 실제로 생기는 순간) 다음 기동에서 잡힌다.

    ⚠️ `enabled:false` 는 로더가 **의도적으로** 건너뛴다(config.py:443-444).
       이걸 로드실패로 세면 비활성 전략을 둘 때마다 WARNING 이 떠서 진짜
       결함이 소음에 묻힌다 — 별도 정보 버킷으로 분리한다.

    🔴 헤드라인은 **선언 기준 auto 수와 실효 기준 auto 수를 둘 다** 찍는다.
       하나만 찍으면 자기참조 문제가 그대로 남는다. 두 수가 다르면 그 사실
       자체가 결함이므로 별도 WARNING 을 낸다.

    🔴 선언을 **못 읽었으면**(`declared_specs is None`) `결함 0건` 을 찍지
       않는다(F2). 0 은 「대조했더니 결함이 없다」로 읽히는데 실제로는
       「대조를 못 했다」다 — 검증자 실측에서 `strategies` 키 이름만 바꾸자
       봇이 8전략에서 레거시 1전략으로 추락했는데도 `결함 0건 · WARNING 0건`
       이 찍혔다. 「경보가 조용함」은 증거가 아니다.
       거기에 더해 `load_ok=True`(조건A) 또는 인스턴스 2개 이상(조건B)이면
       WARNING 으로 승격한다 — 상세 근거는 모듈 상단 「실제 사정거리」 참조.

    ⚠️ `결함 N건` 의 정의: **버킷 합**이다. 한 전략이 두 버킷에 걸리면 2로
       센다(예: 선언 `"Auto"` 가 인스턴스에 안 닿으면 미반영 1 + 인식불가 1).
       전략 수가 아니라 결함 이벤트 수이며, 내역이 괄호 안에 함께 찍힌다.

    건수가 전부 0이어도 반드시 한 줄은 낸다 — 「0건이라 안 찍음」은 「배선이
    끊겨 안 찍힘」과 로그상 구분되지 않는다. 활성화 전 현행 설정에서는
    `선언 0 · 실효 0 · 결함 0(…/인식불가 0) · 정상 8` 이 나오며, **그 줄 자체가
    「검사가 동작한다」는 증거**다.
    """
    strategies = strategies or {}
    effective: Dict[str, str] = {
        name: effective_regime_index(s) for name, s in strategies.items()
    }
    effective_auto = sum(1 for v in effective.values() if v == "auto")

    ok: List[str] = []
    unplanted: List[Tuple[str, str, str]] = []   # (전략, 선언, 실효)
    not_loaded: List[Tuple[str, Optional[str]]] = []
    undeclared: List[Tuple[str, str]] = []
    disabled: List[Tuple[str, Optional[str]]] = []
    declared_enabled: List[Tuple[str, str]] = []  # (전략, 선언값) — enabled·키 있음만
    malformed = 0
    declared_auto = 0
    declared_names = set()

    legacy = declared_specs is None
    for spec in (declared_specs or []):
        if not isinstance(spec, dict):
            malformed += 1
            continue
        name = spec.get('name')
        if not isinstance(name, str) or not name:
            malformed += 1
            continue

        declared_value = (str(spec['regime_index'])
                          if 'regime_index' in spec else None)

        if not spec.get('enabled', True):
            # 로더가 건너뛰므로 인스턴스가 없는 것이 정상이다.
            disabled.append((name, declared_value))
            continue

        declared_names.add(name)
        if declared_value is not None:
            declared_enabled.append((name, declared_value))
        if declared_value == "auto":
            declared_auto += 1

        if name not in effective:
            not_loaded.append((name, declared_value))
        elif declared_value is None:
            undeclared.append((name, effective[name]))
        elif declared_value == effective[name]:
            ok.append(name)
        else:
            unplanted.append((name, declared_value, effective[name]))

    # ---- 인식 불가 값 (F1) ----
    # 전략 단위로 모은다 — 선언·실효가 **같은 오타로 나란히 틀린** 게 정확히
    # 기본 실패모드라, 건마다 세면 한 전략이 2건으로 부풀어 오독을 부른다.
    unknown_sources: Dict[str, List[str]] = {}

    def _flag_unknown(name: str, origin: str, value: str) -> None:
        if value in KNOWN_REGIME_INDEX_VALUES:
            return
        unknown_sources.setdefault(name, []).append(f'{origin} "{value}"')

    for name, value in declared_enabled:
        _flag_unknown(name, "파일", value)
    for name, value in effective.items():
        _flag_unknown(name, "인스턴스", value)

    # 🔴 인식 불가 값을 「정상」으로 셀 수 없다 — 그 숫자가 곧 거짓 안심이다.
    ok = [n for n in ok if n not in unknown_sources]

    instance_only = sorted(set(effective) - declared_names)
    defects = len(unplanted) + len(not_loaded) + malformed + len(unknown_sources)
    legacy_note = (" · 🟡레거시(파일에 strategies 배열 없음 = 선언 없음)"
                   if legacy else "")

    if legacy:
        # F2: 대조를 **못 했다**. 0 을 찍으면 「결함이 없다」로 읽힌다.
        defect_text = (f"결함 판정불가(선언 없음 — strategies 배열을 못 읽었다) · "
                       f"인스턴스측 인식불가 {len(unknown_sources)}건")
    else:
        defect_text = (f"결함 {defects}건(미반영 {len(unplanted)}"
                       f"/로드실패 {len(not_loaded)}/구조이상 {malformed}"
                       f"/인식불가 {len(unknown_sources)})")

    headline = (
        f"{CONFIG_CROSSCHECK_LOG_TAG} "
        f"선언 auto {declared_auto}건 · 실효 auto {effective_auto}건 · "
        f"{defect_text} · "
        f"정상 {len(ok)}건 · 파일미선언 {len(undeclared)}건 · "
        f"비활성 {len(disabled)}건 · 인스턴스에만 {len(instance_only)}건"
        f"{legacy_note} · 파일 {source}"
    )
    lines: List[Tuple[str, str]] = [("info", headline)]

    if declared_auto != effective_auto:
        lines.append(("warning", (
            f"{CONFIG_CROSSCHECK_LOG_TAG} 🔴 선언 auto {declared_auto}건 ≠ "
            f"실효 auto {effective_auto}건 — 설정이 전략 인스턴스에 닿지 않았다. "
            f"기동 로그의 auto_active 와 EOD 해석 카운터는 **둘 다 인스턴스를 "
            f"읽으므로 이 상태에서 나란히 침묵한다**(판별력 0)."
        )))

    if unplanted:
        detail = ", ".join(f"{n}: 파일 \"{d}\" → 인스턴스 \"{e}\""
                           for n, d, e in unplanted)
        lines.append(("warning", (
            f"{CONFIG_CROSSCHECK_LOG_TAG} 🔴 선언값 미반영 {len(unplanted)}건 — "
            f"{detail}"
        )))

    if not_loaded:
        detail = ", ".join(f"{n}(선언 \"{d}\")" if d else n
                           for n, d in not_loaded)
        lines.append(("warning", (
            f"{CONFIG_CROSSCHECK_LOG_TAG} 🔴 파일이 enabled 로 선언했는데 전략 "
            f"인스턴스가 없다 {len(not_loaded)}건 = 로드 실패 — {detail}"
        )))

    if malformed:
        lines.append(("warning", (
            f"{CONFIG_CROSSCHECK_LOG_TAG} 🔴 strategies 항목 구조 이상 "
            f"{malformed}건(dict 아님 또는 name 부재) — 조용히 무시되면 그 전략의 "
            f"설정 전체가 사라진다."
        )))

    if unknown_sources:
        detail = ", ".join(f"{n}({' · '.join(v)})"
                           for n, v in unknown_sources.items())
        lines.append(("warning", (
            f"{CONFIG_CROSSCHECK_LOG_TAG} 🔴 인식 불가 regime_index "
            f"{len(unknown_sources)}건 — 알려진 값 "
            f"{list(KNOWN_REGIME_INDEX_VALUES)} 밖이다: {detail}. "
            f"하류 처리가 **비대칭**이라 조치가 갈린다 — 급락게이트"
            f"(check_market_direction)는 WARNING 을 남기고 \"both\" 로 폴백하지만"
            f"(양쪽 지수 검사 = 보호 과잉, 무방비 아님), 일봉 국면게이트"
            f"(check_regime_gate, core/trading_decision_engine.py:234)는 **무음으로 "
            f"KOSPI 를 강제**한다 ⇒ regime_gate != \"none\" 전략이면 일봉 판정축이 "
            f"조용히 KOSPI 로 고정된다. 대소문자 오타(\"Auto\" != \"auto\")와 JSON "
            f"null(로더가 strategies/config.py:450 에서 문자열 \"None\" 을 심는다)이 "
            f"여기서 잡힌다."
        )))

    if legacy:
        # 🔴 두 조건은 **서로 다른 상황**을 잡는다. 무조건 승격하면 진짜 레거시
        #    단일전략 배포에서 매 기동 경보가 되고, 오경보가 잦으면 사람이 무시하게
        #    되어 가드가 무력화된다 — 그래서 좁힌다. 어느 조건이 걸렸는지는 반드시
        #    구분되게 찍는다(같은 문구로 뭉치면 원인 추적이 불가능해진다).
        triggered = []
        if load_ok is True:
            triggered.append(
                "조건A(로더가 파일을 정상 파싱했는데 strategies 배열이 없다)")
        if len(instance_only) >= 2:
            triggered.append(
                f"조건B(전략 인스턴스가 {len(instance_only)}개 — 다중 전략은 "
                f"strategies 배열에서만 나온다, main.py:166-186. "
                f"이 조건은 「대조가 로더와 다른 파일을 보고 있다」도 함께 잡는다)")

        if triggered:
            lines.append(("warning", (
                f"{CONFIG_CROSSCHECK_LOG_TAG} 🔴 선언을 못 읽었다 "
                f"[{' + '.join(triggered)}] — ⚠️ **단정이 아니다**: 의도된 레거시 "
                f"단일전략 배포라면 무해하고, 아니라면 다중 전략 설정이 로더에게 "
                f"보이지 않아 전략이 {len(effective)}개로 추락한 상태다(이 경우 "
                f"대조 자체가 무력화돼 auto 활성 여부를 말할 수 없다). "
                f"판정 재료 — 읽은 파일 {source} · 로더 파싱 성공 {load_ok} · "
                f"전략 인스턴스 {len(effective)}개 {sorted(effective)}."
            )))

    if undeclared:
        detail = ", ".join(f"{n}→\"{e}\"" for n, e in undeclared)
        lines.append(("info", (
            f"{CONFIG_CROSSCHECK_LOG_TAG} 🟡 파일 미선언 {len(undeclared)}건 "
            f"(클래스 기본값 유지 — 하위호환): {detail}"
        )))

    if disabled:
        auto_disabled = [n for n, d in disabled if d == "auto"]
        extra = (f" ⚠️ 이 중 \"auto\" 선언 {len(auto_disabled)}건은 "
                 f"전략 자체가 꺼져 있어 효력이 없다: {auto_disabled}"
                 if auto_disabled else "")
        lines.append(("info", (
            f"{CONFIG_CROSSCHECK_LOG_TAG} 🟡 비활성(enabled:false) "
            f"{len(disabled)}건 — 로더가 건너뛰므로 인스턴스 부재가 정상: "
            f"{[n for n, _ in disabled]}{extra}"
        )))

    if instance_only:
        lines.append(("info", (
            f"{CONFIG_CROSSCHECK_LOG_TAG} 🟡 인스턴스에만 존재 "
            f"{len(instance_only)}건(파일 미선언 경로 — 레거시 단일전략 등): "
            f"{instance_only}"
        )))

    return lines


class BotInitializer:
    """봇 초기화 담당 클래스"""

    def __init__(self, bot: 'DayTradingBot') -> None:
        self.bot = bot
        self.logger = setup_logger(__name__)

    def setup_signal_handlers(self) -> None:
        """시그널 핸들러 등록"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame) -> None:
        """시그널 핸들러 (Ctrl+C 등)"""
        self.logger.info(f"종료 신호 수신: {signum}")
        self.bot.is_running = False

    def check_duplicate_process(self, pid_file: Path) -> None:
        """프로세스 중복 실행 방지"""
        check_duplicate_process(str(pid_file))

    def load_config(self) -> None:
        """설정 로드"""
        return load_config()

    def log_rebalancing_mode(self, config) -> None:
        """리밸런싱 모드 상태 로깅"""
        if getattr(config, 'rebalancing_mode', False):
            self.logger.info("리밸런싱 모드 활성화: 09:05 리밸런싱으로 매수, 장중 손절/익절 매도 판단 활성화")
        else:
            self.logger.info("하이브리드 모드: 리밸런싱 + 실시간 매수 판단 병행")

    def _allocate_strategy_capital(self) -> None:
        """가상매매 모드에서 각 전략 폴더키에 독립 초기자본을 할당.

        VirtualTradingManager 전략별 자금 격리 원장을 활성화한다.
        - 키는 self.bot.strategies의 폴더키 — TradingContext._strategy_key와 동일하게 매칭됨.
        - 할당이 1건이라도 있으면 집계 virtual_balance = 전략 잔고 합계로 동기화됨.
        - 실전 모드이거나 전략이 없으면 자금 할당은 하지 않음(레거시 단일 잔고 보존).

        부수 책임(2026-07-29): 같은 순회에서 읽은 전략별 K를 합산해
        fund_manager.max_position_count를 정정한다(_apply_total_k_position_limit).
        자금 할당은 가상 전용이지만 **한도 정정은 모드 무관**이므로, 순회를 가상
        게이트 바깥으로 끌어내고 할당 호출만 게이트 안에 둔다.
        """
        try:
            strategies = getattr(self.bot, 'strategies', None) or {}
            engine = getattr(self.bot, 'decision_engine', None)
            vtm = getattr(engine, 'virtual_trading', None)
            is_virtual = getattr(engine, 'is_virtual_mode', False)
            # 자금 할당 가능 여부(= 기존 조기 return 조건들과 동치).
            can_allocate = bool(
                strategies and is_virtual and vtm is not None
                and hasattr(vtm, 'allocate_strategy_capital')
            )

            k_by_strategy: dict = {}   # 유효 K가 확인된 전략만
            unknown_k: list = []       # K 미상 — 합계에서 제외(조용히 0으로 세지 않음)

            for key, strat in strategies.items():
                # 종목당 기본 예산 = 초기자본/K 균등분할 (A안, 2026-06-11 결재 —
                # 백테스트 균등복리 K분할 정합. Elder K20→50만/종목 등).
                # K는 yaml config에서 직접 읽는다 — _max_positions 속성은 각 전략
                # on_init()(bot.initialize 시점)에서야 설정되므로 여기(__init__)서는
                # 항상 부재 → K분할 전면 미적용이었음 (2026-06-12 라이브 확인).
                risk = ((getattr(strat, "config", None) or {})
                        .get("risk_management", {}) or {})
                k = risk.get("max_positions") or getattr(strat, '_max_positions', None)

                # 같은 K를 한도 합산에도 재사용 (별도 순회를 만들지 않는다).
                try:
                    k_int = int(k)
                except (TypeError, ValueError):
                    k_int = 0
                if k_int > 0:
                    k_by_strategy[key] = k_int
                else:
                    unknown_k.append(key)

                if not can_allocate:
                    continue

                vtm.allocate_strategy_capital(
                    key, VIRTUAL_CAPITAL_PER_STRATEGY, max_positions=k)
                # 전략별 종목당 투자금액 (yaml risk_management.paper_investment_per_stock).
                # 명시 시 K분할 기본값을 덮어씀 — 사이징 시나리오 검증값(예: deep_mr_dev20).
                try:
                    per_stock = ((getattr(strat, "config", None) or {})
                                 .get("risk_management", {})
                                 .get("paper_investment_per_stock"))
                    if per_stock and hasattr(vtm, "set_strategy_investment_amount"):
                        vtm.set_strategy_investment_amount(key, float(per_stock))
                except Exception as e:
                    self.logger.warning(f"전략 종목당 투자금액 설정 실패({key}): {e}")

            if can_allocate:
                self.logger.info(
                    f"전략별 가상 자금 할당 완료: {list(strategies.keys())} "
                    f"(전략당 {VIRTUAL_CAPITAL_PER_STRATEGY:,.0f}원, "
                    f"총 {vtm.get_virtual_balance():,.0f}원)"
                )
        except Exception as e:
            self.logger.warning(f"전략별 가상 자금 할당 실패 (단일 잔고 사용): {e}")
            return

        self._apply_total_k_position_limit(k_by_strategy, unknown_k)

    def _apply_total_k_position_limit(self, k_by_strategy: dict,
                                      unknown_k: list) -> None:
        """전략별 K 합계로 fund_manager.max_position_count를 정정 (2026-07-29).

        왜 필요한가 — main.py는 ``FundManager(max_daily_loss_ratio=...)``로만 생성해
        동시 보유 한도가 기본값 **20**이었다. 이 20은 **단일전략 시절의 레거시**다.
        현재는 8전략 독립 운영이라 전략별 K 합계가 58이고, 07-29 실보유는 40종목
        (한도 2배)이었다. 실전 전환 시 20에서 매수가 막히는 사고를 예방하는 것이 목적.

        ⚠️ 이 값을 페이퍼 매수 경로에 결선하지 말 것 — 한도를 실제로 강제하는
        fund_manager.can_add_position()은 core/trading/order_execution.py의 **실주문
        경로에만** 결선돼 있고, 그대로 두는 것이 사장님 결정(2026-07-29)이다. 전역
        한도는 2026-06-16 채택한 *전략별 완전독립 포지션(B안)* 설계와 충돌한다 —
        먼저 채운 전략이 나머지 전략을 굶기는 교차 간섭이 생긴다. 여기서 하는 일은
        **한도값 정정뿐이며 페이퍼 동작은 완전 불변**이다.

        가드:
        - K 미상 전략은 합계에서 제외하고 WARNING (조용히 0으로 세지 않는다).
        - max(기존값, ΣK) — 바닥을 둬서 어떤 경우에도 한도가 좁아지지 않게 한다.
          이 작업은 완화 방향이지 조임 방향이 아니다.
        - 전략이 없거나 ΣK<=0이면 기존값 유지 + WARNING.
        - 가상/실전 모드 무관 적용(실전에서 정확한 값이 필요한 게 목적).
        """
        try:
            fund_manager = getattr(self.bot, 'fund_manager', None)
            if fund_manager is None:
                self.logger.warning(
                    "동시 보유 한도 ΣK 정정 스킵: fund_manager 미연결")
                return

            if unknown_k:
                self.logger.warning(
                    f"동시 보유 한도 ΣK 합산에서 제외 (K 미상 = "
                    f"risk_management.max_positions·_max_positions 모두 부재/무효): "
                    f"{unknown_k}"
                )

            total_k = sum(k_by_strategy.values())
            current = int(getattr(fund_manager, 'max_position_count', 0) or 0)

            if total_k <= 0:
                self.logger.warning(
                    f"동시 보유 한도 ΣK 산출 불가 (유효 K 전략 0개) — "
                    f"기존 한도 {current}종목 유지"
                )
                return

            new_limit = max(current, total_k)
            breakdown = ", ".join(f"{k}={v}" for k, v in k_by_strategy.items())
            fund_manager.max_position_count = new_limit
            self.logger.info(
                f"동시 보유 한도 정정(ΣK): {breakdown} → 합계 {total_k}종목 / "
                f"기존 {current} → 적용 {new_limit}종목 "
                f"(max(기존, ΣK) — 한도는 좁아지지 않음)"
            )
        except Exception as e:
            self.logger.warning(f"동시 보유 한도 ΣK 정정 실패 (기존값 유지): {e}")

    async def initialize_system(self) -> bool:
        """시스템 초기화 (비동기)"""
        try:
            self.logger.info("주식 단타 거래 시스템 초기화 시작")

            # 0. 오늘 거래시간 정보 출력 (특수일 확인)
            today_info = MarketHours.get_today_info('KRX')
            self.logger.info(f"오늘 거래시간 정보:\n{today_info}")

            # 1. API 초기화
            self.logger.info("API 매니저 초기화 시작...")
            if not await self.bot.broker.connect():
                self.logger.error("API 초기화 실패")
                return False
            self.logger.info("API 초기화 완료")

            # 1.5. 자금 관리자 초기화 (API 초기화 후)
            await self._initialize_fund_manager()

            # 2. 시장 상태 확인
            market_status = get_market_status()
            self.logger.info(f"현재 시장 상태: {market_status}")

            # 3. 텔레그램 초기화
            await self.bot.telegram.initialize()

            # 4. DB에서 오늘 날짜의 후보 종목 복원
            await self.bot.state_restoration_helper.restore_todays_candidates()

            # 5. 급락게이트 regime_index 설정 대조 (프리로드보다 **먼저** —
            #    프리로드가 쓰는 실효 auto 수의 근거를 먼저 로그에 남긴다)
            self._crosscheck_regime_index_config()

            # 6. 급락게이트 auto 용 시장 매핑 프리로드 (기동 1회)
            self._preload_market_mapping()

            self.logger.info("시스템 초기화 완료")
            return True

        except Exception as e:
            self.logger.error(f"시스템 초기화 실패: {e}")
            return False

    def _preload_market_mapping(self) -> None:
        """급락게이트 `regime_index="auto"` 용 시장 매핑을 기동 시 1회 적재한다.

        여기에 두는 근거: 판정에 필요한 `regime_index` 는 StrategyLoader 가
        전략 인스턴스 속성으로 심고(strategies/config.py:449-452), 그 로드는
        `DayTradingBot.__init__`(main.py:134)에서 끝난다. `initialize_system()`
        은 그 뒤(main.py:267)에 돌므로 `self.bot.strategies` 가 이미 채워져
        있다 — `on_init()`(_initialize_strategy)을 기다릴 필요가 없다.

        auto 전략이 하나도 없으면 DB 를 아예 건드리지 않는다(활성화 전 무해).
        실패해도 기동을 막지 않는다 — 매핑 결측은 "both" 폴백으로 흡수된다.
        """
        try:
            from core.regime.market_classifier import preload_market_mapping
            strategies = getattr(self.bot, 'strategies', None) or {}
            # 판정식은 `compute_effective_auto_count` 하나뿐이다 — 대조 검사와
            # 같은 식을 써야 「프리로드는 돌았는데 대조는 안 돌았다」가 안 생긴다.
            auto_active = compute_effective_auto_count(strategies) > 0
            preload_market_mapping(auto_active=auto_active)
        except Exception as e:
            self.logger.warning(f"시장 매핑 프리로드 오류 (무시): {e}")

    def _crosscheck_regime_index_config(self) -> None:
        """설정파일이 선언한 `regime_index` 가 전략 인스턴스에 실제로 심겼는지 대조.

        여기에 두는 근거는 `_preload_market_mapping` 과 같다 — `self.bot.strategies`
        가 이미 채워져 있고(main.py:134 → 267), 기동 시퀀스에 한 번만 돈다.

        🔴 기동을 죽이지 않는다. 대조 실패가 그날 매매를 통째로 없애면 주객이
           전도된다 — 전체를 try/except 로 감싸고, 실패해도 **태그가 붙은 줄
           하나는 반드시 남긴다**(침묵하면 「검사가 없는 것」과 구분이 안 된다).

        🔴 부작용은 설정 파일 읽기 하나뿐이다. 쓰기·네트워크·DB 접촉 없음.
        """
        try:
            declared_specs, source, load_ok = read_declared_strategy_specs()
            strategies = getattr(self.bot, 'strategies', None) or {}
            for level, message in format_regime_config_crosscheck(
                    declared_specs, strategies, source, load_ok):
                getattr(self.logger, level, self.logger.info)(message)
        except Exception as e:
            self.logger.warning(
                f"{CONFIG_CROSSCHECK_LOG_TAG} 🔴 대조 실패 (기동 계속): {e} — "
                f"설정 선언값과 전략 인스턴스가 어긋나도 이번 기동에서는 "
                f"드러나지 않는다."
            )

    async def _initialize_fund_manager(self) -> None:
        """자금 관리자 초기화"""
        if self.bot.decision_engine.is_virtual_mode:
            # 가상매매: VirtualTradingManager가 D-1 잔고를 이미 이월했으므로 그 값을 사용
            virtual_trading = getattr(self.bot.decision_engine, 'virtual_trading', None)
            total_funds = (
                virtual_trading.get_virtual_balance()
                if virtual_trading is not None
                else 0
            )
            if total_funds <= 0:
                total_funds = 10000000  # fallback: 1천만원
            self.bot.fund_manager.update_total_funds(total_funds)
            self.logger.info(f"자금 관리자 초기화 완료 (가상매매 모드): {total_funds:,.0f}원")
        else:
            balance_info = self.bot.broker.get_account_balance()
            if balance_info:
                # KISBroker returns dict, KISAPIManager returns AccountInfo
                if isinstance(balance_info, dict):
                    total_funds = float(balance_info.get('account_balance', 10000000))
                else:
                    total_funds = float(balance_info.account_balance) if hasattr(balance_info, 'account_balance') else 10000000
                self.bot.fund_manager.update_total_funds(total_funds)
                self.logger.info(f"자금 관리자 초기화 완료: {total_funds:,.0f}원")
            else:
                self.logger.warning("잔고 조회 실패 - 기본값 1천만원으로 설정")
                self.bot.fund_manager.update_total_funds(10000000)

    async def shutdown(self) -> None:
        """시스템 종료"""
        try:
            self.logger.info("시스템 종료 시작")

            # 데이터 수집 중단
            self.bot.data_collector.stop_collection()

            # 주문 모니터링 중단
            self.bot.order_manager.stop_monitoring()

            # 메모리 상태 DB/파일 flush (텔레그램 종료 전 — 실패해도 계속)
            self._flush_state_to_db()

            # 텔레그램 통합 종료
            await self.bot.telegram.shutdown()

            # 미체결 주문 취소
            await self._cancel_pending_orders()

            # API 매니저 종료
            self.bot.broker.shutdown()

            # PID 파일 삭제
            if self.bot.pid_file.exists():
                self.bot.pid_file.unlink()
                self.logger.info("PID 파일 삭제 완료")

            self.logger.info("시스템 종료 완료")

        except Exception as e:
            self.logger.error(f"시스템 종료 중 오류: {e}")

    def _flush_state_to_db(self) -> None:
        """종료 시 메모리 상태를 DB/파일에 flush.

        재시작 후 state_restorer가 올바른 익절/손절률과 최고가를 복원할 수 있도록
        POSITIONED/SELL_PENDING 포지션의 런타임 상태를 영속화합니다.
        실패해도 warning만 기록하고 shutdown을 중단하지 않습니다.
        """
        try:
            trading_manager = getattr(self.bot, 'trading_manager', None)
            if trading_manager is None:
                return

            from core.models import StockState
            is_virtual = getattr(
                getattr(self.bot, 'decision_engine', None), 'is_virtual_mode', True
            )

            # DB 업데이트 대상: POSITIONED 또는 SELL_PENDING 종목
            open_states = {StockState.POSITIONED, StockState.SELL_PENDING}
            open_stocks = [
                ts for ts in trading_manager.trading_stocks.values()
                if ts.state in open_states
            ]

            db_manager = getattr(self.bot, 'db_manager', None)
            trading_repo = (
                getattr(db_manager, 'trading', None) if db_manager else None
            )

            # 종목별 런타임 상태 수집 (JSON dump용)
            position_states = {}
            db_flush_count = 0

            for ts in open_stocks:
                stock_code = ts.stock_code
                position_states[stock_code] = {
                    'highest_price_since_buy': ts.highest_price_since_buy,
                    'trailing_stop_activated': ts.trailing_stop_activated,
                    'target_profit_rate': ts.target_profit_rate,
                    'stop_loss_rate': ts.stop_loss_rate,
                }

                # BUY 레코드의 익절/손절률 UPDATE (재시작 시 복원에 사용)
                if trading_repo is not None:
                    try:
                        buy_record_id = (
                            ts._virtual_buy_record_id if is_virtual
                            else getattr(ts, '_real_buy_record_id', None)
                        )
                        if buy_record_id is not None:
                            updated = trading_repo.update_open_position_state(
                                buy_record_id=buy_record_id,
                                target_profit_rate=ts.target_profit_rate,
                                stop_loss_rate=ts.stop_loss_rate,
                                is_virtual=is_virtual,
                            )
                            if updated:
                                db_flush_count += 1
                    except Exception as db_err:
                        self.logger.warning(
                            f"DB flush 실패 ({stock_code}): {db_err}"
                        )

            # FundManager 일일손실 누적값 포함하여 JSON 파일에 저장
            fund_state = {}
            fund_manager = getattr(self.bot, 'fund_manager', None)
            if fund_manager is not None:
                try:
                    today_str = now_kst().strftime('%Y-%m-%d')
                    fund_state = {
                        'date': today_str,
                        'daily_realized_loss': getattr(fund_manager, '_daily_realized_loss', 0.0),
                        'daily_loss_date': getattr(fund_manager, '_daily_loss_date', ''),
                        'total_funds': fund_manager.total_funds,
                    }
                except Exception as fe:
                    self.logger.warning(f"FundManager 상태 수집 실패: {fe}")

            # logs/state/ 하위에 JSON dump
            try:
                log_root = Path(__file__).parent.parent / 'logs' / 'state'
                log_root.mkdir(parents=True, exist_ok=True)
                date_str = now_kst().strftime('%Y-%m-%d')
                state_file = log_root / f'fund_state_{date_str}.json'
                payload = {
                    'timestamp': now_kst().strftime('%Y-%m-%d %H:%M:%S'),
                    'fund': fund_state,
                    'positions': position_states,
                }
                state_file.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
                self.logger.info(
                    f"종료 상태 flush 완료: DB {db_flush_count}건, "
                    f"JSON {len(position_states)}종목 → {state_file}"
                )
            except Exception as fe:
                self.logger.warning(f"상태 JSON 저장 실패: {fe}")

        except Exception as e:
            self.logger.warning(f"_flush_state_to_db 오류 (종료 계속): {e}")

    async def _cancel_pending_orders(self) -> None:
        """종료 시 미체결 주문 일괄 취소"""
        try:
            pending_orders = self.bot.order_manager.get_pending_orders()
            if not pending_orders:
                self.logger.info("미체결 주문 없음 - 취소 스킵")
                return

            self.logger.info(f"미체결 주문 {len(pending_orders)}건 취소 시작")

            for order in pending_orders:
                try:
                    order_id = getattr(order, 'order_id', None)
                    stock_code = getattr(order, 'stock_code', '')
                    if not order_id:
                        continue

                    result = self.bot.broker.cancel_order(
                        order_id=order_id,
                        stock_code=stock_code
                    )
                    if result and result.get('success'):
                        self.logger.info(f"주문 취소 성공: {order_id} ({stock_code})")
                    else:
                        msg = result.get('message', '알 수 없는 오류') if result else '응답 없음'
                        self.logger.warning(f"주문 취소 실패: {order_id} ({stock_code}) - {msg}")
                except Exception as cancel_err:
                    self.logger.error(f"주문 취소 오류 ({getattr(order, 'order_id', '?')}): {cancel_err}")

            self.logger.info("미체결 주문 취소 처리 완료")

        except Exception as e:
            self.logger.error(f"미체결 주문 일괄 취소 오류: {e}")
