"""D-1 게이트 관측 번들 ⑤(캡 shadow) + 불변 I1·I4·I7.

사전등록: docs/prereg_2026-09-24_gate_observability_bundle.md §2-⑤ · §3 · §4-1.

⑤ 캡(daily_trades·max_positions)에 막힌 «매수루프» 후보의 진입 룰을 평가만 해
   `[shadow] … 룰=참|거짓|오류` 한 줄 — (종목, 사유) 거래일당 1회 · 예외 전파 0.
불변: 반환값(I1) · 상태·data(I2) · ctx.buy/ctx.sell 호출(I4) · 대조군 5전략 무접촉(I7)
는 계기 유무와 무관하게 같다.

⚠️ logger 는 `propagate = False` 라 caplog 로 안 잡힌다 — Mock 로거로 호출을 직접 본다
   (tests/strategies/test_cap_skip_log.py 와 같은 관례).

③(경로 태그) 테스트는 tests/strategies/test_cap_path_tag.py 로 분리했다
(2026-09-24 사전등록 번들 커밋 분할 — 원본 test_cap_path_and_shadow.py 는 삭제).
"""
import copy
import importlib
import inspect
from datetime import date
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import pandas as pd
import pytest

from config.market_hours import MarketHours
from strategies.base import Signal, SignalType
from strategies.book_pullback_ma20.strategy import BookPullbackMa20Strategy
from strategies.books.haru_silijeon.rules_daily import _ma
from strategies.daytrading_3methods_breakout.strategy import (
    DayTrading3MethodsBreakoutStrategy,
)
from strategies.minervini_volume_dryup.strategy import MinerviniVolumeDryupStrategy

FOCUS = [
    (BookPullbackMa20Strategy, "book_pullback_ma20"),
    (MinerviniVolumeDryupStrategy, "minervini_volume_dryup"),
    (DayTrading3MethodsBreakoutStrategy, "daytrading_3methods_breakout"),
]
ALL8 = {
    "elder_ema_pullback": "ElderEmaPullbackStrategy",
    "book_pullback_ma5": "BookPullbackMa5Strategy",
    "rs_leader": "RSLeaderStrategy",
    "deep_mr_dev20": "DeepMrDev20Strategy",
    "book_envelope_200d": "BookEnvelope200dStrategy",
    "book_pullback_ma20": "BookPullbackMa20Strategy",
    "minervini_volume_dryup": "MinerviniVolumeDryupStrategy",
    "daytrading_3methods_breakout": "DayTrading3MethodsBreakoutStrategy",
}
CONTROL5 = ("elder_ema_pullback", "book_pullback_ma5", "rs_leader",
            "deep_mr_dev20", "book_envelope_200d")


# ── 결정론적 일봉 픽스처 ─────────────────────────────────────────────────────

def _frame(closes, highs=None, lows=None, opens=None, volumes=None):
    closes = list(closes)
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2025-01-01", periods=n, freq="D"),
        "open": list(opens) if opens is not None else list(closes),
        "high": list(highs) if highs is not None else [c * 1.01 for c in closes],
        "low": list(lows) if lows is not None else [c * 0.99 for c in closes],
        "close": closes,
        "volume": list(volumes) if volumes is not None else [1_000_000] * n,
    })


def _flat_daily(n: int = 120) -> pd.DataFrame:
    """평평한 일봉 — 세 진입 룰 어느 것도 만족하지 않는다."""
    return _frame([10000.0] * n, highs=[10000.0] * n, lows=[10000.0] * n,
                  volumes=[100000.0] * n)


def _ma20_trigger() -> pd.DataFrame:
    """급등 후 20일선 눌림 지지 양봉 (test_book_pullback_ma20_consistency.py 와 같은 형태)."""
    closes = ([10000.0] * 8 + list(np.linspace(10000, 15000, 8))
              + list(np.linspace(15000, 11800, 33)))
    df = _frame(closes)
    ma20 = _ma(df, 20)
    df.loc[df.index[-1], "low"] = ma20 * 1.005
    df.loc[df.index[-1], "open"] = ma20 * 1.005
    df.loc[df.index[-1], "close"] = ma20 * 1.025
    df.loc[df.index[-1], "high"] = ma20 * 1.03
    return df


def _minervini_trigger() -> pd.DataFrame:
    """최근 10봉 거래량 dry-up (test_minervini_volume_dryup_consistency.py 와 같은 형태)."""
    return _frame(list(np.linspace(10000, 12000, 40)),
                  volumes=[1_000_000] * 30 + [400_000] * 10)


