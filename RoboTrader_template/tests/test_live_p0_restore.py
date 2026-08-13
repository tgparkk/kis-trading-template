"""D2: 실전 복원 — get_holdings 결선·빈/실패 판별·분할매수 합산."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

from tests.broker_contract import make_account_balance, make_holding
from utils.exceptions import LiveStartupAbort
from tests.test_state_restorer_live_real_table import (
    _make_restorer, _wire_trading_manager, _holdings_df,
)
from utils.korean_time import now_kst
from datetime import timedelta


def _real_broker_mock(holdings, total_stocks=None):
    broker = Mock()
    n = len(holdings) if total_stocks is None else total_stocks
    broker.get_account_balance.return_value = make_account_balance(total_stocks=n)
    broker.get_holdings.return_value = holdings
    broker.get_pending_orders.return_value = []   # Task 6 전까지는 소비자 없음(무해)
    return broker


def _restorer_with(db, broker, strat):
    r = _make_restorer(db, strategies={'stratA': strat}, paper_trading=False, broker=broker)
    _wire_trading_manager(r)
    r._sync_fund_manager_for_position = Mock(return_value=0.0)
    r._apply_stale_position_check = Mock(return_value=(0.05, 0.03))
    return r


class TestHoldingsWiring:
    def test_restore_uses_get_holdings_and_restores(self):
        """red 재현: 현행은 요약 dict 의 없는 키 positions 를 읽어 0건 복원."""
        buy_time = now_kst() - timedelta(days=20)
        db = Mock()
        db.get_real_open_positions.return_value = _holdings_df(buy_time)
        strat = Mock()
        broker = _real_broker_mock([make_holding()])
        r = _restorer_with(db, broker, strat)
        asyncio.run(r._restore_holdings_from_real_account())
        broker.get_holdings.assert_called()
        strat.sync_positions.assert_called_once()

    def test_summary_says_n_but_list_empty_aborts(self):
        """7b: total_stocks>0 인데 목록 0건 = 조회 실패 (get_holdings 오류 삼킴 대응)."""
        db = Mock(); db.get_real_open_positions.return_value = pd.DataFrame()
        broker = _real_broker_mock([], total_stocks=2)
        r = _restorer_with(db, broker, Mock())
        with pytest.raises(LiveStartupAbort):
            asyncio.run(r._restore_holdings_from_real_account())

    def test_truly_empty_account_starts_normally(self):
        """7: 요약 0 & 목록 0 & DB 0 = 신규 계좌, 정상."""
        db = Mock(); db.get_real_open_positions.return_value = pd.DataFrame()
        broker = _real_broker_mock([])
        r = _restorer_with(db, broker, Mock())
        asyncio.run(r._restore_holdings_from_real_account())  # no raise

    def test_summary_query_failure_aborts_no_db_fallback(self):
        """조회 실패 시 「DB 폴백으로 계속」 제거 확인."""
        db = Mock(); db.get_real_open_positions.return_value = pd.DataFrame()
        broker = Mock(); broker.get_account_balance.return_value = {}
        r = _restorer_with(db, broker, Mock())
        r._restore_holdings_from_db = AsyncMock()
        with pytest.raises(LiveStartupAbort):
            asyncio.run(r._restore_holdings_from_real_account())
        r._restore_holdings_from_db.assert_not_called()


class TestSplitBuyAggregation:
    def test_two_buy_rows_same_code_are_summed(self):
        """6: 분할매수 BUY 2행이 수량 SUM·가중평균으로 합산돼 불일치 오탐 0."""
        buy_time = now_kst() - timedelta(days=5)
        rows = pd.DataFrame([
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 6,
             'buy_price': 100_000.0, 'buy_time': buy_time, 'strategy': 'stratA'},
            {'stock_code': '005930', 'stock_name': '삼성전자', 'quantity': 4,
             'buy_price': 110_000.0, 'buy_time': buy_time, 'strategy': 'stratA'},
        ])
        db = Mock(); db.get_real_open_positions.return_value = rows
        strat = Mock()
        broker = _real_broker_mock([make_holding(quantity=10, avg_price=104_000.0)])
        r = _restorer_with(db, broker, strat)
        asyncio.run(r._restore_holdings_from_real_account())  # 수량 10=10 → 불일치 없음 → no raise
        strat.sync_positions.assert_called_once()
