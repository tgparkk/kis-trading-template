"""
VirtualTradingManager 유닛 테스트
- 잔고 초기화 (가상/실전)
- 잔고 새로고침
"""
import pytest
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
