import numpy as np
import pandas as pd
from scripts.feature_edge.timing.timing_metrics import (
    summarize_trades, delta_vs_baseline, bootstrap_delta_p05)


def _trades(rets, dates=None):
    n = len(rets)
    dates = dates or pd.date_range("2025-03-01", periods=n, freq="D")
    return pd.DataFrame({"date": dates, "ret_net": rets, "ret_gross": rets})


def test_summarize_trades_basic():
    s = summarize_trades(_trades([0.1, -0.05, 0.2, -0.1]), col="ret_net")
    assert np.isclose(s["mean"], 0.0375, atol=1e-6)
    assert np.isclose(s["hit_rate"], 0.5)
    assert s["n"] == 4


def test_delta_positive_when_alt_better():
    base = _trades([0.0, 0.0, 0.0, 0.0])
    alt = _trades([0.05, 0.05, 0.05, 0.05])
    d = delta_vs_baseline(alt, base, col="ret_net")
    assert d["delta_mean"] > 0


def test_bootstrap_delta_p05_returns_float():
    rng = np.random.RandomState(0)
    alt = _trades(list(rng.randn(60) * 0.02 + 0.01))
    base = _trades(list(rng.randn(60) * 0.02))
    p05 = bootstrap_delta_p05(alt, base, col="ret_net", n_iter=200)
    assert isinstance(p05, float)
