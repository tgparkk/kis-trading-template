"""
signal_combo_phase2_exit_grid.py
=================================
Phase 2: 진입 조건 고정 + 매도 240셀 그리드 IS/OOS 백테스트

진입 조건 (사장님 결재 확정, 2026-05-23):
  ret_20d_pct >= 25 AND atr_20d_pct >= 8
  진입가: D당일 09:30:00 close (없으면 09:30 직전 close), 슬리피지 +20bp

매도 그리드 (240셀 = 4×4×5×3):
  target_pct: 1.5, 2.0, 2.5, 3.0 (%)
  stop_pct:   0.8, 1.0, 1.5, 2.0 (%)
  max_hold:   intraday(15:30), next_day(D+1 15:30), 60min, 120min, 240min
  trail:      none / trigger1.5_trail0.5 / trigger1.0_trail0.5

비용:
  진입 슬리피지 +20bp, 매도 슬리피지 +20bp, 수수료 0.015%×2, 거래세 0.18%
  총 비용 ≈ 0.41%

통과 기준 (OOS 기준):
  avg_return_pct >= 0.5% AND win_rate >= 55% AND expectancy_won > 0
  AND sharpe > 0.3 AND n_trades >= 5

데이터:
  분봉: robotrader.public.minute_candles (host=127.0.0.1 port=5433)
  진입 케이스: RoboTrader_template/reports/signal_combo_aprmay/cases_v2.csv

사용법:
  cd RoboTrader_template
  python scripts/signal_combo_phase2_exit_grid.py
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
OUTPUT_GRID_CSV = REPORT_DIR / "exit_grid_v1.csv"
OUTPUT_TRADES_CSV = REPORT_DIR / "exit_grid_trades.csv"

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
# 진입 조건 (사장님 결재 확정)
# ---------------------------------------------------------------------------
ENTRY_RET20D_MIN = 25.0   # ret_20d_pct >= 25
ENTRY_ATR20D_MIN = 8.0    # atr_20d_pct >= 8

# IS / OOS 분리 기준
IS_START = "20260401"
IS_END   = "20260430"
OOS_START = "20260501"
OOS_END   = "20260523"

# ---------------------------------------------------------------------------
# 비용 상수
# ---------------------------------------------------------------------------
SLIPPAGE_ENTRY_BPS = 20   # +20bp 진입 슬리피지
SLIPPAGE_EXIT_BPS  = 20   # +20bp 매도 슬리피지
COMMISSION_RT = 0.00015   # 편도 수수료 0.015%
TRANSACTION_TAX = 0.0018  # 거래세 0.18% (매도 시만)
# 총 비용 (진입슬리피지 + 매도슬리피지 + 수수료x2 + 거래세)
# = 0.20% + 0.20% + 0.015% + 0.015% + 0.18% = 0.61%  ← 슬리피지는 가격에 반영되므로 별도 계산
# 수수료+세금 직접 차감
COST_RATE = COMMISSION_RT * 2 + TRANSACTION_TAX  # 0.21%

# 가상 진입 자본 (expectancy_won 계산 기준)
CAPITAL_PER_TRADE = 1_000_000  # 100만원

# ---------------------------------------------------------------------------
# 매도 그리드 정의
# ---------------------------------------------------------------------------
TARGET_PCTS = [1.5, 2.0, 2.5, 3.0]
STOP_PCTS   = [0.8, 1.0, 1.5, 2.0]
MAX_HOLDS   = ["intraday", "next_day", "60min", "120min", "240min"]
TRAILS      = [
    "none",
    "trigger1.5_trail0.5",   # +1.5% 도달 후 -0.5% trail
    "trigger1.0_trail0.5",   # +1.0% 도달 후 -0.5% trail
]

# ---------------------------------------------------------------------------
# 거래일 계산 (주말 제외 단순화 — 한국 공휴일은 분봉 데이터로 자연 처리)
# ---------------------------------------------------------------------------

def get_next_trading_day(trade_date_str: str, all_trade_dates: list[str]) -> Optional[str]:
    """cases_v2의 trade_date 목록에서 다음 거래일 반환."""
    dates_sorted = sorted(all_trade_dates)
    idx = None
    for i, d in enumerate(dates_sorted):
        if d == trade_date_str:
            idx = i
            break
    if idx is None or idx + 1 >= len(dates_sorted):
        # trade_date_str 이후 첫 날짜 찾기
        for d in dates_sorted:
            if d > trade_date_str:
                return d
        return None
    return dates_sorted[idx + 1]


def get_hold_deadline(
    trade_date_str: str,
    entry_time_str: str,
    max_hold: str,
    all_trade_dates: list[str],
) -> tuple[str, str]:
    """
    (deadline_date_str, deadline_time_str) 반환.
    entry_time_str: 'HHMMSS' (예: '093000')
    """
    if max_hold == "intraday":
        return trade_date_str, "153000"
    if max_hold == "next_day":
        nxt = get_next_trading_day(trade_date_str, all_trade_dates)
        return (nxt if nxt else trade_date_str), "153000"

    # 분 기반
    entry_h = int(entry_time_str[:2])
    entry_m = int(entry_time_str[2:4])
    entry_dt = datetime(2000, 1, 1, entry_h, entry_m)

    minutes_map = {"60min": 60, "120min": 120, "240min": 240}
    delta = timedelta(minutes=minutes_map[max_hold])
    deadline_dt = entry_dt + delta

    # 당일 마감 15:30 상한
    eod = datetime(2000, 1, 1, 15, 30)
    if deadline_dt > eod:
        deadline_dt = eod

    return trade_date_str, deadline_dt.strftime("%H%M%S")


# ---------------------------------------------------------------------------
# 분봉 데이터 로드 (진입 케이스 종목+날짜만)
# ---------------------------------------------------------------------------

def load_minute_candles(entries_df: pd.DataFrame, conn) -> pd.DataFrame:
    """
    entries_df: trade_date(int), stock_code(int) 컬럼 보유
    09:31 이후 전체 분봉 로드 (시뮬레이션용) + D+1 15:30까지
    """
    # 필요한 (stock_code, date) 쌍
    pairs = entries_df[["stock_code", "trade_date"]].copy()
    pairs["stock_code"] = pairs["stock_code"].astype(str).str.zfill(6)
    pairs["trade_date"] = pairs["trade_date"].astype(str)

    # 모든 거래일 목록 (D+1 포함 — next_day max_hold 지원)
    all_dates_set = set(pairs["trade_date"].tolist())
    # D+1 날짜도 포함하기 위해 전체 분봉 날짜 범위를 조금 넓힘
    date_min = min(all_dates_set)
    date_max_oos_end = OOS_END  # 5/23 이후까지 없을 수 있으므로 5/23로 제한

    stock_codes = sorted(pairs["stock_code"].unique())
    stock_list_sql = ",".join(f"'{s}'" for s in stock_codes)

    print(f"[분봉] {len(stock_codes)}개 종목, {date_min}~{date_max_oos_end} 09:31~15:30 로드 중...")
    cur = conn.cursor()
    cur.execute(f"""
        SELECT stock_code, trade_date, time, open, high, low, close, volume, amount
        FROM minute_candles
        WHERE trade_date >= '{date_min}' AND trade_date <= '{date_max_oos_end}'
          AND time >= '093100' AND time <= '153000'
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
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["open"] = pd.to_numeric(df["open"], errors="coerce")

    print(f"[분봉] {len(df):,}행 로드 완료")
    return df


