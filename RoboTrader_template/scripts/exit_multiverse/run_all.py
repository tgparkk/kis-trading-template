"""4전략 청산 멀티버스 병렬 오케스트레이터 + 종합 summary.

usage:
  python -m scripts.exit_multiverse.run_all --start 2021-01-01 --end 2026-05-29 \
      --top-n 50 --max-workers 4 --dsr-threshold 0.95
"""
from __future__ import annotations
import argparse, logging, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.exit_multiverse import run as run_mod
from scripts.exit_multiverse import adapters

LOG = logging.getLogger("exit_multiverse.run_all")

# 현재 라이브 운용 청산값 (summary 개선/유지 판정 기준 — 참고용 표기)
LIVE_PARAMS = {
    "elder_ema_pullback": {"stop_loss_pct": 0.08, "take_profit_pct": 0.30, "max_hold_bars": 100,
                           "trail_ema": 13, "trend_flip_exit": True},
    "minervini_volume_dryup": {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 20},
    "book_pullback_ma20": {"stop_loss_pct": 0.08, "take_profit_pct": 0.10, "max_hold_bars": 50, "trail_ma": 20},
    "book_pullback_ma5": {"stop_loss_pct": 0.03, "take_profit_pct": 0.15, "max_hold_bars": 30, "trail_ma": 5},
}


def _worker(kwargs):
    return run_mod.run_one(**kwargs)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2021-01-01")
    p.add_argument("--end", default="2026-05-29")
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--max-positions", type=int, default=5)
    p.add_argument("--max-per-stock", type=float, default=3_000_000)
    p.add_argument("--initial-capital", type=float, default=10_000_000)
    p.add_argument("--regime-threshold", type=float, default=0.02)
    p.add_argument("--dsr-threshold", type=float, default=0.95)
    p.add_argument("--reports-dir", default="reports/exit_optimization")
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    common = dict(start=args.start, end=args.end, top_n=args.top_n,
                  max_positions=args.max_positions, max_per_stock=args.max_per_stock,
                  initial_capital=args.initial_capital, regime_threshold=args.regime_threshold,
                  dsr_threshold=args.dsr_threshold, reports_dir=args.reports_dir)
    jobs = [dict(strategy=s, **common) for s in adapters.ADAPTERS.keys()]

    LOG.info(f"4전략 병렬 실행 (max_workers={args.max_workers})")
    with ProcessPoolExecutor(max_workers=args.max_workers) as ex:
        futs = {ex.submit(_worker, j): j["strategy"] for j in jobs}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                LOG.info(f"[{s}] 완료: {fut.result()}")
            except Exception as e:
                LOG.error(f"[{s}] 실패: {e!r}")

    _write_summary(Path(args.reports_dir), args.dsr_threshold)


def _write_summary(out_dir: Path, dsr_threshold: float):
    """4전략 grid.parquet 을 모아 OOS 종합 + 현재값 대비 개선/유지 판정."""
    rows = []
    for s in adapters.ADAPTERS.keys():
        pq = out_dir / f"{s}_grid.parquet"
        if not pq.exists():
            continue
        df = pd.read_parquet(pq)
        mean_oos = df["oos_worst_sharpe"].mean() if len(df) else 0.0
        mean_ret = df["oos_total_return"].mean() if len(df) else 0.0
        max_train_dsr = df["train_dsr"].max() if "train_dsr" in df and len(df) else 0.0
        verdict = ("개선 채택후보" if (mean_oos > 0 and max_train_dsr >= dsr_threshold)
                   else "기존값 유지(유의 개선 없음)")
        rows.append({"strategy": s, "mean_oos_worst_sharpe": mean_oos,
                     "mean_oos_return": mean_ret, "max_train_dsr": max_train_dsr,
                     "verdict": verdict})
    summary = pd.DataFrame(rows)
    try:
        table = summary.to_markdown(index=False) if len(summary) else "(결과 없음)"
    except Exception:
        table = "```\n" + (summary.to_string(index=False) if len(summary) else "(결과 없음)") + "\n```"
    md = ["# 선별 4전략 청산 멀티버스 — 종합 (OOS 기준)\n",
          f"> DSR 게이트 임계 = {dsr_threshold} (1급 0.95 / 과반 0.5)\n",
          table,
          "\n## 판정 규칙",
          "- **개선 채택후보**: 평균 OOS 국면최악 Sharpe > 0 **그리고** train DSR ≥ 임계",
          "- 그 외: **기존값 유지** (default to no-change)",
          "\n## 주의",
          "- 실제 trading_config.json/config.yaml 교체는 **별도 사장님 승인** 필요.",
          "- 폴드 간 파라미터 UNSTABLE 표기 전략은 채택 신중."]
    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    LOG.info(f"summary: {out_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
