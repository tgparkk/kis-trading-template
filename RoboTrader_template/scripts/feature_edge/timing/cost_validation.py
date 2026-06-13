"""first30 매수 타이밍 필터의 cost-aware 검증 (daytrading_3methods_breakout).

측정 전용. 핵심 질문 3가지:
 1) 현실적 한국 왕복비용(수수료+증권거래세+슬리피지) 스윕에서 first30 엣지가 생존하는가.
 2) +엣지가 진입 타이밍(timing) 때문인가 약한 시초 선별(selection) 때문인가.
 3) baseline 거래당 기대값이 왕복비용에 먹히는가 (first30 대비 상대 이점).

비용 근사: net ≈ gross − roundtrip_cost (소액 비용 가법근사). roundtrip_cost 는
매수수수료+매도수수료+증권거래세(매도)+슬리피지(왕복)의 합을 한 값으로 받는다.
"""
from __future__ import annotations

from typing import Dict, Iterable

import numpy as np
import pandas as pd


# ── 순수 분석 함수 ──────────────────────────────────────────────────────────
def roundtrip_net(gross: pd.Series, cost: float) -> pd.Series:
    """왕복비용 차감 net 수익률 (가법근사)."""
    return gross.astype(float) - cost


def cost_sweep(base_gross: pd.Series, alt_gross: pd.Series,
               costs: Iterable[float]) -> pd.DataFrame:
    """비용 수준별 baseline/first30 거래당 net 평균과 델타."""
    rows = []
    for c in costs:
        b = roundtrip_net(base_gross, c)
        a = roundtrip_net(alt_gross, c)
        rows.append({"cost": float(c),
                     "base_net_mean": float(b.mean()), "alt_net_mean": float(a.mean()),
                     "delta_mean": float(a.mean() - b.mean()),
                     "base_n": int(len(b)), "alt_n": int(len(a))})
    return pd.DataFrame(rows)


def breakeven_cost(gross: pd.Series) -> float:
    """거래당 net 평균이 0이 되는 왕복비용 = 평균 gross 수익률."""
    return float(gross.astype(float).mean())


def decompose_timing_selection(per_signal: pd.DataFrame) -> Dict[str, float]:
    """first30 총효과를 timing(진입가/청산) + selection(약한시초 선별)로 분해.

    per_signal: base_gross(모든 신호), entered(first30 진입여부), alt_gross(진입분).
    """
    base_all = per_signal["base_gross"].astype(float)
    ent = per_signal["entered"].astype(bool)
    base_ent = base_all[ent]
    alt_ent = per_signal.loc[ent, "alt_gross"].astype(float)
    selection = float(base_ent.mean() - base_all.mean())
    timing = float((alt_ent.values - base_ent.values).mean())
    total = float(alt_ent.mean() - base_all.mean())
    return {"selection": selection, "timing": timing, "total": total,
            "n_all": int(len(base_all)), "n_entered": int(ent.sum())}


