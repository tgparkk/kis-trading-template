"""StateRestorer 라이브(실전) 복원이 real_trading_records 를 읽는지 회귀.

배경 (사전-실전 감사 BLOCKER #3/#4, 2026-06-24):
  실전 재시작 복원 경로는 보유 종목의 owner 전략·tp/sl 보강을
  get_virtual_open_positions()(=virtual_trading_records WHERE is_test=true)에서
  읽었다. 그러나 실거래 체결은 real_trading_records 에 저장된다(save_real_buy).
  → 가상 테이블엔 실보유가 없어:
    #3 broker 잔고조회 실패 시 _restore_holdings_from_db 폴백이 빈 가상 테이블을
       읽어 실포지션 0건 복원(SL/TP/max_hold/EOD 전무, 슬롯 비어 과다진입).
    #4 happy-path _restore_holdings_from_real_account 도 owner 를 빈 가상 테이블
       에서 유도 → owner 공백 → 전략 self.positions 미주입 → 전략별 청산 무력.

  기존 테스트(test_state_restorer_sync_positions.py)는 paper_trading=True 경로만
  검증해 이 라이브 결함을 가렸다.

검증 포인트:
  1. 라이브 모드 _restore_holdings_from_db 폴백이 real 테이블을 읽어 복원·owner 주입.
  2. 라이브 happy-path _restore_holdings_from_real_account 가 real 테이블에서 owner
     를 바인딩해 sync_positions 로 주입.
  3. 페이퍼 모드는 종전대로 virtual 테이블을 읽는다(회귀 없음).
"""
import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.korean_time import now_kst


def _make_restorer(db_manager, strategies, paper_trading, broker=None):
    from bot.state_restorer import StateRestorer
    config = Mock()
    config.paper_trading = paper_trading
    return StateRestorer(
        trading_manager=Mock(),
        db_manager=db_manager,
        telegram_integration=Mock(),
        config=config,
        get_previous_close_callback=lambda code: 100_000.0,
        broker=broker,
        fund_manager=None,
        virtual_trading_manager=None,
        strategies=strategies,
    )


def _wire_trading_manager(restorer):
    async def _add(**kwargs):
        return True
    restorer.trading_manager.add_selected_stock.side_effect = _add

    stocks = {}

    def _get(code, strategy=None):
        return stocks.setdefault(code, Mock())
    restorer.trading_manager.get_trading_stock.side_effect = _get
    restorer.trading_manager._change_stock_state = Mock()
    return stocks


def _holdings_df(buy_time, owner='stratA'):
    return pd.DataFrame([
        {
            'id': 1, 'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 100_000.0, 'buy_time': buy_time,
            'strategy': owner, 'target_profit_rate': None, 'stop_loss_rate': None,
        },
    ])


class TestLiveDbFallbackReadsRealTable:
    """#3: 라이브 폴백이 real 테이블을 읽어 실포지션을 복원한다."""

    def test_live_fallback_restores_from_real_table(self):
        buy_time = now_kst() - timedelta(days=20)
        strat = Mock()
        db = Mock()
        # 실보유는 real 테이블에만 있고 virtual 은 비어 있다.
        db.get_real_open_positions.return_value = _holdings_df(buy_time)
        db.get_virtual_open_positions.return_value = pd.DataFrame()

        restorer = _make_restorer(db, strategies={'stratA': strat}, paper_trading=False)
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)

        asyncio.run(restorer._restore_holdings_from_db())

        db.get_real_open_positions.assert_called()
        strat.sync_positions.assert_called_once()
        (positions,) = strat.sync_positions.call_args[0]
        assert '005930' in positions
        assert positions['005930']['quantity'] == 10

    def test_paper_mode_still_reads_virtual_table(self):
        """회귀: 페이퍼 모드는 종전대로 virtual 테이블을 읽는다."""
        buy_time = now_kst() - timedelta(days=20)
        strat = Mock()
        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df(buy_time)

        restorer = _make_restorer(db, strategies={'stratA': strat}, paper_trading=True)
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)

        asyncio.run(restorer._restore_holdings_from_db())

        db.get_virtual_open_positions.assert_called()
        strat.sync_positions.assert_called_once()


class TestLiveRealAccountBindsOwnerFromRealTable:
    """#4: happy-path 실계좌 복원이 real 테이블에서 owner 를 바인딩한다."""

    def test_real_account_restore_binds_owner_and_syncs(self):
        buy_time = now_kst() - timedelta(days=20)
        strat = Mock()
        db = Mock()
        db.get_real_open_positions.return_value = _holdings_df(buy_time)
        db.get_virtual_open_positions.return_value = pd.DataFrame()

        broker = Mock()
        broker.get_account_balance.return_value = {
            'positions': [{
                'stock_code': '005930', 'stock_name': '삼성전자',
                'quantity': 10, 'avg_price': 100_000.0,
            }],
        }
        broker.get_pending_orders.return_value = []

        restorer = _make_restorer(db, strategies={'stratA': strat}, paper_trading=False, broker=broker)
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)
        restorer._detect_holdings_mismatch = AsyncMock()
        restorer._apply_stale_position_check = Mock(return_value=(0.05, 0.03))

        asyncio.run(restorer._restore_holdings_from_real_account())

        db.get_real_open_positions.assert_called()
        strat.sync_positions.assert_called_once()
        (positions,) = strat.sync_positions.call_args[0]
        assert '005930' in positions
        assert positions['005930']['quantity'] == 10