def _daytrading_trigger() -> pd.DataFrame:
    """전고점 돌파 + 거래량 폭증 양봉 (test_daytrading_3methods_breakout.py 와 같은 형태)."""
    closes = [10000.0 + (i % 5) * 20 for i in range(26)]
    closes[-1] = 10600.0
    df = _frame(closes)
    df.loc[df.index[-1], "open"] = 10200.0
    df.loc[df.index[-1], "close"] = 10600.0
    df.loc[df.index[-1], "high"] = 10650.0
    df.loc[df.index[-1], "low"] = 10180.0
    df.loc[df.index[-1], "volume"] = 5_000_000
    return df


TRIGGER = {
    "book_pullback_ma20": _ma20_trigger,
    "minervini_volume_dryup": _minervini_trigger,
    "daytrading_3methods_breakout": _daytrading_trigger,
}


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _make(cls):
    s = cls({"paper_trading": True})
    s.on_init(None, None, None)
    s.logger = Mock()
    return s


def _make8(folder):
    mod = importlib.import_module(f"strategies.{folder}.strategy")
    return _make(getattr(mod, ALL8[folder]))


def _info_lines(strategy, prefix):
    return [
        c.args[0] for c in strategy.logger.info.call_args_list
        if c.args and isinstance(c.args[0], str) and c.args[0].startswith(prefix)
    ]


def _fill(strategy, cap):
    if cap == "daily_trades":
        strategy.daily_trades = strategy._max_daily_trades
    else:
        strategy.positions = {
            f"9000{i:02d}": {"quantity": 1} for i in range(strategy._max_positions)}


def _stock(code):
    st = MagicMock()
    st.stock_code = code
    return st


def _ctx(selected, held, frames):
    """on_tick 이 쓰는 TradingContext 최소 모의. frames: code → 일봉."""
    ctx = MagicMock()
    ctx.tracer = None
    ctx.get_selected_stocks.return_value = [_stock(c) for c in selected]
    ctx.get_positions.return_value = [_stock(c) for c in held]

    async def _daily(code, days=60):
        return frames.get(code)

    async def _intraday(code):
        return None

    ctx.get_daily_data = _daily
    ctx.get_intraday_data = _intraday
    ctx.buy = AsyncMock(return_value=None)
    ctx.sell = AsyncMock(return_value=None)
    return ctx


def _stub_instruments(strategy):
    """계기 없는 «대조» 실행 — 두 계기를 인스턴스에서 no-op 으로 덮는다."""
    strategy._log_cap_skip = lambda *a, **k: None
    strategy._log_cap_shadow = lambda *a, **k: None


def _state(strategy):
    return copy.deepcopy((strategy.positions, strategy.daily_trades,
                          strategy._max_positions, strategy._max_daily_trades))


# ── ⑤ shadow ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("cls,key", FOCUS)
async def test_shadow_only_for_buy_loop_candidates(cls, key):
    """같은 (종목, 사유)가 매수·매도 루프 둘 다에서 막혀도 shadow 는 매수루프 두 후보만."""
    s = _make(cls)
    _fill(s, "daily_trades")
    frames = {"005930": _flat_daily(), "000660": _flat_daily()}
    # 매도루프는 «남의» 보유종목(000660)까지 돈다 — 자기 보유가 아니면 매수 분기로 떨어진다.
    ctx = _ctx(selected=["005930", "000660"], held=["000660"], frames=frames)

    await s.on_tick(ctx)

    assert [x.split(" 캡사유=")[0] for x in _info_lines(s, "[shadow]")] == [
        f"[shadow] {key} 005930", f"[shadow] {key} 000660"]


@pytest.mark.parametrize("cls,key", FOCUS)
@pytest.mark.parametrize("cap", ["daily_trades", "max_positions"])
@pytest.mark.parametrize("kind", ["trigger", "flat"])
def test_shadow_verdict_equals_check_buy_when_cap_lifted(cls, key, cap, kind):
    """🔑 동치 — 같은 data 로 캡을 풀었을 때 `_check_buy` 가 BUY ⇔ shadow `룰=참`."""
    data = TRIGGER[key]() if kind == "trigger" else _flat_daily()
    with patch.object(MarketHours, "is_market_open", return_value=True):
        free = _make(cls)
        expected = free._check_buy("005930", data)

        s = _make(cls)
        _fill(s, cap)
        s._eval_path = "매수루프"          # on_tick 매수루프 안과 같은 상태
        assert s.generate_signal("005930", data, timeframe="daily") is None

    is_buy = expected is not None and expected.signal_type == SignalType.BUY
    assert is_buy is (kind == "trigger"), "픽스처가 의도대로 참/거짓이어야 동치 검사가 의미 있다"
    (line,) = _info_lines(s, "[shadow]")
    n, k = len(s.positions), s._max_positions
    d, dd = s.daily_trades, s._max_daily_trades
    head = (f"[shadow] {key} 005930 캡사유={cap} 룰={'참' if is_buy else '거짓'} "
            f"보유={n}/{k} 일일매수={d}/{dd}")
    if is_buy:
        assert line == head + " | " + ", ".join(expected.reasons)
    else:
        assert line == head


