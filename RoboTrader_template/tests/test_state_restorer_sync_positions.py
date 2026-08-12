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
from unittest.mock import AsyncMock, MagicMock, Mock, patch

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


class TestApplyPendingStrategyPositions:
    """운영 순서 결함(2026-08-12 라이브 실측) 재현 + 수정 회귀.

    main.py:264-271 순서: StateRestorer(→_sync_strategy_positions 즉시 주입)가
    strategy.on_init() 보다 먼저 실행된다. on_init 은 self.positions = {} 로
    초기화하므로(daytrading_3methods_breakout/strategy.py:96 등) 복원 직후
    주입이 지워진다. 라이브 로그에서 같은 초(07:40:35)에
    "[sync_positions] 포지션 동기화 완료: 19종목" → "초기화 완료" 가 연달아
    찍힌 뒤 09:00:40 "장 시작 — 보유 종목 없음"으로 이어진 것이 그 증거다.

    apply_pending_strategy_positions() 는 main.py 가 _initialize_strategy()
    (on_init 호출) 직후 재호출해 이 공백을 메운다. main.py 쪽 배선 순서 자체는
    TestApplyPendingWiringOrder 가 별도로 검증한다.
    """

    def _build_real_strategy(self):
        from strategies.daytrading_3methods_breakout.strategy import (
            DayTrading3MethodsBreakoutStrategy,
        )
        return DayTrading3MethodsBreakoutStrategy({
            "parameters": {"min_daily_bars": 25, "max_holding_days": 10},
            "risk_management": {
                "take_profit_pct": 0.10, "stop_loss_pct": 0.10,
                "max_hold_days": 10, "trail_ma": None, "max_positions": 5,
            },
            "paper_trading": True,
        })

    def test_on_init_wipes_injection_then_apply_pending_restores_it(self):
        """대칭 단언: ① on_init 이 실제로 지운다(버그가 실재함을 고정하는,
        판별력 있는 절반) ② apply_pending_strategy_positions 가 되돌린다(수정 실증)."""
        buy_time = now_kst() - timedelta(days=5)
        strat = self._build_real_strategy()
        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df(buy_time)

        restorer = _make_restorer(db, strategies={'stratA': strat})
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)

        # 1) 운영 순서 재현: 복원(즉시 주입, 기존 배선 불변) → on_init
        asyncio.run(restorer._restore_holdings_from_db())
        assert '005930' in strat.positions  # 즉시 주입은 여전히 동작(회귀 없음)

        strat.on_init(broker=None, data_provider=None, executor=None)

        # 판별력 있는 절반: on_init 이 정말로 지운다(라이브 결함의 근본원인을 고정)
        assert strat.positions == {}

        # 2) 수정: on_init 이후 재주입
        synced = restorer.apply_pending_strategy_positions()

        assert synced == 1
        assert '005930' in strat.positions
        pos = strat.positions['005930']
        assert pos['quantity'] == 10
        assert pos['entry_price'] == pytest.approx(100_000.0)
        assert pos['entry_time'] is not None
        assert pos['entry_time'].tzinfo is not None

    def test_apply_pending_is_idempotent(self):
        """재호출해도 크래시·중복 없이 동일 결과
        (BaseStrategy.sync_positions 는 dict.update 라 재주입이 멱등)."""
        buy_time = now_kst() - timedelta(days=5)
        strat = self._build_real_strategy()
        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df(buy_time)

        restorer = _make_restorer(db, strategies={'stratA': strat})
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)

        asyncio.run(restorer._restore_holdings_from_db())
        strat.on_init(broker=None, data_provider=None, executor=None)

        first = restorer.apply_pending_strategy_positions()
        second = restorer.apply_pending_strategy_positions()

        assert first == 1
        assert second == 1
        assert list(strat.positions.keys()) == ['005930']

    def test_unresolved_owner_skips_silently_in_apply_pending(self):
        """apply_pending 시점에 owner 가 strategies dict 에 없으면 조용히 스킵(크래시 없음)."""
        db = Mock()
        db.get_virtual_open_positions.return_value = _holdings_df(now_kst())

        restorer = _make_restorer(db, strategies={})  # stratA 미등록
        _wire_trading_manager(restorer)
        restorer._sync_fund_manager_for_position = Mock(return_value=0.0)

        asyncio.run(restorer._restore_holdings_from_db())

        synced = restorer.apply_pending_strategy_positions()  # 예외 없이 완료
        assert synced == 0


class TestApplyPendingWiringOrder:
    """main.py::DayTradingBot.initialize() 의 배선 순서 회귀.

    ⚠️ 소스 문자열 검사(`inspect.getsource` 로 호출부 존재만 확인)를 의도적으로
    쓰지 않는다 — 이 레포는 그 방식이 실패한 전례가 있다
    (tests/bot/test_initializer_market_mapping_preload.py:93-99, 2026-08-04):
    호출을 주석 처리해도 · `if False:` 안에 넣어도 · 도달 불가 위치로 옮겨도
    문자열 검사는 전부 통과시켰다. 대신 실제 DayTradingBot.initialize() 를
    호출해 호출 "순서"를 기록하는 런타임 검증을 쓴다 — 이는 impractical 하지
    않다: tests/test_main_smoke.py::TestBotInitialization 이 이미 broker/DB/
    telegram/설정/전략로더만 patch 하고 나머지는 실제 __init__ 경로를 태우는
    동일 패턴으로 실제 DayTradingBot() 을 만들어 성공하고 있다.
    """

    def _make_bootable_bot(self, log):
        with patch('main.KISBroker') as mock_broker_cls, \
             patch('main.DatabaseManager') as mock_db_cls, \
             patch('main.TelegramIntegration'), \
             patch('main.check_duplicate_process'), \
             patch('main.load_config') as mock_load_config, \
             patch('main.StrategyLoader') as mock_loader:

            mock_load_config.return_value = MagicMock(
                rebalancing_mode=False,
                strategy={'name': 'sample', 'enabled': False},
            )
            mock_db_cls.return_value.db_path = ':memory:'
            mock_broker_cls.return_value.connect = AsyncMock(return_value=True)
            mock_loader.load_strategy.side_effect = FileNotFoundError("test")

            from main import DayTradingBot
            bot = DayTradingBot()

        # bot.strategies 는 StrategyLoader FileNotFoundError 로 {} 확정
        # (self.strategy=None) → initialize() 의 전략 연결 분기는 전부 스킵되고
        # 아래 3개 호출 순서만 남는다.
        async def _init_system():
            log.append("initialize_system")
            return True
        bot.bot_initializer.initialize_system = _init_system

        async def _init_strategy():
            log.append("_initialize_strategy")
            return True
        bot._initialize_strategy = _init_strategy

        def _apply_pending():
            log.append("apply_pending_strategy_positions")
            return 0
        bot.state_restoration_helper.apply_pending_strategy_positions = _apply_pending

        return bot

    def test_apply_pending_runs_after_initialize_strategy(self):
        log = []
        bot = self._make_bootable_bot(log)

        ok = asyncio.run(bot.initialize())

        assert ok is True
        assert "apply_pending_strategy_positions" in log, (
            f"initialize() 가 apply_pending_strategy_positions 를 호출하지 않았다: {log}"
        )
        assert log.index("apply_pending_strategy_positions") > log.index("_initialize_strategy"), (
            f"재주입이 on_init(_initialize_strategy) 보다 먼저/동시에 실행됐다 — 순서 위반: {log}"
        )
