"""P2 Stage C: 매도 룰 그리드 (단순화 3축)
================================================================
입력:
  - phase2b_signal_passed.csv (271 합격 시그널)
  - phase1_forward_returns.parquet (2,718,959행)
  - robotrader_quant.daily_prices (OHLC)
  - p2b_signal_multiverse.py (시그널 생성 로직 import)

처리:
  - 271 합격 중 (regime, bucket)별 Top 5 = ~48 시그널
  - 75 매도 룰 (5 SL × 5 TP × 3 TM) × ~48 시그널 = ~3,600 평가

산출물:
  - phase2c_exit_grid_all.csv
  - phase2c_exit_passed.csv
  - phase2c_top_triples_by_regime_bucket.md
  - phase2c_summary.md
"""

import sys
import os
import time
import warnings
import traceback
import ast

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# ── 경로 ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR   = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "10pct_strategy")
os.makedirs(REPORT_DIR, exist_ok=True)

OUT_ALL     = os.path.join(REPORT_DIR, "phase2c_exit_grid_all.csv")
OUT_PASS    = os.path.join(REPORT_DIR, "phase2c_exit_passed.csv")
OUT_TOP_MD  = os.path.join(REPORT_DIR, "phase2c_top_triples_by_regime_bucket.md")
OUT_SUMMARY = os.path.join(REPORT_DIR, "phase2c_summary.md")
OUT_CKPT    = os.path.join(REPORT_DIR, "phase2c_checkpoint.csv")

# ── p2b import ────────────────────────────────────────────────────────────────
sys.path.insert(0, SCRIPT_DIR)
from p2b_signal_multiverse import (
    load_data,
    build_regime_date_map,
    compute_signal_features,
    assign_regime_to_prices,
    build_universe_pools,
    apply_universe_filter,
    build_signal_catalog,
    REGIMES_6,
    TOP_N_PER_REGIME,
    BUCKET_HORIZONS,
    N_MIN,
)

# ── 하이퍼파라미터 ────────────────────────────────────────────────────────────
IS_CUTOFF = pd.Timestamp("2025-01-01")

# 매도 룰 3축
SL_GRID = [-0.015, -0.02, -0.03, -0.04, -0.05]
TP_GRID = [0.03, 0.05, 0.07, 0.10, 0.15]
TM_GRID = [5, 10, 20, 30, 45, 60]

# 합격 기준
PASS_MEAN_MIN   = 0.0
PASS_SHARPE_MIN = 0.5
PASS_MDD_MIN    = -0.2    # mdd > -0.2 (즉 최대낙폭 20% 이하)
PASS_N_MIN      = 30


# =============================================================================
# 1. Top-5 시그널 추출
# =============================================================================

def extract_top5(signals_df: pd.DataFrame) -> pd.DataFrame:
    """(regime, bucket)별 lift 상위 5."""
    signals_df = signals_df.copy()
    signals_df["lift"] = pd.to_numeric(signals_df["lift"], errors="coerce")
    top5 = (
        signals_df
        .sort_values("lift", ascending=False)
        .groupby(["regime", "bucket"], group_keys=False)
        .head(5)
        .reset_index(drop=True)
    )
    print(f"  Top-5 시그널: {len(top5)}개 "
          f"({top5.groupby(['regime','bucket']).ngroups} 조합)")
    return top5


# =============================================================================
# 2. 시그널 함수 매핑 (family + params → fn)
# =============================================================================

def build_signal_fn_map(catalog: dict) -> dict:
    """
    catalog의 (bucket, family, params_str) → fn 매핑.
    Returns: {(bucket, family, params_str): fn}
    """
    fn_map = {}
    for bucket, sigs in catalog.items():
        for sig in sigs:
            key = (bucket, sig["family"], str(sig["params"]))
            fn_map[key] = sig["fn"]
    return fn_map


# =============================================================================
# 3. OHLC 기반 매도 시뮬
# =============================================================================

