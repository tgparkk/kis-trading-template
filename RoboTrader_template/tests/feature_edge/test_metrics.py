import numpy as np
import pandas as pd
from scripts.feature_edge.metrics import (
    daily_ic, tercile_expectancy, coverage, oos_sign_consistent,
)


def _panel():
    rows = []
    for d in pd.date_range("2021-01-01", periods=10, freq="D"):
        for k in range(20):
            rows.append({"date": d, "stock_code": f"S{k}", "f": float(k),
                         "y": float(k) + np.random.RandomState(k).randn() * 0.01})
    return pd.DataFrame(rows)


def test_daily_ic_positive_for_aligned_feature():
    p = _panel()
    ic = daily_ic(p, "f", "y")
    assert ic["ic_mean"] > 0.9
    assert "ic_ir" in ic


def test_tercile_expectancy_monotone():
    p = _panel()
    te = tercile_expectancy(p, "f", "y")
    assert te["top_mean"] > te["bottom_mean"]
    assert "spread" in te


def test_coverage_fraction():
    p = _panel()
    p.loc[p.index[:100], "f"] = np.nan
    cov = coverage(p, "f")
    assert 0.0 < cov < 1.0


def test_oos_sign_consistency():
    p = _panel()
    assert oos_sign_consistent(p, "f", "y", split="2021-01-05") is True
