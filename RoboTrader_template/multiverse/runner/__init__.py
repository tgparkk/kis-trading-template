"""multiverse.runner — 그리드 + IS/OOS/WF Runner."""
from RoboTrader_template.multiverse.runner.dsr import deflated_sharpe_ratio, passes_dsr
from RoboTrader_template.multiverse.runner.grid_runner import (
    GridRunConfig,
    GridRunResult,
    run_grid,
    filter_passed_dsr,
    sort_by_primary_metric,
)
from RoboTrader_template.multiverse.runner.report import write_markdown_report
from RoboTrader_template.multiverse.runner.smoke import (
    run_smoke,
    run_smoke_all_personas,
    expand_paramset_variants,
    PERSONA_BUILDERS,
)

__all__ = [
    "deflated_sharpe_ratio", "passes_dsr",
    "GridRunConfig", "GridRunResult", "run_grid",
    "filter_passed_dsr", "sort_by_primary_metric",
    "write_markdown_report",
    "run_smoke",
    "run_smoke_all_personas",
    "expand_paramset_variants",
    "PERSONA_BUILDERS",
]
