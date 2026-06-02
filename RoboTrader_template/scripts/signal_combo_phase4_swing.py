"""
signal_combo_phase4_swing.py
============================
Phase 4: 스윙 그리드 백테스트 (사장님 결재 2026-05-23)

배경:
  Phase 1~3 모두 expectancy 음수로 FAIL.
  4~5월 시장 재진단: 삼성전자 +63% (4/1~5/22) — 강세장+고변동성.
  데이트레이딩(+1~2% 익절) 포기, 스윙(익절 크게, 홀딩 길게)으로 전환.

신호:
  A: ma20_dist_pct >= 20 (n≈496)
  B: ret_20d_pct >= 25 AND atr_20d_pct >= 8 (n≈176)

진입:
  D당일 09:30:00 분봉 close × (1 + 0.20%) 슬리피지

매도 그리드 (72셀 = 3×2×4×3):
  target_pct: 3.0, 5.0, 8.0 (%)
  stop_pct:   2.0, 3.0 (%)
  max_hold_days: 1, 3, 5, 10 (영업일)
  trail: none / trigger2_trail1 / trigger3_trail15

시뮬 로직:
  D당일: 분봉 09:31~15:30 순회 (high/low 동시 → 손절 우선)
  D+1~: 일봉 순회 (갭 상/하 판단, 트레일, 익절/손절)
  max_hold 도달: 마지막 가용 일봉 close 강제 청산
  data_truncated: D+max_hold > 5/22이면 True

비용:
  슬리피지 0.40% (양방향) + 수수료 0.03% + 거래세 0.18% = 총 0.41%
  순수익률 = (exit_price / entry_price - 1) - 0.0041

평가:
  IS = 4월 (trade_date <= 20260430)
  OOS = 5월 (trade_date >= 20260501)
  통과 기준 (OOS):
    avg_return_pct >= 1.0%, win_rate >= 40%,
    expectancy_won > 0, profit_factor > 1.3, n_trades >= 5

산출물:
  reports/signal_combo_aprmay/swing_grid_v1.csv (144행: 신호A/B × 72셀)
  reports/signal_combo_aprmay/swing_trades.csv  (매매 단위)
"""

from __future__ import annotations

import io
import os
import sys
import time
import itertools
from pathlib import Path
from typing import Optional

# Windows cp949 터미널에서 한글 출력 강제 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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

CASES_CSV = REPORT_DIR / "cases_v4.csv"
OUTPUT_GRID_CSV = REPORT_DIR / "swing_grid_v1.csv"
OUTPUT_TRADES_CSV = REPORT_DIR / "swing_trades.csv"

# ---------------------------------------------------------------------------
# DB 연결 설정
# ---------------------------------------------------------------------------
DB_MINUTE = {
    "host": "127.0.0.1",
    "port": 5433,
    "database": "robotrader",
    "user": "robotrader",
    "password": "1234",
}
DB_DAILY = {
    "host": "127.0.0.1",
    "port": 5433,
    "database": "robotrader_quant",
    "user": "robotrader",
    "password": "1234",
}

# ---------------------------------------------------------------------------
# IS / OOS 분리 기준
# ---------------------------------------------------------------------------
IS_START  = "20260401"
IS_END    = "20260430"
OOS_START = "20260501"
OOS_END   = "20260523"
DATA_LAST_DATE = "20260522"  # daily_prices 마지막 날짜

# ---------------------------------------------------------------------------
# 비용 상수
# ---------------------------------------------------------------------------
SLIPPAGE_ENTRY  = 0.0020   # +20bp 진입 슬리피지
SLIPPAGE_EXIT   = 0.0020   # +20bp 매도 슬리피지
COMMISSION_RT   = 0.00015  # 편도 수수료
TRANSACTION_TAX = 0.0018   # 거래세 (매도)
# 총 순비용 (슬리피지 포함 모두)
# entry_price = raw * (1 + SLIPPAGE_ENTRY)
# exit_price  = raw * (1 - SLIPPAGE_EXIT)
# net_return  = (exit/entry - 1) - (COMMISSION_RT*2 + TRANSACTION_TAX)
COST_COMMISSION = COMMISSION_RT * 2 + TRANSACTION_TAX  # 0.21%

CAPITAL_PER_TRADE = 1_000_000  # 100만원 (expectancy_won 계산 기준)

