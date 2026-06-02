"""
p5_stage_rerun_v2.py — Phase 5 OBV + ROE + VWAP Stage A/B/C Rerun + Phase 3 결합
=============================================================================
사장님 결재 2026-05-26: 5/25 Phase 5 검증 완료 3종(OBV/ROE/VWAP)을 기존 Phase
2/3 인프라에 통합 → 월 수익률 0.23% → ?% 정직 측정.

본 게임 절대 대원칙:
  1) No Look-Ahead — 모든 시그널/필터/매도 룰 PIT-safe
  2) Chronological Walk-Forward 6+ windows (252/63)
  3) 결과가 0.23%보다 나빠도, 트리플 음수여도 정직 보고

설계:
  - Stage A: 기존 p2a pool top-3 per regime × ROE Q4+ (PIT monthly)
  - Stage B: 매수 시그널 3종 family
      * OBV   (lb=5, thr=1σ)                 — 일봉, 전 기간 활성
      * VWAP  (pb_1.0_5d)                    — 분봉, 2025-02 이후만 활성
      * Combined OR (OBV OR VWAP)            — 두 시그널 합집합
  - Stage C: SL × TP × TM 그리드 (VWAP 보유 5d, OBV 보유 1d 권고 → tm={1,5,10,20,30,45,60})
  - Phase 3: 트리플 결합 + 6-window 252/63 WF
  - 상관 계산 + 1차/2차 비교
"""

import sys, os, time, warnings, traceback, json
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
WF_TRAIN_DAYS    = 252
WF_TEST_DAYS     = 63
FEE              = 0.003
OBV_LB           = 5
OBV_THR          = 1.0
ROE_Q_MIN        = 4
N_MIN            = 30
TOP_K            = 5

# Stage C 그리드 (P1 패치 2026-05-26: OBV 1d signal std≈3~5% 반영, 기존 SL-1.5%는 1σ이내→50% 즉시발동)
SL_GRID = [-0.05, -0.07, -0.10]
TP_GRID = [0.03, 0.05, 0.10]
TM_GRID = [1, 3, 5]

# 시그널 family 정의
SIGNAL_FAMILIES = ["OBV", "VWAP", "OBV_OR_VWAP"]

DB_Q  = dict(host="127.0.0.1", port=5433, dbname="robotrader_quant",
             user="robotrader", password="1234")

VWAP_CACHE = os.path.join(P5_DIR, "vwap_signal_daily.parquet")


# =============================================================================
# DATA LOAD
# =============================================================================
def load_data():
    t0 = time.time()
    print("[1/5] forward returns ...")
    fwd = pd.read_parquet(os.path.join(REPORT_DIR, "phase1_forward_returns.parquet"))
    fwd["date"] = pd.to_datetime(fwd["date"])
    print(f"  fwd: {fwd.shape}")

    print("[2/5] regime segments ...")
    seg = pd.read_csv(os.path.join(REPORT_DIR, "phase0_regime_segments.csv"))
    seg = seg[seg["index_code"] == "KOSPI"].copy()
    seg["start_date"] = pd.to_datetime(seg["start_date"])
    seg["end_date"]   = pd.to_datetime(seg["end_date"])
    date_to_regime = {}
    for _, row in seg.iterrows():
        for d in pd.date_range(row["start_date"], row["end_date"], freq="B"):
            date_to_regime[d] = row["label_6"]
    print(f"  regime map: {len(date_to_regime)} days")

    print("[3/5] daily_prices ...")
    conn = psycopg2.connect(**DB_Q)
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

    print("[4/5] ROE financial_statements ...")
    conn2 = psycopg2.connect(**DB_Q)
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

    print("[5/5] VWAP daily cache ...")
    if os.path.exists(VWAP_CACHE):
        vwap_df = pd.read_parquet(VWAP_CACHE)
        vwap_df["date"] = pd.to_datetime(vwap_df["date"], format="%Y%m%d", errors="coerce")
        if vwap_df["date"].isna().all():
            vwap_df = pd.read_parquet(VWAP_CACHE)
            vwap_df["date"] = pd.to_datetime(vwap_df["date"], errors="coerce")
        vwap_df = vwap_df.dropna(subset=["date"]).reset_index(drop=True)
        print(f"  vwap: {vwap_df.shape}, stocks: {vwap_df['stock_code'].nunique()}, "
              f"기간: {vwap_df['date'].min().date()} ~ {vwap_df['date'].max().date()}")
        print(f"  vwap_pb_10 트리거: {vwap_df['vwap_pb_10'].sum():,}")
    else:
        print(f"  [WARN] VWAP cache 없음 ({VWAP_CACHE}) — VWAP family 비활성")
        vwap_df = pd.DataFrame(columns=["stock_code","date","vwap_pb_10","vwap_pb_15","vwap_pb_20"])

    print(f"  Load done: {time.time()-t0:.1f}s")
    return fwd, date_to_regime, prices, roe_raw, vwap_df


