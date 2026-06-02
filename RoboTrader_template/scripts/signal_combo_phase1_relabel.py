"""
signal_combo_phase1_relabel.py
==============================
Phase 1 재측정: cases_v2.csv에 safe label 4종 추가 후 reach 분석 재실행.

동기 (사장님):
  - 기존 label_2pct = "D당일 09:30~15:30 어느 시점이든 +2% 도달" → 너무 관대
  - 실전: 손절선이 +2% 익절보다 먼저 걸리면 -stop% 손실 마감
  - safe label = "진입 후 손절선 안 깨고 +2% 먼저 도달" 으로 재정의

safe label 시뮬레이션 로직:
  - 진입가 = 09:30:00 봉의 close (cases_v2.csv close_0930 컬럼)
  - 분봉 09:31 ~ 15:30 시간 ASC 순회
  - high >= entry * (1 + 0.02) 먼저 → 1 (익절)
  - low  <= entry * (1 - stop)  먼저 → 0 (손절)
  - 동시 발생 (같은 봉에서 both) → 0 (보수적, 손절 우선)
  - 15:30까지 둘 다 안 발생 → 0

산출물:
  - cases_v3.csv          (cases_v2 + safe label 4종 + time_to_2pct_min/time_to_stop_min)
  - reach_2pct_analysis_v2.csv  (safe rate 4종 추가 reach 분석)
  - label_comparison.csv        (단순 vs safe 비교 표)

사용법:
  cd RoboTrader_template
  python scripts/signal_combo_phase1_relabel.py
"""

from __future__ import annotations

import io
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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

REPORT_DIR = PROJECT_ROOT / "reports" / "signal_combo_aprmay"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

INPUT_CASES_CSV  = REPORT_DIR / "cases_v2.csv"
OUTPUT_CASES_CSV = REPORT_DIR / "cases_v3.csv"
OUTPUT_REACH_CSV = REPORT_DIR / "reach_2pct_analysis_v2.csv"
OUTPUT_COMP_CSV  = REPORT_DIR / "label_comparison.csv"

# ---------------------------------------------------------------------------
# DB 연결 설정
# ---------------------------------------------------------------------------
DB_MINUTE = {
    "host":     os.getenv("TIMESCALE_HOST",     "127.0.0.1"),
    "port":     int(os.getenv("TIMESCALE_PORT", 5433)),
    "database": "robotrader",
    "user":     os.getenv("TIMESCALE_USER",     "robotrader"),
    "password": os.getenv("TIMESCALE_PASSWORD", "1234"),
}

# ---------------------------------------------------------------------------
# 손절선 목록
# ---------------------------------------------------------------------------
STOP_SPECS = [
    ("stop08", 0.008),
    ("stop10", 0.010),
    ("stop15", 0.015),
    ("stop20", 0.020),
]
SAFE_LABEL_COLS   = [f"label_2pct_safe_{tag}" for tag, _ in STOP_SPECS]
TIME_TO_2PCT_COL  = "time_to_2pct_min"
TIME_TO_STOP_COL  = "time_to_stop_min"

# 분봉 쿼리 기간 (cases_v2와 동일)
DATE_START = "20260401"
DATE_END   = "20260523"

# ---------------------------------------------------------------------------
# 분봉 데이터 로드 (09:31 ~ 15:30)
# ---------------------------------------------------------------------------

