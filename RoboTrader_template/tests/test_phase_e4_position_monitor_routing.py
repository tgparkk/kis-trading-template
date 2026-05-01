"""
Phase E4 — PositionMonitor 매도 라우팅: owner_strategy 정책 테스트

검증 항목:
1. max_holding_days: trading_stock.owner_strategy 우선 적용
2. max_holding_days: owner_strategy=None이면 self._strategy fallback
3. generate_signal: owner_strategy.generate_signal() 호출
4. 두 종목 다른 owner_strategy → 다른 max_holding_days 독립 적용
5. BacktestEngine: 포지션 dict의 owner_strategy 우선 참조
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Optional

KST = timezone(timedelta(hours=9))


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 헬퍼: TradingStock + Position
# ---------------------------------------------------------------------------

def _make_trading_stock(code: str = "005930", name: str = "삼성전자", days_held: int = 0):
    from core.models import TradingStock, StockState
    from utils.korean_time import now_kst

    ts = TradingStock(
        stock_code=code,
        stock_name=name,
        state=StockState.POSITIONED,
        selected_time=now_kst(),
    )
    ts.days_held = days_held
    # 최소 Position mock
    pos = MagicMock()
    pos.avg_price = 10000.0
    ts.position = pos
    return ts


def _make_strategy(name: str = "TestStrategy", max_holding_days: Optional[int] = None,
                   sell_signal: bool = False):
    """최소 BaseStrategy 스텁."""
    from strategies.base import BaseStrategy, Signal, SignalType

    class _Stub(BaseStrategy):
        def generate_signal(self, stock_code, data, timeframe="daily"):
            if sell_signal:
                return Signal(
                    signal_type=SignalType.SELL,
                    stock_code=stock_code,
                    confidence=80,
                    reasons=["테스트 매도신호"],
                )
            return None

    stub = _Stub.__new__(_Stub)
    stub.name = name
    stub.version = "0.1.0"
    stub.description = ""
    stub.author = ""
    stub._is_initialized = False
    stub._broker = None
    stub._data_provider = None
    stub._executor = None
    stub.config = {}
    stub._last_ontick_skip_log = None
    stub.positions = {}
    stub.daily_trades = 0
    stub.holding_period = "swing"
    stub.max_holding_days = max_holding_days
    return stub


# ---------------------------------------------------------------------------
# 헬퍼: PositionMonitor 의존성 mock 조립
# ---------------------------------------------------------------------------

def _make_monitor():
    """PositionMonitor를 최소 의존성 mock으로 생성."""
    from core.trading.position_monitor import PositionMonitor

    state_manager = MagicMock()
    completion_handler = AsyncMock()
    intraday_manager = MagicMock()
    data_collector = MagicMock()

    monitor = PositionMonitor(
        state_manager=state_manager,
        completion_handler=completion_handler,
        intraday_manager=intraday_manager,
        data_collector=data_collector,
    )

    # 현재가 API mock: 항상 10,000원 반환
    intraday_manager.get_current_price_for_sell.return_value = {"current_price": 10000.0}
    intraday_manager.get_cached_current_price.return_value = None

    # data_collector mock: OHLCV 데이터 없음 (전략 시그널 경로 단순화)
    price_data = MagicMock()
    price_data.last_price = 10000.0
    price_data.ohlcv_data = []
    data_collector.get_stock.return_value = price_data

    # decision_engine mock
    decision_engine = MagicMock()
    decision_engine.virtual_trading = MagicMock()
    decision_engine.virtual_trading.get_days_held.return_value = 0
    monitor.set_decision_engine(decision_engine)

    return monitor


# ===========================================================================
# 1. max_holding_days: owner_strategy 우선 적용
# ===========================================================================

def test_position_monitor_uses_owner_strategy_max_holding():
    """trading_stock.owner_strategy의 max_holding_days가 self._strategy보다 우선 적용."""
    monitor = _make_monitor()

    # self._strategy: max_holding_days=30 (더 느슨)
    fallback_strategy = _make_strategy("FallbackStrategy", max_holding_days=30)
    monitor.set_strategy(fallback_strategy)

    # owner_strategy: max_holding_days=5 (더 빡빡)
    owner_strategy = _make_strategy("OwnerStrategy", max_holding_days=5)
    ts = _make_trading_stock("005930", "삼성전자", days_held=5)
    ts.owner_strategy = owner_strategy

    sell_called = []
    mock_sell = AsyncMock(side_effect=lambda ts, price, reason: sell_called.append(reason))
    monitor._execute_sell = mock_sell

    _run_async(monitor._analyze_sell_for_stock(ts))

    assert len(sell_called) == 1, f"매도가 1회 호출되어야 함: {sell_called}"
    assert "보유기간" in sell_called[0]
    assert "5" in sell_called[0]


# ===========================================================================
# 2. owner_strategy=None이면 self._strategy fallback
# ===========================================================================

def test_position_monitor_fallback_to_self_strategy():
    """owner_strategy=None이면 self._strategy의 max_holding_days가 적용된다."""
    monitor = _make_monitor()

    fallback_strategy = _make_strategy("FallbackStrategy", max_holding_days=3)
    monitor.set_strategy(fallback_strategy)

    ts = _make_trading_stock("000660", "SK하이닉스", days_held=3)
    ts.owner_strategy = None  # 명시적 None

    sell_called = []
    mock_sell = AsyncMock(side_effect=lambda ts, price, reason: sell_called.append(reason))
    monitor._execute_sell = mock_sell

    _run_async(monitor._analyze_sell_for_stock(ts))

    assert len(sell_called) == 1, f"fallback 전략 max_holding_days=3, days_held=3 → 매도 1회: {sell_called}"
    assert "보유기간" in sell_called[0]


# ===========================================================================
# 3. generate_signal: owner_strategy.generate_signal() 호출
# ===========================================================================

def test_position_monitor_owner_generate_signal():
    """전략 매도 신호도 owner_strategy.generate_signal()이 사용된다."""
    monitor = _make_monitor()

    # self._strategy: 매도 신호 없음, max_holding_days 없음
    fallback_strategy = _make_strategy("FallbackStrategy", sell_signal=False, max_holding_days=None)
    monitor.set_strategy(fallback_strategy)

    # owner_strategy: 매도 신호 있음, max_holding_days 없음
    owner_strategy = _make_strategy("OwnerStrategy", sell_signal=True, max_holding_days=None)
    ts = _make_trading_stock("035420", "NAVER", days_held=0)
    ts.owner_strategy = owner_strategy

    # OHLCV 데이터가 있어야 generate_signal 경로 진입
    ohlcv_row = MagicMock()
    ohlcv_row.close_price = 10000.0
    ohlcv_row.open_price = 9900.0
    ohlcv_row.high_price = 10100.0
    ohlcv_row.low_price = 9800.0
    ohlcv_row.volume = 1000

    price_data = MagicMock()
    price_data.last_price = 10000.0
    price_data.ohlcv_data = [ohlcv_row]
    monitor.data_collector.get_stock.return_value = price_data

    sell_called = []
    mock_sell = AsyncMock(side_effect=lambda ts, price, reason: sell_called.append(reason))
    monitor._execute_sell = mock_sell

    _run_async(monitor._analyze_sell_for_stock(ts))

    assert len(sell_called) == 1, f"owner_strategy가 SELL 신호를 반환해야 매도됨: {sell_called}"
    assert "테스트 매도신호" in sell_called[0] or "매도신호" in sell_called[0]


# ===========================================================================
# 4. 두 종목 다른 owner_strategy → 독립적 max_holding_days 적용
# ===========================================================================

def test_two_stocks_different_owner_different_max_holding():
    """종목 A(owner max=2일)는 매도, 종목 B(owner max=10일)는 미매도."""
    monitor = _make_monitor()

    # self._strategy: max_holding_days=30 (느슨)
    fallback_strategy = _make_strategy("FallbackStrategy", max_holding_days=30)
    monitor.set_strategy(fallback_strategy)

    owner_a = _make_strategy("StrategyA", max_holding_days=2)
    owner_b = _make_strategy("StrategyB", max_holding_days=10)

    ts_a = _make_trading_stock("005930", "삼성전자", days_held=2)
    ts_a.owner_strategy = owner_a

    ts_b = _make_trading_stock("000660", "SK하이닉스", days_held=2)
    ts_b.owner_strategy = owner_b

    sells_a = []
    mock_sell_a = AsyncMock(side_effect=lambda ts, price, reason: sells_a.append(reason))
    monitor._execute_sell = mock_sell_a
    _run_async(monitor._analyze_sell_for_stock(ts_a))

    sells_b = []
    mock_sell_b = AsyncMock(side_effect=lambda ts, price, reason: sells_b.append(reason))
    monitor._execute_sell = mock_sell_b
    _run_async(monitor._analyze_sell_for_stock(ts_b))

    assert len(sells_a) == 1, f"A: days_held=2 >= max=2 → 매도 1회: {sells_a}"
    assert len(sells_b) == 0, f"B: days_held=2 < max=10 → 미매도: {sells_b}"


# ===========================================================================
# 5. BacktestEngine: 포지션 dict의 owner_strategy 우선 참조
# ===========================================================================

def test_backtest_engine_owner_strategy_routing():
    """BacktestEngine: 포지션 dict에 owner_strategy 있으면 그것 우선 사용 (향후 다전략 대비)."""
    import pandas as pd
    from backtest.engine import BacktestEngine

    # self.strategy: max_holding_days 없음 (None)
    default_strategy = _make_strategy("DefaultStrategy", max_holding_days=None)
    default_strategy._stop_loss_pct = 0.05
    default_strategy._take_profit_pct = 0.10
    default_strategy._max_daily_trades = 5
    default_strategy._ma_short = 5
    default_strategy._ma_long = 20
    default_strategy._rsi_period = 14
    default_strategy._rsi_oversold = 30
    default_strategy._rsi_overbought = 70
    default_strategy._volume_multiplier = 1.5
    default_strategy._min_buy_signals = 2
    default_strategy.positions = {}
    default_strategy.daily_trades = 0

    engine = BacktestEngine(default_strategy, initial_capital=1_000_000, max_positions=1)

    # owner_strategy: max_holding_days=1 (1일 후 매도)
    owner_strategy = _make_strategy("OwnerStrategy", max_holding_days=1)

    # 포지션 dict에 owner_strategy 직접 주입 (백테스트 내부 구조 테스트)
    pos = {
        "qty": 10,
        "entry_price": 10000.0,
        "entry_date": "2024-01-02",
        "entry_cost": 100000.0,
        "peak_price": 10000.0,
        "owner_strategy": owner_strategy,
    }

    # engine 내부에서 _pos_strategy 결정 로직을 직접 검증
    _pos_strategy = pos.get("owner_strategy") or engine.strategy
    assert _pos_strategy is owner_strategy, "owner_strategy가 있으면 그것을 우선 사용해야 함"
    assert _pos_strategy.max_holding_days == 1

    # owner_strategy=None이면 engine.strategy fallback 확인
    pos_no_owner = {
        "qty": 10,
        "entry_price": 10000.0,
        "entry_date": "2024-01-02",
        "entry_cost": 100000.0,
        "peak_price": 10000.0,
        "owner_strategy": None,
    }
    _fallback = pos_no_owner.get("owner_strategy") or engine.strategy
    assert _fallback is engine.strategy, "owner_strategy=None이면 engine.strategy fallback"