# ---------------------------------------------------------------------------
# 매도 그리드 정의 (72셀 = 3×2×4×3)
# ---------------------------------------------------------------------------
TARGET_PCTS    = [3.0, 5.0, 8.0]
STOP_PCTS      = [2.0, 3.0]
MAX_HOLD_DAYS  = [1, 3, 5, 10]
TRAILS         = [
    "none",
    "trigger2_trail1",    # +2% 도달 후 -1% trail
    "trigger3_trail15",   # +3% 도달 후 -1.5% trail
]


def parse_trail(trail: str):
    """trail 문자열 → (trigger_pct, trail_pct) or (None, None)"""
    if trail == "none":
        return None, None
    if trail == "trigger2_trail1":
        return 2.0, 1.0
    if trail == "trigger3_trail15":
        return 3.0, 1.5
    raise ValueError(f"Unknown trail: {trail}")


# ---------------------------------------------------------------------------
# 거래일 목록 (영업일 기반 D+N 계산)
# ---------------------------------------------------------------------------

def build_trading_calendar(all_trade_dates: list[str]) -> list[str]:
    """cases_v4 + daily_prices에서 수집된 거래일 정렬 목록 반환."""
    return sorted(set(all_trade_dates))


def get_nth_trading_day_after(base_date: str, n: int, calendar: list[str]) -> Optional[str]:
    """base_date 이후 n번째 영업일 반환. 없으면 None."""
    count = 0
    for d in calendar:
        if d > base_date:
            count += 1
            if count == n:
                return d
    return None


# ---------------------------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------------------------

def load_minute_candles(entries_df: pd.DataFrame) -> pd.DataFrame:
    """진입 케이스 종목·날짜의 09:31~15:30 분봉 로드."""
    pairs = entries_df[["stock_code", "trade_date"]].copy()
    pairs["stock_code"] = pairs["stock_code"].astype(str).str.zfill(6)
    pairs["trade_date"] = pairs["trade_date"].astype(str)

    stock_codes = sorted(pairs["stock_code"].unique())
    date_min = pairs["trade_date"].min()
    # 당일 분봉만 필요 (D당일 시뮬은 분봉, D+1 이후는 일봉)
    date_max = pairs["trade_date"].max()

    stock_list_sql = ",".join(f"'{s}'" for s in stock_codes)

    print(f"[분봉] {len(stock_codes)}종목, {date_min}~{date_max} 09:31~15:30 로드 중...")
    conn = psycopg2.connect(**DB_MINUTE)
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT stock_code, trade_date, time, open, high, low, close
            FROM minute_candles
            WHERE trade_date >= '{date_min}' AND trade_date <= '{date_max}'
              AND time >= '093100' AND time <= '153000'
              AND stock_code IN ({stock_list_sql})
            ORDER BY stock_code, trade_date, time
        """)
        rows = cur.fetchall()
    finally:
        conn.close()

    cols = ["stock_code", "trade_date", "time", "open", "high", "low", "close"]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        print("[분봉] 데이터 없음!")
        return df

    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    df["trade_date"] = df["trade_date"].astype(str)
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    print(f"[분봉] {len(df):,}행 로드 완료")
    return df


def load_daily_prices(entries_df: pd.DataFrame, max_hold_max: int = 10) -> pd.DataFrame:
    """
    진입 케이스 종목의 일봉 로드.
    D+1 ~ D+max_hold_max까지 필요하므로 OOS_END 이후까지 넉넉히 로드.
    """
    pairs = entries_df[["stock_code", "trade_date"]].copy()
    pairs["stock_code"] = pairs["stock_code"].astype(str).str.zfill(6)
    pairs["trade_date"] = pairs["trade_date"].astype(str)

    stock_codes = sorted(pairs["stock_code"].unique())
    date_min = pairs["trade_date"].min()
    # max_hold_max=10 영업일 후 = 약 14 캘린더일 후
    # OOS_END=20260523 기준이지만 일봉 DB 마지막은 20260522이므로 그걸로 충분
    stock_list_sql = ",".join(f"'{s}'" for s in stock_codes)

    # date 포맷: daily_prices는 'YYYY-MM-DD' 텍스트
    # cases_v4 date_min은 'YYYYMMDD' → 'YYYY-MM-DD' 변환
    date_min_fmt = f"{date_min[:4]}-{date_min[4:6]}-{date_min[6:8]}"

    print(f"[일봉] {len(stock_codes)}종목, {date_min_fmt}~ 로드 중...")
    conn = psycopg2.connect(**DB_DAILY)
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT stock_code, date, open, high, low, close
            FROM daily_prices
            WHERE date >= '{date_min_fmt}'
              AND date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
              AND stock_code IN ({stock_list_sql})
            ORDER BY stock_code, date
        """)
        rows = cur.fetchall()
    finally:
        conn.close()

    cols = ["stock_code", "date", "open", "high", "low", "close"]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        print("[일봉] 데이터 없음!")
        return df

    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    df["date"] = df["date"].astype(str)
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # daily_prices date 포맷: 'YYYY-MM-DD' → 'YYYYMMDD' 통일
    if df["date"].str.contains("-").any():
        df["date"] = df["date"].str.replace("-", "", regex=False)

    print(f"[일봉] {len(df):,}행 로드 완료")
    return df


