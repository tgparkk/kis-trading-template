"""설정파일 ↔ 전략 인스턴스 `regime_index` 대조 — 활성화 선행조건 A′.

닫으려는 결함은 **자기참조**다. 지금 auto 활성 여부를 말하는 신호가 둘 있는데
둘 다 같은 곳(전략 인스턴스 속성)을 읽는다:

  · 기동 로그  `bot/initializer.py::_preload_market_mapping` 의 `auto_active`
  · EOD 카운터 `market_classifier.resolve_regime_index(configured=...)`

그런데 인스턴스에 값이 심기는 곳은 조건부다(strategies/config.py:449-450 —
`if "regime_index" in spec`). 설정파일이 `"auto"` 라고 선언했는데 그 spec 이
인스턴스에 안 닿으면(전략명 불일치·`enabled:false`·JSON 구조 변경·로더 예외)
인스턴스는 클래스 기본값 `"both"` 를 조용히 유지하고, **두 신호가 나란히
"non-auto" 라고 일치하면서 함께 틀린다.** 판별력이 0 이다.

⇒ 유일한 탈출구는 **설정파일을 독립적으로 읽어 대조**하는 것이다.

이 파일이 단언하는 것:
  ① 다섯 갈래 판정이 각각 실제로 발화한다(정상/미반영/로드실패/파일미선언/인스턴스에만)
  ② **선언 기준 auto 수와 실효 기준 auto 수를 둘 다** 찍고, 다르면 그 자체가 결함
  ③ 🔴 대조 대상 파일이 **로더가 실제로 읽은 그 파일**이다(경로 하드코딩 금지)
  ④ 활성화 전(전부 non-auto)에도 유의미한 줄이 나온다 — 그 줄이 「검사가 동작한다」는 증거
  ⑤ 대조 실패가 기동을 죽이지 않는다
  ⑥ 실제 기동 시퀀스에 **런타임 호출**로 붙어 있다
  ⑦ 🔴 **인식 불가 값**(대소문자 오타·JSON null)이 "정상"으로 계상되지 않는다 (F1)
  ⑧ 선언을 **못 읽었으면** `결함 0건` 을 찍지 않는다 (F2)
  ⑨ 설정파일 부재·파손이 WARNING 한 줄을 낸다 / `정상 N건` 이 실제 대조 건수와 묶여 있다 (F4)

⚠️ DB·네트워크 미접촉: 이 모듈은 JSON 파일 하나만 읽는다. `_NoDb` 로 접속
   시도 자체를 실패로 만들어 그 사실을 단언한다(2026-08-03 미스텁 사고 재발 방지).
   급락게이트 소비자 확인(⑦)은 `get_index_data` 를 목으로 대체해 네트워크도
   건드리지 않는다.
"""
import asyncio
import json
import types
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import api.kis_market_api as kis_market_api
import bot.initializer as initializer_mod
import core.regime.market_classifier as market_classifier
from bot.initializer import (
    CONFIG_CROSSCHECK_LOG_TAG,
    KNOWN_REGIME_INDEX_VALUES,
    BotInitializer,
    effective_regime_index,
    format_regime_config_crosscheck,
    read_declared_strategy_specs,
)
from core.regime.market_classifier import resolve_regime_index
from core.trading_decision_engine import TradingDecisionEngine
from db.kis_db_connection import KisDbConnection
from strategies.config import StrategyLoader

REPO_ROOT = Path(__file__).resolve().parents[2]


class _NoDb:
    """접속 시도 자체를 세는 스텁 — 0회를 직접 단언하기 위한 것."""

    def __init__(self):
        self.connects = 0

    @contextmanager
    def get_connection(self):
        self.connects += 1
        raise AssertionError("테스트가 실제 DB 에 접속하려 했다")
        yield  # pragma: no cover


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    fake = _NoDb()
    monkeypatch.setattr(KisDbConnection, "get_connection", fake.get_connection)
    yield fake
    assert fake.connects == 0, "대조 검사는 DB 를 건드리면 안 된다"


def _instances(mapping):
    """regime_index 만 가진 가짜 전략 인스턴스들.

    값이 `...` 이면 **속성 자체가 없는** 레거시 인스턴스를 만든다
    (클래스 기본값조차 안 잡히는 최악의 경우).
    """
    out = {}
    for name, value in mapping.items():
        out[name] = object() if value is ... else types.SimpleNamespace(regime_index=value)
    return out


def _lines(specs, instances, source="테스트", load_ok=None):
    """기본 `load_ok=None` = 「로더 파싱 성공 여부를 말할 수 없다」.

    레거시 승격 조건A 를 **일부러 기본에서 끈다** — 대부분의 케이스는 조건A 와
    무관하고, 기본을 True 로 두면 무관한 테스트들이 조건A 경보에 휩쓸린다.
    """
    return format_regime_config_crosscheck(specs, instances, source, load_ok)


def _headline(lines):
    assert lines, "요약은 어떤 경우에도 최소 한 줄을 내야 한다"
    level, message = lines[0]
    assert level == "info"
    assert message.startswith(CONFIG_CROSSCHECK_LOG_TAG)
    return message


def _warnings(lines):
    return [m for lv, m in lines if lv == "warning"]


def _spec(name, **kw):
    out = {"name": name, "enabled": True}
    out.update(kw)
    return out


# =========================================================================
# ① 다섯 갈래 판정
# =========================================================================

def test_declared_and_planted_match_is_clean():
    """🟢 파일 선언값이 인스턴스에 그대로 심겼다 — 결함 0."""
    specs = [_spec("a", regime_index="KOSPI"), _spec("b", regime_index="KOSDAQ")]
    lines = _lines(specs, _instances({"a": "KOSPI", "b": "KOSDAQ"}))

    assert _warnings(lines) == []
    assert "결함 0건" in _headline(lines)
    assert "정상 2건" in _headline(lines)


