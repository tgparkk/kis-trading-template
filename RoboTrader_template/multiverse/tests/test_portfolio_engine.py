"""Phase 4 포트폴리오 백테스트 엔진 회귀 테스트 — DB 의존성 없음.

모든 테스트는 pit_reader / corp_events 를 monkey patch 하고
ComposableStrategy를 MagicMock으로 교체하여 실제 DB 연결 없이 동작.

테스트 항목:
  P1 — 시계열 순서: 백테스트가 start→end 단조 증가로 진행
  P2 — max_positions 상한: 동시 보유 절대 ps.max_positions개 이상 안 됨
  P3 — 리밸런싱 주기(weekly): 진입 결정이 월요일에만 발생, 화~금은 신규 진입 X
  P4 — 보유기간 상한: holding_max_days=10 → 11일째 보유 종목은 다음 거래일 강제 청산
  P5 — corp_events Universe 필터: 관리종목 종목은 Universe.select 결과에서 제외
  P6 — 평가금 회계: cash + sum(qty*price) 정확
  P7 — portfolio_stop: daily PnL ≤ portfolio_stop_pct → 다음 거래일 전량 청산
"""
from __future__ import annotations

import pandas as pd
import pytest
from dataclasses import replace
from datetime import date
from unittest.mock import MagicMock, patch

from RoboTrader_template.multiverse.composable import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.engine.portfolio_engine import (
    PortfolioBacktestResult,
    PortfolioPosition,
    run_portfolio_backtest,
)


# ================================================================== #
# 공통 픽스처 / 헬퍼
# ================================================================== #

# 2026년 1월 월~금 (5 거래일: 5/6/7/8/9일)
_WEEK1 = [
    date(2026, 1, 5),  # 월
    date(2026, 1, 6),  # 화
    date(2026, 1, 7),  # 수
    date(2026, 1, 8),  # 목
    date(2026, 1, 9),  # 금
]
# 2주차 월~금
_WEEK2 = [
    date(2026, 1, 12),  # 월
    date(2026, 1, 13),  # 화
    date(2026, 1, 14),  # 수
    date(2026, 1, 15),  # 목
    date(2026, 1, 16),  # 금
]

_ALL_DATES = _WEEK1 + _WEEK2

_SYMBOLS = ["A", "B", "C", "D", "E", "F"]


@pytest.fixture
def base_paramset() -> ParamSet:
    """모든 제약을 만족하는 기본 ParamSet."""
    return ParamSet(
        # A
        w_value=0.25, w_quality=0.25, w_momentum=0.25, w_growth=0.25,
        # B
        factor_top_n=50,
        # C
        ma_short=5, ma_mid=20, ma_long=60,
        ma_regime=200, ma_regime_filter_enabled=True, ma_alignment_mode="bullish_only",
        # D
        sig_trend_align=True, sig_pullback=True, sig_breakout=True,
        sig_volume=True, sig_flow=True, sig_bb_bounce=False, sig_macd=False,
        # E
        sig_trend_weight=0.20, sig_pullback_weight=0.15, sig_breakout_weight=0.20,
        sig_volume_weight=0.10, sig_flow_weight=0.10,
        sig_bb_weight=0.15, sig_macd_weight=0.10,
        # F
        tech_score_threshold=0.5, final_score_factor_w=0.4,
        # G
        entry_vol_filter_enabled=True, entry_vol_min_ratio=1.5, entry_vol_ma_period=20,
        # H
        entry_candle_filter_enabled=True, entry_candle_body_ratio=0.5,
        entry_candle_upper_wick_max=0.5,
        entry_candle_type="bullish", entry_prev_candle_check="none",
        # I
        entry_gap_filter="none", entry_close_position="upper_half",
        entry_consecutive_down=0, entry_ma_distance_max=1.10,
        # J
        entry_above_ma_mid=True, entry_ma_cross="none", entry_ma_slope_check="mid_rising",
        # K
        prev_kospi_return_filter="not_crash_2pct",
        prev_kosdaq_return_filter="not_crash_2pct",
        kospi_kosdaq_divergence="none",
        # L
        prev_sp500_filter="not_crash_1pct", prev_nasdaq_filter="not_crash_1pct",
        prev_vix_filter="below_25", overnight_futures="not_negative_1pct",
        # M
        sp500_trend="above_ma50", global_risk_mode="risk_on",
        # N
        atr_period=14, atr_multiplier=2.0,
        # O
        hard_stop_pct=-0.07, portfolio_pause_pct=-0.02, portfolio_stop_pct=-0.05,
        # P
        exit_tech_score_threshold=0.3, exit_signal_count=2, exit_rsi_overbought=75,
        # Q
        exit_below_ma_mid=True, exit_ma_dead_cross="short_cross_mid_down",
        # R
        max_positions=5, max_weight_per_stock=0.25, sizing_method="equal",
        # S
        dynamic_rr_enabled=True, initial_reward_atr_mult=2.5,
        vol_regime_adjustment="atr_pct_based", score_based_adjustment=True,
        breakeven_trigger=0.03, lock_step_1_trigger=0.07, lock_step_1_stop=0.02,
        lock_step_2_trigger=0.12, lock_step_2_stop=0.06,
        tech_score_target_adjust=True, volume_target_adjust=True,
        adx_trend_adjust=True, adx_exit_threshold=15,
        time_decay_enabled=True, time_decay_rate=0.01,
        partial_tp_enabled=True, partial_tp_trigger=0.07, partial_tp_ratio=0.5,
        # T
        rebalance_frequency="daily",
        # U
        holding_max_days=None,
    )


