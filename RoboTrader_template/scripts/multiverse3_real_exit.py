"""2차 멀티버스 Phase 3 — 진입필터를 **실청산(트레일링)** 드라이버에서 재검 (측정 전용).

배경:
  Phase 2 는 단순 sl/tp 드라이버(book_portfolio_multiverse)로 진입필터를 스윕해
  강건 개선 2건을 찾았다:
    - Book15 ma5_pullback + ma_slope 필터 (4윈도우 개선·약세장 양수전환·BULL보존)
    - Elder + mkt_rs 필터 (전 윈도우 일관 개선)
  그러나 단순 sl/tp 청산은 라이브 실청산(EMA13 트레일·ema65 추세반전, MA5 트레일)과
  다르다. 이 스크립트는 **동일 진입필터(scripts.entry_filters 재사용)를 실청산 위에서**
  재검해, 개선이 진짜 실청산에서도 유지되는지 측정한다.

★라이브 전략(strategies/*) 무수정. 측정 도구만. 진입필터 로직은 scripts.entry_filters
  의 apply_entry_filter 를 그대로 재사용(재구현 금지). filter='none' 이면 baseline 과
  바이트동일(회귀 안전).

실청산 경로 (둘 다 기존 부품 재사용):
  - Elder + mkt_rs : exit_multiverse.adapters.ADAPTERS["elder_ema_pullback"]
      = exit_kind="elder" → exits.exit_reason_elder (sl→tp→mh→EMA13 trail(수익중)→ema65 flip).
        portfolio_sim_elder.simulate_portfolio 의 _elder_exit_reason 과 1:1 동일 로직.
      entry_mechanism="stop" (Elder 매수스톱). K=20(라이브값).
  - ma5_pullback + ma_slope : exit_multiverse.adapters.ADAPTERS["book_pullback_ma5"]
      = exit_kind="simple_ma" → exits.exit_reason_simple_ma (sl→tp→mh→MA5 trail).
        라이브 book_pullback_ma5 = sl0.03/tp0.15/mh30/trail_ma5 와 일치. K=3.

흐름(전략·필터·윈도우마다):
  유니버스/데이터/turnover 로드(exit_multiverse.data_loader, top_volume:50)
  → 진입신호 캐시 1회(signals.precompute_entry_signals, no-lookahead)
  → apply_entry_filter(cache, filt) (no-lookahead, filt='none'면 그대로)
  → run_portfolio(filtered_cache, adapter=실청산, params=라이브청산값)
  → 메트릭(Sharpe/PnL/MaxDD/거래수). TSV 1행 append + per-run parquet.

no-lookahead:
  - 신호: window=df[:i+1] (precompute_entry_signals).
  - 필터: apply_entry_filter 의 모든 통계가 trailing(≤t). mkt_rs 는 진입봉 날짜 ≤t 의
    KOSPI 일수익률만 asof 매핑; ma_slope 는 종가>MA50 & MA50기울기>0 (rolling, ≤t).
  - 체결: run_portfolio 가 bar i 판정 → bar i+1 시가 체결.

usage:
  python scripts/multiverse3_real_exit.py --strategy elder_ema_pullback \
      --filters none mkt_rs --K 20 --window 2022 --out D:/tmp/multiverse3
  python scripts/multiverse3_real_exit.py --strategy book_pullback_ma5 \
      --filters none ma_slope --K 3 --window 2022 --out D:/tmp/multiverse3
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from scripts.exit_multiverse import adapters, data_loader, signals  # noqa: E402
from scripts.exit_multiverse.portfolio_sim import run_portfolio  # noqa: E402
from scripts.entry_filters import FILTER_CHOICES, apply_entry_filter  # noqa: E402

LOG = logging.getLogger("multiverse3_real_exit")

# 4국면창(KOSPI 실측) + FULL. run_elder_realexit.sh 윈도우 정의와 동일.
WINDOWS: Dict[str, tuple] = {
    "2021H2": ("2021-07-01", "2021-12-31"),
    "2022": ("2022-01-01", "2022-12-31"),
    "2024H2": ("2024-07-01", "2024-12-31"),
    "BULL": ("2025-06-01", "2026-05-27"),
    "FULL": ("2021-01-01", "2026-05-27"),
}

# 라이브 청산 파라미터 (전략별). strategies/* 무수정 — 여기서 값만 명시 복제.
#   elder: portfolio_sim_elder.ELDER_A_PARAMS 와 동일.
#   ma5  : strategies/book_pullback_ma5/config.yaml 과 동일(sl0.03/tp0.15/mh30/trail_ma5).
EXIT_PARAMS: Dict[str, dict] = {
    "elder_ema_pullback": dict(stop_loss_pct=0.08, take_profit_pct=0.30,
                               max_hold_bars=100, trail_ema=13, trend_flip_exit=True),
    "book_pullback_ma5": dict(stop_loss_pct=0.03, take_profit_pct=0.15,
                              max_hold_bars=30, trail_ma=5),
}

# 전략별 ma5_pullback 룰 타깃 (legends 일봉 묶음에서 ma5_pullback 만 단일룰로). adapters 가
# 이미 target_rule="ma5_pullback" / "triple_screen_ema_pullback" 로 빌드하므로 추가 불필요.


def _metrics(res: dict, initial: float) -> dict:
    """run_portfolio 결과 → Sharpe/PnL/MaxDD/Calmar/hit/거래수 (book_portfolio 와 동일 수식)."""
    eq = np.asarray(res["equity_curve"], dtype=float)
    if eq.size == 0:
        return dict(n_trades=0, pnl=0.0, sharpe=0.0, calmar=0.0, max_dd=0.0, hit=0.0,
                    max_concurrent=res.get("max_concurrent_positions", 0),
                    n_skipped=res.get("n_skipped", 0))
    pnl = (eq[-1] - initial) / initial
    rets = res["daily_returns"]
    rets = rets.to_numpy() if hasattr(rets, "to_numpy") else np.asarray(rets, dtype=float)
    rets = rets[np.isfinite(rets)]
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(-dd.min()) if len(dd) else 0.0
    calmar = float(pnl / max_dd) if max_dd > 1e-9 else 0.0
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    wins = sum(1 for t in sells if t["pnl_pct"] > 0)
    hit = wins / len(sells) if sells else 0.0
    return dict(n_trades=len(sells), pnl=pnl, sharpe=sharpe, calmar=calmar, max_dd=max_dd,
                hit=hit, max_concurrent=res.get("max_concurrent_positions", 0),
                n_skipped=res.get("n_skipped", 0))


def run_real_exit(
    strategy: str, filt: str, window: str, K: int,
    top_n: int = 50, max_per_stock: float = 3_000_000.0,
    initial_capital: float = 10_000_000.0,
    filter_threshold: float = 0.5, filter_n: int = 60,
    data: Optional[Dict[str, pd.DataFrame]] = None,
    turnover: Optional[Dict[str, float]] = None,
    kospi_close: Optional[pd.Series] = None,
    signal_cache: Optional[Dict[str, List[int]]] = None,
) -> dict:
    """단일 (strategy, filter, window, K) 실청산 평가.

    data/turnover/kospi_close/signal_cache 를 주입하면 재로딩·재계산을 생략(여러 필터·K가
    같은 윈도우 데이터·캐시를 공유). 미주입 시 DB 에서 로드.
    """
    if strategy not in adapters.ADAPTERS:
        raise ValueError(f"unknown strategy {strategy!r}. choices={list(adapters.ADAPTERS)}")
    if filt not in FILTER_CHOICES:
        raise ValueError(f"unknown filter {filt!r}. choices={FILTER_CHOICES}")
    start, end = WINDOWS[window]
    ad = adapters.ADAPTERS[strategy]

    if data is None:
        codes = data_loader.load_top_volume_universe(start, end, top_n)
        data = data_loader.load_daily_adj(codes, start, end)
    if turnover is None:
        turnover = data_loader.load_turnover_rank(start, end)
    if signal_cache is None:
        strat = ad.build_strategy()
        ctx_fn = ad.make_extra_ctx_fn(data)
        signal_cache = signals.precompute_entry_signals(data, strat, ad.warmup_bars, ctx_fn)
    if kospi_close is None and filt == "mkt_rs":
        kospi_close = data_loader.load_kospi_close(start, end)

    # 진입 필터(no-lookahead). filt='none' 이면 cache 그대로(동일 객체) → baseline 동등.
    fcache = apply_entry_filter(data, signal_cache, filt=filt,
                                threshold=filter_threshold, n=filter_n,
                                kospi_close=kospi_close)

    params = dict(EXIT_PARAMS[strategy])
    res = run_portfolio(
        data=data, signal_cache=fcache, adapter=ad, params=params,
        turnover=turnover, initial_capital=initial_capital,
        max_positions=K, max_per_stock=max_per_stock,
    )
    m = _metrics(res, initial_capital)
    m.update(dict(strategy=strategy, filter=filt, window=window, K=K,
                  start=start, end=end))
    return {"metrics": m, "result": res}


def main():
    p = argparse.ArgumentParser(description="Phase 3 실청산 진입필터 재검 (측정 전용)")
    p.add_argument("--strategy", required=True, choices=list(adapters.ADAPTERS.keys()))
    p.add_argument("--filters", nargs="+", default=["none"], choices=list(FILTER_CHOICES),
                   help="진입필터 차원(scripts.entry_filters). none=baseline(바이트동일).")
    p.add_argument("--K", type=int, required=True, help="max_positions (elder=20, ma5=3)")
    p.add_argument("--window", nargs="+", default=list(WINDOWS.keys()),
                   choices=list(WINDOWS.keys()))
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--max-per-stock", type=float, default=3_000_000.0, dest="max_per_stock")
    p.add_argument("--initial-capital", type=float, default=10_000_000.0, dest="initial_capital")
    p.add_argument("--filter-threshold", type=float, default=0.5, dest="filter_threshold")
    p.add_argument("--filter-n", type=int, default=60, dest="filter_n")
    p.add_argument("--out", default="D:/tmp/multiverse3")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    out_root = Path(args.out)
    rows: List[dict] = []
    ad = adapters.ADAPTERS[args.strategy]

    for window in args.window:
        start, end = WINDOWS[window]
        LOG.info(f"=== {args.strategy} | window={window} ({start}~{end}) | loading data ===")
        codes = data_loader.load_top_volume_universe(start, end, args.top_n)
        data = data_loader.load_daily_adj(codes, start, end)
        turnover = data_loader.load_turnover_rank(start, end)
        LOG.info(f"  universe={len(codes)} loaded_data={len(data)}")
        # 신호 캐시 1회 (필터·K 무관). no-lookahead.
        strat = ad.build_strategy()
        ctx_fn = ad.make_extra_ctx_fn(data)
        signal_cache = signals.precompute_entry_signals(data, strat, ad.warmup_bars, ctx_fn)
        n_sig = sum(len(v) for v in signal_cache.values())
        LOG.info(f"  signal bars (pre-filter) = {n_sig}")
        kospi_close = (data_loader.load_kospi_close(start, end)
                       if "mkt_rs" in args.filters else None)

        for filt in args.filters:
            r = run_real_exit(
                strategy=args.strategy, filt=filt, window=window, K=args.K,
                top_n=args.top_n, max_per_stock=args.max_per_stock,
                initial_capital=args.initial_capital,
                filter_threshold=args.filter_threshold, filter_n=args.filter_n,
                data=data, turnover=turnover, kospi_close=kospi_close,
                signal_cache=signal_cache,
            )
            m = r["metrics"]
            rows.append(m)
            # per-run 출력 디렉토리 (forward-slash) <out>/<strategy>/<filter>/<window>/
            run_dir = out_root / args.strategy / filt / window
            run_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(r["result"]["trades"]).to_parquet(run_dir / "trades.parquet", index=False)
            with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=2, default=str)
            LOG.info(f"  [{filt:>8}] K={args.K} Sharpe={m['sharpe']:.3f} PnL={m['pnl']:.4f} "
                     f"MaxDD={m['max_dd']:.2%} ntr={m['n_trades']} skip={m['n_skipped']}")

    # 통합 TSV (이 실행분)
    out_root.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    cols = ["strategy", "filter", "window", "K", "sharpe", "pnl", "max_dd",
            "calmar", "hit", "n_trades", "n_skipped", "max_concurrent", "start", "end"]
    df = df[[c for c in cols if c in df.columns]]
    tsv_path = out_root / f"realexit_{args.strategy}_K{args.K}.tsv"
    df.to_csv(tsv_path, sep="\t", index=False)
    LOG.info(f"TSV written: {tsv_path}")

    print(f"\n=== Phase 3 REAL-EXIT {args.strategy} K={args.K} ===")
    print(df.to_string(index=False))
    print(f"\nTSV: {tsv_path}")


if __name__ == "__main__":
    main()