def test_declared_auto_not_planted_is_warning():
    """🔴 이게 잡으려는 결함이다 — 파일은 auto 인데 인스턴스는 아니다.

    현행 두 신호(기동 auto_active·EOD 카운터)는 **둘 다 인스턴스를 읽으므로**
    이 상황에서 나란히 "non-auto" 라고 침묵한다.
    """
    specs = [_spec("a", regime_index="auto")]
    lines = _lines(specs, _instances({"a": "KOSPI"}))

    warns = _warnings(lines)
    assert warns, "미반영이 WARNING 으로 드러나지 않았다"
    joined = "\n".join(warns)
    assert "a" in joined and "auto" in joined and "KOSPI" in joined
    assert "결함 1건" in _headline(lines)
    assert "미반영 1" in _headline(lines)


def test_declared_strategy_missing_from_instances_is_warning():
    """🔴 파일이 선언(enabled)했는데 인스턴스가 아예 없다 = 로드 실패."""
    specs = [_spec("a", regime_index="KOSPI"), _spec("사라진전략", regime_index="auto")]
    lines = _lines(specs, _instances({"a": "KOSPI"}))

    joined = "\n".join(_warnings(lines))
    assert "사라진전략" in joined
    assert "로드실패 1" in _headline(lines)


def test_spec_without_regime_index_is_info_not_warning():
    """🟡 파일이 키를 안 쓰면 클래스 기본값 유지 = 의도된 하위호환."""
    specs = [_spec("a")]
    lines = _lines(specs, _instances({"a": "both"}))

    assert _warnings(lines) == []
    assert "파일미선언 1건" in _headline(lines)


def test_instance_only_strategy_is_info_not_warning():
    """🟡 인스턴스에만 있고 파일엔 없다(레거시 단일전략 경로 등)."""
    specs = [_spec("a", regime_index="KOSPI")]
    lines = _lines(specs, _instances({"a": "KOSPI", "b": "both"}))

    assert _warnings(lines) == []
    assert "인스턴스에만 1건" in _headline(lines)


def test_disabled_spec_is_not_a_load_failure():
    """🟡 `enabled:false` 는 로더가 의도적으로 건너뛴다 — 거짓 경보 금지.

    이걸 로드실패로 세면 비활성 전략을 하나 둘 때마다 WARNING 이 떠서
    **진짜 결함이 소음에 묻힌다**.
    """
    specs = [_spec("a", regime_index="KOSPI"),
             _spec("b", enabled=False, regime_index="auto")]
    lines = _lines(specs, _instances({"a": "KOSPI"}))

    assert _warnings(lines) == []
    assert "비활성 1건" in _headline(lines)
    assert "로드실패 0" in _headline(lines)


def test_malformed_spec_is_warning():
    """🔴 JSON 구조가 바뀌어 spec 이 dict 도 아니면 조용히 넘기지 않는다."""
    lines = _lines(["문자열이_들어옴", {"enabled": True}], _instances({}))

    assert _warnings(lines), "구조 이상이 침묵으로 처리됐다"
    assert "구조이상 2" in _headline(lines)


def test_legacy_config_without_strategies_key_is_info():
    """🟡 `strategies` 배열 자체가 없는 레거시 설정 — 경보가 아니라 정보."""
    lines = _lines(None, _instances({"sample": "both"}))

    assert _warnings(lines) == []
    assert "레거시" in _headline(lines) or "선언 없음" in _headline(lines)


# =========================================================================
# ⑦ 🔴 F1 — 값이 오타면 대조가 "정상"이라고 말한다
# =========================================================================
# 🔴 왜 하드 게이트인가: **활성화 행위 자체가 바로 그 값을 편집하는 것**이다.
#    활성화가 만들 가장 흔한 실수(대소문자 오타·JSON `null`)를, 활성화를
#    검증하려고 만든 검사가 못 보면 거짓 안심이 자리만 옮긴 것이다 —
#    닫으려던 그 모양 그대로.
#
# 하류 안전망이 **비대칭**이라 조치가 갈린다:
#   급락게이트  check_market_direction(trading_decision_engine.py:158-162)
#       → WARNING + "both" 폴백 (양쪽 지수 검사 = 보호 과잉, 안전)
#   일봉 국면게이트 check_regime_gate(trading_decision_engine.py:234)
#       → **무음 KOSPI 강제** (regime_gate != "none" 전략이면 판정축이 조용히 바뀐다)

def _crash_gate_recognizes(value) -> bool:
    """급락게이트가 이 값을 **인식**하는가(= 폴백 경고를 내지 않는가).

    실제 `check_market_direction` 을 돌린다 — 소스 문자열 검사가 아니다.
    지수 조회만 목으로 대체해 네트워크를 건드리지 않는다.
    """
    engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
    engine.logger = Mock()
    engine._market_direction_cache = {}
    engine._market_direction_cache_time = {}
    engine._MARKET_DIRECTION_CACHE_TTL = 60
    with patch.object(kis_market_api, "get_index_data",
                      lambda code: {"bstp_nmix_prdy_ctrt": "0.0"}):
        engine.check_market_direction(regime_index=value)
    return not engine.logger.warning.called


