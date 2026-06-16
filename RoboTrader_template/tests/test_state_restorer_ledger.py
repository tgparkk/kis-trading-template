"""StateRestorer ↔ 전략 원장 재구성 연동 테스트.

검증 포인트:
- 원장 활성(_strategy_balances 존재) 시:
    · _sync_virtual_balance_for_position 가 즉시 return (이중차감 방지)
    · _restore_holdings_from_db 루프 종료 후 get_strategy_trade_sums 호출 +
      restore_strategy_ledger_from_records 로 전략 원장이 매매기록에서 재구성된다.
- 원장 비활성(레거시) 시:
    · _sync_virtual_balance_for_position 가 기존 update_virtual_balance 호출
    · 재구성 경로 미호출 (단일 잔고 불변)
"""
import asyncio
import pandas as pd
import pytest
from unittest.mock import Mock, patch


def _make_vtm(paper=True):
    with patch('core.virtual_trading_manager.setup_logger'):
        from core.virtual_trading_manager import VirtualTradingManager
        return VirtualTradingManager(db_manager=None, broker=None, paper_trading=paper)


def _make_restorer(db_manager, vtm):
    from bot.state_restorer import StateRestorer
    config = Mock()
    config.paper_trading = True
    restorer = StateRestorer(
        trading_manager=Mock(),
        db_manager=db_manager,
        telegram_integration=Mock(),
        config=config,
        get_previous_close_callback=lambda code: 100_000.0,
        broker=None,
        fund_manager=None,
        virtual_trading_manager=vtm,
        strategies={},
    )
    return restorer


# ---------------------------------------------------------------------------
# _sync_virtual_balance_for_position 가드
# ---------------------------------------------------------------------------

class TestSyncGuard:
    def test_skips_when_ledger_active(self):
        """원장 활성 시 update_virtual_balance 미호출 (재구성이 담당)."""
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", 10_000_000)
        vtm.update_virtual_balance = Mock()
        restorer = _make_restorer(Mock(), vtm)

        restorer._sync_virtual_balance_for_position(10, 100_000.0)
        vtm.update_virtual_balance.assert_not_called()

    def test_runs_when_ledger_inactive(self):
        """레거시(원장 미활성): 기존 update_virtual_balance 호출."""
        vtm = _make_vtm()  # 할당 없음
        vtm.update_virtual_balance = Mock()
        restorer = _make_restorer(Mock(), vtm)

        restorer._sync_virtual_balance_for_position(10, 100_000.0)
        vtm.update_virtual_balance.assert_called_once_with(1_000_000.0, "매수")


# ---------------------------------------------------------------------------
# _restore_holdings_from_db 재구성 연동
# ---------------------------------------------------------------------------

def _holdings_df():
    return pd.DataFrame([
        {
            'id': 1, 'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 100_000.0, 'buy_time': None,
            'strategy': 'stratA', 'target_profit_rate': None, 'stop_loss_rate': None,
        },
        {
            'id': 2, 'stock_code': '000660', 'stock_name': '하이닉스',
            'quantity': 6, 'buy_price': 110_000.0, 'buy_time': None,
            'strategy': 'stratB', 'target_profit_rate': None, 'stop_loss_rate': None,
        },
    ])


def _wire_trading_manager(restorer):
    """add_selected_stock/get_trading_stock 가 동작하도록 trading_manager mock 구성."""
    async def _add(**kwargs):
        return True
    restorer.trading_manager.add_selected_stock.side_effect = _add

    stocks = {}

    def _get(code, strategy=None):
        ts = stocks.setdefault(code, Mock())
        return ts
    restorer.trading_manager.get_trading_stock.side_effect = _get
    restorer.trading_manager._change_stock_state = Mock()
    return stocks


class TestRestoreHoldingsReconstruction:
    def test_ledger_active_triggers_reconstruction(self):
        from config.constants import COMMISSION_RATE
        vtm = _make_vtm()
        vtm.allocate_strategy_capital("stratA", 10_000_000)
        vtm.allocate_strategy_capital("stratB", 10_000_000)

        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df()
        db.get_strategy_trade_sums.return_value = {
            'stratA': {'buy_gross': 1_000_000.0, 'sell_gross': 0.0},
            'stratB': {'buy_gross': 660_000.0, 'sell_gross': 0.0},
        }

        restorer = _make_restorer(db, vtm)
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)
        restorer._resolve_owner_strategy = Mock(return_value=None)

        asyncio.run(restorer._restore_holdings_from_db())

        # 재구성 호출됨
        db.get_strategy_trade_sums.assert_called_once()
        # cash 식 반영 (매수만)
        assert vtm.get_strategy_balance("stratA") == pytest.approx(
            10_000_000 - 1_000_000.0 * (1.0 + COMMISSION_RATE))
        assert vtm.get_strategy_balance("stratB") == pytest.approx(
            10_000_000 - 660_000.0 * (1.0 + COMMISSION_RATE))
        # owner 복원
        assert vtm._position_owner == {'005930': 'stratA', '000660': 'stratB'}

    def test_ledger_inactive_skips_reconstruction(self):
        vtm = _make_vtm()  # 할당 없음 → 원장 비활성

        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df()
        db.get_strategy_trade_sums = Mock()

        restorer = _make_restorer(db, vtm)
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)
        restorer._resolve_owner_strategy = Mock(return_value=None)

        balance_before = vtm.virtual_balance
        asyncio.run(restorer._restore_holdings_from_db())

        # 재구성 미호출
        db.get_strategy_trade_sums.assert_not_called()
        # 레거시 단일 잔고 차감 (2종목 매수액 = 1,000,000 + 660,000)
        assert vtm.virtual_balance == pytest.approx(
            balance_before - 1_000_000.0 - 660_000.0)
