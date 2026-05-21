"""토너먼트 평가 지표 계산 (BacktestResult → metrics dict).

BacktestResult.daily_pnl 필드가 없으므로 trades 리스트에서
일별 pnl을 합산하여 daily_pnl 시리즈를 재구성합니다.

Public API:
    compute_metrics(result, initial_capital) -> dict   # 8종 지표
    _rank_by_composite(df)                             # 합격선 + 종합점수 정렬
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _build_daily_pnl(result: Any) -> pd.Series:
    """trades 리스트에서 exit_date별 pnl 합계 Series를 구성.

    Returns:
        pd.Series, index=exit_date(str), values=pnl(float).
        거래가 없으면 빈 Series 반환.
    """
    trades = getattr(result, "trades", None) or []
    if not trades:
        return pd.Series(dtype=float)

    daily: Dict[str, float] = defaultdict(float)
    for t in trades:
        # exit_date 키 탐색 (exit_date 또는 entry_date fallback)
        date_key = t.get("exit_date") or t.get("entry_date") or ""
        if not date_key:
            continue
        pnl = float(t.get("pnl", 0.0))
        daily[date_key] += pnl

    if not daily:
        return pd.Series(dtype=float)

    series = pd.Series(daily).sort_index()
    return series


def _equity_daily_returns(result: Any) -> pd.Series:
    """equity_curve(List[float])에서 일별 수익률 Series를 구성.

    Returns:
        pd.Series, values=일별 수익률(소수점, 예 0.012 = +1.2%).
        데이터 부족 시 빈 Series.
    """
    curve = getattr(result, "equity_curve", None) or []
    if len(curve) < 2:
        return pd.Series(dtype=float)
    arr = np.array(curve, dtype=float)
    daily_ret = np.diff(arr) / arr[:-1]
    return pd.Series(daily_ret)


def _zero_metrics() -> Dict[str, Any]:
    """결과가 None이거나 거래/데이터가 없을 때 반환하는 기본값 dict."""
    return dict(
        avg_daily_return_pct=0.0,
        win_rate_pct=0.0,
        calmar=0.0,
        sortino=0.0,
        mdd_pct=0.0,
        max_daily_loss_pct=0.0,
        total_pnl_pct=0.0,
        trade_count=0,
    )


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def compute_metrics(result: Any, initial_capital: float) -> Dict[str, Any]:
    """BacktestResult → 평가 지표 dict.

    필수 키 (8종):
      avg_daily_return_pct : 평균 일일수익률 (%)
      win_rate_pct         : 일승률 — pnl > 0인 거래일 비율 (%)
      calmar               : 연환산수익률 / |MDD|
      sortino              : 연환산수익률 / 하방표준편차 (연율화)
      mdd_pct              : 최대낙폭 (%, 음수, 예 -15.0)
      max_daily_loss_pct   : 최대 단일 거래일 손실 (%, 음수)
      total_pnl_pct        : 누적 수익률 (%)
      trade_count          : 총 거래 수 (매수→매도 쌍)

    Args:
        result:          BacktestResult 인스턴스 (또는 None).
        initial_capital: 초기 자본금 (원).

    Returns:
        8종 지표 dict.
    """
    if result is None:
        return _zero_metrics()

    initial_capital = float(initial_capital)
    if initial_capital <= 0:
        return _zero_metrics()

    # ── equity_curve 기반 지표 ────────────────────────────────────────────
    curve = getattr(result, "equity_curve", None) or []
    if len(curve) < 2:
        return _zero_metrics()

    arr = np.array(curve, dtype=float)
    final_equity = float(arr[-1])

    # 총 수익률
    total_pnl_pct = (final_equity - initial_capital) / initial_capital * 100.0

    # MDD (equity_curve 기반, 음수로 반환)
    peak = np.maximum.accumulate(arr)
    drawdown = (arr - peak) / peak * 100.0  # 음수
    mdd_pct = float(np.min(drawdown))       # 가장 큰 음수

    # 일별 수익률 (equity_curve 차분)
    daily_ret = np.diff(arr) / arr[:-1] * 100.0  # %
    daily_ret_series = pd.Series(daily_ret)

    avg_daily_return_pct = float(daily_ret_series.mean())
    max_daily_loss_pct = float(daily_ret_series.min())

    # ── 거래 기반 지표 ────────────────────────────────────────────────────
    trades: List[Dict] = getattr(result, "trades", None) or []
    trade_count = len(trades)

    # 일승률: 거래가 있는 날 중 pnl > 0인 날 비율
    # equity_curve 기반 일승률 (daily_ret > 0)
    if len(daily_ret_series) > 0:
        win_rate_pct = float((daily_ret_series > 0).sum() / len(daily_ret_series) * 100.0)
    else:
        win_rate_pct = 0.0

    # ── Calmar ────────────────────────────────────────────────────────────
    n_days = len(curve) - 1  # 실제 경과 일수
    if n_days > 0 and abs(mdd_pct) > 1e-9:
        years = n_days / 252.0
        total_return_frac = total_pnl_pct / 100.0
        # CAGR (복리 연환산)
        cagr_pct = ((1.0 + total_return_frac) ** (1.0 / years) - 1.0) * 100.0
        calmar = cagr_pct / abs(mdd_pct)
    else:
        calmar = 0.0

    # ── Sortino ───────────────────────────────────────────────────────────
    downside = daily_ret_series[daily_ret_series < 0]
    annual_return_pct = avg_daily_return_pct * 252.0
    if len(downside) >= 2:
        downside_std = float(downside.std())
        if downside_std > 1e-9:
            sortino = annual_return_pct / (downside_std * math.sqrt(252))
        else:
            sortino = 0.0
    else:
        sortino = 0.0

    return dict(
        avg_daily_return_pct=round(avg_daily_return_pct, 6),
        win_rate_pct=round(win_rate_pct, 4),
        calmar=round(calmar, 4),
        sortino=round(sortino, 4),
        mdd_pct=round(mdd_pct, 4),
        max_daily_loss_pct=round(max_daily_loss_pct, 4),
        total_pnl_pct=round(total_pnl_pct, 4),
        trade_count=trade_count,
    )


def _rank_by_composite(df: pd.DataFrame) -> pd.DataFrame:
    """합격선 필터 + 종합 점수 계산 후 내림차순 정렬.

    합격 기준 (사장님 결재 — 균형):
        avg_daily_return_pct >= 0.3
        win_rate_pct         >= 50.0
        mdd_pct              >= -15.0  (손실 폭이 -15% 이내)

    종합 점수:
        0.4 × z(avg_daily_return_pct)
      + 0.3 × z(win_rate_pct)
      + 0.3 × z(calmar)

    Returns:
        'pass', 'composite_score', 'rank' 컬럼이 추가된 DataFrame.
        composite_score 내림차순 정렬, rank는 1부터.
    """
    df = df.copy()

    # 합격선
    df["pass"] = (
        (df["avg_daily_return_pct"] >= 0.3)
        & (df["win_rate_pct"] >= 50.0)
        & (df["mdd_pct"] >= -15.0)
    )

    # z-score 정규화 헬퍼
    def _z(col: str) -> pd.Series:
        s = df[col].astype(float)
        std = s.std()
        # NaN(단일 행 포함) 또는 std≈0 → 모두 0으로 처리
        if std is None or (isinstance(std, float) and math.isnan(std)) or std < 1e-9:
            return pd.Series(0.0, index=s.index)
        return (s - s.mean()) / std

    df["z_daily_return"] = _z("avg_daily_return_pct")
    df["z_win_rate"] = _z("win_rate_pct")
    df["z_calmar"] = _z("calmar")

    df["composite_score"] = (
        0.4 * df["z_daily_return"]
        + 0.3 * df["z_win_rate"]
        + 0.3 * df["z_calmar"]
    )

    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df
