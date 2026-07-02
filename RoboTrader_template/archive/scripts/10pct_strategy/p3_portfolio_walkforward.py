"""P3: 포트폴리오 Walk-Forward 평가
================================================================
사장님 결재 2026-05-24:
  - swing 4 합격 조합 (BULL_HIGH_VOL / BULL_LOW_VOL / BEAR_HIGH_VOL / SIDEWAYS_LOW_VOL)
  - 279 합격 트리플 → regime별 Top 3~5 선택 (sharpe 기준)
  - BEAR_LOW_VOL / SIDEWAYS_HIGH_VOL = 현금 보유
  - 3 자금 배분 방식 × 6 walk-forward 윈도우 평가
  - 정직 보고만 (사후 결정)

산출물:
  - reports/10pct_strategy/phase3_triple_correlation.csv
  - reports/10pct_strategy/phase3_walkforward_results.csv
  - reports/10pct_strategy/phase3_portfolio_combo.md
  - reports/10pct_strategy/phase3_summary.md

실행:
  python RoboTrader_template/scripts/10pct_strategy/p3_portfolio_walkforward.py
"""

import sys
import os
import time
import warnings
import traceback
import ast

# Windows console UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# ── 경로 ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR   = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "10pct_strategy")
os.makedirs(REPORT_DIR, exist_ok=True)

# p2b / p2c import
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
    N_MIN,
)
from p2c_exit_grid import (
    simulate_exit,
    build_prices_pivot,
    build_signal_fn_map,
)

# ── 출력 파일 ──────────────────────────────────────────────────────────────────
OUT_CORR  = os.path.join(REPORT_DIR, "phase3_triple_correlation.csv")
OUT_WF    = os.path.join(REPORT_DIR, "phase3_walkforward_results.csv")
OUT_COMBO = os.path.join(REPORT_DIR, "phase3_portfolio_combo.md")
OUT_SUM   = os.path.join(REPORT_DIR, "phase3_summary.md")

# ── 상수 ──────────────────────────────────────────────────────────────────────
APPROVED_REGIMES = ["BULL_HIGH_VOL", "BULL_LOW_VOL", "BEAR_HIGH_VOL", "SIDEWAYS_LOW_VOL"]
CASH_REGIMES     = ["BEAR_LOW_VOL", "SIDEWAYS_HIGH_VOL"]
TOP_K = 5           # 국면당 최대 트리플 수

# Walk-forward 설정 (calendar days)
WF_TRAIN_DAYS = 365   # ~252 trading days
WF_TEST_DAYS  = 91    # ~63 trading days

# 자금 배분 C 방식 (국면별 고정 비중)
ALLOC_C = {
    "BULL_LOW_VOL":      0.30,
    "BULL_HIGH_VOL":     0.30,
    "BEAR_HIGH_VOL":     0.25,
    "SIDEWAYS_LOW_VOL":  0.15,
}

INITIAL_CAPITAL = 10_000_000   # 1천만 원 가상 자본


# =============================================================================
# 1. 트리플 그룹화 — 합격 swing 트리플 국면별 Top K
# =============================================================================

def select_top_triples(triples_df: pd.DataFrame) -> pd.DataFrame:
    """
    279 합격 트리플에서 승인된 4개 국면의 swing만 추출.
    국면별 sharpe 상위 TOP_K 선택 (중복 제거: 동일 (regime,family,params,sl,tp,tm)).
    """
    swing = triples_df[
        (triples_df["bucket"] == "swing") &
        (triples_df["regime"].isin(APPROVED_REGIMES))
    ].copy()

    # 완전 중복 제거 후 sharpe 상위
    dedup_cols = ["regime", "family", "params", "sl", "tp", "tm"]
    swing = swing.sort_values("sharpe", ascending=False).drop_duplicates(dedup_cols)

    top = (
        swing
        .groupby("regime", group_keys=False)
        .head(TOP_K)
        .reset_index(drop=True)
    )
    top["triple_id"] = [f"T{i:03d}" for i in range(len(top))]
    print(f"  선택된 트리플: {len(top)}개")
    for r in APPROVED_REGIMES:
        cnt = (top["regime"] == r).sum()
        print(f"    {r}: {cnt}개")
    return top


# =============================================================================
# 2. 각 트리플의 일별 PnL 시계열 추출
# =============================================================================

