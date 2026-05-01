"""
Phase E5 — LiquidationHandler 전략별 EOD 청산 분리 테스트

- intraday 전략 보유 종목은 EOD 청산
- swing 전략 보유 종목은 EOD 스킵
- owner_strategy 우선 참조
- owner_strategy=None이면 bot.decision_engine.strategy fallback
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _run_async(coro):
    """asyncio.run() 대신 사용 — 기존 이벤트 루프를 보존하여 테스트 오염 방지."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 헬퍼: BaseStrategy 스텁 생성
# ---------------------------------------------------------------------------

def _make_strategy(name: str = "TestStrategy", holding_period: str = "intraday"):
    """최소 BaseStrategy 스텁. holding_period로 should_liquidate_eod 동작 결정."""
    from strategies.base import BaseStrategy

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
    stub.holding_period = holding_period
    return stub


# ---------------------------------------------------------------------------
# 헬퍼: 최소 TradingStock + position 설정
# ---------------------------------------------------------------------------

def _make_trading_stock(code: str = "005930", name: str = "삼성전자", quantity: int = 10,
                         avg_price: float = 70000.0, owner_strategy=None):
    from core.models import TradingStock, StockState
    from utils.korean_time import now_kst

    ts = TradingStock(
        stock_code=code,
        stock_name=name,
        state=StockState.POSITIONED,
        selected_time=now_kst(),
    )
    # position mock
    pos = MagicMock()
    pos.quantity = quantity
    pos.avg_price = avg_price
    ts.position = pos
    ts.owner_strategy = owner_strategy
    return ts


# ---------------------------------------------------------------------------
# 헬퍼: LiquidationHandler bot mock 구성
# ---------------------------------------------------------------------------

def _make_handler(positioned_stocks, global_strategy=None, is_virtual: bool = True):
    from bot.liquidation_handler import LiquidationHandler

    bot = MagicMock()
    bot.trading_manager.get_stocks_by_state.return_value = positioned_stocks
    bot.trading_manager.move_to_sell_candidate.return_value = True
    bot.trading_manager.execute_sell_order = AsyncMock()
    bot.decision_engine.strategy = global_strategy
    bot.decision_engine.is_virtual_mode = is_virtual
    bot.decision_engine.execute_virtual_sell = AsyncMock(return_value=True)
    bot.fund_manager.release_investment = MagicMock()
    bot.fund_manager.adjust_pnl = MagicMock()
    bot.fund_manager.remove_position = MagicMock()
    bot.intraday_manager.get_combined_chart_data.return_value = None
    bot.broker.get_current_price.return_value = 70000.0

    handler = LiquidationHandler.__new__(LiquidationHandler)
    handler.bot = bot
    handler.logger = MagicMock()
    handler._last_eod_liquidation_date = None
    handler._eod_failed_stocks = set()
    handler._eod_retry_count = 0
    handler._snapshot_done_date = None
    return handler


# ===========================================================================
# 1. intraday 전략 보유 종목 EOD 청산
# ===========================================================================

def test_eod_liquidates_intraday_holding():
    """holding_period=intraday 전략의 종목은 EOD 청산이 실행된다."""
    intraday_strategy = _make_strategy("IntradayStrat", holding_period="intraday")
    ts = _make_trading_stock(code="005930", owner_strategy=intraday_strategy)

    handler = _make_handler([ts], global_strategy=None)

    with patch.object(handler, 'run_screener_snapshot_hook', new_callable=AsyncMock):
        _run_async(handler.execute_end_of_day_liquidation())

    # 가상매도 호출 여부로 청산 실행 확인
    handler.bot.decision_engine.execute_virtual_sell.assert_called_once()


# ===========================================================================
# 2. swing 전략 보유 종목 EOD 스킵
# ===========================================================================

def test_eod_skips_swing_holding():
    """holding_period=swing 전략의 종목은 EOD 청산을 건너뛴다."""
    swing_strategy = _make_strategy("SwingStrat", holding_period="swing")
    ts = _make_trading_stock(code="000660", owner_strategy=swing_strategy)

    handler = _make_handler([ts], global_strategy=None)

    with patch.object(handler, 'run_screener_snapshot_hook', new_callable=AsyncMock):
        _run_async(handler.execute_end_of_day_liquidation())

    # 가상매도 미호출 — swing 스킵
    handler.bot.decision_engine.execute_virtual_sell.assert_not_called()

    # 스킵 로그 확인 (전략 이름 포함)
    info_calls = [str(c) for c in handler.logger.info.call_args_list]
    assert any("SwingStrat" in c and "스킵" in c for c in info_calls)


# ===========================================================================
# 3. owner_strategy 우선 참조 (global과 다른 전략이 owner에 있을 때)
# ===========================================================================

def test_eod_uses_owner_strategy_first():
    """종목의 owner_strategy가 global strategy보다 우선 참조된다."""
    # owner=swing → 스킵
    swing_owner = _make_strategy("OwnerSwing", holding_period="swing")
    # global=intraday → 청산 찬성
    global_intraday = _make_strategy("GlobalIntraday", holding_period="intraday")

    ts = _make_trading_stock(code="035420", owner_strategy=swing_owner)
    handler = _make_handler([ts], global_strategy=global_intraday)

    with patch.object(handler, 'run_screener_snapshot_hook', new_callable=AsyncMock):
        _run_async(handler.execute_end_of_day_liquidation())

    # owner_strategy(swing)를 따라 스킵 — 가상매도 미호출
    handler.bot.decision_engine.execute_virtual_sell.assert_not_called()

    info_calls = [str(c) for c in handler.logger.info.call_args_list]
    assert any("OwnerSwing" in c for c in info_calls)


# ===========================================================================
# 4. owner_strategy=None이면 bot.decision_engine.strategy fallback
# ===========================================================================

def test_eod_fallback_to_global_strategy():
    """owner_strategy가 None이면 bot.decision_engine.strategy로 fallback한다."""
    # owner=None, global=swing → 스킵
    global_swing = _make_strategy("GlobalSwing", holding_period="swing")
    ts = _make_trading_stock(code="051910", owner_strategy=None)

    handler = _make_handler([ts], global_strategy=global_swing)

    with patch.object(handler, 'run_screener_snapshot_hook', new_callable=AsyncMock):
        _run_async(handler.execute_end_of_day_liquidation())

    # global swing fallback → 스킵
    handler.bot.decision_engine.execute_virtual_sell.assert_not_called()

    info_calls = [str(c) for c in handler.logger.info.call_args_list]
    assert any("GlobalSwing" in c for c in info_calls)
