"""
P1 Forward Return Baseline + 90-Cell Matrix
============================================
마스터 계획: C:/Users/sttgp/.claude/plans/10-purrfect-ritchie.md

산출물:
  1. reports/10pct_strategy/phase1_stocks_pit_meta.parquet
  2. reports/10pct_strategy/phase1_forward_returns.parquet
  3. reports/10pct_strategy/phase1_baseline_stats.csv
  4. reports/10pct_strategy/phase1_base_rate_matrix.csv
  5. reports/10pct_strategy/phase1_base_rate_matrix.md
"""

from __future__ import annotations

import sys
import os
import warnings
import time

import psycopg2
import pandas as pd
import numpy as np

# PIT helpers (forward_return, pit_quantile)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from lib.pit_helpers import forward_return, pit_quantile, FutureLeakWarning

# suppress FutureLeakWarning — this is EDA, not signal code
warnings.filterwarnings("ignore", category=FutureLeakWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUT_DIR = os.path.join(PROJECT_ROOT, "reports", "10pct_strategy")
os.makedirs(OUT_DIR, exist_ok=True)

DB_QUANT = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="robotrader_quant")
DB_STRAT = dict(host="127.0.0.1", port=5433, user="postgres",    password="1234", dbname="strategy_analysis")

FWD_WINDOWS = [1, 3, 5, 10, 20, 30, 60]

# ---------------------------------------------------------------------------
# Step 1: Load daily_prices (손상 날짜 필터)
# ---------------------------------------------------------------------------
print("[1/9] Loading daily_prices from robotrader_quant ...")
t0 = time.time()

conn = psycopg2.connect(**DB_QUANT)
query = """
    SELECT stock_code,
           date::date  AS date,
           close,
           adj_factor,
           market_cap
    FROM daily_prices
    WHERE date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      AND stock_code ~ '^[0-9]{6}$'
    ORDER BY stock_code, date
"""
df = pd.read_sql(query, conn)
conn.close()

print(f"    Loaded {len(df):,} rows, {df['stock_code'].nunique():,} stocks  [{time.time()-t0:.1f}s]")

# Ensure correct dtypes
df["date"] = pd.to_datetime(df["date"])
df["close"] = pd.to_numeric(df["close"], errors="coerce")
df["adj_factor"] = pd.to_numeric(df["adj_factor"], errors="coerce").fillna(1.0)
df["market_cap"] = pd.to_numeric(df["market_cap"], errors="coerce")

# Drop rows where close is null or zero (can't compute returns)
df = df[df["close"].notna() & (df["close"] > 0)].copy()
df = df.sort_values(["stock_code", "date"]).reset_index(drop=True)
print(f"    After quality filter: {len(df):,} rows")

# ---------------------------------------------------------------------------
# Step 2: adj_close
# ---------------------------------------------------------------------------
print("[2/9] Computing adj_close ...")
df["adj_close"] = df["close"] / df["adj_factor"]

# ---------------------------------------------------------------------------
# Step 3: Universe PIT meta
# ---------------------------------------------------------------------------
print("[3/9] Building PIT meta ...")
pit_meta = (
    df.groupby("stock_code")["date"]
    .agg(first_date="min", last_date="max", n_days="count")
    .reset_index()
)
pit_meta["first_date"] = pit_meta["first_date"].dt.date
pit_meta["last_date"]  = pit_meta["last_date"].dt.date

out_meta = os.path.join(OUT_DIR, "phase1_stocks_pit_meta.parquet")
pit_meta.to_parquet(out_meta, index=False)
print(f"    PIT meta: {len(pit_meta):,} stocks -> {out_meta}")

# first_date distribution summary
fd = pd.to_datetime(pit_meta["first_date"])
print(f"    first_date: min={fd.min().date()}, max={fd.max().date()}")
print(f"    first_date <= 2022-01-01: {(fd <= '2022-01-01').sum():,} stocks")
print(f"    n_days median: {pit_meta['n_days'].median():.0f}, mean: {pit_meta['n_days'].mean():.0f}")

# ---------------------------------------------------------------------------
# Step 4: Forward returns (PIT helper)
# ---------------------------------------------------------------------------
print("[4/9] Computing forward returns ...")
t1 = time.time()
for n in FWD_WINDOWS:
    df[f"fwd_{n}d"] = forward_return(df, "adj_close", n_days=n, group_col="stock_code")
    print(f"    fwd_{n}d computed")
print(f"    All forward returns done [{time.time()-t1:.1f}s]")

# ---------------------------------------------------------------------------
# Step 5: Save forward returns parquet
# ---------------------------------------------------------------------------
print("[5/9] Saving forward_returns parquet ...")
fwd_cols = ["stock_code", "date"] + [f"fwd_{n}d" for n in FWD_WINDOWS]
out_fwd = os.path.join(OUT_DIR, "phase1_forward_returns.parquet")
df[fwd_cols].to_parquet(out_fwd, index=False)

# Missingness report
print(f"    Rows: {len(df[fwd_cols]):,}")
for c in [f"fwd_{n}d" for n in FWD_WINDOWS]:
    miss_pct = df[c].isna().mean() * 100
    print(f"      {c}: {miss_pct:.1f}% missing")
