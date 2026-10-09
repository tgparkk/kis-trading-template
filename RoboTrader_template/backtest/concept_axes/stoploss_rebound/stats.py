"""검정·게이트·라벨 — 사전등록 §7·§8·§9 그대로(🔒 동결 e4d9ee2). 순수 함수 · DB 없음.

T3(주 검정 · m=1 · α 0.05 양측): Δ 로트 평균 · 종목 클러스터 CR1(§7 식 그대로 — ψ_g = Σ_{ℓ∈g}(Δ_ℓ − Δ̄)/n ·
  V = G/(G−1)·Σψ_g² · 정규). 이름 = «P2 부품»(K2 아님 · P3 미사용).
자기 표본 게이트(개봉 단계 · 진짜 p 보다 먼저): d = Δ − Δ̄ 에 부호 —
  (S) 종목코드 오름차순 · `default_rng([20261017, 12, 1, j])` j=1..400 · `rng.choice([-1, 1], G)` · p<0.10 비율 ≤ 0.13
  (F) 진입일 블록 부호 전수 열거 2^(B−1)(첫 블록 +1 고정 = 전역 부호 대칭 제거) · p<0.10 패턴 수 ≤ ⌊0.13·2^(B−1)⌋
  둘 다 합격 = CR1 · 아니면 2원 CGM(종목 × 블록 · V_s + V_b − V_sb · V ≤ 0 ⇒ max(V_s, V_b) · t(G_b − 1)) 로 같은 게이트
  → 또 실패 = 판정 불가(도구). B < 5 = 판정 불가(도구).
T1/T2 도구 게이트(봉인 단계 · 대조 팔 값만 · 인쇄용): 가짜 이벤트 400회 · `p2_binary`(run_random_entry) · 실패 시 2원.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

SEED0 = 20261017
N_FAKE = 400
FAKE_P = 0.10
FAKE_MAX = 0.13
ALPHA = 0.05
THETA3 = 0.4                 # %p/로트 (§7 실질 임계)
B_MIN = 5
N_MIN = 100
G_MIN = 20
K_MDE = 1.959963984540054 + 0.8416212335729143   # §8 m=1 → 2.80
Z975 = 1.959963984540054

TOOL_CR1, TOOL_CGM, TOOL_FAIL = "CR1", "CGM", "fail"
LAB_UP = "ⓐ 우위"
LAB_NOT = "ⓐ 우위 아님"
LAB_NA = "판정 불가"
TEXT_UP = "단일 로트·gross·자리 점유 무시 조건에서 ⓐ 로트당 수익이 ⓑ 보다 θ₃ 이상 높았다"
TEXT_NOT = "단일 로트·gross·자리 점유 무시 조건에서 ⓐ 로트당 수익이 ⓑ 보다 θ₃ 이상 높지 않았다"


# ── 분산 ─────────────────────────────────────────────────────────────────
def _cl_var(e: np.ndarray, lab: np.ndarray, n: int) -> Tuple[float, int]:
    """G/(G−1)·Σ_g(Σ_{i∈g} e_i / n)² — §7 의 ψ_g = Σ(Δ − Δ̄)/n 꼴."""
    u, inv = np.unique(lab, return_inverse=True)
    G = len(u)
    if G < 2 or n < 1:
        return float("nan"), G
    s = np.bincount(inv, weights=e, minlength=G) / n
    return G / (G - 1) * float((s ** 2).sum()), G


def cr1(d: Sequence[float], g: Sequence[Any]) -> Dict[str, float]:
    d = np.asarray(d, dtype=float)
    n = len(d)
    if n < 2:
        return dict(mean=float("nan"), se=float("nan"), G=0, n=n)
    m = float(d.mean())
    v, G = _cl_var(d - m, np.asarray(g), n)
    return dict(mean=m, se=math.sqrt(v) if v == v and v > 0 else float("nan"), G=G, n=n)


def cgm(d: Sequence[float], g: Sequence[Any], b: Sequence[Any]) -> Dict[str, float]:
    """2원 클러스터(종목 × 블록) — V_s + V_b − V_sb · V ≤ 0 ⇒ max(V_s, V_b)(§7)."""
    d = np.asarray(d, dtype=float)
    n = len(d)
    if n < 2:
        return dict(mean=float("nan"), se=float("nan"), Gs=0, Gb=0, neg=False)
    m = float(d.mean())
    e = d - m
    g = np.asarray(g)
    b = np.asarray(b)
    vs, gs = _cl_var(e, g, n)
    vb, gb = _cl_var(e, b, n)
    vsb, _ = _cl_var(e, np.array([f"{x}|{y}" for x, y in zip(g, b)]), n)
    v = vs + vb - (vsb if vsb == vsb else 0.0)
    neg = not (v > 0)
    if neg:
        cand = [x for x in (vs, vb) if x == x]
        v = max(cand) if cand else float("nan")
    return dict(mean=m, se=math.sqrt(v) if v == v and v > 0 else float("nan"), Gs=gs, Gb=gb, neg=neg,
                Vs=vs, Vb=vb, Vsb=vsb)


def p_norm(m: float, se: float) -> float:
    if not (se == se and se > 0 and m == m):
        return 1.0
    return min(1.0, math.erfc(abs(m / se) / math.sqrt(2)))


def t_crit(df: int) -> float:
    from scipy import stats as sst
    return float(sst.t.ppf(0.975, df))


def p_t(m: float, se: float, df: int) -> float:
    if not (se == se and se > 0 and m == m and df >= 1):
        return 1.0
    from scipy import stats as sst
    return min(1.0, 2.0 * float(sst.t.sf(abs(m / se), df)))


def tool_test(tool: str, d: np.ndarray, g: np.ndarray, b: np.ndarray) -> Dict[str, float]:
    """(평균, SE, p, 95% CI) — CR1 = 정규 · CGM = t(G_b − 1)."""
    if tool == TOOL_CR1:
        r = cr1(d, g)
        p = p_norm(r["mean"], r["se"])
        crit = Z975
    else:
        r = cgm(d, g, b)
        df = int(r["Gb"]) - 1
        p = p_t(r["mean"], r["se"], df)
        crit = t_crit(df) if df >= 1 else float("nan")
    lo = r["mean"] - crit * r["se"]
    hi = r["mean"] + crit * r["se"]
    return dict(mean=r["mean"], se=r["se"], p=p, ci_lo=lo, ci_hi=hi, G=r.get("G", r.get("Gs")), Gb=r.get("Gb"),
                neg=r.get("neg", False))


# ── 자기 표본 게이트(T3) ─────────────────────────────────────────────────
def s_signs(codes_sorted: Sequence[str], j: int) -> Dict[str, int]:
    """(S) 종목코드 오름차순 소비 · default_rng([20261017, 12, 1, j])."""
    rng = np.random.default_rng([SEED0, 12, 1, j])
    s = rng.choice([-1, 1], len(codes_sorted))
    return {c: int(x) for c, x in zip(codes_sorted, s)}


def f_patterns(nb: int) -> List[Tuple[int, ...]]:
    """(F) 블록 부호 전수 — 첫 블록 +1 고정(전역 부호 대칭 제거) → 2^(B−1)개."""
    if nb < 1:
        return []
    return [(1,) + rest for rest in itertools.product((1, -1), repeat=nb - 1)]


@dataclass
class GateOut:
    tool: str
    s_rate: float
    s_pass: bool
    f_count: int
    f_total: int
    f_max: int
    f_pass: bool

    @property
    def passed(self) -> bool:
        return self.s_pass and self.f_pass


def gate(tool: str, delta: Sequence[float], codes: Sequence[str], blocks: Sequence[int],
         n_fake: int = N_FAKE) -> GateOut:
    """한 도구의 (S)·(F) 게이트 — 가짜 = 부호 × (Δ − Δ̄)."""
    d = np.asarray(delta, dtype=float)
    dc = d - d.mean()
    g = np.asarray(codes)
    b = np.asarray(blocks)
    uniq = sorted(set(codes))
    rej = 0
    for j in range(1, n_fake + 1):
        sg = s_signs(uniq, j)
        ds = dc * np.array([sg[c] for c in codes], dtype=float)
        rej += tool_test(tool, ds, g, b)["p"] < FAKE_P
    s_rate = rej / n_fake
    bl = sorted(set(int(x) for x in blocks))
    idx = {x: i for i, x in enumerate(bl)}
    pats = f_patterns(len(bl))
    fcnt = 0
    for pat in pats:
        sgn = np.array([pat[idx[int(x)]] for x in blocks], dtype=float)
        fcnt += tool_test(tool, dc * sgn, g, b)["p"] < FAKE_P
    fmax = int(math.floor(FAKE_MAX * len(pats)))
    return GateOut(tool, s_rate, s_rate <= FAKE_MAX, fcnt, len(pats), fmax, fcnt <= fmax)


@dataclass
class T3Panel:
    B: int
    gates: List[GateOut] = field(default_factory=list)
    tool: str = TOOL_FAIL
    test: Optional[Dict[str, float]] = None


def t3_gate(delta: Sequence[float], codes: Sequence[str], blocks: Sequence[int],
            log: Callable[[str], None] = lambda s: None, n_fake: int = N_FAKE) -> T3Panel:
    """§7 순서: B<5 → 판정 불가(도구) · CR1 게이트 → (실패) CGM 게이트 → (실패) 도구 탈락. 진짜 검정은 `t3_test` 가 «뒤에»."""
    B = len(set(int(x) for x in blocks))
    out = T3Panel(B)
    if B < B_MIN:
        log(f"[게이트] 블록 수 B={B} < {B_MIN} → 판정 불가(도구) · 게이트·검정 생략")
        return out
    for tool in (TOOL_CR1, TOOL_CGM):
        gt = gate(tool, delta, codes, blocks, n_fake)
        out.gates.append(gt)
        log(f"[게이트] {tool}: (S) p<{FAKE_P} 비율 {gt.s_rate:.4f} (≤{FAKE_MAX} {'합격' if gt.s_pass else '불합격'}) · "
            f"(F) {gt.f_count}/{gt.f_total} 패턴 (≤{gt.f_max} {'합격' if gt.f_pass else '불합격'}) → "
            f"{'통과' if gt.passed else '탈락'}")
        if gt.passed:
            out.tool = tool
            break
    if out.tool == TOOL_FAIL:
        log("[게이트] CR1·CGM 모두 탈락 → 판정 불가(도구)")
    return out


def t3_test(panel: T3Panel, delta: Sequence[float], codes: Sequence[str], blocks: Sequence[int]) -> T3Panel:
    """게이트를 통과한 도구로만 진짜 p·95% CI(CR1 = 정규 · CGM = t(G_b − 1)). 탈락·B<5 면 검정하지 않는다."""
    if panel.B < B_MIN or panel.tool == TOOL_FAIL:
        panel.test = None
        return panel
    panel.test = tool_test(panel.tool, np.asarray(delta, dtype=float), np.asarray(codes), np.asarray(blocks))
    return panel


# ── 라벨(§9) ─────────────────────────────────────────────────────────────
@dataclass
class Verdict:
    label: str
    reason: str
    text: str = ""


def panel_outcome(pn: T3Panel) -> Tuple[str, str]:
    """판 하나의 ①(도구)·⑤(p·CI·θ₃) 결과 — ②③ 은 판과 무관해 `decide` 에서 본다."""
    if pn.B < B_MIN:
        return LAB_NA, f"도구(B={pn.B}<{B_MIN})"
    if pn.tool == TOOL_FAIL or pn.test is None:
        return LAB_NA, "도구(자기 표본 게이트 탈락 · 2원 재게이트 포함)"
    t = pn.test
    if t["p"] < ALPHA and t["mean"] >= THETA3:
        return LAB_UP, ""
    if t["ci_hi"] < THETA3:
        return LAB_NOT, ""
    return LAB_NA, "p·CI·θ₃ 어느 라벨 조건도 아님"


def decide(panels: Dict[str, T3Panel], fidelity_any_pass: bool, n: int, G: int) -> Verdict:
    """판정 순서 ① 도구 게이트(B≥5 · 자기 표본) ② 충실도 ③ n·G ④ 판 L/M ⑤ p·CI·θ₃ — 앞 단계 탈락 = 판정 불가."""
    outs = {k: panel_outcome(p) for k, p in panels.items()}
    tool_fail = [f"판 {k}: {r}" for k, (lab, r) in outs.items() if r.startswith("도구")]
    if tool_fail:
        return Verdict(LAB_NA, "① " + " · ".join(tool_fail))
    if not fidelity_any_pass:
        return Verdict(LAB_NA, "② 충실도 전 전략 미달")
    if n < N_MIN or G < G_MIN:
        return Verdict(LAB_NA, f"③ T3 n={n} · G={G} (기준 n ≥ {N_MIN} ∧ G ≥ {G_MIN})")
    labs = {lab for lab, _ in outs.values()}
    if len(labs) != 1:
        return Verdict(LAB_NA, "④ 판 L/M 불일치(" + " · ".join(f"{k}={lab}" for k, (lab, _) in outs.items()) + ")")
    lab = labs.pop()
    if lab == LAB_UP:
        return Verdict(LAB_UP, "", TEXT_UP)
    if lab == LAB_NOT:
        return Verdict(LAB_NOT, "", TEXT_NOT)
    return Verdict(LAB_NA, "⑤ " + " · ".join(f"판 {k}: {r}" for k, (_, r) in outs.items()))


# ── T1/T2 도구 게이트(봉인 단계 · 대조 팔 값만) ─────────────────────────────
@dataclass
class FakeUnit:
    """가짜 이벤트 재료 — 이벤트 하나의 대조 집합(종목코드 오름차순)과 각 대조의 이진 값·블록."""
    controls: List[str]
    y: Dict[str, float]
    block: int


def _p2(y1, c1, y0, c0, w0) -> Dict[str, float]:
    from backtest.concept_axes.candidate_ledger.exit_diag.run_random_entry import p2_binary
    return p2_binary(np.asarray(y1, float), np.asarray(c1), np.asarray(y0, float), np.asarray(c0), np.asarray(w0, float))


def p2_two_sided(r: Dict[str, float]) -> float:
    pu, pd_ = r.get("p_up"), r.get("p_down")
    if pu is None or pd_ is None or pu != pu or pd_ != pd_:
        return 1.0
    return min(1.0, 2.0 * min(pu, pd_))


def p2_cgm(y1, c1, b1, y0, c0, b0, w0) -> Dict[str, float]:
    """p2_binary 와 같은 ψ(CR1 · (N−1)/(N−K) 포함)를 종목·블록·교차로 묶은 2원판 — DART run_dart_events.stats_binary 선례."""
    y1, y0, w0 = np.asarray(y1, float), np.asarray(y0, float), np.asarray(w0, float)
    n1, W0 = float(len(y1)), float(w0.sum())
    if n1 < 2 or W0 <= 0:
        return dict(delta=float("nan"), se=float("nan"), p=1.0, Gb=0)
    m1, m0 = float(y1.mean()), float((w0 * y0).sum() / W0)
    psi = np.concatenate([(y1 - m1) / n1, -(w0 * (y0 - m0)) / W0])
    cs = np.concatenate([np.asarray(c1).astype(str), np.asarray(c0).astype(str)])
    bs = np.concatenate([np.asarray(b1).astype(str), np.asarray(b0).astype(str)])
    N, K = n1 + W0, 2

    def V(lab: np.ndarray) -> Tuple[float, int]:
        u, inv = np.unique(lab, return_inverse=True)
        G = len(u)
        if G < 2:
            return float("nan"), G
        s = np.bincount(inv, weights=psi, minlength=G)
        return G / (G - 1) * (N - 1) / (N - K) * float((s ** 2).sum()), G

    vs, _ = V(cs)
    vb, gb = V(bs)
    vsb, _ = V(np.char.add(np.char.add(cs, "|"), bs))
    v = vs + vb - (vsb if vsb == vsb else 0.0)
    if not (v > 0):
        cand = [x for x in (vs, vb) if x == x]
        v = max(cand) if cand else float("nan")
    d = m1 - m0
    se = math.sqrt(v) if v == v and v > 0 else float("nan")
    return dict(delta=d, se=se, p=p_t(d, se, gb - 1), Gb=gb)


def t12_draws(units: Sequence[FakeUnit], j: int) -> List[str]:
    """§7 T1/T2 ② — `default_rng([20261017, 11, j])` 로 정렬 순서대로 이벤트별 대조 집합(종목코드 오름차순)에서 1개 균등."""
    rng = np.random.default_rng([SEED0, 11, j])
    return [u.controls[int(rng.integers(0, len(u.controls)))] for u in units]


def t12_fake_gate(units: Sequence[FakeUnit], n_fake: int = N_FAKE, two_way: bool = False) -> Dict[str, Any]:
    """§7 T1/T2 ①~④(⑤ = two_way=True) — units 는 (t, 전략, 종목, id) 정렬 · |C(i)| ≥ 2 만 넣는다(호출자)."""
    rej = 0
    ses: List[float] = []
    for j in range(1, n_fake + 1):
        picks = t12_draws(units, j)
        y1: List[float] = []
        c1: List[str] = []
        b1: List[int] = []
        y0: List[float] = []
        c0: List[str] = []
        b0: List[int] = []
        w0: List[float] = []
        for u, h in zip(units, picks):
            y1.append(u.y[h])
            c1.append(h)
            b1.append(u.block)
            rest = [c for c in u.controls if c != h]
            for c in rest:
                y0.append(u.y[c])
                c0.append(c)
                b0.append(u.block)
                w0.append(1.0 / len(rest))
        if two_way:
            r = p2_cgm(y1, c1, b1, y0, c0, b0, w0)
            p = r["p"]
        else:
            r = _p2(y1, c1, y0, c0, w0)
            p = p2_two_sided(r)
        if r.get("se") == r.get("se"):
            ses.append(float(r["se"]))
        rej += p < FAKE_P
    rate = rej / n_fake if n_fake else float("nan")
    return dict(rate=rate, passed=rate <= FAKE_MAX, se_mean=float(np.mean(ses)) if ses else float("nan"),
                n_units=len(units))


def mde_t3(sd: float, n: int) -> Dict[str, float]:
    """§8 `MDE = K·sd/√n`(sd = ⓑ 로트 수익률 집계 sd — sd_Δ 대용) · DEFF 2·4 배수."""
    if n < 1 or sd != sd:
        return dict(mde=float("nan"), deff2=float("nan"), deff4=float("nan"))
    m = K_MDE * sd / math.sqrt(n)
    return dict(mde=m, deff2=m * math.sqrt(2.0), deff4=m * 2.0)
