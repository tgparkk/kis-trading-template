"""
p5_obv_walkforward.py -- OBV Walk-Forward OOS + Regime Decomposition
Phase 5 catalog re-validation methodology (same as TOM pipeline)
"""
import sys, os
sys.path.insert(0, r"D:\GIT\kis-trading-template\RoboTrader_template")
import psycopg2
import pandas as pd
import numpy as np
import warnings
from scipy import stats
warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGURES_DIR = r"D:\GIT\kis-trading-template\.omc\scientist\figures"
REPORTS_DIR = r"D:\GIT\kis-trading-template\RoboTrader_template\reports\10pct_strategy\phase5_signals"
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

DB = dict(host="127.0.0.1", port=5433, database="robotrader_quant", user="robotrader", password="1234")
FEE_A = 0.003
FEE_B = 0.0015
LOOKBACKS = [5, 10, 20]
THR_TYPES = ["0", "0.5std", "1.0std"]

# ---- 1. DATA LOAD ----
print("="*70)
print("[DATA] Loading daily_prices ...")
SQL = """
SELECT stock_code, date, close, volume, returns_1d, market_cap
FROM daily_prices
WHERE returns_1d IS NOT NULL AND volume IS NOT NULL AND volume > 0
  AND close IS NOT NULL AND stock_code NOT IN ('KS11','KQ11')
  AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
ORDER BY stock_code, date
"""
conn = psycopg2.connect(**DB)
df = pd.read_sql(SQL, conn, parse_dates=["date"])
conn.close()
lo_q = df["returns_1d"].quantile(0.01)
hi_q = df["returns_1d"].quantile(0.99)
df["ret_w"] = df["returns_1d"].clip(lo_q, hi_q)
df = df.sort_values(["stock_code","date"]).reset_index(drop=True)
N_ROWS   = len(df)
N_STOCKS = df["stock_code"].nunique()
DATE_MIN = df["date"].min()
DATE_MAX = df["date"].max()
print(f"  Rows: {N_ROWS:,}  Stocks: {N_STOCKS:,}")
print(f"  Date: {DATE_MIN.date()} ~ {DATE_MAX.date()}")
print(f"  Winsorize: [{lo_q:.4%}, {hi_q:.4%}]")

# ---- 2. OBV ----
print("\n[OBV] Computing On-Balance Volume ...")
def compute_obv(close_arr, vol_arr):
    n = len(close_arr)
    obv = np.zeros(n, dtype=float)
    for i in range(1, n):
        c, p, v = close_arr[i], close_arr[i-1], vol_arr[i]
        if np.isnan(c) or np.isnan(p) or np.isnan(v):
            obv[i] = obv[i-1]
        elif c > p: obv[i] = obv[i-1] + v
        elif c < p: obv[i] = obv[i-1] - v
        else:       obv[i] = obv[i-1]
    return obv

parts = []
for code, grp in df.groupby("stock_code", sort=False):
    arr = compute_obv(grp["close"].values.astype(float), grp["volume"].values.astype(float))
    parts.append(pd.Series(arr, index=grp.index))
df["obv"] = pd.concat(parts).sort_index()
print(f"  OBV done.")

# ---- 3. SIGNAL FEATURES ----
print("\n[SIGNAL] Computing OBV slopes ...")
def rolling_slope(obv_vals, lb):
    n = len(obv_vals)
    slope = np.full(n, np.nan)
    x = np.arange(lb, dtype=float) - (lb-1)/2.0
    ss_x = (x**2).sum()
    for i in range(lb-1, n):
        y = obv_vals[i-lb+1:i+1].astype(float)
        slope[i] = (x*(y-y.mean())).sum()/ss_x
    return slope

for lb in LOOKBACKS:
    sp, dp = [], []
    for code, grp in df.groupby("stock_code", sort=False):
        ov = grp["obv"].values.astype(float)
        sp.append(pd.Series(rolling_slope(ov, lb), index=grp.index))
        diff = np.full(len(ov), np.nan)
        for i in range(lb, len(ov)): diff[i] = ov[i]-ov[i-lb]
        dp.append(pd.Series(diff, index=grp.index))
    df[f"obv_slope_{lb}"] = pd.concat(sp).sort_index()
    df[f"obv_diff_{lb}"]  = pd.concat(dp).sort_index()
    print(f"  lb={lb} done")

