"""
p2a_universe_filter.py — Stage A: 6-regime LHS Universe Filter Grid
=====================================================================
사장님 결재 2026-05-24:
  6 국면 × LHS 300셀 × 3 버킷 = 5,400 평가
  국면별 최적 universe 필터 발굴

대원칙:
  - PIT 강제: 모든 필터는 T-1 cross-section 기준
  - 전체기간 통합 분위 금지
  - 중간 체크포인트 1,000셀마다 저장

실행:
  python RoboTrader_template/scripts/10pct_strategy/p2a_universe_filter.py
"""

import sys
import os
import time
import warnings
import traceback

# Force UTF-8 output on Windows (cp949 console cannot encode Korean/special chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import psycopg2
from scipy.stats import qmc

# ── 경로 설정 ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "10pct_strategy")
os.makedirs(REPORT_DIR, exist_ok=True)

# ── 출력 파일 ─────────────────────────────────────────────────────────────────
OUT_ALL     = os.path.join(REPORT_DIR, "phase2a_filter_grid_all.csv")
OUT_PASS    = os.path.join(REPORT_DIR, "phase2a_filter_passed.csv")
OUT_TOP     = os.path.join(REPORT_DIR, "phase2a_top_filters_by_regime.md")
OUT_UNIV    = os.path.join(REPORT_DIR, "phase2a_universal_filters.md")
OUT_SUMMARY = os.path.join(REPORT_DIR, "phase2a_summary.md")

# ── 하이퍼파라미터 ────────────────────────────────────────────────────────────
N_LHS_PER_REGIME = 300          # 국면당 LHS 셀 수
PASS_LIFT_MIN    = 1.10         # lift 합격선
PASS_VAR_MAX     = 1.30         # 분산 비율 합격선
PASS_N_MIN       = 1000         # 최소 stock-day 수
CHECKPOINT_EVERY = 1000         # 셀마다 중간 저장

# ── 3 버킷 ────────────────────────────────────────────────────────────────────
BUCKETS = {
    "swing":    "fwd_5d",
    "mid":      "fwd_20d",
    "position": "fwd_60d",
}

# ── 6 국면 ────────────────────────────────────────────────────────────────────
REGIMES_6 = [
    "BULL_HIGH_VOL",
    "BULL_LOW_VOL",
    "BEAR_HIGH_VOL",
    "BEAR_LOW_VOL",
    "SIDEWAYS_HIGH_VOL",
    "SIDEWAYS_LOW_VOL",
]

# ── 11 차원 변수 그리드 ────────────────────────────────────────────────────────
PARAM_GRID = {
    "mcap_cutoff_top_n":      [100, 200, 300, 500, 1000, 2000],
    "min_trading_value":      [5e8, 1e9, 3e9, 5e9, 1e10],       # 원
    "trading_value_lookback": [5, 20, 60],                        # 일
    "market":                 ["KOSPI", "KOSDAQ", "both"],
    "sector_exclude":         ["none", "financial", "utility", "financial+utility"],
    "min_price":              [1000, 5000, 10000],                # 원
    "min_liquidity_90d":      [0.70, 0.80, 0.90],                # 거래일 비율
    "vol_quintile":           [1, 2, 3, 4, 5, 0],                # 0=전체
    "index_membership":       ["all"],                            # 데이터 없음 → 전체만
    "candle_health":          [0.40, 0.50, 0.60, None],          # 양봉비율 ≥ x / None=무필터
    "candle_trend":           [4, 5, None],                      # 마루보즈 분위 Q4/Q5 / None
}

PARAM_KEYS = list(PARAM_GRID.keys())
PARAM_VALUES = [PARAM_GRID[k] for k in PARAM_KEYS]


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────────────────────────────────────

