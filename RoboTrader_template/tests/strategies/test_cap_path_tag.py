"""D-1 게이트 관측 번들 ③(경로 태그) + 불변 I1·I2·I4.

사전등록: docs/prereg_2026-09-24_gate_observability_bundle.md §2-③ · §3 · §4-1.

③ `[캡]` 줄 끝에 `경로={매수루프|매도루프|루프밖}` — on_tick 이 generate_signal 호출 전후로
   `_eval_path` 를 세우고 finally 로 None 복구한다.
불변: 반환값(I1) · 상태·data(I2) · ctx.buy/ctx.sell 호출(I4) 는 계기 유무와 무관하게 같다.

⚠️ logger 는 `propagate = False` 라 caplog 로 안 잡힌다 — Mock 로거로 호출을 직접 본다
   (tests/strategies/test_cap_skip_log.py 와 같은 관례).

⑤(캡 shadow)·I1/I4/I7 테스트는 tests/strategies/test_cap_shadow.py 로 분리했다
(2026-09-24 사전등록 번들 커밋 분할 — 원본 test_cap_path_and_shadow.py 는 삭제).
"""
from unittest.mock import AsyncMock, MagicMock, Mock

import pandas as pd
import pytest

from strategies.book_pullback_ma20.strategy import BookPullbackMa20Strategy
from strategies.daytrading_3methods_breakout.strategy import (
    DayTrading3MethodsBreakoutStrategy,
)
from strategies.minervini_volume_dryup.strategy import MinerviniVolumeDryupStrategy

FOCUS = [
    (BookPullbackMa20Strategy, "book_pullback_ma20"),
    (MinerviniVolumeDryupStrategy, "minervini_volume_dryup"),
    (DayTrading3MethodsBreakoutStrategy, "daytrading_3methods_breakout"),
]


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


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _make(cls):
    s = cls({"paper_trading": True})
    s.on_init(None, None, None)
    s.logger = Mock()
    return s


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


# ── ③ 경로 태그 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("cls,key", FOCUS)
async def test_buy_and_sell_loop_tags(cls, key):
    """같은 (종목, 사유)가 매수루프·매도루프 둘 다에서 막히면 줄이 경로별로 1개씩."""
    s = _make(cls)
    _fill(s, "daily_trades")
    d = s._max_daily_trades
    k = s._max_positions
    frames = {"005930": _flat_daily(), "000660": _flat_daily()}
    # 매도루프는 «남의» 보유종목(000660)까지 돈다 — 자기 보유가 아니면 매수 분기로 떨어진다.
    ctx = _ctx(selected=["005930", "000660"], held=["000660"], frames=frames)

    await s.on_tick(ctx)

    assert _info_lines(s, "[캡]") == [
        f"[캡] {key} 005930 평가 스킵 사유=daily_trades 보유=0/{k} 일일매수={d}/{d} 경로=매수루프",
        f"[캡] {key} 000660 평가 스킵 사유=daily_trades 보유=0/{k} 일일매수={d}/{d} 경로=매수루프",
        f"[캡] {key} 000660 평가 스킵 사유=daily_trades 보유=0/{k} 일일매수={d}/{d} 경로=매도루프",
    ]
    assert s._eval_path is None
    ctx.buy.assert_not_called()
    ctx.sell.assert_not_called()


@pytest.mark.parametrize("cls,key", FOCUS)
def test_direct_call_is_outside_loop(cls, key):
    """on_tick 밖 호출(position_monitor 등) = 경로=루프밖."""
    s = _make(cls)
    assert s._eval_path is None
    assert s.generate_signal("005930", _flat_daily(), timeframe="intraday") is None
    (line,) = _info_lines(s, "[캡]")
    assert line.endswith(" 경로=루프밖")


@pytest.mark.asyncio
@pytest.mark.parametrize("loop", ["buy", "sell"])
async def test_eval_path_reset_after_generate_signal_raises(loop):
    """generate_signal 이 예외를 던져도 finally 로 None 복구 — 예외는 그대로 전파(거동 불변)."""
    s = _make(BookPullbackMa20Strategy)
    s.generate_signal = Mock(side_effect=RuntimeError("boom"))
    frames = {"005930": _flat_daily()}
    ctx = _ctx(selected=["005930"] if loop == "buy" else [],
               held=["005930"] if loop == "sell" else [], frames=frames)
    with pytest.raises(RuntimeError):
        await s.on_tick(ctx)
    assert s._eval_path is None


@pytest.mark.asyncio
async def test_eval_path_seen_inside_generate_signal():
    """호출 «중»에만 태그가 서 있다 — 매수루프 → 매도루프 순서."""
    s = _make(BookPullbackMa20Strategy)
    seen = []
    s.generate_signal = lambda code, data, timeframe="daily": seen.append((code, s._eval_path))
    ctx = _ctx(selected=["005930"], held=["000660"],
               frames={"005930": _flat_daily(), "000660": _flat_daily()})
    await s.on_tick(ctx)
    assert seen == [("005930", "매수루프"), ("000660", "매도루프")]
    assert s._eval_path is None


def test_new_cap_line_still_parsed_by_research_scanners():
    """끝에 붙인 `경로=` 가 기존 비앵커 파서(logscan8 · cap_skip_ledger)의 그룹 값을 안 바꾼다."""
    from backtest.concept_axes.ledger8 import logscan8 as L
    from backtest.concept_axes.minervini.cap_skip_ledger import logscan as C

    old = "[캡] minervini_volume_dryup 005930 평가 스킵 사유=max_positions 보유=6/6 일일매수=2/5"
    new = old + " 경로=매수루프"
    assert L.RE_CAP.search(new).groups() == L.RE_CAP.search(old).groups()
    assert C.RE_CAP.search(new).groups() == C.RE_CAP.search(old).groups()