# ---- 4. REGIME ----
print("\n[REGIME] Loading/deriving market regime ...")
conn = psycopg2.connect(**DB)
try:
    reg_df = pd.read_sql("SELECT date, regime FROM market_regime ORDER BY date", conn, parse_dates=["date"])
    print(f"  Loaded market_regime: {len(reg_df)} rows")
except Exception as e:
    print(f"  market_regime not available ({e}), deriving from proxy ...")
    reg_df = None
conn.close()

if reg_df is None or len(reg_df)==0:
    conn = psycopg2.connect(**DB)
    ks = pd.read_sql(
        "SELECT date, returns_1d FROM daily_prices WHERE stock_code='KS11' AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' ORDER BY date",
        conn, parse_dates=["date"])
    conn.close()
    if len(ks)==0:
        ks = df.groupby("date")["returns_1d"].mean().reset_index()
        ks.columns = ["date","returns_1d"]
    ks = ks.sort_values("date").reset_index(drop=True)
    ks["roll_ret"] = ks["returns_1d"].rolling(60, min_periods=20).mean()
    ks["roll_vol"] = ks["returns_1d"].rolling(20, min_periods=10).std()
    vol_med = ks["roll_vol"].median()
    def assign_regime(row):
        if pd.isna(row["roll_ret"]) or pd.isna(row["roll_vol"]): return "unknown"
        bull = row["roll_ret"] >= 0
        hv   = row["roll_vol"] >= vol_med
        if bull and hv:      return "bull_high_vol"
        if bull and not hv:  return "bull_low_vol"
        if not bull and hv:  return "bear_high_vol"
        return "bear_low_vol"
    ks["regime"] = ks.apply(assign_regime, axis=1)
    reg_df = ks[["date","regime"]].copy()
    print(f"  Derived: {reg_df['regime'].value_counts().to_dict()}")

df = df.merge(reg_df[["date","regime"]], on="date", how="left")
df["regime"] = df["regime"].fillna("unknown")
print(f"  Regime counts: {df['regime'].value_counts().to_dict()}")

# ---- 5. MCAP QUINTILES ----
print("\n[MCAP] Assigning quintiles ...")
df["mcap_q"] = df.groupby("date")["market_cap"].transform(
    lambda x: pd.qcut(x.rank(method="first"),5,labels=["Q1","Q2","Q3","Q4","Q5"])
              if x.notna().sum()>=5 else np.nan)
print(f"  Done: {df['mcap_q'].notna().sum():,} rows with quintile")

# ---- 6. WALK-FORWARD WINDOWS ----
print("\n[WF] Building walk-forward windows ...")
all_dates = sorted(df["date"].unique())
IS_SIZE, OOS_SIZE, STEP = 252, 63, 63
windows = []
i = 0
while True:
    oe = i + IS_SIZE + OOS_SIZE - 1
    if oe >= len(all_dates): break
    windows.append({"w": len(windows)+1,
        "is_start": all_dates[i], "is_end": all_dates[i+IS_SIZE-1],
        "oos_start": all_dates[i+IS_SIZE], "oos_end": all_dates[oe]})
    i += STEP
print(f"  Windows: {len(windows)}")
for w in windows: print(f"    W{w['w']:02d}: IS {w['is_start'].date()}~{w['is_end'].date()} | OOS {w['oos_start'].date()}~{w['oos_end'].date()}")

# ---- 7. WALK-FORWARD EVALUATION ----
print("\n[WF] Running evaluation ...")
PARAM_GRID = [{"lb":lb,"thr_type":tt} for lb in LOOKBACKS for tt in THR_TYPES]

def get_threshold(data, lb, thr_type):
    s = data[f"obv_slope_{lb}"].dropna()
    if thr_type=="0": return 0.0
    elif thr_type=="0.5std": return 0.5*s.std()
    elif thr_type=="1.0std": return 1.0*s.std()
    return 0.0

