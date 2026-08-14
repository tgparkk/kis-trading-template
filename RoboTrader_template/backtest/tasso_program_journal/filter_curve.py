# -*- coding: utf-8 -*-
"""공통 문턱 τ 를 5축에 동시에 걸었을 때의 재현율 ↔ 선별력 곡선."""
import sys, csv
import numpy as np, pandas as pd
from run_selection import load, build_features, REG
from run_tests import CODES
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

df = build_features(load())
SURV = ["f1_tv_mcap", "f2_tv", "f4_vol20", "f6_spikes60", "f8_ma20dev"]
d = df[(df.date >= "2026-07-13") & (df.date <= "2026-08-14")].copy()

trades = list(csv.DictReader(open("ledger_trades.csv", encoding="utf-8")))
targets = []
for (log_no, item), reg in REG.items():
    name = next(t["stock_name"] for t in trades
                if t["post_log_no"] == log_no and t["item_no"] == item)
    targets.append((name, CODES[name], pd.Timestamp(reg)))

print("## 등록일 당일의 실제 백분위\n")
print("| 종목 | 등록일 | " + " | ".join(f.split('_')[0] for f in SURV) + " | 최솟값 |")
print("|---|---|" + "---|" * (len(SURV) + 1))
mins = []
for name, code, reg in targets:
    r = d[(d.stock_code == code) & (d.date == reg)]
    if r.empty:
        continue
    r = r.iloc[0]
    vals = [r[f + "_pct"] for f in SURV]
    mn = np.nanmin(vals); mins.append(mn)
    print(f"| {name} | {reg.date()} | "
          + " | ".join(f"{v:.0f}" if pd.notna(v) else "—" for v in vals)
          + f" | **{mn:.0f}** |")

print("\n## 공통 문턱 τ — 재현율 ↔ 하루 통과 종목 수\n")
print("| τ (5축 전부) | 재현율 /7 | 통과 종목/일 (중앙) | 통과 종목/일 (평균) |")
print("|---|---|---|---|")
for tau in [99, 95, 90, 85, 80, 70, 60, 50, 40]:
    m = np.ones(len(d), dtype=bool)
    for f in SURV:
        m &= (d[f + "_pct"] >= tau).fillna(False).values
    d["_p"] = m
    per = d.groupby("date")._p.sum()
    rec = 0
    for name, code, reg in targets:
        r = d[(d.stock_code == code) & (d.date == reg)]
        if not r.empty and bool(r.iloc[0]._p):
            rec += 1
    print(f"| {tau} | **{rec}/7** | {per.median():.0f} | {per.mean():.1f} |")
