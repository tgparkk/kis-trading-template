"""Intraday Timing Lab 오케스트레이터 (측정 전용)."""
from __future__ import annotations

import argparse
import os
from typing import Dict

import pandas as pd

from scripts.feature_edge.timing import config
from scripts.feature_edge.timing.timing_metrics import (
    delta_vs_baseline, bootstrap_delta_p05, oos_delta_signs, summarize_trades)


def build_timing_table(rule_trades: Dict[str, pd.DataFrame], baseline: pd.DataFrame,
                       split: str = None) -> pd.DataFrame:
    split = split or config.OOS_SPLIT
    rows = []
    for rule, alt in rule_trades.items():
        dn = delta_vs_baseline(alt, baseline, "ret_net")
        dg = delta_vs_baseline(alt, baseline, "ret_gross")
        oos = oos_delta_signs(alt, baseline, split, "ret_net")
        rows.append({
            "rule": rule, "alt_n": dn["alt_n"], "base_n": dn["base_n"],
            "base_mean_net": dn["base_mean"], "alt_mean_net": dn["alt_mean"],
            "delta_mean_net": dn["delta_mean"], "delta_mean_gross": dg["delta_mean"],
            "delta_hit_net": dn["delta_hit"],
            "bootstrap_p05_net": bootstrap_delta_p05(alt, baseline, "ret_net"),
            "oos_consistent": oos["consistent"],
        })
    return pd.DataFrame(rows).sort_values("delta_mean_net", ascending=False).reset_index(drop=True)


def write_report(per_strategy: Dict[str, pd.DataFrame], path: str, note: str = "") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# Intraday Timing Report (Phase 1 — 측정 전용)", "", note,
             "", "⚠️ 단일국면(2025-02~2026-06 강세/횡보) — 탐색적, 국면강건 주장 불가.",
             "판정(참고): delta_mean_net>0 ∧ bootstrap_p05_net>0 ∧ oos_consistent.", ""]
    for strat, tbl in per_strategy.items():
        lines += [f"## {strat}", "", tbl.to_markdown(index=False), ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _exit_params_for(strat: str) -> dict:
    import yaml
    with open(os.path.join("strategies", strat, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    rm = cfg.get("risk_management", {})
    return {"stop_loss_pct": float(rm.get("stop_loss_pct", 0.08)),
            "take_profit_pct": float(rm.get("take_profit_pct", 0.10)),
            "max_hold_bars": int(rm.get("max_hold_days", 10))}


def _run_rule(sigs, daily_sup, intr_cache, exit_params, brule, srule, buy_params, sell_params):
    from scripts.feature_edge.timing.trade_sim import FixedExitAdapter, simulate_trade
    rows = []
    for _, s in sigs.iterrows():
        d = daily_sup.get(s["stock_code"])
        if d is None:
            continue
        idx = d.index[d["date"] == pd.Timestamp(s["date"])]
        if len(idx) == 0:
            continue
        si = int(idx[0]); intr = intr_cache.get(s["stock_code"], {})
        tr = simulate_trade(si, d, intr, FixedExitAdapter(), exit_params,
                            brule, srule, buy_params, sell_params, config.SLIPPAGE_PER_SIDE)
        if tr.filled:
            rows.append({"date": s["date"], "ret_net": tr.ret_net, "ret_gross": tr.ret_gross})
    return pd.DataFrame(rows)


def main():  # pragma: no cover (통합 실행 경로)
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="전략별 신호 종목수 제한(0=전체)")
    args = ap.parse_args()

    from runners._adapter_factory import build_adapter
    from scripts.feature_edge import loaders, signals
    from scripts.feature_edge.timing import intraday_loader, buy_rules, sell_rules

    cov = intraday_loader.covered_stock_dates()
    cov_codes = set(c for c, n in cov.items() if n >= 20)
    universe = loaders.load_universe(config.INTRADAY_END)
    codes = [c for c in universe if c in cov_codes]
    if args.limit:
        codes = codes[: args.limit]
    daily_sup = loaders.load_daily_supplier(codes, config.INTRADAY_END)

    BUY = {"vwap_entry": buy_rules.vwap_entry, "gap_skip": buy_rules.gap_skip,
           "or_breakout": buy_rules.opening_range_breakout, "pullback_vwap": buy_rules.pullback_to_vwap,
           "first30": buy_rules.first30_strength}
    SELL = {"vwap_break": sell_rules.vwap_break_exit, "intraday_trail": sell_rules.intraday_trail,
            "time_exit": sell_rules.time_exit, "mom_loss": sell_rules.intraday_momentum_loss}
    buy_params = {"gap_skip_pct": config.GAP_SKIP_PCT, "or_min": config.OPENING_RANGE_MIN}
    sell_params = {"trail_pct": config.INTRADAY_TRAIL_PCT, "time_exit": config.TIME_EXIT,
                   "mom_min": config.MOM_LOSS_MIN}

    per_strategy = {}
    for strat in config.TIMING_STRATEGIES:
        adapter = build_adapter(strat)
        exit_params = _exit_params_for(strat)
        sigs = signals.generate_entry_signals(adapter, codes, daily_sup)
        if len(sigs) == 0:
            per_strategy[strat] = pd.DataFrame()
            continue
        intr_cache = {c: intraday_loader.load_intraday_supplier(c)
                      for c in sigs["stock_code"].unique()}
        baseline = _run_rule(sigs, daily_sup, intr_cache, exit_params, None, None,
                             buy_params, sell_params)
        rule_trades = {}
        for name, brule in BUY.items():
            rule_trades[f"buy:{name}"] = _run_rule(sigs, daily_sup, intr_cache, exit_params,
                                                   brule, None, buy_params, sell_params)
        for name, srule in SELL.items():
            rule_trades[f"sell:{name}"] = _run_rule(sigs, daily_sup, intr_cache, exit_params,
                                                    None, srule, buy_params, sell_params)
        per_strategy[strat] = build_timing_table(rule_trades, baseline)

    write_report(per_strategy, config.REPORT_PATH, note="3전략 분봉 타이밍 단일룰 측정.")
    print(f"[timing-lab] 리포트 {config.REPORT_PATH}")


if __name__ == "__main__":
    main()