wf_results = []
for w_info in windows:
    is_m  = (df["date"]>=w_info["is_start"])  & (df["date"]<=w_info["is_end"])
    oos_m = (df["date"]>=w_info["oos_start"]) & (df["date"]<=w_info["oos_end"])
    df_is, df_oos = df[is_m], df[oos_m]
    for param in PARAM_GRID:
        lb, thr_type = param["lb"], param["thr_type"]
        sc = f"obv_slope_{lb}"
        thr = get_threshold(df_is, lb, thr_type)
        # IS stats
        iv = df_is[[sc,"ret_w"]].dropna()
        is_sig = iv[sc] > thr
        isr = iv.loc[is_sig,"ret_w"].mean() if is_sig.sum()>0 else np.nan
        inr = iv.loc[~is_sig,"ret_w"].mean() if (~is_sig).sum()>0 else np.nan
        is_diff = (isr-inr)*100 if not (np.isnan(isr) or np.isnan(inr)) else np.nan
        if is_sig.sum()>1 and (~is_sig).sum()>1:
            _, p_val = stats.ttest_ind(iv.loc[is_sig,"ret_w"], iv.loc[~is_sig,"ret_w"])
        else: p_val = np.nan
        # OOS stats
        ov = df_oos[[sc,"ret_w"]].dropna()
        oos_sig = ov[sc] > thr
        osr = ov.loc[oos_sig,"ret_w"].mean() if oos_sig.sum()>0 else np.nan
        onr = ov.loc[~oos_sig,"ret_w"].mean() if (~oos_sig).sum()>0 else np.nan
        oos_gross = (osr-onr)*100 if not (np.isnan(osr) or np.isnan(onr)) else np.nan
        oos_net_A = oos_gross - FEE_A*100 if not np.isnan(oos_gross) else np.nan
        oos_net_B = oos_gross - FEE_B*100 if not np.isnan(oos_gross) else np.nan
        wf_results.append({"window":w_info["w"],"is_start":w_info["is_start"],
            "is_end":w_info["is_end"],"oos_start":w_info["oos_start"],"oos_end":w_info["oos_end"],
            "lb":lb,"thr_type":thr_type,"threshold":thr,
            "IS_diff_pp":is_diff,"IS_p":p_val,
            "OOS_gross_pp":oos_gross,"OOS_net_A_pp":oos_net_A,"OOS_net_B_pp":oos_net_B,
            "n_sig_oos":int(oos_sig.sum()),"n_nosig_oos":int((~oos_sig).sum())})

wf_df = pd.DataFrame(wf_results)
print(f"  WF done: {len(wf_df)} rows")
print(wf_df.groupby(["lb","thr_type"])[["OOS_gross_pp","OOS_net_A_pp"]].mean().round(4))

# ---- 8. REGIME DECOMPOSITION (full-sample IS) ----
print("\n[REGIME] Full-sample decomposition ...")
regime_results = []
for param in PARAM_GRID:
    lb, thr_type = param["lb"], param["thr_type"]
    sc = f"obv_slope_{lb}"
    thr = get_threshold(df, lb, thr_type)
    for regime in df["regime"].unique():
        sub = df[df["regime"]==regime][[sc,"ret_w"]].dropna()
        if len(sub)<30: continue
        sig = sub[sc]>thr
        sr = sub.loc[sig,"ret_w"].mean() if sig.sum()>0 else np.nan
        nr = sub.loc[~sig,"ret_w"].mean() if (~sig).sum()>0 else np.nan
        diff = (sr-nr)*100 if not (np.isnan(sr) or np.isnan(nr)) else np.nan
        if sig.sum()>1 and (~sig).sum()>1:
            t, p = stats.ttest_ind(sub.loc[sig,"ret_w"], sub.loc[~sig,"ret_w"])
        else: t, p = np.nan, np.nan
        regime_results.append({"lb":lb,"thr_type":thr_type,"regime":regime,
            "sig_ret_pp":sr*100 if not np.isnan(sr) else np.nan,
            "nosig_ret_pp":nr*100 if not np.isnan(nr) else np.nan,
            "diff_pp":diff,"t_stat":t,"p_val":p,
            "n_sig":int(sig.sum()),"n_nosig":int((~sig).sum())})
