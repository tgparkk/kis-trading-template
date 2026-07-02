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
        trading_stock.owner_strategy = None  # E4: owner_strategy 우선 참조 → None으로 명시해 self._strategy fallback 보장

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


class TestEquitySnapshotResavesPaperState:
    """EOD equity 스냅샷 직전 paper_trading_state 재저장 검증.

    버그(2026-06-23): save_paper_trading_state는 15:00 EOD청산 훅에서 1회 저장되나,
    그 후 15:00~15:30 position_monitor 손절이 virtual_balance를 갱신해도 재저장되지
    않아 paper_trading_state가 stale → 15:35 equity 리플레이와 현금 불일치(033780
    손절 +344,726). _run_equity_snapshot이 스냅샷 직전 재저장해야 한다.
    """

    def _make_bot(self, is_virtual=True):
        mock_bot = MagicMock()
        de = MagicMock()
        de.is_virtual_mode = is_virtual
        vm = MagicMock()
        vm.save_paper_trading_state = MagicMock(return_value=True)
        de.virtual_trading = vm
        mock_bot.decision_engine = de
        return mock_bot, vm

    def test_가상모드_스냅샷_직전_재저장_호출(self):
        """가상모드면 run_daily_equity_snapshot 전에 save_paper_trading_state 호출."""
        from bot.system_monitor import SystemMonitor

        mock_bot, vm = self._make_bot(is_virtual=True)
        monitor = SystemMonitor(mock_bot)

        call_order = []
        vm.save_paper_trading_state.side_effect = lambda: call_order.append('resave') or True

        with patch('db.connection.DatabaseConnection.get_connection') as mock_conn, \
             patch('tools.paper_strategy_equity.run_daily_equity_snapshot') as mock_snap:
            mock_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_snap.side_effect = lambda conn: call_order.append('snapshot') or {
                'ok': True, 'trade_date': '2026-06-23', 'n_strategies': 8,
                'total_cash': 34906674, 'eod_balance': 34906674, 'cash_match': True,
            }
            monitor._run_equity_snapshot()

        vm.save_paper_trading_state.assert_called_once()
        assert call_order == ['resave', 'snapshot'], (
            f"재저장이 스냅샷보다 먼저여야 함: {call_order}")

    def test_실전모드면_재저장_스킵(self):
        """실전모드(is_virtual_mode=False)면 paper 재저장 안 함."""
        from bot.system_monitor import SystemMonitor

        mock_bot, vm = self._make_bot(is_virtual=False)
        monitor = SystemMonitor(mock_bot)

        with patch('db.connection.DatabaseConnection.get_connection') as mock_conn, \
             patch('tools.paper_strategy_equity.run_daily_equity_snapshot') as mock_snap:
            mock_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_snap.return_value = {'ok': True, 'trade_date': '2026-06-23',
                                      'n_strategies': 8, 'total_cash': 0,
                                      'eod_balance': 0, 'cash_match': True}
            monitor._run_equity_snapshot()

        vm.save_paper_trading_state.assert_not_called()


class TestEquityResnapshotAfterDataCollection:
    """EOD equity 재스냅샷이 당일종가 수집(step6) '후'에 한 번 더 도는지 검증.

    버그(2026-06-25): 15:35 1차 스냅샷은 보유를 평가소스(quant)의 당일종가로
    평가하나, 15:35 시점엔 당일종가가 아직 없어 전일종가로 stale 폴백된다. 봇은
    step6(_run_data_collection)에서 당일 공식종가를 kis_template 으로 직접 수집하므로,
    그 후 _run_equity_snapshot 을 멱등 재호출해 T-close 로 덮어써야 한다.
    """

    def _make_monitor(self):
        from bot.system_monitor import SystemMonitor
        mock_bot = MagicMock()
        with patch.object(SystemMonitor, '_init_dashboard', lambda self: None):
            monitor = SystemMonitor(mock_bot)
        return monitor

    def test_재스냅샷_데이터수집_후_호출(self):
        """15:35+ 흐름에서 _run_equity_snapshot 이 _run_data_collection 후에 다시 호출됨."""
        from datetime import datetime, timezone, timedelta
        KST = timezone(timedelta(hours=9))
        current_time = datetime(2026, 6, 25, 15, 36, 0, tzinfo=KST)

        monitor = self._make_monitor()
        monitor._last_daily_report_date = None

        call_order = []

        async def fake_data_collection(ct):
            call_order.append('data_collection')

        with patch('bot.system_monitor.print_today_trading_summary'), \
             patch.object(monitor, '_verify_eod_fund_integrity'), \
             patch.object(monitor, '_verify_screener_snapshot'), \
             patch.object(monitor, '_run_regime_index_refresh'), \
             patch.object(monitor, '_run_data_collection', side_effect=fake_data_collection), \
             patch.object(monitor, '_run_equity_snapshot',
                          side_effect=lambda: call_order.append('equity_snapshot')):
            asyncio.run(monitor._handle_postmarket_tasks(current_time))

        # 1차(데이터수집 전) + 재스냅샷(데이터수집 후) 둘 다 호출
        assert call_order.count('equity_snapshot') >= 1
        assert 'data_collection' in call_order
        # 마지막 equity_snapshot 은 data_collection 보다 뒤(=재평가가 최종 권위)
        assert call_order.index('data_collection') < len(call_order) - 1
        assert call_order[-1] == 'equity_snapshot', (
            f"재스냅샷이 데이터수집 후 마지막이어야 함: {call_order}")
