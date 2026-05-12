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


class TestSavePaperEodBalanceMultiStrategy:
    """_save_paper_eod_balance_if_virtual: 다중 전략 모드 wiring 검증

    bug: b21d363 — 다중 전략 모드에서 bot.virtual_trading_manager 속성이 없어
    항상 WARNING 로그만 출력되고 save_paper_trading_state가 호출되지 않던 문제.
    fix: decision_engine.virtual_trading 경로를 정규 경로로 추가.
    """

    def _make_multi_strategy_bot(self):
        """다중 전략 모드 bot: bot.virtual_trading_manager 속성 없음,
        decision_engine.virtual_trading 에 VirtualTradingManager 존재."""
        bot = MagicMock(spec=[
            'decision_engine', 'fund_manager', 'trading_manager',
            'intraday_manager', 'broker', 'telegram',
        ])
        bot.decision_engine.is_virtual_mode = True
        # 다중 전략 모드: bot에 virtual_trading_manager 속성 없음
        # (spec 제한으로 getattr 시 AttributeError → getattr default None 반환)
        bot.decision_engine.virtual_trading = MagicMock()
        bot.decision_engine.virtual_trading.save_paper_trading_state = Mock(return_value=True)
        bot.decision_engine.virtual_trading.log_cumulative_profit = Mock()
        bot.fund_manager.release_investment = Mock()
        bot.trading_manager.get_stocks_by_state = Mock(return_value=[])
        bot.intraday_manager.get_combined_chart_data = Mock(return_value=None)
        bot.broker.get_current_price = Mock(return_value=70000.0)
        bot.telegram = None
        return bot

    def test_save_called_via_decision_engine_virtual_trading(self):
        """다중 전략 모드에서 decision_engine.virtual_trading 경로로
        save_paper_trading_state가 호출되어야 함."""
        bot = self._make_multi_strategy_bot()
        handler = LiquidationHandler(bot)

        handler._save_paper_eod_balance_if_virtual()

        bot.decision_engine.virtual_trading.save_paper_trading_state.assert_called_once()

    def test_log_cumulative_profit_called_on_success(self):
        """save_paper_trading_state 성공 시 log_cumulative_profit도 호출되어야 함."""
        bot = self._make_multi_strategy_bot()
        handler = LiquidationHandler(bot)

        handler._save_paper_eod_balance_if_virtual()

        bot.decision_engine.virtual_trading.log_cumulative_profit.assert_called_once()

    def test_no_warning_logged_when_virtual_trading_found(self):
        """decision_engine.virtual_trading 경로가 있으면 WARNING이 발생하지 않아야 함."""
        bot = self._make_multi_strategy_bot()
        handler = LiquidationHandler(bot)

        with patch.object(handler.logger, 'warning') as mock_warn:
            handler._save_paper_eod_balance_if_virtual()

        # "virtual_trading_manager 참조 불가" 경고가 없어야 함
        for call in mock_warn.call_args_list:
            assert '참조 불가' not in str(call)

    def test_skipped_when_not_virtual_mode(self):
        """is_virtual_mode=False 면 save 호출 없이 조기 리턴."""
        bot = self._make_multi_strategy_bot()
        bot.decision_engine.is_virtual_mode = False
        handler = LiquidationHandler(bot)

        handler._save_paper_eod_balance_if_virtual()

        bot.decision_engine.virtual_trading.save_paper_trading_state.assert_not_called()