def test_known_value_set_is_derived_from_actual_consumer_behavior():
    """🔴 알려진 값 집합의 근거를 **소비자 실동작**에서 확인한다(목록 베끼기 금지).

    값을 소비하는 곳은 둘이고 서로 다른 값을 안다:
      · "auto"                          → core/regime/market_classifier.py:177
        (`if cfg == "auto":` — 종목 소속 시장으로 해석. 급락게이트는 이 값을 모른다)
      · "KOSPI"/"KOSDAQ"/"both"/"none"  → core/trading_decision_engine.py:153·158
        (`if idx == "none": return` 면제 + `if idx not in ("both","KOSPI","KOSDAQ")` 경고)
      · 클래스 기본값 "both"            → strategies/base.py:322

    그래서 집합은 그 **합집합**이다. 아래는 각 값이 실제로 어딘가에서 분기되는지,
    그리고 집합 밖 값은 정말로 인식 불가인지를 런타임으로 확인한다.
    """
    try:
        # "auto" 는 해석기가 특별취급한다(급락게이트에는 이 값이 도달하지 않는다)
        assert resolve_regime_index(
            "auto", "035720", market_lookup={"035720": "KOSDAQ"}.get) == "KOSDAQ"
        assert not _crash_gate_recognizes("auto"), (
            "전제 확인: 급락게이트는 \"auto\" 를 모른다 — 해석기가 먼저 바꿔야 한다")

        # 나머지 4개는 해석기를 그대로 통과하고 급락게이트가 경고 없이 받는다
        for value in ("KOSPI", "KOSDAQ", "both", "none"):
            assert resolve_regime_index(
                value, "035720", market_lookup=lambda c: "KOSDAQ") == value
            assert _crash_gate_recognizes(value), f"{value!r} 를 급락게이트가 모른다"

        # 집합 밖 값은 반드시 경고를 유발한다 = 진짜로 인식 불가다
        for value in ("Auto", "AUTO", "None", "kospi", "KOSPI2"):
            assert not _crash_gate_recognizes(value), f"{value!r} 가 조용히 통과했다"
            assert resolve_regime_index(
                value, "035720", market_lookup=lambda c: "KOSDAQ") == value, (
                "해석기도 이 값을 특별취급하지 않는다")

        assert set(KNOWN_REGIME_INDEX_VALUES) == {
            "auto", "KOSPI", "KOSDAQ", "both", "none"}
    finally:
        # 해석 집계는 프로세스 전역이다 — 다른 파일의 카운터 테스트를 오염시키지 않는다.
        market_classifier.reset_resolution_counts()


@pytest.mark.parametrize("bad", ["Auto", "AUTO", "kospi", "Both", "KOSPI "])
def test_unrecognized_value_is_a_defect_not_normal(bad):
    """🔴 선언·실효가 **일치해도** 값 자체가 집합 밖이면 정상이 아니다.

    관리자 재현: 파일이 `"Auto"` 를 선언하면 로더가 그대로 심어
    `선언 auto 0 · 실효 auto 0 · 결함 0 · 정상 1` = 「이상 없음」이 찍혔다.
    """
    lines = _lines([_spec("a", regime_index=bad)], _instances({"a": bad}))

    head = _headline(lines)
    assert "정상 0건" in head, f"인식 불가 값이 정상으로 계상됐다: {head}"
    assert "결함 0건" not in head, f"인식 불가 값에 결함 0건을 찍었다: {head}"
    assert "인식불가 1" in head, head
    assert _warnings(lines), "인식 불가 값이 무음 처리됐다"


def test_json_null_regime_index_is_caught():
    """🔴 `null` 은 로더가 문자열 `"None"` 으로 심어 **양쪽이 일치**한다.

    `strategies/config.py:450` 이 `str(spec["regime_index"])` 라서 JSON `null`
    → `None` → 문자열 `"None"`. 선언측도 같은 식으로 문자열화되므로
    「선언 == 실효」가 되고, 값 검사가 없으면 그대로 정상으로 보인다.
    """
    planted = str(None)                      # 로더가 실제로 만드는 값(가정하지 않는다)
    assert planted == "None"

    lines = _lines([_spec("a", regime_index=None)], _instances({"a": planted}))

    head = _headline(lines)
    assert "정상 0건" in head, head
    assert "인식불가 1" in head, head
    joined = "\n".join(_warnings(lines))
    assert "None" in joined and "a" in joined, joined


def test_unrecognized_instance_value_is_caught_even_when_file_is_silent():
    """실효값 쪽만 집합 밖인 경우도 잡는다(파일은 키를 안 썼다)."""
    lines = _lines([_spec("a")], _instances({"a": "Auto"}))

    head = _headline(lines)
    assert "인식불가 1" in head, head
    assert _warnings(lines)


def test_unrecognized_value_warning_says_what_happens_downstream():
    """읽는 사람이 **조치를 정할 수 있어야** 한다.

    어느 전략의 어느 값인지 + 하류가 어떻게 처리하는지(급락게이트=both 폴백 /
    일봉 국면게이트=무음 KOSPI 강제)가 문구에 있어야 한다.
    """
    lines = _lines([_spec("전략X", regime_index="Auto")], _instances({"전략X": "Auto"}))
    warn = "\n".join(_warnings(lines))

    assert "전략X" in warn and "Auto" in warn, warn
    assert "both" in warn, warn                      # 급락게이트 폴백
    assert "KOSPI" in warn, warn                     # 일봉게이트 무음 강제
    assert "check_regime_gate" in warn or "국면게이트" in warn, warn


@pytest.mark.parametrize("good", ["auto", "KOSPI", "KOSDAQ", "both", "none"])
def test_known_values_do_not_trigger_the_unknown_bucket(good):
    """거짓 경보 금지 — 알려진 값 5개는 전부 조용해야 한다."""
    lines = _lines([_spec("a", regime_index=good)], _instances({"a": good}))

    assert _warnings(lines) == [], _warnings(lines)
    assert "인식불가 0" in _headline(lines)
    assert "정상 1건" in _headline(lines)


# =========================================================================
# ⑧ 🔴 F2 — 주석이 잡는다고 적은 경우를 안 잡는다 (JSON 구조 변경)
# =========================================================================