reg_df_res = pd.DataFrame(regime_results)
print(reg_df_res.groupby("regime")["diff_pp"].mean().round(4))

# ---- 9. PARAMETER SUMMARY + BEST ----
summary_by_param = wf_df.groupby(["lb","thr_type"]).agg(
    mean_OOS_net_A=("OOS_net_A_pp","mean"),
    pct_positive=("OOS_net_A_pp", lambda x: (x>0).mean()),
    n_windows=("window","count")).reset_index()
print("\nParam summary:")
print(summary_by_param.sort_values("mean_OOS_net_A",ascending=False).round(4))
best_row  = summary_by_param.sort_values("mean_OOS_net_A",ascending=False).iloc[0]
BEST_LB   = int(best_row["lb"])
BEST_THR  = best_row["thr_type"]
print(f"Best: lb={BEST_LB}, thr={BEST_THR}")

# ---- 10. MCAP x REGIME ----
print("\n[MCAP x REGIME] Cross analysis ...")
sc_best = f"obv_slope_{BEST_LB}"
thr_best = get_threshold(df, BEST_LB, BEST_THR)
mcap_regime_results = []
for mq in ["Q1","Q2","Q3","Q4","Q5"]:
    for regime in sorted(df["regime"].unique()):
        sub = df[(df["mcap_q"]==mq)&(df["regime"]==regime)][[sc_best,"ret_w"]].dropna()
        if len(sub)<20: continue
        sig = sub[sc_best]>thr_best
        sr = sub.loc[sig,"ret_w"].mean() if sig.sum()>0 else np.nan
        nr = sub.loc[~sig,"ret_w"].mean() if (~sig).sum()>0 else np.nan
        diff=(sr-nr)*100 if not (np.isnan(sr) or np.isnan(nr)) else np.nan
        if sig.sum()>1 and (~sig).sum()>1:
            t,p = stats.ttest_ind(sub.loc[sig,"ret_w"],sub.loc[~sig,"ret_w"])
        else: t,p=np.nan,np.nan
        mcap_regime_results.append({"mcap_q":mq,"regime":regime,"diff_pp":diff,
            "t_stat":t,"p_val":p,"n_sig":int(sig.sum()),"n_nosig":int((~sig).sum())})
mr_df = pd.DataFrame(mcap_regime_results)
print(mr_df.pivot_table(index="mcap_q",columns="regime",values="diff_pp").round(4))

# ---- 11. FIGURES ----
print("\n[VIZ] Generating figures ...")
best_wf = wf_df[(wf_df["lb"]==BEST_LB)&(wf_df["thr_type"]==BEST_THR)].sort_values("window")

fig1, ax1 = plt.subplots(figsize=(14,5))
colors = ["#2ecc71" if v>0 else "#e74c3c" for v in best_wf["OOS_net_A_pp"]]
ax1.bar(best_wf["window"], best_wf["OOS_net_A_pp"], color=colors, edgecolor="white")
ax1.axhline(0, color="black", lw=1.2)
ax1.axhline(-FEE_A*100, color="orange", lw=1, ls="--", label="Break-even (-0.3pp)")
ax1.set_xlabel("Walk-Forward Window"); ax1.set_ylabel("OOS Net Return Diff (pp)")
ax1.set_title(f"OBV Walk-Forward OOS Net Returns lb={BEST_LB} thr={BEST_THR}")
ax1.legend(); ax1.set_xticks(best_wf["window"])
fig1.tight_layout()
fig1.savefig(os.path.join(FIGURES_DIR,"obv_wf_oos.png"), dpi=150, bbox_inches="tight")
plt.close(fig1)
print("  Saved: obv_wf_oos.png")