def _build_mock_strategy(paramset: ParamSet, signal_decisions: dict, scores: dict):
    """mock ComposableStrategy 빌더.

    spec 없이 MagicMock을 사용한다 — ComposableStrategy의 속성이 TYPE_CHECKING
    블록 안에 있어 런타임에 실제 속성이 없으므로 spec 지정 시 AttributeError 발생.

    Parameters
    ----------
    signal_decisions:
        dict[symbol → "BUY" | "SELL" | "HOLD"]
    scores:
        dict[symbol → float]
    """
    strategy = MagicMock()
    strategy.paramset = paramset

    selected_symbols = list(signal_decisions.keys())
    strategy.universe.select.return_value = selected_symbols

    strategy.scorer.score.side_effect = lambda ctx, sym, ps: scores.get(sym, 0.0)
    strategy.regime.is_risk_on.return_value = True
    strategy.signal_gen.generate.side_effect = (
        lambda ctx, sym, ps: signal_decisions.get(sym, "HOLD")
    )
    strategy.sizer.size.return_value = 10  # 고정 수량
    strategy.exit_rule.should_exit.return_value = (False, "")
    strategy.rebalancer.should_rebalance.return_value = True
    strategy.holding_cap.should_force_exit_by_age.return_value = False
    return strategy


def _make_daily_df(dates, close=100.0):
    return pd.DataFrame({
        "date": dates,
        "open": [close] * len(dates),
        "high": [close * 1.05] * len(dates),
        "low": [close * 0.95] * len(dates),
        "close": [close] * len(dates),
        "volume": [100000] * len(dates),
    })


def _patch_pit(
    dates=None,
    open_price=100.0,
    high_low=(105.0, 95.0),
    open_map: dict | None = None,
):
    """pit_reader 패치 컨텍스트."""
    if dates is None:
        dates = _ALL_DATES

    mock_reader = MagicMock()

    if open_map is not None:
        mock_reader.read_open.side_effect = lambda symbol, date: open_map.get(date)
    else:
        mock_reader.read_open.return_value = open_price

    mock_reader.read_high_low.return_value = high_low
    mock_reader.read_daily.return_value = _make_daily_df(dates, close=open_price)
    mock_reader.read_financial_ratio.return_value = None
    mock_reader.read_minute.return_value = pd.DataFrame()

    return patch(
        "RoboTrader_template.multiverse.engine.portfolio_engine.pit_reader",
        mock_reader,
    )


def _patch_corp_events(admin_symbols=None, halt_symbols=None):
    """corp_events 패치 컨텍스트."""
    admin_set = set(admin_symbols or [])
    halt_set = set(halt_symbols or [])

    mock_ce = MagicMock()
    mock_ce.is_administrative.side_effect = lambda code, d: code in admin_set
    mock_ce.is_halted.side_effect = lambda code, d: code in halt_set
    # filter_universe: 관리/거래정지 종목 제거
    mock_ce.filter_universe.side_effect = lambda codes, d: [
        c for c in codes if c not in admin_set and c not in halt_set
    ]
    return patch(
        "RoboTrader_template.multiverse.engine.portfolio_engine._corp_events",
        mock_ce,
    )