def simulate_exit(ohlc_arr: np.ndarray, sl: float, tp: float, tm: int) -> float:
    """
    ohlc_arr: shape (N, 4) — [adj_open, adj_high, adj_low, adj_close], T+1 시작
    매수가 = ohlc_arr[0, 0] (T+1 시가)
    반환: pnl (decimal)
    """
    if len(ohlc_arr) == 0:
        return np.nan
    entry = ohlc_arr[0, 0]
    if entry <= 0 or np.isnan(entry):
        return np.nan
    sl_price = entry * (1 + sl)
    tp_price = entry * (1 + tp)
    n_days = min(tm, len(ohlc_arr))
    for d in range(n_days):
        high  = ohlc_arr[d, 1]
        low   = ohlc_arr[d, 2]
        close = ohlc_arr[d, 3]
        if np.isnan(low) or np.isnan(high) or np.isnan(close):
            continue
        if low <= sl_price:
            return sl
        if high >= tp_price:
            return tp
    # 시간 만기: 마지막 close
    last_close = ohlc_arr[n_days - 1, 3]
    if np.isnan(last_close) or entry <= 0:
        return np.nan
    return (last_close - entry) / entry


def compute_mdd(pnl_list: list) -> float:
    """pnl 리스트 → 최대 누적 낙폭 (equity curve 기준)."""
    if len(pnl_list) == 0:
        return np.nan
    eq = np.cumprod(1 + np.array(pnl_list))
    running_max = np.maximum.accumulate(eq)
    dd = (eq - running_max) / running_max
    return float(dd.min())


def compute_sharpe(pnl_arr: np.ndarray) -> float:
    if len(pnl_arr) < 2:
        return np.nan
    std = pnl_arr.std()
    if std == 0:
        return np.nan
    return float(pnl_arr.mean() / std * np.sqrt(252))


# =============================================================================
# 4. 단일 시그널 × 단일 매도 룰 평가
# =============================================================================

def evaluate_exit_cell(
    sig_days: pd.DataFrame,       # 시그널 발생 행 (date, stock_code 포함)
    prices_pivot: dict,            # stock_code → 정렬된 OHLC df
    sl: float, tp: float, tm: int,
) -> dict:
    """
    sig_days: signal mask가 True인 행들 (date, stock_code).
    prices_pivot: {stock_code: DataFrame with columns [date, adj_open, adj_high, adj_low, adj_close]}
                  날짜 오름차순 정렬, date를 index로.
    """
    pnl_all = []
    is_pnl  = []
    oos_pnl = []

    for _, row in sig_days.iterrows():
        sc   = row["stock_code"]
        date = row["date"]
        if sc not in prices_pivot:
            continue
        sc_df = prices_pivot[sc]
        # T+1 시가부터 tm일 슬라이스
        try:
            loc = sc_df.index.get_loc(date)
        except KeyError:
            continue
        start = loc + 1  # T+1
        end   = start + tm
        if start >= len(sc_df):
            continue
        slice_df = sc_df.iloc[start:end]
        if len(slice_df) == 0:
            continue
        ohlc = slice_df[["adj_open", "adj_high", "adj_low", "adj_close"]].values
        pnl  = simulate_exit(ohlc, sl, tp, tm)
        if np.isnan(pnl):
            continue
        pnl_all.append(pnl)
        if date < IS_CUTOFF:
            is_pnl.append(pnl)
        else:
            oos_pnl.append(pnl)

    n = len(pnl_all)
    if n < PASS_N_MIN:
        return {"n": n, "mean_pnl": np.nan, "std_pnl": np.nan,
                "win_rate": np.nan, "sharpe": np.nan, "mdd": np.nan,
                "IS_mean": np.nan, "OOS_mean": np.nan}

    arr = np.array(pnl_all)
    result = {
        "n":        n,
        "mean_pnl": float(arr.mean()),
        "std_pnl":  float(arr.std()),
        "win_rate": float((arr > 0).mean()),
        "sharpe":   compute_sharpe(arr),
        "mdd":      compute_mdd(pnl_all),
        "IS_mean":  float(np.mean(is_pnl))  if len(is_pnl)  >= 10 else np.nan,
        "OOS_mean": float(np.mean(oos_pnl)) if len(oos_pnl) >= 10 else np.nan,
    }
    return result


# =============================================================================
# 5. prices_pivot 빌드 (OHLC adj 기준)
# =============================================================================

