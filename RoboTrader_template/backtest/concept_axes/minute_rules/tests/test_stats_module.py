"""`minute_rules/test_stats.py`(통계 모듈) 단위 테스트 — 합성 자료만 · 손계산 대조 · 귀무 보정(⑪ Holm 비교값 포함)."""
from __future__ import annotations

import numpy as np
import pytest

from backtest.concept_axes.minute_rules import test_stats as S


def test_seed_contract():
    a, b = S.rng_for(S.W_E, S.RULE_NO["R1"]), np.random.default_rng([20261111, 0, 1])
    assert a.integers(0, 10**9, 5).tolist() == b.integers(0, 10**9, 5).tolist()
    assert S.rng_for(S.W_C, 1).random() != S.rng_for(S.W_E, 1).random()


def test_paired_delta_all_lots_denominator_and_aff():
    d = S.paired_delta([1.0, 0.0, 3.0, -1.0], [1.0, 0.0, 1.0, 0.0])
    st = S.timing_stat(d)
    assert d.tolist() == [0.0, 0.0, 2.0, -1.0]
    assert st.n == 4 and st.mean == pytest.approx(0.25) and st.f == 0.5 and st.mean_aff == pytest.approx(0.5)
    st2 = S.timing_stat(d, affected=[True, False, True, True])         # 진입이 바뀐 로트(δ=0 이어도 걸림)
    assert st2.f == 0.75 and st2.mean_aff == pytest.approx(1 / 3)
    assert np.isnan(S.paired_delta([1.0], [np.nan])[0])


def test_block_bootstrap_resamples_days_not_lots():
    d = np.array([1.0, 1.0, 1.0, -3.0])
    days = ["a", "a", "a", "b"]
    boot = S.block_boot_means(d, days, 2000, S.rng_for(0, 99))
    assert set(np.round(np.unique(boot), 9)) <= {1.0, 0.0, -3.0}          # 날 단위 = {aa, ab, bb}
    assert abs((boot == 0.0).mean() - 0.5) < 0.05


def test_p_boot_centered_and_one_sided():
    boot = np.array([0.0, 1.0, 2.0, 3.0])                              # T̂ = 1.5 → z = −1.5, −0.5, 0.5, 1.5
    assert S.p_boot(1.5, boot, S.GREATER) == pytest.approx((1 + 1) / 5)
    assert S.p_boot(1.5, boot, S.LESS) == pytest.approx((1 + 4) / 5)
    assert S.p_boot(1.5, boot, S.TWO) == pytest.approx(min(1.0, 2 * min(2 / 5, 5 / 5)))   # 등꼬리(D1)
    with pytest.raises(ValueError):
        S.p_boot(0.0, boot, "x")


def test_timing_null_and_effect_calibration():
    rng = np.random.default_rng(5)
    days = np.repeat(np.arange(60), 10)
    shared = rng.normal(0, 1, 60)[days]                                # 날짜 상관
    null = shared + rng.normal(0, 1, 600)
    null = null - null.mean() + 0.05                                   # 참 평균 ≈ 0 · 날짜 상관만
    assert S.p_boot(null.mean(), S.block_boot_means(null, days, 2000, S.rng_for(0, 1)), S.TWO) > 0.5
    eff = null - null.mean() + 1.0
    p1 = S.p_boot(eff.mean(), S.block_boot_means(eff, days, 2000, S.rng_for(0, 2)), S.GREATER)
    assert p1 < 0.01


