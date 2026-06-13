import numpy as np
import pandas as pd
from scripts.feature_edge.timing.run_timing_lab import build_timing_table


def test_build_timing_table_ranks_rules():
    base = pd.DataFrame({"date": pd.date_range("2025-03-01", periods=40),
                         "ret_net": [0.0]*40, "ret_gross": [0.0]*40})
    good = pd.DataFrame({"date": pd.date_range("2025-03-01", periods=40),
                         "ret_net": [0.03]*40, "ret_gross": [0.03]*40})
    tbl = build_timing_table({"good_rule": good}, base, split="2025-03-20")
    row = tbl[tbl.rule == "good_rule"].iloc[0]
    assert set(["rule", "alt_n", "delta_mean_net", "bootstrap_p05_net",
                "oos_consistent", "base_mean_net"]).issubset(tbl.columns)
    assert row["delta_mean_net"] > 0