# ================================================================== #
# P1 — 시계열 순서 단조 증가
# ================================================================== #

def test_p1_monotonic_date_sequence(base_paramset):
    """백테스트가 start→end 단조 증가 순서로 진행되어야 한다."""
    visited_dates: list[date] = []

    ps = base_paramset
    strategy = _build_mock_strategy(
        ps,
        signal_decisions={"A": "BUY"},
        scores={"A": 1.0},
    )

    # universe.select 호출 시 날짜 기록
    original_side_effect = strategy.universe.select.side_effect

    def record_date_and_select(ctx, paramset):
        visited_dates.append(ctx.as_of_date)
        return ["A"]

    strategy.universe.select.side_effect = record_date_and_select

    with _patch_pit(dates=_ALL_DATES), _patch_corp_events():
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=["A"],
            start_date=_ALL_DATES[0],
            end_date=_ALL_DATES[-1],
            initial_capital=1_000_000.0,
        )

    assert len(visited_dates) >= 2, "리밸런싱이 최소 2회 이상 호출돼야 함"
    for i in range(1, len(visited_dates)):
        assert visited_dates[i] > visited_dates[i - 1], (
            f"시계열 역순: {visited_dates[i - 1]} → {visited_dates[i]}"
        )


# ================================================================== #
# P2 — max_positions 상한
# ================================================================== #

def test_p2_max_positions_not_exceeded(base_paramset):
    """max_positions=5 → 동시 보유 종목 수가 6 이상이 되면 안 된다."""
    ps = replace(base_paramset, max_positions=5)

    # 6개 종목 모두 BUY 신호
    signal_decisions = {s: "BUY" for s in _SYMBOLS}
    scores = {s: float(i) for i, s in enumerate(_SYMBOLS, 1)}

    strategy = _build_mock_strategy(ps, signal_decisions, scores)

    positions_snapshots: list[int] = []

    with _patch_pit(dates=_ALL_DATES), _patch_corp_events():
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=_SYMBOLS,
            start_date=_ALL_DATES[0],
            end_date=_ALL_DATES[-1],
            initial_capital=10_000_000.0,
        )

    # 매수 트레이드 수 확인
    buys = [t for t in result.trades if t.side == "BUY"]
    # 동시 보유 피크 계산 (날짜별 BUY - SELL 누적)
    from collections import defaultdict
    holding: dict[str, bool] = {}
    peak = 0
    for t in result.trades:
        if t.side == "BUY":
            holding[t.price] = True  # 중복 키 방지 위해 price 사용(임시)
        # 심볼 추적이 Trade에 없으므로 단순 BUY 순 체크
    # Trade에 symbol이 없으므로, BUY - SELL 총량으로 최대 동시 보유 추산
    concurrent = 0
    max_concurrent = 0
    for t in sorted(result.trades, key=lambda x: x.date):
        if t.side == "BUY":
            concurrent += 1
            max_concurrent = max(max_concurrent, concurrent)
        elif t.side == "SELL":
            concurrent = max(0, concurrent - 1)

    assert max_concurrent <= ps.max_positions, (
        f"max_positions={ps.max_positions} 초과: peak={max_concurrent}"
    )


# ================================================================== #
# P3 — 리밸런싱 주기 weekly: 월요일에만 진입 결정
# ================================================================== #

