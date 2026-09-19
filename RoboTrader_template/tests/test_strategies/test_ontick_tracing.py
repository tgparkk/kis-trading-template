"""
on_tick 루프 TickTracer 계측 테스트
====================================

TDD: 실패 먼저 작성 → 구현 → PASS 확인

테스트 대상:
  - on_tick이 각 스킵 지점에서 tracer.emit()을 호출하는지
  - tracer=None이면 기존 동작 보존 (no-op)
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from strategies.base import BaseStrategy, Signal, SignalType
from utils.tick_tracer import TickTracer


# ============================================================================
# Minimal concrete strategy for testing
# ============================================================================

class _TestStrategy(BaseStrategy):
    """generate_signal을 주입 가능한 최소 전략."""

    name = "TestStrategy"
    version = "1.0.0"

    def __init__(self, signal_to_return: Optional[Signal] = None):
        super().__init__({})
        self._signal_to_return = signal_to_return

    def generate_signal(self, stock_code, data, timeframe="daily"):
        return self._signal_to_return


# ============================================================================
# Helper: minimal TradingContext mock
# ============================================================================

def _make_ctx(daily_data=None, positions=None, tracer=None):
    """on_tick이 사용하는 TradingContext 최소 모의 객체 생성."""
    import logging

    ctx = MagicMock()
    ctx.tracer = tracer

    # get_selected_stocks: stock_code 속성을 가진 객체 목록 반환
    stock = MagicMock()
    stock.stock_code = "005930"
    ctx.get_selected_stocks.return_value = [stock]

    # get_positions: 빈 목록 (매수 신호 테스트에서는 포지션 불필요)
    ctx.get_positions.return_value = positions or []

    # get_daily_data: AsyncMock
    async def _get_daily(code, days=60):
        return daily_data

    ctx.get_daily_data = _get_daily

    # get_intraday_data: AsyncMock, always returns None
    async def _get_intraday(code):
        return None

    ctx.get_intraday_data = _get_intraday

    # buy: AsyncMock
    ctx.buy = AsyncMock(return_value="005930")

    # logger: 실제 logger를 사용 (혹은 silent mock)
    ctx.logger = logging.getLogger("test_ctx")

    return ctx


def _make_daily_data(n: int) -> pd.DataFrame:
    """n개 일봉 DataFrame 생성."""
    return pd.DataFrame(
        {"close": [50000 + i * 100 for i in range(n)]},
        index=range(n),
    )


# ============================================================================
# Test 1: no_daily_data 스킵 이벤트
# ============================================================================

class TestOnTickEmitsSkipNoDailyData:
    """일봉 데이터가 None이면 skipped/no_daily_data 이벤트 기록."""

    @pytest.mark.asyncio
    async def test_ontick_emits_skip_no_daily_data(self, tmp_path):
        """
        Given: daily_data=None, tracer with tmp dir
        When: await strategy.on_tick(ctx)
        Then: JSONL에 event_type="skipped", skip_reason="no_daily_data", stock_code="005930"
        """
        tracer = TickTracer(base_dir=tmp_path / "tick_trace")
        strategy = _TestStrategy()
        ctx = _make_ctx(daily_data=None, tracer=tracer)

        await strategy.on_tick(ctx)

        # JSONL 파일 읽기
        from datetime import date
        out_file = tmp_path / "tick_trace" / f"{date.today().isoformat()}.jsonl"
        assert out_file.exists(), "JSONL 파일이 생성되지 않음"

        events = [json.loads(line) for line in out_file.read_text("utf-8").strip().splitlines()]
        skip_events = [e for e in events if e.get("event_type") == "skipped"]
        assert len(skip_events) >= 1, f"skipped 이벤트 없음: {events}"

        ev = skip_events[0]
        assert ev["skip_reason"] == "no_daily_data", f"skip_reason 불일치: {ev}"
        assert ev["stock_code"] == "005930", f"stock_code 불일치: {ev}"


# ============================================================================
# Test 2: insufficient_data 스킵 이벤트
# ============================================================================

class TestOnTickEmitsSkipInsufficientData:
    """일봉 데이터 수 < min_len이면 skipped/insufficient_data 이벤트 기록."""

    @pytest.mark.asyncio
    async def test_ontick_emits_skip_insufficient_data(self, tmp_path):
        """
        Given: daily_data with 10 rows (< default min_len=20), tracer
        When: await strategy.on_tick(ctx)
        Then: JSONL에 event_type="skipped", skip_reason="insufficient_data"
        """
        tracer = TickTracer(base_dir=tmp_path / "tick_trace")
        strategy = _TestStrategy()
        ctx = _make_ctx(daily_data=_make_daily_data(10), tracer=tracer)

        await strategy.on_tick(ctx)

        from datetime import date
        out_file = tmp_path / "tick_trace" / f"{date.today().isoformat()}.jsonl"
        assert out_file.exists(), "JSONL 파일이 생성되지 않음"

        events = [json.loads(line) for line in out_file.read_text("utf-8").strip().splitlines()]
        skip_events = [
            e for e in events
            if e.get("event_type") == "skipped" and e.get("skip_reason") == "insufficient_data"
        ]
        assert len(skip_events) >= 1, f"insufficient_data 이벤트 없음: {events}"
        assert skip_events[0]["stock_code"] == "005930"


# ============================================================================
# Test 3: evaluated 이벤트 (generate_signal → None)
# ============================================================================

class TestOnTickEmitsEvaluatedWithNoSignal:
    """일봉 충분 + generate_signal=None → evaluated 이벤트 기록."""

    @pytest.mark.asyncio
    async def test_ontick_emits_evaluated_with_indicators(self, tmp_path):
        """
        Given: 22개 일봉, generate_signal returns None, tracer
        When: await strategy.on_tick(ctx)
        Then: JSONL에 event_type="evaluated", signal_type=None (또는 없음)
        """
        tracer = TickTracer(base_dir=tmp_path / "tick_trace")
        # generate_signal → None 반환 전략
        strategy = _TestStrategy(signal_to_return=None)
        ctx = _make_ctx(daily_data=_make_daily_data(25), tracer=tracer)

        await strategy.on_tick(ctx)

        from datetime import date
        out_file = tmp_path / "tick_trace" / f"{date.today().isoformat()}.jsonl"
        assert out_file.exists(), "JSONL 파일이 생성되지 않음"

        events = [json.loads(line) for line in out_file.read_text("utf-8").strip().splitlines()]
        eval_events = [e for e in events if e.get("event_type") == "evaluated"]
        assert len(eval_events) >= 1, f"evaluated 이벤트 없음: {events}"

        ev = eval_events[0]
        assert ev["stock_code"] == "005930"
        # signal_type은 None 또는 키 자체가 존재하고 null
        assert ev.get("signal_type") is None, f"signal_type 불일치: {ev}"


# ============================================================================
# Test 4: signal_generated 이벤트 (generate_signal → BUY)
# ============================================================================

class TestOnTickEmitsSignalGeneratedOnBuy:
    """generate_signal이 BUY Signal 반환 → signal_generated 이벤트 기록."""

    @pytest.mark.asyncio
    async def test_ontick_emits_signal_generated_on_buy(self, tmp_path):
        """
        Given: 25개 일봉, generate_signal returns BUY Signal, tracer
        When: await strategy.on_tick(ctx)
        Then: JSONL에 event_type="signal_generated", signal_type="BUY"
        """
        tracer = TickTracer(base_dir=tmp_path / "tick_trace")
        buy_signal = Signal(
            signal_type=SignalType.BUY,
            stock_code="005930",
            confidence=80.0,
            reasons=["test buy"],
        )
        strategy = _TestStrategy(signal_to_return=buy_signal)
        ctx = _make_ctx(daily_data=_make_daily_data(25), tracer=tracer)

        await strategy.on_tick(ctx)

        from datetime import date
        out_file = tmp_path / "tick_trace" / f"{date.today().isoformat()}.jsonl"
        assert out_file.exists(), "JSONL 파일이 생성되지 않음"

        events = [json.loads(line) for line in out_file.read_text("utf-8").strip().splitlines()]
        sig_events = [e for e in events if e.get("event_type") == "signal_generated"]
        assert len(sig_events) >= 1, f"signal_generated 이벤트 없음: {events}"

        ev = sig_events[0]
        assert ev["stock_code"] == "005930"
        assert ev["signal_type"] == "BUY", f"signal_type 불일치: {ev}"
        assert "confidence" in ev, f"confidence 필드 없음: {ev}"


# ============================================================================
# Test 5: exit_timeframe — 보유종목 매도판단 데이터 소스 (2026-06-09 whipsaw 수정)
# ============================================================================

class _SellTimeframeRecordingStrategy(BaseStrategy):
    """매도판단에 전달된 timeframe을 기록하는 최소 전략."""

    name = "SellTfRec"
    version = "1.0.0"

    def __init__(self, exit_timeframe=None):
        super().__init__({})
        if exit_timeframe is not None:
            self.exit_timeframe = exit_timeframe
        self.sell_timeframes = []

    def get_min_data_length(self):
        return 1

    def generate_signal(self, stock_code, data, timeframe="daily"):
        # 보유종목 매도 평가에서만 호출됨(이 테스트는 selected=[]). timeframe 기록.
        self.sell_timeframes.append(timeframe)
        return None


def _make_sell_ctx():
    """매도 루프용 ctx: 보유종목 1개 + 일봉/분봉 조회 호출 추적."""
    import logging

    pos = MagicMock()
    pos.stock_code = "005930"

    ctx = MagicMock()
    ctx.tracer = None
    ctx.get_selected_stocks.return_value = []
    ctx.get_positions.return_value = [pos]

    daily_calls, intraday_calls = [], []

    async def _get_daily(code, days=60):
        daily_calls.append(code)
        return _make_daily_data(80)

    async def _get_intraday(code):
        intraday_calls.append(code)
        return _make_daily_data(80)

    ctx.get_daily_data = _get_daily
    ctx.get_intraday_data = _get_intraday
    ctx.sell = AsyncMock()
    ctx.logger = logging.getLogger("test_sell_ctx")
    return ctx, daily_calls, intraday_calls


class TestOnTickExitTimeframe:
    """exit_timeframe에 따라 보유종목 매도판단의 데이터 소스가 달라진다."""

    @pytest.mark.asyncio
    async def test_daily_exit_strategy_uses_daily_data(self):
        """exit_timeframe='daily' → 매도판단에 일봉 조회 + timeframe='daily' 전달."""
        strat = _SellTimeframeRecordingStrategy(exit_timeframe="daily")
        ctx, daily_calls, intraday_calls = _make_sell_ctx()

        await strat.on_tick(ctx)

        assert daily_calls == ["005930"], "보유종목 매도판단에 일봉을 조회해야 함"
        assert intraday_calls == [], "exit_timeframe='daily'면 분봉을 조회하면 안 됨"
        assert strat.sell_timeframes == ["daily"], (
            f"generate_signal에 timeframe='daily' 전달돼야 함: {strat.sell_timeframes}"
        )

    @pytest.mark.asyncio
    async def test_default_strategy_uses_intraday_data(self):
        """기본(exit_timeframe 미설정) → 기존대로 분봉 조회 (하위호환)."""
        strat = _SellTimeframeRecordingStrategy()  # 기본값
        assert strat.exit_timeframe == "intraday"
        ctx, daily_calls, intraday_calls = _make_sell_ctx()

        await strat.on_tick(ctx)

        assert intraday_calls == ["005930"], "기본 전략은 분봉을 조회해야 함"
        assert daily_calls == [], "기본 전략은 매도판단에 일봉을 조회하면 안 됨"
        assert strat.sell_timeframes == ["intraday"]


# ============================================================================
# Test 6: 요약 줄 캡 상태 칸 (2026-09-19) — 「신호 0건」의 평가함/평가 안 함 구분
# ============================================================================

_SUMMARY_PREFIX = "[on_tick] 매수검토"


class _CapAttrStrategy(_TestStrategy):
    """전략별 캡 속성(positions·_max_positions·daily_trades·_max_daily_trades)을 가진 전략."""

    def __init__(self, positions, max_positions, daily_trades, max_daily_trades):
        super().__init__(signal_to_return=None)
        self.positions = positions
        self._max_positions = max_positions
        self.daily_trades = daily_trades
        self._max_daily_trades = max_daily_trades


class _NoLen:
    """len() 이 TypeError 를 던지는 객체."""


class _BrokenCapStrategy(_CapAttrStrategy):
    """속성 접근 자체가 예외를 던지는 전략."""

    @property
    def _max_daily_trades(self):
        raise RuntimeError("boom")

    @_max_daily_trades.setter
    def _max_daily_trades(self, value):
        pass


async def _run_and_get_summaries(strategy):
    """on_tick 1회 실행 후 요약 줄(logger.info 인자)만 돌려준다."""
    strategy.logger = MagicMock()
    ctx = _make_ctx(daily_data=_make_daily_data(25))
    await strategy.on_tick(ctx)
    return [
        c.args[0] for c in strategy.logger.info.call_args_list
        if c.args and str(c.args[0]).startswith(_SUMMARY_PREFIX)
    ]


class TestOnTickSummaryCapState:
    """요약 줄 가운데 `자리 n/N·일일 d/D` 칸 — 로그 전용, 거동 불변."""

    @pytest.mark.asyncio
    async def test_summary_shows_cap_state_when_attrs_present(self):
        strat = _CapAttrStrategy(
            positions={"000001": {}, "000002": {}, "000003": {}},
            max_positions=5, daily_trades=2, max_daily_trades=5,
        )
        lines = await _run_and_get_summaries(strat)
        assert lines == [
            "[on_tick] 매수검토 1종목(스킵 0), 신호 0건 | 자리 3/5·일일 2/5 | 매도검토 0종목, 신호 0건"
        ]

    @pytest.mark.asyncio
    async def test_summary_shows_question_marks_when_attrs_missing(self):
        strat = _TestStrategy(signal_to_return=None)  # 캡 속성 없음(BaseStrategy 계약 아님)
        assert not hasattr(strat, "positions")
        lines = await _run_and_get_summaries(strat)
        assert lines == [
            "[on_tick] 매수검토 1종목(스킵 0), 신호 0건 | 자리 ?/?·일일 ?/? | 매도검토 0종목, 신호 0건"
        ]

    @pytest.mark.asyncio
    async def test_summary_never_raises_when_attr_access_fails(self):
        strat = _BrokenCapStrategy(
            positions=_NoLen(), max_positions=5, daily_trades=2, max_daily_trades=5,
        )
        lines = await _run_and_get_summaries(strat)  # 예외 없이 끝나야 한다
        assert lines == [
            "[on_tick] 매수검토 1종목(스킵 0), 신호 0건 | 자리 ?/5·일일 2/? | 매도검토 0종목, 신호 0건"
        ]

    @pytest.mark.asyncio
    async def test_ledger8_parser_still_matches_new_summary(self):
        """ledger8 logscan8 의 요약 줄 파서(RE_ONTICK_SUMMARY · `"[on_tick] 매수검토" in msg`)가
        새 형식에도 같은 그룹 값으로 매치된다."""
        from backtest.concept_axes.ledger8 import logscan8 as L

        strat = _CapAttrStrategy(
            positions={"000001": {}}, max_positions=10, daily_trades=0, max_daily_trades=5,
        )
        (new_line,) = await _run_and_get_summaries(strat)
        old_line = "[on_tick] 매수검토 1종목(스킵 0), 신호 0건 | 매도검토 0종목, 신호 0건"

        m_new = L.RE_ONTICK_SUMMARY.search(new_line)
        m_old = L.RE_ONTICK_SUMMARY.search(old_line)
        assert m_new is not None
        assert m_new.groups() == m_old.groups() == ("1", "0", "0")

        sd = L.StratDay()
        L._scan_strategy_line(sd, "rs_leader", new_line, "09:24:00", None, {})
        assert sd.ontick_times == ["09:24:00"]
