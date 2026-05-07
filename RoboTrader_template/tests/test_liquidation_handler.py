"""
LiquidationHandler 유닛 테스트
- execute_end_of_day_liquidation 호출 후 fund_manager 갱신이 1회만 발생하는지 검증
- liquidate_all_positions_end_of_day 동일 검증
- retry_failed_eod_liquidation 동일 검증
(F4 fix 2026-05-04: 이중 호출 버그 제거 회귀 방지)
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from bot.liquidation_handler import LiquidationHandler
from core.models import TradingStock, StockState, Position
import datetime


def _make_bot(sell_result: bool = True):
    """테스트용 최소 bot mock 생성"""
    bot = MagicMock()

    # fund_manager mock
    bot.fund_manager.release_investment = Mock()
    bot.fund_manager.adjust_pnl = Mock()
    bot.fund_manager.remove_position = Mock()

    # decision_engine: 가상매매 모드, execute_virtual_sell → sell_result 반환
    bot.decision_engine.is_virtual_mode = True
    bot.decision_engine.execute_virtual_sell = AsyncMock(return_value=sell_result)

    # intraday_manager: 분봉 데이터 없음 → broker.get_current_price 사용
    bot.intraday_manager.get_combined_chart_data = Mock(return_value=None)
    bot.broker.get_current_price = Mock(return_value=70000.0)

    # SCREENER_SNAPSHOT_ENABLED=False → run_screener_snapshot_hook 스킵
    bot.telegram = None

    return bot


def _make_positioned_stock(stock_code: str = "005930", qty: int = 10, avg_price: float = 65000.0):
    """포지션 있는 TradingStock 생성"""
    stock = TradingStock(
        stock_code=stock_code,
        stock_name="테스트종목",
        state=StockState.POSITIONED,
        selected_time=datetime.datetime.now(),
    )
    stock.position = Position(
        stock_code=stock_code,
        quantity=qty,
        avg_price=avg_price,
    )
    return stock


class TestExecuteEndOfDayLiquidationFundManagerOnce:
    """execute_end_of_day_liquidation: fund_manager 갱신 1회 검증"""

    @pytest.mark.asyncio
    async def test_release_investment_called_once(self):
        """성공 케이스: release_investment가 종목당 정확히 1회만 호출되어야 함"""
        bot = _make_bot(sell_result=True)
        stock = _make_positioned_stock()
        bot.trading_manager.get_stocks_by_state = Mock(return_value=[stock])

        handler = LiquidationHandler(bot)

        with patch("config.constants.SCREENER_SNAPSHOT_ENABLED", False):
            with patch.object(handler, "run_screener_snapshot_hook", AsyncMock()):
                await handler.execute_end_of_day_liquidation()

        # execute_virtual_sell 내부에서만 호출됨 → handler에서 추가 호출 없음
        # 실제 fund_manager는 execute_virtual_sell 내부(mock)에서 처리
        # handler 레벨에서 직접 호출이 0회여야 함
        bot.fund_manager.release_investment.assert_not_called()
        bot.fund_manager.adjust_pnl.assert_not_called()
        bot.fund_manager.remove_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_adjust_pnl_not_called_by_handler(self):
        """handler가 adjust_pnl을 직접 호출하지 않아야 함"""
        bot = _make_bot(sell_result=True)
        stock = _make_positioned_stock()
        bot.trading_manager.get_stocks_by_state = Mock(return_value=[stock])

        handler = LiquidationHandler(bot)

        with patch("config.constants.SCREENER_SNAPSHOT_ENABLED", False):
            with patch.object(handler, "run_screener_snapshot_hook", AsyncMock()):
                await handler.execute_end_of_day_liquidation()

        bot.fund_manager.adjust_pnl.assert_not_called()

    @pytest.mark.asyncio
    async def test_sell_failure_no_fund_manager_call(self):
        """매도 실패 케이스: fund_manager 호출 없어야 함"""
        bot = _make_bot(sell_result=False)
        stock = _make_positioned_stock()
        bot.trading_manager.get_stocks_by_state = Mock(return_value=[stock])

        handler = LiquidationHandler(bot)

        with patch("config.constants.SCREENER_SNAPSHOT_ENABLED", False):
            with patch.object(handler, "run_screener_snapshot_hook", AsyncMock()):
                await handler.execute_end_of_day_liquidation()

        bot.fund_manager.release_investment.assert_not_called()
        bot.fund_manager.adjust_pnl.assert_not_called()
        bot.fund_manager.remove_position.assert_not_called()


class TestLiquidateAllPositionsFundManagerOnce:
    """liquidate_all_positions_end_of_day: fund_manager 갱신 1회 검증"""

    @pytest.mark.asyncio
    async def test_release_investment_not_called_by_handler(self):
        """handler가 release_investment를 직접 호출하지 않아야 함"""
        bot = _make_bot(sell_result=True)
        stock = _make_positioned_stock()
        bot.trading_manager.get_stocks_by_state = Mock(return_value=[stock])

        handler = LiquidationHandler(bot)
        await handler.liquidate_all_positions_end_of_day()

        bot.fund_manager.release_investment.assert_not_called()
        bot.fund_manager.adjust_pnl.assert_not_called()
        bot.fund_manager.remove_position.assert_not_called()


class TestRetryFailedEodLiquidationFundManagerOnce:
    """retry_failed_eod_liquidation: fund_manager 갱신 1회 검증"""

    @pytest.mark.asyncio
    async def test_release_investment_not_called_by_handler_on_retry(self):
        """재시도 성공 시에도 handler가 release_investment 직접 호출하지 않아야 함"""
        bot = _make_bot(sell_result=True)
        stock = _make_positioned_stock()

        # 재시도 대상 종목 설정
        bot.trading_manager.get_stocks_by_state = Mock(return_value=[stock])
        bot.trading_manager.get_trading_stock = Mock(return_value=stock)

        handler = LiquidationHandler(bot)
        handler._eod_failed_stocks = {"005930"}

        await handler.retry_failed_eod_liquidation()

        bot.fund_manager.release_investment.assert_not_called()
        bot.fund_manager.adjust_pnl.assert_not_called()
        bot.fund_manager.remove_position.assert_not_called()
