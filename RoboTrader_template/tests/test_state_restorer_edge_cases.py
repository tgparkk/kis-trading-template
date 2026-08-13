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
from tests.broker_contract import make_account_balance, make_holding
from utils.exceptions import LiveStartupAbort


@pytest.fixture
def base_deps():
    """StateRestorer 의존성 기본 Mock"""
    trading_manager = MagicMock()
    trading_manager.add_selected_stock = AsyncMock(return_value=True)
    trading_manager.get_trading_stock = MagicMock()
    trading_manager._change_stock_state = MagicMock()

    db_manager = MagicMock()
    db_manager.get_virtual_open_positions = MagicMock(return_value=pd.DataFrame())
    # 실전 모드 폴백/대사는 real_trading_records 를 읽는다(BLOCKER #3/#4, 2026-06-24).
    # 기본값을 빈 DataFrame 으로 둬 실전 계열 테스트가 대사 단계에서 크래시하지 않게 한다.
    db_manager.get_real_open_positions = MagicMock(return_value=pd.DataFrame())

    telegram = AsyncMock()
    # 2026-08-14 P0(dc63cbf, state_restorer.py 110→253행 diff 실측): send_notification
    # 은 유령 메서드 — 실코드는 notify_urgent_signal 을 부른다. AsyncMock 은 임의
    # 속성 접근을 허용하므로 이 줄이 없어도 호출 자체는 성공하지만, 이름을 맞춰
    # 두어 혼동을 없앤다.
    telegram.notify_urgent_signal = AsyncMock()

    config = MagicMock()
    config.paper_trading = True

    broker = MagicMock()
    # 2026-08-14 P0(b71d3e6): 실전 복원 0단계가 기동 시 미체결을 전량 조회·취소한다.
    # 기본값 없이 두면 MagicMock() 이 매수 목록으로 오인돼(참·비-iterable) 모든
    # 실전 계열 테스트가 이 단계에서 깨진다.
    broker.get_pending_orders = MagicMock(return_value=[])

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
        # 이 클래스는 브로커측 엣지케이스(예외/None/빈 목록 등)를 검증한다 —
        # 계좌-DB 대사(fail-closed, 2026-08-14 P0 결정 5)는 별도 관심사이므로
        # 여기서는 항상 불일치 0으로 고정해 대사 로직이 각 테스트를 가리지 않게 한다.
        r._detect_holdings_mismatch = AsyncMock(return_value=[])
        return r

    @pytest.mark.asyncio
    async def test_계좌_조회_예외_시_기동_중단(self, real_restorer, base_deps):
        """broker.get_account_balance()가 예외 시 기동 중단(LiveStartupAbort).

        구 기대치("DB 폴백")는 2026-08-14 최종 리뷰 I4 로 폐기됐다 — 잔존하던
        마지막 silent-continue 경로(원인 불명 예외 → DB 복원으로 대체)가 실전
        기동 실패는 전부 LiveStartupAbort 로 수렴해야 한다는 계약(결정 5)을
        깨고 있었다. 이제 예외는 삼켜지지 않고 LiveStartupAbort 로 전환되어
        전파된다 — DB 폴백은 더 이상 일어나지 않는다.
        """
        base_deps['broker'].get_account_balance.side_effect = Exception("네트워크 오류")

        with patch('bot.state_restorer.DatabaseConnection'):
            with pytest.raises(LiveStartupAbort):
                await real_restorer._restore_holdings_from_real_account()

        base_deps['db_manager'].get_real_open_positions.assert_not_called()
        base_deps['db_manager'].get_virtual_open_positions.assert_not_called()

    @pytest.mark.asyncio
    async def test_계좌_조회_None_반환_시_기동_중단(self, real_restorer, base_deps):
        """broker.get_account_balance()가 None 반환 시 기동 중단.

        구 기대치("DB 폴백")는 2026-08-14 P0 결정 5(불일치는 경고가 아니라 기동
        중단이다, dc63cbf)로 폐기됐다 — 요약 조회가 None/비-dict 이면 "조회 실패"로
        간주해 LiveStartupAbort 로 중단한다(state_restorer.py:822-825). DB 폴백으로
        조용히 이어가면 텅 빈 실계좌를 만들 위험이 있어 fail-closed 로 바뀌었다.
        """
        base_deps['broker'].get_account_balance.return_value = None

        with patch('bot.state_restorer.DatabaseConnection'):
            with pytest.raises(LiveStartupAbort):
                await real_restorer._restore_holdings_from_real_account()

        base_deps['db_manager'].get_virtual_open_positions.assert_not_called()

    @pytest.mark.asyncio
    async def test_빈_positions_리스트(self, real_restorer, base_deps):
        """계좌에 보유 종목이 없는 경우.

        2026-08-14 P0: 요약(get_account_balance)과 목록(get_holdings)은 분리
        조회다 — 'positions' 키는 실계약에 없는 발명된 키였다(broker_contract.py).
        """
        base_deps['broker'].get_account_balance.return_value = make_account_balance(total_stocks=0)
        base_deps['broker'].get_holdings.return_value = []

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        base_deps['trading_manager'].add_selected_stock.assert_not_called()

    @pytest.mark.asyncio
    async def test_quantity_0_종목_스킵(self, real_restorer, base_deps):
        """quantity <= 0인 종목은 건너뜀"""
        base_deps['broker'].get_account_balance.return_value = make_account_balance(total_stocks=2)
        base_deps['broker'].get_holdings.return_value = [
            make_holding(stock_code='005930', stock_name='삼성전자', quantity=0, avg_price=70000.0),
            make_holding(stock_code='000660', stock_name='SK하이닉스', quantity=5, avg_price=120000.0),
        ]
        # 000660 은 수량이 일치하는 DB 행을 둬 대사(fail-closed, 결정 5)를 통과시킨다
        # — quantity<=0 인 005930 은 _detect_holdings_mismatch 가 애초에 건너뛰므로
        # (real_qty<=0 → continue) DB 행이 없어도 도달 가능 상태다.
        base_deps['db_manager'].get_real_open_positions.return_value = pd.DataFrame([{
            'stock_code': '000660', 'stock_name': 'SK하이닉스',
            'quantity': 5, 'buy_price': 120000.0,
            'strategy': '', 'target_profit_rate': None, 'stop_loss_rate': None,
        }])
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        # quantity 0인 삼성전자는 스킵, SK하이닉스만 복원
        base_deps['trading_manager'].add_selected_stock.assert_called_once()

    @pytest.mark.asyncio
    async def test_tp_sl_미기록_종목은_기본_익절손절률(self, real_restorer, base_deps):
        """DB 행은 있지만 target_profit_rate/stop_loss_rate 가 NULL 인 종목은 기본값 적용.

        2026-08-14 코드리뷰 정정: 구 테스트("실제 계좌에만 있고 DB에 없는 종목")는
        `_detect_holdings_mismatch` 를 mock 으로 우회한 상태에서만 성립하는 조합이었다
        — 대사(fail-closed, 결정 5)와 복원 루프(state_restorer.py:891-908)가 같은
        db_holdings_dict 를 같은 존재-여부 조건으로 훑으므로, "실보유가 DB 에 없는데
        대사는 통과"는 프로덕션에서 구조적으로 도달 불가능하다(도달했다면 mismatches
        가 비지 않아 그 전에 LiveStartupAbort 로 죽는다). 실제로 도달 가능한 「기본값
        폴백」 경로는 DB 행 자체는 있는데 tp/sl 컬럼이 NULL 인 경우다(:843-852 의
        None/NaN 폴백) — 대사는 수량 일치로 통과시키고 이 경로만 골라 검증한다.
        """
        base_deps['broker'].get_account_balance.return_value = make_account_balance(total_stocks=1)
        base_deps['broker'].get_holdings.return_value = [
            make_holding(stock_code='005930', stock_name='삼성전자', quantity=10, avg_price=70000.0),
        ]
        # 수량이 일치하는 DB 행을 둬 대사를 통과시키되(10=10), tp/sl 은 미기록(NULL).
        base_deps['db_manager'].get_real_open_positions.return_value = pd.DataFrame([{
            'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 70000.0,
            'strategy': '', 'target_profit_rate': None, 'stop_loss_rate': None,
        }])
        mock_ts = MagicMock()
        base_deps['trading_manager'].get_trading_stock.return_value = mock_ts

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        # tp/sl NULL → 기본값 적용 확인
        from config.constants import DEFAULT_TARGET_PROFIT_RATE, DEFAULT_STOP_LOSS_RATE
        assert mock_ts.target_profit_rate == DEFAULT_TARGET_PROFIT_RATE
        assert mock_ts.stop_loss_rate == DEFAULT_STOP_LOSS_RATE

    @pytest.mark.asyncio
    async def test_account_balance_dict가_아닌_객체_반환_시_기동_중단(self, real_restorer, base_deps):
        """get_account_balance가 dict 대신 객체를 반환하면 기동 중단.

        구 기대치("객체의 .positions 속성을 읽어 복원 진행")는 폐기됐다 —
        'positions' 속성 자체가 실계약에 없는 발명이었고(broker_contract.py),
        2026-08-14 P0 는 `isinstance(account_info, dict)` 가 아니면 "실계좌 요약
        조회 실패"로 간주해 fail-closed 로 중단한다(state_restorer.py:822-825).
        """
        account_obj = MagicMock()
        account_obj.positions = [
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 5, 'avg_price': 70000}
        ]
        # isinstance(account_obj, dict) → False
        base_deps['broker'].get_account_balance.return_value = account_obj

        with patch('bot.state_restorer.DatabaseConnection'):
            with pytest.raises(LiveStartupAbort):
                await real_restorer._restore_holdings_from_real_account()

        base_deps['trading_manager'].add_selected_stock.assert_not_called()

    @pytest.mark.asyncio
    async def test_account_balance_total_stocks_키_없음(self, real_restorer, base_deps):
        """get_account_balance 결과에 total_stocks 키가 없는 경우 0건으로 처리.

        구 테스트명·본문은 'positions' 키(실계약에 없는 발명)를 전제했다 —
        실계약의 종목수 키는 total_stocks 다(broker_contract.py:14).
        """
        base_deps['broker'].get_account_balance.return_value = {'total_amount': 1000000}
        base_deps['broker'].get_holdings.return_value = []

        with patch('bot.state_restorer.DatabaseConnection'):
            await real_restorer._restore_holdings_from_real_account()

        # total_stocks 키가 없으면 0으로 처리되어 보유 목록도 빈 채로 진행되어야 함
        base_deps['trading_manager'].add_selected_stock.assert_not_called()


