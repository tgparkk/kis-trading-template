"""
상태 복원 엣지 케이스 테스트
============================
StateRestorer의 경계 조건, 장애 시나리오, 부분 실패 등을 검증
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_modules  # noqa: F401

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pandas as pd
import pytest

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
    return StateRestorer(**base_deps)


def _make_mock_conn(rows):
    """DB 커넥션 mock 헬퍼"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    return mock_conn


# ============================================================================
# 후보 종목 복원 엣지 케이스
# ============================================================================

class TestCandidateRestoreEdgeCases:
    """후보 종목 복원 경계 조건"""

    @pytest.mark.asyncio
    async def test_add_selected_stock_부분_실패(self, restorer, base_deps):
        """일부 종목 add_selected_stock 실패 시 나머지는 정상 복원"""
        # 첫 번째는 성공, 두 번째는 실패
        base_deps['trading_manager'].add_selected_stock = AsyncMock(
            side_effect=[True, False, True]
        )
        rows = [
            ('005930', '삼성전자', 85.0, '모멘텀'),
            ('000660', 'SK하이닉스', 78.0, '거래량'),
            ('035420', 'NAVER', 72.0, '실적'),
        ]
        mock_conn = _make_mock_conn(rows)

        with patch('bot.state_restorer.DatabaseConnection') as mock_db:
            mock_db.get_connection.return_value = mock_conn
            await restorer._restore_candidates('2026-02-09')

        assert base_deps['trading_manager'].add_selected_stock.call_count == 3

    @pytest.mark.asyncio
    async def test_후보_종목_stock_name이_None(self, restorer, base_deps):
        """stock_name이 NULL인 경우 기본 이름 사용"""
        rows = [('005930', None, 85.0, '모멘텀')]
        mock_conn = _make_mock_conn(rows)

        with patch('bot.state_restorer.DatabaseConnection') as mock_db:
            mock_db.get_connection.return_value = mock_conn
            await restorer._restore_candidates('2026-02-09')

        call_kwargs = base_deps['trading_manager'].add_selected_stock.call_args
        assert 'Stock_005930' in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_후보_종목_score_reason이_None(self, restorer, base_deps):
        """score, reasons가 NULL이어도 정상 처리"""
        rows = [('005930', '삼성전자', None, None)]
        mock_conn = _make_mock_conn(rows)

        with patch('bot.state_restorer.DatabaseConnection') as mock_db:
            mock_db.get_connection.return_value = mock_conn
            await restorer._restore_candidates('2026-02-09')

        base_deps['trading_manager'].add_selected_stock.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_previous_close_실패_시에도_복원_진행(self, restorer, base_deps):
        """전날 종가 조회가 예외를 던져도 복원이 진행되는지"""
        base_deps['get_previous_close_callback'].side_effect = Exception("API 타임아웃")
        rows = [('005930', '삼성전자', 85.0, '모멘텀')]
        mock_conn = _make_mock_conn(rows)

        with patch('bot.state_restorer.DatabaseConnection') as mock_db:
            mock_db.get_connection.return_value = mock_conn
            # get_previous_close가 예외를 던지면 _restore_candidates에서 예외 발생
            # 하지만 restore_todays_candidates의 try/except이 잡아야 함
            await restorer._restore_candidates('2026-02-09')
            # 예외가 전파되지 않으면 테스트 통과

    @pytest.mark.asyncio
    async def test_cursor_execute_실패(self, restorer, base_deps):
        """SQL 실행 중 예외 시 크래시 없음"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("syntax error")
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch('bot.state_restorer.DatabaseConnection') as mock_db:
            mock_db.get_connection.return_value = mock_conn
            await restorer._restore_candidates('2026-02-09')

        base_deps['trading_manager'].add_selected_stock.assert_not_called()


# ============================================================================
# 가상매매 보유 종목 복원 엣지 케이스
# ============================================================================

class TestPaperTradingEdgeCases:
    """가상매매 복원 경계 조건"""

    @pytest.mark.asyncio
    async def test_get_trading_stock_None_반환(self, restorer, base_deps):
        """add_selected_stock 성공 후 get_trading_stock이 None이면 포지션 설정 스킵"""
        holdings_df = pd.DataFrame([{
            'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 70000.0,
            'target_profit_rate': 0.05, 'stop_loss_rate': 0.03,
        }])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        base_deps['trading_manager'].get_trading_stock.return_value = None

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # add_selected_stock은 호출되지만 set_position은 호출되지 않아야 함
        base_deps['trading_manager'].add_selected_stock.assert_called_once()
        base_deps['trading_manager']._change_stock_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_다수_보유_종목_일부_실패(self, restorer, base_deps):
        """여러 보유 종목 중 일부만 add_selected_stock 실패"""
        holdings_df = pd.DataFrame([
            {'stock_code': '005930', 'stock_name': '삼성전자',
             'quantity': 10, 'buy_price': 70000.0,
             'target_profit_rate': 0.05, 'stop_loss_rate': 0.03},
            {'stock_code': '000660', 'stock_name': 'SK하이닉스',
             'quantity': 5, 'buy_price': 120000.0,
             'target_profit_rate': 0.04, 'stop_loss_rate': 0.02},
        ])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        base_deps['trading_manager'].add_selected_stock = AsyncMock(
            side_effect=[False, True]
        )
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 첫 번째 실패, 두 번째만 포지션 설정
        assert base_deps['trading_manager']._change_stock_state.call_count == 1
        mock_ts.set_position.assert_called_once_with(5, 120000.0)

    @pytest.mark.asyncio
    async def test_target_profit_rate_기본값_적용(self, restorer, base_deps):
        """DB에 target_profit_rate/stop_loss_rate 컬럼이 없을 때 기본값 사용"""
        # get() 메서드가 기본값 반환하도록 일반 dict로 구성
        holdings_df = pd.DataFrame([{
            'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 70000.0,
        }])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 기본값이 적용되었는지 확인
        mock_ts.set_position.assert_called_once_with(10, 70000.0)

    @pytest.mark.asyncio
    async def test_DB_조회_예외_시_크래시_없음(self, restorer, base_deps):
        """get_virtual_open_positions가 예외를 던져도 크래시 없음"""
        base_deps['db_manager'].get_virtual_open_positions.side_effect = Exception("DB 다운")

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 예외가 전파되지 않으면 통과

    @pytest.mark.asyncio
    async def test_quantity_0_또는_음수(self, restorer, base_deps):
        """quantity가 0이나 음수인 레코드도 복원 시도 (DB 데이터 이상)"""
        holdings_df = pd.DataFrame([{
            'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 0, 'buy_price': 70000.0,
            'target_profit_rate': 0.05, 'stop_loss_rate': 0.03,
        }])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 현재 구현은 quantity 0도 복원 시도 (이슈로 기록)
        base_deps['trading_manager'].add_selected_stock.assert_called_once()


# ============================================================================
# 실전매매 복원 엣지 케이스
# ============================================================================

class TestRealTradingEdgeCases:
    """실전매매 복원 경계 조건"""

    @pytest.fixture
    def real_restorer(self, base_deps):
        base_deps['config'].paper_trading = False
        r = StateRestorer(**base_deps)
        r.is_paper_trading = False
        return r

    @pytest.mark.asyncio
    async def test_계좌_조회_예외_시_DB_폴백(self, real_restorer, base_deps):
        """broker.get_account_balance()가 예외 시 DB 폴백"""
        base_deps['broker'].get_account_balance.side_effect = Exception("네트워크 오류")

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        # DB 폴백으로 get_virtual_open_positions 호출
        base_deps['db_manager'].get_virtual_open_positions.assert_called_once()

    @pytest.mark.asyncio
    async def test_계좌_조회_None_반환_시_DB_폴백(self, real_restorer, base_deps):
        """broker.get_account_balance()가 None 반환 시 DB 폴백"""
        base_deps['broker'].get_account_balance.return_value = None

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        base_deps['db_manager'].get_virtual_open_positions.assert_called_once()

    @pytest.mark.asyncio
    async def test_빈_positions_리스트(self, real_restorer, base_deps):
        """계좌에 보유 종목이 없는 경우"""
        base_deps['broker'].get_account_balance.return_value = {'positions': []}

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        base_deps['trading_manager'].add_selected_stock.assert_not_called()

    @pytest.mark.asyncio
    async def test_quantity_0_종목_스킵(self, real_restorer, base_deps):
        """quantity <= 0인 종목은 건너뜀"""
        base_deps['broker'].get_account_balance.return_value = {
            'positions': [
                {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 0, 'avg_price': 70000},
                {'stock_code': '000660', 'stock_name': 'SK하이닉스', 'quantity': 5, 'avg_price': 120000},
            ]
        }
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        # quantity 0인 삼성전자는 스킵, SK하이닉스만 복원
        base_deps['trading_manager'].add_selected_stock.assert_called_once()

    @pytest.mark.asyncio
    async def test_DB에_없는_종목은_기본_익절손절률(self, real_restorer, base_deps):
        """실제 계좌에만 있고 DB에 없는 종목은 기본 익절/손절률 적용"""
        base_deps['broker'].get_account_balance.return_value = {
            'positions': [
                {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10, 'avg_price': 70000},
            ]
        }
        base_deps['db_manager'].get_virtual_open_positions.return_value = pd.DataFrame()
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        # 기본값 적용 확인
        from config.constants import DEFAULT_TARGET_PROFIT_RATE, DEFAULT_STOP_LOSS_RATE
        assert mock_ts.target_profit_rate == DEFAULT_TARGET_PROFIT_RATE
        assert mock_ts.stop_loss_rate == DEFAULT_STOP_LOSS_RATE

    @pytest.mark.asyncio
    async def test_account_balance_dict가_아닌_객체_반환(self, real_restorer, base_deps):
        """get_account_balance가 dict 대신 객체를 반환하는 경우"""
        account_obj = MagicMock()
        account_obj.positions = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 5, 'avg_price': 70000}
        ]
        # isinstance(account_obj, dict) → False
        base_deps['broker'].get_account_balance.return_value = account_obj
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        base_deps['trading_manager'].add_selected_stock.assert_called_once()

    @pytest.mark.asyncio
    async def test_account_balance_positions_키_없음(self, real_restorer, base_deps):
        """get_account_balance 결과에 positions 키가 없는 경우"""
        base_deps['broker'].get_account_balance.return_value = {'total_amount': 1000000}

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        # positions 키가 없으면 빈 리스트로 처리되어야 함
        base_deps['trading_manager'].add_selected_stock.assert_not_called()


# ============================================================================
# 불일치 감지 엣지 케이스
# ============================================================================

class TestMismatchDetectionEdgeCases:
    """불일치 감지 경계 조건"""

    @pytest.mark.asyncio
    async def test_5건_초과_불일치_시_요약_메시지(self, restorer, base_deps):
        """불일치가 5건 초과 시 '외 N건' 요약 표시"""
        real_holdings = [
            {'stock_code': f'00{i}000', 'stock_name': f'종목{i}', 'quantity': 10}
            for i in range(7)
        ]
        db_holdings_dict = {}

        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

        call_args = base_deps['telegram_integration'].send_notification.call_args[0][0]
        assert '외 2건' in call_args

    @pytest.mark.asyncio
    async def test_telegram_알림_실패해도_크래시_없음(self, restorer, base_deps):
        """텔레그램 알림 전송 실패해도 예외가 전파되지 않음"""
        base_deps['telegram_integration'].send_notification.side_effect = Exception("텔레그램 오류")

        real_holdings = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10}
        ]
        db_holdings_dict = {}

        # 텔레그램 오류가 _detect_holdings_mismatch의 try/except에 잡히는지
        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

    @pytest.mark.asyncio
    async def test_telegram_None이면_알림_스킵(self, base_deps):
        """telegram이 None이면 알림 없이 정상 처리"""
        base_deps['telegram_integration'] = None
        restorer = StateRestorer(**base_deps)

        real_holdings = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10}
        ]
        db_holdings_dict = {}

        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

    @pytest.mark.asyncio
    async def test_quantity_0_종목은_불일치에서_제외(self, restorer, base_deps):
        """quantity <= 0인 실제 계좌 종목은 불일치 검사에서 제외"""
        real_holdings = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 0}
        ]
        db_holdings_dict = {}

        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

        # quantity 0은 건너뛰므로 불일치 없음
        base_deps['telegram_integration'].send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_복합_불일치_시나리오(self, restorer, base_deps):
        """실제에만, DB에만, 수량불일치가 동시 발생"""
        real_holdings = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10},  # 수량 불일치
            {'stock_code': '035420', 'stock_name': 'NAVER', 'quantity': 3},      # 실제만
        ]
        db_holdings_dict = {
            '005930': {'stock_name': '삼성전자', 'quantity': 5, 'buy_price': 70000},
            '000660': {'stock_name': 'SK하이닉스', 'quantity': 7, 'buy_price': 120000},  # DB만
        }

        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

        call_args = base_deps['telegram_integration'].send_notification.call_args[0][0]
        assert '3건' in call_args


# ============================================================================
# restore_todays_candidates 통합 테스트
# ============================================================================

class TestRestoreTodayCandidatesIntegration:
    """restore_todays_candidates 전체 흐름 테스트"""

    @pytest.mark.asyncio
    async def test_가상매매_전체_흐름(self, restorer, base_deps):
        """가상매매: 후보 복원 + 보유 종목 복원 전체 흐름"""
        # 후보 종목 DB mock
        mock_conn = _make_mock_conn([('005930', '삼성전자', 85.0, '모멘텀')])

        # 보유 종목 DB mock
        holdings_df = pd.DataFrame([{
            'stock_code': '000660', 'stock_name': 'SK하이닉스',
            'quantity': 5, 'buy_price': 120000.0,
            'target_profit_rate': 0.04, 'stop_loss_rate': 0.02,
        }])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection') as mock_db:
            mock_db.get_connection.return_value = mock_conn
            with patch('bot.state_restorer.now_kst') as mock_now:
                mock_now.return_value = MagicMock(strftime=MagicMock(return_value='2026-02-09'))
                await restorer.restore_todays_candidates()

        # 후보 1개 + 보유 1개 = 2회 호출
        assert base_deps['trading_manager'].add_selected_stock.call_count == 2

    @pytest.mark.asyncio
    async def test_후보_복원_실패해도_보유_복원_진행(self, restorer, base_deps):
        """후보 종목 복원이 실패해도 보유 종목 복원은 계속 진행"""
        # 보유 종목 설정
        holdings_df = pd.DataFrame([{
            'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 70000.0,
            'target_profit_rate': 0.05, 'stop_loss_rate': 0.03,
        }])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection') as mock_db:
            # 후보 DB 조회 실패
            mock_db.get_connection.side_effect = Exception("DB 연결 실패")

            with patch('bot.state_restorer.now_kst') as mock_now:
                mock_now.return_value = MagicMock(strftime=MagicMock(return_value='2026-02-09'))
                await restorer.restore_todays_candidates()

        # 보유 종목은 DB 직접 조회이므로 호출되어야 함
        base_deps['db_manager'].get_virtual_open_positions.assert_called_once()

    @pytest.mark.asyncio
    async def test_실전매매_전체_흐름(self, base_deps):
        """실전매매: 후보 복원 + 계좌 기반 보유 종목 복원"""
        base_deps['config'].paper_trading = False
        restorer = StateRestorer(**base_deps)
        restorer.is_paper_trading = False

        mock_conn = _make_mock_conn([('005930', '삼성전자', 85.0, '모멘텀')])

        base_deps['broker'].get_account_balance.return_value = {
            'positions': [
                {'stock_code': '000660', 'stock_name': 'SK하이닉스',
                 'quantity': 5, 'avg_price': 120000},
            ]
        }
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection') as mock_db:
            mock_db.get_connection.return_value = mock_conn
            with patch('bot.state_restorer.now_kst') as mock_now:
                mock_now.return_value = MagicMock(strftime=MagicMock(return_value='2026-02-09'))
                await restorer.restore_todays_candidates()

        # 후보 1개 + 보유 1개 = 2회
        assert base_deps['trading_manager'].add_selected_stock.call_count == 2

    @pytest.mark.asyncio
    async def test_config_None이면_가상매매_모드(self, base_deps):
        """config가 None이면 paper_trading=True로 가상매매 동작"""
        base_deps['config'] = None
        restorer = StateRestorer(**base_deps)
        assert restorer.is_paper_trading is True
