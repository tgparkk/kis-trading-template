"""
signal_combo_phase1.py
=======================
KOSPI200 PIT × 2026-04-01~2026-05-23 stock-day 피처 추출 + 라벨링.

목적 (사장님):
  - 5%↑ 스파이크 종목의 사전 신호(공통점) 룩어헤드-free 버전 발굴
  - +2% 도달률이 base rate 대비 2배 이상인 신호 조합 확인 (Phase 1 게이트)

데이터:
  - 분봉: robotrader.public.minute_candles (host=127.0.0.1 port=5433)
  - 일봉: robotrader_quant.public.daily_prices (동일 인스턴스)
  - KOSPI200 PIT: multiverse/data/kospi200_pit.py (없으면 DB 직접 조회)

룩어헤드 Hard Rule:
  - 일봉 피처: D-1 close 이전 데이터만 사용 (D당일 일봉 절대 금지)
  - 분봉 피처: 09:00~09:30 윈도우만 사용 (진입 시점 이전)

주의: minute_candles의 amount 컬럼은 누적값 (running total).
      per-bar amount = amount[t] - amount[t-1].
      단, 09:00 첫 봉은 amount[t] 그대로 사용.

사용법:
  cd RoboTrader_template
  python scripts/signal_combo_phase1.py
"""

from __future__ import annotations

import io
import os
import sys

# Windows cp949 터미널에서 한글 출력 강제 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import time
from datetime import date, datetime
from pathlib import Path

import psycopg2
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

REPORT_DIR = PROJECT_ROOT / "reports" / "signal_combo_aprmay"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_CASES_CSV = REPORT_DIR / "cases_v2.csv"
OUTPUT_COMPARE_CSV = REPORT_DIR / "feature_comparison_v2.csv"
OUTPUT_REACH2PCT_CSV = REPORT_DIR / "reach_2pct_analysis.csv"

# ---------------------------------------------------------------------------
# DB 연결 설정
# ---------------------------------------------------------------------------
DB_MINUTE = {
    "host": os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    "port": int(os.getenv("TIMESCALE_PORT", 5433)),
    "database": "robotrader",
    "user": os.getenv("TIMESCALE_USER", "robotrader"),
    "password": os.getenv("TIMESCALE_PASSWORD", "1234"),
}

DB_DAILY = {
    "host": os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    "port": int(os.getenv("TIMESCALE_PORT", 5433)),
    "database": "robotrader_quant",
    "user": os.getenv("TIMESCALE_USER", "robotrader"),
    "password": os.getenv("TIMESCALE_PASSWORD", "1234"),
}

# ---------------------------------------------------------------------------
# 기간 설정
# ---------------------------------------------------------------------------
DATE_START = "20260401"
DATE_END = "20260523"
DATE_START_ISO = "2026-04-01"
DATE_END_ISO = "2026-05-23"

# 일봉 lookback을 위한 충분한 과거 시작일 (D-25 확보)
DAILY_LOOKBACK_START = "2026-02-01"

# ---------------------------------------------------------------------------
# 피처 목록
# ---------------------------------------------------------------------------
INTRADAY_FEATURES = [
    "m30_volatility_pct",
    "m30_amount_sum_won",
    "m30_volume_sum",
    "m30_bullish_ratio",
    "m30_high_low_range_pct",
    "m30_close_vs_open",
    "gap_pct_v2",
    "first_5min_amount_share",
]

DAILY_FEATURES = [
    "ret_1d_pct",
    "ret_5d_pct",
    "ret_20d_pct",
    "vol_ratio_d1_vs_d20",
    "amount_d1_won",
    "atr_20d_pct",
    "ma5_dist_pct",
    "ma20_dist_pct",
    "d20_high_dist_pct",
    "d1_close_won",
]

ALL_FEATURES = INTRADAY_FEATURES + DAILY_FEATURES

# ---------------------------------------------------------------------------
# KOSPI200 PIT 로드
# ---------------------------------------------------------------------------

def load_kospi200_pit_from_db(conn_daily, month_last_dates: list[str]) -> dict[str, list[str]]:
    """
    robotrader_quant.daily_prices에서 월말 시총 상위 200 조회.
    Returns: {'2026-04': [...200 stock_codes...], '2026-05': [...]}
    """
    result = {}
    cur = conn_daily.cursor()
    for ref_date in month_last_dates:
        cur.execute("""
            SELECT stock_code
            FROM daily_prices
            WHERE date = %s AND market_cap IS NOT NULL
            ORDER BY market_cap DESC
            LIMIT 200
        """, (ref_date,))
        stocks = [str(r[0]).zfill(6) for r in cur.fetchall()]
        # 월 키 추출: '2026-04-30' -> '2026-04'
        month_key = ref_date[:7]
        result[month_key] = stocks
        print(f"  KOSPI200 PIT {month_key} ({ref_date}): {len(stocks)}종목")
    return result


def get_month_key(trade_date_str: str) -> str:
    """'20260415' -> '2026-04'"""
    return f"{trade_date_str[:4]}-{trade_date_str[4:6]}"