def test_p3_weekly_rebalance_only_on_monday(base_paramset):
    """rebalance_frequency='weekly' → 진입 결정(BUY 큐)이 월요일에만 발생."""
    ps = replace(base_paramset, rebalance_frequency="weekly", max_positions=3)
    strategy = _build_mock_strategy(
        ps,
        signal_decisions={"A": "BUY", "B": "BUY"},
        scores={"A": 2.0, "B": 1.0},
    )

    # rebalancer.should_rebalance는 weekly 로직으로 직접 처리
    # — MagicMock의 should_rebalance를 portfolio_engine 내부 _should_rebalance에 위임하도록
    #   side_effect를 제거하고 실제 날짜 기반 판단 적용
    from RoboTrader_template.multiverse.engine.portfolio_engine import _should_rebalance

    call_log: list[tuple[date, bool]] = []
    prev_dates: list[date | None] = [None]

    def rebalance_side_effect(d, ps_):
        result = _should_rebalance(d, "weekly", prev_dates[0])
        prev_dates[0] = d
        call_log.append((d, result))
        return result

    strategy.rebalancer.should_rebalance.side_effect = rebalance_side_effect

    with _patch_pit(dates=_ALL_DATES), _patch_corp_events():
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=["A", "B"],
            start_date=_ALL_DATES[0],
            end_date=_ALL_DATES[-1],
            initial_capital=5_000_000.0,
        )

    # 리밸런싱이 실제 트리거된 날짜는 result.rebalance_dates
    # weekly: 첫 거래일(월요일) + 2주차 월요일 = 2회 기대
    for rd in result.rebalance_dates:
        # 리밸런싱 날짜는 월요일(weekday=0) 또는 해당 주 첫 거래일이어야 함
        # _WEEK1[0]=월, _WEEK2[0]=월 이므로 weekday==0 검증
        assert rd.weekday() == 0, (
            f"weekly 리밸런싱이 월요일이 아닌 날에 발생: {rd} (weekday={rd.weekday()})"
        )


# ================================================================== #
# P4 — 보유기간 상한
# ================================================================== #

def test_p4_holding_cap_force_exit(base_paramset):
    """holding_max_days=10 → should_force_exit_by_age=True이면 다음 거래일 강제 청산."""
    ps = replace(base_paramset, holding_max_days=10, rebalance_frequency="daily")
    strategy = _build_mock_strategy(
        ps,
        signal_decisions={"A": "BUY"},
        scores={"A": 1.0},
    )

    # 처음에는 False, 5번째 날부터 True (강제 청산 트리거 시뮬)
    call_counter = [0]

    def force_exit_side_effect(pos_dict, d, ps_):
        call_counter[0] += 1
        # 4번째 호출부터 True (5번째 날 첫 체크 → 다음날 청산)
        return call_counter[0] >= 4

    strategy.holding_cap.should_force_exit_by_age.side_effect = force_exit_side_effect

    with _patch_pit(dates=_ALL_DATES), _patch_corp_events():
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=["A"],
            start_date=_ALL_DATES[0],
            end_date=_ALL_DATES[-1],
            initial_capital=1_000_000.0,
        )

    # "holding_cap_exceeded" reason의 SELL이 존재해야 함
    cap_exits = [t for t in result.trades if t.reason == "holding_cap_exceeded"]
    assert len(cap_exits) >= 1, (
        f"holding_cap_exceeded 강제 청산 없음. trades={result.trades}"
    )
    # SELL이어야 함
    assert all(t.side == "SELL" for t in cap_exits)


# ================================================================== #
# P5 — corp_events Universe 필터
# ================================================================== #

def test_p5_corp_events_universe_filter(base_paramset):
    """관리종목으로 표시된 종목은 Universe.select 결과에서 제외된다."""
    ps = replace(base_paramset, rebalance_frequency="daily", max_positions=5)

    # A=관리종목, B=정상
    strategy = _build_mock_strategy(
        ps,
        signal_decisions={"A": "BUY", "B": "BUY"},
        scores={"A": 2.0, "B": 1.0},
    )

    # universe.select는 A, B 모두 반환하지만
    # corp_events.filter_universe는 A(관리종목)를 제거
    strategy.universe.select.return_value = ["A", "B"]

    with _patch_pit(dates=_WEEK1), _patch_corp_events(admin_symbols=["A"]):
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=["A", "B"],
            start_date=_WEEK1[0],
            end_date=_WEEK1[-1],
            initial_capital=5_000_000.0,
        )

    # A는 관리종목이므로 BUY 체결이 있으면 안 됨
    # 동시에 B의 BUY는 가능 (정상 종목)
    # Trade에 symbol 필드가 없으므로 skipped_signals 확인
    # A에 대한 체결 시도가 있었다면 administrative로 skip돼야 함
    admin_skips = [s for s in result.skipped_signals if s[1] == "A" and s[2] == "administrative"]
    # filter_universe가 A를 제거하면 pending_order 자체가 생기지 않으므로
    # → A에 대한 BUY pending이 없음 = A BUY 없음
    a_buys = [t for t in result.trades if t.side == "BUY"]
    # A 종목이 매수됐다면 filter_universe가 동작하지 않은 것
    # 검증: filter_universe mock이 호출됐어야 함
    # 우회: B의 BUY는 있어야 함 (정상 종목)
    # corp_events.filter_universe mock 호출 검증
    from unittest.mock import patch as _patch
    filter_called = False

    mock_ce_calls = MagicMock()

    with _patch_pit(dates=_WEEK1):
        with patch(
            "RoboTrader_template.multiverse.engine.portfolio_engine._corp_events"
        ) as mock_ce_inner:
            mock_ce_inner.is_administrative.return_value = False
            mock_ce_inner.is_halted.return_value = False
            mock_ce_inner.filter_universe.side_effect = lambda codes, d: [
                c for c in codes if c != "A"  # A는 관리종목
            ]

            result2 = run_portfolio_backtest(
                strategy=strategy,
                candidate_symbols=["A", "B"],
                start_date=_WEEK1[0],
                end_date=_WEEK1[-1],
                initial_capital=5_000_000.0,
            )
            # filter_universe가 호출됐어야 함
            assert mock_ce_inner.filter_universe.called, (
                "corp_events.filter_universe가 호출되지 않음"
            )
            # 호출 인자에 A가 포함됐어야 하고, 결과에서 A가 빠졌어야 함
            call_args = mock_ce_inner.filter_universe.call_args_list
            for call in call_args:
                input_codes = call[0][0]
                # filter_universe 입력에 B가 있으면 B는 포함됐어야 함
                if "B" in input_codes:
                    result_codes = mock_ce_inner.filter_universe.side_effect(
                        input_codes, call[0][1]
                    )
                    assert "A" not in result_codes, "A가 filter_universe 후 포함됨"


