"""무작위 진입 대조군 §5 단위 테스트 — 합성 데이터 · DB 없음.

사전등록 `docs/prereg_2026-09-24_exit_path_diagnosis.md` §6-2 ④: 종목 대응 매핑 · 재현 가드 · (추가) 이진 비교 P2 p 손계산.
"""
from __future__ import annotations

import math
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd

from backtest.concept_axes.candidate_ledger import run as R
from backtest.concept_axes.candidate_ledger.exit_diag import run_random_entry as RE
from backtest.concept_axes.ledger8 import exitsim8 as X


def _pools(n_cal: int, n_stock: int, sets: dict) -> RE.Pools:
    M = np.zeros((n_cal, n_stock), dtype=bool)
    for d, ks in sets.items():
        M[d, list(ks)] = True
    return RE.make_pools(M)


# ── 종목 대응 매핑 ─────────────────────────────────────────────────────────
def test_mapping_same_h_every_day_and_replacement_only_that_day():
    # g=0 이 1·2·3·4일에 나온다. 첫 등장일 U_b = {5} ⇒ π(0) = 5 강제.
    # 3일엔 5 ∉ U_b = {6} ⇒ 그날만 6 으로 대체 · 4일엔 다시 5.
    P = _pools(6, 10, {1: {5}, 2: {5, 6}, 3: {6}, 4: {5, 9}})
    d = np.array([1, 2, 3, 4])
    g = np.array([0, 0, 0, 0])
    o = RE.draw_mapped(np.random.default_rng(0), d, g, RE.first_groups(d, g), P, 10)
    assert o["h"].tolist() == [5, 5, 6, 5]
    assert o["n_replaced"] == 1 and o["n_dropped"] == 0
    assert o["dup_pi"] == 0 and o["dup_real"] == 0


def test_mapping_invariants_over_seeds():
    # g0·g1 첫 등장 1일(같은 그룹 ⇒ 비복원 ⇒ 서로 다른 h) · g2 첫 등장 2일(다른 그룹 ⇒ 같은 h 가능).
    sets = {1: {0, 1, 7}, 2: {0, 2, 7, 8}, 3: {0, 1, 8}}
    P = _pools(5, 10, sets)
    d = np.array([1, 1, 2, 2, 3, 3])
    g = np.array([0, 1, 0, 2, 0, 1])
    groups = RE.first_groups(d, g)
    assert [(x, v.tolist()) for x, v in groups] == [(1, [0, 1]), (2, [2])]
    seen_dup = False
    for seed in range(200):
        o = RE.draw_mapped(np.random.default_rng([20261002, 2, seed]), d, g, groups, P, 10)
        h = o["h"]
        pi = {0: h[0], 1: h[1]}                                   # 첫 등장일엔 대체가 일어날 수 없다
        assert pi[0] != pi[1] and pi[0] in sets[1] and pi[1] in sets[1]
        n_rep = 0
        for i, (dd, gg) in enumerate(zip(d.tolist(), g.tolist())):
            if gg in pi:
                if pi[gg] in sets[dd]:
                    assert h[i] == pi[gg]                          # 모든 날 같은 h
                else:
                    assert h[i] in sets[dd]                        # 그날만 U_b 에서 대체
                    n_rep += 1
            assert h[i] in sets[dd]
        assert o["n_replaced"] == n_rep
        seen_dup |= o["dup_pi"] > 0
    assert seen_dup                                                # 날짜 차로 생기는 매핑 중복이 실제로 나온다


def test_mapping_is_deterministic_per_seed_and_daily_board_distinct_within_day():
    P = _pools(4, 30, {1: set(range(20)), 2: set(range(5, 30))})
    d = np.array([1, 1, 1, 2, 2])
    g = np.array([3, 4, 5, 3, 6])
    a = RE.draw_mapped(np.random.default_rng([20261002, 2, 7]), d, g, RE.first_groups(d, g), P, 30)
    b = RE.draw_mapped(np.random.default_rng([20261002, 2, 7]), d, g, RE.first_groups(d, g), P, 30)
    assert a["h"].tolist() == b["h"].tolist()
    o = RE.draw_daily(np.random.default_rng(1), [(1, np.array([0, 1, 2])), (2, np.array([3, 4]))], P, 5)
    assert len(set(o["h"][:3].tolist())) == 3 and len(set(o["h"][3:].tolist())) == 2


def test_dup_count():
    assert RE.dup_count(np.array([0, 1, 2, 0]), np.array([5, 5, 6, 5])) == 1
    assert RE.dup_count(np.array([0, 1, 2]), np.array([5, 5, 5])) == 2


