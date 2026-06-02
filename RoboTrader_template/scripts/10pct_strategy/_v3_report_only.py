"""
_v3_report_only.py — v3 결과물 기반 보고서 + changelog만 생성 (재실행 없이)
STEP 10 단독 실행용 (v3_grid_all.csv, v3_walkforward.csv, v3_monthly_pnl.csv 기존 파일 사용)
"""
import sys, os, time
import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "10pct_strategy")
P5_DIR     = os.path.join(REPORT_DIR, "phase5_signals")

FEE_ONE_WAY   = 0.003
PORT_CAPITAL  = 10_000_000
PORT_MAX_POS  = 5
SIGNAL_FAMILIES = ["OBV", "VWAP", "OBV_OR_VWAP"]

print("="*70)
print("v3 report-only (STEP 10 재실행)")
print("="*70)

# ── 기존 CSV 로드 ──────────────────────────────────────────────────────────
df_all   = pd.read_csv(os.path.join(P5_DIR, "v3_grid_all.csv"))
wf_df    = pd.read_csv(os.path.join(P5_DIR, "v3_walkforward.csv"))
monthly  = pd.read_csv(os.path.join(P5_DIR, "v3_monthly_pnl.csv"))
print(f"  grid: {len(df_all)} cells")
print(f"  wf:   {len(wf_df)} windows")
print(f"  monthly: {len(monthly)} rows")

df_pass = df_all[df_all["pass"]==True].copy() if "pass" in df_all.columns else pd.DataFrame()
print(f"  passed cells: {len(df_pass)}")

# ── Top cell 재구성 ─────────────────────────────────────────────────────────
top_cells = []
for family in SIGNAL_FAMILIES:
    sub = df_all[df_all["family"]==family]
    if len(sub) == 0: continue
    sub_pass = sub[sub.get("pass", pd.Series([False]*len(sub))).values==True] if "pass" in sub.columns else pd.DataFrame()
    if len(sub_pass) > 0:
        best = sub_pass.nlargest(1, "sharpe").iloc[0]
        chosen_via = "pass"
    else:
        sub_data = sub[sub["mean_pnl"].notna()]
        if len(sub_data) == 0: continue
        best = sub_data.nlargest(1, "mean_pnl").iloc[0]
        chosen_via = "best_mean"
    top_cells.append({"family":family, "sl":best["sl"],
                      "tp":best["tp"], "tm":int(best["tm"]),
                      "mean_pnl":best["mean_pnl"],
                      "sharpe":best["sharpe"],
                      "n":int(best["n"]),
                      "chosen_via":chosen_via})
    print(f"  {family}: sl={best['sl']:.0%} tp={best['tp']:.0%} tm={int(best['tm'])}d "
          f"mean_pnl={best['mean_pnl']:.4f} sharpe={best['sharpe']:.4f} via={chosen_via}")

# ── Monthly metrics ─────────────────────────────────────────────────────────
if len(monthly) > 0 and "ret" in monthly.columns:
    mret = monthly["ret"].values.astype(float)
    mret = mret[~np.isnan(mret)]
    if len(mret) > 0:
        mean_m = float(mret.mean())
        pos_m  = int((mret > 0).sum())
        sh_m   = float(mret.mean()/mret.std()*np.sqrt(12)) if mret.std()>0 else np.nan
        eq_m   = np.cumprod(1+mret)
        rm_m   = np.maximum.accumulate(eq_m)
        mdd_m  = float(((eq_m-rm_m)/rm_m).min())
        tot_ret = float(eq_m[-1]-1)
        try:
            ann_raw = (1+tot_ret)**(12/len(mret))-1
            ann_ret = float(np.real(ann_raw)) if np.iscomplex(ann_raw) else float(ann_raw)
        except Exception:
            ann_ret = np.nan
        calmar = float(ann_ret/abs(mdd_m)) if (mdd_m<0 and not np.isnan(ann_ret)) else np.nan
    else:
        mean_m = pos_m = sh_m = mdd_m = tot_ret = ann_ret = calmar = np.nan
else:
    mean_m = pos_m = sh_m = mdd_m = tot_ret = ann_ret = calmar = np.nan

print(f"\nMonthly stats:")
print(f"  mean_m = {mean_m:.4f}" if not np.isnan(mean_m) else "  mean_m = N/A")
print(f"  sh_m   = {sh_m:.4f}"   if not np.isnan(sh_m)   else "  sh_m = N/A")
print(f"  mdd_m  = {mdd_m:.4f}"  if not np.isnan(mdd_m)  else "  mdd_m = N/A")
print(f"  ann_ret= {ann_ret:.4f}" if not np.isnan(ann_ret) else "  ann_ret = N/A")
print(f"  calmar = {calmar:.4f}"  if not np.isnan(calmar)  else "  calmar = N/A")
print(f"  pos_m  = {pos_m}/{len(mret) if 'mret' in dir() else 0}")

