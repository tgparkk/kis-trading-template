"""
extract_spike_precursors.py
============================
4~5월 장중 5% 이상 상승 케이스(treated)와 통제군(control)의
사전 신호 피처를 추출하고 비교합니다.

입력:
  - RoboTrader_template/reports/intraday_5pct_spikes_aprmay/spikes.csv (6,681건)

출력:
  - RoboTrader_template/reports/spike_precursor_aprmay/cases_with_features.csv
  - RoboTrader_template/reports/spike_precursor_aprmay/feature_comparison.csv

사용법:
  cd RoboTrader_template
  python scripts/extract_spike_precursors.py
"""

from __future__ import annotations

import csv
import os
import sys
import time
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

SPIKES_CSV = PROJECT_ROOT / "reports" / "intraday_5pct_spikes_aprmay" / "spikes.csv"
REPORT_DIR = PROJECT_ROOT / "reports" / "spike_precursor_aprmay"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_CASES_CSV = REPORT_DIR / "cases_with_features.csv"
OUTPUT_COMPARE_CSV = REPORT_DIR / "feature_comparison.csv"

# ---------------------------------------------------------------------------
# DB 연결 설정
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    "port": int(os.getenv("TIMESCALE_PORT", 5433)),
    "database": os.getenv("TIMESCALE_DB", "robotrader"),
    "user": os.getenv("TIMESCALE_USER", "robotrader"),
    "password": os.getenv("TIMESCALE_PASSWORD", "1234"),
}

