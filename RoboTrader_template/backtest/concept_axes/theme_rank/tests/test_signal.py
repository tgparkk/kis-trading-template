from __future__ import annotations

import math

import pytest

from backtest.concept_axes.theme_rank import signal as SG


def test_log10_tail_matches_hand_calc():
    assert SG.log10_binom_tail(10, 0.03, 4) == pytest.approx(-3.83243151364107, rel=1e-9)
    assert SG.log10_binom_tail(99, 0.03, 6) == pytest.approx(-1.108682523122055, rel=1e-9)
    assert SG.log10_binom_tail(3, 0.5, 3) == pytest.approx(math.log10(0.125), rel=1e-12)


def test_log10_tail_edges():
    assert SG.log10_binom_tail(5, 0.2, 0) == 0.0
    assert SG.log10_binom_tail(5, 0.2, 6) == -math.inf


def test_log10_tail_no_underflow_for_extreme_k():
    v = SG.log10_binom_tail(148, 0.0002, 140)
    assert math.isfinite(v) and v < -400


def _st(universe, jumped):
    return SG.day_state({c: (0.06 if c in jumped else 0.0) for c in universe})


def test_day_state_p0_and_floor():
    st = _st({f"{i:06d}" for i in range(10)}, {"000000", "000001"})
    assert st.p0 == pytest.approx(0.2)
    flat = SG.day_state({f"{i:06d}": 0.0 for i in range(10)})
    assert flat.jumped == frozenset() and flat.p0 == pytest.approx(0.05)     # 하한 1/(2·10)


def test_surprise_example_from_spec_with_theme_count_correction():
    # 테마 1: 후보 c + 동료 5(2 튐) · 테마 2,3: 동료 1(안 튐) → m=3 · p0=0.2
    uni = {f"{i:06d}" for i in range(10)}
    st = _st(uni, {"000001", "000002"})
    members = {1: frozenset({"000009", "000001", "000002", "000003", "000004", "000005"}),
               2: frozenset({"000009", "000006"}), 3: frozenset({"000009", "000007"})}
    themes_of = {"000009": frozenset({1, 2, 3})}
    s = SG.surprise("000009", themes_of, members, st)
    assert s.m == 3 and s.main_theme == 1 and (s.k_main, s.n_main) == (2, 5) and not s.single
    assert s.s == pytest.approx(0.1033856098409906, rel=1e-9)        # −log10(3 × P(Bin(5,0.2) ≥ 2))


def test_surprise_k_below_two_counts_theme_but_scores_zero():
    uni = {f"{i:06d}" for i in range(10)}
    st = _st(uni, {"000001"})
    members = {1: frozenset({"000009", "000001", "000002"})}
    s = SG.surprise("000009", {"000009": frozenset({1})}, members, st)
    assert (s.s, s.m, s.main_theme, s.single) == (0.0, 1, None, False)


def test_surprise_theme_with_only_self_is_not_counted_and_unthemed_is_single():
    uni = {f"{i:06d}" for i in range(10)}
    st = _st(uni, set())
    members = {1: frozenset({"000009"})}
    s = SG.surprise("000009", {"000009": frozenset({1})}, members, st)
    assert (s.s, s.m, s.single) == (0.0, 0, True)
    assert SG.surprise("000008", {}, members, st).single


def test_surprise_peers_outside_universe_are_ignored():
    st = _st({"000009", "000001", "000002"}, {"000001", "000002"})
    members = {1: frozenset({"000009", "000001", "000002", "000077"})}   # 000077 은 그날 수익률 없음
    s = SG.surprise("000009", {"000009": frozenset({1})}, members, st)
    assert s.n_main == 2 and s.k_main == 2


def test_surprise_finite_when_no_stock_jumped_market_wide():
    uni = {f"{i:06d}" for i in range(2000)}
    st = SG.day_state({c: -0.03 for c in uni} | {"000001": 0.2, "000002": 0.2, "000003": 0.2})
    members = {1: frozenset({"000009", "000001", "000002", "000003"})}
    s = SG.surprise("000009", {"000009": frozenset({1})}, members, st)
    assert math.isfinite(s.s) and s.s > 5


def test_print_items():
    excess = {"000001": 0.08, "000002": 0.02, "000003": -0.01, "000009": 0.04}
    members = {1: frozenset({"000009", "000001", "000002"}), 2: frozenset({"000009", "000003"})}
    th = {"000009": frozenset({1, 2})}
    assert SG.mean_excess_max("000009", th, members, excess) == pytest.approx(0.05)
    assert SG.same_theme_count("000009", 1, members, frozenset({"000009", "000001", "000777"})) == 1
    assert SG.rank_in_theme("000009", 1, members, excess) == 2
    assert SG.streak([-3.0, -1.0, -2.5, -2.1]) == 2
    assert SG.streak([-1.0]) == 0
