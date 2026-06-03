"""Phase2 필터 스윕 결과 분석 — baseline(filter=none) 대비 필터별 worst-bear/FULL 비교.

입력: D:/tmp/multiverse2/phase2_filters/_phase2_summary.tsv
출력: 콘솔 표 + D:/tmp/multiverse2/phase2_filters/_phase2_analysis.tsv

worst-bear = 약세 윈도우(2022, 2021H2) 중 최소 Sharpe. FULL = 전구간 Sharpe/MaxDD/거래수.
필터 row 는 baseline(none, 동일 strategy/window/K/exit) 대비 비교.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path("D:/tmp/multiverse2/phase2_filters")
SUMM = ROOT / "_phase2_summary.tsv"

BEAR_WINDOWS = ["2022", "2021H2", "2024H2"]


def main():
    df = pd.read_csv(SUMM, sep="\t")
    # 식별키: strategy, window, K, filter, pass, sl/tp/mh, 진입필드(e_*)
    ecols = [c for c in df.columns if c.startswith("e_")]
    # 한 strategy 의 baseline 은 base 패스의 filter=none.
    base = df[(df["filter"] == "none")].copy()
    base_key = base.set_index(["strategy", "window", "K"])

    # 각 필터 row 에 baseline 메트릭 부착
    recs = []
    for _, r in df.iterrows():
        skey, wkey, K = r["strategy"], r["window"], r["K"]
        try:
            b = base_key.loc[(skey, wkey, K)]
            if isinstance(b, pd.DataFrame):
                b = b.iloc[0]
        except KeyError:
            b = None
        rec = dict(
            strategy=skey, window=wkey, K=K,
            filter=r["filter"], pass_=r["pass"], thr=r.get("thr"),
            sharpe=round(float(r["sharpe"]), 3), pnl=round(float(r["pnl"]), 4),
            maxdd=round(float(r["max_dd"]), 4), n_trades=int(r["n_trades"]),
        )
        if b is not None:
            bt = int(b["n_trades"])
            rec["bl_sharpe"] = round(float(b["sharpe"]), 3)
            rec["bl_maxdd"] = round(float(b["max_dd"]), 4)
            rec["bl_ntr"] = bt
            rec["d_sharpe"] = round(rec["sharpe"] - rec["bl_sharpe"], 3)
            rec["tr_chg_pct"] = round((rec["n_trades"] - bt) / bt * 100, 1) if bt else None
        recs.append(rec)
    out = pd.DataFrame(recs)
    out.to_csv(ROOT / "_phase2_analysis.tsv", sep="\t", index=False)

    # worst-bear Sharpe per (strategy, K, filter)
    print("\n=== worst-bear Sharpe (min over 2022/2021H2) per strategy×K×filter ===")
    bear = out[out["window"].isin(BEAR_WINDOWS)]
    wb = (bear.groupby(["strategy", "K", "filter", "pass_"])["sharpe"]
          .min().reset_index().rename(columns={"sharpe": "worst_bear_sharpe"}))
    # baseline worst-bear
    base_wb = wb[wb["filter"] == "none"][["strategy", "K", "worst_bear_sharpe"]] \
        .rename(columns={"worst_bear_sharpe": "bl_worst_bear"})
    wb = wb.merge(base_wb, on=["strategy", "K"], how="left")
    wb["d_worst_bear"] = (wb["worst_bear_sharpe"] - wb["bl_worst_bear"]).round(3)
    wb = wb.sort_values(["strategy", "K", "filter"])
    print(wb.to_string(index=False))

    # FULL window comparison
    print("\n=== FULL window: filter vs baseline ===")
    full = out[out["window"] == "FULL"].sort_values(["strategy", "K", "filter"])
    cols = ["strategy", "K", "filter", "pass_", "sharpe", "d_sharpe", "maxdd",
            "n_trades", "tr_chg_pct"]
    print(full[cols].to_string(index=False))

    # improvement summary: filters that improve worst-bear with maxdd<0.80 in FULL
    print("\n=== IMPROVEMENTS: worst-bear up vs baseline (d_worst_bear>0) ===")
    imp = wb[(wb["filter"] != "none") & (wb["d_worst_bear"] > 0)]
    if imp.empty:
        print("(none — no filter improves worst-bear Sharpe)")
    else:
        print(imp.sort_values("d_worst_bear", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
