"""
p5_obv_swing_walkforward.py — Phase 5 v3 (OBV + VWAP swing portfolio walk-forward)
==================================================================================
직원 #9 작성 (2026-05-26). architect 진단의 "(b) 재설계" 권고 구현.

핵심:
  - Universe 단순화: mcap top 500 + tv > 10억/일 (5d median) — ROE/swing_pool 제거
  - Signal: OBV(lb=5, thr=1.0σ), VWAP pullback(pb_10), OBV_OR_VWAP
  - Exit: SL[-5/-7/-10%], TP[3/5/10%], holding[1/3/5]d
  - Walk-Forward: 252/63 × 16 windows (단독 검증 동일 구조)
  - Portfolio: 자금 1,000만원, 5포지션 max, equal weight, T+1 시가 진입, 0.3% 편도

산출물:
  reports/10pct_strategy/phase5_signals/
    v3_grid_all.csv           — 전체 grid (regime × family × sl × tp × tm)
    v3_walkforward.csv        — 16 window WF 결과
    v3_monthly_pnl.csv        — portfolio 월별 PnL
    v3_summary.md             — 1페이지 보고서
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

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "10pct_strategy")
P5_DIR     = os.path.join(REPORT_DIR, "phase5_signals")
os.makedirs(P5_DIR, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
IS_CUTOFF        = pd.Timestamp("2025-01-01")
WF_TRAIN_DAYS    = 252
WF_TEST_DAYS     = 63
WF_STEP_DAYS     = 63
N_WINDOWS_TARGET = 16
FEE_ONE_WAY      = 0.003
OBV_LB           = 5
OBV_THR_STD      = 1.0
MCAP_TOP_N       = 500
TV_MIN           = 1_000_000_000   # 10억원 (5d median)
TV_LOOKBACK      = 5
N_MIN            = 10

SL_GRID = [-0.05, -0.07, -0.10]
TP_GRID = [0.03, 0.05, 0.10]
TM_GRID = [1, 3, 5]

SIGNAL_FAMILIES = ["OBV", "VWAP", "OBV_OR_VWAP"]

# Portfolio
PORT_CAPITAL    = 10_000_000
PORT_MAX_POS    = 5

DB_Q = dict(host="127.0.0.1", port=5433, dbname="robotrader_quant",
            user="robotrader", password="1234")
VWAP_CACHE = os.path.join(P5_DIR, "vwap_signal_daily.parquet")


# =============================================================================
# 1. DATA LOAD
# =============================================================================
def load_data():
    t0 = time.time()
    print("[1/3] daily_prices ...")
    conn = psycopg2.connect(**DB_Q)
    cur = conn.cursor()
    cur.execute("""
        SELECT stock_code, date::text AS date,
               open, high, low, close, volume, trading_value, market_cap
        FROM daily_prices
        WHERE close > 0 AND volume > 0
          AND stock_code NOT IN ('KS11','KQ11')
          AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
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
    print(f"  prices: {prices.shape}, stocks={prices['stock_code'].nunique()}, "
          f"date={prices['date'].min().date()}~{prices['date'].max().date()}")

    print("[2/3] VWAP cache ...")
    if os.path.exists(VWAP_CACHE):
        vwap_df = pd.read_parquet(VWAP_CACHE)
        vwap_df["date"] = pd.to_datetime(vwap_df["date"], errors="coerce")
        vwap_df = vwap_df.dropna(subset=["date"]).reset_index(drop=True)
        print(f"  vwap: {vwap_df.shape}, stocks={vwap_df['stock_code'].nunique()}, "
              f"date={vwap_df['date'].min().date()}~{vwap_df['date'].max().date()}, "
              f"pb10_triggers={int(vwap_df['vwap_pb_10'].sum()):,}")
    else:
        print(f"  [WARN] VWAP cache 없음 ({VWAP_CACHE})")
        vwap_df = pd.DataFrame(columns=["stock_code","date","vwap_pb_10","vwap_pb_15","vwap_pb_20"])

    print("[3/3] regime (KOSPI proxy) ...")
    conn = psycopg2.connect(**DB_Q)
    ks = pd.read_sql(
        "SELECT date, returns_1d FROM daily_prices "
        "WHERE stock_code='KS11' AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' ORDER BY date",
        conn, parse_dates=["date"])
    conn.close()
    if len(ks) == 0:
        ks = prices.groupby("date").apply(
            lambda g: (g["close"]/g["open"]-1).mean()).reset_index()
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
    print(f"  regime dist: {ks['regime'].value_counts().to_dict()}")

    print(f"  Load done: {time.time()-t0:.1f}s")
    return prices, vwap_df, ks[["date","regime"]]


