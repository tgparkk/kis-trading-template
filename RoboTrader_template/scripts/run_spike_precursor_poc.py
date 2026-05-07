"""Spike Precursor PoC 실행 스크립트.

사용법:
  python scripts/run_spike_precursor_poc.py
  python scripts/run_spike_precursor_poc.py --start 2025-01-02 --end 2025-12-30 --top-n 30 --max-cells 100
"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (RoboTrader_template 패키지 import 가능하게)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import argparse
import csv
import json
import logging
import time
from datetime import date, datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# 헬퍼: KOSPI200 PIT 중 시총 상위 N 종목
# ------------------------------------------------------------------ #

def _get_top_n_symbols(start: date, top_n: int) -> list[str]:
    """start 기준 KOSPI200 PIT 에서 시총 상위 top_n 종목 반환.

    kospi200_pit.get_kospi200_pit()는 이미 시총 내림차순 정렬된 리스트를 반환하므로
    슬라이싱만으로 충분하다.
    """
    from RoboTrader_template.multiverse.data.kospi200_pit import get_kospi200_pit

    all_symbols = get_kospi200_pit(start)
    if not all_symbols:
        logger.warning("KOSPI200 PIT 결과 없음 — 전체 리스트 사용 시도")
        return []
    symbols = all_symbols[:top_n]
    logger.info("KOSPI200 PIT 시총 상위 %d 종목 선택 (전체 %d)", len(symbols), len(all_symbols))
    return symbols


# ------------------------------------------------------------------ #
# 헬퍼: 결과 저장
# ------------------------------------------------------------------ #

def _save_results_csv(output_dir: Path, rows: list[dict]) -> Path:
    """셀별 메트릭을 results.csv 로 저장."""
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
    """precision 상위 5개 셀의 ParamSet 임계값 + 메트릭을 top5.md 로 저장."""
    path = output_dir / "top5.md"

    sorted_rows = sorted(
        rows,
        key=lambda r: r.get("precision", r.get("m_precision", 0.0)),
        reverse=True,
    )
    top5 = sorted_rows[:5]

    lines = ["# Spike Precursor PoC — precision 상위 5개 셀\n"]
    for i, r in enumerate(top5, 1):
        lines.append(f"## 셀 {i}: `{r.get('paramset_id', 'N/A')}`\n")
        lines.append("| 항목 | 값 |\n|------|----|\n")
        for key in (
            "m_precision", "m_expectancy", "m_sharpe", "m_calmar",
            "m_max_drawdown", "m_total_trades",
            "spike_vol_z_thresh", "spike_atr_max", "spike_box_max",
            "spike_vol_trend_min", "spike_match_min",
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
    """전체 요약을 summary.json 으로 저장."""
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
# 메인 실행 로직
# ------------------------------------------------------------------ #

def _run_poc(
    start: date,
    end: date,
    top_n: int,
    max_cells: int,
    n_jobs: int,
    output_dir: Path,
    persona_mode: str = "normal",
) -> None:
    """PoC 실행 핵심 로직.

    Parameters
    ----------
    persona_mode:
        "normal"  : 원본 spike_precursor (고거래량/고점 진입)
        "inverse" : 반전 spike_precursor_inverse (거래량 침체/MA20 아래/좁은 박스)
    """
    from RoboTrader_template.multiverse.composable.personas._grid import (
        expand_grid_spike_precursor,
        expand_grid_spike_precursor_inverse,
    )
    from RoboTrader_template.multiverse.composable.personas import (
        build_spike_precursor_strategy,
        build_spike_precursor_inverse_strategy,
    )
    from RoboTrader_template.multiverse.runner.grid_runner import (
        GridRunConfig,
        run_grid,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # 모드 선택
    if persona_mode == "inverse":
        _expand_fn = expand_grid_spike_precursor_inverse
        _build_fn = build_spike_precursor_inverse_strategy
        logger.info("페르소나 모드: inverse (반전 가설 — 거래량 침체·MA20 아래)")
    else:
        _expand_fn = expand_grid_spike_precursor
        _build_fn = build_spike_precursor_strategy
        logger.info("페르소나 모드: normal (원본 — 고거래량·고점 진입)")

    # 메모리 사용량 기록 (psutil 있으면)
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

    # 2) 그리드 생성 + max_cells 슬라이싱
    all_paramsets = _expand_fn()
    paramsets = all_paramsets[:max_cells]
    logger.info(
        "ParamSet: 전체 %d → %d 슬라이싱 (max_cells=%d)",
        len(all_paramsets), len(paramsets), max_cells,
    )

    # 3) GridRunConfig + strategy_factory 클로저 (candidate_symbols 캡처 필수)
    config = GridRunConfig(
        mode="plain",
        start_date=start,
        end_date=end,
        initial_capital=100_000_000.0,
        candidate_symbols=candidate_symbols,
        output_dir=output_dir,
        n_jobs=n_jobs,
        primary_metric="calmar",
        universe_filter="all",
    )

    _syms = candidate_symbols  # 클로저 캡처 — candidate_symbols 누락 방지

    def _strategy_factory(ps):
        return _build_fn(ps, _syms)

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

    # 5) 진행률 로그에 precision 분포 간략 출력
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
            logger.info("precision 컬럼 없음 — 모든 셀에서 0건 거래 또는 컬럼 미포함")

    # 6) 결과 저장
    _save_results_csv(output_dir, rows)
    _save_top5_md(output_dir, rows)
    _save_summary_json(output_dir, rows, len(paramsets), elapsed)

    # 7) 최종 메모리 기록
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
        description="Spike Precursor PoC: KOSPI200 PIT 시총 상위 N 종목 × 100셀 그리드",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--start", default="2025-01-02", help="백테스트 시작일 YYYY-MM-DD")
    parser.add_argument("--end", default="2025-12-30", help="백테스트 종료일 YYYY-MM-DD")
    parser.add_argument("--top-n", type=int, default=30, help="KOSPI200 PIT 시총 상위 N 종목")
    parser.add_argument("--max-cells", type=int, default=100, help="실행할 최대 셀 수 (슬라이싱)")
    parser.add_argument("--n-jobs", type=int, default=1, help="병렬 worker 수 (게임 중 1 권장)")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="결과 저장 디렉토리 (미지정 시 output/multiverse_spike_poc_<timestamp>/)",
    )
    parser.add_argument(
        "--mode",
        default="normal",
        choices=["normal", "inverse"],
        help="페르소나 모드: normal=원본(고거래량), inverse=반전(거래량침체/MA20아래/좁은박스)",
    )

    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 스크립트 위치 기준 상위 디렉토리(RoboTrader_template)의 output/
        base = Path(__file__).resolve().parent.parent / "output"
        output_dir = base / f"multiverse_spike_poc_{args.mode}_{ts}"

    logger.info(
        "Spike Precursor PoC 시작 — start=%s end=%s top_n=%d max_cells=%d n_jobs=%d mode=%s",
        start, end, args.top_n, args.max_cells, args.n_jobs, args.mode,
    )

    _run_poc(
        start=start,
        end=end,
        top_n=args.top_n,
        max_cells=args.max_cells,
        n_jobs=args.n_jobs,
        output_dir=output_dir,
        persona_mode=args.mode,
    )


if __name__ == "__main__":
    main()
