"""
signal_combo_phase3_entry_compare.py
=====================================
Phase 3: 진입 방식 A(10:00 이동) vs B(Pullback 후 반등) 비교 백테스트

진입 조건 (Phase 1/2 확정):
  ret_20d_pct >= 25 AND atr_20d_pct >= 8

진입 방식 A (베이스라인):
  - D당일 10:00:00 분봉의 close에 진입
  - 슬리피지 +20bp
  - 모든 신호 케이스 진입

진입 방식 B (Pullback 후 반등):
  - reference_price = 09:30:00 분봉 close
  - 09:31~11:30 스캔:
    1. 분봉 close <= reference * (1 - 1%) → 조건1 충족
    2. 조건1 이후 close > open 양봉 첫 발견 → 진입
  - 슬리피지 +20bp
  - 11:30까지 조건1+2 미충족 시 미진입

매도 그리드 (Phase 2와 동일 240셀):
  target_pct: 1.5, 2.0, 2.5, 3.0
  stop_pct:   0.8, 1.0, 1.5, 2.0
  max_hold:   intraday, next_day, 60min, 120min, 240min
  trail:      none / trigger1.5_trail0.5 / trigger1.0_trail0.5

비용:
  진입 슬리피지 +20bp, 매도 슬리피지 +20bp, 수수료 0.015%×2, 거래세 0.18%
  총 거래비용 ≈ 0.21% (슬리피지는 가격에 별도 반영)

OOS 통과 기준:
  avg_return_pct >= 0.5% AND win_rate >= 55% AND expectancy_won > 0
  AND sharpe > 0.3 AND n_trades >= 5

사용법:
  cd RoboTrader_template
  python scripts/signal_combo_phase3_entry_compare.py
"""

from __future__ import annotations

import io
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time
import itertools
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

REPORT_DIR = PROJECT_ROOT / "reports" / "signal_combo_aprmay"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

CASES_CSV = REPORT_DIR / "cases_v2.csv"
OUTPUT_GRID_CSV   = REPORT_DIR / "phase3_grid.csv"
OUTPUT_DIAG_CSV   = REPORT_DIR / "phase3_diagnosis.csv"

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

# ---------------------------------------------------------------------------
# 진입 조건 (확정)
# ---------------------------------------------------------------------------
ENTRY_RET20D_MIN = 25.0
ENTRY_ATR20D_MIN = 8.0

# IS / OOS 분리
IS_START  = "20260401"
IS_END    = "20260430"
OOS_START = "20260501"
OOS_END   = "20260523"

# ---------------------------------------------------------------------------
# 비용 상수
# ---------------------------------------------------------------------------
SLIPPAGE_ENTRY_BPS = 20
SLIPPAGE_EXIT_BPS  = 20
COMMISSION_RT      = 0.00015
TRANSACTION_TAX    = 0.0018
COST_RATE          = COMMISSION_RT * 2 + TRANSACTION_TAX  # 0.21%

CAPITAL_PER_TRADE  = 1_000_000  # 100만원

# ---------------------------------------------------------------------------
# 방식 B 파라미터
# ---------------------------------------------------------------------------
PULLBACK_THRESHOLD = -1.0   # reference 대비 -1% 하락
PULLBACK_SCAN_END  = "113000"  # 11:30까지 스캔

# ---------------------------------------------------------------------------
# 매도 그리드
# ---------------------------------------------------------------------------
TARGET_PCTS = [1.5, 2.0, 2.5, 3.0]
STOP_PCTS   = [0.8, 1.0, 1.5, 2.0]
MAX_HOLDS   = ["intraday", "next_day", "60min", "120min", "240min"]
TRAILS      = [
    "none",
    "trigger1.5_trail0.5",
    "trigger1.0_trail0.5",
]

# ---------------------------------------------------------------------------
# 거래일 유틸
# ---------------------------------------------------------------------------

def get_next_trading_day(trade_date_str: str, all_trade_dates: list[str]) -> Optional[str]:
    dates_sorted = sorted(all_trade_dates)
    for i, d in enumerate(dates_sorted):
        if d == trade_date_str and i + 1 < len(dates_sorted):
            return dates_sorted[i + 1]
    for d in dates_sorted:
        if d > trade_date_str:
            return d
    return None


def get_hold_deadline(
    trade_date_str: str,
    entry_time_str: str,
    max_hold: str,
    all_trade_dates: list[str],
) -> tuple[str, str]:
    """(deadline_date_str, deadline_time_str) 반환. entry_time_str: 'HHMMSS'"""
    if max_hold == "intraday":
        return trade_date_str, "153000"
    if max_hold == "next_day":
        nxt = get_next_trading_day(trade_date_str, all_trade_dates)
        return (nxt if nxt else trade_date_str), "153000"

    entry_h = int(entry_time_str[:2])
    entry_m = int(entry_time_str[2:4])
    entry_dt = datetime(2000, 1, 1, entry_h, entry_m)

    minutes_map = {"60min": 60, "120min": 120, "240min": 240}
    delta = timedelta(minutes=minutes_map[max_hold])
    deadline_dt = entry_dt + delta

    eod = datetime(2000, 1, 1, 15, 30)
    if deadline_dt > eod:
        deadline_dt = eod

    return trade_date_str, deadline_dt.strftime("%H%M%S")