reg_best = reg_df_res[(reg_df_res["lb"]==BEST_LB)&(reg_df_res["thr_type"]==BEST_THR)].sort_values("diff_pp",ascending=False)
fig2, ax2 = plt.subplots(figsize=(10,5))
colors2 = ["#2ecc71" if v>0 else "#e74c3c" for v in reg_best["diff_pp"]]
bars = ax2.bar(reg_best["regime"], reg_best["diff_pp"], color=colors2)
ax2.axhline(0, color="black", lw=1)
ax2.axhline(FEE_A*100, color="orange", ls="--", lw=1, label=f"Break-even (+{FEE_A*100}pp)")
for bar, row in zip(bars, reg_best.itertuples()):
    pstr = f"p={row.p_val:.3f}" if not np.isnan(row.p_val) else ""
    ax2.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.003, pstr, ha="center", va="bottom", fontsize=8)
ax2.set_title(f"OBV Effect by Regime (IS, lb={BEST_LB} thr={BEST_THR})")
ax2.set_xlabel("Regime"); ax2.set_ylabel("Signal-NoSignal Diff (pp)")
ax2.legend(); plt.xticks(rotation=15)
fig2.tight_layout()
fig2.savefig(os.path.join(FIGURES_DIR,"obv_regime.png"), dpi=150, bbox_inches="tight")
plt.close(fig2)
print("  Saved: obv_regime.png")

pivot_plot = mr_df.pivot_table(index="mcap_q",columns="regime",values="diff_pp")
fig3, ax3 = plt.subplots(figsize=(10,5))
im = ax3.imshow(pivot_plot.values, aspect="auto", cmap="RdYlGn", vmin=-0.3, vmax=0.3)
ax3.set_xticks(range(len(pivot_plot.columns))); ax3.set_xticklabels(pivot_plot.columns, rotation=20, ha="right", fontsize=9)
ax3.set_yticks(range(len(pivot_plot.index))); ax3.set_yticklabels(pivot_plot.index)
ax3.set_title(f"OBV Diff (pp) Mcap x Regime (lb={BEST_LB} thr={BEST_THR})")
for i in range(len(pivot_plot.index)):
    for j in range(len(pivot_plot.columns)):
        v = pivot_plot.values[i,j]
        if not np.isnan(v): ax3.text(j,i,f"{v:.3f}", ha="center", va="center", fontsize=8)
plt.colorbar(im, ax=ax3, label="Diff (pp)")
fig3.tight_layout()
fig3.savefig(os.path.join(FIGURES_DIR,"obv_mcap_regime.png"), dpi=150, bbox_inches="tight")
plt.close(fig3)
print("  Saved: obv_mcap_regime.png")

# ---- 12. 5-LINE CRITERIA ----
print("\n[5-LINE] Evaluating ...")
is_p_sig = wf_df[wf_df["IS_p"]<0.05]
oos_fail = is_p_sig[is_p_sig["OOS_net_A_pp"]<=0]
c1_pass = len(oos_fail)>0
c1_detail = f"IS p<0.05={len(is_p_sig)}, OOS net<=0 among those={len(oos_fail)} ({len(oos_fail)/max(1,len(is_p_sig)):.0%})"

best_oos_net = float(best_row["mean_OOS_net_A"])
best_pct_pos = float(best_row["pct_positive"])
c2_pass = (best_oos_net>0) and (best_pct_pos>0.60)
c2_detail = f"Best OOS net@0.3%={best_oos_net:.4f}pp, pct_pos={best_pct_pos:.0%}"

reg_best_data = reg_df_res[(reg_df_res["lb"]==BEST_LB)&(reg_df_res["thr_type"]==BEST_THR)]
regime_pass = reg_best_data[(reg_best_data["diff_pp"]>FEE_A*100)&(reg_best_data["p_val"]<0.05)]
c3_pass = len(regime_pass)>0
c3_detail = f"Regimes surviving fee+p<0.05: {list(regime_pass['regime'])}"

param_winners = summary_by_param[summary_by_param["mean_OOS_net_A"]>0]
c4_pass = len(param_winners)>=3
c4_detail = f"Params with OOS net>0: {len(param_winners)}/9"

