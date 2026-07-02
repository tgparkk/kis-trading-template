from __future__ import annotations
import sys, os, warnings, time
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sqlalchemy
from sqlalchemy import text

FIGURES_DIR = "D:/GIT/kis-trading-template/.omc/scientist/figures"
REPORTS_DIR = "D:/GIT/kis-trading-template/RoboTrader_template/reports/10pct_strategy/phase5_signals"
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

DB_URL = "postgresql+psycopg2://robotrader:1234@127.0.0.1:5433/robotrader_quant"
DB_RT  = "postgresql+psycopg2://robotrader:1234@127.0.0.1:5433/robotrader"
engine    = sqlalchemy.create_engine(DB_URL, pool_pre_ping=True)
engine_rt = sqlalchemy.create_engine(DB_RT,  pool_pre_ping=True)

def sql(q, e=engine):
    with e.connect() as c:
        return pd.read_sql(text(q), c)

# ============================================================
# 1. DATA LOAD
# ============================================================
print("="*70)
print("[DATA] Loading daily_prices ...")
t0 = time.time()

prices_raw = sql("""
    SELECT stock_code, date, close, volume, market_cap, adj_factor
    FROM daily_prices
    WHERE date >= '2021-01-01'
      AND close IS NOT NULL AND volume IS NOT NULL AND volume > 0
    ORDER BY stock_code, date
""")
prices_raw["date"] = pd.to_datetime(prices_raw["date"], errors="coerce")
prices_raw = prices_raw.dropna(subset=["date"])  # drop malformed dates (e.g. 2026--0-3-)
prices_raw["close"]      = pd.to_numeric(prices_raw["close"],      errors="coerce")
prices_raw["volume"]     = pd.to_numeric(prices_raw["volume"],     errors="coerce")
prices_raw["market_cap"] = pd.to_numeric(prices_raw["market_cap"], errors="coerce")
prices_raw["adj_factor"] = pd.to_numeric(prices_raw["adj_factor"], errors="coerce").fillna(1.0)
prices_raw["close_adj"]  = prices_raw["close"] * prices_raw["adj_factor"]
prices_raw = prices_raw.sort_values(["stock_code","date"]).reset_index(drop=True)
n_stocks = prices_raw["stock_code"].nunique()
print(f"  Rows: {len(prices_raw):,}  Stocks: {n_stocks:,}  Time: {time.time()-t0:.1f}s")
print(f"  Date: {prices_raw['date'].min().date()} ~ {prices_raw['date'].max().date()}")

print("[DATA] Loading KOSPI (KS11) ...")
kospi_raw = sql("SELECT stck_bsop_date as ds, stck_clpr as close FROM daily_candles WHERE stock_code='KS11' ORDER BY stck_bsop_date", engine_rt)
kospi_raw["date"]  = pd.to_datetime(kospi_raw["ds"], format="%Y%m%d")
kospi_raw["close"] = pd.to_numeric(kospi_raw["close"], errors="coerce")
kospi = kospi_raw[["date","close"]].dropna().sort_values("date").reset_index(drop=True)
print(f"  KOSPI: {len(kospi)} rows  {kospi['date'].min().date()} ~ {kospi['date'].max().date()}")

# ============================================================
# 2. FORWARD RETURNS
# ============================================================
print("[DATA] Computing forward returns ...")
prices = prices_raw.copy()
all_parts = []
for sc, grp in prices.groupby("stock_code", sort=False):
    g = grp.copy().reset_index(drop=True)
    c = g["close_adj"].values
    n = len(c)
    for h in [1, 5, 20]:
        fwd = np.full(n, np.nan)
        for i in range(n - h):
            fwd[i] = c[i+h] / c[i] - 1.0
        g[f"fwd_{h}"] = fwd
    all_parts.append(g)
prices = pd.concat(all_parts, ignore_index=True)
prices = prices.sort_values(["stock_code","date"]).reset_index(drop=True)

for h in [1, 5, 20]:
    col = f"fwd_{h}"
    lo = prices.groupby("date")[col].transform(lambda x: x.quantile(0.01))
    hi = prices.groupby("date")[col].transform(lambda x: x.quantile(0.99))
    prices[col] = prices[col].clip(lower=lo, upper=hi)

print(f"  prices shape: {prices.shape}")
fwd1_mean = prices['fwd_1'].mean()
print(f"  fwd_1 mean: {fwd1_mean:.4f}")