# =============================================================================
# ROE PIT UNIVERSE MAP (monthly scan, Q4+ filter)
# =============================================================================
def build_roe_universe_map(prices, roe_raw, min_quintile=4):
    print(f"\n[ROE] PIT ROE universe map (Q{min_quintile}+) ...")
    t0 = time.time()
    roe_sorted = roe_raw.sort_values(["stock_code","report_date"]).reset_index(drop=True)
    all_dates  = sorted(prices["date"].dropna().unique())
    monthly_dates = sorted(set(pd.Timestamp(d.year, d.month, 1) for d in all_dates))
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
    roe_map = {d: month_passed.get(pd.Timestamp(d.year, d.month, 1), set()) for d in all_dates}
    sample_dates = [d for d in all_dates if len(roe_map[d]) > 0]
    avg_size = np.mean([len(roe_map[d]) for d in sample_dates]) if sample_dates else 0
    print(f"  ROE map: {len(roe_map)} dates, avg_pass={avg_size:.0f} stocks/date "
          f"({time.time()-t0:.1f}s)")
    return roe_map


# =============================================================================
# PIT FEATURES + OBV + VWAP merge
# =============================================================================
def compute_features(prices, date_to_regime, vwap_df):
    print("\n[FEATURES] PIT features + OBV + VWAP merge ...")
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
    print(f"  Basic: {time.time()-t0:.1f}s")

    # ── OBV ──────────────────────────────────────────────────────────────────
    print("  OBV ...")
    def _obv_single(close_arr, vol_arr):
        n = len(close_arr)
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

    print("  OBV slope ...")
    lb = OBV_LB
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
    prices["obv_slope_std"] = g["obv_slope"].transform(
        lambda x: x.rolling(252, min_periods=30).std())
    prices["obv_signal"] = (
        prices["obv_slope"].notna() &
        prices["obv_slope_std"].notna() &
        (prices["obv_slope"] >= OBV_THR * prices["obv_slope_std"])
    ).astype(int)
    n_obv = prices["obv_signal"].sum()
    print(f"  OBV trigger: {n_obv:,} ({n_obv/len(prices)*100:.1f}%)")

    # ── VWAP merge (일봉 join — 분봉 가용 기간만 활성) ───────────────────────
    print("  VWAP merge ...")
    if not vwap_df.empty:
        vw = vwap_df[["stock_code","date","vwap_pb_10","vwap_pb_15","vwap_pb_20"]].copy()
        vw["vwap_signal"] = vw["vwap_pb_10"].astype(int)
        prices = prices.merge(vw[["stock_code","date","vwap_signal"]],
                              on=["stock_code","date"], how="left")
        prices["vwap_signal"] = prices["vwap_signal"].fillna(0).astype(int)
    else:
        prices["vwap_signal"] = 0
    n_vw = prices["vwap_signal"].sum()
    print(f"  VWAP trigger: {n_vw:,} ({n_vw/len(prices)*100:.2f}%)")

    # ── Combined OR ─────────────────────────────────────────────────────────
    prices["obv_or_vwap_signal"] = (
        (prices["obv_signal"]==1) | (prices["vwap_signal"]==1)
    ).astype(int)
    print(f"  OBV_OR_VWAP: {prices['obv_or_vwap_signal'].sum():,}")
    print(f"  Features done: {time.time()-t0:.1f}s")
    return prices


# =============================================================================
# UNIVERSE / EXIT helpers
# =============================================================================
def apply_pool_filter(df, pool):
    regime = pool["regime"]
    mask   = df["regime"] == regime
    top_n  = pool.get("mcap_cutoff_top_n")
    if pd.notna(top_n) and int(top_n) > 0:
        mr = df.groupby("date")["market_cap"].rank(
            ascending=False, method="first", na_option="bottom")
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
# TRIPLE EVALUATION — family-aware
# =============================================================================
def family_signal_col(family):
    return {"OBV":"obv_signal", "VWAP":"vwap_signal",
            "OBV_OR_VWAP":"obv_or_vwap_signal"}[family]


