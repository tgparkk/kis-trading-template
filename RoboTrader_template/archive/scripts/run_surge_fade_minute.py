"""태쏘의 데이트레이딩 바이블 2 — 급등주 투매폭 매매법 (15분봉) 백테스트 CLI.

run_haru_silijeon_minute.py 를 surge_fade(15분봉) 전용으로 복제·확장.
- universe 기본: top_volume:50 (분봉책 공통)
- robotrader.minute_candles 1분봉 로드 → TimeFrameConverter.convert_to_timeframe(df, 15)
  로 15분봉 변환 → BookBacktester 로 백테스트.
- ma_gate_window=480(15분봉 ≈ 18.5거래일) warmup 을 위해 period_start 이전
  약 30 캘린더일(LOOKBACK_DAYS=35) 1분봉을 추가 로드한다.
  warmup 봉은 지표계산용으로만 쓰이고, 거래 평가는 period_start 이후 봉부터 시작한다.
- no-lookahead, 거래비용/슬리피지는 BookBacktester 기본값과 동일.

usage:
    # 단일 룰(surge_fade) 파일럿
    python scripts/run_surge_fade_minute.py --period 2026-04 --mode single --rule surge_fade --universe top_volume:50

    # 모든 룰 single + all_AND 일괄
    python scripts/run_surge_fade_minute.py --period 2026-04 --all-modes --universe top_volume:50
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# import 경로 설정 (script로 직접 실행 시)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.book_backtester import (  # noqa: E402
    BookBacktester,
    UniverseBacktestResult,
    append_leaderboard,
)
from core.timeframe_converter import TimeFrameConverter  # noqa: E402

LOG = logging.getLogger("surge_fade")
BOOK_ID = "surge_fade"

# 15분봉 리샘플 단위.
TIMEFRAME_MINUTES = 15

PERIODS = {
    "2025-10": ("2025-10-01", "2025-10-31"),
    "2026-04": ("2026-04-01", "2026-04-30"),
    "2026-05": ("2026-05-01", "2026-05-27"),
}

# ma_gate_window=480(15분봉) ≈ 18.5거래일. period_start 이전 약 30 캘린더일
# (≈ 20거래일×24봉=480봉) 의 1분봉을 추가 로드해 MA게이트가 과도 기각되지 않게 한다.
LOOKBACK_DAYS = 35


def _load_book_module(book_id: str):
    mod = importlib.import_module(f"strategies.books.{book_id}.strategy")
    if not hasattr(mod, "build_strategy"):
        raise AttributeError(f"{book_id}.strategy 에 build_strategy() 함수가 없습니다")
    return mod


def _load_minute_data(stock_codes, load_start: str, end_date: str) -> dict:
    """robotrader.minute_candles 에서 종목별 다일 연속 1분봉 로드.

    load_start 는 period_start - LOOKBACK_DAYS (480봉 MA게이트 warmup용).
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


def _resample_15min(data: dict) -> dict:
    """종목별 1분봉 → 15분봉 변환 (no-lookahead 유지: 완성된 봉만)."""
    out: dict = {}
    for code, df in data.items():
        resampled = TimeFrameConverter.convert_to_timeframe(df, TIMEFRAME_MINUTES)
        if resampled is not None and not resampled.empty:
            resampled["datetime"] = pd.to_datetime(resampled["datetime"])
            out[code] = resampled.reset_index(drop=True)
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


def _warmup_bars_for(df: pd.DataFrame, period_start: str, base_warmup: int) -> int:
    """period_start 이전 봉을 warmup(지표계산용)으로 건너뛰도록 warmup_bars 산정.

    BookBacktester 는 `for i in range(warmup_bars, n-1)` 로 평가를 시작하므로,
    period_start 이전 봉 개수를 warmup_bars 로 주면 거래 평가는 period_start 이후 봉부터.
    단 최소 base_warmup 봉은 보장한다.
    """
    start_ts = pd.Timestamp(period_start)
    pre_count = int((df["datetime"] < start_ts).sum())
    return max(pre_count, base_warmup)