# ============================================================
# 3. NHB SIGNALS (pre-compute for all window/vol_mult)
# ============================================================
print("[SIGNAL] Pre-computing NHB signals ...")
WINDOWS   = [60, 120, 180, 252, 360]
VOL_MULTS = [1.0, 1.5, 2.0, 3.0]
HOLDINGS  = [1, 5, 20]
GATES     = ["G0","G1","G2","G3"]
FEE       = 0.003

def nhb_signal_stock(close_arr, vol_arr, window, vol_mult):
    n = len(close_arr)
    sig = np.zeros(n, dtype=bool)
    for i in range(window + 1, n):
        prev_max = np.max(close_arr[i-window:i])
        avg_vol  = np.mean(vol_arr[i-window:i])
        if close_arr[i] > prev_max and vol_arr[i] >= avg_vol * vol_mult:
            sig[i] = True
    return sig

sig_cache = {}
total_sig = len(WINDOWS) * len(VOL_MULTS)
done_sig  = 0
for w in WINDOWS:
    for vm in VOL_MULTS:
        parts = []
        for sc, grp in prices.groupby("stock_code", sort=False):
            s = nhb_signal_stock(grp["close_adj"].values, grp["volume"].values, w, vm)
            parts.append(pd.Series(s, index=grp.index))
        sig_series = pd.concat(parts).sort_index().reindex(prices.index).fillna(False)
        sig_cache[(w, vm)] = sig_series.values.astype(bool)
        done_sig += 1
        sig_rate = sig_series.mean()
        print(f"  [{done_sig}/{total_sig}] w={w},vm={vm}  sig_rate={sig_rate:.4f}")

# ============================================================
# 4. GATE COMPUTATION (PIT-safe)
# ============================================================
print("[GATE] Computing gates ...")
all_dates = pd.DatetimeIndex(sorted(prices["date"].unique()))
kospi_idx = kospi.set_index("date")["close"].reindex(all_dates).ffill()

ma60  = kospi_idx.rolling(60,  min_periods=60).mean()
ma120 = kospi_idx.rolling(120, min_periods=120).mean()
ret60 = kospi_idx.pct_change(60)
ret20 = kospi_idx.pct_change(20)

gate_map = pd.DataFrame({
    "G1": (ma60 > ma120),
    "G2": (ret60 > 0),
    "G3": (ma60 > ma120) & (ret20 > 0),
}, index=all_dates)

prices = prices.merge(gate_map.reset_index().rename(columns={"index":"date"}), on="date", how="left")
for g in ["G1","G2","G3"]:
    prices[g] = prices[g].fillna(False)
prices["G0"] = True

for g in ["G1","G2","G3"]:
    rate = prices[g].mean()
    print(f"  {g} activation: {rate:.2%}")

# ============================================================
# 5. WALK-FORWARD OOS (252/63 rolling)
# ============================================================
print("[WF] Setting up walk-forward windows ...")
trading_days = sorted(prices["date"].unique())
N = len(trading_days)
IS_DAYS, OOS_DAYS = 252, 63

wf_windows = []
start = 0
while start + IS_DAYS + OOS_DAYS <= N:
    ie = start + IS_DAYS
    oe = ie + OOS_DAYS
    wf_windows.append({
        "is_start":  trading_days[start],
        "is_end":    trading_days[ie-1],
        "oos_start": trading_days[ie],
        "oos_end":   trading_days[oe-1],
    })
    start += OOS_DAYS

print(f"  WF windows: {len(wf_windows)}")
print(f"  First OOS: {wf_windows[0]['oos_start'].date()} ~ {wf_windows[0]['oos_end'].date()}")
print(f"  Last  OOS: {wf_windows[-1]['oos_start'].date()} ~ {wf_windows[-1]['oos_end'].date()}")

date_arr  = prices["date"].values
gate_arrays = {g: prices[g].values.astype(bool) for g in GATES}
fwd_arrays  = {h: prices[f"fwd_{h}"].values for h in HOLDINGS}

oos_masks = []
for wf in wf_windows:
    m = (date_arr >= np.datetime64(wf["oos_start"])) & (date_arr <= np.datetime64(wf["oos_end"]))
    oos_masks.append(m)