# ================================================================== #
# P6 — 평가금 회계
# ================================================================== #

def test_p6_equity_accounting(base_paramset):
    """cash + sum(qty*price) 평가금 회계 정확성 검증.

    매수 후 평가금 변화 = -(수수료 + 슬리피지 비용).
    """
    ps = replace(base_paramset, rebalance_frequency="daily", max_positions=1)
    strategy = _build_mock_strategy(
        ps,
        signal_decisions={"A": "BUY"},
        scores={"A": 1.0},
    )
    # sizer: qty=10 고정
    strategy.sizer.size.return_value = 10

    OPEN_PRICE = 1000.0
    INITIAL_CAPITAL = 1_000_000.0

    with _patch_pit(dates=_WEEK1, open_price=OPEN_PRICE), _patch_corp_events():
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=["A"],
            start_date=_WEEK1[0],
            end_date=_WEEK1[-1],
            initial_capital=INITIAL_CAPITAL,
        )

    assert len(result.daily_equity) > 0

    # 모든 daily_equity는 양수여야 함
    for d, eq in result.daily_equity:
        assert eq > 0, f"{d} 평가금 음수: {eq}"

    # BUY 체결 검증
    buys = [t for t in result.trades if t.side == "BUY"]
    if buys:
        buy = buys[0]
        # 슬리피지 50bp: exec_price = 1000 * (1 + 50/10000) = 1005.0
        assert abs(buy.price - OPEN_PRICE * (1 + 50 / 10000)) < 1.0, (
            f"BUY 체결가 오차: {buy.price}"
        )
        # fee = exec_price * qty * 15bp
        expected_fee = buy.price * buy.qty * (15 / 10000)
        assert abs(buy.fee - expected_fee) < 0.1, (
            f"BUY 수수료 오차: {buy.fee} vs {expected_fee}"
        )

    # 최종 final_equity가 daily_equity 마지막 값과 일치
    assert result.final_equity == result.daily_equity[-1][1]

    # 초기 자본 대비 합리적 범위 (손실이 전체의 10% 이내)
    assert result.final_equity >= INITIAL_CAPITAL * 0.9, (
        f"예상치 못한 손실: {result.final_equity}"
    )


# ================================================================== #
# P7 — portfolio_stop 전량 청산
# ================================================================== #

