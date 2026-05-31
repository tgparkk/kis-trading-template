"""단일 전략 청산 멀티버스 워크포워드 실행 CLI.

usage:
  python -m scripts.exit_multiverse.run --strategy elder_ema_pullback \
      --start 2021-01-01 --end 2026-05-29 --top-n 50 --max-positions 5 \
      --max-per-stock 3000000 --initial-capital 10000000 \
      --regime-threshold 0.02 --dsr-threshold 0.95 \
      --reports-dir reports/exit_optimization
"""
from __future__ import annotations
import argparse, logging, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.exit_multiverse import data_loader, signals, adapters, walkforward, report
from backtest.regime_analysis import classify_regime_rolling

LOG = logging.getLogger("exit_multiverse.run")


def run_one(strategy: str, start: str, end: str, top_n: int, max_positions: int,
            max_per_stock: float, initial_capital: float, regime_threshold: float,
            dsr_threshold: float, reports_dir: str) -> Path:
    ad = adapters.ADAPTERS[strategy]
    LOG.info(f"[{strategy}] universe/data 로드 (메모리 상주)")
    codes = data_loader.load_top_volume_universe(start, end, top_n)
    data = data_loader.load_daily_adj(codes, start, end)
    turnover = data_loader.load_turnover_rank(start, end)
    kospi = data_loader.load_kospi_close(start, end)
    regime_series = classify_regime_rolling(kospi, window=20, threshold=regime_threshold)

    LOG.info(f"[{strategy}] 진입 신호 사전계산 (그리드 무관, 1회)")
    strat = ad.build_strategy()
    ctx_fn = ad.make_extra_ctx_fn(data)
    signal_cache = signals.precompute_entry_signals(data, strat, ad.warmup_bars, ctx_fn)

    grid = ad.build_grid()
    folds = walkforward.make_folds(start, end, 24, 6, 6)
    LOG.info(f"[{strategy}] grid={len(grid)} folds={len(folds)} → 평가 시작")

    fold_results = []
    for fi, fold in enumerate(folds):
        fr = walkforward.evaluate_fold(
            fold=fold, data=data, signal_cache_full=signal_cache, adapter=ad,
            grid=grid, turnover=turnover, regime_series=regime_series,
            initial_capital=initial_capital, max_positions=max_positions,
            max_per_stock=max_per_stock)
        fold_results.append(fr)
        LOG.info(f"  fold{fi} {fold['test_start']}~{fold['test_end']}: "
                 f"OOS worst_sharpe={fr['oos_worst_sharpe']:.3f} "
                 f"OOS ret={fr['oos_total_return']:.2%} best_dsr={fr['best']['dsr']:.3f}")

    out_dir = Path(reports_dir)
    path = report.write_strategy_report(strategy, fold_results, out_dir)
    LOG.info(f"[{strategy}] 리포트: {path}")
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True, choices=list(adapters.ADAPTERS.keys()))
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2026-05-29")
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--max-positions", type=int, default=5)
    p.add_argument("--max-per-stock", type=float, default=3_000_000)
    p.add_argument("--initial-capital", type=float, default=10_000_000)
    p.add_argument("--regime-threshold", type=float, default=0.02)
    p.add_argument("--dsr-threshold", type=float, default=0.95)
    p.add_argument("--reports-dir", default="reports/exit_optimization")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_one(args.strategy, args.start, args.end, args.top_n, args.max_positions,
            args.max_per_stock, args.initial_capital, args.regime_threshold,
            args.dsr_threshold, args.reports_dir)


if __name__ == "__main__":
    main()
