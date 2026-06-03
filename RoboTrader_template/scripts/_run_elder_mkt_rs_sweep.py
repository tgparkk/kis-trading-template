"""Elder + mkt_rs 진입게이트 재검 — 정본 portfolio_sim_elder.simulate_portfolio 사용.

★측정 전용 오케스트레이터. 라이브 전략(strategies/*) 무수정. 청산/진입스톱/체결은
  portfolio_sim_elder 의 정본 경로(simulate_portfolio + _elder_exit_reason)를 그대로 호출.
  진입 게이트만 build_mkt_rs_gate 로 AND-필터(none=게이트 미주입=baseline 바이트동일).

윈도우 5종 × {none, mkt_rs} × K=20. 출력 D:/tmp/multiverse3_elder/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.portfolio_sim_elder as P

WINDOWS = {
    "2021H2": ("2021-07-01", "2021-12-31"),
    "2022":   ("2022-01-01", "2022-12-31"),
    "2024H2": ("2024-07-01", "2024-12-31"),
    "BULL":   ("2025-06-01", "2026-05-27"),
    "FULL":   ("2021-01-01", "2026-05-27"),
}
K = 20
TOP_N = 50
FILTER_N = 60
OUT = Path("D:/tmp/multiverse3_elder")


def run_one(data, calendar, kospi, kospi_m, strategy, entry_gate):
    res = P.simulate_portfolio(
        data=data, calendar=calendar, strategy=strategy,
        exit_reason_fn=P._elder_exit_reason, exit_params=P.ELDER_A_PARAMS,
        max_positions=K, use_buy_stop=True, entry_gate=entry_gate,
    )
    m = P.compute_portfolio_metrics(res, P.INITIAL_CAPITAL)
    ab = P.compute_alpha_beta(np.array(res["equity_curve"]), res["equity_dates"], kospi)
    m["alpha_vs_kospi"] = m["cagr"] - kospi_m["cagr"]
    m.update({"beta": ab["beta"], "alpha_ann": ab["alpha_ann"], "info_ratio": ab["info_ratio"]})
    return m, res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    strategy = P.build_elder(mode="single", target_rule="triple_screen_ema_pullback")
    for wname, (start, end) in WINDOWS.items():
        print(f"\n=== window {wname} ({start}~{end}) loading ===", flush=True)
        universe = P._load_top_volume_universe(start, end, TOP_N)
        data = P._load_daily_adj(universe, start, end)
        calendar = P._build_calendar(data)
        kospi = P._load_kospi(start, end)
        kospi_m = P.compute_kospi_metrics(kospi)
        print(f"  universe={len(universe)} data={len(data)} caldays={len(calendar)} "
              f"({calendar[0].date()}~{calendar[-1].date()}) KOSPI_days={len(kospi)}", flush=True)

        # baseline (none) — entry_gate=None → 정본 동작 바이트동일
        m, _ = run_one(data, calendar, kospi, kospi_m, strategy, None)
        m.update({"window": wname, "filter": "none", "K": K, "start": start, "end": end,
                  "kospi_total": kospi_m["total_ret"], "kospi_sharpe": kospi_m["sharpe"]})
        rows.append(m)
        print(f"  [    none] Sharpe={m['sharpe']:.3f} total={m['total_ret']:.4f} "
              f"MaxDD={m['max_dd']:.4f} trades={m['n_trades']}", flush=True)

        # mkt_rs gate
        kospi_close = P._load_kospi_close_lookback(start, end)
        gate = P.build_mkt_rs_gate(data, kospi_close, n=FILTER_N)
        m2, _ = run_one(data, calendar, kospi, kospi_m, strategy, gate)
        m2.update({"window": wname, "filter": "mkt_rs", "K": K, "start": start, "end": end,
                   "kospi_total": kospi_m["total_ret"], "kospi_sharpe": kospi_m["sharpe"]})
        rows.append(m2)
        print(f"  [  mkt_rs] Sharpe={m2['sharpe']:.3f} total={m2['total_ret']:.4f} "
              f"MaxDD={m2['max_dd']:.4f} trades={m2['n_trades']}", flush=True)

    df = pd.DataFrame(rows)
    cols = ["window", "filter", "K", "sharpe", "total_ret", "max_dd", "calmar",
            "cagr", "hit_rate", "n_trades", "avg_holdings", "avg_invested_ratio",
            "alpha_vs_kospi", "beta", "kospi_total", "kospi_sharpe", "start", "end"]
    df = df[[c for c in cols if c in df.columns]]
    tsv = OUT / "elder_mkt_rs_K20.tsv"
    df.to_csv(tsv, sep="\t", index=False)

    # diff table (mkt_rs - none) per window
    diff_rows = []
    for w in WINDOWS:
        nb = df[(df.window == w) & (df["filter"] == "none")].iloc[0]
        mr = df[(df.window == w) & (df["filter"] == "mkt_rs")].iloc[0]
        diff_rows.append({
            "window": w,
            "sharpe_none": nb["sharpe"], "sharpe_mktrs": mr["sharpe"],
            "d_sharpe": mr["sharpe"] - nb["sharpe"],
            "pnl_none": nb["total_ret"], "pnl_mktrs": mr["total_ret"],
            "d_pnl": mr["total_ret"] - nb["total_ret"],
            "maxdd_none": nb["max_dd"], "maxdd_mktrs": mr["max_dd"],
            "d_maxdd": mr["max_dd"] - nb["max_dd"],
            "ntr_none": int(nb["n_trades"]), "ntr_mktrs": int(mr["n_trades"]),
        })
    ddf = pd.DataFrame(diff_rows)
    dtsv = OUT / "elder_mkt_rs_K20_diff.tsv"
    ddf.to_csv(dtsv, sep="\t", index=False)

    print("\n" + "=" * 100)
    print("FULL SWEEP RESULT (Elder A K=20, top_volume:50, 정본 simulate_portfolio)")
    print("=" * 100)
    print(df.to_string(index=False))
    print("\n--- DIFF (mkt_rs - none) ---")
    print(ddf.to_string(index=False))
    print(f"\nTSV: {tsv}")
    print(f"DIFF TSV: {dtsv}")


if __name__ == "__main__":
    main()
