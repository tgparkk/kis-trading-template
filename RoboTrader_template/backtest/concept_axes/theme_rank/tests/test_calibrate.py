from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.theme_rank import calibrate as CA


def _null_arena(n_days=120, per_day=12, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_days):
        for i in range(per_day):
            rows.append((f"2026-{d:04d}", f"{i:06d}", float(rng.standard_normal())))
    return pd.DataFrame(rows, columns=["scan_date", "stock_code", "ret_net"])


def test_choose_picks_first_lag_inside_band_else_empirical():
    t_ok = {11: [3.0] * 10 + [0.0] * 90, 22: [0.0] * 100, 33: [0.0] * 100}       # |t|≥1.645 비율 0.10
    assert CA.choose(t_ok) == {"mode": "hac", "lag": 11, "rates": {11: 0.10, 22: 0.0, 33: 0.0}}
    t_bad = {11: [3.0] * 40 + [0.0] * 60, 22: [3.0] * 30 + [0.0] * 70, 33: [3.0] * 20 + [0.0] * 80}
    c = CA.choose(t_bad)
    assert c["mode"] == "empirical" and c["lag"] == 11


def test_calibrated_p_modes():
    assert CA.calibrated_p(1.96, {"mode": "hac", "lag": 11}) == pytest.approx(math.erfc(1.96 / math.sqrt(2)))
    calib = {"mode": "empirical", "lag": 11, "t_fakes": {"11": [0.5, -2.5, 3.0, 1.0]}}
    assert CA.calibrated_p(2.0, calib) == pytest.approx((1 + 2) / 5)


def test_fake_t_stats_rejection_rate_near_nominal_on_null_data():
    arena = _null_arena()
    members = {t: frozenset(f"{(t * 3 + i) % 12:06d}" for i in range(4)) for t in range(8)}
    th = {}
    for t, m in members.items():
        for c in m:
            th.setdefault(c, set()).add(t)
    th = {c: frozenset(v) for c, v in th.items()}
    days = sorted(arena["scan_date"].unique())
    t = CA.fake_t_stats(arena, th, members, days, lags=(11,), n_fakes=60, seed=7)
    rate = sum(abs(x) >= 1.6448536269514722 for x in t[11]) / len(t[11])
    assert len(t[11]) == 60 and rate <= 0.30


def test_calibrated_p_nan_t_is_nan():
    assert math.isnan(CA.calibrated_p(float("nan"), {"mode": "hac", "lag": 11}))
    calib = {"mode": "empirical", "lag": 11, "t_fakes": {"11": [0.5, -2.5]}}
    assert math.isnan(CA.calibrated_p(float("nan"), calib))


def test_calibrated_p_empirical_uses_requested_lag():
    calib = {"mode": "empirical", "lag": 11, "t_fakes": {"11": [0.5, -2.5, 3.0, 1.0], "22": [0.1, 0.2, 0.3, 0.4]}}
    assert CA.calibrated_p(2.0, calib) == pytest.approx(3 / 5)
    assert CA.calibrated_p(2.0, calib, 22) == pytest.approx(1 / 5)


def test_choose_escalates_to_lag_22():
    t = {11: [3.0] * 30 + [0.0] * 70, 22: [3.0] * 10 + [0.0] * 90, 33: [0.0] * 100}
    c = CA.choose(t)
    assert c["mode"] == "hac" and c["lag"] == 22