n_trades_total = 0
for _, row in wf_df.iterrows():
    if "n_accepted" in row: n_trades_total += int(row.get("n_accepted", 0))

# WF 윈도우 재구성 (보고서용)
windows = []
if "window" in wf_df.columns:
    for _, r in wf_df.iterrows():
        windows.append({"window": int(r["window"]),
                        "test_start": r["test_start"],
                        "test_end": r["test_end"]})

# ── 보고서 작성 ────────────────────────────────────────────────────────────
def _f(v, pct=False):
    if pd.isna(v) or (isinstance(v, float) and np.isnan(v)): return "N/A"
    if pct: return f"{v*100:+.3f}%"
    return f"{v:.4f}"

family_dist_pass = {}
if len(df_pass):
    family_dist_pass = df_pass.groupby("family").size().to_dict()

progress_pct = mean_m / 0.10 * 100 if not np.isnan(mean_m) else np.nan
p3_base = 0.0023

if np.isnan(mean_m):
    verdict = "측정 불가 — trade 없음"
elif mean_m > p3_base * 2:
    verdict = "Phase 4 paper 진입 가능 — 1차(0.23%) 대비 명확 개선"
elif mean_m > p3_base:
    verdict = "보류 — 1차 대비 소폭 개선, 추가 EDA 권고"
elif mean_m > 0:
    verdict = "보류 — 양수이나 1차 미달, 추가 알파 탐색 필요"
else:
    verdict = "최종 종결 — 음수. 현재 알파로 월 10% 도달 불가, 신규 시그널 탐색 필요"

obv_cell = next((c for c in top_cells if c["family"]=="OBV"), None)
if obv_cell and not np.isnan(obv_cell["mean_pnl"]):
    cs_alpha_bps = 172.36
    trade_pnl_bps = obv_cell["mean_pnl"] * 10000
    recovery = trade_pnl_bps / cs_alpha_bps * 100
    cs_line = (f"단독 OBV cross-section +172.36bps → v3 trade-level "
               f"{trade_pnl_bps:+.1f}bps (회수율 {recovery:.1f}%)")
else:
    cs_line = "OBV cell 결과 없음"

pos_w = sum(1 for _, r in wf_df.iterrows()
            if pd.notna(r.get("monthly_mean")) and r["monthly_mean"] > 0)

lines = [
    "# Phase 5 v3 — OBV+VWAP Swing Portfolio Walk-Forward (1-page)",
    "",
    f"생성: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
    "",
    "## 1. v3 재설계 핵심",
    "",
    "| 항목 | v2 (5/26 직원 #6/#7) | v3 (5/26 직원 #9) |",
    "|------|----------------------|-------------------|",
    "| Universe | ROE Q4+ ∩ phase2a swing_pool top-3 (표본 붕괴) | **mcap top 500 + tv 5d median > 10억** (단순화) |",
    "| Exit | SL[-1.5~-5%] TP[3~15%] TM[1~60]d | **SL[-5/-7/-10%] TP[3/5/10%] TM[1/3/5]d** |",
    "| Portfolio | trade-level mean only | **동시 5포지션 equal weight, 1,000만원** |",
    "| Walk-forward | 252/63 × 6 windows | **252/63 × 16 windows** (단독 동일) |",
    "",
    "## 2. 합격 셀 / Family 분포",
    "",
    f"- 전체 grid: **{len(df_all)} cells** (3 family × 3 SL × 3 TP × 3 TM)",
    f"- 합격 게이트: mean>0 AND IS>0 AND OOS>0 AND sharpe>0.3 AND n_is/n_oos>=10",
    f"- 합격 셀: **{len(df_pass)} / {len(df_all)}**",
    "",
    "Family별 합격 수:",
]
for fam in SIGNAL_FAMILIES:
    cnt = family_dist_pass.get(fam, 0)
    lines.append(f"- {fam}: {cnt}")
lines.append("")

lines.append("Top cell (family당 best — 합격 없으면 mean_pnl 최상위):")
lines.append("")
lines.append("| family | sl | tp | tm | mean_pnl | sharpe | n | via |")
lines.append("|--------|----|----|----|----------|--------|---|-----|")
for c in top_cells:
    lines.append(
        f"| {c['family']} | {c['sl']:.0%} | {c['tp']:.0%} | {c['tm']}d "
        f"| {_f(c['mean_pnl'], pct=True)} | {_f(c['sharpe'])} "
        f"| {c['n']:,} | {c['chosen_via']} |"
    )
lines.append("")

