"""
p2b_signal_multiverse.py — Stage B: 매수 시그널 멀티버스 평가
================================================================
사장님 결재 2026-05-24:
  60 universe pool (6 국면 × Top 10 필터) × 3 버킷 시그널 카탈로그
  각 pool × 각 시그널 family × 파라미터 셀 평가

대원칙:
  - PIT 강제: 시그널 식은 T일 종가까지만 사용. 매수는 T+1 시가. forward return은 평가용
  - IS = 2021-01~2024-12, OOS = 2025-01~2026-05
  - pandas shift(-N)은 forward return 계산에만 허용, 시그널 식 절대 금지
  - 체크포인트: 1,000셀마다 저장

실행:
  python RoboTrader_template/scripts/10pct_strategy/p2b_signal_multiverse.py
"""

import sys
import os
import time
import traceback
import warnings
import itertools

# Windows console UTF-8 강제
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# ── 경로 설정 ────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "10pct_strategy")
os.makedirs(REPORT_DIR, exist_ok=True)

# ── 출력 파일 ─────────────────────────────────────────────────────────────────
OUT_ALL      = os.path.join(REPORT_DIR, "phase2b_signal_grid_all.csv")
OUT_PASS     = os.path.join(REPORT_DIR, "phase2b_signal_passed.csv")
OUT_TOP_MD   = os.path.join(REPORT_DIR, "phase2b_top_signals_by_regime_bucket.md")
OUT_SUMMARY  = os.path.join(REPORT_DIR, "phase2b_summary.md")
OUT_CKPT     = os.path.join(REPORT_DIR, "phase2b_checkpoint.csv")

# ── 하이퍼파라미터 ────────────────────────────────────────────────────────────
CHECKPOINT_EVERY  = 1000
IS_CUTOFF         = pd.Timestamp("2025-01-01")    # IS: <, OOS: >=
LIFT_MIN          = 1.2
N_MIN             = 50
IS_OOS_DIFF_REL   = 1.0  # |IS_OOS_diff| < |IS_mean| * IS_OOS_DIFF_REL

# 버킷별 청산 horizon (T+N 종가 청산)
BUCKET_HORIZONS = {
    "swing":    "fwd_3d",   # 3일
    "mid":      "fwd_20d",  # 20일
    "position": "fwd_60d",  # 45일 → fwd_60d 가장 근접
}

# ── 국면 ─────────────────────────────────────────────────────────────────────
REGIMES_6 = [
    "BULL_HIGH_VOL", "BULL_LOW_VOL",
    "BEAR_HIGH_VOL", "BEAR_LOW_VOL",
    "SIDEWAYS_HIGH_VOL", "SIDEWAYS_LOW_VOL",
]

TOP_N_PER_REGIME = 10  # 국면별 Top 10 필터


# =============================================================================
# 1. 데이터 로드
# =============================================================================

def load_data():
    t0 = time.time()
    print("[1/4] phase2a_filter_passed.csv 로드...")
    filters_df = pd.read_csv(os.path.join(REPORT_DIR, "phase2a_filter_passed.csv"))
    print(f"  filters: {filters_df.shape}, regimes: {filters_df['regime'].value_counts().to_dict()}")

    print("[2/4] phase1_forward_returns.parquet 로드...")
    fwd = pd.read_parquet(os.path.join(REPORT_DIR, "phase1_forward_returns.parquet"))
    fwd["date"] = pd.to_datetime(fwd["date"])
    print(f"  fwd: {fwd.shape}")

    print("[3/4] phase0_regime_segments.csv 로드...")
    seg = pd.read_csv(os.path.join(REPORT_DIR, "phase0_regime_segments.csv"))
    seg = seg[seg["index_code"] == "KOSPI"].copy()
    seg["start_date"] = pd.to_datetime(seg["start_date"])
    seg["end_date"]   = pd.to_datetime(seg["end_date"])

    print("[4/4] DB daily_prices 로드 (OHLCV)...")
    conn = psycopg2.connect(
        host="127.0.0.1", port=5433, dbname="robotrader_quant",
        user="robotrader", password="1234"
    )
    query = r"""
        SELECT stock_code, date::text AS date,
               open, high, low, close, volume, trading_value, market_cap
        FROM daily_prices
        WHERE close > 0
          AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        ORDER BY stock_code, date
    """
    prices = pd.read_sql(query, conn)
    conn.close()
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    prices = prices.dropna(subset=["date"]).reset_index(drop=True)
    print(f"  prices: {prices.shape}, {prices['date'].min().date()} ~ {prices['date'].max().date()}")

    print(f"  로드 완료 ({time.time()-t0:.1f}s)")
    return filters_df, fwd, seg, prices


# =============================================================================
# 2. 전처리
# =============================================================================

def build_regime_date_map(seg: pd.DataFrame) -> dict:
    """날짜 → regime 매핑 딕셔너리."""
    date_to_regime = {}
    for _, row in seg.iterrows():
        dates = pd.date_range(row["start_date"], row["end_date"], freq="B")
        for d in dates:
            date_to_regime[d] = row["label_6"]
    return date_to_regime