def get_kospi200_universe(trade_dates: list[str], conn_daily) -> dict[str, set[str]]:
    """
    각 거래일에 대해 해당 월의 KOSPI200 PIT 종목 집합 반환.
    캐시 파일이 있으면 사용하고, 없으면 DB에서 조회.

    Returns: {trade_date_str: set(stock_codes)}
    """
    # 필요한 월 목록 추출
    months_needed = sorted(set(get_month_key(td) for td in trade_dates))
    print(f"[Universe] 필요 월: {months_needed}")

    # 캐시 파일 확인 (multiverse/data/kospi200_pit.py 형식과 호환)
    cache_dir = PROJECT_ROOT / "cache" / "kospi200_pit"
    pit_by_month: dict[str, list[str]] = {}

    months_to_query = []
    for month in months_needed:
        cache_path = cache_dir / f"{month}.json"
        if cache_path.exists():
            import json
            with cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            stocks = data.get("stocks", [])
            if stocks:
                pit_by_month[month] = stocks
                print(f"  KOSPI200 PIT {month}: 캐시에서 로드 ({len(stocks)}종목)")
            else:
                months_to_query.append(month)
        else:
            months_to_query.append(month)

    if months_to_query:
        # 각 월의 마지막 거래일 조회
        cur = conn_daily.cursor()
        ref_dates = []
        for month in months_to_query:
            year, mon = month.split("-")
            month_start = f"{month}-01"
            if mon == "12":
                month_end = f"{int(year)+1}-01-01"
            else:
                next_mon = f"{year}-{int(mon)+1:02d}-01"
                # 해당 월의 마지막 날
                import calendar
                last_day = calendar.monthrange(int(year), int(mon))[1]
                month_end = f"{month}-{last_day}"
            cur.execute("""
                SELECT MAX(date) FROM daily_prices
                WHERE date >= %s AND date <= %s AND market_cap IS NOT NULL
            """, (month_start, month_end))
            row = cur.fetchone()
            if row and row[0]:
                ref_dates.append(row[0])
            else:
                # 5월은 5/23까지이므로 fallback
                ref_dates.append(DATE_END_ISO)

        queried = load_kospi200_pit_from_db(conn_daily, ref_dates)
        pit_by_month.update(queried)

        # 캐시 저장
        import json
        cache_dir.mkdir(parents=True, exist_ok=True)
        for month, stocks in queried.items():
            cache_path = cache_dir / f"{month}.json"
            payload = {"as_of_date": month + "-01", "stocks": stocks}
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"  캐시 저장: {cache_path.name}")

    # 각 거래일 → 해당 월 PIT 종목 집합
    date_to_universe: dict[str, set[str]] = {}
    for td in trade_dates:
        month = get_month_key(td)
        stocks = pit_by_month.get(month, [])
        date_to_universe[td] = set(stocks)

    return date_to_universe


# ---------------------------------------------------------------------------
# 분봉 데이터 일괄 로드
# ---------------------------------------------------------------------------

def load_minute_data(stock_codes: list[str], conn_minute) -> pd.DataFrame:
    """
    09:00~15:30 분봉 로드.
    amount는 누적값(running total)이므로 per_bar_amount를 계산해 추가.
    """
    print(f"[분봉] {len(stock_codes):,}개 종목, 09:00~15:30 로드 중... (수십 초 예상)")
    stock_list_sql = ",".join(f"'{s}'" for s in stock_codes)
    cur = conn_minute.cursor()
    cur.execute(f"""
        SELECT stock_code, trade_date, time, open, high, low, close, volume, amount
        FROM minute_candles
        WHERE trade_date >= '{DATE_START}' AND trade_date <= '{DATE_END}'
          AND time >= '090000' AND time <= '153000'
          AND stock_code IN ({stock_list_sql})
        ORDER BY stock_code, trade_date, time
    """)
    rows = cur.fetchall()
    cols = ["stock_code", "trade_date", "time", "open", "high", "low", "close", "volume", "amount"]
    df = pd.DataFrame(rows, columns=cols)
    print(f"[분봉] {len(df):,}행 로드 완료")

    if df.empty:
        df["per_bar_amount"] = pd.Series(dtype=float)
        return df

    # per_bar_amount 계산: amount는 누적값이므로 diff, 09:00 첫 봉은 그대로
    df = df.sort_values(["stock_code", "trade_date", "time"]).reset_index(drop=True)
    df["prev_amount"] = df.groupby(["stock_code", "trade_date"])["amount"].shift(1)
    # 첫 봉(prev_amount=NaN) → amount 그대로
    df["per_bar_amount"] = np.where(
        df["prev_amount"].isna(),
        df["amount"],
        df["amount"] - df["prev_amount"]
    )
    # 음수 방지 (데이터 이상)
    df["per_bar_amount"] = df["per_bar_amount"].clip(lower=0)
    df.drop(columns=["prev_amount"], inplace=True)

    return df


# ---------------------------------------------------------------------------
# 일봉 데이터 일괄 로드
# ---------------------------------------------------------------------------

def load_daily_data(stock_codes: list[str], conn_daily) -> pd.DataFrame:
    """
    robotrader_quant.daily_prices에서 2026-02-01 이후 데이터 로드.
    """
    print(f"[일봉] {len(stock_codes):,}개 종목 로드 중...")
    stock_list_sql = ",".join(f"'{s}'" for s in stock_codes)
    cur = conn_daily.cursor()
    cur.execute(f"""
        SELECT stock_code, date, open, high, low, close, volume, trading_value
        FROM daily_prices
        WHERE date >= '{DAILY_LOOKBACK_START}' AND date <= '{DATE_END_ISO}'
          AND stock_code IN ({stock_list_sql})
        ORDER BY stock_code, date
    """)
    rows = cur.fetchall()
    cols = ["stock_code", "date", "open", "high", "low", "close", "volume", "trading_value"]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    print(f"[일봉] {len(df):,}행 로드 완료, {df['stock_code'].nunique():,}개 종목")
    return df


