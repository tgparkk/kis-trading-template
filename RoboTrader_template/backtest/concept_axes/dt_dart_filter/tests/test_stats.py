import math

import numpy as np

from backtest.concept_axes.dt_dart_filter import stats as ST


def _panel(beta, seed=0, n_days=200, per_day=30):
    rng = np.random.default_rng(seed)
    day = np.repeat(np.arange(n_days), per_day)
    stock = rng.integers(0, 400, len(day))
    x = (rng.random(len(day)) < 0.05).astype(float)
    y = rng.normal(0, 1, n_days)[day] * 5 + beta * x + rng.normal(0, 8, len(day))
    return y, x, day, stock, day // 20


def test_fe_recovers_effect_and_one_sided_p():
    fe = ST.fe_regression(*_panel(-3.0, seed=1))
    assert -4.5 < fe.beta < -1.5 and fe.se_cr1 > 0 and fe.p1_cr1 < 0.05 and fe.n1 > 0


def test_fe_null_effect_not_rejected_with_seed():
    fe = ST.fe_regression(*_panel(0.0, seed=2))
    assert fe.p2_cr1 > 0.01 and 0 <= fe.p1_cr1 <= 1


def test_fe_drops_single_group_days():
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    x = np.array([1.0, 0.0, 0.0, 0.0, 1.0, 0.0])
    day = np.array([0, 0, 1, 1, 2, 2])          # day 1 = 표식 없음 → 제외
    fe = ST.fe_regression(y, x, day, np.array([1, 2, 3, 4, 5, 6]), day)
    assert fe.n_days == 2 and fe.n == 4


def test_fe_single_cluster_returns_nan_se():
    y = np.array([1.0, 0.0, 2.0, 0.0]); x = np.array([1.0, 0.0, 1.0, 0.0])
    fe = ST.fe_regression(y, x, np.array([0, 0, 1, 1]), np.array([7, 7, 7, 7]), np.array([0, 0, 0, 0]))
    assert math.isnan(fe.se_cr1)


def test_mde_and_holm():
    assert abs(ST.mde(1.0) - 2.486) < 1e-3
    assert ST.holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]


def _dummy_sandwich(y, x, day, stock):
    """Reference: OLS of y on [x, day dummies] + stock-clustered sandwich with CR1 c = G/(G-1)·(N-1)/(N-K)."""
    days_all = np.unique(day)
    keep = [d for d in days_all if 0 < x[day == d].sum() < (day == d).sum()]
    m = np.isin(day, keep)
    y, x, day, stock = y[m], x[m], day[m], stock[m]
    days = np.unique(day)
    X = np.column_stack([x, (day[:, None] == days[None, :]).astype(float)])
    N, K = X.shape                      # K = 1 + n_days (x + absorbed day FE)
    bread = np.linalg.inv(X.T @ X)
    b = bread @ X.T @ y
    u = y - X @ b
    meat = np.zeros((K, K))
    stocks = np.unique(stock)
    for s in stocks:
        idx = stock == s
        sc = X[idx].T @ u[idx]
        meat += np.outer(sc, sc)
    G = len(stocks)
    c = G / (G - 1) * (N - 1) / (N - K)
    V = c * bread @ meat @ bread
    return float(b[0]), float(np.sqrt(V[0, 0])), N, K - 1


def test_cr1_matches_dummy_sandwich():
    rng = np.random.default_rng(20261010)
    n_days, per_day = 20, 15
    day = np.repeat(np.arange(n_days), per_day)
    stock = rng.integers(0, 15, len(day))
    x = (rng.random(len(day)) < 0.3).astype(float)
    x[day == 3] = 0.0                   # all-0 day → dropped by the filter
    x[day == 5] = 1.0                   # all-1 day → dropped by the filter
    y = rng.normal(0, 1, n_days)[day] * 5 + (-2.0) * x + rng.normal(0, 8, len(day))
    beta_ref, se_ref, n_ref, nd_ref = _dummy_sandwich(y, x, day, stock)
    fe = ST.fe_regression(y, x, day, stock, day // 5)
    assert fe.n == n_ref and fe.n_days == nd_ref
    assert abs(fe.beta - beta_ref) < 1e-10
    assert abs(fe.se_cr1 - se_ref) < 1e-10
