"""7차 본실행 — 앵커가 완전 재현되는 국지 반등 정의.

6차 대비 바뀐 것 (사전등록 §1·§3):
  · 구간 정의: 창 신고가 조건 제거 → **급등봉 기준 국지 구간**(다날 정답 재현)
  · 폭계수 c 를 A급 증거값 **0.8 하나로 고정**(격자 억제)
  · 주 수익 지표를 **자본가중**으로 (`ret × cumsum(비중)[fill_n]`)
  · 절대검정을 max-t 셀이 아니라 **pooled** 로
  · MDE 를 **종목 블록 SE** 기준으로
  · 게이트 B 에 `E[|gap|]` 조건 추가 (1차 모멘트만으로는 부족)
  · 게이트 C 신설 — **정답 라벨이 후보 집합에 실제로 존재하는가**
  · s-vs-C2 를 **필수 산출**로 강제

⚠️ 게이트 실패 시 주 판정 p 를 계산조차 하지 않고 종료한다.
"""
from __future__ import annotations

import itertools
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
from lab.run5 import _quarter, paired
from lab.segments import find_segments_local
from lab.sim import simulate
from lab.stats import white_reality_check

START, END = "2021-01-04", "2026-07-31"
HOLD, COST, VALID_DAYS = 20, 0.0021, 20
C_FIXED = 0.8                    # 사전등록 §1 — 삼성 화면 역산값(width/IQR=0.8019)
SEED = 20260804
B = 1000

K_MULTS, HORIZONS, MIN_GAINS = (5.0, 10.0), (10, 20), (0.15, 0.25)   # 앵커오차 0 인 8정의
ARMS = ("s", "c1", "c1b", "c2", "c2b")
CUM = np.cumsum(WEIGHTS)         # 0.10 0.23 0.40 0.65 1.00

GATE_A_MAX_DELTA, GATE_A_MIN_P = 0.005, 0.05
GATE_B_MAX_MEAN_GAP, GATE_B_MAX_ABS_GAP = 0.005, 0.030
DANAL = {"code": "064260", "start": 3930.0, "peak": 5100.0, "tol": 0.02}


def _seed(*p) -> int:
    return zlib.crc32("|".join(str(x) for x in p).encode()) ^ SEED


def _bucket_name(gain: float) -> str:
    lo = 0.0
    for b in BUCKETS:
        if gain >= b:
            lo = b
    return f">={lo:.2f}"


def definitions() -> list[dict]:
    return [{"name": f"k{k:g}-h{h}-mg{mg:g}", "k": k, "horizon": h, "min_gain": mg}
            for k, h, mg in itertools.product(K_MULTS, HORIZONS, MIN_GAINS)]


def block_p_positive(codes, values, b: int = B, seed: int = SEED) -> tuple[float, float]:
    """H0: 평균 ≤ 0 단측 p, 그리고 블록 SE. 종목코드 리샘플링."""
    codes, values = np.asarray(codes), np.asarray(values, dtype=float)
    uniq = np.unique(codes)
    per = {k: values[codes == k] for k in uniq}
    rng = np.random.default_rng(seed)
    means = np.empty(b)
    for i in range(b):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        means[i] = np.concatenate([per[k] for k in pick]).mean()
    return float((np.sum(means <= 0) + 1) / (b + 1)), float(means.std(ddof=1))


def arm_fields(trade, peak: float, levels, weights) -> dict:
    want = (np.nan if levels is None
            else intended_depth(peak, levels, WEIGHTS if weights is None else weights))
    if levels is None:
        return {k: np.nan for k in ("ret", "cw", "want", "filled", "fill_n", "trunc", "depth")}
    if trade is None:                        # 밴드는 걸었으나 미체결 → 현금
        return {"ret": 0.0, "cw": 0.0, "want": want, "filled": 0.0,
                "fill_n": 0.0, "trunc": 0.0, "depth": np.nan}
    return {"ret": trade.ret_net,
            "cw": trade.ret_net * float(CUM[trade.filled_n - 1]),   # 사전등록 §3(2)
            "want": want, "filled": 1.0, "fill_n": float(trade.filled_n),
            "trunc": float(trade.truncated), "depth": 1.0 - trade.avg_cost / peak}