# ---------------------------------------------------------------------------
# 단일 매매 시뮬레이션 (분봉 D당일 + 일봉 D+1~)
# ---------------------------------------------------------------------------

def simulate_trade(
    entry_price_raw: float,
    intraday_bars: pd.DataFrame,   # D당일 09:31~15:30 분봉 (time 오름차순)
    daily_bars: pd.DataFrame,      # D+1 이후 일봉 (date 오름차순)
    target_pct: float,
    stop_pct: float,
    max_hold_days: int,
    trail: str,
    trade_date: str,               # 진입일 YYYYMMDD
    calendar: list[str],
) -> dict:
    """
    단일 매매 시뮬레이션.
    Returns:
        exit_price_raw, exit_reason, trail_activated,
        net_return_pct, hold_days, data_truncated
    """
    # 진입가 (슬리피지 포함)
    entry_price = entry_price_raw * (1 + SLIPPAGE_ENTRY)

    # 익절/손절 절대가 (raw 기준)
    take_profit_raw = entry_price_raw * (1 + target_pct / 100)
    stop_loss_raw   = entry_price_raw * (1 - stop_pct / 100)

    # 트레일 설정
    trail_trigger_pct, trail_pct = parse_trail(trail)

    trail_activated = False
    peak_raw = entry_price_raw

    # max_hold_days 영업일 후 마감일 계산
    last_trading_day = get_nth_trading_day_after(trade_date, max_hold_days, calendar)
    # data_truncated: last_trading_day가 DATA_LAST_DATE를 초과하면 True
    data_truncated = False
    if last_trading_day is None or last_trading_day > DATA_LAST_DATE:
        data_truncated = True
        # 마지막 가용일로 대체
        available_days = [d for d in calendar if d > trade_date and d <= DATA_LAST_DATE]
        last_trading_day = available_days[-1] if available_days else None

    exit_price_raw = None
    exit_reason = None
    hold_days = 0

    # -----------------------------------------------------------------------
    # Step 1: D당일 분봉 09:31~15:30 순회
    # -----------------------------------------------------------------------
    for _, bar in intraday_bars.iterrows():
        bar_high  = float(bar["high"])  if pd.notna(bar["high"])  else None
        bar_low   = float(bar["low"])   if pd.notna(bar["low"])   else None

        if bar_high is None or bar_low is None:
            continue

        # 트레일 활성화
        if trail_trigger_pct is not None and not trail_activated:
            if bar_high >= entry_price_raw * (1 + trail_trigger_pct / 100):
                trail_activated = True
                peak_raw = max(peak_raw, bar_high)

        if trail_activated:
            peak_raw = max(peak_raw, bar_high)

        # 트레일 손절 (활성화 후)
        if trail_activated:
            trail_stop = peak_raw * (1 - trail_pct / 100)
            if bar_low <= trail_stop:
                exit_price_raw = trail_stop
                exit_reason = "EXIT_TRAIL"
                break

        # 익절/손절 동시: 손절 우선 (보수적)
        hit_tp = bar_high >= take_profit_raw
        hit_sl = bar_low  <= stop_loss_raw

        if hit_tp and hit_sl:
            exit_price_raw = stop_loss_raw
            exit_reason = "EXIT_STOP"
            break
        elif hit_tp:
            exit_price_raw = take_profit_raw
            exit_reason = "EXIT_TARGET"
            break
        elif hit_sl:
            exit_price_raw = stop_loss_raw
            exit_reason = "EXIT_STOP"
            break

    # D당일 청산됐으면 완료 (hold_days = 0, 당일 내)
    if exit_price_raw is not None:
        hold_days = 0
    else:
        # D당일 15:30 close로 강제 청산 여부 = max_hold_days == 1
        if max_hold_days == 1:
            # 당일 내 청산 못 했으면 15:30 close로 강제
            if not intraday_bars.empty:
                last_bar = intraday_bars.iloc[-1]
                exit_price_raw = float(last_bar["close"]) if pd.notna(last_bar["close"]) else entry_price_raw
            else:
                exit_price_raw = entry_price_raw
            exit_reason = "MAX_HOLD"
            hold_days = 1
        else:
            # -----------------------------------------------------------------------
            # Step 2: D+1 이후 일봉 순회
            # -----------------------------------------------------------------------
            day_count = 0
            for _, dbar in daily_bars.iterrows():
                ddate = str(dbar["date"])
                if ddate <= trade_date:
                    continue
                if last_trading_day and ddate > last_trading_day:
                    break

                day_count += 1
                dopen  = float(dbar["open"])  if pd.notna(dbar["open"])  else None
                dhigh  = float(dbar["high"])  if pd.notna(dbar["high"])  else None
                dlow   = float(dbar["low"])   if pd.notna(dbar["low"])   else None
                dclose = float(dbar["close"]) if pd.notna(dbar["close"]) else None

                if dopen is None:
                    continue

                # 갭다운 시가 손절
                if dopen <= stop_loss_raw:
                    exit_price_raw = dopen
                    exit_reason = "EXIT_STOP"
                    hold_days = day_count
                    break

                # 갭업 시가 익절
                if dopen >= take_profit_raw:
                    exit_price_raw = dopen
                    exit_reason = "EXIT_TARGET"
                    hold_days = day_count
                    break

                # 트레일 체크 (일봉)
                if trail_trigger_pct is not None and dhigh is not None:
                    if not trail_activated and dhigh >= entry_price_raw * (1 + trail_trigger_pct / 100):
                        trail_activated = True
                        peak_raw = max(peak_raw, dhigh)

                if trail_activated and dhigh is not None:
                    peak_raw = max(peak_raw, dhigh)

                if trail_activated and dlow is not None:
                    trail_stop = peak_raw * (1 - trail_pct / 100)
                    if dlow <= trail_stop:
                        exit_price_raw = trail_stop
                        exit_reason = "EXIT_TRAIL"
                        hold_days = day_count
                        break

                # 일봉 내 익절/손절 (보수적: 손절 우선)
                hit_tp = (dhigh is not None) and dhigh >= take_profit_raw
                hit_sl = (dlow  is not None) and dlow  <= stop_loss_raw

                if hit_tp and hit_sl:
                    exit_price_raw = stop_loss_raw
                    exit_reason = "EXIT_STOP"
                    hold_days = day_count
                    break
                elif hit_tp:
                    exit_price_raw = take_profit_raw
                    exit_reason = "EXIT_TARGET"
                    hold_days = day_count
                    break
                elif hit_sl:
                    exit_price_raw = stop_loss_raw
                    exit_reason = "EXIT_STOP"
                    hold_days = day_count
                    break

                # max_hold 도달 (마지막 영업일의 close 강제 청산)
                if ddate == last_trading_day:
                    exit_price_raw = dclose if dclose is not None else entry_price_raw
                    exit_reason = "DATA_TRUNCATED" if data_truncated else "MAX_HOLD"
                    hold_days = day_count
                    break

            # Step 2 루프 종료 후 아직 미청산
            if exit_price_raw is None:
                # 가용 데이터 소진 (data_truncated)
                avail = daily_bars[
                    (daily_bars["date"] > trade_date) &
                    (daily_bars["date"] <= DATA_LAST_DATE)
                ]
                if not avail.empty:
                    last_close = avail.iloc[-1]["close"]
                    exit_price_raw = float(last_close) if pd.notna(last_close) else entry_price_raw
                else:
                    exit_price_raw = entry_price_raw
                exit_reason = "DATA_TRUNCATED"
                hold_days = day_count

    # -----------------------------------------------------------------------
    # 수익률 계산
    # -----------------------------------------------------------------------
    exit_price = exit_price_raw * (1 - SLIPPAGE_EXIT)
    gross_return = (exit_price / entry_price) - 1
    net_return = gross_return - COST_COMMISSION

    return {
        "exit_price_raw": round(exit_price_raw, 2),
        "exit_reason": exit_reason,
        "trail_activated": trail_activated,
        "net_return_pct": round(net_return * 100, 4),
        "hold_days": hold_days,
        "data_truncated": data_truncated,
    }


