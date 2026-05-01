"""Phase 2 PIT 백테스트 엔진 회귀 테스트 — DB 의존성 없음.

모든 테스트는 pit_reader / corp_events 를 monkey patch 하여
실제 DB 연결 없이 동작.

테스트 항목:
  D1 — run_backtest() 키워드 인자 강제 (positional 거부)
  D2 — signal_fn 에 전달되는 as_of_date 단조 증가 (시계열 순서)
  D3 — T-1 종가 BUY 신호 → T일 시가 체결, 슬리피지 정확
  D4 — 일중 TP: take_profit=110, T일 high=115 → 110 체결
  D5 — 상한가 거부: T-1 종가 100, T 시가 131(+31%) → BUY 거부
  D6 — 관리종목 자동 청산: 보유 중 administrative 편입 → 다음 거래일 강제 청산
  D7 — 비대칭 거래비용: BUY 0.15%, SELL 2.45% 정확 적용
"""
from __future__ import annotations

import pandas as pd
import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from RoboTrader_template.multiverse.engine import (
    BacktestResult,
    PITContext,
    Signal,
    Trade,
    run_backtest,
)

# ------------------------------------------------------------------ #
# 공통 Mock 팩토리
# ------------------------------------------------------------------ #

_DATES = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]


def _make_daily_df(dates=None):
    """단조 증가 일봉 DataFrame — close=100 고정."""
    if dates is None:
        dates = _DATES
    return pd.DataFrame({
        "date": dates,
        "open": [100.0] * len(dates),
        "high": [105.0] * len(dates),
        "low": [95.0] * len(dates),
        "close": [100.0] * len(dates),
        "volume": [10000] * len(dates),
    })


def _patch_pit(
    open_map: dict,
    high_low_map: dict,
    daily_df=None,
    financial_ratio=None,
):
    """pit_reader 를 monkey patch 하는 컨텍스트 매니저 반환."""
    if daily_df is None:
        daily_df = _make_daily_df()

    mock_reader = MagicMock()
    mock_reader.read_open.side_effect = lambda symbol, date: open_map.get(date)
    mock_reader.read_high_low.side_effect = lambda symbol, date: high_low_map.get(date)
    mock_reader.read_daily.return_value = daily_df
    mock_reader.read_financial_ratio.return_value = financial_ratio
    mock_reader.read_minute.return_value = pd.DataFrame()
    return patch(
        "RoboTrader_template.multiverse.engine.pit_engine.pit_reader",
        mock_reader,
    )


def _patch_corp_events(admin_dates=None, halt_dates=None):
    """corp_events 를 monkey patch — 기본값은 모두 False."""
    admin_dates = set(admin_dates or [])
    halt_dates = set(halt_dates or [])

    mock_ce = MagicMock()
    mock_ce.is_administrative.side_effect = lambda code, d: d in admin_dates
    mock_ce.is_halted.side_effect = lambda code, d: d in halt_dates
    return patch(
        "RoboTrader_template.multiverse.engine.pit_engine._corp_events",
        mock_ce,
    )


# ------------------------------------------------------------------ #
# D1 — 키워드 인자 강제
# ------------------------------------------------------------------ #

def test_d1_keyword_only():
    """run_backtest()가 positional 인자를 거부해야 한다."""
    with pytest.raises(TypeError):
        # positional 로 호출 — 키워드 전용 함수이므로 TypeError 발생
        run_backtest(  # type: ignore[call-overload]
            "TEST",
            date(2026, 1, 5),
            date(2026, 1, 6),
            10000,
            lambda ctx: Signal(action="HOLD"),
        )


# ------------------------------------------------------------------ #
# D2 — 시계열 순서 단조 증가
# ------------------------------------------------------------------ #

def test_d2_monotonic_dates():
    """signal_fn 에 전달되는 as_of_date 가 start→end 단조 증가."""
    visited: list[date] = []

    def signal_fn(ctx: PITContext) -> Signal:
        visited.append(ctx.as_of_date)
        return Signal(action="HOLD")

    open_map = {d: 100.0 for d in _DATES}
    high_low_map = {d: (105.0, 95.0) for d in _DATES}
    daily_df = _make_daily_df(_DATES)

    with _patch_pit(open_map, high_low_map, daily_df), _patch_corp_events():
        run_backtest(
            symbol="TEST",
            start_date=_DATES[0],
            end_date=_DATES[-1],
            initial_capital=10000.0,
            signal_fn=signal_fn,
        )

    # 단조 증가 확인
    assert len(visited) >= 2
    for i in range(1, len(visited)):
        assert visited[i] > visited[i - 1], (
            f"시계열 순서 위반: {visited[i - 1]} -> {visited[i]}"
        )