mr_ok = mr_df[(mr_df["diff_pp"]>FEE_A*100)&(mr_df["p_val"]<0.05)]
c5_pass = len(mr_ok)>0
c5_detail = f"Mcap x Regime surviving cells: {len(mr_ok)}"

criteria = [
    (1,"IS p-value-only guard",c1_pass,c1_detail),
    (2,"OOS Net@0.3%>0 AND pct_pos>60%",c2_pass,c2_detail),
    (3,"Regime conditional survival",c3_pass,c3_detail),
    (4,"Param diversity (>=3 params OOS positive)",c4_pass,c4_detail),
    (5,"Mcap x Regime (>=1 cell surviving)",c5_pass,c5_detail),
]
n_pass = sum(1 for _,_,p,_ in criteria if p)

print("\n" + "="*60)
print(f"5-LINE RESULT: {n_pass}/5 PASS")
print(sep60)
for num,name,passed,detail in criteria:
    st2 = "PASS" if passed else "FAIL"
    print(f"  [{st2}] C{num}: {name}")
    print(f"         {detail}")

if n_pass>=4: recommendation="무조건 채택"
elif n_pass>=2: recommendation="조건부 채택"
else: recommendation="폐기"
print(f"\n최종 권고: {recommendation}")

# ---- 13. REPORT ----
print("\n[REPORT] Writing report ...")
oos_mean_gross = float(best_wf["OOS_gross_pp"].mean())
oos_mean_net   = float(best_wf["OOS_net_A_pp"].mean())
oos_pct_pos2   = float((best_wf["OOS_net_A_pp"]>0).mean())

lines_rep = []
lines_rep.append("# OBV (On-Balance Volume) Walk-Forward 검증 보고서")
lines_rep.append("")
lines_rep.append(f"> 작성일: 2026-05-25  ")
lines_rep.append(f"> 분석자: Scientist (Claude Sonnet 4.6)  ")
lines_rep.append(f"> 데이터: robotrader_quant.daily_prices ({DATE_MIN.date()} ~ {DATE_MAX.date()})  ")
lines_rep.append("> 방법론: Phase 5 카탈로그 재검증 — TOM 파이프라인 완전 복제  ")
lines_rep.append("> 시그널: F-23 OBV (lib/signals/flow.py)")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")
lines_rep.append("## 1. 데이터 개요")
lines_rep.append("")
lines_rep.append("| 항목 | 값 |")
lines_rep.append("|------|-----|")
lines_rep.append(f"| 분석 기간 | {DATE_MIN.date()} ~ {DATE_MAX.date()} |")
lines_rep.append(f"| 총 행수 | {N_ROWS:,}건 |")
lines_rep.append(f"| 종목 수 | {N_STOCKS:,}종목 |")
lines_rep.append(f"| Winsorize | [{lo_q:.4%}, {hi_q:.4%}] |")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")
lines_rep.append("## 2. Walk-Forward 설계")
lines_rep.append("")
lines_rep.append("| 항목 | 값 |")
lines_rep.append("|------|-----|")
lines_rep.append("| IS 기간 | 252영업일 |")
lines_rep.append("| OOS 기간 | 63영업일 |")
lines_rep.append("| Step | 63영업일 |")
lines_rep.append(f"| 총 윈도우 | {len(windows)}개 |")
lines_rep.append("| 거래비용 A | 0.3% 왕복 |")
lines_rep.append("")
lines_rep.append("| W# | IS 시작 | IS 종료 | OOS 시작 | OOS 종료 |")
lines_rep.append("|----|---------|---------|----------|----------|")
for w in windows:
    lines_rep.append(f"| W{w['w']:02d} | {w['is_start'].date()} | {w['is_end'].date()} | {w['oos_start'].date()} | {w['oos_end'].date()} |")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")
