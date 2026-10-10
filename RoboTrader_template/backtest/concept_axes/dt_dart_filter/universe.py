"""시총 조건만 뺀 daytrading 후보 재현 — 스펙 §3-2.

라이브 어댑터의 룰(15봉 고가 돌파 · 거래량 20봉 평균×2 · 양봉 · 불가능봉 가드 · 점수 = 거래량 배수)은 그대로,
`base_filter` 의 시총 조건만 뺀다. 유니버스는 시총 결측 행도 담는다(2021~2023 시총 = 결측).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

import pandas as pd

from backtest.concept_axes.candidate_ledger import run as R
from backtest.concept_axes.replayer import scan as SC
from strategies.daytrading_3methods_breakout.screener import Daytrading3MethodsBreakoutScreenerAdapter


class NoCapDaytradingAdapter(Daytrading3MethodsBreakoutScreenerAdapter):
    """시총 조건만 뺀 판 — 거래대금 ≥ 10억만 남긴다."""

    def base_filter(self, universe):
        p = self.default_params()
        return [u for u in universe if float(u.get("trading_value") or 0.0) >= p["min_trading_value"]]


def build_universe_all(px: pd.DataFrame) -> Dict[pd.Timestamp, Dict[str, Tuple[float, float]]]:
    """`replayer.loader.build_universe` 와 같되 시총 결측 행도 담는다(시총 = NaN 유지)."""
    tv = (px["close"].astype(float) * px["volume"].astype(float)).to_numpy()
    out: Dict[pd.Timestamp, Dict[str, Tuple[float, float]]] = {}
    for d, c, mc, t in zip(px["date"].to_numpy(), px["stock_code"].to_numpy(), px["market_cap"].to_numpy(), tv):
        mcf = float(mc) if mc is not None and mc == mc else float("nan")
        out.setdefault(pd.Timestamp(d), {})[str(c)] = (mcf, float(t))
    return out


def scan_window(px: pd.DataFrame, scan_days: List[pd.Timestamp]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    adapter = NoCapDaytradingAdapter()
    params = adapter.default_params()
    uni = build_universe_all(px)
    elig, info = SC.eligible_for_dates(uni, adapter, scan_days)
    ga = R.GuardedAdapter(adapter)
    ms, _dgs, _imp = SC.scan_strategy(px, {d: elig.get(d, set()) for d in scan_days}, ga, params, 60,
                                      scan_dates=scan_days, max_candidates=None, progress_every=0)
    by: Dict[pd.Timestamp, List[Dict[str, Any]]] = defaultdict(list)
    for m in ms:
        by[pd.Timestamp(m["scan_date"])].append(m)
    rows: List[Dict[str, Any]] = []
    for d in scan_days:
        eff = info.get(d, {}).get("eff_date")
        day_uni = uni.get(eff, {}) if eff is not None else {}
        for r in R.rank_day(by.get(d, [])):
            mc, tv = day_uni.get(r["stock_code"], (float("nan"), float("nan")))
            rows.append(dict(scan_date=pd.Timestamp(d).date(), stock_code=r["stock_code"], score=float(r["score"]),
                             rank=int(r["rank"]), n_passed=int(r["n_passed"]), market_cap=mc, trading_value=tv))
    diag = {"n_errors": int(sum(ga.errors.values())), "n_days": len(scan_days), "n_rows": len(rows)}
    return rows, diag