print(f"    -> {out_fwd}")

# ---------------------------------------------------------------------------
# Step 6: 3-bucket baseline stats
# ---------------------------------------------------------------------------
print("[6/9] Computing 3-bucket baseline stats ...")

df["swing"]    = df[["fwd_1d",  "fwd_3d",  "fwd_5d"]].mean(axis=1)
df["mid"]      = df[["fwd_10d", "fwd_20d", "fwd_30d"]].mean(axis=1)
df["position"] = df[["fwd_30d", "fwd_60d"]].mean(axis=1)

stats_rows = []
for bucket in ["swing", "mid", "position"]:
    s = df[bucket].dropna()
    stats_rows.append({
        "bucket":      bucket,
        "mean":        s.mean(),
        "median":      s.median(),
        "std":         s.std(),
        "sharpe_252":  s.mean() / s.std() * (252 ** 0.5) if s.std() > 0 else np.nan,
        "win_rate":    (s > 0).mean(),
        "n":           len(s),
    })

stats_df = pd.DataFrame(stats_rows).set_index("bucket")
out_stats = os.path.join(OUT_DIR, "phase1_baseline_stats.csv")
stats_df.to_csv(out_stats)
print(stats_df.to_string())
print(f"    -> {out_stats}")

# ---------------------------------------------------------------------------
# Step 7: Market cap quintile (PIT cross-section)
# ---------------------------------------------------------------------------
print("[7/9] Computing market_cap quintile (PIT) ...")
# pit_quantile uses date-level cross-section (no look-ahead)
df["mcap_quintile"] = pit_quantile(df, "market_cap", "date", n_bins=5)
# NaN market_cap -> quintile NaN; label as "NA"
df["mcap_quintile"] = df["mcap_quintile"].astype("object")
df.loc[df["mcap_quintile"].isna(), "mcap_quintile"] = "NA"
print(f"    mcap_quintile distribution:\n{df['mcap_quintile'].value_counts(dropna=False)}")

# ---------------------------------------------------------------------------
# Step 8: Load market_regime and derive 6-segment label
# ---------------------------------------------------------------------------
print("[8/9] Loading market_regime from strategy_analysis ...")
conn2 = psycopg2.connect(**DB_STRAT)
regime = pd.read_sql(
    """
    SELECT date, regime, regime_score
    FROM market_regime
    WHERE index_code = 'KOSPI' AND method = 'rolling'
    ORDER BY date
    """,
    conn2,
)
conn2.close()

regime["date"] = pd.to_datetime(regime["date"])
print(f"    market_regime: {len(regime):,} rows, regimes: {regime['regime'].unique().tolist()}")

# Derive volatility quintile from regime_score within each regime
# (regime_score is a continuous score; we cut it into high/low within each regime)
# Strategy: 3 regime labels × 2 volatility levels = 6 segments
regime["vol_level"] = pd.qcut(
    regime["regime_score"].rank(method="first"),
    q=2,
    labels=["low_vol", "high_vol"],
)
regime["regime_6seg"] = regime["regime"].astype(str) + "_" + regime["vol_level"].astype(str)

# Merge regime into df
df = df.merge(
    regime[["date", "regime", "regime_score", "regime_6seg"]],
    on="date",
    how="left",
)
print(f"    After regime merge: {df['regime'].isna().sum():,} rows with no regime (outside KOSPI dates)")
print(f"    regime_6seg value counts:\n{df['regime_6seg'].value_counts()}")

# ---------------------------------------------------------------------------
# Step 9: 90-cell matrix (regime_6seg × mcap_quintile × bucket)
# ---------------------------------------------------------------------------
print("[9/9] Building 90-cell matrix ...")

matrix_rows = []
for bucket in ["swing", "mid", "position"]:
    grp = (
        df[df["regime_6seg"].notna() & (df["mcap_quintile"] != "NA")]
        .groupby(["regime_6seg", "mcap_quintile"])[bucket]
    )
    for (regime_label, mcap_q), s in grp:
        s_clean = s.dropna()
        if len(s_clean) < 10:
            continue
        matrix_rows.append({
            "regime_label":  regime_label,
            "mcap_quintile": mcap_q,
            "bucket":        bucket,
            "mean":          s_clean.mean(),
            "median":        s_clean.median(),
            "std":           s_clean.std(),
            "win_rate":      (s_clean > 0).mean(),
            "n":             len(s_clean),
        })

matrix_df = pd.DataFrame(matrix_rows)
matrix_df = matrix_df.sort_values("mean", ascending=False).reset_index(drop=True)

out_matrix_csv = os.path.join(OUT_DIR, "phase1_base_rate_matrix.csv")
matrix_df.to_csv(out_matrix_csv, index=False)
print(f"    Matrix cells: {len(matrix_df)} -> {out_matrix_csv}")

# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------
top5 = matrix_df.head(5)
bottom5 = matrix_df.tail(5)

