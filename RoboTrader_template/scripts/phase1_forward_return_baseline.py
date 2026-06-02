"""
Phase 1 — Forward Return 베이스라인 + 90셀 매트릭스
=======================================================
산출물:
  reports/10pct_strategy/phase1_stocks_pit_meta.parquet
  reports/10pct_strategy/phase1_forward_returns.parquet
  reports/10pct_strategy/phase1_baseline_stats.csv
  reports/10pct_strategy/phase1_baseline_stats.md
  reports/10pct_strategy/phase1_base_rate_matrix.csv
  reports/10pct_strategy/phase1_base_rate_matrix.md

대원칙:
  ① No Look-Ahead PIT — universe 가용성은 T 시점 기준
  ② forward_return() 사용 시 FutureLeakWarning 정상 (평가 전용)
"""

from __future__ import annotations

import io
import os
import sys
import warnings
from pathlib import Path

# Windows cp949 콘솔에서 유니코드 출력 강제
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import psycopg2

# ── 경로 설정 ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]        # RoboTrader_template/
sys.path.insert(0, str(ROOT))

from lib.pit_helpers import forward_return, pit_quantile, FutureLeakWarning  # noqa: E402

REPORT_DIR = ROOT / "reports" / "10pct_strategy"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── DB 연결 ─────────────────────────────────────────────────────────────────
DB_CFG = dict(
    host="127.0.0.1",
    port=5433,
    dbname="robotrader_quant",
    user="robotrader",
    password="1234",
)


def get_conn():
    return psycopg2.connect(**DB_CFG)


# ── 1. Universe PIT 메타 ────────────────────────────────────────────────────

def build_pit_meta() -> pd.DataFrame:
    print("[1/4] Universe PIT 메타 추출 중...")
    sql = """
        SELECT
            stock_code,
            MIN(date::date) AS first_date,
            MAX(date::date) AS last_date,
            COUNT(*)        AS n_days
        FROM robotrader_quant.daily_prices
        WHERE date ~ '^\\d{4}-\\d{2}-\\d{2}$'
        GROUP BY stock_code
        ORDER BY stock_code
    """
    with get_conn() as conn:
        meta = pd.read_sql(sql, conn)

    meta["first_date"] = pd.to_datetime(meta["first_date"])
    meta["last_date"]  = pd.to_datetime(meta["last_date"])

    out = REPORT_DIR / "phase1_stocks_pit_meta.parquet"
    meta.to_parquet(out, index=False)
    print(f"  → {len(meta):,}종목  저장: {out.name}")
    return meta


# ── 2. Forward Returns ───────────────────────────────────────────────────────

def build_forward_returns() -> pd.DataFrame:
    print("[2/4] Forward Returns 계산 중 (adj_close = close / adj_factor)...")
    sql = """
        SELECT
            stock_code,
            date::date                                   AS date,
            CASE
                WHEN adj_factor IS NOT NULL AND adj_factor <> 0
                THEN close::float / adj_factor::float
                ELSE close::float
            END                                          AS adj_close
        FROM robotrader_quant.daily_prices
        WHERE date ~ '^\\d{4}-\\d{2}-\\d{2}$'
          AND close IS NOT NULL
        ORDER BY stock_code, date
    """
    print("  DB 조회 중 (약 273만 행)...")
    with get_conn() as conn:
        df = pd.read_sql(sql, conn)

    df["date"] = pd.to_datetime(df["date"])
    print(f"  조회 완료: {len(df):,}행, {df['stock_code'].nunique():,}종목")

    # forward return 계산 (FutureLeakWarning 무시 — 평가 전용)
    horizons = [1, 3, 5, 10, 20, 30, 60]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureLeakWarning)
        for n in horizons:
            print(f"  fwd_{n}d 계산...")
            df[f"fwd_{n}d"] = forward_return(df, "adj_close", n_days=n)

    fwd_cols = [f"fwd_{n}d" for n in horizons]
    result = df[["stock_code", "date"] + fwd_cols].copy()

    out = REPORT_DIR / "phase1_forward_returns.parquet"
    result.to_parquet(out, index=False)
    print(f"  → 저장: {out.name}  ({len(result):,}행)")
    return result


