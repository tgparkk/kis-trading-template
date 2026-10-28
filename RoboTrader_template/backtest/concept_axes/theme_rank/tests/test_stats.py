from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.theme_rank import stats as ST


def test_spearman_pins_including_ties():
    assert ST.spearman([1, 2, 3, 4, 5], [5, 6, 7, 8, 7]) == pytest.approx(0.8207826816681234)
    assert ST.spearman([0, 0, 0, 1, 2], [1, 3, 2, 5, 4]) == pytest.approx(0.7826237921249264)
    assert math.isnan(ST.spearman([1, 1, 1], [1, 2, 3]))


def test_daily_ic_skips_degenerate_days_and_counts_them():
    rows = []
    for i in range(5):                                          # 정상일 — 완전 정순
        rows.append(("2026-01-02", float(i), float(i)))
    for i in range(4):                                          # 체결 4개 < 5 → 제외
        rows.append(("2026-01-05", float(i), float(i)))
    for i in range(6):                                          # S 전부 0 → 제외
        rows.append(("2026-01-06", 0.0, float(i)))
    df = pd.DataFrame(rows, columns=["scan_date", "s", "ret"])
    ic, skipped = ST.daily_ic(df, "s", "ret")
    assert list(ic.index) == ["2026-01-02"] and ic.iloc[0] == pytest.approx(1.0)
    assert skipped == 2


def test_hac_t_pins_match_newsquant_metrics():
    """NewsQuant `news_scraper/backtest/metrics.hac_t` 와 같은 식(Bartlett) — 같은 손계산 핀."""
    s = pd.Series(([0.1] * 10 + [-0.1] * 10) * 3) + 0.02
    assert ST.hac_t(s, 3)["t_hac"] == pytest.approx(0.02 / math.sqrt(0.0308333333 / 60), rel=1e-6)
    xs = [0.03, -0.01, 0.05, 0.02, 0.04]
    n, mean = len(xs), sum(xs) / len(xs)
    ssd = sum((x - mean) ** 2 for x in xs)
    assert ST.hac_t(pd.Series(xs), 0)["t_hac"] == pytest.approx(mean / (math.sqrt(ssd / n) / math.sqrt(n)))
    assert math.isnan(ST.hac_t(pd.Series([0.1] * 5), 1)["t_hac"])
    assert math.isnan(ST.hac_t(pd.Series([0.01, 0.02, 0.04]), 5)["p_hac"])


def test_degree_preserving_shuffle_keeps_sizes_and_degrees_and_changes_graph():
    rng = np.random.default_rng(1)
    members = {t: frozenset(f"{(t * 7 + i) % 40:06d}" for i in range(5 + t % 4)) for t in range(12)}
    out = ST.degree_preserving_shuffle(members, rng)
    assert {t: len(v) for t, v in out.items()} == {t: len(v) for t, v in members.items()}
    deg = lambda m: pd.Series([c for v in m.values() for c in v]).value_counts().sort_index().to_dict()  # noqa: E731
    assert deg(out) == deg(members)
    assert out != members


def test_ar1_noise_shape_and_persistence():
    z = ST.ar1_noise([1, 2], 2000, 0.9, np.random.default_rng(3))
    assert set(z) == {1, 2} and z[1].shape == (2000,)
    lag1 = np.corrcoef(z[1][1:], z[1][:-1])[0, 1]
    assert 0.85 < lag1 < 0.95 and 0.9 < z[1].std() < 1.1


def test_fake_s_mirrors_real_structure():
    members = {1: frozenset({"000009", "000001"}), 2: frozenset({"000009", "000002"}), 3: frozenset({"000009"})}
    th = {"000009": frozenset({1, 2, 3})}
    # 동료 있는 테마 2개(1·2) · 최소 p = upper_p(1.0)=0.158655… → S = −log10(2 × 0.158655…)
    assert ST.fake_s("000009", th, members, {1: 1.0, 2: -1.0, 3: 9.0}) == pytest.approx(
        -math.log10(2 * 0.15865525393145707))
    assert ST.fake_s("000123", th, members, {1: 3.0}) == 0.0


def test_episode_first_keeps_first_of_consecutive_days_per_stock():
    cal = {date(2026, 1, d): i for i, d in enumerate([2, 5, 6, 7])}
    df = pd.DataFrame({"scan_date": [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 7), date(2026, 1, 5)],
                       "stock_code": ["000001", "000001", "000001", "000002"]})
    out = ST.episode_first(df, cal)
    assert sorted(map(tuple, out[["scan_date", "stock_code"]].values.tolist())) == [
        (date(2026, 1, 2), "000001"), (date(2026, 1, 5), "000002"), (date(2026, 1, 7), "000001")]
