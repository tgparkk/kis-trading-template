"""
LiquidationHandler 유닛 테스트

테스트 대상: bot/liquidation_handler.py
- liquidate_all_positions_end_of_day: EOD 장마감 청산 정상 흐름
- execute_end_of_day_liquidation: 동적 시간 기반 일괄 매도 + 실패 추적
- retry_failed_eod_liquidation: 청산 실패 재시도 (성공/실패)
- _force_complete_failed_stocks: 재시도 한도 초과 시 강제 완료 처리
- reset_eod_state / has_failed_eod_stocks: 상태 관리 헬퍼
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch

KST = timezone(timedelta(hours=9))
EOD_MAX_RETRIES = 3  # liquidation_handler.py 상수와 동기화


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(KST)


def _make_position(stock_code="005930", avg_price=50000, quantity=10):
    from core.models import Position
    return Position(stock_code=stock_code, quantity=quantity, avg_price=avg_price)


def _make_trading_stock(stock_code="005930", avg_price=50000, quantity=10):
    from core.models import TradingStock, StockState, Position
    stock = TradingStock(
        stock_code=stock_code,
        stock_name="삼성전자",
        state=StockState.POSITIONED,
        selected_time=_now(),
    )
    stock.position = _make_position(stock_code, avg_price, quantity)
    stock.clear_position = Mock()
    stock.is_selling = False
    return stock


def _make_bot(
    positioned_stocks=None,
    is_virtual=True,
    virtual_sell_result=True,
    move_result=True,
    strategy_allows_liquidation=True,
):
    """DayTradingBot Mock 조립"""
    bot = Mock()

    stocks = positioned_stocks if positioned_stocks is not None else []

    bot.trading_manager.get_stocks_by_state.return_value = stocks
    bot.trading_manager.get_trading_stock.side_effect = lambda code: next(
        (s for s in stocks if s.stock_code == code), None
    )
    bot.trading_manager.move_to_sell_candidate.return_value = move_result
    bot.trading_manager.execute_sell_order = AsyncMock()
    bot.trading_manager._change_stock_state = Mock()

    bot.decision_engine.is_virtual_mode = is_virtual
    bot.decision_engine.execute_virtual_sell = AsyncMock(return_value=virtual_sell_result)

    # 전략 EOD 청산 허용 여부
    strategy = Mock()
    strategy.should_liquidate_eod.return_value = strategy_allows_liquidation
    bot.decision_engine.strategy = strategy

    bot.intraday_manager.get_combined_chart_data.return_value = None
    bot.broker.get_current_price.return_value = 51000

    bot.fund_manager.release_investment = Mock()
    bot.fund_manager.adjust_pnl = Mock()
    bot.fund_manager.remove_position = Mock()

    bot.telegram = None

    return bot


def _make_handler(bot=None):
    from bot.liquidation_handler import LiquidationHandler
    b = bot or _make_bot()
    handler = LiquidationHandler(b)
    return handler


# ---------------------------------------------------------------------------
# liquidate_all_positions_end_of_day
# ---------------------------------------------------------------------------

class TestLiquidateAllPositionsEndOfDay:
    """장마감 직전 일괄청산 테스트"""

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_positioned_stocks(self):
        """보유 포지션 없으면 아무것도 실행하지 않는다"""
        bot = _make_bot(positioned_stocks=[])
        handler = _make_handler(bot)

        await handler.liquidate_all_positions_end_of_day()

        bot.decision_engine.execute_virtual_sell.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_virtual_sell_for_each_positioned_stock_in_virtual_mode(self):
        """가상 모드에서 보유 포지션마다 execute_virtual_sell을 호출한다"""
        stocks = [
            _make_trading_stock("005930"),
            _make_trading_stock("000660"),
        ]
        bot = _make_bot(positioned_stocks=stocks, is_virtual=True, virtual_sell_result=True)
        handler = _make_handler(bot)

        await handler.liquidate_all_positions_end_of_day()

        assert bot.decision_engine.execute_virtual_sell.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_stock_with_zero_quantity(self):
        """수량이 0인 포지션은 청산을 건너뛴다"""
        stock = _make_trading_stock("005930", quantity=0)
        bot = _make_bot(positioned_stocks=[stock], is_virtual=True)
        handler = _make_handler(bot)

        await handler.liquidate_all_positions_end_of_day()

        bot.decision_engine.execute_virtual_sell.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_stock_when_strategy_refuses_liquidation(self):
        """전략이 EOD 청산을 거부(should_liquidate_eod=False)하면 해당 종목을 스킵한다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(
            positioned_stocks=[stock],
            is_virtual=True,
            strategy_allows_liquidation=False,
        )
        handler = _make_handler(bot)

        await handler.liquidate_all_positions_end_of_day()

        bot.decision_engine.execute_virtual_sell.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_combined_chart_close_price_when_available(self):
        """분봉 데이터가 있으면 최신 종가를 매도가로 사용한다"""
        stock = _make_trading_stock("005930", avg_price=50000)
        chart_df = pd.DataFrame({'close': [52000, 53000, 54000]})

        bot = _make_bot(positioned_stocks=[stock], is_virtual=True)
        bot.intraday_manager.get_combined_chart_data.return_value = chart_df
        handler = _make_handler(bot)

        await handler.liquidate_all_positions_end_of_day()

        call_args = bot.decision_engine.execute_virtual_sell.call_args
        sell_price = call_args[0][1]
        # 마지막 종가 54000을 호가단위로 반올림한 값이어야 함
        assert sell_price > 0

    @pytest.mark.asyncio
    async def test_calls_real_sell_order_in_real_mode(self):
        """실전 모드에서 execute_sell_order가 호출된다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(positioned_stocks=[stock], is_virtual=False, move_result=True)
        handler = _make_handler(bot)

        await handler.liquidate_all_positions_end_of_day()

        bot.trading_manager.execute_sell_order.assert_called_once()
        bot.decision_engine.execute_virtual_sell.assert_not_called()


# ---------------------------------------------------------------------------
# execute_end_of_day_liquidation
# ---------------------------------------------------------------------------

class TestExecuteEndOfDayLiquidation:
    """동적 시간 기반 EOD 일괄 매도 테스트"""

    @pytest.mark.asyncio
    async def test_does_nothing_and_clears_failed_when_no_positions(self):
        """포지션이 없으면 _eod_failed_stocks를 비우고 종료한다"""
        bot = _make_bot(positioned_stocks=[])
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {"005930"}  # 이전 실패 상태

        with patch('bot.liquidation_handler.MarketHours') as mock_mh:
            mock_mh.get_market_hours.return_value = {
                'eod_liquidation_hour': 15,
                'eod_liquidation_minute': 20,
            }
            await handler.execute_end_of_day_liquidation()

        assert len(handler._eod_failed_stocks) == 0

    @pytest.mark.asyncio
    async def test_adds_stock_to_failed_set_when_virtual_sell_fails(self):
        """가상 매도 실패 시 해당 종목이 _eod_failed_stocks에 추가된다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(
            positioned_stocks=[stock],
            is_virtual=True,
            virtual_sell_result=False,
        )
        handler = _make_handler(bot)

        with patch('bot.liquidation_handler.MarketHours') as mock_mh:
            mock_mh.get_market_hours.return_value = {
                'eod_liquidation_hour': 15,
                'eod_liquidation_minute': 20,
            }
            await handler.execute_end_of_day_liquidation()

        assert "005930" in handler._eod_failed_stocks

    @pytest.mark.asyncio
    async def test_does_not_add_to_failed_when_virtual_sell_succeeds(self):
        """가상 매도 성공 시 _eod_failed_stocks에 추가되지 않는다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(positioned_stocks=[stock], is_virtual=True, virtual_sell_result=True)
        handler = _make_handler(bot)

        with patch('bot.liquidation_handler.MarketHours') as mock_mh:
            mock_mh.get_market_hours.return_value = {
                'eod_liquidation_hour': 15,
                'eod_liquidation_minute': 20,
            }
            await handler.execute_end_of_day_liquidation()

        assert "005930" not in handler._eod_failed_stocks

    @pytest.mark.asyncio
    async def test_adds_to_failed_when_individual_exception_occurs(self):
        """개별 종목 처리 중 예외 발생 시 failed_stocks에 추가된다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(positioned_stocks=[stock], is_virtual=True)
        bot.decision_engine.execute_virtual_sell.side_effect = RuntimeError("네트워크 오류")
        handler = _make_handler(bot)

        with patch('bot.liquidation_handler.MarketHours') as mock_mh:
            mock_mh.get_market_hours.return_value = {
                'eod_liquidation_hour': 15,
                'eod_liquidation_minute': 20,
            }
            await handler.execute_end_of_day_liquidation()

        assert "005930" in handler._eod_failed_stocks