def load_data():
    t0 = time.time()
    print("[1/5] forward returns 로드 중...")
    fwd = pd.read_parquet(os.path.join(REPORT_DIR, "phase1_forward_returns.parquet"))
    fwd["date"] = pd.to_datetime(fwd["date"])
    print(f"  fwd: {fwd.shape}, {fwd['date'].min().date()} ~ {fwd['date'].max().date()}")

    print("[2/5] regime segments 로드 중...")
    seg = pd.read_csv(os.path.join(REPORT_DIR, "phase0_regime_segments.csv"))
    seg = seg[seg["index_code"] == "KOSPI"].copy()   # KOSPI 기준 국면 사용
    seg["start_date"] = pd.to_datetime(seg["start_date"])
    seg["end_date"]   = pd.to_datetime(seg["end_date"])
    print(f"  seg (KOSPI): {len(seg)} segments, labels: {seg['label_6'].unique().tolist()}")

    print("[3/5] DB에서 daily_prices 로드 중 (mcap/trading_value/close/ohlc)...")
    conn = psycopg2.connect(
        host="127.0.0.1", port=5433, dbname="robotrader_quant",
        user="robotrader", password="1234"
    )
    query = """
        SELECT stock_code,
               date::text AS date,
               close,
               open,
               high,
               low,
               volume,
               trading_value,
               market_cap
        FROM daily_prices
        WHERE close > 0
          AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        ORDER BY stock_code, date
    """
    prices = pd.read_sql(query, conn)
    conn.close()
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    prices = prices.dropna(subset=["date"])
    # market_cap proxy: close * volume when market_cap = 0
    prices["market_cap_eff"] = np.where(
        prices["market_cap"] > 0,
        prices["market_cap"],
        prices["close"] * prices["volume"]
    )
    print(f"  prices: {prices.shape}")

    print("[4/5] stock_info (market 분류) 로드 중...")
    conn2 = psycopg2.connect(
        host="127.0.0.1", port=5433, dbname="strategy_analysis",
        user="postgres", password="1234"
    )
    mkt_df = pd.read_sql("SELECT stock_code, market FROM stock_info", conn2)
    conn2.close()
    # stock_sector의 market은 KOSPI만 있어서 stock_info 우선
    # stock_sector에 있는 KOSDAQ을 찾기 위해 stock_code 6자리 규칙도 보완
    mkt_map = dict(zip(mkt_df["stock_code"], mkt_df["market"]))
    # 종목코드 6자리: KOSDAQ은 보통 0으로 시작하지 않는 경우 있으나
    # stock_info가 가장 신뢰할 수 있는 소스
    print(f"  stock_info: {len(mkt_map)} 종목, markets: {mkt_df['market'].value_counts().to_dict()}")

    print("[5/5] stock_sector (섹터) 로드 중...")
    conn3 = psycopg2.connect(
        host="127.0.0.1", port=5433, dbname="strategy_analysis",
        user="postgres", password="1234",
        options="-c client_encoding=utf8"
    )
    sector_df = pd.read_sql(
        "SELECT stock_code, sector_name FROM stock_sector", conn3,
    )
    conn3.close()
    # sector_name이 깨진 경우가 있으므로 bytes→utf8 재디코딩 시도
    def try_decode(v):
        if isinstance(v, bytes):
            try:
                return v.decode("utf-8")
            except Exception:
                return ""
        return v
    sector_df["sector_name"] = sector_df["sector_name"].apply(try_decode)
    sector_map = dict(zip(sector_df["stock_code"], sector_df["sector_name"]))
    print(f"  sector_map: {len(sector_map)} 종목")

    elapsed = time.time() - t0
    print(f"  데이터 로드 완료 ({elapsed:.1f}s)")
    return fwd, seg, prices, mkt_map, sector_map


# ─────────────────────────────────────────────────────────────────────────────
# 전처리: fwd에 regime label 조인 + prices에서 PIT 피처 계산
# ─────────────────────────────────────────────────────────────────────────────

def assign_regime_labels(fwd: pd.DataFrame, seg: pd.DataFrame) -> pd.DataFrame:
    """fwd 각 행(stock_code, date)에 regime label 부여."""
    print("  regime label 조인 중...")
    # date → label_6 매핑 (날짜 범위)
    # 각 segment: start_date ~ end_date (inclusive)
    date_to_regime = {}
    for _, row in seg.iterrows():
        dates = pd.date_range(row["start_date"], row["end_date"], freq="B")
        for d in dates:
            date_to_regime[d] = row["label_6"]

    fwd["regime"] = fwd["date"].map(date_to_regime)
    n_mapped = fwd["regime"].notna().sum()
    print(f"  regime 매핑: {n_mapped:,}/{len(fwd):,} 행 ({n_mapped/len(fwd)*100:.1f}%)")
    # regime 없는 날짜(세그먼트 공백)는 제외
    fwd = fwd.dropna(subset=["regime"]).copy()
    return fwd


