"""Raschke anti 파라미터 sweep — k_period × d_period × impulse_pct.

베이스라인 (k=7, d=10, impulse=0.005) 대비 최적 조합 탐색.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.book_backtester import BookBacktester  # noqa: E402
from strategies.books._base_book_strategy import BookStrategy  # noqa: E402
from strategies.books.raschke_street_smarts.rules import rule_anti  # noqa: E402

LOG = logging.getLogger("sweep_anti")

PERIODS = {
    "2025-10": ("2025-10-01", "2025-10-31"),
    "2026-04": ("2026-04-01", "2026-04-30"),
    "2026-05": ("2026-05-01", "2026-05-27"),
}

K_PERIODS = [5, 7, 9]
D_PERIODS = [7, 10, 14]
IMPULSE_PCTS = [0.003, 0.005, 0.010]
EMA_PERIOD = 20

STOP_LOSS = 0.03
TAKE_PROFIT = 0.05
MAX_HOLD = 120
INITIAL_CAPITAL = 10_000_000


def _load_top_volume_universe(period_start: str, period_end: str, top_n: int) -> list:
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        q = """
            SELECT stock_code, SUM(close * volume) AS turnover
            FROM minute_candles
            WHERE datetime >= %s AND datetime < %s::date + INTERVAL '1 day'
            GROUP BY stock_code
            ORDER BY turnover DESC
            LIMIT %s
        """
        df = pd.read_sql(q, conn, params=(period_start, period_end, top_n))
    return df["stock_code"].tolist()


def _load_minute_data(stock_codes, start_date: str, end_date: str) -> dict:
    from db.connection import DatabaseConnection
    out = {}
    with DatabaseConnection.get_connection() as conn:
        for code in stock_codes:
            q = """
                SELECT datetime, open, high, low, close, volume
                FROM minute_candles
                WHERE stock_code = %s AND datetime >= %s AND datetime < %s::date + INTERVAL '1 day'
                ORDER BY datetime ASC
            """
            df = pd.read_sql(q, conn, params=(code, start_date, end_date))
            if not df.empty:
                out[code] = df
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="reports/books_research/raschke_street_smarts/anti_sweep.parquet")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    rows = []
    for period_id, (start, end) in PERIODS.items():
        LOG.info(f"=== period={period_id} ({start} ~ {end}) ===")
        universe = _load_top_volume_universe(start, end, 50)
        data = _load_minute_data(universe, start, end)
        LOG.info(f"data loaded: {len(data)} stocks")

        for k in K_PERIODS:
            for d in D_PERIODS:
                for imp in IMPULSE_PCTS:
                    rule = rule_anti(
                        k_period=k, d_period=d,
                        ema_period=EMA_PERIOD, impulse_pct=imp,
                    )
                    strategy = BookStrategy(rules=[rule], mode="single", target_rule="anti")
                    bt = BookBacktester(
                        strategy=strategy,
                        initial_capital=INITIAL_CAPITAL,
                        warmup_bars=20,
                        stop_loss_pct=STOP_LOSS,
                        take_profit_pct=TAKE_PROFIT,
                        max_hold_bars=MAX_HOLD,
                    )
                    agg = bt.run_universe(data)
                    LOG.info(
                        f"[k={k} d={d} imp={imp}] n_trades={agg.n_trades} "
                        f"pnl={agg.pnl_pct:.4%} sharpe={agg.sharpe:.2f} calmar={agg.calmar:.2f}"
                    )
                    rows.append({
                        "period": period_id,
                        "k_period": k,
                        "d_period": d,
                        "impulse_pct": imp,
                        "n_stocks": agg.n_stocks,
                        "n_trades": agg.n_trades,
                        "pnl_pct": agg.pnl_pct,
                        "sharpe": agg.sharpe,
                        "calmar": agg.calmar,
                        "sortino": agg.sortino,
                        "max_dd_pct": agg.max_dd_pct,
                        "hit_rate": agg.hit_rate,
                        "avg_hold_bars": agg.avg_hold_bars,
                        "run_at": datetime.utcnow().isoformat(),
                    })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out_path, index=False)
    LOG.info(f"sweep saved: {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