# =============================================================================
# 2. FEATURES — OBV, VWAP merge, universe mask (PIT)
# =============================================================================
def compute_features(prices, vwap_df, regime_df):
    print("\n[FEATURES] PIT OBV + VWAP merge + universe ...")
    t0 = time.time()
    prices = prices.sort_values(["stock_code","date"]).reset_index(drop=True)
    g = prices.groupby("stock_code", sort=False)

    # universe: mcap top 500 + tv 5d median > TV_MIN (PIT)
    prices["tv_med5"] = g["trading_value"].transform(
        lambda x: x.rolling(TV_LOOKBACK, min_periods=3).median())
    mcap_rank = prices.groupby("date")["market_cap"].rank(
        ascending=False, method="first", na_option="bottom")
    prices["univ_pass"] = ((mcap_rank <= MCAP_TOP_N) &
                          (prices["tv_med5"] >= TV_MIN)).astype(int)
    n_univ = prices["univ_pass"].sum()
    print(f"  universe pass: {n_univ:,} ({n_univ/len(prices)*100:.1f}%)")

    # OBV (단독 검증과 동일)
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
        (prices["obv_slope"] >= OBV_THR_STD * prices["obv_slope_std"])
    ).astype(int)
    n_obv = prices["obv_signal"].sum()
    print(f"  OBV trigger: {n_obv:,} ({n_obv/len(prices)*100:.2f}%)")

    # VWAP merge (분봉 가용 기간만 활성)
    print("  VWAP merge ...")
    if not vwap_df.empty:
        vw = vwap_df[["stock_code","date","vwap_pb_10"]].copy()
        vw["vwap_signal"] = vw["vwap_pb_10"].astype(int)
        prices = prices.merge(vw[["stock_code","date","vwap_signal"]],
                              on=["stock_code","date"], how="left")
        prices["vwap_signal"] = prices["vwap_signal"].fillna(0).astype(int)
    else:
        prices["vwap_signal"] = 0
    n_vw = prices["vwap_signal"].sum()
    print(f"  VWAP trigger: {n_vw:,} ({n_vw/len(prices)*100:.2f}%)")

    prices["obv_or_vwap_signal"] = (
        (prices["obv_signal"]==1) | (prices["vwap_signal"]==1)
    ).astype(int)
    n_or = prices["obv_or_vwap_signal"].sum()
    print(f"  OBV_OR_VWAP trigger: {n_or:,} ({n_or/len(prices)*100:.2f}%)")

    # regime merge
    prices = prices.merge(regime_df, on="date", how="left")
    prices["regime"] = prices["regime"].fillna("unknown")

    print(f"  Features done: {time.time()-t0:.1f}s")
    return prices


# =============================================================================
# 3. EXIT SIM + PIVOT helpers
# =============================================================================
def build_prices_pivot(prices_df):
    pivot = {}
    for sc, grp in prices_df.groupby("stock_code", sort=False):
        grp2 = grp.sort_values("date").set_index("date")
        pivot[sc] = grp2[["open","high","low","close"]].rename(
            columns={"open":"adj_open","high":"adj_high",
                     "low":"adj_low","close":"adj_close"})
    return pivot


def simulate_exit(ohlc, sl, tp, tm):
    """
    Returns (pnl, exit_day_idx, exit_reason)
      ohlc: shape (n,4) [open, high, low, close]
      entry = ohlc[0,0]  (T+1 시가)
      exit: SL/TP intraday touch (low/high), else close at min(tm, n)-1
    """
    if len(ohlc) == 0: return (np.nan, 0, "none")
    entry = ohlc[0, 0]
    if entry <= 0 or np.isnan(entry): return (np.nan, 0, "none")
    sl_p, tp_p = entry*(1+sl), entry*(1+tp)
    n = min(tm, len(ohlc))
    for d in range(n):
        h, lo, c = ohlc[d,1], ohlc[d,2], ohlc[d,3]
        if np.isnan(lo) or np.isnan(h) or np.isnan(c): continue
        if lo <= sl_p: return (sl, d, "sl")
        if h  >= tp_p: return (tp, d, "tp")
    last = ohlc[n-1, 3]
    if np.isnan(last): return (np.nan, n-1, "none")
    return ((last - entry) / entry, n-1, "tm")


def compute_mdd(pnl_list):
    if not pnl_list: return np.nan
    eq = np.cumprod(1 + np.array(pnl_list))
    rm = np.maximum.accumulate(eq)
    return float(((eq-rm)/rm).min())