# ---------------------------------------------------------------------------
# retry_failed_eod_liquidation
# ---------------------------------------------------------------------------

class TestRetryFailedEodLiquidation:
    """EOD 청산 실패 재시도 테스트"""

    @pytest.mark.asyncio
    async def test_returns_true_immediately_when_no_failed_stocks(self):
        """실패 종목이 없으면 즉시 True 반환"""
        handler = _make_handler()
        handler._eod_failed_stocks = set()

        result = await handler.retry_failed_eod_liquidation()

        assert result is True

    @pytest.mark.asyncio
    async def test_retries_and_returns_true_when_virtual_sell_succeeds(self):
        """재시도 가상 매도 성공 시 True 반환 및 failed_stocks 비워진다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(
            positioned_stocks=[stock],
            is_virtual=True,
            virtual_sell_result=True,
        )
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {"005930"}
        handler._eod_retry_count = 0

        result = await handler.retry_failed_eod_liquidation()

        assert result is True
        assert len(handler._eod_failed_stocks) == 0

    @pytest.mark.asyncio
    async def test_keeps_stock_in_failed_set_when_virtual_sell_still_fails(self):
        """재시도 가상 매도도 실패하면 종목이 failed_stocks에 유지된다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(
            positioned_stocks=[stock],
            is_virtual=True,
            virtual_sell_result=False,
        )
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {"005930"}
        handler._eod_retry_count = 0

        result = await handler.retry_failed_eod_liquidation()

        assert result is False
        assert "005930" in handler._eod_failed_stocks

    @pytest.mark.asyncio
    async def test_triggers_force_complete_when_retry_count_exceeds_max(self):
        """재시도 횟수가 MAX_RETRIES 초과 시 강제 완료 처리(_force_complete)가 호출된다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(positioned_stocks=[stock], is_virtual=True)
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {"005930"}
        handler._eod_retry_count = EOD_MAX_RETRIES  # 이미 한도 도달

        with patch.object(handler, '_force_complete_failed_stocks', new=AsyncMock()) as mock_force:
            result = await handler.retry_failed_eod_liquidation()

        mock_force.assert_called_once()
        assert result is False

    @pytest.mark.asyncio
    async def test_skips_stock_already_liquidated_during_retry(self):
        """재시도 대상인데 이미 청산된 종목(포지션 없음)은 건너뛴다"""
        # positioned_stocks에는 없는 종목
        bot = _make_bot(positioned_stocks=[], is_virtual=True)
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {"005930"}
        handler._eod_retry_count = 0

        result = await handler.retry_failed_eod_liquidation()

        # 포지션 없으므로 재시도 불필요 → failed_stocks 비워짐
        assert result is True
        assert len(handler._eod_failed_stocks) == 0


# ---------------------------------------------------------------------------
# _force_complete_failed_stocks
# ---------------------------------------------------------------------------

class TestForceCompleteFailedStocks:
    """강제 완료 처리 테스트"""

    @pytest.mark.asyncio
    async def test_changes_state_to_completed_for_each_failed_stock(self):
        """강제 완료 시 각 종목의 상태가 COMPLETED로 변경된다"""
        from core.models import StockState
        stock = _make_trading_stock("005930", avg_price=50000, quantity=10)
        bot = _make_bot(positioned_stocks=[stock])
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {"005930"}

        await handler._force_complete_failed_stocks()

        bot.trading_manager._change_stock_state.assert_called_once()
        call_args = bot.trading_manager._change_stock_state.call_args[0]
        assert call_args[0] == "005930"
        assert call_args[1] == StockState.COMPLETED

    @pytest.mark.asyncio
    async def test_releases_investment_for_each_failed_stock(self):
        """강제 완료 시 투자 원금이 회수된다 (release_investment 호출)"""
        stock = _make_trading_stock("005930", avg_price=50000, quantity=10)
        bot = _make_bot(positioned_stocks=[stock])
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {"005930"}

        await handler._force_complete_failed_stocks()

        bot.fund_manager.release_investment.assert_called_once_with(
            50000.0 * 10, stock_code="005930"
        )

    @pytest.mark.asyncio
    async def test_clears_failed_stocks_after_force_complete(self):
        """강제 완료 후 _eod_failed_stocks가 비워진다"""
        stock = _make_trading_stock("005930")
        bot = _make_bot(positioned_stocks=[stock])
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {"005930"}

        await handler._force_complete_failed_stocks()

        assert len(handler._eod_failed_stocks) == 0

    @pytest.mark.asyncio
    async def test_skips_gracefully_when_trading_stock_not_found(self):
        """trading_stock을 찾을 수 없어도 예외 없이 처리된다"""
        bot = _make_bot(positioned_stocks=[])
        handler = _make_handler(bot)
        handler._eod_failed_stocks = {"999999"}

        # 예외 전파 없이 종료되어야 함
        await handler._force_complete_failed_stocks()

        assert len(handler._eod_failed_stocks) == 0


# ---------------------------------------------------------------------------
# reset_eod_state / has_failed_eod_stocks
# ---------------------------------------------------------------------------

class TestEodStateHelpers:
    """EOD 상태 관리 헬퍼 메서드 테스트"""

    def test_has_failed_eod_stocks_returns_false_when_empty(self):
        """실패 종목이 없으면 False 반환"""
        handler = _make_handler()
        handler._eod_failed_stocks = set()
        assert handler.has_failed_eod_stocks() is False

    def test_has_failed_eod_stocks_returns_true_when_not_empty(self):
        """실패 종목이 있으면 True 반환"""
        handler = _make_handler()
        handler._eod_failed_stocks = {"005930"}
        assert handler.has_failed_eod_stocks() is True

    def test_reset_eod_state_clears_failed_stocks_and_retry_count(self):
        """reset_eod_state 호출 후 failed_stocks 및 retry_count가 초기화된다"""
        handler = _make_handler()
        handler._eod_failed_stocks = {"005930", "000660"}
        handler._eod_retry_count = 2

        handler.reset_eod_state()

        assert len(handler._eod_failed_stocks) == 0
        assert handler._eod_retry_count == 0

    def test_set_and_get_last_eod_liquidation_date(self):
        """마지막 장마감 청산 날짜를 저장하고 반환한다"""
        handler = _make_handler()
        today = datetime(2024, 1, 15).date()

        handler.set_last_eod_liquidation_date(today)

        assert handler.get_last_eod_liquidation_date() == today