# ---------------------------------------------------------------------------
# 피처 컬럼 목록
# ---------------------------------------------------------------------------
INTRADAY_FEATURES = [
    "gap_pct",
    "pre_duration_min",
    "pre_volume_sum",
    "pre_amount_sum",
    "pre_volatility_pct",
    "pre_bullish_minute_ratio",
    "first_5min_amount_share",
    "low_drawdown_pct",
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

META_COLS = [
    "group", "trade_date", "stock_code", "stock_name",
    "peak_ratio", "rise_pct",
    "low_time", "low_price", "high_time", "high_price",
    "day_open", "day_close",
    "prior_days_available",
]

# ---------------------------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------------------------

def fmt_time(t: str) -> str:
    """'HHMMSS' -> 'HH:MM'"""
    if not t or len(t) < 4:
        return t or ""
    return f"{t[:2]}:{t[2:4]}"


def parse_time_to_minutes(hhmm: str) -> int | None:
    """'HH:MM' 또는 'HHMMSS' -> 09:00 기준 분 오프셋. 실패 시 None"""
    if not hhmm:
        return None
    hhmm = hhmm.replace(":", "")
    if len(hhmm) < 4:
        return None
    try:
        h = int(hhmm[:2])
        m = int(hhmm[2:4])
        return (h - 9) * 60 + m
    except ValueError:
        return None


def hhmmss_to_minutes(hhmmss: str) -> int | None:
    """'HHMMSS' -> 09:00 기준 분 오프셋"""
    if not hhmmss or len(hhmmss) < 6:
        return None
    try:
        h = int(hhmmss[:2])
        m = int(hhmmss[2:4])
        return (h - 9) * 60 + m
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# STEP 1: treated 케이스 로드
# ---------------------------------------------------------------------------

def load_treated(path: Path) -> pd.DataFrame:
    """spikes.csv 로드 → treated DataFrame"""
    df = pd.read_csv(path, dtype={"stock_code": str, "trade_date": str})
    df["group"] = "treated"
    df["trade_date"] = df["trade_date"].astype(str).str.zfill(8)
    # peak_ratio 계산 (high / low)
    df["peak_ratio"] = df.apply(
        lambda r: round(r["high_price"] / r["low_price"], 4)
        if pd.notna(r["low_price"]) and r["low_price"] > 0 else None,
        axis=1,
    )
    print(f"[Treated] {len(df):,}건 로드, 고유 종목 {df['stock_code'].nunique():,}개")
    return df


# ---------------------------------------------------------------------------
# STEP 2: 통제군 후보 stock-day 생성
# ---------------------------------------------------------------------------

def build_control_stockdays(treated: pd.DataFrame, conn) -> pd.DataFrame:
    """
    treated의 832개 고유 종목 × 4~5월 거래일에서
    treated가 아닌 stock-day를 통제군으로 생성.
    """
    unique_stocks = treated["stock_code"].unique().tolist()
    treated_set = set(zip(treated["trade_date"], treated["stock_code"]))

    # DB에서 해당 종목의 거래일 목록 조회 (minute_candles 기준)
    print(f"[Control] {len(unique_stocks):,}개 종목의 거래일 조회 중...")
    stock_list_sql = "'" + "','".join(unique_stocks) + "'"
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT stock_code, trade_date
        FROM minute_candles
        WHERE trade_date BETWEEN '20260401' AND '20260523'
          AND stock_code IN ({stock_list_sql})
        ORDER BY stock_code, trade_date
    """)
    rows = cur.fetchall()

    control_rows = []
    for stock_code, trade_date in rows:
        if (trade_date, stock_code) not in treated_set:
            control_rows.append({"stock_code": stock_code, "trade_date": trade_date})

    df = pd.DataFrame(control_rows)
    print(f"[Control] {len(df):,}건 stock-day (treated 제외 후)")
    return df


# ---------------------------------------------------------------------------
# STEP 3: 분봉 데이터 일괄 로드
# ---------------------------------------------------------------------------

def load_minute_data(stock_codes: list[str], conn) -> pd.DataFrame:
    """해당 종목들의 4~5월 전체 분봉(09:00~15:30) 로드"""
    print("[분봉] 데이터 로드 중... (수십 초 예상)")
    stock_list_sql = "'" + "','".join(stock_codes) + "'"
    cur = conn.cursor()
    cur.execute(f"""
        SELECT stock_code, trade_date, time, open, high, low, close, volume, amount
        FROM minute_candles
        WHERE trade_date BETWEEN '20260401' AND '20260523'
          AND time >= '090000'
          AND time <= '153000'
          AND stock_code IN ({stock_list_sql})
        ORDER BY stock_code, trade_date, time
    """)
    rows = cur.fetchall()
    cols = ["stock_code", "trade_date", "time", "open", "high", "low", "close", "volume", "amount"]
    df = pd.DataFrame(rows, columns=cols)
    print(f"[분봉] {len(df):,}행 로드 완료")
    return df


# ---------------------------------------------------------------------------
# STEP 4: 일봉 데이터 일괄 로드 (D-1 ~ D-21 lookback)
# ---------------------------------------------------------------------------

def load_daily_data(stock_codes: list[str], conn) -> pd.DataFrame:
    """
    daily_prices에서 2026-02-01 이후 데이터 로드
    (4월 최초 거래일 기준 D-21 확보를 위해 여유 있게 로드)
    """
    print("[일봉] 데이터 로드 중...")
    stock_list_sql = "'" + "','".join(stock_codes) + "'"
    cur = conn.cursor()
    cur.execute(f"""
        SELECT stock_code, date, open, high, low, close, volume, trading_value
        FROM daily_prices
        WHERE date >= '2026-02-01'
          AND date <= '2026-05-23'
          AND stock_code IN ({stock_list_sql})
        ORDER BY stock_code, date
    """)
    rows = cur.fetchall()
    cols = ["stock_code", "date", "open", "high", "low", "close", "volume", "trading_value"]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    # date -> 'YYYYMMDD' 문자열도 추가
    df["date_str"] = df["date"].dt.strftime("%Y%m%d")
    print(f"[일봉] {len(df):,}행 로드 완료, {df['stock_code'].nunique():,}개 종목")
    return df


# ---------------------------------------------------------------------------
# STEP 5: 종목명 로드
# ---------------------------------------------------------------------------

def load_stock_names(conn) -> dict:
    cur = conn.cursor()
    cur.execute("""
        SELECT stock_code, stock_name
        FROM (
            SELECT DISTINCT ON (stock_code) stock_code, stock_name
            FROM (
                SELECT stock_code, stock_name FROM candidate_stocks WHERE stock_name IS NOT NULL
                UNION ALL
                SELECT stock_code, stock_name FROM screener_snapshots WHERE stock_name IS NOT NULL
                UNION ALL
                SELECT stock_code, stock_name FROM virtual_trading_records WHERE stock_name IS NOT NULL
            ) combined
            ORDER BY stock_code
        ) deduped
    """)
    return {row[0]: row[1] for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# STEP 6: control peak 계산 (running min low → peak ratio)
# ---------------------------------------------------------------------------

def compute_control_peak(group_df: pd.DataFrame) -> dict:
    """
    하루 분봉 데이터에서 running_min_low 기반 최대 peak_ratio 계산.
    반환: {low_time, low_price, high_time, high_price, peak_ratio, rise_pct, day_open, day_close}
    """
    df = group_df.sort_values("time").reset_index(drop=True)
    if df.empty:
        return {}

    day_open = float(df.iloc[0]["open"]) if pd.notna(df.iloc[0]["open"]) else None
    day_close = float(df.iloc[-1]["close"]) if pd.notna(df.iloc[-1]["close"]) else None

    # running_min_low: 각 시점까지의 누적 최저가
    df["running_min_low"] = df["low"].cummin()

    best_ratio = 0.0
    best_high_idx = -1
    best_running_min = None

    for i, row in df.iterrows():
        rml = row["running_min_low"]
        if rml > 0:
            ratio = row["high"] / rml
            if ratio > best_ratio:
                best_ratio = ratio
                best_high_idx = i
                best_running_min = rml

    if best_high_idx < 0 or best_running_min is None:
        return {}

    target_low = best_running_min
    high_row = df.loc[best_high_idx]

    # 저점 시각: running_min_low가 target_low에 처음 도달한 시각
    low_candidates = df[df["running_min_low"] <= target_low + 0.5]
    if low_candidates.empty:
        return {}
    low_row = low_candidates.iloc[0]

    # low_time이 high_time 이전이어야 함
    if low_row["time"] > high_row["time"]:
        return {}

    return {
        "low_time": fmt_time(low_row["time"]),
        "low_price": float(target_low),
        "high_time": fmt_time(high_row["time"]),
        "high_price": float(high_row["high"]),
        "peak_ratio": round(float(best_ratio), 4),
        "rise_pct": round((float(best_ratio) - 1) * 100, 2),
        "day_open": day_open,
        "day_close": day_close,
    }


# ---------------------------------------------------------------------------
# STEP 7: 분봉 피처 계산
# ---------------------------------------------------------------------------

def compute_intraday_features(
    minute_df: pd.DataFrame,
    low_time_hhmm: str,
    open_09: float | None,
    prev_close: float | None,
) -> dict:
    """
    09:00 ~ low_time 구간의 분봉 피처 계산.
    low_time: 'HH:MM' 형식
    """
    features = {f: None for f in INTRADAY_FEATURES}

    if minute_df.empty or not low_time_hhmm:
        return features

    # low_time을 HHMMSS 형식으로 변환
    low_hhmmss = low_time_hhmm.replace(":", "") + "00"
    open_09_hhmmss = "090000"

    # gap_pct
    if prev_close and prev_close > 0 and open_09:
        features["gap_pct"] = round((open_09 - prev_close) / prev_close * 100, 4)

    # pre window: 09:00 ~ low_time (inclusive)
    pre_df = minute_df[
        (minute_df["time"] >= open_09_hhmmss) &
        (minute_df["time"] <= low_hhmmss)
    ].copy()

    # pre_duration_min
    low_min = hhmmss_to_minutes(low_hhmmss)
    if low_min is not None:
        features["pre_duration_min"] = low_min  # 09:00 기준 분 오프셋

    # pre_duration이 0~2분이면 분봉 피처 NULL
    if low_min is None or low_min < 3:
        features["low_drawdown_pct"] = None
        if open_09 and open_09 > 0:
            # low_drawdown은 계산 가능 (시가 기준)
            low_price_val = pre_df["low"].min() if not pre_df.empty else None
            if low_price_val is not None and pd.notna(low_price_val):
                features["low_drawdown_pct"] = round((float(low_price_val) - open_09) / open_09 * 100, 4)
        return features

    if pre_df.empty:
        return features

    # pre_volume_sum
    vol_sum = pre_df["volume"].sum()
    features["pre_volume_sum"] = float(vol_sum) if pd.notna(vol_sum) else None

    # pre_amount_sum (백만원 단위)
    amt_sum = pre_df["amount"].sum()
    features["pre_amount_sum"] = round(float(amt_sum) / 1_000_000, 2) if pd.notna(amt_sum) and amt_sum > 0 else None

    # pre_volatility_pct
    pre_high = pre_df["high"].max()
    pre_low = pre_df["low"].min()
    if pd.notna(pre_low) and pre_low > 0 and pd.notna(pre_high):
        features["pre_volatility_pct"] = round((float(pre_high) - float(pre_low)) / float(pre_low) * 100, 4)

    # pre_bullish_minute_ratio
    if len(pre_df) > 0:
        bullish = (pre_df["close"] >= pre_df["open"]).sum()
        features["pre_bullish_minute_ratio"] = round(float(bullish) / len(pre_df), 4)

    # first_5min_amount_share
    if low_min >= 5:
        first5_df = minute_df[
            (minute_df["time"] >= "090000") &
            (minute_df["time"] < "090500")
        ]
        first5_amt = first5_df["amount"].sum()
        if features["pre_amount_sum"] and features["pre_amount_sum"] > 0 and pd.notna(first5_amt):
            total_amt_raw = float(features["pre_amount_sum"]) * 1_000_000
            features["first_5min_amount_share"] = round(float(first5_amt) / total_amt_raw, 4) if total_amt_raw > 0 else None

    # low_drawdown_pct
    if open_09 and open_09 > 0 and pd.notna(pre_low):
        features["low_drawdown_pct"] = round((float(pre_low) - open_09) / open_09 * 100, 4)

    return features


# ---------------------------------------------------------------------------
# STEP 8: 일봉 피처 계산
# ---------------------------------------------------------------------------

def compute_daily_features(daily_stock_df: pd.DataFrame, trade_date_str: str) -> dict:
    """
    trade_date 기준 D-1 ~ D-21 일봉 피처 계산.
    daily_stock_df: 특정 종목의 전체 일봉 (date 오름차순 정렬)
    trade_date_str: 'YYYYMMDD'
    """
    features = {f: None for f in DAILY_FEATURES}
    features["prior_days_available"] = 0

    if daily_stock_df.empty:
        return features

    # trade_date 이전 영업일만 사용 (D-1, D-2, ...)
    trade_dt = pd.to_datetime(trade_date_str, format="%Y%m%d")
    past = daily_stock_df[daily_stock_df["date"] < trade_dt].sort_values("date", ascending=False).reset_index(drop=True)

    n = len(past)
    features["prior_days_available"] = n

    if n < 1:
        return features

    d1 = past.iloc[0]
    features["d1_close_won"] = float(d1["close"]) if pd.notna(d1["close"]) else None
    features["amount_d1_won"] = float(d1["trading_value"]) if pd.notna(d1.get("trading_value")) else None

    # ret_1d_pct: (D-1 close / D-2 close - 1) * 100
    if n >= 2 and pd.notna(past.iloc[1]["close"]) and float(past.iloc[1]["close"]) > 0:
        features["ret_1d_pct"] = round((float(d1["close"]) / float(past.iloc[1]["close"]) - 1) * 100, 4)

    # ret_5d_pct: (D-1 close / D-6 close - 1) * 100
    if n >= 6 and pd.notna(past.iloc[5]["close"]) and float(past.iloc[5]["close"]) > 0:
        features["ret_5d_pct"] = round((float(d1["close"]) / float(past.iloc[5]["close"]) - 1) * 100, 4)

    # ret_20d_pct: (D-1 close / D-21 close - 1) * 100 (가용 가장 오래된 날짜로 대체)
    oldest_idx = min(n - 1, 20)
    if oldest_idx > 0 and pd.notna(past.iloc[oldest_idx]["close"]) and float(past.iloc[oldest_idx]["close"]) > 0:
        features["ret_20d_pct"] = round((float(d1["close"]) / float(past.iloc[oldest_idx]["close"]) - 1) * 100, 4)

    # vol_ratio_d1_vs_d20: D-1 volume / avg(D-2..D-21)
    if n >= 2:
        lookback_end = min(n, 21)
        comparison_vols = past.iloc[1:lookback_end]["volume"].dropna()
        if len(comparison_vols) > 0:
            avg_vol = comparison_vols.mean()
            if avg_vol > 0 and pd.notna(d1["volume"]):
                features["vol_ratio_d1_vs_d20"] = round(float(d1["volume"]) / float(avg_vol), 4)

    # atr_20d_pct: avg(high - low) for D-1..D-20 / D-1 close * 100
    atr_window = past.iloc[:min(n, 20)]
    valid_atr = atr_window[atr_window["high"].notna() & atr_window["low"].notna()]
    if len(valid_atr) > 0 and pd.notna(d1["close"]) and float(d1["close"]) > 0:
        atr_vals = (valid_atr["high"].astype(float) - valid_atr["low"].astype(float)).mean()
        features["atr_20d_pct"] = round(float(atr_vals) / float(d1["close"]) * 100, 4)

    # ma5_dist_pct: (D-1 close - mean(D-1..D-5)) / mean(D-1..D-5) * 100
    ma5_window = past.iloc[:min(n, 5)]["close"].dropna()
    if len(ma5_window) >= 1:
        ma5 = ma5_window.astype(float).mean()
        if ma5 > 0 and pd.notna(d1["close"]):
            features["ma5_dist_pct"] = round((float(d1["close"]) - ma5) / ma5 * 100, 4)

    # ma20_dist_pct: (D-1 close - mean(D-1..D-20)) / mean(D-1..D-20) * 100
    ma20_window = past.iloc[:min(n, 20)]["close"].dropna()
    if len(ma20_window) >= 1:
        ma20 = ma20_window.astype(float).mean()
        if ma20 > 0 and pd.notna(d1["close"]):
            features["ma20_dist_pct"] = round((float(d1["close"]) - ma20) / ma20 * 100, 4)

    # d20_high_dist_pct: (D-1 close / max(high D-1..D-20) - 1) * 100
    high_window = past.iloc[:min(n, 20)]["high"].dropna()
    if len(high_window) >= 1 and pd.notna(d1["close"]) and float(d1["close"]) > 0:
        d20_max_high = high_window.astype(float).max()
        if d20_max_high > 0:
            features["d20_high_dist_pct"] = round((float(d1["close"]) / d20_max_high - 1) * 100, 4)

    return features


# ---------------------------------------------------------------------------
# STEP 9: 전체 케이스에 피처 부착
# ---------------------------------------------------------------------------

def enrich_cases(
    cases_df: pd.DataFrame,
    minute_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    name_map: dict,
    group: str,
) -> list[dict]:
    """
    cases_df: stock_code, trade_date, low_time(HH:MM), low_price, high_time, high_price,
              peak_ratio, rise_pct, day_open, day_close 포함
    """
    results = []
    n_missing_intraday = 0
    n_missing_daily = 0

    # 분봉 인덱스: (stock_code, trade_date) → DataFrame
    print(f"[{group}] 분봉 인덱스 생성 중...")
    minute_idx = {}
    for (sc, td), grp in minute_df.groupby(["stock_code", "trade_date"]):
        minute_idx[(sc, td)] = grp

    # 일봉 인덱스: stock_code → DataFrame (date 오름차순)
    daily_idx = {}
    for sc, grp in daily_df.groupby("stock_code"):
        daily_idx[sc] = grp.sort_values("date").reset_index(drop=True)

    total = len(cases_df)
    for i, row in cases_df.iterrows():
        if (i + 1) % 1000 == 0:
            print(f"  [{group}] {i+1:,}/{total:,} 처리 중...")

        sc = row["stock_code"]
        td = row["trade_date"]

        # 기본 메타
        record = {
            "group": group,
            "trade_date": td,
            "stock_code": sc,
            "stock_name": name_map.get(sc, ""),
            "peak_ratio": row.get("peak_ratio"),
            "rise_pct": row.get("rise_pct"),
            "low_time": row.get("low_time", ""),
            "low_price": row.get("low_price"),
            "high_time": row.get("high_time", ""),
            "high_price": row.get("high_price"),
            "day_open": row.get("day_open"),
            "day_close": row.get("day_close"),
        }

        # 분봉 피처
        m_df = minute_idx.get((sc, td))
        if m_df is None or m_df.empty:
            n_missing_intraday += 1
            for f in INTRADAY_FEATURES:
                record[f] = None
            record["prior_days_available"] = 0
        else:
            low_time = row.get("low_time", "")
            open_09_row = m_df[m_df["time"] >= "090000"].sort_values("time")
            open_09 = float(open_09_row.iloc[0]["open"]) if not open_09_row.empty else None

            # prev_close: D-1 일봉 종가
            prev_close = None
            d_df = daily_idx.get(sc)
            if d_df is not None:
                trade_dt = pd.to_datetime(td, format="%Y%m%d")
                past = d_df[d_df["date"] < trade_dt].sort_values("date", ascending=False)
                if not past.empty and pd.notna(past.iloc[0]["close"]):
                    prev_close = float(past.iloc[0]["close"])

            intra_features = compute_intraday_features(m_df, low_time, open_09, prev_close)
            record.update(intra_features)

        # 일봉 피처
        d_df = daily_idx.get(sc)
        if d_df is None or d_df.empty:
            n_missing_daily += 1
            for f in DAILY_FEATURES:
                record[f] = None
            record["prior_days_available"] = 0
        else:
            daily_features = compute_daily_features(d_df, td)
            record.update(daily_features)

        results.append(record)

    print(f"  [{group}] 분봉 누락: {n_missing_intraday}건, 일봉 누락: {n_missing_daily}건")
    return results


# ---------------------------------------------------------------------------
# STEP 10: control peak 계산 및 메타 채우기
# ---------------------------------------------------------------------------

def build_control_cases(control_df: pd.DataFrame, minute_df: pd.DataFrame) -> pd.DataFrame:
    """통제군 stock-day에 peak 정보 계산"""
    print("[Control] peak 계산 중...")
    minute_idx = {}
    for (sc, td), grp in minute_df.groupby(["stock_code", "trade_date"]):
        minute_idx[(sc, td)] = grp

    records = []
    total = len(control_df)
    n_no_data = 0

    for i, row in control_df.iterrows():
        sc = row["stock_code"]
        td = row["trade_date"]

        if (i + 1) % 2000 == 0:
            print(f"  [Control peak] {i+1:,}/{total:,} 처리 중...")

        m_df = minute_idx.get((sc, td))
        if m_df is None or m_df.empty:
            n_no_data += 1
            continue

        peak = compute_control_peak(m_df)
        if not peak:
            n_no_data += 1
            continue

        records.append({
            "stock_code": sc,
            "trade_date": td,
            **peak,
        })

    print(f"  [Control] peak 계산 완료: {len(records):,}건 (데이터 없음: {n_no_data}건)")
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# STEP 11: 피처 비교 요약 계산
# ---------------------------------------------------------------------------

def compute_feature_comparison(cases_df: pd.DataFrame) -> pd.DataFrame:
    """각 피처별 treated vs control 통계 비교"""
    rows = []
    for feat in ALL_FEATURES:
        if feat not in cases_df.columns:
            continue

        t_vals = cases_df[cases_df["group"] == "treated"][feat].dropna().astype(float)
        c_vals = cases_df[cases_df["group"] == "control"][feat].dropna().astype(float)

        if len(t_vals) == 0 and len(c_vals) == 0:
            continue

        def stats(v):
            if len(v) == 0:
                return dict(n=0, mean=None, median=None, p25=None, p75=None, std=None)
            return dict(
                n=len(v),
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
# STEP 12: 콘솔 보고
# ---------------------------------------------------------------------------

def print_report(cases_df: pd.DataFrame, comparison_df: pd.DataFrame, elapsed: float) -> None:
    n_treated = (cases_df["group"] == "treated").sum()
    n_control = (cases_df["group"] == "control").sum()

    print()
    print("=" * 75)
    print("  스파이크 사전 신호 피처 분석 결과")
    print("=" * 75)
    print(f"  실행 시간    : {elapsed:.1f}초")
    print(f"  Treated 케이스: {n_treated:,}건")
    print(f"  Control 케이스: {n_control:,}건")
    print()

    # 결측치 비율
    print("  [피처별 결측치 비율 (treated / control)]")
    for feat in ALL_FEATURES:
        if feat not in cases_df.columns:
            continue
        t_miss = cases_df[cases_df["group"] == "treated"][feat].isna().mean() * 100
        c_miss = cases_df[cases_df["group"] == "control"][feat].isna().mean() * 100
        if t_miss > 5 or c_miss > 5:
            print(f"    {feat:<30}  treated {t_miss:5.1f}%  control {c_miss:5.1f}%")
    print()

    # |normalized_diff| 상위 15개
    if not comparison_df.empty and "normalized_diff" in comparison_df.columns:
        top15 = (
            comparison_df
            .dropna(subset=["normalized_diff"])
            .assign(abs_nd=lambda d: d["normalized_diff"].abs())
            .sort_values("abs_nd", ascending=False)
            .head(15)
        )
        print("  [|normalized_diff| 상위 15개 피처]")
        print(f"  {'피처':<30}  {'normalized_diff':>16}  {'direction':<20}  {'treated_median':>14}  {'control_median':>14}")
        print("  " + "-" * 100)
        for _, r in top15.iterrows():
            nd_str = f"{r['normalized_diff']:+.4f}"
            tm = f"{r['treated_median']:.4f}" if r["treated_median"] is not None else "N/A"
            cm = f"{r['control_median']:.4f}" if r["control_median"] is not None else "N/A"
            print(f"  {r['feature']:<30}  {nd_str:>16}  {r['direction']:<20}  {tm:>14}  {cm:>14}")

        print()
        print("  [해석]")
        for _, r in top15.iterrows():
            nd = r["normalized_diff"]
            if nd is None:
                continue
            feat = r["feature"]
            tm = r["treated_median"]
            cm = r["control_median"]
            if tm is None or cm is None:
                continue
            ratio = tm / cm if cm and abs(cm) > 1e-9 else None
            if r["direction"] == "higher_in_spike":
                ratio_str = f"(treated 중앙값 {ratio:.2f}x)" if ratio else ""
                print(f"    {feat}: 스파이크일이 더 높음 {ratio_str}")
            elif r["direction"] == "lower_in_spike":
                ratio_str = f"(treated 중앙값 {ratio:.2f}x)" if ratio else ""
                print(f"    {feat}: 스파이크일이 더 낮음 {ratio_str}")

    print()
    print(f"  산출물:")
    print(f"    {OUTPUT_CASES_CSV}")
    print(f"    {OUTPUT_COMPARE_CSV}")
    print("=" * 75)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()

    print("=" * 75)
    print("  스파이크 사전 신호 피처 추출 (2026-04 ~ 2026-05)")
    print("=" * 75)

    # 1) treated 로드
    print("\n[1/9] Treated 케이스 로드...")
    treated = load_treated(SPIKES_CSV)

    # 2) DB 연결
    print("\n[2/9] DB 연결...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True

    # 3) 종목명 로드
    print("\n[3/9] 종목명 로드...")
    name_map = load_stock_names(conn)
    print(f"  {len(name_map):,}개 종목명")

    # 4) 통제군 stock-day 생성
    print("\n[4/9] 통제군 stock-day 생성...")
    control_stockdays = build_control_stockdays(treated, conn)

    # 5) 분봉 데이터 일괄 로드 (treated + control 동일 종목 집합)
    all_stocks = treated["stock_code"].unique().tolist()
    print(f"\n[5/9] 분봉 데이터 로드 ({len(all_stocks):,}개 종목)...")
    minute_df = load_minute_data(all_stocks, conn)

    # 6) 일봉 데이터 일괄 로드
    print(f"\n[6/9] 일봉 데이터 로드...")
    daily_df = load_daily_data(all_stocks, conn)

    conn.close()
    print("  DB 연결 종료")

    # 7) 통제군 peak 계산
    print("\n[7/9] 통제군 peak 계산...")
    control_with_peak = build_control_cases(control_stockdays, minute_df)
    if control_with_peak.empty:
        print("  WARNING: 통제군 peak 계산 결과 없음")

    # 8) treated/control 피처 enrich
    print("\n[8/9] 피처 enrich...")

    # treated: open_09는 CSV의 open_09 컬럼 사용
    # low_time은 HH:MM 형식
    treated_cases = treated.rename(columns={
        "open_09": "day_open_09",
    }).copy()
    # day_open은 day_open 컬럼이 있으면 사용, 없으면 open_09
    if "day_open" not in treated_cases.columns:
        treated_cases["day_open"] = treated_cases.get("day_open_09")
    if "day_close" not in treated_cases.columns:
        treated_cases["day_close"] = treated_cases.get("close_eod")

    print("  [Treated 피처 계산]")
    treated_records = enrich_cases(treated_cases, minute_df, daily_df, name_map, "treated")

    print("  [Control 피처 계산]")
    if not control_with_peak.empty:
        control_records = enrich_cases(control_with_peak, minute_df, daily_df, name_map, "control")
    else:
        control_records = []

    all_records = treated_records + control_records
    cases_df = pd.DataFrame(all_records)

    # 컬럼 순서 정리 (META_COLS에 이미 prior_days_available 포함됨 — 중복 제거)
    col_order = META_COLS + ALL_FEATURES
    existing_cols = [c for c in col_order if c in cases_df.columns]
    extra_cols = [c for c in cases_df.columns if c not in existing_cols]
    cases_df = cases_df[existing_cols + extra_cols]

    # 9) 피처 비교 + 저장
    print("\n[9/9] 피처 비교 계산 및 저장...")
    comparison_df = compute_feature_comparison(cases_df)

    cases_df.to_csv(OUTPUT_CASES_CSV, index=False, encoding="utf-8-sig")
    comparison_df.to_csv(OUTPUT_COMPARE_CSV, index=False, encoding="utf-8-sig")
    print(f"  cases_with_features.csv: {len(cases_df):,}행")
    print(f"  feature_comparison.csv: {len(comparison_df):,}행")

    elapsed = time.time() - t0
    print_report(cases_df, comparison_df, elapsed)


if __name__ == "__main__":
    main()
