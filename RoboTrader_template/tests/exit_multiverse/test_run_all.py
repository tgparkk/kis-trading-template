import pandas as pd
from pathlib import Path
from scripts.exit_multiverse import run_all


def test_write_summary_from_fake_parquet(tmp_path):
    for s in run_all.adapters.ADAPTERS.keys():
        pd.DataFrame({"oos_worst_sharpe": [0.3, 0.4], "oos_total_return": [0.1, 0.05],
                      "train_dsr": [0.96, 0.5]}).to_parquet(tmp_path / f"{s}_grid.parquet")
    run_all._write_summary(tmp_path, dsr_threshold=0.95)
    assert (tmp_path / "summary.md").exists()
    txt = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "개선 채택후보" in txt or "기존값 유지" in txt