def compute_pit_features(prices: pd.DataFrame) -> pd.DataFrame:
    """
    PIT 피처 계산 (T-1 값이 T 날의 필터로 사용됨):
    - mcap_rank_t1: T-1 시점 시총 rank (cross-section)
    - tv_5d_t1, tv_20d_t1, tv_60d_t1: T-1까지 lookback 일평균 거래대금
    - price_t1: T-1 종가
    - liq_90d_t1: 최근 90거래일 중 거래 있는 날 비율
    - vol_quintile_t1: T-1 cross-section 변동성 분위
    - bullish_ratio_20d_t1: 최근 20일 양봉 비율 (T-1 기준)
    - marubozu_ratio_60d_t1: 최근 60일 마루보즈 양봉 비율 (T-1 기준)
    """
    print("  PIT 피처 계산 중 (그룹별 shift)...")
    prices = prices.sort_values(["stock_code", "date"]).copy()
    g = prices.groupby("stock_code", sort=False)

    # T-1 가격 (PIT)
    prices["price_t1"] = g["close"].shift(1)

    # T-1 시총 (PIT)
    prices["mcap_t1"] = g["market_cap_eff"].shift(1)

    # 거래대금 rolling 평균 (T-1 기준: shift(1) 후 rolling)
    # shift(1)로 T-1을 현재로 만든 뒤 rolling
    tv_s1 = g["trading_value"].shift(1)
    prices["tv_5d_t1"]  = g["trading_value"].shift(1).groupby(prices["stock_code"]).transform(
        lambda x: x.rolling(5,  min_periods=1).mean()
    )
    prices["tv_20d_t1"] = g["trading_value"].shift(1).groupby(prices["stock_code"]).transform(
        lambda x: x.rolling(20, min_periods=1).mean()
    )
    prices["tv_60d_t1"] = g["trading_value"].shift(1).groupby(prices["stock_code"]).transform(
        lambda x: x.rolling(60, min_periods=1).mean()
    )

    # 유동성: 최근 90거래일 중 거래일 비율 (trading_value > 0)
    prices["traded_flag"] = (prices["trading_value"] > 0).astype(float)
    prices["liq_90d_t1"] = g["traded_flag"].shift(1).groupby(prices["stock_code"]).transform(
        lambda x: x.rolling(90, min_periods=1).mean()
    )

    # 변동성 (volatility_20d는 DB에 없으므로 returns로 계산)
    # returns_1d = close/close.shift(1) - 1
    prices["ret1d"] = g["close"].pct_change()
    prices["vol_20d_t1"] = g["ret1d"].shift(1).groupby(prices["stock_code"]).transform(
        lambda x: x.rolling(20, min_periods=5).std()
    )

    # 양봉 비율: close >= open
    prices["is_bullish"] = (prices["close"] >= prices["open"]).astype(float)
    prices["bullish_ratio_20d_t1"] = g["is_bullish"].shift(1).groupby(prices["stock_code"]).transform(
        lambda x: x.rolling(20, min_periods=5).mean()
    )

    # 마루보즈 양봉: close/high >= 0.98 AND open/low >= 0.98 (윗꼬리/아랫꼬리 거의 없음)
    wick_tol = 0.98
    prices["is_marubozu_bull"] = (
        (prices["close"] >= prices["open"]) &
        (prices["close"] / prices["high"].replace(0, np.nan) >= wick_tol) &
        (prices["open"] / prices["low"].replace(0, np.nan)  >= wick_tol)
    ).astype(float)
    prices["marubozu_ratio_60d_t1"] = g["is_marubozu_bull"].shift(1).groupby(prices["stock_code"]).transform(
        lambda x: x.rolling(60, min_periods=10).mean()
    )

    print(f"  PIT 피처 계산 완료. prices shape: {prices.shape}")
    return prices