def compute_signal_features(prices: pd.DataFrame) -> pd.DataFrame:
    """
    시그널 계산에 필요한 PIT 피처를 사전 계산.
    모든 rolling/shift는 T 기준 과거 데이터만 사용 (PIT 강제).
    T+1 매수이므로 시그널은 T 날에 발생 → fwd join 시 T의 forward return 사용.
    """
    print("  PIT 피처 계산 중 (sort + groupby shift)...")
    t0 = time.time()
    prices = prices.sort_values(["stock_code", "date"]).reset_index(drop=True)
    g = prices.groupby("stock_code", sort=False)

    # --- 기본 ---
    prices["ret1d"]    = g["close"].pct_change()
    prices["open_t"]   = prices["open"]
    prices["high_t"]   = prices["high"]
    prices["low_t"]    = prices["low"]
    prices["close_t"]  = prices["close"]
    prices["vol_t"]    = prices["volume"]

    # --- 이전 값 (PIT) ---
    prices["close_lag1"] = g["close"].shift(1)
    prices["close_lag2"] = g["close"].shift(2)
    prices["close_lag3"] = g["close"].shift(3)
    prices["high_lag1"]  = g["high"].shift(1)
    prices["low_lag1"]   = g["low"].shift(1)
    prices["open_lag1"]  = g["open"].shift(1)
    prices["open_lag2"]  = g["open"].shift(2)
    prices["close_lag4"] = g["close"].shift(4)
    prices["high_lag2"]  = g["high"].shift(2)
    prices["low_lag2"]   = g["low"].shift(2)
    prices["vol_lag1"]   = g["volume"].shift(1)

    # --- BB (볼린저밴드) — 여러 period 사전계산 ---
    for period in [15, 20, 25]:
        ma = g["close"].transform(lambda x: x.rolling(period, min_periods=period).mean())
        std = g["close"].transform(lambda x: x.rolling(period, min_periods=period).std())
        prices[f"bb_ma{period}"]  = ma
        prices[f"bb_std{period}"] = std

    # --- RSI 사전계산 ---
    for rsi_p in [7, 14, 21]:
        delta = g["close"].diff()
        gain  = delta.clip(lower=0)
        loss  = (-delta).clip(lower=0)
        avg_g = g["close"].transform(
            lambda x: x.diff().clip(lower=0).rolling(rsi_p, min_periods=rsi_p).mean()
        )
        avg_l = g["close"].transform(
            lambda x: (-x.diff()).clip(lower=0).rolling(rsi_p, min_periods=rsi_p).mean()
        )
        rs = avg_g / avg_l.replace(0, np.nan)
        prices[f"rsi{rsi_p}"] = 100 - (100 / (1 + rs))

    # --- 거래량 rolling 평균 ---
    for vw in [5, 20]:
        prices[f"vol_ma{vw}"] = g["volume"].transform(
            lambda x: x.rolling(vw, min_periods=1).mean()
        )

    # --- 일평균 거래대금 rolling ---
    prices["tv_ma20"] = g["trading_value"].transform(
        lambda x: x.rolling(20, min_periods=1).mean()
    )

    # --- MA (이동평균) ---
    for ma_p in [5, 10, 20, 30, 60, 200]:
        prices[f"ma{ma_p}"] = g["close"].transform(
            lambda x: x.rolling(ma_p, min_periods=ma_p).mean()
        )

    # --- 52주 고가 ---
    prices["high_52w"] = g["high"].transform(
        lambda x: x.rolling(252, min_periods=20).max()
    )
    # 20일 / 40일 / 60일 저가
    for n in [20, 40, 60]:
        prices[f"low_{n}d"]  = g["low"].transform(lambda x, nn=n: x.rolling(nn, min_periods=nn).min())
        prices[f"high_{n}d"] = g["high"].transform(lambda x, nn=n: x.rolling(nn, min_periods=nn).max())

    # 15일/40일 고가 (박스권 돌파용)
    prices["high_15d"] = g["high"].transform(lambda x: x.rolling(15, min_periods=15).max())
    prices["low_15d"]  = g["low"].transform(lambda x: x.rolling(15, min_periods=15).min())
    prices["high_40d"] = g["high"].transform(lambda x: x.rolling(40, min_periods=40).max())
    prices["low_40d"]  = g["low"].transform(lambda x: x.rolling(40, min_periods=40).min())
    # 5일/10일 고가 (신고가 돌파용)
    prices["high_5d"]  = g["high"].transform(lambda x: x.rolling(5,  min_periods=5 ).max())
    prices["high_10d"] = g["high"].transform(lambda x: x.rolling(10, min_periods=10).max())

    # --- EMA ---
    for ema_p in [60, 200]:
        prices[f"ema{ema_p}"] = g["close"].transform(
            lambda x, pp=ema_p: x.ewm(span=pp, adjust=False, min_periods=pp).mean()
        )

    # --- 캔들 속성 ---
    prices["body"]       = prices["close_t"] - prices["open_t"]
    prices["body_abs"]   = prices["body"].abs()
    prices["candle_rng"] = (prices["high_t"] - prices["low_t"]).replace(0, np.nan)
    prices["body_pct"]   = prices["body_abs"] / prices["candle_rng"]  # 몸통비율
    prices["upper_wick"] = prices["high_t"] - prices[["close_t", "open_t"]].max(axis=1)
    prices["lower_wick"] = prices[["close_t", "open_t"]].min(axis=1) - prices["low_t"]
    prices["upper_wick_pct"] = prices["upper_wick"] / prices["candle_rng"]
    prices["lower_wick_pct"] = prices["lower_wick"] / prices["candle_rng"]
    prices["is_bullish"]     = (prices["close_t"] >= prices["open_t"]).astype(int)

    # 몸통 분위 (날짜별 cross-section, PIT)
    def quintile_rank(s):
        pct = s.rank(pct=True, na_option="keep")
        bins = [-1e-10, 0.2, 0.4, 0.6, 0.8, 1.0]
        labels = [1, 2, 3, 4, 5]
        return pd.cut(pct, bins=bins, labels=labels).astype("Int64")

    prices["body_quintile"] = prices.groupby("date")["body_abs"].transform(quintile_rank)

    # --- 양봉 비율 (20일) ---
    prices["bullish_ratio_20d"] = g["is_bullish"].transform(
        lambda x: x.rolling(20, min_periods=5).mean()
    )

    # --- 20d 수익률 ---
    prices["ret20d"] = g["close"].pct_change(20)
    prices["ret60d"] = g["close"].pct_change(60)
    prices["ret120d"] = g["close"].pct_change(120)

    # --- 변동성 ---
    prices["vol20d_std"] = g["ret1d"].transform(
        lambda x: x.rolling(20, min_periods=5).std()
    )
    prices["vol120d_std"] = g["ret1d"].transform(
        lambda x: x.rolling(120, min_periods=20).std()
    )

    # 변동성 분위 (날짜별)
    prices["vol20d_quintile"] = prices.groupby("date")["vol20d_std"].transform(quintile_rank)

    # 20d 수익률 분위
    prices["ret20d_quintile"] = prices.groupby("date")["ret20d"].transform(quintile_rank)
    prices["ret60d_quintile"] = prices.groupby("date")["ret60d"].transform(quintile_rank)
    prices["ret120d_quintile"] = prices.groupby("date")["ret120d"].transform(quintile_rank)

    # MA 기울기 (20일)
    prices["ma20_slope"] = (prices["ma20"] - g["ma20"].shift(5)) / g["ma20"].shift(5)

    print(f"  PIT 피처 완료 ({time.time()-t0:.1f}s), shape: {prices.shape}")
    return prices


def build_universe_pools(filters_df: pd.DataFrame, top_n: int) -> list:
    """
    6 국면 × Top N 필터 = 60 universe pool 목록.
    각 pool = dict(regime, cell_idx, filter_params, ...)
    """
    pools = []
    for regime in REGIMES_6:
        sub = filters_df[filters_df["regime"] == regime].copy()
        if len(sub) == 0:
            print(f"  [WARN] regime {regime} 필터 없음. 스킵.")
            continue
        # lift_mean 기준 Top N
        sub["lift_mean"] = sub[["swing_lift", "mid_lift", "position_lift"]].mean(axis=1)
        top = sub.nlargest(min(top_n, len(sub)), "lift_mean")
        for rank, (_, row) in enumerate(top.iterrows(), 1):
            pools.append({
                "regime":    regime,
                "pool_rank": rank,
                "cell_idx":  int(row["cell_idx"]),
                "lift_mean": float(row["lift_mean"]),
                # 필터 파라미터 (universe 구성에 사용)
                "mcap_cutoff_top_n":      row["mcap_cutoff_top_n"],
                "min_trading_value":      row["min_trading_value"],
                "trading_value_lookback": row["trading_value_lookback"],
                "market":                 row["market"],
                "sector_exclude":         row["sector_exclude"],
                "min_price":              row["min_price"],
                "min_liquidity_90d":      row["min_liquidity_90d"],
                "vol_quintile":           row["vol_quintile"],
                "candle_health":          row["candle_health"],
                "candle_trend":           row["candle_trend"],
                "n_filtered":             row["n_filtered"],
            })
    print(f"  Universe pools: {len(pools)} (목표 60)")
    return pools


def assign_regime_to_prices(prices: pd.DataFrame, date_to_regime: dict) -> pd.DataFrame:
    """prices에 regime label 붙이기."""
    prices["regime"] = prices["date"].map(date_to_regime)
    return prices


# =============================================================================
# 3. Universe 필터 적용
# =============================================================================

def apply_universe_filter(prices: pd.DataFrame, pool: dict) -> pd.Series:
    """
    pool 파라미터에 따라 prices에서 해당 국면 & 필터 조건 만족하는 boolean mask 반환.
    PIT: 필터 기준은 T 시점 값 (prices의 현재 행 = T).
    """
    regime = pool["regime"]
    mask = prices["regime"] == regime

    # mcap_cutoff_top_n: 날짜별 시총 rank (PIT — 이미 같은 날짜 내 rank이므로 PIT 충족)
    top_n = pool["mcap_cutoff_top_n"]
    if pd.notna(top_n) and top_n > 0:
        # 날짜별 시총 내림차순 rank
        mcap_rank = prices.groupby("date")["market_cap"].rank(
            ascending=False, method="first", na_option="bottom"
        )
        mask &= (mcap_rank <= top_n)

    # min_trading_value + lookback
    lb  = int(pool["trading_value_lookback"]) if pd.notna(pool["trading_value_lookback"]) else 20
    tv_col = f"tv_ma{min(lb, 20)}"  # 5d or 20d rolling mean (precomputed: tv_ma20)
    # tv_ma5 is not precomputed; use tv_ma20 as proxy for lb<=20
    # actually we only precomputed tv_ma20. Use that.
    min_tv = pool["min_trading_value"]
    if pd.notna(min_tv) and min_tv > 0:
        mask &= (prices["tv_ma20"] >= min_tv)

    # min_price: T 종가 기준
    mp = pool["min_price"]
    if pd.notna(mp) and mp > 0:
        mask &= (prices["close_t"] >= mp)

    # vol_quintile (0 = 전체)
    vq = pool["vol_quintile"]
    if pd.notna(vq) and int(vq) != 0:
        mask &= (prices["vol20d_quintile"] == int(vq))

    # candle_health: 20일 양봉비율
    ch = pool["candle_health"]
    if pd.notna(ch) and ch > 0:
        mask &= (prices["bullish_ratio_20d"] >= float(ch))

    return mask