# ---------------------------------------------------------------------------
# 셀별 통계
# ---------------------------------------------------------------------------

def compute_cell_stats(trade_results: list[dict]) -> dict:
    if not trade_results:
        return {
            "n_trades": 0, "win_rate": None, "avg_return_pct": None,
            "expectancy_won": None, "profit_factor": None,
            "avg_hold_days": None, "data_truncated_share": None,
            "exit_target": 0, "exit_stop": 0, "exit_trail": 0,
            "exit_max_hold": 0, "exit_data_truncated": 0,
        }

    returns = np.array([t["net_return_pct"] for t in trade_results])
    n = len(returns)

    wins   = returns[returns > 0]
    losses = returns[returns <= 0]

    win_rate      = len(wins) / n
    avg_return    = float(np.mean(returns))
    expectancy_won = avg_return / 100 * CAPITAL_PER_TRADE

    gross_profit = float(np.sum(wins))   if len(wins)   > 0 else 0.0
    gross_loss   = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0
    profit_factor = (
        (gross_profit / gross_loss) if gross_loss > 0
        else (9999.0 if gross_profit > 0 else 0.0)
    )

    avg_hold = float(np.mean([t["hold_days"] for t in trade_results]))
    dt_share = float(np.mean([1.0 if t["data_truncated"] else 0.0 for t in trade_results]))

    exit_counts = {"EXIT_TARGET": 0, "EXIT_STOP": 0, "EXIT_TRAIL": 0,
                   "MAX_HOLD": 0, "DATA_TRUNCATED": 0}
    for t in trade_results:
        r = t["exit_reason"]
        if r in exit_counts:
            exit_counts[r] += 1

    return {
        "n_trades": n,
        "win_rate": round(win_rate, 4),
        "avg_return_pct": round(avg_return, 4),
        "expectancy_won": round(expectancy_won, 1),
        "profit_factor": round(min(profit_factor, 9999.0), 4),
        "avg_hold_days": round(avg_hold, 2),
        "data_truncated_share": round(dt_share, 4),
        "exit_target": exit_counts["EXIT_TARGET"],
        "exit_stop": exit_counts["EXIT_STOP"],
        "exit_trail": exit_counts["EXIT_TRAIL"],
        "exit_max_hold": exit_counts["MAX_HOLD"],
        "exit_data_truncated": exit_counts["DATA_TRUNCATED"],
    }


