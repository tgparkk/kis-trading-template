"""전략이 «자기 룰을 거친 종목만» 받는지 — 후보 공급 경로 게이트 (2026-08-18).

배경:
  전략이 후보를 받는 문이 셋인데 자물쇠가 «첫 번째»에만 있었다.

    | 문 | 출처 | 그 전략의 진입 룰 | base_filter | 열리는 조건 |
    |----|------|------------------|-------------|-------------|
    | 1  | `screener_snapshots` (전략 전용) | ✅ | ✅ | 항상 1순위 |
    | 2  | 공통 `data/screener_*.json`      | ❌ | 🔴 **미적용** | 그 전략 «하나»만 0건 |
    | 3  | 거래량 순위                       | ❌ | ✅ | 8전략 «전부» 0건 |

  2번 문은 `"N일연속상승, 거래대금 N억"` 으로 뽑힌 «전략 무관» 명단이고,
  `accepts_volume_fallback` 깃발조차 보지 않았다(`deep_mr_dev20` 이 명시적으로
  거부했는데도 받게 돼 있었다).

  🔑 그런데도 실제로 새지 않은 이유는 설계가 아니라 **우연**이었다 — 그 JSON 을 쓰는
     유일한 주체가 수동 연구 스크립트(`scripts/run_screener.py`)뿐이라 파일이 4개월째
     낡았고, `_resolve_screener_path` 가 «당일자» 파일만 받기 때문이다.
     ⇒ ***「한 번도 발동한 적 없다」는 「막혀 있다」가 아니다.***

  2026-08-18 조치(사장님 승인): **2번 문 제거** + 「없다」와 「고장」 분리 + 3번 문 경보.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from core.candidate_selector import CandidateSelector
from core.models import TradingConfig


@pytest.fixture
def selector():
    return CandidateSelector(config=TradingConfig(), broker=MagicMock())


def _snapshot(monkeypatch, *, codes=None, raises=None):
    """1순위(screener_snapshots) 를 원하는 상태로 만든다."""
    import core.screener_snapshot_provider as provider_mod

    def _provider(strategy_name):
        def _call(name, day):
            if raises is not None:
                raise raises
            return list(codes or [])
        return _call

    monkeypatch.setattr(provider_mod, "make_screener_snapshot_provider", _provider)


def _forbid_json_pool(monkeypatch, selector):
    """2번 문이 «호출되면» 즉시 실패시킨다."""
    def _boom(*args, **kwargs):
        pytest.fail("전략별 경로가 공통 스크리너 JSON(2번 문)을 호출했다 — 제거됐어야 한다")

    monkeypatch.setattr(selector, "load_from_screener", _boom)


class _Records(logging.Handler):
    """이 프로젝트 로거 전용 캡처.

    🔑 `utils.logger.setup_logger` 가 `logger.propagate = False` 로 두기 때문에
       pytest 의 `caplog`(루트 핸들러 기반)로는 **한 줄도 안 잡힌다**. 그러면
       「로그가 안 났다」와 「캡처를 못 했다」가 구별되지 않아, 경보 테스트가
       조용히 무의미해진다. 그래서 대상 로거에 직접 핸들러를 붙인다.
    """

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def max_level(self) -> int:
        return max((r.levelno for r in self.records), default=0)


@pytest.fixture
def logs(selector):
    h = _Records()
    selector.logger.addHandler(h)
    old = selector.logger.level
    selector.logger.setLevel(logging.DEBUG)
    yield h
    selector.logger.removeHandler(h)
    selector.logger.setLevel(old)


def test_capture_helper_actually_captures(selector, logs):
    """🔑 캡처 장치 자체의 건전성 — 이게 없으면 아래 경보 테스트가 «항상 통과»한다.

    (`caplog` 를 썼다면 propagate=False 때문에 0건이 잡히고, 「ERROR 가 없다」는
     주장은 참이 되지만 그건 로그가 안 난 게 아니라 «못 본» 것이다.)
    """
    selector.logger.error("probe")
    assert logs.max_level() >= logging.ERROR


# ── 2번 문 제거 ──────────────────────────────────────────────────────────────

def test_empty_snapshot_yields_no_candidates_and_never_touches_json_pool(
    selector, monkeypatch
):
    """🔑 「조건에 맞는 종목이 없다」의 올바른 답은 «안 산다» 이지 «딴 데서 사온다» 가 아니다."""
    _snapshot(monkeypatch, codes=[])
    _forbid_json_pool(monkeypatch, selector)

    assert selector._fetch_candidates_for_strategy("minervini_volume_dryup", 10) == []


def test_snapshot_failure_is_fail_closed_and_loud(selector, monkeypatch, logs):
    """🔴 「조회가 고장났다」는 «없다» 와 다르다 — ERROR 로 보이고, 대체 명단은 없다.

    종전에는 둘이 똑같이 「다른 명단에서 사오기」로 처리됐고, 고장 로그는 `debug` 라
    라이브(LOG_LEVEL=INFO)에서는 «보이지도» 않았다. 즉 폴백은 고장을 대비한 게 아니라
    감추면서 다른 종목을 사고 있었다.
    """
    _snapshot(monkeypatch, raises=RuntimeError("DB down"))
    _forbid_json_pool(monkeypatch, selector)

    got = selector._fetch_candidates_for_strategy("minervini_volume_dryup", 10)

    assert got == [], "조회 실패인데 후보를 만들어냈다"
    assert logs.max_level() >= logging.ERROR, (
        "조회 실패가 ERROR 로 보이지 않는다 — 라이브(INFO)에서 묻힌다"
    )


def test_failure_and_emptiness_are_distinguishable_in_logs(selector, monkeypatch, logs):
    """대칭 주장 — 「없다」는 ERROR 가 아니어야 한다(정상 상황을 사고로 세지 말 것)."""
    _snapshot(monkeypatch, codes=[])
    _forbid_json_pool(monkeypatch, selector)

    selector._fetch_candidates_for_strategy("minervini_volume_dryup", 10)

    assert logs.records, "아무 로그도 안 났다 — 0건 상황이 조용히 지나간다"
    assert logs.max_level() < logging.ERROR, (
        "후보 0건(정상)을 ERROR 로 찍으면 진짜 고장 경보가 마비된다"
    )


def test_populated_snapshot_still_returns_candidates(selector, monkeypatch):
    """대칭 주장 — 정상 경로는 그대로 동작해야 한다."""
    _snapshot(monkeypatch, codes=["005930", "000660"])
    _forbid_json_pool(monkeypatch, selector)
    monkeypatch.setattr(selector, "_filter_unsafe_stocks", lambda pool, **kw: pool)

    got = selector._fetch_candidates_for_strategy("minervini_volume_dryup", 10)

    assert [c.code for c in got] == ["005930", "000660"]


def test_safety_filter_failure_is_also_fail_closed(selector, monkeypatch, logs):
    """안전성 필터가 터져도 «무필터로 통과»시키지 않는다."""
    _snapshot(monkeypatch, codes=["005930"])
    _forbid_json_pool(monkeypatch, selector)

    def _boom(pool, **kw):
        raise RuntimeError("safety API down")

    monkeypatch.setattr(selector, "_filter_unsafe_stocks", _boom)

    got = selector._fetch_candidates_for_strategy("minervini_volume_dryup", 10)

    assert got == []
    assert logs.max_level() >= logging.ERROR


# ── 3번 문(거래량 폴백) — 유지하되 «보이게» ─────────────────────────────────

def test_volume_fallback_only_when_every_strategy_is_empty():
    """3번 문은 「하나라도 후보가 있으면」 열리지 않는다(전략별 격리 유지)."""
    from bot.candidate_loader import should_use_volume_fallback

    assert should_use_volume_fallback({"a": [], "b": []}) is True
    assert should_use_volume_fallback({"a": ["x"], "b": []}) is False


def test_minervini_declines_the_volume_fallback():
    """🔴 TT 는 매수 시점에 재검사되지 않는다 — 스크리너를 안 거친 종목은 받으면 안 된다.

    `evaluate_entry()` 는 `rule_volume_dryup` 만 돌린다(TT 없음). 외부 풀에서 온
    종목은 TT 를 한 번도 통과하지 않은 채 매수될 수 있고, 그 종목들만 `D` 로
    매매된다 — `D` 는 무작위 10종목 뽑기를 못 넘은 arm 이다(p=1.0000).
    """
    from strategies.minervini_volume_dryup.strategy import MinerviniVolumeDryupStrategy

    assert MinerviniVolumeDryupStrategy.accepts_volume_fallback is False


def test_entry_recheck_does_not_include_trend_template():
    """위 테스트의 «전제»를 고정한다 — 이게 바뀌면 위 결론도 다시 봐야 한다.

    `evaluate_entry` 가 TT 를 «보지 않는다»는 사실이 `accepts_volume_fallback=False`
    의 근거다. 나중에 TT 가 매수 경로에도 들어오면 이 테스트가 깨지면서
    「이제 외부 후보를 받아도 되는가」를 다시 묻게 된다.
    """
    import inspect

    from strategies.minervini_volume_dryup.strategy import MinerviniVolumeDryupStrategy

    src = inspect.getsource(MinerviniVolumeDryupStrategy.evaluate_entry)
    assert "rule_volume_dryup" in src
    assert "trend_template" not in src, (
        "매수 경로에 TT 가 생겼다 — accepts_volume_fallback 재검토 필요"
    )