baselines = {}
for wi, (wf, om) in enumerate(zip(wf_windows, oos_masks)):
    for h in HOLDINGS:
        vals = fwd_arrays[h][om]
        baselines[(wi, h)] = float(np.nanmean(vals)) if vals.size > 0 else np.nan

print("[WF] Running grid search (240 combos x", len(wf_windows), "windows) ...")
results = []
total_c = len(WINDOWS)*len(VOL_MULTS)*len(HOLDINGS)*len(GATES)
done_c  = 0

for w in WINDOWS:
    for vm in VOL_MULTS:
        sig_arr = sig_cache[(w, vm)]
        for h in HOLDINGS:
            fv = fwd_arrays[h]
            for gate in GATES:
                ga = gate_arrays[gate]
                wf_rows = []
                for wi, (wf, om) in enumerate(zip(wf_windows, oos_masks)):
                    base    = baselines[(wi, h)]
                    active  = om & ga & sig_arr
                    n_tr    = int(active.sum())
                    if n_tr == 0 or np.isnan(base):
                        continue
                    gross = float(np.nanmean(fv[active]))
                    net   = gross - FEE
                    wf_rows.append({"dg": gross-base, "dn": net-base, "nt": n_tr})
                if not wf_rows:
                    done_c += 1
                    continue
                wf_df = pd.DataFrame(wf_rows)
                results.append({
                    "window": w, "vol_mult": vm, "holding": h, "gate": gate,
                    "oos_net_pp":   float(wf_df["dn"].mean() * 100),
                    "oos_gross_pp": float(wf_df["dg"].mean() * 100),
                    "pct_positive": float((wf_df["dn"] > 0).mean()),
                    "n_windows":    len(wf_df),
                    "avg_trades":   float(wf_df["nt"].mean()),
                })
                done_c += 1
        pct = done_c/total_c*100
        print(f"  [{done_c}/{total_c} {pct:.0f}%] w={w},vm={vm}")

results_df = pd.DataFrame(results)
print(f"[WF] Done. {len(results_df)} result rows.")
csv_path = f"{REPORTS_DIR}/nhb_optimization_grid.csv"
results_df.to_csv(csv_path, index=False)
print(f"[CSV] Saved: {csv_path}")

# ============================================================
# 6. OUTLIER EXCLUSION (2025-07, 2025-10)
# ============================================================
print("[OUTLIER] Excluding 2025-07 and 2025-10 ...")
OUTLIER_RANGES = [
    (pd.Timestamp("2025-07-01"), pd.Timestamp("2025-07-31")),
    (pd.Timestamp("2025-10-01"), pd.Timestamp("2025-10-31")),
]

results_noout = []
for w in WINDOWS:
    for vm in VOL_MULTS:
        sig_arr = sig_cache[(w, vm)]
        for h in HOLDINGS:
            fv = fwd_arrays[h]
            for gate in GATES:
                ga = gate_arrays[gate]
                wf_rows = []
                for wi, (wf, om) in enumerate(zip(wf_windows, oos_masks)):
                    skip = any(
                        wf["oos_start"] <= me and wf["oos_end"] >= ms
                        for ms, me in OUTLIER_RANGES
                    )
                    if skip:
                        continue
                    base   = baselines[(wi, h)]
                    active = om & ga & sig_arr
                    n_tr   = int(active.sum())
                    if n_tr == 0 or np.isnan(base):
                        continue
                    gross = float(np.nanmean(fv[active]))
                    net   = gross - FEE
                    wf_rows.append({"dg": gross-base, "dn": net-base})
                if not wf_rows:
                    continue
                wf_df = pd.DataFrame(wf_rows)
                results_noout.append({
                    "window": w, "vol_mult": vm, "holding": h, "gate": gate,
                    "oos_net_pp":   float(wf_df["dn"].mean() * 100),
                    "oos_gross_pp": float(wf_df["dg"].mean() * 100),
                    "pct_positive": float((wf_df["dn"] > 0).mean()),
                    "n_windows":    len(wf_df),
                })

results_noout_df = pd.DataFrame(results_noout)
print(f"  Outlier-excluded: {len(results_noout_df)} rows")

# ============================================================
# 7. OBV SIGNAL + NHB x OBV COMBO
# ============================================================
print("[OBV] Computing OBV signals (lb=5, thr=1.0std) ...")

