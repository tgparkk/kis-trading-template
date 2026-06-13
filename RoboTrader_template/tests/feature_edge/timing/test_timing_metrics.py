import numpy as np
import pandas as pd
from scripts.feature_edge.timing.timing_metrics import (
    summarize_trades, delta_vs_baseline, bootstrap_delta_p05, oos_delta_signs)


def test_empty_trades_no_keyerror():
    # 체결 0건 → 컬럼 없는 빈 프레임이어도 KeyError 없이 n=0 처리(통합경로 버그 회귀).
    empty = pd.DataFrame()
    assert summarize_trades(empty, "ret_net")["n"] == 0
    d = delta_vs_baseline(empty, empty, "ret_net")
    assert d["alt_n"] == 0 and np.isnan(d["delta_mean"])
    assert np.isnan(bootstrap_delta_p05(empty, empty, "ret_net"))
    assert oos_delta_signs(empty, empty, "2026-01-01", "ret_net")["consistent"] is False


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