# ---------------------------------------------------------------------------
# 분봉 데이터 로드 (09:30~15:30 전체 로드)
# ---------------------------------------------------------------------------

def load_minute_candles(entries_df: pd.DataFrame, conn) -> pd.DataFrame:
    """
    09:30~15:30 전체 분봉 로드.
    - 방식 A: 10:00 진입 분봉 필요
    - 방식 B: 09:30 reference + 09:31~11:30 스캔 필요
    - 매도 시뮬: 진입 이후 분봉 필요
    """
    pairs = entries_df[["stock_code", "trade_date"]].copy()
    pairs["stock_code"] = pairs["stock_code"].astype(str).str.zfill(6)
    pairs["trade_date"] = pairs["trade_date"].astype(str)

    date_min = pairs["trade_date"].min()
    stock_codes = sorted(pairs["stock_code"].unique())
    stock_list_sql = ",".join(f"'{s}'" for s in stock_codes)

    print(f"[분봉] {len(stock_codes)}개 종목, {date_min}~{OOS_END} 09:30~15:30 로드 중...")
    cur = conn.cursor()
    cur.execute(f"""
        SELECT stock_code, trade_date, time, open, high, low, close, volume, amount
        FROM minute_candles
        WHERE trade_date >= '{date_min}' AND trade_date <= '{OOS_END}'
          AND time >= '093000' AND time <= '153000'
          AND stock_code IN ({stock_list_sql})
        ORDER BY stock_code, trade_date, time
    """)
    rows = cur.fetchall()
    cols = ["stock_code", "trade_date", "time", "open", "high", "low", "close", "volume", "amount"]
    df = pd.DataFrame(rows, columns=cols)

    if df.empty:
        return df

    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    df["trade_date"] = df["trade_date"].astype(str)
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    print(f"[분봉] {len(df):,}행 로드 완료")
    return df


# ---------------------------------------------------------------------------
# 진입가 결정
# ---------------------------------------------------------------------------

def resolve_entry_method_a(day_bars: pd.DataFrame) -> Optional[tuple[float, str]]:
    """
    방식 A: 10:00:00 close를 진입가로 사용.
    반환: (entry_price_raw, entry_time_str) 또는 None
    """
    bar_1000 = day_bars[day_bars["time"] == "100000"]
    if bar_1000.empty:
        # 10:00 봉 없으면 09:59 이전 가장 가까운 close
        nearby = day_bars[day_bars["time"] <= "100000"]
        if nearby.empty:
            return None
        close_val = float(nearby.iloc[-1]["close"])
        time_val  = str(nearby.iloc[-1]["time"])
    else:
        close_val = float(bar_1000.iloc[0]["close"])
        time_val  = "100000"

    if pd.isna(close_val):
        return None
    return close_val, time_val


def resolve_entry_method_b(
    day_bars: pd.DataFrame,
    reference_price: float,
) -> Optional[tuple[float, str]]:
    """
    방식 B: Pullback 후 반등 진입.
    - reference_price: 09:30:00 close
    - 09:31~11:30 스캔
    - 조건1: close <= reference * (1 - 1%)
    - 조건2: 조건1 이후 첫 양봉(close > open)
    반환: (entry_price_raw, entry_time_str) 또는 None
    """
    pullback_threshold_price = reference_price * (1 + PULLBACK_THRESHOLD / 100)

    # 09:31~11:30 분봉만 스캔
    scan_bars = day_bars[
        (day_bars["time"] >= "093100") & (day_bars["time"] <= PULLBACK_SCAN_END)
    ].copy()

    if scan_bars.empty:
        return None

    condition1_met = False

    for _, bar in scan_bars.iterrows():
        bar_close = bar["close"]
        bar_open  = bar["open"]
        bar_time  = str(bar["time"])

        if pd.isna(bar_close) or pd.isna(bar_open):
            continue

        bar_close = float(bar_close)
        bar_open  = float(bar_open)

        if not condition1_met:
            # 조건1 체크: close <= pullback threshold
            if bar_close <= pullback_threshold_price:
                condition1_met = True
            # 조건1 미충족이면 계속 스캔
            continue

        # 조건1 충족 후 → 첫 양봉 찾기
        if bar_close > bar_open:
            return float(bar_close), bar_time

    return None


# ---------------------------------------------------------------------------
# 진입 후 분봉 슬라이스 추출
# ---------------------------------------------------------------------------

def get_post_entry_bars(
    day_bars: pd.DataFrame,
    entry_time: str,
) -> pd.DataFrame:
    """진입 시점 다음 분봉부터 반환 (entry_time 이후)."""
    # entry_time 봉의 다음 분봉부터 (entry_time 초과)
    after = day_bars[day_bars["time"] > entry_time].copy()
    return after.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 단일 매매 시뮬레이션 (Phase 2와 동일 로직)
# ---------------------------------------------------------------------------