def check_pass_oos(stats: dict) -> bool:
    if stats["n_trades"] is None or stats["n_trades"] < 5:
        return False
    if stats["avg_return_pct"] is None or stats["avg_return_pct"] < 1.0:
        return False
    if stats["win_rate"] is None or stats["win_rate"] < 0.40:
        return False
    if stats["expectancy_won"] is None or stats["expectancy_won"] <= 0:
        return False
    if stats["profit_factor"] is None or stats["profit_factor"] < 1.3:
        return False
    return True


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    t_start = time.time()

    print("=" * 65)
    print("Phase 4: 스윙 그리드 백테스트 (72셀 × 신호A/B × IS/OOS)")
    print("=" * 65)

    # ------------------------------------------------------------------
    # 1. cases_v4 로드 & 신호 A/B 필터
    # ------------------------------------------------------------------
    df_cases = pd.read_csv(CASES_CSV)
    df_cases["trade_date"] = df_cases["trade_date"].astype(str)
    df_cases["stock_code"]  = df_cases["stock_code"].astype(str).str.zfill(6)

    # 진입가 필수
    df_cases = df_cases[df_cases["close_0930"].notna()].copy()

    # 신호 A: ma20_dist_pct >= 20
    sig_a_mask = df_cases["ma20_dist_pct"] >= 20.0
    # 신호 B: ret_20d_pct >= 25 AND atr_20d_pct >= 8
    sig_b_mask = (df_cases["ret_20d_pct"] >= 25.0) & (df_cases["atr_20d_pct"] >= 8.0)

    entries_a = df_cases[sig_a_mask].copy().reset_index(drop=True)
    entries_b = df_cases[sig_b_mask].copy().reset_index(drop=True)

    mask_is  = lambda df: df["trade_date"].between(IS_START, IS_END)
    mask_oos = lambda df: df["trade_date"].between(OOS_START, OOS_END)

    print(f"\n[신호 A] ma20_dist_pct>=20: 전체={len(entries_a)}건 "
          f"IS={len(entries_a[mask_is(entries_a)])}건 OOS={len(entries_a[mask_oos(entries_a)])}건")
    print(f"[신호 B] ret_20d>=25 AND atr_20d>=8: 전체={len(entries_b)}건 "
          f"IS={len(entries_b[mask_is(entries_b)])}건 OOS={len(entries_b[mask_oos(entries_b)])}건")

    # ------------------------------------------------------------------
    # 2. 분봉 + 일봉 데이터 로드
    # ------------------------------------------------------------------
    all_entries = pd.concat([entries_a, entries_b]).drop_duplicates(
        subset=["trade_date", "stock_code"]
    ).reset_index(drop=True)

    minute_df = load_minute_candles(all_entries)
    daily_df  = load_daily_prices(all_entries, max_hold_max=10)

    if minute_df.empty:
        print("[ERROR] 분봉 데이터 없음. DB 연결 확인.")
        sys.exit(1)
    if daily_df.empty:
        print("[ERROR] 일봉 데이터 없음. DB 연결 확인.")
        sys.exit(1)

    # 분봉 그룹화
    minute_groups: dict[tuple[str, str], pd.DataFrame] = {}
    for (sc, td), grp in minute_df.groupby(["stock_code", "trade_date"]):
        minute_groups[(str(sc), str(td))] = grp.reset_index(drop=True)

    # 일봉 그룹화
    daily_groups: dict[str, pd.DataFrame] = {}
    for sc, grp in daily_df.groupby("stock_code"):
        daily_groups[str(sc)] = grp.sort_values("date").reset_index(drop=True)

    # 거래일 캘린더 (cases + daily_prices 날짜 합산)
    all_dates = sorted(
        set(df_cases["trade_date"].unique().tolist()) |
        set(daily_df["date"].unique().tolist())
    )
    calendar = all_dates
    print(f"[캘린더] {len(calendar)}개 거래일 ({calendar[0]}~{calendar[-1]})")

    # ------------------------------------------------------------------
    # 3. 그리드 정의 (72셀)
    # ------------------------------------------------------------------
    grid = list(itertools.product(TARGET_PCTS, STOP_PCTS, MAX_HOLD_DAYS, TRAILS))
    assert len(grid) == 72, f"그리드 셀 수 불일치: {len(grid)}"
    print(f"\n[그리드] {len(grid)}셀 × 신호A/B × IS/OOS = {len(grid)*2*2}번 평가")

    # ------------------------------------------------------------------
    # 4. 신호별 시뮬레이션
    # ------------------------------------------------------------------
    results = []
    all_trades_log = []

    for sig_name, entries in [("A", entries_a), ("B", entries_b)]:
        is_ent  = entries[mask_is(entries)].copy()
        oos_ent = entries[mask_oos(entries)].copy()

        print(f"\n{'='*50}")
        print(f"신호 {sig_name}: IS={len(is_ent)}건 / OOS={len(oos_ent)}건")
        print(f"{'='*50}")

        for cell_idx, (target_pct, stop_pct, max_hold_days, trail) in enumerate(grid):
            cell_id = f"{sig_name}_C{cell_idx:03d}"

            is_trades  = []
            oos_trades = []

            for split_name, split_entries in [("IS", is_ent), ("OOS", oos_ent)]:
                for _, row in split_entries.iterrows():
                    sc  = str(row["stock_code"])
                    td  = str(row["trade_date"])
                    ep  = float(row["close_0930"])

                    # 분봉 (D당일)
                    intraday = minute_groups.get((sc, td), pd.DataFrame())

                    # 일봉 (D+1 이후)
                    sc_daily = daily_groups.get(sc, pd.DataFrame())
                    if not sc_daily.empty:
                        d1_daily = sc_daily[sc_daily["date"] > td].reset_index(drop=True)
                    else:
                        d1_daily = pd.DataFrame()

                    res = simulate_trade(
                        entry_price_raw=ep,
                        intraday_bars=intraday,
                        daily_bars=d1_daily,
                        target_pct=target_pct,
                        stop_pct=stop_pct,
                        max_hold_days=max_hold_days,
                        trail=trail,
                        trade_date=td,
                        calendar=calendar,
                    )

                    trade_log = {
                        "signal": sig_name,
                        "cell_id": cell_id,
                        "split": split_name,
                        "trade_date": td,
                        "stock_code": sc,
                        "stock_name": row.get("stock_name", ""),
                        "entry_price_raw": ep,
                        "target_pct": target_pct,
                        "stop_pct": stop_pct,
                        "max_hold_days": max_hold_days,
                        "trail": trail,
                        **res,
                    }
                    all_trades_log.append(trade_log)

                    if split_name == "IS":
                        is_trades.append(res)
                    else:
                        oos_trades.append(res)

            is_stats  = compute_cell_stats(is_trades)
            oos_stats = compute_cell_stats(oos_trades)
            oos_pass  = check_pass_oos(oos_stats)

            row_out = {
                "signal": sig_name,
                "cell_id": cell_id,
                "target_pct": target_pct,
                "stop_pct": stop_pct,
                "max_hold_days": max_hold_days,
                "trail": trail,
                # IS
                "is_n_trades": is_stats["n_trades"],
                "is_win_rate": is_stats["win_rate"],
                "is_avg_return_pct": is_stats["avg_return_pct"],
                "is_expectancy_won": is_stats["expectancy_won"],
                "is_profit_factor": is_stats["profit_factor"],
                "is_avg_hold_days": is_stats["avg_hold_days"],
                "is_data_truncated_share": is_stats["data_truncated_share"],
                "is_exit_target": is_stats["exit_target"],
                "is_exit_stop": is_stats["exit_stop"],
                "is_exit_trail": is_stats["exit_trail"],
                "is_exit_max_hold": is_stats["exit_max_hold"],
                "is_exit_data_truncated": is_stats["exit_data_truncated"],
                # OOS
                "oos_n_trades": oos_stats["n_trades"],
                "oos_win_rate": oos_stats["win_rate"],
                "oos_avg_return_pct": oos_stats["avg_return_pct"],
                "oos_expectancy_won": oos_stats["expectancy_won"],
                "oos_profit_factor": oos_stats["profit_factor"],
                "oos_avg_hold_days": oos_stats["avg_hold_days"],
                "oos_data_truncated_share": oos_stats["data_truncated_share"],
                "oos_exit_target": oos_stats["exit_target"],
                "oos_exit_stop": oos_stats["exit_stop"],
                "oos_exit_trail": oos_stats["exit_trail"],
                "oos_exit_max_hold": oos_stats["exit_max_hold"],
                "oos_exit_data_truncated": oos_stats["exit_data_truncated"],
                "pass_flag": oos_pass,
            }
            results.append(row_out)

            # 진행 상황 (24셀마다)
            if (cell_idx + 1) % 24 == 0 or cell_idx == 0:
                elapsed = time.time() - t_start
                print(f"  [신호{sig_name} {cell_idx+1:3d}/72] {elapsed:.1f}s | "
                      f"target={target_pct}% stop={stop_pct}% hold={max_hold_days}d trail={trail} "
                      f"| OOS pass={'O' if oos_pass else 'X'} "
                      f"avg_ret={oos_stats['avg_return_pct'] or 'N/A'}")

    # ------------------------------------------------------------------
    # 5. CSV 저장
    # ------------------------------------------------------------------
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(
        ["signal", "oos_avg_return_pct"], ascending=[True, False]
    ).reset_index(drop=True)
    df_results.to_csv(OUTPUT_GRID_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[저장] swing_grid_v1.csv → {OUTPUT_GRID_CSV}")

    df_trades = pd.DataFrame(all_trades_log)
    df_trades.to_csv(OUTPUT_TRADES_CSV, index=False, encoding="utf-8-sig")
    print(f"[저장] swing_trades.csv → {OUTPUT_TRADES_CSV}")

    # ------------------------------------------------------------------
    # 6. 콘솔 보고
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("Phase 4 결과 보고")
    print("=" * 65)

    for sig_name in ["A", "B"]:
        sig_df = df_results[df_results["signal"] == sig_name].copy()
        sig_df = sig_df.sort_values("oos_avg_return_pct", ascending=False).reset_index(drop=True)
        pass_df = sig_df[sig_df["pass_flag"] == True]

        print(f"\n[신호 {sig_name}] 통과 셀: {len(pass_df)}/72")
        print(f"  IS={int(sig_df['is_n_trades'].iloc[0])}건 / OOS={int(sig_df['oos_n_trades'].iloc[0])}건 (셀 고정 케이스 수 동일)")

        # 상위 3개 셀
        print(f"\n  [OOS avg_return_pct 기준 상위 3개 셀]")
        header = (f"  {'셀':>8} {'익절':>5} {'손절':>5} {'홀딩':>5} {'트레일':>18} "
                  f"{'n':>4} {'승률':>6} {'평균수익%':>9} {'기대수익(원)':>12} {'보유일':>6} {'pass':>5}")
        print(header)
        print("  " + "-" * (len(header) - 2))
        for rank, (_, r) in enumerate(sig_df.head(3).iterrows(), 1):
            print(
                f"  {r['cell_id']:>8} "
                f"{r['target_pct']:>4.1f}% "
                f"{r['stop_pct']:>4.1f}% "
                f"{r['max_hold_days']:>4}d "
                f"{r['trail']:>18} "
                f"{int(r['oos_n_trades']):>4} "
                f"{r['oos_win_rate']*100 if r['oos_win_rate'] else 0:>5.1f}% "
                f"{r['oos_avg_return_pct'] or 0:>8.3f}% "
                f"{r['oos_expectancy_won'] or 0:>11,.0f}원 "
                f"{r['oos_avg_hold_days'] or 0:>5.1f}일 "
                f"{'O' if r['pass_flag'] else 'X':>5}"
            )

        # 통과 셀 청산 사유 분포
        if len(pass_df) > 0:
            total_n = pass_df["oos_n_trades"].sum()
            reasons = {
                "EXIT_TARGET":       pass_df["oos_exit_target"].sum(),
                "EXIT_STOP":         pass_df["oos_exit_stop"].sum(),
                "EXIT_TRAIL":        pass_df["oos_exit_trail"].sum(),
                "MAX_HOLD":          pass_df["oos_exit_max_hold"].sum(),
                "DATA_TRUNCATED":    pass_df["oos_exit_data_truncated"].sum(),
            }
            print(f"\n  [청산 사유 분포 (통과 셀 OOS 합산)]")
            for rname, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
                pct = cnt / total_n * 100 if total_n > 0 else 0
                print(f"    {rname:>18}: {int(cnt):>5}건 ({pct:.1f}%)")

        # data_truncated_share
        avg_dt = sig_df["oos_data_truncated_share"].mean()
        print(f"\n  data_truncated_share 전체 평균: {avg_dt:.1%}")

    # ------------------------------------------------------------------
    # 7. A vs B 비교 요약
    # ------------------------------------------------------------------
    print("\n" + "-" * 65)
    a_pass = len(df_results[(df_results["signal"] == "A") & (df_results["pass_flag"] == True)])
    b_pass = len(df_results[(df_results["signal"] == "B") & (df_results["pass_flag"] == True)])
    a_best = df_results[df_results["signal"] == "A"]["oos_avg_return_pct"].max()
    b_best = df_results[df_results["signal"] == "B"]["oos_avg_return_pct"].max()
    print(f"\n[A vs B 비교] 신호A 통과={a_pass}/72 (최우수 OOS return={a_best:.3f}%) | "
          f"신호B 통과={b_pass}/72 (최우수 OOS return={b_best:.3f}%)")
    if a_pass > b_pass or (a_pass == b_pass and a_best > b_best):
        print("  → 신호A(ma20_dist_pct≥20)가 케이스 수 및 OOS 성과 모두 우위")
    elif b_pass > a_pass or (a_pass == b_pass and b_best > a_best):
        print("  → 신호B(ret_20d≥25 AND atr_20d≥8)가 OOS 성과 우위")
    else:
        print("  → 두 신호 동등 수준")

    # ------------------------------------------------------------------
    # 8. Phase 4 게이트 판정
    # ------------------------------------------------------------------
    total_pass = a_pass + b_pass
    print(f"\n{'='*65}")
    if total_pass >= 3:
        gate = "PASS"
        msg = f"통과 셀 합계 {total_pass}개 ≥ 3 → 스윙 전략 실전 배포 결재 후보"
    elif total_pass >= 1:
        gate = "WARNING"
        msg = f"통과 셀 {total_pass}개 (1~2) → 단일 셀로 라이브 가상매매 5일 진행 후 재판단"
    else:
        gate = "FAIL"
        msg = "통과 셀 0개 → 스윙 그리드도 FAIL. 익절폭/홀딩 재검토 또는 신호 재설계"

    print(f"[Phase 4 게이트 판정]: {gate}")
    print(f"  {msg}")

    elapsed = time.time() - t_start
    print(f"\n[실행 시간] {elapsed:.1f}초 ({elapsed/60:.1f}분)")
    print(f"\n[산출물]")
    print(f"  {OUTPUT_GRID_CSV}")
    print(f"  {OUTPUT_TRADES_CSV}")


if __name__ == "__main__":
    main()