def extract_triple_daily_pnl(
    top_triples: pd.DataFrame,
    merged: pd.DataFrame,
    prices_pivot: dict,
    fn_map: dict,
    pool_map: dict,
) -> dict:
    """
    triple_id → 일별 PnL Series (date index).
    시그널 발생일에 simulate_exit로 PnL 계산 후 signal_date 기준으로 집계.
    """
    print("  트리플별 일별 PnL 시계열 추출 중...")
    t0 = time.time()
    pnl_series = {}   # triple_id → pd.Series(date → pnl)

    for _, row in top_triples.iterrows():
        tid    = row["triple_id"]
        regime = row["regime"]
        family = row["family"]
        params = row["params"]
        sl     = row["sl"]
        tp     = row["tp"]
        tm     = int(row["tm"])
        pool_rank = int(row["pool_rank"])

        # fn 조회
        fn_key = ("swing", family, params)
        sig_fn = fn_map.get(fn_key)
        if sig_fn is None:
            try:
                pd_dict = ast.literal_eval(params)
                sig_fn = fn_map.get(("swing", family, str(pd_dict)))
            except Exception:
                pass
        if sig_fn is None:
            print(f"  [WARN] fn 없음: {family}/{params} → {tid} 스킵")
            pnl_series[tid] = pd.Series(dtype=float)
            continue

        # pool 데이터
        pool_key = (regime, pool_rank)
        if pool_key not in pool_map:
            print(f"  [WARN] pool 없음: {pool_key} → {tid} 스킵")
            pnl_series[tid] = pd.Series(dtype=float)
            continue

        pool = pool_map[pool_key]
        pool_mask = apply_universe_filter(merged, pool)
        pool_df   = merged[pool_mask].copy()

        if len(pool_df) < N_MIN:
            pnl_series[tid] = pd.Series(dtype=float)
            continue

        # 시그널 계산
        try:
            sig_mask = sig_fn(pool_df).fillna(False).astype(bool)
        except Exception as e:
            print(f"  [WARN] sig_fn 오류 {tid}: {e}")
            pnl_series[tid] = pd.Series(dtype=float)
            continue

        sig_days = pool_df[sig_mask][["date", "stock_code"]].copy()

        # 각 시그널 → simulate_exit
        records = []
        for _, srow in sig_days.iterrows():
            sc   = srow["stock_code"]
            date = srow["date"]
            if sc not in prices_pivot:
                continue
            sc_df = prices_pivot[sc]
            try:
                loc = sc_df.index.get_loc(date)
            except KeyError:
                continue
            start = loc + 1
            end   = start + tm
            if start >= len(sc_df):
                continue
            slice_df = sc_df.iloc[start:end]
            if len(slice_df) == 0:
                continue
            ohlc = slice_df[["adj_open", "adj_high", "adj_low", "adj_close"]].values
            pnl  = simulate_exit(ohlc, sl, tp, tm)
            if not np.isnan(pnl):
                records.append({"date": date, "pnl": pnl})

        if not records:
            pnl_series[tid] = pd.Series(dtype=float)
            continue

        df_r = pd.DataFrame(records)
        # 같은 날 여러 종목 시그널 → 날짜별 평균 (equal-weight per signal)
        daily = df_r.groupby("date")["pnl"].mean()
        pnl_series[tid] = daily

    elapsed = time.time() - t0
    print(f"  PnL 시계열 완료 ({elapsed:.1f}s), 유효 트리플: {sum(1 for v in pnl_series.values() if len(v)>0)}개")
    return pnl_series


# =============================================================================
# 3. 트리플 간 상관관계 매트릭스
# =============================================================================

def compute_triple_correlation(
    top_triples: pd.DataFrame,
    pnl_series: dict,
) -> pd.DataFrame:
    """Pearson 상관계수 매트릭스 (triple_id 기준)."""
    tids = top_triples["triple_id"].tolist()
    # 전체 날짜 union
    all_dates = sorted(set().union(*[s.index for s in pnl_series.values() if len(s) > 0]))
    if not all_dates:
        return pd.DataFrame()

    mat = pd.DataFrame(index=all_dates, columns=tids, dtype=float)
    for tid in tids:
        if tid in pnl_series and len(pnl_series[tid]) > 0:
            mat[tid] = pnl_series[tid].reindex(all_dates)

    corr = mat.corr(method="pearson")

    # Flatten for CSV
    rows = []
    for i, t1 in enumerate(tids):
        for j, t2 in enumerate(tids):
            if j <= i:
                continue
            r1 = top_triples[top_triples["triple_id"] == t1].iloc[0]
            r2 = top_triples[top_triples["triple_id"] == t2].iloc[0]
            c  = corr.loc[t1, t2] if (t1 in corr.index and t2 in corr.columns) else np.nan
            rows.append({
                "triple_id_a": t1, "regime_a": r1["regime"],
                "family_a": r1["family"],
                "triple_id_b": t2, "regime_b": r2["regime"],
                "family_b": r2["family"],
                "pearson_corr": round(float(c), 4) if pd.notna(c) else np.nan,
            })

    df_corr = pd.DataFrame(rows)
    return df_corr


