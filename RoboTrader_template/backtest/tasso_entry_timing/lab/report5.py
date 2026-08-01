"""5차 집계 — `trades5.parquet` 에서 게이트 재측정 후 판정.

⚠️ 게이트 B 는 **주 판정이 쓰는 바로 그 표본**(전략·C1 둘 다 체결)에서 잰다.
   본실행 초판은 「전략이 체결된 모든 행」에서 쟀는데, 그건 Δ 를 계산하는
   표본이 아니다(사전등록 정정 2). 임계 0.5%p 는 그대로다.
⚠️ 게이트가 실패하면 주 판정 p 를 **계산하지 않고** 종료한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from lab.run5 import (ARMS, B, GATE_A_MAX_DELTA, GATE_A_MIN_P,
                      GATE_B_MAX_WANT_GAP, SEED, block_bootstrap_positive_p,
                      paired)
from lab.stats import mde, white_reality_check


def _want_gap(df: pd.DataFrame, arm: str) -> pd.Series:
    """주 판정 표본(전략·해당 팔 둘 다 체결)에서의 셀별 의도깊이 차."""
    sub = df.dropna(subset=["ret_s", f"ret_{arm}"])
    g = sub.groupby("cell")
    return (g["want_s"].mean() - g[f"want_{arm}"].mean())


def main() -> None:
    out = Path("out5")
    df = pd.read_parquet(out / "trades5.parquet")

    # ---- 게이트 A (재확인, 표본 동일) --------------------------------------
    gate_a = {}
    for fam, (a, b_) in {"c1": ("c1", "c1b"), "c2": ("c2", "c2b")}.items():
        fr = paired(df, a, b_)
        per_cell = fr.groupby("cell")["d"].mean().abs()
        p = white_reality_check(fr[["cell", "code", "d"]], b=B, seed=SEED)
        gate_a[fam] = {"n": int(len(fr)), "max_abs_delta": float(per_cell.max()),
                       "p": float(p),
                       "pass": bool(per_cell.max() <= GATE_A_MAX_DELTA and p >= GATE_A_MIN_P)}

    # ---- 게이트 B (정정: 주 판정 표본에서 측정) ----------------------------
    gap_c1, gap_c2 = _want_gap(df, "c1"), _want_gap(df, "c2")
    pd.DataFrame({"want_gap_c1": gap_c1, "want_gap_c2": gap_c2}).reset_index().to_csv(
        out / "gate_b_depth_paired.csv", index=False)
    gate_b = {
        "max_abs_want_gap_c1": float(gap_c1.abs().max()),
        "max_abs_want_gap_c2": float(gap_c2.abs().max()),
        "threshold": GATE_B_MAX_WANT_GAP,
        "signed_range_c1": [float(gap_c1.min()), float(gap_c1.max())],
        "c1_pass": bool(gap_c1.abs().max() <= GATE_B_MAX_WANT_GAP),
        "c2_pass": bool(gap_c2.abs().max() <= GATE_B_MAX_WANT_GAP),
    }

    verdict = {"gate_a": gate_a, "gate_b": gate_b,
               "n_rows": int(len(df)), "n_codes": int(df["code"].nunique()),
               "n_cells": int(df["cell"].nunique()), "seed": SEED}
    print(json.dumps({"gate_a_c1": gate_a["c1"], "gate_b": gate_b}, ensure_ascii=False), flush=True)

    if not (gate_a["c1"]["pass"] and gate_b["c1_pass"]):
        verdict["verdict"] = "GATE_FAIL"
        verdict["note"] = "사전 게이트 실패 — 주 판정 p 를 계산하지 않았다(사전등록 §3)."
        (out / "verdict5.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
        print(json.dumps(verdict, ensure_ascii=False))
        return

    # ---- 주 판정 ------------------------------------------------------------
    pr1 = paired(df, "s", "c1")
    cell_rows = []
    for cell in sorted(df["cell"].unique()):
        g1 = pr1[pr1["cell"] == cell]
        sub = df[df["cell"] == cell]
        se = g1["d"].std(ddof=1) / np.sqrt(len(g1))
        cell_rows.append({
            "cell": cell, "n": len(g1), "n_codes": g1["code"].nunique(),
            "delta_c1": g1["d"].mean(), "t_c1": g1["d"].mean() / se if se > 0 else 0.0,
            "want_gap_c1": float(gap_c1[cell]),
            **{f"mean_{a}": sub[f"ret_{a}"].mean() for a in ("s", "c1")},
            **{f"depth_{a}": sub[f"depth_{a}"].mean() for a in ("s", "c1")},
            **{f"fill_{a}": sub[f"fill_{a}"].mean() for a in ("s", "c1")},
            **{f"trunc_{a}": int(sub[f"trunc_{a}"].sum()) for a in ("s", "c1")},
        })
    cells = pd.DataFrame(cell_rows).sort_values("t_c1", ascending=False)
    cells.to_csv(out / "cells5.csv", index=False)

    p_rel = white_reality_check(pr1[["cell", "code", "d"]], b=B, seed=SEED)
    best = cells.iloc[0]["cell"]
    g = df[df["cell"] == best].dropna(subset=["ret_s"])
    p_abs = block_bootstrap_positive_p(g["code"].to_numpy(), g["ret_s"].to_numpy())

    pr1.groupby("year")["d"].agg(["count", "mean"]).to_csv(out / "by_year_c1.csv")
    pr1.groupby("bucket")["d"].agg(["count", "mean"]).to_csv(out / "by_bucket_c1.csv")
    ex = pr1[pr1["year"] != "2026"]
    ex.groupby("cell")["d"].agg(["count", "mean"]).to_csv(out / "cells5_ex2026.csv")
    q = pd.qcut(pr1["want_s"], 5, labels=False, duplicates="drop")
    (pr1.assign(stratum=q).groupby("stratum")
       .agg(n=("d", "size"), mean_d=("d", "mean"),
            want_lo=("want_s", "min"), want_hi=("want_s", "max"))
       .to_csv(out / "delta_by_intended_depth.csv"))
    df.groupby("cell").agg(**{
        **{f"trunc_{a}": (f"trunc_{a}", "sum") for a in ARMS},
        **{f"fill_{a}": (f"fill_{a}", "mean") for a in ARMS},
        **{f"n_{a}": (f"ret_{a}", "count") for a in ARMS},
    }).reset_index().to_csv(out / "truncation5.csv", index=False)

    sd = float(pr1["d"].std(ddof=1))
    verdict.update({
        "best_cell": best, "p_relative": p_rel, "p_absolute": p_abs,
        "delta_best": float(cells.iloc[0]["delta_c1"]),
        "mean_ret_s_best": float(g["ret_s"].mean()),
        "n_paired": int(len(pr1)), "sd_d": sd, "mde": mde(int(len(pr1)), sd),
        "verdict": "PASS" if (p_rel < 0.05 and p_abs < 0.05) else "FAIL",
    })
    (out / "verdict5.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False))


if __name__ == "__main__":
    main()
