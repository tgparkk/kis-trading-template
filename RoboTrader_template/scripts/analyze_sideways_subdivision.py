"""SIDEWAYS 세분화 — 2026-04 vs 2026-05 fade_vwap 결과 정반대 원인 규명.

KOSPI 일봉으로 두 기간의 드리프트·변동성·5일 모멘텀 분포·ATR 비교.
SIDEWAYS를 3단계 (SIDEWAYS_UP / SIDEWAYS_FLAT / SIDEWAYS_DOWN) 로 세분.
fade_vwap 거래를 세분 라벨에 재매핑.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = logging.getLogger("sideways_subdivision")
KOSPI_CODE = "KS11"
MOMENTUM_WINDOW = 5

PERIODS = {
    "2025-10": ("2025-10-01", "2025-10-31"),
    "2026-04": ("2026-04-01", "2026-04-30"),
    "2026-05": ("2026-05-01", "2026-05-27"),
}


def _load_kospi(start: str, end: str) -> pd.DataFrame:
    from db.connection import DatabaseConnection
    # Convert YYYY-MM-DD to YYYYMMDD for daily_candles
    start_db = start.replace("-", "")
    end_db = end.replace("-", "")
    with DatabaseConnection.get_connection() as conn:
        q = """
            SELECT stck_bsop_date AS date,
                   stck_clpr::float AS close,
                   stck_hgpr::float AS high,
                   stck_lwpr::float AS low,
                   stck_oprc::float AS open
            FROM daily_candles
            WHERE stock_code = %s
              AND stck_bsop_date >= %s
              AND stck_bsop_date <= %s
            ORDER BY stck_bsop_date ASC
        """
        df = pd.read_sql(q, conn, params=(KOSPI_CODE, start_db, end_db))
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    return df


def _summary_per_period(kospi: pd.DataFrame) -> pd.DataFrame:
    """기간별 다중 지표."""
    rows = []
    for period_id, (start, end) in PERIODS.items():
        s = pd.to_datetime(start)
        e = pd.to_datetime(end)
        sub = kospi[(kospi["date"] >= s) & (kospi["date"] <= e)].copy()
        if sub.empty:
            LOG.warning(f"{period_id}: no data")
            continue
        sub["ret_1d"] = sub["close"].pct_change()
        sub["range_pct"] = (sub["high"] - sub["low"]) / sub["close"]
        # 5일 모멘텀 (해당 기간 내 어떤 분포인가)
        sub["mom_5d"] = sub["close"].pct_change(MOMENTUM_WINDOW)

        cum_ret = sub["close"].iloc[-1] / sub["close"].iloc[0] - 1 if len(sub) >= 2 else 0
        rows.append({
            "period": period_id,
            "n_days": len(sub),
            "cum_return_pct": round(cum_ret * 100, 2),
            "avg_daily_return_pct": round(sub["ret_1d"].mean() * 100, 4),
            "vol_daily_pct": round(sub["ret_1d"].std() * 100, 4),
            "avg_range_pct": round(sub["range_pct"].mean() * 100, 4),
            "mom_5d_mean_pct": round(sub["mom_5d"].mean() * 100, 4),
            "mom_5d_median_pct": round(sub["mom_5d"].median() * 100, 4),
            "pos_day_ratio": round((sub["ret_1d"] > 0).mean(), 4),
        })
    return pd.DataFrame(rows)


def _label_subdivided(df: pd.DataFrame) -> pd.DataFrame:
    """SIDEWAYS 5단계 세분화."""
    df = df.copy()
    df["mom_5d"] = df["close"].pct_change(MOMENTUM_WINDOW)
    # Default: SIDEWAYS_FLAT
    df["regime"] = "SIDEWAYS_FLAT"
    # BULL / BEAR boundaries
    df.loc[df["mom_5d"] >= 0.01, "regime"] = "BULL"
    df.loc[df["mom_5d"] <= -0.01, "regime"] = "BEAR"
    # SIDEWAYS 내부 세분
    sw_mask = (df["mom_5d"] > -0.01) & (df["mom_5d"] < 0.01)
    df.loc[sw_mask & (df["mom_5d"] > 0.003), "regime"] = "SIDEWAYS_UP"
    df.loc[sw_mask & (df["mom_5d"] < -0.003), "regime"] = "SIDEWAYS_DOWN"
    # else stays SIDEWAYS_FLAT
    return df


def _map_trades_to_regime(trades_df: pd.DataFrame, regime_df: pd.DataFrame) -> pd.DataFrame:
    df = trades_df.copy()
    df = df[df["side"] == "sell"].copy()
    df["sell_dt"] = pd.to_datetime(df["datetime"])
    df["sell_date"] = df["sell_dt"].dt.normalize()
    lookup = regime_df.set_index("date")["regime"]
    df["regime"] = df["sell_date"].map(lookup)
    df["regime"] = df["regime"].fillna("UNKNOWN")
    return df


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    LOG.info("loading KOSPI 2025-09-01 ~ 2026-05-31")
    kospi = _load_kospi("2025-09-01", "2026-05-31")
    LOG.info(f"rows: {len(kospi)}")

    # 기간별 다중 지표
    summary = _summary_per_period(kospi)
    print("\n=== KOSPI 기간 비교 (다중 지표) ===")
    print(summary.to_string(index=False))
    print()

    # 세분화 라벨
    labeled = _label_subdivided(kospi)
    print("=== 전체 regime 분포 ===")
    print(labeled["regime"].value_counts().to_dict())
    print()
    for period_id, (start, end) in PERIODS.items():
        s = pd.to_datetime(start)
        e = pd.to_datetime(end)
        sub = labeled[(labeled["date"] >= s) & (labeled["date"] <= e)]
        print(f"=== {period_id} 5단계 regime 분포 ===")
        print(sub["regime"].value_counts().to_dict())
    print()

    # fade_vwap 거래 매핑
    trades_dir = Path("reports/books_research/bellafiore_playbook")
    all_trades = []
    for period in PERIODS:
        f = trades_dir / f"results_single_fade_vwap_{period}_top_volume50_sl030_tp050_mh120.parquet"
        if f.exists():
            df = pd.read_parquet(f)
            df["period"] = period
            all_trades.append(df)
            LOG.info(f"loaded {f.name}: {len(df)} rows")
        else:
            LOG.warning(f"not found: {f}")
    if not all_trades:
        LOG.error("no trade parquets found")
        return

    trades = pd.concat(all_trades, ignore_index=True)
    mapped = _map_trades_to_regime(trades, labeled)
    LOG.info(f"sell trades mapped: {len(mapped)}")

    # 5단계 regime별 집계 (전체)
    agg = mapped.groupby("regime").agg(
        n_trades=("pnl_pct", "size"),
        pnl_mean=("pnl_pct", "mean"),
        pnl_sum=("pnl_pct", "sum"),
        hit_rate=("pnl_pct", lambda x: (x > 0).mean()),
        pnl_std=("pnl_pct", "std"),
    ).reset_index()
    agg["sharpe"] = agg.apply(
        lambda r: r["pnl_mean"] / r["pnl_std"] * np.sqrt(252) if r["pnl_std"] > 0 else 0.0,
        axis=1,
    )
    agg["pnl_mean"] = agg["pnl_mean"].round(6)
    agg["pnl_sum"] = agg["pnl_sum"].round(6)
    agg["hit_rate"] = agg["hit_rate"].round(4)
    agg["sharpe"] = agg["sharpe"].round(4)
    print("=== 5단계 regime별 fade_vwap PnL (전체 기간) ===")
    print(agg.to_string(index=False))
    print()

    # 기간 × 세분 regime
    by_period = mapped.groupby(["period", "regime"]).agg(
        n_trades=("pnl_pct", "size"),
        pnl_mean=("pnl_pct", "mean"),
        pnl_sum=("pnl_pct", "sum"),
        hit_rate=("pnl_pct", lambda x: (x > 0).mean()),
    ).reset_index()
    by_period["pnl_mean"] = by_period["pnl_mean"].round(6)
    by_period["pnl_sum"] = by_period["pnl_sum"].round(6)
    by_period["hit_rate"] = by_period["hit_rate"].round(4)
    print("=== 기간 × 5단계 regime ===")
    print(by_period.to_string(index=False))
    print()

    # 저장
    out_dir = trades_dir
    summary.to_parquet(out_dir / "sideways_subdivision_kospi_summary.parquet", index=False)
    agg.to_parquet(out_dir / "sideways_subdivision_regime_summary.parquet", index=False)
    by_period.to_parquet(out_dir / "sideways_subdivision_by_period.parquet", index=False)
    labeled.to_parquet(out_dir / "sideways_subdivision_kospi_labels.parquet", index=False)
    LOG.info(f"saved 4 parquets to {out_dir}/")


if __name__ == "__main__":
    main()