@pytest.mark.parametrize("cls,key", FOCUS)
@pytest.mark.parametrize("cap", ["daily_trades", "max_positions"])
def test_shadow_state_and_data_untouched(cls, key, cap):
    """I2 — positions·daily_trades·K·D·data 불변 · Signal 도 🧾 줄도 없다."""
    data = TRIGGER[key]()
    before_data = data.copy(deep=True)
    s = _make(cls)
    _fill(s, cap)
    before = _state(s)
    s._eval_path = "매수루프"
    with patch.object(MarketHours, "is_market_open", return_value=True):
        assert s.generate_signal("005930", data, timeframe="daily") is None
    assert _state(s) == before
    pd.testing.assert_frame_equal(data, before_data)
    assert len(_info_lines(s, "[shadow]")) == 1
    assert not any("매수 시그널" in str(c.args[0])
                   for c in s.logger.info.call_args_list if c.args)


@pytest.mark.parametrize("cls,key", FOCUS)
@pytest.mark.parametrize("path", [None, "매도루프"])
def test_no_shadow_outside_buy_loop(cls, key, path):
    """매도루프·루프밖에서는 shadow 0줄 (`[캡]` 은 그대로 찍힌다)."""
    s = _make(cls)
    _fill(s, "max_positions")
    s._eval_path = path
    assert s.generate_signal("005930", TRIGGER[key](), timeframe="daily") is None
    assert _info_lines(s, "[shadow]") == []
    assert len(_info_lines(s, "[캡]")) == 1


@pytest.mark.parametrize("cls,key", FOCUS)
def test_shadow_once_per_stock_reason_per_day(cls, key):
    """(종목, 사유) 거래일당 1회 — 표지를 평가 «전»에 찍어 반복 평가도 0."""
    s = _make(cls)
    _fill(s, "daily_trades")
    s._eval_path = "매수루프"
    data = _flat_daily()
    calls = []
    real = s.evaluate_entry

    def _counting(*a, **kw):
        calls.append(1)
        return real(*a, **kw)

    s.evaluate_entry = _counting

    for _ in range(50):
        s.generate_signal("005930", data, timeframe="daily")
    assert len(_info_lines(s, "[shadow]")) == 1
    assert len(calls) == 1

    s.generate_signal("035720", data, timeframe="daily")        # 다른 종목 = 별도 1회
    assert len(_info_lines(s, "[shadow]")) == 2

    s.daily_trades = 0                                          # 같은 종목 · 다른 사유 = 별도 1회
    _fill(s, "max_positions")
    s.generate_signal("005930", data, timeframe="daily")
    assert len(_info_lines(s, "[shadow]")) == 3

    s._cap_shadow_log_date = date(2000, 1, 1)                   # 다음 거래일 = 억제 해제
    s.generate_signal("005930", data, timeframe="daily")
    assert len(_info_lines(s, "[shadow]")) == 4


@pytest.mark.parametrize("cls,key", FOCUS)
def test_shadow_rule_exception_logs_error_and_never_escapes(cls, key):
    s = _make(cls)
    _fill(s, "max_positions")
    s._eval_path = "매수루프"
    s.evaluate_entry = Mock(side_effect=RuntimeError("rule boom"))
    assert s.generate_signal("005930", _flat_daily(), timeframe="daily") is None
    (line,) = _info_lines(s, "[shadow]")
    assert " 룰=오류 " in line and "|" not in line


@pytest.mark.parametrize("cls,key", FOCUS)
def test_shadow_logger_exception_never_escapes(cls, key):
    s = _make(cls)
    _fill(s, "daily_trades")
    s._eval_path = "매수루프"

    def _info(msg, *a, **kw):
        if str(msg).startswith("[shadow]"):
            raise RuntimeError("log boom")

    s.logger.info = Mock(side_effect=_info)
    assert s.generate_signal("005930", _flat_daily(), timeframe="daily") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,key", FOCUS)
