"""강창권 『단기 트레이딩의 정석』 분봉 백테스트 CLI.

run_books_research.py 를 haru_silijeon 분봉 전용으로 복제·확장.
- universe 기본: top_volume:50 (분봉책 공통)
- CK480 등 분봉 룰의 480분선 멀티데이 연결을 위해 종목별 다일 연속 분봉 로드
- no-lookahead, 거래비용/슬리피지는 BookBacktester 기본값과 동일

usage:
    # 단일 룰 (CK480) 파일럿
    python scripts/run_haru_silijeon_minute.py --period 2026-04 --mode single --rule ck480 --universe top_volume:50

    # 모든 분봉 룰 single + all_AND 일괄
    python scripts/run_haru_silijeon_minute.py --period 2026-04 --all-modes --universe top_volume:50
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

LOG = logging.getLogger("haru_silijeon")
BOOK_ID = "haru_silijeon"

PERIODS = {
    "2025-10": ("2025-10-01", "2025-10-31"),
    "2026-04": ("2026-04-01", "2026-04-30"),
    "2026-05": ("2026-05-01", "2026-05-27"),
}

# CK480/240·480분선 룰은 직전 거래일까지 연속 분봉이 있어야 480분 이평이 채워진다.
# 480분 ≈ 1.25 거래일이므로, 기간 시작 전 LOOKBACK_DAYS 만큼 분봉을 추가 로드한다.
LOOKBACK_DAYS = 5


def _load_book_module(book_id: str):
    mod = importlib.import_module(f"strategies.books.{book_id}.strategy")
    if not hasattr(mod, "build_strategy"):
        raise AttributeError(f"{book_id}.strategy 에 build_strategy() 함수가 없습니다")
    return mod


def _load_minute_data(stock_codes, load_start: str, end_date: str) -> dict:
    """robotrader.minute_candles 에서 종목별 다일 연속 분봉 로드.

    load_start 는 period_start - LOOKBACK_DAYS (480분선 warmup용).
    """
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
            df = pd.read_sql(q, conn, params=(code, load_start, end_date))
            if not df.empty:
                df["datetime"] = pd.to_datetime(df["datetime"])
                out[code] = df.reset_index(drop=True)
    return out


def _load_top_volume_universe(period_start: str, period_end: str, top_n: int) -> list:
    """일별 거래대금(close*volume) 합계 상위 N종목."""
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


def _load_all_universe(period_start: str) -> list:
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
    p.add_argument("--period", required=True, choices=list(PERIODS.keys()))
    p.add_argument("--mode", default=None, choices=["single", "all_AND", "top_K_OR"],
                   help="단일 mode 실행 시 지정. --all-modes 와 동시 사용 금지")
    p.add_argument("--rule", default=None, help="single 모드에서 규칙 이름 (예: ck480)")
    p.add_argument("--or-members", default=None, help="top_K_OR 모드용 쉼표 구분 규칙 이름들")
    p.add_argument("--all-modes", action="store_true",
                   help="기간 1개 데이터를 1번 로드해서 모든 분봉 룰 single + all_AND 일괄 실행")
    p.add_argument("--limit", type=int, default=None, help="유니버스 N개로 제한 (디버그용)")
    p.add_argument("--initial-capital", type=float, default=10_000_000)
    p.add_argument("--reports-dir", default="reports/books_research")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--universe", default="top_volume:50",
                   help="유니버스 선택: 'top_volume:N' (기본 50) | 'all'")
    # CK480 권장: tp +1~3%, sl -2%. 기본을 tp 0.02 / sl 0.02 로 둔다 (분봉책 sl3/tp5 차용도 가능).
    p.add_argument("--stop-loss-pct", type=float, default=0.02)
    p.add_argument("--take-profit-pct", type=float, default=0.02)
    p.add_argument("--max-hold-bars", type=int, default=30,
                   help="분봉 최대 보유 봉수 (CK480 단타 → 기본 30분)")
    args = p.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.all_modes and args.mode is not None:
        p.error("--all-modes 와 --mode 는 동시 사용 불가")
    if not args.all_modes and args.mode is None:
        p.error("--mode 또는 --all-modes 둘 중 하나는 필수")

    start, end = PERIODS[args.period]
    load_start = (pd.Timestamp(start) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    LOG.info(
        f"period={args.period} ({start} ~ {end}) book={BOOK_ID} "
        f"all_modes={args.all_modes} warmup_load_start={load_start}"
    )

    book_mod = _load_book_module(BOOK_ID)

    if args.universe.startswith("top_volume:"):
        top_n = int(args.universe.split(":", 1)[1])
        universe = _load_top_volume_universe(start, end, top_n)
        LOG.info(f"universe mode=top_volume:{top_n} → loaded {len(universe)} stocks")
    else:
        universe = _load_all_universe(start)
    if args.limit:
        universe = universe[: args.limit]
    LOG.info(f"universe size: {len(universe)}")

    data = _load_minute_data(universe, load_start, end)
    total_bars = sum(len(df) for df in data.values())
    LOG.info(f"loaded data for {len(data)} stocks, total {total_bars} bars")

    reports_dir = Path(args.reports_dir) / BOOK_ID
    reports_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_path = Path(args.reports_dir) / "leaderboard.parquet"
    book_meta = getattr(book_mod, "BOOK_META", {})

    if args.all_modes:
        rules_mod = importlib.import_module(f"strategies.books.{BOOK_ID}.rules")
        if not hasattr(rules_mod, "ALL_RULES"):
            raise AttributeError(f"strategies.books.{BOOK_ID}.rules 에 ALL_RULES 상수가 없습니다")
        rule_names = [cls().name for cls in rules_mod.ALL_RULES]
        combos = [("single", name) for name in rule_names] + [("all_AND", None)]
    else:
        combos = [(args.mode, args.rule)]

    for mode, rule_name in combos:
        or_members = args.or_members.split(",") if args.or_members else None
        strategy = book_mod.build_strategy(mode=mode, target_rule=rule_name, or_members=or_members)
        bt = BookBacktester(
            strategy=strategy,
            initial_capital=args.initial_capital,
            warmup_bars=20,
            stop_loss_pct=args.stop_loss_pct,
            take_profit_pct=args.take_profit_pct,
            max_hold_bars=args.max_hold_bars,
        )
        agg = bt.run_universe(data)

        rule_label = rule_name if mode == "single" else (
            mode if mode == "all_AND" else "+".join(or_members or [])
        )
        LOG.info(
            f"[{mode}/{rule_label}] n_stocks={agg.n_stocks} n_trades={agg.n_trades} "
            f"pnl={agg.pnl_pct:.4%} sharpe={agg.sharpe:.2f} calmar={agg.calmar:.2f} "
            f"hit={agg.hit_rate:.2%}"
        )

        universe_tag = args.universe.replace(":", "")
        exit_tag = f"sl{int(args.stop_loss_pct*1000):03d}_tp{int(args.take_profit_pct*1000):03d}_mh{args.max_hold_bars}"
        out_file = reports_dir / f"results_{mode}_{rule_label}_{args.period}_{universe_tag}_{exit_tag}.parquet"
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
                "book_id": BOOK_ID,
                "book_name": book_meta.get("name", BOOK_ID),
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
                "universe": args.universe,
                "stop_loss_pct": args.stop_loss_pct,
                "take_profit_pct": args.take_profit_pct,
                "max_hold_bars": args.max_hold_bars,
            },
        )
    LOG.info(f"leaderboard updated: {leaderboard_path}")


if __name__ == "__main__":
    main()