def test_legacy_does_not_claim_zero_defects():
    """🔴 선언을 못 읽었으면 `결함 0건` 을 찍으면 안 된다.

    검증자 실측: `strategies` → `strategy_list` 로 **키 이름만** 바꾸면 봇은
    8전략에서 레거시 단일전략 1개로 조용히 추락하는데, 대조는
    `결함 0건 · 정상 0건 · 인스턴스에만 1건 · 🟡레거시` 에 WARNING 0건이었다.
    「경보가 조용함」이 증거가 아니라던 원칙의 위반이다.
    """
    head = _headline(_lines(None, _instances({"sample": "both"})))

    assert "결함 0건" not in head, head
    assert "판정불가" in head, head


def test_legacy_with_multiple_instances_is_a_warning():
    """🔴 조건B — 레거시 + 인스턴스 2개 이상은 **구조적으로 불가능**하다.

    다중 인스턴스는 오직 `strategies` 배열에서만 나온다(main.py:166-186 —
    배열이 없으면 단일 전략 1개 또는 0개). 배열을 못 읽었는데 2개 이상이면
    「보는 파일이 로더가 읽은 파일과 다르다」거나 「구조가 바뀌었다」다.
    """
    lines = _lines(None, _instances({"a": "both", "b": "both"}), load_ok=None)

    joined = "\n".join(_warnings(lines))
    assert joined, "구조적으로 불가능한 상태가 무음 처리됐다"
    assert "조건B" in joined, joined


def test_legacy_with_successful_parse_is_a_warning():
    """🔴 조건A — 로더가 파일을 **정상 파싱**했는데 strategies 배열이 없다.

    이 배포는 항상 `strategies` 배열을 쓴다(8전략). 파싱이 성공했는데 배열이
    없다면 구조가 바뀐 것 말고 설명이 없다 — 인스턴스가 1개뿐이라 조건B 가
    안 걸리는 실제 재현(`strategies` → `strategy_list`)을 이 조건이 잡는다.
    """
    lines = _lines(None, _instances({"sample": "both"}), load_ok=True)

    joined = "\n".join(_warnings(lines))
    assert joined, "조건A 가 무음 처리됐다"
    assert "조건A" in joined, joined


@pytest.mark.parametrize("load_ok", [False, None])
def test_genuine_legacy_deployment_is_not_a_false_alarm(load_ok):
    """🟡 좁힌 이유 — 진짜 레거시 단일전략 배포는 매 기동 경보가 되면 안 된다.

    **오경보가 잦으면 사람이 무시하게 되고 그게 가드를 무력화한다.**
    조건A(파싱 성공) 도 조건B(다중 인스턴스) 도 아닌 상태는 INFO 로 남는다.
    """
    lines = _lines(None, _instances({"sample": "both"}), load_ok=load_ok)

    assert _warnings(lines) == [], _warnings(lines)
    assert "판정불가" in _headline(lines)


def test_legacy_warning_distinguishes_which_condition_fired():
    """어느 조건이 걸렸는지 구분되게 찍는다 — 뭉치면 원인 추적이 불가능하다."""
    only_a = "\n".join(_warnings(_lines(None, _instances({"x": "both"}), load_ok=True)))
    only_b = "\n".join(_warnings(
        _lines(None, _instances({"x": "both", "y": "both"}), load_ok=False)))
    both = "\n".join(_warnings(
        _lines(None, _instances({"x": "both", "y": "both"}), load_ok=True)))

    assert "조건A" in only_a and "조건B" not in only_a, only_a
    assert "조건B" in only_b and "조건A" not in only_b, only_b
    assert "조건A" in both and "조건B" in both, both


def test_legacy_warning_gives_material_to_judge():
    """🔴 **단정이 아니다** — 읽는 사람이 판정할 재료를 줘야 한다.

    이 경고는 「구조가 깨졌다」가 아니라 「배열을 못 읽었다」다. 의도된 레거시면
    무해하고, 아니면 다중 전략이 로더에게 안 보이는 상태다.
    """
    warn = "\n".join(_warnings(
        _lines(None, _instances({"sample": "both"}), source="파일경로X", load_ok=True)))

    assert "의도된 레거시" in warn, warn      # 단정하지 않는다
    assert "파일경로X" in warn, warn          # 읽은 파일
    assert "로더 파싱 성공 True" in warn, warn  # load_ok
    assert "1개" in warn and "sample" in warn, warn   # 인스턴스 수·이름


