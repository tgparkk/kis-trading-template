import pandas as pd
from pathlib import Path
from scripts.exit_multiverse import report


def test_build_grid_dataframe():
    fold_results = [{
        "fold": {"train_start": "2021-01-01", "train_end": "2023-01-01",
                 "test_start": "2023-01-01", "test_end": "2023-07-01"},
        "best": {"params": {"stop_loss_pct": 0.08, "take_profit_pct": 0.30,
                            "max_hold_bars": 100}, "worst_sharpe": 0.5, "dsr": 0.97,
                 "n_trades": 30},
        "all_results": [],
        "oos_worst_sharpe": 0.3, "oos_total_return": 0.12, "oos_n_trades": 8,
    }]
    df = report.build_fold_table(fold_results)
    assert "oos_total_return" in df.columns
    assert len(df) == 1


def test_param_stability_flag():
    best_params = [{"stop_loss_pct": 0.08}, {"stop_loss_pct": 0.06}, {"stop_loss_pct": 0.10}]
    assert report.param_stability(best_params)["stop_loss_pct"]["unstable"] is True
