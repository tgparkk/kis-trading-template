import sys, os
sys.path.insert(0, "D:/GIT/kis-trading-template/RoboTrader_template")
os.chdir("D:/GIT/kis-trading-template/RoboTrader_template")

import psycopg2, pandas as pd, numpy as np, warnings
from scipy import stats
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB = dict(host="127.0.0.1", port=5433, database="robotrader_quant",
          user="robotrader", password="1234")
FEE = 0.003

FIGURES_DIR = "D:/GIT/kis-trading-template/RoboTrader_template/.omc/scientist/figures"
os.makedirs(FIGURES_DIR, exist_ok=True)

def qry(sql):
    conn = psycopg2.connect(**DB)
    try:
        df = pd.read_sql(sql, conn)
    finally:
        conn.close()
    return df

print("[1] Loading...", flush=True)
raw = qry("""
    SELECT stock_code, date, high, low, close, volume, market_cap
    FROM daily_prices
    WHERE date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      AND stock_code NOT IN ('KS11','KQ11')
      AND close > 0 AND volume > 0
    ORDER BY stock_code, date
""")
raw["date"] = pd.to_datetime(raw["date"])
raw = raw.sort_values(["stock_code","date"]).reset_index(drop=True)
print(f"  Rows: {len(raw):,}  Stocks: {raw.stock_code.nunique():,}")
print(f"  Range: {raw.date.min().date()} ~ {raw.date.max().date()}")

print("[2] Forward returns...", flush=True)
def fwd_ret(c, n):
    c = c.astype(float)
    ret = np.full(len(c), np.nan)
    for i in range(len(c)-n):
        if c[i] > 0 and c[i+n] > 0:
            ret[i] = c[i+n]/c[i] - 1.0
    return ret

parts = []
for code, grp in raw.groupby("stock_code", sort=False):
    g = grp.copy()
    c = g["close"].values
    g["ret1"]  = fwd_ret(c, 1)
    g["ret5"]  = fwd_ret(c, 5)
    g["ret10"] = fwd_ret(c, 10)
    parts.append(g)
df = pd.concat(parts, ignore_index=True)
print(f"  ret1 valid: {df.ret1.notna().sum():,}")

print("[3] CMF...", flush=True)
from lib.signals.flow import cmf as compute_cmf
for w in [10, 20, 40]:
    df[f"cmf{w}"] = compute_cmf(df, window=w, group_col="stock_code",
                                  close_col="close", high_col="high",
                                  low_col="low", volume_col="volume")
    print(f"  cmf{w}: valid={df[f'cmf{w}'].notna().sum():,}, mean={df[f'cmf{w}'].mean():.4f}")

print("[4] Preprocessing...", flush=True)
for col in ["ret1","ret5","ret10"]:
    lo, hi = df[col].quantile(0.01), df[col].quantile(0.99)
    df[f"{col}_w"] = df[col].clip(lo, hi)

def safe_mc_q(x):
    try:
        return pd.qcut(x, 4, labels=["Q1","Q2","Q3","Q4"], duplicates="drop")
    except Exception:
        return pd.Series(np.nan, index=x.index)

df["mc_q"] = df.groupby("date")["market_cap"].transform(safe_mc_q)

daily_mkt = df.groupby("date").agg(
    mkt_ret=("ret1_w","median"),
    mkt_vol=("volume","median")
).reset_index().sort_values("date")
daily_mkt["ma60_ret"] = daily_mkt["mkt_ret"].rolling(60, min_periods=30).mean()
daily_mkt["ma60_vol"] = daily_mkt["mkt_vol"].rolling(60, min_periods=30).mean()

def regime_lbl(row):
    is_bull = row["mkt_ret"] >= row["ma60_ret"]
    is_hvol = row["mkt_vol"] >= row["ma60_vol"]
    if is_bull and is_hvol:       return "bull_high_vol"
    elif is_bull:                 return "bull_low_vol"
    elif is_hvol:                 return "bear_high_vol"
    else:                         return "bear_low_vol"