def obv_signal_stock(close_arr, vol_arr, lb=5):
    n = len(close_arr)
    obv = np.zeros(n)
    for i in range(1, n):
        if   close_arr[i] > close_arr[i-1]: obv[i] = obv[i-1] + vol_arr[i]
        elif close_arr[i] < close_arr[i-1]: obv[i] = obv[i-1] - vol_arr[i]
        else:                                obv[i] = obv[i-1]
    slope = np.full(n, np.nan)
    for i in range(lb, n):
        slope[i] = obv[i] - obv[i-lb]
    sig = np.zeros(n, dtype=bool)
    slope_s = pd.Series(slope)
    roll_m = slope_s.rolling(252, min_periods=30).mean().shift(1)
    roll_s = slope_s.rolling(252, min_periods=30).std().shift(1)
    for i in range(n):
        if pd.isna(roll_m.iloc[i]) or pd.isna(roll_s.iloc[i]) or roll_s.iloc[i] == 0:
            continue
        z = (slope[i] - roll_m.iloc[i]) / roll_s.iloc[i]
        if z > 1.0:
            sig[i] = True
    return sig

obv_parts = []
for sc, grp in prices.groupby("stock_code", sort=False):
    s = obv_signal_stock(grp["close_adj"].values, grp["volume"].values)
    obv_parts.append(pd.Series(s, index=grp.index))
obv_arr = pd.concat(obv_parts).sort_index().reindex(prices.index).fillna(False).values.astype(bool)
nhb_ref_arr = sig_cache[(252, 1.5)]
nhb_obv_arr = nhb_ref_arr & obv_arr
print(f"  OBV rate: {obv_arr.mean():.4f}  NHBxOBV rate: {nhb_obv_arr.mean():.4f}")

def wf_net_summary(sig_a, gate, h):
    ga = gate_arrays[gate]
    fv = fwd_arrays[h]
    vals = []
    for wi, (wf, om) in enumerate(zip(wf_windows, oos_masks)):
        base   = baselines[(wi, h)]
        active = om & ga & sig_a
        if active.sum() == 0 or np.isnan(base):
            continue
        net = float(np.nanmean(fv[active])) - FEE
        vals.append(net - base)
    if not vals:
        return np.nan, np.nan
    arr = np.array(vals)
    return float(np.mean(arr) * 100), float((arr > 0).mean())

combo_results = []
for gate in GATES:
    for h in HOLDINGS:
        nhb_n, nhb_p = wf_net_summary(nhb_ref_arr, gate, h)
        obv_n, obv_p = wf_net_summary(obv_arr, gate, h)
        cmb_n, cmb_p = wf_net_summary(nhb_obv_arr, gate, h)
        combo_results.append({"gate":gate,"holding":h,
            "nhb_net_pp":nhb_n,"nhb_pct_pos":nhb_p,
            "obv_net_pp":obv_n,"obv_pct_pos":obv_p,
            "combo_net_pp":cmb_n,"combo_pct_pos":cmb_p})
combo_df = pd.DataFrame(combo_results)
print(f"  Combo results: {len(combo_df)} rows")