def build_prices_pivot(prices: pd.DataFrame) -> dict:
    """
    {stock_code: DataFrame} — date를 index, adj OHLC 컬럼.
    adj_factor 없으면 원본 사용.
    """
    print("  prices_pivot 빌드 중...")
    t0 = time.time()
    needed = ["stock_code", "date", "open", "high", "low", "close"]
    has_adj = "adj_factor" in prices.columns

    pivot = {}
    for sc, grp in prices.groupby("stock_code", sort=False):
        grp = grp.sort_values("date").set_index("date")
        if has_adj:
            af = grp["adj_factor"].replace(0, np.nan).fillna(1.0)
            grp["adj_open"]  = grp["open"]  / af
            grp["adj_high"]  = grp["high"]  / af
            grp["adj_low"]   = grp["low"]   / af
            grp["adj_close"] = grp["close"] / af
        else:
            grp["adj_open"]  = grp["open"]
            grp["adj_high"]  = grp["high"]
            grp["adj_low"]   = grp["low"]
            grp["adj_close"] = grp["close"]
        pivot[sc] = grp[["adj_open", "adj_high", "adj_low", "adj_close"]]
    print(f"  prices_pivot 완료: {len(pivot)}개 종목 ({time.time()-t0:.1f}s)")
    return pivot


# =============================================================================
# 6. 메인 루프
# =============================================================================

