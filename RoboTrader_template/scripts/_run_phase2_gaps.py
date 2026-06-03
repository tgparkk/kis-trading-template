"""Phase2 진입필터 스윕 — 누락분만 채우는 gap-filler (일회성).

★측정 전용. 라이브 전략 무수정. 출력 D:/tmp/multiverse2/phase2_filters/<skey>/<plabel>/<wkey>/.

기존 elder=완주(skip), minervini=부분, haru/tl/dt3=미실행. 이미 존재하는 TSV 는 skip,
없는 (strategy,plabel,window) 조합만 driver 직접 호출. FULL 윈도우 생략(단순 sl/tp FULL
은 MaxDD≈0.99 퇴화로 신뢰불가, 시간만 잡아먹음).

rule-module/rule 은 task spec 권위 적용:
  haru_silijeon  : rules_daily / daily_ma20_pullback (K3)
  trading_legends: rules_daily / ma5_pullback         (K3)
  daytrading_3methods: rules / breakout_prev_high      (K3)
  minervini_vcp  : rules / volume_dryup                (K3, 누락 윈도우만)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = Path("D:/tmp/multiverse2/phase2_filters")
PY = sys.executable
DRIVER = str(ROOT / "scripts" / "book_portfolio_multiverse.py")

# (skey, book, rules_module, rule, entry_grid, exit_grid, K-list)
STRATS = [
    ("minervini", "minervini_vcp", "rules", "volume_dryup",
     '{"ratio_max":[0.7]}', '{"sl":[0.08],"tp":[0.12],"mh":[20]}', ["3"]),
    ("haru_ma20", "haru_silijeon", "rules_daily", "daily_ma20_pullback",
     '{"ma_window":[20]}', '{"sl":[0.10],"tp":[0.10],"mh":[20]}', ["3"]),
    ("tl_ma5", "trading_legends", "rules_daily", "ma5_pullback",
     '{"ma_window":[5]}', '{"sl":[0.03],"tp":[0.15],"mh":[10]}', ["3"]),
    ("dt3_breakout", "daytrading_3methods", "rules", "breakout_prev_high",
     '{"high_window":[20]}', '{"sl":[0.10],"tp":[0.10],"mh":[10]}', ["3"]),
]

# FULL 생략 — 4개 국면창만.
WINDOWS = [
    ("2021H2", "2021-07-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2024H2", "2024-07-01", "2024-12-31"),
    ("BULL", "2025-06-01", "2026-05-27"),
]

# (plabel, filter-list, threshold)
FILTER_PASSES = [
    ("base", ["none", "rs_rank", "mkt_rs", "ma_slope"], 0.50),
    ("rs070", ["rs_rank"], 0.70),
    ("adx20", ["adx"], 20.0),
    ("adx25", ["adx"], 25.0),
]


def run_one(skey, book, mod, rule, egrid, xgrid, klist, wkey, start, end,
            plabel, filters, thr):
    out = OUT_ROOT / skey / plabel / wkey
    tsv = out / f"book_portfolio_{book}_{rule}.tsv"
    if tsv.exists():
        print(f"  SKIP exists: {skey}/{plabel}/{wkey}", flush=True)
        return
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        PY, DRIVER, "--book", book, "--rules-module", mod, "--rule", rule,
        "--granularity", "daily", "--start", start, "--end", end,
        "--entry-grid", egrid, "--exit-grid", xgrid,
        "--K-list", *klist, "--universe", "top_volume:50",
        "--max-per-stock", "3000000", "--initial-capital", "10000000",
        "--entry-filter", *filters, "--filter-threshold", str(thr),
        "--filter-n", "60", "--workers", "1", "--top-k", "30",
        "--out", str(out),
    ]
    print(f">>> RUN {skey}/{plabel}/{wkey}: filters={filters} thr={thr}", flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)
    if not tsv.exists():
        print(f"  !! NO TSV (rc={r.returncode}) STDERR tail:\n{(r.stderr or '')[-2000:]}",
              flush=True)
    else:
        print(f"  OK rc={r.returncode} -> {tsv}", flush=True)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None  # optional skey filter
    for skey, book, mod, rule, egrid, xgrid, klist in STRATS:
        if only and skey != only:
            continue
        for wkey, start, end in WINDOWS:
            for plabel, filters, thr in FILTER_PASSES:
                run_one(skey, book, mod, rule, egrid, xgrid, klist,
                        wkey, start, end, plabel, filters, thr)
    print("=== gap-filler done ===", flush=True)


if __name__ == "__main__":
    main()