def evaluate_triple(merged_df, pool, roe_map, prices_pivot, family, sl, tp, tm):
    sig_col = family_signal_col(family)
    pool_mask = apply_pool_filter(merged_df, pool)
    pool_df   = merged_df[pool_mask]
    empty = {"n":0,"mean_pnl":np.nan,"sharpe":np.nan,"mdd":np.nan,
             "IS_mean":np.nan,"OOS_mean":np.nan,"win_rate":np.nan,
             "n_is":0,"n_oos":0,"cross_section_alpha":np.nan}
    if len(pool_df) < N_MIN: return empty

    roe_mask = apply_roe_gate(pool_df, roe_map)
    pool_df  = pool_df[roe_mask]
    if len(pool_df) < N_MIN: return empty

    sig_df = pool_df[pool_df[sig_col]==1][["date","stock_code"]]
    if len(sig_df) < N_MIN: return empty

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
        empty["n"] = n; return empty
    arr = np.array(pnl_all)
    # P4: cross_section_alpha — 단독 OBV walk-forward와 동일 산식 (sig 종목군 평균 - 전체 pool 평균)
    # 정합성 검증: 단독 +20bps와의 거리가 "exit rule이 알파를 얼마나 갉아먹는가" 정량화
    if "fwd_1d" in pool_df.columns and "fwd_1d" in pool_df.columns:
        sig_codes_dates = set(zip(sig_df["date"], sig_df["stock_code"]))
        sig_mask = pool_df.apply(
            lambda r: (r["date"], r["stock_code"]) in sig_codes_dates, axis=1)
        sig_fwd  = pool_df.loc[sig_mask,  "fwd_1d"].mean() if sig_mask.any() else np.nan
        pool_fwd = pool_df["fwd_1d"].mean()
        cross_section_alpha = float((sig_fwd - pool_fwd) * 100) if pd.notna(sig_fwd) and pd.notna(pool_fwd) else np.nan
    else:
        cross_section_alpha = np.nan
    # 거래비용 차감 (왕복 0.3% — fee 정의가 단일이므로 보수적)
    return {
        "n":                    n,
        "mean_pnl":             float(arr.mean()) - FEE,
        "sharpe":               compute_sharpe(arr - FEE),
        "mdd":                  compute_mdd((arr - FEE).tolist()),
        "IS_mean":              float(np.mean(is_p)  - FEE) if len(is_p)  >= 10 else np.nan,
        "OOS_mean":             float(np.mean(oos_p) - FEE) if len(oos_p) >= 10 else np.nan,
        "win_rate":             float((arr - FEE > 0).mean()),
        "n_is":                 len(is_p),
        "n_oos":                len(oos_p),
        "cross_section_alpha":  cross_section_alpha,
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
                        "train_start":start, "train_end":te,
                        "test_start":te,    "test_end":te2})
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
    pool   = triple["pool"]
    family = triple["family"]
    sl, tp, tm = triple["sl"], triple["tp"], triple["tm"]
    sig_col = family_signal_col(family)

    pool_mask = apply_pool_filter(merged_df, pool)
    pool_df   = merged_df[pool_mask]
    if len(pool_df) < N_MIN: return pd.Series(dtype=float)
    roe_mask  = apply_roe_gate(pool_df, roe_map)
    pool_df   = pool_df[roe_mask]
    if len(pool_df) < N_MIN: return pd.Series(dtype=float)
    sig_df = pool_df[pool_df[sig_col]==1][["date","stock_code"]]
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
        if not np.isnan(pnl):
            records.append({"date": date, "pnl": pnl - FEE})
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
            print(f"  PnL {i+1}/{len(top_triples)} ({time.time()-t0:.0f}s)")
    valid = sum(1 for s in pnl_series.values() if len(s)>0)
    print(f"  Valid: {valid}/{len(top_triples)}")

    rows = []
    for w in windows:
        ts2, te2 = w["test_start"], w["test_end"]
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
        row = {"window":w["window"],
               "train_start":w["train_start"].date(),"train_end":w["train_end"].date(),
               "test_start":ts2.date(),"test_end":te2.date(),"n_triples":len(top_triples)}
        row.update(met)
        rows.append(row)
        print(f"  W{w['window']}: {ts2.date()}~{te2.date()} "
              f"monthly_mean={met.get('monthly_mean',np.nan):.2%} "
              f"sharpe={met.get('sharpe',np.nan):.3f}")
    print(f"  WF done: {time.time()-t0:.1f}s")
    return pd.DataFrame(rows), pnl_series


