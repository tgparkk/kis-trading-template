"""
TradingContext 단위 테스트

core/trading_context.py의 13개 public 메서드 커버리지:
- is_market_open(), get_market_phase(), get_current_time()
- get_daily_data(), get_intraday_data(), get_current_price()
- get_selected_stocks(), get_positions()
- buy(), sell()
- get_available_funds(), get_max_buy_amount(), get_total_funds()
- log()
"""
import pytest
import asyncio
import pandas as pd
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from core.trading_context import TradingContext


# ============================================================================
# Fixtures
# ============================================================================

def _make_context(**overrides):
    """기본 Mock 의존성으로 TradingContext 생성"""
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


@pytest.fixture
def ctx():
    return _make_context()


# ============================================================================
# a) 시장 상태
# ============================================================================

class TestIsMarketOpen:
    def test_returns_true_when_market_is_open(self, ctx):
        with patch('core.trading_context.is_market_open', return_value=True):
            assert ctx.is_market_open() is True

    def test_returns_false_when_market_is_closed(self, ctx):
        with patch('core.trading_context.is_market_open', return_value=False):
            assert ctx.is_market_open() is False


class TestGetMarketPhase:
    def test_returns_phase_value_string(self, ctx):
        with patch('core.trading_context.MarketHours') as mock_hours:
            mock_phase = Mock()
            mock_phase.value = "TRADING"
            mock_hours.get_market_phase.return_value = mock_phase
            result = ctx.get_market_phase()
        assert result == "TRADING"


class TestGetCurrentTime:
    def test_returns_datetime_object(self, ctx):
        from datetime import datetime
        with patch('core.trading_context.now_kst') as mock_now:
            fake_time = datetime(2026, 3, 7, 10, 0, 0)
            mock_now.return_value = fake_time
            result = ctx.get_current_time()
        assert result == fake_time


# ============================================================================
# b) 데이터 조회
# ============================================================================

class TestGetDailyData:
    @pytest.mark.asyncio
    async def test_returns_dataframe_when_data_available(self):
        df = pd.DataFrame({'close': [70000, 71000]})
        db = Mock()
        db.price_repo = Mock()
        db.price_repo.get_daily_prices.return_value = df
        ctx = _make_context(db_manager=db)

        result = await ctx.get_daily_data("005930", days=30)

        assert result is not None
        assert len(result) == 2
        db.price_repo.get_daily_prices.assert_called_once_with("005930", days=30)

    @pytest.mark.asyncio
    async def test_returns_none_when_db_manager_is_none(self):
        ctx = _make_context(db_manager=None)
        result = await ctx.get_daily_data("005930")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_data_is_empty(self):
        db = Mock()
        db.price_repo = Mock()
        db.price_repo.get_daily_prices.return_value = pd.DataFrame()
        ctx = _make_context(db_manager=db)

        result = await ctx.get_daily_data("005930")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_db_raises_exception(self):
        db = Mock()
        db.price_repo = Mock()
        db.price_repo.get_daily_prices.side_effect = RuntimeError("DB error")
        ctx = _make_context(db_manager=db)

        result = await ctx.get_daily_data("005930")
        assert result is None


class TestGetIntradayData:
    @pytest.mark.asyncio
    async def test_returns_dataframe_when_data_available(self):
        df = pd.DataFrame({'close': [70000, 70500]})
        intraday = Mock()
        intraday.get_combined_chart_data.return_value = df
        ctx = _make_context(intraday_manager=intraday)

        result = await ctx.get_intraday_data("005930")

        assert result is not None
        intraday.get_combined_chart_data.assert_called_once_with("005930")

    @pytest.mark.asyncio
    async def test_returns_none_when_intraday_manager_is_none(self):
        ctx = _make_context(intraday_manager=None)
        result = await ctx.get_intraday_data("005930")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_data_is_empty(self):
        intraday = Mock()
        intraday.get_combined_chart_data.return_value = pd.DataFrame()
        ctx = _make_context(intraday_manager=intraday)

        result = await ctx.get_intraday_data("005930")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        intraday = Mock()
        intraday.get_combined_chart_data.side_effect = RuntimeError("fail")
        ctx = _make_context(intraday_manager=intraday)

        result = await ctx.get_intraday_data("005930")
        assert result is None


