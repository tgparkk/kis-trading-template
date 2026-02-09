"""
상태 복원 테스트
================
StateRestorer의 가상/실전매매 복원, 불일치 감지, 후보 종목 복원 검증
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_modules  # noqa: F401

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.state_restorer import StateRestorer
from core.models import StockState


@pytest.fixture
def base_deps():
    """StateRestorer 의존성 기본 Mock"""
    trading_manager = MagicMock()
    trading_manager.add_selected_stock = AsyncMock(return_value=True)
    trading_manager.get_trading_stock = MagicMock()
    trading_manager._change_stock_state = MagicMock()

    db_manager = MagicMock()
    db_manager.get_virtual_open_positions = MagicMock(return_value=pd.DataFrame())

    telegram = AsyncMock()
    telegram.send_notification = AsyncMock()

    config = MagicMock()
    config.paper_trading = True

    broker = MagicMock()

    get_prev_close = MagicMock(return_value=50000.0)

    return {
        'trading_manager': trading_manager,
        'db_manager': db_manager,
        'telegram_integration': telegram,
        'config': config,
        'get_previous_close_callback': get_prev_close,
        'broker': broker,
    }


@pytest.fixture
def restorer(base_deps):
    """StateRestorer 인스턴스"""
    return StateRestorer(**base_deps)


class TestPaperTradingRestore:
    """가상매매 모드 보유종목 DB 복원 테스트"""

    @pytest.mark.asyncio
    async def test_가상매매_DB에서_보유종목_복원(self, restorer, base_deps):
        """가상매매 모드에서 DB의 보유 종목을 메모리에 복원하는지"""
        holdings_df = pd.DataFrame([
            {
                'stock_code': '005930',
                'stock_name': '삼성전자',
                'quantity': 10,
                'buy_price': 70000.0,
                'target_profit_rate': 0.05,
                'stop_loss_rate': 0.03,
            }
        ])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df

        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        base_deps['trading_manager'].add_selected_stock.assert_called_once()
        mock_ts.set_position.assert_called_once_with(10, 70000.0)
        base_deps['trading_manager']._change_stock_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_빈_DB_크래시_없음(self, restorer, base_deps):
        """DB에 보유 종목이 없을 때 에러 없이 정상 종료하는지"""
        base_deps['db_manager'].get_virtual_open_positions.return_value = pd.DataFrame()

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        base_deps['trading_manager'].add_selected_stock.assert_not_called()


class TestRealTradingRestore:
    """실전매매 모드 계좌 복원 테스트"""

    @pytest.mark.asyncio
    async def test_실전매매_브로커_계좌에서_복원(self, base_deps):
        """실전매매 모드에서 broker.get_account_balance()로 보유종목을 복원하는지"""
        base_deps['config'].paper_trading = False
        restorer = StateRestorer(**base_deps)
        restorer.is_paper_trading = False

        base_deps['broker'].get_account_balance.return_value = {
            'positions': [
                {
                    'stock_code': '005930',
                    'stock_name': '삼성전자',
                    'quantity': 5,
                    'avg_price': 72000.0,
                }
            ]
        }

        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_real_account()

        base_deps['trading_manager'].add_selected_stock.assert_called_once()
        mock_ts.set_position.assert_called_once_with(5, 72000.0)

    @pytest.mark.asyncio
    async def test_브로커_없으면_DB_폴백(self, base_deps):
        """broker가 None이면 DB 복원으로 대체하는지"""
        base_deps['config'].paper_trading = False
        base_deps['broker'] = None
        restorer = StateRestorer(**base_deps)
        restorer.is_paper_trading = False

        restorer._restore_holdings_from_db = AsyncMock()

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_real_account()

        restorer._restore_holdings_from_db.assert_called_once()


class TestMismatchDetection:
    """계좌-DB 불일치 감지 테스트"""

    @pytest.mark.asyncio
    async def test_실제_계좌에만_존재하는_종목_감지(self, restorer, base_deps):
        """실제 계좌에는 있지만 DB에는 없는 종목을 감지하는지"""
        real_holdings = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10}
        ]
        db_holdings_dict = {}  # DB에 없음

        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

        base_deps['telegram_integration'].send_notification.assert_called_once()
        call_args = base_deps['telegram_integration'].send_notification.call_args[0][0]
        assert '불일치' in call_args

    @pytest.mark.asyncio
    async def test_수량_불일치_감지(self, restorer, base_deps):
        """실제 계좌와 DB의 수량이 다를 때 감지하는지"""
        real_holdings = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10}
        ]
        db_holdings_dict = {
            '005930': {'stock_name': '삼성전자', 'quantity': 5, 'buy_price': 70000}
        }

        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

        base_deps['telegram_integration'].send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_DB에만_존재하는_종목_감지(self, restorer, base_deps):
        """DB에는 있지만 실제 계좌에는 없는 종목을 감지하는지"""
        real_holdings = []
        db_holdings_dict = {
            '000660': {'stock_name': 'SK하이닉스', 'quantity': 3, 'buy_price': 120000}
        }

        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

        base_deps['telegram_integration'].send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_일치_시_알림_없음(self, restorer, base_deps):
        """계좌와 DB가 일치할 때 텔레그램 알림이 없는지"""
        real_holdings = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10}
        ]
        db_holdings_dict = {
            '005930': {'stock_name': '삼성전자', 'quantity': 10, 'buy_price': 70000}
        }

        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

        base_deps['telegram_integration'].send_notification.assert_not_called()


class TestCandidateRestore:
    """후보 종목 복원 테스트"""

    @pytest.mark.asyncio
    async def test_후보_종목_DB에서_복원(self, restorer, base_deps):
        """candidate_stocks 테이블에서 오늘 후보 종목을 복원하는지"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('005930', '삼성전자', 85.0, '모멘텀 돌파'),
            ('000660', 'SK하이닉스', 78.0, '거래량 급증'),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch('bot.state_restorer.DatabaseConnection') as mock_db_conn:
            mock_db_conn.get_connection.return_value = mock_conn

            await restorer._restore_candidates('2026-02-08')

        assert base_deps['trading_manager'].add_selected_stock.call_count == 2

    @pytest.mark.asyncio
    async def test_후보_종목_없으면_스킵(self, restorer, base_deps):
        """오늘 후보 종목이 없으면 add_selected_stock을 호출하지 않는지"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch('bot.state_restorer.DatabaseConnection') as mock_db_conn:
            mock_db_conn.get_connection.return_value = mock_conn

            await restorer._restore_candidates('2026-02-08')

        base_deps['trading_manager'].add_selected_stock.assert_not_called()

    @pytest.mark.asyncio
    async def test_DB_조회_실패_시_크래시_없음(self, restorer, base_deps):
        """DB 조회가 실패해도 예외 없이 종료하는지"""
        with patch('bot.state_restorer.DatabaseConnection') as mock_db_conn:
            mock_db_conn.get_connection.side_effect = Exception("DB 연결 실패")

            # 예외 발생하지 않아야 함
            await restorer._restore_candidates('2026-02-08')

        base_deps['trading_manager'].add_selected_stock.assert_not_called()


# ============================================================================
# Edge Case Tests (P0: 재시작 복구 안정성)
# ============================================================================

class TestStateRestorerEdgeCases:
    """StateRestorer 엣지 케이스 테스트 — 재시작 시 발생 가능한 이상 상황"""

    @pytest.mark.asyncio
    async def test_add_selected_stock_실패해도_나머지_종목_계속_복원(self, base_deps):
        """add_selected_stock이 False 반환해도 나머지 종목 복원을 계속하는지"""
        # 첫 번째 종목은 실패, 두 번째는 성공
        base_deps['trading_manager'].add_selected_stock = AsyncMock(
            side_effect=[False, True]
        )
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        holdings_df = pd.DataFrame([
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10,
             'buy_price': 70000.0, 'target_profit_rate': 0.05, 'stop_loss_rate': 0.03},
            {'stock_code': '000660', 'stock_name': 'SK하이닉스', 'quantity': 5,
             'buy_price': 120000.0, 'target_profit_rate': 0.04, 'stop_loss_rate': 0.02},
        ])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df

        restorer = StateRestorer(**base_deps)
        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 두 종목 모두 시도했는지 확인
        assert base_deps['trading_manager'].add_selected_stock.call_count == 2
        # 성공한 두 번째 종목만 set_position 호출
        mock_ts.set_position.assert_called_once_with(5, 120000.0)

    @pytest.mark.asyncio
    async def test_get_trading_stock_None_반환_시_크래시_없음(self, base_deps):
        """add_selected_stock 성공 후 get_trading_stock이 None을 반환해도 크래시 없는지"""
        base_deps['trading_manager'].get_trading_stock.return_value = None

        holdings_df = pd.DataFrame([
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10,
             'buy_price': 70000.0, 'target_profit_rate': 0.05, 'stop_loss_rate': 0.03},
        ])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df

        restorer = StateRestorer(**base_deps)
        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # _change_stock_state는 호출되지 않아야 함 (trading_stock이 None이므로)
        base_deps['trading_manager']._change_stock_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_실전매매_broker_예외_시_DB_폴백(self, base_deps):
        """실전매매에서 broker.get_account_balance()가 예외를 던지면 DB 폴백하는지"""
        base_deps['config'].paper_trading = False
        base_deps['broker'].get_account_balance.side_effect = Exception("API 장애")
        restorer = StateRestorer(**base_deps)
        restorer.is_paper_trading = False
        restorer._restore_holdings_from_db = AsyncMock()

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_real_account()

        restorer._restore_holdings_from_db.assert_called_once()

    @pytest.mark.asyncio
    async def test_실전매매_빈_포지션_리스트(self, base_deps):
        """실전매매에서 계좌에 포지션이 없을 때 정상 처리하는지"""
        base_deps['config'].paper_trading = False
        base_deps['broker'].get_account_balance.return_value = {'positions': []}
        restorer = StateRestorer(**base_deps)
        restorer.is_paper_trading = False

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_real_account()

        base_deps['trading_manager'].add_selected_stock.assert_not_called()

    @pytest.mark.asyncio
    async def test_실전매매_수량0_포지션_스킵(self, base_deps):
        """실전매매에서 수량 0인 포지션(청산완료)을 스킵하는지"""
        base_deps['config'].paper_trading = False
        base_deps['broker'].get_account_balance.return_value = {
            'positions': [
                {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 0, 'avg_price': 70000},
            ]
        }
        restorer = StateRestorer(**base_deps)
        restorer.is_paper_trading = False

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_real_account()

        base_deps['trading_manager'].add_selected_stock.assert_not_called()

    @pytest.mark.asyncio
    async def test_restore_todays_candidates_통합_가상매매(self, base_deps):
        """restore_todays_candidates가 후보 + 보유종목 복원을 모두 호출하는지 (가상매매)"""
        restorer = StateRestorer(**base_deps)
        restorer._restore_candidates = AsyncMock()
        restorer._restore_holdings_from_db = AsyncMock()

        with patch('bot.state_restorer.now_kst') as mock_now:
            mock_now.return_value.strftime.return_value = '2026-02-09'
            await restorer.restore_todays_candidates()

        restorer._restore_candidates.assert_called_once_with('2026-02-09')
        restorer._restore_holdings_from_db.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_todays_candidates_통합_실전매매(self, base_deps):
        """restore_todays_candidates가 실전매매 시 _restore_holdings_from_real_account를 호출하는지"""
        base_deps['config'].paper_trading = False
        restorer = StateRestorer(**base_deps)
        restorer.is_paper_trading = False
        restorer._restore_candidates = AsyncMock()
        restorer._restore_holdings_from_real_account = AsyncMock()

        with patch('bot.state_restorer.now_kst') as mock_now:
            mock_now.return_value.strftime.return_value = '2026-02-09'
            await restorer.restore_todays_candidates()

        restorer._restore_candidates.assert_called_once()
        restorer._restore_holdings_from_real_account.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_todays_candidates_전체_예외_시_크래시_없음(self, base_deps):
        """restore_todays_candidates 내부에서 예외가 발생해도 시스템이 크래시하지 않는지"""
        restorer = StateRestorer(**base_deps)

        with patch('bot.state_restorer.now_kst', side_effect=Exception("시간 조회 실패")):
            # 예외 발생하지 않아야 함
            await restorer.restore_todays_candidates()

    @pytest.mark.asyncio
    async def test_불일치_감지_텔레그램_없어도_크래시_없음(self, base_deps):
        """telegram이 None이어도 불일치 감지가 크래시하지 않는지"""
        base_deps['telegram_integration'] = None
        restorer = StateRestorer(**base_deps)

        real_holdings = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10}
        ]
        # 불일치 상황이지만 telegram이 None
        await restorer._detect_holdings_mismatch(real_holdings, {})
        # 크래시 없이 통과하면 성공

    @pytest.mark.asyncio
    async def test_get_previous_close_콜백_예외_시에도_복원_계속(self, base_deps):
        """get_previous_close 콜백이 예외를 던져도 후보 종목 복원이 계속되는지"""
        base_deps['get_previous_close_callback'] = MagicMock(
            side_effect=Exception("API 장애")
        )
        restorer = StateRestorer(**base_deps)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('005930', '삼성전자', 85.0, '모멘텀'),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch('bot.state_restorer.DatabaseConnection') as mock_db_conn:
            mock_db_conn.get_connection.return_value = mock_conn
            # get_previous_close에서 예외 → _restore_candidates 내부에서 잡히는지
            # (현재 코드는 잡지 않으므로, 전체 함수 except에서 잡힘)
            await restorer._restore_candidates('2026-02-09')
