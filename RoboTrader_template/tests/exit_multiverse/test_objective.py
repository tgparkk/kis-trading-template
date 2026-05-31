import numpy as np
import pandas as pd
from scripts.exit_multiverse import objective
from backtest.regime_analysis import MarketRegime


def _regime_series(dates, labels):
    return pd.Series([getattr(MarketRegime, l) for l in labels], index=pd.to_datetime(dates))


def test_regime_worst_sharpe_picks_min():
    dates = pd.date_range("2021-01-01", periods=9)
    rets = pd.Series([0.01, 0.02, 0.015, -0.01, -0.02, -0.015, 0.0, 0.001, -0.001], index=dates)
    regimes = _regime_series(dates, ["BULL"]*3 + ["BEAR"]*3 + ["SIDEWAYS"]*3)
    out = objective.regime_sharpes(rets, regimes, min_obs=2)
    assert out["BEAR"] < out["BULL"]
    assert out["worst"] == min(out["BULL"], out["BEAR"], out["SIDEWAYS"])


def test_dsr_computed():
    dates = pd.date_range("2021-01-01", periods=300)
    rng = np.random.default_rng(0)
    rets = pd.Series(rng.normal(0.001, 0.01, 300), index=dates)
    dsr = objective.compute_dsr(rets, n_trials=54)
    assert 0.0 <= dsr <= 1.0