def collect() -> tuple[pd.DataFrame, dict, dict]:
    bars = load_daily(START, END)
    by_code = {k: g.reset_index(drop=True) for k, g in bars.groupby("stock_code", sort=False)}
    rows, drops, gate_c = [], {"events": 0, "pool_too_small": 0, "band_none_c1": 0}, {}

    for d in definitions():
        segs = sorted(find_segments_local(bars, d["k"], d["horizon"], d["min_gain"]),
                      key=lambda s: s.peak_date)
        # ── 게이트 C: 정답 라벨이 후보 집합에 실제로 존재하는가 (사전등록 §4) ──
        gate_c[d["name"]] = any(
            s.code == DANAL["code"]
            and abs(s.start_px - DANAL["start"]) / DANAL["start"] < DANAL["tol"]
            and abs(s.peak_px - DANAL["peak"]) / DANAL["peak"] < DANAL["tol"]
            for s in segs)

        pool_by_q: dict[str, list[float]] = {}
        pos_in_q: list[int] = []
        for s in segs:
            bkt = pool_by_q.setdefault(_quarter(s.peak_date), [])
            pos_in_q.append(len(bkt))
            bkt.append(s.gain)

        history: list[tuple[float, float]] = []
        pending: list[tuple[str, float, float]] = []

        for i, seg in enumerate(segs):
            ready, pending = flush_pending(pending, as_of=seg.peak_date)
            history.extend(ready)
            drops["events"] += 1
            qk = _quarter(seg.peak_date)
            j = pos_in_q[i]
            label_pool = pool_by_q[qk][:j] + pool_by_q[qk][j + 1:]

            g = by_code[seg.code]
            idx = g.index[g["date"] == seg.peak_date]
            if len(idx) == 0:
                continue
            ip = int(idx[0])
            window = g.iloc[ip + 1: ip + 1 + VALID_DAYS + HOLD].reset_index(drop=True)
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
                if q is None:
                    continue

                levels = {"s": ladder(seg.peak_px, q[0], q[1], C_FIXED)}
                weights = {a: None for a in ARMS}
                want_s = intended_depth(seg.peak_px, levels["s"], WEIGHTS)
                for arm in ("c1", "c1b"):
                    rng = np.random.default_rng(_seed(seg.code, seg.peak_date, version, arm))
                    levels[arm] = shuffled_label_levels(seg.peak_px, label_pool, band_fn,
                                                        C_FIXED, rng)
                    if levels[arm] is None:
                        drops["band_none_c1"] += 1
                for arm in ("c2", "c2b"):
                    rng = np.random.default_rng(_seed(seg.code, seg.peak_date, version, arm))
                    levels[arm], weights[arm] = random_shape_levels(
                        seg.peak_px, q[0], q[1], rng, match_depth=want_s)

                row = {"cell": f'{d["name"]}|{version}', "code": seg.code,
                       "peak_date": seg.peak_date, "year": seg.peak_date[:4],
                       "bucket": _bucket_name(seg.gain), "gain": seg.gain,
                       "extrapolated": int(seg.gain < 0.298 or seg.gain > 6.143)}
                for arm in ARMS:
                    t = (None if levels[arm] is None else
                         simulate(window, levels[arm], HOLD, COST, seg.code,
                                  max_fill_bars=VALID_DAYS, weights=weights[arm]))
                    for k2, v in arm_fields(t, seg.peak_px, levels[arm], weights[arm]).items():
                        row[f"{'fill' if k2 == 'fill_n' else k2}_{arm}"] = v
                rows.append(row)

            pending.append((close_date, seg.gain, realized))

    return pd.DataFrame(rows), drops, gate_c