def compute_cross_section_ranks(prices: pd.DataFrame) -> pd.DataFrame:
    """날짜별 cross-section rank (mcap, vol) — PIT."""
    print("  날짜별 cross-section rank 계산 중...")
    # mcap_rank: 날짜별 내림차순 rank (1 = 최대 시총)
    prices["mcap_rank_t1"] = prices.groupby("date")["mcap_t1"].rank(
        ascending=False, method="first", na_option="bottom"
    )
    # vol quintile: 날짜별 5분위 (1=저변동성, 5=고변동성)
    def quintile_rank(s):
        pct = s.rank(pct=True, na_option="keep")
        bins = [-1e-10, 0.2, 0.4, 0.6, 0.8, 1.0]
        labels = [1, 2, 3, 4, 5]
        return pd.cut(pct, bins=bins, labels=labels).astype("Int64")

    prices["vol_quintile_t1"] = prices.groupby("date")["vol_20d_t1"].transform(quintile_rank)
    # marubozu quintile (for candle_trend filter)
    prices["marubozu_quintile_t1"] = prices.groupby("date")["marubozu_ratio_60d_t1"].transform(quintile_rank)
    print("  cross-section rank 완료.")
    return prices


# ─────────────────────────────────────────────────────────────────────────────
# 필터 함수
# ─────────────────────────────────────────────────────────────────────────────

def apply_filter(merged: pd.DataFrame, params: dict,
                 mkt_map: dict, sector_map: dict) -> pd.Series:
    """params 조합에 따라 boolean mask 반환."""
    mask = pd.Series(True, index=merged.index)

    # 1. mcap_cutoff_top_n: T-1 시총 상위 N 종목
    top_n = params["mcap_cutoff_top_n"]
    mask &= (merged["mcap_rank_t1"] <= top_n)

    # 2. min_trading_value + lookback
    lb = params["trading_value_lookback"]
    min_tv = params["min_trading_value"]
    tv_col = f"tv_{lb}d_t1"
    mask &= (merged[tv_col] >= min_tv)

    # 3. market
    mkt = params["market"]
    if mkt != "both":
        codes = merged["stock_code"]
        mkt_series = codes.map(lambda c: mkt_map.get(c, "UNKNOWN"))
        mask &= (mkt_series == mkt)

    # 4. sector_exclude
    se = params["sector_exclude"]
    if se != "none":
        excl_keywords = []
        if "financial" in se:
            excl_keywords += ["보험", "증권", "은행", "금융", "Financial", "Insurance", "Bank"]
        if "utility" in se:
            excl_keywords += ["전기", "가스", "유틸", "Utility"]
        if excl_keywords:
            def in_excl(code):
                sname = sector_map.get(code, "")
                if not sname:
                    return False
                for kw in excl_keywords:
                    if kw in sname:
                        return True
                return False
            excl_mask = merged["stock_code"].map(in_excl)
            mask &= ~excl_mask

    # 5. min_price
    mask &= (merged["price_t1"] >= params["min_price"])

    # 6. min_liquidity_90d
    mask &= (merged["liq_90d_t1"] >= params["min_liquidity_90d"])

    # 7. vol_quintile (0 = 전체)
    vq = params["vol_quintile"]
    if vq != 0:
        mask &= (merged["vol_quintile_t1"] == vq)

    # 8. index_membership — 데이터 없음, 전체만 지원
    # params["index_membership"] == "all" → no filter

    # 9. candle_health: 20일 양봉비율
    ch = params["candle_health"]
    if ch is not None:
        mask &= (merged["bullish_ratio_20d_t1"] >= ch)

    # 10. candle_trend: 마루보즈 분위 Q4/Q5
    ct = params["candle_trend"]
    if ct is not None:
        mask &= (merged["marubozu_quintile_t1"] >= ct)

    return mask


# ─────────────────────────────────────────────────────────────────────────────
# LHS 샘플링
# ─────────────────────────────────────────────────────────────────────────────

def lhs_sample(n: int, seed: int = 42) -> list[dict]:
    """11차원 LHS로 n개 파라미터 조합 샘플링."""
    # index_membership은 항상 "all" → 10차원만 실질 샘플링
    active_keys = [k for k in PARAM_KEYS if k != "index_membership"]
    active_vals = [PARAM_GRID[k] for k in active_keys]
    n_dims = len(active_keys)

    sampler = qmc.LatinHypercube(d=n_dims, seed=seed)
    sample = sampler.random(n=n)  # (n, n_dims) in [0, 1)

    cells = []
    for row in sample:
        cell = {"index_membership": "all"}
        for i, key in enumerate(active_keys):
            vals = active_vals[i]
            idx = int(row[i] * len(vals))
            idx = min(idx, len(vals) - 1)
            cell[key] = vals[idx]
        cells.append(cell)
    return cells