# =============================================================================
# 4. Walk-Forward 6 윈도우
# =============================================================================

def build_wf_windows(date_min: pd.Timestamp, date_max: pd.Timestamp) -> list:
    """
    252 train / 63 test 슬라이딩 (calendar days WF_TRAIN_DAYS / WF_TEST_DAYS).
    최대 6 윈도우.
    """
    windows = []
    start = date_min
    while len(windows) < 6:
        train_end = start + pd.Timedelta(days=WF_TRAIN_DAYS)
        test_end  = train_end + pd.Timedelta(days=WF_TEST_DAYS)
        if test_end > date_max:
            break
        windows.append({
            "window":      len(windows) + 1,
            "train_start": start,
            "train_end":   train_end,
            "test_start":  train_end,
            "test_end":    test_end,
        })
        start = start + pd.Timedelta(days=WF_TEST_DAYS)
    return windows


# =============================================================================
# 5. 포트폴리오 PnL 합산 (자금 배분 방식 적용)
# =============================================================================

def _compute_portfolio_metrics(monthly_pnl: pd.Series) -> dict:
    """월별 PnL Series → 통계 지표."""
    if len(monthly_pnl) == 0:
        return {k: np.nan for k in [
            "total_return", "ann_return", "sharpe", "calmar", "sortino",
            "mdd", "monthly_mean", "monthly_median", "monthly_q1",
            "monthly_q5", "monthly_std", "n_positive_months",
        ]}

    arr = monthly_pnl.values
    eq  = np.cumprod(1 + arr)

    total_return = float(eq[-1] - 1)
    n_months = len(arr)
    ann_return = float((1 + total_return) ** (12 / n_months) - 1) if n_months > 0 else np.nan

    std = arr.std()
    sharpe = float(arr.mean() / std * np.sqrt(12)) if std > 0 else np.nan

    # MDD
    running_max = np.maximum.accumulate(eq)
    dd = (eq - running_max) / running_max
    mdd = float(dd.min())

    calmar = float(ann_return / abs(mdd)) if (mdd < 0 and not np.isnan(ann_return)) else np.nan

    # Sortino (downside std)
    neg = arr[arr < 0]
    down_std = neg.std() if len(neg) > 1 else np.nan
    sortino = float(arr.mean() / down_std * np.sqrt(12)) if (down_std and down_std > 0) else np.nan

    return {
        "total_return":       round(total_return, 4),
        "ann_return":         round(ann_return,   4) if not np.isnan(ann_return) else np.nan,
        "sharpe":             round(sharpe,        4) if not np.isnan(sharpe)    else np.nan,
        "calmar":             round(calmar,         4) if not np.isnan(calmar)   else np.nan,
        "sortino":            round(sortino,        4) if not np.isnan(sortino)  else np.nan,
        "mdd":                round(mdd,            4),
        "monthly_mean":       round(float(arr.mean()),             4),
        "monthly_median":     round(float(np.median(arr)),         4),
        "monthly_q1":         round(float(np.percentile(arr, 25)), 4),
        "monthly_q5":         round(float(np.percentile(arr, 5)),  4),
        "monthly_std":        round(float(std),                    4),
        "n_positive_months":  int((arr > 0).sum()),
    }


def portfolio_pnl_from_weights(
    top_triples: pd.DataFrame,
    pnl_series: dict,
    weights: dict,   # triple_id → weight (합계 1)
    date_filter=None,  # (start, end) pd.Timestamp
) -> pd.Series:
    """
    가중 합산 → 일별 포트폴리오 PnL.
    date_filter = (start, end) — inclusive start, exclusive end.
    """
    all_dates = sorted(set().union(*[
        s.index for tid, s in pnl_series.items()
        if len(s) > 0 and tid in weights
    ]))
    if not all_dates:
        return pd.Series(dtype=float)

    port = pd.Series(0.0, index=all_dates)
    for tid, w in weights.items():
        if tid not in pnl_series or len(pnl_series[tid]) == 0:
            continue
        s = pnl_series[tid].reindex(all_dates, fill_value=0.0)
        port += s * w

    if date_filter is not None:
        start, end = date_filter
        port = port[(port.index >= start) & (port.index < end)]

    return port