def simulate_trade(
    bars: pd.DataFrame,
    entry_price_raw: float,
    target_pct: float,
    stop_pct: float,
    max_hold: str,
    trail: str,
    trade_date: str,
    entry_time: str,
    all_trade_dates: list[str],
    next_day_bars: Optional[pd.DataFrame] = None,
) -> dict:
    entry_price = entry_price_raw * (1 + SLIPPAGE_ENTRY_BPS / 10000)

    take_profit_price = entry_price_raw * (1 + target_pct / 100)
    stop_loss_price   = entry_price_raw * (1 - stop_pct / 100)

    trail_trigger_pct = None
    trail_pct_val = None
    if trail == "trigger1.5_trail0.5":
        trail_trigger_pct = 1.5
        trail_pct_val = 0.5
    elif trail == "trigger1.0_trail0.5":
        trail_trigger_pct = 1.0
        trail_pct_val = 0.5

    deadline_date, deadline_time = get_hold_deadline(
        trade_date, entry_time, max_hold, all_trade_dates
    )

    trail_activated = False
    peak_price = entry_price_raw

    if max_hold == "next_day" and next_day_bars is not None and not next_day_bars.empty:
        all_bars = pd.concat([bars, next_day_bars], ignore_index=True)
    else:
        all_bars = bars

    exit_price_raw = None
    exit_reason = "hold_expired"

    for _, bar in all_bars.iterrows():
        bar_date  = str(bar["trade_date"])
        bar_time  = str(bar["time"])
        bar_high  = float(bar["high"])  if pd.notna(bar["high"])  else None
        bar_low   = float(bar["low"])   if pd.notna(bar["low"])   else None
        bar_close = float(bar["close"]) if pd.notna(bar["close"]) else None
        bar_open  = float(bar["open"])  if pd.notna(bar["open"])  else None

        if bar_high is None or bar_low is None or bar_close is None:
            continue

        if bar_date > deadline_date or (bar_date == deadline_date and bar_time > deadline_time):
            break

        # D+1 갭다운 처리
        is_next_day_bar = (bar_date != trade_date)
        if is_next_day_bar and bar_time == "093100":
            if bar_open is not None and bar_open <= stop_loss_price:
                exit_price_raw = bar_open
                exit_reason = "gap_stop"
                break

        # 트레일 활성화 체크
        if trail_trigger_pct is not None and not trail_activated:
            trigger_price = entry_price_raw * (1 + trail_trigger_pct / 100)
            if bar_high >= trigger_price:
                trail_activated = True
                peak_price = max(peak_price, bar_high)

        if trail_activated:
            peak_price = max(peak_price, bar_high)

        # 트레일 청산
        if trail_activated:
            trail_stop = peak_price * (1 - trail_pct_val / 100)
            if bar_low <= trail_stop:
                exit_price_raw = trail_stop
                exit_reason = "trail"
                break

        hit_tp = bar_high >= take_profit_price
        hit_sl = bar_low  <= stop_loss_price

        if hit_tp and hit_sl:
            exit_price_raw = stop_loss_price
            exit_reason = "stop"
            break
        elif hit_tp:
            exit_price_raw = take_profit_price
            exit_reason = "target"
            break
        elif hit_sl:
            exit_price_raw = stop_loss_price
            exit_reason = "stop"
            break

    # 홀딩 만료: 데드라인 봉 close
    if exit_price_raw is None:
        deadline_bar = all_bars[
            (all_bars["trade_date"].astype(str) == deadline_date) &
            (all_bars["time"].astype(str) <= deadline_time)
        ]
        if not deadline_bar.empty:
            exit_price_raw = float(deadline_bar.iloc[-1]["close"])
        elif not all_bars.empty:
            exit_price_raw = float(all_bars.iloc[-1]["close"])
        else:
            exit_price_raw = entry_price_raw
        exit_reason = "hold_expired"

    # 수익률 계산
    exit_price  = exit_price_raw * (1 - SLIPPAGE_EXIT_BPS / 10000)
    gross_return = (exit_price / entry_price) - 1
    net_return   = gross_return - COST_RATE

    return {
        "exit_price_raw":  round(exit_price_raw, 2),
        "exit_reason":     exit_reason,
        "trail_activated": trail_activated,
        "net_return_pct":  round(net_return * 100, 4),
    }


# ---------------------------------------------------------------------------
# 셀별 통계
# ---------------------------------------------------------------------------

def compute_cell_stats(trade_results: list[dict]) -> dict:
    empty = {
        "n_trades": 0,
        "win_rate": None,
        "avg_return_pct": None,
        "expectancy_won": None,
        "profit_factor": None,
        "max_drawdown_pct": None,
        "sharpe": None,
        "exit_target": 0,
        "exit_stop": 0,
        "exit_trail": 0,
        "exit_hold_expired": 0,
        "exit_gap_stop": 0,
    }
    if not trade_results:
        return empty

    returns = np.array([t["net_return_pct"] for t in trade_results])
    n = len(returns)

    wins   = returns[returns > 0]
    losses = returns[returns <= 0]

    win_rate      = len(wins) / n if n > 0 else 0.0
    avg_return    = float(np.mean(returns))
    expectancy_won = avg_return / 100 * CAPITAL_PER_TRADE

    gross_profit = float(np.sum(wins))   if len(wins)   > 0 else 0.0
    gross_loss   = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )

    cumulative   = np.cumsum(returns)
    running_max  = np.maximum.accumulate(cumulative)
    drawdowns    = running_max - cumulative
    max_dd       = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    if n >= 2 and float(np.std(returns)) > 0:
        sharpe = float(np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(252))
    else:
        sharpe = 0.0

    exit_counts = {"target": 0, "stop": 0, "trail": 0, "hold_expired": 0, "gap_stop": 0}
    for t in trade_results:
        r = t["exit_reason"]
        exit_counts[r] = exit_counts.get(r, 0) + 1

    return {
        "n_trades":        n,
        "win_rate":        round(win_rate, 4),
        "avg_return_pct":  round(avg_return, 4),
        "expectancy_won":  round(expectancy_won, 1),
        "profit_factor":   round(profit_factor, 4) if profit_factor != float("inf") else 9999.0,
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe":          round(sharpe, 4),
        "exit_target":     exit_counts.get("target", 0),
        "exit_stop":       exit_counts.get("stop", 0),
        "exit_trail":      exit_counts.get("trail", 0),
        "exit_hold_expired": exit_counts.get("hold_expired", 0),
        "exit_gap_stop":   exit_counts.get("gap_stop", 0),
    }