# =============================================================================
# 4. 시그널 카탈로그
# =============================================================================

# ─── 스윙 버킷 시그널 family (1~5일) ─────────────────────────────────────────

def sig_bb_reversion(df, period, stddev, rsi_thr):
    """BB 역추세: 종가가 하단밴드 아래이고 RSI < rsi_thr."""
    lower = df[f"bb_ma{period}"] - stddev * df[f"bb_std{period}"]
    rsi   = df[f"rsi14"]  # 14가 표준, rsi_thr로 조정
    return (df["close_t"] < lower) & (rsi < rsi_thr) & lower.notna()


def sig_gap_down_reversal(df, gap_pct, vol_mult, close_pos_pct):
    """갭다운 반등: 오늘 시가가 전일 종가 대비 gap_pct% 이상 하락 후 종가가 저점+close_pos_pct% 이내."""
    gap = (df["open_t"] - df["close_lag1"]) / df["close_lag1"].replace(0, np.nan)
    close_from_low = (df["close_t"] - df["low_t"]) / df["close_t"].replace(0, np.nan)
    vol_ratio = df["vol_t"] / df["vol_ma20"].replace(0, np.nan)
    return (gap <= gap_pct) & (vol_ratio >= vol_mult) & (close_from_low <= close_pos_pct)


def sig_new_low_reversal(df, lookback, vol_mult):
    """신저가 반발: 종가가 N일 저가에 근접 + 거래량 증가."""
    low_col = f"low_{lookback}d"
    if low_col not in df.columns:
        return pd.Series(False, index=df.index)
    near_low = (df["close_t"] <= df[low_col] * 1.01)
    vol_ratio = df["vol_t"] / df["vol_ma20"].replace(0, np.nan)
    return near_low & (vol_ratio >= vol_mult) & df[low_col].notna()


def sig_vol_spike_bullish(df, vol_mult, body_quantile_min):
    """거래량 폭증 + 양봉: 거래량이 20일 평균의 vol_mult배 이상이고 몸통이 상위 분위."""
    vol_ratio = df["vol_t"] / df["vol_ma20"].replace(0, np.nan)
    return (vol_ratio >= vol_mult) & (df["is_bullish"] == 1) & (df["body_quintile"] >= body_quantile_min)


def sig_hammer(df, vol_mult):
    """망치형: 아래꼬리 >= 2×몸통, 위꼬리 <= 0.2×범위, 하락 컨텍스트."""
    long_lower = df["lower_wick"] >= 2 * df["body_abs"]
    short_upper = df["upper_wick_pct"] <= 0.2
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    # 하락 컨텍스트: 3일 전 대비 하락
    down_trend = df["close_t"] < df["close_lag3"]
    return long_lower & short_upper & vol_ok & down_trend & (df["candle_rng"] > 0)


def sig_inverted_hammer(df, vol_mult):
    """역망치형: 위꼬리 >= 2×몸통, 아래꼬리 <= 0.2×범위, 하락 컨텍스트."""
    long_upper = df["upper_wick"] >= 2 * df["body_abs"]
    short_lower = df["lower_wick_pct"] <= 0.2
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    down_trend = df["close_t"] < df["close_lag3"]
    return long_upper & short_lower & vol_ok & down_trend & (df["candle_rng"] > 0)


def sig_doji(df, vol_mult):
    """도지: 몸통/범위 <= 0.1, 거래량 조건."""
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return (df["body_pct"] <= 0.1) & vol_ok & (df["candle_rng"] > 0)


def sig_marubozu_bull(df, vol_mult):
    """마루보즈 양봉: 몸통/범위 >= 0.9, 양봉, 거래량 조건."""
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return (df["body_pct"] >= 0.9) & (df["is_bullish"] == 1) & vol_ok & (df["candle_rng"] > 0)


def sig_bullish_engulfing(df, body_ratio, vol_mult):
    """상승장악형: 전일 음봉, 오늘 양봉이 전일 몸통을 완전히 감쌈."""
    prev_bear  = df["close_lag1"] < df["open_lag1"]
    today_bull = df["close_t"] > df["open_t"]
    engulf = (df["open_t"] <= df["close_lag1"]) & (df["close_t"] >= df["open_lag1"])
    # body_ratio: 오늘 몸통이 전일 몸통의 N배 이상
    prev_body = (df["open_lag1"] - df["close_lag1"]).abs().replace(0, np.nan)
    today_body = (df["close_t"] - df["open_t"]).abs()
    size_ok = today_body >= prev_body * body_ratio
    vol_ok  = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return prev_bear & today_bull & engulf & size_ok & vol_ok


def sig_three_white_soldiers(df, vol_mult):
    """적삼병: 3일 연속 양봉, 각 종가가 전일 종가보다 높음."""
    c3 = (df["close_t"]    > df["open_t"])
    c2 = (df["close_lag1"] > df["open_lag1"])
    c1 = (df["close_lag2"] > df["open_lag2"])
    hi3 = df["close_t"]    > df["close_lag1"]
    hi2 = df["close_lag1"] > df["close_lag2"]
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return c3 & c2 & c1 & hi3 & hi2 & vol_ok


def sig_morning_star(df, vol_mult):
    """샛별: 1) 긴 음봉 2) 도지/작은몸통 3) 긴 양봉."""
    bear1 = df["close_lag2"] < df["open_lag2"]
    body1_pct = (df["open_lag2"] - df["close_lag2"]).abs() / df["close_lag2"].replace(0, np.nan)
    big_bear1 = body1_pct >= 0.02
    small2 = (df["open_lag1"] - df["close_lag1"]).abs() / df["close_lag1"].replace(0, np.nan) <= 0.01
    bull3 = df["close_t"] > df["open_t"]
    body3_pct = (df["close_t"] - df["open_t"]) / df["open_t"].replace(0, np.nan)
    big_bull3 = body3_pct >= 0.02
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return bear1 & big_bear1 & small2 & bull3 & big_bull3 & vol_ok


def sig_rsi_divergence(df, rsi_period, strength):
    """
    RSI 다이버전스: 종가 신저가 갱신이지만 RSI는 이전 저점보다 높음 (강세 다이버전스).
    strength: 'weak' = RSI 차이 >= 2, 'strong' = RSI 차이 >= 5.
    """
    rsi_col = f"rsi{rsi_period}"
    if rsi_col not in df.columns:
        return pd.Series(False, index=df.index)
    rsi_diff_thr = 2.0 if strength == "weak" else 5.0
    new_low_price = df["low_t"] < df["low_lag1"]
    rsi_higher    = df[rsi_col] > df[rsi_col].shift(1) + rsi_diff_thr
    return new_low_price & rsi_higher & df[rsi_col].notna()


def sig_ma_pullback_reversal(df, ma_period, pullback_pct):
    """MA 이탈 후 회귀: 종가가 MA 아래로 pullback_pct% 이상 이탈."""
    ma_col = f"ma{ma_period}"
    if ma_col not in df.columns:
        return pd.Series(False, index=df.index)
    deviation = (df["close_t"] - df[ma_col]) / df[ma_col].replace(0, np.nan)
    return (deviation <= pullback_pct) & df[ma_col].notna()


def sig_vwap_pullback(df, pullback_pct, vol_mult):
    """VWAP 이탈: VWAP 근사치(MA20) 대비 pullback_pct% 아래 + 거래량."""
    vwap_proxy = df["ma20"]  # 일봉 VWAP 근사
    if "ma20" not in df.columns:
        return pd.Series(False, index=df.index)
    deviation = (df["close_t"] - vwap_proxy) / vwap_proxy.replace(0, np.nan)
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return (deviation <= pullback_pct) & vol_ok & vwap_proxy.notna()


# ─── 미드 버킷 시그널 family (10~30일) ───────────────────────────────────────