def test_structure_change_repro_is_not_silent(tmp_path, monkeypatch):
    """실측 재현 — 키 이름만 `strategy_list` 로 바꾼 파일.

    🔴 `load_ok` 를 settings 에서 따로 읽지 않고 **리더가 함께 돌려준 값**을
       쓴다. 「어느 파일을 봤는가」와 「그 파일 파싱이 성공했는가」가 갈리면
       이 검사가 정확히 자기가 잡으려던 종류의 거짓말을 하게 된다.
    """
    from config import settings

    target = tmp_path / "renamed.json"
    target.write_text(json.dumps({"strategy_list": [
        {"name": "a", "enabled": True, "regime_index": "auto"}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "LAST_LOADED_TRADING_CONFIG_PATH", target, raising=False)
    monkeypatch.setattr(settings, "LAST_TRADING_CONFIG_LOAD_OK", True, raising=False)

    specs, source, load_ok = read_declared_strategy_specs()
    assert specs is None, "전제 확인: 키가 바뀌면 선언을 못 읽는다"
    assert load_ok is True, "전제 확인: 로더는 이 파일을 정상 파싱했다"

    lines = _lines(specs, _instances({"sample": "both"}), source, load_ok)
    head = _headline(lines)
    assert "결함 0건" not in head, head
    assert "판정불가" in head, head
    # 🔴 인스턴스가 1개뿐이라 조건B 는 안 걸린다 — 조건A 가 잡아야 한다.
    assert "조건A" in "\n".join(_warnings(lines)), _warnings(lines)


def test_loader_not_run_yields_unknown_load_ok(tmp_path, monkeypatch):
    """로더 미실행이면 `load_ok` 는 `False` 가 아니라 `None`(말할 수 없음)이다.

    `False` 로 뭉개면 「파싱 실패」와 「미실행」이 섞여 조건A 판정이 조용히
    틀어진다.
    """
    from config import settings

    target = tmp_path / "fallback.json"
    target.write_text(json.dumps({"strategies": []}), encoding="utf-8")
    monkeypatch.setattr(settings, "LAST_LOADED_TRADING_CONFIG_PATH", None, raising=False)
    monkeypatch.setattr(settings, "TRADING_CONFIG_FILE", target)

    _specs, source, load_ok = read_declared_strategy_specs()

    assert load_ok is None, load_ok
    assert "모듈상수" in source


# =========================================================================
# ② 선언 auto 수 · 실효 auto 수를 **둘 다** 찍는다
# =========================================================================

def test_headline_reports_both_declared_and_effective_auto_counts():
    """둘 중 하나만 찍으면 자기참조 문제가 그대로 남는다."""
    specs = [_spec("a", regime_index="auto"), _spec("b", regime_index="auto")]
    lines = _lines(specs, _instances({"a": "auto", "b": "auto"}))

    head = _headline(lines)
    assert "선언 auto 2건" in head
    assert "실효 auto 2건" in head


def test_declared_effective_divergence_is_itself_a_defect():
    """🔴 선언 2 · 실효 1 — 두 수가 다르면 그 자체가 결함이다.

    이 케이스가 정확히 「기동 로그와 EOD 카운터가 나란히 틀리는」 상황이다.
    """
    specs = [_spec("a", regime_index="auto"), _spec("b", regime_index="auto")]
    lines = _lines(specs, _instances({"a": "auto", "b": "KOSPI"}))

    head = _headline(lines)
    assert "선언 auto 2건" in head
    assert "실효 auto 1건" in head
    joined = "\n".join(_warnings(lines))
    assert "선언" in joined and "실효" in joined, (
        "선언≠실효 자체를 알리는 WARNING 이 없다")


def test_effective_auto_uses_the_same_expression_as_preload():
    """실효 auto 는 `_preload_market_mapping` 의 auto_active 와 **같은 식**이어야 한다.

    두 곳이 갈리면 「프리로드는 돌았는데 대조는 안 돌았다」 같은
    설명 불가능한 상태가 생긴다. 속성 부재·None·"" 를 전부 both 로 본다.
    """
    specs = [_spec(n) for n in ("a", "b", "c", "d")]
    instances = _instances({"a": ..., "b": None, "c": "", "d": "auto"})
    lines = _lines(specs, instances)

    assert "실효 auto 1건" in _headline(lines)
    # 같은 입력에 대해 기동 경로의 판정과 일치하는지 직접 대조
    assert initializer_mod.compute_effective_auto_count(instances) == 1


@pytest.mark.parametrize("planted", [None, "", ...])
def test_unset_instance_value_is_normalized_to_class_default(planted):
    """🔴 정규화를 빼면 **거짓 경보 발생기**가 된다.

    인스턴스의 `regime_index` 가 None/""/속성부재면 실효값은 클래스 기본값
    `"both"` 다(`BaseStrategy.regime_index`). 정규화 없이 raw 값을 비교하면
    파일이 `"both"` 라고 정확히 선언한 전략이 `both → None` 미반영으로
    보고된다 — 진짜 결함을 소음에 묻는다.
    """
    lines = _lines([_spec("a", regime_index="both")], _instances({"a": planted}))

    assert _warnings(lines) == [], f"정규화 누락으로 거짓 경보: {_warnings(lines)}"
    assert "정상 1건" in _headline(lines)


def test_unset_instance_value_is_reported_as_both_not_none():
    """파일 미선언 건의 **실효값 표기**도 정규화돼야 한다(로그 오독 방지)."""
    lines = _lines([_spec("a")], _instances({"a": None}))

    info = "\n".join(m for lv, m in lines if lv == "info")
    assert '"both"' in info or "→\"both\"" in info, info
    assert "None" not in info


# =========================================================================
# ④ 활성화 전에도 유의미하다 — 이 줄 자체가 「검사가 동작한다」는 증거
# =========================================================================

def test_summary_is_emitted_even_when_nothing_is_auto():
    specs = [_spec(n, regime_index="KOSPI") for n in ("a", "b")]
    head = _headline(_lines(specs, _instances({"a": "KOSPI", "b": "KOSPI"})))

    assert "선언 auto 0건" in head
    assert "실효 auto 0건" in head
    assert "결함 0건" in head
    # 「0/0/0」만으로는 대조가 실제로 돈 건지 알 수 없다 — 대조 건수가 있어야 한다.
    assert "정상 2건" in head


def _mirror_loader(specs):
    """`StrategyLoader.load_strategies` 가 만드는 (전략명 → 실효 regime_index).

    🔴 실제 로더는 `regime_index` **유무와 무관하게** enabled 전건에 인스턴스를
       만들고(strategies/config.py:442-453), 키가 없으면 클래스 기본값 `"both"`
       가 남는다. 이전 판본의 거울은 `and "regime_index" in s` 로 걸러서
       ① 지원되는 하위호환 설정에 「로드실패」 거짓 경보를 냈고
       ② 로더 규칙과 조용히 갈렸다.
       아래 `test_mirror_matches_real_loader` 가 이 함수를 **진짜 로더와 런타임
       대조**한다 — 거울이 낡으면 거기서 터진다.
    """
    return {s["name"]: (str(s["regime_index"]) if "regime_index" in s else "both")
            for s in specs if s.get("enabled", True)}


def test_mirror_matches_real_loader(monkeypatch):
    """거울 함수가 진짜 로더와 일치하는지 **런타임으로** 대조한다.

    소스 문자열 검사가 아니라 `StrategyLoader.load_strategies` 를 실제로 돌린다
    (전략 클래스 로드만 스텁 — 파일·DB·네트워크 미접촉).
    """
    class _Dummy:
        regime_index = "both"                # BaseStrategy 클래스 기본값과 동일

    monkeypatch.setattr(StrategyLoader, "load_strategy",
                        staticmethod(lambda name: _Dummy()))
    specs = [
        _spec("keyed", regime_index="KOSDAQ"),
        _spec("unkeyed"),                     # 🔴 키 없음 = 명시적으로 지원되는 하위호환
        _spec("off", enabled=False, regime_index="auto"),
        _spec("nulled", regime_index=None),   # 로더가 str(None) 로 심는다
    ]

    real = StrategyLoader.load_strategies(specs)

    assert {n: effective_regime_index(s) for n, s in real.items()} == _mirror_loader(specs)


def test_backward_compatible_spec_without_key_does_not_false_alarm():
    """🔴 지원되는 하위호환(전략 하나에서 `regime_index` 삭제)이 경보가 되면 안 된다."""
    specs = [_spec("a", regime_index="KOSPI"), _spec("b")]   # b 는 키 없음
    lines = _lines(specs, _instances(_mirror_loader(specs)))

    assert _warnings(lines) == [], _warnings(lines)
    assert "로드실패 0" in _headline(lines)
    assert "파일미선언 1건" in _headline(lines)


def test_live_config_declared_values_are_recognized_and_self_consistent():
    """실제 `config/trading_config.json` 의 **선언값 자체**를 검사한다.

    ⚠️ 이름·범위 정정(2026-08-04). 이 테스트는 「대조가 동작한다」의 증거가
       **아니다** — 인스턴스를 파일에서 거울로 만들기 때문에
       `declared == effective` 가 구성상 항상 참이고, 따라서 spec 이 인스턴스에
       안 닿는 상황을 원리적으로 볼 수 없다(그건
       `test_declared_auto_not_planted_is_warning` 이 본다).

       거울이 참이어도 남는 판별력이 있다: **파일이 선언한 값이 하류가 인식하는
       값인가**(대소문자 오타·`null`). 활성화 편집이 만들 가장 흔한 실수다.

    ⚠️ `선언 auto == 0` 은 단언하지 않는다 — 활성화(Task 6)되면 바로 깨지는 지뢰다.
    """
    raw = json.loads((REPO_ROOT / "config" / "trading_config.json").read_text(encoding="utf-8"))
    specs = raw.get("strategies")
    assert specs, "전제 확인: 현행 설정은 다중 전략 배열을 갖는다"

    lines = _lines(specs, _instances(_mirror_loader(specs)))

    assert _warnings(lines) == [], f"현행 설정이 이미 결함이다: {_warnings(lines)}"
    head = _headline(lines)
    assert "결함 0건" in head
    assert "인식불가 0" in head, f"현행 설정에 인식 불가 값이 있다: {head}"
    declared = head.split("선언 auto ")[1].split("건")[0]
    effective = head.split("실효 auto ")[1].split("건")[0]
    assert declared == effective, f"선언≠실효: {head}"


# =========================================================================
# ③ 🔴 로더가 실제로 읽은 그 파일을 본다 (경로 하드코딩 금지)
# =========================================================================

def test_reads_the_path_the_loader_recorded(tmp_path, monkeypatch):
    """로더가 기록한 경로를 따라간다 — 딴 파일을 보면 검사가 무의미해진다."""
    from config import settings

    target = tmp_path / "instance_trading_config.json"
    target.write_text(json.dumps(
        {"strategies": [{"name": "only_here", "regime_index": "auto"}]}), encoding="utf-8")

    monkeypatch.setattr(settings, "LAST_LOADED_TRADING_CONFIG_PATH", target, raising=False)
    monkeypatch.setattr(settings, "LAST_TRADING_CONFIG_LOAD_OK", True, raising=False)
    # 모듈 상수는 **딴 곳**을 가리키게 둔다 — 이걸 읽으면 테스트가 실패한다.
    monkeypatch.setattr(settings, "TRADING_CONFIG_FILE", tmp_path / "wrong.json")

    specs, source, _load_ok = read_declared_strategy_specs()

    assert [s["name"] for s in specs] == ["only_here"]
    assert str(target) in source
    assert "로더기록" in source


def test_falls_back_to_module_constant_and_says_so(tmp_path, monkeypatch):
    """로더가 아직 안 돌았으면(기록 None) 모듈 상수를 쓰되 **출처를 밝힌다**.

    출처 표기가 없으면 「어느 파일을 봤는지」가 로그에서 사라져, 거짓 경보가
    떴을 때 원인을 못 가린다.
    """
    from config import settings

    target = tmp_path / "fallback.json"
    target.write_text(json.dumps({"strategies": []}), encoding="utf-8")
    monkeypatch.setattr(settings, "LAST_LOADED_TRADING_CONFIG_PATH", None, raising=False)
    monkeypatch.setattr(settings, "TRADING_CONFIG_FILE", target)

    specs, source, _load_ok = read_declared_strategy_specs()

    assert specs == []
    assert str(target) in source
    assert "모듈상수" in source


def test_loader_records_the_path_it_actually_opened(tmp_path, monkeypatch):
    """🔴 기록이 실제 로드 시점에 남는가 — 기록 자체가 거짓이면 전부 무의미하다."""
    from config import settings

    target = tmp_path / "recorded.json"
    target.write_text(json.dumps({"strategies": [{"name": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "TRADING_CONFIG_FILE", target)
    monkeypatch.setattr(settings, "LAST_LOADED_TRADING_CONFIG_PATH", None, raising=False)

    cfg = settings.load_trading_config()

    assert cfg.strategies == [{"name": "x"}]
    assert Path(settings.LAST_LOADED_TRADING_CONFIG_PATH) == target
    assert settings.LAST_TRADING_CONFIG_LOAD_OK is True


def test_loader_records_failure_when_file_is_unreadable(tmp_path, monkeypatch):
    """파싱 실패 시 로더는 기본 설정으로 조용히 넘어간다 — 그 사실이 기록돼야 한다.

    이 경로가 정확히 「파일은 auto 라 선언했는데 인스턴스엔 아무것도 안 닿는」
    상황을 만든다.
    """
    from config import settings

    target = tmp_path / "broken.json"
    target.write_text("{ 이건 JSON 이 아니다", encoding="utf-8")
    monkeypatch.setattr(settings, "TRADING_CONFIG_FILE", target)
    monkeypatch.setattr(settings, "LAST_TRADING_CONFIG_LOAD_OK", True, raising=False)

    cfg = settings.load_trading_config()

    assert cfg.strategies is None
    assert settings.LAST_TRADING_CONFIG_LOAD_OK is False


def test_source_note_surfaces_loader_failure(tmp_path, monkeypatch):
    """로더가 실패했다는 사실이 대조 줄에 드러나야 한다."""
    from config import settings

    target = tmp_path / "broken.json"
    target.write_text(json.dumps({"strategies": [{"name": "a", "regime_index": "auto"}]}),
                      encoding="utf-8")
    monkeypatch.setattr(settings, "LAST_LOADED_TRADING_CONFIG_PATH", target, raising=False)
    monkeypatch.setattr(settings, "LAST_TRADING_CONFIG_LOAD_OK", False, raising=False)

    _specs, source, _load_ok = read_declared_strategy_specs()

    assert "load_ok=False" in source


# =========================================================================
# ⑤⑥ 기동 배선 — 죽이지 않고, 실제로 돈다
# =========================================================================

def _make_initializer(monkeypatch, strategies=None, reader=None):
    logged = []
    init = BotInitializer.__new__(BotInitializer)  # __init__ 우회(봇 전체 불필요)
    init.bot = types.SimpleNamespace(strategies=strategies or {})
    init.logger = types.SimpleNamespace(
        info=lambda m, *a, **k: logged.append(("info", str(m))),
        warning=lambda m, *a, **k: logged.append(("warning", str(m))),
        error=lambda m, *a, **k: logged.append(("error", str(m))),
    )
    if reader is not None:
        monkeypatch.setattr(initializer_mod, "read_declared_strategy_specs", reader)
    return init, logged


def test_crosscheck_logs_one_greppable_line(monkeypatch):
    init, logged = _make_initializer(
        monkeypatch,
        strategies=_instances({"a": "KOSPI"}),
        reader=lambda: ([_spec("a", regime_index="KOSPI")], "stub", True),
    )
    init._crosscheck_regime_index_config()

    tagged = [m for _lv, m in logged if m.startswith(CONFIG_CROSSCHECK_LOG_TAG)]
    assert len(tagged) >= 1
    assert "선언 auto 0건" in tagged[0] and "실효 auto 0건" in tagged[0]


def test_crosscheck_tag_does_not_collide_with_existing_tags():
    """기존 태그와 겹치면 grep 이 섞인다."""
    import core.regime.market_classifier as mc

    assert CONFIG_CROSSCHECK_LOG_TAG != mc.RESOLUTION_LOG_TAG
    assert CONFIG_CROSSCHECK_LOG_TAG != "[시장매핑]"
    assert not CONFIG_CROSSCHECK_LOG_TAG.startswith(mc.RESOLUTION_LOG_TAG.rstrip("]"))


def test_crosscheck_failure_does_not_break_startup(monkeypatch):
    """대조 실패가 그날 매매를 통째로 없애면 주객전도다."""
    def _boom():
        raise RuntimeError("설정 파일이 사라졌다")

    init, logged = _make_initializer(monkeypatch, reader=_boom)
    init._crosscheck_regime_index_config()  # 예외가 새어나오면 실패

    assert any(lv == "warning" and CONFIG_CROSSCHECK_LOG_TAG in m for lv, m in logged), (
        "실패해도 태그가 붙은 줄 하나는 남아야 한다(침묵 금지)")


class _AsyncStub:
    def __init__(self, log, name, result=None):
        self._log, self._name, self._result = log, name, result

    async def __call__(self, *a, **k):
        self._log.append(self._name)
        return self._result


def _make_bootable_initializer(monkeypatch, *, broker_ok=True):
    """`initialize_system()` 의 외부 의존을 전부 스텁한 초기화기.

    ⚠️ 소스 문자열 검사가 아니라 **런타임 호출**을 센다 — 주석 처리·`if False:`
       ·도달 불가 위치 이동을 전부 잡기 위해서다
       (`test_initializer_market_mapping_preload.py` 의 같은 교훈).
    """
    log = []
    monkeypatch.setattr(
        initializer_mod, "MarketHours",
        types.SimpleNamespace(get_today_info=lambda market='KRX': f"[{market}] stub"),
    )
    monkeypatch.setattr(initializer_mod, "get_market_status", lambda: "pre_market")

    bot = types.SimpleNamespace(
        broker=types.SimpleNamespace(connect=_AsyncStub(log, "broker.connect", broker_ok)),
        telegram=types.SimpleNamespace(initialize=_AsyncStub(log, "telegram.initialize")),
        state_restoration_helper=types.SimpleNamespace(
            restore_todays_candidates=_AsyncStub(log, "restore_candidates")),
        decision_engine=types.SimpleNamespace(
            is_virtual_mode=True,
            virtual_trading=types.SimpleNamespace(get_virtual_balance=lambda: 1_000_000.0)),
        fund_manager=types.SimpleNamespace(update_total_funds=lambda v: None),
        strategies={},
    )
    init = BotInitializer.__new__(BotInitializer)
    init.bot = bot
    init.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    init._preload_market_mapping = lambda: log.append("preload")
    init._crosscheck_regime_index_config = lambda: log.append("crosscheck")
    return init, log


def test_initialize_system_actually_calls_crosscheck(monkeypatch):
    """기동이 성공하면 대조가 **정확히 1회** 실제로 실행된다."""
    init, log = _make_bootable_initializer(monkeypatch)

    ok = asyncio.run(init.initialize_system())

    assert ok is True, "스텁 기동은 성공해야 한다(전제가 깨지면 아래 단언이 무의미)"
    assert log.count("crosscheck") == 1, f"대조가 실행되지 않았다: {log}"


def test_crosscheck_runs_before_preload(monkeypatch):
    """대조가 먼저다 — 프리로드가 쓰는 실효 auto 수의 근거를 먼저 남긴다."""
    init, log = _make_bootable_initializer(monkeypatch)

    asyncio.run(init.initialize_system())

    assert log.index("crosscheck") < log.index("preload"), log


def test_crosscheck_is_not_reached_when_startup_aborts_early(monkeypatch):
    """무조건 실행되는 위치(함수 최상단 등)로 옮기면 여기서 잡힌다."""
    init, log = _make_bootable_initializer(monkeypatch, broker_ok=False)

    ok = asyncio.run(init.initialize_system())

    assert ok is False
    assert "crosscheck" not in log, f"API 초기화 실패 경로에서 대조가 돌았다: {log}"


# =========================================================================
# ⑨ F4 — 검증자 신규 변이 생존분. **코드는 옳고 테스트가 없었다.**
# =========================================================================

def _tagged(logged, level):
    return [m for lv, m in logged if lv == level and CONFIG_CROSSCHECK_LOG_TAG in m]


def _point_loader_record_at(monkeypatch, path):
    from config import settings
    monkeypatch.setattr(settings, "LAST_LOADED_TRADING_CONFIG_PATH", path, raising=False)
    monkeypatch.setattr(settings, "LAST_TRADING_CONFIG_LOAD_OK", False, raising=False)


def test_missing_config_file_produces_a_warning(tmp_path, monkeypatch):
    """🔴 N1 — 없는 설정파일은 **WARNING 한 줄**을 낸다.

    검증자 변이: `read_declared_strategy_specs` 의 `open`/`json.load` 를
    `try/except: raw = {}` 로 감싸는 「검사가 예외를 던지면 안 되지」류 리팩터가
    설정파일 부재·파손을 🔴 WARNING 에서 🟡레거시 INFO 로 둔갑시키는데
    기존 28건이 전부 green 이었다.
    """
    missing = tmp_path / "does_not_exist.json"
    _point_loader_record_at(monkeypatch, missing)

    with pytest.raises(OSError):
        read_declared_strategy_specs()

    init, logged = _make_initializer(monkeypatch, strategies=_instances({"a": "both"}))
    init._crosscheck_regime_index_config()

    assert len(_tagged(logged, "warning")) == 1, f"부재 파일이 WARNING 을 안 냈다: {logged}"
    assert not any("레거시" in m for _lv, m in logged), (
        f"부재 파일이 레거시 INFO 로 둔갑했다: {logged}")


def test_broken_json_produces_a_warning(tmp_path, monkeypatch):
    """🔴 N1 — 깨진 JSON 도 마찬가지다."""
    broken = tmp_path / "broken.json"
    broken.write_text("{ 이건 JSON 이 아니다", encoding="utf-8")
    _point_loader_record_at(monkeypatch, broken)

    with pytest.raises(json.JSONDecodeError):
        read_declared_strategy_specs()

    init, logged = _make_initializer(monkeypatch, strategies=_instances({"a": "both"}))
    init._crosscheck_regime_index_config()

    assert len(_tagged(logged, "warning")) == 1, f"깨진 JSON 이 WARNING 을 안 냈다: {logged}"
    assert not any("레거시" in m for _lv, m in logged), logged


@pytest.mark.parametrize("specs", [None, []])
def test_normal_count_is_zero_when_nothing_was_compared(specs):
    """🔑 N2 — `정상 N건` 은 **대조 건수**여야 한다. 전략 수가 아니다.

    검증자 변이: `정상 {len(ok)}` → `{len(strategies)}` 로 바꿔도 기존 28건이
    전부 green. 실행자가 「검사가 돌았다」의 증거로 내세운 바로 그 숫자가
    실제 대조와 묶여 있지 않았다.
    """
    head = _headline(_lines(specs, _instances({"a": "both", "b": "both"})))

    assert "정상 0건" in head, f"대조를 한 건도 안 했는데 정상이 0이 아니다: {head}"


def test_normal_count_counts_only_matching_strategies():
    """🔑 N2 — 인스턴스 3개 중 실제 일치는 1건뿐이다."""
    specs = [_spec("a", regime_index="KOSPI"),
             _spec("b", regime_index="auto"),      # 미반영
             _spec("c")]                            # 파일미선언
    head = _headline(_lines(specs, _instances({"a": "KOSPI", "b": "KOSPI", "c": "both"})))

    assert "정상 1건" in head, head