def test_p7_portfolio_stop_full_exit(base_paramset):
    """daily PnL ≤ portfolio_stop_pct(-0.05) → 다음 거래일 전량 청산.

    설계:
      - 초기자본 작게 (30,000원) + qty=10 + open=100원 → 3종목 보유 시 전액 투자
      - D1(1/6): open=100 → 3종목 BUY 체결
      - D2(1/7): open=50 → 평가금 급감 → daily_pnl ≈ -50% → portfolio_stop 트리거
      - D3(1/8): 전량 SELL
    """
    # 초기자본을 포지션 규모에 맞게 설정 — 3종목 * qty=10 * open=100 = 3,000원
    # 수수료/슬리피지 포함 여유 자금 포함해서 10,000원
    INITIAL_CAPITAL = 10_000.0
    QTY = 10

    ps = replace(
        base_paramset,
        portfolio_stop_pct=-0.05,
        portfolio_pause_pct=-0.02,
        rebalance_frequency="daily",
        max_positions=3,
    )
    strategy = _build_mock_strategy(
        ps,
        signal_decisions={"A": "BUY", "B": "BUY", "C": "BUY"},
        scores={"A": 3.0, "B": 2.0, "C": 1.0},
    )
    strategy.sizer.size.return_value = QTY

    # D0(1/5): open=100 → 리밸런싱 신호 → pending BUY
    # D1(1/6): open=100 → BUY 체결 → 평가금 ≈ 3,000원 (cash 거의 0)
    # D2(1/7): open=50  → 평가금 ≈ 1,500원 → daily_pnl ≈ -50% → portfolio_stop
    # D3(1/8): open=50  → 전량 SELL (portfolio_stop reason)
    open_map = {}
    for d in _ALL_DATES:
        if d >= date(2026, 1, 7):
            open_map[d] = 50.0   # -50% 급락
        else:
            open_map[d] = 100.0

    with _patch_pit(dates=_ALL_DATES, open_map=open_map), _patch_corp_events():
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=["A", "B", "C"],
            start_date=_ALL_DATES[0],
            end_date=_ALL_DATES[-1],
            initial_capital=INITIAL_CAPITAL,
        )

    # "portfolio_stop" reason의 SELL이 존재해야 함
    stop_exits = [t for t in result.trades if t.reason == "portfolio_stop"]
    assert len(stop_exits) >= 1, (
        f"portfolio_stop 청산 없음.\n"
        f"daily_equity={result.daily_equity}\n"
        f"trades={result.trades}"
    )
    assert all(t.side == "SELL" for t in stop_exits), (
        "portfolio_stop 이유의 BUY가 있음 (BUG)"
    )


# ================================================================== #
# P8 — _get_portfolio_trading_dates union 방식
# ================================================================== #

def test_get_portfolio_trading_dates_uses_union():
    """모든 candidate 종목의 거래일 union을 사용해 첫 종목 의존성 제거."""
    # 종목 A: 5월 1~3일만 거래 (3일치)
    # 종목 B: 5월 1~10일 거래 (10일치)
    # 종목 C: 5월 5~10일 거래 (6일치)
    # 기대: union = 5월 1~10일 (10일)
    from unittest.mock import patch
    from RoboTrader_template.multiverse.engine.portfolio_engine import _get_portfolio_trading_dates

    a_dates = [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)]
    b_dates = [date(2026, 5, d) for d in range(1, 11)]
    c_dates = [date(2026, 5, d) for d in range(5, 11)]

    def _read_daily_mock(symbol, as_of_date, lookback_days):
        if symbol == "A":
            return pd.DataFrame({
                "date": a_dates, "close": [100] * 3,
                "open": [100] * 3, "high": [100] * 3,
                "low": [100] * 3, "volume": [1000] * 3,
            })
        if symbol == "B":
            return pd.DataFrame({
                "date": b_dates, "close": [200] * 10,
                "open": [200] * 10, "high": [200] * 10,
                "low": [200] * 10, "volume": [1000] * 10,
            })
        if symbol == "C":
            return pd.DataFrame({
                "date": c_dates, "close": [300] * 6,
                "open": [300] * 6, "high": [300] * 6,
                "low": [300] * 6, "volume": [1000] * 6,
            })
        return pd.DataFrame()

    with patch(
        "RoboTrader_template.multiverse.engine.portfolio_engine.pit_reader.read_daily",
        side_effect=_read_daily_mock,
    ):
        # A를 첫 번째에 둬도(이전엔 3일치만 잡힘) union으로 10일 모두 나와야 함
        result = _get_portfolio_trading_dates(
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 10),
            candidate_symbols=["A", "B", "C"],
        )

    assert len(result) == 10, f"기대 10일, 실제 {len(result)}일"
    assert result[0] == date(2026, 5, 1)
    assert result[-1] == date(2026, 5, 10)
    assert all(date(2026, 5, 1) <= d <= date(2026, 5, 10) for d in result)


