"""
B2 버그(경로 B): 음수 target_profit_rate → 매수 직후 즉시 익절 회귀 테스트

근거: docs/superpowers/plans/2026-06-25-B2-sameday-exit-findings.md §2 경로 B, §5 권고

확정 사례: 089970 (2026-06-12)
- signal.target_price = 전일종가 × 1.10 (전일 확정종가 기준)
- buy_price = 갭업 체결가 > signal.target_price
- → target_profit_rate = (target_price - buy_price)/buy_price = 음수
- → position_monitor L307 "profit_rate >= 음수tp" 즉시 참 → 매수 10초 후 청산

2겹 방어:
1. trading_decision_engine: Signal 역산 tp는 양수일 때만 채택 → 전략 config tp로 fallback
2. position_monitor: 음수 tp 방어 (익절 미발동)
"""
import asyncio
from unittest.mock import Mock, AsyncMock

import pytest

from core.trading_decision_engine import TradingDecisionEngine
from core.trading.position_monitor import PositionMonitor
from core.models import TradingStock, StockState, Position


# ---------------------------------------------------------------------------
# Path 1: trading_decision_engine.execute_virtual_buy — Signal 역산 tp 음수 방어
# ---------------------------------------------------------------------------

def _make_engine(strategy=None):
    """execute_virtual_buy 경로를 태우기 위한 최소 의존성 엔진."""
    engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
    engine.logger = Mock()
    engine.strategy = strategy
    engine.intraday_manager = None
    engine.broker = None
    engine.config = Mock(risk_management=None)
    engine.strategies_by_key = {}

    # VTM mock: 체결 성공으로 가정, target/stop_loss를 기록만
    vtm = Mock()
    vtm.get_max_quantity.return_value = 10
    vtm.execute_virtual_buy.return_value = 123  # set_virtual_buy_info(record_id: int)
    engine.virtual_trading = vtm

    # 전략 콜백 no-op
    engine._notify_strategy_order_filled = Mock()
    return engine


def _make_signal(target_price, stop_loss=None):
    sig = Mock()
    sig.target_price = target_price
    sig.stop_loss = stop_loss
    return sig


def _make_trading_stock():
    return TradingStock(
        stock_code="089970",
        stock_name="에이피티씨",
        state=StockState.SELECTED,
        selected_time=__import__('datetime').datetime.now(),
    )


def test_gap_up_signal_does_not_set_negative_tp_falls_back_to_config():
    """갭업 체결이어도 tp/sl은 항상 전략 config%(진입가 기준)로 결정된다.

    옵션α(2026-06-25 Task 5(D)): Signal.target_price/stop_loss 역산(2순위)을 제거.
    Signal 절대가가 무엇이든 tp/sl은 3순위(전략 config%)로 결정 → 백테스트 정합.
    """
    # 전략 config의 take_profit_ratio = 10%, stop_loss_ratio = 8%
    strategy = Mock()
    strategy.name = "book_envelope_200d"
    strategy.config = {"risk_management": {"take_profit_ratio": 0.10, "stop_loss_ratio": 0.08}}

    engine = _make_engine(strategy=strategy)
    stock = _make_trading_stock()

    # 089970 재현 수치: target_price 93,610 < buy_price 95,400 (갭업) — 역산 시 tp 음수였던 케이스
    signal = _make_signal(target_price=93_610, stop_loss=87_900)
    buy_price = 95_400

    result = asyncio.new_event_loop().run_until_complete(
        engine.execute_virtual_buy(
            trading_stock=stock,
            combined_data=None,
            buy_reason="test gap-up",
            buy_price=buy_price,
            signal=signal,
            strategy_name="book_envelope_200d",
        )
    )

    assert result is True
    # 핵심: Signal 절대가 무관, 전략 config%로 결정
    assert stock.target_profit_rate == pytest.approx(0.10)
    assert stock.stop_loss_rate == pytest.approx(0.08)


def test_signal_absolute_price_is_ignored_uses_config():
    """Signal.target_price/stop_loss(절대가)가 설정돼 있어도 무시되고 config%가 사용된다(옵션α).

    갭업 5% 체결: signal.target_price = ref_close*1.10, buy_price = ref_close*1.05.
    역산(구 2순위)이면 tp ≈ +4.76%, sl ≈ +3.81%로 config(10%/8%)와 달라졌을 것.
    제거 후에는 항상 config tp=0.10 / sl=0.08 (진입가 기준)이어야 한다.
    """
    strategy = Mock()
    strategy.name = "rs_leader"
    strategy.config = {"risk_management": {"take_profit_ratio": 0.10, "stop_loss_ratio": 0.08}}

    engine = _make_engine(strategy=strategy)
    stock = _make_trading_stock()

    ref_close = 100_000
    signal = _make_signal(target_price=ref_close * 1.10, stop_loss=ref_close * 0.92)
    buy_price = ref_close * 1.05  # 갭업 5%

    result = asyncio.new_event_loop().run_until_complete(
        engine.execute_virtual_buy(
            trading_stock=stock,
            combined_data=None,
            buy_reason="test gap-up ignore signal",
            buy_price=buy_price,
            signal=signal,
            strategy_name="rs_leader",
        )
    )

    assert result is True
    assert stock.target_profit_rate == pytest.approx(0.10)
    assert stock.stop_loss_rate == pytest.approx(0.08)


