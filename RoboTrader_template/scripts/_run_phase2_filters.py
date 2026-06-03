"""Phase2 진입 필터 스윕 러너 (일회성). book_portfolio_multiverse 를 subprocess 로
5전략 × 5윈도우 × (baseline + 필터×임계) 호출하고, 각 run 의 baseline(filter=none) row 와
필터 row 를 모아 요약 TSV 를 만든다.

★측정 전용. 라이브 전략 무수정. 출력 D:/tmp/multiverse2/phase2_filters/.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = Path("D:/tmp/multiverse2/phase2_filters")

PY = sys.executable
DRIVER = str(ROOT / "scripts" / "book_portfolio_multiverse.py")

# (key, book, rules_module, rule, entry_grid, exit_grid, K-list)
STRATS = [
    ("elder", "elder_triple_screen", "rules", "triple_screen_ema_pullback",
     '{"touch_band":[1.01]}', '{"sl":[0.05],"tp":[0.10],"mh":[20]}', ["10", "20"]),
    ("minervini", "minervini_vcp", "rules", "volume_dryup",
     '{"ratio_max":[0.7]}', '{"sl":[0.08],"tp":[0.12],"mh":[20]}', ["3"]),
    ("haru_ma20", "haru_silijeon", "rules", "ma20_pullback",
     '{"ma_window":[20]}', '{"sl":[0.10],"tp":[0.10],"mh":[20]}', ["3"]),
    ("tl_ma5", "trading_legends", "rules_daily", "ma5_pullback",
     '{"ma_window":[5]}', '{"sl":[0.03],"tp":[0.15],"mh":[10]}', ["3"]),
    ("dt3_breakout", "daytrading_3methods", "rules", "breakout_prev_high",
     '{"high_window":[20]}', '{"sl":[0.10],"tp":[0.10],"mh":[10]}', ["3"]),
]

WINDOWS = [
    ("2021H2", "2021-07-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2024H2", "2024-07-01", "2024-12-31"),
    ("BULL", "2025-06-01", "2026-05-27"),
]

# 필터 패스: (label, filter-list, threshold, n). rs_rank/adx 임계 2종, mkt_rs/ma_slope 1종.
FILTER_PASSES = [
    # base: rs_rank 임계는 threshold(0.5) 적용, mkt_rs/ma_slope 는 threshold 무시.
    ("base", ["none", "rs_rank", "mkt_rs", "ma_slope"], 0.50, 60),
    ("rs070", ["rs_rank"], 0.70, 60),
    ("adx20", ["adx"], 20.0, 60),
    ("adx25", ["adx"], 25.0, 60),
]


def run_one(skey, book, mod, rule, egrid, xgrid, klist, wkey, start, end,
            plabel, filters, thr, n):
    out = OUT_ROOT / skey / plabel / wkey
    out.mkdir(parents=True, exist_ok=True)
    tsv = out / f"book_portfolio_{book}_{rule}.tsv"
    if tsv.exists() and tsv.stat().st_size > 0:
        df = pd.read_csv(tsv, sep="\t")
        df["strategy"] = skey; df["window"] = wkey; df["pass"] = plabel; df["thr"] = thr
        print(f">>> skip existing {skey} {wkey} {plabel}", flush=True)
        return df
    cmd = [
        PY, DRIVER, "--book", book, "--rules-module", mod, "--rule", rule,
        "--granularity", "daily", "--start", start, "--end", end,
        "--entry-grid", egrid, "--exit-grid", xgrid,
        "--K-list", *klist, "--universe", "top_volume:50",
        "--max-per-stock", "3000000", "--initial-capital", "10000000",
        "--entry-filter", *filters, "--filter-threshold", str(thr),
        "--filter-n", str(n), "--workers", "1", "--top-k", "30",
        "--out", str(out),
    ]
    print(f"\n>>> {skey} {wkey} {plabel}: filters={filters} thr={thr}", flush=True)
    # 드라이버는 UTF-8 로 출력하므로 cp949 디코드 크래시 방지(errors=replace).
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1200)
    tsv = out / f"book_portfolio_{book}_{rule}.tsv"
    if not tsv.exists():
        print(f"  no tsv (rc={r.returncode}) STDERR tail:", (r.stderr or "")[-1500:], flush=True)
        return None
    if r.returncode != 0:
        print(f"  warn rc={r.returncode} but tsv exists", flush=True)
    df = pd.read_csv(tsv, sep="\t")
    df["strategy"] = skey
    df["window"] = wkey
    df["pass"] = plabel
    df["thr"] = thr
    return df


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    allrows = []
    for skey, book, mod, rule, egrid, xgrid, klist in STRATS:
        for wkey, start, end in WINDOWS:
            for plabel, filters, thr, n in FILTER_PASSES:
                df = run_one(skey, book, mod, rule, egrid, xgrid, klist,
                             wkey, start, end, plabel, filters, thr, n)
                if df is not None:
                    allrows.append(df)
    if allrows:
        full = pd.concat(allrows, ignore_index=True)
        summ = OUT_ROOT / "_phase2_summary.tsv"
        full.to_csv(summ, sep="\t", index=False)
        print(f"\n=== SUMMARY written: {summ} ({len(full)} rows) ===")


if __name__ == "__main__":
    main()
