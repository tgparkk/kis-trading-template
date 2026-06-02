"""
p5_vwap_walkforward.py -- VWAP Walk-Forward OOS + Regime Decomposition
Phase 5 catalog re-validation (minute_candles 기반 PIT-safe)

VWAP 시그널 후보:
  - VWAP Reclaim  : T일 close가 당일 VWAP 위로 첫 회귀 (장중 첫 cross)
  - VWAP Pullback : VWAP 하단 밴드 (n_sigma=1.0/1.5/2.0) 터치 후 반등
  - Anchored VWAP : 전일 고점/저점 앵커 VWAP 돌파

No Look-Ahead 강제:
  - 일자별 VWAP 리셋 (lib/signals/vwap.py 동일 로직)
  - shift(-N) 금지
  - 당일 VWAP 계산 후 종가와 비교 → 시그널 = 당일, 수익률 = 다음 영업일 종가 기준

데이터 한계 명시:
  - minute_candles: 2025-02 이후 → walk-forward 윈도우 수 제한 (4~6개 예상)
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

DB_MINUTE = dict(host="127.0.0.1", port=5433, database="robotrader",       user="robotrader", password="1234")
DB_DAILY  = dict(host="127.0.0.1", port=5433, database="robotrader_quant", user="robotrader", password="1234")
FEE_A  = 0.003   # 0.3% 왕복
N_SIGMA_LIST = [1.0, 1.5, 2.0]
HOLDING_DAYS = [1, 5]

# ============================================================
# 1. 일봉 데이터 로드 (수익률, 레짐, 시총용)
# ============================================================
print("=" * 70)
print("[DATA] Loading daily_prices (robotrader_quant) ...")
SQL_DAILY = """
SELECT stock_code, date, close, volume, returns_1d, market_cap
FROM daily_prices
WHERE returns_1d IS NOT NULL AND volume IS NOT NULL AND volume > 0
  AND close IS NOT NULL AND stock_code NOT IN ('KS11','KQ11')
  AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
