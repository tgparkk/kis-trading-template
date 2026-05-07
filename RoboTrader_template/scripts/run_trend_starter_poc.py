"""Trend Starter PoC 실행 스크립트.

데이터 분석(2023~2026 4년) 결과 기반:
  F3 atr_ratio>=0.06 AND F1 vol_zscore_20>=1.5 → 양성률 11.76% (3.74x lift)
  교차검증 N=10에서도 11.21% 재현.

사용법:
  python scripts/run_trend_starter_poc.py
  python scripts/run_trend_starter_poc.py --start 2023-01-02 --end 2025-12-30 \\
      --top-n 30 --max-cells 100 --n-jobs 4
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# 헬퍼: KOSPI200 PIT 시총 상위 N
# ------------------------------------------------------------------ #

def _get_top_n_symbols(start: date, top_n: int) -> list[str]:
    """start 기준 KOSPI200 PIT 시총 상위 top_n 종목."""
    from RoboTrader_template.multiverse.data.kospi200_pit import get_kospi200_pit

    all_symbols = get_kospi200_pit(start)
    if not all_symbols:
        logger.warning("KOSPI200 PIT 결과 없음")
        return []
    symbols = all_symbols[:top_n]
    logger.info("KOSPI200 PIT 시총 상위 %d 종목 선택 (전체 %d)", len(symbols), len(all_symbols))
    return symbols


# ------------------------------------------------------------------ #
# 헬퍼: 결과 저장
# ------------------------------------------------------------------ #

def _save_results_csv(output_dir: Path, rows: list[dict]) -> Path:
    path = output_dir / "results.csv"
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames = sorted(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("results.csv 저장: %s (%d 행)", path, len(rows))
    return path


def _save_top5_md(output_dir: Path, rows: list[dict]) -> Path:
    """precision 상위 5개 셀 ParamSet 임계값 + 메트릭."""
    path = output_dir / "top5.md"
    sorted_rows = sorted(
        rows,
        key=lambda r: r.get("precision", r.get("m_precision", 0.0)),
        reverse=True,
    )
    top5 = sorted_rows[:5]

    lines = ["# Trend Starter PoC — precision 상위 5개 셀\n"]
    for i, r in enumerate(top5, 1):
        lines.append(f"## 셀 {i}: `{r.get('paramset_id', 'N/A')}`\n")
        lines.append("| 항목 | 값 |\n|------|----|\n")
        for key in (
            "m_precision", "m_expectancy", "m_sharpe", "m_calmar",
            "m_max_drawdown", "m_total_trades",
            "ts_atr_min", "ts_volz_min", "ts_box_min",
            "ts_target_pct", "ts_hold_days", "ts_stop_pct",
        ):
            val = r.get(key, "N/A")
            if isinstance(val, float):
                val = f"{val:.4f}"
            lines.append(f"| {key} | {val} |\n")
        lines.append("\n")
    path.write_text("".join(lines), encoding="utf-8")
    logger.info("top5.md 저장: %s", path)
    return path


def _save_summary_json(
    output_dir: Path,
    rows: list[dict],
    n_cells_requested: int,
    elapsed: float,
) -> Path:
    path = output_dir / "summary.json"
    n_cells = len(rows)
    precisions = [
        r.get("precision", r.get("m_precision", 0.0))
        for r in rows
        if r.get("precision") is not None or r.get("m_precision") is not None
    ]
    base_rate = sum(precisions) / len(precisions) if precisions else 0.0
    positive_cells = sum(1 for p in precisions if p > 0.10)

    summary = {
        "generated_at": datetime.now().isoformat(),
        "n_cells_requested": n_cells_requested,
        "n_cells_evaluated": n_cells,
        "positive_cells_precision_gt10pct": positive_cells,
        "mean_precision": round(base_rate, 4),
        "elapsed_seconds": round(elapsed, 1),
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info("summary.json 저장: %s", path)
    return path


# ------------------------------------------------------------------ #
# 메인 실행
# ------------------------------------------------------------------ #

def _run_poc(
    start: date,
    end: date,
    top_n: int,
    max_cells: int,
    n_jobs: int,
    output_dir: Path,
) -> None:
    from RoboTrader_template.multiverse.composable.personas._grid import (
        expand_grid_trend_starter,
    )
    from RoboTrader_template.multiverse.composable.personas import (
        build_trend_starter_strategy,
    )
    from RoboTrader_template.multiverse.runner.grid_runner import (
        GridRunConfig,
        run_grid,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # 메모리 사용량 기록
    try:
        import psutil
        _proc = psutil.Process()
        mem_start_mb = _proc.memory_info().rss / 1024 / 1024
        logger.info("시작 메모리: %.1f MB", mem_start_mb)
    except ImportError:
        _proc = None
        mem_start_mb = 0.0

    # 1) 후보 종목 조달
    logger.info("KOSPI200 PIT 시총 상위 %d 종목 조달 중...", top_n)
    candidate_symbols = _get_top_n_symbols(start, top_n)
    if not candidate_symbols:
        logger.error("후보 종목 없음 — 종료")
        sys.exit(1)

    # 2) 그리드 생성 + max_cells 랜덤 샘플링 (seed=42 고정, 다양성 보장)
    all_paramsets = expand_grid_trend_starter()
    import random as _random
    if len(all_paramsets) <= max_cells:
        paramsets = list(all_paramsets)
    else:
        paramsets = _random.Random(42).sample(all_paramsets, max_cells)
    logger.info(
        "ParamSet: 전체 %d → %d 랜덤샘플 (max_cells=%d, seed=42)",
        len(all_paramsets), len(paramsets), max_cells,
    )

    # 3) GridRunConfig + 클로저 (candidate_symbols 캡처 필수 — 5/3 에러 회피)
    config = GridRunConfig(
        mode="plain",
        start_date=start,
        end_date=end,
        initial_capital=10_000_000.0,  # 1천만원 (사장님 명시)
        candidate_symbols=candidate_symbols,
        output_dir=output_dir,
        n_jobs=n_jobs,
        primary_metric="calmar",
        universe_filter="all",
    )

    _syms = candidate_symbols  # 클로저 캡처 — candidate_symbols 누락 방지

    def _strategy_factory(ps):
        return build_trend_starter_strategy(ps, _syms)

    # 4) 그리드 실행
    logger.info(
        "PoC 그리드 실행 시작 — %d 셀, n_jobs=%d, %s~%s",
        len(paramsets), n_jobs, start, end,
    )
    t0 = time.monotonic()
    result = run_grid(config=config, paramsets=paramsets, strategy_factory=_strategy_factory)
    elapsed = time.monotonic() - t0

    logger.info(
        "PoC 완료 — %d 셀 평가, DSR 통과 %d, 소요 %.1fs",
        result.n_cells_evaluated,
        result.n_cells_passed_dsr,
        elapsed,
    )

    # 5) precision 분포 로그
    rows = result.rows
    if rows:
        precisions = sorted(
            [r.get("precision", r.get("m_precision", 0.0)) for r in rows
             if r.get("precision") is not None or r.get("m_precision") is not None],
            reverse=True,
        )
        if precisions:
            logger.info(
                "precision 분포: max=%.4f median=%.4f min=%.4f",
                precisions[0],
                precisions[len(precisions) // 2],
                precisions[-1],
            )
        else:
            logger.info("precision 컬럼 없음 — 모든 셀에서 0건 거래")

    # 6) 결과 저장
    _save_results_csv(output_dir, rows)
    _save_top5_md(output_dir, rows)
    _save_summary_json(output_dir, rows, len(paramsets), elapsed)

    # 7) 메모리 기록
    if _proc is not None:
        mem_end_mb = _proc.memory_info().rss / 1024 / 1024
        logger.info(
            "종료 메모리: %.1f MB (증가: %.1f MB)",
            mem_end_mb, mem_end_mb - mem_start_mb,
        )

    logger.info("출력 디렉토리: %s", output_dir)


# ------------------------------------------------------------------ #
# CLI 진입점
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trend Starter PoC: KOSPI200 PIT 시총 상위 N 종목 × 그리드",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--start", default="2023-01-02", help="백테스트 시작일 YYYY-MM-DD")
    parser.add_argument("--end", default="2025-12-30", help="백테스트 종료일 YYYY-MM-DD")
    parser.add_argument("--top-n", type=int, default=30, help="KOSPI200 PIT 시총 상위 N 종목")
    parser.add_argument("--max-cells", type=int, default=100, help="실행할 최대 셀 수 (슬라이싱)")
    parser.add_argument("--n-jobs", type=int, default=4, help="병렬 worker 수")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="결과 저장 디렉토리 (미지정 시 output/multiverse_trend_starter_poc_<timestamp>/)",
    )

    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(__file__).resolve().parent.parent / "output"
        output_dir = base / f"multiverse_trend_starter_poc_{ts}"

    logger.info(
        "Trend Starter PoC 시작 — start=%s end=%s top_n=%d max_cells=%d n_jobs=%d",
        start, end, args.top_n, args.max_cells, args.n_jobs,
    )

    _run_poc(
        start=start,
        end=end,
        top_n=args.top_n,
        max_cells=args.max_cells,
        n_jobs=args.n_jobs,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    main()
