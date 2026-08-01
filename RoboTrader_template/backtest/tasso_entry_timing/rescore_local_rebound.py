"""국지 반등 정의 재채점 — 신고가 조건을 뺀 급등봉 기준 구간.

⚠️ **채점표만 본다. Δ·p 는 계산하지 않는다.**
묻는 것 둘:
  (1) 태쏘의 정답 사건이 후보 집합에 **실제로 들어오는가** (`g1_hit`)
  (2) 들어온다면 앵커 재현이 기존 `low`(0.3114)보다 나은가 (`g1_err`)
"""
import itertools
import json
from pathlib import Path

import pandas as pd

from lab.bands import exogenous_quantiles, ladder
from lab.calibrate import score_grade1, score_grade2
from lab.calibrate_run import _fill_missing_grade1_codes
from lab.data import load_daily
from lab.segments import find_segments_local

K_MULTS = (3.0, 5.0, 10.0)
HORIZONS = (5, 10, 20)
MIN_GAINS = (0.15, 0.25, 0.50)
TOL = 0.02          # 정답 재현 판정 허용오차 (시작점·최고점 각각 2%)

bars = load_daily("2021-01-04", "2026-07-31")

# ── 1. 다날 직접 확인 — 정답 사건이 생성되는가 ────────────────────────────────
print("=== 다날 064260 정답: 시작점 3,930 → 최고점 5,100 (+29.77%) ===")
d = bars[bars["stock_code"] == "064260"]
for k in K_MULTS:
    segs = [s for s in find_segments_local(d, k, 10, 0.15)
            if s.peak_date >= "2026-07-01" and s.peak_date <= "2026-07-31"]
    hit = [s for s in segs if abs(s.start_px - 3930) / 3930 < TOL and abs(s.peak_px - 5100) / 5100 < TOL]
    tag = (f"✅ 재현  시작점 {hit[0].start_px:,.0f} / 최고점 {hit[0].peak_px:,.0f} / "
           f"상승폭 {hit[0].gain:.2%}") if hit else f"❌ 미재현 (7월 후보 {len(segs)}개)"
    print(f"  k={k:>4} : {tag}")

# ── 2. 격자 채점 + 정답 존재 여부 단언 ────────────────────────────────────────
labels = json.loads(Path("labels/labels.json").read_text(encoding="utf-8"))
_fill_missing_grade1_codes(labels)
g1_labels = [l for l in labels["grade1"] if l.get("code")]
codes = {s["code"] for s in labels["grade1"] + labels["grade2"] if s.get("code")}
sub = bars[bars["stock_code"].isin(codes)]

print(f"\n1급 라벨 {len(g1_labels)}건: " + " · ".join(
    f'{l["name"]}({l["code"]}) {l["start"]:,.0f}→{l["peak"]:,.0f}' for l in g1_labels))

rows = []
for k, h, mg in itertools.product(K_MULTS, HORIZONS, MIN_GAINS):
    segs = find_segments_local(sub, k, h, mg)
    by_code: dict[str, list] = {}
    for s in segs:
        by_code.setdefault(s.code, []).append(s)

    hits, errs = [], []
    for lab in g1_labels:
        cand = by_code.get(lab["code"], [])
        if not cand:
            continue
        errs.append(min(score_grade1(s, lab) for s in cand))
        hits.append(any(abs(s.start_px - lab["start"]) / lab["start"] < TOL
                        and abs(s.peak_px - lab["peak"]) / lab["peak"] < TOL for s in cand))

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

    rows.append({"k_mult": k, "horizon": h, "min_gain": mg, "n_segments": len(segs),
                 "g1_n": len(errs), "g1_hit": int(sum(hits)),
                 "g1_err": sum(errs) / len(errs) if errs else None,
                 "g2_n": len(g2), "g2_err": sum(g2) / len(g2) if g2 else None})

df = pd.DataFrame(rows)
df.to_csv("out/calibration_scores_local.csv", index=False)
print("\n=== 국지 반등 정의 채점표 (g1_hit = 정답을 실제로 재현한 라벨 수 / 3) ===")
print(df.to_string(index=False))

print("\n=== 기존 정의와 비교 ===")
print(f"  기존 최고 (low/lb120/mg0.3)  : g1_err 0.3114  g1_hit ?  ← 정답 존재 여부를 잰 적 없음")
best = df.dropna(subset=["g1_err"]).nsmallest(1, "g1_err").iloc[0]
print(f"  국지 최고 (k={best.k_mult}/h={best.horizon}/mg={best.min_gain}) : "
      f"g1_err {best.g1_err:.4f}  g1_hit {int(best.g1_hit)}/3  구간 {int(best.n_segments):,}개")
print(f"\n  g1_hit ≥ 1 인 셀: {int((df.g1_hit >= 1).sum())}/{len(df)}")
print("\n(주의: 이것은 채점표다. Δ·p 는 계산하지 않았다.)")