# ── 3. 베이스라인 통계 ────────────────────────────────────────────────────────

def trimmed_mean(s: pd.Series, pct: float = 0.05) -> float:
    """양쪽 pct% 제거 후 평균."""
    lo, hi = s.quantile(pct), s.quantile(1 - pct)
    return float(s[(s >= lo) & (s <= hi)].mean())


def bucket_stats(s: pd.Series, label: str) -> dict:
    """단일 버킷 시리즈에 대한 통계."""
    clean = s.dropna()
    n = len(clean)
    if n == 0:
        return {k: np.nan for k in ["label", "mean", "median", "std", "sharpe_annual", "win_rate", "trimmed_mean_5pct", "n"]}
    mean   = clean.mean()
    std    = clean.std()
    sharpe = (mean / std * np.sqrt(252)) if std > 0 else np.nan
    return {
        "label":            label,
        "mean":             round(mean, 6),
        "median":           round(float(clean.median()), 6),
        "std":              round(std, 6),
        "sharpe_annual":    round(sharpe, 4),
        "win_rate":         round((clean > 0).mean(), 4),
        "trimmed_mean_5pct": round(trimmed_mean(clean), 6),
        "n":                n,
    }


def build_baseline_stats(fwd: pd.DataFrame) -> pd.DataFrame:
    print("[3/4] 베이스라인 통계 계산 중...")

    # 3-버킷 평균 수익률
    fwd["bucket_swing"]    = fwd[["fwd_1d", "fwd_3d", "fwd_5d"]].mean(axis=1)
    fwd["bucket_mid"]      = fwd[["fwd_10d", "fwd_20d", "fwd_30d"]].mean(axis=1)
    fwd["bucket_position"] = fwd[["fwd_30d", "fwd_60d"]].mean(axis=1)

    rows = []
    for col, label in [
        ("bucket_swing",    "스윙 (1~5일)"),
        ("bucket_mid",      "미드 (10~30일)"),
        ("bucket_position", "포지션 (30~60일)"),
    ]:
        rows.append(bucket_stats(fwd[col], label))

    stats_df = pd.DataFrame(rows)

    csv_out = REPORT_DIR / "phase1_baseline_stats.csv"
    stats_df.to_csv(csv_out, index=False, encoding="utf-8-sig")

    # 마크다운 보고서
    md_lines = [
        "# Phase 1 — 베이스라인 통계 (Universe 전체)\n",
        "",
        "| 버킷 | 평균 | 중앙값 | 표준편차 | Sharpe(연환산) | 승률 | 트리밍평균(5%) | N |",
        "|------|------|--------|----------|----------------|------|----------------|---|",
    ]
    for _, r in stats_df.iterrows():
        md_lines.append(
            f"| {r['label']} | {r['mean']:.4%} | {r['median']:.4%} | {r['std']:.4%} "
            f"| {r['sharpe_annual']:.3f} | {r['win_rate']:.2%} | {r['trimmed_mean_5pct']:.4%} | {r['n']:,} |"
        )
    md_lines += ["", f"_(계산 기준: {pd.Timestamp.now().date()})_"]

    md_out = REPORT_DIR / "phase1_baseline_stats.md"
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"  → {csv_out.name}, {md_out.name}")
    for _, r in stats_df.iterrows():
        print(f"     {r['label']:20s}  mean={r['mean']:.4%}  sharpe={r['sharpe_annual']:.3f}  win={r['win_rate']:.2%}")

    return fwd  # bucket 컬럼 포함


# ── 4. 90셀 Base Rate 매트릭스 ────────────────────────────────────────────────