# ─────────────────────────────────────────────────────────────────────────────
# 평가 함수
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_cell(regime_data: pd.DataFrame, universe_stats: dict,
                  params: dict, mkt_map: dict, sector_map: dict) -> dict:
    """
    단일 셀(params) × 단일 국면의 3버킷 평가.
    Returns dict with bucket-level results.
    """
    mask = apply_filter(regime_data, params, mkt_map, sector_map)
    filtered = regime_data[mask]
    n_filtered = len(filtered)

    result = {}
    any_pass = False

    for bucket, fwd_col in BUCKETS.items():
        ret = filtered[fwd_col].dropna()
        n   = len(ret)
        if n == 0:
            result[f"{bucket}_mean"] = np.nan
            result[f"{bucket}_std"]  = np.nan
            result[f"{bucket}_wr"]   = np.nan
            result[f"{bucket}_lift"] = np.nan
            result[f"{bucket}_n"]    = 0
            result[f"{bucket}_pass"] = False
            continue

        mean_val = ret.mean()
        std_val  = ret.std()
        wr       = (ret > 0).mean()

        univ_mean = universe_stats[bucket]["mean"]
        univ_std  = universe_stats[bucket]["std"]

        lift = mean_val / univ_mean if (univ_mean != 0 and not np.isnan(univ_mean)) else np.nan
        var_ratio = (std_val**2) / (univ_std**2) if (univ_std > 0) else np.nan

        passed = (
            (not np.isnan(lift)) and lift >= PASS_LIFT_MIN and
            (not np.isnan(var_ratio)) and var_ratio <= PASS_VAR_MAX and
            n >= PASS_N_MIN
        )
        if passed:
            any_pass = True

        result[f"{bucket}_mean"] = round(mean_val, 6)
        result[f"{bucket}_std"]  = round(std_val,  6)
        result[f"{bucket}_wr"]   = round(wr,       4)
        result[f"{bucket}_lift"] = round(lift, 4) if not np.isnan(lift) else np.nan
        result[f"{bucket}_n"]    = n
        result[f"{bucket}_pass"] = passed

    result["n_filtered"] = n_filtered
    result["any_pass"]   = any_pass
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 국면별 universe 통계 (baseline)
# ─────────────────────────────────────────────────────────────────────────────

def compute_universe_stats(regime_data: pd.DataFrame) -> dict:
    """국면 전체 데이터의 버킷별 mean/std."""
    stats = {}
    for bucket, fwd_col in BUCKETS.items():
        ret = regime_data[fwd_col].dropna()
        stats[bucket] = {
            "mean": ret.mean(),
            "std":  ret.std(),
            "n":    len(ret),
        }
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# 보고서 생성
# ─────────────────────────────────────────────────────────────────────────────

