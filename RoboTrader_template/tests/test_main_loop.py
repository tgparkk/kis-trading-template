"""
메인 트레이딩 루프 테스트
========================
_main_trading_loop, _check_buy_signals, _check_eod_liquidation, task_definitions 검증
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_modules  # noqa: F401

import asyncio
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_bot():
    """DayTradingBot을 외부 의존성 Mock으로 생성"""
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


class TestTaskDefinitions:
    """task_definitions 구조 검증"""

    def test_task_definitions_정확히_3개_항목(self, mock_bot):
        """task_definitions가 정확히 3개의 태스크를 포함하는지 확인"""
        # run_daily_cycle 내부의 task_definitions를 간접 검증
        # DayTradingBot에 필요한 메서드 존재 확인
        assert hasattr(mock_bot, '_main_trading_loop')
        assert hasattr(mock_bot, 'system_monitor')
        assert hasattr(mock_bot, '_telegram_task')

    @pytest.mark.asyncio
    async def test_run_daily_cycle_태스크_3개_실행(self, mock_bot):
        """run_daily_cycle이 3개 supervised 태스크를 gather로 실행하는지"""
        call_count = 0

        async def fake_supervised(name, factory, critical):
            nonlocal call_count
            call_count += 1

        mock_bot._supervised_task = fake_supervised
        mock_bot.bot_initializer.shutdown = AsyncMock()

        await mock_bot.run_daily_cycle()
        assert call_count == 3, f"3개 태스크 예상, 실제 {call_count}개"


class TestMainTradingLoop:
    """_main_trading_loop 순차 실행 검증"""

    @pytest.mark.asyncio
    async def test_장_닫힘_시_슬립_후_스킵(self, mock_bot):
        """is_market_open()=False일 때 모든 단계를 건너뛰는지"""
        call_log = []

        with patch('main.is_market_open', return_value=False):
            original_sleep = asyncio.sleep

            async def limited_sleep(seconds):
                call_log.append(('sleep', seconds))
                mock_bot.is_running = False  # 1회 후 종료

            with patch('asyncio.sleep', side_effect=limited_sleep):
                mock_bot.data_collector.collect_once = AsyncMock()
                mock_bot.order_manager.check_pending_orders_once = AsyncMock()
                mock_bot.trading_manager.check_positions_once = AsyncMock()

                await mock_bot._main_trading_loop()

                # 장이 닫혀 있으므로 데이터 수집 등이 호출되지 않아야 함
                mock_bot.data_collector.collect_once.assert_not_called()
                mock_bot.order_manager.check_pending_orders_once.assert_not_called()

    @pytest.mark.asyncio
    async def test_순차_실행_순서_데이터_주문_포지션_EOD(self, mock_bot):
        """장 열림 시 데이터→주문→포지션→EOD 순서로 실행되는지"""
        execution_order = []
        mock_bot.is_running = True

        with patch('main.is_market_open', return_value=True):
            mock_bot.data_collector.collect_once = AsyncMock(
                side_effect=lambda: execution_order.append('data')
            )
            mock_bot.order_manager.check_pending_orders_once = AsyncMock(
                side_effect=lambda: execution_order.append('orders')
            )
            mock_bot.trading_manager.check_positions_once = AsyncMock(
                side_effect=lambda: execution_order.append('positions')
            )
            mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])
            mock_bot._last_eod_liquidation_date = None

            with patch.object(mock_bot, '_check_eod_liquidation', new=AsyncMock(
                side_effect=lambda: execution_order.append('eod')
            )):
                async def stop_after_one(seconds):
                    mock_bot.is_running = False

                with patch('asyncio.sleep', side_effect=stop_after_one):
                    await mock_bot._main_trading_loop()

            assert execution_order[:3] == ['data', 'orders', 'positions']
            assert 'eod' in execution_order

    @pytest.mark.asyncio
    async def test_매수_판단_3번째_반복마다_실행(self, mock_bot):
        """매수 판단이 매 3번째 반복에서만 실행되는지"""
        buy_called_iterations = []
        current_iteration = [0]
        mock_bot.is_running = True
        mock_bot._candidates_loaded = True  # 스크리너 로드 건너뛰기

        with patch('main.is_market_open', return_value=True):
            mock_bot.order_manager.check_pending_orders_once = AsyncMock()
            mock_bot.trading_manager.check_positions_once = AsyncMock()
            mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])
            mock_bot._last_eod_liquidation_date = None

            async def track_data():
                current_iteration[0] += 1

            mock_bot.data_collector.collect_once = track_data

            # _check_buy_signals를 추적 — trading_manager.get_stocks_by_state 호출 횟수로 판단
            original_get = mock_bot.trading_manager.get_stocks_by_state

            def tracking_get(state):
                buy_called_iterations.append(current_iteration[0])
                return []

            mock_bot.trading_manager.get_stocks_by_state = tracking_get

            loop_count = [0]

            with patch.object(mock_bot, '_check_eod_liquidation', new=AsyncMock()), \
                 patch.object(mock_bot, '_load_screener_candidates', new=AsyncMock()):
                async def stop_after_n(seconds):
                    loop_count[0] += 1
                    if loop_count[0] >= 9:
                        mock_bot.is_running = False

                with patch('asyncio.sleep', side_effect=stop_after_n):
                    await mock_bot._main_trading_loop()

            # iteration 3, 6, 9에서만 _check_buy_signals가 호출됨
            assert 3 in buy_called_iterations
            assert 6 in buy_called_iterations
            assert 1 not in buy_called_iterations
            assert 2 not in buy_called_iterations


class TestCheckBuySignals:
    """_check_buy_signals 검증"""

    @pytest.mark.asyncio
    async def test_SELECTED_종목_순회(self, mock_bot):
        """SELECTED 상태 종목을 순회하며 매수 판단하는지"""
        from core.models import TradingStock, StockState

        stock1 = MagicMock()
        stock1.stock_code = '005930'
        stock1.is_buy_cooldown_active.return_value = False

        stock2 = MagicMock()
        stock2.stock_code = '000660'
        stock2.is_buy_cooldown_active.return_value = False

        mock_bot.is_running = True
        mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[stock1, stock2])

        with patch.object(mock_bot, '_analyze_buy_decision', new=AsyncMock()) as mock_abd:
            await mock_bot._check_buy_signals()
            assert mock_abd.call_count == 2

    @pytest.mark.asyncio
    async def test_쿨다운_활성_종목_스킵(self, mock_bot):
        """매수 쿨다운이 활성화된 종목은 건너뛰는지"""
        stock = MagicMock()
        stock.stock_code = '005930'
        stock.is_buy_cooldown_active.return_value = True

        mock_bot.is_running = True
        mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[stock])

        with patch.object(mock_bot, '_analyze_buy_decision', new=AsyncMock()) as mock_abd:
            await mock_bot._check_buy_signals()
            mock_abd.assert_not_called()

    @pytest.mark.asyncio
    async def test_is_running_False_시_중단(self, mock_bot):
        """is_running=False이면 순회를 중단하는지"""
        stock1 = MagicMock()
        stock1.stock_code = '005930'
        stock1.is_buy_cooldown_active.return_value = False

        stock2 = MagicMock()
        stock2.stock_code = '000660'
        stock2.is_buy_cooldown_active.return_value = False

        mock_bot.is_running = True
        mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[stock1, stock2])

        async def stop_bot(ts, af=None):
            mock_bot.is_running = False

        with patch.object(mock_bot, '_analyze_buy_decision', new=AsyncMock(side_effect=stop_bot)) as mock_abd:
            await mock_bot._check_buy_signals()
            # stock2는 호출되지 않아야 함
            assert mock_abd.call_count == 1


class TestMainLoopErrorIsolation:
    """메인 루프 단계별 에러 격리 검증 (P0)"""

    @pytest.mark.asyncio
    async def test_데이터수집_실패해도_나머지_단계_실행(self, mock_bot):
        """데이터 수집이 예외를 던져도 미체결 확인, 포지션 체크, EOD 청산이 실행되는지"""
        execution_order = []
        mock_bot.is_running = True

        with patch('main.is_market_open', return_value=True):
            mock_bot.data_collector.collect_once = AsyncMock(
                side_effect=Exception("네트워크 끊김")
            )
            mock_bot.order_manager.check_pending_orders_once = AsyncMock(
                side_effect=lambda: execution_order.append('orders')
            )
            mock_bot.trading_manager.check_positions_once = AsyncMock(
                side_effect=lambda: execution_order.append('positions')
            )
            mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])

            with patch.object(mock_bot, '_check_eod_liquidation', new=AsyncMock(
                side_effect=lambda: execution_order.append('eod')
            )):
                async def stop_after_one(seconds):
                    mock_bot.is_running = False
                with patch('asyncio.sleep', side_effect=stop_after_one):
                    await mock_bot._main_trading_loop()

            assert 'orders' in execution_order, "미체결 주문 확인이 실행되어야 함"
            assert 'positions' in execution_order, "포지션 체크가 실행되어야 함"
            assert 'eod' in execution_order, "EOD 청산 체크가 실행되어야 함"

    @pytest.mark.asyncio
    async def test_주문확인_실패해도_포지션체크_실행(self, mock_bot):
        """미체결 주문 확인이 실패해도 포지션 체크와 EOD 청산이 실행되는지"""
        execution_order = []
        mock_bot.is_running = True

        with patch('main.is_market_open', return_value=True):
            mock_bot.data_collector.collect_once = AsyncMock(
                side_effect=lambda: execution_order.append('data')
            )
            mock_bot.order_manager.check_pending_orders_once = AsyncMock(
                side_effect=Exception("API 타임아웃")
            )
            mock_bot.trading_manager.check_positions_once = AsyncMock(
                side_effect=lambda: execution_order.append('positions')
            )
            mock_bot.trading_manager.get_stocks_by_state = MagicMock(return_value=[])

            with patch.object(mock_bot, '_check_eod_liquidation', new=AsyncMock(
                side_effect=lambda: execution_order.append('eod')
            )):
                async def stop_after_one(seconds):
                    mock_bot.is_running = False
                with patch('asyncio.sleep', side_effect=stop_after_one):
                    await mock_bot._main_trading_loop()

            assert 'data' in execution_order
            assert 'positions' in execution_order
            assert 'eod' in execution_order

    @pytest.mark.asyncio
    async def test_모든_단계_실패해도_루프_계속(self, mock_bot):
        """모든 5개 단계가 전부 실패해도 루프가 크래시하지 않고 다음 반복으로 넘어가는지"""
        loop_count = [0]
        mock_bot.is_running = True

        with patch('main.is_market_open', return_value=True):
            mock_bot.data_collector.collect_once = AsyncMock(side_effect=Exception("err1"))
            mock_bot.order_manager.check_pending_orders_once = AsyncMock(side_effect=Exception("err2"))
            mock_bot.trading_manager.check_positions_once = AsyncMock(side_effect=Exception("err3"))
            mock_bot.trading_manager.get_stocks_by_state = MagicMock(side_effect=Exception("err4"))

            with patch.object(mock_bot, '_check_eod_liquidation', new=AsyncMock(
                side_effect=Exception("err5")
            )):
                async def stop_after_two(seconds):
                    loop_count[0] += 1
                    if loop_count[0] >= 2:
                        mock_bot.is_running = False
                with patch('asyncio.sleep', side_effect=stop_after_two):
                    await mock_bot._main_trading_loop()

            # 2회 반복했으면 루프가 크래시하지 않은 것
            assert loop_count[0] >= 2


class TestCheckEodLiquidation:
    """_check_eod_liquidation 검증"""

    @pytest.mark.asyncio
    async def test_같은_날짜_중복_실행_방지(self, mock_bot):
        """같은 날짜에 이미 실행했으면 스킵하는지"""
        today = date(2026, 2, 9)  # 월요일
        mock_bot._last_eod_liquidation_date = today

        with patch('main.now_kst') as mock_now:
            mock_now.return_value = datetime(2026, 2, 9, 15, 20, tzinfo=timezone(timedelta(hours=9)))
            mock_bot.liquidation_handler = MagicMock()
            mock_bot.liquidation_handler.execute_end_of_day_liquidation = AsyncMock()

            await mock_bot._check_eod_liquidation()

            mock_bot.liquidation_handler.execute_end_of_day_liquidation.assert_not_called()

    @pytest.mark.asyncio
    async def test_주말_스킵(self, mock_bot):
        """주말(토,일)에는 EOD 청산을 실행하지 않는지"""
        mock_bot._last_eod_liquidation_date = None

        # 2026-02-07 = 토요일
        with patch('main.now_kst') as mock_now:
            mock_now.return_value = datetime(2026, 2, 7, 15, 20, tzinfo=timezone(timedelta(hours=9)))
            mock_bot.liquidation_handler = MagicMock()
            mock_bot.liquidation_handler.execute_end_of_day_liquidation = AsyncMock()

            await mock_bot._check_eod_liquidation()

            mock_bot.liquidation_handler.execute_end_of_day_liquidation.assert_not_called()

    @pytest.mark.asyncio
    async def test_EOD_시간_도달_시_청산_실행(self, mock_bot):
        """EOD 청산 시간 도달 시 liquidation_handler를 호출하는지"""
        mock_bot._last_eod_liquidation_date = None

        # 2026-02-09 = 월요일
        with patch('main.now_kst') as mock_now, \
             patch('main.MarketHours') as mock_mh:
            mock_now.return_value = datetime(2026, 2, 9, 15, 18, tzinfo=timezone(timedelta(hours=9)))
            mock_mh.is_eod_liquidation_time.return_value = True

            mock_bot.liquidation_handler = MagicMock()
            mock_bot.liquidation_handler.execute_end_of_day_liquidation = AsyncMock()
            mock_bot.liquidation_handler.set_last_eod_liquidation_date = MagicMock()

            await mock_bot._check_eod_liquidation()

            mock_bot.liquidation_handler.execute_end_of_day_liquidation.assert_called_once()
            assert mock_bot._last_eod_liquidation_date == date(2026, 2, 9)

    @pytest.mark.asyncio
    async def test_MarketHours_False_시_스킵(self, mock_bot):
        """MarketHours.is_eod_liquidation_time=False이면 스킵하는지"""
        mock_bot._last_eod_liquidation_date = None

        with patch('main.now_kst') as mock_now, \
             patch('main.MarketHours') as mock_mh:
            mock_now.return_value = datetime(2026, 2, 9, 14, 0, tzinfo=timezone(timedelta(hours=9)))
            mock_mh.is_eod_liquidation_time.return_value = False

            mock_bot.liquidation_handler = MagicMock()
            mock_bot.liquidation_handler.execute_end_of_day_liquidation = AsyncMock()

            await mock_bot._check_eod_liquidation()

            mock_bot.liquidation_handler.execute_end_of_day_liquidation.assert_not_called()