# ── 데이터 수집 (daytrading 신호별 baseline vs first30 per-trade) ───────────
def collect_daytrading_per_signal(limit: int = 0) -> pd.DataFrame:  # pragma: no cover (통합 DB 경로)
    """daytrading 신호마다 baseline(D+1 시가) 과 first30 결과(gross)를 per-signal 수집."""
    from runners._adapter_factory import build_adapter
    from scripts.feature_edge import loaders, signals
    from scripts.feature_edge.timing import config, intraday_loader, buy_rules
    from scripts.feature_edge.timing.trade_sim import FixedExitAdapter, simulate_trade
    from scripts.feature_edge.timing.run_timing_lab import _exit_params_for

    cov = set(c for c, n in intraday_loader.covered_stock_dates().items() if n >= 20)
    codes = [c for c in loaders.load_universe(config.INTRADAY_END) if c in cov]
    if limit:
        codes = codes[:limit]
    daily_sup = loaders.load_daily_supplier(codes, config.INTRADAY_END)

    adapter = build_adapter("daytrading_3methods_breakout")
    exit_params = _exit_params_for("daytrading_3methods_breakout")
    sigs = signals.generate_entry_signals(adapter, codes, daily_sup)
    intr_cache = {c: intraday_loader.load_intraday_supplier(c) for c in sigs["stock_code"].unique()}
    bp = {"gap_skip_pct": config.GAP_SKIP_PCT, "or_min": config.OPENING_RANGE_MIN}

    rows = []
    for _, s in sigs.iterrows():
        d = daily_sup.get(s["stock_code"])
        if d is None:
            continue
        idx = d.index[d["date"] == pd.Timestamp(s["date"])]
        if len(idx) == 0:
            continue
        si = int(idx[0]); intr = intr_cache.get(s["stock_code"], {})
        base = simulate_trade(si, d, intr, FixedExitAdapter(), exit_params,
                              None, None, {}, {}, 0.0)
        if not base.filled:
            continue
        alt = simulate_trade(si, d, intr, FixedExitAdapter(), exit_params,
                             buy_rules.first30_strength, None, bp, {}, 0.0)
        rows.append({"date": s["date"], "stock_code": s["stock_code"],
                     "base_gross": base.ret_gross,
                     "entered": bool(alt.filled), "alt_gross": alt.ret_gross if alt.filled else np.nan})
    return pd.DataFrame(rows)


def build_report(per_signal: pd.DataFrame, costs: Iterable[float]) -> str:  # pragma: no cover
    base_all = per_signal["base_gross"]
    alt_ent = per_signal.loc[per_signal["entered"], "alt_gross"]
    sweep = cost_sweep(base_all, alt_ent, costs)
    dec = decompose_timing_selection(per_signal)
    lines = ["# first30 Cost-Aware 검증 — daytrading_3methods_breakout", "",
             "⚠️ 분봉 단일국면(2025-02~2026-06 강세/횡보) — 탐색적. 비용=왕복 가법근사.", "",
             f"- 신호(체결) 총 {dec['n_all']}건 중 first30 진입 {dec['n_entered']}건 "
             f"({dec['n_entered']/max(dec['n_all'],1)*100:.1f}%)",
             f"- baseline 평균 gross {base_all.mean()*100:.3f}% → 손익분기 왕복비용 "
             f"{breakeven_cost(base_all)*100:.3f}%",
             f"- first30 평균 gross {alt_ent.mean()*100:.3f}% → 손익분기 왕복비용 "
             f"{breakeven_cost(alt_ent)*100:.3f}%", "",
             "## 효과 분해 (gross, 거래당)",
             f"- selection(약한시초 선별) {dec['selection']*100:+.3f}%p",
             f"- timing(진입가/청산)    {dec['timing']*100:+.3f}%p",
             f"- total                 {dec['total']*100:+.3f}%p", "",
             "## 왕복비용 스윕 (거래당 net 평균)", "",
             sweep.assign(
                 cost=lambda t: (t["cost"]*100).round(2).astype(str)+"%",
                 base_net_mean=lambda t: (t["base_net_mean"]*100).round(3),
                 alt_net_mean=lambda t: (t["alt_net_mean"]*100).round(3),
                 delta_mean=lambda t: (t["delta_mean"]*100).round(3),
             ).to_markdown(index=False)]
    return "\n".join(lines)


def main():  # pragma: no cover
    import argparse, os
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    per = collect_daytrading_per_signal(limit=args.limit)
    # 한국 왕복비용: 수수료 ~0.03% + 증권거래세(매도) ~0.15~0.18% + 슬리피지 → 0.1~1.0% 스윕
    report = build_report(per, costs=(0.001, 0.002, 0.003, 0.004, 0.005, 0.0075, 0.01, 0.02))
    out = os.path.join("reports", "discovery", "timing_lab", "first30_cost_validation.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[cost-val] {out} (per-signal {len(per)})")


if __name__ == "__main__":
    main()
