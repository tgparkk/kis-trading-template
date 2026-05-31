import pytest
from pathlib import Path
from scripts.exit_multiverse import run


@pytest.mark.slow
def test_run_one_ma5_smoke(tmp_path):
    # 2021-01-01 ~ 2024-06-30 = 42개월 → train24/test6/step6 기준 3폴드 생성
    path = run.run_one(
        strategy="book_pullback_ma5", start="2021-01-01", end="2024-06-30",
        top_n=10, max_positions=5, max_per_stock=3_000_000,
        initial_capital=10_000_000, regime_threshold=0.02, dsr_threshold=0.95,
        reports_dir=str(tmp_path))
    assert path.exists()
    assert (tmp_path / "book_pullback_ma5_grid.parquet").exists()
    # 폴드가 실제 평가됐는지 확인 (parquet에 행이 있어야 함)
    import pandas as pd
    df = pd.read_parquet(tmp_path / "book_pullback_ma5_grid.parquet")
    assert len(df) >= 1, "폴드 평가 결과가 없음 — 기간이 너무 짧거나 폴드 생성 실패"
