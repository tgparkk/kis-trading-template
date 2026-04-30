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
        assert '005930' in vtm._buy_times
        assert vtm._buy_times['005930'] == kst_now

    def test_days_held_calculation_1day(self):
        """매수 후 1일 경과 시 days_held == 1"""
        vtm = _make_vtm()
        buy_time = datetime(2026, 4, 29, 9, 0, 0, tzinfo=timezone.utc)
        vtm._buy_times['005930'] = buy_time

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            days = vtm.get_days_held('005930')

        assert days == 1

    def test_days_held_calculation_5days(self):
        """매수 후 5일 경과 시 days_held == 5"""
        vtm = _make_vtm()
        buy_time = datetime(2026, 4, 25, 9, 0, 0, tzinfo=timezone.utc)
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


class TestIsStaleFlagAfter30Days:
    """test_is_stale_flag_after_30_days"""

    def test_not_stale_before_30_days(self):
        """29일 보유 시 is_stale_position == False"""
        vtm = _make_vtm()
        buy_time = datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc)
        vtm._buy_times['005930'] = buy_time

        # 29일 후
        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            assert vtm.is_stale_position('005930') is False

    def test_stale_at_exactly_30_days(self):
        """정확히 30일 보유 시 is_stale_position == True"""
        vtm = _make_vtm()
        buy_time = datetime(2026, 3, 31, 9, 0, 0, tzinfo=timezone.utc)
        vtm._buy_times['005930'] = buy_time

        # 30일 후
        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            assert vtm.is_stale_position('005930') is True

    def test_stale_after_30_days(self):
        """31일 보유 시 is_stale_position == True"""
        vtm = _make_vtm()
        buy_time = datetime(2026, 3, 30, 9, 0, 0, tzinfo=timezone.utc)
        vtm._buy_times['005930'] = buy_time

        now_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        with patch('core.virtual_trading_manager.now_kst', return_value=now_time):
            assert vtm.is_stale_position('005930') is True


class TestStateRestorerCompatibility:
    """test_state_restorer_compatibility: DB timestamp(BUY 행)로 buy_time 복원"""

    def test_restore_buy_time_from_db(self):
        """restore_buy_time()으로 DB timestamp 복원 후 days_held 계산 가능"""
        vtm = _make_vtm()
        # buy_time과 now를 동일 시각(09:00)으로 맞춰 날짜 차이 10일이 명확하게 나오도록
        db_buy_time = datetime(2026, 4, 20, 9, 0, 0, tzinfo=timezone.utc)

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
        """execute_virtual_sell 성공 시 _buy_times에서 제거됨"""
        vtm = _make_vtm()
        vtm._buy_times['005930'] = datetime(2026, 4, 20, 9, 0, 0, tzinfo=timezone.utc)

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

        assert '005930' not in vtm._buy_times