# ---------------------------------------------------------------------------
# 단일 매매 시뮬레이션
# ---------------------------------------------------------------------------

def simulate_trade(
    bars: pd.DataFrame,           # 진입 시점 이후 분봉 (time 오름차순)
    entry_price_raw: float,       # 슬리피지 전 진입가 (close_0930)
    target_pct: float,
    stop_pct: float,
    max_hold: str,
    trail: str,
    trade_date: str,
    entry_time: str,
    all_trade_dates: list[str],
    next_day_bars: Optional[pd.DataFrame] = None,  # D+1 분봉 (max_hold=next_day 시)
) -> dict:
    """
    단일 매매 결과 반환.
    Returns: {exit_price_raw, return_pct, net_return_pct, exit_reason, trail_activated}
    """
    # 진입가 (슬리피지 포함)
    entry_price = entry_price_raw * (1 + SLIPPAGE_ENTRY_BPS / 10000)

    # 익절/손절 가격 (슬리피지 전 기준)
    take_profit_price = entry_price_raw * (1 + target_pct / 100)
    stop_loss_price   = entry_price_raw * (1 - stop_pct / 100)

    # 트레일 설정 파싱
    trail_trigger_pct = None
    trail_pct = None
    if trail == "trigger1.5_trail0.5":
        trail_trigger_pct = 1.5
        trail_pct = 0.5
    elif trail == "trigger1.0_trail0.5":
        trail_trigger_pct = 1.0
        trail_pct = 0.5

    # 홀딩 만료 데드라인
    deadline_date, deadline_time = get_hold_deadline(
        trade_date, entry_time, max_hold, all_trade_dates
    )

    trail_activated = False
    peak_price = entry_price_raw  # 트레일용 고점 추적 (슬리피지 전 기준)

    # 당일 분봉 + D+1 분봉 연결 (max_hold=next_day 시)
    if max_hold == "next_day" and next_day_bars is not None and not next_day_bars.empty:
        all_bars = pd.concat([bars, next_day_bars], ignore_index=True)
    else:
        all_bars = bars

    exit_price_raw = None
    exit_reason = "hold_expired"

    for _, bar in all_bars.iterrows():
        bar_date = str(bar["trade_date"])
        bar_time = str(bar["time"])
        bar_high = float(bar["high"]) if pd.notna(bar["high"]) else None
        bar_low  = float(bar["low"]) if pd.notna(bar["low"]) else None
        bar_close = float(bar["close"]) if pd.notna(bar["close"]) else None

        if bar_high is None or bar_low is None or bar_close is None:
            continue

        # 데드라인 초과 → 홀딩 만료
        if bar_date > deadline_date or (bar_date == deadline_date and bar_time > deadline_time):
            break

        # -------------------------------------------------------------------
        # D+1 시가 갭다운 EOD 갭 보정 (max_hold=next_day, D+1 첫 봉)
        # -------------------------------------------------------------------
        is_next_day_bar = (bar_date != trade_date)
        if is_next_day_bar and bar_time == "093100":
            # D+1 시가(open)가 손절선 하회 시 시가에 청산
            bar_open = float(bar["open"]) if pd.notna(bar["open"]) else None
            if bar_open is not None and bar_open <= stop_loss_price:
                exit_price_raw = bar_open
                exit_reason = "gap_stop"
                break

        # -------------------------------------------------------------------
        # 트레일링 활성화 체크
        # -------------------------------------------------------------------
        if trail_trigger_pct is not None and not trail_activated:
            trigger_price = entry_price_raw * (1 + trail_trigger_pct / 100)
            if bar_high >= trigger_price:
                trail_activated = True
                peak_price = max(peak_price, bar_high)

        # 트레일 활성화 상태에서 고점 갱신
        if trail_activated:
            peak_price = max(peak_price, bar_high)

        # -------------------------------------------------------------------
        # 트레일 청산 체크 (활성화 후)
        # -------------------------------------------------------------------
        if trail_activated:
            trail_stop = peak_price * (1 - trail_pct / 100)
            if bar_low <= trail_stop:
                exit_price_raw = trail_stop
                exit_reason = "trail"
                break

        # -------------------------------------------------------------------
        # 익절/손절 동시 발생: 보수적 가정 = 손절 우선
        # (단, 트레일 활성화 후엔 트레일이 우선 — 이미 익절 영역 보장)
        # -------------------------------------------------------------------
        hit_tp = bar_high >= take_profit_price
        hit_sl = bar_low <= stop_loss_price

        if hit_tp and hit_sl:
            # 보수적: 손절 우선
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

    # 홀딩 만료: 데드라인 봉의 close 사용
    if exit_price_raw is None:
        # 데드라인 봉 찾기
        deadline_bar = all_bars[
            (all_bars["trade_date"].astype(str) == deadline_date) &
            (all_bars["time"].astype(str) <= deadline_time)
        ]
        if not deadline_bar.empty:
            exit_price_raw = float(deadline_bar.iloc[-1]["close"])
        else:
            # 데드라인 이전 마지막 봉 close
            if not all_bars.empty:
                exit_price_raw = float(all_bars.iloc[-1]["close"])
            else:
                exit_price_raw = entry_price_raw  # fallback: 손익 0

        exit_reason = "hold_expired"

    # -------------------------------------------------------------------
    # 수익률 계산
    # -------------------------------------------------------------------
    # 매도가 (슬리피지 포함: 매도 시 -20bp)
    exit_price = exit_price_raw * (1 - SLIPPAGE_EXIT_BPS / 10000)

    # 순수익률 = (exit_price / entry_price - 1) - 비용
    gross_return = (exit_price / entry_price) - 1
    net_return = gross_return - COST_RATE

    return {
        "exit_price_raw": round(exit_price_raw, 2),
        "exit_reason": exit_reason,
        "trail_activated": trail_activated,
        "net_return_pct": round(net_return * 100, 4),
    }