def make_reports(df_all: pd.DataFrame) -> None:
    # ── 합격 필터
    pass_cols = [c for c in df_all.columns if c.endswith("_pass")]
    df_all["any_pass"] = df_all[pass_cols].any(axis=1)
    df_pass = df_all[df_all["any_pass"]].copy()
    df_pass.to_csv(OUT_PASS, index=False)
    print(f"  합격 필터: {len(df_pass)} / {len(df_all)} 셀 → {OUT_PASS}")

    # ── Top 5 필터 by regime (swing lift 기준)
    lines = ["# Phase 2A: 국면별 Top 5 필터\n"]
    for regime in REGIMES_6:
        sub = df_all[df_all["regime"] == regime].copy()
        sub_valid = sub[sub["swing_n"] >= PASS_N_MIN].copy()
        sub_valid = sub_valid.sort_values("swing_lift", ascending=False).head(5)
        lines.append(f"\n## {regime} (n_cells={len(sub)}, valid_n={len(sub_valid)})\n")
        if sub_valid.empty:
            lines.append("합격 셀 없음\n")
            continue
        param_cols = PARAM_KEYS
        for rank, (_, row) in enumerate(sub_valid.iterrows(), 1):
            params_str = " | ".join(f"{k}={row[k]}" for k in param_cols)
            lines.append(
                f"{rank}. swing_lift={row['swing_lift']:.3f} "
                f"mid_lift={row['mid_lift']:.3f} "
                f"pos_lift={row['position_lift']:.3f} "
                f"n={row['swing_n']:.0f}\n"
                f"   {params_str}\n"
            )
    with open(OUT_TOP, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"  Top 필터 보고서 → {OUT_TOP}")

    # ── 범용 필터: 모든 국면에서 swing_lift > 0
    lines_univ = ["# Phase 2A: 범용 필터 (모든 국면 양수)\n\n"]
    regime_lift_dfs = {}
    for regime in REGIMES_6:
        sub = df_all[df_all["regime"] == regime][PARAM_KEYS + ["swing_lift"]].copy()
        sub = sub.rename(columns={"swing_lift": f"lift_{regime}"})
        regime_lift_dfs[regime] = sub

    # cell_id로 교차 (regime별 동일 params → 범용)
    # params를 문자열 키로 merge
    df_all["_param_key"] = df_all[PARAM_KEYS].astype(str).apply(
        lambda r: "|".join(r.values), axis=1
    )
    regime_groups = df_all.groupby(["_param_key", "regime"])["swing_lift"].mean().unstack("regime")
    if regime_groups.shape[1] == len(REGIMES_6):
        # 모든 국면에서 lift > 0
        universal = regime_groups[(regime_groups > 0).all(axis=1)]
        if len(universal) > 0:
            lines_univ.append(f"총 {len(universal)}개 범용 필터 발견\n\n")
            for pk, row in universal.sort_values(
                universal.columns.tolist(), ascending=False
            ).head(10).iterrows():
                lines_univ.append(f"params: {pk}\n")
                for col in row.index:
                    lines_univ.append(f"  {col}: lift={row[col]:.3f}\n")
                lines_univ.append("\n")
        else:
            lines_univ.append("모든 국면에서 lift>0인 범용 필터 없음\n")
    else:
        lines_univ.append(f"일부 국면 누락 ({regime_groups.columns.tolist()}), 범용 분석 스킵\n")

    with open(OUT_UNIV, "w", encoding="utf-8") as f:
        f.writelines(lines_univ)
    print(f"  범용 필터 보고서 → {OUT_UNIV}")

    # ── Summary
    n_total  = len(df_all)
    n_passed = len(df_pass)
    lines_sum = ["# Phase 2A Summary\n\n"]
    lines_sum.append(f"- 총 평가 셀: {n_total}\n")
    lines_sum.append(f"- 합격 셀 (any_pass): {n_passed} ({n_passed/n_total*100:.1f}%)\n\n")
    lines_sum.append("## 국면별 합격 수\n")
    for regime in REGIMES_6:
        sub = df_pass[df_pass["regime"] == regime]
        sub_all = df_all[df_all["regime"] == regime]
        lines_sum.append(f"- {regime}: {len(sub)} / {len(sub_all)} 셀 합격\n")
    lines_sum.append("\n## bull_high_vol lift≥1.5 필터\n")
    bhv = df_all[df_all["regime"] == "BULL_HIGH_VOL"]
    lift15 = bhv[bhv["swing_lift"] >= 1.5]
    if len(lift15) > 0:
        lines_sum.append(f"lift ≥ 1.5 필터 존재: {len(lift15)}개\n")
        lines_sum.append("Stage B 진입 가능: **OK**\n")
    else:
        lines_sum.append("lift ≥ 1.5 필터 없음\n")
        best_bhv_lift = bhv["swing_lift"].max() if len(bhv) > 0 else np.nan
        lines_sum.append(f"  (최대 swing_lift: {best_bhv_lift:.3f})\n")
        lines_sum.append("Stage B 진입 가능: **조건부** (lift≥1.10 합격 셀 기준)\n")

    stage_b_ok = n_passed > 0
    lines_sum.append(f"\n## Stage B 진입 판단\n")
    lines_sum.append(f"{'OK' if stage_b_ok else 'NG'} — 합격 셀 {n_passed}개 존재\n")

    with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
        f.writelines(lines_sum)
    print(f"  Summary → {OUT_SUMMARY}")