# ------------------------------------------------------------------ #
# D3 — T일 시가 체결 + 슬리피지 검증
# ------------------------------------------------------------------ #

def test_d3_open_execution():
    """BUY 신호 → T일 시가 100원에 체결, 슬리피지 50bp 반영."""
    call_count = [0]

    def signal_fn(ctx: PITContext) -> Signal:
        call_count[0] += 1
        # 첫 번째 날에만 BUY
        if call_count[0] == 1:
            return Signal(action="BUY", qty=10)
        return Signal(action="HOLD")

    # open=100, prev_close=100 (갭 없음) → 슬리피지 50bp
    # 기대 exec_price = 100 * (1 + 50/10000) = 100.5
    open_map = {d: 100.0 for d in _DATES}
    high_low_map = {d: (101.0, 99.0) for d in _DATES}

    with _patch_pit(open_map, high_low_map), _patch_corp_events():
        result = run_backtest(
            symbol="TEST",
            start_date=_DATES[0],
            end_date=_DATES[-1],
            initial_capital=100000.0,
            signal_fn=signal_fn,
        )

    buys = [t for t in result.trades if t.side == "BUY"]
    assert len(buys) >= 1, "BUY 체결이 없음"

    buy = buys[0]
    # 슬리피지 50bp: 100 * 1.005 = 100.5
    assert abs(buy.price - 100.5) < 0.1, f"체결가 오차: {buy.price}"
    # fee = exec_price * qty * 15bp
    expected_fee = buy.price * 10 * (15 / 10000)
    assert abs(buy.fee - expected_fee) < 0.01, f"BUY 수수료 오차: {buy.fee}"


# ------------------------------------------------------------------ #
# D4 — 일중 TP 체결
# ------------------------------------------------------------------ #

def test_d4_intraday_take_profit():
    """take_profit=110, T일 high=115 → 110에 체결 (reason='take_profit')."""
    call_count = [0]

    def signal_fn(ctx: PITContext) -> Signal:
        call_count[0] += 1
        if call_count[0] == 1:
            return Signal(action="BUY", qty=5, take_profit=110.0)
        return Signal(action="HOLD")

    # 2일차에 high=115 → TP 도달
    open_map = {
        _DATES[0]: 100.0,
        _DATES[1]: 100.0,
        _DATES[2]: 100.0,
    }
    high_low_map = {
        _DATES[0]: (101.0, 99.0),   # 매수 당일 TP 미달
        _DATES[1]: (115.0, 99.0),   # TP 도달 (high=115 >= 110)
        _DATES[2]: (101.0, 99.0),
    }

    with _patch_pit(open_map, high_low_map), _patch_corp_events():
        result = run_backtest(
            symbol="TEST",
            start_date=_DATES[0],
            end_date=_DATES[-1],
            initial_capital=100000.0,
            signal_fn=signal_fn,
        )

    tp_trades = [t for t in result.trades if t.reason == "take_profit"]
    assert len(tp_trades) >= 1, "TP 체결이 없음"
    tp = tp_trades[0]
    assert abs(tp.price - 110.0) < 0.01, f"TP 체결가 오차: {tp.price}"
    assert tp.side == "SELL"


# ------------------------------------------------------------------ #
# D5 — 상한가 거부
# ------------------------------------------------------------------ #