def check_pass(stats: dict) -> bool:
    if stats["n_trades"] < 5:
        return False
    if stats["avg_return_pct"] is None or stats["avg_return_pct"] < 0.5:
        return False
    if stats["win_rate"] is None or stats["win_rate"] < 0.55:
        return False
    if stats["expectancy_won"] is None or stats["expectancy_won"] <= 0:
        return False
    if stats["sharpe"] is None or stats["sharpe"] < 0.3:
        return False
    return True


# ---------------------------------------------------------------------------
# 진단 통계 (whip-saw 분석)
# ---------------------------------------------------------------------------

def compute_diagnosis(
    trade_records: list[dict],
    minute_groups: dict,
    all_trade_dates: list[str],
) -> dict:
    """
    진입 후 5/10/30분 평균 수익률, 진입 후 최저점 중앙값, 손절 -0.8% 도달률 계산.
    trade_records: {stock_code, trade_date, entry_price_raw, entry_time, split} 포함
    """
    ret_5min  = []
    ret_10min = []
    ret_30min = []
    low_dips  = []   # 진입 후 120분 내 최저점 수익률 (%)
    stop08_hits = 0  # -0.8% 도달 건수
    total = 0

    for rec in trade_records:
        sc         = rec["stock_code"]
        td         = rec["trade_date"]
        entry_raw  = rec["entry_price_raw"]
        entry_time = rec["entry_time"]  # "HHMMSS"

        entry_price = entry_raw * (1 + SLIPPAGE_ENTRY_BPS / 10000)

        key = (sc, td)
        day_bars = minute_groups.get(key)
        if day_bars is None or day_bars.empty:
            continue

        post_bars = day_bars[day_bars["time"] > entry_time].copy()
        if post_bars.empty:
            continue

        total += 1

        # 진입 후 5/10/30분 수익률 (close 기준)
        entry_h = int(entry_time[:2])
        entry_m = int(entry_time[2:4])
        entry_dt = datetime(2000, 1, 1, entry_h, entry_m)

        for minutes, ret_list in [(5, ret_5min), (10, ret_10min), (30, ret_30min)]:
            target_dt   = entry_dt + timedelta(minutes=minutes)
            target_time = target_dt.strftime("%H%M%S")
            # target_time 이하의 마지막 봉 close
            candidate = post_bars[post_bars["time"] <= target_time]
            if not candidate.empty:
                c = float(candidate.iloc[-1]["close"])
                if not pd.isna(c):
                    ret_list.append((c / entry_price - 1) * 100)

        # 진입 후 120분 내 최저점
        cap_dt   = entry_dt + timedelta(minutes=120)
        cap_time = cap_dt.strftime("%H%M%S")
        cap_time = min(cap_time, "153000")
        window   = post_bars[post_bars["time"] <= cap_time]
        if not window.empty:
            min_low = window["low"].min()
            if pd.notna(min_low):
                dip = (float(min_low) / entry_price - 1) * 100
                low_dips.append(dip)

        # 손절 -0.8% 도달 여부
        stop08_price = entry_raw * (1 - 0.8 / 100)
        window_full  = post_bars.copy()
        hit = (window_full["low"].dropna().astype(float) <= stop08_price).any()
        if hit:
            stop08_hits += 1

    result = {
        "n_entries":           total,
        "avg_ret_5min_pct":    round(float(np.mean(ret_5min)), 4)  if ret_5min  else None,
        "avg_ret_10min_pct":   round(float(np.mean(ret_10min)), 4) if ret_10min else None,
        "avg_ret_30min_pct":   round(float(np.mean(ret_30min)), 4) if ret_30min else None,
        "median_low_dip_pct":  round(float(np.median(low_dips)), 4) if low_dips else None,
        "stop08_reach_rate":   round(stop08_hits / total, 4) if total > 0 else None,
        "stop08_hits":         stop08_hits,
    }
    return result


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    t_start = time.time()

    print("=" * 70)
    print("Phase 3: 진입 방식 A(10:00) vs B(Pullback 반등) 비교 백테스트")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. 진입 케이스 로드 및 필터
    # ------------------------------------------------------------------
    df_cases = pd.read_csv(CASES_CSV)
    df_cases["trade_date"] = df_cases["trade_date"].astype(str)
    df_cases["stock_code"] = df_cases["stock_code"].astype(str).str.zfill(6)

    mask_entry = (
        (df_cases["ret_20d_pct"] >= ENTRY_RET20D_MIN) &
        (df_cases["atr_20d_pct"] >= ENTRY_ATR20D_MIN)
    )
    base_entries = df_cases[mask_entry].copy().reset_index(drop=True)

    mask_is  = base_entries["trade_date"].between(IS_START, IS_END)
    mask_oos = base_entries["trade_date"].between(OOS_START, OOS_END)

    is_base  = base_entries[mask_is].copy()
    oos_base = base_entries[mask_oos].copy()

    print(f"\n[베이스 케이스 (신호 조건 충족)]")
    print(f"  IS  (4월): {len(is_base)}건")
    print(f"  OOS (5월): {len(oos_base)}건")
    print(f"  합계: {len(base_entries)}건")

    all_trade_dates = sorted(df_cases["trade_date"].unique().tolist())

    # ------------------------------------------------------------------
    # 2. 분봉 데이터 로드
    # ------------------------------------------------------------------
    conn = psycopg2.connect(**DB_MINUTE)
    try:
        minute_df = load_minute_candles(base_entries, conn)
    finally:
        conn.close()

    if minute_df.empty:
        print("[ERROR] 분봉 데이터 없음. DB 연결 확인 필요.")
        sys.exit(1)

    # (stock_code, trade_date) 그룹화 (09:30~15:30 전체)
    minute_groups: dict[tuple[str, str], pd.DataFrame] = {}
    for (sc, td), grp in minute_df.groupby(["stock_code", "trade_date"]):
        minute_groups[(str(sc), str(td))] = grp.reset_index(drop=True)

    print(f"[분봉] 그룹 수: {len(minute_groups):,}개 (종목×날짜)")

    # ------------------------------------------------------------------
    # 3. 진입 방식 A/B — 실제 진입 케이스 확정
    # ------------------------------------------------------------------
    print("\n[진입 결정 중...]")

    # entry_info: {split: {method: [{stock_code, trade_date, entry_price_raw, entry_time, stock_name}]}}
    entry_info: dict[str, dict[str, list[dict]]] = {
        "IS":  {"A": [], "B": []},
        "OOS": {"A": [], "B": []},
    }

    for split_name, split_base in [("IS", is_base), ("OOS", oos_base)]:
        for _, row in split_base.iterrows():
            sc   = str(row["stock_code"])
            td   = str(row["trade_date"])
            name = row.get("stock_name", "")
            key  = (sc, td)

            day_bars = minute_groups.get(key, pd.DataFrame())
            if day_bars.empty:
                continue

            # 방식 A: 10:00 close
            result_a = resolve_entry_method_a(day_bars)
            if result_a is not None:
                entry_price_a, entry_time_a = result_a
                entry_info[split_name]["A"].append({
                    "stock_code":      sc,
                    "trade_date":      td,
                    "stock_name":      name,
                    "entry_price_raw": entry_price_a,
                    "entry_time":      entry_time_a,
                    "split":           split_name,
                })

            # 방식 B: Pullback 후 반등
            # reference: 09:30:00 close
            bar_0930 = day_bars[day_bars["time"] == "093000"]
            if bar_0930.empty:
                continue
            ref_price = float(bar_0930.iloc[0]["close"])
            if pd.isna(ref_price):
                continue

            result_b = resolve_entry_method_b(day_bars, ref_price)
            if result_b is not None:
                entry_price_b, entry_time_b = result_b
                entry_info[split_name]["B"].append({
                    "stock_code":      sc,
                    "trade_date":      td,
                    "stock_name":      name,
                    "entry_price_raw": entry_price_b,
                    "entry_time":      entry_time_b,
                    "split":           split_name,
                })

    n_a_is  = len(entry_info["IS"]["A"])
    n_a_oos = len(entry_info["OOS"]["A"])
    n_b_is  = len(entry_info["IS"]["B"])
    n_b_oos = len(entry_info["OOS"]["B"])

    print(f"\n[방식 A (10:00 진입)]")
    print(f"  IS  진입: {n_a_is}건  /  OOS 진입: {n_a_oos}건")
    print(f"[방식 B (Pullback 반등)]")
    pct_b_is  = n_b_is  / len(is_base)  * 100 if len(is_base)  > 0 else 0
    pct_b_oos = n_b_oos / len(oos_base) * 100 if len(oos_base) > 0 else 0
    print(f"  IS  진입: {n_b_is}건 ({pct_b_is:.1f}%)  /  OOS 진입: {n_b_oos}건 ({pct_b_oos:.1f}%)")
    print(f"  IS  미진입: {len(is_base)  - n_b_is}건  /  OOS 미진입: {len(oos_base) - n_b_oos}건")

    # ------------------------------------------------------------------
    # 4. 진단 통계 (whip-saw 분석)
    # ------------------------------------------------------------------
    print("\n[진단 통계 계산 중 (A/B 각각)...]")

    all_a_records = entry_info["IS"]["A"] + entry_info["OOS"]["A"]
    all_b_records = entry_info["IS"]["B"] + entry_info["OOS"]["B"]

    diag_a = compute_diagnosis(all_a_records, minute_groups, all_trade_dates)
    diag_b = compute_diagnosis(all_b_records, minute_groups, all_trade_dates)

    # IS/OOS 별도 진단도
    diag_a_is  = compute_diagnosis(entry_info["IS"]["A"],  minute_groups, all_trade_dates)
    diag_a_oos = compute_diagnosis(entry_info["OOS"]["A"], minute_groups, all_trade_dates)
    diag_b_is  = compute_diagnosis(entry_info["IS"]["B"],  minute_groups, all_trade_dates)
    diag_b_oos = compute_diagnosis(entry_info["OOS"]["B"], minute_groups, all_trade_dates)

    # ------------------------------------------------------------------
    # 5. 그리드 (240셀) 시뮬레이션 — 방식 A / B 동시
    # ------------------------------------------------------------------
    grid = list(itertools.product(TARGET_PCTS, STOP_PCTS, MAX_HOLDS, TRAILS))
    assert len(grid) == 240, f"그리드 셀 수 불일치: {len(grid)}"
    print(f"\n[그리드] {len(grid)}셀 × 2방식 × 2분기 = {len(grid)*4}번 실행")

    results = []

    for cell_idx, (target_pct, stop_pct, max_hold, trail) in enumerate(grid):
        cell_id = f"C{cell_idx:03d}"

        cell_row: dict = {
            "entry_method": None,  # placeholder — 두 방식 각각 row 추가
            "cell_id": cell_id,
            "target_pct": target_pct,
            "stop_pct": stop_pct,
            "max_hold": max_hold,
            "trail": trail,
        }

        for method in ("A", "B"):
            is_trades  = []
            oos_trades = []

            for split_name in ("IS", "OOS"):
                records = entry_info[split_name][method]

                for rec in records:
                    sc         = rec["stock_code"]
                    td         = rec["trade_date"]
                    entry_raw  = rec["entry_price_raw"]
                    entry_time = rec["entry_time"]

                    key = (sc, td)
                    day_bars = minute_groups.get(key, pd.DataFrame())

                    # 진입 시점 이후 분봉
                    post_bars = get_post_entry_bars(day_bars, entry_time)

                    # D+1 분봉 (next_day max_hold)
                    next_day_bars = None
                    if max_hold == "next_day":
                        nxt = get_next_trading_day(td, all_trade_dates)
                        if nxt:
                            next_day_bars = minute_groups.get((sc, nxt))

                    trade_result = simulate_trade(
                        bars=post_bars,
                        entry_price_raw=entry_raw,
                        target_pct=target_pct,
                        stop_pct=stop_pct,
                        max_hold=max_hold,
                        trail=trail,
                        trade_date=td,
                        entry_time=entry_time,
                        all_trade_dates=all_trade_dates,
                        next_day_bars=next_day_bars,
                    )

                    if split_name == "IS":
                        is_trades.append(trade_result)
                    else:
                        oos_trades.append(trade_result)

            is_stats  = compute_cell_stats(is_trades)
            oos_stats = compute_cell_stats(oos_trades)
            oos_pass  = check_pass(oos_stats)

            row_out = {
                "entry_method": method,
                "cell_id": cell_id,
                "target_pct": target_pct,
                "stop_pct": stop_pct,
                "max_hold": max_hold,
                "trail": trail,
                # IS
                "is_n_trades":          is_stats["n_trades"],
                "is_win_rate":          is_stats["win_rate"],
                "is_avg_return_pct":    is_stats["avg_return_pct"],
                "is_expectancy_won":    is_stats["expectancy_won"],
                "is_profit_factor":     is_stats["profit_factor"],
                "is_max_drawdown_pct":  is_stats["max_drawdown_pct"],
                "is_sharpe":            is_stats["sharpe"],
                "is_exit_target":       is_stats["exit_target"],
                "is_exit_stop":         is_stats["exit_stop"],
                "is_exit_trail":        is_stats["exit_trail"],
                "is_exit_hold_expired": is_stats["exit_hold_expired"],
                "is_exit_gap_stop":     is_stats["exit_gap_stop"],
                # OOS
                "oos_n_trades":          oos_stats["n_trades"],
                "oos_win_rate":          oos_stats["win_rate"],
                "oos_avg_return_pct":    oos_stats["avg_return_pct"],
                "oos_expectancy_won":    oos_stats["expectancy_won"],
                "oos_profit_factor":     oos_stats["profit_factor"],
                "oos_max_drawdown_pct":  oos_stats["max_drawdown_pct"],
                "oos_sharpe":            oos_stats["sharpe"],
                "oos_exit_target":       oos_stats["exit_target"],
                "oos_exit_stop":         oos_stats["exit_stop"],
                "oos_exit_trail":        oos_stats["exit_trail"],
                "oos_exit_hold_expired": oos_stats["exit_hold_expired"],
                "oos_exit_gap_stop":     oos_stats["exit_gap_stop"],
                "pass_flag":             oos_pass,
            }
            results.append(row_out)

        # 진행 상황 (40셀마다 = 방식A+B 각 20셀)
        if (cell_idx + 1) % 40 == 0 or cell_idx == 0:
            elapsed = time.time() - t_start
            print(f"  [{cell_idx+1:3d}/240] {elapsed:.1f}s | target={target_pct}% stop={stop_pct}% hold={max_hold}")

    # ------------------------------------------------------------------
    # 6. CSV 저장
    # ------------------------------------------------------------------
    df_results = pd.DataFrame(results)
    # 정렬: entry_method ASC, OOS avg_return_pct DESC
    df_results = df_results.sort_values(
        ["entry_method", "oos_avg_return_pct"], ascending=[True, False]
    ).reset_index(drop=True)
    df_results.to_csv(OUTPUT_GRID_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[저장] phase3_grid.csv → {OUTPUT_GRID_CSV}")

    # 진단 CSV
    diag_rows = []
    for method, split, diag in [
        ("A", "IS",   diag_a_is),
        ("A", "OOS",  diag_a_oos),
        ("A", "전체", diag_a),
        ("B", "IS",   diag_b_is),
        ("B", "OOS",  diag_b_oos),
        ("B", "전체", diag_b),
    ]:
        row = {"entry_method": method, "split": split}
        row.update(diag)
        diag_rows.append(row)
    df_diag = pd.DataFrame(diag_rows)
    df_diag.to_csv(OUTPUT_DIAG_CSV, index=False, encoding="utf-8-sig")
    print(f"[저장] phase3_diagnosis.csv → {OUTPUT_DIAG_CSV}")

    # ------------------------------------------------------------------
    # 7. 콘솔 보고
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("Phase 3 결과 보고")
    print("=" * 70)

    # --- 7-1. 진입 케이스 수 ---
    print(f"\n[1] 진입 케이스 수")
    print(f"  방식 A (10:00): IS={n_a_is}건 / OOS={n_a_oos}건 / 합계={n_a_is+n_a_oos}건")
    print(f"  방식 B (Pullback): IS={n_b_is}건({pct_b_is:.1f}%) / OOS={n_b_oos}건({pct_b_oos:.1f}%) / 합계={n_b_is+n_b_oos}건")

    # --- 7-2. 진단 통계 A vs B ---
    print(f"\n[2] 진단 통계 (whip-saw 분석) — Phase 2 기준값: 최저점 -3.3%, 손절 도달률 85.6%")
    print(f"  {'항목':<30} {'A(전체)':>12} {'B(전체)':>12}")
    print(f"  {'-'*54}")

    def fmt(v):
        if v is None:
            return "    N/A"
        return f"{v:>+12.2f}" if isinstance(v, float) else f"{v:>12}"

    diag_items = [
        ("진입 수 (n)",         diag_a["n_entries"],       diag_b["n_entries"]),
        ("5분 후 평균수익(%)",   diag_a["avg_ret_5min_pct"], diag_b["avg_ret_5min_pct"]),
        ("10분 후 평균수익(%)",  diag_a["avg_ret_10min_pct"], diag_b["avg_ret_10min_pct"]),
        ("30분 후 평균수익(%)",  diag_a["avg_ret_30min_pct"], diag_b["avg_ret_30min_pct"]),
        ("최저점 중앙값(%)",     diag_a["median_low_dip_pct"], diag_b["median_low_dip_pct"]),
        ("손절-0.8% 도달률",     diag_a["stop08_reach_rate"],  diag_b["stop08_reach_rate"]),
    ]
    for label, va, vb in diag_items:
        if isinstance(va, float):
            sa = f"{va:>+12.2f}" if va is not None else "         N/A"
            sb = f"{vb:>+12.2f}" if vb is not None else "         N/A"
        else:
            sa = f"{va:>12}" if va is not None else "         N/A"
            sb = f"{vb:>12}" if vb is not None else "         N/A"
        print(f"  {label:<30} {sa} {sb}")

    # --- 7-3. 통과 셀 수 ---
    df_a = df_results[df_results["entry_method"] == "A"]
    df_b = df_results[df_results["entry_method"] == "B"]

    pass_a = df_a[df_a["pass_flag"] == True]
    pass_b = df_b[df_b["pass_flag"] == True]

    print(f"\n[3] OOS 통과 셀 수")
    print(f"  방식 A: {len(pass_a)}개 / 240셀")
    print(f"  방식 B: {len(pass_b)}개 / 240셀")

    # --- 7-4. 상위 5개 셀 ---
    def print_top5(df_method: pd.DataFrame, label: str):
        print(f"\n[4] 상위 5개 셀 — 방식 {label} (OOS avg_return 기준)")
        header = (f"  {'셀':>5} {'익절':>6} {'손절':>5} {'홀딩':>10} {'트레일':>22} "
                  f"{'n':>4} {'승률':>6} {'평균수익%':>9} {'기대수익(원)':>12} {'샤프':>6} {'pass':>5}")
        print(header)
        print("  " + "-" * (len(header) - 2))
        for _, r in df_method.head(5).iterrows():
            print(
                f"  {r['cell_id']:>5} "
                f"{r['target_pct']:>5.1f}% "
                f"{r['stop_pct']:>4.1f}% "
                f"{r['max_hold']:>10} "
                f"{r['trail']:>22} "
                f"{int(r['oos_n_trades']):>4} "
                f"{r['oos_win_rate']*100 if r['oos_win_rate'] is not None else 0:>5.1f}% "
                f"{r['oos_avg_return_pct'] if r['oos_avg_return_pct'] is not None else 0:>8.3f}% "
                f"{r['oos_expectancy_won'] if r['oos_expectancy_won'] is not None else 0:>11,.0f}원 "
                f"{r['oos_sharpe'] if r['oos_sharpe'] is not None else 0:>5.2f} "
                f"{'O' if r['pass_flag'] else 'X':>5}"
            )

    print_top5(df_a.sort_values("oos_avg_return_pct", ascending=False), "A")
    print_top5(df_b.sort_values("oos_avg_return_pct", ascending=False), "B")

    # --- 7-5. A vs B 직접 비교 (최상위 셀) ---
    print(f"\n[5] A vs B 직접 비교 (최상위 셀 OOS 기준)")
    best_a = df_a.sort_values("oos_avg_return_pct", ascending=False).iloc[0] if len(df_a) > 0 else None
    best_b = df_b.sort_values("oos_avg_return_pct", ascending=False).iloc[0] if len(df_b) > 0 else None

    if best_a is not None:
        print(f"  방식 A 최상위: cell={best_a['cell_id']} target={best_a['target_pct']}% "
              f"stop={best_a['stop_pct']}% hold={best_a['max_hold']} trail={best_a['trail']}")
        print(f"    OOS: n={int(best_a['oos_n_trades'])}, win_rate={best_a['oos_win_rate']*100:.1f}%, "
              f"avg_return={best_a['oos_avg_return_pct']:.3f}%, "
              f"expectancy={best_a['oos_expectancy_won']:,.0f}원, sharpe={best_a['oos_sharpe']:.2f}")
    if best_b is not None:
        print(f"  방식 B 최상위: cell={best_b['cell_id']} target={best_b['target_pct']}% "
              f"stop={best_b['stop_pct']}% hold={best_b['max_hold']} trail={best_b['trail']}")
        print(f"    OOS: n={int(best_b['oos_n_trades'])}, win_rate={best_b['oos_win_rate']*100:.1f}%, "
              f"avg_return={best_b['oos_avg_return_pct']:.3f}%, "
              f"expectancy={best_b['oos_expectancy_won']:,.0f}원, sharpe={best_b['oos_sharpe']:.2f}")

    if best_a is not None and best_b is not None:
        diff_ret = best_b["oos_avg_return_pct"] - best_a["oos_avg_return_pct"]
        diff_wr  = (best_b["oos_win_rate"] - best_a["oos_win_rate"]) * 100
        print(f"  B vs A: avg_return {diff_ret:+.3f}%p, win_rate {diff_wr:+.1f}%p, "
              f"매매수 {int(best_b['oos_n_trades'])} vs {int(best_a['oos_n_trades'])}")

    # --- 7-6. Phase 3 게이트 판정 ---
    print(f"\n[6] Phase 3 게이트 판정")

    def gate_judgment(n_pass: int, label: str, n_entries_oos: int) -> str:
        if n_entries_oos < 5:
            verdict = "FAIL"
            reason = f"OOS 진입 {n_entries_oos}건 < 5 — 샘플 부족"
        elif n_pass >= 3:
            verdict = "PASS"
            reason = f"통과 셀 {n_pass}개 ≥ 3 → Phase 4 진행 권고"
        elif n_pass >= 1:
            verdict = "WARNING"
            reason = f"통과 셀 {n_pass}개 (1~2) — 단일 셀로 Phase 4 진행 시 robustness 한계 명시"
        else:
            verdict = "FAIL"
            reason = f"통과 셀 0개 — 진입 조건 재검토 필요"
        print(f"  방식 {label}: [{verdict}] {reason}")
        return verdict

    verdict_a = gate_judgment(len(pass_a), "A", n_a_oos)
    verdict_b = gate_judgment(len(pass_b), "B", n_b_oos)

    # 결합 권고
    print(f"\n  [결합 권고]")
    if verdict_a == "PASS" and verdict_b == "PASS":
        winner = "B" if (
            best_b is not None and best_a is not None and
            best_b["oos_avg_return_pct"] > best_a["oos_avg_return_pct"]
        ) else "A"
        print(f"  양쪽 PASS → OOS avg_return 우위 방식 {winner}을 Phase 4로 권고")
        print(f"  (방식 {winner}가 더 높은 OOS 수익률 기록)")
    elif verdict_a in ("PASS", "WARNING") and verdict_b == "FAIL":
        print(f"  방식 A를 Phase 4로 권고 (B는 샘플 부족 또는 미통과)")
    elif verdict_b in ("PASS", "WARNING") and verdict_a == "FAIL":
        print(f"  방식 B를 Phase 4로 권고 (A는 미통과)")
    elif verdict_a in ("PASS", "WARNING") and verdict_b in ("PASS", "WARNING"):
        print(f"  양쪽 WARNING → 더 높은 OOS avg_return 방식 우선 선택")
        if best_a is not None and best_b is not None:
            rec = "B" if best_b["oos_avg_return_pct"] > best_a["oos_avg_return_pct"] else "A"
            print(f"  권고: 방식 {rec}")
    else:
        print(f"  양쪽 FAIL → 진입 조건 전체 재검토 필요. Phase 4 보류.")

    # 최상위 셀 고정 권고 (방식 A)
    if best_a is not None:
        print(f"\n  [방식 A Phase 4 권고 조건]")
        print(f"    target={best_a['target_pct']}%, stop={best_a['stop_pct']}%, "
              f"hold={best_a['max_hold']}, trail={best_a['trail']}")

    # 최상위 셀 고정 권고 (방식 B)
    if best_b is not None and n_b_oos >= 5:
        print(f"\n  [방식 B Phase 4 권고 조건]")
        print(f"    target={best_b['target_pct']}%, stop={best_b['stop_pct']}%, "
              f"hold={best_b['max_hold']}, trail={best_b['trail']}")

    elapsed = time.time() - t_start
    print(f"\n[실행 시간] {elapsed:.1f}초")
    print(f"\n[산출물]")
    print(f"  {OUTPUT_GRID_CSV}")
    print(f"  {OUTPUT_DIAG_CSV}")


if __name__ == "__main__":
    main()