# ── U_b 밴드 ───────────────────────────────────────────────────────────────
def test_ub_mask_band_edges_bad_open_and_missing_d_bar():
    cal = [date(2024, 3, 11), date(2024, 3, 12), date(2024, 3, 13)]
    n = 5
    C = np.full((3, n), np.nan)
    O = np.full((3, n), np.nan)
    HAS = np.zeros((3, n), dtype=bool)
    C[0, :] = 100.0
    HAS[0, :4] = True                                                # 종목 4 는 D 봉 없음
    O[1, :] = [101.0, 101.5, 92.0, 91.9, 100.0]
    HAS[1, :] = True
    BAD = np.zeros((3, n), dtype=bool)
    mk = RE.Market(cal, np.array(cal, dtype="datetime64[ns]"), np.array([f"00000{i}" for i in range(n)]), O, O, O,
                   C, HAS, BAD, np.array([], dtype="datetime64[ns]"), np.array([]), np.zeros(n + 1, dtype=np.int64))
    elig = {pd.Timestamp(cal[0]): {f"00000{i}" for i in range(n)}}
    M = RE.ub_mask(mk, elig, 0.08, 0.01, [0])                        # ma20 밴드 [92, 101]
    assert M[0].tolist() == [True, False, True, False, False]
    BAD[1, 0] = True
    assert RE.ub_mask(mk, elig, 0.08, 0.01, [0])[0].tolist() == [False, False, True, False, False]
    assert RE.ub_mask(mk, elig, None, 0.03, [0])[0].tolist() == [False, True, True, True, False]


# ── 청산 재구현 = exitsim8(탐침 없음) ─────────────────────────────────────────
def _view(o, h, lo, c, has):
    n = len(o)
    return SimpleNamespace(o=list(o), h=list(h), lo=list(lo), has=list(has), pc=list(c), pc_np=np.asarray(c),
                           cs=[0.0] + np.cumsum(c).tolist(), J=list(range(n)), S0=[0] * n)


def test_sim_fast_matches_exitsim8_without_data_exits():
    cal = [d.date() for d in pd.bdate_range("2024-01-02", periods=40)]
    cal_idx = {d: i for i, d in enumerate(cal)}
    HC = list(range(1, 41))
    HCm1 = list(range(0, 40))
    rng = np.random.default_rng(3)
    n_checked = 0
    for trial in range(400):
        tp, sl, mh = [(0.10, 0.08, 5), (0.12, 0.08, 7), (0.10, 0.10, 4)][trial % 3]
        c = 10_000 * np.exp(np.cumsum(rng.normal(0, 0.04, 40)))
        o = c * np.exp(rng.normal(0, 0.03, 40))
        h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.03, 40)))
        lo = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.03, 40)))
        has = rng.random(40) > 0.15
        e = int(rng.integers(0, 30))
        has[e] = True
        sp = RE.SimSpec(tp=tp, sl=sl, mh=mh, smh=10 ** 6, min_len=10 ** 6, trail=None, hold_mode="count1")
        got = RE.sim_fast(sp, _view(o, h, lo, c, has), e, len(cal), HC, HCm1)
        bars = {cal[i]: X.Bar(cal[i], float(o[i]), float(h[i]), float(lo[i]), float(c[i])) for i in range(40) if has[i]}
        pos = X.Pos("000001", cal[e], None, float(o[e]), 1, X.BASIS_D_OPEN)
        ex = X.simulate_lot(pos, X.ExitRules(tp, sl, mh), R.build_path(cal, cal_idx, bars, cal[e], mh),
                            lambda p, d: None)
        if ex.closed:
            assert (got[0], cal[got[1]]) == (ex.reason, ex.exit_date)
            assert abs(got[2] - ex.ret_pct) <= 1e-12 and got[3] == ex.price
        else:
            assert got[0] == "open"
        n_checked += 1
    assert n_checked == 400


def test_sim_fast_data_exits_hold_and_trail():
    n = 30
    c = np.full(n, 100.0)
    o, h, lo = c.copy(), c * 1.01, c * 0.99
    has = [True] * n
    HC, HCm1 = list(range(1, n + 1)), list(range(0, n))
    sp = RE.SimSpec(tp=0.5, sl=0.5, mh=50, smh=3, min_len=1, trail=None, hold_mode="count1")
    v = _view(o, h, lo, c, has)
    v.J = list(range(n))                                             # 창 = [0, t) · 마지막 봉 = t−1
    assert RE.sim_fast(sp, v, 5, n, HC, HCm1)[:2] == ("max_hold", 8)  # 보유일 = t − e ≥ 3
    assert RE.sim_fast(RE.SimSpec(0.5, 0.5, 50, 3, 1, None, "elapsed"), v, 5, n, HC, HCm1)[:2] == ("max_hold", 8)
    # trail: 진입가 90(시가) · 종가 100 > 90(수익 중) · MA20 = 105 > 100 ⇒ k=0 에서 trail_ma(가격 = 진입가)
    c2 = np.concatenate([np.full(19, 105.25), [100.0], np.full(n - 20, 100.0)])
    o2 = c2.copy()
    o2[20] = 90.0
    v2 = _view(o2, o2 * 1.01, o2 * 0.99, c2, has)
    sp2 = RE.SimSpec(tp=0.5, sl=0.5, mh=50, smh=99, min_len=20, trail=20, hold_mode="count1")
    rs, xi, rt, xp = RE.sim_fast(sp2, v2, 20, n, HC, HCm1)
    assert (rs, xi, rt, xp) == ("trail_ma", 20, 0.0, 90.0)