# ============================================================
# 8. ROE Q4+ COMBO
# ============================================================
print("[ROE] Loading ROE from quant_factors ...")
HAS_ROE = False
try:
    roe_raw = sql("SELECT stock_code, date, roe FROM quant_factors WHERE roe IS NOT NULL ORDER BY stock_code, date")
    roe_raw["date"] = pd.to_datetime(roe_raw["date"])
    roe_raw["roe"]  = pd.to_numeric(roe_raw["roe"], errors="coerce")
    roe_raw["roe_q"] = roe_raw.groupby("date")["roe"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
    roe_q4 = roe_raw[roe_raw["roe_q"] >= 3][["stock_code","date"]].copy()
    roe_q4["roe_q4"] = True
    prices = prices.merge(roe_q4, on=["stock_code","date"], how="left")
    prices["roe_q4"] = prices["roe_q4"].fillna(False)
    roe_arr = prices["roe_q4"].values.astype(bool)
    HAS_ROE = True
    print(f"  ROE Q4+ rate: {roe_arr.mean():.2%}")
except Exception as ex:
    print(f"  ROE load failed: {ex}")
    roe_arr = np.ones(len(prices), dtype=bool)

roe_combo_results = []
for gate in GATES:
    ga = gate_arrays[gate]
    for h in HOLDINGS:
        fv = fwd_arrays[h]
        vals = []
        for wi, (wf, om) in enumerate(zip(wf_windows, oos_masks)):
            base   = baselines[(wi, h)]
            active = om & ga & nhb_ref_arr & roe_arr
            if active.sum() == 0 or np.isnan(base):
                continue
            net = float(np.nanmean(fv[active])) - FEE
            vals.append(net - base)
        if vals:
            arr = np.array(vals)
            roe_combo_results.append({"gate":gate,"holding":h,
                "nhb_roe_net_pp":float(np.mean(arr)*100),
                "nhb_roe_pct_pos":float((arr>0).mean()),
                "n_windows":len(arr)})
        else:
            roe_combo_results.append({"gate":gate,"holding":h,
                "nhb_roe_net_pp":np.nan,"nhb_roe_pct_pos":np.nan,"n_windows":0})
roe_combo_df = pd.DataFrame(roe_combo_results)

# ============================================================
# 9. MCAP QUINTILE CROSS
# ============================================================
print("[MCAP] Computing market-cap quintile cross ...")
prices["mcap_q"] = prices.groupby("date")["market_cap"].transform(
    lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
mcap_results = []
for q in range(5):
    q_arr = (prices["mcap_q"] == q).values
    for gate in ["G0","G1"]:
        ga = gate_arrays[gate]
        for h in [1, 5]:
            fv = fwd_arrays[h]
            vals = []
            for wi, (wf, om) in enumerate(zip(wf_windows, oos_masks)):
                base   = baselines[(wi, h)]
                active = om & ga & nhb_ref_arr & q_arr
                if active.sum() == 0 or np.isnan(base):
                    continue
                net = float(np.nanmean(fv[active])) - FEE
                vals.append(net - base)
            if vals:
                arr = np.array(vals)
                mcap_results.append({"mcap_q":q+1,"gate":gate,"holding":h,
                    "net_pp":float(np.mean(arr)*100),
                    "pct_pos":float((arr>0).mean()),
                    "n_windows":len(arr)})
mcap_df = pd.DataFrame(mcap_results)

# ============================================================
# 10. 5-LINE EVALUATION
# ============================================================
print("[5-LINE] Evaluating ...")
five_line = {}
g0h1_net = results_df[(results_df["gate"]=="G0")&(results_df["holding"]==1)]["oos_net_pp"].mean()

for gate in GATES:
    sub = results_df[(results_df["gate"]==gate) & (results_df["holding"]==1)]
    if len(sub) == 0:
        five_line[gate] = {"c1":True,"c2":False,"c3":False,"c4":False,"c5":False,"total":1}
        continue
    c1 = True
    c2 = bool((sub["oos_net_pp"] > 0).mean() > 0.5 and sub["pct_positive"].mean() > 0.6)
    if gate == "G0":
        c3 = True
    else:
        gate_net = sub["oos_net_pp"].mean()
        c3 = bool(gate_net >= g0h1_net)
    best = sub.nlargest(1,"oos_net_pp").iloc[0]
    bw, bvm = best["window"], best["vol_mult"]
    stable_rows = results_df[(results_df["gate"]==gate)&(results_df["window"]==bw)&(results_df["vol_mult"]==bvm)]
    c4 = bool(stable_rows["pct_positive"].mean() >= 0.5) if len(stable_rows) > 0 else False
    sub_mc = mcap_df[(mcap_df["gate"]==("G0" if gate=="G0" else "G1"))&(mcap_df["mcap_q"]==5)&(mcap_df["holding"]==1)]
    c5 = bool(len(sub_mc) > 0 and sub_mc["net_pp"].values[0] > 0)
    total = sum([c1,c2,c3,c4,c5])
    five_line[gate] = {"c1":c1,"c2":c2,"c3":c3,"c4":c4,"c5":c5,"total":total}
    print(f"  {gate}: C1={c1} C2={c2} C3={c3} C4={c4} C5={c5} -> {total}/5")

# ============================================================
# 11. VISUALIZATIONS
# ============================================================
print("[VIZ] Generating figures ...")

# Fig 1: Heatmap 60 params OOS Net pp (G0)
fig1, axes = plt.subplots(1, 3, figsize=(18,5))
fig1.suptitle("NHB OOS Net pp (Benchmark-adj, fee=0.3%) - G0 No Gate", fontsize=13, fontweight="bold")
for ai, h in enumerate([1, 5, 20]):
    sub   = results_df[(results_df["gate"]=="G0") & (results_df["holding"]==h)]
    pivot = sub.pivot(index="window", columns="vol_mult", values="oos_net_pp")
    ax    = axes[ai]
    flat  = pivot.values[~np.isnan(pivot.values)]
    vmax  = max(abs(flat).max(), 0.05) if len(flat) > 0 else 0.1
    im    = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"{v}x" for v in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(w) for w in pivot.index])
    ax.set_xlabel("vol_mult"); ax.set_ylabel("window (days)")
    ax.set_title(f"Holding={h}d")
    plt.colorbar(im, ax=ax, label="OOS Net pp")
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i,j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7)
plt.tight_layout()
fig1_path = f"{FIGURES_DIR}/nhb_heatmap_g0.png"
plt.savefig(fig1_path, dpi=120, bbox_inches="tight"); plt.close()
print(f"  Fig1: {fig1_path}")

