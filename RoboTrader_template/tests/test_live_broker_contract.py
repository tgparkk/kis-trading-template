"""실브로커 반환 키 = fixture 키 동일성 고정 (스펙 §4 테스트 12)."""
from unittest.mock import Mock

from framework.broker import KISBroker
from tests.broker_contract import (
    ACCOUNT_BALANCE_KEYS, HOLDING_ITEM_KEYS,
    make_account_balance, make_holding,
)


def _bare_broker(api_mock):
    """생성자 부작용 없이 실메서드만 실행하는 KISBroker."""
    b = object.__new__(KISBroker)
    b._connected = True
    b.logger = Mock()
    b._kis_market_api = api_mock
    return b


def _api_level_balance(stocks):
    # api/kis_market_api.get_account_balance() 가 실제로 만드는 형태 (:661-733)
    return {
        'total_stocks': len(stocks), 'total_value': 5_000_000,
        'total_profit_loss': 0, 'total_profit_loss_rate': 0.0,
        'available_amount': 4_000_000, 'cash_balance': 4_000_000,
        'purchase_amount': 1_000_000, 'next_day_amount': 4_000_000,
        'deposit_total': 4_000_000, 'stocks': stocks,
        'inquiry_time': '2026-08-14 08:00:00',
    }


class TestAccountBalanceContract:
    def test_real_broker_keys_equal_fixture_keys(self):
        """실브로커 get_account_balance() 반환 키 집합이 fixture 와 일치."""
        api = Mock()
        api.get_account_balance.return_value = _api_level_balance([make_holding()])
        result = _bare_broker(api).get_account_balance()
        assert set(result.keys()) == ACCOUNT_BALANCE_KEYS

    def test_invented_keys_are_absent(self):
        """이번 사고의 발명 키 2종이 실계약에 없음을 «양방향»으로 고정."""
        api = Mock()
        api.get_account_balance.return_value = _api_level_balance([])
        result = _bare_broker(api).get_account_balance()
        assert 'positions' not in result
        assert 'account_balance' not in result

    def test_fixture_is_self_consistent(self):
        """fixture 에서 만든 dict 의 키가 선언과 일치."""
        assert set(make_account_balance().keys()) == ACCOUNT_BALANCE_KEYS


class TestHoldingsContract:
    def test_get_holdings_item_keys_equal_fixture_keys(self):
        """실브로커 get_holdings() 반환 항목 키 집합이 fixture 와 일치."""
        api = Mock()
        api.get_existing_holdings.return_value = [make_holding()]
        result = _bare_broker(api).get_holdings()
        assert len(result) == 1
        assert set(result[0].keys()) == HOLDING_ITEM_KEYS

    def test_fixture_is_self_consistent(self):
        """fixture 에서 만든 dict 의 키가 선언과 일치."""
        assert set(make_holding().keys()) == HOLDING_ITEM_KEYS
