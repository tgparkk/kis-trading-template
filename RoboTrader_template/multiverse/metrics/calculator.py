"""성과 지표 계산 모듈.

compute_metrics(daily_equity, trades, initial_capital) → Metrics
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class Metrics:
    cagr: float
    mdd: float            # 0~1 (양수, abs)
    sharpe: float
    sortino: float
    calmar: float         # CAGR / MDD
    profit_factor: float
    win_rate: float       # 0~1
    volatility: float     # annualized
    avg_hold_days: float
    turnover: float       # sum(buy_value) / avg_equity (annualized)
    tuw_days: int         # Time Under Water
    return_skew: float
    return_kurt: float    # excess kurtosis
    tail_ratio: float     # |p95| / |p5|


_ZERO_METRICS = Metrics(
    cagr=0.0, mdd=0.0, sharpe=0.0, sortino=0.0, calmar=0.0,
    profit_factor=0.0, win_rate=0.0, volatility=0.0, avg_hold_days=0.0,
    turnover=0.0, tuw_days=0, return_skew=0.0, return_kurt=0.0, tail_ratio=0.0,
)


def _safe_float(v: float) -> float:
    """NaN/Inf → 0.0."""
    if not math.isfinite(v):
        return 0.0
    return float(v)


def _pair_trades(trades: list) -> List[Tuple]:
    """BUY-SELL FIFO 페어링.

    같은 종목 그룹에서 첫 BUY → 첫 SELL 순서로 매칭.
    Trade는 multiverse.engine.pit_engine.Trade 혹은 동일 필드(date, side, price, qty, fee)를 가진 객체.
    미매칭 거래는 무시.

    Returns
    -------
    list of (buy_trade, sell_trade)
    """
    # 종목 구분 없이(단일 종목 엔진 기준) BUY/SELL 순서대로 매칭
    buys = [t for t in trades if t.side == "BUY"]
    sells = [t for t in trades if t.side == "SELL"]

    pairs = []
    for buy, sell in zip(buys, sells):
        pairs.append((buy, sell))
    return pairs


def compute_metrics(
    daily_equity: List[Tuple[date, float]],
    trades: list,
    initial_capital: float,
    risk_free_annual: float = 0.0,
    trading_days_per_year: int = 252,
) -> Metrics:
    """모든 지표 계산.

    daily_equity가 비었거나 1개면 0.0 보호.
    """
    # ------------------------------------------------------------------
    # 빈 케이스 가드
    # ------------------------------------------------------------------
    if len(daily_equity) < 2:
        return _ZERO_METRICS

    equities = np.array([e for _, e in daily_equity], dtype=float)
    n = len(equities)

    # ------------------------------------------------------------------
    # 일간 수익률 (첫날 r=0)
    # ------------------------------------------------------------------
    returns = np.zeros(n, dtype=float)
    returns[1:] = equities[1:] / equities[:-1] - 1.0

    rf_daily = (1 + risk_free_annual) ** (1 / trading_days_per_year) - 1

    # ------------------------------------------------------------------
    # CAGR
    # ------------------------------------------------------------------
    final_equity = equities[-1]
    if initial_capital > 0 and final_equity > 0:
        cagr = (final_equity / initial_capital) ** (trading_days_per_year / n) - 1.0
    else:
        cagr = 0.0
    cagr = _safe_float(cagr)

    # ------------------------------------------------------------------
    # MDD
    # ------------------------------------------------------------------
    peak = np.maximum.accumulate(equities)
    drawdowns = (peak - equities) / np.where(peak > 0, peak, 1.0)
    mdd = float(np.max(drawdowns))
    mdd = _safe_float(mdd)

    # ------------------------------------------------------------------
    # Sharpe
    # ------------------------------------------------------------------
    excess = returns - rf_daily
    std_all = float(np.std(returns, ddof=1)) if n > 1 else 0.0
    if std_all > 0:
        sharpe = _safe_float(float(np.mean(excess)) / std_all * math.sqrt(trading_days_per_year))
    else:
        sharpe = 0.0

    # ------------------------------------------------------------------
    # Sortino
    # ------------------------------------------------------------------
    downside = np.where(returns < 0, returns, 0.0)
    std_down = float(np.std(downside, ddof=1)) if n > 1 else 0.0
    if std_down > 0:
        sortino = _safe_float(float(np.mean(excess)) / std_down * math.sqrt(trading_days_per_year))
    else:
        sortino = 0.0

    # ------------------------------------------------------------------
    # Calmar
    # ------------------------------------------------------------------
    calmar = _safe_float(cagr / mdd) if mdd > 0 else 0.0

    # ------------------------------------------------------------------
    # Volatility (annualized)
    # ------------------------------------------------------------------
    volatility = _safe_float(std_all * math.sqrt(trading_days_per_year))

    # ------------------------------------------------------------------
    # Profit Factor / Win Rate / Avg Hold Days — trade 페어링
    # ------------------------------------------------------------------
    pairs = _pair_trades(trades)

    if pairs:
        gross_wins = 0.0
        gross_losses = 0.0
        win_count = 0
        hold_days_list = []

        for buy_t, sell_t in pairs:
            # pnl = (매도 체결액 - 매수 체결액) - (매도 수수료 + 매수 수수료)
            buy_value = buy_t.price * buy_t.qty
            sell_value = sell_t.price * sell_t.qty
            pnl = (sell_value - buy_value) - (sell_t.fee + buy_t.fee)

            if pnl > 0:
                gross_wins += pnl
                win_count += 1
            else:
                gross_losses += abs(pnl)

            # 보유기간 (거래일 단위)
            delta = (sell_t.date - buy_t.date).days
            hold_days_list.append(delta)

        profit_factor = _safe_float(gross_wins / gross_losses) if gross_losses > 0 else 0.0
        win_rate = _safe_float(win_count / len(pairs))
        avg_hold_days = _safe_float(float(np.mean(hold_days_list))) if hold_days_list else 0.0
    else:
        profit_factor = 0.0
        win_rate = 0.0
        avg_hold_days = 0.0

    # ------------------------------------------------------------------
    # Turnover (annualized)
    # ------------------------------------------------------------------
    buy_trades = [t for t in trades if t.side == "BUY"]
    total_buy_value = sum(t.price * t.qty for t in buy_trades)
    avg_equity = float(np.mean(equities)) if n > 0 else initial_capital
    if avg_equity > 0 and n > 0:
        turnover = _safe_float(total_buy_value / avg_equity * (trading_days_per_year / n))
    else:
        turnover = 0.0

    # ------------------------------------------------------------------
    # TUW (Time Under Water) — 거래일 기준
    # ------------------------------------------------------------------
    tuw_days = 0
    if mdd > 0:
        # MDD 발생 구간의 시작 peak를 찾는다.
        # drawdown[i] = (peak_until_i - equity_i) / peak_until_i
        # 최대 drawdown 위치(mdd_idx)를 구하고, 그 직전까지의 누적 peak 최고점(peak_start_idx)을 TUW 시작으로 삼는다.
        mdd_idx = int(np.argmax(drawdowns))
        # mdd_idx 직전 구간에서 누적 peak에 해당하는 마지막 인덱스
        peak_start_idx = int(np.argmax(equities[: mdd_idx + 1]))
        peak_val = equities[peak_start_idx]
        recovered = False
        for i in range(peak_start_idx + 1, n):
            if equities[i] >= peak_val:
                tuw_days = i - peak_start_idx
                recovered = True
                break
        if not recovered:
            tuw_days = n - 1 - peak_start_idx

    # ------------------------------------------------------------------
    # Skewness / Kurtosis
    # ------------------------------------------------------------------
    try:
        from scipy.stats import skew as _skew, kurtosis as _kurt  # type: ignore
        if n > 3:
            return_skew = _safe_float(float(_skew(returns, bias=False)))
            return_kurt = _safe_float(float(_kurt(returns, fisher=True, bias=False)))
        else:
            return_skew = 0.0
            return_kurt = 0.0
    except ImportError:
        return_skew = 0.0
        return_kurt = 0.0

    # ------------------------------------------------------------------
    # Tail Ratio
    # ------------------------------------------------------------------
    if n > 10:
        p95 = float(np.percentile(returns, 95))
        p5 = float(np.percentile(returns, 5))
        if abs(p5) > 0:
            tail_ratio = _safe_float(abs(p95) / abs(p5))
        else:
            tail_ratio = 0.0
    else:
        tail_ratio = 0.0

    return Metrics(
        cagr=cagr,
        mdd=mdd,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        profit_factor=profit_factor,
        win_rate=win_rate,
        volatility=volatility,
        avg_hold_days=avg_hold_days,
        turnover=turnover,
        tuw_days=tuw_days,
        return_skew=return_skew,
        return_kurt=return_kurt,
        tail_ratio=tail_ratio,
    )
