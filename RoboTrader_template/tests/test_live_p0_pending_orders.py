"""D4(a,b): 기동 시 미체결 전량 취소 — 전날/크래시 잔존 주문의 고아·중복매도 차단."""
import asyncio
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from framework.broker import KISBroker
from utils.exceptions import LiveStartupAbort


def _bare_broker():
    b = object.__new__(KISBroker)
    b._connected = True
    b.logger = Mock()
    return b


class TestGetPendingOrders:
    def test_returns_records_list(self):
        df = pd.DataFrame([{'odno': '0001', 'pdno': '005930', 'sll_buy_dvsn_cd': '02'}])
        with patch('api.kis_order_api.get_inquire_psbl_rvsecncl_lst', return_value=df):
            result = _bare_broker().get_pending_orders()
        assert result == [{'odno': '0001', 'pdno': '005930', 'sll_buy_dvsn_cd': '02'}]

    def test_failure_is_none_and_empty_is_list(self):
        """실패 None / 없음 [] 구분 — get_holdings 오류 삼킴의 교훈."""
        with patch('api.kis_order_api.get_inquire_psbl_rvsecncl_lst', return_value=None):
            assert _bare_broker().get_pending_orders() is None
        with patch('api.kis_order_api.get_inquire_psbl_rvsecncl_lst', return_value=pd.DataFrame()):
            assert _bare_broker().get_pending_orders() == []


class TestStartupCancelAll:
    def _restorer(self, broker):
        from tests.test_live_p0_restore import _restorer_with
        from unittest.mock import Mock as M
        db = M(); db.get_real_open_positions.return_value = pd.DataFrame()
        return _restorer_with(db, broker, M())

    def test_cancels_all_then_proceeds(self):
        from tests.broker_contract import make_account_balance
        broker = Mock()
        broker.get_account_balance.return_value = make_account_balance()
        broker.get_holdings.return_value = []
        broker.get_pending_orders.side_effect = [
            [{'odno': '0001', 'pdno': '005930', 'sll_buy_dvsn_cd': '02'}],  # 발견
            [],                                                              # 취소 후 재확인
        ]
        broker.cancel_order.return_value = {'success': True}
        r = self._restorer(broker)
        asyncio.run(r._restore_holdings_from_real_account())
        broker.cancel_order.assert_called_once_with('0001', '005930')

    def test_cancel_failure_aborts(self):
        broker = Mock()
        broker.get_pending_orders.return_value = [{'odno': '0001', 'pdno': '005930', 'sll_buy_dvsn_cd': '01'}]
        broker.cancel_order.return_value = {'success': False, 'message': 'rejected'}
        r = self._restorer(broker)
        with pytest.raises(LiveStartupAbort):
            asyncio.run(r._restore_holdings_from_real_account())

    def test_query_failure_aborts(self):
        broker = Mock()
        broker.get_pending_orders.return_value = None
        r = self._restorer(broker)
        with pytest.raises(LiveStartupAbort):
            asyncio.run(r._restore_holdings_from_real_account())