def sig_new_high_breakout(df, lookback, vol_mult):
    """단기 신고가 돌파: 종가가 N일 고가 돌파 + 거래량 조건."""
    high_col = f"high_{lookback}d"
    if high_col not in df.columns:
        return pd.Series(False, index=df.index)
    # 신고가 = 전일까지의 N일 고가 돌파 (PIT: shift(1) 적용)
    prev_high = df.groupby("stock_code")[high_col].shift(1)
    breakout = df["close_t"] > prev_high
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return breakout & vol_ok & prev_high.notna()


def sig_box_breakout(df, box_n, box_width_pct, vol_mult):
    """박스권 돌파: N일 고가와 저가의 차이가 box_width_pct% 이내인 박스권에서 고가 돌파."""
    high_col = f"high_{box_n}d"
    low_col  = f"low_{box_n}d"
    if high_col not in df.columns or low_col not in df.columns:
        return pd.Series(False, index=df.index)
    box_h = df[high_col]
    box_l = df[low_col]
    box_width = (box_h - box_l) / box_l.replace(0, np.nan)
    in_box = box_width <= box_width_pct
    breakout = df["close_t"] > box_h * 0.99  # 고가 근접 돌파
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return in_box & breakout & vol_ok & box_h.notna()


def sig_golden_cross(df, fast_ma, slow_ma, vol_mult):
    """MA 골든크로스: fast_ma가 slow_ma를 상향 돌파."""
    fc = f"ma{fast_ma}"
    sc = f"ma{slow_ma}"
    if fc not in df.columns or sc not in df.columns:
        return pd.Series(False, index=df.index)
    cross_today = (df[fc] > df[sc])
    cross_prev  = (df.groupby("stock_code")[fc].shift(1) <= df.groupby("stock_code")[sc].shift(1))
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return cross_today & cross_prev & vol_ok & df[fc].notna() & df[sc].notna()


def sig_near_52w_high(df, within_pct, vol_mult):
    """52주 신고가 N% 이내: 종가가 52주 고가의 (1-within_pct) 이상."""
    if "high_52w" not in df.columns:
        return pd.Series(False, index=df.index)
    ratio = df["close_t"] / df["high_52w"].replace(0, np.nan)
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return (ratio >= 1 - within_pct) & vol_ok & df["high_52w"].notna()


def sig_momentum_low_vol(df, ret_quintile_min, vol_quintile_max):
    """모멘텀 + 저변동성: 20d 수익률 분위 높고 변동성 분위 낮음."""
    if "ret20d_quintile" not in df.columns or "vol20d_quintile" not in df.columns:
        return pd.Series(False, index=df.index)
    return (df["ret20d_quintile"] >= ret_quintile_min) & (df["vol20d_quintile"] <= vol_quintile_max)


def sig_ema200_breakout(df, hold_days, vol_mult):
    """EMA200 돌파: 종가가 EMA200 위에서 hold_days일 유지."""
    if "ema200" not in df.columns:
        return pd.Series(False, index=df.index)
    above_ema = (df["close_t"] > df["ema200"]).astype(int)
    # hold_days 연속 EMA 위에 있음
    consec = df.groupby("stock_code")["close_t"].transform(
        lambda x: (x > df.loc[x.index, "ema200"]).rolling(hold_days, min_periods=hold_days).min()
    )
    # PIT: consec은 rolling min이므로 미래 사용 없음
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    # Simpler: check today above + N days ago below
    cross = (df["close_t"] > df["ema200"]) & (
        df.groupby("stock_code")["close_t"].shift(hold_days) <= df.groupby("stock_code")["ema200"].shift(hold_days)
    )
    return cross & vol_ok & df["ema200"].notna()


def sig_mid_three_soldiers(df, vol_mult):
    """미드버킷 적삼병 + MA20 위."""
    three_sol = sig_three_white_soldiers(df, vol_mult)
    above_ma20 = df["close_t"] > df["ma20"]
    return three_sol & above_ma20 & df["ma20"].notna()


def sig_long_candle_dist(df, bull_ratio_quintile):
    """장기 캔들 분포: 20일 양봉 비율 분위 상위."""
    bq = df.groupby("date")["bullish_ratio_20d"].transform(
        lambda s: s.rank(pct=True, na_option="keep")
    )
    thr = (bull_ratio_quintile - 1) / 5.0
    return (bq >= thr) & df["bullish_ratio_20d"].notna()


def sig_breakout_marubozu(df, lookback, vol_mult):
    """돌파 캔들 강도: N일 고가 돌파 + 마루보즈/장대양봉 (위꼬리 <= 10%)."""
    high_col = f"high_{lookback}d"
    if high_col not in df.columns:
        return pd.Series(False, index=df.index)
    prev_high = df.groupby("stock_code")[high_col].shift(1)
    breakout = df["close_t"] > prev_high
    is_strong = (df["body_pct"] >= 0.7) & (df["is_bullish"] == 1) & (df["upper_wick_pct"] <= 0.1)
    vol_ok = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return breakout & is_strong & vol_ok & prev_high.notna()


# ─── 포지션 버킷 시그널 family (30~60일) ─────────────────────────────────────

def sig_momentum_performance(df, ret_quintile_min):
    """실적 모멘텀 대체 — 60일 수익률 분위 상위."""
    if "ret60d_quintile" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["ret60d_quintile"] >= ret_quintile_min


def sig_pbr_momentum(df, mcap_quintile_max, ret60d_quintile_min):
    """PBR 대체(시총 분위 저평가) + 모멘텀."""
    mcap_q = df.groupby("date")["market_cap"].transform(
        lambda s: s.rank(pct=True, na_option="keep")
    )
    low_mcap = mcap_q <= mcap_quintile_max / 5.0
    hi_ret = df.get("ret60d_quintile", pd.Series(np.nan, index=df.index)) >= ret60d_quintile_min
    return low_mcap & hi_ret


def sig_long_momentum_low_vol(df, ret120d_quintile_min, vol120d_quintile_max):
    """장기 모멘텀 × 저변동성: 120d 수익률 높고 변동성 낮음."""
    if "ret120d_quintile" not in df.columns or "vol20d_quintile" not in df.columns:
        return pd.Series(False, index=df.index)
    return (df["ret120d_quintile"] >= ret120d_quintile_min) & (df["vol20d_quintile"] <= vol120d_quintile_max)


def sig_ema200_trend(df, hold_days, slope_min):
    """EMA200 위 N일 추세 + MA 기울기."""
    if "ema200" not in df.columns or "ma20_slope" not in df.columns:
        return pd.Series(False, index=df.index)
    above_ema = (df["close_t"] > df["ema200"])
    # N일 연속 EMA 위
    consec_above = df.groupby("stock_code")["close_t"].transform(
        lambda x: (x > df.loc[x.index, "ema200"]).rolling(hold_days, min_periods=hold_days).min()
    )
    slope_ok = df["ma20_slope"] >= slope_min
    return consec_above.fillna(0).astype(bool) & slope_ok & df["ema200"].notna()


def sig_long_bullish_candle(df, period_days, bull_ratio_min):
    """장기 양봉 우세: period_days 양봉 비율 상위."""
    # Use bullish_ratio_20d as proxy
    return (df["bullish_ratio_20d"] >= bull_ratio_min) & df["bullish_ratio_20d"].notna()


def sig_pos_three_soldiers_ema(df, vol_mult):
    """적삼병 + EMA60 위 + 거래량."""
    three_sol = sig_three_white_soldiers(df, vol_mult)
    above_ema60 = df["close_t"] > df.get("ema60", pd.Series(np.nan, index=df.index))
    return three_sol & above_ema60 & df.get("ema60", pd.Series(np.nan, index=df.index)).notna()


def sig_sector_momentum(df, ret_quintile_min):
    """섹터 모멘텀 대체 — 60d 수익률 분위 상위 (섹터 데이터 없으므로 전체 대체)."""
    if "ret60d_quintile" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["ret60d_quintile"] >= ret_quintile_min