# ---------------------------------------------------------------------------
# 종목명 로드
# ---------------------------------------------------------------------------

def load_stock_names(conn_minute) -> dict[str, str]:
    cur = conn_minute.cursor()
    cur.execute("""
        SELECT stock_code, stock_name
        FROM (
            SELECT DISTINCT ON (stock_code) stock_code, stock_name
            FROM (
                SELECT stock_code, stock_name FROM candidate_stocks WHERE stock_name IS NOT NULL
                UNION ALL
                SELECT stock_code, stock_name FROM virtual_trading_records WHERE stock_name IS NOT NULL
            ) combined
            ORDER BY stock_code
        ) deduped
    """)
    return {row[0]: row[1] for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# 분봉 피처 계산 (09:00~09:30 윈도우)
# ---------------------------------------------------------------------------

def compute_intraday_features(
    m_day_df: pd.DataFrame,
    prev_close: float | None,
) -> dict:
    """
    m_day_df: 특정 (stock_code, trade_date)의 분봉 DataFrame (time 오름차순 정렬).
    룩어헤드 Hard Rule: 09:00~09:30 윈도우만 사용.
    """
    features = {f: None for f in INTRADAY_FEATURES}

    if m_day_df.empty:
        return features

    # 09:00~09:30 윈도우
    pre_df = m_day_df[(m_day_df["time"] >= "090000") & (m_day_df["time"] <= "093000")].copy()

    if pre_df.empty:
        return features

    # open_09: 09:00 봉의 open (없으면 첫 봉의 open)
    row_0900 = pre_df[pre_df["time"] == "090000"]
    if not row_0900.empty:
        open_09 = float(row_0900.iloc[0]["open"])
    else:
        open_09 = float(pre_df.iloc[0]["open"])

    # close_0930: 09:30 봉의 close (없으면 09:30 이전 마지막 봉의 close)
    row_0930 = pre_df[pre_df["time"] == "093000"]
    if not row_0930.empty:
        close_0930 = float(row_0930.iloc[0]["close"])
    else:
        close_0930 = float(pre_df.iloc[-1]["close"])

    # gap_pct_v2: (open_09 - prev_close) / prev_close * 100
    if prev_close and prev_close > 0:
        features["gap_pct_v2"] = round((open_09 - prev_close) / prev_close * 100, 4)

    # m30_volatility_pct: (max(high) - min(low)) / min(low) * 100
    pre_high = float(pre_df["high"].max())
    pre_low = float(pre_df["low"].min())
    if pre_low > 0:
        features["m30_volatility_pct"] = round((pre_high - pre_low) / pre_low * 100, 4)

    # m30_amount_sum_won: sum(per_bar_amount) in 09:00~09:30 (원 단위 → 억원 단위는 하지 않음, 원 그대로)
    amt_sum = float(pre_df["per_bar_amount"].sum())
    features["m30_amount_sum_won"] = round(amt_sum / 1_000_000, 2) if amt_sum > 0 else None  # 백만원 단위

    # m30_volume_sum
    vol_sum = float(pre_df["volume"].sum())
    features["m30_volume_sum"] = vol_sum if vol_sum > 0 else None

    # m30_bullish_ratio: count(close >= open) / count(*)
    n_total = len(pre_df)
    if n_total > 0:
        n_bullish = int((pre_df["close"] >= pre_df["open"]).sum())
        features["m30_bullish_ratio"] = round(n_bullish / n_total, 4)

    # m30_high_low_range_pct: (max(high) - min(low)) / open_09 * 100
    if open_09 > 0:
        features["m30_high_low_range_pct"] = round((pre_high - pre_low) / open_09 * 100, 4)

    # m30_close_vs_open: (close_0930 - open_09) / open_09 * 100
    if open_09 > 0:
        features["m30_close_vs_open"] = round((close_0930 - open_09) / open_09 * 100, 4)

    # first_5min_amount_share: sum(per_bar_amount in 09:00~09:04) / m30_amount_sum
    first5_df = pre_df[pre_df["time"] < "090500"]
    first5_amt = float(first5_df["per_bar_amount"].sum())
    if amt_sum > 0 and first5_amt >= 0:
        features["first_5min_amount_share"] = round(first5_amt / amt_sum, 4)

    return features


# ---------------------------------------------------------------------------
# 일봉 피처 계산 (D-1 기준)
# ---------------------------------------------------------------------------

def compute_daily_features(daily_stock_df: pd.DataFrame, trade_date_str: str) -> dict:
    """
    trade_date_str: 'YYYYMMDD'
    daily_stock_df: 특정 종목의 전체 일봉 (date 오름차순)
    룩어헤드 Hard Rule: D당일 일봉 절대 사용 금지
    """
    features = {f: None for f in DAILY_FEATURES}
    features["prior_days_available"] = 0

    if daily_stock_df.empty:
        return features

    trade_dt = pd.to_datetime(trade_date_str, format="%Y%m%d")
    # D-1 이전 데이터만 (strict <)
    past = daily_stock_df[daily_stock_df["date"] < trade_dt].sort_values("date", ascending=False).reset_index(drop=True)

    n = len(past)
    features["prior_days_available"] = n

    if n < 1:
        return features

    d1 = past.iloc[0]
    d1_close = float(d1["close"]) if pd.notna(d1["close"]) else None
    features["d1_close_won"] = d1_close

    # amount_d1_won: D-1 거래대금 (백만원)
    if pd.notna(d1.get("trading_value")) and d1["trading_value"]:
        tv = float(d1["trading_value"])
        features["amount_d1_won"] = round(tv / 1_000_000, 2) if tv > 0 else None

    # ret_1d_pct: (D-1 close / D-2 close - 1) * 100
    if n >= 2 and pd.notna(past.iloc[1]["close"]) and float(past.iloc[1]["close"]) > 0:
        features["ret_1d_pct"] = round((float(d1["close"]) / float(past.iloc[1]["close"]) - 1) * 100, 4)

    # ret_5d_pct: (D-1 close / D-6 close - 1) * 100
    if n >= 6 and pd.notna(past.iloc[5]["close"]) and float(past.iloc[5]["close"]) > 0:
        features["ret_5d_pct"] = round((float(d1["close"]) / float(past.iloc[5]["close"]) - 1) * 100, 4)

    # ret_20d_pct: (D-1 close / D-21 close - 1) * 100
    oldest_idx = min(n - 1, 20)
    if oldest_idx > 0 and pd.notna(past.iloc[oldest_idx]["close"]) and float(past.iloc[oldest_idx]["close"]) > 0:
        features["ret_20d_pct"] = round((float(d1["close"]) / float(past.iloc[oldest_idx]["close"]) - 1) * 100, 4)

    # vol_ratio_d1_vs_d20: D-1 volume / avg(D-2..D-21)
    if n >= 2 and pd.notna(d1["volume"]):
        lookback_end = min(n, 21)
        comp_vols = past.iloc[1:lookback_end]["volume"].dropna().astype(float)
        if len(comp_vols) > 0:
            avg_vol = comp_vols.mean()
            if avg_vol > 0:
                features["vol_ratio_d1_vs_d20"] = round(float(d1["volume"]) / avg_vol, 4)

    # atr_20d_pct: avg(high - low) for D-1..D-20 / D-1 close * 100
    atr_window = past.iloc[:min(n, 20)]
    valid_atr = atr_window[atr_window["high"].notna() & atr_window["low"].notna()]
    if len(valid_atr) > 0 and d1_close and d1_close > 0:
        atr_vals = (valid_atr["high"].astype(float) - valid_atr["low"].astype(float)).mean()
        features["atr_20d_pct"] = round(float(atr_vals) / d1_close * 100, 4)

    # ma5_dist_pct: (D-1 close - mean(D-1..D-5)) / mean(D-1..D-5) * 100
    ma5_w = past.iloc[:min(n, 5)]["close"].dropna().astype(float)
    if len(ma5_w) >= 1 and d1_close:
        ma5 = ma5_w.mean()
        if ma5 > 0:
            features["ma5_dist_pct"] = round((d1_close - ma5) / ma5 * 100, 4)

    # ma20_dist_pct: (D-1 close - mean(D-1..D-20)) / mean(D-1..D-20) * 100
    ma20_w = past.iloc[:min(n, 20)]["close"].dropna().astype(float)
    if len(ma20_w) >= 1 and d1_close:
        ma20 = ma20_w.mean()
        if ma20 > 0:
            features["ma20_dist_pct"] = round((d1_close - ma20) / ma20 * 100, 4)

    # d20_high_dist_pct: (D-1 close / max(high D-1..D-20) - 1) * 100
    high_w = past.iloc[:min(n, 20)]["high"].dropna().astype(float)
    if len(high_w) >= 1 and d1_close and d1_close > 0:
        d20_max_high = high_w.max()
        if d20_max_high > 0:
            features["d20_high_dist_pct"] = round((d1_close / d20_max_high - 1) * 100, 4)

    return features


# ---------------------------------------------------------------------------
# 라벨 계산 (09:30 이후 15:30 종료 윈도우)
# ---------------------------------------------------------------------------

def compute_labels(m_day_df: pd.DataFrame) -> dict:
    """
    진입가 = 09:30 봉의 close (없으면 09:30 이전 마지막 봉의 close).
    09:30 이후 ~ 15:30 윈도우의 max(high)로 도달률 계산.
    룩어헤드 Hard Rule: 09:30 이전 분봉은 라벨 계산에 사용하지 않음.

    Returns:
        {open_09, close_0930, day_high, day_close, label_5pct, label_2pct}
    """
    result = {
        "open_09": None,
        "close_0930": None,
        "day_high": None,
        "day_close": None,
        "label_5pct": None,
        "label_2pct": None,
    }

    if m_day_df.empty:
        return result

    pre_df = m_day_df[(m_day_df["time"] >= "090000") & (m_day_df["time"] <= "093000")]

    # open_09
    row_0900 = pre_df[pre_df["time"] == "090000"]
    if not row_0900.empty:
        result["open_09"] = float(row_0900.iloc[0]["open"])
    elif not pre_df.empty:
        result["open_09"] = float(pre_df.iloc[0]["open"])

    # close_0930: 진입가
    row_0930 = pre_df[pre_df["time"] == "093000"]
    if not row_0930.empty:
        result["close_0930"] = float(row_0930.iloc[0]["close"])
    elif not pre_df.empty:
        result["close_0930"] = float(pre_df.iloc[-1]["close"])

    entry_price = result["close_0930"]
    if not entry_price or entry_price <= 0:
        return result

    # 09:30 초과 ~ 15:30 윈도우 (룩어헤드 방지: 09:30은 진입봉, 이후 봉에서 최고가)
    post_df = m_day_df[m_day_df["time"] > "093000"]

    # day_close: 마지막 봉의 close
    all_df = m_day_df[m_day_df["time"] <= "153000"]
    if not all_df.empty:
        result["day_close"] = float(all_df.iloc[-1]["close"])

    if post_df.empty:
        # 09:30 이후 데이터가 없으면 라벨 None (데이터 부족)
        return result

    day_high = float(post_df["high"].max())
    result["day_high"] = day_high

    max_gain_pct = (day_high - entry_price) / entry_price * 100

    result["label_5pct"] = 1 if max_gain_pct >= 5.0 else 0
    result["label_2pct"] = 1 if max_gain_pct >= 2.0 else 0

    return result


# ---------------------------------------------------------------------------
# 피처 비교 (treated=label_5pct=1 vs control=label_5pct=0)
# ---------------------------------------------------------------------------

def compute_feature_comparison(cases_df: pd.DataFrame) -> pd.DataFrame:
    """
    label_5pct=1 (treated) vs label_5pct=0 (control) 피처 비교.
    normalized_diff = (treated_mean - control_mean) / control_std
    """
    valid = cases_df[cases_df["label_5pct"].notna()].copy()
    treated = valid[valid["label_5pct"] == 1]
    control = valid[valid["label_5pct"] == 0]

    rows = []
    for feat in ALL_FEATURES:
        if feat not in cases_df.columns:
            continue

        t_vals = treated[feat].dropna().astype(float)
        c_vals = control[feat].dropna().astype(float)

        if len(t_vals) == 0 and len(c_vals) == 0:
            continue

        def stats(v):
            if len(v) == 0:
                return dict(n=0, mean=None, median=None, p25=None, p75=None, std=None)
            return dict(
                n=int(len(v)),
                mean=round(float(v.mean()), 6),
                median=round(float(v.median()), 6),
                p25=round(float(v.quantile(0.25)), 6),
                p75=round(float(v.quantile(0.75)), 6),
                std=round(float(v.std()), 6) if len(v) > 1 else 0.0,
            )

        ts = stats(t_vals)
        cs = stats(c_vals)

        mean_diff = None
        normalized_diff = None
        direction = "similar"

        if ts["mean"] is not None and cs["mean"] is not None:
            mean_diff = round(ts["mean"] - cs["mean"], 6)
            if cs["std"] and cs["std"] > 0:
                normalized_diff = round(mean_diff / cs["std"], 4)
                if abs(normalized_diff) < 0.2:
                    direction = "similar"
                elif normalized_diff > 0:
                    direction = "higher_in_spike"
                else:
                    direction = "lower_in_spike"

        rows.append({
            "feature": feat,
            "treated_n": ts["n"],
            "treated_mean": ts["mean"],
            "treated_median": ts["median"],
            "treated_p25": ts["p25"],
            "treated_p75": ts["p75"],
            "treated_std": ts["std"],
            "control_n": cs["n"],
            "control_mean": cs["mean"],
            "control_median": cs["median"],
            "control_p25": cs["p25"],
            "control_p75": cs["p75"],
            "control_std": cs["std"],
            "mean_diff": mean_diff,
            "normalized_diff": normalized_diff,
            "direction": direction,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# +2% 도달률 분석 (Phase 1 게이트 평가용)
# ---------------------------------------------------------------------------

def compute_reach_2pct_analysis(cases_df: pd.DataFrame) -> pd.DataFrame:
    """
    각 신호 룰에 대해 +5%/+2% 도달률 및 lift 계산.
    """
    valid = cases_df[cases_df["label_2pct"].notna() & cases_df["label_5pct"].notna()].copy()

    n_total = len(valid)
    base_5pct_rate = float(valid["label_5pct"].mean()) if n_total > 0 else 0.0
    base_2pct_rate = float(valid["label_2pct"].mean()) if n_total > 0 else 0.0

    def evaluate_rule(mask: pd.Series, rule_desc: str) -> dict | None:
        sub = valid[mask]
        n = len(sub)
        if n == 0:
            return None
        r5 = float(sub["label_5pct"].mean())
        r2 = float(sub["label_2pct"].mean())
        lift5 = round(r5 / base_5pct_rate, 4) if base_5pct_rate > 0 else None
        lift2 = round(r2 / base_2pct_rate, 4) if base_2pct_rate > 0 else None
        return {
            "signal_rule": rule_desc,
            "n_cases": n,
            "reach_5pct_rate": round(r5, 4),
            "reach_2pct_rate": round(r2, 4),
            "base_5pct_rate": round(base_5pct_rate, 4),
            "base_2pct_rate": round(base_2pct_rate, 4),
            "lift_5pct": lift5,
            "lift_2pct": lift2,
        }

    rows = []

    # --- 단일 신호 임계 ---

    # ret_20d_pct >= {10, 15, 20, 25, 30}
    for thr in [10, 15, 20, 25, 30]:
        col = "ret_20d_pct"
        if col in valid.columns:
            mask = valid[col].notna() & (valid[col] >= thr)
            r = evaluate_rule(mask, f"ret_20d_pct>={thr}")
            if r:
                rows.append(r)

    # ma20_dist_pct >= {5, 10, 15, 20}
    for thr in [5, 10, 15, 20]:
        col = "ma20_dist_pct"
        if col in valid.columns:
            mask = valid[col].notna() & (valid[col] >= thr)
            r = evaluate_rule(mask, f"ma20_dist_pct>={thr}")
            if r:
                rows.append(r)

    # atr_20d_pct >= {6, 8, 10}
    for thr in [6, 8, 10]:
        col = "atr_20d_pct"
        if col in valid.columns:
            mask = valid[col].notna() & (valid[col] >= thr)
            r = evaluate_rule(mask, f"atr_20d_pct>={thr}")
            if r:
                rows.append(r)

    # m30_volatility_pct >= {1, 2, 3, 4}
    for thr in [1, 2, 3, 4]:
        col = "m30_volatility_pct"
        if col in valid.columns:
            mask = valid[col].notna() & (valid[col] >= thr)
            r = evaluate_rule(mask, f"m30_volatility_pct>={thr}")
            if r:
                rows.append(r)

    # m30_close_vs_open >= {0, 0.5, 1.0, 1.5}
    for thr in [0.0, 0.5, 1.0, 1.5]:
        col = "m30_close_vs_open"
        if col in valid.columns:
            mask = valid[col].notna() & (valid[col] >= thr)
            r = evaluate_rule(mask, f"m30_close_vs_open>={thr}")
            if r:
                rows.append(r)

    # vol_ratio_d1_vs_d20 >= {1.0, 1.5, 2.0}
    for thr in [1.0, 1.5, 2.0]:
        col = "vol_ratio_d1_vs_d20"
        if col in valid.columns:
            mask = valid[col].notna() & (valid[col] >= thr)
            r = evaluate_rule(mask, f"vol_ratio_d1_vs_d20>={thr}")
            if r:
                rows.append(r)

    # gap_pct_v2 >= {0, 1, 2}
    for thr in [0.0, 1.0, 2.0]:
        col = "gap_pct_v2"
        if col in valid.columns:
            mask = valid[col].notna() & (valid[col] >= thr)
            r = evaluate_rule(mask, f"gap_pct_v2>={thr}")
            if r:
                rows.append(r)

    # --- AND 조합 8개 ---

    def get_col_mask(col, thr):
        if col not in valid.columns:
            return pd.Series([False] * len(valid), index=valid.index)
        return valid[col].notna() & (valid[col] >= thr)

    combos = [
        ("ret_20d>=20 AND ma20_dist>=10",
         get_col_mask("ret_20d_pct", 20) & get_col_mask("ma20_dist_pct", 10)),
        ("ret_20d>=20 AND m30_volatility>=2",
         get_col_mask("ret_20d_pct", 20) & get_col_mask("m30_volatility_pct", 2)),
        ("ret_20d>=20 AND ma20_dist>=10 AND m30_volatility>=2",
         get_col_mask("ret_20d_pct", 20) & get_col_mask("ma20_dist_pct", 10) & get_col_mask("m30_volatility_pct", 2)),
        ("ret_20d>=15 AND ma20_dist>=8 AND m30_volatility>=2",
         get_col_mask("ret_20d_pct", 15) & get_col_mask("ma20_dist_pct", 8) & get_col_mask("m30_volatility_pct", 2)),
        ("ret_20d>=25 AND atr_20d>=8",
         get_col_mask("ret_20d_pct", 25) & get_col_mask("atr_20d_pct", 8)),
        ("ma20_dist>=10 AND m30_close_vs_open>=0.5",
         get_col_mask("ma20_dist_pct", 10) & get_col_mask("m30_close_vs_open", 0.5)),
        ("ret_20d>=20 AND vol_ratio_d1_vs_d20>=1.5",
         get_col_mask("ret_20d_pct", 20) & get_col_mask("vol_ratio_d1_vs_d20", 1.5)),
        ("m30_volatility>=2 AND m30_close_vs_open>=0.5 AND ret_5d>=5",
         get_col_mask("m30_volatility_pct", 2) & get_col_mask("m30_close_vs_open", 0.5) & get_col_mask("ret_5d_pct", 5)),
    ]

    for desc, mask in combos:
        r = evaluate_rule(mask, desc)
        if r:
            rows.append(r)

    df = pd.DataFrame(rows)
    if not df.empty and "lift_2pct" in df.columns:
        df = df.sort_values("lift_2pct", ascending=False).reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# 콘솔 보고
# ---------------------------------------------------------------------------

def print_report(
    cases_df: pd.DataFrame,
    compare_df: pd.DataFrame,
    reach_df: pd.DataFrame,
    elapsed: float,
    n_trade_dates: int,
    n_universe_stocks: int,
) -> None:
    valid = cases_df[cases_df["label_2pct"].notna() & cases_df["label_5pct"].notna()]
    n_valid = len(valid)
    base_5pct = float(valid["label_5pct"].mean()) if n_valid > 0 else 0.0
    base_2pct = float(valid["label_2pct"].mean()) if n_valid > 0 else 0.0

    print()
    print("=" * 80)
    print("  Phase 1 신호 결합 분석 결과")
    print("=" * 80)
    print(f"  실행 시간       : {elapsed:.1f}초")
    print(f"  전체 stock-day  : {len(cases_df):,}건")
    print(f"  라벨 유효 건수  : {n_valid:,}건 (분봉 데이터 있음)")
    print(f"  KOSPI200 종목수 : {n_universe_stocks}종목 (월별 변동)")
    print(f"  영업일 수       : {n_trade_dates}일")
    print()

    print("  [라벨 분포]")
    print(f"    label_5pct=1 (5%↑ 도달) : {valid['label_5pct'].sum():,.0f}건 ({base_5pct*100:.1f}%)")
    print(f"    label_2pct=1 (2%↑ 도달) : {valid['label_2pct'].sum():,.0f}건 ({base_2pct*100:.1f}%)")
    print()

    # 결측치 비율
    print("  [피처별 결측치 비율 (전체 cases_df, >5% 만 표시)]")
    for feat in ALL_FEATURES:
        if feat not in cases_df.columns:
            continue
        miss_pct = cases_df[feat].isna().mean() * 100
        if miss_pct > 5:
            print(f"    {feat:<35}  {miss_pct:5.1f}%")
    print()

    # feature_comparison 상위 10개
    if not compare_df.empty and "normalized_diff" in compare_df.columns:
        top10 = (
            compare_df
            .dropna(subset=["normalized_diff"])
            .assign(abs_nd=lambda d: d["normalized_diff"].abs())
            .sort_values("abs_nd", ascending=False)
            .head(10)
        )
        print("  [feature_comparison_v2 상위 10개 신호 (|normalized_diff| 정렬)]")
        print(f"  {'피처':<35}  {'normalized_diff':>16}  {'방향':<22}  {'treated_median':>14}  {'control_median':>14}")
        print("  " + "-" * 110)
        for _, r in top10.iterrows():
            nd = r["normalized_diff"]
            nd_str = f"{nd:+.4f}" if nd is not None else "N/A"
            tm = f"{r['treated_median']:.4f}" if r["treated_median"] is not None else "N/A"
            cm = f"{r['control_median']:.4f}" if r["control_median"] is not None else "N/A"
            print(f"  {r['feature']:<35}  {nd_str:>16}  {r['direction']:<22}  {tm:>14}  {cm:>14}")
    print()

    # reach_2pct_analysis 상위 10개
    if not reach_df.empty and "lift_2pct" in reach_df.columns:
        top10r = reach_df.sort_values("lift_2pct", ascending=False).head(10)
        print("  [reach_2pct_analysis 상위 10개 룰 (lift_2pct 정렬)]")
        print(f"  {'신호 룰':<50}  {'n_cases':>8}  {'reach_2pct':>10}  {'lift_2pct':>9}  {'lift_5pct':>9}")
        print("  " + "-" * 100)
        for _, r in top10r.iterrows():
            l2 = f"{r['lift_2pct']:.4f}" if r["lift_2pct"] is not None else "N/A"
            l5 = f"{r['lift_5pct']:.4f}" if r["lift_5pct"] is not None else "N/A"
            r2 = f"{r['reach_2pct_rate']*100:.1f}%"
            print(f"  {r['signal_rule']:<50}  {r['n_cases']:>8,}  {r2:>10}  {l2:>9}  {l5:>9}")
    print()

    # Phase 1 게이트 평가
    print("  [Phase 1 게이트 평가]")
    if not reach_df.empty and "lift_2pct" in reach_df.columns:
        lift2_vals = reach_df["lift_2pct"].dropna()
        n_pass = int((lift2_vals >= 2.0).sum())
        n_warning = int(((lift2_vals >= 1.5) & (lift2_vals < 2.0)).sum())

        best_row = reach_df.iloc[0] if len(reach_df) > 0 else None

        print(f"    lift_2pct >= 2.0 룰 수 : {n_pass}개")
        if best_row is not None:
            l2 = best_row["lift_2pct"]
            l5 = best_row["lift_5pct"]
            nc = best_row["n_cases"]
            r2 = best_row["reach_2pct_rate"]
            print(f"    최강 룰            : {best_row['signal_rule']}")
            print(f"    최강 lift_2pct     : {l2:.4f}x  (reach_2pct={r2*100:.1f}%, n={nc:,})")
            print(f"    최강 lift_5pct     : {l5:.4f}x")

        if n_pass >= 1:
            verdict = "PASS"
            reason = f"lift_2pct >= 2.0 룰 {n_pass}개 확인 → Phase 2 진행"
        elif n_warning >= 1:
            verdict = "WARNING"
            reason = f"lift_2pct 1.5~2.0 룰 {n_warning}개 → Phase 2 진행하되 robustness 한계 명시"
        else:
            verdict = "FAIL"
            reason = "lift_2pct < 1.5배 → 신호 자체 재검토 필요"

        print(f"    게이트 판정        : [{verdict}] {reason}")
    print()

    print("  [산출물]")
    print(f"    {OUTPUT_CASES_CSV}")
    print(f"    {OUTPUT_COMPARE_CSV}")
    print(f"    {OUTPUT_REACH2PCT_CSV}")
    print("=" * 80)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()

    print("=" * 80)
    print("  신호 결합 백테스트 Phase 1 - 룩어헤드-free 피처셋 추출")
    print("  기간: 2026-04-01 ~ 2026-05-23 / Universe: KOSPI200 PIT")
    print("=" * 80)

    # --- DB 연결 ---
    print("\n[1/7] DB 연결...")
    conn_minute = psycopg2.connect(**DB_MINUTE)
    conn_minute.autocommit = True
    conn_daily = psycopg2.connect(**DB_DAILY)
    conn_daily.autocommit = True
    print("  OK")

    # --- 영업일 목록 조회 ---
    print("\n[2/7] 영업일 목록 조회...")
    cur = conn_minute.cursor()
    cur.execute(f"""
        SELECT DISTINCT trade_date
        FROM minute_candles
        WHERE trade_date >= '{DATE_START}' AND trade_date <= '{DATE_END}'
        ORDER BY trade_date
    """)
    trade_dates = [r[0] for r in cur.fetchall()]
    print(f"  영업일 {len(trade_dates)}일")

    # --- KOSPI200 PIT 유니버스 ---
    print("\n[3/7] KOSPI200 PIT 유니버스 구성...")
    date_to_universe = get_kospi200_universe(trade_dates, conn_daily)
    all_universe_stocks = set()
    for stocks in date_to_universe.values():
        all_universe_stocks.update(stocks)
    print(f"  전체 KOSPI200 유니버스 (4~5월 합산): {len(all_universe_stocks)}개 종목")

    # Universe 내 stock-day 목록
    stockday_list = []
    for td in trade_dates:
        for sc in date_to_universe.get(td, set()):
            stockday_list.append((sc, td))
    print(f"  전체 stock-day: {len(stockday_list):,}건")

    # --- 데이터 로드 ---
    all_stocks = sorted(all_universe_stocks)

    print("\n[4/7] 분봉 데이터 로드...")
    minute_df = load_minute_data(all_stocks, conn_minute)

    print("\n[5/7] 일봉 데이터 로드...")
    daily_df = load_daily_data(all_stocks, conn_daily)

    print("\n[5b/7] 종목명 로드...")
    name_map = load_stock_names(conn_minute)
    print(f"  {len(name_map):,}개 종목명")

    conn_minute.close()
    conn_daily.close()
    print("  DB 연결 종료")

    # --- 분봉 인덱스 구성 ---
    print("\n[6/7] 피처 계산 중...")
    print("  분봉 인덱스 구성...")
    minute_idx: dict[tuple[str, str], pd.DataFrame] = {}
    for (sc, td), grp in minute_df.groupby(["stock_code", "trade_date"]):
        minute_idx[(sc, td)] = grp.sort_values("time").reset_index(drop=True)

    # 일봉 인덱스 구성
    daily_idx: dict[str, pd.DataFrame] = {}
    for sc, grp in daily_df.groupby("stock_code"):
        daily_idx[sc] = grp.sort_values("date").reset_index(drop=True)

    # stock-day별 피처 계산
    records = []
    total = len(stockday_list)
    n_no_minute = 0
    n_no_daily = 0

    for i, (sc, td) in enumerate(stockday_list):
        if (i + 1) % 2000 == 0:
            pct = (i + 1) / total * 100
            print(f"  {i+1:,}/{total:,} ({pct:.1f}%) 처리 중...")

        record = {
            "trade_date": td,
            "stock_code": sc,
            "stock_name": name_map.get(sc, ""),
        }

        # 분봉 데이터
        m_day_df = minute_idx.get((sc, td))

        # 라벨 계산
        if m_day_df is not None and not m_day_df.empty:
            labels = compute_labels(m_day_df)
        else:
            labels = {
                "open_09": None, "close_0930": None,
                "day_high": None, "day_close": None,
                "label_5pct": None, "label_2pct": None,
            }
            n_no_minute += 1

        record.update(labels)

        # 일봉 피처
        d_df = daily_idx.get(sc)
        if d_df is None or d_df.empty:
            n_no_daily += 1
            for f in DAILY_FEATURES:
                record[f] = None
            record["prior_days_available"] = 0
            daily_features = {}
        else:
            daily_features = compute_daily_features(d_df, td)
            record.update(daily_features)

        # 분봉 피처 (09:00~09:30)
        if m_day_df is not None and not m_day_df.empty:
            # prev_close: D-1 일봉 종가
            prev_close = None
            if d_df is not None and not d_df.empty:
                trade_dt = pd.to_datetime(td, format="%Y%m%d")
                past = d_df[d_df["date"] < trade_dt].sort_values("date", ascending=False)
                if not past.empty and pd.notna(past.iloc[0]["close"]):
                    prev_close = float(past.iloc[0]["close"])
            intra_features = compute_intraday_features(m_day_df, prev_close)
        else:
            intra_features = {f: None for f in INTRADAY_FEATURES}

        record.update(intra_features)
        records.append(record)

    print(f"  분봉 데이터 없음: {n_no_minute}건, 일봉 데이터 없음: {n_no_daily}건")

    # --- DataFrame 구성 및 컬럼 정리 ---
    cases_df = pd.DataFrame(records)

    col_order = [
        "trade_date", "stock_code", "stock_name",
        "open_09", "close_0930", "day_high", "day_close",
        "label_5pct", "label_2pct", "prior_days_available",
    ] + INTRADAY_FEATURES + DAILY_FEATURES

    existing_cols = [c for c in col_order if c in cases_df.columns]
    extra_cols = [c for c in cases_df.columns if c not in existing_cols]
    cases_df = cases_df[existing_cols + extra_cols]

    # --- 비교 계산 ---
    print("\n[7/7] 피처 비교 + reach_2pct 분석 + 저장...")

    compare_df = compute_feature_comparison(cases_df)
    reach_df = compute_reach_2pct_analysis(cases_df)

    # CSV 저장
    cases_df.to_csv(OUTPUT_CASES_CSV, index=False, encoding="utf-8-sig")
    compare_df.to_csv(OUTPUT_COMPARE_CSV, index=False, encoding="utf-8-sig")
    reach_df.to_csv(OUTPUT_REACH2PCT_CSV, index=False, encoding="utf-8-sig")

    print(f"  cases_v2.csv: {len(cases_df):,}행")
    print(f"  feature_comparison_v2.csv: {len(compare_df):,}행")
    print(f"  reach_2pct_analysis.csv: {len(reach_df):,}행")

    elapsed = time.time() - t0

    # 유니버스 종목 수 (월별 최대)
    max_universe = max(len(v) for v in date_to_universe.values()) if date_to_universe else 0
    print_report(cases_df, compare_df, reach_df, elapsed, len(trade_dates), max_universe)


if __name__ == "__main__":
    main()