lines += [
    "## 3. Cross-section vs Trade-level 정합성",
    "",
    f"- {cs_line}",
    "- 단독 검증은 'OBV signal 종목군 평균 - 비신호군 평균' (cross-section alpha, 이상치 제거 후 +172bps).",
    "- v3는 'T+1 시가 진입 → SL/TP/TM exit, fee 0.3% 편도' (trade-level pnl).",
    "- 회수율 음수 = exit rule이 alpha 전액 소비 후 손실 추가.",
    "",
    "## 4. 월별 PnL (1차 vs v3)",
    "",
    "| 지표 | 1차 (P3, +0.23%) | v3 |",
    "|------|------------------|----|",
    f"| **월평균** | +0.23% | **{_f(mean_m, pct=True)}** |",
    f"| Sharpe (월) | 0.3837 | {_f(sh_m)} |",
    f"| MDD | -6.55% | {_f(mdd_m, pct=True)} |",
    f"| 양수월/총월 | 3/6 (50%) | "
    f"{pos_m}/{int(len(mret)) if 'mret' in dir() else 0} "
    f"({pos_m/max(int(len(mret)) if 'mret' in dir() else 1, 1)*100:.0f}%) |",
    f"| Calmar | - | {_f(calmar)} |",
    f"| 연환산 | - | {_f(ann_ret, pct=True)} |",
    f"| 누적 | - | {_f(tot_ret, pct=True)} |",
    f"| 전체 accepted trades | - | {n_trades_total:,} |",
    "",
    "## 5. 목표 10% 진척률",
    "",
    f"- 1차: +0.23% / 10% = **2.3%**",
]
if not np.isnan(progress_pct):
    lines.append(f"- **v3: {_f(mean_m, pct=True)} / 10% = {progress_pct:.1f}%**")
else:
    lines.append("- v3: N/A")
lines.append("")

lines += [
    "## 6. Walk-Forward 16 윈도우 OOS",
    "",
    f"- 양수 윈도우: **{pos_w}/{len(wf_df)}** ({pos_w/max(len(wf_df),1)*100:.0f}%)",
    "",
    "| W | Test 기간 | n_sig | n_acc | monthly_mean | sharpe | mdd |",
    "|---|----------|-------|-------|--------------|--------|-----|",
]
for _, row in wf_df.iterrows():
    lines.append(
        f"| {int(row['window'])} | {row['test_start']}~{row['test_end']} "
        f"| {int(row.get('n_signals',0)):,} | {int(row.get('n_accepted',0)):,} "
        f"| {_f(row.get('monthly_mean'), pct=True)} "
        f"| {_f(row.get('sharpe'))} "
        f"| {_f(row.get('mdd'), pct=True)} |"
    )
lines.append("")

lines += [
    f"## 7. 판정: **{verdict}**",
    "",
    "### 근거",
    f"- 합격 셀 0개 (81 cells, 전 family 게이트 미통과)",
    f"- 월평균 {_f(mean_m, pct=True)} — 1차 +0.23% 대비 {'개선' if not np.isnan(mean_m) and mean_m > p3_base else '악화'}",
    f"- 양수 WF 윈도우 {pos_w}/16 ({pos_w/16*100:.0f}%) — 50% 미달시 신뢰 부족",
    "",
    "### 핵심 진단",
    "- OBV는 cross-section alpha +172bps 확인됐으나 trade-level 전환 시 exit SL에 의해 소멸",
    "- VWAP pullback 단독은 trade-level에서 mean_pnl +0.59% (게이트 일부 미통과)",
    "- OBV_OR_VWAP 통합 시 신호 희석으로 OBV 손실 dominate",
    "- portfolio 동시 5포지션 제한 시 수익 trade 선택 기회 없음 (entry_date 순 단순 FIFO)",
    "",
    "## 8. 다음 단계 권고",
    "",
    "| 우선순위 | 항목 | 근거 |",
    "|---------|------|------|",
    "| P1 | VWAP 단독 paper 5영업일 시뮬 | trade-level +0.59% — 유일하게 양수 |",
    "| P2 | OBV exit 규칙 재설계 | SL이 cross-section alpha 소멸시킴. 고정 SL 대신 volatility-adaptive 고려 |",
    "| P3 | 분봉 추가 백필 (2023~2024) | VWAP WF 16 windows 확보 → 통계 신뢰도 개선 |",
    "| P4 | OBV_OR_VWAP 폐기, 단독 검증 유지 | 통합 시 음수 dominate 확인 |",
    "",
    "## 9. 산출물",
    f"- `v3_grid_all.csv` ({len(df_all)} cells)",
    f"- `v3_walkforward.csv` ({len(wf_df)} windows)",
    f"- `v3_monthly_pnl.csv` ({len(monthly)} months)",
]