def test_caller_explicit_rate_takes_priority_over_config():
    """1순위(호출자 명시 rate)는 여전히 config보다 우선한다."""
    strategy = Mock()
    strategy.name = "rs_leader"
    strategy.config = {"risk_management": {"take_profit_ratio": 0.10, "stop_loss_ratio": 0.08}}

    engine = _make_engine(strategy=strategy)
    stock = _make_trading_stock()

    signal = _make_signal(target_price=110_000, stop_loss=92_000)

    result = asyncio.new_event_loop().run_until_complete(
        engine.execute_virtual_buy(
            trading_stock=stock,
            combined_data=None,
            buy_reason="test explicit",
            buy_price=100_000,
            signal=signal,
            target_profit_rate=0.20,
            stop_loss_rate=0.05,
            strategy_name="rs_leader",
        )
    )

    assert result is True
    # 호출자 명시값 우선 (config 0.10/0.08 아님)
    assert stock.target_profit_rate == pytest.approx(0.20)
    assert stock.stop_loss_rate == pytest.approx(0.05)


def test_config_sl_below_floor_is_clamped_to_3pct():
    """config sl < 3%이면 STOP_LOSS_FLOOR(0.03)로 clamp된다(역산 제거 후에도 유지)."""
    strategy = Mock()
    strategy.name = "book_pullback_ma5_like"
    # config sl = 2% < 3% floor
    strategy.config = {"risk_management": {"take_profit_ratio": 0.15, "stop_loss_ratio": 0.02}}

    engine = _make_engine(strategy=strategy)
    stock = _make_trading_stock()

    signal = _make_signal(target_price=115_000, stop_loss=98_000)

    result = asyncio.new_event_loop().run_until_complete(
        engine.execute_virtual_buy(
            trading_stock=stock,
            combined_data=None,
            buy_reason="test floor",
            buy_price=100_000,
            signal=signal,
            strategy_name="book_pullback_ma5_like",
        )
    )

    assert result is True
    assert stock.target_profit_rate == pytest.approx(0.15)
    # 2% → FLOOR 3%로 clamp
    assert stock.stop_loss_rate == pytest.approx(0.03)


# ---------------------------------------------------------------------------
# Path 2: position_monitor._analyze_sell_for_stock — 음수 tp 익절 미발동
# ---------------------------------------------------------------------------

def _make_monitor():
    monitor = PositionMonitor.__new__(PositionMonitor)
    monitor.logger = Mock()
    monitor.decision_engine = None
    monitor._strategy = None
    monitor.intraday_manager = None
    monitor.data_collector = None
    # 매도 실행 mock (호출 여부로 트리거 판정)
    monitor._execute_sell = AsyncMock()
    monitor._check_trailing_stop = Mock()
    return monitor


def _positioned_stock(buy_price):
    stock = TradingStock(
        stock_code="089970",
        stock_name="에이피티씨",
        state=StockState.POSITIONED,
        selected_time=__import__('datetime').datetime.now(),
    )
    stock.position = Position(stock_code="089970", quantity=10, avg_price=buy_price)
    return stock


def test_position_monitor_skips_take_profit_when_tp_negative():
    """trading_stock.target_profit_rate < 0이어도 익절 매도가 트리거되지 않음."""
    monitor = _make_monitor()
    buy_price = 95_400
    stock = _positioned_stock(buy_price)
    # 음수 tp가 어떤 경로로든 들어온 상황
    stock.target_profit_rate = -0.0188
    stock.stop_loss_rate = 0.18  # 손절 미발동 (큰 손절폭)

    # 현재가: 매수직후 소폭 상승(+0.84%) → profit_rate >= 음수tp 라면 구버전은 즉시 익절
    current_price = buy_price * 1.0084
    monitor._get_current_price = AsyncMock(return_value=current_price)

    asyncio.new_event_loop().run_until_complete(
        monitor._analyze_sell_for_stock(stock)
    )

    # 음수 tp 익절은 발동되면 안 됨
    monitor._execute_sell.assert_not_called()


def test_position_monitor_triggers_take_profit_when_tp_positive():
    """정상 케이스: 양수 tp & profit_rate >= tp이면 익절 정상 발동(회귀 방지)."""
    monitor = _make_monitor()
    buy_price = 100_000
    stock = _positioned_stock(buy_price)
    stock.target_profit_rate = 0.10  # +10% 익절
    stock.stop_loss_rate = 0.08

    # 현재가 +12% → 익절 도달
    current_price = buy_price * 1.12
    monitor._get_current_price = AsyncMock(return_value=current_price)

    asyncio.new_event_loop().run_until_complete(
        monitor._analyze_sell_for_stock(stock)
    )

    monitor._execute_sell.assert_awaited_once()
    # 익절 사유로 호출되었는지 확인
    _, kwargs = (), {}
    call = monitor._execute_sell.await_args
    reason = call.args[2] if len(call.args) >= 3 else call.kwargs.get("reason", "")
    assert "익절" in reason or "목표" in reason