def daily_to_monthly(daily: pd.Series) -> pd.Series:
    """일별 PnL → 월별 복리 수익률."""
    if len(daily) == 0:
        return pd.Series(dtype=float)
    # PnL을 수익률로 취급, 복리 합산
    monthly = daily.groupby([daily.index.year, daily.index.month]).apply(
        lambda x: float(np.prod(1 + x) - 1)
    )
    return monthly


def compute_weights(
    top_triples: pd.DataFrame,
    pnl_series: dict,
    method: str,   # "A", "B", "C"
    train_start: pd.Timestamp = None,
    train_end:   pd.Timestamp = None,
) -> dict:
    """
    3가지 자금 배분 방식.
    A: 동일 가중
    B: Sharpe 가중 (train 기간 Sharpe 비례)
    C: 국면별 고정 비중 (ALLOC_C) + 국면 내 동일 가중
    """
    tids = top_triples["triple_id"].tolist()

    if method == "A":
        n = len(tids)
        return {tid: 1.0 / n for tid in tids}

    elif method == "B":
        sharpe_map = {}
        for tid in tids:
            s = pnl_series.get(tid, pd.Series(dtype=float))
            if train_start is not None and len(s) > 0:
                s = s[(s.index >= train_start) & (s.index < train_end)]
            if len(s) < 10:
                sharpe_map[tid] = 0.0
                continue
            arr = s.values
            std = arr.std()
            sharpe_map[tid] = float(arr.mean() / std * np.sqrt(252)) if std > 0 else 0.0

        total_pos = sum(max(v, 0) for v in sharpe_map.values())
        if total_pos == 0:
            # fallback to equal
            n = len(tids)
            return {tid: 1.0 / n for tid in tids}
        return {tid: max(sharpe_map[tid], 0) / total_pos for tid in tids}

    elif method == "C":
        # 국면별 합계 = ALLOC_C 비중, 국면 내 동일 가중
        regime_groups = {}
        for _, row in top_triples.iterrows():
            r = row["regime"]
            regime_groups.setdefault(r, []).append(row["triple_id"])

        weights = {}
        for regime, tids_in_regime in regime_groups.items():
            regime_alloc = ALLOC_C.get(regime, 0.0)
            per_triple   = regime_alloc / len(tids_in_regime)
            for tid in tids_in_regime:
                weights[tid] = per_triple

        # 정규화 (합=1)
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        return weights

    else:
        raise ValueError(f"Unknown method: {method}")


# =============================================================================
# 6. Walk-Forward 실행
# =============================================================================

def run_walkforward(
    top_triples: pd.DataFrame,
    pnl_series: dict,
    windows: list,
) -> pd.DataFrame:
    """
    6 윈도우 × 3 자금 배분 방식 → 결과 DataFrame.
    """
    rows = []
    for w in windows:
        wn    = w["window"]
        ts    = w["train_start"]
        te    = w["train_end"]
        ts2   = w["test_start"]
        te2   = w["test_end"]
        print(f"  Window {wn}: train={ts.date()}~{te.date()}, test={ts2.date()}~{te2.date()}")

        for method in ["A", "B", "C"]:
            weights = compute_weights(top_triples, pnl_series, method, ts, te)

            test_daily = portfolio_pnl_from_weights(
                top_triples, pnl_series, weights,
                date_filter=(ts2, te2),
            )

            test_monthly = daily_to_monthly(test_daily)
            metrics = _compute_portfolio_metrics(test_monthly)

            row = {
                "window":      wn,
                "method":      method,
                "train_start": ts.date(),
                "train_end":   te.date(),
                "test_start":  ts2.date(),
                "test_end":    te2.date(),
                "n_test_days": len(test_daily),
                "n_test_months": len(test_monthly),
            }
            row.update(metrics)
            rows.append(row)

    df = pd.DataFrame(rows)
    return df


# =============================================================================
# 7. 전체 OOS 합산 통계 (6 윈도우 연결)
# =============================================================================

