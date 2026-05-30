"""동적 자산배분 백테스터 (월간 리밸런싱, 연속 비중).

systrader79 평균모멘텀스코어처럼 "위험자산에 몇 % 노출할까"(연속 비중)를
표현하는 시계열 모멘텀/자산배분 전략 전용 시뮬레이터.

기존 `book_backtester`(종목별 독립계좌·이진 풀인/풀아웃)와 구조가 다르다:
- 출력이 종목 리스트가 아니라 **자산별 연속 비중 벡터** w[m].
- 단일 포트폴리오 equity 를 비중×수익으로 직접 합성(개별 계좌 합산 ✗).
- 월간 빈도 → 연율화 상수 √12 (분봉 √(252*390) 부적합).

no-lookahead 규약: t월 말 비중 w[m] 은 t월 말까지의 종가만 사용하고
t→t+1 월 수익으로 보유한다(월말 신호 → 익월 보유).

usage:
    bt = AllocationBacktester(round_trip_bps=15.0)
    result = bt.run(monthly_risk_close, weight_series, safe_rate_monthly=0.0)
    result.cagr, result.sharpe, result.max_dd_pct, ...
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

MONTHS_PER_YEAR = 12
ANNUALIZE = math.sqrt(MONTHS_PER_YEAR)


@dataclass
class AllocationBacktestResult:
    n_months: int
    final_return_pct: float          # 누적 수익률 (소수, 0.5 = +50%)
    cagr: float
    sharpe: float                    # 월수익 기준 √12 연율화
    sortino: float
    max_dd_pct: float
    calmar: float
    avg_risk_weight: float           # 위험자산 평균 노출 비중
    turnover_total: float            # 누적 회전율 (왕복 비중변화 합)
    equity_curve: List[float] = field(default_factory=list)
    dates: List[pd.Timestamp] = field(default_factory=list)
    monthly_returns: List[float] = field(default_factory=list)
    weights: List[float] = field(default_factory=list)


def resample_month_end(daily_close: pd.Series) -> pd.Series:
    """일봉 종가 → 월말 종가 시계열 (영업일 월말의 마지막 종가)."""
    s = daily_close.sort_index()
    return s.resample("ME").last().dropna()


def _annualized_metrics(
    initial: float,
    equity: np.ndarray,
    monthly_rets: np.ndarray,
    dates: List[pd.Timestamp],
) -> Dict[str, float]:
    """월간 equity/수익으로 CAGR·Sharpe·Sortino·MaxDD·Calmar 산출."""
    final = float(equity[-1])
    total_ret = (final - initial) / initial

    n_months = len(monthly_rets)
    years = n_months / MONTHS_PER_YEAR if n_months > 0 else 0.0
    cagr = ((final / initial) ** (1.0 / years) - 1.0) if years > 0 and final > 0 else 0.0

    if len(monthly_rets) > 1 and monthly_rets.std() > 0:
        sharpe = float(monthly_rets.mean() / monthly_rets.std() * ANNUALIZE)
    else:
        sharpe = 0.0

    downside = monthly_rets[monthly_rets < 0]
    if len(downside) > 1 and downside.std() > 0:
        sortino = float(monthly_rets.mean() / downside.std() * ANNUALIZE)
    else:
        sortino = 0.0

    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd_pct = float(-dd.min()) if len(dd) else 0.0
    calmar = float(cagr / max_dd_pct) if max_dd_pct > 1e-9 else 0.0

    return dict(
        final_return_pct=total_ret,
        cagr=cagr,
        sharpe=sharpe,
        sortino=sortino,
        max_dd_pct=max_dd_pct,
        calmar=calmar,
    )


class AllocationBacktester:
    """단일 위험자산 + 안전자산(현금) 동적 비중 백테스터.

    MVP: 위험자산 1개(KOSPI) 비중 w_risk[m], 안전자산 비중 1-w_risk[m].
    equity[m+1] = equity[m] * (1 + w_risk[m]*ret_risk[m→m+1]
                                  + (1-w_risk[m])*safe_rate - rebal_cost)
    리밸런싱 비용: turnover = Σ|w_target - w_drift| × round_trip_bps.
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        round_trip_bps: float = 15.0,
        safe_rate_annual: float = 0.0,
    ):
        self.initial_capital = float(initial_capital)
        self.round_trip_bps = float(round_trip_bps)
        self.safe_rate_annual = float(safe_rate_annual)

    def run(
        self,
        monthly_risk_close: pd.Series,
        weight_series: pd.Series,
        safe_rate_monthly: Optional[float] = None,
    ) -> AllocationBacktestResult:
        """월간 백테스트.

        monthly_risk_close: 월말 위험자산 종가 (index=월말 Timestamp).
        weight_series: 월말 위험자산 목표비중 w_risk[m] (index=월말 Timestamp,
            0~1). no-lookahead 책임은 호출자(전략)에 있다 — 이 함수는
            w[m] 을 m→m+1 수익에 적용한다(시점규약 강제).
        safe_rate_monthly: 월 안전자산 수익률. None 이면 safe_rate_annual/12.
        """
        if safe_rate_monthly is None:
            safe_rate_monthly = self.safe_rate_annual / MONTHS_PER_YEAR

        close = monthly_risk_close.sort_index()
        w = weight_series.sort_index()

        # 비중이 정의된 월말부터, 다음 월 수익이 존재하는 구간만 보유.
        common = w.index.intersection(close.index)
        common = common.sort_values()
        if len(common) < 2:
            return _empty_result()

        bps = self.round_trip_bps / 10_000.0
        equity = self.initial_capital
        equity_curve: List[float] = [equity]
        eq_dates: List[pd.Timestamp] = [common[0]]
        monthly_rets: List[float] = []
        weights_applied: List[float] = []
        turnover_total = 0.0
        w_drift = 0.0  # 직전 보유기간 말 위험자산 비중(드리프트 후)

        for i in range(len(common) - 1):
            m = common[i]
            m_next = common[i + 1]
            w_target = float(np.clip(w.loc[m], 0.0, 1.0))

            # 리밸런싱 비용: 목표비중과 드리프트 비중 차이 → 회전율.
            # 위험자산 한쪽만 거래해도 현금쪽이 반대로 움직이므로
            # |Δw_risk| 가 한 자산의 단방향 거래량(=왕복비용 기준).
            turnover = abs(w_target - w_drift)
            turnover_total += turnover
            cost = turnover * bps

            p0 = float(close.loc[m])
            p1 = float(close.loc[m_next])
            ret_risk = (p1 - p0) / p0

            port_ret = w_target * ret_risk + (1.0 - w_target) * safe_rate_monthly - cost
            equity *= (1.0 + port_ret)

            # 보유 후 위험자산 비중 드리프트(가치 변동으로 비중이 이동).
            risk_val = w_target * (1.0 + ret_risk)
            safe_val = (1.0 - w_target) * (1.0 + safe_rate_monthly)
            tot = risk_val + safe_val
            w_drift = risk_val / tot if tot > 0 else w_target

            monthly_rets.append(port_ret)
            weights_applied.append(w_target)
            equity_curve.append(equity)
            eq_dates.append(m_next)

        eq = np.array(equity_curve, dtype=float)
        rets = np.array(monthly_rets, dtype=float)
        metrics = _annualized_metrics(self.initial_capital, eq, rets, eq_dates)

        return AllocationBacktestResult(
            n_months=len(rets),
            final_return_pct=metrics["final_return_pct"],
            cagr=metrics["cagr"],
            sharpe=metrics["sharpe"],
            sortino=metrics["sortino"],
            max_dd_pct=metrics["max_dd_pct"],
            calmar=metrics["calmar"],
            avg_risk_weight=float(np.mean(weights_applied)) if weights_applied else 0.0,
            turnover_total=turnover_total,
            equity_curve=list(map(float, eq.tolist())),
            dates=eq_dates,
            monthly_returns=list(map(float, rets.tolist())),
            weights=list(map(float, weights_applied)),
        )

    def run_buy_and_hold(self, monthly_risk_close: pd.Series) -> AllocationBacktestResult:
        """벤치마크: 위험자산 100% 단순보유(비중 항상 1, 리밸런싱 비용 0)."""
        close = monthly_risk_close.sort_index()
        w = pd.Series(1.0, index=close.index)
        # b&h 는 회전율 0 (최초 1회 진입만) → bps 0 으로 별도 인스턴스.
        bh = AllocationBacktester(
            initial_capital=self.initial_capital,
            round_trip_bps=0.0,
            safe_rate_annual=0.0,
        )
        return bh.run(close, w, safe_rate_monthly=0.0)


def _empty_result() -> AllocationBacktestResult:
    return AllocationBacktestResult(
        n_months=0, final_return_pct=0.0, cagr=0.0, sharpe=0.0, sortino=0.0,
        max_dd_pct=0.0, calmar=0.0, avg_risk_weight=0.0, turnover_total=0.0,
        equity_curve=[], dates=[], monthly_returns=[], weights=[],
    )
