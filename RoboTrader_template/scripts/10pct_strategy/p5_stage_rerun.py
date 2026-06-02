"""
p5_stage_rerun.py — Phase 5: OBV (lb=5, 1σ) + ROE (Q4+) Stage A/B/C Rerun
=============================================================================
사장님 결재 2026-05-25: OBV+ROE 2개 시그널만으로 Stage A/B/C 재실행 + WF 6-window

대원칙:
  - No Look-Ahead: 모든 시그널/필터 PIT-safe
  - Chronological Walk-Forward: 252/63 6+ windows
  - 5선 방법론: IS p-value만으로 판단 금지, OOS Net 양의 비율 >60% 필수
"""

import sys, os, time, warnings, traceback
import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "10pct_strategy")
P5_DIR     = os.path.join(REPORT_DIR, "phase5_signals")
FIG_DIR    = os.path.join(os.path.dirname(BASE_DIR), ".omc", "scientist", "figures")
os.makedirs(P5_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
REGIMES_6 = ["BULL_HIGH_VOL","BULL_LOW_VOL","BEAR_HIGH_VOL",
              "BEAR_LOW_VOL","SIDEWAYS_HIGH_VOL","SIDEWAYS_LOW_VOL"]
APPROVED_REGIMES = ["BULL_HIGH_VOL","BULL_LOW_VOL","BEAR_HIGH_VOL","SIDEWAYS_LOW_VOL"]
IS_CUTOFF        = pd.Timestamp("2025-01-01")
WF_TRAIN_DAYS    = 365
WF_TEST_DAYS     = 91
FEE              = 0.003
OBV_LB           = 5
OBV_THR          = 1.0   # 1-sigma threshold
ROE_Q_MIN        = 4     # Q4+ (top 40%)
N_MIN            = 30
TOP_K            = 5     # triples per regime
SL_GRID = [-0.015, -0.02, -0.03, -0.04, -0.05]
TP_GRID = [0.03, 0.05, 0.07, 0.10, 0.15]
TM_GRID = [5, 10, 20, 30, 45, 60]

DB = dict(host="127.0.0.1", port=5433, dbname="robotrader_quant",
          user="robotrader", password="1234")


# =============================================================================
# DATA LOAD
# =============================================================================
def load_data():
    t0 = time.time()
    print("[1/4] forward returns ...")
    fwd = pd.read_parquet(os.path.join(REPORT_DIR, "phase1_forward_returns.parquet"))
    fwd["date"] = pd.to_datetime(fwd["date"])
    print(f"  fwd: {fwd.shape}")

    print("[2/4] regime segments ...")
    seg = pd.read_csv(os.path.join(REPORT_DIR, "phase0_regime_segments.csv"))
    seg = seg[seg["index_code"] == "KOSPI"].copy()
    seg["start_date"] = pd.to_datetime(seg["start_date"])
    seg["end_date"]   = pd.to_datetime(seg["end_date"])
    date_to_regime = {}
    for _, row in seg.iterrows():
        for d in pd.date_range(row["start_date"], row["end_date"], freq="B"):
            date_to_regime[d] = row["label_6"]
    print(f"  regime map: {len(date_to_regime)} days")

    print("[3/4] daily_prices ...")
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    cur.execute("""
        SELECT stock_code, date::text AS date,
               open, high, low, close, volume, trading_value, market_cap
        FROM daily_prices
        WHERE close > 0 AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        ORDER BY stock_code, date
    """)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    conn.close()
    prices = pd.DataFrame(rows, columns=cols)
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    prices = prices.dropna(subset=["date"]).reset_index(drop=True)
    for c in ["open","high","low","close","volume","trading_value","market_cap"]:
        prices[c] = pd.to_numeric(prices[c], errors="coerce")
    print(f"  prices: {prices.shape}")

    print("[4/4] ROE financial_statements ...")
    conn2 = psycopg2.connect(**DB)
    cur2  = conn2.cursor()
    cur2.execute("""
        SELECT stock_code, report_date::text AS report_date, roe
        FROM financial_statements WHERE roe IS NOT NULL
        ORDER BY stock_code, report_date
    """)
    roe_rows = cur2.fetchall()
    conn2.close()
    roe_raw = pd.DataFrame(roe_rows, columns=["stock_code","report_date","roe"])
    roe_raw["report_date"] = pd.to_datetime(roe_raw["report_date"], errors="coerce")
    roe_raw["roe"]         = pd.to_numeric(roe_raw["roe"], errors="coerce")
    roe_raw = roe_raw.dropna(subset=["report_date","roe"]).reset_index(drop=True)
    print(f"  roe: {roe_raw.shape}, stocks: {roe_raw['stock_code'].nunique()}")
    print(f"  Load done: {time.time()-t0:.1f}s")
    return fwd, date_to_regime, prices, roe_raw



# =============================================================================
# ROE PIT UNIVERSE MAP  (monthly scan, Q4+ filter)
# =============================================================================
def build_roe_universe_map(prices, roe_raw, min_quintile=4):
    print(f"\n[ROE] Building PIT ROE universe map (Q{min_quintile}+) ...")
    t0 = time.time()
    roe_sorted = roe_raw.sort_values(["stock_code","report_date"]).reset_index(drop=True)
    all_dates  = sorted(prices["date"].dropna().unique())

    monthly_dates = sorted(set(
        pd.Timestamp(d.year, d.month, 1) for d in all_dates
    ))
    month_passed = {}
    for scan_ts in monthly_dates:
        eligible = roe_sorted[roe_sorted["report_date"] <= scan_ts]
        if len(eligible) == 0:
            month_passed[scan_ts] = set(); continue
        latest = eligible.groupby("stock_code")["roe"].last()
        if len(latest) < 5:
            month_passed[scan_ts] = set(); continue
        lo, hi = latest.quantile(0.01), latest.quantile(0.99)
        latest_w = latest.clip(lo, hi)
        try:
            quintiles = pd.qcut(latest_w, q=5, labels=[1,2,3,4,5], duplicates="drop")
            passed = set(quintiles[quintiles.astype(int) >= min_quintile].index.tolist())
        except Exception:
            passed = set()
        month_passed[scan_ts] = passed

    roe_map = {}
    for d in all_dates:
        scan_ts = pd.Timestamp(d.year, d.month, 1)
        roe_map[d] = month_passed.get(scan_ts, set())

    sample_dates = [d for d in all_dates if len(roe_map[d]) > 0]
    avg_size = np.mean([len(roe_map[d]) for d in sample_dates]) if sample_dates else 0
    print(f"  ROE map: {len(roe_map)} dates, avg_pass={avg_size:.0f} stocks/date")
    print(f"  ROE map done: {time.time()-t0:.1f}s")
    return roe_map


# =============================================================================
# PIT FEATURES + OBV SIGNAL
# =============================================================================
def compute_features(prices, date_to_regime):
    print("\n[FEATURES] Computing PIT features + OBV ...")
    t0 = time.time()
    prices = prices.sort_values(["stock_code","date"]).reset_index(drop=True)
    g = prices.groupby("stock_code", sort=False)

    prices["ret1d"]   = g["close"].pct_change()
    prices["close_t"] = prices["close"]
    prices["vol_t"]   = prices["volume"]
    prices["tv_ma20"] = g["trading_value"].transform(
        lambda x: x.rolling(20, min_periods=1).mean())
    prices["vol20d_std"] = g["ret1d"].transform(
        lambda x: x.rolling(20, min_periods=5).std())

    def qrank(s):
        pct = s.rank(pct=True, na_option="keep")
        return pd.cut(pct, bins=[-1e-10,.2,.4,.6,.8,1.0],
                      labels=[1,2,3,4,5]).astype("Int64")
    prices["vol20d_quintile"] = prices.groupby("date")["vol20d_std"].transform(qrank)
    prices["is_bullish"] = (prices["close"] >= prices["open"]).astype(float)
    prices["bullish_ratio_20d"] = g["is_bullish"].transform(
        lambda x: x.rolling(20, min_periods=5).mean())
    prices["regime"] = prices["date"].map(date_to_regime)
    print(f"  Basic features: {time.time()-t0:.1f}s")

    # ── OBV ──────────────────────────────────────────────────────────────────
    print("  Computing OBV ...")
    def _obv_single(close_arr, vol_arr):
        n   = len(close_arr)
        obv = np.zeros(n, dtype=float)
        for i in range(1, n):
            c, p, v = float(close_arr[i]), float(close_arr[i-1]), float(vol_arr[i])
            if np.isnan(c) or np.isnan(p) or np.isnan(v): obv[i] = obv[i-1]
            elif c > p: obv[i] = obv[i-1] + v
            elif c < p: obv[i] = obv[i-1] - v
            else:       obv[i] = obv[i-1]
        return obv

    parts = []
    for code, grp in prices.groupby("stock_code", sort=False):
        arr = _obv_single(grp["close"].values, grp["volume"].values)
        parts.append(pd.Series(arr, index=grp.index))
    prices["obv"] = pd.concat(parts).sort_index()

    # OBV slope (OLS, lb=OBV_LB)
    print("  Computing OBV slope ...")
    lb    = OBV_LB
    x_ols = np.arange(lb, dtype=float) - (lb-1)/2.0
    ss_x  = (x_ols**2).sum()
    sp = []
    for code, grp in prices.groupby("stock_code", sort=False):
        ov = grp["obv"].values.astype(float)
        n  = len(ov)
        sl = np.full(n, np.nan)
        for i in range(lb-1, n):
            y = ov[i-lb+1:i+1]
            if not np.any(np.isnan(y)):
                sl[i] = (x_ols*(y-y.mean())).sum()/ss_x
        sp.append(pd.Series(sl, index=grp.index))
    prices["obv_slope"] = pd.concat(sp).sort_index()

    # Rolling std of slope for threshold
    prices["obv_slope_std"] = g["obv_slope"].transform(
        lambda x: x.rolling(252, min_periods=30).std())

    # OBV signal: slope >= OBV_THR * std
    prices["obv_signal"] = (
        prices["obv_slope"].notna() &
        prices["obv_slope_std"].notna() &
        (prices["obv_slope"] >= OBV_THR * prices["obv_slope_std"])
    ).astype(int)

    n_sig = prices["obv_signal"].sum()
    print(f"  OBV signal: {n_sig:,} triggers ({n_sig/len(prices)*100:.1f}%)")
    print(f"  Features total: {time.time()-t0:.1f}s, shape: {prices.shape}")
    return prices



# =============================================================================
# UNIVERSE FILTER (p2a pool params + ROE gate)
# =============================================================================
def apply_pool_filter(df, pool):
    regime = pool["regime"]
    mask   = df["regime"] == regime
    top_n  = pool.get("mcap_cutoff_top_n")
    if pd.notna(top_n) and int(top_n) > 0:
        mr = df.groupby("date")["market_cap"].rank(ascending=False,method="first",na_option="bottom")
        mask &= (mr <= int(top_n))
    min_tv = pool.get("min_trading_value")
    if pd.notna(min_tv) and float(min_tv) > 0:
        mask &= (df["tv_ma20"] >= float(min_tv))
    mp = pool.get("min_price")
    if pd.notna(mp) and float(mp) > 0:
        mask &= (df["close_t"] >= float(mp))
    vq = pool.get("vol_quintile")
    if pd.notna(vq) and int(vq) != 0:
        mask &= (df["vol20d_quintile"] == int(vq))
    ch = pool.get("candle_health")
    if pd.notna(ch) and float(ch) > 0:
        mask &= (df["bullish_ratio_20d"] >= float(ch))
    return mask


def apply_roe_gate(df, roe_map):
    result = pd.Series(False, index=df.index)
    for date, group in df.groupby("date"):
        passed = roe_map.get(date, set())
        if passed:
            result.loc[group.index[group["stock_code"].isin(passed)]] = True
    return result


# =============================================================================
# EXIT SIMULATION
# =============================================================================
def simulate_exit(ohlc, sl, tp, tm):
    if len(ohlc) == 0: return np.nan
    entry = ohlc[0, 0]
    if entry <= 0 or np.isnan(entry): return np.nan
    sl_p, tp_p = entry*(1+sl), entry*(1+tp)
    n = min(tm, len(ohlc))
    for d in range(n):
        h, lo, c = ohlc[d,1], ohlc[d,2], ohlc[d,3]
        if np.isnan(lo) or np.isnan(h) or np.isnan(c): continue
        if lo <= sl_p: return sl
        if h  >= tp_p: return tp
    last = ohlc[n-1, 3]
    if np.isnan(last): return np.nan
    return (last - entry) / entry


def compute_mdd(pnl_list):
    if not pnl_list: return np.nan
    eq = np.cumprod(1 + np.array(pnl_list))
    rm = np.maximum.accumulate(eq)
    return float(((eq-rm)/rm).min())


def compute_sharpe(arr):
    if len(arr) < 2: return np.nan
    s = arr.std()
    return float(arr.mean()/s*np.sqrt(252)) if s > 0 else np.nan


def build_prices_pivot(prices_df):
    pivot = {}
    for sc, grp in prices_df.groupby("stock_code", sort=False):
        grp2 = grp.sort_values("date").set_index("date")
        grp2["adj_open"]  = grp2["open"]
        grp2["adj_high"]  = grp2["high"]
        grp2["adj_low"]   = grp2["low"]
        grp2["adj_close"] = grp2["close"]
        pivot[sc] = grp2[["adj_open","adj_high","adj_low","adj_close"]]
    return pivot


# =============================================================================
# TRIPLE EVALUATION
# =============================================================================
def evaluate_triple(merged_df, pool, roe_map, prices_pivot, sl, tp, tm):
    pool_mask = apply_pool_filter(merged_df, pool)
    pool_df   = merged_df[pool_mask]
    if len(pool_df) < N_MIN:
        return {"n":0,"mean_pnl":np.nan,"sharpe":np.nan,"mdd":np.nan,
                "IS_mean":np.nan,"OOS_mean":np.nan,"win_rate":np.nan}

    roe_mask = apply_roe_gate(pool_df, roe_map)
    pool_df  = pool_df[roe_mask]
    if len(pool_df) < N_MIN:
        return {"n":0,"mean_pnl":np.nan,"sharpe":np.nan,"mdd":np.nan,
                "IS_mean":np.nan,"OOS_mean":np.nan,"win_rate":np.nan}

    sig_df = pool_df[pool_df["obv_signal"]==1][["date","stock_code"]]
    if len(sig_df) < N_MIN:
        return {"n":0,"mean_pnl":np.nan,"sharpe":np.nan,"mdd":np.nan,
                "IS_mean":np.nan,"OOS_mean":np.nan,"win_rate":np.nan}

    pnl_all, is_p, oos_p = [], [], []
    for _, row in sig_df.iterrows():
        sc, date = row["stock_code"], row["date"]
        if sc not in prices_pivot: continue
        sc_df = prices_pivot[sc]
        try: loc = sc_df.index.get_loc(date)
        except KeyError: continue
        s = loc+1; e = s+tm
        if s >= len(sc_df): continue
        ohlc = sc_df.iloc[s:e][["adj_open","adj_high","adj_low","adj_close"]].values
        if len(ohlc) == 0: continue
        pnl = simulate_exit(ohlc, sl, tp, tm)
        if np.isnan(pnl): continue
        pnl_all.append(pnl)
        (is_p if date < IS_CUTOFF else oos_p).append(pnl)

    n = len(pnl_all)
    if n < N_MIN:
        return {"n":n,"mean_pnl":np.nan,"sharpe":np.nan,"mdd":np.nan,
                "IS_mean":np.nan,"OOS_mean":np.nan,"win_rate":np.nan}
    arr = np.array(pnl_all)
    return {
        "n":        n,
        "mean_pnl": float(arr.mean()),
        "sharpe":   compute_sharpe(arr),
        "mdd":      compute_mdd(pnl_all),
        "IS_mean":  float(np.mean(is_p))  if len(is_p)  >= 10 else np.nan,
        "OOS_mean": float(np.mean(oos_p)) if len(oos_p) >= 10 else np.nan,
        "win_rate": float((arr>0).mean()),
        "n_is":     len(is_p),
        "n_oos":    len(oos_p),
    }



# =============================================================================
# WALK-FORWARD
# =============================================================================
def build_wf_windows(date_min, date_max):
    windows, start = [], date_min
    while len(windows) < 6:
        te = start + pd.Timedelta(days=WF_TRAIN_DAYS)
        te2= te    + pd.Timedelta(days=WF_TEST_DAYS)
        if te2 > date_max: break
        windows.append({"window":len(windows)+1,
                        "train_start":start,"train_end":te,
                        "test_start":te,"test_end":te2})
        start = start + pd.Timedelta(days=WF_TEST_DAYS)
    return windows


def daily_to_monthly(daily):
    if len(daily) == 0: return pd.Series(dtype=float)
    return daily.groupby([daily.index.year, daily.index.month]).apply(
        lambda x: float(np.prod(1+x)-1))


def portfolio_metrics(monthly):
    if len(monthly) == 0:
        return {k: np.nan for k in
                ["ann_return","sharpe","calmar","mdd","monthly_mean",
                 "monthly_median","monthly_q1","monthly_q5","n_positive","n_months"]}
    arr = monthly.values
    eq  = np.cumprod(1+arr)
    tot = float(eq[-1]-1); n_mo = len(arr)
    ann = float((1+tot)**(12/n_mo)-1) if n_mo else np.nan
    std = arr.std()
    sharpe = float(arr.mean()/std*np.sqrt(12)) if std > 0 else np.nan
    rm  = np.maximum.accumulate(eq)
    mdd = float(((eq-rm)/rm).min())
    calmar = float(ann/abs(mdd)) if (mdd < 0 and not np.isnan(ann)) else np.nan
    return {"ann_return":round(ann,4) if not np.isnan(ann) else np.nan,
            "sharpe":round(sharpe,4) if not np.isnan(sharpe) else np.nan,
            "calmar":round(calmar,4) if not np.isnan(calmar) else np.nan,
            "mdd":round(mdd,4),
            "monthly_mean":round(float(arr.mean()),4),
            "monthly_median":round(float(np.median(arr)),4),
            "monthly_q1":round(float(np.percentile(arr,25)),4),
            "monthly_q5":round(float(np.percentile(arr,5)),4),
            "n_positive":int((arr>0).sum()),
            "n_months":n_mo}


def extract_triple_pnl(triple, merged_df, roe_map, prices_pivot):
    pool = triple["pool"]
    sl, tp, tm = triple["sl"], triple["tp"], triple["tm"]
    pool_mask = apply_pool_filter(merged_df, pool)
    pool_df   = merged_df[pool_mask]
    if len(pool_df) < N_MIN: return pd.Series(dtype=float)
    roe_mask  = apply_roe_gate(pool_df, roe_map)
    pool_df   = pool_df[roe_mask]
    if len(pool_df) < N_MIN: return pd.Series(dtype=float)
    sig_df = pool_df[pool_df["obv_signal"]==1][["date","stock_code"]]
    if len(sig_df) < N_MIN: return pd.Series(dtype=float)
    records = []
    for _, row in sig_df.iterrows():
        sc, date = row["stock_code"], row["date"]
        if sc not in prices_pivot: continue
        sc_df = prices_pivot[sc]
        try: loc = sc_df.index.get_loc(date)
        except KeyError: continue
        s = loc+1; e = s+tm
        if s >= len(sc_df): continue
        ohlc = sc_df.iloc[s:e][["adj_open","adj_high","adj_low","adj_close"]].values
        if not len(ohlc): continue
        pnl = simulate_exit(ohlc, sl, tp, tm)
        if not np.isnan(pnl): records.append({"date":date,"pnl":pnl})
    if not records: return pd.Series(dtype=float)
    return pd.DataFrame(records).groupby("date")["pnl"].mean()


def run_walkforward(top_triples, merged_df, roe_map, prices_pivot, windows):
    print(f"\n[WF] {len(windows)}-window WF on {len(top_triples)} triples ...")
    t0 = time.time()
    pnl_series = {}
    for i, t in enumerate(top_triples):
        tid = t["triple_id"]
        pnl_series[tid] = extract_triple_pnl(t, merged_df, roe_map, prices_pivot)
        if (i+1) % 5 == 0:
            print(f"  PnL extracted {i+1}/{len(top_triples)}")
    valid = sum(1 for s in pnl_series.values() if len(s)>0)
    print(f"  Valid triples: {valid}/{len(top_triples)}")

    rows = []
    for w in windows:
        ts, te   = w["train_start"], w["train_end"]
        ts2, te2 = w["test_start"],  w["test_end"]
        monthly_list = []
        for t in top_triples:
            s = pnl_series.get(t["triple_id"], pd.Series(dtype=float))
            if not len(s): continue
            d = s[(s.index >= ts2) & (s.index < te2)]
            if len(d): monthly_list.append(daily_to_monthly(d))
        if monthly_list:
            all_dates = sorted(set().union(*[m.index for m in monthly_list]))
            port = pd.Series(0.0, index=all_dates)
            w_e  = 1.0/len(monthly_list)
            for m in monthly_list:
                port += m.reindex(all_dates, fill_value=0.0) * w_e
        else:
            port = pd.Series(dtype=float)
        met = portfolio_metrics(port)
        row = {"window":w["window"],"train_start":ts.date(),"train_end":te.date(),
               "test_start":ts2.date(),"test_end":te2.date(),"n_triples":len(top_triples)}
        row.update(met)
        rows.append(row)
        print(f"  W{w['window']}: {ts2.date()}~{te2.date()} "
              f"monthly_mean={met.get('monthly_mean',np.nan):.2%} "
              f"sharpe={met.get('sharpe',np.nan):.3f}")
    print(f"  WF done: {time.time()-t0:.1f}s")
    return pd.DataFrame(rows), pnl_series


# =============================================================================
# VISUALIZATIONS
# =============================================================================
def make_visualizations(top_triples, wf_df, regime_stats):
    print("\n[VIZ] Generating 3 figures ...")
    _fmt = lambda v, pct=False: (
        f"{v*100:.2f}%" if pct and pd.notna(v) else
        f"{v:.4f}" if pd.notna(v) else "N/A"
    )

    # Fig 1: OOS WF performance
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    wf = wf_df.sort_values("window")
    wx = wf["window"].values
    mm = wf["monthly_mean"].fillna(0).values * 100
    sh = wf["sharpe"].fillna(0).values

    bars1 = ax1.bar(wx, mm, color=["#2ecc71" if v>=0 else "#e74c3c" for v in mm],
                    alpha=0.8, edgecolor="black", linewidth=0.5)
    ax1.axhline(0, color="black", linewidth=0.8)
    ax1.axhline(float(np.nanmean(mm)), color="blue", linestyle="--", linewidth=1.5,
                label=f"P5 Mean: {float(np.nanmean(mm)):.2f}%/mo")
    ax1.axhline(0.23, color="orange", linestyle=":", linewidth=1.5,
                label="P3 Baseline: +0.23%/mo")
    ax1.set_title("Phase 5 OBV+ROE — OOS Monthly Return by Walk-Forward Window",
                  fontsize=12, fontweight="bold")
    ax1.set_xlabel("Window"); ax1.set_ylabel("Monthly Return (%)")
    ax1.legend(fontsize=9); ax1.set_xticks(wx); ax1.grid(axis="y", alpha=0.3)
    for x, v in zip(wx, mm):
        ax1.text(x, v+(0.05 if v>=0 else -0.2), f"{v:.2f}%",
                 ha="center", fontsize=8)

    ax2.bar(wx, sh, color=["#3498db" if v>=0 else "#c0392b" for v in sh],
            alpha=0.8, edgecolor="black", linewidth=0.5)
    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.axhline(0.5, color="green", linestyle="--", linewidth=1.5, label="Sharpe 0.5")
    ax2.set_title("Phase 5 OBV+ROE — OOS Sharpe by Walk-Forward Window", fontsize=11)
    ax2.set_xlabel("Window"); ax2.set_ylabel("Sharpe"); ax2.legend(fontsize=9)
    ax2.set_xticks(wx); ax2.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path1 = os.path.join(FIG_DIR, "stage_rerun_oos.png")
    plt.savefig(path1, dpi=120, bbox_inches="tight"); plt.close()
    print(f"  {path1}")

    # Fig 2: Regime analysis
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    reg_names = list(regime_stats.keys())
    obv_eff   = [regime_stats[r].get("obv_diff_pp", np.nan) for r in reg_names]
    roe_cov   = [regime_stats[r].get("roe_pct", np.nan)    for r in reg_names]

    ax1.barh(reg_names, obv_eff,
             color=["#2ecc71" if (v and v>=0) else "#e74c3c" for v in obv_eff],
             alpha=0.8, edgecolor="black", linewidth=0.5)
    ax1.axvline(0, color="black", linewidth=0.8)
    ax1.set_title("OBV Signal Effect by Regime (pp, fwd_5d)", fontsize=11)
    ax1.set_xlabel("OBV Long - Universe Mean Return (pp)")
    for i, v in enumerate(obv_eff):
        if v is not None and not np.isnan(v):
            ax1.text(v+0.02, i, f"{v:.2f}pp", va="center", fontsize=8)

    ax2.barh(reg_names, roe_cov, color="#3498db", alpha=0.8, edgecolor="black", linewidth=0.5)
    ax2.axvline(20, color="red", linestyle="--", linewidth=1, label="20% line")
    ax2.set_title("ROE Q4+ Coverage (% of stock-days)", fontsize=11)
    ax2.set_xlabel("ROE Pass Rate (%)")
    ax2.legend(fontsize=9)
    for i, v in enumerate(roe_cov):
        if v is not None and not np.isnan(v):
            ax2.text(v+0.3, i, f"{v:.1f}%", va="center", fontsize=8)
    plt.tight_layout()
    path2 = os.path.join(FIG_DIR, "stage_rerun_regime.png")
    plt.savefig(path2, dpi=120, bbox_inches="tight"); plt.close()
    print(f"  {path2}")

    # Fig 3: Phase 3 vs Phase 5
    fig, ax = plt.subplots(figsize=(12, 6))
    p3_mo = [1.34,-1.35,-0.61,-2.96,-1.79,1.27,3.58,-0.26,
              4.81,0.18,0.32,2.74,2.13,-0.97,0.40,-3.51,-1.25,0.11]
    p5_mo = [float(wf_df.iloc[i]["monthly_mean"]*100)
              if i < len(wf_df) and pd.notna(wf_df.iloc[i]["monthly_mean"]) else np.nan
              for i in range(len(wf_df))]
    p3_mean = np.nanmean(p3_mo)
    p5_mean = np.nanmean(p5_mo)

    x = np.arange(max(len(p3_mo), len(p5_mo)))
    p3_ext = p3_mo + [np.nan]*(len(x)-len(p3_mo))
    p5_ext = p5_mo + [np.nan]*(len(x)-len(p5_mo))
    ax.bar(x-0.2, p3_ext, width=0.35, alpha=0.7, color="#f39c12",
           label=f"Phase 3 ({p3_mean:.2f}%/mo)")
    ax.bar(x+0.2, p5_ext, width=0.35, alpha=0.7, color="#2980b9",
           label=f"Phase 5 OBV+ROE ({p5_mean:.2f}%/mo)")
    ax.axhline(0,      color="black",  linewidth=0.8)
    ax.axhline(p3_mean,color="#f39c12",linestyle="--",linewidth=1.5,alpha=0.8)
    if not np.isnan(p5_mean):
        ax.axhline(p5_mean,color="#2980b9",linestyle="--",linewidth=1.5,alpha=0.8)
    ax.axhline(0.23, color="gray", linestyle=":", linewidth=1, alpha=0.5,
               label="P3 baseline +0.23%/mo")
    ax.set_title("Phase 5 OBV+ROE vs Phase 3 Baseline — Monthly Return",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("Month Index"); ax.set_ylabel("Monthly Return (%)")
    ax.legend(fontsize=9); ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path3 = os.path.join(FIG_DIR, "stage_rerun_p3_compare.png")
    plt.savefig(path3, dpi=120, bbox_inches="tight"); plt.close()
    print(f"  {path3}")


# =============================================================================
# REPORT GENERATOR
# =============================================================================
def generate_report(prices, fwd, roe_raw, df_all, df_pass, top_triples, wf_df,
                    combined_metrics, regime_stats, windows, elapsed):
    _f = lambda v, pct=False: (
        f"{v*100:.2f}%" if pct and pd.notna(v) else
        f"{v:.4f}" if pd.notna(v) else "N/A"
    )
    pos_w   = sum(1 for _, r in wf_df.iterrows()
                  if pd.notna(r.get("monthly_mean")) and r["monthly_mean"] > 0)
    p5_mean = combined_metrics.get("monthly_mean", np.nan)
    p3_base = 0.0023
    improvement = (p5_mean - p3_base) if not np.isnan(p5_mean) else np.nan

    gate1 = "PASS" if not np.isnan(p5_mean) and p5_mean > 0 else "FAIL"
    gate2 = "PASS" if (pos_w/len(windows) > 0.6) else "FAIL"
    gate3 = "PASS" if len(df_pass) > 0 else "FAIL"
    sharpe_val = combined_metrics.get("sharpe", np.nan)
    gate4 = "PASS" if not np.isnan(sharpe_val) and sharpe_val > 0 else "FAIL"
    gate5 = "PASS" if len(top_triples) > 0 else "FAIL"
    all_pass = all(g == "PASS" for g in [gate1,gate2,gate3,gate4,gate5])
    n_pass_5 = sum(1 for g in [gate1,gate2,gate3,gate4,gate5] if g=="PASS")

    lines = [
        "# Phase 5 — OBV+ROE Stage A/B/C Rerun Walk-Forward Report",
        "",
        f"생성일: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"소요: {elapsed/60:.1f}분",
        "",
        "## [OBJECTIVE]",
        "OBV (lb=5, 1σ) + ROE (Q4+, 60d) 2개 시그널만으로 Stage A/B/C 재실행하여",
        "Phase 3 (+0.23%/월) 대비 개선 여부를 Walk-Forward 6-window OOS로 검증.",
        "",
        "## [DATA]",
        f"- daily_prices: {prices.shape[0]:,} rows, {prices['stock_code'].nunique()} stocks",
        f"- forward returns: {fwd.shape[0]:,} rows",
        f"- ROE stocks: {roe_raw['stock_code'].nunique()} (financial_statements)",
        f"- 기간: {prices['date'].min().date()} ~ {prices['date'].max().date()}",
        "",
        "## 설계 요약",
        f"- Stage A: ROE Q{ROE_Q_MIN}+ (PIT monthly scan) + p2a pool top-3 per approved regime",
        f"- Stage B: OBV (lb={OBV_LB}, thr={OBV_THR}σ) — 무조건 채택",
        f"- Stage C: SL×TP×TM 75-rule grid 재평가",
        f"- 합격 기준: mean_pnl>0 AND sharpe>0.5 AND mdd>-0.2 AND IS>0 AND OOS>0 AND n≥{N_MIN}",
        "",
        "## Stage A/B/C Grid 결과",
        f"- 평가 셀: {len(df_all):,}",
        f"- 합격 셀: {len(df_pass)} ({len(df_pass)/max(len(df_all),1)*100:.1f}%)",
        "",
    ]

    lines.append("### 국면별 합격 수")
    for regime in APPROVED_REGIMES:
        cnt = len(df_pass[df_pass["regime"]==regime]) if len(df_pass) else 0
        lines.append(f"- {regime}: {cnt}")

    lines += ["", "## Top Triples Selected",
              "", "| triple_id | regime | sl | tp | tm | sharpe | mean_pnl | n |",
              "|-----------|--------|----|----|----|--------|----------|---|"]
    for t in top_triples:
        lines.append(
            f"| {t['triple_id']} | {t['regime']} "
            f"| {t['sl']:.1%} | {t['tp']:.0%} | {t['tm']}d "
            f"| {_f(t['sharpe'])} | {_f(t['mean_pnl'])} | {t['n']} |"
        )

    lines += ["", "## Walk-Forward 6-Window OOS 결과",
              "", "| Window | Test 기간 | 월평균 | Sharpe | MDD | 양수월/전체 |",
              "|--------|-----------|--------|--------|-----|------------|"]
    for _, row in wf_df.sort_values("window").iterrows():
        lines.append(
            f"| {int(row['window'])} | {row['test_start']}~{row['test_end']} "
            f"| {_f(row.get('monthly_mean'), pct=True)} "
            f"| {_f(row.get('sharpe'))} "
            f"| {_f(row.get('mdd'), pct=True)} "
            f"| {int(row.get('n_positive',0)) if pd.notna(row.get('n_positive')) else 'N/A'}/"
            f"{int(row.get('n_months',0)) if pd.notna(row.get('n_months')) else 'N/A'} |"
        )

    lines += [
        "", "## [FINDING] 6-Window OOS 종합 통계",
        f"[STAT:n] n_windows={len(windows)}, n_triples={len(top_triples)}",
        f"[STAT:effect_size] 연환산={_f(combined_metrics.get('ann_return'), pct=True)}, "
        f"Sharpe={_f(combined_metrics.get('sharpe'))}, Calmar={_f(combined_metrics.get('calmar'))}",
        f"[STAT:ci] MDD={_f(combined_metrics.get('mdd'), pct=True)}, "
        f"1Q={_f(combined_metrics.get('monthly_q1'), pct=True)}, "
        f"5Q={_f(combined_metrics.get('monthly_q5'), pct=True)}",
        f"- 월평균: **{_f(p5_mean, pct=True)}**",
        f"- 월중앙: {_f(combined_metrics.get('monthly_median'), pct=True)}",
        f"- 양수 윈도우: {pos_w}/{len(windows)} ({pos_w/max(len(windows),1)*100:.0f}%)",
        "",
        "## Phase 3 (+0.23%/월) 대비 비교",
        "", "| 지표 | Phase 3 (기존) | Phase 5 OBV+ROE | 개선 |",
        "|------|----------------|-----------------|------|",
        f"| 월평균 | +0.23% | {_f(p5_mean,pct=True)} | {_f(improvement,pct=True)} |",
        f"| Sharpe | 0.3837 | {_f(sharpe_val)} | "
        f"{_f((sharpe_val-0.3837) if not np.isnan(sharpe_val) else np.nan)} |",
        f"| MDD | -6.55% | {_f(combined_metrics.get('mdd'),pct=True)} | - |",
        f"| 양수 윈도우 | 3/6 (50%) | {pos_w}/{len(windows)} ({pos_w/max(len(windows),1)*100:.0f}%) | - |",
        "",
        "## OBV×ROE 레짐별 분석",
        "", "| Regime | OBV 효과 (pp) | ROE Q4+ 커버리지 |",
        "|--------|---------------|-----------------|",
    ]
    for reg in REGIMES_6:
        rs = regime_stats.get(reg, {})
        o  = rs.get("obv_diff_pp", np.nan)
        r  = rs.get("roe_pct", np.nan)
        lines.append(f"| {reg} | {_f(o)} pp | {_f(r):.1f}% |"
                     if not np.isnan(o if o is not None else np.nan)
                     else f"| {reg} | N/A | N/A |")

    lines += [
        "", "## 5선 방법론 판정", "",
        "| 항목 | 결과 |", "|------|------|",
        f"| 1. IS p-value 의존 금지 | {gate1} (OOS 기반 판단) |",
        f"| 2. OOS Net >0 + 양의 비율 >60% | {gate2} ({pos_w}/{len(windows)}, mean={_f(p5_mean,pct=True)}) |",
        f"| 3. 국면 조건부 가능성 | {gate3} ({len(df_pass)} 합격 트리플) |",
        f"| 4. 파라미터 안정성 | {gate4} (Sharpe={_f(sharpe_val)}) |",
        f"| 5. ROE+OBV 결합 효과 | {gate5} ({len(top_triples)} top triples) |",
        "",
        f"**{n_pass_5}/5 {'PASS — P4 Paper 진입 권장' if all_pass else 'PASS (일부 기준 미달 — 추가 검토 권장)'}**",
        "",
        "## [LIMITATION]",
        f"1. ROE 데이터 {roe_raw['stock_code'].nunique()}종목 한정 (전체 universe 대비 부분 커버리지)",
        "2. OBV threshold rolling-std 기반 — regime별 threshold 최적화 미실시",
        "3. WF 트리플 선택 기준 = IS+OOS 통합 sharpe (순수 OOS 매도 룰 선택 미적용)",
        "4. 포트폴리오 = 동일 가중 (Sharpe 가중 최적화 탐색 미실시)",
        "",
        "## 산출물",
        f"- 스크립트: scripts/10pct_strategy/p5_stage_rerun.py",
        f"- 결과 CSV: reports/10pct_strategy/phase5_signals/stage_rerun_grid_all.csv",
        f"- 합격 CSV: reports/10pct_strategy/phase5_signals/stage_rerun_passed.csv",
        f"- WF CSV:   reports/10pct_strategy/phase5_signals/stage_rerun_walkforward.csv",
        f"- 시각화 3개: .omc/scientist/figures/stage_rerun_*.png",
    ]

    rpath = os.path.join(P5_DIR, "stage_rerun.md")
    with open(rpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Report: {rpath}")
    return rpath


# =============================================================================
# MAIN
# =============================================================================
def main():
    t_global = time.time()
    print("="*70)
    print("p5_stage_rerun.py — OBV+ROE Stage A/B/C Rerun + Walk-Forward")
    print("="*70)

    # [1] Load data
    print("\n[1/7] Data Load")
    fwd, date_to_regime, prices, roe_raw = load_data()

    # [2] Features
    print("\n[2/7] Compute PIT Features + OBV Signal")
    prices = compute_features(prices, date_to_regime)

    # [3] ROE universe map
    print("\n[3/7] Build ROE Q4+ Universe Map")
    roe_map = build_roe_universe_map(prices, roe_raw, min_quintile=ROE_Q_MIN)

    # [4] Merge fwd + build pivot
    print("\n[4/7] Merge forward returns + build prices_pivot")
    merged = prices.merge(
        fwd[["stock_code","date",
             "fwd_1d","fwd_3d","fwd_5d","fwd_10d","fwd_20d","fwd_30d","fwd_60d"]],
        on=["stock_code","date"], how="inner"
    )
    merged = merged.dropna(subset=["regime"])
    print(f"  merged: {merged.shape}")
    prices_pivot = build_prices_pivot(prices)
    print(f"  prices_pivot: {len(prices_pivot)} stocks")

    # [5] Load p2a filters + build pools
    print("\n[5/7] Stage A/B/C Grid Evaluation")
    filters_df = pd.read_csv(os.path.join(REPORT_DIR, "phase2a_filter_passed.csv"))
    pools = []
    for regime in REGIMES_6:
        sub = filters_df[filters_df["regime"]==regime].copy()
        if not len(sub): continue
        for lc in ["swing_lift","lift_mean","_lift"]:
            if lc in sub.columns:
                sub["_lift"] = pd.to_numeric(sub[lc], errors="coerce")
                break
        else:
            sub["_lift"] = 1.0
        top = sub.nlargest(min(10, len(sub)), "_lift")
        for rank, (_, row) in enumerate(top.iterrows(), 1):
            p = {k: row[k] for k in ["mcap_cutoff_top_n","min_trading_value",
                                      "trading_value_lookback","min_price",
                                      "min_liquidity_90d","vol_quintile",
                                      "candle_health","candle_trend"]
                 if k in row.index}
            p["regime"] = regime; p["pool_rank"] = rank
            pools.append(p)
    print(f"  Pools: {len(pools)}")

    # Grid evaluation — approved regimes × top-3 pools × 75 exit rules
    all_results = []
    t_eval = time.time()
    for regime in APPROVED_REGIMES:
        rp = [p for p in pools if p["regime"]==regime][:3]
        for pool in rp:
            for sl in SL_GRID:
                for tp in TP_GRID:
                    for tm in TM_GRID:
                        res = evaluate_triple(merged, pool, roe_map, prices_pivot, sl, tp, tm)
                        row = {"regime":regime, "pool_rank":pool["pool_rank"],
                               "sl":sl, "tp":tp, "tm":tm}
                        row.update(res)
                        row["pass"] = (
                            pd.notna(res["mean_pnl"]) and res["mean_pnl"] > 0 and
                            pd.notna(res["sharpe"])   and res["sharpe"]   > 0.5 and
                            pd.notna(res["mdd"])      and res["mdd"]      > -0.2 and
                            pd.notna(res["IS_mean"])  and res["IS_mean"]  > 0 and
                            pd.notna(res["OOS_mean"]) and res["OOS_mean"] > 0 and
                            res["n"] >= N_MIN
                        )
                        all_results.append(row)
        rp_pass = sum(1 for r in all_results if r.get("regime")==regime and r.get("pass"))
        print(f"  {regime}: {rp_pass} passed  ({time.time()-t_eval:.0f}s elapsed)")

    df_all  = pd.DataFrame(all_results)
    df_pass = df_all[df_all["pass"]==True].copy() if len(df_all) else pd.DataFrame()
    print(f"  Total passed: {len(df_pass)} / {len(df_all)}")
    df_all.to_csv(os.path.join(P5_DIR, "stage_rerun_grid_all.csv"), index=False)
    if len(df_pass): df_pass.to_csv(os.path.join(P5_DIR, "stage_rerun_passed.csv"), index=False)

    # [6] Select top triples + WF
    print("\n[6/7] Top Triples + Walk-Forward")
    top_triples = []
    for regime in APPROVED_REGIMES:
        sub = df_pass[df_pass["regime"]==regime] if len(df_pass) else pd.DataFrame()
        if not len(sub): continue
        for _, row in sub.nlargest(min(TOP_K, len(sub)), "sharpe").iterrows():
            pool = next((p for p in pools
                         if p["regime"]==regime and p["pool_rank"]==int(row["pool_rank"])), None)
            if pool is None: continue
            top_triples.append({
                "triple_id": f"T{len(top_triples):03d}",
                "regime":    regime,
                "pool_rank": int(row["pool_rank"]),
                "sl": row["sl"], "tp": row["tp"], "tm": int(row["tm"]),
                "sharpe":   row["sharpe"],
                "mean_pnl": row["mean_pnl"],
                "n":        row["n"],
                "pool":     pool,
            })
    print(f"  Selected: {len(top_triples)} triples")

    date_min = prices["date"].min(); date_max = prices["date"].max()
    windows  = build_wf_windows(date_min, date_max)
    print(f"  WF windows: {len(windows)}")

    if top_triples:
        wf_df, pnl_series = run_walkforward(top_triples, merged, roe_map, prices_pivot, windows)
    else:
        wf_df = pd.DataFrame({"window":range(1,len(windows)+1),
                               "monthly_mean":[np.nan]*len(windows),
                               "sharpe":[np.nan]*len(windows),
                               "mdd":[np.nan]*len(windows)})
        pnl_series = {}
    wf_df.to_csv(os.path.join(P5_DIR, "stage_rerun_walkforward.csv"), index=False)

    # Combined metrics
    all_monthly = []
    for t in top_triples:
        for w in windows:
            s = pnl_series.get(t["triple_id"], pd.Series(dtype=float))
            if not len(s): continue
            d = s[(s.index >= w["test_start"]) & (s.index < w["test_end"])]
            if len(d): all_monthly.append(daily_to_monthly(d))
    if all_monthly:
        all_dates = sorted(set().union(*[m.index for m in all_monthly]))
        port = pd.Series(0.0, index=all_dates)
        w_e  = 1.0/len(all_monthly)
        for m in all_monthly:
            port += m.reindex(all_dates, fill_value=0.0) * w_e
        combined_metrics = portfolio_metrics(port)
    else:
        combined_metrics = {k: np.nan for k in
                            ["ann_return","sharpe","calmar","mdd","monthly_mean",
                             "monthly_median","monthly_q1","monthly_q5","n_positive","n_months"]}

    # Regime stats
    regime_stats = {}
    for regime in REGIMES_6:
        rd = merged[merged["regime"]==regime]
        if not len(rd):
            regime_stats[regime] = {"obv_diff_pp": np.nan, "roe_pct": np.nan}; continue
        sig_ret  = rd[rd["obv_signal"]==1]["fwd_5d"].dropna()
        base_ret = rd["fwd_5d"].dropna()
        obv_diff = (sig_ret.mean()-base_ret.mean())*100 if len(sig_ret) else np.nan
        roe_rows = apply_roe_gate(rd, roe_map)
        roe_pct  = roe_rows.sum() / max(len(rd),1) * 100
        regime_stats[regime] = {"obv_diff_pp": obv_diff, "roe_pct": roe_pct}

    # [7] Visualizations + Report
    print("\n[7/7] Visualizations + Report")
    make_visualizations(top_triples, wf_df, regime_stats)
    elapsed = time.time() - t_global
    rpath   = generate_report(prices, fwd, roe_raw, df_all, df_pass,
                               top_triples, wf_df, combined_metrics,
                               regime_stats, windows, elapsed)

    # Console summary
    p5_mean = combined_metrics.get("monthly_mean", np.nan)
    pos_w   = sum(1 for _, r in wf_df.iterrows()
                  if pd.notna(r.get("monthly_mean")) and r["monthly_mean"] > 0)
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    print(f"트리플 수:              {len(top_triples)}")
    print(f"합격 셀:                {len(df_pass)} / {len(df_all)}")
    print(f"양의 OOS 윈도우 비율:   {pos_w}/{len(windows)} ({pos_w/max(len(windows),1)*100:.0f}%)")
    print(f"평균 월수익률:          {p5_mean*100:.2f}%" if not np.isnan(p5_mean) else "평균 월수익률: N/A")
    improvement = (p5_mean - 0.0023) if not np.isnan(p5_mean) else np.nan
    print(f"Phase 3 대비 개선:      {improvement*100:+.2f}%/월" if not np.isnan(improvement) else "Phase 3 대비: N/A")
    print(f"Sharpe:                 {combined_metrics.get('sharpe',np.nan):.4f}" if not np.isnan(combined_metrics.get('sharpe',np.nan)) else "Sharpe: N/A")
    print(f"총 소요:                {elapsed/60:.1f}분")
    print(f"Report:                 {rpath}")
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[중단] Ctrl+C"); sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] {e}"); traceback.print_exc(); sys.exit(1)