def compute_oos_combined(
    top_triples: pd.DataFrame,
    pnl_series: dict,
    windows: list,
    method: str,
) -> dict:
    """6 윈도우 OOS를 시계열 연결 → 종합 월별 통계."""
    combined_monthly = []
    for w in windows:
        weights = compute_weights(
            top_triples, pnl_series, method,
            w["train_start"], w["train_end"],
        )
        daily = portfolio_pnl_from_weights(
            top_triples, pnl_series, weights,
            date_filter=(w["test_start"], w["test_end"]),
        )
        monthly = daily_to_monthly(daily)
        combined_monthly.append(monthly)

    if not combined_monthly:
        return {}
    all_monthly = pd.concat(combined_monthly).sort_index()
    metrics = _compute_portfolio_metrics(all_monthly)
    metrics["n_windows"] = len(windows)
    metrics["n_positive_windows"] = sum(
        1 for w in windows
        if _compute_portfolio_metrics(
            daily_to_monthly(
                portfolio_pnl_from_weights(
                    top_triples, pnl_series,
                    compute_weights(top_triples, pnl_series, method,
                                    w["train_start"], w["train_end"]),
                    date_filter=(w["test_start"], w["test_end"]),
                )
            )
        ).get("total_return", -1) > 0
    )
    return metrics, all_monthly


# =============================================================================
# 8. 보고서 생성
# =============================================================================

def _fmt(v, pct=False, decimals=4):
    if pd.isna(v) or v is None:
        return "N/A"
    if pct:
        return f"{v*100:.2f}%"
    return f"{v:.{decimals}f}"