def sig_cup_handle(df, cup_depth_max, vol_mult):
    """Cup & Handle 근사: 20일 저가 대비 회복 + 거래량."""
    if "low_20d" not in df.columns or "high_20d" not in df.columns:
        return pd.Series(False, index=df.index)
    cup_bottom = df["low_20d"]
    cup_top    = df["high_20d"]
    cup_depth  = (cup_top - cup_bottom) / cup_top.replace(0, np.nan)
    near_top   = df["close_t"] >= cup_top * 0.97
    deep_ok    = cup_depth <= cup_depth_max
    vol_ok     = df["vol_t"] / df["vol_ma20"].replace(0, np.nan) >= vol_mult
    return near_top & deep_ok & vol_ok & cup_top.notna()


# =============================================================================
# 5. 시그널 카탈로그 빌더 (sparse grid)
# =============================================================================

def build_signal_catalog() -> dict:
    """
    버킷별 시그널 (family, params) 목록 반환.
    Sparse 그리드 — 각 family의 50~70% 셀만 (파라미터 조합 축소).

    Returns: {"swing": [...], "mid": [...], "position": [...]}
    각 원소: {"bucket", "family", "params", "signal_fn"}
    """
    catalog = {"swing": [], "mid": [], "position": []}

    # ── 스윙 버킷 ──────────────────────────────────────────────────────────────
    # BB 역추세: period(15/20/25) × stddev(1.5/2.0/2.5) × RSI(25/30/35) = 27셀
    for period, stddev, rsi_thr in itertools.product([15, 20, 25], [1.5, 2.0, 2.5], [25, 30, 35]):
        p = {"period": period, "stddev": stddev, "rsi_thr": rsi_thr}
        catalog["swing"].append({
            "family": "bb_reversion",
            "params": p,
            "fn": lambda df, p=p: sig_bb_reversion(df, p["period"], p["stddev"], p["rsi_thr"]),
        })

    # 갭다운 반등: gap%(-3/-5) × vol_mult(1.5/2/3) × close_pos(0/0.01) = 12셀
    for gap_pct, vol_mult, close_pos in itertools.product([-0.03, -0.05], [1.5, 2.0, 3.0], [0.0, 0.01]):
        p = {"gap_pct": gap_pct, "vol_mult": vol_mult, "close_pos": close_pos}
        catalog["swing"].append({
            "family": "gap_down_reversal",
            "params": p,
            "fn": lambda df, p=p: sig_gap_down_reversal(df, p["gap_pct"], p["vol_mult"], p["close_pos"]),
        })

    # 신저가 반발: lookback(20/40/60) × vol_mult(1.5/2/3) = 9셀
    for lookback, vol_mult in itertools.product([20, 40, 60], [1.5, 2.0, 3.0]):
        p = {"lookback": lookback, "vol_mult": vol_mult}
        catalog["swing"].append({
            "family": "new_low_reversal",
            "params": p,
            "fn": lambda df, p=p: sig_new_low_reversal(df, p["lookback"], p["vol_mult"]),
        })

    # 거래량 폭증 + 양봉: vol_mult(3/5/10) × body_q(3/4) = 6셀
    for vol_mult, body_q in itertools.product([3.0, 5.0, 10.0], [3, 4]):
        p = {"vol_mult": vol_mult, "body_q": body_q}
        catalog["swing"].append({
            "family": "vol_spike_bullish",
            "params": p,
            "fn": lambda df, p=p: sig_vol_spike_bullish(df, p["vol_mult"], p["body_q"]),
        })

    # 망치형: vol_mult(1.5/2.0) = 2셀
    for vol_mult in [1.5, 2.0]:
        p = {"vol_mult": vol_mult}
        catalog["swing"].append({
            "family": "hammer",
            "params": p,
            "fn": lambda df, p=p: sig_hammer(df, p["vol_mult"]),
        })

    # 역망치형: vol_mult(1.5/2.0) = 2셀
    for vol_mult in [1.5, 2.0]:
        p = {"vol_mult": vol_mult}
        catalog["swing"].append({
            "family": "inverted_hammer",
            "params": p,
            "fn": lambda df, p=p: sig_inverted_hammer(df, p["vol_mult"]),
        })

    # 도지: vol_mult(1.0/1.5) = 2셀
    for vol_mult in [1.0, 1.5]:
        p = {"vol_mult": vol_mult}
        catalog["swing"].append({
            "family": "doji",
            "params": p,
            "fn": lambda df, p=p: sig_doji(df, p["vol_mult"]),
        })

    # 마루보즈 양봉: vol_mult(1.5/2.0) = 2셀
    for vol_mult in [1.5, 2.0]:
        p = {"vol_mult": vol_mult}
        catalog["swing"].append({
            "family": "marubozu_bull",
            "params": p,
            "fn": lambda df, p=p: sig_marubozu_bull(df, p["vol_mult"]),
        })

    # 상승장악형: body_ratio(1.0/1.5) × vol_mult(1.5/2.0) = 4셀
    for body_ratio, vol_mult in itertools.product([1.0, 1.5], [1.5, 2.0]):
        p = {"body_ratio": body_ratio, "vol_mult": vol_mult}
        catalog["swing"].append({
            "family": "bullish_engulfing",
            "params": p,
            "fn": lambda df, p=p: sig_bullish_engulfing(df, p["body_ratio"], p["vol_mult"]),
        })

    # 적삼병: vol_mult(1.0/1.5) = 2셀
    for vol_mult in [1.0, 1.5]:
        p = {"vol_mult": vol_mult}
        catalog["swing"].append({
            "family": "three_white_soldiers",
            "params": p,
            "fn": lambda df, p=p: sig_three_white_soldiers(df, p["vol_mult"]),
        })

    # 샛별: vol_mult(1.0/1.5) = 2셀
    for vol_mult in [1.0, 1.5]:
        p = {"vol_mult": vol_mult}
        catalog["swing"].append({
            "family": "morning_star",
            "params": p,
            "fn": lambda df, p=p: sig_morning_star(df, p["vol_mult"]),
        })

    # RSI 다이버전스: period(7/14/21) × strength(weak/strong) = 6셀
    for rsi_p, strength in itertools.product([7, 14, 21], ["weak", "strong"]):
        p = {"rsi_period": rsi_p, "strength": strength}
        catalog["swing"].append({
            "family": "rsi_divergence",
            "params": p,
            "fn": lambda df, p=p: sig_rsi_divergence(df, p["rsi_period"], p["strength"]),
        })

    # MA 이탈 후 회귀: MA(5/10/20) × pullback(-0.03/-0.05) = 6셀
    for ma_p, pb in itertools.product([5, 10, 20], [-0.03, -0.05]):
        p = {"ma_period": ma_p, "pullback_pct": pb}
        catalog["swing"].append({
            "family": "ma_pullback_reversal",
            "params": p,
            "fn": lambda df, p=p: sig_ma_pullback_reversal(df, p["ma_period"], p["pullback_pct"]),
        })

    # VWAP 이탈: pullback(-0.02/-0.03/-0.05) × vol_mult(1.5/2.0) = 6셀
    for pb, vol_mult in itertools.product([-0.02, -0.03, -0.05], [1.5, 2.0]):
        p = {"pullback_pct": pb, "vol_mult": vol_mult}
        catalog["swing"].append({
            "family": "vwap_pullback",
            "params": p,
            "fn": lambda df, p=p: sig_vwap_pullback(df, p["pullback_pct"], p["vol_mult"]),
        })

    # ── 미드 버킷 ──────────────────────────────────────────────────────────────
    # 단기 신고가 돌파: lookback(5/10/20) × vol_mult(1.2/1.5/2.0) = 9셀
    for lookback, vol_mult in itertools.product([5, 10, 20], [1.2, 1.5, 2.0]):
        p = {"lookback": lookback, "vol_mult": vol_mult}
        catalog["mid"].append({
            "family": "new_high_breakout",
            "params": p,
            "fn": lambda df, p=p: sig_new_high_breakout(df, p["lookback"], p["vol_mult"]),
        })

    # 박스권 돌파: box_n(15/20/40) × box_width(0.05/0.10) × vol_mult(1.5/2.0) = 12셀
    for box_n, bw, vol_mult in itertools.product([15, 20, 40], [0.05, 0.10], [1.5, 2.0]):
        p = {"box_n": box_n, "box_width": bw, "vol_mult": vol_mult}
        catalog["mid"].append({
            "family": "box_breakout",
            "params": p,
            "fn": lambda df, p=p: sig_box_breakout(df, p["box_n"], p["box_width"], p["vol_mult"]),
        })

    # MA 골든크로스: (5,20)/(10,30)/(20,60) × vol_mult(1.0/1.5) = 6셀
    for (fast, slow), vol_mult in itertools.product([(5, 20), (10, 30), (20, 60)], [1.0, 1.5]):
        p = {"fast_ma": fast, "slow_ma": slow, "vol_mult": vol_mult}
        catalog["mid"].append({
            "family": "golden_cross",
            "params": p,
            "fn": lambda df, p=p: sig_golden_cross(df, p["fast_ma"], p["slow_ma"], p["vol_mult"]),
        })

    # 52주 신고가 N% 이내: within_pct(0.03/0.05/0.10) × vol_mult(1.2/1.5) = 6셀
    for wp, vol_mult in itertools.product([0.03, 0.05, 0.10], [1.2, 1.5]):
        p = {"within_pct": wp, "vol_mult": vol_mult}
        catalog["mid"].append({
            "family": "near_52w_high",
            "params": p,
            "fn": lambda df, p=p: sig_near_52w_high(df, p["within_pct"], p["vol_mult"]),
        })

    # 모멘텀 + 저변동성: ret_q(4/5) × vol_q(1/2) = 4셀
    for ret_q, vol_q in itertools.product([4, 5], [1, 2]):
        p = {"ret_quintile_min": ret_q, "vol_quintile_max": vol_q}
        catalog["mid"].append({
            "family": "momentum_low_vol",
            "params": p,
            "fn": lambda df, p=p: sig_momentum_low_vol(df, p["ret_quintile_min"], p["vol_quintile_max"]),
        })

    # EMA200 돌파: hold_days(3/5/10) × vol_mult(1.5/2.0) = 6셀
    for hd, vol_mult in itertools.product([3, 5, 10], [1.5, 2.0]):
        p = {"hold_days": hd, "vol_mult": vol_mult}
        catalog["mid"].append({
            "family": "ema200_breakout",
            "params": p,
            "fn": lambda df, p=p: sig_ema200_breakout(df, p["hold_days"], p["vol_mult"]),
        })

    # 3캔들 추세(미드): vol_mult(1.0/1.5) = 2셀
    for vol_mult in [1.0, 1.5]:
        p = {"vol_mult": vol_mult}
        catalog["mid"].append({
            "family": "mid_three_soldiers",
            "params": p,
            "fn": lambda df, p=p: sig_mid_three_soldiers(df, p["vol_mult"]),
        })

    # 장기 캔들 분포: bull_ratio_quintile(4/5) = 2셀
    for bq in [4, 5]:
        p = {"bull_ratio_quintile": bq}
        catalog["mid"].append({
            "family": "long_candle_dist",
            "params": p,
            "fn": lambda df, p=p: sig_long_candle_dist(df, p["bull_ratio_quintile"]),
        })

    # 돌파 캔들 강도: lookback(5/10/20) × vol_mult(1.5/2.0) = 6셀
    for lookback, vol_mult in itertools.product([5, 10, 20], [1.5, 2.0]):
        p = {"lookback": lookback, "vol_mult": vol_mult}
        catalog["mid"].append({
            "family": "breakout_marubozu",
            "params": p,
            "fn": lambda df, p=p: sig_breakout_marubozu(df, p["lookback"], p["vol_mult"]),
        })

    # ── 포지션 버킷 ──────────────────────────────────────────────────────────
    # 실적 모멘텀 대체 (60d 수익률 분위): 3셀
    for ret_q in [3, 4, 5]:
        p = {"ret_quintile_min": ret_q}
        catalog["position"].append({
            "family": "momentum_performance",
            "params": p,
            "fn": lambda df, p=p: sig_momentum_performance(df, p["ret_quintile_min"]),
        })

    # PBR 저평가 대체 + 모멘텀: mcap_q(1/2) × ret60d_q(4/5) = 4셀
    for mcap_q, ret_q in itertools.product([1, 2], [4, 5]):
        p = {"mcap_quintile_max": mcap_q, "ret60d_quintile_min": ret_q}
        catalog["position"].append({
            "family": "pbr_momentum",
            "params": p,
            "fn": lambda df, p=p: sig_pbr_momentum(df, p["mcap_quintile_max"], p["ret60d_quintile_min"]),
        })

    # 장기 모멘텀 × 저변동성: ret120d_q(3/4/5) × vol_q(1/2/3) = 9셀
    for ret_q, vol_q in itertools.product([3, 4, 5], [1, 2, 3]):
        p = {"ret120d_quintile_min": ret_q, "vol120d_quintile_max": vol_q}
        catalog["position"].append({
            "family": "long_momentum_low_vol",
            "params": p,
            "fn": lambda df, p=p: sig_long_momentum_low_vol(df, p["ret120d_quintile_min"], p["vol120d_quintile_max"]),
        })

    # EMA200 위 N일 추세: hold_days(20/40/60) × slope_min(0/0.001) = 6셀
    for hd, slope in itertools.product([20, 40, 60], [0.0, 0.001]):
        p = {"hold_days": hd, "slope_min": slope}
        catalog["position"].append({
            "family": "ema200_trend",
            "params": p,
            "fn": lambda df, p=p: sig_ema200_trend(df, p["hold_days"], p["slope_min"]),
        })

    # 장기 양봉 우세: bull_ratio_min(0.5/0.6) = 2셀
    for br_min in [0.5, 0.6]:
        p = {"bull_ratio_min": br_min}
        catalog["position"].append({
            "family": "long_bullish_candle",
            "params": p,
            "fn": lambda df, p=p: sig_long_bullish_candle(df, 60, p["bull_ratio_min"]),
        })

    # 섹터 모멘텀 대체: ret60d_q(4/5) = 2셀
    for ret_q in [4, 5]:
        p = {"ret_quintile_min": ret_q}
        catalog["position"].append({
            "family": "sector_momentum",
            "params": p,
            "fn": lambda df, p=p: sig_sector_momentum(df, p["ret_quintile_min"]),
        })

    # Cup & Handle: cup_depth(0.10/0.20) × vol_mult(1.5/2.0) = 4셀
    for cup_depth, vol_mult in itertools.product([0.10, 0.20], [1.5, 2.0]):
        p = {"cup_depth_max": cup_depth, "vol_mult": vol_mult}
        catalog["position"].append({
            "family": "cup_handle",
            "params": p,
            "fn": lambda df, p=p: sig_cup_handle(df, p["cup_depth_max"], p["vol_mult"]),
        })

    # 적삼병 + EMA60: vol_mult(1.0/1.5) = 2셀
    for vol_mult in [1.0, 1.5]:
        p = {"vol_mult": vol_mult}
        catalog["position"].append({
            "family": "pos_three_soldiers_ema",
            "params": p,
            "fn": lambda df, p=p: sig_pos_three_soldiers_ema(df, p["vol_mult"]),
        })

    for bucket, cells in catalog.items():
        print(f"  {bucket} 버킷: {len(cells)} 셀")
    total = sum(len(v) for v in catalog.values())
    print(f"  전체 시그널 셀: {total}")
    return catalog