lines_rep.append(f"## 3. Walk-Forward OOS 결과 (최적 파라미터: lb={BEST_LB}, threshold={BEST_THR})")
lines_rep.append("")
lines_rep.append("| W# | OOS 시작 | OOS 종료 | IS diff(pp) | IS p-val | OOS Gross(pp) | OOS Net@0.3%(pp) | n_sig |")
lines_rep.append("|----|---------|---------|------------|---------|--------------|-----------------|-------|")
for _, row in best_wf.iterrows():
    isd = f"{row['IS_diff_pp']:.4f}" if not np.isnan(row['IS_diff_pp']) else "—"
    isp = f"{row['IS_p']:.3f}" if not np.isnan(row['IS_p']) else "—"
    og  = f"{row['OOS_gross_pp']:.4f}" if not np.isnan(row['OOS_gross_pp']) else "—"
    on  = f"{row['OOS_net_A_pp']:.4f}" if not np.isnan(row['OOS_net_A_pp']) else "—"
    lines_rep.append(f"| W{int(row['window']):02d} | {row['oos_start'].date()} | {row['oos_end'].date()} | {isd} | {isp} | {og} | {on} | {row['n_sig_oos']:,} |")
lines_rep.append("")
lines_rep.append(f"**OOS 평균 Gross**: {oos_mean_gross:.4f}pp  ")
lines_rep.append(f"**OOS 평균 Net@0.3%**: {oos_mean_net:.4f}pp  ")
lines_rep.append(f"**OOS 양의 비율**: {oos_pct_pos2:.0%} ({int((best_wf['OOS_net_A_pp']>0).sum())}/{len(best_wf)} 윈도우)")
lines_rep.append("")
lines_rep.append("### 전 파라미터 OOS 요약")
lines_rep.append("")
lines_rep.append("| lb | threshold | OOS Net@0.3% 평균 | 양의 비율 | 윈도우 수 |")
lines_rep.append("|----|-----------|--------------------|-----------|-----------|")
for _, r in summary_by_param.sort_values("mean_OOS_net_A",ascending=False).iterrows():
    lines_rep.append(f"| {int(r['lb'])} | {r['thr_type']} | {r['mean_OOS_net_A']:.4f}pp | {r['pct_positive']:.0%} | {int(r['n_windows'])} |")
lines_rep.append("")
lines_rep.append(f"> **손익분기점**: OOS Gross > 0.30pp 필요 (0.3% 왕복 수수료)")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")
lines_rep.append(f"## 4. 레짐 조건부 효과 분해 (Full-sample IS, lb={BEST_LB}, thr={BEST_THR})")
lines_rep.append("")
lines_rep.append("| 레짐 | Signal 평균(pp) | No-Signal 평균(pp) | Diff(pp) | t-stat | p-value | n_sig | 수수료 후 생존 |")
lines_rep.append("|------|----------------|-------------------|----------|--------|---------|-------|--------------|")
reg_table = reg_df_res[(reg_df_res["lb"]==BEST_LB)&(reg_df_res["thr_type"]==BEST_THR)].sort_values("diff_pp",ascending=False)
for _, row in reg_table.iterrows():
    sr = f"{row['sig_ret_pp']:.4f}" if not np.isnan(row['sig_ret_pp']) else "—"
    nr = f"{row['nosig_ret_pp']:.4f}" if not np.isnan(row['nosig_ret_pp']) else "—"
    ds = f"{row['diff_pp']:.4f}" if not np.isnan(row['diff_pp']) else "—"
    ts = f"{row['t_stat']:.3f}" if not np.isnan(row['t_stat']) else "—"
    ps = f"{row['p_val']:.4f}" if not np.isnan(row['p_val']) else "—"
    sv = "O" if (not np.isnan(row['diff_pp']) and row['diff_pp']>FEE_A*100 and not np.isnan(row['p_val']) and row['p_val']<0.05) else "X"
    lines_rep.append(f"| {row['regime']} | {sr} | {nr} | {ds} | {ts} | {ps} | {row['n_sig']:,} | {sv} |")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")