# ─────────────────────────────────────────────────────────────────────────────
# TV rolling 계산: groupby.transform 대신 직접 계산 (성능)
# ─────────────────────────────────────────────────────────────────────────────

def compute_tv_rolling(prices: pd.DataFrame) -> pd.DataFrame:
    """trading_value rolling 평균 (PIT: shift(1) 후 rolling)."""
    prices = prices.sort_values(["stock_code", "date"]).copy()
    for lb in [5, 20, 60]:
        col = f"tv_{lb}d_t1"
        prices[col] = (
            prices.groupby("stock_code")["trading_value"]
            .transform(lambda s: s.shift(1).rolling(lb, min_periods=1).mean())
        )
    return prices


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t_start = time.time()
    print("=" * 70)
    print("p2a_universe_filter.py -- 6 regime x LHS 300 cells x 3 buckets = 5,400 evals")
    print("=" * 70)

    # 1. 데이터 로드
    fwd, seg, prices, mkt_map, sector_map = load_data()

    # 2. TV rolling 피처
    print("[전처리] TV rolling 계산 중...")
    prices = compute_tv_rolling(prices)

    # 3. 나머지 PIT 피처
    print("[전처리] 나머지 PIT 피처 계산 중...")
    prices = prices.sort_values(["stock_code", "date"]).copy()
    g = prices.groupby("stock_code", sort=False)

    prices["price_t1"]  = g["close"].shift(1)
    prices["mcap_t1"]   = g["market_cap_eff"].shift(1)

    prices["traded_flag"] = (prices["trading_value"] > 0).astype(float)
    prices["liq_90d_t1"]  = g["traded_flag"].transform(
        lambda s: s.shift(1).rolling(90, min_periods=1).mean()
    )

    prices["ret1d"] = g["close"].transform(lambda s: s.pct_change())
    prices["vol_20d_t1"] = g["ret1d"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=5).std()
    )

    prices["is_bullish"] = (prices["close"] >= prices["open"]).astype(float)
    prices["bullish_ratio_20d_t1"] = g["is_bullish"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=5).mean()
    )

    wick_tol = 0.98
    prices["is_marubozu_bull"] = (
        (prices["close"] >= prices["open"]) &
        (prices["close"] / prices["high"].replace(0, np.nan) >= wick_tol) &
        (prices["open"]  / prices["low"].replace(0, np.nan)  >= wick_tol)
    ).astype(float)
    prices["marubozu_ratio_60d_t1"] = g["is_marubozu_bull"].transform(
        lambda s: s.shift(1).rolling(60, min_periods=10).mean()
    )

    # 4. Cross-section ranks
    print("[전처리] cross-section rank 계산 중...")
    prices["mcap_rank_t1"] = prices.groupby("date")["mcap_t1"].rank(
        ascending=False, method="first", na_option="bottom"
    )

    def quintile_rank(s):
        pct = s.rank(pct=True, na_option="keep")
        bins = [-1e-10, 0.2, 0.4, 0.6, 0.8, 1.0]
        labels = [1, 2, 3, 4, 5]
        result = pd.cut(pct, bins=bins, labels=labels)
        return result.astype("Int64")

    prices["vol_quintile_t1"] = prices.groupby("date")["vol_20d_t1"].transform(quintile_rank)
    prices["marubozu_quintile_t1"] = prices.groupby("date")["marubozu_ratio_60d_t1"].transform(quintile_rank)

    print(f"  prices 피처 완료. shape: {prices.shape}")

    # 5. fwd에 regime 조인
    print("[전처리] fwd에 regime label 조인 중...")
    fwd = assign_regime_labels(fwd, seg)

    # 6. fwd × prices merge (T-1 PIT 피처를 fwd의 T 날짜에 매핑)
    print("[전처리] fwd × prices merge 중...")
    pit_cols = [
        "stock_code", "date",
        "price_t1", "mcap_t1", "mcap_rank_t1",
        "tv_5d_t1", "tv_20d_t1", "tv_60d_t1",
        "liq_90d_t1", "vol_quintile_t1",
        "bullish_ratio_20d_t1", "marubozu_quintile_t1",
    ]
    pit_df = prices[pit_cols].copy()
    merged = fwd.merge(pit_df, on=["stock_code", "date"], how="inner")
    print(f"  merged shape: {merged.shape}")

    # 7. 국면별 데이터 분할 + universe stats
    regime_data_map = {}
    universe_stats_map = {}
    for regime in REGIMES_6:
        rd = merged[merged["regime"] == regime].copy()
        regime_data_map[regime] = rd
        universe_stats_map[regime] = compute_universe_stats(rd)
        print(f"  {regime}: {len(rd):,} 행, "
              f"swing_mean={universe_stats_map[regime]['swing']['mean']:.4f}, "
              f"n={universe_stats_map[regime]['swing']['n']:,}")

    # 8. LHS 샘플링 (국면당 300셀, 각 국면마다 다른 seed)
    print(f"\n[LHS] 국면당 {N_LHS_PER_REGIME}셀 샘플링 중...")
    regime_cells = {}
    for i, regime in enumerate(REGIMES_6):
        cells = lhs_sample(N_LHS_PER_REGIME, seed=42 + i * 100)
        regime_cells[regime] = cells
        print(f"  {regime}: {len(cells)} 셀")

    # 9. 평가 루프 (6 × 300 = 1,800 셀 × 3 버킷)
    print(f"\n[평가] 총 {len(REGIMES_6) * N_LHS_PER_REGIME} 셀 평가 시작...")
    all_results = []
    total_cells = len(REGIMES_6) * N_LHS_PER_REGIME
    cell_count = 0
    t_eval_start = time.time()

    for regime in REGIMES_6:
        rd = regime_data_map[regime]
        us = universe_stats_map[regime]
        cells = regime_cells[regime]

        for cell_idx, params in enumerate(cells):
            cell_count += 1
            try:
                res = evaluate_cell(rd, us, params, mkt_map, sector_map)
            except Exception as e:
                print(f"  ERROR cell {cell_count} ({regime}/{cell_idx}): {e}")
                traceback.print_exc()
                res = {"any_pass": False}

            row = {"regime": regime, "cell_idx": cell_idx}
            row.update(params)
            row.update(res)
            all_results.append(row)

            # 진행 보고 + 중간 저장
            if cell_count % 100 == 0:
                elapsed = time.time() - t_eval_start
                rate = cell_count / elapsed
                eta  = (total_cells - cell_count) / rate if rate > 0 else 0
                print(f"  [{cell_count:4d}/{total_cells}] "
                      f"{elapsed:.0f}s elapsed, "
                      f"ETA {eta:.0f}s, "
                      f"{rate:.1f} cells/s")

            if cell_count % CHECKPOINT_EVERY == 0:
                df_cp = pd.DataFrame(all_results)
                cp_path = OUT_ALL.replace(".csv", f"_cp{cell_count}.csv")
                df_cp.to_csv(cp_path, index=False)
                print(f"  체크포인트 저장: {cp_path}")

    # 10. 최종 저장
    df_all = pd.DataFrame(all_results)
    df_all.to_csv(OUT_ALL, index=False)
    print(f"\n[저장] 전체 결과 → {OUT_ALL} ({len(df_all)} 셀)")

    # 11. 보고서 생성
    print("[보고서] 생성 중...")
    make_reports(df_all)

    t_total = time.time() - t_start
    print(f"\n완료! 총 소요 시간: {t_total/60:.1f}분 ({t_total:.0f}초)")
    print(f"처리 셀: {cell_count}")

    # 12. 간단 콘솔 요약
    pass_cols = [c for c in df_all.columns if c.endswith("_pass")]
    df_all["any_pass"] = df_all[pass_cols].any(axis=1)
    n_pass = df_all["any_pass"].sum()
    print(f"\n===== 결과 요약 =====")
    print(f"합격 셀: {n_pass} / {len(df_all)}")
    for regime in REGIMES_6:
        sub = df_all[df_all["regime"] == regime]
        sub_pass = sub[sub["any_pass"]]
        best_lift = sub["swing_lift"].max() if "swing_lift" in sub.columns else np.nan
        print(f"  {regime}: {len(sub_pass)}/{len(sub)} 합격, best swing_lift={best_lift:.3f}")


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
    main()
