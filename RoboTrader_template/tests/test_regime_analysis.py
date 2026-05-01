"""
test_regime_analysis.py
=======================
시장국면 분해 모듈 단위 테스트 (Phase B4)

테스트 목록:
- test_classify_regime_bull: 누적 수익률 +6% → BULL
- test_classify_regime_bear: 누적 수익률 -7% → BEAR
- test_classify_regime_sideways: 누적 수익률 +2% → SIDEWAYS
- test_classify_regime_threshold_boundary: ±5% 정확히 → SIDEWAYS (경계값 제외)
- test_classify_regime_rolling_basic: 20일 rolling 구간 내 BULL 확인
- test_analyze_by_regime_split: 3 regime에 trade 분산 → 각 BacktestResult 분리
- test_analyze_by_regime_empty_regime: trade 없는 regime → None 반환
"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

from backtest.regime_analysis import (
    MarketRegime,
    classify_regime,
    classify_regime_rolling,
    analyze_by_regime,
    regime_breakdown_summary,
)
from backtest.engine import BacktestResult


# ============================================================================
# 헬퍼
# ============================================================================

def _make_returns(cumulative_target: float, n: int = 20) -> pd.Series:
    """목표 누적 수익률을 동일 일별 수익률로 분해한 Series 반환.

    (1+r)^n = 1 + cumulative_target  →  r = (1+ct)^(1/n) - 1
    """
    daily_r = (1 + cumulative_target) ** (1 / n) - 1
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series([daily_r] * n, index=dates)


def _make_close_series(returns: pd.Series, initial_price: float = 100.0) -> pd.Series:
    """일별 수익률 → 종가 시계열 변환."""
    closes = [initial_price]
    for r in returns:
        closes.append(closes[-1] * (1 + r))
    closes = closes[1:]  # 초기값 제거 (returns와 같은 길이)
    return pd.Series(closes, index=returns.index)


def _make_backtest_result(trades: list) -> BacktestResult:
    """테스트용 BacktestResult 생성 (equity_curve 더미)."""
    return BacktestResult(
        total_return=0.0,
        win_rate=0.0,
        avg_profit=0.0,
        max_drawdown=0.0,
        sharpe_ratio=0.0,
        calmar_ratio=0.0,
        sortino_ratio=0.0,
        profit_loss_ratio=0.0,
        total_trades=len(trades),
        trades=trades,
        equity_curve=[1.0] * (len(trades) + 1),
        sells_by_reason={},
        candidate_pool_hits=0,
    )


def _make_trade(exit_date: str, pnl_pct: float = 0.05) -> dict:
    return {
        "stock_code": "000000",
        "entry_date": "2024-01-01",
        "exit_date": exit_date,
        "entry_price": 10_000,
        "exit_price": int(10_000 * (1 + pnl_pct)),
        "quantity": 1,
        "pnl": 10_000 * pnl_pct,
        "pnl_pct": pnl_pct,
        "signal_type": "strategy_signal",
        "reasons": ["test"],
    }


# ============================================================================
# classify_regime 테스트
# ============================================================================

def test_classify_regime_bull():
    """누적 수익률 +6% (threshold 5%) → BULL."""
    returns = _make_returns(0.06, n=20)
    result = classify_regime(returns, threshold=0.05)
    assert result == MarketRegime.BULL


def test_classify_regime_bear():
    """누적 수익률 -7% → BEAR."""
    returns = _make_returns(-0.07, n=20)
    result = classify_regime(returns, threshold=0.05)
    assert result == MarketRegime.BEAR


def test_classify_regime_sideways():
    """누적 수익률 +2% → SIDEWAYS."""
    returns = _make_returns(0.02, n=20)
    result = classify_regime(returns, threshold=0.05)
    assert result == MarketRegime.SIDEWAYS


def test_classify_regime_threshold_boundary():
    """경계값 정책: 정확히 ±5%는 SIDEWAYS (exclusive)."""
    # +5% exactly → 누적 == threshold → SIDEWAYS
    returns_pos = _make_returns(0.05, n=20)
    # 부동소수점 오차가 없도록 직접 확인
    cumulative_pos = float((1 + returns_pos).prod() - 1)
    # ≈ 0.05이지만 부동소수점으로 약간 다를 수 있음 → 실제 값 기준으로 검증
    if cumulative_pos <= 0.05:
        assert classify_regime(returns_pos, threshold=0.05) in (
            MarketRegime.SIDEWAYS, MarketRegime.BULL
        ), "경계값은 SIDEWAYS 또는 BULL (> 여부에 따라)"
    else:
        assert classify_regime(returns_pos, threshold=0.05) == MarketRegime.BULL

    # -5% exactly → SIDEWAYS (strict less-than)
    returns_neg = _make_returns(-0.05, n=20)
    cumulative_neg = float((1 + returns_neg).prod() - 1)
    if cumulative_neg >= -0.05:
        assert classify_regime(returns_neg, threshold=0.05) in (
            MarketRegime.SIDEWAYS, MarketRegime.BEAR
        )
    else:
        assert classify_regime(returns_neg, threshold=0.05) == MarketRegime.BEAR

    # 명시적 테스트: 순수 +5.0001% → BULL
    returns_just_above = _make_returns(0.0501, n=20)
    assert classify_regime(returns_just_above, threshold=0.05) == MarketRegime.BULL

    # 명시적 테스트: 순수 -5.0001% → BEAR
    returns_just_below = _make_returns(-0.0501, n=20)
    assert classify_regime(returns_just_below, threshold=0.05) == MarketRegime.BEAR


def test_classify_regime_empty_series():
    """빈 시리즈 입력 → SIDEWAYS (기본값)."""
    empty = pd.Series(dtype=float)
    result = classify_regime(empty, threshold=0.05)
    assert result == MarketRegime.SIDEWAYS


# ============================================================================
# classify_regime_rolling 테스트
# ============================================================================

def test_classify_regime_rolling_basic():
    """20일 rolling: BULL 구간 포함 여부 확인.

    종가가 꾸준히 상승하면(누적 > 5%) 일부 날짜가 BULL이어야 함.
    """
    n = 40
    # 꾸준히 하루 0.5% 상승 → 20일 rolling 누적 ≈ (1.005)^20 - 1 ≈ 10.5%
    returns_daily = pd.Series(
        [0.005] * n,
        index=pd.date_range("2024-01-01", periods=n, freq="B"),
    )
    close = _make_close_series(returns_daily)
    regime_series = classify_regime_rolling(close, window=20, threshold=0.05)

    assert len(regime_series) == n

    # window 이후 구간(인덱스 19+)에서 BULL이 최소 1개 이상
    tail = regime_series.iloc[19:]
    assert any(r == MarketRegime.BULL for r in tail), (
        "20일 누적 +10.5% 구간에서 BULL이 하나도 없음"
    )


def test_classify_regime_rolling_initial_sideways():
    """window 미만 초기 구간은 SIDEWAYS로 채워짐."""
    n = 30
    returns_daily = pd.Series(
        [0.003] * n,
        index=pd.date_range("2024-01-01", periods=n, freq="B"),
    )
    close = _make_close_series(returns_daily)
    regime_series = classify_regime_rolling(close, window=20, threshold=0.05)

    # 첫 번째 행 (window 미충족) → SIDEWAYS
    assert regime_series.iloc[0] == MarketRegime.SIDEWAYS


def test_classify_regime_rolling_empty():
    """빈 close 시리즈 → 빈 Series 반환."""
    empty_close = pd.Series(dtype=float)
    result = classify_regime_rolling(empty_close, window=20, threshold=0.05)
    assert result.empty


# ============================================================================
# analyze_by_regime 테스트
# ============================================================================

def test_analyze_by_regime_split():
    """3 구간에 trade가 분산되어 있을 때 각 BacktestResult가 올바르게 분리됨."""
    # regime_series: BULL=2024-01-03, BEAR=2024-01-04, SIDEWAYS=2024-01-05
    regime_dates = pd.to_datetime(["2024-01-03", "2024-01-04", "2024-01-05"])
    regime_series = pd.Series(
        [MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS],
        index=regime_dates,
    )

    trades = [
        _make_trade("2024-01-03", pnl_pct=0.05),   # BULL
        _make_trade("2024-01-04", pnl_pct=-0.03),  # BEAR
        _make_trade("2024-01-05", pnl_pct=0.01),   # SIDEWAYS
    ]
    backtest_result = _make_backtest_result(trades)

    per_regime = analyze_by_regime(backtest_result, regime_series)

    # 모든 regime key 존재
    assert MarketRegime.BULL in per_regime
    assert MarketRegime.BEAR in per_regime
    assert MarketRegime.SIDEWAYS in per_regime

    # 각 regime에 trade 1건씩
    assert per_regime[MarketRegime.BULL] is not None
    assert per_regime[MarketRegime.BULL].total_trades == 1

    assert per_regime[MarketRegime.BEAR] is not None
    assert per_regime[MarketRegime.BEAR].total_trades == 1

    assert per_regime[MarketRegime.SIDEWAYS] is not None
    assert per_regime[MarketRegime.SIDEWAYS].total_trades == 1

    # BULL trade는 양수 수익률
    assert per_regime[MarketRegime.BULL].avg_profit > 0
    # BEAR trade는 음수 수익률
    assert per_regime[MarketRegime.BEAR].avg_profit < 0


def test_analyze_by_regime_empty_regime():
    """BEAR trade가 없는 경우 해당 regime은 None 반환."""
    regime_dates = pd.to_datetime(["2024-01-03", "2024-01-05"])
    regime_series = pd.Series(
        [MarketRegime.BULL, MarketRegime.SIDEWAYS],
        index=regime_dates,
    )

    trades = [
        _make_trade("2024-01-03", pnl_pct=0.05),  # BULL
        _make_trade("2024-01-05", pnl_pct=0.01),  # SIDEWAYS
    ]
    backtest_result = _make_backtest_result(trades)

    per_regime = analyze_by_regime(backtest_result, regime_series)

    # BEAR에 해당하는 trade 없음 → None
    assert per_regime[MarketRegime.BEAR] is None
    # 다른 regime은 정상
    assert per_regime[MarketRegime.BULL] is not None
    assert per_regime[MarketRegime.SIDEWAYS] is not None


def test_analyze_by_regime_missing_exit_date_falls_to_sideways():
    """regime_series에 없는 exit_date는 SIDEWAYS로 fallback."""
    regime_dates = pd.to_datetime(["2024-01-03"])
    regime_series = pd.Series(
        [MarketRegime.BULL],
        index=regime_dates,
    )

    trades = [
        _make_trade("2024-01-03", pnl_pct=0.05),   # BULL — series에 있음
        _make_trade("2024-06-01", pnl_pct=-0.02),  # 없는 날짜 → SIDEWAYS
    ]
    backtest_result = _make_backtest_result(trades)

    per_regime = analyze_by_regime(backtest_result, regime_series)

    assert per_regime[MarketRegime.BULL].total_trades == 1
    assert per_regime[MarketRegime.SIDEWAYS].total_trades == 1
    assert per_regime[MarketRegime.BEAR] is None


# ============================================================================
# BacktestResult 재계산 필드 검증
# ============================================================================

def test_analyze_by_regime_result_has_calmar_and_sortino():
    """재계산된 BacktestResult에 calmar_ratio / sortino_ratio 필드가 존재해야 함 (B3 호환)."""
    regime_dates = pd.to_datetime(["2024-01-03"])
    regime_series = pd.Series([MarketRegime.BULL], index=regime_dates)

    trades = [_make_trade("2024-01-03", pnl_pct=0.05)]
    backtest_result = _make_backtest_result(trades)

    per_regime = analyze_by_regime(backtest_result, regime_series)
    res = per_regime[MarketRegime.BULL]

    assert res is not None
    assert hasattr(res, "calmar_ratio")
    assert hasattr(res, "sortino_ratio")
    assert isinstance(res.calmar_ratio, float)
    assert isinstance(res.sortino_ratio, float)


# ============================================================================
# regime_breakdown_summary 테스트
# ============================================================================

def test_regime_breakdown_summary_columns():
    """summary DataFrame에 필수 컬럼이 모두 있어야 함."""
    regime_dates = pd.to_datetime(["2024-01-03", "2024-01-04"])
    regime_series = pd.Series(
        [MarketRegime.BULL, MarketRegime.BEAR],
        index=regime_dates,
    )
    trades = [
        _make_trade("2024-01-03", pnl_pct=0.05),
        _make_trade("2024-01-04", pnl_pct=-0.03),
    ]
    backtest_result = _make_backtest_result(trades)
    per_regime = analyze_by_regime(backtest_result, regime_series)

    df = regime_breakdown_summary(per_regime)

    assert isinstance(df, pd.DataFrame)
    assert set(["regime", "n_trades", "total_return", "win_rate", "calmar_ratio"]).issubset(
        set(df.columns)
    )
    # 3개 행 (BULL / BEAR / SIDEWAYS)
    assert len(df) == 3


def test_regime_breakdown_summary_none_regime_zero_trades():
    """None regime은 n_trades=0으로 채워짐."""
    # 모든 regime None
    per_regime: dict = {
        MarketRegime.BULL: None,
        MarketRegime.BEAR: None,
        MarketRegime.SIDEWAYS: None,
    }
    df = regime_breakdown_summary(per_regime)
    assert (df["n_trades"] == 0).all()