def load_post_entry_minute_data(stock_codes: list[str], conn) -> pd.DataFrame:
    """
    09:31:00 ~ 15:30:00 분봉 로드.
    time 컬럼: 'HHMMSS' 문자열.
    """
    print(f"[분봉] {len(stock_codes):,}개 종목, 09:31~15:30 로드 중...")
    stock_list_sql = ",".join(f"'{s}'" for s in stock_codes)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT stock_code, trade_date, time, high, low
        FROM minute_candles
        WHERE trade_date >= '{DATE_START}' AND trade_date <= '{DATE_END}'
          AND time >  '093000'
          AND time <= '153000'
          AND stock_code IN ({stock_list_sql})
        ORDER BY stock_code, trade_date, time
    """)
    rows = cur.fetchall()
    cols = ["stock_code", "trade_date", "time", "high", "low"]
    df = pd.DataFrame(rows, columns=cols)
    print(f"[분봉] {len(df):,}행 로드 완료")
    return df


# ---------------------------------------------------------------------------
# safe label 시뮬레이션 (단일 stock-day)
# ---------------------------------------------------------------------------

def simulate_safe_labels(
    bars: pd.DataFrame,
    entry_price: float,
    stop_rates: list[float],
) -> tuple[list[int], float | None, float | None]:
    """
    bars: (time, high, low) — 09:31~15:30 시간 오름차순 정렬된 분봉
    entry_price: close_0930
    stop_rates: [0.008, 0.010, 0.015, 0.020]

    Returns:
        safe_labels: [0/1 per stop_rate]
        time_to_2pct_min:  진입 후 +2% 도달 경과 분 (None이면 미도달)
        time_to_stop_min:  진입 후 손절 도달 경과 분 (stop_rates[0] 기준)
    """
    target = entry_price * 1.02

    # 손절가 배열
    stop_prices = [entry_price * (1 - r) for r in stop_rates]

    # 결과 초기화
    n_stops = len(stop_rates)
    finished  = [False] * n_stops  # 각 stop_rate별로 결과 확정 여부
    results   = [0]     * n_stops  # 기본값 0 (손절 또는 미도달)

    time_to_2pct_min = None
    time_to_stop_min = None  # stop_rates[0] 기준

    # 진입 시각: 09:30 = 분봉 index 0 → 09:31봉이 1분 뒤
    # time 컬럼 'HHMMSS' → 시간 차이 계산
    entry_hour, entry_min = 9, 30

    for _, row in bars.iterrows():
        h = float(row["high"])
        lo = float(row["low"])
        t_str = str(row["time"]).zfill(6)
        t_h, t_m = int(t_str[:2]), int(t_str[2:4])
        elapsed_min = (t_h - entry_hour) * 60 + (t_m - entry_min)

        hit_target = h >= target
        # time_to_2pct_min: 처음 도달하는 봉 기준
        if hit_target and time_to_2pct_min is None:
            time_to_2pct_min = elapsed_min

        for i, sp in enumerate(stop_prices):
            if finished[i]:
                continue
            hit_stop = lo <= sp
            if hit_target and hit_stop:
                # 동시 발생 → 보수적: 손절 우선 (결과 0)
                results[i] = 0
                finished[i] = True
                if i == 0 and time_to_stop_min is None:
                    time_to_stop_min = elapsed_min
            elif hit_target:
                results[i] = 1
                finished[i] = True
            elif hit_stop:
                results[i] = 0
                finished[i] = True
                if i == 0 and time_to_stop_min is None:
                    time_to_stop_min = elapsed_min

        if all(finished):
            break

    return results, time_to_2pct_min, time_to_stop_min


# ---------------------------------------------------------------------------
# cases_v2에 safe label 추가
# ---------------------------------------------------------------------------

def add_safe_labels(cases_df: pd.DataFrame, minute_df: pd.DataFrame) -> pd.DataFrame:
    """
    cases_df에 safe label 4종 + time_to_2pct_min + time_to_stop_min 컬럼 추가.
    분봉이 없거나 entry_price가 None인 케이스는 NaN 처리.
    """
    stop_rates = [r for _, r in STOP_SPECS]

    # 분봉 인덱스: (stock_code, trade_date) -> sorted DataFrame
    print("[인덱스] 분봉 in-memory 인덱스 구성 중...")
    minute_idx: dict[tuple[str, str], pd.DataFrame] = {}
    for (sc, td), grp in minute_df.groupby(["stock_code", "trade_date"]):
        minute_idx[(str(sc), str(td))] = grp.sort_values("time").reset_index(drop=True)
    print(f"  {len(minute_idx):,}개 (stock, date) 쌍 인덱스 완료")

    # 결과 컬럼 초기화
    for col in SAFE_LABEL_COLS:
        cases_df[col] = np.nan
    cases_df[TIME_TO_2PCT_COL] = np.nan
    cases_df[TIME_TO_STOP_COL] = np.nan

    n_total = len(cases_df)
    n_no_minute = 0
    n_no_entry  = 0

    print(f"[시뮬] {n_total:,}건 safe label 계산 중...")
    for i, row in cases_df.iterrows():
        if (i + 1) % 1000 == 0:
            pct = (i + 1) / n_total * 100
            print(f"  {i+1:,}/{n_total:,} ({pct:.1f}%)")

        sc = str(row["stock_code"]).zfill(6)
        td = str(row["trade_date"])
        entry_price = row["close_0930"]

        # entry_price 없음 → skip (NaN 유지)
        if pd.isna(entry_price) or entry_price <= 0:
            n_no_entry += 1
            continue

        bars = minute_idx.get((sc, td))
        if bars is None or bars.empty:
            n_no_minute += 1
            continue

        safe_labels, t2pct, tstop = simulate_safe_labels(bars, float(entry_price), stop_rates)

        for j, col in enumerate(SAFE_LABEL_COLS):
            cases_df.at[i, col] = float(safe_labels[j])
        if t2pct is not None:
            cases_df.at[i, TIME_TO_2PCT_COL] = float(t2pct)
        if tstop is not None:
            cases_df.at[i, TIME_TO_STOP_COL] = float(tstop)

    print(f"  entry_price 없음: {n_no_entry}건, 분봉 없음: {n_no_minute}건")
    return cases_df


# ---------------------------------------------------------------------------
# reach_2pct_analysis_v2 계산
# ---------------------------------------------------------------------------

def compute_reach_analysis_v2(cases_df: pd.DataFrame) -> pd.DataFrame:
    """
    기존 reach_2pct_analysis.csv와 동일 룰셋 + safe rate 4종 추가.
    """
    valid = cases_df[cases_df["label_2pct"].notna()].copy()
    n_total = len(valid)

    # base rates
    base_2pct_rate = float(valid["label_2pct"].mean()) if n_total > 0 else 0.0
    base_safe_rates = {}
    for col in SAFE_LABEL_COLS:
        sub = valid[valid[col].notna()]
        base_safe_rates[col] = float(sub[col].mean()) if len(sub) > 0 else 0.0

    def evaluate_rule(mask: pd.Series, rule_desc: str) -> dict | None:
        sub = valid[mask]
        n = len(sub)
        if n == 0:
            return None
        r2 = float(sub["label_2pct"].mean())
        lift2 = round(r2 / base_2pct_rate, 4) if base_2pct_rate > 0 else None

        row: dict = {
            "signal_rule":      rule_desc,
            "n_cases":          n,
            "reach_2pct_rate":  round(r2, 4),
            "base_2pct_rate":   round(base_2pct_rate, 4),
            "lift_2pct":        lift2,
        }
        for col, tag_pair in zip(SAFE_LABEL_COLS, STOP_SPECS):
            tag, _ = tag_pair
            sub_safe = sub[sub[col].notna()]
            if len(sub_safe) > 0:
                rs = float(sub_safe[col].mean())
                base_s = base_safe_rates[col]
                lift_s = round(rs / base_s, 4) if base_s > 0 else None
            else:
                rs = None
                lift_s = None
            row[f"reach_2pct_safe_{tag}"]  = round(rs, 4) if rs is not None else None
            row[f"base_2pct_safe_{tag}"]   = round(base_safe_rates[col], 4)
            row[f"lift_2pct_safe_{tag}"]   = lift_s
        return row

    def get_col_mask(col, thr):
        if col not in valid.columns:
            return pd.Series([False] * len(valid), index=valid.index)
        return valid[col].notna() & (valid[col] >= thr)

    rows = []

    # --- 단일 신호 임계 ---
    for thr in [10, 15, 20, 25, 30]:
        r = evaluate_rule(get_col_mask("ret_20d_pct", thr), f"ret_20d_pct>={thr}")
        if r: rows.append(r)

    for thr in [5, 10, 15, 20]:
        r = evaluate_rule(get_col_mask("ma20_dist_pct", thr), f"ma20_dist_pct>={thr}")
        if r: rows.append(r)

    for thr in [6, 8, 10]:
        r = evaluate_rule(get_col_mask("atr_20d_pct", thr), f"atr_20d_pct>={thr}")
        if r: rows.append(r)

    for thr in [1, 2, 3, 4]:
        r = evaluate_rule(get_col_mask("m30_volatility_pct", thr), f"m30_volatility_pct>={thr}")
        if r: rows.append(r)

    for thr in [0.0, 0.5, 1.0, 1.5]:
        r = evaluate_rule(get_col_mask("m30_close_vs_open", thr), f"m30_close_vs_open>={thr}")
        if r: rows.append(r)

    for thr in [1.0, 1.5, 2.0]:
        r = evaluate_rule(get_col_mask("vol_ratio_d1_vs_d20", thr), f"vol_ratio_d1_vs_d20>={thr}")
        if r: rows.append(r)

    for thr in [0.0, 1.0, 2.0]:
        r = evaluate_rule(get_col_mask("gap_pct_v2", thr), f"gap_pct_v2>={thr}")
        if r: rows.append(r)

    # --- AND 조합 8개 ---
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
        if r: rows.append(r)

    df = pd.DataFrame(rows)
    if not df.empty and "lift_2pct_safe_stop10" in df.columns:
        df = df.sort_values("lift_2pct_safe_stop10", ascending=False).reset_index(drop=True)
    return df, base_2pct_rate, base_safe_rates


# ---------------------------------------------------------------------------
# label_comparison.csv 생성
# ---------------------------------------------------------------------------

def compute_label_comparison(cases_df: pd.DataFrame) -> pd.DataFrame:
    """
    단순 +2% 도달 vs safe +2% (각 stop별) 전체 비교.
    """
    valid = cases_df[cases_df["label_2pct"].notna()].copy()
    base_2pct = float(valid["label_2pct"].mean()) if len(valid) > 0 else 0.0

    rows = []
    for col, (tag, stop_rate) in zip(SAFE_LABEL_COLS, STOP_SPECS):
        sub = valid[valid[col].notna()]
        n_safe = len(sub)
        safe_rate = float(sub[col].mean()) if n_safe > 0 else 0.0
        trap_rate = (base_2pct - safe_rate) / base_2pct if base_2pct > 0 else 0.0
        rows.append({
            "label":           f"label_2pct_safe_{tag}",
            "stop_pct":        stop_rate * 100,
            "n_total":         len(valid),
            "n_safe_valid":    n_safe,
            "base_2pct_rate":  round(base_2pct, 4),
            "safe_rate":       round(safe_rate, 4),
            "trap_rate":       round(trap_rate, 4),   # (단순 - safe) / 단순
            "delta":           round(base_2pct - safe_rate, 4),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 콘솔 보고
# ---------------------------------------------------------------------------

def print_report(
    cases_df: pd.DataFrame,
    reach_df: pd.DataFrame,
    comp_df: pd.DataFrame,
    base_2pct_rate: float,
    base_safe_rates: dict,
    elapsed: float,
) -> None:
    valid = cases_df[cases_df["label_2pct"].notna()]
    n_valid = len(valid)

    print()
    print("=" * 80)
    print("  Phase 1 재측정 — Safe Label 분석 결과")
    print("=" * 80)
    print(f"  실행 시간       : {elapsed:.1f}초")
    print(f"  전체 stock-day  : {len(cases_df):,}건")
    print(f"  라벨 유효 건수  : {n_valid:,}건")
    print()

    # 1. base rates 표
    print("  [1] Base Rate 비교 (단순 도달 vs Safe)")
    print(f"  {'라벨':<38}  {'base_rate':>10}  {'함정율':>8}")
    print("  " + "-" * 62)
    print(f"  {'base_2pct_rate (단순 +2% 도달)':<38}  {base_2pct_rate*100:>9.1f}%  {'  -':>8}")
    trap_rates = []
    for col, (tag, stop_rate) in zip(SAFE_LABEL_COLS, STOP_SPECS):
        sr = base_safe_rates.get(col, 0.0)
        trap = (base_2pct_rate - sr) / base_2pct_rate if base_2pct_rate > 0 else 0.0
        trap_rates.append(trap)
        label_str = f"base_2pct_safe_{tag} (stop={stop_rate*100:.1f}%)"
        print(f"  {label_str:<38}  {sr*100:>9.1f}%  {trap*100:>7.1f}%")
    avg_trap = sum(trap_rates) / len(trap_rates) if trap_rates else 0.0
    print(f"\n  평균 함정율: {avg_trap*100:.1f}%  (단순 도달하지만 손절 먼저 걸리는 비율)")
    print()

    # 2. top 5 룰 (lift_2pct_safe_stop10 기준)
    print("  [2] 가장 강한 룰 Top 5 (lift_2pct_safe_stop10 기준)")
    safe10_col = "lift_2pct_safe_stop10"
    if not reach_df.empty and safe10_col in reach_df.columns:
        top5 = reach_df.dropna(subset=[safe10_col]).nlargest(5, safe10_col)
        print(f"  {'룰':<52}  {'n':>6}  {'단순':>7}  {'safe10':>7}  {'함정율':>7}  {'lift_s10':>9}")
        print("  " + "-" * 97)
        for _, r in top5.iterrows():
            r2 = r["reach_2pct_rate"]
            rs10 = r.get("reach_2pct_safe_stop10")
            ls10 = r.get(safe10_col)
            trap = (r2 - rs10) / r2 if (rs10 is not None and r2 > 0) else None
            trap_str = f"{trap*100:.1f}%" if trap is not None else "N/A"
            rs10_str = f"{rs10*100:.1f}%" if rs10 is not None else "N/A"
            ls10_str = f"{ls10:.3f}x" if ls10 is not None else "N/A"
            print(f"  {r['signal_rule']:<52}  {int(r['n_cases']):>6,}  {r2*100:>6.1f}%  {rs10_str:>7}  {trap_str:>7}  {ls10_str:>9}")
    print()

    # 3. 단순 → safe 변환 표 (전체 룰)
    print("  [3] 단순 도달률 → safe10 변환 표 (상위 20 룰, lift_2pct 정렬)")
    if not reach_df.empty:
        display = reach_df.sort_values("lift_2pct", ascending=False).head(20)
        print(f"  {'룰':<52}  {'단순':>7}  {'safe08':>7}  {'safe10':>7}  {'safe15':>7}  {'safe20':>7}")
        print("  " + "-" * 100)
        for _, r in display.iterrows():
            def fmt(v): return f"{v*100:.1f}%" if (v is not None and not pd.isna(v)) else "  N/A"
            print(
                f"  {r['signal_rule']:<52}  {fmt(r['reach_2pct_rate']):>7}  "
                f"{fmt(r.get('reach_2pct_safe_stop08')):>7}  "
                f"{fmt(r.get('reach_2pct_safe_stop10')):>7}  "
                f"{fmt(r.get('reach_2pct_safe_stop15')):>7}  "
                f"{fmt(r.get('reach_2pct_safe_stop20')):>7}"
            )
    print()

    # 4. Phase 1 재측정 게이트 판정 (safe stop10 기준 lift >= 2)
    print("  [4] Phase 1 재측정 게이트 판정 (safe stop10 lift >= 2)")
    if not reach_df.empty and "lift_2pct_safe_stop10" in reach_df.columns:
        lift_vals = reach_df["lift_2pct_safe_stop10"].dropna()
        n_pass    = int((lift_vals >= 2.0).sum())
        n_warn    = int(((lift_vals >= 1.5) & (lift_vals < 2.0)).sum())
        print(f"    safe stop10 lift >= 2.0 룰 수 : {n_pass}개")
        print(f"    safe stop10 lift 1.5~2.0 룰 수: {n_warn}개")
        if n_pass >= 1:
            verdict = "PASS"
            reason  = f"safe stop10 lift >= 2.0 룰 {n_pass}개 확인 → Phase 2 재실행 권고"
        elif n_warn >= 1:
            verdict = "WARNING"
            reason  = f"safe stop10 lift 1.5~2.0 룰 {n_warn}개 → Phase 2 재실행 가능하나 robustness 한계 명시 필요"
        else:
            verdict = "FAIL"
            reason  = "safe stop10 lift < 1.5 → 신호 자체 재검토 필요"
        print(f"    게이트 판정 : [{verdict}] {reason}")
    print()

    # 5. 가설 검증
    print("  [5] 가설 검증")
    if not reach_df.empty:
        # 가설 1: "ret_20d>=25 AND atr_20d>=8" Phase 2~3 진입 조건
        h1_rule = "ret_20d>=25 AND atr_20d>=8"
        h1_row = reach_df[reach_df["signal_rule"] == h1_rule]
        if not h1_row.empty:
            h1 = h1_row.iloc[0]
            r2   = h1["reach_2pct_rate"]
            rs10 = h1.get("reach_2pct_safe_stop10")
            ls10 = h1.get("lift_2pct_safe_stop10")
            trap = (r2 - rs10) / r2 if (rs10 is not None and r2 > 0) else None
            print(f"  가설 1: [{h1_rule}] (Phase 2~3 진입 조건)")
            print(f"    단순 +2% 도달률 : {r2*100:.1f}%  (n={int(h1['n_cases']):,})")
            print(f"    safe stop10 rate: {rs10*100:.1f}%  lift={ls10:.3f}x" if rs10 is not None else "    safe stop10 rate: N/A")
            print(f"    함정율          : {trap*100:.1f}%" if trap is not None else "    함정율: N/A")
            if ls10 is not None:
                verdict_h1 = "OK (lift >= 2)" if ls10 >= 2.0 else ("경고 (lift 1.5~2.0)" if ls10 >= 1.5 else "실패 (lift < 1.5)")
                print(f"    판정            : {verdict_h1}")
                if ls10 < 1.5:
                    print("    → Phase 2~3 실패의 근본 원인: 진입 조건 자체의 safe lift 부족")
        else:
            print(f"  가설 1: [{h1_rule}] 룰 데이터 없음")
        print()

        # 가설 2: 모든 룰의 safe rate가 단순 도달률보다 크게 낮은가
        all_traps = []
        for _, row in reach_df.iterrows():
            r2 = row.get("reach_2pct_rate")
            rs10 = row.get("reach_2pct_safe_stop10")
            if r2 and rs10 and r2 > 0 and not pd.isna(r2) and not pd.isna(rs10):
                all_traps.append((r2 - rs10) / r2)
        if all_traps:
            mean_trap = sum(all_traps) / len(all_traps)
            print(f"  가설 2: 모든 룰의 함정율 평균 = {mean_trap*100:.1f}%")
            print(f"    (전체 {len(all_traps)}개 룰 중 safe rate < 단순 도달률인 룰 비율)")
            if mean_trap > 0.1:
                print("    → 시장 전체에 '올라가지만 손절 먼저 걸리는' 패턴이 광범위하게 존재")
            else:
                print("    → 함정율 낮음: safe label과 단순 label 간 괴리 미미")
    print()

    # 권고
    print("  [권고]")
    if not reach_df.empty and "lift_2pct_safe_stop10" in reach_df.columns:
        lift_vals = reach_df["lift_2pct_safe_stop10"].dropna()
        n_pass = int((lift_vals >= 2.0).sum())
        if n_pass >= 1:
            # 상위 룰 제시
            best = reach_df.dropna(subset=["lift_2pct_safe_stop10"]).nlargest(3, "lift_2pct_safe_stop10")
            rules_str = ", ".join(f'"{r["signal_rule"]}"' for _, r in best.iterrows())
            print(f"    Phase 2 재실행 권고: {rules_str} 조건으로 safe stop10 기준 재측정")
        else:
            print("    신호 재설계 권고: 현재 신호 조합으로는 safe lift >= 2 미달")
            print("    검토사항: 진입 시점 변경(09:30 외), 더 강한 모멘텀 필터, stop_rate 조정")
    print()

    print("  [산출물]")
    print(f"    {OUTPUT_CASES_CSV}")
    print(f"    {OUTPUT_REACH_CSV}")
    print(f"    {OUTPUT_COMP_CSV}")
    print("=" * 80)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()

    print("=" * 80)
    print("  Phase 1 재측정 — Safe Label 계산 (손절선 고려)")
    print("  기간: 2026-04-01 ~ 2026-05-23 / 입력: cases_v2.csv")
    print("=" * 80)

    # --- cases_v2.csv 로드 ---
    print(f"\n[1/6] cases_v2.csv 로드: {INPUT_CASES_CSV}")
    if not INPUT_CASES_CSV.exists():
        print(f"  ERROR: {INPUT_CASES_CSV} 가 없습니다. signal_combo_phase1.py를 먼저 실행하세요.")
        sys.exit(1)
    cases_df = pd.read_csv(INPUT_CASES_CSV, dtype={"stock_code": str, "trade_date": str})
    # stock_code 6자리 zero-pad
    cases_df["stock_code"] = cases_df["stock_code"].str.zfill(6)
    print(f"  {len(cases_df):,}행 로드 완료")

    # --- DB 연결 ---
    print("\n[2/6] DB 연결...")
    conn = psycopg2.connect(**DB_MINUTE)
    conn.autocommit = True
    print("  OK")

    # --- 분봉 로드 (09:31~15:30) ---
    print("\n[3/6] 분봉 데이터 로드 (09:31~15:30)...")
    all_stocks = cases_df["stock_code"].unique().tolist()
    minute_df = load_post_entry_minute_data(all_stocks, conn)
    conn.close()
    print("  DB 연결 종료")

    # --- safe label 계산 ---
    print("\n[4/6] safe label 시뮬레이션...")
    cases_df = add_safe_labels(cases_df, minute_df)

    # safe label 결과 요약
    print("\n[4b] safe label 분포 확인:")
    for col, (tag, stop_rate) in zip(SAFE_LABEL_COLS, STOP_SPECS):
        sub = cases_df[cases_df[col].notna()]
        if len(sub) > 0:
            rate = float(sub[col].mean())
            print(f"  {col}: {rate*100:.1f}%  (n={len(sub):,})")
        else:
            print(f"  {col}: N/A")

    # --- reach 분석 ---
    print("\n[5/6] reach_2pct_analysis_v2 계산...")
    reach_df, base_2pct_rate, base_safe_rates = compute_reach_analysis_v2(cases_df)
    print(f"  {len(reach_df):,}개 룰 평가 완료")

    # --- label_comparison ---
    comp_df = compute_label_comparison(cases_df)

    # --- 저장 ---
    print("\n[6/6] CSV 저장...")
    cases_df.to_csv(OUTPUT_CASES_CSV, index=False, encoding="utf-8-sig")
    reach_df.to_csv(OUTPUT_REACH_CSV, index=False, encoding="utf-8-sig")
    comp_df.to_csv(OUTPUT_COMP_CSV, index=False, encoding="utf-8-sig")
    print(f"  cases_v3.csv:              {len(cases_df):,}행")
    print(f"  reach_2pct_analysis_v2.csv:{len(reach_df):,}행")
    print(f"  label_comparison.csv:      {len(comp_df):,}행")

    elapsed = time.time() - t0
    print_report(cases_df, reach_df, comp_df, base_2pct_rate, base_safe_rates, elapsed)


if __name__ == "__main__":
    main()
