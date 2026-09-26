"""검정 도구 교정(`docs/prereg_2026-09-24_test_tool_calibration.md` §9-②) 단위 테스트 — 합성 데이터 · DB 없음."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from backtest.concept_axes.candidate_ledger.feature_study import run_features as RF
from backtest.concept_axes.candidate_ledger.tool_calibration import run_calib as RC


def _materialize(struct, lab, partners):
    """P1 을 행 단위로 직접 적용 — partners[k][z] = 층 z 의 π(블록 g) 배열."""
    out = lab.copy()
    for k, sk in enumerate(struct):
        for z, S in enumerate(sk["strata"]):
            pi = partners[k][z]
            g_of_row = np.repeat(np.arange(S["k"]), S["sizes"])
            out[S["yrows"]] = lab[S["src"][np.arange(len(g_of_row)), pi[g_of_row]]]
    return out


def _one_strategy(sizes, seed=0):
    """전략 0 하나 · 종목 i 가 sizes[i] 개 연속 날짜에 등장."""
    rows = []
    for g, m in enumerate(sizes):
        for j in range(m):
            rows.append((0, g, j + 2 * g))
    s, g, ci = (np.array(v, dtype=np.int64) for v in zip(*rows))
    y = np.random.default_rng(seed).normal(size=len(s))
    return s, g, ci, y


# ── P1 ────────────────────────────────────────────────────────────────────
def test_p1_stock_constant_equals_mapping_shuffle():
    """종목 상수 특징 · 블록 크기 같음 ⇒ P1 = 「종목→값 매핑 섞기」 뒤 분위를 다시 매긴 것과 행 단위로 같다."""
    s, g, ci, y = _one_strategy([4] * 9)
    xv = np.random.default_rng(1).normal(size=9)
    x = xv[g]
    lab, _ = RC.make_labels(x, s, ci, "window")
    struct = RC.p1_struct(s, g, ci, lab > 0)
    assert len(struct[0]["strata"]) == 1 and struct[0]["strata"][0]["k"] == 9
    pi = np.random.default_rng(2).permutation(9)
    perm_lab = _materialize(struct, lab, [[pi], [], []])
    lab_remap, _ = RC.make_labels(xv[pi][g], s, ci, "window")     # 블록 g 가 π(g) 의 값을 받음
    assert np.array_equal(perm_lab, lab_remap)
    # 크기가 달라도 블록 안은 상수 · 값 = 짝 블록의 라벨
    s2, g2, ci2, _ = _one_strategy([1, 1, 2, 3, 4, 4, 5, 5, 6, 6])
    x2 = np.random.default_rng(3).normal(size=10)[g2]
    lab2, _ = RC.make_labels(x2, s2, ci2, "window")
    st2 = RC.p1_struct(s2, g2, ci2, lab2 > 0)
    parts = [[np.random.default_rng(10 + z).permutation(S["k"]) for z, S in enumerate(st2[0]["strata"])], [], []]
    pl = _materialize(st2, lab2, parts)
    for z, S in enumerate(st2[0]["strata"]):
        blocks = np.unique(g2[S["yrows"]])
        for gl, gb in enumerate(blocks):
            partner_block = blocks[parts[0][z][gl]]
            assert set(pl[g2 == gb]) == {lab2[g2 == partner_block][0]}


def test_p1_circular_repeat_and_truncate():
    """층 2 = 크기 2·3 블록 · 3 이 2 를 받으면 [a,b,a] · 2 가 3 을 받으면 [c,d](앞부분)."""
    s, g, ci, _ = _one_strategy([1, 1, 2, 3, 4, 4, 5, 5, 6, 6])
    lab = np.zeros(len(s), dtype=np.int8)
    lab[g == 2] = [1, 3]
    lab[g == 3] = [2, 3, 1]
    lab[lab == 0] = 2
    struct = RC.p1_struct(s, g, ci, np.ones(len(s), dtype=bool))
    z2 = [z for z, S in enumerate(struct[0]["strata"]) if set(S["sizes"].tolist()) == {2, 3}]
    assert len(z2) == 1
    zi = z2[0]
    parts = [[np.arange(T["k"]) for T in struct[0]["strata"]], [], []]
    parts[0][zi] = np.array([1, 0])                                  # 두 블록 맞바꿈
    pl = _materialize(struct, lab, parts)
    assert pl[g == 3].tolist() == [1, 3, 1]
    assert pl[g == 2].tolist() == [2, 3]


def test_p1_pair_matrix_matches_materialized():
    """짝 행렬(p1_quant) 합 = 행 단위로 직접 섞은 라벨의 Δ · 항등 짝 = 관측 Δ."""
    rng = np.random.default_rng(5)
    rows = []
    for k in range(3):
        for gg in range(60):
            m = int(rng.integers(1, 12))
            start = int(rng.integers(0, 40))
            for j in range(m):
                rows.append((k, gg, start + j + (j // 3)))           # 중간에 틈(에피소드 여럿)
    s, g, ci = (np.array(v, dtype=np.int64) for v in zip(*rows))
    y = rng.normal(size=len(s))
    x = rng.normal(size=len(s))
    lab, _ = RC.make_labels(x, s, ci, "window")
    st = RC.delta_stat(y, lab, s)
    struct = RC.p1_struct(s, g, ci, lab > 0)
    for pr in (None, 7):
        parts, tot = [], np.zeros((3, 4))
        for k in range(3):
            pk = []
            for S in struct[k]["strata"]:
                pi = np.arange(S["k"]) if pr is None else np.random.default_rng([pr, k, S["k"]]).permutation(S["k"])
                pk.append(pi)
                Q = RC.p1_quant(S, lab, y)
                tot[k] += Q[:, np.arange(S["k"]), pi].sum(axis=1)
            parts.append(pk)
        pl = _materialize(struct, lab, parts)
        for k in range(3):
            m = s == k
            exp = y[m & (pl == 3)].mean() - y[m & (pl == 1)].mean()
            assert math.isclose(tot[k, 0] / tot[k, 1] - tot[k, 2] / tot[k, 3], exp, rel_tol=1e-12, abs_tol=1e-12)
            if pr is None:
                assert math.isclose(exp, st["per"][k], rel_tol=1e-12)
                assert tot[k, 1] == st["n3"][k] and tot[k, 3] == st["n1"][k]


def test_p1_strata_are_size_quintiles():
    s, g, ci, _ = _one_strategy([1, 1, 2, 3, 4, 4, 5, 5, 6, 6])
    struct = RC.p1_struct(s, g, ci, np.ones(len(s), dtype=bool))
    got = [sorted(S["sizes"].tolist()) for S in struct[0]["strata"]]
    assert got == [[1, 1], [2, 3], [4, 4], [5, 5], [6, 6]]


# ── P3 ────────────────────────────────────────────────────────────────────
def test_p3_within_date_quantiles_and_small_days():
    s = np.array([0] * 6 + [0] * 2 + [1] * 3, dtype=np.int64)
    ci = np.array([0] * 6 + [1] * 2 + [0] * 3, dtype=np.int64)
    x = np.array([5, 1, 3, 2, 6, 4, 9, 8, 1, 2, 3], dtype=float)
    lab, info = RC.make_labels(x, s, ci, "date")
    assert lab[:6].tolist() == [3, 1, 2, 1, 3, 2]
    assert lab[6:8].tolist() == [0, 0]                               # 비결측 2행인 날 제외
    assert lab[8:].tolist() == [1, 2, 3]
    assert info["ma20"] == dict(days=2, days_excl=1, rows_excl=2)
    # 결측은 세지 않는다: 3행 중 1행 결측 ⇒ 그날 제외
    x2 = x.copy()
    x2[8] = np.nan
    lab2, _ = RC.make_labels(x2, s, ci, "date")
    assert lab2[8:].tolist() == [0, 0, 0]


def test_window_labels_equal_B_labels_for():
    rng = np.random.default_rng(3)
    s = rng.integers(0, 3, 500)
    x = np.round(rng.normal(size=500), 1)                            # 동률 포함
    x[rng.integers(0, 500, 20)] = np.nan
    lab, _ = RC.make_labels(x, s, np.zeros(500, dtype=np.int64), "window")
    for k in range(3):
        m = (s == k) & ~np.isnan(x)
        assert np.array_equal(lab[m], RF.labels_for(pd.Series(x[m]), "F01"))
    assert (lab[np.isnan(x)] == 0).all()


# ── 에피소드 ───────────────────────────────────────────────────────────────
def test_episodes_recomputed_both_windows():
    rows = [("A", "000001", d) for d in ("2024-03-13", "2024-03-14", "2024-03-15", "2024-03-20", "2024-03-21")]
    rows += [("B", "000001", "2024-03-14"), ("A", "000002", "2024-03-14")]
    rows += [("A", "000001", d) for d in ("2025-07-01", "2025-07-02", "2025-07-04")]
    cal = ["2024-03-13", "2024-03-14", "2024-03-15", "2024-03-18", "2024-03-19", "2024-03-20", "2024-03-21",
           "2025-07-01", "2025-07-02", "2025-07-03", "2025-07-04"]
    smap = {"A": RF.SNAMES[0], "B": RF.SNAMES[1]}
    full = pd.DataFrame([dict(strategy=smap[a], stock_code=c, scan_date=d, ret_pct=1.0,
                              window="E" if d <= "2025-06-30" else "C") for a, c, d in rows])
    data = RC.build_data(full, cal)
    for w, exp in (("E", {0: True, 1: False, 2: False, 3: True, 4: False, 5: True, 6: True}),
                   ("C", {7: True, 8: False, 9: True})):
        D = data["W"][w]
        got = dict(zip(D["rowid"].tolist(), D["first"].tolist()))
        assert got == exp
    # 창 E 에서도 첫 행이 계산된다(csv ep_first 는 E 에서 전부 False 였다)
    assert data["W"]["E"]["first"].sum() == 4


# ── 가짜 특징 ───────────────────────────────────────────────────────────────
def test_gar_autocorrelation_near_phi():
    x = RC.ar1_panel(np.random.default_rng([RC.SEED0, 4, 1]), 617, 400)
    a, b = x[:-1].ravel(), x[1:].ravel()
    r = np.corrcoef(a, b)[0, 1]
    assert abs(r - 0.9) < 0.01
    assert abs(x.var() - 1.0) < 0.1


def test_make_fake_structure():
    data = dict(n_rows=6, n_codes=3, n_cal=4, gi_full=np.array([0, 0, 1, 2, 1, 0]), ci_full=np.array([0, 1, 1, 1, 2, 3]))
    g1 = RC.make_fake(1, 1, data)
    assert g1[0] == g1[1] == g1[5] and g1[2] == g1[4]
    g2 = RC.make_fake(2, 1, data)
    assert np.ptp(g2[[1, 2, 3]]) < 1e-6 and len(set(np.round(g2[[1, 2, 3]], 12))) == 3
    g4 = RC.make_fake(4, 1, data)
    pan = RC.ar1_panel(np.random.default_rng([RC.SEED0, 4, 1]), 4, 3)
    assert np.allclose(g4, pan[data["ci_full"], data["gi_full"]])
    assert np.array_equal(RC.make_fake(1, 7, data), RC.make_fake(1, 7, data))


# ── P2 · CR1 손계산 ────────────────────────────────────────────────────────
def test_cr1_hand_calculation():
    """T3: A 2·A 4·B 6 (평균 4) · T1: A 1·C 3 (평균 2) · T2: D 9.
    Δ = 2 · ψ_A = −2/3·… = −1/6 · ψ_B = 2/3 · ψ_C = −1/2 · Σψ² = 13/18 · CR1 = 3/2 · 4/3 = 2 ⇒ V = 13/9."""
    y = np.array([2, 4, 6, 1, 3, 9], dtype=float)
    lab = np.array([3, 3, 3, 1, 1, 2], dtype=np.int8)
    cl = np.array([0, 0, 1, 0, 2, 3])
    s = np.zeros(6, dtype=np.int64)
    st = dict(pool=2.0, per=np.array([2.0, np.nan, np.nan]), n=np.array([6.0, 0, 0]), n1=np.array([2.0, 0, 0]),
              n3=np.array([3.0, 0, 0]), ok=np.array([True, False, False]))
    r = RC.cr1_test(y, lab, s, cl, st, 4)
    se = math.sqrt(13 / 9)
    assert math.isclose(r["se"], se, rel_tol=1e-12)
    assert math.isclose(r["se_s"][0], se, rel_tol=1e-12)
    assert math.isclose(r["p"], math.erfc(2 / se / math.sqrt(2)), rel_tol=1e-12)


def test_cr1_pooled_is_linear_combination_across_strategies():
    """두 전략이 같은 종목 클러스터를 공유 · 풀링 ψ = Σ a_s ψ_s(전략 가로질러 한 클러스터)."""
    rng = np.random.default_rng(9)
    n = 400
    s = np.repeat([0, 1], n // 2)
    cl = rng.integers(0, 40, n)
    y = rng.normal(size=n) + 0.3 * cl / 40
    lab = rng.choice(np.array([1, 2, 3], dtype=np.int8), n)
    st = RC.delta_stat(y, lab, s)
    r = RC.cr1_test(y, lab, s, cl, st, 40)
    psi = np.zeros(40)
    N, used = 0, set()
    for k in (0, 1):
        m1, m3 = (s == k) & (lab == 1), (s == k) & (lab == 3)
        w = np.where(m3, 1 / m3.sum(), np.where(m1, -1 / m1.sum(), 0))
        u = np.where(m3, y - y[m3].mean(), np.where(m1, y - y[m1].mean(), 0))
        psi += st["n"][k] / st["n"][:2].sum() * np.bincount(cl, weights=w * u, minlength=40)
        N += int((m1 | m3).sum())
        used |= set(cl[m1 | m3].tolist())
    G = len(used)
    v = G / (G - 1) * (N - 1) / (N - 4) * (psi ** 2).sum()
    assert math.isclose(r["se"], math.sqrt(v), rel_tol=1e-12)


# ── K0 · 판정 ──────────────────────────────────────────────────────────────
def test_k0_singleton_blocks_null_equals_observed():
    """(전략, 날짜) 블록이 전부 1행이면 섞을 것이 없다 ⇒ 순열 Δ = 관측 Δ ⇒ p = 1."""
    n = 120
    s = np.zeros(n, dtype=np.int64)
    ci = np.arange(n)
    rng = np.random.default_rng(1)
    y, x = rng.normal(size=n), rng.normal(size=n)
    lab, _ = RC.make_labels(x, s, ci, "window")
    st = RC.delta_stat(y, lab, s)
    null, _ = RC.k0_null(y, lab, s, ci, st, np.random.default_rng(0), 50)
    assert np.allclose(null, st["pool"])
    assert RC.perm_p(null, st["pool"]) == 1.0


def test_classify_boundaries():
    c = RC.classify
    assert c({1: (7, 100), 2: (13, 100), 4: (10, 100)}) == "합격"
    assert c({1: (6, 100), 2: (10, 100), 4: (10, 100)}) == "경계"
    assert c({1: (16, 100), 2: (10, 100), 4: (4, 100)}) == "경계"
    assert c({1: (17, 100), 2: (10, 100), 4: (10, 100)}) == "불합격"
    assert c({1: (3, 100), 2: (10, 100), 4: (10, 100)}) == "불합격"
    assert RC.stage2_verdict({1: (28, 400), 2: (52, 400), 4: (40, 400)}) == "합격"
    assert RC.stage2_verdict({1: (27, 400), 2: (40, 400), 4: (40, 400)}) == "불합격"