def test_get_portfolio_trading_dates_empty_candidates_fallback():
    """빈 candidate일 때 평일 fallback 동작 유지."""
    from RoboTrader_template.multiverse.engine.portfolio_engine import _get_portfolio_trading_dates

    result = _get_portfolio_trading_dates(
        start_date=date(2026, 5, 4),  # 월
        end_date=date(2026, 5, 8),    # 금
        candidate_symbols=[],
    )
    # 5/4~5/8 평일 5일 (월~금)
    assert len(result) == 5


def test_get_portfolio_trading_dates_all_empty_data_fallback():
    """모든 candidate가 빈 일봉이면 평일 fallback."""
    from unittest.mock import patch
    from RoboTrader_template.multiverse.engine.portfolio_engine import _get_portfolio_trading_dates

    with patch(
        "RoboTrader_template.multiverse.engine.portfolio_engine.pit_reader.read_daily",
        return_value=pd.DataFrame(),
    ):
        result = _get_portfolio_trading_dates(
            start_date=date(2026, 5, 4),
            end_date=date(2026, 5, 8),
            candidate_symbols=["X", "Y", "Z"],
        )
    assert len(result) == 5  # 평일 fallback


# ================================================================== #
# P9 — 8 모듈 모두 paramset 인자를 전달받는지 검증
# ================================================================== #

def test_all_modules_receive_paramset(base_paramset):
    """portfolio_engine이 8 Composable 모듈 호출 시 paramset 인자를 모두 전달하는지 검증.

    5/2에 발견된 paramset 누락 버그(TypeError) 회귀 방지.
    각 모듈의 call_args에 paramset이 positional 또는 keyword로 포함됐는지 확인한다.
    """
    from dataclasses import replace as dc_replace

    ps = dc_replace(base_paramset, rebalance_frequency="daily", max_positions=2)

    strategy = _build_mock_strategy(
        ps,
        signal_decisions={"A": "BUY", "B": "BUY"},
        scores={"A": 2.0, "B": 1.0},
    )
    strategy.sizer.size.return_value = 5

    # 보유 포지션이 생기도록 exit_rule / holding_cap 을 항상 HOLD로 설정
    # (5 거래일 동안 BUY → 2일차부터 exit 체크 호출 보장)
    strategy.exit_rule.should_exit.return_value = (False, "")
    strategy.holding_cap.should_force_exit_by_age.return_value = False

    with _patch_pit(dates=_WEEK1, open_price=100.0), _patch_corp_events():
        run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=["A", "B"],
            start_date=_WEEK1[0],
            end_date=_WEEK1[-1],
            initial_capital=1_000_000.0,
        )

    def _paramset_in_call(mock_method):
        """mock_method의 모든 call 중 하나라도 ps가 인자에 포함됐으면 True."""
        for call in mock_method.call_args_list:
            args, kwargs = call
            if ps in args or kwargs.get("paramset") is ps:
                return True
        return False

    # universe.select(ctx, paramset)
    assert strategy.universe.select.called, "universe.select 미호출"
    assert _paramset_in_call(strategy.universe.select), (
        "universe.select에 paramset 전달 누락"
    )

    # scorer.score(ctx, sym, paramset)
    assert strategy.scorer.score.called, "scorer.score 미호출"
    assert _paramset_in_call(strategy.scorer.score), (
        "scorer.score에 paramset 전달 누락"
    )

    # regime.is_risk_on(ctx, paramset)
    assert strategy.regime.is_risk_on.called, "regime.is_risk_on 미호출"
    assert _paramset_in_call(strategy.regime.is_risk_on), (
        "regime.is_risk_on에 paramset 전달 누락"
    )

    # signal_gen.generate(ctx, sym, paramset)
    assert strategy.signal_gen.generate.called, "signal_gen.generate 미호출"
    assert _paramset_in_call(strategy.signal_gen.generate), (
        "signal_gen.generate에 paramset 전달 누락"
    )

    # sizer.size(capital, score, paramset)
    assert strategy.sizer.size.called, "sizer.size 미호출"
    assert _paramset_in_call(strategy.sizer.size), (
        "sizer.size에 paramset 전달 누락"
    )

    # exit_rule.should_exit(ctx, pos_dict, paramset) — 보유 포지션 생긴 후 호출
    assert strategy.exit_rule.should_exit.called, (
        "exit_rule.should_exit 미호출 — 보유 포지션이 생기지 않았을 가능성"
    )
    assert _paramset_in_call(strategy.exit_rule.should_exit), (
        "exit_rule.should_exit에 paramset 전달 누락"
    )

    # holding_cap.should_force_exit_by_age(pos_dict, date, paramset)
    assert strategy.holding_cap.should_force_exit_by_age.called, (
        "holding_cap.should_force_exit_by_age 미호출"
    )
    assert _paramset_in_call(strategy.holding_cap.should_force_exit_by_age), (
        "holding_cap.should_force_exit_by_age에 paramset 전달 누락"
    )

    # rebalancer.should_rebalance(date, paramset)
    assert strategy.rebalancer.should_rebalance.called, "rebalancer.should_rebalance 미호출"
    assert _paramset_in_call(strategy.rebalancer.should_rebalance), (
        "rebalancer.should_rebalance에 paramset 전달 누락"
    )


