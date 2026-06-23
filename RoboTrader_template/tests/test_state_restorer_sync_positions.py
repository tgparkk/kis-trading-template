"""StateRestorer → 전략 self.positions 복원(sync_positions 배선) 회귀.

배경 (Imp-3, 2026-06-23):
  재시작 시 전략 인스턴스의 self.positions 는 인메모리라 {}로 초기화된다.
  base.on_tick 매도 루프는 ctx.get_positions()(프레임워크 보유)를 순회하며
  generate_signal 을 호출하지만, daytrading 등은 `stock_code in self.positions`
  일 때만 _check_sell 로 분기한다. → 복원 포지션은 전략측 _check_sell 이
  영영 호출되지 않아 max_hold(거래일)·sl·tp·trail 청산이 작동하지 않는다.
  프레임워크 백스톱(_apply_stale_position_check)은 30일 stale 마킹·7일 기본
  tp/sl 만 손대고 max_hold 강제청산을 하지 않는다.

수정:
  StateRestorer 가 복원한 보유 종목을 owner 전략의 sync_positions() 로 주입한다.
  entry_time 은 now_kst() 와 비교 가능한 tz-aware KST datetime 으로 정규화한다
  (naive/tz-aware 혼용 시 count_trading_days_between 에서 TypeError → tick 손상).

검증 포인트:
  1. _restore_holdings_from_db 가 owner 전략의 sync_positions 를
     {stock_code: {quantity, entry_price, entry_time}} 형태로 호출한다.
  2. 주입된 entry_time 이 tz-aware 이며 count_trading_days_between(entry_time,
     now_kst()) 가 예외 없이 동작한다.
  3. buy_time 이 None 이면 entry_time=None (daytrading hold_days=0, 무크래시).
  4. e2e: 실제 DayTrading3MethodsBreakoutStrategy 가 sync_positions 로 오래된
     entry_time 을 받은 뒤 _check_sell 이 max_hold SELL 을 낸다 (재시작 후 청산 복원).
"""
import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.korean_time import now_kst
from utils.korean_holidays import count_trading_days_between


def _make_restorer(db_manager, strategies):
    from bot.state_restorer import StateRestorer
    config = Mock()
    config.paper_trading = True
    return StateRestorer(
        trading_manager=Mock(),
        db_manager=db_manager,
        telegram_integration=Mock(),
        config=config,
        get_previous_close_callback=lambda code: 100_000.0,
        broker=None,
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


def _holdings_df(buy_time):
    return pd.DataFrame([
        {
            'id': 1, 'stock_code': '005930', 'stock_name': '삼성전자',
            'quantity': 10, 'buy_price': 100_000.0, 'buy_time': buy_time,
            'strategy': 'stratA', 'target_profit_rate': None, 'stop_loss_rate': None,
        },
    ])


class TestSyncPositionsWiring:
    def test_restore_db_calls_sync_positions(self):
        """복원 시 owner 전략의 sync_positions 가 올바른 형태로 호출된다."""
        buy_time = now_kst() - timedelta(days=20)
        strat = Mock()
        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df(buy_time)

        restorer = _make_restorer(db, strategies={'stratA': strat})
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)

        asyncio.run(restorer._restore_holdings_from_db())

        strat.sync_positions.assert_called_once()
        (positions,) = strat.sync_positions.call_args[0]
        assert '005930' in positions
        pos = positions['005930']
        assert pos['quantity'] == 10
        assert pos['entry_price'] == pytest.approx(100_000.0)
        # entry_time tz-aware + now_kst 와 비교 가능 (TypeError 없음)
        assert pos['entry_time'] is not None
        assert pos['entry_time'].tzinfo is not None
        assert count_trading_days_between(pos['entry_time'], now_kst()) >= 1

    def test_buy_time_none_yields_none_entry_time(self):
        """buy_time None → entry_time None (daytrading hold_days=0, 무크래시)."""
        strat = Mock()
        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df(None)

        restorer = _make_restorer(db, strategies={'stratA': strat})
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)

        asyncio.run(restorer._restore_holdings_from_db())

        strat.sync_positions.assert_called_once()
        (positions,) = strat.sync_positions.call_args[0]
        assert positions['005930']['entry_time'] is None

    def test_unresolved_owner_skips_silently(self):
        """owner 전략이 strategies dict 에 없으면 조용히 스킵(크래시 없음)."""
        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df(now_kst())

        restorer = _make_restorer(db, strategies={})  # stratA 미등록
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)

        # 예외 없이 완료되어야 한다
        asyncio.run(restorer._restore_holdings_from_db())


class TestDaytradingMaxHoldAfterRestart:
    def _build(self):
        from strategies.daytrading_3methods_breakout.strategy import (
            DayTrading3MethodsBreakoutStrategy,
        )
        strat = DayTrading3MethodsBreakoutStrategy({
            "parameters": {"min_daily_bars": 25, "max_holding_days": 10},
            "risk_management": {
                "take_profit_pct": 0.10, "stop_loss_pct": 0.10,
                "max_hold_days": 10, "trail_ma": None, "max_positions": 5,
            },
            "paper_trading": True,
        })
        strat.on_init(broker=None, data_provider=None, executor=None)
        return strat

    def test_max_hold_fires_after_sync_positions(self):
        """sync_positions 로 오래된 entry_time 주입 → _check_sell 이 max_hold SELL."""
        from strategies.base import SignalType
        strat = self._build()

        # 손익 0%(ret≈0) 평탄 일봉 — sl/tp 미발동, max_hold 만 트리거되게
        entry_price = 10_000.0
        df = pd.DataFrame({
            "datetime": pd.date_range("2025-01-01", periods=30, freq="D"),
            "open": [entry_price] * 30,
            "high": [entry_price * 1.001] * 30,
            "low": [entry_price * 0.999] * 30,
            "close": [entry_price] * 30,
            "volume": [1_000_000] * 30,
        })

        # 20 캘린더일 전 진입(>10 거래일) — tz-aware
        old_entry = now_kst() - timedelta(days=20)
        strat.sync_positions({
            "005930": {"quantity": 10, "entry_price": entry_price,
                       "entry_time": old_entry},
        })

        sig = strat.generate_signal("005930", df, timeframe="daily")
        assert sig is not None
        assert sig.signal_type == SignalType.SELL
        assert sig.metadata["exit_reason"] == "max_hold"
