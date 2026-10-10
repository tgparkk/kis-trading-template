import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.dt_dart_filter import proxy as P


def test_features_rolling_20_and_logs():
    n = 25
    px = pd.DataFrame({"stock_code": ["000001"] * n, "date": pd.date_range("2024-01-01", periods=n),
                       "close": [100.0] * n, "volume": [1000.0] * n})
    f = P.add_proxy_features(px)
    assert f["tv20"].iloc[:19].isna().all() and f["tv20"].iloc[19] == 100000.0
    assert np.isclose(f["x1"].iloc[24], np.log(100000.0)) and np.isclose(f["x2"].iloc[0], np.log(100.0))


def test_features_nonpositive_close_gives_nan():
    px = pd.DataFrame({"stock_code": ["1"] * 2, "date": pd.date_range("2024-01-01", periods=2),
                       "close": [0.0, 5.0], "volume": [1.0, 1.0]})
    assert np.isnan(P.add_proxy_features(px)["x2"].iloc[0])


def test_logistic_recovers_coefficients():
    rng = np.random.default_rng(1)
    x1, x2 = rng.normal(0, 1, 20000), rng.normal(0, 1, 20000)
    X = P.design(x1, x2)
    true = np.array([-0.5, 1.2, -0.8])
    y = (rng.random(20000) < P.predict(true, X)).astype(float)
    b = P.fit_logistic(X, y)
    assert np.allclose(b, true, atol=0.08)


def _seeded_xy():
    rng = np.random.default_rng(1)
    x1, x2 = rng.normal(0, 1, 20000), rng.normal(0, 1, 20000)
    X = P.design(x1, x2)
    true = np.array([-0.5, 1.2, -0.8])
    y = (rng.random(20000) < P.predict(true, X)).astype(float)
    return X, y


def test_logistic_nan_in_X_raises_value_error():
    X, y = _seeded_xy()
    X[3, 1] = np.nan
    with pytest.raises(ValueError):
        P.fit_logistic(X, y)


def test_logistic_inf_in_y_raises_value_error():
    X, y = _seeded_xy()
    y[5] = np.inf
    with pytest.raises(ValueError):
        P.fit_logistic(X, y)


def test_logistic_max_iter_one_raises_runtime_error():
    X, y = _seeded_xy()
    with pytest.raises(RuntimeError):
        P.fit_logistic(X, y, max_iter=1)


def test_auc_extremes():
    assert P.auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert P.auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0
    assert np.isnan(P.auc([1, 1], [0.1, 0.2]))
