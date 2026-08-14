# -*- coding: utf-8 -*-
"""살아남은 5축을 「필터」로 걸면 하루에 몇 종목이 남는가 (선별력 측정)."""
import sys, csv
import numpy as np, pandas as pd
from run_selection import load, build_features, FEATS, REG
from run_tests import CODES
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

df = build_features(load())
SURV = {"f1_tv_mcap": 99.4, "f2_tv": 96.4, "f4_vol20": 97.4,
        "f6_spikes60": 95.7, "f8_ma20dev": 98.4}   # 관측 중앙 백분위를 문턱으로

d = df[(df.date >= "2026-07-13") & (df.date <= "2026-08-14")].copy()
mask = np.ones(len(d), dtype=bool)
for f, th in SURV.items():
    mask &= (d[f + "_pct"] >= th).fillna(False).values
d["pass_all"] = mask

per_day = d.groupby("date").pass_all.sum()
uni = d.groupby("date").size()
print(f"기간 {d.date.min().date()}~{d.date.max().date()} · {len(per_day)}거래일\n")
print(f"5축 전부 통과 종목 수/일: 중앙 **{per_day.median():.0f}** "
      f"· 평균 {per_day.mean():.1f} · 최소 {per_day.min()} · 최대 {per_day.max()}")
print(f"유니버스 대비: 중앙 {per_day.median()/uni.median()*100:.2f}%\n")

# 등록일이 특정된 7건이 그날 필터를 통과하는가 (재현율)
print("등록일 특정 7건의 그날 통과 여부:")
trades = list(csv.DictReader(open("ledger_trades.csv", encoding="utf-8")))
hit = 0
for (log_no, item), reg in REG.items():
    name = next(t["stock_name"] for t in trades
                if t["post_log_no"] == log_no and t["item_no"] == item)
    row = d[(d.stock_code == CODES[name]) & (d.date == pd.Timestamp(reg))]
    if row.empty:
        print(f"  {name:12s} {reg}  (데이터 없음)"); continue
    r = row.iloc[0]
    ok = bool(r.pass_all); hit += ok
    fails = [f for f, th in SURV.items() if not (r[f + "_pct"] >= th)]
    print(f"  {name:12s} {reg}  {'✅ 통과' if ok else '❌ 탈락 ' + str(fails)}")
print(f"\n재현율 {hit}/7")