def main():
    t_global = time.time()
    print("=" * 70)
    print("P2C Exit Grid — 시작")
    print("=" * 70)

    # ── 데이터 로드 (p2b 함수 재사용) ─────────────────────────────────────────
    print("\n[1/6] 데이터 로드")
    filters_df, fwd, seg, prices = load_data()

    # ── 전처리 ────────────────────────────────────────────────────────────────
    print("\n[2/6] 전처리 + 피처 계산")
    date_to_regime = build_regime_date_map(seg)
    prices = compute_signal_features(prices)
    prices = assign_regime_to_prices(prices, date_to_regime)
    fwd["date"] = pd.to_datetime(fwd["date"])
    fwd["regime"] = fwd["date"].map(date_to_regime)

    print("  prices + fwd 조인...")
    merged = prices.merge(
        fwd[["stock_code", "date",
             "fwd_1d", "fwd_3d", "fwd_5d", "fwd_10d", "fwd_20d", "fwd_30d", "fwd_60d"]],
        on=["stock_code", "date"],
        how="inner",
    )
    merged = merged.dropna(subset=["regime"])
    print(f"  merged: {merged.shape}")

    # ── prices_pivot (OHLC for exit sim) ─────────────────────────────────────
    print("\n[3/6] prices_pivot 빌드")
    # adj_factor 컬럼이 merged에 있을 수 있으므로 원본 prices 사용
    prices_pivot = build_prices_pivot(prices)

    # ── Top-5 시그널 추출 ─────────────────────────────────────────────────────
    print("\n[4/6] Top-5 시그널 추출")
    signals_df = pd.read_csv(os.path.join(REPORT_DIR, "phase2b_signal_passed.csv"))
    top5 = extract_top5(signals_df)

    # ── 시그널 카탈로그 빌드 + fn 매핑 ───────────────────────────────────────
    print("\n[5/6] 시그널 카탈로그 + fn 매핑")
    catalog  = build_signal_catalog()
    fn_map   = build_signal_fn_map(catalog)
    pools    = build_universe_pools(filters_df, TOP_N_PER_REGIME)
    pool_map = {(p["regime"], p["pool_rank"]): p for p in pools}

    # ── 체크포인트 로드 ───────────────────────────────────────────────────────
    results   = []
    done_keys = set()
    if os.path.exists(OUT_CKPT):
        print(f"  체크포인트 발견 → 재개: {OUT_CKPT}")
        prev = pd.read_csv(OUT_CKPT)
        results = prev.to_dict("records")
        for r in results:
            done_keys.add((r["regime"], r["bucket"], r["family"],
                           r["params"], r["sl"], r["tp"], r["tm"]))
        print(f"  기존 {len(results)} 셀 로드.")

    # ── 평가 루프 ─────────────────────────────────────────────────────────────
    print("\n[6/6] 평가 루프")
    total_sigs = len(top5)
    total_exit = len(SL_GRID) * len(TP_GRID) * len(TM_GRID)
    total_cells = total_sigs * total_exit
    print(f"  예상 셀: {total_sigs} 시그널 × {total_exit} 매도 룰 = {total_cells}")

    cell_count = 0
    pass_count = 0

    for sig_idx, sig_row in top5.iterrows():
        regime     = sig_row["regime"]
        bucket     = sig_row["bucket"]
        pool_rank  = int(sig_row["pool_rank"])
        family     = sig_row["family"]
        params_str = sig_row["params"]

        # fn 조회
        fn_key = (bucket, family, params_str)
        if fn_key not in fn_map:
            # params_str 형식 불일치 허용: ast.literal_eval 후 재시도
            try:
                params_dict = ast.literal_eval(params_str)
                fn_key_alt  = (bucket, family, str(params_dict))
                sig_fn = fn_map.get(fn_key_alt)
            except Exception:
                sig_fn = None
        else:
            sig_fn = fn_map[fn_key]

        if sig_fn is None:
            print(f"  [WARN] fn 없음: {bucket}/{family}/{params_str} → 스킵")
            cell_count += total_exit
            continue

        # pool 데이터 준비
        pool_key = (regime, pool_rank)
        if pool_key not in pool_map:
            print(f"  [WARN] pool 없음: {pool_key} → 스킵")
            cell_count += total_exit
            continue
        pool = pool_map[pool_key]
        pool_mask = apply_universe_filter(merged, pool)
        pool_df   = merged[pool_mask].copy()

        if len(pool_df) < N_MIN:
            cell_count += total_exit
            continue

        # 시그널 mask 계산 (한 번만)
        try:
            sig_mask = sig_fn(pool_df).fillna(False).astype(bool)
        except Exception as e:
            print(f"  [WARN] sig_fn 오류 ({family}): {e}")
            cell_count += total_exit
            continue

        sig_days = pool_df[sig_mask][["date", "stock_code"]].copy()
        if len(sig_days) == 0:
            cell_count += total_exit
            continue

        # 75 매도 룰 순회
        for sl in SL_GRID:
            for tp in TP_GRID:
                for tm in TM_GRID:
                    ck = (regime, bucket, family, params_str, sl, tp, tm)
                    if ck in done_keys:
                        cell_count += 1
                        continue

                    res = evaluate_exit_cell(sig_days, prices_pivot, sl, tp, tm)

                    mean_pnl = res["mean_pnl"]
                    sharpe   = res["sharpe"]
                    mdd      = res["mdd"]
                    IS_mean  = res["IS_mean"]
                    OOS_mean = res["OOS_mean"]
                    n        = res["n"]

                    pass_flag = (
                        pd.notna(mean_pnl)  and mean_pnl  > PASS_MEAN_MIN   and
                        pd.notna(sharpe)    and sharpe    > PASS_SHARPE_MIN  and
                        pd.notna(mdd)       and mdd       > PASS_MDD_MIN     and
                        pd.notna(IS_mean)   and IS_mean   > 0                and
                        pd.notna(OOS_mean)  and OOS_mean  > 0                and
                        n >= PASS_N_MIN
                    )

                    row = {
                        "regime":        regime,
                        "bucket":        bucket,
                        "pool_rank":     pool_rank,
                        "family":        family,
                        "params":        params_str,
                        "sl":            sl,
                        "tp":            tp,
                        "tm":            tm,
                        "n":             n,
                        "mean_pnl":      mean_pnl,
                        "std_pnl":       res["std_pnl"],
                        "win_rate":      res["win_rate"],
                        "sharpe":        sharpe,
                        "mdd":           mdd,
                        "IS_mean":       IS_mean,
                        "OOS_mean":      OOS_mean,
                        "sig_lift":      sig_row["lift"],
                        "pass":          pass_flag,
                    }
                    results.append(row)
                    done_keys.add(ck)
                    cell_count += 1
                    if pass_flag:
                        pass_count += 1

        # 진행 로그 (시그널 단위)
        pct = (sig_idx + 1) / total_sigs * 100
        elapsed = time.time() - t_global
        print(f"  [{sig_idx+1}/{total_sigs} {pct:.0f}%] "
              f"{regime}/{bucket}/{family} "
              f"sig_days={len(sig_days)} pass_so_far={pass_count} "
              f"({elapsed:.0f}s)")

        # 체크포인트 (시그널 10개마다)
        if (sig_idx + 1) % 10 == 0 and results:
            pd.DataFrame(results).to_csv(OUT_CKPT, index=False)

    # ── 결과 저장 ─────────────────────────────────────────────────────────────
    print("\n[저장]")
    if not results:
        print("  결과 없음.")
        return

    df_all  = pd.DataFrame(results)
    df_pass = df_all[df_all["pass"] == True].copy()

    df_all.to_csv(OUT_ALL,  index=False)
    df_pass.to_csv(OUT_PASS, index=False)
    print(f"  전체: {len(df_all):,} 셀 → {OUT_ALL}")
    print(f"  합격: {len(df_pass):,} 셀 → {OUT_PASS}")

    if os.path.exists(OUT_CKPT):
        os.remove(OUT_CKPT)

    # ── 리포트 ────────────────────────────────────────────────────────────────
    generate_top_triples_report(df_all, df_pass)
    generate_summary_report(df_all, df_pass, time.time() - t_global)

    print(f"\n완료! 총 {cell_count:,} 셀, 합격 {pass_count} 셀, "
          f"소요 {(time.time()-t_global)/60:.1f}분")


