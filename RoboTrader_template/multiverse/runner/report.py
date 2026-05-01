"""Markdown 요약 리포트 생성."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from RoboTrader_template.multiverse.runner.grid_runner import (
    GridRunResult,
    sort_by_primary_metric,
)


def write_markdown_report(
    grid_result: GridRunResult,
    output_path: Path | None = None,
    top_n: int = 20,
) -> Path:
    """그리드 결과를 Markdown으로 요약.

    구조:
      # Multiverse Report (mode, 날짜)
      ## 요약 — 셀 수 / DSR 통과 수 / 평균 지표
      ## 상위 N (1급 정렬, DSR 통과 우선)
      ## 1급 미통과 상위 5 (참고용)
      ## 메타 — 실행 시간 / Parquet 경로 / 파라미터셋 수
    """
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = (
            grid_result.config.output_dir
            / f"multiverse_report_{grid_result.config.mode}_{ts}.md"
        )

    rows = grid_result.rows
    sorted_rows = sort_by_primary_metric(rows, grid_result.config.primary_metric)
    passed = [r for r in sorted_rows if r.get("m_passes_dsr")]
    failed = [r for r in sorted_rows if not r.get("m_passes_dsr")]

    lines = [
        f"# Multiverse Report — {grid_result.config.mode}",
        f"",
        f"실행: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        "## 요약",
        f"- 평가된 셀: {grid_result.n_cells_evaluated}",
        f"- DSR 통과(≥{grid_result.config.dsr_threshold}): {grid_result.n_cells_passed_dsr}",
        f"- 1급 정렬 키: {grid_result.config.primary_metric}",
        f"- Parquet: `{grid_result.parquet_path}`",
        "",
        f"## 상위 {min(top_n, len(passed))} (DSR 통과)",
        "",
        "| 순위 | paramset_id | mode | window | calmar | sharpe | mdd | cagr | dsr |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(passed[:top_n], 1):
        lines.append(
            f"| {i} | `{str(r.get('paramset_id', ''))[:8]}` | {r.get('mode')} "
            f"| {r.get('window_idx')} | {r.get('m_calmar', 0.0):.3f} "
            f"| {r.get('m_sharpe', 0.0):.3f} | {r.get('m_mdd', 0.0):.3f} "
            f"| {r.get('m_cagr', 0.0):.3f} | {r.get('m_dsr', 0.0):.3f} |"
        )

    if failed:
        lines += [
            "",
            "## 참고 — 1급 미통과 상위 5",
            "",
            "| paramset_id | calmar | sharpe | dsr |",
            "|---|---|---|---|",
        ]
        for r in failed[:5]:
            lines.append(
                f"| `{str(r.get('paramset_id', ''))[:8]}` "
                f"| {r.get('m_calmar', 0.0):.3f} | {r.get('m_sharpe', 0.0):.3f} "
                f"| {r.get('m_dsr', 0.0):.3f} |"
            )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
