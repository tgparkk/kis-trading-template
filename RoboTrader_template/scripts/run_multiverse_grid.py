"""G2 멀티버스 그리드 백테스트 CLI 러너.

사용 예:
    python -m RoboTrader_template.scripts.run_multiverse_grid \
      --persona all --universe kospi200_pit \
      --start 2021-01-12 --end 2026-04-30 \
      --mode plain --n-jobs 8 \
      --output RoboTrader_template/output/multiverse_grid_XXX/

모드:
  plain       — 단일 IS 구간 백테스트
  oos_split   — IS/OOS 자동 분리 (--is-ratio)
  walkforward — rolling 윈도우 (--n-windows, --is-window-days, --oos-window-days)
"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트 + RoboTrader_template 디렉토리를 sys.path에 추가
# - _PROJECT_ROOT: RoboTrader_template 패키지 import용 (from RoboTrader_template.xxx)
# - _PKG_ROOT: 내부 bare import용 (from utils.logger, from config.xxx 등)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PKG_ROOT = _PROJECT_ROOT / "RoboTrader_template"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PKG_ROOT))

import argparse
import json
import logging
import time
from datetime import date, datetime
from typing import Callable

# Windows cp949 환경에서 em-dash 등 Unicode 문자 로깅 시 UnicodeEncodeError 방지
# Python 3.7+ sys.stdout.reconfigure 사용; errors='replace'로 실패해도 프로세스 유지
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# 페르소나 → (expand_grid 함수, strategy_factory 함수) 매핑
# ------------------------------------------------------------------ #

def _get_persona_registry() -> dict[str, tuple[Callable, Callable]]:
    from RoboTrader_template.multiverse.composable.personas._grid import (
        expand_grid_quant,
        expand_grid_long_term,
        expand_grid_swing,
        expand_grid_intraday,
        expand_grid_spike_precursor,
        expand_grid_trend_starter,
    )
    from RoboTrader_template.multiverse.composable.personas import (
        build_quant_strategy,
        build_long_term_strategy,
        build_swing_strategy,
        build_intraday_strategy,
        build_spike_precursor_strategy,
        build_trend_starter_strategy,
    )
    return {
        "quant":            (expand_grid_quant,            build_quant_strategy),
        "long_term":        (expand_grid_long_term,        build_long_term_strategy),
        "swing":            (expand_grid_swing,            build_swing_strategy),
        "intraday":         (expand_grid_intraday,         build_intraday_strategy),
        "spike_precursor":  (expand_grid_spike_precursor,  build_spike_precursor_strategy),
        "trend_starter":    (expand_grid_trend_starter,    build_trend_starter_strategy),
    }


# ------------------------------------------------------------------ #
# candidate_symbols 조달
# ------------------------------------------------------------------ #

def _get_candidate_symbols(universe: str, start: date, end: date) -> list[str]:
    """universe 방식에 따라 후보 종목 코드 리스트 반환."""
    if universe == "kospi200_pit":
        from RoboTrader_template.multiverse.data.kospi200_pit import get_kospi200_pit
        # 시작일 기준 KOSPI200 — 전 기간 커버를 위해 start 시점 기준 200개 사용
        # 실제 PIT 필터는 portfolio_engine 리밸런싱 루프에서 매 거래일 적용됨
        symbols = get_kospi200_pit(start)
        logger.info("KOSPI200 PIT 후보풀: %d 종목 (기준일 %s)", len(symbols), start)
        return symbols
    else:
        raise ValueError(f"알 수 없는 universe: {universe!r}. 현재 지원: kospi200_pit")


# ------------------------------------------------------------------ #
# 페르소나별 그리드 실행
# ------------------------------------------------------------------ #

def _run_persona(
    persona_name: str,
    expand_fn: Callable,
    factory_fn: Callable,
    candidate_symbols: list[str],
    start: date,
    end: date,
    mode: str,
    is_ratio: float,
    n_windows: int,
    is_window_days: int,
    oos_window_days: int,
    n_jobs: int,
    output_dir: Path,
    universe: str,
    paramset_input: Path | None,
) -> dict:
    """단일 페르소나 그리드 실행 후 요약 dict 반환."""
    from RoboTrader_template.multiverse.runner.grid_runner import GridRunConfig, run_grid

    persona_out = output_dir / persona_name
    persona_out.mkdir(parents=True, exist_ok=True)

    # ParamSet 리스트 확보
    if paramset_input is not None:
        logger.info("[%s] --paramset-input %s 로드 중...", persona_name, paramset_input)
        from RoboTrader_template.multiverse.composable.paramset import ParamSet
        with paramset_input.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        paramsets = [ParamSet.from_dict(d) for d in raw]
        logger.info("[%s] %d ParamSet 로드 완료", persona_name, len(paramsets))
    else:
        paramsets = expand_fn()
        logger.info("[%s] expand_grid: %d ParamSet", persona_name, len(paramsets))

    if not paramsets:
        logger.warning("[%s] ParamSet 0개 — 스킵", persona_name)
        return {"persona": persona_name, "n_paramsets": 0, "skipped": True}

    config = GridRunConfig(
        mode=mode,
        start_date=start,
        end_date=end,
        initial_capital=100_000_000.0,
        candidate_symbols=candidate_symbols,
        output_dir=persona_out,
        n_jobs=n_jobs,
        is_ratio=is_ratio,
        is_window_days=is_window_days,
        oos_window_days=oos_window_days,
        n_windows=n_windows,
        universe_filter=universe,
    )

    # factory_fn(paramset, candidate_symbols) → grid_runner은 factory(paramset) 단일 인자 호출
    # 클로저로 candidate_symbols 캡처
    _syms = candidate_symbols  # closure capture
    def _strategy_factory(ps):
        return factory_fn(ps, _syms)

    t0 = time.monotonic()
    logger.info(
        "[%s] 그리드 시작 — %d 셀, mode=%s, n_jobs=%d, %s~%s",
        persona_name, len(paramsets), mode, n_jobs, start, end,
    )

    result = run_grid(
        config=config,
        paramsets=paramsets,
        strategy_factory=_strategy_factory,
    )

    elapsed = time.monotonic() - t0
    n_cells = result.n_cells_evaluated
    avg_sec = elapsed / n_cells if n_cells > 0 else 0.0

    logger.info(
        "[%s] 완료 — %d 셀 평가, DSR 통과 %d, 소요 %.1fs (셀당 %.2fs), 저장: %s",
        persona_name,
        n_cells,
        result.n_cells_passed_dsr,
        elapsed,
        avg_sec,
        result.parquet_path,
    )

    return {
        "persona": persona_name,
        "n_paramsets": len(paramsets),
        "n_cells_evaluated": n_cells,
        "n_cells_passed_dsr": result.n_cells_passed_dsr,
        "elapsed_seconds": round(elapsed, 1),
        "avg_seconds_per_cell": round(avg_sec, 2),
        "parquet_path": str(result.parquet_path),
    }


# ------------------------------------------------------------------ #
# CLI 진입점
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="G2 멀티버스 그리드 백테스트 CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--persona",
        choices=["quant", "long_term", "swing", "intraday", "spike_precursor", "trend_starter", "all"],
        default="all",
        help="실행할 페르소나 (all = 6개 모두)",
    )
    parser.add_argument(
        "--universe",
        default="kospi200_pit",
        help="유니버스 필터 (현재: kospi200_pit)",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="백테스트 시작일 YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="백테스트 종료일 YYYY-MM-DD",
    )
    parser.add_argument(
        "--mode",
        choices=["plain", "oos_split", "walkforward"],
        default="plain",
        help="백테스트 모드",
    )
    parser.add_argument(
        "--is-ratio",
        type=float,
        default=0.7,
        help="oos_split 모드 IS 비율",
    )
    parser.add_argument(
        "--n-windows",
        type=int,
        default=6,
        help="walkforward 윈도우 수",
    )
    parser.add_argument(
        "--is-window-days",
        type=int,
        default=252,
        help="walkforward IS 윈도우 거래일 수",
    )
    parser.add_argument(
        "--oos-window-days",
        type=int,
        default=63,
        help="walkforward OOS 윈도우 거래일 수",
    )
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=8,
        help="병렬 worker 수",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="결과 저장 디렉토리 (페르소나별 서브디렉토리 자동 생성)",
    )
    parser.add_argument(
        "--paramset-input",
        default=None,
        help="외부 ParamSet JSON 파일 경로 (2차 단계용 — 미지정 시 expand_grid 사용)",
    )

    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    paramset_input = Path(args.paramset_input) if args.paramset_input else None

    registry = _get_persona_registry()

    if args.persona == "all":
        target_personas = list(registry.keys())
    else:
        target_personas = [args.persona]

    logger.info(
        "=== G2 멀티버스 그리드 시작 === 페르소나: %s | 기간: %s~%s | 모드: %s | n_jobs: %d",
        target_personas, start, end, args.mode, args.n_jobs,
    )
    run_start = datetime.now()

    # 후보풀 1회 조달 (전 페르소나 공유)
    candidate_symbols = _get_candidate_symbols(args.universe, start, end)

    summaries = []
    for persona_name in target_personas:
        expand_fn, factory_fn = registry[persona_name]
        summary = _run_persona(
            persona_name=persona_name,
            expand_fn=expand_fn,
            factory_fn=factory_fn,
            candidate_symbols=candidate_symbols,
            start=start,
            end=end,
            mode=args.mode,
            is_ratio=args.is_ratio,
            n_windows=args.n_windows,
            is_window_days=args.is_window_days,
            oos_window_days=args.oos_window_days,
            n_jobs=args.n_jobs,
            output_dir=output_dir,
            universe=args.universe,
            paramset_input=paramset_input,
        )
        summaries.append(summary)

    total_elapsed = (datetime.now() - run_start).total_seconds()

    # 요약 리포트 출력
    print("\n" + "=" * 60)
    print("G2 그리드 완료 요약")
    print("=" * 60)
    for s in summaries:
        if s.get("skipped"):
            print(f"  {s['persona']:12s}  SKIPPED (ParamSet 0개)")
        else:
            print(
                f"  {s['persona']:12s}  "
                f"셀={s['n_cells_evaluated']:4d}  "
                f"DSR통과={s['n_cells_passed_dsr']:4d}  "
                f"소요={s['elapsed_seconds']:7.1f}s  "
                f"셀당={s['avg_seconds_per_cell']:.2f}s"
            )
            print(f"    -> {s['parquet_path']}")
    print(f"\n전체 소요 시간: {total_elapsed:.1f}s ({total_elapsed/3600:.2f}h)")
    print(f"시작: {run_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 요약 JSON 저장
    summary_path = output_dir / "grid_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "started_at": run_start.isoformat(),
                "finished_at": datetime.now().isoformat(),
                "total_elapsed_seconds": round(total_elapsed, 1),
                "args": vars(args),
                "personas": summaries,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    logger.info("요약 저장: %s", summary_path)


if __name__ == "__main__":
    main()