class TestGetCurrentPrice:
    @pytest.mark.asyncio
    async def test_returns_price_from_intraday_cache_first(self):
        intraday = Mock()
        intraday.get_cached_current_price.return_value = {'current_price': 71000}
        broker = Mock()
        ctx = _make_context(intraday_manager=intraday, broker=broker)

        result = await ctx.get_current_price("005930")

        assert result == 71000.0
        broker.get_current_price.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_broker_when_cache_is_empty(self):
        intraday = Mock()
        intraday.get_cached_current_price.return_value = {'current_price': 0}
        broker = Mock()
        broker.get_current_price.return_value = 72000
        ctx = _make_context(intraday_manager=intraday, broker=broker)

        result = await ctx.get_current_price("005930")

        assert result == 72000.0

    @pytest.mark.asyncio
    async def test_falls_back_to_broker_when_cache_returns_none(self):
        intraday = Mock()
        intraday.get_cached_current_price.return_value = None
        broker = Mock()
        broker.get_current_price.return_value = 69000
        ctx = _make_context(intraday_manager=intraday, broker=broker)

        result = await ctx.get_current_price("005930")

        assert result == 69000.0

    @pytest.mark.asyncio
    async def test_returns_none_when_both_sources_fail(self):
        intraday = Mock()
        intraday.get_cached_current_price.return_value = None
        broker = Mock()
        broker.get_current_price.return_value = None
        ctx = _make_context(intraday_manager=intraday, broker=broker)

        result = await ctx.get_current_price("005930")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        intraday = Mock()
        intraday.get_cached_current_price.side_effect = RuntimeError("fail")
        broker = Mock()
        broker.get_current_price.side_effect = RuntimeError("fail")
        ctx = _make_context(intraday_manager=intraday, broker=broker)

        result = await ctx.get_current_price("005930")

        assert result is None


# ============================================================================
# c) 종목 관리
# ============================================================================

class TestGetSelectedStocks:
    def test_returns_selected_stocks_list(self):
        from core.models import StockState
        trading_manager = Mock()
        trading_manager.get_stocks_by_state.return_value = [Mock(), Mock()]
        ctx = _make_context(trading_manager=trading_manager)

        result = ctx.get_selected_stocks()

        assert len(result) == 2
        trading_manager.get_stocks_by_state.assert_called_once_with(StockState.SELECTED)

    def test_returns_empty_list_on_exception(self):
        trading_manager = Mock()
        trading_manager.get_stocks_by_state.side_effect = RuntimeError("fail")
        ctx = _make_context(trading_manager=trading_manager)

        result = ctx.get_selected_stocks()

        assert result == []


class TestGetPositions:
    def test_returns_positioned_stocks(self):
        from core.models import StockState
        trading_manager = Mock()
        trading_manager.get_stocks_by_state.return_value = [Mock()]
        ctx = _make_context(trading_manager=trading_manager)

        result = ctx.get_positions()

        assert len(result) == 1
        trading_manager.get_stocks_by_state.assert_called_once_with(StockState.POSITIONED)

    def test_returns_empty_list_on_exception(self):
        trading_manager = Mock()
        trading_manager.get_stocks_by_state.side_effect = RuntimeError("fail")
        ctx = _make_context(trading_manager=trading_manager)

        result = ctx.get_positions()

        assert result == []


# ============================================================================
# d) 주문 — buy()
# ============================================================================

def _make_trading_stock_mock(prev_close=0):
    """buy()/sell() 경로의 prev_close 비교를 통과하는 TradingStock Mock"""
    stock = Mock()
    stock.prev_close = prev_close  # int이어야 <= 비교 통과
    stock.is_selling = False
    return stock


def _make_intraday_no_price():
    """get_current_price() 내부 캐시 조회가 None을 반환하는 intraday_manager Mock.
    이 경우 broker도 None을 반환하면 get_current_price()=None이 되어
    상/하한가 가드의 'if current_price and current_price > 0' 분기를 건너뜀."""
    intraday = Mock()
    intraday.get_cached_current_price.return_value = None
    return intraday