# =============================================================================
# 7. 리포트
# =============================================================================

def generate_top_triples_report(df_all: pd.DataFrame, df_pass: pd.DataFrame):
    """(regime, bucket)별 Top 트리플 표."""
    lines = [
        "# Phase 2C — (필터, 시그널, 출구) Top 트리플 by Regime × Bucket",
        "",
        f"생성일: {pd.Timestamp.now().strftime('%Y-%m-%d')}",
        f"전체 평가: {len(df_all):,} 셀 | 합격: {len(df_pass):,} 셀",
        "",
    ]

    buckets = ["swing", "mid", "position"]
    bucket_label = {"swing": "스윙 (5d 청산)", "mid": "미드 (20d 청산)", "position": "포지션 (60d 청산)"}

    for regime in REGIMES_6:
        for bucket in buckets:
            sub = df_pass[
                (df_pass["regime"] == regime) & (df_pass["bucket"] == bucket)
            ].copy()
            lines.append(f"## {regime} × {bucket_label.get(bucket, bucket)}")
            if len(sub) == 0:
                lines.append("_합격 없음_\n")
                continue
            # mean_pnl × sharpe 복합 정렬
            sub["score"] = sub["mean_pnl"] * sub["sharpe"].fillna(0)
            top = sub.nlargest(min(5, len(sub)), "score")
            lines.append("")
            lines.append("| rank | family | params | SL | TP | TM | mean_pnl | sharpe | mdd | IS_mean | OOS_mean | n |")
            lines.append("|------|--------|--------|----|----|----|----------|--------|-----|---------|----------|---|")
            for i, (_, r) in enumerate(top.iterrows(), 1):
                def fmt(v): return f"{v:.4f}" if pd.notna(v) else "N/A"
                lines.append(
                    f"| {i} | {r['family']} | {r['params']} "
                    f"| {r['sl']:.1%} | {r['tp']:.0%} | {int(r['tm'])}d "
                    f"| {fmt(r['mean_pnl'])} | {fmt(r['sharpe'])} | {fmt(r['mdd'])} "
                    f"| {fmt(r['IS_mean'])} | {fmt(r['OOS_mean'])} | {int(r['n'])} |"
                )
            lines.append("")

    with open(OUT_TOP_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Top 트리플 → {OUT_TOP_MD}")


def generate_summary_report(df_all: pd.DataFrame, df_pass: pd.DataFrame, elapsed: float):
    """한 장 요약 + P3 OK/NG."""
    total = len(df_all)
    n_pass = len(df_pass)
    pass_rate = n_pass / total * 100 if total > 0 else 0

    # (regime, bucket) 커버리지
    if n_pass > 0:
        covered = df_pass.groupby(["regime", "bucket"]).size()
        n_covered = len(covered)
    else:
        covered = pd.Series(dtype=int)
        n_covered = 0

    # BULL_HIGH_VOL × position top 매도 룰
    bhv_pos = df_pass[
        (df_pass["regime"] == "BULL_HIGH_VOL") &
        (df_pass["bucket"] == "position")
    ].copy()
    if len(bhv_pos) > 0:
        bhv_pos["score"] = bhv_pos["mean_pnl"] * bhv_pos["sharpe"].fillna(0)
        bhv_top = bhv_pos.nlargest(min(3, len(bhv_pos)), "score")
    else:
        bhv_top = pd.DataFrame()

    # 최우수 트리플 10개
    if n_pass > 0:
        df_pass2 = df_pass.copy()
        df_pass2["score"] = df_pass2["mean_pnl"] * df_pass2["sharpe"].fillna(0)
        best10 = df_pass2.nlargest(min(10, n_pass), "score")
    else:
        best10 = pd.DataFrame()

    # P3 판단
    p3_ok = "OK" if (n_pass >= 30 and n_covered >= 6) else "NG"

    lines = [
        "# Phase 2C 요약 — 매도 룰 그리드 결과",
        "",
        f"생성일: {pd.Timestamp.now().strftime('%Y-%m-%d')}",
        f"소요: {elapsed/60:.1f}분",
        "",
        "## 처리 결과",
        f"- 전체 평가 셀: **{total:,}**",
        f"- 합격 셀: **{n_pass}** ({pass_rate:.1f}%)",
        f"- 합격 기준: mean_pnl > 0 AND sharpe > {PASS_SHARPE_MIN} AND mdd > {PASS_MDD_MIN} AND IS > 0 AND OOS > 0 AND n ≥ {PASS_N_MIN}",
        "",
        "## 매도 룰 그리드",
        f"- 손절(SL): {SL_GRID}",
        f"- 익절(TP): {TP_GRID}",
        f"- 시간만기(TM): {TM_GRID}일",
        "",
        "## (Regime, Bucket) 커버리지",
        f"- 합격 조합: **{n_covered}** / {len(REGIMES_6) * 3}",
        "",
    ]

    if n_covered > 0:
        lines += ["| Regime × Bucket | 합격 셀 |", "|-----------------|---------|"]
        for (reg, bkt), cnt in covered.items():
            lines.append(f"| {reg} × {bkt} | {cnt} |")
        lines.append("")

    lines += [
        "## BULL_HIGH_VOL × Position 최우수 매도 룰",
        "",
    ]
    if len(bhv_top) > 0:
        lines += [
            "| rank | family | SL | TP | TM | mean_pnl | sharpe | mdd | IS_mean | OOS_mean | n |",
            "|------|--------|----|----|----|----------|--------|-----|---------|----------|---|",
        ]
        for i, (_, r) in enumerate(bhv_top.iterrows(), 1):
            def fmt(v): return f"{v:.4f}" if pd.notna(v) else "N/A"
            lines.append(
                f"| {i} | {r['family']} "
                f"| {r['sl']:.1%} | {r['tp']:.0%} | {int(r['tm'])}d "
                f"| {fmt(r['mean_pnl'])} | {fmt(r['sharpe'])} | {fmt(r['mdd'])} "
                f"| {fmt(r['IS_mean'])} | {fmt(r['OOS_mean'])} | {int(r['n'])} |"
            )
        lines.append("")
    else:
        lines.append("_합격 없음_\n")

    lines += [
        "## 전체 최우수 (필터, 시그널, 출구) 트리플 Top 10",
        "",
    ]
    if len(best10) > 0:
        lines += [
            "| rank | regime | bucket | family | params | SL | TP | TM | mean_pnl | sharpe | n |",
            "|------|--------|--------|--------|--------|----|----|----|----------|--------|---|",
        ]
        for i, (_, r) in enumerate(best10.iterrows(), 1):
            def fmt(v): return f"{v:.4f}" if pd.notna(v) else "N/A"
            lines.append(
                f"| {i} | {r['regime']} | {r['bucket']} | {r['family']} | {r['params']} "
                f"| {r['sl']:.1%} | {r['tp']:.0%} | {int(r['tm'])}d "
                f"| {fmt(r['mean_pnl'])} | {fmt(r['sharpe'])} | {int(r['n'])} |"
            )
        lines.append("")
    else:
        lines.append("_합격 없음_\n")

    lines += [
        "## P3 진입 판단",
        f"- **{p3_ok}** — 합격 셀 {n_pass}개, (regime, bucket) 조합 커버 {n_covered}/{len(REGIMES_6)*3}",
        "",
        "### 판정 기준",
        "- OK: 합격 셀 ≥ 30 AND (regime, bucket) 조합 커버 ≥ 6/18",
        "- NG: 기준 미달 → 합격선 완화 또는 매도 룰 그리드 확장 필요",
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
