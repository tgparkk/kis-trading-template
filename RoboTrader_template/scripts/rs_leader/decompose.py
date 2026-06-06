"""거래의 국면별 분해 + 소표본 통계 (검증 스파이크 분석층).

- decompose_trades_by_regime: run_portfolio trades(sell)를 진입일 국면라벨로 그룹화.
- episode_stats: 특정 날짜 구간(약세장 에피소드)으로 거래 필터 후 통계.
- probabilistic_sharpe_ratio: 표본길이·왜도·첨도 반영 PSR(소표본 적합, Bailey-LdP).
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import NormalDist
from typing import Dict, List

import pandas as pd


def _stats(pnls: List[float]) -> dict:
    s = pd.Series(pnls, dtype=float)
    return {
        "n": int(s.size),
        "mean_pnl": float(s.mean()) if s.size else 0.0,
        "median_pnl": float(s.median()) if s.size else 0.0,
        "win_rate": float((s > 0).mean()) if s.size else 0.0,
    }


def decompose_trades_by_regime(
    trades: List[dict], regime_map: Dict[pd.Timestamp, str]
) -> Dict[str, dict]:
    """sell 거래를 진입일(entry_date) 국면 라벨로 그룹화해 그룹별 통계 반환."""
    buckets: Dict[str, List[float]] = defaultdict(list)
    for t in trades:
        if t.get("side") != "sell":
            continue
        ed = pd.Timestamp(t["entry_date"]).normalize()
        regime = regime_map.get(ed, "unknown")
        buckets[regime].append(float(t["pnl_pct"]))
    return {reg: _stats(p) for reg, p in buckets.items()}


def episode_stats(trades: List[dict], start: str, end: str) -> dict:
    """진입일이 [start, end] 인 sell 거래만의 통계 (약세장 에피소드 OOS용)."""
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    pnls = [
        float(t["pnl_pct"]) for t in trades
        if t.get("side") == "sell" and lo <= pd.Timestamp(t["entry_date"]).normalize() <= hi
    ]
    return _stats(pnls)


def probabilistic_sharpe_ratio(
    sharpe: float, n: int, skew: float = 0.0, kurt: float = 3.0, benchmark: float = 0.0
) -> float:
    """PSR = Prob(true Sharpe > benchmark). sharpe/benchmark 는 동일 주기 기준.

    소표본·비정규성 반영(Bailey & López de Prado 2012). n<=1 이면 0.5 반환.
    """
    if n <= 1:
        return 0.5
    denom = math.sqrt(1.0 - skew * sharpe + (kurt - 1.0) / 4.0 * sharpe ** 2)
    if denom <= 0:
        return 0.5
    z = (sharpe - benchmark) * math.sqrt(n - 1) / denom
    return float(NormalDist().cdf(z))