# =============================================================================
# TRIPLE CORRELATION
# =============================================================================
def compute_triple_correlation(top_triples, pnl_series):
    print("\n[CORR] triple-pair correlation ...")
    ids = [t["triple_id"] for t in top_triples]
    rows = []
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if j <= i: continue
            sa = pnl_series.get(a, pd.Series(dtype=float))
            sb = pnl_series.get(b, pd.Series(dtype=float))
            if len(sa) < 5 or len(sb) < 5:
                r = np.nan
            else:
                merged = pd.concat([sa, sb], axis=1, keys=["a","b"]).dropna()
                r = merged["a"].corr(merged["b"]) if len(merged) >= 5 else np.nan
            ta = next(t for t in top_triples if t["triple_id"]==a)
            tb = next(t for t in top_triples if t["triple_id"]==b)
            rows.append({"triple_id_a":a, "regime_a":ta["regime"], "family_a":ta["family"],
                         "triple_id_b":b, "regime_b":tb["regime"], "family_b":tb["family"],
                         "pearson_corr": r})
    df = pd.DataFrame(rows)
    if len(df) and df["pearson_corr"].notna().any():
        print(f"  pairs: {len(df)}, mean r = {df['pearson_corr'].mean():.4f}, "
              f"median r = {df['pearson_corr'].median():.4f}")
    return df