class TestBuy:
    # get_circuit_breaker_state는 buy() 내부 local import이므로
    # 패치 대상은 config.market_hours.get_circuit_breaker_state

    def _make_buy_ctx(self, cb_halted=False, vi_active=False,
                      is_crashing=False, daily_loss_hit=False,
                      trading_stock_override=None):
        """buy() 테스트용 컨텍스트 팩토리"""
        cb_state = Mock()
        cb_state.is_market_halted.return_value = cb_halted
        cb_state.is_vi_active.return_value = vi_active

        decision_engine = Mock()
        decision_engine.check_market_direction.return_value = (is_crashing, "폭락" if is_crashing else "")

        fund_manager = Mock()
        fund_manager.is_daily_loss_limit_hit.return_value = daily_loss_hit
        fund_manager.max_daily_loss_ratio = 0.02
        fund_manager._daily_realized_loss = 0

        # trading_stock_override=None means "stock not found"; use sentinel to distinguish
        if trading_stock_override is None:
            # default: a valid stock with prev_close=0 so upper-limit guard is skipped
            the_stock = _make_trading_stock_mock(prev_close=0)
        else:
            the_stock = trading_stock_override  # could be None for "not found" case

        trading_manager = Mock()
        trading_manager.get_trading_stock.return_value = the_stock

        trading_analyzer = AsyncMock()

        broker = Mock()
        broker.get_current_price.return_value = None  # 상한가 가드가 None 반환 시 건너뜀

        ctx = _make_context(
            decision_engine=decision_engine,
            fund_manager=fund_manager,
            trading_manager=trading_manager,
            trading_analyzer=trading_analyzer,
            intraday_manager=_make_intraday_no_price(),
            broker=broker,
        )

        return ctx, cb_state, trading_analyzer

    @pytest.mark.asyncio
    async def test_returns_stock_code_on_successful_buy(self):
        ctx, cb_state, analyzer = self._make_buy_ctx()
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930")
        assert result == "005930"
        analyzer.analyze_buy_decision.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_circuit_breaker_is_halted(self):
        ctx, cb_state, analyzer = self._make_buy_ctx(cb_halted=True)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930")
        assert result is None
        analyzer.analyze_buy_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_market_is_crashing(self):
        ctx, cb_state, analyzer = self._make_buy_ctx(is_crashing=True)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930")
        assert result is None
        analyzer.analyze_buy_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_trading_stock_not_found(self):
        # trading_stock_override=None (the sentinel): get_trading_stock returns None
        ctx, cb_state, analyzer = self._make_buy_ctx()
        ctx._trading_manager.get_trading_stock.return_value = None
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930")
        assert result is None
        analyzer.analyze_buy_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_vi_is_active(self):
        ctx, cb_state, analyzer = self._make_buy_ctx(vi_active=True)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930")
        assert result is None
        analyzer.analyze_buy_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_daily_loss_limit_hit(self):
        ctx, cb_state, analyzer = self._make_buy_ctx(daily_loss_hit=True)
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930")
        assert result is None
        analyzer.analyze_buy_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_signal_parameter_to_analyzer(self):
        ctx, cb_state, analyzer = self._make_buy_ctx()
        signal = Mock()
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            await ctx.buy("005930", signal=signal)
        _, call_kwargs = analyzer.analyze_buy_decision.call_args
        assert call_kwargs.get('signal') is signal

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        ctx, cb_state, analyzer = self._make_buy_ctx()
        analyzer.analyze_buy_decision.side_effect = RuntimeError("order failed")
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state):
            result = await ctx.buy("005930")
        assert result is None


# ============================================================================
# d) 주문 — sell()
# ============================================================================

class TestSell:
    @pytest.mark.asyncio
    async def test_returns_stock_code_on_successful_sell(self):
        # prev_close=0 so the lower-limit guard branch is skipped entirely
        trading_stock = _make_trading_stock_mock(prev_close=0)
        trading_manager = Mock()
        trading_manager.get_trading_stock.return_value = trading_stock
        trading_analyzer = AsyncMock()
        broker = Mock()
        broker.get_current_price.return_value = None
        ctx = _make_context(trading_manager=trading_manager,
                            trading_analyzer=trading_analyzer,
                            intraday_manager=_make_intraday_no_price(),
                            broker=broker)

        result = await ctx.sell("005930")

        assert result == "005930"
        trading_analyzer.analyze_sell_decision.assert_awaited_once_with(trading_stock)

    @pytest.mark.asyncio
    async def test_returns_none_when_trading_stock_not_found(self):
        trading_manager = Mock()
        trading_manager.get_trading_stock.return_value = None
        trading_analyzer = AsyncMock()
        ctx = _make_context(trading_manager=trading_manager,
                            trading_analyzer=trading_analyzer)

        result = await ctx.sell("005930")

        assert result is None
        trading_analyzer.analyze_sell_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_already_selling(self):
        trading_stock = _make_trading_stock_mock(prev_close=0)
        trading_stock.is_selling = True
        trading_manager = Mock()
        trading_manager.get_trading_stock.return_value = trading_stock
        trading_analyzer = AsyncMock()
        # is_selling=True causes early return before get_current_price is reached
        ctx = _make_context(trading_manager=trading_manager,
                            trading_analyzer=trading_analyzer)

        result = await ctx.sell("005930")

        assert result is None
        trading_analyzer.analyze_sell_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        trading_stock = _make_trading_stock_mock(prev_close=0)
        trading_manager = Mock()
        trading_manager.get_trading_stock.return_value = trading_stock
        trading_analyzer = AsyncMock()
        trading_analyzer.analyze_sell_decision.side_effect = RuntimeError("sell error")
        broker = Mock()
        broker.get_current_price.return_value = None
        ctx = _make_context(trading_manager=trading_manager,
                            trading_analyzer=trading_analyzer,
                            intraday_manager=_make_intraday_no_price(),
                            broker=broker)

        result = await ctx.sell("005930")

        assert result is None


