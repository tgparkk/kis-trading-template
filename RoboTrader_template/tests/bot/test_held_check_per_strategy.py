"""analyze_buy_decision «보유 중» 가드는 전략별이어야 한다 (2026-10-19 결함).

실례 10-19: book_envelope_200d 가 09:06:55 396300 매수 → daytrading_3methods_breakout
의 396300 매수 신호가 09:19:58·09:26:30 「보유 중인 종목 매수 신호 무시」 로 막혔다.
가드가 POSITIONED 슬롯을 «종목코드로만» 비교했기 때문이다.

사장님 정의: 전략이 다르면 각각 사야 정상 · 같은 전략이 이미 들고 있으면 막는 것은 정상.
owner 표기는 폴더키(복원)/클래스명(라이브 매수) 두 가지라 둘 다 시험한다.
"""
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

from core.models import Position, StockState, TradingStock
from core.trading.stock_state_manager import StockStateManager

KST = timezone(timedelta(hours=9))
CODE = "396300"

DT_KEY = "daytrading_3methods_breakout"
DT_CLASS = "DayTrading3MethodsBreakoutStrategy"
BE_KEY = "book_envelope_200d"
BE_CLASS = "BookEnvelope200dStrategy"


def _strategy(name):
    s = Mock()
    s.name = name
    return s


def _slot(owner, state):
    ts = TradingStock(
        stock_code=CODE, stock_name="테스트", state=state,
        selected_time=datetime.now(KST), owner_strategy_name=owner,
    )
    if state == StockState.POSITIONED:
        ts.position = Position(stock_code=CODE, quantity=10, avg_price=10000)
    return ts


def _make_bot(mgr):
    strategies = {DT_KEY: _strategy(DT_CLASS), BE_KEY: _strategy(BE_CLASS)}
    by_name = {}
    for key, inst in strategies.items():
        by_name[key] = inst
        by_name[inst.name] = inst

    bot = Mock()
    bot.strategies = strategies
    bot.trading_manager.get_stocks_by_state = mgr.get_stocks_by_state
    bot.trading_manager.get_trading_stock = mgr.get_trading_stock
    bot.trading_manager.resolve_owner_strategy = Mock(side_effect=lambda n: by_name.get(n))
    bot.trading_manager._change_stock_state = Mock()
    bot.db_manager.price_repo.get_daily_prices.return_value = pd.DataFrame(
        {"date": [f"2024{i:04d}" for i in range(30)], "close": [10000] * 30}
    )
    bot.decision_engine.set_fund_manager = Mock()
    bot.decision_engine.is_virtual_mode = True
    bot.decision_engine.analyze_buy_decision = AsyncMock(return_value=(
        True, "돌파", {"buy_price": 10000, "quantity": 10, "max_buy_amount": 100000},
    ))
    bot.decision_engine.execute_virtual_buy = AsyncMock(return_value=True)
    bot.fund_manager.reserve_funds.return_value = True
    return bot


def _run_buy(other_slots, own_slot, strategy_name=DT_KEY):
    from bot.trading_analyzer import TradingAnalyzer
    mgr = StockStateManager()
    for s in other_slots:
        assert mgr.register_stock(s)
    assert mgr.register_stock(own_slot)
    bot = _make_bot(mgr)
    analyzer = TradingAnalyzer(bot)
    return bot, analyzer, mgr


async def _buy_capturing(analyzer, stock, caplog, **kw):
    """setup_logger 가 propagate=False 라 caplog 가 못 본다 — 한시적으로 켠다
    (tests/bot/test_buy_rejection_visibility.py 와 같은 방식)."""
    analyzer.logger._logger.propagate = True
    try:
        with caplog.at_level(logging.DEBUG, logger=analyzer.logger._logger.name):
            return await analyzer.analyze_buy_decision(stock, **kw)
    finally:
        analyzer.logger._logger.propagate = False