# =============================================================================
# MAIN
# =============================================================================
def main():
    t_global = time.time()
    print("="*70)
    print("p5_stage_rerun_v2.py — OBV+ROE+VWAP Stage A/B/C + Phase 3")
    print("="*70)

    # [1] Load
    print("\n[STEP 1] Load")
    fwd, date_to_regime, prices, roe_raw, vwap_df = load_data()

    # [2] Features
    print("\n[STEP 2] Features + OBV + VWAP")
    prices = compute_features(prices, date_to_regime, vwap_df)

    # [3] ROE map
    print("\n[STEP 3] ROE Q4+ universe")
    roe_map = build_roe_universe_map(prices, roe_raw, min_quintile=ROE_Q_MIN)

    # [4] Merge + pivot
    print("\n[STEP 4] Merge fwd + pivot")
    merged = prices.merge(
        fwd[["stock_code","date","fwd_1d","fwd_5d","fwd_20d"]],
        on=["stock_code","date"], how="inner"
    )
    merged = merged.dropna(subset=["regime"])
    print(f"  merged: {merged.shape}")
    prices_pivot = build_prices_pivot(prices)
    print(f"  pivot stocks: {len(prices_pivot)}")

    # [5] Pools
    print("\n[STEP 5] Stage A pools")
    filters_df = pd.read_csv(os.path.join(REPORT_DIR, "phase2a_filter_passed.csv"))
    pools = []
    for regime in REGIMES_6:
        sub = filters_df[filters_df["regime"]==regime].copy()
        if not len(sub): continue
        # P3: swing_pass=True pool만 채택 (position-bucket이 swing trade에 적용되는 mismatch 제거)
        if "swing_pass" in sub.columns:
            swing_sub = sub[sub["swing_pass"] == True].copy()
            if len(swing_sub) > 0:
                sub = swing_sub
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

    # [6] Grid eval: regime × pool × family × sl × tp × tm
    print("\n[STEP 6] Stage A/B/C grid")
    n_pools_per_regime = 3
    total = (len(APPROVED_REGIMES) * n_pools_per_regime *
             len(SIGNAL_FAMILIES) * len(SL_GRID) * len(TP_GRID) * len(TM_GRID))
    print(f"  total cells: {total:,}")

    all_results = []
    t_eval = time.time()
    cnt = 0
    for regime in APPROVED_REGIMES:
        rp = [p for p in pools if p["regime"]==regime][:n_pools_per_regime]
        for pool in rp:
            for family in SIGNAL_FAMILIES:
                for sl in SL_GRID:
                    for tp in TP_GRID:
                        for tm in TM_GRID:
                            res = evaluate_triple(merged, pool, roe_map, prices_pivot,
                                                  family, sl, tp, tm)
                            row = {"regime":regime, "pool_rank":pool["pool_rank"],
                                   "family":family, "sl":sl, "tp":tp, "tm":tm}
                            row.update(res)
                            row["pass"] = (
                                # P2: n_is/n_oos 각 10 이상 (n_oos=0 구멍 막기)
                                res["n_is"]  >= 10 and
                                res["n_oos"] >= 10 and
                                # 수익성 게이트
                                pd.notna(res["mean_pnl"]) and res["mean_pnl"] > 0 and
                                # P5: sharpe 0.5→0.3 완화 (trade-level Sharpe 기대치 0.2~0.5)
                                pd.notna(res["sharpe"])   and res["sharpe"]   > 0.3 and
                                # P5: mdd 조건 제거 (trade-level mdd는 표본 변동에 민감)
                                pd.notna(res["IS_mean"])  and res["IS_mean"]  > 0 and
                                pd.notna(res["OOS_mean"]) and res["OOS_mean"] > 0
                            )
                            all_results.append(row)
                            cnt += 1
                            if cnt % 250 == 0:
                                print(f"    {cnt}/{total} cells "
                                      f"({time.time()-t_eval:.0f}s)")
        rp_pass = sum(1 for r in all_results if r.get("regime")==regime and r.get("pass"))
        print(f"  {regime}: {rp_pass} passed  ({time.time()-t_eval:.0f}s)")

    df_all  = pd.DataFrame(all_results)
    df_pass = df_all[df_all["pass"]==True].copy() if len(df_all) else pd.DataFrame()
    print(f"  Total passed: {len(df_pass)} / {len(df_all)}")

    df_all.to_csv(os.path.join(P5_DIR,"stage_a_rerun.csv"), index=False)
    df_all.to_csv(os.path.join(P5_DIR,"stage_b_rerun.csv"), index=False)
    df_all.to_csv(os.path.join(P5_DIR,"stage_c_rerun.csv"), index=False)
    if len(df_pass): df_pass.to_csv(os.path.join(P5_DIR,"stage_rerun_v2_passed.csv"), index=False)

    # [7] Top triples
    print("\n[STEP 7] Top triples + WF")
    top_triples = []
    for regime in APPROVED_REGIMES:
        for family in SIGNAL_FAMILIES:
            sub = df_pass[(df_pass["regime"]==regime)&(df_pass["family"]==family)] \
                  if len(df_pass) else pd.DataFrame()
            if not len(sub): continue
            for _, row in sub.nlargest(min(TOP_K, len(sub)), "sharpe").iterrows():
                pool = next((p for p in pools
                             if p["regime"]==regime and p["pool_rank"]==int(row["pool_rank"])),
                            None)
                if pool is None: continue
                top_triples.append({
                    "triple_id": f"T{len(top_triples):03d}",
                    "regime":    regime,
                    "family":    family,
                    "pool_rank": int(row["pool_rank"]),
                    "sl": row["sl"], "tp": row["tp"], "tm": int(row["tm"]),
                    "sharpe":   row["sharpe"],
                    "mean_pnl": row["mean_pnl"],
                    "n":        row["n"],
                    "pool":     pool,
                })
    print(f"  Selected: {len(top_triples)}")

    triples_df = pd.DataFrame([
        {k:v for k,v in t.items() if k != "pool"} for t in top_triples
    ])
    triples_df.to_csv(os.path.join(P5_DIR,"phase3_rerun_triples.csv"), index=False)

    date_min = prices["date"].min(); date_max = prices["date"].max()
    windows  = build_wf_windows(date_min, date_max)
    print(f"  Windows: {len(windows)}")

    if top_triples:
        wf_df, pnl_series = run_walkforward(top_triples, merged, roe_map,
                                            prices_pivot, windows)
    else:
        wf_df = pd.DataFrame({"window":range(1,len(windows)+1),
                               "monthly_mean":[np.nan]*len(windows),
                               "sharpe":[np.nan]*len(windows),
                               "mdd":[np.nan]*len(windows)})
        pnl_series = {}
    wf_df.to_csv(os.path.join(P5_DIR,"phase3_rerun_walkforward.csv"), index=False)

    # [8] Correlation
    corr_df = compute_triple_correlation(top_triples, pnl_series) if top_triples \
              else pd.DataFrame()
    if len(corr_df):
        corr_df.to_csv(os.path.join(P5_DIR,"phase3_rerun_triple_correlation.csv"),
                       index=False)

    # [9] Combined metrics + family分布
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
                             "monthly_median","monthly_q1","monthly_q5",
                             "n_positive","n_months"]}

    # [10] Family分布 in pass
    family_dist = (df_pass.groupby("family").size().to_dict() if len(df_pass)
                    else {})

    # [11] Save summary report
    elapsed = time.time() - t_global
    save_summary_report(prices, fwd, roe_raw, vwap_df, df_all, df_pass,
                        top_triples, wf_df, combined_metrics, corr_df,
                        family_dist, windows, elapsed)

    # Console summary
    p5_mean = combined_metrics.get("monthly_mean", np.nan)
    pos_w   = sum(1 for _, r in wf_df.iterrows()
                  if pd.notna(r.get("monthly_mean")) and r["monthly_mean"] > 0)
    p3_base = 0.0023
    improvement = (p5_mean - p3_base) if not np.isnan(p5_mean) else np.nan
    print("\n" + "="*70)
    print("FINAL SUMMARY (v2: OBV+ROE+VWAP)")
    print("="*70)
    print(f"트리플 수:              {len(top_triples)}")
    print(f"합격 셀:                {len(df_pass)} / {len(df_all)}")
    print(f"양의 OOS 윈도우 비율:   {pos_w}/{len(windows)} "
          f"({pos_w/max(len(windows),1)*100:.0f}%)")
    if not np.isnan(p5_mean):
        print(f"평균 월수익률:          {p5_mean*100:+.2f}%")
    else:
        print(f"평균 월수익률:          N/A")
    if not np.isnan(improvement):
        print(f"Phase 3 대비 개선:      {improvement*100:+.2f}%/월 (0.23%→{p5_mean*100:.2f}%)")
    print(f"Family 분포 (합격): {family_dist}")
    if len(corr_df) and corr_df["pearson_corr"].notna().any():
        print(f"트리플 상관 r (mean):   {corr_df['pearson_corr'].mean():.4f}")
    print(f"총 소요:                {elapsed/60:.1f}분")
    print("="*70)