lines_rep.append(f"## 5. 시총 분위 x 레짐 결합 평가 (lb={BEST_LB}, thr={BEST_THR})")
lines_rep.append("")
lines_rep.append("| 시총 분위 | 레짐 | Diff(pp) | p-value | n_sig | 생존 |")
lines_rep.append("|-----------|------|----------|---------|-------|------|")
for _, row in mr_df.sort_values(["mcap_q","diff_pp"],ascending=[True,False]).iterrows():
    ds = f"{row['diff_pp']:.4f}" if not np.isnan(row['diff_pp']) else "—"
    ps = f"{row['p_val']:.4f}" if not np.isnan(row['p_val']) else "—"
    sv = "O" if (not np.isnan(row['diff_pp']) and row['diff_pp']>FEE_A*100 and not np.isnan(row['p_val']) and row['p_val']<0.05) else "X"
    lines_rep.append(f"| {row['mcap_q']} | {row['regime']} | {ds} | {ps} | {row['n_sig']:,} | {sv} |")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")
lines_rep.append("## 6. 5선 방법론 평가")
lines_rep.append("")
lines_rep.append("| 선 | 기준 | 결과 | 세부 |")
lines_rep.append("|-----|------|------|------|")
for num,name,passed,detail in criteria:
    st = "**PASS**" if passed else "**FAIL**"
    lines_rep.append(f"| 선{num} | {name} | {st} | {detail} |")
lines_rep.append("")
lines_rep.append(f"**최종 점수**: {n_pass}/5 통과")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")
lines_rep.append(f"## 7. 최종 판정: {recommendation}")
lines_rep.append("")
lines_rep.append(f"- OOS 평균 Net@0.3%: **{oos_mean_net:.4f}pp**")
lines_rep.append(f"- OOS 양의 윈도우 비율: **{oos_pct_pos2:.0%}**")
lines_rep.append(f"- 5선 통과: **{n_pass}/5**")
lines_rep.append("")
lines_rep.append("### 살아남은 레짐/시총 조건")
if len(regime_pass)>0:
    for _, row in regime_pass.iterrows():
        lines_rep.append(f"- 레짐 **{row['regime']}**: diff={row['diff_pp']:.4f}pp, p={row['p_val']:.4f}")
else:
    lines_rep.append("- 수수료 후 유의하게 생존하는 레짐 없음")
if len(mr_ok)>0:
    lines_rep.append("")
    lines_rep.append("**시총 x 레짐 생존 셀 (상위 5):**")
    for _, row in mr_ok.sort_values("diff_pp",ascending=False).head(5).iterrows():
        lines_rep.append(f"- {row['mcap_q']} x {row['regime']}: diff={row['diff_pp']:.4f}pp, p={row['p_val']:.4f}")
else:
    lines_rep.append("- 시총 x 레짐 생존 셀 없음")
lines_rep.append("")
lines_rep.append("### 한계 (LIMITATION)")
lines_rep.append("- OBV 절대값 종목 간 비교 불가 (시총 규모 편향)")
lines_rep.append("- 시총 분위: full-sample 할당 (PIT 근사 — 미래 정보 일부 포함 가능성)")
lines_rep.append("- 레짐 레이블: KOSPI 프록시 기반 (전용 regime 테이블 미사용 시)")
lines_rep.append("- 거래비용 0.3% 가정 — 슬리피지·스프레드 미포함")
lines_rep.append("- 단일 신호 평가 — 복합 필터 조합 시 결과 상이 가능")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")
lines_rep.append("## 8. 시각화")
lines_rep.append("- `.omc/scientist/figures/obv_wf_oos.png` — 16 윈도우 OOS net return")
lines_rep.append("- `.omc/scientist/figures/obv_regime.png` — 레짐별 효과")
lines_rep.append("- `.omc/scientist/figures/obv_mcap_regime.png` — 시총 x 레짐 히트맵")

report_path = os.path.join(REPORTS_DIR, "obv_walkforward.md")
with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines_rep))
print(f"  Report saved: {report_path}")

print("\n" + "="*70)
print("ANALYSIS COMPLETE")
print(f"  5선 방법론 통과: {n_pass}/5")
print(f"  최종 권고: {recommendation}")
print(f"  OOS Net@0.3%: {oos_mean_net:.4f}pp")
print(f"  OOS 양의 비율: {oos_pct_pos2:.0%}")
print("="*70)