async def test_raising_rule_does_not_abort_on_tick(cls, key):
    """룰 예외가 on_tick 을 끊지 않는다 — 두 후보 모두 평가되고 요약줄까지 간다."""
    s = _make(cls)
    _fill(s, "max_positions")
    s.evaluate_entry = Mock(side_effect=RuntimeError("rule boom"))
    ctx = _ctx(selected=["005930", "035720"], held=[],
               frames={"005930": _flat_daily(), "035720": _flat_daily()})
    await s.on_tick(ctx)
    shadows = _info_lines(s, "[shadow]")
    assert len(shadows) == 2 and all(" 룰=오류 " in x for x in shadows)
    assert len(_info_lines(s, "[on_tick] 매수검토")) == 1
    ctx.buy.assert_not_called()
    assert s._eval_path is None


# ── I1 반환값 · I2 상태 (8전략) ──────────────────────────────────────────────

GATE_STATES = ["free", "daily_trades", "max_positions", "held", "intraday"]


@pytest.mark.parametrize("folder", list(ALL8))
@pytest.mark.parametrize("state", GATE_STATES)
def test_generate_signal_return_invariant_under_instruments(folder, state):
    """I1 — 경로 태그 3종 × 계기 on/off 에서 generate_signal 반환이 같다(8전략 · 게이트 상태 5)."""
    buy_sentinel = Signal(signal_type=SignalType.BUY, stock_code="005930", reasons=["buy"])
    sell_sentinel = Signal(signal_type=SignalType.SELL, stock_code="005930", reasons=["sell"])
    data = _flat_daily(260)
    results = []
    for path in (None, "매수루프", "매도루프", "stub"):
        s = _make8(folder)
        s._check_buy = Mock(return_value=buy_sentinel)
        s._check_sell = Mock(return_value=sell_sentinel)
        if state in ("daily_trades", "max_positions"):
            _fill(s, state)
        elif state == "held":
            s.positions = {"005930": {"quantity": 1, "entry_price": 10000.0}}
        if path == "stub":
            _stub_instruments(s)
        else:
            s._eval_path = path
        before = _state(s)
        before_data = data.copy(deep=True)
        tf = "intraday" if state == "intraday" else "daily"
        results.append(s.generate_signal("005930", data, timeframe=tf))
        assert _state(s) == before                                   # I2
        pd.testing.assert_frame_equal(data, before_data)            # I2 data
    assert all(r is results[0] for r in results), (folder, state, results)


@pytest.mark.parametrize("folder", CONTROL5)
def test_control_strategies_have_no_shadow_hook(folder):
    """I7 가드 — 대조군 5전략 소스에 shadow 계기가 없다(P5 창 · §0-5)."""
    src = inspect.getsource(importlib.import_module(f"strategies.{folder}.strategy"))
    assert "_log_cap_shadow" not in src and "_eval_path" not in src


# ── I4 주문 (ctx.buy / ctx.sell) ─────────────────────────────────────────────

async def _orders(cls, key, *, cap, stub):
    s = _make(cls)
    s.positions = {"000660": {"quantity": 1, "entry_price": 10000.0}}
    if cap == "daily_trades":
        s.daily_trades = s._max_daily_trades
    elif cap == "max_positions":
        s.positions.update(
            {f"9000{i:02d}": {"quantity": 1} for i in range(s._max_positions - 1)})
    s._check_sell = Mock(return_value=Signal(
        signal_type=SignalType.SELL, stock_code="000660", reasons=["exit"]))
    if stub:
        _stub_instruments(s)
    frames = {"005930": TRIGGER[key](), "035720": _flat_daily(), "000660": _flat_daily(),
              "123456": _flat_daily()}
    ctx = _ctx(selected=["005930", "035720"], held=["000660", "123456"], frames=frames)
    with patch.object(MarketHours, "is_market_open", return_value=True):
        await s.on_tick(ctx)
    return ctx.buy.call_args_list, ctx.sell.call_args_list


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,key", FOCUS)
@pytest.mark.parametrize("cap", [None, "daily_trades", "max_positions"])
async def test_orders_identical_with_and_without_instruments(cls, key, cap):
    """I4 — ctx.buy/ctx.sell 호출 순서·인자가 계기 on/off 에서 같다."""
    buys, sells = await _orders(cls, key, cap=cap, stub=False)
    buys0, sells0 = await _orders(cls, key, cap=cap, stub=True)
    assert buys == buys0 and sells == sells0
    assert len(sells) == 1 and sells[0].args == ("000660",)
    if cap is None:
        # 캡이 비면 트리거 후보(005930)만 산다 — 매도루프의 남의 보유(123456)는 평평해 신호 없음.
        assert [c.args for c in buys] == [("005930",)]
    else:
        assert buys == []
