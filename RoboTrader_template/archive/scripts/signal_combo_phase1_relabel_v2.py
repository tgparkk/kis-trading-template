"""
signal_combo_phase1_relabel_v2.py
==================================
Phase 1 재재측정: +1% 익절 목표로 조정.

동기 (사장님 결재 2026-05-23):
  - 기존 +2% 익절 / -1% 손절: base safe rate 25.4%, 가장 강한 신호로도 expectancy 음수
  - 결재: +1% 익절로 낮춰서 빈도 우선 재측정
  - 목표: "매매당 +1% 이상이라도 안정적으로"

신규 라벨 정의 (4종):
  진입가 = close_0930 (09:30:00 봉 close, cases_v3.csv 기존 동일)
  분봉 09:31 ~ 15:30 시간순 순회:
    - low  <= entry * (1 - stop) 먼저 → 0 (손절)
    - high >= entry * (1 + 0.01) 먼저 → 1 (익절)
    - 동시 발생 → 0 (보수적, 손절 우선)
    - 15:30까지 미발생 → 0

손절선 4종:
  label_1pct_safe_stop03  (-0.3%)
  label_1pct_safe_stop05  (-0.5%)
  label_1pct_safe_stop07  (-0.7%)
  label_1pct_safe_stop10  (-1.0%)

Expectancy 계산:
  비용 = 0.41% (슬리피지+수수료+거래세)
  expectancy_stopXX = safe_rate × (1.0 - 0.41) - (1 - safe_rate) × (stop_pct + 0.41)
  단위: % per trade

산출물:
  cases_v4.csv              (cases_v3 + 신규 4종 라벨)
  reach_1pct_analysis.csv   (safe rate + expectancy 4종)
  label_comparison_v2.csv   (2pct + 1pct 전체 base rate 통합 비교)

사용법:
  cd RoboTrader_template
  python scripts/signal_combo_phase1_relabel_v2.py
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

INPUT_CASES_CSV   = REPORT_DIR / "cases_v3.csv"
OUTPUT_CASES_CSV  = REPORT_DIR / "cases_v4.csv"
OUTPUT_REACH_CSV  = REPORT_DIR / "reach_1pct_analysis.csv"
OUTPUT_COMP_CSV   = REPORT_DIR / "label_comparison_v2.csv"

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
# 1% 익절 손절선 목록
# ---------------------------------------------------------------------------
STOP_SPECS_1PCT = [
    ("stop03", 0.003),
    ("stop05", 0.005),
    ("stop07", 0.007),
    ("stop10", 0.010),
]
LABEL_1PCT_COLS = [f"label_1pct_safe_{tag}" for tag, _ in STOP_SPECS_1PCT]

# 비용 가정 (슬리피지+수수료+거래세), 단위 %
COST_PCT = 0.41
# 익절 목표
TARGET_PCT = 0.01

# 분봉 쿼리 기간
DATE_START = "20260401"
DATE_END   = "20260523"

# 2pct safe 라벨 컬럼 (cases_v3에서 보존)
LABEL_2PCT_COLS = [
    "label_2pct_safe_stop08",
    "label_2pct_safe_stop10",
    "label_2pct_safe_stop15",
    "label_2pct_safe_stop20",
]
STOP_SPECS_2PCT = [
    ("stop08", 0.008),
    ("stop10", 0.010),
    ("stop15", 0.015),
    ("stop20", 0.020),
]

# ---------------------------------------------------------------------------
# 분봉 데이터 로드 (09:31 ~ 15:30)
# ---------------------------------------------------------------------------

def load_post_entry_minute_data(stock_codes: list[str], conn) -> pd.DataFrame:
    """09:31:00 ~ 15:30:00 분봉 로드."""
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
# 1pct safe label 시뮬레이션 (단일 stock-day)
# ---------------------------------------------------------------------------

def simulate_1pct_safe_labels(
    bars: pd.DataFrame,
    entry_price: float,
    stop_rates: list[float],
) -> list[int]:
    """
    bars: (time, high, low) — 09:31~15:30 시간 오름차순 정렬된 분봉
    entry_price: close_0930
    stop_rates: [0.003, 0.005, 0.007, 0.010]

    Returns:
        safe_labels: [0/1 per stop_rate]
          1 = +1% 익절 먼저 도달 (손절선 미돌파)
          0 = 손절 먼저 또는 만기 또는 동시 (보수적)
    """
    target = entry_price * (1 + TARGET_PCT)
    stop_prices = [entry_price * (1 - r) for r in stop_rates]

    n_stops = len(stop_rates)
    finished = [False] * n_stops
    results  = [0]     * n_stops   # 기본값 0

    for _, row in bars.iterrows():
        h  = float(row["high"])
        lo = float(row["low"])

        hit_target = h >= target

        for i, sp in enumerate(stop_prices):
            if finished[i]:
                continue
            hit_stop = lo <= sp
            if hit_target and hit_stop:
                # 동시 발생 → 보수적: 손절 우선
                results[i] = 0
                finished[i] = True
            elif hit_target:
                results[i] = 1
                finished[i] = True
            elif hit_stop:
                results[i] = 0
                finished[i] = True

        if all(finished):
            break

    return results


# ---------------------------------------------------------------------------
# cases_v3에 1pct safe label 추가
# ---------------------------------------------------------------------------

def add_1pct_safe_labels(cases_df: pd.DataFrame, minute_df: pd.DataFrame) -> pd.DataFrame:
    """cases_df에 label_1pct_safe_stopXX 4종 컬럼 추가."""
    stop_rates = [r for _, r in STOP_SPECS_1PCT]

    # 분봉 in-memory 인덱스
    print("[인덱스] 분봉 in-memory 인덱스 구성 중...")
    minute_idx: dict[tuple[str, str], pd.DataFrame] = {}
    for (sc, td), grp in minute_df.groupby(["stock_code", "trade_date"]):
        minute_idx[(str(sc), str(td))] = grp.sort_values("time").reset_index(drop=True)
    print(f"  {len(minute_idx):,}개 (stock, date) 쌍 인덱스 완료")

    # 결과 컬럼 초기화
    for col in LABEL_1PCT_COLS:
        cases_df[col] = np.nan

    n_total     = len(cases_df)
    n_no_minute = 0
    n_no_entry  = 0

    print(f"[시뮬] {n_total:,}건 1pct safe label 계산 중...")
    for i, row in cases_df.iterrows():
        if (i + 1) % 1000 == 0:
            pct = (i + 1) / n_total * 100
            print(f"  {i+1:,}/{n_total:,} ({pct:.1f}%)")

        sc = str(row["stock_code"]).zfill(6)
        td = str(row["trade_date"])
        entry_price = row["close_0930"]

        if pd.isna(entry_price) or entry_price <= 0:
            n_no_entry += 1
            continue

        bars = minute_idx.get((sc, td))
        if bars is None or bars.empty:
            n_no_minute += 1
            continue

        safe_labels = simulate_1pct_safe_labels(bars, float(entry_price), stop_rates)

        for j, col in enumerate(LABEL_1PCT_COLS):
            cases_df.at[i, col] = float(safe_labels[j])

    print(f"  entry_price 없음: {n_no_entry}건, 분봉 없음: {n_no_minute}건")
    return cases_df


# ---------------------------------------------------------------------------
# Expectancy 계산 헬퍼
# ---------------------------------------------------------------------------

def calc_expectancy(safe_rate: float, stop_pct_decimal: float) -> float:
    """
    expectancy = safe_rate × (target_pct - cost_pct) - (1 - safe_rate) × (stop_pct + cost_pct)
    target_pct = 1.0% (고정), cost_pct = 0.41%
    단위: % per trade
    """
    win  = safe_rate * (1.0 - COST_PCT)
    loss = (1 - safe_rate) * (stop_pct_decimal * 100 + COST_PCT)
    return win - loss


# ---------------------------------------------------------------------------
# reach_1pct_analysis 계산
# ---------------------------------------------------------------------------

def compute_reach_1pct_analysis(cases_df: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """
    기존 Phase 1 reach 분석과 동일 룰셋 + 1pct safe rate 4종 + expectancy 4종.
    """
    valid = cases_df[cases_df["label_2pct"].notna()].copy()
    n_total = len(valid)

    # base rates
    base_rates: dict[str, float] = {}
    # 단순 1pct 도달 (참고용): high_max >= entry * 1.01
    # cases_v3에 없으므로 계산
    if "label_1pct_raw" not in valid.columns:
        # 1pct 단순 도달 = 어떤 stop이든 상관없이 +1% 이상 도달
        # stop03이 가장 관대하므로 stop03의 1 or stop05 상위집합? 아님.
        # 실제로는 분봉 재조회 없이는 단순 1pct 도달 불가. label_1pct_safe_stop03을 참고값으로 사용.
        pass

    for col in LABEL_1PCT_COLS:
        sub = valid[valid[col].notna()]
        base_rates[col] = float(sub[col].mean()) if len(sub) > 0 else 0.0

    base_2pct = float(valid["label_2pct"].mean()) if n_total > 0 else 0.0

    def get_col_mask(col, thr):
        if col not in valid.columns:
            return pd.Series([False] * len(valid), index=valid.index)
        return valid[col].notna() & (valid[col] >= thr)

    def evaluate_rule(mask: pd.Series, rule_desc: str) -> dict | None:
        sub = valid[mask]
        n = len(sub)
        if n == 0:
            return None

        row: dict = {
            "signal_rule": rule_desc,
            "n_cases":     n,
        }

        # 1pct safe rates
        for col, (tag, stop_rate) in zip(LABEL_1PCT_COLS, STOP_SPECS_1PCT):
            sub_safe = sub[sub[col].notna()]
            if len(sub_safe) > 0:
                sr = float(sub_safe[col].mean())
                base_s = base_rates[col]
                lift_s = round(sr / base_s, 4) if base_s > 0 else None
                exp = round(calc_expectancy(sr, stop_rate), 4)
            else:
                sr = None
                lift_s = None
                exp = None
            row[f"reach_1pct_safe_{tag}"]  = round(sr, 4) if sr is not None else None
            row[f"base_1pct_safe_{tag}"]   = round(base_rates[col], 4)
            row[f"lift_1pct_safe_{tag}"]   = lift_s
            row[f"expectancy_{tag}"]       = exp

        return row

    rows = []

    # --- 단일 신호 임계 (기존 Phase 1과 동일 셋) ---
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

    # --- AND 조합 8개 (기존 Phase 1과 동일) ---
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
    # 기본 정렬: expectancy_stop05 내림차순 (사장님 결재 기준)
    if not df.empty and "expectancy_stop05" in df.columns:
        df = df.sort_values("expectancy_stop05", ascending=False).reset_index(drop=True)

    return df, base_rates, base_2pct


# ---------------------------------------------------------------------------
# label_comparison_v2.csv — 2pct + 1pct 통합 비교
# ---------------------------------------------------------------------------

def compute_label_comparison_v2(cases_df: pd.DataFrame, base_2pct: float) -> pd.DataFrame:
    """모든 라벨의 base rate를 한눈에 비교."""
    rows = []

    # label_2pct 단순
    valid_2 = cases_df[cases_df["label_2pct"].notna()]
    rows.append({
        "label":       "label_2pct (단순)",
        "target_pct":  2.0,
        "stop_pct":    None,
        "n_valid":     len(valid_2),
        "base_rate":   round(float(valid_2["label_2pct"].mean()) if len(valid_2) > 0 else 0.0, 4),
        "trap_rate":   None,
        "expectancy_vs_stop": None,
    })

    # 2pct safe labels (from cases_v3)
    for col, (tag, stop_rate) in zip(LABEL_2PCT_COLS, STOP_SPECS_2PCT):
        if col not in cases_df.columns:
            continue
        sub = cases_df[cases_df[col].notna()]
        safe_rate = float(sub[col].mean()) if len(sub) > 0 else 0.0
        trap = (base_2pct - safe_rate) / base_2pct if base_2pct > 0 else None
        exp = round(safe_rate * (2.0 - COST_PCT) - (1 - safe_rate) * (stop_rate * 100 + COST_PCT), 4)
        rows.append({
            "label":              f"label_2pct_safe_{tag}",
            "target_pct":         2.0,
            "stop_pct":           stop_rate * 100,
            "n_valid":            len(sub),
            "base_rate":          round(safe_rate, 4),
            "trap_rate":          round(trap, 4) if trap is not None else None,
            "expectancy_vs_stop": exp,
        })

    # 1pct safe labels (신규)
    for col, (tag, stop_rate) in zip(LABEL_1PCT_COLS, STOP_SPECS_1PCT):
        if col not in cases_df.columns:
            continue
        sub = cases_df[cases_df[col].notna()]
        safe_rate = float(sub[col].mean()) if len(sub) > 0 else 0.0
        # trap_rate 참고: stop03 기준 단순 1pct 도달 없으므로 N/A
        exp = round(calc_expectancy(safe_rate, stop_rate), 4)
        rows.append({
            "label":              f"label_1pct_safe_{tag}",
            "target_pct":         1.0,
            "stop_pct":           stop_rate * 100,
            "n_valid":            len(sub),
            "base_rate":          round(safe_rate, 4),
            "trap_rate":          None,
            "expectancy_vs_stop": exp,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 콘솔 보고
# ---------------------------------------------------------------------------

def print_report(
    cases_df: pd.DataFrame,
    reach_df: pd.DataFrame,
    comp_df: pd.DataFrame,
    base_rates_1pct: dict,
    base_2pct: float,
    elapsed: float,
) -> None:
    print()
    print("=" * 90)
    print("  Phase 1 재재측정 — +1% 익절 Safe Label 분석 결과 (사장님 결재 2026-05-23)")
    print("=" * 90)
    print(f"  실행 시간       : {elapsed:.1f}초")
    print(f"  전체 stock-day  : {len(cases_df):,}건")
    valid_n = int(cases_df["label_2pct"].notna().sum())
    print(f"  라벨 유효 건수  : {valid_n:,}건")
    print()

    # ------------------------------------------------------------------ #
    # 1. Base rates 표
    # ------------------------------------------------------------------ #
    print("  [1] Base Rate 비교")
    print(f"  {'라벨':<40}  {'base_rate':>10}  {'expectancy':>12}")
    print("  " + "-" * 67)
    print(f"  {'base_2pct_rate (단순 +2% 도달, 참고)':<40}  {base_2pct*100:>9.1f}%  {'  -':>12}")
    print(f"  {'base_2pct_safe_stop10 (기존 최우수)':<40}  ", end="")
    col10 = "label_2pct_safe_stop10"
    sub10 = cases_df[cases_df[col10].notna()] if col10 in cases_df.columns else pd.DataFrame()
    if len(sub10) > 0:
        sr10 = float(sub10[col10].mean())
        exp10 = round(sr10 * (2.0 - COST_PCT) - (1 - sr10) * (1.0 + COST_PCT), 4)
        print(f"{sr10*100:>9.1f}%  {exp10:>+11.2f}%")
    else:
        print("   N/A")
    print()

    for col, (tag, stop_rate) in zip(LABEL_1PCT_COLS, STOP_SPECS_1PCT):
        sr = base_rates_1pct.get(col, 0.0)
        exp = calc_expectancy(sr, stop_rate)
        label_str = f"base_1pct_safe_{tag} (stop={stop_rate*100:.1f}%)"
        print(f"  {label_str:<40}  {sr*100:>9.1f}%  {exp:>+11.2f}%")

    # 사장님 목표 stop 강조
    sr05_key = "label_1pct_safe_stop05"
    sr05 = base_rates_1pct.get(sr05_key, 0.0)
    exp05_base = calc_expectancy(sr05, 0.005)
    print(f"\n  ** 사장님 결재 중심: base_1pct_safe_stop05 = {sr05*100:.1f}%,"
          f" expectancy = {exp05_base:+.2f}% **")
    print()

    # ------------------------------------------------------------------ #
    # 2. Top 5 룰 (expectancy_stop05 기준)
    # ------------------------------------------------------------------ #
    print("  [2] 가장 강한 룰 Top 5 (expectancy_stop05 기준, 사장님 결재 +1%/-0.5%)")
    exp05_col = "expectancy_stop05"
    if not reach_df.empty and exp05_col in reach_df.columns:
        top5 = reach_df.dropna(subset=[exp05_col]).nlargest(5, exp05_col)
        print(f"  {'룰':<52}  {'n':>5}  {'safe05':>7}  {'exp_03':>8}  {'exp_05':>8}  {'exp_07':>8}  {'exp_10':>8}")
        print("  " + "-" * 104)
        for _, r in top5.iterrows():
            sr05 = r.get("reach_1pct_safe_stop05")
            def _fmt_exp(v):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return "    N/A"
                return f"{v:+7.2f}%"
            def _fmt_rate(v):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return "   N/A"
                return f"{v*100:6.1f}%"
            print(
                f"  {r['signal_rule']:<52}  {int(r['n_cases']):>5,}"
                f"  {_fmt_rate(sr05):>7}"
                f"  {_fmt_exp(r.get('expectancy_stop03')):>8}"
                f"  {_fmt_exp(r.get('expectancy_stop05')):>8}"
                f"  {_fmt_exp(r.get('expectancy_stop07')):>8}"
                f"  {_fmt_exp(r.get('expectancy_stop10')):>8}"
            )
    print()

    # ------------------------------------------------------------------ #
    # 3. expectancy 양수 룰 개수 (각 stop별)
    # ------------------------------------------------------------------ #
    print("  [3] Expectancy 양수 룰 개수 (stop별)")
    print(f"  {'stop':>10}  {'양수 룰 수':>10}  {'전체 룰 수':>10}  {'비율':>8}")
    print("  " + "-" * 44)
    for tag, stop_rate in STOP_SPECS_1PCT:
        exp_col = f"expectancy_{tag}"
        if exp_col not in reach_df.columns:
            continue
        vals = reach_df[exp_col].dropna()
        n_pos  = int((vals > 0).sum())
        n_all  = len(vals)
        ratio  = n_pos / n_all * 100 if n_all > 0 else 0.0
        print(f"  {tag:>10}  {n_pos:>10}  {n_all:>10}  {ratio:>7.1f}%")
    print()

    # ------------------------------------------------------------------ #
    # 4. Phase 1 재재측정 게이트 판정
    # ------------------------------------------------------------------ #
    print("  [4] Phase 1 재재측정 게이트 판정 (expectancy_stop05 양수 룰 기준)")
    gate_col = "expectancy_stop05"
    if not reach_df.empty and gate_col in reach_df.columns:
        vals = reach_df[gate_col].dropna()
        n_pos = int((vals > 0).sum())
        if n_pos >= 3:
            verdict = "PASS"
            reason  = f"expectancy_stop05 양수 룰 {n_pos}개 확인 → Phase 2 그리드 재실행 권고"
        elif n_pos >= 1:
            verdict = "WARNING"
            reason  = (f"expectancy_stop05 양수 룰 {n_pos}개 → 신중 진행 (샘플 수 / robustness 확인 필요)")
        else:
            verdict = "FAIL"
            reason  = "expectancy_stop05 양수 룰 0개 → 사장님께 추가 결재 필요 (익절 목표 재논의)"
        print(f"    양수 룰 수   : {n_pos}개")
        print(f"    게이트 판정  : [{verdict}] {reason}")
    print()

    # ------------------------------------------------------------------ #
    # 5. Phase 2 진행 권고
    # ------------------------------------------------------------------ #
    print("  [5] Phase 2 진행 권고")
    if not reach_df.empty and gate_col in reach_df.columns:
        pos_rules = reach_df[reach_df[gate_col].notna() & (reach_df[gate_col] > 0)]
        if not pos_rules.empty:
            top3 = pos_rules.nlargest(3, gate_col)
            print("    다음 룰로 +1% 익절 그리드 재실행 권고:")
            for _, r in top3.iterrows():
                exp05_val = r.get(gate_col)
                sr05_val  = r.get("reach_1pct_safe_stop05")
                n_val     = int(r["n_cases"])
                exp_str   = f"{exp05_val:+.2f}%" if exp05_val is not None and not pd.isna(exp05_val) else "N/A"
                sr_str    = f"{sr05_val*100:.1f}%" if sr05_val is not None and not pd.isna(sr05_val) else "N/A"
                print(f"    - \"{r['signal_rule']}\" (n={n_val:,}, safe05={sr_str}, expectancy_05={exp_str})")
        else:
            print("    Expectancy 양수 룰 없음. 사장님께 추가 결재 요청:")
            print("    - 익절 목표 재논의 (예: +0.7%?)")
            print("    - 진입 시점 변경 (09:30 외)")
            print("    - stop_rate 완화 (stop05 → stop03)")
    print()

    print("  [산출물]")
    print(f"    {OUTPUT_CASES_CSV}")
    print(f"    {OUTPUT_REACH_CSV}")
    print(f"    {OUTPUT_COMP_CSV}")
    print("=" * 90)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()

    print("=" * 90)
    print("  Phase 1 재재측정 — +1% 익절 Safe Label 계산")
    print("  기간: 2026-04-01 ~ 2026-05-23 / 입력: cases_v3.csv")
    print("=" * 90)

    # --- cases_v3.csv 로드 ---
    print(f"\n[1/6] cases_v3.csv 로드: {INPUT_CASES_CSV}")
    if not INPUT_CASES_CSV.exists():
        print(f"  ERROR: {INPUT_CASES_CSV} 없음. signal_combo_phase1_relabel.py를 먼저 실행하세요.")
        sys.exit(1)
    cases_df = pd.read_csv(INPUT_CASES_CSV, dtype={"stock_code": str, "trade_date": str})
    cases_df["stock_code"] = cases_df["stock_code"].str.zfill(6)
    print(f"  {len(cases_df):,}행 로드 완료 / 컬럼: {len(cases_df.columns)}개")

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

    # --- 1pct safe label 계산 ---
    print("\n[4/6] 1pct safe label 시뮬레이션 (4종: stop03/05/07/10)...")
    cases_df = add_1pct_safe_labels(cases_df, minute_df)

    # 분포 확인
    print("\n[4b] 1pct safe label 분포 확인:")
    for col, (tag, stop_rate) in zip(LABEL_1PCT_COLS, STOP_SPECS_1PCT):
        sub = cases_df[cases_df[col].notna()]
        if len(sub) > 0:
            rate = float(sub[col].mean())
            print(f"  {col}: {rate*100:.1f}%  (n={len(sub):,})")
        else:
            print(f"  {col}: N/A")

    # --- reach 분석 ---
    print("\n[5/6] reach_1pct_analysis 계산...")
    reach_df, base_rates_1pct, base_2pct = compute_reach_1pct_analysis(cases_df)
    print(f"  {len(reach_df):,}개 룰 평가 완료")

    # --- label_comparison_v2 ---
    comp_df = compute_label_comparison_v2(cases_df, base_2pct)

    # --- 저장 ---
    print("\n[6/6] CSV 저장...")
    cases_df.to_csv(OUTPUT_CASES_CSV, index=False, encoding="utf-8-sig")
    reach_df.to_csv(OUTPUT_REACH_CSV, index=False, encoding="utf-8-sig")
    comp_df.to_csv(OUTPUT_COMP_CSV, index=False, encoding="utf-8-sig")
    print(f"  cases_v4.csv            : {len(cases_df):,}행")
    print(f"  reach_1pct_analysis.csv : {len(reach_df):,}행")
    print(f"  label_comparison_v2.csv : {len(comp_df):,}행")

    elapsed = time.time() - t0
    print_report(cases_df, reach_df, comp_df, base_rates_1pct, base_2pct, elapsed)


if __name__ == "__main__":
    main()
