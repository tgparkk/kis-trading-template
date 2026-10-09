"""장 시작/마감 전략 콜백이 로드된 전략 «전부»에 간다 (2026-10-09 · fix/real-flow-7).

10-08 페이퍼 로그: 「장 마감 — 매수 N건」 줄이 elder(첫 전략) 1줄뿐 — main.py 가 `self.strategy`
(첫 전략)만 불렀다. 실전 인스턴스(daytrading 단일 전략)는 원래 첫 전략이라 동작 변화 0.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_modules  # noqa: F401,E402

import pytest  # noqa: E402


class _Strat:
    def __init__(self, name, fail=False):
        self.name = name
        self.fail = fail
        self.opened = 0
        self.closed = 0

    def on_market_open(self):
        self.opened += 1
        if self.fail:
            raise RuntimeError("boom")

    def on_market_close(self):
        self.closed += 1
        if self.fail:
            raise RuntimeError("boom")


def _bot(strats):
    from main import DayTradingBot
    bot = DayTradingBot.__new__(DayTradingBot)       # 무거운 초기화 없이 콜백 메서드만 시험
    bot.logger = MagicMock()
    bot.strategies = {s.name: s for s in strats}
    bot.strategy = strats[0] if strats else None
    return bot


@pytest.mark.asyncio
@pytest.mark.parametrize("method,attr", [("_call_strategy_market_close", "closed"),
                                         ("_call_strategy_market_open", "opened")])
async def test_callback_reaches_every_loaded_strategy(method, attr):
    strats = [_Strat("elder_ema_pullback"), _Strat("book_envelope_200d"), _Strat("daytrading_3methods_breakout")]
    await getattr(_bot(strats), method)()
    assert [getattr(s, attr) for s in strats] == [1, 1, 1], "첫 전략만 불렀다"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,attr", [("_call_strategy_market_close", "closed"),
                                         ("_call_strategy_market_open", "opened")])
async def test_one_strategy_failure_does_not_skip_the_rest(method, attr):
    strats = [_Strat("a", fail=True), _Strat("b"), _Strat("c", fail=True), _Strat("d")]
    bot = _bot(strats)
    await getattr(bot, method)()
    assert [getattr(s, attr) for s in strats] == [1, 1, 1, 1]
    assert bot.logger.warning.call_count == 2


@pytest.mark.asyncio
async def test_single_strategy_instance_unchanged_and_none_is_noop():
    only = _Strat("daytrading_3methods_breakout")
    bot = _bot([only])
    await bot._call_strategy_market_open()
    await bot._call_strategy_market_close()
    assert (only.opened, only.closed) == (1, 1)
    empty = _bot([])
    await empty._call_strategy_market_open()
    await empty._call_strategy_market_close()
    empty.logger.warning.assert_not_called()


def test_paper_strategies_market_close_changes_no_state():
    """페이퍼 8전략(config/trading_config.json)의 on_market_close 는 로그만 — 이제 전부 불러도 상태 변화 0
    (positions·daily_trades·속성 집합 불변)."""
    import copy
    import json
    from strategies.config import StrategyLoader
    from utils.korean_time import now_kst
    root = Path(__file__).resolve().parent.parent
    cfg = json.loads((root / "config" / "trading_config.json").read_text(encoding="utf-8"))
    names = [s["name"] for s in cfg.get("strategies", []) if s.get("enabled", True)]
    assert len(names) == 8
    for name in names:
        st = StrategyLoader.load_strategy(name)
        assert st.on_init(broker=None, data_provider=None, executor=None)
        st.positions["005930"] = {"entry_price": 70000.0, "entry_time": now_kst(), "quantity": 10}
        st.daily_trades = 2
        before_positions = copy.deepcopy(st.positions)
        before_attrs = set(vars(st))
        st.on_market_close()
        assert st.positions == before_positions, name
        assert st.daily_trades == 2, name
        assert set(vars(st)) == before_attrs, name