def test_filter_stat_hand_computed():
    # 날 a: keep [2, 4] filter [0] → w = 2·1/3 · diff = 3 − 0 = 3 · 날 b: keep [1] filter [3, 5] → w = 2/3 · diff = −3
    # 날 c: keep 만 → 기여 0
    ret = [2, 4, 0, 1, 3, 5, 9]
    keep = [True, True, False, True, False, False, True]
    days = ["a", "a", "a", "b", "b", "b", "c"]
    st = S.filter_stat(ret, keep, days)
    assert st.delta == pytest.approx(0.0) and st.n_info_days == 2 and st.n_keep == 4 and st.n_filter == 3
    st2 = S.filter_stat(ret[:3], keep[:3], days[:3])
    assert st2.delta == pytest.approx(3.0) and st2.f == pytest.approx(1 / 3)
    w = [1, 1, 1, 0, 0, 0, 1]                                          # 날 b 를 가중 0 → 날 a 만
    assert S.filter_stat(ret, keep, days, weights=w).delta == pytest.approx(3.0)


def test_filter_perm_keeps_day_composition_and_is_calibrated():
    rng = np.random.default_rng(11)
    days = np.repeat(np.arange(50), 8)
    ret = rng.normal(0, 3, 400) + np.repeat(rng.normal(0, 2, 50), 8)
    keep = rng.random(400) > 0.3
    perm = S.filter_perm(ret, keep, days, 300, S.rng_for(0, 4))
    assert np.isfinite(perm).all() and abs(perm.mean()) < 0.3
    order = np.argsort(days, kind="stable")
    g = days[order]
    k = keep[order]
    p = np.argsort(np.random.default_rng(0).random((1, 400)) + g[None, :], axis=1)[0]
    assert all(k[p][g == d].sum() == k[g == d].sum() for d in range(50))  # 날마다 keep 수 보존
    t = S.filter_stat(ret, keep, days).delta
    assert 0.0 < S.p_perm(t, perm, S.TWO) <= 1.0
    shifted = ret + 5.0 * keep
    t2 = S.filter_stat(shifted, keep, days).delta
    assert t2 == pytest.approx(t + 5.0)
    assert S.p_perm(t2, S.filter_perm(shifted, keep, days, 300, S.rng_for(0, 4)), S.GREATER) < 0.01


def test_filter_block_boot_centred_on_estimate():
    rng = np.random.default_rng(2)
    days = np.repeat(np.arange(40), 6)
    keep = np.tile([True, True, True, False, False, False], 40)
    ret = rng.normal(0, 1, 240) + 2.0 * keep
    boot = S.filter_block_boot(ret, keep, days, 500, S.rng_for(0, 5))
    t = S.filter_stat(ret, keep, days).delta
    lo, hi = S.basic_ci(boot, t, 0.05)
    assert lo < t < hi and lo > 0


def test_twoway_weights_are_products_of_draw_counts():
    W = S.twoway_weights(["x", "x", "y"], ["d1", "d2", "d1"], 50, S.rng_for(0, 6))
    assert W.shape == (50, 3) and (W >= 0).all()
    # 종목 2 · 날짜 2 → 뽑힌 수 각 0~2 · 가중 = 곱 ∈ {0,1,2,4}
    assert set(np.unique(W)) <= {0.0, 1.0, 2.0, 4.0}
    st = S.weighted_mean_stat([1.0, 3.0, 5.0])
    assert st(np.array([1.0, 1.0, 2.0])) == pytest.approx((1 + 3 + 10) / 4)
    assert np.isnan(st(np.zeros(3)))


def test_twoway_boot_wider_than_block_when_stock_clustered():
    rng = np.random.default_rng(3)
    stocks = np.repeat(np.arange(20), 30)
    days = np.tile(np.arange(30), 20)
    d = np.repeat(rng.normal(0, 2, 20), 30) + rng.normal(0, 1, 600)    # 종목 상관만
    tw = S.twoway_boot(S.weighted_mean_stat(d), stocks, days, 400, S.rng_for(0, 7))
    bb = S.block_boot_means(d, days, 400, S.rng_for(0, 8))
    assert np.nanstd(tw) > 2 * np.std(bb)
    fs = S.filter_weighted_stat(d, stocks % 2 == 0, days)
    assert np.isfinite(fs(np.ones(600)))