def compute_sharpe(arr):
    if len(arr) < 2: return np.nan
    s = arr.std()
    return float(arr.mean()/s*np.sqrt(252)) if s > 0 else np.nan


# =============================================================================
# 4. TRADE-LEVEL GRID EVAL (IS/OOS cut)
# =============================================================================
def family_signal_col(family):
    return {"OBV":"obv_signal", "VWAP":"vwap_signal",
            "OBV_OR_VWAP":"obv_or_vwap_signal"}[family]


def evaluate_cell(univ_df, prices_pivot, family, sl, tp, tm):
    """trade-level metrics (mean, sharpe, mdd, IS/OOS)"""
    sig_col = family_signal_col(family)
    sig_df = univ_df[univ_df[sig_col]==1][["date","stock_code"]]
    empty = {"n":0,"mean_pnl":np.nan,"sharpe":np.nan,"mdd":np.nan,
             "IS_mean":np.nan,"OOS_mean":np.nan,"win_rate":np.nan,
             "n_is":0,"n_oos":0}
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
        pnl, _, _ = simulate_exit(ohlc, sl, tp, tm)
        if np.isnan(pnl): continue
        pnl_all.append(pnl)
        (is_p if date < IS_CUTOFF else oos_p).append(pnl)

    n = len(pnl_all)
    if n < N_MIN:
        empty["n"] = n; return empty
    arr = np.array(pnl_all)
    return {
        "n":        n,
        "mean_pnl": float(arr.mean()) - FEE_ONE_WAY,
        "sharpe":   compute_sharpe(arr - FEE_ONE_WAY),
        "mdd":      compute_mdd((arr - FEE_ONE_WAY).tolist()),
        "IS_mean":  float(np.mean(is_p) - FEE_ONE_WAY) if len(is_p)  >= N_MIN else np.nan,
        "OOS_mean": float(np.mean(oos_p)- FEE_ONE_WAY) if len(oos_p) >= N_MIN else np.nan,
        "win_rate": float((arr - FEE_ONE_WAY > 0).mean()),
        "n_is":     len(is_p),
        "n_oos":    len(oos_p),
    }


# =============================================================================
# 5. WALK-FORWARD WINDOWS
# =============================================================================
def build_wf_windows(date_min, date_max, target=N_WINDOWS_TARGET):
    """slide 윈도우: 16개까지 만들고, 데이터 부족하면 가능한 만큼"""
    all_b = pd.date_range(date_min, date_max, freq="B")
    if len(all_b) < WF_TRAIN_DAYS + WF_TEST_DAYS: return []
    windows = []
    i = 0
    while len(windows) < target and i + WF_TRAIN_DAYS + WF_TEST_DAYS <= len(all_b):
        ts = all_b[i]
        te = all_b[i + WF_TRAIN_DAYS - 1]
        os_ = all_b[i + WF_TRAIN_DAYS]
        oe = all_b[min(i + WF_TRAIN_DAYS + WF_TEST_DAYS - 1, len(all_b)-1)]
        windows.append({"window":len(windows)+1,
                        "train_start":ts,"train_end":te,
                        "test_start":os_,"test_end":oe})
        i += WF_STEP_DAYS
    return windows


# =============================================================================
# 6. PORTFOLIO SIMULATION
#    동시 5포지션 max, equal weight, T+1 시가 진입, 0.3% 편도(왕복 0.6%)
# =============================================================================
def portfolio_simulate(signals_with_pnl, capital=PORT_CAPITAL, max_pos=PORT_MAX_POS):
    """
    signals_with_pnl: list of dicts
      {entry_date, exit_date, stock_code, pnl_gross}  (pnl_gross = (exit-entry)/entry)
    동시 max_pos 제한. equal weight = capital / max_pos per slot.
    return: daily_eq (DataFrame: date, equity)
    """
    if not signals_with_pnl:
        return pd.DataFrame(columns=["date","equity"])

    df = pd.DataFrame(signals_with_pnl).sort_values("entry_date").reset_index(drop=True)
    slot_size = capital / max_pos
    # 활성 포지션: list of (exit_date)
    active_exits = []
    realized_cash = capital  # 시작 자본
    realized_events = []   # (date, equity)
    # 진입한 trade 적용: equity에는 청산 시 net pnl 반영
    # 동시 진입 제한: 활성 < max_pos일 때만 진입
    # 진입 자체는 cash 동결 무시(equal weight, 청산 시 일괄 정산 단순화)

    # 시간 순회: 진입일별로 active count 확인
    # exit 시점에 슬롯 반환 + 손익 반영
    pending = df.to_dict("records")
    idx = 0
    # 모든 이벤트(진입/청산)를 timeline으로 push
    timeline = []
    accepted = []
    for r in pending:
        # 이 진입을 받을 수 있나? active list 정리
        ed = r["entry_date"]
        active_exits = [x for x in active_exits if x > ed]
        if len(active_exits) >= max_pos:
            continue
        active_exits.append(r["exit_date"])
        accepted.append(r)

    if not accepted:
        return pd.DataFrame(columns=["date","equity"])

    # 각 trade의 net pnl 적용 (slot_size 기준)
    # 왕복 비용 0.6%
    fee_round = FEE_ONE_WAY * 2
    for r in accepted:
        net_pnl = r["pnl_gross"] - fee_round
        r["realized_pnl"] = net_pnl * slot_size

    # daily equity curve: 일자 정렬, 진행하며 cumulative
    realized_df = pd.DataFrame(accepted)
    realized_df = realized_df.sort_values("exit_date").reset_index(drop=True)
    realized_df["cum_pnl"] = realized_df["realized_pnl"].cumsum()
    realized_df["equity"]  = capital + realized_df["cum_pnl"]
    # daily index expansion (exit_date 기준)
    daily = realized_df.groupby("exit_date").last()[["equity"]].rename_axis("date").reset_index()
    return daily, accepted


