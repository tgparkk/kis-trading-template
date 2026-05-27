"""책 백테스트 실행 CLI.

usage:
    python scripts/run_books_research.py --book aziz_day_trade --period 2026-04 --mode single --rule abcd
    python scripts/run_books_research.py --book aziz_day_trade --period 2026-04 --mode all_AND

책 모듈 로드 -> 데이터 로드 -> 백테스트 -> results parquet 저장 -> 리더보드 append.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

import pandas as pd

# import 경로 설정 (script로 직접 실행 시)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.book_backtester import BookBacktester, append_leaderboard  # noqa: E402

LOG = logging.getLogger("books_research")
PERIODS = {
    "2025-10": ("2025-10-01", "2025-10-31"),
    "2026-04": ("2026-04-01", "2026-04-30"),
    "2026-05": ("2026-05-01", "2026-05-27"),
}


def _load_book_module(book_id: str):
    """strategies.books.{book_id}.strategy 에서 build_strategy(mode, target_rule, or_members) 호출."""
    mod = importlib.import_module(f"strategies.books.{book_id}.strategy")
    if not hasattr(mod, "build_strategy"):
        raise AttributeError(f"{book_id}.strategy 에 build_strategy() 함수가 없습니다")
    return mod


def _load_minute_data(stock_codes, start_date: str, end_date: str) -> dict:
    """robotrader.minute_candles 에서 stock_code, datetime, open, high, low, close, volume 로드."""
    from db.connection import DatabaseConnection  # 지연 import

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


def _load_universe(period_start: str) -> list:
    """1,347 종목 풀. minute_candles에 해당 기간 데이터가 있는 종목만 반환."""
    from db.connection import DatabaseConnection

    with DatabaseConnection.get_connection() as conn:
        q = """
            SELECT DISTINCT stock_code
            FROM minute_candles
            WHERE datetime >= %s
              AND datetime < %s::date + INTERVAL '7 days'
            ORDER BY stock_code
        """
        df = pd.read_sql(q, conn, params=(period_start, period_start))
    return df["stock_code"].tolist()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--book", required=True, help="책 ID (예: aziz_day_trade)")
    p.add_argument("--period", required=True, choices=list(PERIODS.keys()))
    p.add_argument("--mode", default=None, choices=["single", "all_AND", "top_K_OR"],
                   help="단일 mode 실행 시 지정. --all-modes 와 동시 사용 금지")
    p.add_argument("--rule", default=None, help="single 모드에서 규칙 이름")
    p.add_argument("--or-members", default=None, help="top_K_OR 모드용 쉼표 구분 규칙 이름들")
    p.add_argument("--all-modes", action="store_true",
                   help="기간 1개 데이터를 1번 로드해서 모든 규칙 single + all_AND 일괄 실행")
    p.add_argument("--limit", type=int, default=None, help="유니버스 N개로 제한 (디버그용)")
    p.add_argument("--initial-capital", type=float, default=10_000_000)
    p.add_argument("--reports-dir", default="reports/books_research")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.all_modes and args.mode is not None:
        p.error("--all-modes 와 --mode 는 동시 사용 불가")
    if not args.all_modes and args.mode is None:
        p.error("--mode 또는 --all-modes 둘 중 하나는 필수")

    start, end = PERIODS[args.period]
    LOG.info(f"period={args.period} ({start} ~ {end}) book={args.book} all_modes={args.all_modes}")

    book_mod = _load_book_module(args.book)

    universe = _load_universe(start)
    if args.limit:
        universe = universe[: args.limit]
    LOG.info(f"universe size: {len(universe)}")

    data = _load_minute_data(universe, start, end)
    LOG.info(f"loaded data for {len(data)} stocks")

    reports_dir = Path(args.reports_dir) / args.book
    reports_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = Path(args.reports_dir) / "leaderboard.parquet"
    book_meta = getattr(book_mod, "BOOK_META", {})

    if args.all_modes:
        # 8개 single + 1 all_AND
        from strategies.books.aziz_day_trade.rules import ALL_RULES  # 책별 import
        rule_names = [cls().name for cls in ALL_RULES]
        combos = [("single", name) for name in rule_names] + [("all_AND", None)]
    else:
        combos = [(args.mode, args.rule)]

    for mode, rule_name in combos:
        or_members = args.or_members.split(",") if args.or_members else None
        strategy = book_mod.build_strategy(mode=mode, target_rule=rule_name, or_members=or_members)
        bt = BookBacktester(strategy=strategy, initial_capital=args.initial_capital, warmup_bars=20)
        agg = bt.run_universe(data)

        rule_label = rule_name if mode == "single" else (
            mode if mode == "all_AND" else "+".join(or_members or [])
        )
        LOG.info(
            f"[{mode}/{rule_label}] n_stocks={agg.n_stocks} n_trades={agg.n_trades} "
            f"pnl={agg.pnl_pct:.4%} sharpe={agg.sharpe:.2f} calmar={agg.calmar:.2f}"
        )

        out_file = reports_dir / f"results_{mode}_{rule_label}_{args.period}.parquet"
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
                "book_id": args.book,
                "book_name": book_meta.get("name", args.book),
                "period": args.period,
                "rule_combo": rule_label,
                "mode": mode,
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
    LOG.info(f"leaderboard updated: {leaderboard_path}")


if __name__ == "__main__":
    main()
