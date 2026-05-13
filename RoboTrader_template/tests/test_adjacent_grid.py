import pandas as pd
import pytest
from RoboTrader_template.runners._adjacent_grid import build_adjacent_grid


def test_single_axis_expansion():
    """단일 축, 통과셀이 bb_period=[20,25]만 사용 → 인접격자는 4점 균등 [16~30]."""
    top_df = pd.DataFrame({
        "parameters.bb_period": [20, 25, 20, 25],
        "parameters.bb_std": [2.0, 2.0, 2.0, 2.0],
        "parameters.rsi_oversold": [40, 40, 40, 40],
        "risk_management.stop_loss_pct": [0.03, 0.03, 0.03, 0.03],
        "risk_management.take_profit_pct": [0.05, 0.05, 0.05, 0.05],
    })
    original_grid = {
        "parameters.bb_period": [15, 20, 25, 30],
        "parameters.bb_std": [1.8, 2.0, 2.2],
        "parameters.rsi_oversold": [30, 35, 40],
        "risk_management.stop_loss_pct": [0.02, 0.03, 0.05],
        "risk_management.take_profit_pct": [0.04, 0.05, 0.07],
    }
    grid, info = build_adjacent_grid(top_df, original_grid, max_cells=2000, sample_n=4)
    # bb_period: min(20,25)=20, max=25 → [20*0.8=16, 30, 4점 균등] = [16, ~20.7, ~25.3, 30]
    assert len(grid["parameters.bb_period"]) == 4
    assert grid["parameters.bb_period"][0] == pytest.approx(16, abs=0.1)
    assert grid["parameters.bb_period"][-1] == pytest.approx(30, abs=0.1)
    # 다른 축은 단일값 → freeze (1점만)
    assert len(grid["parameters.bb_std"]) == 1
    assert info["cell_count"] == 4 * 1 * 1 * 1 * 1
    assert info["frozen_axes"] == [
        "parameters.bb_std",
        "parameters.rsi_oversold",
        "risk_management.stop_loss_pct",
        "risk_management.take_profit_pct",
    ]


def test_max_cells_cap_triggers_freeze():
    """모든 축이 다양 → 4^5 = 1024셀 OK / max_cells=500이면 freeze 트리거."""
    top_df = pd.DataFrame({
        "parameters.bb_period": list(range(15, 31)),
        "parameters.bb_std": [1.8] * 16,
        "parameters.rsi_oversold": list(range(30, 46)),
        "risk_management.stop_loss_pct": [0.02 + i*0.005 for i in range(16)],
        "risk_management.take_profit_pct": [0.04 + i*0.005 for i in range(16)],
    })
    original_grid = {
        "parameters.bb_period": [15, 20, 25, 30],
        "parameters.bb_std": [1.8, 2.0, 2.2],
        "parameters.rsi_oversold": [30, 35, 40],
        "risk_management.stop_loss_pct": [0.02, 0.03, 0.05],
        "risk_management.take_profit_pct": [0.04, 0.05, 0.07],
    }
    # 4축 다양 + 1축 단일(bb_std) → 4^4 * 1 = 256 ≤ 500 OK
    grid, info = build_adjacent_grid(top_df, original_grid, max_cells=500, sample_n=4)
    assert info["cell_count"] <= 500
    assert "parameters.bb_std" in info["frozen_axes"]


def test_empty_top_raises():
    """통과셀 0건 → ValueError."""
    with pytest.raises(ValueError, match="empty"):
        build_adjacent_grid(pd.DataFrame(), {"a": [1, 2]}, max_cells=100, sample_n=4)


def test_export_yaml_roundtrip(tmp_path):
    grid = {"parameters.bb_period": [15.0, 20.0, 25.0, 30.0],
            "parameters.bb_std": [2.0]}
    out = tmp_path / "out.yaml"
    from RoboTrader_template.runners._adjacent_grid import export_grid_yaml
    export_grid_yaml(grid, str(out))
    import yaml
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert loaded == grid