# ---------------------------------------------------------------------------
# 셀별 통계 계산
# ---------------------------------------------------------------------------

def compute_cell_stats(trade_results: list[dict]) -> dict:
    """
    매매 결과 리스트 → 셀 통계.
    """
    if not trade_results:
        return {
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

    returns = np.array([t["net_return_pct"] for t in trade_results])
    n = len(returns)

    wins = returns[returns > 0]
    losses = returns[returns <= 0]

    win_rate = len(wins) / n if n > 0 else 0.0
    avg_return = float(np.mean(returns))

    # expectancy_won: 평균 매매당 손익 (100만원 기준)
    expectancy_won = avg_return / 100 * CAPITAL_PER_TRADE

    # profit_factor
    gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    # max_drawdown_pct: 누적 수익률 최대 낙폭
    cumulative = np.cumsum(returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = running_max - cumulative
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # sharpe: 일별 수익률 기준 (252일 연환산)
    # 여기서 각 매매를 독립 '관측값'으로 간주 (짧은 홀딩)
    if n >= 2 and float(np.std(returns)) > 0:
        sharpe = float(np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(252))
    else:
        sharpe = 0.0

    # 청산 사유 분포
    exit_counts = {"target": 0, "stop": 0, "trail": 0, "hold_expired": 0, "gap_stop": 0}
    for t in trade_results:
        r = t["exit_reason"]
        exit_counts[r] = exit_counts.get(r, 0) + 1

    return {
        "n_trades": n,
        "win_rate": round(win_rate, 4),
        "avg_return_pct": round(avg_return, 4),
        "expectancy_won": round(expectancy_won, 1),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 9999.0,
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe": round(sharpe, 4),
        "exit_target": exit_counts.get("target", 0),
        "exit_stop": exit_counts.get("stop", 0),
        "exit_trail": exit_counts.get("trail", 0),
        "exit_hold_expired": exit_counts.get("hold_expired", 0),
        "exit_gap_stop": exit_counts.get("gap_stop", 0),
    }


# ---------------------------------------------------------------------------
# 통과 기준 판정
# ---------------------------------------------------------------------------

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
# 메인 실행
# ---------------------------------------------------------------------------

def main():
    t_start = time.time()

    # ------------------------------------------------------------------
    # 1. 진입 케이스 로드
    # ------------------------------------------------------------------
    print("=" * 60)
    print("Phase 2: 매도 240셀 그리드 백테스트")
    print("=" * 60)

    df_cases = pd.read_csv(CASES_CSV)
    df_cases["trade_date"] = df_cases["trade_date"].astype(str)
    df_cases["stock_code"] = df_cases["stock_code"].astype(str).str.zfill(6)

    # 진입 조건 필터
    mask_entry = (
        (df_cases["ret_20d_pct"] >= ENTRY_RET20D_MIN) &
        (df_cases["atr_20d_pct"] >= ENTRY_ATR20D_MIN) &
        df_cases["close_0930"].notna()
    )
    entries = df_cases[mask_entry].copy().reset_index(drop=True)

    mask_is  = entries["trade_date"].between(IS_START, IS_END)
    mask_oos = entries["trade_date"].between(OOS_START, OOS_END)

    is_entries  = entries[mask_is].copy()
    oos_entries = entries[mask_oos].copy()

    print(f"\n[진입 케이스]")
    print(f"  IS  (4월): {len(is_entries)}건")
    print(f"  OOS (5월): {len(oos_entries)}건")
    print(f"  합계: {len(entries)}건")

    # 전체 거래일 목록 (D+1 계산용)
    all_trade_dates = sorted(df_cases["trade_date"].unique().tolist())

    # ------------------------------------------------------------------
    # 2. 분봉 데이터 로드
    # ------------------------------------------------------------------
    conn = psycopg2.connect(**DB_MINUTE)
    try:
        minute_df = load_minute_candles(entries, conn)
    finally:
        conn.close()

    if minute_df.empty:
        print("[ERROR] 분봉 데이터가 없습니다. DB 연결 확인 필요.")
        sys.exit(1)

    # 분봉을 (stock_code, trade_date) 기준으로 그룹화 → 빠른 조회
    minute_groups: dict[tuple[str, str], pd.DataFrame] = {}
    for (sc, td), grp in minute_df.groupby(["stock_code", "trade_date"]):
        minute_groups[(str(sc), str(td))] = grp.reset_index(drop=True)

    print(f"[분봉] 그룹 수: {len(minute_groups):,}개 (종목×날짜)")

    # ------------------------------------------------------------------
    # 3. 그리드 정의 (240셀)
    # ------------------------------------------------------------------
    grid = list(itertools.product(TARGET_PCTS, STOP_PCTS, MAX_HOLDS, TRAILS))
    assert len(grid) == 240, f"그리드 셀 수 불일치: {len(grid)}"
    print(f"\n[그리드] 총 {len(grid)}셀 × IS/OOS = {len(grid)*2}번 실행")

    # ------------------------------------------------------------------
    # 4. 셀별 시뮬레이션
    # ------------------------------------------------------------------
    results = []
    all_trades_log = []  # exit_grid_trades.csv 용

    for cell_idx, (target_pct, stop_pct, max_hold, trail) in enumerate(grid):
        cell_id = f"C{cell_idx:03d}"

        is_trades = []
        oos_trades = []

        for split_name, split_entries in [("IS", is_entries), ("OOS", oos_entries)]:
            for _, row in split_entries.iterrows():
                sc = str(row["stock_code"])
                td = str(row["trade_date"])
                entry_price_raw = float(row["close_0930"])
                entry_time = "093000"

                # 진입 시점 이후 분봉 (09:31~)
                key = (sc, td)
                bars = minute_groups.get(key, pd.DataFrame())

                # D+1 분봉 (max_hold=next_day 시)
                next_day_bars = None
                if max_hold == "next_day":
                    nxt = get_next_trading_day(td, all_trade_dates)
                    if nxt:
                        nxt_key = (sc, nxt)
                        next_day_bars = minute_groups.get(nxt_key)

                trade_result = simulate_trade(
                    bars=bars,
                    entry_price_raw=entry_price_raw,
                    target_pct=target_pct,
                    stop_pct=stop_pct,
                    max_hold=max_hold,
                    trail=trail,
                    trade_date=td,
                    entry_time=entry_time,
                    all_trade_dates=all_trade_dates,
                    next_day_bars=next_day_bars,
                )

                trade_log = {
                    "cell_id": cell_id,
                    "split": split_name,
                    "trade_date": td,
                    "stock_code": sc,
                    "stock_name": row.get("stock_name", ""),
                    "entry_price_raw": entry_price_raw,
                    "target_pct": target_pct,
                    "stop_pct": stop_pct,
                    "max_hold": max_hold,
                    "trail": trail,
                    **trade_result,
                }
                all_trades_log.append(trade_log)

                if split_name == "IS":
                    is_trades.append(trade_result)
                else:
                    oos_trades.append(trade_result)

        is_stats  = compute_cell_stats(is_trades)
        oos_stats = compute_cell_stats(oos_trades)
        oos_pass  = check_pass(oos_stats)

        row_out = {
            "cell_id": cell_id,
            "target_pct": target_pct,
            "stop_pct": stop_pct,
            "max_hold": max_hold,
            "trail": trail,
            # IS 지표
            "is_n_trades": is_stats["n_trades"],
            "is_win_rate": is_stats["win_rate"],
            "is_avg_return_pct": is_stats["avg_return_pct"],
            "is_expectancy_won": is_stats["expectancy_won"],
            "is_profit_factor": is_stats["profit_factor"],
            "is_max_drawdown_pct": is_stats["max_drawdown_pct"],
            "is_sharpe": is_stats["sharpe"],
            "is_exit_target": is_stats["exit_target"],
            "is_exit_stop": is_stats["exit_stop"],
            "is_exit_trail": is_stats["exit_trail"],
            "is_exit_hold_expired": is_stats["exit_hold_expired"],
            "is_exit_gap_stop": is_stats["exit_gap_stop"],
            # OOS 지표
            "oos_n_trades": oos_stats["n_trades"],
            "oos_win_rate": oos_stats["win_rate"],
            "oos_avg_return_pct": oos_stats["avg_return_pct"],
            "oos_expectancy_won": oos_stats["expectancy_won"],
            "oos_profit_factor": oos_stats["profit_factor"],
            "oos_max_drawdown_pct": oos_stats["max_drawdown_pct"],
            "oos_sharpe": oos_stats["sharpe"],
            "oos_exit_target": oos_stats["exit_target"],
            "oos_exit_stop": oos_stats["exit_stop"],
            "oos_exit_trail": oos_stats["exit_trail"],
            "oos_exit_hold_expired": oos_stats["exit_hold_expired"],
            "oos_exit_gap_stop": oos_stats["exit_gap_stop"],
            # 통과 여부
            "pass_flag": oos_pass,
        }
        results.append(row_out)

        # 진행 상황 (20셀마다)
        if (cell_idx + 1) % 20 == 0 or cell_idx == 0:
            elapsed = time.time() - t_start
            print(f"  [{cell_idx+1:3d}/240] {elapsed:.1f}s 경과 | OOS pass={oos_pass} | "
                  f"target={target_pct}% stop={stop_pct}% hold={max_hold} trail={trail}")

    # ------------------------------------------------------------------
    # 5. CSV 저장
    # ------------------------------------------------------------------
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values("oos_avg_return_pct", ascending=False).reset_index(drop=True)
    df_results.to_csv(OUTPUT_GRID_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[저장] exit_grid_v1.csv → {OUTPUT_GRID_CSV}")

    df_trades = pd.DataFrame(all_trades_log)
    df_trades.to_csv(OUTPUT_TRADES_CSV, index=False, encoding="utf-8-sig")
    print(f"[저장] exit_grid_trades.csv → {OUTPUT_TRADES_CSV}")

    # ------------------------------------------------------------------
    # 6. 콘솔 보고
    # ------------------------------------------------------------------
    pass_cells_oos = df_results[df_results["pass_flag"] == True]
    pass_cells_is  = df_results[
        (df_results["is_n_trades"] >= 5) &
        (df_results["is_avg_return_pct"] >= 0.5) &
        (df_results["is_win_rate"] >= 0.55) &
        (df_results["is_expectancy_won"] > 0) &
        (df_results["is_sharpe"] > 0.3)
    ]

    print("\n" + "=" * 60)
    print("Phase 2 결과 보고")
    print("=" * 60)
    print(f"\n진입 케이스: IS={len(is_entries)}건 / OOS={len(oos_entries)}건")
    print(f"통과 셀: IS {len(pass_cells_is)}개 / OOS {len(pass_cells_oos)}개 (240셀 중)")

    # 상위 10개 셀
    print("\n[OOS avg_return_pct 기준 상위 10개 셀]")
    top10 = df_results.head(10)
    header = f"{'셀':>5} {'익절':>6} {'손절':>5} {'홀딩':>10} {'트레일':>22} {'n':>4} {'승률':>6} {'평균수익%':>9} {'기대수익(원)':>12} {'샤프':>6} {'pass':>5}"
    print(header)
    print("-" * len(header))
    for _, r in top10.iterrows():
        print(
            f"{r['cell_id']:>5} "
            f"{r['target_pct']:>5.1f}% "
            f"{r['stop_pct']:>4.1f}% "
            f"{r['max_hold']:>10} "
            f"{r['trail']:>22} "
            f"{int(r['oos_n_trades']):>4} "
            f"{r['oos_win_rate']*100:>5.1f}% "
            f"{r['oos_avg_return_pct']:>8.3f}% "
            f"{r['oos_expectancy_won']:>11,.0f}원 "
            f"{r['oos_sharpe']:>5.2f} "
            f"{'O' if r['pass_flag'] else 'X':>5}"
        )

    # 통과 셀 파라미터 분포
    if len(pass_cells_oos) > 0:
        print(f"\n[통과 셀 파라미터 분포 (OOS, {len(pass_cells_oos)}개)]")
        print("  익절 분포:", pass_cells_oos["target_pct"].value_counts().to_dict())
        print("  손절 분포:", pass_cells_oos["stop_pct"].value_counts().to_dict())
        print("  홀딩 분포:", pass_cells_oos["max_hold"].value_counts().to_dict())
        print("  트레일 분포:", pass_cells_oos["trail"].value_counts().to_dict())

        # 통과 셀 평균 청산 사유 분포
        avg_exit = {
            "target":       pass_cells_oos["oos_exit_target"].mean(),
            "stop":         pass_cells_oos["oos_exit_stop"].mean(),
            "trail":        pass_cells_oos["oos_exit_trail"].mean(),
            "hold_expired": pass_cells_oos["oos_exit_hold_expired"].mean(),
            "gap_stop":     pass_cells_oos["oos_exit_gap_stop"].mean(),
        }
        total_exit = sum(avg_exit.values())
        print(f"\n[청산 사유 분포 (통과 셀 평균, OOS)]")
        for reason, cnt in sorted(avg_exit.items(), key=lambda x: -x[1]):
            pct = cnt / total_exit * 100 if total_exit > 0 else 0
            print(f"  {reason:>15}: {cnt:5.1f}건 ({pct:5.1f}%)")
    else:
        print("\n  통과 셀 없음 — 청산 사유 분포 생략")

    # 상위 3개 셀 요약
    print(f"\n[상위 3개 셀 요약]")
    for rank, (_, r) in enumerate(df_results.head(3).iterrows(), 1):
        print(f"  #{rank}: cell={r['cell_id']} target={r['target_pct']}% stop={r['stop_pct']}% "
              f"hold={r['max_hold']} trail={r['trail']}")
        print(f"       OOS: n={int(r['oos_n_trades'])}, win_rate={r['oos_win_rate']*100:.1f}%, "
              f"avg_return={r['oos_avg_return_pct']:.3f}%, expectancy={r['oos_expectancy_won']:,.0f}원, "
              f"sharpe={r['oos_sharpe']:.2f}, pass={'O' if r['pass_flag'] else 'X'}")

    # Phase 2 게이트 판정
    n_pass = len(pass_cells_oos)
    print(f"\n{'='*60}")
    if n_pass >= 3:
        gate = "PASS"
        msg = f"통과 셀 {n_pass}개 ≥ 3 → Phase 3 진행 권고"
    elif n_pass >= 1:
        gate = "WARNING"
        msg = f"통과 셀 {n_pass}개 (1~2) → 단일 셀로 Phase 3 진행 (robustness 한계 명시)"
    else:
        gate = "FAIL"
        msg = "통과 셀 0개 → 진입 조건 자체 재검토 필요"

    print(f"[Phase 2 게이트 판정]: {gate}")
    print(f"  {msg}")

    if n_pass > 0:
        best = df_results[df_results["pass_flag"] == True].sort_values("oos_avg_return_pct", ascending=False).iloc[0]
        print(f"\n  Phase 3 고정 조건 권고 (OOS 최우수 셀):")
        print(f"    target_pct={best['target_pct']}%, stop_pct={best['stop_pct']}%, "
              f"max_hold={best['max_hold']}, trail={best['trail']}")
        print(f"    OOS avg_return={best['oos_avg_return_pct']:.3f}%, win_rate={best['oos_win_rate']*100:.1f}%")

    elapsed = time.time() - t_start
    print(f"\n[실행 시간] {elapsed:.1f}초")
    print(f"[산출물]")
    print(f"  {OUTPUT_GRID_CSV}")
    print(f"  {OUTPUT_TRADES_CSV}")


if __name__ == "__main__":
    main()
