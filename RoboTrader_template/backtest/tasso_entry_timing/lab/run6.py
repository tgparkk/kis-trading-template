"""6차 본실행 — 미체결을 현금(0.00%)으로 처리해 체결 조건화를 제거한다.

5차는 「체결된 거래」만 표본에 넣었다. 얕게 건 주문이 더 자주 체결되므로
**"체결됐다"는 조건 자체가 깊이를 선택**했고, 어느 표본에서 재느냐로 교란의
부호가 뒤집혔다(전체행 −1.0%p / 짝지은 표본 +2.98%p).

여기서는 사건 × 판본 × 폭계수 조합마다 **양팔 모두 반드시 한 행**이 생긴다.
미체결이면 `ret = 0.0`(비용도 없다). 조건화가 원리적으로 사라진다.

⚠️ 게이트 실패 시 주 판정 p 를 **계산하지 않고** 종료하는 순서는 그대로다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from lab.bands import (BUCKETS, WEIGHTS, exogenous_quantiles, ladder,
                       pit_quantiles)
from lab.control5 import (MIN_LABEL_POOL, intended_depth, random_shape_levels,
                          shuffled_label_levels)
from lab.data import load_daily
from lab.run import flush_pending
from lab.run5 import _quarter, block_bootstrap_positive_p, paired
from lab.segments import find_segments
from lab.sim import simulate
from lab.stats import mde, white_reality_check

START, END = "2021-01-04", "2026-07-31"
HOLD, COST = 20, 0.0021
C_GRID = (0.6, 0.8, 1.0)
SEED = 20260803                 # 사전등록 §4. 4차 20260801 · 5차 20260802 와 구별
B = 1000

GATE_A_MAX_DELTA = 0.005
GATE_A_MIN_P = 0.05
GATE_B_MAX_WANT_GAP = 0.005

ARMS = ("s", "c1", "c1b", "c2", "c2b")
CASH_RETURN = 0.0               # 미체결 = 현금. 비용도 발생하지 않는다.


def _seed(*parts) -> int:
    import zlib
    return zlib.crc32("|".join(str(p) for p in parts).encode()) ^ SEED


def _bucket_name(gain: float) -> str:
    lo = 0.0
    for b in BUCKETS:
        if gain >= b:
            lo = b
    return f">={lo:.2f}"


def arm_fields(trade, peak: float, levels, weights) -> dict:
    """한 팔의 결과를 행으로. **미체결도 행이 된다** — 그게 6차의 전부다."""
    want = (np.nan if levels is None
            else intended_depth(peak, levels, WEIGHTS if weights is None else weights))
    if levels is None:                      # 밴드 자체를 못 만든 경우만 결측
        return {"ret": np.nan, "want": want, "filled": np.nan,
                "fill_n": np.nan, "trunc": np.nan, "depth": np.nan}
    if trade is None:                       # 밴드는 걸었으나 안 걸림 → 현금
        return {"ret": CASH_RETURN, "want": want, "filled": 0.0,
                "fill_n": 0.0, "trunc": 0.0, "depth": np.nan}
    return {"ret": trade.ret_net, "want": want, "filled": 1.0,
            "fill_n": float(trade.filled_n), "trunc": float(trade.truncated),
            "depth": 1.0 - trade.avg_cost / peak}


def collect(defs_path: Path) -> tuple[pd.DataFrame, dict]:
    bars = load_daily(START, END)
    by_code = {k: g.reset_index(drop=True) for k, g in bars.groupby("stock_code", sort=False)}
    selected = json.loads(defs_path.read_text(encoding="utf-8"))

    rows = []
    drops = {"events": 0, "pool_too_small": 0, "no_band_s": 0, "band_none_c1": 0}

    for d in selected:
        segs = sorted(find_segments(bars, d["variant"], d["lookback"], d["min_gain"]),
                      key=lambda s: s.peak_date)
        pool_by_q: dict[str, list[float]] = {}
        pos_in_q: list[int] = []
        for s in segs:
            bucket = pool_by_q.setdefault(_quarter(s.peak_date), [])
            pos_in_q.append(len(bucket))
            bucket.append(s.gain)

        history: list[tuple[float, float]] = []
        pending: list[tuple[str, float, float]] = []

        for seg_i, seg in enumerate(segs):
            ready, pending = flush_pending(pending, as_of=seg.peak_date)
            history.extend(ready)
            drops["events"] += 1
            qk = _quarter(seg.peak_date)
            j = pos_in_q[seg_i]
            label_pool = pool_by_q[qk][:j] + pool_by_q[qk][j + 1:]

            g_bars = by_code[seg.code]
            idx = g_bars.index[g_bars["date"] == seg.peak_date]
            if len(idx) == 0:
                continue
            i_peak = int(idx[0])
            window = g_bars.iloc[i_peak + 1: i_peak + 1 + d["valid_days"] + HOLD].reset_index(drop=True)
            if window.empty:
                continue
            close_date = str(window["date"].iat[-1])
            realized = 1.0 - float(window["low"].min()) / seg.peak_px

            if len(label_pool) < MIN_LABEL_POOL:
                drops["pool_too_small"] += 1
                pending.append((close_date, seg.gain, realized))
                continue

            for version in ("pit", "exo"):
                if version == "pit":
                    def band_fn(x, _h=history):
                        return pit_quantiles(_h, x)
                else:
                    band_fn = exogenous_quantiles
                q = band_fn(seg.gain)
                if q is None:                   # 전략이 밴드를 못 만들면 양팔 모두 없음
                    drops["no_band_s"] += 1
                    continue

                for c in C_GRID:
                    levels = {"s": ladder(seg.peak_px, q[0], q[1], c)}
                    weights = {a: None for a in ARMS}
                    want_s = intended_depth(seg.peak_px, levels["s"], WEIGHTS)
                    for arm in ("c1", "c1b"):
                        rng = np.random.default_rng(_seed(seg.code, seg.peak_date, version, c, arm))
                        levels[arm] = shuffled_label_levels(seg.peak_px, label_pool, band_fn, c, rng)
                        if levels[arm] is None:
                            drops["band_none_c1"] += 1
                    for arm in ("c2", "c2b"):
                        rng = np.random.default_rng(_seed(seg.code, seg.peak_date, version, c, arm))
                        levels[arm], weights[arm] = random_shape_levels(
                            seg.peak_px, q[0], q[1], rng, match_depth=want_s)

                    row = {"cell": f'{d["name"]}|{version}|c{c}', "code": seg.code,
                           "peak_date": seg.peak_date, "year": seg.peak_date[:4],
                           "bucket": _bucket_name(seg.gain), "gain": seg.gain}
                    for arm in ARMS:
                        t = (None if levels[arm] is None else
                             simulate(window, levels[arm], HOLD, COST, seg.code,
                                      max_fill_bars=d["valid_days"], weights=weights[arm]))
                        f = arm_fields(t, seg.peak_px, levels[arm], weights[arm])
                        for k, v in f.items():
                            row[f"{k}_{arm}" if k != "fill_n" else f"fill_{arm}"] = v
                    rows.append(row)

            pending.append((close_date, seg.gain, realized))

    return pd.DataFrame(rows), drops


def main() -> None:
    out = Path("out6")
    out.mkdir(exist_ok=True)
    defs = out / "selected_definitions.json"
    if not defs.exists():
        defs.write_text((Path("out") / "selected_definitions.json").read_text(encoding="utf-8"),
                        encoding="utf-8")

    df, drops = collect(defs)
    df.to_parquet(out / "trades6.parquet")
    print(json.dumps({"rows": len(df), "codes": int(df["code"].nunique()), **drops},
                     ensure_ascii=False), flush=True)

    # ---- 게이트 B: 의도 깊이 대칭 (측정 표본 = 판정 표본) -------------------
    gaps = {}
    for arm in ("c1", "c2"):
        sub = df.dropna(subset=["ret_s", f"ret_{arm}"])
        g = sub.groupby("cell")
        gaps[arm] = g["want_s"].mean() - g[f"want_{arm}"].mean()
    pd.DataFrame(gaps).reset_index().to_csv(out / "gate_b_depth.csv", index=False)
    gate_b = {
        "max_abs_want_gap_c1": float(gaps["c1"].abs().max()),
        "max_abs_want_gap_c2": float(gaps["c2"].abs().max()),
        "threshold": GATE_B_MAX_WANT_GAP,
        "signed_range_c1": [float(gaps["c1"].min()), float(gaps["c1"].max())],
        "c1_pass": bool(gaps["c1"].abs().max() <= GATE_B_MAX_WANT_GAP),
        "c2_pass": bool(gaps["c2"].abs().max() <= GATE_B_MAX_WANT_GAP),
    }

    # ---- 게이트 A: 귀무 실측 ------------------------------------------------
    gate_a = {}
    for fam, (a, b_) in {"c1": ("c1", "c1b"), "c2": ("c2", "c2b")}.items():
        fr = paired(df, a, b_)
        per_cell = fr.groupby("cell")["d"].mean().abs()
        p = white_reality_check(fr[["cell", "code", "d"]], b=B, seed=SEED)
        gate_a[fam] = {"n": int(len(fr)), "max_abs_delta": float(per_cell.max()),
                       "p": float(p),
                       "pass": bool(per_cell.max() <= GATE_A_MAX_DELTA and p >= GATE_A_MIN_P)}
        fr.groupby("cell")["d"].agg(["count", "mean"]).to_csv(out / f"gate_a_{fam}.csv")

    verdict = {"gate_a": gate_a, "gate_b": gate_b, "drops": drops,
               "n_rows": int(len(df)), "n_codes": int(df["code"].nunique()),
               "n_cells": int(df["cell"].nunique()), "seed": SEED,
               "cash_share_s": float(1.0 - df["filled_s"].mean()),
               "cash_share_c1": float(1.0 - df["filled_c1"].mean())}
    print(json.dumps({"gate_a_c1": gate_a["c1"], "gate_b": gate_b}, ensure_ascii=False), flush=True)

    if not (gate_a["c1"]["pass"] and gate_b["c1_pass"]):
        verdict["verdict"] = "GATE_FAIL"
        verdict["note"] = "사전 게이트 실패 — 주 판정 p 를 계산하지 않았다(사전등록 §3)."
        (out / "verdict6.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False),
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
            "want_gap_c1": float(gaps["c1"][cell]),
            **{f"mean_{a}": sub[f"ret_{a}"].mean() for a in ("s", "c1")},
            **{f"fillrate_{a}": sub[f"filled_{a}"].mean() for a in ("s", "c1")},
            **{f"depth_{a}": sub[f"depth_{a}"].mean() for a in ("s", "c1")},
            **{f"trunc_{a}": float(np.nansum(sub[f"trunc_{a}"])) for a in ("s", "c1")},
        })
    cells = pd.DataFrame(cell_rows).sort_values("t_c1", ascending=False)
    cells.to_csv(out / "cells6.csv", index=False)

    p_rel = white_reality_check(pr1[["cell", "code", "d"]], b=B, seed=SEED)
    best = cells.iloc[0]["cell"]
    g = df[df["cell"] == best].dropna(subset=["ret_s"])
    p_abs = block_bootstrap_positive_p(g["code"].to_numpy(), g["ret_s"].to_numpy(), b=B, seed=SEED)

    pr1.groupby("year")["d"].agg(["count", "mean"]).to_csv(out / "by_year_c1.csv")
    pr1.groupby("bucket")["d"].agg(["count", "mean"]).to_csv(out / "by_bucket_c1.csv")
    pr1[pr1["year"] != "2026"].groupby("cell")["d"].agg(["count", "mean"]).to_csv(
        out / "cells6_ex2026.csv")
    q = pd.qcut(pr1["want_s"], 5, labels=False, duplicates="drop")
    (pr1.assign(stratum=q).groupby("stratum")
       .agg(n=("d", "size"), mean_d=("d", "mean"),
            want_lo=("want_s", "min"), want_hi=("want_s", "max"))
       .to_csv(out / "delta_by_intended_depth.csv"))

    sd = float(pr1["d"].std(ddof=1))
    verdict.update({
        "best_cell": best, "p_relative": p_rel, "p_absolute": p_abs,
        "delta_best": float(cells.iloc[0]["delta_c1"]),
        "mean_ret_s_best": float(g["ret_s"].mean()),
        "n_paired": int(len(pr1)), "sd_d": sd, "mde": mde(int(len(pr1)), sd),
        "verdict": "PASS" if (p_rel < 0.05 and p_abs < 0.05) else "FAIL",
    })
    (out / "verdict6.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False))


if __name__ == "__main__":
    main()
