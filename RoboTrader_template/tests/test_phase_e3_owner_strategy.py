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
# 3. strategy_name property — 하위 호환성
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


# ===========================================================================
# 4. StateRestorer — DB 클래스명 / bot_strategies 폴더명 불일치 양방향 호환
# ===========================================================================

def _make_restorer_with_strategies(strategies_dict: dict):
    """StateRestorer 인스턴스를 최소 mock으로 생성."""
    from bot.state_restorer import StateRestorer
    restorer = StateRestorer.__new__(StateRestorer)
    restorer.strategies = strategies_dict
    return restorer


def test_state_restorer_class_name_matches_when_key_is_folder_name():
    """DB에 클래스명("SampleStrategy")이 저장됐을 때
    bot_strategies 키가 폴더명("sample")이어도 owner_strategy가 복원된다.

    시나리오 ①: 클래스명 2차 매핑 경로를 검증.
    """
    strategy = _make_strategy("SampleStrategy")  # strategy.name = "SampleStrategy"
    restorer = _make_restorer_with_strategies({"sample": strategy})

    matched = restorer._resolve_owner_strategy("SampleStrategy")  # DB 값 = 클래스명

    assert matched is strategy, "클래스명으로 보조 매핑에서 찾아야 한다"


def test_state_restorer_folder_name_still_works_for_legacy_records():
    """과거 레코드에 폴더명("sample")이 남아 있을 때도 인스턴스가 반환된다.

    시나리오 ②: 폴더명 1차 조회 경로를 검증.
    """
    strategy = _make_strategy("SampleStrategy")
    restorer = _make_restorer_with_strategies({"sample": strategy})

    matched = restorer._resolve_owner_strategy("sample")  # DB 값 = 폴더명 (레거시)

    assert matched is strategy, "폴더명 키로 직접 조회돼야 한다"


def test_state_restorer_both_lookups_fail_returns_none():
    """폴더명·클래스명 모두 불일치 시 None을 반환한다.

    시나리오 ③: 비활성 전략 분기 검증.
    """
    strategy = _make_strategy("MomentumStrategy")
    restorer = _make_restorer_with_strategies({"momentum": strategy})

    matched = restorer._resolve_owner_strategy("ObsoleteStrategy")

    assert matched is None, "미등록 전략이면 None을 반환해야 한다"


def test_state_restorer_class_name_key_also_works():
    """bot_strategies 키가 클래스명인 경우(폴더명=클래스명 동일 환경)에도 동작한다.

    시나리오 ④: 1차 조회(폴더명 = 클래스명)에서 바로 성공하는 경로를 검증.
    """
    strategy = _make_strategy("LynchStrategy")
    restorer = _make_restorer_with_strategies({"LynchStrategy": strategy})

    matched = restorer._resolve_owner_strategy("LynchStrategy")

    assert matched is strategy