# =============================================================================
# 6. 단일 셀 평가
# =============================================================================

def evaluate_signal_cell(
    pool_df: pd.DataFrame,   # 해당 universe pool × 해당 국면 dates의 merged df
    signal_fn,
    fwd_col: str,            # 버킷 horizon
    regime: str,
) -> dict:
    """
    pool_df: prices + fwd가 조인된 df, regime 필터 적용 완료.
    signal_fn: boolean mask 반환 callable.
    fwd_col: forward return 컬럼명 (평가용).

    Returns dict: mean, std, win_rate, lift, n, IS_mean, OOS_mean, IS_OOS_diff, PASS
    """
    try:
        sig_mask = signal_fn(pool_df)
        sig_mask = sig_mask.fillna(False).astype(bool)
    except Exception:
        return {"mean": np.nan, "std": np.nan, "win_rate": np.nan,
                "lift": np.nan, "n": 0,
                "IS_mean": np.nan, "OOS_mean": np.nan, "IS_OOS_diff": np.nan, "PASS": False}

    sig_df  = pool_df[sig_mask]
    n       = len(sig_df)
    if n == 0 or fwd_col not in sig_df.columns:
        return {"mean": np.nan, "std": np.nan, "win_rate": np.nan,
                "lift": np.nan, "n": 0,
                "IS_mean": np.nan, "OOS_mean": np.nan, "IS_OOS_diff": np.nan, "PASS": False}

    fwd_vals = sig_df[fwd_col].dropna()
    if len(fwd_vals) < N_MIN:
        return {"mean": np.nan, "std": np.nan, "win_rate": np.nan,
                "lift": np.nan, "n": len(fwd_vals),
                "IS_mean": np.nan, "OOS_mean": np.nan, "IS_OOS_diff": np.nan, "PASS": False}

    # Baseline: 전체 pool의 fwd_col 평균 (시그널 없는 경우)
    baseline_fwd = pool_df[fwd_col].dropna()
    baseline_mean = baseline_fwd.mean() if len(baseline_fwd) > 0 else 0.0

    sig_mean = fwd_vals.mean()
    sig_std  = fwd_vals.std()
    win_rate = (fwd_vals > 0).mean()

    # Lift: signal mean / baseline mean (baseline이 0이면 NaN)
    if abs(baseline_mean) < 1e-8:
        lift = np.nan
    else:
        lift = sig_mean / baseline_mean

    # IS / OOS 분리
    is_mask  = sig_df["date"] < IS_CUTOFF
    oos_mask = sig_df["date"] >= IS_CUTOFF
    is_vals  = sig_df.loc[is_mask,  fwd_col].dropna()
    oos_vals = sig_df.loc[oos_mask, fwd_col].dropna()
    IS_mean  = is_vals.mean()  if len(is_vals)  >= 10 else np.nan
    OOS_mean = oos_vals.mean() if len(oos_vals) >= 10 else np.nan
    IS_OOS_diff = (IS_mean - OOS_mean) if (pd.notna(IS_mean) and pd.notna(OOS_mean)) else np.nan

    # 합격선 판정
    # lift >= LIFT_MIN AND IS >= 0 AND OOS >= 0 AND |IS_OOS_diff| < |IS_mean| AND n >= N_MIN
    pass_flag = (
        pd.notna(lift) and lift >= LIFT_MIN and
        pd.notna(IS_mean) and IS_mean > 0 and
        pd.notna(OOS_mean) and OOS_mean > 0 and
        pd.notna(IS_OOS_diff) and abs(IS_OOS_diff) < abs(IS_mean) * IS_OOS_DIFF_REL and
        len(fwd_vals) >= N_MIN
    )

    return {
        "mean":         float(sig_mean),
        "std":          float(sig_std),
        "win_rate":     float(win_rate),
        "lift":         float(lift) if pd.notna(lift) else np.nan,
        "n":            int(len(fwd_vals)),
        "IS_mean":      float(IS_mean)  if pd.notna(IS_mean)  else np.nan,
        "OOS_mean":     float(OOS_mean) if pd.notna(OOS_mean) else np.nan,
        "IS_OOS_diff":  float(IS_OOS_diff) if pd.notna(IS_OOS_diff) else np.nan,
        "PASS":         bool(pass_flag),
    }


