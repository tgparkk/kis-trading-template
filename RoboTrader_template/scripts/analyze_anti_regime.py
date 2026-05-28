"""Anti 거래를 KOSPI BULL/BEAR/SIDEWAYS × 변동성 4분면으로 분해 + 필터 적용 시뮬레이션."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = logging.getLogger("anti_regime")
KOSPI_CODE = "KS11"
MOMENTUM_WINDOW = 5
BULL_THRESHOLD = 0.01
BEAR_THRESHOLD = -0.01
VOLATILITY_THRESHOLD = 0.03  # avg_range_pct 3%

PERIODS = ["2025-10", "2026-04", "2026-05"]
TRADES_DIR = Path(__file__).resolve().parent.parent / "reports/books_research/raschke_street_smarts"


def _load_kospi(start: str, end: str) -> pd.DataFrame:
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        q = """
            SELECT stck_bsop_date AS date, stck_clpr AS close, stck_hgpr AS high, stck_lwpr AS low
            FROM daily_candles
            WHERE stock_code = %s AND stck_bsop_date >= %s AND stck_bsop_date <= %s
            ORDER BY stck_bsop_date ASC
        """
        df = pd.read_sql(q, conn, params=(KOSPI_CODE, start, end))
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    return df


def _label_regime_and_volatility(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mom_5d"] = df["close"].pct_change(MOMENTUM_WINDOW)
    df["regime"] = "SIDEWAYS"
    df.loc[df["mom_5d"] >= BULL_THRESHOLD, "regime"] = "BULL"
    df.loc[df["mom_5d"] <= BEAR_THRESHOLD, "regime"] = "BEAR"
    df["range_pct"] = (df["high"] - df["low"]) / df["close"]
    df["high_vol"] = df["range_pct"] >= VOLATILITY_THRESHOLD
    return df


def _map_trades(trades_df: pd.DataFrame, regime_df: pd.DataFrame) -> pd.DataFrame:
    df = trades_df.copy()
    df = df[df["side"] == "sell"].copy()
    df["sell_dt"] = pd.to_datetime(df["datetime"])
    df["sell_date"] = df["sell_dt"].dt.normalize()
    lookup_regime = regime_df.set_index("date")["regime"]
    lookup_vol = regime_df.set_index("date")["high_vol"]
    df["regime"] = df["sell_date"].map(lookup_regime).fillna("SIDEWAYS")
    df["high_vol"] = df["sell_date"].map(lookup_vol).fillna(False)
    return df


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    LOG.info("loading KOSPI 2025-09-01 ~ 2026-05-31")
    kospi = _load_kospi("2025-09-01", "2026-05-31")
    LOG.info(f"KOSPI rows: {len(kospi)}")
    labeled = _label_regime_and_volatility(kospi)
    LOG.info(f"regime counts: {labeled['regime'].value_counts().to_dict()}")
    LOG.info(f"high_vol days: {labeled['high_vol'].sum()} / {len(labeled)}")

    all_trades = []
    for period in PERIODS:
        f = TRADES_DIR / f"results_single_anti_{period}_top_volume50_sl030_tp050_mh120.parquet"
        if f.exists():
            df = pd.read_parquet(f)
            df["period"] = period
            all_trades.append(df)
        else:
            LOG.warning(f"missing {f.name}, skipping")
    if not all_trades:
        LOG.error("no anti parquets found")
        return

    trades = pd.concat(all_trades, ignore_index=True)
    LOG.info(f"total raw trade rows: {len(trades)}")
    mapped = _map_trades(trades, labeled)
    LOG.info(f"sell trades mapped: {len(mapped)}")

    # 4분면: regime × volatility
    mapped["quadrant"] = mapped["regime"] + "_" + np.where(mapped["high_vol"], "HIGHVOL", "LOWVOL")
    quad = mapped.groupby("quadrant").agg(
        n_trades=("pnl_pct", "size"),
        pnl_mean=("pnl_pct", "mean"),
        pnl_sum=("pnl_pct", "sum"),
        hit_rate=("pnl_pct", lambda x: (x > 0).mean()),
        pnl_std=("pnl_pct", "std"),
    ).reset_index()
    quad["sharpe"] = quad.apply(
        lambda r: r["pnl_mean"] / r["pnl_std"] * np.sqrt(252) if r["pnl_std"] > 0 else 0.0,
        axis=1,
    )
    print("=== 4분면 (regime × volatility) ===")
    print(quad.to_string(index=False))
    print()

    # 필터 시뮬레이션 — 베이스라인 vs 6가지 필터 조합
    def simulate(label, mask):
        sub = mapped[mask]
        n = len(sub)
        pnl_sum = sub["pnl_pct"].sum() if n > 0 else 0
        pnl_mean = sub["pnl_pct"].mean() if n > 0 else 0
        hit = (sub["pnl_pct"] > 0).mean() if n > 0 else 0
        std = sub["pnl_pct"].std() if n > 0 else 0
        sharpe = pnl_mean / std * np.sqrt(252) if std > 0 else 0
        return {
            "filter": label, "n_trades": n,
            "pnl_sum": pnl_sum, "pnl_mean": pnl_mean,
            "hit_rate": hit, "sharpe": sharpe,
        }

    sims = [
        simulate("baseline (모든 거래)", pd.Series([True] * len(mapped), index=mapped.index)),
        simulate("low_vol only (변동성<3%)", ~mapped["high_vol"]),
        simulate("BULL only", mapped["regime"] == "BULL"),
        simulate("BULL + low_vol", (mapped["regime"] == "BULL") & ~mapped["high_vol"]),
        simulate("BULL+SIDEWAYS only (BEAR 회피)", mapped["regime"].isin(["BULL", "SIDEWAYS"])),
        simulate("BULL+SIDEWAYS + low_vol", mapped["regime"].isin(["BULL", "SIDEWAYS"]) & ~mapped["high_vol"]),
    ]
    sim_df = pd.DataFrame(sims)
    print("=== 필터 시뮬레이션 ===")
    print(sim_df.to_string(index=False))
    print()

    # 기간별 4분면
    by_period = mapped.groupby(["period", "quadrant"]).agg(
        n_trades=("pnl_pct", "size"),
        pnl_mean=("pnl_pct", "mean"),
        pnl_sum=("pnl_pct", "sum"),
        hit_rate=("pnl_pct", lambda x: (x > 0).mean()),
    ).reset_index()
    print("=== 기간 × 4분면 ===")
    print(by_period.to_string(index=False))

    # 저장
    out_dir = TRADES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    quad.to_parquet(out_dir / "anti_regime_quadrant_summary.parquet", index=False)
    sim_df.to_parquet(out_dir / "anti_filter_simulation.parquet", index=False)
    by_period.to_parquet(out_dir / "anti_regime_by_period.parquet", index=False)
    mapped.to_parquet(out_dir / "anti_trades_with_regime.parquet", index=False)
    LOG.info(f"saved 4 parquet files to {out_dir}/")


if __name__ == "__main__":
    main()
