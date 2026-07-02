"""KOSPI 시장 국면 라벨링 + fade_vwap 거래 국면별 PnL 집계.

KOSPI(KS11) 일봉을 BULL/BEAR/SIDEWAYS로 라벨링하고, fade_vwap의 매도(sell) 거래
parquet에서 sell datetime → 날짜로 매핑해 국면별 PnL을 집계한다.

국면 정의:
- BULL: KOSPI 5일 종가 모멘텀 ≥ +1.0%
- BEAR: KOSPI 5일 종가 모멘텀 ≤ -1.0%
- SIDEWAYS: 그 외 (-1% < 5일 모멘텀 < +1%)

usage:
    python scripts/analyze_fade_vwap_regime.py
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

LOG = logging.getLogger("regime_analysis")

KOSPI_CODE = "KS11"
BULL_THRESHOLD = 0.01
BEAR_THRESHOLD = -0.01
MOMENTUM_WINDOW = 5

PERIODS = ["2025-10", "2026-04", "2026-05"]
TRADES_DIR = ROOT / "reports/books_research/bellafiore_playbook"


def _load_kospi_daily(start: str, end: str) -> pd.DataFrame:
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        q = """
            SELECT stck_bsop_date AS date, stck_clpr AS close
            FROM daily_candles
            WHERE stock_code = %s
              AND stck_bsop_date >= %s
              AND stck_bsop_date <= %s
            ORDER BY stck_bsop_date ASC
        """
        df = pd.read_sql(q, conn, params=(KOSPI_CODE, start, end))
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df


def _label_regime(df: pd.DataFrame) -> pd.DataFrame:
    """일별 국면 라벨링.

    momentum = close.pct_change(MOMENTUM_WINDOW)
    BULL/BEAR/SIDEWAYS by thresholds.
    """
    df = df.copy()
    df["momentum_5d"] = df["close"].pct_change(MOMENTUM_WINDOW)
    df["regime"] = "SIDEWAYS"
    df.loc[df["momentum_5d"] >= BULL_THRESHOLD, "regime"] = "BULL"
    df.loc[df["momentum_5d"] <= BEAR_THRESHOLD, "regime"] = "BEAR"
    return df


def _map_trades_to_regime(trades_df: pd.DataFrame, regime_df: pd.DataFrame) -> pd.DataFrame:
    """trades 의 sell datetime → 날짜 → regime 매핑."""
    df = trades_df.copy()
    # sell만 — pnl_pct가 의미 있는 행
    df = df[df["side"] == "sell"].copy()
    df["sell_dt"] = pd.to_datetime(df["datetime"])
    df["sell_date"] = df["sell_dt"].dt.normalize()

    # left join with regime
    regime_lookup = regime_df.set_index("date")["regime"]
    df["regime"] = df["sell_date"].map(regime_lookup)
    # 라벨 못 받은 행은 SIDEWAYS로
    df["regime"] = df["regime"].fillna("SIDEWAYS")
    return df


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # KOSPI 일봉은 모든 기간 + 직전 30일 buffer
    LOG.info("loading KOSPI daily 2025-09-01 ~ 2026-05-31")
    kospi = _load_kospi_daily("2025-09-01", "2026-05-31")
    LOG.info(f"KOSPI rows: {len(kospi)}")

    kospi_labeled = _label_regime(kospi)
    LOG.info(f"regime counts: {kospi_labeled['regime'].value_counts().to_dict()}")

    all_trades = []
    for period in PERIODS:
        parquet = TRADES_DIR / f"results_single_fade_vwap_{period}_top_volume50_sl030_tp050_mh120.parquet"
        if not parquet.exists():
            LOG.warning(f"missing {parquet}, skipping {period}")
            continue
        df = pd.read_parquet(parquet)
        df["period"] = period
        all_trades.append(df)

    if not all_trades:
        LOG.error("no trade parquet found")
        return

    trades = pd.concat(all_trades, ignore_index=True)
    LOG.info(f"total raw trade rows: {len(trades)}")

    mapped = _map_trades_to_regime(trades, kospi_labeled)
    LOG.info(f"sell trades after mapping: {len(mapped)}")

    # 국면별 집계
    summary = mapped.groupby("regime").agg(
        n_trades=("pnl_pct", "size"),
        pnl_mean=("pnl_pct", "mean"),
        pnl_sum=("pnl_pct", "sum"),
        hit_rate=("pnl_pct", lambda x: (x > 0).mean()),
        pnl_std=("pnl_pct", "std"),
    ).reset_index()
    summary["sharpe"] = summary.apply(
        lambda r: r["pnl_mean"] / r["pnl_std"] * np.sqrt(252) if r["pnl_std"] > 0 else 0.0,
        axis=1,
    )
    summary = summary[["regime", "n_trades", "pnl_mean", "pnl_sum", "hit_rate", "sharpe"]]
    print("=== 국면별 fade_vwap 거래 ===")
    print(summary.to_string(index=False))

    # 기간별 × 국면별
    by_period = mapped.groupby(["period", "regime"]).agg(
        n_trades=("pnl_pct", "size"),
        pnl_mean=("pnl_pct", "mean"),
        pnl_sum=("pnl_pct", "sum"),
        hit_rate=("pnl_pct", lambda x: (x > 0).mean()),
    ).reset_index()
    print()
    print("=== 기간 × 국면 ===")
    print(by_period.to_string(index=False))

    # 저장
    out_dir = TRADES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    summary.to_parquet(out_dir / "fade_vwap_regime_summary.parquet", index=False)
    by_period.to_parquet(out_dir / "fade_vwap_regime_by_period.parquet", index=False)
    mapped.to_parquet(out_dir / "fade_vwap_trades_with_regime.parquet", index=False)

    # KOSPI 라벨 자체도 저장
    kospi_labeled.to_parquet(out_dir / "kospi_regime_labels.parquet", index=False)
    LOG.info(f"saved 4 parquet files to {out_dir}/")


if __name__ == "__main__":
    main()