daily_mkt["regime"] = daily_mkt.apply(regime_lbl, axis=1)
df = df.merge(daily_mkt[["date","regime"]], on="date", how="left")
print(f"  Regime:\n{df.regime.value_counts().to_string()}")
print(f"  mc_q valid: {df.mc_q.notna().sum():,}")

print("[5] Walk-forward windows...", flush=True)
all_dates = sorted(df["date"].unique())
n_dates = len(all_dates)
IS_DAYS, OOS_DAYS, SLIDE = 252, 63, 63

windows = []
start_idx = 0
while True:
    is_end  = start_idx + IS_DAYS
    oos_end = is_end + OOS_DAYS
    if oos_end > n_dates:
        break
    is_dates  = all_dates[start_idx:is_end]
    oos_dates = all_dates[is_end:oos_end]
    windows.append(dict(
        w_id     = len(windows)+1,
        is_start = is_dates[0],
        is_end   = is_dates[-1],
        oos_start= oos_dates[0],
        oos_end  = oos_dates[-1],
        is_set   = set(is_dates),
        oos_set  = set(oos_dates),
    ))
    start_idx += SLIDE

print(f"  Windows: {len(windows)}")
for ww in windows:
    print(f"    W{ww['w_id']:02d}: IS={ww['is_start'].date()}~{ww['is_end'].date()}  OOS={ww['oos_start'].date()}~{ww['oos_end'].date()}")

def eval_seg(sub, cmf_col, thr, ret_col="ret1_w"):
    mask_sig = sub[cmf_col] > thr
    mask_ns  = sub[cmf_col].notna() & ~mask_sig
    sig_r = sub.loc[mask_sig, ret_col].dropna()
    ns_r  = sub.loc[mask_ns,  ret_col].dropna()
    if len(sig_r) < 10 or len(ns_r) < 10:
        return None
    diff  = sig_r.mean() - ns_r.mean()
    t, pv = stats.ttest_ind(sig_r, ns_r, equal_var=False)
    ci95  = stats.t.interval(0.95, df=len(sig_r)-1,
                              loc=sig_r.mean(), scale=stats.sem(sig_r))
    return dict(diff=diff, net=diff-FEE, pval=pv, n=len(sig_r),
                sig_mean=sig_r.mean(), ns_mean=ns_r.mean(), ci95=ci95)

print("[6] Main walk-forward loop...", flush=True)
PARAMS = [
    (10,0.05),(10,0.10),(10,0.20),
    (20,0.05),(20,0.10),(20,0.20),
    (40,0.05),(40,0.10),(40,0.20),
]

wf_rows = []
for w_cmf, thr in PARAMS:
    cmf_col = f"cmf{w_cmf}"
    param   = f"w{w_cmf}_t{int(thr*100):02d}"
    for ww in windows:
        is_sub  = df[df["date"].isin(ww["is_set"])]
        oos_sub = df[df["date"].isin(ww["oos_set"])]
        is_r  = eval_seg(is_sub,  cmf_col, thr)
        oos_r = eval_seg(oos_sub, cmf_col, thr)
        if oos_r is None:
            continue
        wf_rows.append(dict(
            param=param, w_cmf=w_cmf, threshold=thr,
            win_id=ww["w_id"],
            oos_start=ww["oos_start"], oos_end=ww["oos_end"],
            is_diff=is_r["diff"] if is_r else np.nan,
            is_pval=is_r["pval"] if is_r else np.nan,
            oos_diff=oos_r["diff"], oos_net=oos_r["net"],
            oos_pval=oos_r["pval"], oos_n=oos_r["n"],
            oos_sig_mean=oos_r["sig_mean"], oos_ns_mean=oos_r["ns_mean"],
            ci95_lo=oos_r["ci95"][0], ci95_hi=oos_r["ci95"][1],
        ))

wf = pd.DataFrame(wf_rows)
print(f"  WF rows: {len(wf)}")

