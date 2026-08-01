"""정의 격자를 라벨에 맞춰 채점하고 상위 3개를 고른다."""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pandas as pd

from lab.bands import exogenous_quantiles, ladder
from lab.calibrate import score_grade1, score_grade2
from lab.data import load_daily
from lab.segments import find_segments

VARIANTS = ("low", "surge_open", "prev_close")
LOOKBACKS = (60, 120, 250)
MIN_GAINS = (0.30, 0.50, 1.00)
VALID_DAYS = 20


def _fill_missing_grade1_codes(labels: dict) -> None:
    """1급 항목의 code 가 null 이면 같은 name 의 2급 항목에서 보충한다.

    다날 1급 라벨은 브리프 verbatim 유지 목적으로 code 가 null 로 남아 있으나
    (2급에는 064260 이 기재돼 있음), 그대로 두면 g1 채점 리스트 컴프리헨션의
    `lab.get("code")` 가드에 걸려 다날이 통째로 빠지고 1급 표본이 2건으로
    줄어든다.
    """
    g2_code_by_name = {s["name"]: s["code"] for s in labels["grade2"] if s.get("code")}
    for s in labels["grade1"]:
        if not s.get("code"):
            s["code"] = g2_code_by_name.get(s["name"])


def main() -> None:
    out = Path("out")
    out.mkdir(exist_ok=True)
    labels = json.loads(Path("labels/labels.json").read_text(encoding="utf-8"))
    _fill_missing_grade1_codes(labels)
    bars = load_daily("2021-01-04", "2026-07-31")

    codes = {s["code"] for s in labels["grade1"] + labels["grade2"] if s.get("code")}
    sub = bars[bars["stock_code"].isin(codes)]
    skipped = [s["name"] for s in labels["grade2"] if not s.get("code")]

    rows = []
    for variant, lb, mg in itertools.product(VARIANTS, LOOKBACKS, MIN_GAINS):
        segs = find_segments(sub, variant, lb, mg)
        by_code: dict[str, list] = {}
        for s in segs:
            by_code.setdefault(s.code, []).append(s)

        g1 = [min(score_grade1(s, lab) for s in by_code[lab["code"]])
              for lab in labels["grade1"]
              if lab.get("code") and lab["code"] in by_code]

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

        rows.append({"variant": variant, "lookback": lb, "min_gain": mg,
                     "n_segments": len(segs),
                     "g1_n": len(g1), "g1_err": sum(g1) / len(g1) if g1 else None,
                     "g2_n": len(g2), "g2_err": sum(g2) / len(g2) if g2 else None})

    df = pd.DataFrame(rows)
    df.to_csv(out / "calibration_scores.csv", index=False)

    ranked = (df.dropna(subset=["g1_err", "g2_err"])
                .assign(score=lambda x: x["g1_err"].rank() + x["g2_err"].rank())
                .sort_values("score").head(3))
    selected = [{"name": f"{r.variant}-lb{r.lookback}-mg{r.min_gain}",
                 "variant": r.variant, "lookback": int(r.lookback),
                 "min_gain": float(r.min_gain), "valid_days": VALID_DAYS}
                for r in ranked.itertuples()]
    (out / "selected_definitions.json").write_text(
        json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8")

    print(df.to_string(index=False))
    print("\n코드 미확인으로 채점 제외:", skipped or "없음")
    print("selected:", json.dumps(selected, ensure_ascii=False))


if __name__ == "__main__":
    main()
