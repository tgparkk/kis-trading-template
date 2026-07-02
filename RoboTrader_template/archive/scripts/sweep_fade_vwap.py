"""fade_vwap 파라미터 sweep — Bellafiore best 규칙 정밀화.

deviation_pct × rsi_oversold 그리드를 한 종목 데이터 위에서 인메모리로 평가.
데이터는 기간당 1회만 로드.

usage:
    python scripts/sweep_fade_vwap.py [--out reports/books_research/bellafiore_playbook/fade_vwap_sweep.parquet]
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
from strategies.books.bellafiore_playbook.rules import rule_fade_vwap  # noqa: E402

LOG = logging.getLogger("sweep_fade_vwap")

PERIODS = {
    "2025-10": ("2025-10-01", "2025-10-31"),
    "2026-04": ("2026-04-01", "2026-04-30"),
    "2026-05": ("2026-05-01", "2026-05-27"),
}

# sweep 그리드
DEVIATION_PCTS = [0.015, 0.020, 0.025]
RSI_OVERSOLDS = [10.0, 15.0, 20.0]
RSI_PERIODS = [2]

# 청산 (Bellafiore baseline)
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
            WHERE datetime >= %s
              AND datetime < %s::date + INTERVAL '1 day'
            GROUP BY stock_code
            ORDER BY turnover DESC
            LIMIT %s
        """
        df = pd.read_sql(q, conn, params=(period_start, period_end, top_n))
    return df["stock_code"].tolist()


def _load_minute_data(stock_codes, start_date: str, end_date: str) -> dict:
    from db.connection import DatabaseConnection
    out: dict = {}
    with DatabaseConnection.get_connection() as conn:
        for code in stock_codes:
            q = """
                SELECT datetime, open, high, low, close, volume
                FROM minute_candles
                WHERE stock_code = %s
                  AND datetime >= %s
                  AND datetime < %s::date + INTERVAL '1 day'
                ORDER BY datetime ASC
            """
            df = pd.read_sql(q, conn, params=(code, start_date, end_date))
            if not df.empty:
                out[code] = df
    return out


def main():
    p = argparse.ArgumentParser(description="fade_vwap 파라미터 sweep: Bellafiore best 규칙 정밀화")
    p.add_argument(
        "--out",
        default="reports/books_research/bellafiore_playbook/fade_vwap_sweep.parquet",
        help="결과 저장 경로 (parquet)",
    )
    p.add_argument("--log-level", default="INFO", help="로그 레벨 (DEBUG/INFO/WARNING)")
    args = p.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    rows = []

    for period_id, (start, end) in PERIODS.items():
        LOG.info(f"=== period={period_id} ({start} ~ {end}) ===")
        universe = _load_top_volume_universe(start, end, 50)
        LOG.info(f"universe size: {len(universe)}")

        data = _load_minute_data(universe, start, end)
        LOG.info(f"loaded data for {len(data)} stocks")

        for dev_pct in DEVIATION_PCTS:
            for rsi_thr in RSI_OVERSOLDS:
                for rsi_p in RSI_PERIODS:
                    rule = rule_fade_vwap(
                        deviation_pct=dev_pct,
                        rsi_period=rsi_p,
                        rsi_oversold=rsi_thr,
                    )
                    strategy = BookStrategy(
                        rules=[rule],
                        mode="single",
                        target_rule="fade_vwap",
                    )
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
                        f"[dev={dev_pct} rsi_thr={rsi_thr} rsi_p={rsi_p}] "
                        f"n_trades={agg.n_trades} pnl={agg.pnl_pct:.4%} "
                        f"sharpe={agg.sharpe:.2f} calmar={agg.calmar:.2f} hit={agg.hit_rate:.3f}"
                    )

                    rows.append({
                        "period": period_id,
                        "deviation_pct": dev_pct,
                        "rsi_oversold": rsi_thr,
                        "rsi_period": rsi_p,
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