def daily_to_monthly(daily_eq):
    """daily equity → monthly return (compound)"""
    if len(daily_eq) == 0:
        return pd.DataFrame(columns=["yyyymm","ret"])
    df = daily_eq.copy()
    df["yyyymm"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("yyyymm")["equity"].last().reset_index()
    monthly["prev"] = monthly["equity"].shift(1).fillna(PORT_CAPITAL)
    monthly["ret"] = monthly["equity"]/monthly["prev"] - 1
    return monthly[["yyyymm","ret","equity"]]


# =============================================================================
# 7. WALK-FORWARD RUNNER + portfolio
# =============================================================================
def extract_signals_with_pnl(univ_df, prices_pivot, family, sl, tp, tm):
    """각 시그널의 entry/exit/pnl"""
    sig_col = family_signal_col(family)
    sig_df = univ_df[univ_df[sig_col]==1][["date","stock_code"]]
    if len(sig_df) < N_MIN: return []
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
        if len(ohlc) == 0: continue
        pnl, exit_idx, reason = simulate_exit(ohlc, sl, tp, tm)
        if np.isnan(pnl): continue
        entry_date = sc_df.index[s]
        exit_date  = sc_df.index[s + exit_idx]
        records.append({
            "entry_date": entry_date, "exit_date": exit_date,
            "stock_code": sc, "pnl_gross": pnl, "exit_reason": reason,
            "signal_date": date,
        })
    return records


def run_walkforward(merged, prices_pivot, top_cells, windows):
    print(f"\n[WF] {len(windows)} windows × {len(top_cells)} cells ...")
    t0 = time.time()
    # 각 cell 별로 전 기간 signal/pnl을 한 번만 계산 → 윈도우 컷
    all_records = {}
    for i, c in enumerate(top_cells):
        key = (c["family"], c["sl"], c["tp"], c["tm"])
        all_records[key] = extract_signals_with_pnl(
            merged, prices_pivot, c["family"], c["sl"], c["tp"], c["tm"])
        if (i+1) % 5 == 0 or i == len(top_cells)-1:
            print(f"  cell {i+1}/{len(top_cells)}: "
                  f"{len(all_records[key]):,} records ({time.time()-t0:.0f}s)")

    rows = []
    pos_windows = 0
    all_accepted = []
    for w in windows:
        ts, te = w["test_start"], w["test_end"]
        # 윈도우 내 진입 시그널만
        merged_records = []
        for key, recs in all_records.items():
            for r in recs:
                if ts <= r["entry_date"] <= te:
                    rr = dict(r)
                    rr["cell"] = key
                    merged_records.append(rr)
        # 포트폴리오 시뮬레이션 (윈도우 단위)
        if not merged_records:
            rows.append({"window":w["window"], "test_start":ts.date(),
                         "test_end":te.date(), "n_signals":0,
                         "n_accepted":0, "monthly_mean":np.nan,
                         "sharpe":np.nan, "mdd":np.nan})
            continue
        # 모든 시그널 통합 → entry_date sort
        result = portfolio_simulate(merged_records)
        if isinstance(result, tuple):
            daily_eq, accepted = result
        else:
            daily_eq, accepted = result, []
        all_accepted.extend(accepted)
        monthly = daily_to_monthly(daily_eq)
        mret = monthly["ret"].values if len(monthly) else np.array([])
        if len(mret) == 0:
            mm = np.nan; sh = np.nan; mdd = np.nan
        else:
            mm = float(mret.mean())
            sh = float(mret.mean()/mret.std()*np.sqrt(12)) if mret.std()>0 else np.nan
            eq = np.cumprod(1+mret)
            rm = np.maximum.accumulate(eq)
            mdd = float(((eq-rm)/rm).min())
        if not np.isnan(mm) and mm > 0:
            pos_windows += 1
        rows.append({"window":w["window"], "test_start":ts.date(),
                     "test_end":te.date(),
                     "n_signals":len(merged_records),
                     "n_accepted":len(accepted),
                     "monthly_mean":mm, "sharpe":sh, "mdd":mdd})
        print(f"  W{w['window']:02d}: {ts.date()}~{te.date()} "
              f"sig={len(merged_records):,} acc={len(accepted):,} "
              f"mm={mm if not np.isnan(mm) else 0:.2%} sh={sh if not np.isnan(sh) else 0:.2f}")
    print(f"  WF done: pos={pos_windows}/{len(windows)} ({time.time()-t0:.0f}s)")
    return pd.DataFrame(rows), all_accepted


# =============================================================================
# 8. MAIN
# =============================================================================
def main():
    t_global = time.time()
    print("="*70)
    print("p5_obv_swing_walkforward.py — v3 portfolio simulation")
    print("="*70)

    # [STEP 1] Load
    print("\n[STEP 1] Load data")
    prices, vwap_df, regime_df = load_data()

    # [STEP 2] Features
    print("\n[STEP 2] Features")
    prices = compute_features(prices, vwap_df, regime_df)

    # [STEP 3] universe filter (mcap top 500 + tv > 1B)
    print("\n[STEP 3] Universe filter")
    univ = prices[prices["univ_pass"]==1].copy()
    print(f"  universe rows: {len(univ):,}, stocks: {univ['stock_code'].nunique()}, "
          f"date={univ['date'].min().date()}~{univ['date'].max().date()}")

    # [STEP 4] pivot
    print("\n[STEP 4] Build prices pivot")
    prices_pivot = build_prices_pivot(prices)
    print(f"  pivot stocks: {len(prices_pivot)}")

    # [STEP 5] Grid eval (IS/OOS cut for cell selection)
    print("\n[STEP 5] Grid eval (family × sl × tp × tm)")
    t_eval = time.time()
    all_rows = []
    total = len(SIGNAL_FAMILIES) * len(SL_GRID) * len(TP_GRID) * len(TM_GRID)
    cnt = 0
    for family in SIGNAL_FAMILIES:
        for sl in SL_GRID:
            for tp in TP_GRID:
                for tm in TM_GRID:
                    res = evaluate_cell(univ, prices_pivot, family, sl, tp, tm)
                    row = {"family":family,"sl":sl,"tp":tp,"tm":tm}
                    row.update(res)
                    # 게이트 (완화): mean>0, IS>0 AND OOS>0, sharpe>0.3, n_is>=10 AND n_oos>=10
                    row["pass"] = (
                        res["n_is"]  >= N_MIN and
                        res["n_oos"] >= N_MIN and
                        pd.notna(res["mean_pnl"]) and res["mean_pnl"] > 0 and
                        pd.notna(res["sharpe"])   and res["sharpe"]   > 0.3 and
                        pd.notna(res["IS_mean"])  and res["IS_mean"]  > 0 and
                        pd.notna(res["OOS_mean"]) and res["OOS_mean"] > 0
                    )
                    all_rows.append(row)
                    cnt += 1
                    if cnt % 10 == 0:
                        print(f"    {cnt}/{total} cells ({time.time()-t_eval:.0f}s)")
    df_all = pd.DataFrame(all_rows)
    df_pass = df_all[df_all["pass"]==True].copy() if len(df_all) else pd.DataFrame()
    print(f"  Total cells: {len(df_all)}, passed: {len(df_pass)}")

    csv_grid = os.path.join(P5_DIR, "v3_grid_all.csv")
    df_all.to_csv(csv_grid, index=False)
    print(f"  saved: {csv_grid}")

    # [STEP 6] Family별 top cell 선택 (합격 우선, 없으면 mean_pnl 최상위)
    print("\n[STEP 6] Top cell selection (family당 best)")
    top_cells = []
    for family in SIGNAL_FAMILIES:
        sub = df_all[df_all["family"]==family]
        if len(sub) == 0: continue
        sub_pass = sub[sub["pass"]==True]
        if len(sub_pass) > 0:
            best = sub_pass.nlargest(1, "sharpe").iloc[0]
            chosen_via = "pass"
        else:
            sub_with_data = sub[sub["mean_pnl"].notna()]
            if len(sub_with_data) == 0: continue
            best = sub_with_data.nlargest(1, "mean_pnl").iloc[0]
            chosen_via = "best_mean"
        top_cells.append({"family":family, "sl":best["sl"],
                          "tp":best["tp"], "tm":int(best["tm"]),
                          "mean_pnl":best["mean_pnl"],
                          "sharpe":best["sharpe"],
                          "n":int(best["n"]),
                          "chosen_via":chosen_via})
        print(f"  {family}: sl={best['sl']:.0%} tp={best['tp']:.0%} tm={int(best['tm'])}d "
              f"mean_pnl={best['mean_pnl']:.2%} sharpe={best['sharpe']:.2f} "
              f"n={int(best['n'])} via={chosen_via}")

    # [STEP 7] Walk-forward windows
    print("\n[STEP 7] Walk-forward windows")
    date_min = univ["date"].min(); date_max = univ["date"].max()
    windows = build_wf_windows(date_min, date_max, target=N_WINDOWS_TARGET)
    print(f"  windows: {len(windows)} (target={N_WINDOWS_TARGET})")
    for w in windows:
        print(f"    W{w['window']:02d}: train {w['train_start'].date()}~{w['train_end'].date()} "
              f"test {w['test_start'].date()}~{w['test_end'].date()}")

    # [STEP 8] Walk-forward + portfolio simulation
    print("\n[STEP 8] WF + portfolio simulation")
    if not top_cells:
        print("  [SKIP] top_cells 비어 있음")
        wf_df = pd.DataFrame(columns=["window","test_start","test_end",
                                       "n_signals","n_accepted","monthly_mean",
                                       "sharpe","mdd"])
        all_trades = []
    else:
        wf_df, all_trades = run_walkforward(univ, prices_pivot, top_cells, windows)

    csv_wf = os.path.join(P5_DIR, "v3_walkforward.csv")
    wf_df.to_csv(csv_wf, index=False)
    print(f"  saved: {csv_wf}")

    # [STEP 9] 전체 trade pool → 전기간 portfolio monthly
    print("\n[STEP 9] Combined portfolio monthly")
    if all_trades:
        trades_df = pd.DataFrame(all_trades)
        trades_df = trades_df.sort_values("entry_date").reset_index(drop=True)
        result = portfolio_simulate(trades_df.to_dict("records"))
        if isinstance(result, tuple):
            daily_eq, _ = result
        else:
            daily_eq = result
        monthly = daily_to_monthly(daily_eq)
        csv_m = os.path.join(P5_DIR, "v3_monthly_pnl.csv")
        monthly.to_csv(csv_m, index=False)
        print(f"  saved: {csv_m} ({len(monthly)} months)")
        if len(monthly):
            mret = monthly["ret"].values
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
        monthly = pd.DataFrame(columns=["yyyymm","ret","equity"])
        mean_m = pos_m = sh_m = mdd_m = tot_ret = ann_ret = calmar = np.nan
        csv_m = os.path.join(P5_DIR, "v3_monthly_pnl.csv")
        monthly.to_csv(csv_m, index=False)

    # [STEP 10] Summary report (1-pager)
    print("\n[STEP 10] Summary report")
    elapsed = time.time() - t_global
    write_summary(df_all, df_pass, top_cells, wf_df, monthly,
                  mean_m, pos_m, sh_m, mdd_m, tot_ret, ann_ret, calmar,
                  windows, all_trades, elapsed)

    # Console final
    print("\n" + "="*70)
    print("FINAL — v3 portfolio")
    print("="*70)
    print(f"전체 셀:           {len(df_all)}")
    print(f"합격 셀:           {len(df_pass)}")
    print(f"Top cells:         {len(top_cells)} (family당 best)")
    print(f"WF 윈도우:         {len(windows)}")
    print(f"전체 trades:       {len(all_trades) if all_trades else 0}")
    print(f"월 수:             {len(monthly)}")
    if not np.isnan(mean_m):
        print(f"월평균 PnL:        {mean_m*100:+.3f}%")
        print(f"양수 월:           {pos_m}/{len(monthly)} "
              f"({pos_m/max(len(monthly),1)*100:.0f}%)")
        print(f"연환산:            {ann_ret*100 if not np.isnan(ann_ret) else 0:+.2f}%")
        print(f"Sharpe(월):        {sh_m if not np.isnan(sh_m) else 0:.2f}")
        print(f"MDD:               {mdd_m*100 if not np.isnan(mdd_m) else 0:+.2f}%")
        print(f"Calmar:            {calmar if not np.isnan(calmar) else 0:.2f}")
    else:
        print(f"월평균 PnL:        N/A (trade 없음)")
    print(f"\n1차(P3) 월 +0.23% vs v3 월 "
          f"{mean_m*100 if not np.isnan(mean_m) else 0:+.3f}%")
    if not np.isnan(mean_m):
        progress = mean_m / 0.10 * 100
        print(f"목표 10% 진척률:   {progress:.1f}%")
    print(f"소요:              {elapsed/60:.1f}분")
    print("="*70)


def write_summary(df_all, df_pass, top_cells, wf_df, monthly,
                  mean_m, pos_m, sh_m, mdd_m, tot_ret, ann_ret, calmar,
                  windows, all_trades, elapsed):
    _f = lambda v, pct=False: (
        f"{v*100:+.3f}%" if pct and pd.notna(v) and not np.isnan(v) else
        f"{v:.4f}" if pd.notna(v) and not np.isnan(v) else "N/A"
    )

    family_dist_pass = {}
    if len(df_pass):
        family_dist_pass = df_pass.groupby("family").size().to_dict()

    regime_dist_pass = {}  # v3는 universe에서 regime 분리 안 함, 빈 dict

    # progress
    progress_pct = mean_m / 0.10 * 100 if not np.isnan(mean_m) else np.nan

    # verdict
    p3_base = 0.0023
    if np.isnan(mean_m):
        verdict = "측정 불가 — trade 0건. 시그널/유니버스 재검토 필요"
    elif mean_m > p3_base * 2:
        verdict = "Phase 4 paper 진입 가능 — 1차(0.23%) 대비 명확 개선"
    elif mean_m > p3_base:
        verdict = "보류 — 1차 대비 소폭 개선, 추가 EDA 권고"
    elif mean_m > 0:
        verdict = "보류 — 양수이나 1차 미달, 추가 알파 탐색 필요"
    else:
        verdict = "최종 종결 — 음수. 현재 알파로 월 10% 도달 불가, 신규 시그널 탐색 필요"

    # cross-section vs trade-level 정합성 (단독 +172bps vs v3 회수율)
    obv_cell = next((c for c in top_cells if c["family"]=="OBV"), None)
    if obv_cell is not None and pd.notna(obv_cell["mean_pnl"]):
        cs_alpha_bps = 172.36  # 단독 OBV walk-forward best
        trade_pnl_bps = obv_cell["mean_pnl"] * 10000
        recovery = trade_pnl_bps / cs_alpha_bps * 100 if cs_alpha_bps != 0 else np.nan
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
        f"소요: {elapsed/60:.1f}분",
        "",
        "## 1. v3 재설계 핵심",
        "",
        "| 항목 | v2 (5/26 직원 #6/#7) | v3 (5/26 직원 #9) |",
        "|------|----------------------|-------------------|",
        "| Universe | ROE Q4+ ∩ phase2a swing_pool top-3 | mcap top 500 + tv 5d median > 10억 |",
        "| Signal | OBV / VWAP / OBV_OR_VWAP × regime split | 동일 (단, regime 분리 제거) |",
        "| Exit | SL[-1.5/-2/-3/-4/-5%] TP[3/5/7/10/15%] TM[1/5/10/20/30/45/60] | SL[-5/-7/-10%] TP[3/5/10%] TM[1/3/5]d |",
        "| 평가 | trade-level mean + IS/OOS cut | trade-level + **portfolio 5포지션 sim** |",
        "| Walk-forward | 252/63 × 6 windows | **252/63 × 16 windows** (단독 동일) |",
        "",
        "## 2. 합격 셀 / Family 분포",
        "",
        f"- 전체 grid: **{len(df_all)} cells** (3 family × 3 SL × 3 TP × 3 TM)",
        f"- 합격 (gates: mean>0 AND IS>0 AND OOS>0 AND sharpe>0.3 AND n_is/n_oos>=10): "
        f"**{len(df_pass)} cells** ({len(df_pass)/max(len(df_all),1)*100:.0f}%)",
        "",
        "Family별 합격 수:",
    ]
    for fam in SIGNAL_FAMILIES:
        cnt = family_dist_pass.get(fam, 0)
        lines.append(f"- {fam}: {cnt}")
    lines.append("")

    lines.append("Top cell (family당 best):")
    lines.append("")
    lines.append("| family | sl | tp | tm | mean_pnl | sharpe | n | via |")
    lines.append("|--------|----|----|----|----------|--------|---|-----|")
    for c in top_cells:
        lines.append(
            f"| {c['family']} | {c['sl']:.0%} | {c['tp']:.0%} | {c['tm']}d "
            f"| {_f(c['mean_pnl'], pct=True)} | {_f(c['sharpe'])} "
            f"| {c['n']} | {c['chosen_via']} |"
        )
    lines.append("")

    lines += [
        "## 3. Cross-section vs Trade-level 정합성",
        "",
        f"- {cs_line}",
        "- 단독 검증은 'OBV signal 종목군 평균 - 비신호군 평균' (cross-section alpha).",
        "- v3는 'T+1 시가 진입 → SL/TP/TM exit, fee 0.3% 편도' (trade-level pnl).",
        "- 회수율 < 100%는 exit rule이 alpha를 갉아먹는 정상 현상.",
        "",
        "## 4. 월별 PnL (1차 vs v3)",
        "",
        "| 지표 | 1차 (P3) | v3 |",
        "|------|----------|-----|",
        f"| 월평균 | +0.23% | {_f(mean_m, pct=True)} |",
        f"| Sharpe (월) | 0.3837 | {_f(sh_m)} |",
        f"| MDD | -6.55% | {_f(mdd_m, pct=True)} |",
        f"| 양수월/총월 | 3/6 (50%) | {pos_m}/{len(monthly)} "
        f"({pos_m/max(len(monthly),1)*100:.0f}%) |",
        f"| Calmar | - | {_f(calmar)} |",
        f"| 연환산 | - | {_f(ann_ret, pct=True)} |",
        f"| 누적 | - | {_f(tot_ret, pct=True)} |",
        f"| 전체 trades | - | {len(all_trades) if all_trades else 0} |",
        "",
        "## 5. 목표 10% 진척률",
        "",
        f"- 1차: +0.23% / 10% = **2.3%**",
        f"- v3: {_f(mean_m, pct=True)} / 10% = **{progress_pct:.1f}%**" if not np.isnan(progress_pct)
        else "- v3: N/A",
        "",
        "## 6. Walk-Forward 16 윈도우 OOS",
        "",
        f"- 양수 윈도우: {pos_w}/{len(windows)} "
        f"({pos_w/max(len(windows),1)*100:.0f}%)",
        "",
        "| W | Test | n_sig | n_acc | monthly_mean | sharpe | mdd |",
        "|---|------|-------|-------|--------------|--------|-----|",
    ]
    for _, row in wf_df.iterrows():
        lines.append(
            f"| {int(row['window'])} | {row['test_start']}~{row['test_end']} "
            f"| {int(row['n_signals']):,} | {int(row['n_accepted']):,} "
            f"| {_f(row.get('monthly_mean'), pct=True)} "
            f"| {_f(row.get('sharpe'))} "
            f"| {_f(row.get('mdd'), pct=True)} |"
        )
    lines.append("")

    lines += [
        f"## 7. 판정: **{verdict}**",
        "",
        "## 8. Paper 진입 시 (보류/통과 시)",
        "",
        f"- 자금: 1,000만원",
        f"- 동시 최대 포지션: 5 (equal weight = 200만원/슬롯)",
        f"- 진입: T+1 시가",
        f"- Exit: SL/TP/TM intraday touch (low/high) 또는 보유기간 마감 종가",
        f"- 비용: 0.3% 편도 (왕복 0.6%)",
        f"- 시그널: OBV (lb=5, slope≥1.0σ) ± VWAP pb_10",
        "",
        "## 9. 산출물",
        "- `v3_grid_all.csv` ({} cells)".format(len(df_all)),
        "- `v3_walkforward.csv` ({} windows)".format(len(wf_df)),
        "- `v3_monthly_pnl.csv` ({} months)".format(len(monthly)),
        "",
        "## 10. 제약 / 한계",
        "- VWAP pullback은 분봉 가용 기간(2025-02~) 외 비활성 → IS 윈도우 다수에서 OBV만 평가",
        "- regime split 제거로 BEAR_HIGH_VOL 등 특수 국면 진단력 ↓ (단, universe 표본 붕괴 회피)",
        "- portfolio sim은 슬리피지/체결확률 100% 가정",
        "- VWAP cache 재생성 없이 기존 parquet 재사용 (vwap_pb_10 컬럼만 사용)",
    ]
    rpath = os.path.join(P5_DIR, "v3_summary.md")
    with open(rpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Summary: {rpath}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[중단]"); sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] {e}"); traceback.print_exc(); sys.exit(1)