def load_regime_map() -> pd.DataFrame:
    """phase0_regime_segments.csv → date별 label_6 매핑 (KOSPI 기준)."""
    seg_path = REPORT_DIR / "phase0_regime_segments.csv"
    seg = pd.read_csv(seg_path)
    seg = seg[seg["index_code"] == "KOSPI"].copy()
    seg["start_date"] = pd.to_datetime(seg["start_date"])
    seg["end_date"]   = pd.to_datetime(seg["end_date"])

    # 날짜 → 국면 매핑 (date range expand)
    rows = []
    for _, row in seg.iterrows():
        dates = pd.date_range(row["start_date"], row["end_date"], freq="D")
        for d in dates:
            rows.append({"date": d, "regime6": row["label_6"]})
    return pd.DataFrame(rows)


def build_base_rate_matrix(fwd: pd.DataFrame) -> pd.DataFrame:
    print("[4/4] 90셀 Base Rate 매트릭스 계산 중...")

    # ── (a) market_cap (PIT: T 시점 값 → T+1 매매 결정에 사용 합법)
    print("  시총 5분위 계산 (pit_quantile)...")
    cap_sql = """
        SELECT stock_code, date::date AS date, market_cap::float AS market_cap
        FROM robotrader_quant.daily_prices
        WHERE date ~ '^\\d{4}-\\d{2}-\\d{2}$'
          AND market_cap IS NOT NULL
        ORDER BY stock_code, date
    """
    with get_conn() as conn:
        cap_df = pd.read_sql(cap_sql, conn)
    cap_df["date"] = pd.to_datetime(cap_df["date"])

    cap_df["cap_q5"] = pit_quantile(cap_df, "market_cap", "date", n_bins=5)
    cap_df = cap_df[["stock_code", "date", "cap_q5"]]

    # ── (b) regime 매핑
    print("  국면 매핑 (phase0_regime_segments)...")
    regime_map = load_regime_map()

    # ── (c) fwd에 결합
    # bucket 컬럼이 없으면 재계산
    if "bucket_swing" not in fwd.columns:
        fwd["bucket_swing"]    = fwd[["fwd_1d", "fwd_3d", "fwd_5d"]].mean(axis=1)
        fwd["bucket_mid"]      = fwd[["fwd_10d", "fwd_20d", "fwd_30d"]].mean(axis=1)
        fwd["bucket_position"] = fwd[["fwd_30d", "fwd_60d"]].mean(axis=1)

    merged = fwd.merge(cap_df, on=["stock_code", "date"], how="left")
    merged = merged.merge(regime_map, on="date", how="left")

    # NaN 국면 처리 (주말/공휴일 → ffill)
    merged = merged.sort_values("date")
    merged["regime6"] = merged["regime6"].ffill()

    # ── (d) 90셀 집계
    buckets = {
        "swing":    "bucket_swing",
        "mid":      "bucket_mid",
        "position": "bucket_position",
    }

    all_rows = []
    for bk_name, bk_col in buckets.items():
        grp = (
            merged.dropna(subset=["regime6", "cap_q5", bk_col])
            .groupby(["regime6", "cap_q5"])[bk_col]
            .agg(
                mean=lambda x: x.mean(),
                std=lambda x: x.std(),
                win_rate=lambda x: (x > 0).mean(),
                n="count",
            )
            .reset_index()
        )
        grp["bucket"] = bk_name
        all_rows.append(grp)

    matrix = pd.concat(all_rows, ignore_index=True)
    matrix["sharpe_annual"] = (matrix["mean"] / matrix["std"] * np.sqrt(252)).round(4)
    matrix["mean"]     = matrix["mean"].round(6)
    matrix["std"]      = matrix["std"].round(6)
    matrix["win_rate"] = matrix["win_rate"].round(4)

    # NaN 셀 확인
    nan_cells = matrix["mean"].isna().sum()
    total_cells = len(matrix)
    expected_cells = 6 * 5 * 3  # 90
    print(f"  총 셀: {total_cells} (목표 90) / NaN mean 셀: {nan_cells}")

    csv_out = REPORT_DIR / "phase1_base_rate_matrix.csv"
    matrix.to_csv(csv_out, index=False, encoding="utf-8-sig")

    # ── 마크다운 요약
    md_lines = [
        "# Phase 1 — 90셀 Base Rate 매트릭스\n",
        "",
        "차원: **국면 6** × **시총 5분위** × **보유 버킷 3** = 90셀  ",
        "(regime6: BULL/BEAR/SIDEWAYS × HIGH/LOW_VOL, cap_q5: Q1=소형~Q5=대형, bucket: swing/mid/position)\n",
        "",
        "| regime6 | cap_q5 | bucket | mean | std | sharpe | win_rate | n |",
        "|---------|--------|--------|------|-----|--------|----------|---|",
    ]
    for _, r in matrix.sort_values(["bucket", "regime6", "cap_q5"]).iterrows():
        md_lines.append(
            f"| {r['regime6']} | Q{int(r['cap_q5'])} | {r['bucket']} "
            f"| {r['mean']:.4%} | {r['std']:.4%} | {r['sharpe_annual']:.3f} "
            f"| {r['win_rate']:.2%} | {int(r['n']):,} |"
        )

    # ── 상위 5셀 (Sharpe 기준)
    top5 = matrix.nlargest(5, "sharpe_annual")
    md_lines += [
        "",
        "## 상위 5셀 (Sharpe 기준)\n",
        "",
        "| 순위 | regime6 | cap_q5 | bucket | mean | sharpe | win_rate | n |",
        "|------|---------|--------|--------|------|--------|----------|---|",
    ]
    for rank, (_, r) in enumerate(top5.iterrows(), 1):
        md_lines.append(
            f"| {rank} | {r['regime6']} | Q{int(r['cap_q5'])} | {r['bucket']} "
            f"| {r['mean']:.4%} | {r['sharpe_annual']:.3f} "
            f"| {r['win_rate']:.2%} | {int(r['n']):,} |"
        )

    md_lines += ["", f"_(계산 기준: {pd.Timestamp.now().date()}, NaN 셀: {nan_cells})_"]

    md_out = REPORT_DIR / "phase1_base_rate_matrix.md"
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"  → {csv_out.name}, {md_out.name}")
    print("\n  [상위 5셀]")
    for _, r in top5.iterrows():
        print(f"    {r['regime6']:20s} Q{int(r['cap_q5'])} {r['bucket']:10s}  mean={r['mean']:.4%}  sharpe={r['sharpe_annual']:.3f}  win={r['win_rate']:.2%}  n={int(r['n']):,}")

    return matrix


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Phase 1 -- Forward Return baseline + 90cell matrix")
    print("=" * 60)

    # 사전 회귀: test_no_lookahead.py
    import subprocess
    test_path = ROOT / "tests" / "test_no_lookahead.py"
    print(f"\n[사전 회귀] pytest {test_path.name}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_path), "-q", "--tb=short"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.returncode != 0:
        print("[FAIL] 사전 회귀 실패 — 중단")
        sys.exit(1)
    print("[PASS] 사전 회귀 통과\n")

    # 1. PIT 메타
    meta = build_pit_meta()
    print(f"  first_date 분포: {meta['first_date'].dt.year.value_counts().sort_index().to_dict()}\n")

    # 2. Forward Returns
    fwd = build_forward_returns()

    # 결측률 요약
    fwd_cols = [f"fwd_{n}d" for n in [1, 3, 5, 10, 20, 30, 60]]
    print("\n  결측률:")
    for c in fwd_cols:
        missing_pct = fwd[c].isna().mean()
        mean_val    = fwd[c].mean()
        print(f"    {c:10s}  결측={missing_pct:.2%}  universe 평균={mean_val:+.4%}")

    # 3. 베이스라인 통계
    fwd = build_baseline_stats(fwd)

    # 4. 90셀 매트릭스
    matrix = build_base_rate_matrix(fwd)

    print("\n" + "=" * 60)
    print("Phase 1 완료")
    print(f"  산출물 디렉토리: {REPORT_DIR}")
    print("=" * 60)

    return meta, fwd, matrix


if __name__ == "__main__":
    main()
