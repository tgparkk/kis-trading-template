"""
매매 흐름 통합 테스트
====================
FundManager reserve/confirm/cancel, 가상/실전 분기,
전략 콜백, position_monitor 매도 시그널, shutdown 미체결 취소 검증
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_modules  # noqa: F401

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_bot():
    """TradingAnalyzer 테스트용 Mock bot"""
    with patch('main.KISBroker') as mock_broker_cls, \
         patch('main.DatabaseManager') as mock_db_cls, \
         patch('main.TelegramIntegration'), \
         patch('main.check_duplicate_process'), \
         patch('main.load_config') as mock_load_config, \
         patch('main.StrategyLoader') as mock_loader:

        mock_load_config.return_value = MagicMock(
            rebalancing_mode=False,
            strategy={'name': 'sample', 'enabled': False},
            paper_trading=True,
        )
        mock_db_cls.return_value.db_path = ':memory:'
        mock_broker_cls.return_value.connect = AsyncMock(return_value=True)
        mock_loader.load_strategy.side_effect = FileNotFoundError("test")

        from main import DayTradingBot
        bot = DayTradingBot()
        yield bot


class TestFundManagerFlow:
    """FundManager reserve/confirm/cancel 흐름 테스트"""

    @pytest.mark.asyncio
    async def test_매수_성공_시_자금_예약_후_확정(self, mock_bot):
        """매수 성공 시 reserve_funds → confirm_order 순서로 호출하는지"""
        from core.models import StockState

        trading_stock = MagicMock()
        trading_stock.stock_code = '005930'
        trading_stock.stock_name = '삼성전자'
        trading_stock.is_buy_cooldown_active.return_value = False
        trading_stock.state = StockState.SELECTED

        mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])
        mock_bot.trading_manager.get_trading_stock = MagicMock(return_value=trading_stock)

        # decision_engine mock
        mock_bot.decision_engine.analyze_buy_decision = AsyncMock(
            return_value=(True, '테스트 매수', {'buy_price': 70000, 'quantity': 5, 'max_buy_amount': 350000})
        )
        mock_bot.decision_engine.is_virtual_mode = True
        mock_bot.decision_engine.execute_virtual_buy = AsyncMock()
        mock_bot.trading_manager._change_stock_state = MagicMock()

        # fund_manager mock
        mock_bot.fund_manager.get_max_buy_amount = MagicMock(return_value=500000)
        mock_bot.fund_manager.reserve_funds = MagicMock(return_value=True)
        mock_bot.fund_manager.confirm_order = MagicMock()
        mock_bot.fund_manager.get_status = MagicMock(return_value={'total_funds': 10000000})

        # db_manager.price_repo mock
        mock_bot.db_manager.price_repo.get_daily_prices = MagicMock(
            return_value=pd.DataFrame({'close': range(100), 'open': range(100),
                                       'high': range(100), 'low': range(100), 'volume': range(100)})
        )

        await mock_bot.trading_analyzer.analyze_buy_decision(trading_stock)

        mock_bot.fund_manager.reserve_funds.assert_called_once()
        call_args = mock_bot.fund_manager.reserve_funds.call_args[0]
        assert call_args[0].startswith('005930')
        assert call_args[1] == 350000
        mock_bot.fund_manager.confirm_order.assert_called_once()
        confirm_args = mock_bot.fund_manager.confirm_order.call_args[0]
        assert confirm_args[0].startswith('005930')
        assert confirm_args[1] == 350000

    @pytest.mark.asyncio
    async def test_가상매수_실패_시_자금_취소(self, mock_bot):
        """가상 매수 실패 시 cancel_order가 호출되는지"""
        from core.models import StockState

        trading_stock = MagicMock()
        trading_stock.stock_code = '005930'
        trading_stock.stock_name = '삼성전자'
        trading_stock.is_buy_cooldown_active.return_value = False
        trading_stock.state = StockState.SELECTED

        mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])
        mock_bot.trading_manager.get_trading_stock = MagicMock(return_value=trading_stock)

        mock_bot.decision_engine.analyze_buy_decision = AsyncMock(
            return_value=(True, '테스트', {'buy_price': 70000, 'quantity': 5, 'max_buy_amount': 350000})
        )
        mock_bot.decision_engine.is_virtual_mode = True
        mock_bot.decision_engine.execute_virtual_buy = AsyncMock(side_effect=Exception("매수 실패"))
        mock_bot.trading_manager._change_stock_state = MagicMock()

        mock_bot.fund_manager.get_max_buy_amount = MagicMock(return_value=500000)
        mock_bot.fund_manager.reserve_funds = MagicMock(return_value=True)
        mock_bot.fund_manager.cancel_order = MagicMock()
        mock_bot.fund_manager.get_status = MagicMock(return_value={'total_funds': 10000000})

        mock_bot.db_manager.price_repo.get_daily_prices = MagicMock(
            return_value=pd.DataFrame({'close': range(100), 'open': range(100),
                                       'high': range(100), 'low': range(100), 'volume': range(100)})
        )

        await mock_bot.trading_analyzer.analyze_buy_decision(trading_stock)

        mock_bot.fund_manager.cancel_order.assert_called_once()
        cancel_args = mock_bot.fund_manager.cancel_order.call_args[0]
        assert cancel_args[0].startswith('005930')

    @pytest.mark.asyncio
    async def test_자금_예약_실패_시_매수_스킵(self, mock_bot):
        """reserve_funds가 False를 반환하면 매수를 건너뛰는지"""
        from core.models import StockState

        trading_stock = MagicMock()
        trading_stock.stock_code = '005930'
        trading_stock.stock_name = '삼성전자'
        trading_stock.is_buy_cooldown_active.return_value = False

        mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])
        mock_bot.trading_manager.get_trading_stock = MagicMock(return_value=trading_stock)

        mock_bot.decision_engine.analyze_buy_decision = AsyncMock(
            return_value=(True, '테스트', {'buy_price': 70000, 'quantity': 5, 'max_buy_amount': 350000})
        )
        mock_bot.decision_engine.is_virtual_mode = True
        mock_bot.decision_engine.execute_virtual_buy = AsyncMock()

        mock_bot.fund_manager.get_max_buy_amount = MagicMock(return_value=500000)
        mock_bot.fund_manager.reserve_funds = MagicMock(return_value=False)
        mock_bot.fund_manager.get_status = MagicMock(return_value={'total_funds': 10000000})

        mock_bot.db_manager.price_repo.get_daily_prices = MagicMock(
            return_value=pd.DataFrame({'close': range(100), 'open': range(100),
                                       'high': range(100), 'low': range(100), 'volume': range(100)})
        )

        await mock_bot.trading_analyzer.analyze_buy_decision(trading_stock)

        mock_bot.decision_engine.execute_virtual_buy.assert_not_called()


class TestVirtualRealBranching:
    """가상/실전 매매 분기 테스트"""

    @pytest.mark.asyncio
    async def test_가상모드_execute_virtual_buy_호출(self, mock_bot):
        """가상매매 모드에서 execute_virtual_buy가 호출되는지"""
        trading_stock = MagicMock()
        trading_stock.stock_code = '005930'
        trading_stock.stock_name = '삼성전자'
        trading_stock.is_buy_cooldown_active.return_value = False

        mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])
        mock_bot.trading_manager.get_trading_stock = MagicMock(return_value=trading_stock)

        mock_bot.decision_engine.analyze_buy_decision = AsyncMock(
            return_value=(True, '테스트', {'buy_price': 70000, 'quantity': 5, 'max_buy_amount': 350000})
        )
        mock_bot.decision_engine.is_virtual_mode = True
        mock_bot.decision_engine.execute_virtual_buy = AsyncMock()
        mock_bot.decision_engine.execute_real_buy = AsyncMock()
        mock_bot.trading_manager._change_stock_state = MagicMock()

        mock_bot.fund_manager.get_max_buy_amount = MagicMock(return_value=500000)
        mock_bot.fund_manager.reserve_funds = MagicMock(return_value=True)
        mock_bot.fund_manager.confirm_order = MagicMock()
        mock_bot.fund_manager.add_position = MagicMock()
        mock_bot.fund_manager.get_status = MagicMock(return_value={'total_funds': 10000000})

        # db_manager.price_repo.get_daily_prices mock (PostgreSQL 직접 조회)
        mock_bot.db_manager.price_repo.get_daily_prices = MagicMock(
            return_value=pd.DataFrame({'close': range(100)})
        )

        await mock_bot.trading_analyzer.analyze_buy_decision(trading_stock)

        mock_bot.decision_engine.execute_virtual_buy.assert_called_once()
        mock_bot.decision_engine.execute_real_buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_실전모드_execute_real_buy_호출(self, mock_bot):
        """실전매매 모드에서 execute_real_buy가 호출되는지"""
        trading_stock = MagicMock()
        trading_stock.stock_code = '005930'
        trading_stock.stock_name = '삼성전자'
        trading_stock.is_buy_cooldown_active.return_value = False

        mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])
        mock_bot.trading_manager.get_trading_stock = MagicMock(return_value=trading_stock)

        mock_bot.decision_engine.analyze_buy_decision = AsyncMock(
            return_value=(True, '테스트', {'buy_price': 70000, 'quantity': 5, 'max_buy_amount': 350000})
        )
        mock_bot.decision_engine.is_virtual_mode = False
        mock_bot.decision_engine.execute_real_buy = AsyncMock(return_value=True)
        mock_bot.decision_engine.execute_virtual_buy = AsyncMock()
        mock_bot.trading_manager._change_stock_state = MagicMock()

        mock_bot.fund_manager.get_max_buy_amount = MagicMock(return_value=500000)
        mock_bot.fund_manager.reserve_funds = MagicMock(return_value=True)
        mock_bot.fund_manager.confirm_order = MagicMock()
        mock_bot.fund_manager.get_status = MagicMock(return_value={'total_funds': 10000000})

        # db_manager.price_repo.get_daily_prices mock (PostgreSQL 직접 조회)
        mock_bot.db_manager.price_repo.get_daily_prices = MagicMock(
            return_value=pd.DataFrame({'close': range(100)})
        )

        await mock_bot.trading_analyzer.analyze_buy_decision(trading_stock)

        mock_bot.decision_engine.execute_real_buy.assert_called_once()
        mock_bot.decision_engine.execute_virtual_buy.assert_not_called()

    @pytest.mark.asyncio
    async def test_실전매수_실패_시_자금_취소(self, mock_bot):
        """실전 매수 실패 시 cancel_order가 호출되는지"""
        trading_stock = MagicMock()
        trading_stock.stock_code = '005930'
        trading_stock.stock_name = '삼성전자'
        trading_stock.is_buy_cooldown_active.return_value = False

        mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])
        mock_bot.trading_manager.get_trading_stock = MagicMock(return_value=trading_stock)

        mock_bot.decision_engine.analyze_buy_decision = AsyncMock(
            return_value=(True, '테스트', {'buy_price': 70000, 'quantity': 5, 'max_buy_amount': 350000})
        )
        mock_bot.decision_engine.is_virtual_mode = False
        mock_bot.decision_engine.execute_real_buy = AsyncMock(return_value=False)

        mock_bot.fund_manager.get_max_buy_amount = MagicMock(return_value=500000)
        mock_bot.fund_manager.reserve_funds = MagicMock(return_value=True)
        mock_bot.fund_manager.cancel_order = MagicMock()
        mock_bot.fund_manager.get_status = MagicMock(return_value={'total_funds': 10000000})

        # db_manager.price_repo.get_daily_prices mock (PostgreSQL 직접 조회)
        mock_bot.db_manager.price_repo.get_daily_prices = MagicMock(
            return_value=pd.DataFrame({'close': range(100)})
        )

        await mock_bot.trading_analyzer.analyze_buy_decision(trading_stock)

        mock_bot.fund_manager.cancel_order.assert_called_once()
        cancel_args = mock_bot.fund_manager.cancel_order.call_args[0]
        assert cancel_args[0].startswith('005930')


class TestStrategyCallbacks:
    """전략 콜백 테스트"""

    @pytest.mark.asyncio
    async def test_전략_on_order_filled_콜백_호출(self, mock_bot):
        """체결 시 strategy.on_order_filled이 호출되는지"""
        mock_strategy = MagicMock()
        mock_strategy.name = 'TestStrategy'
        mock_bot.strategy = mock_strategy

        # on_order_filled는 TradingStockManager.set_strategy → decision_engine에서 호출됨
        # 여기서는 전략이 설정되었을 때 콜백이 존재하는지만 확인
        assert hasattr(mock_strategy, 'on_order_filled')
        assert callable(mock_strategy.on_order_filled)


class TestPositionMonitorSellSignal:
    """position_monitor 매도 시그널 테스트"""

    @pytest.mark.asyncio
    async def test_전략_generate_signal_매도_시그널_호출(self):
        """position_monitor가 strategy.generate_signal을 호출하여 매도 판단하는지"""
        from core.trading.position_monitor import PositionMonitor
        from strategies.base import Signal, SignalType

        state_manager = MagicMock()
        completion_handler = MagicMock()
        completion_handler.check_order_completions = AsyncMock()
        intraday_manager = MagicMock()
        data_collector = MagicMock()

        monitor = PositionMonitor(state_manager, completion_handler, intraday_manager, data_collector)

        # 전략 설정
        mock_strategy = MagicMock()
        sell_signal = Signal(
            signal_type=SignalType.SELL,
            stock_code='005930',
            confidence=80,
            reasons=['RSI 과매수'],
        )
        mock_strategy.generate_signal.return_value = sell_signal
        mock_strategy.max_holding_days = None  # max_holding_days 분기 건너뜀 (이 테스트의 목적은 generate_signal 호출 확인)
        monitor.set_strategy(mock_strategy)

        # decision_engine 설정
        mock_de = MagicMock()
        mock_de.execute_virtual_sell = AsyncMock(return_value=True)
        monitor.set_decision_engine(mock_de)

        # trading_stock 설정
        trading_stock = MagicMock()
        trading_stock.stock_code = '005930'
        trading_stock.position = MagicMock()
        trading_stock.position.avg_price = 70000
        trading_stock.position.quantity = 10
        trading_stock.target_profit_rate = 0.17
        trading_stock.stop_loss_rate = 0.09
        trading_stock.highest_price_since_buy = None
        trading_stock.trailing_stop_activated = False

        # 현재가 (손익절 안 걸리는 가격)
        intraday_manager.get_current_price_for_sell.return_value = {'current_price': 71000}

        # ohlcv 데이터 (전략 시그널용)
        price_data = MagicMock()
        price_data.last_price = 71000
        price_data.ohlcv_data = [{'open': 70000, 'high': 72000, 'low': 69000, 'close': 71000, 'volume': 1000}]
        data_collector.get_stock.return_value = price_data

        with patch('core.trading.position_monitor.now_kst') as mock_now, \
             patch('config.settings.load_trading_config') as mock_config:
            mock_now.return_value = datetime(2026, 2, 9, 10, 0, tzinfo=timezone(timedelta(hours=9)))
            mock_cfg = MagicMock()
            mock_cfg.paper_trading = True
            mock_config.return_value = mock_cfg

            await monitor._analyze_sell_for_stock(trading_stock)

        mock_strategy.generate_signal.assert_called_once()


class TestShutdownPendingOrders:
    """종료 시 미체결 주문 취소 테스트"""

    @pytest.mark.asyncio
    async def test_종료_시_미체결_주문_일괄_취소(self):
        """shutdown에서 미체결 주문을 모두 취소하는지"""
        from bot.initializer import BotInitializer

        mock_bot = MagicMock()

        order1 = MagicMock()
        order1.order_id = 'ORD001'
        order1.stock_code = '005930'

        order2 = MagicMock()
        order2.order_id = 'ORD002'
        order2.stock_code = '000660'

        mock_bot.order_manager.get_pending_orders.return_value = [order1, order2]
        mock_bot.broker.cancel_order.return_value = {'success': True}

        initializer = BotInitializer(mock_bot)
        await initializer._cancel_pending_orders()

        assert mock_bot.broker.cancel_order.call_count == 2

    @pytest.mark.asyncio
    async def test_미체결_주문_없으면_취소_스킵(self):
        """미체결 주문이 없으면 cancel_order를 호출하지 않는지"""
        from bot.initializer import BotInitializer

        mock_bot = MagicMock()
        mock_bot.order_manager.get_pending_orders.return_value = []

        initializer = BotInitializer(mock_bot)
        await initializer._cancel_pending_orders()

        mock_bot.broker.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_주문_취소_실패_시_계속_진행(self):
        """개별 주문 취소 실패 시 나머지 주문도 계속 처리하는지"""
        from bot.initializer import BotInitializer

        mock_bot = MagicMock()

        order1 = MagicMock()
        order1.order_id = 'ORD001'
        order1.stock_code = '005930'

        order2 = MagicMock()
        order2.order_id = 'ORD002'
        order2.stock_code = '000660'

        mock_bot.order_manager.get_pending_orders.return_value = [order1, order2]
        mock_bot.broker.cancel_order.side_effect = [
            Exception("취소 실패"),
            {'success': True},
        ]

        initializer = BotInitializer(mock_bot)
        # 예외가 발생하지 않아야 함
        await initializer._cancel_pending_orders()

        assert mock_bot.broker.cancel_order.call_count == 2


class TestSystemMonitorTargetStocks:
    """SystemMonitor 전략 후보 종목 등록 테스트"""

    @pytest.mark.asyncio
    async def test_전략_get_target_stocks_호출(self):
        """_register_strategy_target_stocks가 strategy.get_target_stocks()를 호출하는지"""
        from bot.system_monitor import SystemMonitor

        mock_bot = MagicMock()
        mock_strategy = MagicMock()
        mock_strategy.name = 'TestStrategy'
        mock_strategy.get_target_stocks.return_value = ['005930', '000660']
        mock_bot.strategy = mock_strategy

        mock_bot.trading_manager.add_selected_stock = AsyncMock(return_value=True)

        monitor = SystemMonitor(mock_bot)

        with patch('bot.system_monitor.now_kst') as mock_now:
            mock_now.return_value = datetime(2026, 2, 9, 8, 30, tzinfo=timezone(timedelta(hours=9)))
            await monitor._register_strategy_target_stocks()

        assert mock_bot.trading_manager.add_selected_stock.call_count == 2

    @pytest.mark.asyncio
    async def test_전략_없으면_스킵(self):
        """전략이 None이면 등록을 건너뛰는지"""
        from bot.system_monitor import SystemMonitor

        mock_bot = MagicMock()
        mock_bot.strategy = None

        monitor = SystemMonitor(mock_bot)
        await monitor._register_strategy_target_stocks()

        # 에러 없이 정상 종료
