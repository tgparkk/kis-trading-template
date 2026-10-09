"""stats — CR1 식 · 2원 CGM(max(V) 대체) · S 게이트 시드·소비 순서 · F 전수 열거 · 판정 순서(§7·§9 · 합성)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from backtest.concept_axes.stoploss_rebound import stats as ST


# ── 분산 ─────────────────────────────────────────────────────────────────
def test_cr1_matches_prereg_formula():
    d = np.array([1.0, 2.0, 4.0, -1.0, 0.5])
    g = np.array(["A", "A", "B", "C", "C"])
    r = ST.cr1(d, g)
    m = d.mean()
    psi = {k: sum(d[g == k] - m) / len(d) for k in "ABC"}
    v = 3 / 2 * sum(x ** 2 for x in psi.values())
    assert r["mean"] == pytest.approx(m) and r["se"] == pytest.approx(math.sqrt(v)) and r["G"] == 3


def test_cgm_negative_variance_replaced_by_max():
    d = np.array([2.0, -1.0, -1.0, 0.0])
    g = np.array(["A", "A", "B", "B"])
    b = np.array([1, 2, 1, 2])
    r = ST.cgm(d, g, b)
    assert r["neg"] and r["Vs"] == pytest.approx(0.25) and r["Vb"] == pytest.approx(0.25)
    assert r["Vsb"] == pytest.approx(0.5) and r["se"] == pytest.approx(0.5)      # √max(0.25, 0.25)


def test_cgm_positive_variance_uses_sum():
    rng = np.random.default_rng(1)
    d = rng.normal(size=40)
    g = np.repeat(np.arange(10), 4)
    b = np.tile(np.arange(5), 8)
    r = ST.cgm(d, g, b)
    if not r["neg"]:
        assert r["se"] ** 2 == pytest.approx(r["Vs"] + r["Vb"] - r["Vsb"])


def test_tool_test_cgm_uses_t_with_gb_minus_1():
    rng = np.random.default_rng(2)
    d = rng.normal(0.3, 1, size=30)
    g = np.arange(30) % 7
    b = np.arange(30) % 5
    r = ST.tool_test(ST.TOOL_CGM, d, g, b)
    from scipy import stats as sst
    assert r["ci_hi"] - r["mean"] == pytest.approx(float(sst.t.ppf(0.975, 4)) * r["se"])
    r1 = ST.tool_test(ST.TOOL_CR1, d, g, b)
    assert r1["ci_hi"] - r1["mean"] == pytest.approx(1.959963984540054 * r1["se"])
    assert r1["p"] == pytest.approx(math.erfc(abs(r1["mean"] / r1["se"]) / math.sqrt(2)))


# ── S 게이트 ─────────────────────────────────────────────────────────────
def test_s_signs_seed_and_ascending_code_order():
    codes = ["000100", "000200", "000300"]
    want = np.random.default_rng([20261017, 12, 1, 7]).choice([-1, 1], 3)
    assert [ST.s_signs(codes, 7)[c] for c in codes] == [int(x) for x in want]


def test_gate_invariant_to_lot_order_but_uses_sorted_codes():
    rng = np.random.default_rng(3)
    codes = [f"{i % 9:06d}" for i in range(45)]
    d = rng.normal(size=45)
    blocks = [i % 5 for i in range(45)]
    g1 = ST.gate(ST.TOOL_CR1, d, codes, blocks, n_fake=40)
    perm = rng.permutation(45)
    g2 = ST.gate(ST.TOOL_CR1, d[perm], [codes[i] for i in perm], [blocks[i] for i in perm], n_fake=40)
    assert (g1.s_rate, g1.f_count) == (g2.s_rate, g2.f_count)


def test_s_gate_rate_manual_recompute():
    rng = np.random.default_rng(4)
    codes = [f"{i % 6:06d}" for i in range(30)]
    d = rng.normal(size=30)
    g = ST.gate(ST.TOOL_CR1, d, codes, [i % 5 for i in range(30)], n_fake=25)
    dc = d - d.mean()
    rej = 0
    for j in range(1, 26):
        s = np.random.default_rng([20261017, 12, 1, j]).choice([-1, 1], 6)
        sg = dict(zip(sorted(set(codes)), s))
        x = dc * np.array([sg[c] for c in codes])
        rej += ST.p_norm(*[ST.cr1(x, codes)[k] for k in ("mean", "se")]) < 0.10
    assert g.s_rate == pytest.approx(rej / 25)


# ── F 게이트(전수 열거) ───────────────────────────────────────────────────
def test_f_patterns_counts_and_first_block_fixed():
    p5 = ST.f_patterns(5)
    assert len(p5) == 16 and len(set(p5)) == 16 and all(p[0] == 1 for p in p5)
    assert len(ST.f_patterns(6)) == 32
    assert math.floor(0.13 * 16) == 2 and math.floor(0.13 * 32) == 4


@pytest.mark.parametrize("nrej,ok", [(2, True), (3, False)])
def test_f_gate_pass_is_at_most_two_of_sixteen(monkeypatch, nrej, ok):
    calls = {"n": 0}
    real = ST.tool_test

    def fake(tool, d, g, b):
        k = calls["n"] - ST.N_FAKE                    # 앞 400회 = (S) · 그 뒤 = (F) 패턴
        calls["n"] += 1
        return dict(real(tool, d, g, b), p=0.01 if 0 <= k < nrej else 0.9)

    monkeypatch.setattr(ST, "tool_test", fake)
    d = np.arange(25, dtype=float)
    gt = ST.gate(ST.TOOL_CR1, d, [f"{i:06d}" for i in range(25)], [i // 5 for i in range(25)])
    assert gt.f_total == 16 and gt.f_max == 2 and gt.f_count == nrej and gt.f_pass is ok and gt.s_pass


def test_t3_gate_block_floor_and_fallback_order(monkeypatch):
    d = np.zeros(20)
    codes = [f"{i:06d}" for i in range(20)]
    pn = ST.t3_gate(d, codes, [i // 5 for i in range(20)])            # B = 4
    assert pn.B == 4 and pn.tool == ST.TOOL_FAIL and pn.gates == []
    assert ST.t3_test(pn, d, codes, [i // 5 for i in range(20)]).test is None
    seen = []

    def fake_gate(tool, *a, **k):
        seen.append(tool)
        ok = tool == ST.TOOL_CGM
        return ST.GateOut(tool, 0.0 if ok else 0.5, ok, 0, 16, 2, True)

    monkeypatch.setattr(ST, "gate", fake_gate)
    pn = ST.t3_gate(d, codes, [i // 4 for i in range(20)])            # B = 5
    assert seen == [ST.TOOL_CR1, ST.TOOL_CGM] and pn.tool == ST.TOOL_CGM
    monkeypatch.setattr(ST, "gate", lambda tool, *a, **k: ST.GateOut(tool, 0.5, False, 9, 16, 2, False))
    assert ST.t3_gate(d, codes, [i // 4 for i in range(20)]).tool == ST.TOOL_FAIL


# ── 판정 순서(§9) ─────────────────────────────────────────────────────────
def _pn(tool=ST.TOOL_CR1, B=6, mean=0.0, p=0.5, hi=0.3):
    return ST.T3Panel(B, [], tool, None if tool == ST.TOOL_FAIL else dict(mean=mean, p=p, ci_hi=hi, ci_lo=-1, se=0.1))


def test_decide_gate_failure_beats_everything():
    v = ST.decide({"L": _pn(ST.TOOL_FAIL), "M": _pn(mean=1.0, p=0.001, hi=1.5)}, False, 10, 3)
    assert v.label == ST.LAB_NA and v.reason.startswith("①")
    v = ST.decide({"L": _pn(B=4), "M": _pn(B=4)}, True, 200, 50)
    assert v.label == ST.LAB_NA and "B=4" in v.reason


def test_decide_order_fidelity_then_n_g_then_panels():
    good = {"L": _pn(mean=1.0, p=0.001, hi=1.5), "M": _pn(mean=1.0, p=0.001, hi=1.5)}
    assert ST.decide(good, False, 200, 50).reason.startswith("②")
    assert ST.decide(good, True, 99, 50).reason.startswith("③")
    assert ST.decide(good, True, 200, 19).reason.startswith("③")
    v = ST.decide({"L": _pn(mean=1.0, p=0.001, hi=1.5), "M": _pn(mean=0.1, p=0.5, hi=0.3)}, True, 200, 50)
    assert v.label == ST.LAB_NA and v.reason.startswith("④")
    v = ST.decide(good, True, 100, 20)
    assert v.label == ST.LAB_UP and v.text == ST.TEXT_UP


def test_label_boundaries():
    up = {k: _pn(mean=0.4, p=0.049, hi=0.8) for k in "LM"}
    assert ST.decide(up, True, 150, 30).label == ST.LAB_UP
    no = {k: _pn(mean=0.4, p=0.05, hi=0.8) for k in "LM"}
    assert ST.decide(no, True, 150, 30).label == ST.LAB_NA
    nn = {k: _pn(mean=0.1, p=0.3, hi=0.3999) for k in "LM"}
    assert ST.decide(nn, True, 150, 30).label == ST.LAB_NOT
    edge = {k: _pn(mean=0.1, p=0.3, hi=0.4) for k in "LM"}
    assert ST.decide(edge, True, 150, 30).label == ST.LAB_NA
    neg = {k: _pn(mean=-2.0, p=0.001, hi=-1.0) for k in "LM"}
    assert ST.decide(neg, True, 150, 30).label == ST.LAB_NOT          # 부호 반대도 «우위 아님»


# ── T1/T2 도구 게이트 ─────────────────────────────────────────────────────
def _units(n=30, k=4, seed=5):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        cs = sorted(f"{rng.integers(0, 60):06d}" for _ in range(k))
        cs = sorted(set(cs))
        if len(cs) < 2:
            cs = ["000001", "000002"]
        out.append(ST.FakeUnit(cs, {c: float(rng.random() < 0.3) for c in cs}, i // 6))
    return out


def test_t12_draws_seed_and_order():
    units = _units()
    for j in (1, 2, 400):
        rng = np.random.default_rng([20261017, 11, j])
        assert ST.t12_draws(units, j) == [u.controls[int(rng.integers(0, len(u.controls)))] for u in units]


def test_t12_fake_draw_seed_and_order():
    units = _units()
    rng = np.random.default_rng([20261017, 11, 1])
    picks = [u.controls[int(rng.integers(0, len(u.controls)))] for u in units]
    y1 = [u.y[h] for u, h in zip(units, picks)]
    y0, c0, w0 = [], [], []
    for u, h in zip(units, picks):
        rest = [c for c in u.controls if c != h]
        for c in rest:
            y0.append(u.y[c])
            c0.append(c)
            w0.append(1 / len(rest))
    want = ST.p2_two_sided(ST._p2(y1, picks, y0, c0, w0)) < 0.10
    got = ST.t12_fake_gate(units, n_fake=1)
    assert got["rate"] == float(want) and got["n_units"] == len(units)


def test_t12_fake_gate_two_way_runs_and_is_deterministic():
    units = _units()
    a = ST.t12_fake_gate(units, n_fake=20, two_way=True)
    b = ST.t12_fake_gate(units, n_fake=20, two_way=True)
    assert a == b and 0.0 <= a["rate"] <= 1.0


def test_p2_cgm_single_block_gives_p_one():
    r = ST.p2_cgm([1, 0, 1], ["a", "b", "c"], [0, 0, 0], [0, 1, 0], ["d", "e", "f"], [0, 0, 0], [1, 1, 1])
    assert r["p"] == 1.0


def test_mde_t3_formula():
    m = ST.mde_t3(5.0, 200)
    assert m["mde"] == pytest.approx(2.8016 * 5 / math.sqrt(200), rel=1e-3)
    assert m["deff4"] == pytest.approx(2 * m["mde"])


@pytest.mark.parametrize("n_rej,ok", [(52, True), (53, False)])
def test_s_gate_threshold_is_0_13_of_400(monkeypatch, n_rej, ok):
    calls = {"n": 0}
    real = ST.tool_test

    def fake(tool, d, g, b):
        k = calls["n"]
        calls["n"] += 1
        return dict(real(tool, d, g, b), p=0.01 if k < n_rej else 0.9)     # 앞 400회 = (S)

    monkeypatch.setattr(ST, "tool_test", fake)
    gt = ST.gate(ST.TOOL_CR1, np.arange(25, dtype=float), [f"{i:06d}" for i in range(25)], [i // 5 for i in range(25)])
    assert gt.s_rate == pytest.approx(n_rej / 400) and gt.s_pass is ok