# Fig 2: Gate comparison bar chart
gate_labels = {"G0":"G0: None","G1":"G1: MA60>MA120","G2":"G2: ret60>0","G3":"G3: Bull Regime"}
gate_colors = {"G0":"#2196F3","G1":"#4CAF50","G2":"#FF9800","G3":"#9C27B0"}
fig2, axes2 = plt.subplots(1, 3, figsize=(18,6))
fig2.suptitle("NHB: Gate Comparison - Best Params per Gate", fontsize=13, fontweight="bold")
for ai, h in enumerate([1, 5, 20]):
    ax = axes2[ai]
    nets, pos_pct, labels, colors = [], [], [], []
    for gate in GATES:
        sub = results_df[(results_df["gate"]==gate) & (results_df["holding"]==h)]
        if len(sub) == 0: continue
        best = sub.nlargest(1,"oos_net_pp").iloc[0]
        nets.append(best["oos_net_pp"])
        pos_pct.append(best["pct_positive"] * 100)
        labels.append(f"{gate_labels[gate]}\n(w={int(best['window'])},vm={best['vol_mult']})")
        colors.append(gate_colors[gate])
    x    = np.arange(len(nets))
    bars = ax.bar(x, nets, color=colors, alpha=0.85, width=0.5)
    ax.axhline(0, color="black", lw=0.8, ls="--")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("OOS Net pp"); ax.set_title(f"Holding={h}d")
    for bar, p in zip(bars, pos_pct):
        ypos = bar.get_height() + (0.02 if bar.get_height() >= 0 else -0.08)
        ax.text(bar.get_x()+bar.get_width()/2, ypos, f"{p:.0f}%+", ha="center", va="bottom", fontsize=8)
plt.tight_layout()
fig2_path = f"{FIGURES_DIR}/nhb_gate_comparison.png"
plt.savefig(fig2_path, dpi=120, bbox_inches="tight"); plt.close()
print(f"  Fig2: {fig2_path}")

# Fig 3: NHB x OBV scatter
fig3, axes3 = plt.subplots(1, 3, figsize=(15,5))
fig3.suptitle("NHB x OBV Combination Effect", fontsize=13, fontweight="bold")
for ai, h in enumerate([1, 5, 20]):
    ax  = axes3[ai]
    sub = combo_df[(combo_df["holding"]==h) & (combo_df["gate"]=="G0")]
    if len(sub) == 0: continue
    r   = sub.iloc[0]
    strategies  = ["NHB alone", "OBV alone", "NHB x OBV"]
    xvals = [r["nhb_net_pp"], r["obv_net_pp"], r["combo_net_pp"]]
    yvals = [r["nhb_pct_pos"]*100 if not pd.isna(r["nhb_pct_pos"]) else np.nan,
             r["obv_pct_pos"]*100 if not pd.isna(r["obv_pct_pos"]) else np.nan,
             r["combo_pct_pos"]*100 if not pd.isna(r["combo_pct_pos"]) else np.nan]
    dot_colors = ["#2196F3","#4CAF50","#FF5722"]
    for sx, sy, sc, ss in zip(xvals, yvals, dot_colors, strategies):
        if pd.isna(sx) or pd.isna(sy): continue
        ax.scatter(sx, sy, color=sc, s=200, zorder=5, label=ss)
        ax.annotate(f"{ss}\n({sx:.2f}pp,{sy:.0f}%+)", (sx,sy),
                    textcoords="offset points", xytext=(6,6), fontsize=8)
    ax.axhline(60, color="gray", ls="--", lw=0.8, label="60% threshold")
    ax.axvline(0,  color="gray", ls="--", lw=0.8)
    ax.set_xlabel("OOS Net pp"); ax.set_ylabel("Pct Positive Windows (%)")
    ax.set_title(f"Holding={h}d"); ax.legend(fontsize=7)
