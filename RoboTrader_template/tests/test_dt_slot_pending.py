"""daytrading 자리(max_positions) = «체결 보유 + 미체결 매수(BUY_PENDING)» (2026-10-26 결함).

닫으려는 결함(10-26 실전 로그 `logs/daytrading/trading_20261026.log`): dt 전략의 자리 검사
`len(self.positions) >= self._max_positions` 는 체결 콜백(`on_order_filled`)에서만 늘어나는
`positions` 만 셌다. 실전 지정가 주문은 수십~수백 초 미체결로 머무는데(013810 09:18:22 주문 →
09:20:02 체결) 그 사이 «자리 9/10» 으로 338840 주문이 추가 접수돼 두 체결 뒤 보유 11/10.
페이퍼는 가상 체결이 즉시(BUY_PENDING→POSITIONED 동기 전이)라 발생 0.

수정: 엔진(TradingContext)이 아는 «이 전략 소유 BUY_PENDING 종목» 을 전략에 꽂아 주는 얇은 훅
`BaseStrategy.pending_buy_codes_provider` 를 두고, dt 자리 검사·`[on_tick]` 자리 표시가
«체결 + (positions 에 없는) 미체결» 을 같은 값으로 센다. 상태의 진실은 엔진이라 취소·타임아웃
(BUY_PENDING → SELECTED/COMPLETED) 때 자리가 저절로 풀린다.

이 파일이 단언하는 것:
  ① 체결 9 + 미체결 1 = 자리 꽉 참(매수 신호 None + `[캡] 사유=max_positions`)
  ② 미체결이 취소/타임아웃으로 사라지면 다시 열린다
  ③ 미체결이 체결되면 positions 로 옮겨 가 이중 계산 안 됨(9+1 → 10+0 · 8+1 → 9+0 은 열림)
  ④ 훅 미주입(기본)·훅 예외 = 기존 동작 그대로(페이퍼·기존 테스트 회귀 0)
  ⑤ 엔진 쪽: TradingContext 는 «자기 소유»(폴더키·클래스명 둘 다) BUY_PENDING 만 돌려준다
  ⑥ 배선: main.ctx_for_strategy 가 전략에 훅을 꽂는다
  ⑦ `[on_tick]` 자리 표시 = 검사와 같은 값(체결+미체결) · 미체결 있을 때만 꼬리 `| 미체결매수 m`

⚠️ logger 는 propagate=False 라 caplog 로 안 잡힌다 — Mock 로거를 꽂아 호출을 직접 본다.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
import pandas as pd

from core.models import StockState
from strategies.base import OrderInfo
from strategies.daytrading_3methods_breakout.strategy import (
    DayTrading3MethodsBreakoutStrategy,
)

K = 10
HELD = [f"0000{i:02d}" for i in range(1, 10)]  # 9종목 체결 보유
PENDING_CODE = "338840"
NEW_CODE = "005930"
BUY_SIGNAL = object()  # _check_buy 도달 표지


def _make(provider=None):
    s = DayTrading3MethodsBreakoutStrategy(
        {"paper_trading": False, "risk_management": {"max_positions": K}}
    )
    assert s.on_init(None, None, None)
    s.logger = Mock()
    s._check_buy = Mock(return_value=BUY_SIGNAL)
    if provider is not None:
        s.pending_buy_codes_provider = provider
    return s


def _hold(s, codes):
    for c in codes:
        s.positions[c] = {"quantity": 1, "entry_price": 10000.0, "entry_time": None}


def _daily(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    flat = np.full(n, 10000.0)
    return pd.DataFrame(
        {"datetime": idx, "open": flat, "high": flat, "low": flat,
         "close": flat, "volume": np.full(n, 100000.0)}
    )


def _cap_lines(s) -> list:
    return [
        c.args[0] for c in s.logger.info.call_args_list
        if c.args and isinstance(c.args[0], str) and c.args[0].startswith("[캡]")
    ]


def _buy_fill(code: str) -> OrderInfo:
    return OrderInfo(order_id="O1", stock_code=code, side="buy", quantity=1,
                     price=10000.0, filled_at=datetime(2026, 10, 27, 9, 20))


# ① 체결 9 + 미체결 1 → 꽉 참 ---------------------------------------------------

def test_held9_plus_pending1_is_full():
    pending = [PENDING_CODE]
    s = _make(lambda: list(pending))
    _hold(s, HELD)

    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is None
    s._check_buy.assert_not_called()
    lines = _cap_lines(s)
    assert len(lines) == 1, lines
    assert "사유=max_positions" in lines[0]
    # 기존 파서 호환: «보유=n/K» 는 체결 수 그대로 · 미체결은 꼬리 필드로 따로
    assert "보유=9/10 " in lines[0]
    assert lines[0].endswith("미체결매수=1")


# ② 취소/타임아웃으로 BUY_PENDING 이 사라지면 다시 열림 ---------------------------

def test_pending_cancelled_reopens_slot():
    pending = [PENDING_CODE]
    s = _make(lambda: list(pending))
    _hold(s, HELD)
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is None

    pending.clear()  # 엔진: 타임아웃 복구 BUY_PENDING → SELECTED/COMPLETED
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is BUY_SIGNAL
    s._check_buy.assert_called_once()


# ③ 체결되면 positions 로 이동 — 이중 계산 0 -------------------------------------

def test_pending_filled_not_double_counted_9_plus_1_to_10_plus_0():
    pending = [PENDING_CODE]  # 체결 콜백 순간 엔진 상태가 아직 BUY_PENDING 이어도
    s = _make(lambda: list(pending))
    _hold(s, HELD)
    assert s._pending_buy_count() == 1

    s.on_order_filled(_buy_fill(PENDING_CODE))
    assert len(s.positions) == 10
    assert s._pending_buy_count() == 0  # positions 에 있는 코드는 미체결로 안 셈
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is None


def test_pending_filled_8_plus_1_to_9_plus_0_stays_open():
    pending = [PENDING_CODE]
    s = _make(lambda: list(pending))
    _hold(s, HELD[:8])
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is BUY_SIGNAL  # 8+1=9 <10

    s.on_order_filled(_buy_fill(PENDING_CODE))  # 상태가 늦게 바뀌어도 9+0 = 9
    assert s.generate_signal("000777", _daily(), timeframe="daily") is BUY_SIGNAL


def test_held_code_pending_duplicate_not_counted_twice():
    """같은 종목이 positions 와 BUY_PENDING 양쪽에 보여도 한 자리."""
    s = _make(lambda: [HELD[0]])
    _hold(s, HELD)
    assert s._pending_buy_count() == 0
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is BUY_SIGNAL


# ④ 훅 미주입·예외 = 기존 동작 ----------------------------------------------------

def test_no_provider_keeps_legacy_behavior():
    s = _make()
    assert s.pending_buy_codes_provider is None
    assert s._pending_buy_count() == 0
    _hold(s, HELD)
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is BUY_SIGNAL

    _hold(s, ["000099"])
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is None
    lines = _cap_lines(s)
    assert lines == [
        f"[캡] daytrading_3methods_breakout {NEW_CODE} 평가 스킵 사유=max_positions "
        f"보유=10/10 일일매수=0/{s._max_daily_trades} 경로=루프밖"
    ], lines


def test_provider_exception_falls_back_to_legacy():
    def boom():
        raise RuntimeError("state manager gone")

    s = _make(boom)
    _hold(s, HELD)
    assert s._pending_buy_count() == 0
    assert s.generate_signal(NEW_CODE, _daily(), timeframe="daily") is BUY_SIGNAL


# ⑤ 엔진 쪽 조회 — 자기 소유 BUY_PENDING 만 ---------------------------------------

def test_trading_context_returns_only_own_buy_pending():
    from core.trading_context import TradingContext

    strat = SimpleNamespace(name="DayTrading3MethodsBreakoutStrategy")
    by_state = {
        StockState.BUY_PENDING: [
            SimpleNamespace(stock_code="111111", owner_strategy_name="daytrading_3methods_breakout"),
            SimpleNamespace(stock_code="222222", owner_strategy_name="DayTrading3MethodsBreakoutStrategy"),
            SimpleNamespace(stock_code="333333", owner_strategy_name="RSLeaderStrategy"),
            SimpleNamespace(stock_code="444444", owner_strategy_name=""),
        ],
        StockState.POSITIONED: [
            SimpleNamespace(stock_code="555555", owner_strategy_name="DayTrading3MethodsBreakoutStrategy"),
        ],
    }
    tm = Mock()
    tm.get_stocks_by_state.side_effect = lambda st: list(by_state.get(st, []))
    ctx = TradingContext(
        trading_manager=tm, decision_engine=Mock(), fund_manager=Mock(),
        data_collector=Mock(), intraday_manager=Mock(), trading_analyzer=Mock(),
        db_manager=Mock(), strategy_name="daytrading_3methods_breakout",
        strategies_dict={"daytrading_3methods_breakout": strat},
    )
    assert sorted(ctx.get_own_buy_pending_codes()) == ["111111", "222222"]


# ⑥ 배선 — main.ctx_for_strategy 가 훅을 꽂는다 -----------------------------------

def test_ctx_for_strategy_wires_provider():
    from main import DayTradingBot

    s = _make()
    fake_ctx = Mock()
    fake_ctx.get_own_buy_pending_codes = Mock(return_value=[PENDING_CODE])
    bot = SimpleNamespace(strategies={"daytrading_3methods_breakout": s})
    bot._create_trading_context = lambda strategy_name="": fake_ctx

    assert DayTradingBot.ctx_for_strategy(bot, "daytrading_3methods_breakout") is fake_ctx
    assert s.pending_buy_codes_provider is fake_ctx.get_own_buy_pending_codes
    assert s._pending_buy_count() == 1


# ⑦ [on_tick] 자리 표시 = 검사와 같은 값 -----------------------------------------

def _summary_line(s) -> str:
    lines = [
        c.args[0] for c in s.logger.info.call_args_list
        if c.args and isinstance(c.args[0], str) and c.args[0].startswith("[on_tick] 매수검토")
    ]
    assert len(lines) == 1, lines
    return lines[0]


async def _run_empty_tick(s):
    ctx = Mock()
    ctx.get_selected_stocks = Mock(return_value=[])
    ctx.get_positions = Mock(return_value=[])
    ctx.get_daily_data = AsyncMock(return_value=None)
    ctx.tracer = None
    await s.on_tick(ctx)


async def test_ontick_summary_counts_pending():
    s = _make(lambda: [PENDING_CODE])
    _hold(s, HELD)
    await _run_empty_tick(s)
    line = _summary_line(s)
    assert "자리 10/10·일일 0/5 |" in line
    assert line.endswith("| 미체결매수 1")


async def test_ontick_summary_unchanged_without_pending():
    s = _make(lambda: [])
    _hold(s, HELD)
    await _run_empty_tick(s)
    assert _summary_line(s) == (
        "[on_tick] 매수검토 0종목(스킵 0), 신호 0건 | 자리 9/10·일일 0/5 | "
        "매도검토 0종목, 신호 0건"
    )
