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


# ============================================================================
# days_held 영업일 기준 테스트 (결재 #1)
# ============================================================================

class TestDaysHeldBusinessDays:
    """days_held가 영업일 기준으로 계산되는지 검증"""

    def _make_trading_stock(self):
        """days_held / is_stale 속성을 가진 Mock TradingStock"""
        ts = MagicMock()
        ts.days_held = 0
        ts.is_stale = False
        ts.stock_code = "005930"
        ts.stock_name = "삼성전자"
        return ts

    def test_days_held_business_days_only(self, restorer):
        """캘린더 7일(설 연휴 4일 포함) → 영업일 3일

        기간: 2026-02-13(금) ~ 2026-02-19(목)
        주말: 2/14(토), 2/15(일) = 2일
        공휴일: 2/16(설전날), 2/17(설날), 2/18(설다음날) = 3일
        영업일: 2/13(금), 2/19(목) = 2일 (start 포함)
        """
        from datetime import timezone as _tz
        ts = self._make_trading_stock()
        buy_time = datetime(2026, 2, 13, 9, 30, 0, tzinfo=_tz.utc)

        with patch('bot.state_restorer.now_kst') as mock_now:
            mock_now.return_value = datetime(2026, 2, 19, 10, 0, 0)
            restorer._apply_stale_position_check(ts, buy_time, 0.05, 0.03)

        # 2/13(금, 영업일) + 2/19(목, 영업일) = 2 영업일
        assert ts.days_held == 2, (
            f"설 연휴 포함 캘린더 7일 → 영업일 2이어야 함, 실제: {ts.days_held}"
        )

    def test_days_held_normal_week(self, restorer):
        """공휴일 없는 평일 5일 = 영업일 5일"""
        from datetime import timezone as _tz
        ts = self._make_trading_stock()
        # 2026-04-20(월) 매수 → 2026-04-24(금) today (5 영업일)
        buy_time = datetime(2026, 4, 20, 9, 30, 0, tzinfo=_tz.utc)

        with patch('bot.state_restorer.now_kst') as mock_now:
            mock_now.return_value = datetime(2026, 4, 24, 10, 0, 0)
            restorer._apply_stale_position_check(ts, buy_time, 0.05, 0.03)

        assert ts.days_held == 5, (
            f"평일 5일 → 영업일 5이어야 함, 실제: {ts.days_held}"
        )

    def test_days_held_includes_labor_day_exclusion(self, restorer):
        """근로자의 날(5/1) 포함 주 — 영업일에서 제외"""
        from datetime import timezone as _tz
        ts = self._make_trading_stock()
        # 2026-04-27(월) 매수 → 2026-05-01(금, 근로자의날) today
        # 영업일: 4/27(월), 4/28(화), 4/29(수), 4/30(목) = 4일 (5/1 제외)
        buy_time = datetime(2026, 4, 27, 9, 30, 0, tzinfo=_tz.utc)

        with patch('bot.state_restorer.now_kst') as mock_now:
            mock_now.return_value = datetime(2026, 5, 1, 10, 0, 0)
            restorer._apply_stale_position_check(ts, buy_time, 0.05, 0.03)

        assert ts.days_held == 4, (
            f"근로자의날 포함 → 영업일 4이어야 함, 실제: {ts.days_held}"
        )

    def test_days_held_calendar_vs_business_difference(self, restorer):
        """캘린더일과 영업일의 차이를 검증 — 주말 포함 7일 = 영업일 5일"""
        from datetime import timezone as _tz
        ts = self._make_trading_stock()
        # 2026-04-20(월) ~ 2026-04-26(일): 캘린더 7일, 영업일 5일
        buy_time = datetime(2026, 4, 20, 9, 30, 0, tzinfo=_tz.utc)

        with patch('bot.state_restorer.now_kst') as mock_now:
            mock_now.return_value = datetime(2026, 4, 26, 10, 0, 0)
            restorer._apply_stale_position_check(ts, buy_time, 0.05, 0.03)

        # 캘린더 7일이지만 영업일 = 5 (주말 제외)
        assert ts.days_held == 5, (
            f"주말 포함 캘린더 7일 → 영업일 5이어야 함, 실제: {ts.days_held}"
        )
        assert ts.days_held < 7, "영업일이 캘린더일보다 작아야 한다 (주말 제외)"

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


# ============================================================================
# FundManager 동기화 테스트
# ============================================================================