plt.tight_layout()
fig3_path = f"{FIGURES_DIR}/nhb_obv_combo.png"
plt.savefig(fig3_path, dpi=120, bbox_inches="tight"); plt.close()
print(f"  Fig3: {fig3_path}")

# ============================================================
# 12. SUMMARY PRINT
# ============================================================
print()
print("="*70)
print("FINAL RESULTS SUMMARY")
print("="*70)

print("\n[TOP 10] Best combos (all gates, holding=1):")
top10 = results_df[results_df["holding"]==1].nlargest(10,"oos_net_pp")[
    ["gate","window","vol_mult","holding","oos_net_pp","oos_gross_pp","pct_positive","n_windows","avg_trades"]]
print(top10.to_string(index=False))

print("\n[GATE BEST] Best params per gate (holding=1):")
for gate in GATES:
    sub = results_df[(results_df["gate"]==gate) & (results_df["holding"]==1)]
    if len(sub) == 0: continue
    best = sub.nlargest(1,"oos_net_pp").iloc[0]
    print(f"  {gate}: w={int(best['window'])}, vm={best['vol_mult']}, net={best['oos_net_pp']:.3f}pp, pos={best['pct_positive']:.2%}, n_win={int(best['n_windows'])}")

print("\n[G0 ALL PARAMS h=1] 60-cell grid:")
g0h1 = results_df[(results_df["gate"]=="G0") & (results_df["holding"]==1)].sort_values("oos_net_pp", ascending=False)
print(g0h1[["window","vol_mult","oos_net_pp","pct_positive","n_windows"]].to_string(index=False))

print("\n[OUTLIER] Excluding 2025-07 & 2025-10:")
for gate in ["G0","G1"]:
    for h in [1, 5]:
        sub_a = results_df[(results_df["gate"]==gate) & (results_df["holding"]==h)]
        sub_n = results_noout_df[(results_noout_df["gate"]==gate) & (results_noout_df["holding"]==h)]
        if len(sub_a) == 0 or len(sub_n) == 0: continue
        na = sub_a["oos_net_pp"].mean()
        nn = sub_n["oos_net_pp"].mean()
        print(f"  {gate} h={h}: incl={na:.3f}pp  excl={nn:.3f}pp  delta={nn-na:+.3f}pp")

print("\n[NHB x OBV] Combination (G0):")
sub_c = combo_df[combo_df["gate"]=="G0"]
print(sub_c[["holding","nhb_net_pp","obv_net_pp","combo_net_pp","combo_pct_pos"]].to_string(index=False))

if HAS_ROE:
    print("\n[NHB x ROE Q4+] (G0):")
    sub_r = roe_combo_df[roe_combo_df["gate"]=="G0"]
    print(sub_r[["holding","nhb_roe_net_pp","nhb_roe_pct_pos","n_windows"]].to_string(index=False))

print("\n[MCAP CROSS] (G0, h=1):")
sub_m = mcap_df[(mcap_df["gate"]=="G0") & (mcap_df["holding"]==1)]
if len(sub_m) > 0:
    print(sub_m[["mcap_q","net_pp","pct_pos","n_windows"]].to_string(index=False))

print("\n[5-LINE EVALUATION]:")
for gate in GATES:
    fl = five_line.get(gate, {})
    print(f"  {gate}: C1={fl.get('c1','?')} C2={fl.get('c2','?')} C3={fl.get('c3','?')} C4={fl.get('c4','?')} C5={fl.get('c5','?')} -> {fl.get('total','?')}/5")

print()
print("="*70)
print(f"CSV: {csv_path}")
print(f"Fig1: {fig1_path}")
print(f"Fig2: {fig2_path}")
print(f"Fig3: {fig3_path}")
print("="*70)
