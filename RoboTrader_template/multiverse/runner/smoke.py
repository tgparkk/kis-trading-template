"""스모크 그리드 발사 — 4 페르소나 × ParamSet 변형으로 인프라 정합성 검증."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Callable, Literal

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.personas import (
    build_quant_strategy,
    build_swing_strategy,
    build_long_term_strategy,
    build_intraday_strategy,
)
from RoboTrader_template.multiverse.runner.grid_runner import (
    GridRunConfig,
    GridRunResult,
    run_grid,
)
from RoboTrader_template.multiverse.runner.report import write_markdown_report


PERSONA_BUILDERS: dict[str, Callable] = {
    "quant": build_quant_strategy,
    "swing": build_swing_strategy,
    "long_term": build_long_term_strategy,
    "intraday": build_intraday_strategy,
}


def expand_paramset_variants(base: ParamSet, n: int = 5) -> list[ParamSet]:
    """기준 ParamSet에서 n개 변형 생성 (tech_score_threshold 변경).

    n=5 → 5개 변형. 변경 축: tech_score_threshold ∈ {0.3, 0.4, 0.5, 0.6, 0.7} 중 n개.
    """
    thresholds = [0.3, 0.4, 0.5, 0.6, 0.7][:n]
    variants = [replace(base, tech_score_threshold=t) for t in thresholds]
    for v in variants:
        v.validate()
    return variants


def run_smoke(
    *,
    persona: Literal["quant", "swing", "long_term", "intraday"],
    base_paramset: ParamSet,
    candidate_symbols: list[str],
    start_date: date,
    end_date: date,
    output_dir: Path,
    n_variants: int = 5,
    initial_capital: float = 10_000_000.0,
) -> tuple[GridRunResult, Path]:
    """단일 페르소나 스모크 — N 변형 × 단일 윈도우(plain 모드).

    Returns (GridRunResult, markdown_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    paramsets = expand_paramset_variants(base_paramset, n=n_variants)
    builder = PERSONA_BUILDERS[persona]

    config = GridRunConfig(
        mode="plain",
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        candidate_symbols=candidate_symbols,
        output_dir=output_dir,
        n_jobs=1,  # 스모크는 디버깅 친화적으로 직렬
        primary_metric="calmar",
    )

    def _factory(ps: ParamSet) -> object:
        return builder(ps, candidate_symbols)

    result = run_grid(config=config, paramsets=paramsets, strategy_factory=_factory)
    md_path = write_markdown_report(result, top_n=n_variants)
    return result, md_path


def run_smoke_all_personas(
    *,
    base_paramset: ParamSet,
    candidate_symbols: list[str],
    start_date: date,
    end_date: date,
    output_dir: Path,
    n_variants: int = 5,
    initial_capital: float = 10_000_000.0,
) -> dict[str, tuple[GridRunResult, Path]]:
    """4 페르소나 모두 스모크 — 페르소나명 → (result, md_path)."""
    results = {}
    for persona in PERSONA_BUILDERS.keys():
        persona_dir = output_dir / persona
        results[persona] = run_smoke(
            persona=persona,
            base_paramset=base_paramset,
            candidate_symbols=candidate_symbols,
            start_date=start_date,
            end_date=end_date,
            output_dir=persona_dir,
            n_variants=n_variants,
            initial_capital=initial_capital,
        )
    return results
