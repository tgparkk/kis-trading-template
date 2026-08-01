"""5차 본실행 — 매수 타이밍 단독. 사전등록 §2~§5 대로만 돈다.

⚠️ 게이트 A(귀무 실측)·게이트 B(의도 깊이 대칭)가 실패하면 **주 판정 p 를
   계산조차 하지 않고** 종료한다. 4차는 결함 있는 대조군으로 p 를 먼저 봤고,
   그 뒤로는 무엇을 봐도 이미 늦었다. 순서를 코드로 못 박는다.

⚠️ 게이트 B 는 **의도 깊이**(지정가 기준, 사전 설계변수)로 건다. 실현 깊이는
   가격 경로의 함수인 결과변수라서, 그것이 같기를 요구하면 두 팔이 똑같이
   행동하기를 요구하는 셈이 되고 검정할 것이 남지 않는다. 실현 깊이는
   게이트가 아니라 필수 보고 항목이다.
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from lab.bands import (BUCKETS, WEIGHTS, exogenous_quantiles, ladder,
                       pit_quantiles)
from lab.control5 import (MIN_LABEL_POOL, intended_depth, random_shape_levels,
                          shuffled_label_levels)
from lab.data import load_daily
from lab.run import flush_pending
from lab.segments import find_segments
from lab.sim import simulate
from lab.stats import mde, white_reality_check

START, END = "2021-01-04", "2026-07-31"
HOLD, COST = 20, 0.0021
C_GRID = (0.6, 0.8, 1.0)
SEED = 20260802                 # 사전등록 §4. 4차(20260801)와 다른 시드
B = 1000

GATE_A_MAX_DELTA = 0.005        # 셀별 |Δ| 상한 (사전등록 §3-A)
GATE_A_MIN_P = 0.05
GATE_B_MAX_WANT_GAP = 0.005     # 셀별 |의도 깊이 차| 상한 (사전등록 §3-B 정정판)

ARMS = ("s", "c1", "c1b", "c2", "c2b")


def _seed(*parts) -> int:
    return zlib.crc32("|".join(str(p) for p in parts).encode()) ^ SEED


def _bucket_name(gain: float) -> str:
    lo = 0.0
    for b in BUCKETS:
        if gain >= b:
            lo = b
    return f">={lo:.2f}"


def block_bootstrap_positive_p(codes, values, b: int = B, seed: int = SEED) -> float:
    """H0: 평균 ≤ 0 에 대한 단측 p. 종목코드 블록 리샘플링.

    주 판정과 같은 블록 단위를 써야 유효표본이 일관된다(거래 수가 아니라 종목 수).
    """
    codes = np.asarray(codes)
    values = np.asarray(values, dtype=float)
    uniq = np.unique(codes)
    per = {k: values[codes == k] for k in uniq}
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(b):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        if np.concatenate([per[k] for k in pick]).mean() <= 0:
            hits += 1
    return float((hits + 1) / (b + 1))


def paired(df: pd.DataFrame, a: str, c: str) -> pd.DataFrame:
    """두 팔의 완전관측 표본만. `d` = a 팔 − c 팔."""
    sub = df.dropna(subset=[f"ret_{a}", f"ret_{c}"])
    out = sub[["cell", "code", "year", "bucket"]].copy()
    out["d"] = sub[f"ret_{a}"].to_numpy() - sub[f"ret_{c}"].to_numpy()
    out["want_s"] = sub["want_s"].to_numpy()
    return out


def _quarter(date_str: str) -> str:
    y, m = int(date_str[:4]), int(date_str[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def collect(defs_path: Path) -> tuple[pd.DataFrame, dict]:
    bars = load_daily(START, END)
    by_code = {k: g.reset_index(drop=True) for k, g in bars.groupby("stock_code", sort=False)}
    selected = json.loads(defs_path.read_text(encoding="utf-8"))

    rows = []
    drops = {"events": 0, "pool_too_small": 0, "band_none": 0,
             **{f"no_fill_{a}": 0 for a in ARMS}}

    for d in selected:
        segs = sorted(find_segments(bars, d["variant"], d["lookback"], d["min_gain"]),
                      key=lambda s: s.peak_date)
        # C1 라벨 풀 — 같은 분기의 **다른** 사건들의 상승폭 (기간 내 교차 셔플).
        # 분포의 시간 드리프트를 제거해 깊이의 주변분포를 사건과 맞춘다.
        pool_by_q: dict[str, list[float]] = {}
        pos_in_q: list[int] = []
        for s in segs:
            qk = _quarter(s.peak_date)
            bucket = pool_by_q.setdefault(qk, [])
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
            label_pool = pool_by_q[qk][:j] + pool_by_q[qk][j + 1:]   # 자기 자신 제외

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

            if len(label_pool) < MIN_LABEL_POOL:      # 사전등록 §2 — 양팔 모두 진입 금지
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
                if q is None:
                    continue

                for c in C_GRID:
                    levels = {"s": ladder(seg.peak_px, q[0], q[1], c)}
                    weights = {a: None for a in ARMS}
                    want_s = intended_depth(seg.peak_px, levels["s"], WEIGHTS)
                    for arm in ("c1", "c1b"):
                        rng = np.random.default_rng(_seed(seg.code, seg.peak_date, version, c, arm))
                        levels[arm] = shuffled_label_levels(seg.peak_px, label_pool, band_fn, c, rng)
                        if levels[arm] is None:
                            drops["band_none"] += 1
                    for arm in ("c2", "c2b"):
                        rng = np.random.default_rng(_seed(seg.code, seg.peak_date, version, c, arm))
                        levels[arm], weights[arm] = random_shape_levels(
                            seg.peak_px, q[0], q[1], rng, match_depth=want_s)

                    trades = {a: (None if levels[a] is None else
                                  simulate(window, levels[a], HOLD, COST, seg.code,
                                           max_fill_bars=d["valid_days"], weights=weights[a]))
                              for a in ARMS}
                    if trades["s"] is None:           # 전략이 안 사면 비교 자체가 없다
                        drops["no_fill_s"] += 1
                        continue

                    row = {"cell": f'{d["name"]}|{version}|c{c}', "code": seg.code,
                           "peak_date": seg.peak_date, "year": seg.peak_date[:4],
                           "bucket": _bucket_name(seg.gain), "gain": seg.gain}
                    for arm in ARMS:
                        row[f"want_{arm}"] = (
                            np.nan if levels[arm] is None else
                            intended_depth(seg.peak_px, levels[arm],
                                           WEIGHTS if weights[arm] is None else weights[arm]))
                        t = trades[arm]
                        if t is None:
                            if levels[arm] is not None and arm != "s":
                                drops[f"no_fill_{arm}"] += 1
                            row[f"ret_{arm}"] = np.nan
                            row[f"trunc_{arm}"] = np.nan
                            row[f"fill_{arm}"] = np.nan
                            row[f"depth_{arm}"] = np.nan
                        else:
                            row[f"ret_{arm}"] = t.ret_net
                            row[f"trunc_{arm}"] = float(t.truncated)
                            row[f"fill_{arm}"] = float(t.filled_n)
                            row[f"depth_{arm}"] = 1.0 - t.avg_cost / seg.peak_px
                    rows.append(row)

            pending.append((close_date, seg.gain, realized))

    return pd.DataFrame(rows), drops


def main() -> None:
    out = Path("out5")
    out.mkdir(exist_ok=True)
    defs = out / "selected_definitions.json"
    if not defs.exists():
        defs.write_text((Path("out") / "selected_definitions.json").read_text(encoding="utf-8"),
                        encoding="utf-8")

    df, drops = collect(defs)
    df.to_parquet(out / "trades5.parquet")
    print(json.dumps({"rows": len(df), "codes": int(df["code"].nunique()), **drops},
                     ensure_ascii=False), flush=True)

    # ---- 게이트 B: 의도 깊이 대칭 (사전등록 §3-B 정정판) --------------------
    want = df.groupby("cell").agg(**{f"want_{a}": (f"want_{a}", "mean") for a in ARMS})
    real = df.groupby("cell").agg(**{f"depth_{a}": (f"depth_{a}", "mean") for a in ARMS})
    depth_tbl = want.join(real)
    depth_tbl["want_gap_c1"] = (depth_tbl["want_s"] - depth_tbl["want_c1"]).abs()
    depth_tbl["want_gap_c2"] = (depth_tbl["want_s"] - depth_tbl["want_c2"]).abs()
    depth_tbl["real_gap_c1"] = depth_tbl["depth_s"] - depth_tbl["depth_c1"]   # 부호 보존(보고용)
    depth_tbl["real_gap_c2"] = depth_tbl["depth_s"] - depth_tbl["depth_c2"]
    depth_tbl.reset_index().to_csv(out / "gate_b_depth.csv", index=False)
    gate_b = {
        "max_want_gap_c1": float(depth_tbl["want_gap_c1"].max()),
        "max_want_gap_c2": float(depth_tbl["want_gap_c2"].max()),
        "threshold": GATE_B_MAX_WANT_GAP,
        "reported_real_gap_c1_range": [float(depth_tbl["real_gap_c1"].min()),
                                       float(depth_tbl["real_gap_c1"].max())],
        "reported_real_gap_c2_range": [float(depth_tbl["real_gap_c2"].min()),
                                       float(depth_tbl["real_gap_c2"].max())],
    }
    gate_b["c1_pass"] = bool(gate_b["max_want_gap_c1"] <= GATE_B_MAX_WANT_GAP)
    gate_b["c2_pass"] = bool(gate_b["max_want_gap_c2"] <= GATE_B_MAX_WANT_GAP)

    # ---- 게이트 A: 귀무 실측 (사전등록 §3-A) -------------------------------
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
               "n_cells": int(df["cell"].nunique()), "seed": SEED}

    if not (gate_a["c1"]["pass"] and gate_b["c1_pass"]):
        verdict["verdict"] = "GATE_FAIL"
        verdict["note"] = "사전 게이트 실패 — 주 판정 p 를 계산하지 않았다(사전등록 §3)."
        (out / "verdict5.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
        print(json.dumps(verdict, ensure_ascii=False))
        return

    # ---- 주 판정 (게이트 통과 후에만 도달) ----------------------------------
    pr1, pr2 = paired(df, "s", "c1"), paired(df, "s", "c2")
    cell_rows = []
    for cell in sorted(df["cell"].unique()):
        g1 = pr1[pr1["cell"] == cell]
        g2 = pr2[pr2["cell"] == cell]
        se = g1["d"].std(ddof=1) / np.sqrt(len(g1))
        sub = df[df["cell"] == cell]
        cell_rows.append({
            "cell": cell, "n_c1": len(g1), "n_codes_c1": g1["code"].nunique(),
            "delta_c1": g1["d"].mean(), "t_c1": g1["d"].mean() / se if se > 0 else 0.0,
            "n_c2": len(g2), "delta_c2": g2["d"].mean(),
            **{f"mean_{a}": sub[f"ret_{a}"].mean() for a in ARMS},
            **{f"depth_{a}": sub[f"depth_{a}"].mean() for a in ARMS},
        })
    cells = pd.DataFrame(cell_rows).sort_values("t_c1", ascending=False)
    cells.to_csv(out / "cells5.csv", index=False)

    p_rel = white_reality_check(pr1[["cell", "code", "d"]], b=B, seed=SEED)
    best = cells.iloc[0]["cell"]
    g = df[(df["cell"] == best)].dropna(subset=["ret_s"])
    p_abs = block_bootstrap_positive_p(g["code"].to_numpy(), g["ret_s"].to_numpy())

    for tag, fr in (("c1", pr1), ("c2", pr2)):
        fr.groupby("year")["d"].agg(["count", "mean"]).to_csv(out / f"by_year_{tag}.csv")
        fr.groupby("bucket")["d"].agg(["count", "mean"]).to_csv(out / f"by_bucket_{tag}.csv")
    ex = pr1[pr1["year"] != "2026"]
    ex.groupby("cell")["d"].agg(["count", "mean"]).to_csv(out / "cells5_ex2026.csv")

    # 의도 깊이(사전변수) 5분위 층별 Δ — 실현 깊이 잔차에 대한 민감도
    q = pd.qcut(pr1["want_s"], 5, labels=False, duplicates="drop")
    (pr1.assign(stratum=q).groupby("stratum")
       .agg(n=("d", "size"), mean_d=("d", "mean"), want_lo=("want_s", "min"),
            want_hi=("want_s", "max"))
       .to_csv(out / "delta_by_intended_depth.csv"))

    df.groupby("cell").agg(**{
        **{f"trunc_{a}": (f"trunc_{a}", "sum") for a in ARMS},
        **{f"fill_{a}": (f"fill_{a}", "mean") for a in ARMS},
        **{f"n_{a}": (f"ret_{a}", "count") for a in ARMS},
    }).reset_index().to_csv(out / "truncation5.csv", index=False)

    sd = float(df["ret_s"].std(ddof=1))
    verdict.update({
        "best_cell": best, "p_relative": p_rel, "p_absolute": p_abs,
        "delta_best": float(cells.iloc[0]["delta_c1"]),
        "mean_ret_s_best": float(g["ret_s"].mean()),
        "sd": sd, "mde": mde(int(len(pr1)), sd),
        "verdict": "PASS" if (p_rel < 0.05 and p_abs < 0.05) else "FAIL",
    })
    (out / "verdict5.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False))


if __name__ == "__main__":
    main()
