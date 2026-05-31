"""multiverse.runner — 그리드 + IS/OOS/WF Runner."""
from .dsr import deflated_sharpe_ratio, passes_dsr

try:
    from .grid_runner import (
        GridRunConfig,
        GridRunResult,
        run_grid,
        filter_passed_dsr,
        sort_by_primary_metric,
    )
    from .report import write_markdown_report
    from .smoke import (
        run_smoke,
        run_smoke_all_personas,
        expand_paramset_variants,
        PERSONA_BUILDERS,
    )
except ImportError:
    pass

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