# ============================================================================
# e) 자금
# ============================================================================

class TestGetAvailableFunds:
    def test_returns_available_funds_from_fund_manager(self):
        fund_manager = Mock()
        fund_manager.available_funds = 5_000_000.0
        ctx = _make_context(fund_manager=fund_manager)

        assert ctx.get_available_funds() == 5_000_000.0

    def test_returns_zero_when_fund_manager_is_none(self):
        ctx = _make_context(fund_manager=None)
        assert ctx.get_available_funds() == 0.0

    def test_returns_zero_on_exception(self):
        fund_manager = Mock()
        type(fund_manager).available_funds = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("err"))
        )
        ctx = _make_context(fund_manager=fund_manager)
        assert ctx.get_available_funds() == 0.0


class TestGetMaxBuyAmount:
    def test_returns_max_buy_amount_for_stock(self):
        fund_manager = Mock()
        fund_manager.get_max_buy_amount.return_value = 900_000.0
        ctx = _make_context(fund_manager=fund_manager)

        result = ctx.get_max_buy_amount("005930")

        assert result == 900_000.0
        fund_manager.get_max_buy_amount.assert_called_once_with("005930")

    def test_returns_zero_when_fund_manager_is_none(self):
        ctx = _make_context(fund_manager=None)
        assert ctx.get_max_buy_amount("005930") == 0.0

    def test_returns_zero_on_exception(self):
        fund_manager = Mock()
        fund_manager.get_max_buy_amount.side_effect = RuntimeError("err")
        ctx = _make_context(fund_manager=fund_manager)
        assert ctx.get_max_buy_amount("005930") == 0.0


class TestGetTotalFunds:
    def test_returns_total_funds_from_fund_manager(self):
        fund_manager = Mock()
        fund_manager.total_funds = 10_000_000.0
        ctx = _make_context(fund_manager=fund_manager)

        assert ctx.get_total_funds() == 10_000_000.0

    def test_returns_zero_when_fund_manager_is_none(self):
        ctx = _make_context(fund_manager=None)
        assert ctx.get_total_funds() == 0.0


# ============================================================================
# f) 유틸리티 — log()
# ============================================================================

class TestLog:
    def test_log_info_level_by_default(self, ctx):
        with patch.object(ctx.logger, 'info') as mock_info:
            ctx.log("테스트 메시지")
        mock_info.assert_called_once_with("테스트 메시지")

    def test_log_debug_level(self, ctx):
        with patch.object(ctx.logger, 'debug') as mock_debug:
            ctx.log("디버그 메시지", level="debug")
        mock_debug.assert_called_once_with("디버그 메시지")

    def test_log_warning_level(self, ctx):
        with patch.object(ctx.logger, 'warning') as mock_warn:
            ctx.log("경고 메시지", level="warning")
        mock_warn.assert_called_once_with("경고 메시지")

    def test_log_error_level(self, ctx):
        with patch.object(ctx.logger, 'error') as mock_err:
            ctx.log("에러 메시지", level="error")
        mock_err.assert_called_once_with("에러 메시지")

    def test_log_unknown_level_falls_back_to_info(self, ctx):
        with patch.object(ctx.logger, 'info') as mock_info:
            ctx.log("메시지", level="nonexistent")
        mock_info.assert_called_once_with("메시지")