# =============================================================================
# 7. 메인 루프
# =============================================================================

def main():
    t_global = time.time()
    print("=" * 70)
    print("P2B Signal Multiverse — 시작")
    print("=" * 70)

    # ── 데이터 로드 ────────────────────────────────────────────────────────────
    filters_df, fwd, seg, prices = load_data()

    # ── 전처리 ────────────────────────────────────────────────────────────────
    print("\n[전처리]")
    date_to_regime = build_regime_date_map(seg)
    prices = compute_signal_features(prices)
    prices = assign_regime_to_prices(prices, date_to_regime)
    fwd["regime"] = fwd["date"].map(date_to_regime)
    # fwd와 prices 조인 (stock_code + date)
    print("  prices + fwd 조인 중...")
    merged = prices.merge(
        fwd[["stock_code", "date",
             "fwd_1d", "fwd_3d", "fwd_5d", "fwd_10d", "fwd_20d", "fwd_30d", "fwd_60d"]],
        on=["stock_code", "date"],
        how="inner",
    )
    merged = merged.dropna(subset=["regime"])
    print(f"  merged shape: {merged.shape}")

    # ── Universe pools ─────────────────────────────────────────────────────────
    print("\n[Universe pools 구성]")
    pools = build_universe_pools(filters_df, TOP_N_PER_REGIME)

    # ── 시그널 카탈로그 ────────────────────────────────────────────────────────
    print("\n[시그널 카탈로그 빌드]")
    catalog = build_signal_catalog()

    # ── 총 셀 수 계산 ──────────────────────────────────────────────────────────
    total_cells = len(pools) * sum(len(catalog[b]) for b in ["swing", "mid", "position"])
    print(f"\n총 평가 셀: {len(pools)} pools × {sum(len(catalog[b]) for b in ['swing','mid','position'])} signals = {total_cells:,}")

    # ── 체크포인트 로드 ────────────────────────────────────────────────────────
    results = []
    done_keys = set()
    if os.path.exists(OUT_CKPT):
        print(f"  체크포인트 발견 → 재개: {OUT_CKPT}")
        prev = pd.read_csv(OUT_CKPT)
        results = prev.to_dict("records")
        for r in results:
            done_keys.add((r["regime"], r["pool_rank"], r["bucket"], r["family"], str(r["params"])))
        print(f"  기존 {len(results)} 셀 로드 완료.")

    # ── 평가 루프 ──────────────────────────────────────────────────────────────
    cell_count = 0
    pass_count = 0
    t_chunk    = time.time()

    for pool_idx, pool in enumerate(pools):
        regime   = pool["regime"]
        pool_rank = pool["pool_rank"]

        # pool에 해당하는 데이터 추출
        pool_mask    = apply_universe_filter(merged, pool)
        pool_df      = merged[pool_mask].copy()

        if len(pool_df) < N_MIN:
            print(f"  [SKIP] pool {pool_idx+1}/{len(pools)} {regime} rank{pool_rank}: n={len(pool_df)} < {N_MIN}")
            continue

        for bucket, signals in catalog.items():
            fwd_col = BUCKET_HORIZONS[bucket]

            for sig in signals:
                family     = sig["family"]
                params     = sig["params"]
                params_str = str(params)
                key        = (regime, pool_rank, bucket, family, params_str)

                if key in done_keys:
                    cell_count += 1
                    continue

                # 평가
                result = evaluate_signal_cell(pool_df, sig["fn"], fwd_col, regime)

                row = {
                    "regime":     regime,
                    "pool_rank":  pool_rank,
                    "cell_idx":   pool["cell_idx"],
                    "bucket":     bucket,
                    "universe_pool": f"{regime}_rank{pool_rank}",
                    "family":     family,
                    "params":     params_str,
                    "mean":       result["mean"],
                    "std":        result["std"],
                    "win_rate":   result["win_rate"],
                    "lift":       result["lift"],
                    "n":          result["n"],
                    "IS_mean":    result["IS_mean"],
                    "OOS_mean":   result["OOS_mean"],
                    "IS_OOS_diff": result["IS_OOS_diff"],
                    "PASS":       result["PASS"],
                }
                results.append(row)
                done_keys.add(key)
                cell_count += 1
                if result["PASS"]:
                    pass_count += 1

                # 진행 로그
                if cell_count % 200 == 0:
                    pct = cell_count / total_cells * 100
                    elapsed = time.time() - t_chunk
                    eta_sec = elapsed / max(cell_count, 1) * (total_cells - cell_count)
                    print(f"  [{cell_count:,}/{total_cells:,} {pct:.1f}%] "
                          f"pool={pool_idx+1} {regime} rank{pool_rank} "
                          f"bucket={bucket} family={family} "
                          f"pass={pass_count} ETA={eta_sec/60:.1f}min")

                # 체크포인트 저장
                if cell_count % CHECKPOINT_EVERY == 0 and results:
                    pd.DataFrame(results).to_csv(OUT_CKPT, index=False)
                    print(f"  [CKPT] {cell_count:,} 셀 저장 ({time.time()-t_global:.0f}s 경과)")

    # ── 최종 저장 ──────────────────────────────────────────────────────────────
    print("\n[결과 저장]")
    if not results:
        print("  결과 없음.")
        return

    df_all  = pd.DataFrame(results)
    df_pass = df_all[df_all["PASS"] == True].copy()

    df_all.to_csv(OUT_ALL,  index=False)
    df_pass.to_csv(OUT_PASS, index=False)
    print(f"  전체: {len(df_all):,} 셀 → {OUT_ALL}")
    print(f"  합격: {len(df_pass):,} 셀 → {OUT_PASS}")

    # 체크포인트 삭제 (완료)
    if os.path.exists(OUT_CKPT):
        os.remove(OUT_CKPT)

    # ── 리포트 생성 ────────────────────────────────────────────────────────────
    generate_top_signals_report(df_all, df_pass)
    generate_summary_report(df_all, df_pass, time.time() - t_global)

    print(f"\n완료! 총 {cell_count:,} 셀, 합격 {pass_count} 셀, 소요 {(time.time()-t_global)/60:.1f}분")