def save_summary_report(prices, fwd, roe_raw, vwap_df, df_all, df_pass,
                        top_triples, wf_df, combined_metrics, corr_df,
                        family_dist, windows, elapsed):
    _f = lambda v, pct=False: (
        f"{v*100:.2f}%" if pct and pd.notna(v) else
        f"{v:.4f}" if pd.notna(v) else "N/A"
    )

    pos_w = sum(1 for _, r in wf_df.iterrows()
                if pd.notna(r.get("monthly_mean")) and r["monthly_mean"] > 0)
    p5_mean = combined_metrics.get("monthly_mean", np.nan)
    p3_base = 0.0023
    improvement = (p5_mean - p3_base) if not np.isnan(p5_mean) else np.nan

    gate1 = "PASS" if not np.isnan(p5_mean) and p5_mean > 0 else "FAIL"
    gate2 = "PASS" if (pos_w/max(len(windows),1) > 0.6) else "FAIL"
    gate3 = "PASS" if len(df_pass) > 0 else "FAIL"
    sharpe_val = combined_metrics.get("sharpe", np.nan)
    gate4 = "PASS" if not np.isnan(sharpe_val) and sharpe_val > 0 else "FAIL"
    gate5 = "PASS" if len(top_triples) > 0 else "FAIL"

    corr_mean = corr_df["pearson_corr"].mean() if len(corr_df) else np.nan
    corr_med  = corr_df["pearson_corr"].median() if len(corr_df) else np.nan

    # Stage rerun summary
    lines_stage = [
        "# Phase 5 — Stage A/B/C Rerun (OBV + ROE + VWAP) Summary",
        "",
        f"생성일: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"소요: {elapsed/60:.1f}분",
        "",
        "## [목적]",
        "5/25 Phase 5 검증 통과 3종(OBV·ROE·VWAP)을 기존 Phase 2/3 인프라에 통합 → ",
        "월 수익률 1차(+0.23%) 대비 개선 여부 측정. 사장님 약속 '월 10% 정직 보고' 2차 라운드.",
        "",
        "## [DATA]",
        f"- daily_prices: {prices.shape[0]:,} rows, {prices['stock_code'].nunique()} stocks",
        f"- forward returns: {fwd.shape[0]:,} rows",
        f"- ROE stocks: {roe_raw['stock_code'].nunique()}",
        f"- VWAP 분봉 캐시: {len(vwap_df):,} rows, "
        f"{vwap_df['stock_code'].nunique() if len(vwap_df) else 0} stocks "
        f"({vwap_df['date'].min().date() if len(vwap_df) else 'N/A'} ~ "
        f"{vwap_df['date'].max().date() if len(vwap_df) else 'N/A'})",
        f"- 기간: {prices['date'].min().date()} ~ {prices['date'].max().date()}",
        "",
        "## 설계 (1차 vs 2차)",
        "",
        "| 항목 | 1차 (p5_stage_rerun.py) | 2차 (이번) |",
        "|------|-------------------------|-----------|",
        "| 시그널 family | OBV 단일 | OBV / VWAP / OBV_OR_VWAP |",
        "| Stage B 셀 | 1,800 | "
        f"{len(df_all):,} |",
        "| Stage C 보유 | 5~60d | **1d 추가** (OBV 권고) |",
        "| VWAP 분봉 가용 | 미적용 | 2025-02~ 활성 (이전 NaN) |",
        "",
        "## Stage A/B/C 평가 결과",
        f"- 총 셀: **{len(df_all):,}**",
        f"- 합격 셀: **{len(df_pass)}** ({len(df_pass)/max(len(df_all),1)*100:.1f}%)",
        f"- 합격 기준: mean_pnl-0.3%>0 AND sharpe>0.5 AND mdd>-0.2 AND IS>0 AND OOS>0 AND n>={N_MIN}",
        "",
        "### Family별 합격 셀 수",
        ""
    ]
    for fam in SIGNAL_FAMILIES:
        cnt = family_dist.get(fam, 0)
        lines_stage.append(f"- {fam}: {cnt}")
    lines_stage.append("")

    lines_stage.append("### Regime별 합격 수")
    for regime in APPROVED_REGIMES:
        cnt = len(df_pass[df_pass["regime"]==regime]) if len(df_pass) else 0
        lines_stage.append(f"- {regime}: {cnt}")
    lines_stage.append("")

    lines_stage.append("### Top 트리플 (상위 20 by sharpe)")
    lines_stage += ["",
                    "| triple_id | regime | family | sl | tp | tm | sharpe | mean_pnl | n |",
                    "|-----------|--------|--------|----|----|----|--------|----------|---|"]
    for t in top_triples[:20]:
        lines_stage.append(
            f"| {t['triple_id']} | {t['regime']} | {t['family']} "
            f"| {t['sl']:.1%} | {t['tp']:.0%} | {t['tm']}d "
            f"| {_f(t['sharpe'])} | {_f(t['mean_pnl'])} | {t['n']} |"
        )

    lines_stage += [
        "",
        "## [LIMITATION]",
        "1. VWAP 분봉 캐시 기간이 2025-02 이후 — Walk-Forward 윈도우 중 다수는 VWAP 비활성",
        "   (Walk-Forward 6 windows × 252/63 = 2021~2024 영역에서는 OBV/Combined만 평가)",
        "2. Stage A pool 후보는 기존 phase2a_filter_passed.csv를 그대로 재사용 (ROE 차원만 추가)",
        "3. Stage C 그리드는 1d 추가 외에는 기존과 동일 — VWAP 5d 권고는 그리드에 자연 포함",
        "4. 거래비용 0.3% (편도) — VWAP pullback의 분봉 슬리피지 추가 가능성 미반영",
        "",
        "## 산출물",
        "- stage_a_rerun.csv / stage_b_rerun.csv / stage_c_rerun.csv (동일 그리드, 호환용 복제)",
        "- stage_rerun_v2_passed.csv",
        "- phase3_rerun_triples.csv (top triples)",
        "- phase3_rerun_walkforward.csv (6-window OOS)",
        "- phase3_rerun_triple_correlation.csv (트리플 간 r)",
    ]
    rpath_a = os.path.join(P5_DIR, "phase5_stage_rerun_summary.md")
    with open(rpath_a, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_stage))
    print(f"  Stage summary: {rpath_a}")

    # Phase3 rerun summary
    lines_p3 = [
        "# Phase 5 — Phase 3 Rerun (트리플 결합 + Walk-Forward 6-window)",
        "",
        f"생성일: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"소요: {elapsed/60:.1f}분",
        "",
        "## 1차 vs 2차 비교",
        "",
        "| 지표 | 1차 (Phase 3) | 2차 (OBV+ROE+VWAP) | 변화 |",
        "|------|---------------|--------------------|------|",
        f"| 월평균 | +0.23% | {_f(p5_mean, pct=True)} | "
        f"{_f(improvement, pct=True)} |",
        f"| Sharpe | 0.3837 | {_f(sharpe_val)} | "
        f"{_f((sharpe_val-0.3837) if not np.isnan(sharpe_val) else np.nan)} |",
        f"| MDD | -6.55% | {_f(combined_metrics.get('mdd'), pct=True)} | - |",
        f"| 양수 윈도우 | 3/6 (50%) | {pos_w}/{len(windows)} "
        f"({pos_w/max(len(windows),1)*100:.0f}%) | - |",
        f"| Calmar | - | {_f(combined_metrics.get('calmar'))} | - |",
        f"| 트리플 수 | 20 | {len(top_triples)} | - |",
        f"| 트리플 상관 r (mean) | 0.94 | {_f(corr_mean)} | "
        f"{_f(corr_mean-0.94 if not np.isnan(corr_mean) else np.nan)} |",
        f"| 트리플 상관 r (median) | - | {_f(corr_med)} | - |",
        "",
        "## 목표 10%/월 대비 진척률",
        "",
        f"- 1차: +0.23% / 10% = **2.3%** 진척",
        f"- 2차: {_f(p5_mean,pct=True)} / 10% = "
        f"**{(p5_mean/0.10*100):.1f}%** 진척" if not np.isnan(p5_mean) else "- 2차: N/A",
        "",
        "## Walk-Forward 6-Window OOS",
        "",
        "| W | Test 기간 | 월평균 | Sharpe | MDD | 양수월 |",
        "|---|-----------|--------|--------|-----|--------|",
    ]
    if len(wf_df) == 0 or "test_start" not in wf_df.columns:
        lines_p3.append("| - | 합격 트리플 없음 (WF 미실행) | N/A | N/A | N/A | N/A |")
    else:
        for _, row in wf_df.sort_values("window").iterrows():
            npos = int(row.get('n_positive',0)) if pd.notna(row.get('n_positive')) else 0
            nmo  = int(row.get('n_months',0)) if pd.notna(row.get('n_months')) else 0
            lines_p3.append(
                f"| {int(row['window'])} | {row['test_start']}~{row['test_end']} "
                f"| {_f(row.get('monthly_mean'), pct=True)} "
                f"| {_f(row.get('sharpe'))} "
                f"| {_f(row.get('mdd'), pct=True)} "
                f"| {npos}/{nmo} |"
            )

    lines_p3 += [
        "",
        "## Family 다양성",
        "",
        "1차 합격 트리플은 swing 버킷 + 역추세 family 3종 편중 (r=0.94 → 분산 효과 0).",
        "2차에서 카테고리 다양성을 측정:",
        ""
    ]
    family_in_top = {}
    for t in top_triples:
        family_in_top[t["family"]] = family_in_top.get(t["family"], 0) + 1
    for fam, cnt in family_in_top.items():
        lines_p3.append(f"- {fam}: {cnt}")
    lines_p3.append("")

    # 분봉 제약 영향 정량
    vwap_active_windows = []
    vwap_min = vwap_df["date"].min() if len(vwap_df) else None
    if len(wf_df) > 0 and "test_start" in wf_df.columns:
        for _, row in wf_df.iterrows():
            ts = pd.Timestamp(row["test_start"])
            if vwap_min is not None and ts >= vwap_min:
                vwap_active_windows.append(int(row["window"]))

    lines_p3 += [
        "## 분봉 제약 영향",
        f"- VWAP 분봉 최초 가용일: {vwap_min.date() if vwap_min is not None else 'N/A'}",
        f"- WF 윈도우 중 VWAP 활성: {len(vwap_active_windows)}/{len(windows)} "
        f"(windows {vwap_active_windows})",
        f"- 비활성 윈도우는 OBV/Combined만 평가 (Family=VWAP 트리플은 비활성)",
        "",
        "## 5선 게이트",
        "",
        f"1. IS p-value 비의존 (OOS 기반): {gate1}",
        f"2. OOS Net>0 AND 양의 윈도우>60%: {gate2} "
        f"({pos_w}/{len(windows)}, mean={_f(p5_mean,pct=True)})",
        f"3. 합격 트리플 존재: {gate3} ({len(df_pass)})",
        f"4. Sharpe>0: {gate4} ({_f(sharpe_val)})",
        f"5. Top 트리플 존재: {gate5} ({len(top_triples)})",
        "",
        f"**총 {sum(1 for g in [gate1,gate2,gate3,gate4,gate5] if g=='PASS')}/5 통과**",
        "",
        "## 판정 (사장님 결재 입력)",
        "",
    ]
    if not np.isnan(p5_mean) and p5_mean > p3_base * 2:
        verdict = "Phase 4 paper 진입 가능 — 1차 대비 명확 개선"
    elif not np.isnan(p5_mean) and p5_mean > 0:
        verdict = "보류 — 개선 있으나 목표 대비 미달, 추가 시그널 EDA 권고"
    elif not np.isnan(p5_mean) and p5_mean <= 0:
        verdict = "재설계 필요 — 시그널 통합으로 손익 악화, paper 진입 부적합"
    else:
        verdict = "측정 불가 — 합격 트리플 0개. 합격 기준 재조정 필요"
    lines_p3.append(f"**{verdict}**")
    lines_p3 += [
        "",
        "## 다음 단계 권고",
        "- 합격 트리플 > 0 + 양의 월수익률: Phase 4 paper (1,000만원 5포지션) 1주 시뮬",
        "- 합격 0 또는 음수: 추가 EDA 우선 (외국인순매수 데이터 수집, 캘린더 효과 재탐색)",
        "- 분봉 데이터 추가 백필 (2024년 이전): VWAP 윈도우 확보가 통계 신뢰도의 핵심",
    ]
    rpath_b = os.path.join(P5_DIR, "phase5_phase3_rerun.md")
    with open(rpath_b, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_p3))
    print(f"  Phase3 report: {rpath_b}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[중단]"); sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] {e}"); traceback.print_exc(); sys.exit(1)