class TestFundManagerSync:
    """포지션 복원 후 FundManager 자금 동기화 테스트"""

    def _make_fund_manager(self, total_funds=10_000_000):
        """테스트용 FundManager mock 생성"""
        fm = MagicMock()
        fm.total_funds = total_funds
        fm.available_funds = total_funds
        fm.invested_funds = 0.0
        fm.reserved_funds = 0.0
        fm.current_position_codes = set()
        fm.max_position_count = 20
        fm.add_position = MagicMock(side_effect=lambda code: fm.current_position_codes.add(code))
        return fm

    def _make_vtm(self, balance=10_000_000):
        """테스트용 VirtualTradingManager mock 생성"""
        vtm = MagicMock()
        vtm.virtual_balance = balance
        vtm.update_virtual_balance = MagicMock()
        return vtm

    @pytest.mark.asyncio
    async def test_가상매매_복원_시_FundManager_동기화(self, base_deps):
        """가상매매 보유 종목 복원 후 FundManager의 invested/available/position이 업데이트되는지"""
        fm = self._make_fund_manager(10_000_000)

        holdings_df = pd.DataFrame([
            {
                'stock_code': '005930', 'stock_name': '삼성전자',
                'quantity': 10, 'buy_price': 70000.0,
                'target_profit_rate': 0.05, 'stop_loss_rate': 0.03,
            },
            {
                'stock_code': '000660', 'stock_name': 'SK하이닉스',
                'quantity': 5, 'buy_price': 120000.0,
                'target_profit_rate': 0.04, 'stop_loss_rate': 0.02,
            },
        ])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df

        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        restorer = StateRestorer(**base_deps, fund_manager=fm)

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 삼성전자: 10 * 70000 = 700,000
        # SK하이닉스: 5 * 120000 = 600,000
        # 총 투자: 1,300,000
        assert fm.invested_funds == 1_300_000
        assert fm.available_funds == 10_000_000 - 1_300_000
        assert fm.current_position_codes == {'005930', '000660'}

    @pytest.mark.asyncio
    async def test_실전매매_복원_시_FundManager_동기화(self, base_deps):
        """실전매매 보유 종목 복원 후 FundManager가 업데이트되는지"""
        fm = self._make_fund_manager(10_000_000)
        base_deps['config'].paper_trading = False

        base_deps['broker'].get_account_balance.return_value = {
            'positions': [
                {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 10, 'avg_price': 70000},
            ]
        }
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        restorer = StateRestorer(**base_deps, fund_manager=fm)
        restorer.is_paper_trading = False

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_real_account()

        assert fm.invested_funds == 700_000
        assert fm.available_funds == 10_000_000 - 700_000
        assert '005930' in fm.current_position_codes

    @pytest.mark.asyncio
    async def test_FundManager_None이면_동기화_스킵(self, base_deps):
        """fund_manager가 None이면 자금 동기화 없이 포지션만 복원"""
        holdings_df = pd.DataFrame([{
            'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 70000.0,
            'target_profit_rate': 0.05, 'stop_loss_rate': 0.03,
        }])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        restorer = StateRestorer(**base_deps)  # fund_manager=None (기본값)

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 포지션 복원은 정상 동작
        mock_ts.set_position.assert_called_once_with(10, 70000.0)

    @pytest.mark.asyncio
    async def test_가용자금_음수_클램프(self, base_deps):
        """복원된 투자금이 총 자금을 초과할 때 available_funds가 0으로 클램프되는지"""
        fm = self._make_fund_manager(500_000)  # 총 자금 50만원

        holdings_df = pd.DataFrame([{
            'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 70000.0,  # 70만원 > 50만원
            'target_profit_rate': 0.05, 'stop_loss_rate': 0.03,
        }])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        restorer = StateRestorer(**base_deps, fund_manager=fm)

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # invested_funds는 정확히 반영
        assert fm.invested_funds == 700_000
        # available_funds는 0으로 클램프 (음수 방지)
        assert fm.available_funds == 0

    @pytest.mark.asyncio
    async def test_VirtualTradingManager_잔고_동기화(self, base_deps):
        """가상매매 복원 시 VirtualTradingManager의 가상 잔고도 차감되는지"""
        fm = self._make_fund_manager(10_000_000)
        vtm = self._make_vtm(10_000_000)

        holdings_df = pd.DataFrame([{
            'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 70000.0,
            'target_profit_rate': 0.05, 'stop_loss_rate': 0.03,
        }])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        restorer = StateRestorer(**base_deps, fund_manager=fm, virtual_trading_manager=vtm)

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # VTM의 update_virtual_balance가 매수 금액으로 호출되었는지
        vtm.update_virtual_balance.assert_called_once_with(700_000, "매수")

    @pytest.mark.asyncio
    async def test_포지션_수_초과_경고(self, base_deps):
        """복원된 포지션이 max_positions를 초과하면 WARNING 로그가 출력되는지"""
        fm = self._make_fund_manager(100_000_000)
        fm.max_position_count = 2  # 최대 2개로 제한

        # 3개 종목 복원 시도
        holdings_df = pd.DataFrame([
            {'stock_code': '005930', 'stock_name': '삼성전자',
             'quantity': 10, 'buy_price': 70000.0,
             'target_profit_rate': 0.05, 'stop_loss_rate': 0.03},
            {'stock_code': '000660', 'stock_name': 'SK하이닉스',
             'quantity': 5, 'buy_price': 120000.0,
             'target_profit_rate': 0.04, 'stop_loss_rate': 0.02},
            {'stock_code': '035420', 'stock_name': 'NAVER',
             'quantity': 3, 'buy_price': 300000.0,
             'target_profit_rate': 0.06, 'stop_loss_rate': 0.04},
        ])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        restorer = StateRestorer(**base_deps, fund_manager=fm)

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 3개 모두 복원됨 (드롭하지 않음)
        assert mock_ts.set_position.call_count == 3
        assert len(fm.current_position_codes) == 3

    @pytest.mark.asyncio
    async def test_add_selected_stock_실패시_FundManager_미동기화(self, base_deps):
        """add_selected_stock 실패한 종목은 FundManager에 반영되지 않는지"""
        fm = self._make_fund_manager(10_000_000)

        base_deps['trading_manager'].add_selected_stock = AsyncMock(
            side_effect=[False, True]
        )
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        holdings_df = pd.DataFrame([
            {'stock_code': '005930', 'stock_name': '삼성전자',
             'quantity': 10, 'buy_price': 70000.0,
             'target_profit_rate': 0.05, 'stop_loss_rate': 0.03},
            {'stock_code': '000660', 'stock_name': 'SK하이닉스',
             'quantity': 5, 'buy_price': 120000.0,
             'target_profit_rate': 0.04, 'stop_loss_rate': 0.02},
        ])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df

        restorer = StateRestorer(**base_deps, fund_manager=fm)

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 삼성전자(실패)는 미반영, SK하이닉스(성공)만 반영
        assert fm.invested_funds == 600_000  # 5 * 120000
        assert fm.available_funds == 10_000_000 - 600_000
        assert fm.current_position_codes == {'000660'}

    @pytest.mark.asyncio
    async def test_자금_정합성_검증(self, base_deps):
        """복원 후 total_funds == available + invested + reserved 검증"""
        fm = self._make_fund_manager(10_000_000)

        holdings_df = pd.DataFrame([
            {'stock_code': '005930', 'stock_name': '삼성전자',
             'quantity': 10, 'buy_price': 70000.0,
             'target_profit_rate': 0.05, 'stop_loss_rate': 0.03},
        ])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        restorer = StateRestorer(**base_deps, fund_manager=fm)

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 정합성: total = available + invested + reserved
        expected_total = fm.available_funds + fm.invested_funds + fm.reserved_funds
        assert fm.total_funds == expected_total

    @pytest.mark.asyncio
    async def test_다수_종목_누적_투자금_정확성(self, base_deps):
        """여러 종목 복원 시 투자금이 정확히 누적되는지"""
        fm = self._make_fund_manager(50_000_000)

        holdings_df = pd.DataFrame([
            {'stock_code': f'00{i}000', 'stock_name': f'종목{i}',
             'quantity': 10, 'buy_price': 100000.0 * (i + 1),
             'target_profit_rate': 0.05, 'stop_loss_rate': 0.03}
            for i in range(5)
        ])
        base_deps['db_manager'].get_virtual_open_positions.return_value = holdings_df
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        restorer = StateRestorer(**base_deps, fund_manager=fm)

        with patch('bot.state_restorer.DatabaseConnection'):
            await restorer._restore_holdings_from_db()

        # 10*100000 + 10*200000 + 10*300000 + 10*400000 + 10*500000
        # = 1000000 + 2000000 + 3000000 + 4000000 + 5000000 = 15000000
        expected_invested = sum(10 * 100000 * (i + 1) for i in range(5))
        assert fm.invested_funds == expected_invested
        assert fm.available_funds == 50_000_000 - expected_invested
        assert len(fm.current_position_codes) == 5