def generate_combo_report(
    top_triples: pd.DataFrame,
    wf_df: pd.DataFrame,
    oos_stats: dict,   # method → (metrics, monthly_series)
):
    lines = [
        "# Phase 3 — 포트폴리오 Walk-Forward 종합 보고서",
        "",
        f"생성일: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"트리플 수: {len(top_triples)}, Walk-Forward 윈도우: {len(wf_df['window'].unique())}",
        "",
        "## 1. 선택된 트리플",
        "",
        "| triple_id | regime | family | params | sl | tp | tm | sharpe | mean_pnl | n |",
        "|-----------|--------|--------|--------|----|----|-----|--------|----------|---|",
    ]
    for _, r in top_triples.iterrows():
        lines.append(
            f"| {r['triple_id']} | {r['regime']} | {r['family']} | {r['params']} "
            f"| {r['sl']:.1%} | {r['tp']:.0%} | {int(r['tm'])}d "
            f"| {_fmt(r['sharpe'])} | {_fmt(r['mean_pnl'])} | {int(r['n'])} |"
        )

    lines += [
        "",
        "## 2. 자금 배분 방식",
        "",
        "| 방식 | 설명 |",
        "|------|------|",
        "| A | 동일 가중 (트리플 수 N으로 균등 분배) |",
        "| B | Sharpe 가중 (train 기간 Sharpe 비례) |",
        f"| C | 국면별 고정: BULL_LV 30% / BULL_HV 30% / BEAR_HV 25% / SW_LV 15% |",
        "",
        "## 3. Walk-Forward 윈도우별 OOS 결과",
        "",
    ]

    for method in ["A", "B", "C"]:
        lines.append(f"### 방식 {method}")
        lines.append("")
        lines.append("| 윈도우 | test 기간 | 월평균 | 월중앙 | 1Q | 5Q | Sharpe | Calmar | MDD | 양수월 |")
        lines.append("|--------|-----------|--------|--------|-----|-----|--------|--------|-----|--------|")
        sub = wf_df[wf_df["method"] == method].sort_values("window")
        for _, row in sub.iterrows():
            lines.append(
                f"| {int(row['window'])} "
                f"| {row['test_start']}~{row['test_end']} "
                f"| {_fmt(row['monthly_mean'], pct=True)} "
                f"| {_fmt(row['monthly_median'], pct=True)} "
                f"| {_fmt(row['monthly_q1'], pct=True)} "
                f"| {_fmt(row['monthly_q5'], pct=True)} "
                f"| {_fmt(row['sharpe'])} "
                f"| {_fmt(row['calmar'])} "
                f"| {_fmt(row['mdd'], pct=True)} "
                f"| {int(row['n_positive_months']) if pd.notna(row['n_positive_months']) else 'N/A'} |"
            )
        lines.append("")

    lines += [
        "## 4. 6-윈도우 OOS 연결 종합 통계",
        "",
        "| 방식 | 연환산 | Sharpe | Calmar | MDD | 월평균 | 월중앙 | 1Q | 5Q | 양수윈도우 |",
        "|------|--------|--------|--------|-----|--------|--------|-----|-----|-----------|",
    ]
    for method in ["A", "B", "C"]:
        if method not in oos_stats:
            continue
        m, _ = oos_stats[method]
        lines.append(
            f"| {method} "
            f"| {_fmt(m.get('ann_return'), pct=True)} "
            f"| {_fmt(m.get('sharpe'))} "
            f"| {_fmt(m.get('calmar'))} "
            f"| {_fmt(m.get('mdd'), pct=True)} "
            f"| {_fmt(m.get('monthly_mean'), pct=True)} "
            f"| {_fmt(m.get('monthly_median'), pct=True)} "
            f"| {_fmt(m.get('monthly_q1'), pct=True)} "
            f"| {_fmt(m.get('monthly_q5'), pct=True)} "
            f"| {m.get('n_positive_windows', 'N/A')}/{m.get('n_windows', 'N/A')} |"
        )

    lines += [
        "",
        "## 5. 월 수익률 분포 (최우수 방식 상세)",
        "",
    ]

    # 최우수 방식 = Sharpe 기준
    best_method = None
    best_sharpe = -999
    for method in ["A", "B", "C"]:
        if method in oos_stats:
            s = oos_stats[method][0].get("sharpe", np.nan)
            if pd.notna(s) and s > best_sharpe:
                best_sharpe = s
                best_method = method

    if best_method and best_method in oos_stats:
        _, monthly_s = oos_stats[best_method]
        lines.append(f"**최우수 방식: {best_method} (Sharpe {best_sharpe:.3f})**")
        lines.append("")
        lines.append("| 연도-월 | 월수익률 |")
        lines.append("|---------|---------|")
        for idx, v in monthly_s.items():
            year, month = idx
            lines.append(f"| {year}-{month:02d} | {v*100:.2f}% |")
        lines.append("")

    with open(OUT_COMBO, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Combo 보고서 → {OUT_COMBO}")


def generate_summary_report(
    top_triples: pd.DataFrame,
    wf_df: pd.DataFrame,
    oos_stats: dict,
    corr_df: pd.DataFrame,
    windows: list,
):
    # 최우수 방식
    best_method = None
    best_sharpe = -999
    for method in ["A", "B", "C"]:
        if method in oos_stats:
            s = oos_stats[method][0].get("sharpe", np.nan)
            if pd.notna(s) and s > best_sharpe:
                best_sharpe = s
                best_method = method

    best_m = oos_stats[best_method][0] if best_method else {}
    best_monthly = oos_stats[best_method][1] if best_method else pd.Series(dtype=float)

    # 월 10% 도달 판정
    ann_return = best_m.get("ann_return", np.nan)
    monthly_mean = best_m.get("monthly_mean", np.nan)
    monthly_median = best_m.get("monthly_median", np.nan)
    mdd = best_m.get("mdd", np.nan)

    # 정직 판정
    if pd.notna(monthly_mean):
        if monthly_mean >= 0.10:
            verdict = "도달 (월평균 >= 10%)"
            verdict_detail = f"월평균 {monthly_mean*100:.2f}% — 목표 충족"
        elif monthly_mean >= 0.05:
            verdict = "부분 도달 (월평균 5~10%)"
            verdict_detail = f"월평균 {monthly_mean*100:.2f}% — 목표 미달, 방향성 OK"
        else:
            verdict = "미달 (월평균 < 5%)"
            verdict_detail = f"월평균 {monthly_mean*100:.2f}% — 시그널 강도 또는 종목 수 부족"
    else:
        verdict = "데이터 부족"
        verdict_detail = "유효 시그널 없음"

    # 최악 윈도우
    worst_row = None
    worst_ret = 999
    for method_check in ["A", "B", "C"]:
        sub = wf_df[wf_df["method"] == method_check]
        for _, r in sub.iterrows():
            if pd.notna(r["total_return"]) and r["total_return"] < worst_ret:
                worst_ret = r["total_return"]
                worst_row = r
                worst_row_method = method_check

    # 상관관계 요약
    if len(corr_df) > 0 and "pearson_corr" in corr_df.columns:
        avg_corr = corr_df["pearson_corr"].mean()
        high_corr = (corr_df["pearson_corr"].abs() > 0.7).sum()
    else:
        avg_corr = np.nan
        high_corr = 0

    lines = [
        "# Phase 3 요약 — 사장님 판단용 한 장 보고서",
        "",
        f"생성일: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## 처리 요약",
        f"- 분석 트리플 수: **{len(top_triples)}개** (swing, 4개 국면)",
        f"- Walk-Forward 윈도우: **{len(windows)}개**",
        f"- 자금 배분 방식: A(동일), B(Sharpe가중), C(국면별고정)",
        "",
        "## 트리플 간 상관관계",
        f"- 평균 Pearson 상관계수: {_fmt(avg_corr)}",
        f"- 고상관 쌍 (|r|>0.7): {high_corr}쌍",
        ("- 해석: 상관 낮을수록 포트폴리오 분산 효과 있음" if pd.notna(avg_corr) else ""),
        "",
        "## 6-윈도우 OOS 종합 (최우수 방식)",
        f"- 최우수 방식: **방식 {best_method}** (Sharpe {best_sharpe:.3f})" if best_method else "- 유효 방식 없음",
        f"- 연환산 수익률: **{_fmt(ann_return, pct=True)}**",
        f"- Sharpe: {_fmt(best_m.get('sharpe'))} / Calmar: {_fmt(best_m.get('calmar'))} / Sortino: {_fmt(best_m.get('sortino'))}",
        f"- MDD: {_fmt(mdd, pct=True)}",
        "",
        "## 월 수익률 분포",
        f"- 평균: **{_fmt(monthly_mean, pct=True)}**",
        f"- 중앙값: {_fmt(monthly_median, pct=True)}",
        f"- 1분위 (Q1): {_fmt(best_m.get('monthly_q1'), pct=True)}",
        f"- 5분위 (worst 5%): {_fmt(best_m.get('monthly_q5'), pct=True)}",
        f"- 표준편차: {_fmt(best_m.get('monthly_std'), pct=True)}",
        f"- 양수 월 비율: {best_m.get('n_positive_months', 'N/A')}/{len(best_monthly)} ({(best_m.get('n_positive_months',0)/len(best_monthly)*100 if len(best_monthly)>0 else 0):.0f}%)",
        "",
        "## Walk-Forward 일관성",
        f"- 양수 윈도우: {best_m.get('n_positive_windows', 'N/A')}/{best_m.get('n_windows', 'N/A')}",
    ]

    if worst_row is not None:
        lines += [
            f"- 최악 윈도우: 방식 {worst_row_method}, {worst_row['test_start']}~{worst_row['test_end']}",
            f"  → OOS 수익: {_fmt(float(worst_row['total_return']), pct=True)}",
            f"  → MDD: {_fmt(float(worst_row['mdd']), pct=True)}",
        ]

    lines += [
        "",
        "---",
        "",
        "## 월 10% 도달 여부 — 정직 판정",
        f"**{verdict}**",
        f"{verdict_detail}",
        "",
    ]

    if pd.notna(monthly_mean) and monthly_mean < 0.10:
        lines += [
            "### 부족한 영역",
            "- 월 10% 달성에는 더 강한 시그널 또는 레버리지 필요",
            f"- 현재 월평균 {monthly_mean*100:.2f}% = 연환산 약 {(1+monthly_mean)**12-1:.1%}",
        ]
        if pd.notna(mdd) and abs(mdd) > 0.15:
            lines.append(f"- MDD {mdd*100:.1f}% → 리스크 대비 수익 추가 개선 필요")

    # P4 진입 권장
    p4_ok = (
        pd.notna(best_m.get("sharpe")) and best_m["sharpe"] > 0.5 and
        pd.notna(best_m.get("n_positive_windows")) and
        best_m["n_positive_windows"] >= 4 and
        pd.notna(mdd) and mdd > -0.30
    )

    lines += [
        "",
        "## P4 Paper 진입 권장",
        f"**{'OK' if p4_ok else 'NG'}**",
    ]
    if p4_ok:
        lines.append(f"- 이유: Sharpe {best_sharpe:.2f} > 0.5, 양수 윈도우 {best_m.get('n_positive_windows')}/{best_m.get('n_windows')}, MDD {mdd*100:.1f}% < 30%")
    else:
        lines.append("- 이유: Sharpe 또는 윈도우 일관성 기준 미달 → 시그널/파라미터 재검토 권장")

    with open(OUT_SUM, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  요약 보고서 → {OUT_SUM}")


# =============================================================================
# 메인
# =============================================================================

def main():
    t_global = time.time()
    print("=" * 70)
    print("P3 포트폴리오 Walk-Forward — 시작")
    print("=" * 70)

    # ── [1] 입력 로드 ─────────────────────────────────────────────────────────
    print("\n[1/7] 입력 파일 로드")
    triples_df = pd.read_csv(os.path.join(REPORT_DIR, "phase2c_exit_passed.csv"))
    print(f"  합격 트리플: {len(triples_df)}개")

    print("\n[2/7] DB + 피처 계산 (p2b 재사용)")
    filters_df, fwd, seg, prices = load_data()

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

    prices_pivot = build_prices_pivot(prices)

    # ── [2] 트리플 선택 ───────────────────────────────────────────────────────
    print("\n[3/7] 트리플 선택 (swing × 4 regime × Top 5)")
    top_triples = select_top_triples(triples_df)

    # ── [3] fn_map + pool_map ─────────────────────────────────────────────────
    print("\n[4/7] 시그널 카탈로그 + pool 빌드")
    catalog  = build_signal_catalog()
    fn_map   = build_signal_fn_map(catalog)
    pools    = build_universe_pools(filters_df, TOP_N_PER_REGIME)
    pool_map = {(p["regime"], p["pool_rank"]): p for p in pools}

    # ── [4] 일별 PnL 시계열 ───────────────────────────────────────────────────
    print("\n[5/7] 트리플별 일별 PnL 시계열")
    pnl_series = extract_triple_daily_pnl(
        top_triples, merged, prices_pivot, fn_map, pool_map
    )

    # 상관관계
    print("  상관관계 계산...")
    corr_df = compute_triple_correlation(top_triples, pnl_series)
    corr_df.to_csv(OUT_CORR, index=False)
    print(f"  상관관계 → {OUT_CORR}")
    if len(corr_df) > 0 and "pearson_corr" in corr_df.columns:
        valid_corr = corr_df["pearson_corr"].dropna()
        print(f"  Pearson 상관계수 평균: {valid_corr.mean():.3f}, 최대: {valid_corr.abs().max():.3f}")

    # ── [5] Walk-Forward ──────────────────────────────────────────────────────
    print("\n[6/7] Walk-Forward 6-윈도우")
    date_min = prices["date"].min()
    date_max = prices["date"].max()
    windows  = build_wf_windows(date_min, date_max)
    print(f"  윈도우 수: {len(windows)}")

    wf_df = run_walkforward(top_triples, pnl_series, windows)
    wf_df.to_csv(OUT_WF, index=False)
    print(f"  Walk-Forward 결과 → {OUT_WF}")

    # ── [6] OOS 연결 통계 ─────────────────────────────────────────────────────
    print("\n[7/7] OOS 종합 통계 + 보고서 생성")
    oos_stats = {}
    for method in ["A", "B", "C"]:
        result = compute_oos_combined(top_triples, pnl_series, windows, method)
        if isinstance(result, tuple):
            oos_stats[method] = result
        print(f"  방식 {method}: 연환산 {_fmt(oos_stats.get(method, ({},))[0].get('ann_return') if method in oos_stats else None, pct=True)}, "
              f"Sharpe {_fmt(oos_stats.get(method, ({},))[0].get('sharpe') if method in oos_stats else None)}")

    generate_combo_report(top_triples, wf_df, oos_stats)
    generate_summary_report(top_triples, wf_df, oos_stats, corr_df, windows)

    # ── 콘솔 최종 요약 ────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("최종 요약")
    print("=" * 70)
    print(f"트리플 수: {len(top_triples)}, 윈도우 수: {len(windows)}")
    print()
    for method in ["A", "B", "C"]:
        if method not in oos_stats:
            continue
        m, monthly_s = oos_stats[method]
        print(f"방식 {method}: 연환산={_fmt(m.get('ann_return'), pct=True)}, "
              f"Sharpe={_fmt(m.get('sharpe'))}, Calmar={_fmt(m.get('calmar'))}, "
              f"MDD={_fmt(m.get('mdd'), pct=True)}")
        print(f"       월평균={_fmt(m.get('monthly_mean'), pct=True)}, "
              f"중앙={_fmt(m.get('monthly_median'), pct=True)}, "
              f"1Q={_fmt(m.get('monthly_q1'), pct=True)}, "
              f"5Q={_fmt(m.get('monthly_q5'), pct=True)}")
        print(f"       양수윈도우={m.get('n_positive_windows')}/{m.get('n_windows')}")
        print()

    print(f"소요: {(time.time()-t_global)/60:.1f}분")
    print("완료!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[중단] Ctrl+C 감지.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] {e}")
        traceback.print_exc()
        sys.exit(1)