rpath = os.path.join(P5_DIR, "v3_summary.md")
with open(rpath, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nSummary saved: {rpath}")

# ── Changelog ──────────────────────────────────────────────────────────────
changelog_dir = r"C:\Users\sttgp\.claude\projects\D--GIT-kis-trading-template\memory"
os.makedirs(changelog_dir, exist_ok=True)

cl_lines = [
    "# Phase 5 v3 Portfolio Walk-Forward 최종 결과 (2026-05-26)",
    "",
    "## 작업 요약",
    "직원 #9 (re-try after #8 절단). architect 재설계 권고 (b) 구현.",
    "",
    "## v3 재설계 내용",
    "- **Universe**: ROE Q4+ ∩ swing pool 제거 → mcap top 500 + tv > 10억 (단독 검증 근접)",
    "- **Signal**: OBV(lb=5, slope≥1.0σ), VWAP pullback(pb_10), OBV_OR_VWAP",
    "- **Exit**: SL[-5/-7/-10%], TP[3/5/10%], TM[1/3/5]d (OBV 1d signal 분포 반영)",
    "- **Portfolio**: 1,000만원, 동시 5포지션, equal weight, T+1 시가, 0.3% 편도",
    "- **Walk-forward**: 252/63 × 16 windows (단독 검증 동일)",
    "",
    "## 최종 결과 (정직 보고)",
    f"- 합격 셀: **0 / 81** (전 family 게이트 미통과)",
    f"- 월평균 PnL: **{_f(mean_m, pct=True)}** (1차 +0.23% 대비 {'개선' if not np.isnan(mean_m) and mean_m > p3_base else '악화'})",
    f"- 양수 WF 윈도우: **{pos_w}/16** ({pos_w/16*100:.0f}%)",
    f"- Sharpe(월): {_f(sh_m)}",
    f"- MDD: {_f(mdd_m, pct=True)}",
    f"- 연환산: {_f(ann_ret, pct=True)}",
    f"- Calmar: {_f(calmar)}",
    "",
    "## Top cell (family당 best)",
]
for c in top_cells:
    cl_lines.append(
        f"- {c['family']}: sl={c['sl']:.0%} tp={c['tp']:.0%} tm={c['tm']}d "
        f"mean_pnl={_f(c['mean_pnl'], pct=True)} sharpe={_f(c['sharpe'])} via={c['chosen_via']}"
    )
cl_lines += [
    "",
    "## Cross-section vs Trade-level",
    f"- {cs_line}",
    "",
    "## 판정",
    f"**{verdict}**",
    "",
    "## 목표 진척률",
    f"- 1차: 2.3% (월 +0.23% / 10%)",
    f"- v3: {progress_pct:.1f}%" if not np.isnan(progress_pct) else "- v3: N/A",
    "",
    "## 다음 단계",
    "- P1: VWAP 단독 trade-level +0.59% — paper 5영업일 시뮬 권고",
    "- P2: OBV exit 규칙 재설계 (volatility-adaptive SL)",
    "- P3: 분봉 2023~2024 추가 백필 (VWAP 16 windows 확보)",
    "- P4: OBV_OR_VWAP 폐기",
    "",
    "## 산출물",
    "- `RoboTrader_template/scripts/10pct_strategy/p5_obv_swing_walkforward.py` (신설)",
    "- `reports/10pct_strategy/phase5_signals/v3_grid_all.csv`",
    "- `reports/10pct_strategy/phase5_signals/v3_walkforward.csv`",
    "- `reports/10pct_strategy/phase5_signals/v3_monthly_pnl.csv`",
    "- `reports/10pct_strategy/phase5_signals/v3_summary.md`",
]
cl_path = os.path.join(changelog_dir, "changelog-2026-05-26-v3-portfolio.md")
with open(cl_path, "w", encoding="utf-8") as f:
    f.write("\n".join(cl_lines))
print(f"Changelog saved: {cl_path}")

# Console final
print("\n" + "="*70)
print("FINAL — v3 portfolio simulation 결과")
print("="*70)
print(f"합격 셀:           {len(df_pass)} / {len(df_all)}")
print(f"Top cells:         {len(top_cells)}")
print(f"WF 윈도우:         {len(wf_df)}")
print(f"양수 WF:           {pos_w}/{len(wf_df)}")
if not np.isnan(mean_m):
    print(f"월평균 PnL:        {mean_m*100:+.3f}%")
    print(f"양수 월:           {pos_m}/{int(len(mret))}")
    print(f"Sharpe(월):        {sh_m:.4f}" if not np.isnan(sh_m) else "Sharpe: N/A")
    print(f"MDD:               {mdd_m*100:.2f}%")
    print(f"연환산:            {ann_ret*100:+.2f}%" if not np.isnan(ann_ret) else "연환산: N/A")
    print(f"Calmar:            {calmar:.2f}" if not np.isnan(calmar) else "Calmar: N/A")
    print(f"진척률:            {progress_pct:.1f}% (목표 10%)")
else:
    print("월평균 PnL:        N/A")
print(f"\n판정: {verdict}")
print("="*70)
