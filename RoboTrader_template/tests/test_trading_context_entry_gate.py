"""TradingContext.buy() 매수스톱(entry_min_price) 게이트 — 실행레이어 강제 (Task 2 / C).

근본: PR 3629d13이 elder Signal에 매수스톱(entry_min_price=전일고가+1틱)을 실었으나,
실행레이어 `TradingContext.buy()`가 그 값을 게이트로 쓰지 않아 현재가가 매수스톱
미도달인데도 주문 경로(analyze_buy_decision)로 진입했다(돌파 게이트 미작동).

설계: `ctx.buy()` 진입 검증부에서 signal.entry_min_price가 설정돼 있으면 실시간
현재가와 비교 — 현재가 < entry_min이면 주문 경로(analyze_buy_decision) 미진입(None).
백테스트 entry_mechanism="stop"(돌파 시에만 체결)과 정합.

보존: entry_min 미설정(None) Signal·signal 없는 호출은 무조건 통과(기존 동작 불변,
elder 외 전략 무영향).
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from core.trading_context import TradingContext
from strategies.base import Signal, SignalType


# ---------------------------------------------------------------------------
# Fixtures — test_trading_context.py의 TestBuy 패턴 재사용
# ---------------------------------------------------------------------------
def _make_context(**overrides):
    defaults = dict(
        trading_manager=Mock(),
        decision_engine=Mock(),
        fund_manager=Mock(),
        data_collector=Mock(),
        intraday_manager=Mock(),
        trading_analyzer=AsyncMock(),
        db_manager=Mock(),
        broker=Mock(),
        is_running_check=None,
    )
    defaults.update(overrides)
    return TradingContext(**defaults)


def _make_trading_stock_mock(prev_close=0):
    stock = Mock()
    stock.prev_close = prev_close
    stock.is_selling = False
    return stock


def _make_intraday_with_price(price):
    """get_cached_current_price가 현재가를 반환하는 intraday_manager Mock."""
    intraday = Mock()
    intraday.get_cached_current_price.return_value = {"current_price": price}
    return intraday


def _make_buy_ctx(current_price):
    """매수스톱 게이트 테스트용 컨텍스트 — 다른 가드는 전부 통과하도록 설정."""
    cb_state = Mock()
    cb_state.is_market_halted.return_value = False
    cb_state.is_vi_active.return_value = False

    decision_engine = Mock()
    decision_engine.check_market_direction.return_value = (False, "")
    decision_engine.check_regime_gate.return_value = (False, "")

    fund_manager = Mock()
    fund_manager.is_daily_loss_limit_hit.return_value = False
    fund_manager.max_daily_loss_ratio = 0.02
    fund_manager._daily_realized_loss = 0

    trading_manager = Mock()
    trading_manager.get_trading_stock.return_value = _make_trading_stock_mock(prev_close=0)
    trading_manager.stock_state_manager = None

    trading_analyzer = AsyncMock()
    trading_analyzer.analyze_buy_decision.return_value = True

    broker = Mock()
    broker.get_current_price.return_value = current_price

    ctx = _make_context(
        decision_engine=decision_engine,
        fund_manager=fund_manager,
        trading_manager=trading_manager,
        trading_analyzer=trading_analyzer,
        intraday_manager=_make_intraday_with_price(current_price),
        broker=broker,
    )
    return ctx, cb_state, trading_analyzer


def _buy_signal(entry_min=None):
    return Signal(
        signal_type=SignalType.BUY,
        stock_code="005930",
        confidence=60.0,
        entry_min_price=entry_min,
        reasons=["elder breakout"],
    )


@pytest.fixture(autouse=True)
def _patch_eod_not_time():
    with patch('config.market_hours.MarketHours.is_eod_liquidation_time', return_value=False):
        yield


# ---------------------------------------------------------------------------
# 게이트 동작
# ---------------------------------------------------------------------------
class TestEntryMinGate:

    @pytest.mark.asyncio
    async def test_buy_skipped_when_price_below_entry_min(self):
        """현재가(10,000) < 매수스톱(10,100) → 주문 미제출(None), analyze_buy_decision 미호출."""
        ctx, cb_state, analyzer = _make_buy_ctx(current_price=10_000)
        sig = _buy_signal(entry_min=10_100)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930", signal=sig)
        assert result is None, "현재가가 매수스톱 미도달이면 진입하지 않아야 함"
        analyzer.analyze_buy_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_buy_proceeds_when_price_at_entry_min(self):
        """현재가(10,100) == 매수스톱(10,100) → 정상 진입(돌파 성립)."""
        ctx, cb_state, analyzer = _make_buy_ctx(current_price=10_100)
        sig = _buy_signal(entry_min=10_100)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930", signal=sig)
        assert result == "005930"
        analyzer.analyze_buy_decision.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_buy_proceeds_when_price_above_entry_min(self):
        """현재가(10,200) > 매수스톱(10,100) → 정상 진입."""
        ctx, cb_state, analyzer = _make_buy_ctx(current_price=10_200)
        sig = _buy_signal(entry_min=10_100)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930", signal=sig)
        assert result == "005930"
        analyzer.analyze_buy_decision.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_buy_proceeds_when_entry_min_none(self):
        """entry_min 미설정 Signal(elder 외 전략) → 게이트 무영향, 기존 동작 보존."""
        ctx, cb_state, analyzer = _make_buy_ctx(current_price=10_000)
        sig = _buy_signal(entry_min=None)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930", signal=sig)
        assert result == "005930"
        analyzer.analyze_buy_decision.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_buy_proceeds_when_no_signal(self):
        """signal 없는 매수 호출 → 게이트 무영향(기존 동작 보존)."""
        ctx, cb_state, analyzer = _make_buy_ctx(current_price=10_000)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930")
        assert result == "005930"
        analyzer.analyze_buy_decision.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gate_skips_gracefully_when_price_unavailable(self):
        """실시간가 미확보(None) → 게이트는 막지 않고 통과(다운스트림 보류가 처리).

        현재가를 못 받으면 매수스톱 비교가 불가하므로 게이트는 보수적으로 통과시킨다.
        실제 진입 보류는 decision_engine._get_live_price(=None)가 담당(2026-06-15).
        """
        ctx, cb_state, analyzer = _make_buy_ctx(current_price=10_000)
        # 현재가 소스 전부 None
        ctx._intraday_manager.get_cached_current_price.return_value = None
        ctx._broker.get_current_price.return_value = None
        sig = _buy_signal(entry_min=10_100)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930", signal=sig)
        # 게이트가 막지 않음 → analyze_buy_decision까지 진입
        analyzer.analyze_buy_decision.assert_awaited_once()
        assert result == "005930"