def test_11_holm_compare_values_and_stepdown():
    assert S.compare_value(0.02, one_sided=True) == pytest.approx(0.04)
    assert S.compare_value(0.02, one_sided=False) == pytest.approx(0.02)
    assert S.compare_value(0.7, one_sided=True) == 1.0
    cmp = {"R1": 0.005, "R3": 0.009, "R7": 0.0125, "R6": 0.04, "R4": 0.2, "R5": 1.0}
    rows = {r.rule: r for r in S.holm(cmp, m=6)}
    assert [rows[k].order for k in ("R1", "R3", "R7", "R6", "R4", "R5")] == [1, 2, 3, 4, 5, 6]
    assert rows["R1"].threshold == pytest.approx(0.05 / 6) and rows["R1"].rejected        # 0.005 ≤ 0.00833
    assert rows["R3"].threshold == pytest.approx(0.01) and rows["R3"].rejected            # 0.009 ≤ 0.01
    assert rows["R7"].threshold == pytest.approx(0.0125) and rows["R7"].rejected          # 0.0125 ≤ 0.0125
    assert not rows["R6"].rejected and not rows["R4"].rejected                          # 0.04 > 0.01667 → 멈춤
    stop = {r.rule: r.rejected for r in S.holm({"A": 0.02, "B": 0.001}, m=2)}
    assert stop == {"B": True, "A": True}
    gap = {r.rule: r.rejected for r in S.holm({"A": 0.03, "B": 0.001, "C": 0.0001}, m=6)}
    assert gap == {"C": True, "B": True, "A": False}
    with pytest.raises(ValueError):
        S.holm({"A": 0.1, "B": 0.1}, m=1)


def test_fake_filter_stock_constant_and_rate_switch():
    stocks = np.repeat(np.arange(500), 3)
    keep = S.fake_filter_keep(stocks, 0.2, S.rng_for(S.W_FAKE, S.FAKE_FILTER_R0))
    assert all(len(set(keep[stocks == s])) == 1 for s in range(0, 500, 37))
    assert abs((~keep).mean() - 0.2) < 0.05
    assert S.fake_rate([0.01, 0.2, 0.04, 0.5]) == 0.5
    assert S.use_twoway(0.08) and not S.use_twoway(0.075)


def test_fake_filters_null_rate_near_alpha():
    """귀무(종목 상수 노이즈 거르기 · 날짜 효과만)에서 블록 순열 p<0.05 비율이 0.05 근처."""
    rng = np.random.default_rng(21)
    days = np.repeat(np.arange(40), 10)
    stocks = rng.integers(0, 150, 400)
    ret = rng.normal(0, 3, 400) + np.repeat(rng.normal(0, 2, 40), 10)
    ps = []
    for k in range(40):
        r = S.rng_for(S.W_FAKE, S.FAKE_FILTER_R0 + k)
        keep = S.fake_filter_keep(stocks, 0.2, r)
        t = S.filter_stat(ret, keep, days).delta
        ps.append(S.p_perm(t, S.filter_perm(ret, keep, days, 200, r), S.TWO))
    assert S.fake_rate(ps) <= 0.2


def test_ipw_cell_inverse_cap_and_ess():
    held = [True, False, False, False, True, True, True, False] + [True] + [False] * 30
    bucket = ["a"] * 4 + ["b"] * 4 + ["c"] * 31
    month = ["m"] * 39
    out = S.ipw_weights(held, bucket, month, cap=20)
    # a: 1/4 보유 → 4 · b: 3/4 → 4/3 ×3 · c: 1/31 → 31 → 상한 20
    assert out.weights.tolist() == pytest.approx([4.0, 4 / 3, 4 / 3, 4 / 3, 20.0])
    assert out.n_capped == 1
    w = out.weights
    assert out.ess == pytest.approx(w.sum() ** 2 / (w ** 2).sum())
    assert S.ess([1, 1, 1, 1]) == pytest.approx(4.0) and S.ess([]) == 0.0