summary_rows = []
for param, g in wf.groupby("param"):
    mn    = g.oos_net.mean()
    mg    = g.oos_diff.mean()
    pr    = (g.oos_net > 0).mean()
    t, pv = stats.ttest_1samp(g.oos_net.dropna(), 0)
    summary_rows.append(dict(
        param=param, windows=len(g),
        mean_gross_pp=mg*100, mean_net_pp=mn*100,
        pos_ratio=pr, pval_net=pv,
        mean_n_signal=g.oos_n.mean(),
    ))

summary = pd.DataFrame(summary_rows).sort_values("mean_net_pp", ascending=False)
print("\n=== OOS Summary ===")
print(summary.to_string(index=False))

print("\n[7] Regime decomposition...", flush=True)
REGIMES = ["bull_high_vol","bull_low_vol","bear_high_vol","bear_low_vol"]
oos_all_dates = set()
for ww in windows:
    oos_all_dates |= ww["oos_set"]
oos_df = df[df["date"].isin(oos_all_dates)].copy()

regime_rows = []
for w_cmf, thr in PARAMS:
    cmf_col = f"cmf{w_cmf}"
    param   = f"w{w_cmf}_t{int(thr*100):02d}"
    for regime in REGIMES:
        rsub = oos_df[oos_df["regime"]==regime]
        r = eval_seg(rsub, cmf_col, thr)
        if r is None:
            continue
        regime_rows.append(dict(
            param=param, w_cmf=w_cmf, threshold=thr, regime=regime,
            gross_pp=r["diff"]*100, net_pp=r["net"]*100,
            pval=r["pval"], n=r["n"],
        ))

regime_df = pd.DataFrame(regime_rows)
print("=== Regime Decomposition ===")
print(regime_df.to_string(index=False))

print("\n[8] bull_high_vol x market_cap...", flush=True)
bhv_df = oos_df[oos_df["regime"]=="bull_high_vol"].copy()
cross_rows = []
for w_cmf, thr in PARAMS:
    cmf_col = f"cmf{w_cmf}"
    param   = f"w{w_cmf}_t{int(thr*100):02d}"
    for mc in ["Q1","Q2","Q3","Q4"]:
        csub = bhv_df[bhv_df["mc_q"]==mc]
        r = eval_seg(csub, cmf_col, thr)
        if r is None:
            continue
        cross_rows.append(dict(
            param=param, mc_q=mc,
            gross_pp=r["diff"]*100, net_pp=r["net"]*100,
            pval=r["pval"], n=r["n"],
        ))
cross_df = pd.DataFrame(cross_rows)
print("=== bull_high_vol x market_cap ===")
print(cross_df.to_string(index=False))

print("\n[9] 5-line methodology...", flush=True)
crit1 = True

crit2_params = summary[(summary.mean_net_pp > 0) & (summary.pos_ratio > 0.60)]
crit2 = len(crit2_params) > 0
print(f"Crit2 (OOS Net>0 AND pos>60%): {len(crit2_params)} params pass")
if len(crit2_params) > 0:
    print(crit2_params[["param","mean_net_pp","pos_ratio"]].to_string(index=False))

bhv_pass = regime_df[(regime_df.regime=="bull_high_vol") & (regime_df.net_pp > 0)] if len(regime_df)>0 else pd.DataFrame()
crit3 = len(bhv_pass) > 0
print(f"Crit3 (bull_high_vol net>0): {len(bhv_pass)} entries")
if len(bhv_pass) > 0:
    print(bhv_pass[["param","net_pp","pval","n"]].to_string(index=False))

best_per_win = wf.loc[wf.groupby("win_id")["oos_net"].idxmax(), "param"]
mode_param = best_per_win.mode().iloc[0] if len(best_per_win) > 0 else None
mode_pct   = (best_per_win == mode_param).mean() if mode_param else 0.0
crit4 = mode_pct > 0.50
print(f"Crit4 (param stability): best='{mode_param}' in {mode_pct:.1%} -> {'PASS' if crit4 else 'FAIL'}")