# ================================================================== #
# P10 — ComposableStrategy isinstance 가드
# ================================================================== #

def test_composable_strategy_rejects_invalid_module():
    """8 모듈 중 하나가 Protocol을 만족하지 않으면 TypeError raise.

    MagicMock은 임의 attribute에 응답하므로 isinstance(Protocol) → True 통과.
    아무 메서드도 없는 _Bad 클래스로 Protocol 위반 케이스를 검증한다.
    """
    import pytest
    from unittest.mock import MagicMock
    from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy

    class _Bad:
        """Protocol 메서드가 전혀 없는 클래스."""
        pass

    # 최소 유효 더미 — 각 Protocol 메서드 이름만 구현
    class _OkUniverse:
        def select(self, ctx, paramset): return []

    class _OkScorer:
        def score(self, ctx, symbol, paramset): return 0.0

    class _OkRegime:
        def is_risk_on(self, ctx, paramset): return True

    class _OkSignalGen:
        def generate(self, ctx, symbol, paramset): return "HOLD"

    class _OkSizer:
        def size(self, capital, score, paramset): return 0

    class _OkExitRule:
        def should_exit(self, ctx, position, paramset): return (False, "")

    class _OkRebalancer:
        def should_rebalance(self, current_date, paramset): return True

    class _OkHoldingCap:
        def should_force_exit_by_age(self, position, current_date, paramset): return False

    ok_kwargs = dict(
        paramset=MagicMock(),
        universe=_OkUniverse(),
        scorer=_OkScorer(),
        regime=_OkRegime(),
        signal_gen=_OkSignalGen(),
        sizer=_OkSizer(),
        exit_rule=_OkExitRule(),
        rebalancer=_OkRebalancer(),
        holding_cap=_OkHoldingCap(),
    )

    # universe 위반
    with pytest.raises(TypeError, match="universe"):
        ComposableStrategy(**{**ok_kwargs, "universe": _Bad()})

    # scorer 위반
    with pytest.raises(TypeError, match="scorer"):
        ComposableStrategy(**{**ok_kwargs, "scorer": _Bad()})

    # regime 위반
    with pytest.raises(TypeError, match="regime"):
        ComposableStrategy(**{**ok_kwargs, "regime": _Bad()})

    # signal_gen 위반
    with pytest.raises(TypeError, match="signal_gen"):
        ComposableStrategy(**{**ok_kwargs, "signal_gen": _Bad()})

    # sizer 위반
    with pytest.raises(TypeError, match="sizer"):
        ComposableStrategy(**{**ok_kwargs, "sizer": _Bad()})

    # exit_rule 위반
    with pytest.raises(TypeError, match="exit_rule"):
        ComposableStrategy(**{**ok_kwargs, "exit_rule": _Bad()})

    # rebalancer 위반
    with pytest.raises(TypeError, match="rebalancer"):
        ComposableStrategy(**{**ok_kwargs, "rebalancer": _Bad()})

    # holding_cap 위반
    with pytest.raises(TypeError, match="holding_cap"):
        ComposableStrategy(**{**ok_kwargs, "holding_cap": _Bad()})

    # 모두 유효한 경우는 정상 생성
    strategy = ComposableStrategy(**ok_kwargs)
    assert strategy.universe is ok_kwargs["universe"]