# Bucket baseline table for markdown
baseline_md = stats_df[["mean", "sharpe_252", "win_rate", "n"]].copy()
baseline_md["mean_%"]    = (baseline_md["mean"] * 100).map("{:.3f}%".format)
baseline_md["sharpe_252"] = baseline_md["sharpe_252"].map("{:.3f}".format)
baseline_md["win_rate_%"] = (baseline_md["win_rate"] * 100).map("{:.1f}%".format)
baseline_md["n"]          = baseline_md["n"].map("{:,.0f}".format)

md_lines = [
    "# Phase 1 — Forward Return Baseline & 90-Cell Matrix",
    "",
    f"생성일: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
    "",
    "## 1. Universe PIT Meta",
    "",
    f"- 총 종목 수: **{len(pit_meta):,}**",
    f"- first_date 범위: {fd.min().date()} ~ {fd.max().date()}",
    f"- first_date ≤ 2022-01-01 (충분한 히스토리): **{(fd <= '2022-01-01').sum():,}** 종목",
    f"- n_days 중앙값: {pit_meta['n_days'].median():.0f}일, 평균: {pit_meta['n_days'].mean():.0f}일",
    "",
    "## 2. Forward Returns 파켓",
    "",
    f"- 총 행 수: **{len(df[fwd_cols]):,}**",
    "- 컬럼별 결측률:",
    "",
]
for c in [f"fwd_{n}d" for n in FWD_WINDOWS]:
    miss_pct = df[c].isna().mean() * 100
    md_lines.append(f"  - {c}: {miss_pct:.1f}%")

md_lines += [
    "",
    "## 3. 3-버킷 베이스라인 통계",
    "",
    "| Bucket | Mean (%) | Sharpe×√252 | Win Rate | N |",
    "|--------|----------|-------------|----------|---|",
]
for bucket in ["swing", "mid", "position"]:
    row = stats_df.loc[bucket]
    md_lines.append(
        f"| {bucket} | {row['mean']*100:.3f}% | {row['sharpe_252']:.3f} "
        f"| {row['win_rate']*100:.1f}% | {int(row['n']):,} |"
    )

md_lines += [
    "",
    "## 4. 90-Cell Matrix — Top 5 셀 (mean forward return 기준)",
    "",
    "| Regime | McapQ | Bucket | Mean (%) | Win Rate | N |",
    "|--------|-------|--------|----------|----------|---|",
]
for _, r in top5.iterrows():
    md_lines.append(
        f"| {r['regime_label']} | Q{r['mcap_quintile']} | {r['bucket']} "
        f"| {r['mean']*100:.3f}% | {r['win_rate']*100:.1f}% | {int(r['n']):,} |"
    )

md_lines += [
    "",
    "### Bottom 5 셀 (참고)",
    "",
    "| Regime | McapQ | Bucket | Mean (%) | Win Rate | N |",
    "|--------|-------|--------|----------|----------|---|",
]
for _, r in bottom5.iterrows():
    md_lines.append(
        f"| {r['regime_label']} | Q{r['mcap_quintile']} | {r['bucket']} "
        f"| {r['mean']*100:.3f}% | {r['win_rate']*100:.1f}% | {int(r['n']):,} |"
    )

# P2 readiness check
swing_sharpe = stats_df.loc["swing", "sharpe_252"]
swing_win    = stats_df.loc["swing", "win_rate"]
p2_ok = (swing_sharpe > 0.05) and (len(matrix_df) >= 30)

md_lines += [
    "",
    "## 5. P2 Stage A 진입 가능 여부",
    "",
    f"- swing Sharpe×√252: {swing_sharpe:.3f}",
    f"- 매트릭스 셀 수: {len(matrix_df)}",
    f"- **P2 진입: {'OK' if p2_ok else 'NG'}**",
    "",
    "---",
    "_자동 생성: p1_forward_return_matrix.py_",
]

md_text = "\n".join(md_lines)
out_md = os.path.join(OUT_DIR, "phase1_base_rate_matrix.md")
with open(out_md, "w", encoding="utf-8") as f:
    f.write(md_text)
print(f"    -> {out_md}")

# ---------------------------------------------------------------------------
# Final summary print
# ---------------------------------------------------------------------------
print("\n" + "="*60)
print("P1 COMPLETE — Summary")
print("="*60)
print(f"Universe: {len(pit_meta):,} stocks  |  Rows: {len(df):,}")
print()
print("3-Bucket Baseline:")
for bucket in ["swing", "mid", "position"]:
    row = stats_df.loc[bucket]
    print(f"  {bucket:10s}  mean={row['mean']*100:.3f}%  sharpe={row['sharpe_252']:.3f}  winrate={row['win_rate']*100:.1f}%  n={int(row['n']):,}")
print()
print("Top 5 Matrix Cells:")
for _, r in top5.iterrows():
    print(f"  {r['regime_label']:25s} Q{r['mcap_quintile']} {r['bucket']:8s}  mean={r['mean']*100:.3f}%  wr={r['win_rate']*100:.1f}%  n={int(r['n']):,}")
print()
print(f"P2 진입: {'OK' if p2_ok else 'NG'}")
print("="*60)
