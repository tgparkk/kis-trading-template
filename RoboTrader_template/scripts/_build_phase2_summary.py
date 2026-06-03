"""Phase2 요약 재구성 — 전 트리(elder 기존 + gap-filler 신규)의 개별 TSV 를 스캔해
_phase2_summary.tsv 로 합친다. _analyze_phase2_filters.py 의 입력.

경로 규약: <OUT_ROOT>/<skey>/<plabel>/<wkey>/book_portfolio_*.tsv
각 row 에 strategy=skey, window=wkey, pass=plabel, thr(plabel→임계) 부착.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT_ROOT = Path("D:/tmp/multiverse2/phase2_filters")

PASS_THR = {"base": 0.50, "rs070": 0.70, "adx20": 20.0, "adx25": 25.0}


def main():
    rows = []
    for tsv in sorted(OUT_ROOT.rglob("book_portfolio_*.tsv")):
        parts = tsv.relative_to(OUT_ROOT).parts
        if len(parts) != 4:
            continue
        skey, plabel, wkey, _ = parts
        df = pd.read_csv(tsv, sep="\t")
        df["strategy"] = skey
        df["window"] = wkey
        df["pass"] = plabel
        df["thr"] = PASS_THR.get(plabel, float("nan"))
        rows.append(df)
    full = pd.concat(rows, ignore_index=True)
    out = OUT_ROOT / "_phase2_summary.tsv"
    full.to_csv(out, sep="\t", index=False)
    print(f"=== summary rebuilt: {out} ({len(full)} rows) ===")
    print("strategies:", sorted(full["strategy"].unique()))
    print("windows:", sorted(full["window"].unique()))
    print("passes:", sorted(full["pass"].unique()))


if __name__ == "__main__":
    main()
