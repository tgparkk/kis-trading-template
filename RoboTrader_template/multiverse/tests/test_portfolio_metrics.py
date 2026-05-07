"""precision / expectancy 메트릭 단위 테스트.

DB 의존성 없음 — pit_reader / corp_events 를 monkey patch.

테스트 항목:
  M1 — precision: 5건 BUY 중 2건이 +5% 도달 → 0.4
  M2 — expectancy: 합성 거래 평균 손익 검증
  M3 — 거래 0건일 때 precision=0.0, expectancy=0.0
  M4 — BUY만 있고 SELL 없을 때 expectancy=0.0 (미청산)
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from dataclasses import replace

from RoboTrader_template.multiverse.composable import ParamSet
from RoboTrader_template.multiverse.engine.portfolio_engine import (
    PortfolioBacktestResult,
    run_portfolio_backtest,
)


# ================================================================== #
# 공통 픽스처
# ================================================================== #

_DATES = [
    date(2026, 1, 5),   # D0
    date(2026, 1, 6),   # D1
    date(2026, 1, 7),   # D2
    date(2026, 1, 8),   # D3
    date(2026, 1, 9),   # D4
    date(2026, 1, 12),  # D5
]


@pytest.fixture
def base_ps() -> ParamSet:
    return ParamSet(
        w_value=0.25, w_quality=0.25, w_momentum=0.25, w_growth=0.25,
        factor_top_n=50,
        ma_short=5, ma_mid=20, ma_long=60,
        ma_regime=200, ma_regime_filter_enabled=True, ma_alignment_mode="bullish_only",
        sig_trend_align=True, sig_pullback=True, sig_breakout=True,
        sig_volume=True, sig_flow=True, sig_bb_bounce=False, sig_macd=False,
        sig_trend_weight=0.20, sig_pullback_weight=0.15, sig_breakout_weight=0.20,
        sig_volume_weight=0.10, sig_flow_weight=0.10,
        sig_bb_weight=0.15, sig_macd_weight=0.10,
        tech_score_threshold=0.5, final_score_factor_w=0.4,
        entry_vol_filter_enabled=True, entry_vol_min_ratio=1.5, entry_vol_ma_period=20,
        entry_candle_filter_enabled=True, entry_candle_body_ratio=0.5,
        entry_candle_upper_wick_max=0.5,
        entry_candle_type="bullish", entry_prev_candle_check="none",
        entry_gap_filter="none", entry_close_position="upper_half",
        entry_consecutive_down=0, entry_ma_distance_max=1.10,
        entry_above_ma_mid=True, entry_ma_cross="none", entry_ma_slope_check="mid_rising",
        prev_kospi_return_filter="not_crash_2pct",
        prev_kosdaq_return_filter="not_crash_2pct",
        kospi_kosdaq_divergence="none",
        prev_sp500_filter="not_crash_1pct", prev_nasdaq_filter="not_crash_1pct",
        prev_vix_filter="below_25", overnight_futures="not_negative_1pct",
        sp500_trend="above_ma50", global_risk_mode="risk_on",
        atr_period=14, atr_multiplier=2.0,
        hard_stop_pct=-0.07, portfolio_pause_pct=-0.02, portfolio_stop_pct=-0.05,
        exit_tech_score_threshold=0.3, exit_signal_count=2, exit_rsi_overbought=75,
        exit_below_ma_mid=True, exit_ma_dead_cross="short_cross_mid_down",
        max_positions=5, max_weight_per_stock=0.25, sizing_method="equal",
        dynamic_rr_enabled=True, initial_reward_atr_mult=2.5,
        vol_regime_adjustment="atr_pct_based", score_based_adjustment=True,
        breakeven_trigger=0.03, lock_step_1_trigger=0.07, lock_step_1_stop=0.02,
        lock_step_2_trigger=0.12, lock_step_2_stop=0.06,
        tech_score_target_adjust=True, volume_target_adjust=True,
        adx_trend_adjust=True, adx_exit_threshold=15,
        time_decay_enabled=True, time_decay_rate=0.01,
        partial_tp_enabled=True, partial_tp_trigger=0.07, partial_tp_ratio=0.5,
        rebalance_frequency="daily",
        holding_max_days=None,
    )


def _build_mock_strategy(ps, signal_sym="A"):
    strategy = MagicMock()
    strategy.paramset = ps
    strategy.universe.select.return_value = [signal_sym]
    strategy.scorer.score.return_value = 1.0
    strategy.regime.is_risk_on.return_value = True
    strategy.signal_gen.generate.return_value = "BUY"
    strategy.sizer.size.return_value = 10
    strategy.exit_rule.should_exit.return_value = (False, "")
    strategy.rebalancer.should_rebalance.return_value = True
    strategy.holding_cap.should_force_exit_by_age.return_value = False
    return strategy


def _make_df(dates, close=1000.0):
    return pd.DataFrame({
        "date": dates,
        "open": [close] * len(dates),
        "high": [close * 1.06] * len(dates),   # +6% high 기본 (precision hit)
        "low": [close * 0.95] * len(dates),
        "close": [close] * len(dates),
        "volume": [100_000] * len(dates),
    })


# ================================================================== #
# M1 — precision: 5건 BUY 중 2건이 +5% 도달 → 0.4
# ================================================================== #

def test_m1_precision_two_of_five(base_ps):
    """5개 종목 BUY, 2개만 당일 high ≥ entry*1.05 → precision=0.4."""
    SYMBOLS = ["A", "B", "C", "D", "E"]
    OPEN_PRICE = 1000.0

    ps = replace(base_ps, max_positions=5, rebalance_frequency="daily")
    strategy = _build_mock_strategy(ps)
    strategy.universe.select.return_value = SYMBOLS
    strategy.signal_gen.generate.side_effect = lambda ctx, sym, p: "BUY"
    strategy.scorer.score.side_effect = lambda ctx, sym, p: {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}[sym]

    # 첫날만 BUY되도록 holding_cap: 두번째날부터 force_exit → 다음날 SELL
    call_counts: dict[str, int] = {}

    def force_exit_side_effect(pos_dict, d, p):
        sym = pos_dict["symbol"]
        call_counts[sym] = call_counts.get(sym, 0) + 1
        return call_counts[sym] >= 1  # 첫 체크에서 바로 청산 예약

    strategy.holding_cap.should_force_exit_by_age.side_effect = force_exit_side_effect

    # high_low 설정: A, B만 +6% (≥+5%) → precision hit
    # C, D, E는 +4% (< +5%) → precision miss
    def read_high_low_side_effect(symbol, date):
        if symbol in ("A", "B"):
            return (OPEN_PRICE * 1.06, OPEN_PRICE * 0.95)
        return (OPEN_PRICE * 1.04, OPEN_PRICE * 0.95)

    mock_reader = MagicMock()
    mock_reader.read_open.return_value = OPEN_PRICE
    mock_reader.read_high_low.side_effect = read_high_low_side_effect
    mock_reader.read_daily.return_value = _make_df(_DATES, close=OPEN_PRICE)

    mock_ce = MagicMock()
    mock_ce.is_administrative.return_value = False
    mock_ce.is_halted.return_value = False
    mock_ce.filter_universe.side_effect = lambda codes, d: codes

    with patch("RoboTrader_template.multiverse.engine.portfolio_engine.pit_reader", mock_reader), \
         patch("RoboTrader_template.multiverse.engine.portfolio_engine._corp_events", mock_ce):
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=SYMBOLS,
            start_date=_DATES[0],
            end_date=_DATES[-1],
            initial_capital=10_000_000.0,
        )

    buys = [t for t in result.trades if t.side == "BUY"]
    assert len(buys) >= 5, f"BUY 최소 5건 기대, 실제 {len(buys)}건"
    # A, B는 항상 precision hit (+6%), C/D/E는 항상 miss (+4%)
    # 비율은 심볼별로 같은 횟수 매수되므로 항상 2/5 = 0.4
    assert abs(result.precision - 0.4) < 1e-9, (
        f"precision 기대 0.4, 실제 {result.precision}"
    )


# ================================================================== #
# M2 — expectancy: 합성 거래 평균 손익 검증
# ================================================================== #

def test_m2_expectancy_calculation(base_ps):
    """1종목 BUY→SELL, 손익이 정확히 계산되는지 검증."""
    OPEN_PRICE = 1000.0
    QTY = 10
    # BUY: exec_price = 1000*(1+50bp) = 1005, fee = 1005*10*15bp = 15.075
    # SELL: exec_price = 1000*(1-50bp) = 995, fee = 995*10*245bp = 243.775
    # realized_pnl = (995*10 - 243.775) - (1005*10 + 15.075)
    #              = (9950 - 243.775) - (10050 + 15.075)
    #              = 9706.225 - 10065.075 = -358.85
    BUY_FEE_BPS = 15
    SELL_FEE_BPS = 245
    SLIP_BPS = 50  # non-top30

    buy_exec = OPEN_PRICE * (1 + SLIP_BPS / 10000)
    sell_exec = OPEN_PRICE * (1 - SLIP_BPS / 10000)
    buy_fee = buy_exec * QTY * (BUY_FEE_BPS / 10000)
    sell_fee = sell_exec * QTY * (SELL_FEE_BPS / 10000)
    expected_pnl = (sell_exec * QTY - sell_fee) - (buy_exec * QTY + buy_fee)

    ps = replace(base_ps, max_positions=1, rebalance_frequency="daily")
    strategy = _build_mock_strategy(ps, signal_sym="A")

    # 첫날 BUY 체결, 두번째날 holding_cap → SELL
    call_count = [0]

    def force_exit(pos_dict, d, p):
        call_count[0] += 1
        return call_count[0] >= 1

    strategy.holding_cap.should_force_exit_by_age.side_effect = force_exit

    mock_reader = MagicMock()
    mock_reader.read_open.return_value = OPEN_PRICE
    mock_reader.read_high_low.return_value = (OPEN_PRICE * 1.02, OPEN_PRICE * 0.98)
    mock_reader.read_daily.return_value = _make_df(_DATES, close=OPEN_PRICE)

    mock_ce = MagicMock()
    mock_ce.is_administrative.return_value = False
    mock_ce.is_halted.return_value = False
    mock_ce.filter_universe.side_effect = lambda codes, d: codes

    with patch("RoboTrader_template.multiverse.engine.portfolio_engine.pit_reader", mock_reader), \
         patch("RoboTrader_template.multiverse.engine.portfolio_engine._corp_events", mock_ce):
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=["A"],
            start_date=_DATES[0],
            end_date=_DATES[-1],
            initial_capital=1_000_000.0,
        )

    sells = [t for t in result.trades if t.side == "SELL"]
    assert len(sells) >= 1, "SELL 체결 없음 — expectancy 계산 불가"
    assert abs(result.expectancy - expected_pnl) < 1.0, (
        f"expectancy 기대 {expected_pnl:.2f}, 실제 {result.expectancy:.2f}"
    )


# ================================================================== #
# M3 — 거래 0건일 때 precision=0.0, expectancy=0.0
# ================================================================== #

def test_m3_zero_trades_defaults(base_ps):
    """BUY 신호 없음 → 거래 0건 → precision=0.0, expectancy=0.0."""
    ps = replace(base_ps, max_positions=1, rebalance_frequency="daily")
    strategy = _build_mock_strategy(ps, signal_sym="A")
    strategy.signal_gen.generate.return_value = "HOLD"  # 신호 없음

    mock_reader = MagicMock()
    mock_reader.read_open.return_value = 1000.0
    mock_reader.read_high_low.return_value = (1060.0, 950.0)
    mock_reader.read_daily.return_value = _make_df(_DATES)

    mock_ce = MagicMock()
    mock_ce.is_administrative.return_value = False
    mock_ce.is_halted.return_value = False
    mock_ce.filter_universe.side_effect = lambda codes, d: codes

    with patch("RoboTrader_template.multiverse.engine.portfolio_engine.pit_reader", mock_reader), \
         patch("RoboTrader_template.multiverse.engine.portfolio_engine._corp_events", mock_ce):
        result = run_portfolio_backtest(
            strategy=strategy,
            candidate_symbols=["A"],
            start_date=_DATES[0],
            end_date=_DATES[-1],
            initial_capital=1_000_000.0,
        )

    assert result.precision == 0.0, f"거래 0건인데 precision={result.precision}"
    assert result.expectancy == 0.0, f"거래 0건인데 expectancy={result.expectancy}"


# ================================================================== #
# M4 — PortfolioBacktestResult 기본값 0.0 확인
# ================================================================== #

def test_m4_dataclass_defaults():
    """PortfolioBacktestResult에 precision/expectancy 기본값 0.0이 있어야 한다."""
    result = PortfolioBacktestResult(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        initial_capital=1_000_000.0,
        final_equity=1_000_000.0,
        daily_equity=[],
        trades=[],
        skipped_signals=[],
        rebalance_dates=[],
        paramset_id="test",
        paused_until=None,
    )
    assert result.precision == 0.0
    assert result.expectancy == 0.0
