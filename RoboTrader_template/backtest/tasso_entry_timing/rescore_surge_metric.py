"""캘리브레이션 재채점 — 급등봉 판정축만 거래량 → 거래대금으로 바꾼다.

⚠️ **채점표만 본다. Δ·p 는 계산하지 않는다.** 사장님 지시(2026-08-01).
질문 하나: 앵커 실측이 확정한 `prev_close` 가, 탐지기를 고치면 `low` 를 이기는가?
"""
import itertools
import json
from pathlib import Path

import pandas as pd

from lab.bands import exogenous_quantiles, ladder
from lab.calibrate import score_grade1, score_grade2
from lab.calibrate_run import VARIANTS, LOOKBACKS, MIN_GAINS, _fill_missing_grade1_codes
from lab.data import load_daily
from lab.segments import find_segments

bars = load_daily("2021-01-04", "2026-07-31")

# ── 1. 다날 직접 확인: 탐지기를 고치면 시작점 3,930 이 나오는가 ──────────────
print("=== 다날 064260 — 태쏘 화면: 시작점 3,930 / 최고점 5,100 ===")
danal = bars[bars["stock_code"] == "064260"]
for metric in ("volume", "value"):
    segs = [s for s in find_segments(danal, "prev_close", 60, 0.20, surge_by=metric)
            if s.peak_date.startswith("2026-07")]
    hit = [s for s in segs if abs(s.peak_px - 5100) < 1]
    if hit:
        s = min(hit, key=lambda x: abs(x.start_px - 3930))
        mark = "완전일치" if abs(s.start_px - 3930) < 1 else f"불일치(오차 {abs(s.start_px-3930)/3930:.2%})"
        print(f"  surge_by={metric:7} -> 시작점 {s.start_px:>8,.0f} / 최고점 {s.peak_px:>8,.0f}  {mark}")
    else:
        print(f"  surge_by={metric:7} -> 최고점 5,100 구간을 못 찾음 (후보 {len(segs)}개)")

# ── 2. 격자 재채점 ────────────────────────────────────────────────────────────
labels = json.loads(Path("labels/labels.json").read_text(encoding="utf-8"))
_fill_missing_grade1_codes(labels)
codes = {s["code"] for s in labels["grade1"] + labels["grade2"] if s.get("code")}
sub = bars[bars["stock_code"].isin(codes)]

rows = []
for metric, variant, lb, mg in itertools.product(("volume", "value"), VARIANTS, LOOKBACKS, MIN_GAINS):
    segs = find_segments(sub, variant, lb, mg, surge_by=metric)
    by_code: dict[str, list] = {}
    for s in segs:
        by_code.setdefault(s.code, []).append(s)

    g1 = [min(score_grade1(s, lab) for s in by_code[lab["code"]])
          for lab in labels["grade1"] if lab.get("code") and lab["code"] in by_code]
    g2 = []
    for lab in labels["grade2"]:
        code, fills = lab.get("code"), lab.get("fills") or []
        if not code or code not in by_code or not fills:
            continue
        best = float("inf")
        for s in by_code[code]:
            q1, q3 = exogenous_quantiles(s.gain)
            best = min(best, score_grade2(ladder(s.peak_px, q1, q3, 0.8), fills))
        g2.append(best)

    rows.append({"surge_by": metric, "variant": variant, "lookback": lb, "min_gain": mg,
                 "n_segments": len(segs),
                 "g1_n": len(g1), "g1_err": sum(g1) / len(g1) if g1 else None,
                 "g2_n": len(g2), "g2_err": sum(g2) / len(g2) if g2 else None})

df = pd.DataFrame(rows)
df.to_csv("out/calibration_scores_surge_metric.csv", index=False)

print("\n=== 변형별 최소 앵커오차 g1_err (낮을수록 저자의 앵커에 가깝다) ===")
piv = df.pivot_table(index="variant", columns="surge_by", values="g1_err", aggfunc="min").round(4)
piv["개선"] = (piv["volume"] - piv["value"]).round(4)
print(piv.to_string())

print("\n=== 구간 생성 수 (선택 아티팩트 진단: 많을수록 최소오차 채점에 유리) ===")
print(df.pivot_table(index="variant", columns="surge_by", values="n_segments", aggfunc="max").to_string())

print("\n=== 거래대금 기준 상위 6개 (g1_err 순) ===")
v = df[df.surge_by == "value"].dropna(subset=["g1_err"]).nsmallest(6, "g1_err")
print(v[["variant", "lookback", "min_gain", "n_segments", "g1_err", "g2_err"]].to_string(index=False))

print("\n=== 4차 선정식(g1 순위 + g2 순위)을 거래대금 기준에 적용하면 ===")
for metric in ("volume", "value"):
    d = df[df.surge_by == metric].dropna(subset=["g1_err", "g2_err"]).copy()
    d["score"] = d["g1_err"].rank() + d["g2_err"].rank()
    top = d.nsmallest(3, "score")
    print(f"  {metric:7} -> " + " · ".join(f"{r.variant}/lb{r.lookback}/mg{r.min_gain}"
                                           for r in top.itertuples()))
print("\n(주의: 이것은 채점표다. Δ·p 는 계산하지 않았다.)")