def _run_universe_with_warmup(
    book_mod,
    mode: str,
    rule_name,
    or_members,
    data: dict,
    period_start: str,
    args,
) -> UniverseBacktestResult:
    """종목별 warmup_bars(=period_start 이전 봉 수)로 run_single 후 집계.

    run_universe 와 동일 집계지만, 종목마다 period_start 위치가 달라서
    warmup_bars 를 per-stock 으로 지정해야 하므로 직접 루프.
    """
    per_stock = {}
    for code, df in data.items():
        wb = _warmup_bars_for(df, period_start, base_warmup=20)
        strategy = book_mod.build_strategy(mode=mode, target_rule=rule_name, or_members=or_members)
        bt = BookBacktester(
            strategy=strategy,
            initial_capital=args.initial_capital,
            warmup_bars=wb,
            stop_loss_pct=args.stop_loss_pct,
            take_profit_pct=args.take_profit_pct,
            max_hold_bars=args.max_hold_bars,
        )
        per_stock[code] = bt.run_single(code, df)

    n_stocks = len(per_stock)
    if n_stocks == 0:
        return UniverseBacktestResult(
            n_stocks=0, n_trades=0, pnl_pct=0.0, sharpe=0.0, calmar=0.0,
            sortino=0.0, max_dd_pct=0.0, hit_rate=0.0, avg_hold_bars=0.0,
        )

    pnls = np.array([r.pnl_pct for r in per_stock.values()])
    sharpes = np.array([r.sharpe for r in per_stock.values()])
    calmars = np.array([r.calmar for r in per_stock.values()])
    sortinos = np.array([r.sortino for r in per_stock.values()])
    dds = np.array([r.max_dd_pct for r in per_stock.values()])
    hits = np.array([r.hit_rate for r in per_stock.values()])
    holds = np.array([r.avg_hold_bars for r in per_stock.values()])
    trades_total = int(sum(r.n_trades for r in per_stock.values()))

    return UniverseBacktestResult(
        n_stocks=n_stocks,
        n_trades=trades_total,
        pnl_pct=float(pnls.mean()),
        sharpe=float(sharpes.mean()),
        calmar=float(calmars.mean()),
        sortino=float(sortinos.mean()),
        max_dd_pct=float(dds.mean()),
        hit_rate=float(hits.mean()),
        avg_hold_bars=float(holds.mean()),
        per_stock=per_stock,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--period", required=True, choices=list(PERIODS.keys()))
    p.add_argument("--mode", default=None, choices=["single", "all_AND", "top_K_OR"],
                   help="단일 mode 실행 시 지정. --all-modes 와 동시 사용 금지")
    p.add_argument("--rule", default="surge_fade", help="single 모드에서 규칙 이름 (기본 surge_fade)")
    p.add_argument("--or-members", default=None, help="top_K_OR 모드용 쉼표 구분 규칙 이름들")
    p.add_argument("--all-modes", action="store_true",
                   help="기간 1개 데이터를 1번 로드해서 모든 룰 single + all_AND 일괄 실행")
    p.add_argument("--limit", type=int, default=None, help="유니버스 N개로 제한 (디버그용)")
    p.add_argument("--initial-capital", type=float, default=10_000_000)
    p.add_argument("--reports-dir", default="reports/books_research")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--universe", default="top_volume:50",
                   help="유니버스 선택: 'top_volume:N' (기본 50) | 'all'")
    # 급등주 투매폭: 저점대비 +7% 익절 / 지지저점 이탈 손절 -4% (intraday → EOD 청산).
    p.add_argument("--stop-loss-pct", type=float, default=0.04)
    p.add_argument("--take-profit-pct", type=float, default=0.07)
    p.add_argument("--max-hold-bars", type=int, default=26,
                   help="15분봉 최대 보유 봉수 (intraday → EOD 청산 보조, 기본 26봉≈1거래일)")
    args = p.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.all_modes and args.mode is not None:
        p.error("--all-modes 와 --mode 는 동시 사용 불가")
    if not args.all_modes and args.mode is None:
        p.error("--mode 또는 --all-modes 둘 중 하나는 필수")

    start, end = PERIODS[args.period]
    load_start = (pd.Timestamp(start) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    LOG.info(
        f"period={args.period} ({start} ~ {end}) book={BOOK_ID} tf={TIMEFRAME_MINUTES}min "
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

    raw = _load_minute_data(universe, load_start, end)
    raw_bars = sum(len(df) for df in raw.values())
    data = _resample_15min(raw)
    total_bars = sum(len(df) for df in data.values())
    LOG.info(
        f"loaded 1min for {len(raw)} stocks ({raw_bars} bars) → "
        f"{TIMEFRAME_MINUTES}min for {len(data)} stocks ({total_bars} bars)"
    )

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
        agg = _run_universe_with_warmup(
            book_mod, mode, rule_name, or_members, data, start, args
        )

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
                "timeframe_minutes": TIMEFRAME_MINUTES,
            },
        )
    LOG.info(f"leaderboard updated: {leaderboard_path}")


if __name__ == "__main__":
    main()