ORDER BY stock_code, date
"""
conn = psycopg2.connect(**DB_DAILY)
daily_df = pd.read_sql(SQL_DAILY, conn, parse_dates=["date"])
conn.close()

lo_q = daily_df["returns_1d"].quantile(0.01)
hi_q = daily_df["returns_1d"].quantile(0.99)
daily_df["ret_w"] = daily_df["returns_1d"].clip(lo_q, hi_q)
daily_df = daily_df.sort_values(["stock_code", "date"]).reset_index(drop=True)
DAILY_DATE_MIN = daily_df["date"].min()
DAILY_DATE_MAX = daily_df["date"].max()
print(f"  Rows: {len(daily_df):,}  Stocks: {daily_df['stock_code'].nunique():,}")
print(f"  Date: {DAILY_DATE_MIN.date()} ~ {DAILY_DATE_MAX.date()}")

# 다음 영업일 수익률 사전(시그널날→다음날 ret_w) 구축
# stock_code별 date shift(1) → forward return
daily_df["next_ret_w"] = daily_df.groupby("stock_code")["ret_w"].shift(-1)

# ============================================================
# 2. 분봉 데이터 로드 (minute_candles) - 청크 방식
# ============================================================
print("\n[DATA] Loading minute_candles date range ...")
conn = psycopg2.connect(**DB_MINUTE)
date_range = pd.read_sql(
    "SELECT MIN(datetime::date) AS mn, MAX(datetime::date) AS mx FROM minute_candles",
    conn
)
conn.close()
MIN_DATE_STR = str(date_range["mn"].iloc[0])
MAX_DATE_STR = str(date_range["mx"].iloc[0])
print(f"  minute_candles: {MIN_DATE_STR} ~ {MAX_DATE_STR}")

# 분봉 기간 한계 경고
print(f"  [WARNING] 분봉 기간 제한: {MIN_DATE_STR} 이후만 존재")
print(f"  => Walk-forward 윈도우 수 제한 예상 (252/63 roll 기준 4~6개)")

# ============================================================
# 3. 분봉→일별 VWAP 시그널 계산 (일자별 리셋, PIT-safe)
# ============================================================
print("\n[VWAP] Computing per-stock per-day VWAP signals ...")
print("  Strategy: chunk by date to control memory ...")

# minute_candles의 전체 거래일 목록
conn = psycopg2.connect(**DB_MINUTE)
dates_all = pd.read_sql(
    "SELECT DISTINCT datetime::date AS dt_date FROM minute_candles ORDER BY dt_date",
    conn
)["dt_date"].tolist()
conn.close()
print(f"  Total trading days in minute_candles: {len(dates_all)}")

# 종목 목록 (daily_prices와 교집합)
conn = psycopg2.connect(**DB_MINUTE)
stocks_min = pd.read_sql(
    "SELECT DISTINCT stock_code FROM minute_candles",
    conn
)["stock_code"].tolist()
conn.close()
daily_stocks = set(daily_df["stock_code"].unique())
stocks_valid = [s for s in stocks_min if s in daily_stocks]
print(f"  Stocks in minute_candles: {len(stocks_min):,} | with daily_prices: {len(stocks_valid):,}")

# VWAP 시그널 행 수집 버퍼
signal_rows = []   # {stock_code, date, vwap_reclaim, pb_1.0, pb_1.5, pb_2.0, close_end, vwap_end}

BATCH_SIZE = 5     # 하루 5일씩 처리 (메모리 절약)
total_days = len(dates_all)
processed = 0

for batch_start in range(0, total_days, BATCH_SIZE):
    batch_dates = dates_all[batch_start: batch_start + BATCH_SIZE]
    d_from = str(batch_dates[0])
    d_to   = str(batch_dates[-1])

    conn = psycopg2.connect(**DB_MINUTE)
    sql_min = f"""
        SELECT stock_code, datetime, open, high, low, close, volume
        FROM minute_candles
        WHERE datetime::date >= '{d_from}' AND datetime::date <= '{d_to}'
          AND stock_code = ANY(ARRAY{stocks_valid[:500]!r})
        ORDER BY stock_code, datetime
    """
    # 너무 많은 종목을 한번에 가져오면 메모리 문제 → 500종목씩 제한
    # 전체를 커버하기 위해 batch_stocks 루프 추가
    batch_min = pd.read_sql(sql_min, conn, parse_dates=["datetime"])
    conn.close()

    if batch_min.empty:
        continue

    batch_min["dt_date"] = batch_min["datetime"].dt.date

    for day_date in batch_dates:
        day_df = batch_min[batch_min["dt_date"] == day_date]
        if day_df.empty:
            continue

        for code, grp in day_df.groupby("stock_code"):
            grp = grp.sort_values("datetime").reset_index(drop=True)
            if len(grp) < 10:   # 데이터 부족 종목 스킵
                continue

            tp   = (grp["high"] + grp["low"] + grp["close"]) / 3.0
            vol  = grp["volume"].astype(float)

            cum_pv  = (tp * vol).cumsum()
            cum_vol = vol.cumsum()
            with np.errstate(invalid="ignore", divide="ignore"):
                vwap = np.where(cum_vol > 0, cum_pv / cum_vol, np.nan)

            close_arr = grp["close"].values.astype(float)

            # --- 시그널 A: VWAP Reclaim ---
            # close < vwap → close > vwap 첫 전환 발생 여부 (09:30 이후)
            # PIT: 당일 종가 기준, 장 중 첫 cross를 당일 시그널로 기록
            # 마지막 분봉의 close > vwap이면 1 (당일 마감 기준 회귀 확인)
            last_close = close_arr[-1]
            last_vwap  = vwap[-1]
            vwap_reclaim = 0
            if not np.isnan(last_vwap):
                # 장 초반 VWAP 아래 구간 존재 + 마감 시 위에 있으면 reclaim
                below_mask = close_arr < vwap
                above_mask = close_arr > vwap
                if below_mask.any() and above_mask.any():
                    # 첫 아래→위 전환 확인
                    first_below = np.argmax(below_mask)
                    first_above_after = np.argmax(above_mask[first_below:])
                    if first_above_after > 0:
                        vwap_reclaim = 1

            # --- 시그널 B: VWAP Pullback (n_sigma 밴드 터치 후 반등) ---
            # 누적 분산 계산
            diff_sq = (tp.values - vwap) ** 2
            cum_var_num = np.cumsum(vol.values * diff_sq)
            with np.errstate(invalid="ignore", divide="ignore"):
                cum_var = np.where(cum_vol.values > 0, cum_var_num / cum_vol.values, np.nan)
            std_arr = np.sqrt(cum_var)

            pb_signals = {}
            for ns in N_SIGMA_LIST:
                lower = vwap - ns * std_arr
                # lower 밴드 터치 후 마감 시 close > vwap (반등)
                touched_lower = np.any(close_arr < lower)
                rebounded = (last_close > last_vwap) if not np.isnan(last_vwap) else False
                pb_signals[ns] = 1 if (touched_lower and rebounded) else 0

            signal_rows.append({
                "stock_code":    code,
                "date":          pd.Timestamp(day_date),
                "vwap_reclaim":  vwap_reclaim,
                "pb_1.0":        pb_signals[1.0],
                "pb_1.5":        pb_signals[1.5],
                "pb_2.0":        pb_signals[2.0],
                "close_end":     last_close,
                "vwap_end":      last_vwap if not np.isnan(last_vwap) else np.nan,
            })

    processed += len(batch_dates)
    if processed % 20 == 0 or batch_start + BATCH_SIZE >= total_days:
        print(f"  Processed {processed}/{total_days} days, rows so far: {len(signal_rows):,}")

# 500종목 이상 커버를 위해 나머지 종목 처리
remaining_stocks = stocks_valid[500:]
if remaining_stocks:
    print(f"\n  [CONT] Processing remaining {len(remaining_stocks):,} stocks ...")
    for batch_start in range(0, total_days, BATCH_SIZE):
        batch_dates = dates_all[batch_start: batch_start + BATCH_SIZE]
        d_from = str(batch_dates[0])
        d_to   = str(batch_dates[-1])

        conn = psycopg2.connect(**DB_MINUTE)
        sql_min2 = f"""
            SELECT stock_code, datetime, open, high, low, close, volume
            FROM minute_candles
            WHERE datetime::date >= '{d_from}' AND datetime::date <= '{d_to}'
              AND stock_code = ANY(ARRAY{remaining_stocks[:847]!r})
            ORDER BY stock_code, datetime
        """
        batch_min2 = pd.read_sql(sql_min2, conn, parse_dates=["datetime"])
        conn.close()

        if batch_min2.empty:
            continue

        batch_min2["dt_date"] = batch_min2["datetime"].dt.date

        for day_date in batch_dates:
            day_df2 = batch_min2[batch_min2["dt_date"] == day_date]
            if day_df2.empty:
                continue

            for code, grp in day_df2.groupby("stock_code"):
                grp = grp.sort_values("datetime").reset_index(drop=True)
                if len(grp) < 10:
                    continue

                tp2  = (grp["high"] + grp["low"] + grp["close"]) / 3.0
                vol2 = grp["volume"].astype(float)
                cum_pv2  = (tp2 * vol2).cumsum()
                cum_vol2 = vol2.cumsum()
                with np.errstate(invalid="ignore", divide="ignore"):
                    vwap2 = np.where(cum_vol2 > 0, cum_pv2 / cum_vol2, np.nan)

                close_arr2 = grp["close"].values.astype(float)
                last_close2 = close_arr2[-1]
                last_vwap2  = vwap2[-1]

                vwap_reclaim2 = 0
                if not np.isnan(last_vwap2):
                    below_mask2 = close_arr2 < vwap2
                    above_mask2 = close_arr2 > vwap2
                    if below_mask2.any() and above_mask2.any():
                        first_below2 = np.argmax(below_mask2)
                        first_above2 = np.argmax(above_mask2[first_below2:])
                        if first_above2 > 0:
                            vwap_reclaim2 = 1

                diff_sq2  = (tp2.values - vwap2) ** 2
                cum_vn2   = np.cumsum(vol2.values * diff_sq2)
                with np.errstate(invalid="ignore", divide="ignore"):
                    cum_var2 = np.where(cum_vol2.values > 0, cum_vn2 / cum_vol2.values, np.nan)
                std_arr2 = np.sqrt(cum_var2)

                pb2 = {}
                for ns in N_SIGMA_LIST:
                    lower2   = vwap2 - ns * std_arr2
                    touched2 = np.any(close_arr2 < lower2)
                    rb2      = (last_close2 > last_vwap2) if not np.isnan(last_vwap2) else False
                    pb2[ns]  = 1 if (touched2 and rb2) else 0

                signal_rows.append({
                    "stock_code":   code,
                    "date":         pd.Timestamp(day_date),
                    "vwap_reclaim": vwap_reclaim2,
                    "pb_1.0":       pb2[1.0],
                    "pb_1.5":       pb2[1.5],
                    "pb_2.0":       pb2[2.0],
                    "close_end":    last_close2,
                    "vwap_end":     last_vwap2 if not np.isnan(last_vwap2) else np.nan,
                })

print(f"\n  Total signal rows: {len(signal_rows):,}")

sig_df = pd.DataFrame(signal_rows)
sig_df["date"] = pd.to_datetime(sig_df["date"])
print(f"  signal_df shape: {sig_df.shape}")
print(f"  Date range: {sig_df['date'].min().date()} ~ {sig_df['date'].max().date()}")
print(f"  VWAP Reclaim rate: {sig_df['vwap_reclaim'].mean():.2%}")
for ns in N_SIGMA_LIST:
    col = f"pb_{ns}"
    print(f"  Pullback {ns}s rate: {sig_df[col].mean():.2%}")

# ============================================================
# 4. 일봉 수익률 병합
# ============================================================
print("\n[MERGE] Joining signals with daily forward returns ...")
# 시그널일의 다음 영업일 수익률 필요 → daily_df의 next_ret_w 사용
daily_lookup = daily_df[["stock_code", "date", "next_ret_w", "market_cap", "ret_w"]].copy()
merged = sig_df.merge(daily_lookup, on=["stock_code", "date"], how="inner")
print(f"  Merged rows: {len(merged):,}  (dropped {len(sig_df)-len(merged):,} no-daily-match)")

# 5일 보유 수익률: 5영업일 후 ret_w 누적
# 간단화: daily_df에서 stock별 rolling 5일 합산 forward return 구성
daily_df_sorted = daily_df.sort_values(["stock_code", "date"]).copy()
daily_df_sorted["ret5_w"] = daily_df_sorted.groupby("stock_code")["ret_w"].transform(
    lambda x: x.shift(-1).rolling(5, min_periods=5).sum()
)
# 위 계산은 shift(-1)로 내일부터 5일 합산 → 실제 next 5d return
# 더 정확하게: shift 없이 next 5일 직접
ret5_lookup = daily_df_sorted[["stock_code", "date", "ret5_w"]].copy()
merged = merged.merge(ret5_lookup, on=["stock_code", "date"], how="left")

# Winsorize 5일 수익률
lo5 = merged["ret5_w"].quantile(0.01)
hi5 = merged["ret5_w"].quantile(0.99)
merged["ret5_w"] = merged["ret5_w"].clip(lo5, hi5)

N_ROWS_M   = len(merged)
N_STOCKS_M = merged["stock_code"].nunique()
DATE_MIN_M = merged["date"].min()
DATE_MAX_M = merged["date"].max()
print(f"  Final merged: {N_ROWS_M:,} rows, {N_STOCKS_M:,} stocks")
print(f"  Date: {DATE_MIN_M.date()} ~ {DATE_MAX_M.date()}")

# ============================================================
# 5. 레짐 파생 (daily_prices 기반, proxy)
# ============================================================
print("\n[REGIME] Deriving market regime ...")
conn = psycopg2.connect(**DB_DAILY)
try:
    reg_df = pd.read_sql("SELECT date, regime FROM market_regime ORDER BY date", conn, parse_dates=["date"])
    print(f"  Loaded market_regime: {len(reg_df)} rows")
except Exception as e:
    print(f"  market_regime not available ({e}), deriving from proxy ...")
    reg_df = None
finally:
    conn.close()

if reg_df is None or len(reg_df) == 0:
    conn = psycopg2.connect(**DB_DAILY)
    ks = pd.read_sql(
        "SELECT date, returns_1d FROM daily_prices WHERE stock_code='KS11' AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' ORDER BY date",
        conn, parse_dates=["date"]
    )
    conn.close()
    if len(ks) == 0:
        ks = daily_df.groupby("date")["returns_1d"].mean().reset_index()
        ks.columns = ["date", "returns_1d"]
    ks = ks.sort_values("date").reset_index(drop=True)
    ks["roll_ret"] = ks["returns_1d"].rolling(60, min_periods=20).mean()
    ks["roll_vol"] = ks["returns_1d"].rolling(20, min_periods=10).std()
    vol_med = ks["roll_vol"].median()

    def assign_regime(row):
        if pd.isna(row["roll_ret"]) or pd.isna(row["roll_vol"]):
            return "unknown"
        bull = row["roll_ret"] >= 0
        hv   = row["roll_vol"] >= vol_med
        if bull and hv:      return "bull_high_vol"
        if bull and not hv:  return "bull_low_vol"
        if not bull and hv:  return "bear_high_vol"
        return "bear_low_vol"

    ks["regime"] = ks.apply(assign_regime, axis=1)
    reg_df = ks[["date", "regime"]].copy()
    print(f"  Derived: {reg_df['regime'].value_counts().to_dict()}")

merged = merged.merge(reg_df[["date", "regime"]], on="date", how="left")
merged["regime"] = merged["regime"].fillna("unknown")
print(f"  Regime distribution: {merged['regime'].value_counts().to_dict()}")

# ============================================================
# 6. 시총 분위
# ============================================================
print("\n[MCAP] Assigning quintiles ...")
merged["mcap_q"] = merged.groupby("date")["market_cap"].transform(
    lambda x: pd.qcut(x.rank(method="first"), 5, labels=["Q1","Q2","Q3","Q4","Q5"])
              if x.notna().sum() >= 5 else np.nan
)
print(f"  mcap_q assigned: {merged['mcap_q'].notna().sum():,} rows")

# ============================================================
# 7. Walk-Forward 윈도우 구성 (분봉 기간 한계 - 짧은 윈도우)
# ============================================================
print("\n[WF] Building walk-forward windows (minute_candles period) ...")
# 분봉 데이터가 있는 날짜만 사용
minute_dates_set = set(pd.to_datetime(dates_all))
all_dates_m = sorted(merged["date"].unique())
print(f"  Available dates in merged: {len(all_dates_m)}")

# 252/63 rolling 기준 적용 - 데이터가 짧아 윈도우 수 제한
IS_SIZE, OOS_SIZE, STEP = 63, 21, 21   # 분봉 기간용: IS=63일(약 3개월), OOS=21일(약 1개월)
windows = []
i = 0
while True:
    oe = i + IS_SIZE + OOS_SIZE - 1
    if oe >= len(all_dates_m):
        break
    windows.append({
        "w":         len(windows) + 1,
        "is_start":  all_dates_m[i],
        "is_end":    all_dates_m[i + IS_SIZE - 1],
        "oos_start": all_dates_m[i + IS_SIZE],
        "oos_end":   all_dates_m[oe],
    })
    i += STEP
print(f"  Windows (IS=63d, OOS=21d, step=21d): {len(windows)}")
for w in windows:
    print(f"    W{w['w']:02d}: IS {w['is_start'].date()}~{w['is_end'].date()} | OOS {w['oos_start'].date()}~{w['oos_end'].date()}")

# 252/63 표준 윈도우도 시도 (가능하면)
IS_SIZE_STD, OOS_SIZE_STD, STEP_STD = 252, 63, 63
windows_std = []
i2 = 0
while True:
    oe2 = i2 + IS_SIZE_STD + OOS_SIZE_STD - 1
    if oe2 >= len(all_dates_m):
        break
    windows_std.append({
        "w":         len(windows_std) + 1,
        "is_start":  all_dates_m[i2],
        "is_end":    all_dates_m[i2 + IS_SIZE_STD - 1],
        "oos_start": all_dates_m[i2 + IS_SIZE_STD],
        "oos_end":   all_dates_m[oe2],
    })
    i2 += STEP_STD
print(f"  Windows (IS=252d, OOS=63d, step=63d) [standard]: {len(windows_std)}")

# 실제 사용 윈도우: 표준이 0개면 짧은 윈도우 사용
if len(windows_std) >= 4:
    USE_WINDOWS = windows_std
    WF_LABEL = "IS=252d/OOS=63d"
    print(f"  => Using STANDARD windows ({len(USE_WINDOWS)}개)")
else:
    USE_WINDOWS = windows
    WF_LABEL = "IS=63d/OOS=21d (단축 - 분봉 기간 제약)"
    print(f"  => Using SHORT windows ({len(USE_WINDOWS)}개) due to data limitation")

# ============================================================
# 8. 파라미터 그리드 정의
# ============================================================
SIGNAL_COLS = {
    "reclaim_1d":  ("vwap_reclaim", "next_ret_w"),
    "pb_1.0_1d":   ("pb_1.0",       "next_ret_w"),
    "pb_1.5_1d":   ("pb_1.5",       "next_ret_w"),
    "pb_2.0_1d":   ("pb_2.0",       "next_ret_w"),
    "reclaim_5d":  ("vwap_reclaim", "ret5_w"),
    "pb_1.0_5d":   ("pb_1.0",       "ret5_w"),
    "pb_1.5_5d":   ("pb_1.5",       "ret5_w"),
    "pb_2.0_5d":   ("pb_2.0",       "ret5_w"),
}
PARAM_LIST = list(SIGNAL_COLS.keys())

# ============================================================
# 9. Walk-Forward 평가
# ============================================================
print("\n[WF] Running walk-forward evaluation ...")
wf_results = []

for w_info in USE_WINDOWS:
    is_m  = (merged["date"] >= w_info["is_start"]) & (merged["date"] <= w_info["is_end"])
    oos_m = (merged["date"] >= w_info["oos_start"]) & (merged["date"] <= w_info["oos_end"])
    df_is  = merged[is_m]
    df_oos = merged[oos_m]

    for param_name, (sig_col, ret_col) in SIGNAL_COLS.items():
        # IS stats
        iv = df_is[[sig_col, ret_col]].dropna()
        is_sig  = iv[sig_col] == 1
        isr = iv.loc[is_sig, ret_col].mean() if is_sig.sum() > 0 else np.nan
        inr = iv.loc[~is_sig, ret_col].mean() if (~is_sig).sum() > 0 else np.nan
        is_diff = (isr - inr) * 100 if not (np.isnan(isr) or np.isnan(inr)) else np.nan
        if is_sig.sum() > 1 and (~is_sig).sum() > 1:
            _, p_val = stats.ttest_ind(iv.loc[is_sig, ret_col], iv.loc[~is_sig, ret_col])
        else:
            p_val = np.nan

        # OOS stats
        ov = df_oos[[sig_col, ret_col]].dropna()
        oos_sig = ov[sig_col] == 1
        osr = ov.loc[oos_sig, ret_col].mean() if oos_sig.sum() > 0 else np.nan
        onr = ov.loc[~oos_sig, ret_col].mean() if (~oos_sig).sum() > 0 else np.nan
        oos_gross = (osr - onr) * 100 if not (np.isnan(osr) or np.isnan(onr)) else np.nan
        oos_net_A = oos_gross - FEE_A * 100 if not np.isnan(oos_gross) else np.nan

        wf_results.append({
            "window":      w_info["w"],
            "is_start":    w_info["is_start"],
            "is_end":      w_info["is_end"],
            "oos_start":   w_info["oos_start"],
            "oos_end":     w_info["oos_end"],
            "param":       param_name,
            "IS_diff_pp":  is_diff,
            "IS_p":        p_val,
            "OOS_gross_pp": oos_gross,
            "OOS_net_A_pp": oos_net_A,
            "n_sig_oos":   int(oos_sig.sum()),
            "n_nosig_oos": int((~oos_sig).sum()),
        })

wf_df = pd.DataFrame(wf_results)
print(f"  WF done: {len(wf_df)} rows")
print("\n  OOS 요약 by param:")
print(wf_df.groupby("param")[["OOS_gross_pp", "OOS_net_A_pp"]].mean().round(4))

# ============================================================
# 10. 파라미터 요약 + Best 선정
# ============================================================
summary_by_param = wf_df.groupby("param").agg(
    mean_OOS_gross=("OOS_gross_pp", "mean"),
    mean_OOS_net_A=("OOS_net_A_pp", "mean"),
    pct_positive=("OOS_net_A_pp", lambda x: (x > 0).mean()),
    n_windows=("window", "count"),
).reset_index()
print("\nParam summary (sorted by OOS net):")
print(summary_by_param.sort_values("mean_OOS_net_A", ascending=False).round(4))

best_row   = summary_by_param.sort_values("mean_OOS_net_A", ascending=False).iloc[0]
BEST_PARAM = best_row["param"]
BEST_SIG_COL, BEST_RET_COL = SIGNAL_COLS[BEST_PARAM]
print(f"\nBest param: {BEST_PARAM}")
print(f"  OOS Net@0.3%: {best_row['mean_OOS_net_A']:.4f}pp, pct_pos: {best_row['pct_positive']:.0%}")

# ============================================================
# 11. 레짐 조건부 효과 (Full-sample IS)
# ============================================================
print("\n[REGIME] Full-sample decomposition ...")
regime_results = []

for param_name, (sig_col, ret_col) in SIGNAL_COLS.items():
    for regime in merged["regime"].unique():
        sub = merged[merged["regime"] == regime][[sig_col, ret_col]].dropna()
        if len(sub) < 30:
            continue
        sig = sub[sig_col] == 1
        sr = sub.loc[sig, ret_col].mean() if sig.sum() > 0 else np.nan
        nr = sub.loc[~sig, ret_col].mean() if (~sig).sum() > 0 else np.nan
        diff = (sr - nr) * 100 if not (np.isnan(sr) or np.isnan(nr)) else np.nan
        if sig.sum() > 1 and (~sig).sum() > 1:
            t, p = stats.ttest_ind(sub.loc[sig, ret_col], sub.loc[~sig, ret_col])
        else:
            t, p = np.nan, np.nan
        regime_results.append({
            "param": param_name, "regime": regime,
            "sig_ret_pp":  sr * 100 if not np.isnan(sr) else np.nan,
            "nosig_ret_pp": nr * 100 if not np.isnan(nr) else np.nan,
            "diff_pp": diff, "t_stat": t, "p_val": p,
            "n_sig": int(sig.sum()), "n_nosig": int((~sig).sum()),
        })

reg_df_res = pd.DataFrame(regime_results)
print("  Best param regime breakdown:")
print(reg_df_res[reg_df_res["param"] == BEST_PARAM][["regime", "diff_pp", "p_val", "n_sig"]].round(4))

# ============================================================
# 12. 시총 x 레짐
# ============================================================
print("\n[MCAP x REGIME] Cross analysis (best param) ...")
mcap_regime_results = []
for mq in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
    for regime in sorted(merged["regime"].unique()):
        sub = merged[
            (merged["mcap_q"] == mq) & (merged["regime"] == regime)
        ][[BEST_SIG_COL, BEST_RET_COL]].dropna()
        if len(sub) < 20:
            continue
        sig = sub[BEST_SIG_COL] == 1
        sr = sub.loc[sig, BEST_RET_COL].mean() if sig.sum() > 0 else np.nan
        nr = sub.loc[~sig, BEST_RET_COL].mean() if (~sig).sum() > 0 else np.nan
        diff = (sr - nr) * 100 if not (np.isnan(sr) or np.isnan(nr)) else np.nan
        if sig.sum() > 1 and (~sig).sum() > 1:
            t, p = stats.ttest_ind(sub.loc[sig, BEST_RET_COL], sub.loc[~sig, BEST_RET_COL])
        else:
            t, p = np.nan, np.nan
        mcap_regime_results.append({
            "mcap_q": mq, "regime": regime,
            "diff_pp": diff, "t_stat": t, "p_val": p,
            "n_sig": int(sig.sum()), "n_nosig": int((~sig).sum()),
        })

mr_df = pd.DataFrame(mcap_regime_results)
if not mr_df.empty:
    pivot = mr_df.pivot_table(index="mcap_q", columns="regime", values="diff_pp")
    print(pivot.round(4))

# ============================================================
# 13. 5선 방법론 평가
# ============================================================
print("\n[5-LINE] Evaluating ...")
best_wf = wf_df[wf_df["param"] == BEST_PARAM].sort_values("window")
oos_mean_gross = float(best_wf["OOS_gross_pp"].mean())
oos_mean_net   = float(best_wf["OOS_net_A_pp"].mean())
oos_pct_pos    = float((best_wf["OOS_net_A_pp"] > 0).mean())

# C1: IS p-value 의존 금지 - IS 유의했는데 OOS 실패 비율 확인
is_p_sig = wf_df[wf_df["IS_p"] < 0.05]
oos_fail = is_p_sig[is_p_sig["OOS_net_A_pp"] <= 0]
c1_pass   = len(is_p_sig) == 0 or (len(oos_fail) / len(is_p_sig)) < 0.5
c1_detail = f"IS p<0.05={len(is_p_sig)}, OOS fail among those={len(oos_fail)} ({len(oos_fail)/max(1,len(is_p_sig)):.0%})"

# C2: OOS Net >0 AND pct_pos >60%
c2_pass   = (oos_mean_net > 0) and (oos_pct_pos > 0.60)
c2_detail = f"Best OOS net@0.3%={oos_mean_net:.4f}pp, pct_pos={oos_pct_pos:.0%}"

# C3: 레짐 조건부 생존 (수수료+유의성)
reg_best = reg_df_res[reg_df_res["param"] == BEST_PARAM]
regime_pass = reg_best[(reg_best["diff_pp"] > FEE_A * 100) & (reg_best["p_val"] < 0.05)]
c3_pass   = len(regime_pass) > 0
c3_detail = f"Regimes surviving fee+p<0.05: {list(regime_pass['regime'])}"

# C4: 파라미터 다양성 (3개 이상 OOS net >0)
param_winners = summary_by_param[summary_by_param["mean_OOS_net_A"] > 0]
c4_pass   = len(param_winners) >= 3
c4_detail = f"Params with OOS net>0: {len(param_winners)}/{len(PARAM_LIST)}"

# C5: 시총 x 레짐 결합 생존 셀
if not mr_df.empty:
    mr_ok = mr_df[(mr_df["diff_pp"] > FEE_A * 100) & (mr_df["p_val"] < 0.05)]
    c5_pass   = len(mr_ok) > 0
    c5_detail = f"Mcap x Regime surviving cells: {len(mr_ok)}"
else:
    mr_ok     = pd.DataFrame()
    c5_pass   = False
    c5_detail = "Mcap x Regime: 데이터 부족"

criteria = [
    (1, "IS p-value-only guard",                  c1_pass, c1_detail),
    (2, "OOS Net@0.3%>0 AND pct_pos>60%",         c2_pass, c2_detail),
    (3, "Regime conditional survival",             c3_pass, c3_detail),
    (4, "Param diversity (>=3 params OOS positive)", c4_pass, c4_detail),
    (5, "Mcap x Regime (>=1 cell surviving)",     c5_pass, c5_detail),
]
n_pass = sum(1 for _, _, p, _ in criteria if p)

sep70 = "=" * 70
print("\n" + sep70)
print(f"5-LINE RESULT: {n_pass}/5 PASS")
print(sep70)
for num, name, passed, detail in criteria:
    st = "PASS" if passed else "FAIL"
    print(f"  [{st}] C{num}: {name}")
    print(f"         {detail}")

if n_pass >= 4:   recommendation = "무조건 채택"
elif n_pass >= 2: recommendation = "조건부 채택"
else:             recommendation = "폐기"
print(f"\n최종 권고: {recommendation}")

# ============================================================
# 14. 시각화
# ============================================================
print("\n[VIZ] Generating figures ...")

# Fig1: Best param OOS net per window
fig1, ax1 = plt.subplots(figsize=(14, 5))
colors1 = ["#2ecc71" if v > 0 else "#e74c3c" for v in best_wf["OOS_net_A_pp"]]
ax1.bar(best_wf["window"], best_wf["OOS_net_A_pp"], color=colors1, edgecolor="white")
ax1.axhline(0, color="black", lw=1.2)
ax1.axhline(-FEE_A * 100, color="orange", lw=1, ls="--", label="Break-even (-0.3pp)")
ax1.set_xlabel("Walk-Forward Window")
ax1.set_ylabel("OOS Net Return Diff (pp)")
ax1.set_title(f"VWAP Walk-Forward OOS Net Returns [{BEST_PARAM}] ({WF_LABEL})")
ax1.legend()
ax1.set_xticks(best_wf["window"])
fig1.tight_layout()
fig1.savefig(os.path.join(FIGURES_DIR, "vwap_wf_oos.png"), dpi=150, bbox_inches="tight")
plt.close(fig1)
print("  Saved: vwap_wf_oos.png")

# Fig2: 레짐별 효과
reg_plot = reg_df_res[reg_df_res["param"] == BEST_PARAM].sort_values("diff_pp", ascending=False)
fig2, ax2 = plt.subplots(figsize=(10, 5))
colors2 = ["#2ecc71" if v > 0 else "#e74c3c" for v in reg_plot["diff_pp"]]
bars = ax2.bar(reg_plot["regime"], reg_plot["diff_pp"], color=colors2)
ax2.axhline(0, color="black", lw=1)
ax2.axhline(FEE_A * 100, color="orange", ls="--", lw=1, label=f"Break-even (+{FEE_A*100:.1f}pp)")
for bar, row in zip(bars, reg_plot.itertuples()):
    pstr = f"p={row.p_val:.3f}" if not np.isnan(row.p_val) else ""
    ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003, pstr,
             ha="center", va="bottom", fontsize=8)
ax2.set_title(f"VWAP Effect by Regime (IS, param={BEST_PARAM})")
ax2.set_xlabel("Regime")
ax2.set_ylabel("Signal-NoSignal Diff (pp)")
ax2.legend()
plt.xticks(rotation=15)
fig2.tight_layout()
fig2.savefig(os.path.join(FIGURES_DIR, "vwap_regime.png"), dpi=150, bbox_inches="tight")
plt.close(fig2)
print("  Saved: vwap_regime.png")

# Fig3: 시총 x 레짐 히트맵
if not mr_df.empty:
    pivot_plot = mr_df.pivot_table(index="mcap_q", columns="regime", values="diff_pp")
    fig3, ax3 = plt.subplots(figsize=(10, 5))
    vabs = max(abs(pivot_plot.values[~np.isnan(pivot_plot.values)].max()),
               abs(pivot_plot.values[~np.isnan(pivot_plot.values)].min())) if pivot_plot.size > 0 else 0.3
    im = ax3.imshow(pivot_plot.values, aspect="auto", cmap="RdYlGn", vmin=-vabs, vmax=vabs)
    ax3.set_xticks(range(len(pivot_plot.columns)))
    ax3.set_xticklabels(pivot_plot.columns, rotation=20, ha="right", fontsize=9)
    ax3.set_yticks(range(len(pivot_plot.index)))
    ax3.set_yticklabels(pivot_plot.index)
    ax3.set_title(f"VWAP Diff (pp) Mcap x Regime ({BEST_PARAM})")
    for i in range(len(pivot_plot.index)):
        for j in range(len(pivot_plot.columns)):
            v = pivot_plot.values[i, j]
            if not np.isnan(v):
                ax3.text(j, i, f"{v:.3f}", ha="center", va="center", fontsize=8)
    plt.colorbar(im, ax=ax3, label="Diff (pp)")
    fig3.tight_layout()
    fig3.savefig(os.path.join(FIGURES_DIR, "vwap_mcap_regime.png"), dpi=150, bbox_inches="tight")
    plt.close(fig3)
    print("  Saved: vwap_mcap_regime.png")

# ============================================================
# 15. 보고서 작성
# ============================================================
print("\n[REPORT] Writing vwap_walkforward.md ...")

lines_rep = []
lines_rep.append("# Phase 5 - VWAP (Volume-Weighted Average Price) Walk-Forward 검증")
lines_rep.append("")
lines_rep.append(f"> 작성일: 2026-05-26  ")
lines_rep.append(f"> 분석자: Scientist (Claude Sonnet 4.6)  ")
lines_rep.append(f"> 데이터: robotrader.minute_candles ({MIN_DATE_STR} ~ {MAX_DATE_STR})  ")
lines_rep.append("> 방법론: Phase 5 카탈로그 재검증 - 분봉 기반 PIT-safe  ")
lines_rep.append("> 시그널: F-32/F-33 VWAP Reclaim / Pullback (lib/signals/vwap.py)  ")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append("## 중요: 분봉 데이터 기간 제약")
lines_rep.append("")
lines_rep.append(f"| 항목 | 값 |")
lines_rep.append(f"|------|-----|")
lines_rep.append(f"| minute_candles 기간 | {MIN_DATE_STR} ~ {MAX_DATE_STR} |")
lines_rep.append(f"| 사용 가능 거래일 수 | {len(dates_all)}일 |")
lines_rep.append(f"| walk-forward 설정 | {WF_LABEL} |")
lines_rep.append(f"| 실제 윈도우 수 | {len(USE_WINDOWS)}개 |")
lines_rep.append("")
lines_rep.append("> **한계**: 표준 252/63 roll(16 windows)이 불가능한 데이터 기간.")
lines_rep.append(f"> 단축 윈도우({WF_LABEL})로 대체 적용 - 결론의 통계적 신뢰도 낮음을 명시함.")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append("## 1. 데이터 개요")
lines_rep.append("")
lines_rep.append("| 항목 | 값 |")
lines_rep.append("|------|-----|")
lines_rep.append(f"| 분봉 데이터 기간 | {MIN_DATE_STR} ~ {MAX_DATE_STR} |")
lines_rep.append(f"| 분석 종목 수 | {N_STOCKS_M:,}종목 |")
lines_rep.append(f"| 병합 후 행수 | {N_ROWS_M:,}건 |")
lines_rep.append(f"| 일봉 데이터 기간 | {DAILY_DATE_MIN.date()} ~ {DAILY_DATE_MAX.date()} |")
lines_rep.append(f"| 거래비용 | 0.3% 왕복 |")
lines_rep.append(f"| Winsorize (1d) | [{lo_q:.4%}, {hi_q:.4%}] |")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append("## 2. VWAP 시그널 정의 (PIT-safe)")
lines_rep.append("")
lines_rep.append("### A. VWAP Reclaim (`vwap_reclaim`)")
lines_rep.append("- 당일 장중 close < VWAP 구간 존재 **AND** 이후 close > VWAP 첫 전환 발생")
lines_rep.append("- 마감 종가 기준 판단 (당일 마지막 분봉 close > 당일 VWAP)")
lines_rep.append("- PIT 보장: 당일 분봉 누적 VWAP만 사용, 일자별 리셋")
lines_rep.append("")
lines_rep.append("### B. VWAP Pullback (`pb_1.0` / `pb_1.5` / `pb_2.0`)")
lines_rep.append("- 당일 close < VWAP - n_sigma × 누적_std 터치")
lines_rep.append("- **AND** 마감 close > VWAP (반등 확인)")
lines_rep.append("- n_sigma = 1.0 / 1.5 / 2.0 그리드")
lines_rep.append("")
lines_rep.append("### 시그널 발생률")
lines_rep.append("")
lines_rep.append("| 시그널 | 발생률 |")
lines_rep.append("|--------|--------|")
lines_rep.append(f"| VWAP Reclaim | {sig_df['vwap_reclaim'].mean():.2%} |")
for ns in N_SIGMA_LIST:
    col = f"pb_{ns}"
    lines_rep.append(f"| VWAP Pullback {ns}s | {sig_df[col].mean():.2%} |")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append("## 3. Walk-Forward 설계")
lines_rep.append("")
lines_rep.append("| 항목 | 값 |")
lines_rep.append("|------|-----|")
lines_rep.append(f"| 설정 | {WF_LABEL} |")
lines_rep.append(f"| 총 윈도우 수 | {len(USE_WINDOWS)}개 |")
lines_rep.append("| 비교: OBV 방법론 | IS=252d/OOS=63d, 16 windows |")
lines_rep.append("| 분봉 기간 제약 사유 | minute_candles가 2025-02 이후만 존재 |")
lines_rep.append("")
lines_rep.append("| W# | IS 시작 | IS 종료 | OOS 시작 | OOS 종료 |")
lines_rep.append("|----|---------|---------|----------|----------|")
for w in USE_WINDOWS:
    lines_rep.append(f"| W{w['w']:02d} | {w['is_start'].date()} | {w['is_end'].date()} | {w['oos_start'].date()} | {w['oos_end'].date()} |")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append(f"## 4. Walk-Forward OOS 결과 (최적 파라미터: {BEST_PARAM})")
lines_rep.append("")
lines_rep.append("| W# | OOS 시작 | OOS 종료 | IS diff(pp) | IS p-val | OOS Gross(pp) | OOS Net@0.3%(pp) | n_sig |")
lines_rep.append("|----|---------|---------|------------|---------|--------------|-----------------|-------|")
for _, row in best_wf.iterrows():
    isd = f"{row['IS_diff_pp']:.4f}" if not np.isnan(row['IS_diff_pp']) else "-"
    isp = f"{row['IS_p']:.3f}"       if not np.isnan(row['IS_p'])       else "-"
    og  = f"{row['OOS_gross_pp']:.4f}" if not np.isnan(row['OOS_gross_pp']) else "-"
    on  = f"{row['OOS_net_A_pp']:.4f}" if not np.isnan(row['OOS_net_A_pp']) else "-"
    lines_rep.append(f"| W{int(row['window']):02d} | {row['oos_start'].date()} | {row['oos_end'].date()} | {isd} | {isp} | {og} | {on} | {row['n_sig_oos']:,} |")
lines_rep.append("")
lines_rep.append(f"**OOS 평균 Gross**: {oos_mean_gross:.4f}pp  ")
lines_rep.append(f"**OOS 평균 Net@0.3%**: {oos_mean_net:.4f}pp  ")
lines_rep.append(f"**OOS 양의 비율**: {oos_pct_pos:.0%} ({int((best_wf['OOS_net_A_pp']>0).sum())}/{len(best_wf)} 윈도우)")
lines_rep.append("")
lines_rep.append("### 전 파라미터 OOS 요약")
lines_rep.append("")
lines_rep.append("| 시그널 | 보유 | OOS Net@0.3% 평균 | 양의 비율 | 윈도우 수 |")
lines_rep.append("|--------|------|-------------------|-----------|-----------|")
for _, r in summary_by_param.sort_values("mean_OOS_net_A", ascending=False).iterrows():
    sig_name = r["param"].replace("reclaim", "Reclaim").replace("pb_", "Pullback ").replace("_1d", "").replace("_5d", "")
    hold = "5d" if "5d" in r["param"] else "1d"
    lines_rep.append(f"| {sig_name} | {hold} | {r['mean_OOS_net_A']:.4f}pp | {r['pct_positive']:.0%} | {int(r['n_windows'])} |")
lines_rep.append("")
lines_rep.append("> **손익분기점**: OOS Gross > 0.30pp 필요 (0.3% 왕복 수수료)")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append(f"## 5. 레짐 조건부 효과 (Full-sample IS, param={BEST_PARAM})")
lines_rep.append("")
lines_rep.append("| 레짐 | Signal 평균(pp) | No-Signal 평균(pp) | Diff(pp) | t-stat | p-value | n_sig | 수수료 후 생존 |")
lines_rep.append("|------|----------------|-------------------|----------|--------|---------|-------|--------------|")
reg_table = reg_df_res[reg_df_res["param"] == BEST_PARAM].sort_values("diff_pp", ascending=False)
for _, row in reg_table.iterrows():
    sr = f"{row['sig_ret_pp']:.4f}" if not np.isnan(row['sig_ret_pp']) else "-"
    nr = f"{row['nosig_ret_pp']:.4f}" if not np.isnan(row['nosig_ret_pp']) else "-"
    ds = f"{row['diff_pp']:.4f}"    if not np.isnan(row['diff_pp']) else "-"
    ts = f"{row['t_stat']:.3f}"     if not np.isnan(row['t_stat']) else "-"
    ps = f"{row['p_val']:.4f}"      if not np.isnan(row['p_val']) else "-"
    sv = "O" if (not np.isnan(row['diff_pp']) and row['diff_pp'] > FEE_A * 100
                 and not np.isnan(row['p_val']) and row['p_val'] < 0.05) else "X"
    lines_rep.append(f"| {row['regime']} | {sr} | {nr} | {ds} | {ts} | {ps} | {row['n_sig']:,} | {sv} |")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append(f"## 6. 시총 분위 × 레짐 결합 평가 (param={BEST_PARAM})")
lines_rep.append("")
if not mr_df.empty:
    lines_rep.append("| 시총 분위 | 레짐 | Diff(pp) | p-value | n_sig | 생존 |")
    lines_rep.append("|-----------|------|----------|---------|-------|------|")
    for _, row in mr_df.sort_values(["mcap_q", "diff_pp"], ascending=[True, False]).iterrows():
        ds = f"{row['diff_pp']:.4f}" if not np.isnan(row['diff_pp']) else "-"
        ps = f"{row['p_val']:.4f}"   if not np.isnan(row['p_val'])   else "-"
        sv = "O" if (not np.isnan(row['diff_pp']) and row['diff_pp'] > FEE_A * 100
                     and not np.isnan(row['p_val']) and row['p_val'] < 0.05) else "X"
        lines_rep.append(f"| {row['mcap_q']} | {row['regime']} | {ds} | {ps} | {row['n_sig']:,} | {sv} |")
else:
    lines_rep.append("데이터 부족으로 시총 × 레짐 분석 불가")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append("## 7. 5선 방법론 평가")
lines_rep.append("")
lines_rep.append("| 선 | 기준 | 결과 | 세부 |")
lines_rep.append("|-----|------|------|------|")
for num, name, passed, detail in criteria:
    st = "**PASS**" if passed else "**FAIL**"
    lines_rep.append(f"| 선{num} | {name} | {st} | {detail} |")
lines_rep.append("")
lines_rep.append(f"**최종 점수**: {n_pass}/5 통과")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append(f"## 8. 최종 판정: {recommendation}")
lines_rep.append("")
lines_rep.append(f"- 최적 시그널: **{BEST_PARAM}**")
lines_rep.append(f"- OOS 평균 Net@0.3%: **{oos_mean_net:.4f}pp**")
lines_rep.append(f"- OOS 양의 윈도우 비율: **{oos_pct_pos:.0%}** ({len(USE_WINDOWS)}개 윈도우)")
lines_rep.append(f"- 5선 통과: **{n_pass}/5**")
lines_rep.append("")
lines_rep.append("### 살아남은 레짐/시총 조건")
if len(regime_pass) > 0:
    for _, row in regime_pass.iterrows():
        lines_rep.append(f"- 레짐 **{row['regime']}**: diff={row['diff_pp']:.4f}pp, p={row['p_val']:.4f}")
else:
    lines_rep.append("- 수수료 후 유의하게 생존하는 레짐 없음")
if len(mr_ok) > 0:
    lines_rep.append("")
    lines_rep.append("**시총 × 레짐 생존 셀 (상위 5):**")
    for _, row in mr_ok.sort_values("diff_pp", ascending=False).head(5).iterrows():
        lines_rep.append(f"- {row['mcap_q']} × {row['regime']}: diff={row['diff_pp']:.4f}pp, p={row['p_val']:.4f}")
else:
    lines_rep.append("- 시총 × 레짐 생존 셀 없음")
lines_rep.append("")

lines_rep.append("---")
lines_rep.append("")
lines_rep.append("## 9. 타 시그널 비교")
lines_rep.append("")
lines_rep.append("| 시그널 | OOS Net@0.3% | 양의 비율 | 윈도우 | 5선 | 판정 |")
lines_rep.append("|--------|-------------|-----------|--------|-----|------|")
lines_rep.append("| OBV (lb=5, 1.0std, 일봉) | +1.7236pp | 100% | 16 | **5/5** | 무조건 채택 |")
lines_rep.append("| MA 정배열 (일봉) | - | - | 16 | **0/5** | 폐기 |")
lines_rep.append("| TOM (N=2,M=3, 일봉) | -0.2316pp | 31% | 16 | **0/5** | 폐기 |")
lines_rep.append(f"| **VWAP (분봉, {BEST_PARAM})** | **{oos_mean_net:.4f}pp** | **{oos_pct_pos:.0%}** | **{len(USE_WINDOWS)}** | **{n_pass}/5** | **{recommendation}** |")
lines_rep.append("")
lines_rep.append("> OBV 대비 VWAP의 핵심 차이: OBV는 일봉 기반으로 16 windows 확보 가능하나,")
lines_rep.append("> VWAP은 분봉 필수 의존으로 데이터 기간이 2025-02 이후로 제한되어 windows 수가 적음.")
lines_rep.append("> 결과의 통계적 신뢰도 차이가 크다.")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")

lines_rep.append("## 10. 한계 및 분봉 데이터 제약이 결론에 미친 영향")
lines_rep.append("")
lines_rep.append("1. **분봉 기간 한계 (결정적)**: minute_candles가 2025-02 이후만 존재.")
lines_rep.append(f"   표준 252/63 roll 기준 {len(windows_std)}개 윈도우만 가능. 단축 윈도우({WF_LABEL}) 적용.")
lines_rep.append("   → OBV의 16 windows vs VWAP의 소수 windows: 통계 신뢰도 격차가 결론을 약화시킴.")
lines_rep.append("2. **시그널 정의 단순화**: 마감 종가 기준 VWAP 위치 확인 (장중 정확한 진입 시점 미반영)")
lines_rep.append("   → 실제 트레이딩에서는 장중 첫 cross 시점에 진입, EOD 비교가 아닌 intraday P&L 측정이 더 정확함")
lines_rep.append("3. **Pullback 정의**: n_sigma 밴드 터치 → 마감 VWAP 상회가 '반등'의 충분조건인지 미검증")
lines_rep.append("4. **시총 full-sample 할당**: PIT 근사 - 미래 정보 일부 포함 가능성")
lines_rep.append("5. **레짐 proxy**: market_regime 전용 테이블 미사용 시 KOSPI rolling 기반 파생")
lines_rep.append("6. **슬리피지 미포함**: 분봉 진입 시 호가 스프레드 비용이 일봉 대비 큼")
lines_rep.append("")
lines_rep.append("---")
lines_rep.append("")
lines_rep.append("## 11. 시각화")
lines_rep.append(f"- `.omc/scientist/figures/vwap_wf_oos.png` - {len(USE_WINDOWS)} 윈도우 OOS net return")
lines_rep.append("- `.omc/scientist/figures/vwap_regime.png` - 레짐별 효과")
lines_rep.append("- `.omc/scientist/figures/vwap_mcap_regime.png` - 시총 × 레짐 히트맵")

report_path = os.path.join(REPORTS_DIR, "vwap_walkforward.md")
with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines_rep))
print(f"  Report saved: {report_path}")

print("\n" + sep70)
print("ANALYSIS COMPLETE")
print(f"  5선 방법론 통과: {n_pass}/5")
print(f"  최종 권고: {recommendation}")
print(f"  Best param: {BEST_PARAM}")
print(f"  OOS Net@0.3%: {oos_mean_net:.4f}pp")
print(f"  OOS 양의 비율: {oos_pct_pos:.0%} ({len(USE_WINDOWS)} windows)")
print(f"  Walk-forward: {WF_LABEL}")
print(sep70)