# ---------------------------------------------------------------------------
# 다른 전략 보유 → 매수 진행
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("other_owner", [BE_CLASS, BE_KEY])
async def test_other_strategy_holding_does_not_block_buy(other_owner, caplog):
    """book_envelope 이 POSITIONED 로 보유 중이어도 daytrading 은 자기 슬롯으로 산다."""
    other = _slot(other_owner, StockState.POSITIONED)
    own = _slot(DT_KEY, StockState.SELECTED)
    bot, analyzer, _ = _run_buy([other], own)

    executed = await _buy_capturing(analyzer, own, caplog, strategy_name=DT_KEY)

    assert executed is True
    bot.decision_engine.execute_virtual_buy.assert_awaited_once()
    # 매수 대상은 «자기» 슬롯 객체여야 한다(남의 슬롯 변이 금지)
    assert bot.decision_engine.execute_virtual_buy.await_args.args[0] is own
    assert "보유 중인 종목 매수 신호 무시" not in caplog.text


# ---------------------------------------------------------------------------
# 같은 전략 보유 → 차단 (종전 동작 유지)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("own_pos_owner", [DT_CLASS, DT_KEY])
async def test_same_strategy_holding_blocks_buy(own_pos_owner, caplog):
    """같은 전략이 이미 POSITIONED 면(표기가 클래스명이든 폴더키든) 막는다."""
    held = _slot(own_pos_owner, StockState.POSITIONED)
    other = _slot(BE_CLASS, StockState.POSITIONED)
    bot, analyzer, _ = _run_buy([other], held)

    executed = await _buy_capturing(analyzer, held, caplog, strategy_name=DT_KEY)

    assert not executed
    bot.decision_engine.execute_virtual_buy.assert_not_called()
    assert "보유 중인 종목 매수 신호 무시" in caplog.text


@pytest.mark.asyncio
async def test_same_strategy_holding_by_instance_blocks_buy():
    """owner 이름이 어느 표기와도 안 맞아도, 바인딩된 인스턴스가 같은 전략이면 막는다."""
    held = _slot("", StockState.POSITIONED)
    own = _slot(DT_KEY, StockState.SELECTED)
    bot, analyzer, _ = _run_buy([held], own)
    held.owner_strategy = bot.strategies[DT_KEY]

    executed = await analyzer.analyze_buy_decision(own, strategy_name=DT_KEY)

    assert not executed
    bot.decision_engine.execute_virtual_buy.assert_not_called()


# ---------------------------------------------------------------------------
# 신원 판정 불가 → 보수적으로 차단 (종전 동작)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("ghost_owner", ["GhostStrategy", ""])
async def test_unresolvable_owner_blocks_buy(ghost_owner):
    """보유 슬롯 owner 를 어느 전략으로도 해석 못 하면 종전처럼 막는다."""
    ghost = _slot(ghost_owner, StockState.POSITIONED)
    own = _slot(DT_KEY, StockState.SELECTED)
    bot, analyzer, _ = _run_buy([ghost], own)

    executed = await analyzer.analyze_buy_decision(own, strategy_name=DT_KEY)

    assert not executed
    bot.decision_engine.execute_virtual_buy.assert_not_called()


@pytest.mark.asyncio
async def test_no_strategy_name_keeps_code_only_block():
    """strategy_name 미전달(레거시 호출)은 판정 근거가 없어 종전처럼 코드만으로 막는다."""
    other = _slot(BE_CLASS, StockState.POSITIONED)
    own = _slot(DT_KEY, StockState.SELECTED)
    bot, analyzer, _ = _run_buy([other], own)

    executed = await analyzer.analyze_buy_decision(own)

    assert not executed
    bot.decision_engine.execute_virtual_buy.assert_not_called()


@pytest.mark.asyncio
async def test_other_code_positioned_does_not_block():
    """다른 종목 보유는 원래부터 무관."""
    from bot.trading_analyzer import TradingAnalyzer
    mgr = StockStateManager()
    other = TradingStock(stock_code="005930", stock_name="x", state=StockState.POSITIONED,
                         selected_time=datetime.now(KST), owner_strategy_name=DT_CLASS)
    own = _slot(DT_KEY, StockState.SELECTED)
    assert mgr.register_stock(other) and mgr.register_stock(own)
    bot = _make_bot(mgr)

    executed = await TradingAnalyzer(bot).analyze_buy_decision(own, strategy_name=DT_KEY)

    assert executed is True
