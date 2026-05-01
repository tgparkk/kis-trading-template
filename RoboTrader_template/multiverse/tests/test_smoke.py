"""스모크 그리드 인프라 정합성 테스트 — mock 기반 (실제 DB 불필요)."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from RoboTrader_template.multiverse.engine.portfolio_engine import PortfolioBacktestResult
from RoboTrader_template.multiverse.runner.smoke import (
    expand_paramset_variants,
    run_smoke,
    run_smoke_all_personas,
)


@pytest.fixture
def mock_pbr() -> PortfolioBacktestResult:
    """최소 유효 PortfolioBacktestResult — 메트릭 계산에 충분한 300일 시계열."""
    days = 300
    start = date(2025, 1, 1)
    equity = [(start + timedelta(days=i), 10_000_000.0 * (1 + 0.001 * i)) for i in range(days)]
    return PortfolioBacktestResult(
        start_date=equity[0][0],
        end_date=equity[-1][0],
        initial_capital=10_000_000.0,
        final_equity=equity[-1][1],
        daily_equity=equity,
        trades=[],
        skipped_signals=[],
        rebalance_dates=[],
        paramset_id="mock",
        paused_until=None,
    )


def test_expand_paramset_variants(valid_paramset):
    """n=5 변형 생성 — 개수 및 고유성 검증."""
    variants = expand_paramset_variants(valid_paramset, n=5)
    assert len(variants) == 5
    thresholds = {v.tech_score_threshold for v in variants}
    assert len(thresholds) == 5  # 모두 다른 값


def test_run_smoke_quant_creates_outputs(tmp_path, valid_paramset, mock_pbr):
    """단일 페르소나 스모크 — Parquet + Markdown 둘 다 생성."""
    with patch(
        "RoboTrader_template.multiverse.runner.grid_runner.run_portfolio_backtest",
        return_value=mock_pbr,
    ):
        result, md = run_smoke(
            persona="quant",
            base_paramset=valid_paramset,
            candidate_symbols=["005930", "000660"],
            start_date=date(2025, 1, 1),
            end_date=date(2026, 1, 1),
            output_dir=tmp_path,
            n_variants=3,
        )
    assert result.n_cells_evaluated == 3
    assert result.parquet_path.exists()
    assert md.exists()
    assert "Multiverse Report" in md.read_text(encoding="utf-8")


def test_run_smoke_all_personas(tmp_path, valid_paramset, mock_pbr):
    """4 페르소나 모두 동일 절차로 결과 생성."""
    with patch(
        "RoboTrader_template.multiverse.runner.grid_runner.run_portfolio_backtest",
        return_value=mock_pbr,
    ):
        results = run_smoke_all_personas(
            base_paramset=valid_paramset,
            candidate_symbols=["005930"],
            start_date=date(2025, 1, 1),
            end_date=date(2026, 1, 1),
            output_dir=tmp_path,
            n_variants=2,
        )
    assert set(results.keys()) == {"quant", "swing", "long_term", "intraday"}
    for persona, (result, md) in results.items():
        assert result.n_cells_evaluated == 2
        assert md.exists()