# ── 재현 가드 대조 ─────────────────────────────────────────────────────────
def test_guard_compare_counts_each_field_and_any():
    got = dict(reason=["tp", "sl", "tp", "max_hold", "tp"], date=["2024-01-02"] * 5, ret=[10.0, -8.0, 10.0, 1.0, 10.0])
    want = dict(reason=["tp", "tp", "tp", "max_hold", "tp"], date=["2024-01-02", "2024-01-02", "2024-01-03",
                                                                   "2024-01-02", "2024-01-02"],
                ret=[10.0 + 5e-10, -8.0, 10.0, 1.0 + 1e-6, 10.0])
    r = RE.guard_compare(got["reason"], got["date"], got["ret"], want["reason"], want["date"], want["ret"])
    assert r == dict(n=5, reason=1, date=1, ret=1, any=3)             # 5e-10 은 여유 안 · 1e-6 은 밖
    assert r["any"] / r["n"] > RE.GUARD_TOL                            # ⇒ 대체 경로


# ── 이진 비교 P2 p 손계산 ───────────────────────────────────────────────────
def test_p2_binary_hand_calculation():
    # 룰 y=[1,3] 종목 [0,1] · 무작위 풀 y=[0,2,1,1] 종목 [0,2,2,3] · 가중 1/2(반복 2)
    # m1=2 · m0=1 ⇒ Δ=1 · ψ = {0: −0.5+0.25, 1: 0.5, 2: −0.25, 3: 0} ⇒ Σψ²=0.375
    # G=4 · N=2+2=4 · K=2 ⇒ 4/3·3/2=2 ⇒ V=0.75 · SE=√0.75 · z=1/√0.75
    t = RE.p2_binary(np.array([1.0, 3.0]), np.array([0, 1]), np.array([0.0, 2.0, 1.0, 1.0]), np.array([0, 2, 2, 3]),
                     np.full(4, 0.5))
    se = math.sqrt(0.75)
    assert t["delta"] == 1.0 and t["G"] == 4 and t["N"] == 4.0
    assert abs(t["se"] - se) < 1e-15
    assert abs(t["p_up"] - 0.5 * math.erfc(1 / se / math.sqrt(2))) < 1e-15
    assert abs(t["p_up"] - 0.12410653949496186) < 1e-12
    assert abs(t["p_up"] + t["p_down"] - 1.0) < 1e-15


def test_p2_binary_equals_weighted_sandwich():
    rng = np.random.default_rng(11)
    n1, n0, R_ = 40, 120, 3
    y1, y0 = rng.normal(0.5, 2, n1), rng.normal(0, 2, n0)
    c1, c0 = rng.integers(0, 15, n1), rng.integers(5, 30, n0)
    w0 = np.full(n0, 1.0 / R_)
    t = RE.p2_binary(y1, c1, y0, c0, w0)
    y = np.concatenate([y1, y0])
    Xm = np.column_stack([np.ones(n1 + n0), np.r_[np.ones(n1), np.zeros(n0)]])
    w = np.r_[np.ones(n1), w0]
    bread = np.linalg.inv(Xm.T @ (w[:, None] * Xm))
    beta = bread @ (Xm.T @ (w * y))
    e = y - Xm @ beta
    cl = np.r_[c1, c0]
    meat = np.zeros((2, 2))
    for c in np.unique(cl):
        m = cl == c
        s = Xm[m].T @ (w[m] * e[m])
        meat += np.outer(s, s)
    G, N = len(np.unique(cl)), w.sum()
    V = G / (G - 1) * (N - 1) / (N - 2) * (bread @ meat @ bread)
    assert abs(beta[1] - t["delta"]) < 1e-12
    assert abs(math.sqrt(V[1, 1]) - t["se"]) < 1e-12


# ── Holm · 라벨 ───────────────────────────────────────────────────────────
def test_holm_step_down_m6():
    ps = {"a": 0.001, "b": 0.02, "c": 0.009, "d": 0.5, "e": 0.3, "f": 0.012}
    # 0.001 ≤ .05/6 ✓ · 0.009 ≤ .05/5 ✓ · 0.012 ≤ .05/4 ✓ · 0.02 > .05/3 ✗ ⇒ 멈춤
    assert RE.holm(ps) == {"a": True, "c": True, "f": True, "b": False, "e": False, "d": False}


def test_labels_fixed_rules():
    assert RE.label(0.30, True, False, 0.9) == RE.LAB_UP
    assert RE.label(-0.30, False, True, 0.9) == RE.LAB_DOWN
    assert RE.label(0.20, True, False, 0.20) == RE.LAB_NONE
    assert RE.label(0.20, False, False, 0.30) == RE.LAB_HOLD          # 검정력 없음 ⇒ 차이 없음 아님
    assert RE.label(0.30, False, False, 0.10) == RE.LAB_HOLD
    assert RE.label(0.25, False, False, 0.10) == RE.LAB_HOLD          # |T| < 0.25 아님
    assert abs(RE.MDE_K - (2.3939797998185104 + 0.8416212335729143)) < 1e-9
