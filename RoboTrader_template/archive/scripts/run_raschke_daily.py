"""Raschke Phase 2 일봉 5셋업 백테스트."""

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

from backtest.book_backtester import BookBacktester, append_leaderboard
from strategies.books._base_book_strategy import BookStrategy
from strategies.books.raschke_street_smarts.rules_daily import ALL_RULES_DAILY
from strategies.books.raschke_street_smarts.strategy_daily import BOOK_META_DAILY

LOG = logging.getLogger("raschke_daily")

# 일봉 - 기간 더 크게 (긴 lookback 위해)
PERIODS = {
    "2025-10": ("2025-08-01", "2025-10-31"),  # warmup 60일 + 평가 기간
    "2026-04": ("2026-02-01", "2026-04-30"),
    "2026-05": ("2026-03-01", "2026-05-27"),
}


def _to_yyyymmdd(date_str: str) -> str:
    """'2026-05-01' → '20260501' (daily_candles varchar 형식)."""
    return date_str.replace("-", "")


def _load_top_volume_universe_daily(period_start: str, period_end: str, top_n: int = 50) -> list:
    from db.connection import DatabaseConnection
    start_key = _to_yyyymmdd(period_start)
    end_key = _to_yyyymmdd(period_end)
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, SUM(stck_clpr::numeric) AS proxy
            FROM daily_candles
            WHERE stck_bsop_date >= %s AND stck_bsop_date <= %s
              AND stock_code != 'KS11'
              AND stock_code NOT LIKE 'K%%'
            GROUP BY stock_code
            ORDER BY proxy DESC
            LIMIT %s
        """, (start_key, end_key, top_n))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _load_daily(stock_codes, start_date: str, end_date: str) -> dict:
    from db.connection import DatabaseConnection
    start_key = _to_yyyymmdd(start_date)
    end_key = _to_yyyymmdd(end_date)
    out = {}
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        for code in stock_codes:
            cur.execute("""
                SELECT stck_bsop_date AS datetime,
                       stck_oprc::numeric AS open,
                       stck_hgpr::numeric AS high,
                       stck_lwpr::numeric AS low,
                       stck_clpr::numeric AS close,
                       COALESCE(acml_vol::numeric, 1000) AS volume
                FROM daily_candles
                WHERE stock_code = %s
                  AND stck_bsop_date >= %s AND stck_bsop_date <= %s
                ORDER BY stck_bsop_date ASC
            """, (code, start_key, end_key))
            rows = cur.fetchall()
            cols = ["datetime", "open", "high", "low", "close", "volume"]
            df = pd.DataFrame(rows, columns=cols)
            if not df.empty and len(df) >= 30:
                df["datetime"] = pd.to_datetime(df["datetime"])
                out[code] = df
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reports-dir", default="reports/books_research/raschke_street_smarts_daily")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    rules_meta = {cls().name: cls for cls in ALL_RULES_DAILY}
    rule_names = list(rules_meta.keys())
    combos = [("single", name) for name in rule_names] + [("all_AND", None)]

    leaderboard_path = Path("reports/books_research/leaderboard.parquet")
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    for period_id, (start, end) in PERIODS.items():
        LOG.info(f"=== period={period_id} ({start} ~ {end}) ===")
        universe = _load_top_volume_universe_daily(start, end, 50)
        data = _load_daily(universe, start, end)
        LOG.info(f"data loaded: {len(data)} stocks")

        for mode, rule_name in combos:
            rules_list = [cls() for cls in ALL_RULES_DAILY]
            strategy = BookStrategy(
                rules=rules_list, mode=mode,
                target_rule=rule_name,
                or_members=None,
            )
            bt = BookBacktester(
                strategy=strategy,
                initial_capital=10_000_000,
                warmup_bars=30,
                eod_liquidate=False,  # 일봉이므로 EOD 비활성
                stop_loss_pct=0.05,   # 일봉용 — 분봉 -3% 대비 완화
                take_profit_pct=0.10,
                max_hold_bars=10,     # 10일 보유 한도
            )
            agg = bt.run_universe(data)
            label = rule_name if mode == "single" else mode
            LOG.info(
                f"[{mode}/{label}] n_stocks={agg.n_stocks} n_trades={agg.n_trades} "
                f"pnl={agg.pnl_pct:.4%} sharpe={agg.sharpe:.2f}"
            )
            out_file = reports_dir / f"results_{mode}_{label}_{period_id}_daily.parquet"
            trade_rows = []
            for code, res in agg.per_stock.items():
                for t in res.trades:
                    t = dict(t)
                    t["stock_code"] = code
                    trade_rows.append(t)
            if trade_rows:
                pd.DataFrame(trade_rows).to_parquet(out_file, index=False)
            append_leaderboard(
                path=leaderboard_path,
                row={
                    "book_id": "raschke_street_smarts_daily",
                    "book_name": BOOK_META_DAILY["name"],
                    "period": period_id,
                    "rule_combo": label,
                    "mode": mode,
                    "universe": "top_volume_daily:50",
                    "stop_loss_pct": 0.05,
                    "take_profit_pct": 0.10,
                    "max_hold_bars": 10,
                    "n_stocks": agg.n_stocks,
                    "n_trades": agg.n_trades,
                    "pnl_pct": agg.pnl_pct,
                    "sharpe": agg.sharpe,
                    "calmar": agg.calmar,
                    "sortino": agg.sortino,
                    "max_dd_pct": agg.max_dd_pct,
                    "hit_rate": agg.hit_rate,
                    "avg_hold_bars": agg.avg_hold_bars,
                },
            )


if __name__ == "__main__":
    main()