cross_pass = cross_df[(cross_df.net_pp > 0) & (cross_df.pval < 0.05)] if len(cross_df) > 0 else pd.DataFrame()
crit5 = len(cross_pass) > 0
print(f"Crit5 (regime x cap net>0 p<0.05): {len(cross_pass)} entries")
if len(cross_pass) > 0:
    print(cross_pass.to_string(index=False))

score = sum([crit1, crit2, crit3, crit4, crit5])
labels = ["IS p-value 독립","OOS Net>0 & pos>60%","레짐 조건부","파라미터 안정성","레짐x시총 교차"]
flags  = [crit1, crit2, crit3, crit4, crit5]
print(f"\n{'='*60}")
print(f"5-Line Score: {score}/5")
for lbl, flag in zip(labels, flags):
    print(f"  {'PASS' if flag else 'FAIL'}: {lbl}")
if score >= 4:   verdict = "무조건 채택"
elif score == 3: verdict = "조건부 채택"
elif score == 2: verdict = "조건부 폐기"
else:            verdict = "폐기"
print(f"  판정: {verdict}")
print("="*60)

print("\n[10] Visualizations...", flush=True)
fig, axes = plt.subplots(3, 3, figsize=(15, 12), sharey=True)
fig.suptitle("CMF Walk-Forward: OOS Net Return per Window (pp)", fontsize=13)
for ax, (w_cmf, thr) in zip(axes.flat, PARAMS):
    param = f"w{w_cmf}_t{int(thr*100):02d}"
    g = wf[wf.param==param].sort_values("win_id")
    colors = ["green" if v > 0 else "red" for v in g.oos_net]
    ax.bar(g.win_id, g.oos_net*100, color=colors, alpha=0.7)
    ax.axhline(0, color="black", lw=0.8)
    mn = g.oos_net.mean()*100
    ax.axhline(mn, color="blue", lw=1.2, ls="--", label=f"mean={mn:.2f}pp")
    ax.set_title(f"CMF{w_cmf}, thr={thr}", fontsize=10)
    ax.set_xlabel("Window")
    ax.legend(fontsize=7)
plt.tight_layout()
p1 = f"{FIGURES_DIR}/cmf_oos_net_per_window.png"
plt.savefig(p1, dpi=120, bbox_inches="tight")
plt.close()
print(f"  Saved: {p1}")

if len(regime_df) > 0:
    pivot = regime_df.pivot_table(values="net_pp", index="param", columns="regime", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(12, 6))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=-0.5, vmax=0.5)
    plt.colorbar(im, ax=ax, label="Net Return (pp)")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=8)
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i,j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.3f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(val)>0.3 else "black")
    ax.set_title("CMF Regime Decomposition -- OOS Net Return (pp)", fontsize=12)
    plt.tight_layout()
    p2 = f"{FIGURES_DIR}/cmf_regime_heatmap.png"
    plt.savefig(p2, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {p2}")

if len(cross_df) > 0:
    params_sorted = [f"w{w}_t{int(t*100):02d}" for w,t in PARAMS]
    x = np.arange(len(params_sorted))
    width = 0.2
    fig, ax = plt.subplots(figsize=(12, 5))
    for i, mc in enumerate(["Q1","Q2","Q3","Q4"]):
        vals = []
        for p in params_sorted:
            row = cross_df[(cross_df.param==p) & (cross_df.mc_q==mc)]
            vals.append(row.net_pp.values[0] if len(row)>0 else np.nan)
        ax.bar(x + i*width, vals, width, label=mc, alpha=0.8)
    ax.set_xticks(x + width*1.5)
    ax.set_xticklabels(params_sorted, rotation=45, ha="right", fontsize=8)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Net Return (pp)")
    ax.set_title("CMF: bull_high_vol x Market Cap -- OOS Net Return (pp, after 0.3% fee)", fontsize=11)
    ax.legend(title="Market Cap")
    plt.tight_layout()
    p3 = f"{FIGURES_DIR}/cmf_cap_cross.png"
    plt.savefig(p3, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {p3}")

print("\n=== ALL DONE ===", flush=True)