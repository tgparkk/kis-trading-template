"""기동 시 시장 매핑 프리로드 배선 — 활성화 선행조건 ①-4.

프리로드를 `BotInitializer` 에 두는 근거: 판정에 필요한 `regime_index` 는
`StrategyLoader.load_strategies`(strategies/config.py:449-452)가 전략 인스턴스
속성으로 심고, 그 로드는 `DayTradingBot.__init__`(main.py:134)에서 끝난다.
`initialize_system()`(main.py:267)은 그 뒤에 돌므로 `self.bot.strategies` 가
이미 채워져 있다 — `on_init()` 을 기다릴 필요가 없다.

⚠️ DB·네트워크 미접촉: `preload_market_mapping` 자체를 스텁으로 갈아끼운다.
   `test_preload_is_skipped_when_no_auto_strategy` 는 그 스텁이 받은
   `auto_active` 인자를 단언해, non-auto 상태에서 DB 조회가 일어나지 않음을
   호출 인자 수준에서 고정한다.
"""
import asyncio
import types

import pytest

import bot.initializer as initializer_mod
import core.regime.market_classifier as mc
from bot.initializer import BotInitializer


def _make_initializer(regime_indices, monkeypatch):
    """regime_index 만 다른 가짜 전략들로 초기화기를 만든다."""
    calls = []
    monkeypatch.setattr(
        mc, "preload_market_mapping",
        lambda auto_active=False: calls.append(auto_active) or 0,
    )
    strategies = {
        f"s{i}": types.SimpleNamespace(regime_index=ri)
        for i, ri in enumerate(regime_indices)
    }
    init = BotInitializer.__new__(BotInitializer)  # __init__ 우회(봇 전체 불필요)
    init.bot = types.SimpleNamespace(strategies=strategies)
    init.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    return init, calls


def test_preload_is_skipped_when_no_auto_strategy(monkeypatch):
    """현행 config(8전략 전부 non-auto) — 프리로드가 DB 를 건드리지 않는다."""
    init, calls = _make_initializer(
        ["KOSPI", "KOSPI", "KOSDAQ", "KOSPI", "both", "none"], monkeypatch)
    init._preload_market_mapping()
    assert calls == [False]


def test_preload_is_active_when_any_strategy_is_auto(monkeypatch):
    """한 전략만 auto 여도 매핑이 필요하다."""
    init, calls = _make_initializer(["KOSPI", "auto", "KOSDAQ"], monkeypatch)
    init._preload_market_mapping()
    assert calls == [True]


@pytest.mark.parametrize("value", [None, ""])
def test_missing_regime_index_is_not_auto(monkeypatch, value):
    """미설정 전략의 기본값은 both — auto 로 오인하면 안 된다
    (`_get_strategy_regime_settings` 규약과 일치)."""
    init, calls = _make_initializer([value], monkeypatch)
    init._preload_market_mapping()
    assert calls == [False]


def test_strategy_without_attribute_is_not_auto(monkeypatch):
    """regime_index 속성 자체가 없는 레거시 전략도 안전해야 한다."""
    init, calls = _make_initializer([], monkeypatch)
    init.bot.strategies = {"legacy": object()}
    init._preload_market_mapping()
    assert calls == [False]


def test_no_strategies_loaded_does_not_crash(monkeypatch):
    init, calls = _make_initializer([], monkeypatch)
    init.bot.strategies = {}
    init._preload_market_mapping()
    assert calls == [False]


