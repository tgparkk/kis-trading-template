import numpy as np
import pandas as pd
from scripts.feature_edge.run_edge_lab import build_edge_table


def test_build_edge_table_ranks_features():
    rows = []
    rng = np.random.RandomState(0)
    for d in pd.date_range("2021-01-01", periods=40, freq="D"):
        for k in range(30):
            rows.append({"date": d, "stock_code": f"S{k}",
                         "good": float(k), "noise": rng.randn(),
                         "fwd_5d": float(k) * 0.001})
    panel = pd.DataFrame(rows)
    tbl = build_edge_table(panel, features=["good", "noise"], labels=["fwd_5d"])
    assert set(["feature", "label", "ic_mean", "ic_ir", "spread",
                "coverage", "bootstrap_p05", "oos_consistent"]).issubset(tbl.columns)
    good = tbl[(tbl.feature == "good") & (tbl.label == "fwd_5d")].iloc[0]
    noise = tbl[(tbl.feature == "noise") & (tbl.label == "fwd_5d")].iloc[0]
    assert good["ic_mean"] > noise["ic_mean"]