# =============================================================================
# 8. 리포트 생성
# =============================================================================

def generate_top_signals_report(df_all: pd.DataFrame, df_pass: pd.DataFrame):
    """6 국면 × 3 버킷 = 18 매트릭스, 각 Top 5 시그널."""
    lines = ["# Phase 2B — 국면 × 버킷 Top 시그널 매트릭스\n",
             f"생성일: 2026-05-24\n",
             f"전체 평가: {len(df_all):,} 셀 | 합격: {len(df_pass):,} 셀\n",
             ""]

    buckets = ["swing", "mid", "position"]
    bucket_labels = {"swing": "스윙 (3d 청산)", "mid": "미드 (20d 청산)", "position": "포지션 (60d 청산)"}

    for regime in REGIMES_6:
        for bucket in buckets:
            sub = df_all[(df_all["regime"] == regime) & (df_all["bucket"] == bucket)].copy()
            lines.append(f"## {regime} × {bucket_labels[bucket]}")
            if len(sub) == 0:
                lines.append("_데이터 없음_\n")
                continue
            sub_sorted = sub.dropna(subset=["lift"]).nlargest(5, "lift")
            if len(sub_sorted) == 0:
                lines.append("_유효 시그널 없음_\n")
                continue
            lines.append("")
            lines.append("| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |")
            lines.append("|------|--------|--------|------|---------|----------|---|------|")
            for i, (_, row) in enumerate(sub_sorted.iterrows(), 1):
                pass_str = "**PASS**" if row["PASS"] else "-"
                is_m  = f"{row['IS_mean']:.4f}"  if pd.notna(row["IS_mean"])  else "N/A"
                oos_m = f"{row['OOS_mean']:.4f}" if pd.notna(row["OOS_mean"]) else "N/A"
                lift  = f"{row['lift']:.3f}"      if pd.notna(row["lift"])     else "N/A"
                lines.append(f"| {i} | {row['family']} | {row['params']} | {lift} | {is_m} | {oos_m} | {int(row['n'])} | {pass_str} |")
            lines.append("")

    with open(OUT_TOP_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Top 시그널 매트릭스 → {OUT_TOP_MD}")


def generate_summary_report(df_all: pd.DataFrame, df_pass: pd.DataFrame, elapsed: float):
    """한 장 요약 + Stage C 진입 판단."""
    total_cells = len(df_all)
    pass_cells  = len(df_pass)
    pass_rate   = pass_cells / total_cells * 100 if total_cells > 0 else 0

    # IS 강 OOS 약 비율
    valid = df_all.dropna(subset=["IS_mean", "OOS_mean"])
    is_strong_oos_weak = valid[(valid["IS_mean"] > 0.01) & (valid["OOS_mean"] < 0)].shape[0]
    is_strong_oos_weak_pct = is_strong_oos_weak / len(valid) * 100 if len(valid) > 0 else 0

    # bull_high_vol × position Top 3
    bhv_pos = df_all[
        (df_all["regime"] == "BULL_HIGH_VOL") &
        (df_all["bucket"] == "position")
    ].copy().dropna(subset=["lift"]).nlargest(3, "lift")

    # 18 매트릭스별 합격 수
    matrix_stats = {}
    buckets = ["swing", "mid", "position"]
    for regime in REGIMES_6:
        for bucket in buckets:
            sub = df_pass[(df_pass["regime"] == regime) & (df_pass["bucket"] == bucket)]
            matrix_stats[f"{regime}×{bucket}"] = len(sub)

    # Stage C 진입 판단
    # 각 (regime, bucket) 조합에서 5~10개 시그널 목표
    combo_ok = sum(1 for v in matrix_stats.values() if v >= 3)
    stage_c_ok = "OK" if pass_cells >= 50 and combo_ok >= 9 else "NG"

    lines = [
        "# Phase 2B 요약 — 시그널 멀티버스 결과",
        "",
        f"생성일: 2026-05-24",
        f"소요: {elapsed/60:.1f}분",
        "",
        "## 처리 결과",
        f"- 전체 평가 셀: **{total_cells:,}**",
        f"- 합격 셀: **{pass_cells}** ({pass_rate:.1f}%)",
        f"- 합격선: lift ≥ {LIFT_MIN} AND IS > 0 AND OOS > 0 AND |IS_OOS_diff| < |IS_mean| AND n ≥ {N_MIN}",
        "",
        "## 18 매트릭스 합격 수 (6 국면 × 3 버킷)",
        "",
        "| 국면\\버킷 | 스윙 | 미드 | 포지션 |",
        "|-----------|------|------|--------|",
    ]

    for regime in REGIMES_6:
        sw  = matrix_stats.get(f"{regime}×swing",    0)
        mid = matrix_stats.get(f"{regime}×mid",      0)
        pos = matrix_stats.get(f"{regime}×position", 0)
        lines.append(f"| {regime} | {sw} | {mid} | {pos} |")

    lines += [
        "",
        "## BULL_HIGH_VOL × Position 최강 시그널 Top 3",
        "",
        "| rank | family | params | lift | IS_mean | OOS_mean | n |",
        "|------|--------|--------|------|---------|----------|---|",
    ]

    for i, (_, row) in enumerate(bhv_pos.iterrows(), 1):
        is_m  = f"{row['IS_mean']:.4f}"  if pd.notna(row["IS_mean"])  else "N/A"
        oos_m = f"{row['OOS_mean']:.4f}" if pd.notna(row["OOS_mean"]) else "N/A"
        lift  = f"{row['lift']:.3f}"      if pd.notna(row["lift"])     else "N/A"
        lines.append(f"| {i} | {row['family']} | {row['params']} | {lift} | {is_m} | {oos_m} | {int(row['n'])} |")

    lines += [
        "",
        "## IS/OOS 정합 분석",
        f"- IS 강(>1%) OOS 약(<0%) 시그널 비율: **{is_strong_oos_weak_pct:.1f}%** ({is_strong_oos_weak}/{len(valid)})",
        f"- 과적합 위험: {'높음' if is_strong_oos_weak_pct > 30 else '보통' if is_strong_oos_weak_pct > 15 else '낮음'}",
        "",
        "## Stage C 진입 판단",
        f"- **{stage_c_ok}** — 합격 셀 {pass_cells}개, 조합 커버 {combo_ok}/18",
        "",
        "### 판정 기준",
        "- OK: 합격 셀 ≥ 50 AND (regime, bucket) 조합 커버 ≥ 9/18",
        "- NG: 위 기준 미달 → 합격선 완화 또는 시그널 family 보강 필요",
    ]

    with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  요약 보고서 → {OUT_SUMMARY}")


# =============================================================================
# 진입점
# =============================================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[중단] Ctrl+C 감지. 체크포인트는 보존됩니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] {e}")
        traceback.print_exc()
        sys.exit(1)