def test_preload_failure_does_not_break_startup(monkeypatch):
    """프리로드는 편의 기능이다 — 실패해도 기동을 막으면 안 된다."""
    init, _ = _make_initializer(["auto"], monkeypatch)
    monkeypatch.setattr(
        mc, "preload_market_mapping",
        lambda auto_active=False: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    init._preload_market_mapping()  # 예외가 새어나오면 실패


# =========================================================================
# 실제 기동 시퀀스에 붙어 있는가 — 소스 문자열이 아니라 **런타임 호출**로 본다
#
# ⚠️ 이전 판(`inspect.getsource` 에 "_preload_market_mapping" 이 있는지)은
#    호출을 주석 처리해도 · `if False:` 안에 넣어도 · `return` 뒤 도달 불가
#    위치로 옮겨도 전부 통과했다(2026-08-04 실측). 잡히는 것은 이름 변경뿐이라
#    docstring 이 약속한 "안 부르면 무의미하다"를 정확히 못 지켰다.
# =========================================================================

class _AsyncStub:
    """await 가능한 외부 의존 스텁 — 호출을 공유 로그에 순서대로 남긴다."""

    def __init__(self, log, name, result=None):
        self._log = log
        self._name = name
        self._result = result

    async def __call__(self, *a, **k):
        self._log.append(self._name)
        return self._result


def _make_bootable_initializer(monkeypatch, *, broker_ok=True):
    """`initialize_system()` 의 외부 의존을 전부 스텁한 초기화기.

    스텁 대상 = `initialize_system` 이 실제로 건드리는 것 전부:
      · `MarketHours.get_today_info`  (모듈 전역 import — 휴장일 캐시 파일 접촉)
      · `get_market_status`           (모듈 전역 import — 동일)
      · `bot.broker.connect`          (KIS 네트워크)
      · `_initialize_fund_manager` 가 읽는 `decision_engine`/`fund_manager`
      · `bot.telegram.initialize`     (네트워크)
      · `bot.state_restoration_helper.restore_todays_candidates`  (DB)
      · `_preload_market_mapping`     ← 레코더로 교체(검증 대상)
    """
    log = []
    monkeypatch.setattr(
        initializer_mod, "MarketHours",
        types.SimpleNamespace(get_today_info=lambda market='KRX': f"[{market}] stub"),
    )
    monkeypatch.setattr(initializer_mod, "get_market_status", lambda: "pre_market")

    bot = types.SimpleNamespace(
        broker=types.SimpleNamespace(
            connect=_AsyncStub(log, "broker.connect", broker_ok)),
        telegram=types.SimpleNamespace(
            initialize=_AsyncStub(log, "telegram.initialize")),
        state_restoration_helper=types.SimpleNamespace(
            restore_todays_candidates=_AsyncStub(log, "restore_candidates")),
        decision_engine=types.SimpleNamespace(
            is_virtual_mode=True,
            virtual_trading=types.SimpleNamespace(
                get_virtual_balance=lambda: 1_000_000.0)),
        fund_manager=types.SimpleNamespace(
            update_total_funds=lambda v: log.append("fund.update")),
        strategies={},
    )

    init = BotInitializer.__new__(BotInitializer)  # __init__ 우회(봇 전체 불필요)
    init.bot = bot
    init.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    # 인스턴스 속성이 클래스 메서드를 가린다 — 실제 호출만 세는 레코더.
    init._preload_market_mapping = lambda: log.append("preload")
    return init, log


def test_initialize_system_actually_calls_preload(monkeypatch):
    """기동이 성공하면 프리로드가 **정확히 1회** 실제로 실행된다."""
    init, log = _make_bootable_initializer(monkeypatch)

    ok = asyncio.run(init.initialize_system())

    assert ok is True, "스텁 기동은 성공해야 한다(전제가 깨지면 아래 단언이 무의미)"
    assert log.count("preload") == 1, f"프리로드가 실행되지 않았다: {log}"


def test_preload_is_not_reached_when_startup_aborts_early(monkeypatch):
    """프리로드는 성공 경로의 마지막 단계다 — 기동이 실패로 끝나면 도달하지 않는다.

    무조건 실행되는 위치(예: 함수 최상단)로 옮기면 여기서 잡힌다.
    """
    init, log = _make_bootable_initializer(monkeypatch, broker_ok=False)

    ok = asyncio.run(init.initialize_system())

    assert ok is False
    assert "preload" not in log, f"API 초기화 실패 경로에서 프리로드가 돌았다: {log}"
