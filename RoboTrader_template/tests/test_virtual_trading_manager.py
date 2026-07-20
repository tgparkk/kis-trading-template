"""
VirtualTradingManager 유닛 테스트
- 잔고 초기화 (가상/실전)
- 잔고 새로고침
- buy_time / days_held / is_stale 추적
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch


class TestVirtualTradingInit:
    def test_paper_trading_mode(self):
        with patch('core.virtual_trading_manager.setup_logger'):
            from core.virtual_trading_manager import VirtualTradingManager
            vtm = VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)
        assert vtm.virtual_balance == 10000000
        assert vtm.virtual_investment_amount == 1000000
        assert vtm.paper_trading is True

    def test_real_mode_with_broker(self):
        broker = Mock()
        broker.get_account_balance.return_value = {'available_cash': 5000000}
        with patch('core.virtual_trading_manager.setup_logger'):
            from core.virtual_trading_manager import VirtualTradingManager
            vtm = VirtualTradingManager(db_manager=None, broker=broker, paper_trading=False)
        assert vtm.virtual_balance == 5000000

    def test_real_mode_no_broker(self):
        with patch('core.virtual_trading_manager.setup_logger'):
            from core.virtual_trading_manager import VirtualTradingManager
            vtm = VirtualTradingManager(db_manager=None, broker=None, paper_trading=False)
        # Should fall back to default
        assert vtm.virtual_balance == 10000000

    def test_real_mode_broker_fails(self):
        broker = Mock()
        broker.get_account_balance.side_effect = Exception("API Error")
        with patch('core.virtual_trading_manager.setup_logger'):
            from core.virtual_trading_manager import VirtualTradingManager
            vtm = VirtualTradingManager(db_manager=None, broker=broker, paper_trading=False)
        assert vtm.virtual_balance == 10000000


class TestRefreshBalance:
    def test_refresh_real_mode(self):
        broker = Mock()
        broker.get_account_balance.return_value = {'available_cash': 5000000}
        with patch('core.virtual_trading_manager.setup_logger'):
            from core.virtual_trading_manager import VirtualTradingManager
            vtm = VirtualTradingManager(db_manager=None, broker=broker, paper_trading=False)
        broker.get_account_balance.return_value = {'available_cash': 6000000}
        vtm.refresh_balance()
        assert vtm.virtual_balance == 6000000

    def test_refresh_paper_mode_noop(self):
        with patch('core.virtual_trading_manager.setup_logger'):
            from core.virtual_trading_manager import VirtualTradingManager
            vtm = VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)
        vtm.refresh_balance()
        assert vtm.virtual_balance == 10000000


# ---------------------------------------------------------------------------
# buy_time / days_held / is_stale 추적
# ---------------------------------------------------------------------------

def _make_vtm():
    """패치 없이 VTM 인스턴스 생성 헬퍼"""
    with patch('core.virtual_trading_manager.setup_logger'):
        from core.virtual_trading_manager import VirtualTradingManager
        return VirtualTradingManager(db_manager=None, broker=None, paper_trading=True)


class TestBuyTimeDaysHeld:
    """test_buy_records_buy_time + test_days_held_calculation"""

    def test_buy_records_buy_time(self):
        """execute_virtual_buy 성공 시 _buy_times에 buy_time 저장"""
        vtm = _make_vtm()

        db_manager = Mock()
        db_manager.save_virtual_buy.return_value = 42  # buy_record_id
        vtm.db_manager = db_manager

        with patch('core.virtual_trading_manager.now_kst') as mock_now:
            kst_now = datetime(2026, 4, 30, 9, 30, 0, tzinfo=timezone.utc)
            mock_now.return_value = kst_now

            result = vtm.execute_virtual_buy(
                stock_code='005930',
                stock_name='삼성전자',
                price=70000,
                quantity=10,
                strategy='SampleStrategy',
                reason='테스트 매수',
            )

        assert result == 42
        # (stock_code, buy_record_id) 키로 기록됨
        assert ('005930', 42) in vtm._buy_times
        assert vtm._buy_times[('005930', 42)] == kst_now

    def test_days_held_calculation_1day(self):
        """매수 당일 days_held == 1 (count_trading_days_between는 양 끝 포함 카운트)"""
        vtm = _make_vtm()
        # production: count_trading_days_between(buy, today) — 매수일 당일 포함
        # buy=4/30(오늘) → count(4/30, 4/30) = 1
        buy_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        vtm._buy_times['005930'] = buy_time

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            days = vtm.get_days_held('005930')

        assert days == 1

    def test_days_held_calculation_5days(self):
        """매수일 포함 영업일 5일 경과 시 days_held == 5"""
        vtm = _make_vtm()
        # production: count_trading_days_between(buy, today) — 매수일 당일 포함
        # buy=4/24(금) → count(4/24, 4/30) = 5 (4/24,4/27,4/28,4/29,4/30)
        buy_time = datetime(2026, 4, 24, 9, 0, 0, tzinfo=timezone.utc)
        vtm._buy_times['005930'] = buy_time

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            days = vtm.get_days_held('005930')

        assert days == 5

    def test_days_held_no_buy_time(self):
        """buy_time 없으면 days_held == 0"""
        vtm = _make_vtm()
        assert vtm.get_days_held('999999') == 0

    def test_get_position_buy_time_returns_none_when_missing(self):
        """미매수 종목은 get_position_buy_time() == None"""
        vtm = _make_vtm()
        assert vtm.get_position_buy_time('000000') is None


class TestBuyTimeCrossStrategyIsolation:
    """회귀: _buy_times 가 stock_code 단독 키였을 때, 두 전략(owner)이 같은 종목을
    보유하면 buy_time 이 서로 덮어써지거나 한쪽 매도 시 통째로 삭제되어
    get_days_held(=max_holding/stale 타이밍)가 오귀속된다. (stock_code, buy_record_id)
    키로 재구성하면 각 owner 의 보유기간이 독립적으로 유지된다."""

    def test_days_held_isolated_per_owner(self):
        vtm = _make_vtm()
        t_old = datetime(2026, 4, 20, 9, 0, 0, tzinfo=timezone.utc)  # owner1 먼저 매수
        t_new = datetime(2026, 4, 27, 9, 0, 0, tzinfo=timezone.utc)  # owner2 나중 매수
        vtm.restore_buy_time('005930', t_old, buy_record_id=1)
        vtm.restore_buy_time('005930', t_new, buy_record_id=2)

        # 각 owner 는 자기 매수시각을 반환(덮어쓰기 없음)
        assert vtm.get_position_buy_time('005930', 1) == t_old
        assert vtm.get_position_buy_time('005930', 2) == t_new

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            d1 = vtm.get_days_held('005930', 1)
            d2 = vtm.get_days_held('005930', 2)
        assert d1 > d2  # 먼저 산 owner1 이 더 오래 보유

    def test_sell_one_owner_preserves_other_buy_time(self):
        vtm = _make_vtm()
        t_old = datetime(2026, 4, 20, 9, 0, 0, tzinfo=timezone.utc)
        t_new = datetime(2026, 4, 27, 9, 0, 0, tzinfo=timezone.utc)
        vtm.restore_buy_time('005930', t_old, buy_record_id=1)
        vtm.restore_buy_time('005930', t_new, buy_record_id=2)

        db_manager = Mock()
        db_manager.save_virtual_sell.return_value = True
        vtm.db_manager = db_manager

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            vtm.execute_virtual_sell(
                stock_code='005930', stock_name='삼성전자', price=75000,
                quantity=10, strategy='SampleStrategy', reason='매도',
                buy_record_id=1,
            )

        # owner1 매도 후 owner1 buy_time 은 제거, owner2 buy_time 은 보존
        assert vtm.get_position_buy_time('005930', 1) is None
        assert vtm.get_position_buy_time('005930', 2) == t_new

    def test_pop_concrete_id_miss_preserves_other_owner(self):
        """회귀(MEDIUM): 구체 buy_record_id 로 pop 했는데 정확 키가 없으면
        타 owner 의 동일종목 항목을 오삭제하면 안 된다(read 경로와 대칭).

        시나리오: 재시작 후 _buy_times 가 비었다가 owner C 가 매수해 {(code,idC)}만
        존재. 재시작 前 owner A(idA)를 매도하면 정확 키 (code,idA)가 없다 —
        폴백으로 owner C 항목을 지워버리면 오귀속 창이 다시 열린다.
        """
        vtm = _make_vtm()
        t_c = datetime(2026, 4, 27, 9, 0, 0, tzinfo=timezone.utc)
        vtm.restore_buy_time('005930', t_c, buy_record_id=3)  # owner C

        vtm._pop_buy_time('005930', buy_record_id=1)  # owner A(부재) 매도

        # owner C 항목은 반드시 보존
        assert vtm.get_position_buy_time('005930', 3) == t_c
        assert ('005930', 3) in vtm._buy_times


class TestIsStaleFlagAfter30Days:
    """test_is_stale_flag_after_30_days"""

    def test_not_stale_before_30_days(self):
        """영업일 29일 보유 시 is_stale_position == False"""
        vtm = _make_vtm()
        # count_trading_days_between(buy, 4/30) == 29 → buy=2026-03-23(월)
        buy_time = datetime(2026, 3, 23, 9, 0, 0, tzinfo=timezone.utc)
        vtm._buy_times['005930'] = buy_time

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            assert vtm.is_stale_position('005930') is False

    def test_stale_at_exactly_30_days(self):
        """정확히 영업일 30일 보유 시 is_stale_position == True"""
        vtm = _make_vtm()
        # count_trading_days_between(buy, 4/30) == 30 → buy=2026-03-20(금)
        buy_time = datetime(2026, 3, 20, 9, 0, 0, tzinfo=timezone.utc)
        vtm._buy_times['005930'] = buy_time

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            assert vtm.is_stale_position('005930') is True

    def test_stale_after_30_days(self):
        """영업일 31일 보유 시 is_stale_position == True"""
        vtm = _make_vtm()
        # count_trading_days_between(buy, 4/30) == 31 → buy=2026-03-19(목)
        buy_time = datetime(2026, 3, 19, 9, 0, 0, tzinfo=timezone.utc)
        vtm._buy_times['005930'] = buy_time

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            assert vtm.is_stale_position('005930') is True


class TestStateRestorerCompatibility:
    """test_state_restorer_compatibility: DB timestamp(BUY 행)로 buy_time 복원"""

    def test_restore_buy_time_from_db(self):
        """restore_buy_time()으로 DB timestamp 복원 후 days_held 계산 가능"""
        vtm = _make_vtm()
        # count_trading_days_between(buy, 4/30) == 10 → buy=2026-04-17(금)
        # (4/17,4/20,4/21,4/22,4/23,4/24,4/27,4/28,4/29,4/30 = 10 영업일)
        db_buy_time = datetime(2026, 4, 17, 9, 0, 0, tzinfo=timezone.utc)

        vtm.restore_buy_time('005930', db_buy_time)

        assert vtm.get_position_buy_time('005930') == db_buy_time

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            assert vtm.get_days_held('005930') == 10

    def test_restore_buy_time_none_is_ignored(self):
        """None buy_time은 저장하지 않음"""
        vtm = _make_vtm()
        vtm.restore_buy_time('005930', None)
        assert vtm.get_position_buy_time('005930') is None

    def test_sell_clears_buy_time(self):
        """execute_virtual_sell 성공 시 해당 슬롯의 _buy_times 항목이 제거됨.

        Fix C 이후 저장키는 (stock_code, buy_record_id) — 매도 슬롯의 매수기록ID로
        정확히 그 항목만 제거한다.
        """
        vtm = _make_vtm()
        vtm._buy_times[('005930', 42)] = datetime(2026, 4, 20, 9, 0, 0, tzinfo=timezone.utc)

        db_manager = Mock()
        db_manager.save_virtual_sell.return_value = True
        vtm.db_manager = db_manager

        vtm.execute_virtual_sell(
            stock_code='005930',
            stock_name='삼성전자',
            price=72000,
            quantity=10,
            strategy='SampleStrategy',
            reason='테스트 매도',
            buy_record_id=42,
        )

        assert ('005930', 42) not in vtm._buy_times
        assert vtm.get_position_buy_time('005930', 42) is None


class TestGetCumulativeProfitInfo:
    """get_cumulative_profit_info: initial_balance 기준 수익률 계산 검증 (결함 C 수정 회귀 방지)"""

    def test_initial_balance_uses_session_balance_not_hardcoded(self):
        """initial_balance가 10M 하드코딩이 아닌 세션 시작 잔고를 반영해야 함."""
        vtm = _make_vtm()
        vtm.virtual_balance = 9_500_000
        vtm.initial_balance = 9_500_000  # D-1 이월 잔고로 시작한 경우

        # DB 없으므로 DB 조회 부분은 스킵되고 기본 result만 반환
        info = vtm.get_cumulative_profit_info()

        # initial_balance는 세션 시작 잔고(9.5M)여야 함 (10M 하드코딩이면 실패)
        assert info['initial_balance'] == 9_500_000

    def test_initial_balance_fallback_when_zero(self):
        """initial_balance가 0이면 10M fallback을 사용해야 함."""
        vtm = _make_vtm()
        vtm.virtual_balance = 10_000_000
        vtm.initial_balance = 0  # 비정상 상태

        info = vtm.get_cumulative_profit_info()

        assert info['initial_balance'] == 10_000_000

    def test_current_balance_reflects_actual_balance(self):
        """current_balance는 virtual_balance와 일치해야 함."""
        vtm = _make_vtm()
        vtm.virtual_balance = 9_979_251
        vtm.initial_balance = 9_979_251

        info = vtm.get_cumulative_profit_info()

        assert info['current_balance'] == 9_979_251

    def test_profit_rate_based_on_session_balance(self):
        """누적 수익률 계산에 세션 시작 잔고가 사용되는지 log_cumulative_profit 호출로 확인."""
        vtm = _make_vtm()
        vtm.virtual_balance = 9_800_000
        vtm.initial_balance = 9_800_000

        # DB 없으면 trade_count=0, pnl=0 반환 → 로그 정상 호출 확인
        try:
            vtm.log_cumulative_profit()
        except Exception as exc:
            pytest.fail(f"log_cumulative_profit raised unexpectedly: {exc}")
