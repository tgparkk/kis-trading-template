"""
Regime Analysis
===============

KOSPI 시장국면(BULL / BEAR / SIDEWAYS)을 분류하고,
백테스트 결과를 국면별로 분해하는 순수 함수 모음.

설계 원칙:
- DB 호출 없음 — KOSPI 시계열 fetch는 호출자 책임.
- BacktestResult 재계산 시 calmar_ratio / sortino_ratio 포함 (B3 호환).

Usage:
    import pandas as pd
    from backtest.regime_analysis import (
        MarketRegime,
        classify_regime,
        classify_regime_rolling,
        analyze_by_regime,
        regime_breakdown_summary,
    )

    # 전체 기간 국면
    regime = classify_regime(kospi_returns, threshold=0.05)

    # 일별 rolling 국면
    regime_series = classify_regime_rolling(kospi_close, window=20, threshold=0.05)

    # 국면별 BacktestResult 분해
    per_regime = analyze_by_regime(backtest_result, regime_series)
    df = regime_breakdown_summary(per_regime)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from backtest.engine import BacktestResult

logger = logging.getLogger(__name__)


# ============================================================================
# 열거형
# ============================================================================

class MarketRegime(Enum):
    """시장 국면."""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"


# ============================================================================
# 국면 분류 함수
# ============================================================================

def classify_regime(
    kospi_returns: pd.Series,
    threshold: float = 0.05,
) -> MarketRegime:
    """전체 기간의 시장 국면을 누적 수익률 기준으로 분류.

    Args:
        kospi_returns: KOSPI 일별 수익률 시계열 (index=date, values=daily return).
                       예: pd.Series([0.01, -0.005, 0.02, ...])
        threshold: 누적 수익률 절대값 기준선 (기본 0.05 = ±5%).

    Returns:
        MarketRegime:
            - 누적 > +threshold  → BULL
            - 누적 < -threshold  → BEAR
            - 그 외              → SIDEWAYS

    Note:
        경계값 (누적 == ±threshold) 정책: **제외** (SIDEWAYS 처리).
        즉 BULL은 cumulative > threshold, BEAR는 cumulative < -threshold.
    """
    if kospi_returns.empty:
        return MarketRegime.SIDEWAYS

    # 누적 수익률: (1+r1)*(1+r2)*... - 1
    cumulative = float((1 + kospi_returns).prod() - 1)

    if cumulative > threshold:
        return MarketRegime.BULL
    if cumulative < -threshold:
        return MarketRegime.BEAR
    return MarketRegime.SIDEWAYS


def classify_regime_rolling(
    kospi_close: pd.Series,
    window: int = 20,
    threshold: float = 0.05,
) -> pd.Series:
    """일별 rolling N일 누적 수익률로 매일 국면을 분류.

    Args:
        kospi_close: KOSPI 종가 시계열 (index=date, values=close price).
                     날짜 오름차순 정렬 가정.
        window: rolling 윈도우 크기 (영업일 수, 기본 20).
        threshold: classify_regime()과 동일한 누적 수익률 절대값 기준선.

    Returns:
        pd.Series: index=date, values=MarketRegime enum.
                   데이터가 window보다 짧은 초기 구간은 SIDEWAYS로 채움.
    """
    if kospi_close.empty:
        return pd.Series(dtype=object)

    # rolling window 내의 누적 수익률: close[t] / close[t-window+1] - 1
    # pct_change는 1일 수익률, 누적은 rolling(window).apply(prod)로 계산
    daily_returns = kospi_close.pct_change()

    def _cum_return(window_vals: np.ndarray) -> float:
        return float((1 + window_vals).prod() - 1)

    rolling_cum = daily_returns.rolling(window=window, min_periods=window).apply(
        _cum_return, raw=True
    )

    def _to_regime(val: float) -> MarketRegime:
        if np.isnan(val):
            return MarketRegime.SIDEWAYS
        if val > threshold:
            return MarketRegime.BULL
        if val < -threshold:
            return MarketRegime.BEAR
        return MarketRegime.SIDEWAYS

    result = rolling_cum.map(_to_regime)
    return result


# ============================================================================
# 국면별 BacktestResult 분해
# ============================================================================

def analyze_by_regime(
    backtest_result: BacktestResult,
    regime_series: pd.Series,
) -> Dict[MarketRegime, Optional[BacktestResult]]:
    """BacktestResult.trades를 국면별로 분리해 각 BacktestResult를 재계산.

    Args:
        backtest_result: 전체 기간 백테스트 결과.
                         trades 각 항목에 'exit_date' 키(str "YYYY-MM-DD") 필요.
        regime_series: classify_regime_rolling() 또는 호출자가 준비한 국면 시계열.
                       index가 문자열 또는 날짜 모두 허용.

    Returns:
        {MarketRegime: BacktestResult or None} — 해당 국면에 trade가 없으면 None.

    Note:
        각 trade의 국면은 exit_date 기준으로 매핑.
        exit_date가 regime_series에 없으면 SIDEWAYS 처리 (보수적 fallback).
    """
    # regime_series index를 str(YYYY-MM-DD) 형태로 통일
    regime_index: Dict[str, MarketRegime] = {}
    for idx, val in regime_series.items():
        key = str(idx)[:10]
        regime_index[key] = val if isinstance(val, MarketRegime) else MarketRegime.SIDEWAYS

    # trade를 국면별로 분류
    regime_trades: Dict[MarketRegime, List[Dict]] = {
        MarketRegime.BULL: [],
        MarketRegime.BEAR: [],
        MarketRegime.SIDEWAYS: [],
    }

    for trade in backtest_result.trades:
        exit_date = str(trade.get("exit_date", ""))[:10]
        regime = regime_index.get(exit_date, MarketRegime.SIDEWAYS)
        regime_trades[regime].append(trade)

    result: Dict[MarketRegime, Optional[BacktestResult]] = {}
    for regime, trades in regime_trades.items():
        result[regime] = _build_result_from_trades(trades) if trades else None

    return result


def _build_result_from_trades(trades: List[Dict]) -> BacktestResult:
    """trade 리스트로 BacktestResult를 새로 계산.

    equity_curve는 trade의 pnl을 순서대로 누적해 근사 계산.
    (per-trade 손익 기준이므로 일별 equity curve와는 다를 수 있음)
    """
    n = len(trades)
    if n == 0:
        return _empty_result()

    pnl_pcts = [t.get("pnl_pct", 0.0) for t in trades]
    wins = [p for p in pnl_pcts if p > 0]
    losses = [p for p in pnl_pcts if p <= 0]

    win_rate = len(wins) / n
    avg_profit = float(np.mean(pnl_pcts))

    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = abs(float(np.mean(losses))) if losses else 0.0
    profit_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else float("inf")

    # 누적 수익률 근사: 각 거래 pnl_pct 단순 합 (자금 재투자 미적용)
    total_return = float(np.sum(pnl_pcts))

    # equity curve 근사: 기준 1.0에서 pnl_pct 순차 가산
    equity_curve = [1.0]
    for p in pnl_pcts:
        equity_curve.append(equity_curve[-1] + p)

    mdd = _calc_mdd(equity_curve)
    sharpe = _calc_sharpe(equity_curve)
    calmar = _calc_calmar(total_return, mdd, n)
    sortino = _calc_sortino(equity_curve)

    return BacktestResult(
        total_return=total_return,
        win_rate=win_rate,
        avg_profit=avg_profit,
        max_drawdown=mdd,
        sharpe_ratio=sharpe,
        calmar_ratio=calmar,
        sortino_ratio=sortino,
        profit_loss_ratio=profit_loss_ratio,
        total_trades=n,
        trades=list(trades),
        equity_curve=equity_curve,
        sells_by_reason={},
        candidate_pool_hits=0,
    )


def _empty_result() -> BacktestResult:
    return BacktestResult(
        total_return=0.0,
        win_rate=0.0,
        avg_profit=0.0,
        max_drawdown=0.0,
        sharpe_ratio=0.0,
        calmar_ratio=0.0,
        sortino_ratio=0.0,
        profit_loss_ratio=0.0,
        total_trades=0,
        trades=[],
        equity_curve=[],
        sells_by_reason={},
        candidate_pool_hits=0,
    )


# ============================================================================
# 지표 계산 (BacktestEngine._calc_* 와 동일 로직, 독립 복사)
# ============================================================================

def _calc_mdd(equity_curve: List[float]) -> float:
    if len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve, dtype=float)
    peak = np.maximum.accumulate(arr)
    drawdowns = (peak - arr) / np.where(peak == 0, 1.0, peak)
    return float(np.max(drawdowns))


def _calc_sharpe(equity_curve: List[float], risk_free_rate: float = 0.0) -> float:
    if len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve, dtype=float)
    daily_returns = np.diff(arr) / np.where(arr[:-1] == 0, 1.0, arr[:-1])
    excess = daily_returns - risk_free_rate / 252
    std = excess.std()
    if std == 0:
        return 0.0
    return float(excess.mean() / std * np.sqrt(252))


def _calc_calmar(total_return: float, mdd: float, n_trades: int) -> float:
    if mdd <= 0 or n_trades <= 0:
        return 0.0
    years = n_trades / 252.0
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0
    return float(cagr / mdd)


def _calc_sortino(equity_curve: List[float], risk_free_rate: float = 0.0) -> float:
    if len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve, dtype=float)
    daily_returns = np.diff(arr) / np.where(arr[:-1] == 0, 1.0, arr[:-1])
    excess = daily_returns - risk_free_rate / 252
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float(excess.mean() * np.sqrt(252)) if excess.mean() > 0 else 0.0
    downside_std = float(np.std(downside))
    if downside_std == 0:
        return 0.0
    return float(excess.mean() / downside_std * np.sqrt(252))


# ============================================================================
# 요약 DataFrame
# ============================================================================

def regime_breakdown_summary(
    per_regime: Dict[MarketRegime, Optional[BacktestResult]],
) -> pd.DataFrame:
    """국면별 요약 DataFrame 반환.

    Args:
        per_regime: analyze_by_regime() 반환값.

    Returns:
        pd.DataFrame with columns:
            regime, n_trades, total_return, win_rate, calmar_ratio,
            sortino_ratio, sharpe_ratio, max_drawdown, profit_loss_ratio
    """
    rows = []
    for regime in [MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS]:
        res = per_regime.get(regime)
        if res is None:
            rows.append({
                "regime": regime.value,
                "n_trades": 0,
                "total_return": 0.0,
                "win_rate": 0.0,
                "calmar_ratio": 0.0,
                "sortino_ratio": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "profit_loss_ratio": 0.0,
            })
        else:
            rows.append({
                "regime": regime.value,
                "n_trades": res.total_trades,
                "total_return": res.total_return,
                "win_rate": res.win_rate,
                "calmar_ratio": res.calmar_ratio,
                "sortino_ratio": res.sortino_ratio,
                "sharpe_ratio": res.sharpe_ratio,
                "max_drawdown": res.max_drawdown,
                "profit_loss_ratio": res.profit_loss_ratio,
            })
    return pd.DataFrame(rows)