# ============================================================================
# 불일치 감지 엣지 케이스
# ============================================================================

class TestMismatchDetectionEdgeCases:
    """불일치 감지 경계 조건"""

    @pytest.mark.asyncio
    async def test_10건_초과_불일치_시_요약_메시지(self, restorer, base_deps):
        """불일치가 10건 초과 시 '외 N건' 요약 표시.

        구 테스트는 임계값을 5건으로 가정했다 — 현 구현(state_restorer.py:1062-1065)의
        요약 임계값은 10건이다. 7건으로는 절대 잘리지 않으므로 12건으로 늘려
        '외 2건'(12-10) 을 재현한다.
        """
        real_holdings = [
            {'stock_code': f'{i:06d}', 'stock_name': f'종목{i}', 'quantity': 10}
            for i in range(12)
        ]
        db_holdings_dict = {}

        await restorer._detect_holdings_mismatch(real_holdings, db_holdings_dict)

        call_args = base_deps['telegram_integration'].notify_urgent_signal.call_args[0][0]
        assert '외 2건' in call_args

    @pytest.mark.asyncio
    async def test_telegram_알림_실패해도_크래시_없음(self, restorer, base_deps):
        """텔레그램 알림 전송 실패해도 예외가 전파되지 않음"""
        base_deps['telegram_integration'].notify_urgent_signal.side_effect = Exception("텔레그램 오류")

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
        base_deps['telegram_integration'].notify_urgent_signal.assert_not_called()

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

        call_args = base_deps['telegram_integration'].notify_urgent_signal.call_args[0][0]
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
        """실전매매: 후보 복원 + 계좌 기반 보유 종목 복원.

        2026-08-14 P0: 요약/목록 분리 조회(get_account_balance/get_holdings)로
        갱신 — 'positions' 키는 실계약에 없는 발명이었다. 계좌-DB 대사는 이
        테스트의 관심사가 아니므로 불일치 0으로 고정한다.
        """
        base_deps['config'].paper_trading = False
        restorer = StateRestorer(**base_deps)
        restorer.is_paper_trading = False
        restorer._detect_holdings_mismatch = AsyncMock(return_value=[])

        mock_conn = _make_mock_conn([('005930', '삼성전자', 85.0, '모멘텀')])

        base_deps['broker'].get_account_balance.return_value = make_account_balance(total_stocks=1)
        base_deps['broker'].get_holdings.return_value = [
            make_holding(stock_code='000660', stock_name='SK하이닉스', quantity=5, avg_price=120000.0),
        ]
        # 000660 은 수량이 일치하는 DB 행을 둬 대사를 통과시킨다(10=10 패턴과 동일,
        # _detect_holdings_mismatch mock 은 방어층으로 남기되 상태 자체를 도달
        # 가능하게 만든다 — 2026-08-14 코드리뷰).
        base_deps['db_manager'].get_real_open_positions.return_value = pd.DataFrame([{
            'stock_code': '000660', 'stock_name': 'SK하이닉스',
            'quantity': 5, 'buy_price': 120000.0,
            'strategy': '', 'target_profit_rate': None, 'stop_loss_rate': None,
        }])
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
