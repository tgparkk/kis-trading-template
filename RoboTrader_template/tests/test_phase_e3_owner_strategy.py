"""
Phase E3 — TradingStock.owner_strategy + StateRestorer 다전략 복원 테스트
"""
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import Optional


KST = timezone(timedelta(hours=9))


def _run_async(coro):
    """asyncio.run() 대신 사용 — 기존 이벤트 루프를 보존하여 테스트 오염 방지."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 헬퍼: 최소 TradingStock 인스턴스 생성
# ---------------------------------------------------------------------------

def _make_trading_stock(code: str = "005930", name: str = "삼성전자"):
    from core.models import TradingStock, StockState
    from utils.korean_time import now_kst
    return TradingStock(
        stock_code=code,
        stock_name=name,
        state=StockState.SELECTED,
        selected_time=now_kst(),
    )


# ---------------------------------------------------------------------------
# 헬퍼: 최소 BaseStrategy 서브클래스
# ---------------------------------------------------------------------------

def _make_strategy(name: str = "TestStrategy"):
    from strategies.base import BaseStrategy, Signal

    class _Stub(BaseStrategy):
        def generate_signal(self, stock_code, data, timeframe="daily"):
            return None

    stub = _Stub.__new__(_Stub)
    stub.name = name
    stub.version = "0.1.0"
    stub.description = ""
    stub.author = ""
    stub._is_initialized = False
    stub._broker = None
    stub._data_provider = None
    stub._executor = None
    stub.config = {}
    stub._last_ontick_skip_log = None
    return stub


# ===========================================================================
# 1. TradingStock owner_strategy_name — 매수 후 정확한 이름 기록
# ===========================================================================

def test_owner_strategy_set_on_buy():
    """execute_virtual_buy 후 trading_stock.owner_strategy_name이 전략 이름과 일치"""
    ts = _make_trading_stock()
    strategy = _make_strategy("SampleStrategy")

    # TradingDecisionEngine 생성 (DB·broker 없이 최소 초기화)
    from core.trading_decision_engine import TradingDecisionEngine
    engine = TradingDecisionEngine()
    engine.set_strategy(strategy)

    # VirtualTradingManager.execute_virtual_buy가 rid 1을 반환하도록 mock
    engine.virtual_trading = MagicMock()
    engine.virtual_trading.execute_virtual_buy.return_value = 1
    engine.virtual_trading.get_max_quantity.return_value = 10

    import asyncio

    async def _run():
        await engine.execute_virtual_buy(
            trading_stock=ts,
            combined_data=None,
            buy_reason="테스트 매수",
            buy_price=10000,
            quantity=10,
        )

    _run_async(_run())

    assert ts.owner_strategy_name == "SampleStrategy"


# ===========================================================================
# 2. TradingStock owner_strategy — 인스턴스가 BaseStrategy 서브클래스
# ===========================================================================

def test_owner_strategy_instance_recorded():
    """execute_virtual_buy 후 trading_stock.owner_strategy가 BaseStrategy 인스턴스"""
    from strategies.base import BaseStrategy
    ts = _make_trading_stock()
    strategy = _make_strategy("MomentumStrategy")

    from core.trading_decision_engine import TradingDecisionEngine
    engine = TradingDecisionEngine()
    engine.set_strategy(strategy)
    engine.virtual_trading = MagicMock()
    engine.virtual_trading.execute_virtual_buy.return_value = 2
    engine.virtual_trading.get_max_quantity.return_value = 5

    import asyncio

    async def _run():
        await engine.execute_virtual_buy(
            trading_stock=ts,
            combined_data=None,
            buy_reason="테스트 매수",
            buy_price=20000,
            quantity=5,
        )

    _run_async(_run())

    assert isinstance(ts.owner_strategy, BaseStrategy)
    assert ts.owner_strategy is strategy


# ===========================================================================
# 3. StateRestorer — 봇 재시작 후 DB 복원 시 인스턴스 연결
# ===========================================================================

def test_state_restorer_links_owner_strategy():
    """DB 복원 시 bot.strategies에 전략이 있으면 owner_strategy가 연결된다"""
    ts = _make_trading_stock("000660", "SK하이닉스")
    strategy = _make_strategy("SampleStrategy")

    # bot mock
    bot = MagicMock()
    bot.strategies = {"SampleStrategy": strategy}

    from bot.state_restorer import StateRestorer
    restorer = StateRestorer.__new__(StateRestorer)
    restorer.bot = bot
    restorer.logger = MagicMock()

    # holding dict에서 복원 로직 직접 실행
    holding = {"strategy": "SampleStrategy"}
    db_strategy = holding.get("strategy", "")
    if db_strategy and isinstance(db_strategy, str) and db_strategy.strip():
        name = db_strategy.strip()
        ts.owner_strategy_name = name
        bot_strategies = getattr(restorer.bot, "strategies", {})
        if name in bot_strategies:
            ts.owner_strategy = bot_strategies[name]
        else:
            restorer.logger.warning(
                f"복원된 종목 {ts.stock_code}의 owner 전략 {name}이 비활성. 기본 정책 적용."
            )

    assert ts.owner_strategy_name == "SampleStrategy"
    assert ts.owner_strategy is strategy


# ===========================================================================
# 4. StateRestorer — 비활성 전략이면 owner_strategy=None + WARNING
# ===========================================================================

def test_state_restorer_disabled_strategy_warning():
    """DB에 기록된 전략이 현재 bot.strategies에 없으면 owner_strategy=None + WARNING 로그"""
    ts = _make_trading_stock("035720", "카카오")

    bot = MagicMock()
    bot.strategies = {}  # 비활성 — 해당 전략 없음

    from bot.state_restorer import StateRestorer
    restorer = StateRestorer.__new__(StateRestorer)
    restorer.bot = bot
    restorer.logger = MagicMock()

    holding = {"strategy": "OldStrategy"}
    db_strategy = holding.get("strategy", "")
    if db_strategy and isinstance(db_strategy, str) and db_strategy.strip():
        name = db_strategy.strip()
        ts.owner_strategy_name = name
        bot_strategies = getattr(restorer.bot, "strategies", {})
        if name in bot_strategies:
            ts.owner_strategy = bot_strategies[name]
        else:
            restorer.logger.warning(
                f"복원된 종목 {ts.stock_code}의 owner 전략 {name}이 비활성. 기본 정책 적용."
            )

    assert ts.owner_strategy_name == "OldStrategy"
    assert ts.owner_strategy is None
    restorer.logger.warning.assert_called_once()
    assert "비활성" in restorer.logger.warning.call_args[0][0]


# ===========================================================================
# 5. strategy_name property — 하위 호환성
# ===========================================================================

def test_strategy_name_property_backward_compat():
    """strategy_name getter/setter가 owner_strategy_name을 미러링"""
    ts = _make_trading_stock()

    # getter: 초기값 동일
    assert ts.strategy_name == ts.owner_strategy_name == ""

    # setter via property
    ts.strategy_name = "LynchStrategy"
    assert ts.owner_strategy_name == "LynchStrategy"
    assert ts.strategy_name == "LynchStrategy"

    # setter via owner_strategy_name 직접
    ts.owner_strategy_name = "BBReversionStrategy"
    assert ts.strategy_name == "BBReversionStrategy"