def test_d5_limit_up_rejected():
    """T-1 종가 100, T 시가 131(+31%) → BUY 신호 거부, skipped_signals 기록."""

    def signal_fn(ctx: PITContext) -> Signal:
        return Signal(action="BUY", qty=10)

    # prev_close=100, open=131 → +31% → 상한가 거부
    # read_daily 마지막 행이 prev_close 로 사용됨 (close=100)
    daily_df = pd.DataFrame({
        "date": [date(2026, 1, 2)],  # start_date 이전 날짜
        "open": [100.0],
        "high": [100.0],
        "low": [100.0],
        "close": [100.0],
        "volume": [10000],
    })

    open_map = {_DATES[0]: 131.0}  # +31% 갭
    high_low_map = {_DATES[0]: (135.0, 130.0)}

    with _patch_pit(open_map, high_low_map, daily_df), _patch_corp_events():
        result = run_backtest(
            symbol="TEST",
            start_date=_DATES[0],
            end_date=_DATES[0],
            initial_capital=100000.0,
            signal_fn=signal_fn,
        )

    # BUY 체결이 없어야 함
    buys = [t for t in result.trades if t.side == "BUY"]
    assert len(buys) == 0, "상한가인데 BUY 체결됨"

    # skipped_signals 에 "limit_up_or_down" 기록
    reasons = [r for _, r in result.skipped_signals]
    assert "limit_up_or_down" in reasons, f"skipped_signals: {result.skipped_signals}"


# ------------------------------------------------------------------ #
# D6 — 관리종목 자동 청산
# ------------------------------------------------------------------ #

def test_d6_administrative_force_exit():
    """보유 중 관리종목 편입 → 다음 거래일 시가 강제 청산."""
    call_count = [0]

    def signal_fn(ctx: PITContext) -> Signal:
        call_count[0] += 1
        if call_count[0] == 1:
            return Signal(action="BUY", qty=5)
        return Signal(action="HOLD")

    open_map = {d: 100.0 for d in _DATES}
    high_low_map = {d: (101.0, 99.0) for d in _DATES}

    # _DATES[1] (2일차) 에 관리종목 편입 → _DATES[2] 에 강제 청산
    with _patch_pit(open_map, high_low_map), _patch_corp_events(admin_dates=[_DATES[1]]):
        result = run_backtest(
            symbol="TEST",
            start_date=_DATES[0],
            end_date=_DATES[-1],
            initial_capital=100000.0,
            signal_fn=signal_fn,
        )

    force_exits = [t for t in result.trades if t.reason == "administrative_force_exit"]
    assert len(force_exits) >= 1, f"강제청산 없음. trades={result.trades}"

    # 강제 청산은 관리종목 감지 다음 날 (_DATES[2])
    assert force_exits[0].date == _DATES[2], (
        f"강제청산 날짜 오류: {force_exits[0].date}"
    )


# ------------------------------------------------------------------ #
# D7 — 비대칭 거래비용
# ------------------------------------------------------------------ #

def test_d7_asymmetric_fee():
    """BUY 수수료=price*qty*0.0015, SELL 수수료=price*qty*0.0245 정확 적용."""
    call_count = [0]

    def signal_fn(ctx: PITContext) -> Signal:
        call_count[0] += 1
        if call_count[0] == 1:
            return Signal(action="BUY", qty=10)
        if call_count[0] == 2:
            return Signal(action="SELL")
        return Signal(action="HOLD")

    open_map = {d: 100.0 for d in _DATES}
    high_low_map = {d: (101.0, 99.0) for d in _DATES}

    with _patch_pit(open_map, high_low_map), _patch_corp_events():
        result = run_backtest(
            symbol="TEST",
            start_date=_DATES[0],
            end_date=_DATES[-1],
            initial_capital=100000.0,
            signal_fn=signal_fn,
        )

    buys = [t for t in result.trades if t.side == "BUY" and t.reason == "signal"]
    sells = [t for t in result.trades if t.side == "SELL" and t.reason == "signal"]

    assert len(buys) >= 1, "BUY 없음"
    assert len(sells) >= 1, "SELL 없음"

    buy = buys[0]
    sell = sells[0]

    # BUY: fee = exec_price * qty * 15bp
    expected_buy_fee = buy.price * buy.qty * (15 / 10000)
    assert abs(buy.fee - expected_buy_fee) < 0.01, (
        f"BUY 수수료 오차: {buy.fee} vs {expected_buy_fee}"
    )

    # SELL: fee = exec_price * qty * 245bp
    expected_sell_fee = sell.price * sell.qty * (245 / 10000)
    assert abs(sell.fee - expected_sell_fee) < 0.01, (
        f"SELL 수수료 오차: {sell.fee} vs {expected_sell_fee}"
    )