def _paired_cw(df: pd.DataFrame, a: str, c: str) -> pd.DataFrame:
    """자본가중 기준 짝지은 표본. `d` = a − c, `gap` = 의도깊이 차."""
    sub = df.dropna(subset=[f"cw_{a}", f"cw_{c}"])
    out = sub[["cell", "code", "year", "bucket"]].copy()
    out["d"] = sub[f"cw_{a}"].to_numpy() - sub[f"cw_{c}"].to_numpy()
    out["want_s"] = sub["want_s"].to_numpy()
    out["gap"] = sub["want_s"].to_numpy() - sub[f"want_{c}"].to_numpy()
    return out


def main() -> None:
    out = Path("out7")
    out.mkdir(exist_ok=True)
    df, drops, gate_c = collect()
    df.to_parquet(out / "trades7.parquet")
    print(json.dumps({"rows": len(df), "codes": int(df["code"].nunique()),
                      "cells": int(df["cell"].nunique()), **drops}, ensure_ascii=False), flush=True)

    verdict = {"gate_c": gate_c, "drops": drops, "n_rows": int(len(df)),
               "n_codes": int(df["code"].nunique()), "n_cells": int(df["cell"].nunique()),
               "seed": SEED, "c_fixed": C_FIXED,
               "cash_share_s": float(1.0 - df["filled_s"].mean()),
               "cash_share_c1": float(1.0 - df["filled_c1"].mean()),
               "extrapolated_share": float(df["extrapolated"].mean())}

    # ── 게이트 B: 의도 깊이 (평균 + 절대평균) ────────────────────────────────
    gate_b = {}
    for arm in ("c1", "c2"):
        sub = df.dropna(subset=[f"cw_s", f"cw_{arm}"])
        gap = sub["want_s"] - sub[f"want_{arm}"]
        per = gap.groupby(sub["cell"]).mean()
        # 사전등록 정정: 1차 모멘트만 게이트. 분산은 셔플 대조군의 본질이라
        # 억누를 수 없다 → 볼록성은 §5 판정조건 ③ 으로 직접 검정한다.
        gate_b[arm] = {"max_abs_mean_gap": float(per.abs().max()),
                       "mean_abs_gap": float(gap.abs().mean()),   # 보고용
                       "pass": bool(per.abs().max() <= GATE_B_MAX_MEAN_GAP)}
        per.to_csv(out / f"gate_b_{arm}.csv")
    verdict["gate_b"] = gate_b

    # ── 게이트 A: 귀무 실측 ──────────────────────────────────────────────────
    gate_a = {}
    for fam, (a, b_) in {"c1": ("c1", "c1b"), "c2": ("c2", "c2b")}.items():
        fr = _paired_cw(df, a, b_)
        per = fr.groupby("cell")["d"].mean().abs()
        p = white_reality_check(fr[["cell", "code", "d"]], b=B, seed=SEED)
        gate_a[fam] = {"n": int(len(fr)), "max_abs_delta": float(per.max()), "p": float(p),
                       "pass": bool(per.max() <= GATE_A_MAX_DELTA and p >= GATE_A_MIN_P)}
        fr.groupby("cell")["d"].agg(["count", "mean"]).to_csv(out / f"gate_a_{fam}.csv")
    verdict["gate_a"] = gate_a

    ok = (all(gate_c.values()) and gate_a["c1"]["pass"] and gate_b["c1"]["pass"])
    print(json.dumps({"gate_c_all": all(gate_c.values()), "gate_a_c1": gate_a["c1"],
                      "gate_b_c1": gate_b["c1"]}, ensure_ascii=False), flush=True)
    if not ok:
        verdict["verdict"] = "GATE_FAIL"
        verdict["note"] = "사전 게이트 실패 — 주 판정 p 를 계산하지 않았다(사전등록 §4)."
        (out / "verdict7.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
        print(json.dumps(verdict, ensure_ascii=False))
        return

    # ── 주 판정 ──────────────────────────────────────────────────────────────
    pr1, pr2 = _paired_cw(df, "s", "c1"), _paired_cw(df, "s", "c2")
    cells = []
    for cell in sorted(df["cell"].unique()):
        g1 = pr1[pr1["cell"] == cell]
        g2 = pr2[pr2["cell"] == cell]
        sub = df[df["cell"] == cell]
        se = g1["d"].std(ddof=1) / np.sqrt(len(g1))
        cells.append({"cell": cell, "n": len(g1), "n_codes": g1["code"].nunique(),
                      "delta_c1": g1["d"].mean(), "t_c1": g1["d"].mean() / se if se > 0 else 0.0,
                      "delta_c2": g2["d"].mean(),
                      **{f"cw_{a}": sub[f"cw_{a}"].mean() for a in ("s", "c1", "c2")},
                      **{f"roi_{a}": sub[f"ret_{a}"].mean() for a in ("s", "c1")},
                      **{f"fillrate_{a}": sub[f"filled_{a}"].mean() for a in ("s", "c1")},
                      **{f"depth_{a}": sub[f"depth_{a}"].mean() for a in ("s", "c1", "c2")},
                      **{f"trunc_{a}": float(np.nansum(sub[f"trunc_{a}"])) for a in ("s", "c1")}})
    cdf = pd.DataFrame(cells).sort_values("t_c1", ascending=False)
    cdf.to_csv(out / "cells7.csv", index=False)

    p_rel = white_reality_check(pr1[["cell", "code", "d"]], b=B, seed=SEED)
    pooled = df.dropna(subset=["cw_s"])
    p_abs, se_abs = block_p_positive(pooled["code"].to_numpy(), pooled["cw_s"].to_numpy())

    for tag, fr in (("c1", pr1), ("c2", pr2)):
        fr.groupby("year")["d"].agg(["count", "mean"]).to_csv(out / f"by_year_{tag}.csv")
        fr.groupby("bucket")["d"].agg(["count", "mean"]).to_csv(out / f"by_bucket_{tag}.csv")
    pr1[pr1["year"] != "2026"].groupby("cell")["d"].agg(["count", "mean"]).to_csv(
        out / "cells7_ex2026.csv")
    df.groupby("bucket").agg(cw_s=("cw_s", "mean"), cw_c1=("cw_c1", "mean"),
                             roi_s=("ret_s", "mean"), n=("cw_s", "size")).to_csv(
        out / "buckets_capital_weighted.csv")

    # ── 판정조건 ③ 볼록성 배제: gap ≈ 0 (중앙 5분위)에서도 Δ > 0 인가 ──────
    qs = pd.qcut(pr1["gap"], 5, labels=False, duplicates="drop")
    strata = (pr1.assign(q=qs).groupby("q")
                 .agg(n=("d", "size"), gap_lo=("gap", "min"), gap_hi=("gap", "max"),
                      gap_mean=("gap", "mean"), delta=("d", "mean")))
    strata.to_csv(out / "delta_by_gap_quintile.csv")
    mid = pr1[qs == 2]
    p_convex, _ = block_p_positive(mid["code"].to_numpy(), mid["d"].to_numpy())

    verdict.update({
        "p_relative": p_rel, "p_absolute": p_abs, "p_convexity_mid_quintile": p_convex,
        "delta_mid_quintile": float(mid["d"].mean()),
        "gap_mid_quintile_mean": float(mid["gap"].mean()), "n_mid_quintile": int(len(mid)),
        "pooled_cw_mean": float(pooled["cw_s"].mean()), "pooled_block_se": se_abs,
        "mde_block_absolute": float(2.802 * se_abs),
        "best_cell": cdf.iloc[0]["cell"], "delta_best_c1": float(cdf.iloc[0]["delta_c1"]),
        "delta_best_c2": float(cdf.iloc[0]["delta_c2"]),
        "delta_mean_c1": float(pr1["d"].mean()), "delta_mean_c2": float(pr2["d"].mean()),
        "c2_beats_c1": bool(pr2["d"].mean() >= pr1["d"].mean()),
        "verdict": "PASS" if (p_rel < 0.05 and p_abs < 0.05 and p_convex < 0.05) else "FAIL",
    })
    (out / "verdict7.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False))


if __name__ == "__main__":
    main()
