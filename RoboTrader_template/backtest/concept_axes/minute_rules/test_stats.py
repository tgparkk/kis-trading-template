"""통계 «모듈»(pytest 파일 아님 · 이름 = 사전등록 §9) — 짝 차 · 블록 부트스트랩/순열 · 2원 군집 · Holm · 가짜 · IPW.

규범 = `docs/prereg_2026-11-11_minute_rules.md` §5-3·§5-4·§5-6. 순수 numpy(DB·파일 없음). 수집 제외 = 같은 폴더
`conftest.py` 의 `collect_ignore`(이 이름이 pytest 기본 패턴 `test_*.py` 에 걸리므로) · 이 모듈에는 `test` 로 시작하는
이름을 두지 않는다.

🔒 정의
  시점 δ̄  = 로트 짝 차 δ_i = ret(규칙) − ret(R0) 의 평균 · 분모 = 모든 로트(안 걸린 로트 δ=0 · 결정 ②) ·
           δ̄_aff · f(걸린 몫)는 따로(판정 아님) · p = 매수일 블록 부트스트랩 B=10,000.
  거르기 Δ = Σ_d w_d(keep 평균_d − filter 평균_d) / Σ_d w_d · w_d = n_k·n_s/(n_k+n_s) · 한쪽만 있는 날 기여 0 ·
           p = 블록(매수일) 안 라벨 섞기 10,000회 · `undetermined` 는 호출 전에 뺀다.
  2원 군집 = 종목×날짜 두 축을 독립으로 복원 추출하고 관측 가중 = (종목 뽑힌 수)×(날짜 뽑힌 수)(Owen 2007 «pigeonhole»).
  Holm   = 비교값(단측 = 2×p_단측 · 양측 = p_양측 · 1 상한) 오름차순 k번째 ≤ α/(m−k+1) 를 1번째부터 연속 만족한 것만 ·
           m = 등록 수 고정(빠진 규칙 = p 1).
  가짜 규칙 = p<0.05 비율 > 0.075 → 그 분류의 판정 p 를 2원 군집 p 로(`use_twoway`).
  IPW    = P(보유 | 순위 구간, 월) 칸 빈도의 역수 · 상한 20 · ESS = (Σw)²/Σw².
⚙ 사전등록이 정하지 않아 여기서 정한 것(보고서에 적는다): 부트스트랩 p = 귀무 중심화(«basic») T*−T̂ 를 T̂ 와 비교 ·
  +1 보정 (1+#)/(B+1) · 순열 p 도 +1 보정 · 가짜 규칙 p 는 양측 · 구간 = «basic»(p 와 같은 순서통계량 · 수정 1
  결정 3 · 양측 p = 2·min 등꼬리 · §7 D1) ·
  한 규칙의 rng 는 [20261111, w, r] 하나를 «주 검정(시점: 같은 표본으로 구간) → 구간(거르기) → 2원 군집» 순서로 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

SEED_BASE = 20261111
W_E, W_C, W_C2, W_U, W_FAKE = 0, 1, 2, 3, 4
RULE_NO = {"R1": 1, "R3": 3, "R4": 4, "R5": 5, "R6": 6, "R7": 7, "H2_HIST": 21, "H_PLUS2": 22}
FAKE_FILTER_R0 = 0                 # 가짜 거르기 k 의 r = 0 + k
FAKE_TIMING_R0 = 100               # 가짜 시점 k 의 u 추출 r = 100 + k(run.py) · 그 p 의 r = 200 + k
FAKE_TIMING_P_R0 = 200
B_DEFAULT = 10_000
ALPHA = 0.05
FAKE_CUT, FAKE_SWITCH = 0.05, 0.075
IPW_CAP = 20.0
GREATER, LESS, TWO = "greater", "less", "two-sided"


def rng_for(w: int, r: int) -> np.random.Generator:
    """🔒 §5-3 시드 `default_rng([20261111, w, r])`."""
    return np.random.default_rng([SEED_BASE, w, r])


def _codes(ids: Sequence) -> Tuple[np.ndarray, int]:
    uniq, inv = np.unique(np.asarray(ids), return_inverse=True)
    return inv.astype(np.int64), len(uniq)


# ── 짝 차(시점) ───────────────────────────────────────────────────────────
@dataclass
class TimingStat:
    n: int
    mean: float                    # δ̄ (분모 = 모든 로트)
    f: float                       # 걸린 몫
    mean_aff: Optional[float]      # 걸린 로트만의 평균(판정 아님)


def paired_delta(rule_ret: Sequence[float], base_ret: Sequence[float]) -> np.ndarray:
    """δ_i = ret(규칙) − ret(기준) · 한쪽이 결측(NaN · 민감도 b)이면 그 짝은 NaN(호출자가 뺀다)."""
    return np.asarray(rule_ret, dtype=np.float64) - np.asarray(base_ret, dtype=np.float64)


def timing_stat(delta: Sequence[float], affected: Optional[Sequence[bool]] = None) -> TimingStat:
    d = np.asarray(delta, dtype=np.float64)
    aff = (d != 0) if affected is None else np.asarray(affected, dtype=bool)
    n = len(d)
    return TimingStat(n, float(d.mean()) if n else float("nan"), float(aff.mean()) if n else float("nan"),
                      float(d[aff].mean()) if aff.any() else None)


def block_boot_means(delta: Sequence[float], days: Sequence, B: int, rng: np.random.Generator,
                     chunk: int = 1000) -> np.ndarray:
    """매수일 블록 부트스트랩 — 날짜를 복원 추출하고 뽑힌 날의 로트 전부로 평균(Σ합/Σ수)."""
    d = np.asarray(delta, dtype=np.float64)
    g, G = _codes(days)
    s = np.bincount(g, weights=d, minlength=G)
    c = np.bincount(g, minlength=G).astype(np.float64)
    out = np.empty(B)
    for i in range(0, B, chunk):
        b = min(chunk, B - i)
        idx = rng.integers(0, G, size=(b, G))
        out[i: i + b] = s[idx].sum(axis=1) / c[idx].sum(axis=1)
    return out


def _finite(boot: np.ndarray) -> np.ndarray:
    b = np.asarray(boot, dtype=np.float64)
    return b[np.isfinite(b)]


def p_boot(t_hat: float, boot: np.ndarray, alternative: str) -> float:
    """귀무 중심화 부트스트랩 p — z = T* − T̂ · 단측 = (1+#{z ≥ T̂})/(B+1)(less = #{z ≤ T̂}) ·
    🔒 양측 = min(1, 2·min(p_greater, p_less))(등꼬리 · 수정 1 §7 D1 — basic 구간과 같은 조건) · 유한값만 센다."""
    b = _finite(boot)
    if not b.size or t_hat != t_hat:
        return float("nan")
    two_t = 2.0 * t_hat                       # z ≥ T̂ ⇔ T* ≥ 2T̂ — 구간과 같은 비교(부동소수 일치)
    pg = (1 + int((b >= two_t).sum())) / (len(b) + 1)
    pl = (1 + int((b <= two_t).sum())) / (len(b) + 1)
    if alternative == GREATER:
        return pg
    if alternative == LESS:
        return pl
    if alternative == TWO:
        return min(1.0, 2.0 * min(pg, pl))
    raise ValueError(alternative)


def basic_ci(boot: np.ndarray, t_hat: float, alpha: float) -> Tuple[float, float]:
    """🔒 수정 1 결정 3(+§7 D1) — p 와 같은 순서통계량으로 낸 «basic» 구간(2T̂ − t_(n−m), 2T̂ − t_(m+1)).

    m = floor(α/2·(n+1)) − 1 · t_(i) = 오름차순 i번째(1-based · t_(0) = −∞ · t_(n+1) = +∞). 이렇게 정하면
    «하한 > 0 ⇔ p_greater ≤ α/2» · «상한 < 0 ⇔ p_less ≤ α/2» 가 정확히 같다(+1 보정·분위 보간 차이 없음) →
    양측 p(= 2·min) ≤ α ⇔ 구간이 0 을 벗어남 · 단측 비교값 2p ≤ α_k ⇔ 유리한 쪽 경계가 0 밖(§5-4)."""
    b = np.sort(_finite(boot))
    n = len(b)
    if not n or t_hat != t_hat:
        return float("nan"), float("nan")
    m = int(np.floor(alpha / 2.0 * (n + 1))) - 1

    def order(i: int) -> float:
        return float("-inf") if i < 1 else float("inf") if i > n else float(b[i - 1])
    return float(2 * t_hat - order(n - m)), float(2 * t_hat - order(m + 1))


# ── 거르기 Δ · 블록 안 순열 ───────────────────────────────────────────────
@dataclass
class FilterStat:
    delta: float
    n_keep: int
    n_filter: int
    n_info_days: int               # 두 군이 다 있는 날 수
    f: float                       # filter 몫(f < 0.15 = 판정 불가 · §5-3)


def _day_delta(sk: np.ndarray, ck: np.ndarray, sf: np.ndarray, cf: np.ndarray) -> np.ndarray:
    """per-day 합·수(마지막 축 = 날짜) → Δ(앞 축들). 한쪽 0 인 날 w_d = 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.where((ck > 0) & (cf > 0), ck * cf / (ck + cf), 0.0)
        diff = np.where(w > 0, sk / np.where(ck > 0, ck, 1) - sf / np.where(cf > 0, cf, 1), 0.0)
        sw = w.sum(axis=-1)
        return np.where(sw > 0, (w * diff).sum(axis=-1) / np.where(sw > 0, sw, 1), np.nan)


def filter_stat(ret: Sequence[float], keep: Sequence[bool], days: Sequence,
                weights: Optional[Sequence[float]] = None) -> FilterStat:
    """Δ = 날짜 가중 keep − filter 평균 · `weights`(IPW·2원 군집) 가 있으면 n_k·n_s 와 평균을 가중 합으로."""
    r = np.asarray(ret, dtype=np.float64)
    k = np.asarray(keep, dtype=bool)
    w = np.ones(len(r)) if weights is None else np.asarray(weights, dtype=np.float64)
    g, G = _codes(days)
    sk = np.bincount(g, weights=w * r * k, minlength=G)
    ck = np.bincount(g, weights=w * k, minlength=G)
    sf = np.bincount(g, weights=w * r * ~k, minlength=G)
    cf = np.bincount(g, weights=w * ~k, minlength=G)
    return FilterStat(float(_day_delta(sk, ck, sf, cf)), int(k.sum()), int((~k).sum()),
                      int(((ck > 0) & (cf > 0)).sum()), float((~k).mean()) if len(k) else float("nan"))


def filter_perm(ret: Sequence[float], keep: Sequence[bool], days: Sequence, B: int, rng: np.random.Generator,
                chunk: int = 500) -> np.ndarray:
    """블록(매수일) 안 라벨 섞기 B 회의 Δ — 날마다 keep 수는 그대로."""
    r = np.asarray(ret, dtype=np.float64)
    k = np.asarray(keep, dtype=bool)
    g, G = _codes(days)
    order = np.argsort(g, kind="stable")
    r, k, g = r[order], k[order], g[order]
    out = np.empty(B)
    for i in range(0, B, chunk):
        b = min(chunk, B - i)
        perm = np.argsort(rng.random((b, len(r))) + g[None, :], axis=1)
        kp = k[perm]
        sk = _rows_bincount(g, r[None, :] * kp, G)
        ck = _rows_bincount(g, kp.astype(np.float64), G)
        sf = _rows_bincount(g, r[None, :] * ~kp, G)
        cf = _rows_bincount(g, (~kp).astype(np.float64), G)
        out[i: i + b] = _day_delta(sk, ck, sf, cf)
    return out


def _rows_bincount(g: np.ndarray, vals: np.ndarray, G: int) -> np.ndarray:
    """vals [b, n] 의 행마다 날짜별 합 → [b, G](원-핫 행렬곱)."""
    onehot = np.zeros((len(g), G))
    onehot[np.arange(len(g)), g] = 1.0
    return vals @ onehot


def p_perm(t_hat: float, perm: np.ndarray, alternative: str) -> float:
    """순열 p — 귀무 분포에서 T̂ 이상(이하·절대값 이상) · (1+#)/(B+1)."""
    perm = np.asarray(perm)
    perm = perm[np.isfinite(perm)]
    if alternative == GREATER:
        k = int((perm >= t_hat).sum())
    elif alternative == LESS:
        k = int((perm <= t_hat).sum())
    elif alternative == TWO:
        k = int((np.abs(perm) >= abs(t_hat)).sum())
    else:
        raise ValueError(alternative)
    return (1 + k) / (len(perm) + 1)


def filter_block_boot(ret: Sequence[float], keep: Sequence[bool], days: Sequence, B: int,
                      rng: np.random.Generator, chunk: int = 1000) -> np.ndarray:
    """거르기 Δ 의 매수일 블록 부트스트랩(구간용) — 뽑힌 날의 per-day 합·수를 그대로 더한다."""
    r = np.asarray(ret, dtype=np.float64)
    k = np.asarray(keep, dtype=bool)
    g, G = _codes(days)
    per = [np.bincount(g, weights=v, minlength=G) for v in (r * k, k.astype(float), r * ~k, (~k).astype(float))]
    out = np.empty(B)
    for i in range(0, B, chunk):
        b = min(chunk, B - i)
        idx = rng.integers(0, G, size=(b, G))
        out[i: i + b] = _day_delta(*(p[idx] for p in per))
    return out


# ── 2원 군집(종목 × 날짜) ─────────────────────────────────────────────────
def twoway_weights(stocks: Sequence, days: Sequence, B: int, rng: np.random.Generator) -> np.ndarray:
    """[B, n] 관측 가중 = 종목 뽑힌 수 × 날짜 뽑힌 수(두 축 독립 복원 추출)."""
    s, S = _codes(stocks)
    d, Dn = _codes(days)
    cs = np.stack([np.bincount(rng.integers(0, S, S), minlength=S) for _ in range(B)])
    cd = np.stack([np.bincount(rng.integers(0, Dn, Dn), minlength=Dn) for _ in range(B)])
    return (cs[:, s] * cd[:, d]).astype(np.float64)


def twoway_boot(stat: Callable[[np.ndarray], float], stocks: Sequence, days: Sequence, B: int,
                rng: np.random.Generator, chunk: int = 500) -> np.ndarray:
    """통계량 `stat(weights[n]) -> float` 의 2원 군집 부트스트랩 분포(가중 0 행 = 빠짐)."""
    out = np.empty(B)
    for i in range(0, B, chunk):
        b = min(chunk, B - i)
        W = twoway_weights(stocks, days, b, rng)
        out[i: i + b] = [stat(w) for w in W]
    return out


def weighted_mean_stat(delta: Sequence[float]) -> Callable[[np.ndarray], float]:
    d = np.asarray(delta, dtype=np.float64)

    def f(w: np.ndarray) -> float:
        sw = w.sum()
        return float((w * d).sum() / sw) if sw > 0 else float("nan")
    return f


def filter_weighted_stat(ret: Sequence[float], keep: Sequence[bool], days: Sequence) -> Callable[[np.ndarray], float]:
    def f(w: np.ndarray) -> float:
        return filter_stat(ret, keep, days, weights=w).delta
    return f


# ── Holm ─────────────────────────────────────────────────────────────────
@dataclass
class HolmRow:
    rule: str
    compare: float                 # 비교값(단측 2p · 양측 p)
    order: int                     # 1-based 오름차순 위치
    threshold: float               # α/(m−k+1) — 조정 구간 수준(1 − threshold)
    rejected: bool


def compare_value(p: float, one_sided: bool) -> float:
    """🔒 §5-4 단측 규칙 = 2×p_단측(사전 선언 방향) · 양측 = p_양측 · 1 상한."""
    return min(1.0, 2.0 * p if one_sided else p)


def holm(compare: Dict[str, float], m: Optional[int] = None, alpha: float = ALPHA) -> List[HolmRow]:
    """오름차순 k번째 ≤ α/(m−k+1) 를 1번째부터 연속 만족한 것만 기각 · 동점은 규칙 id 순 · m = 등록 수(기본 len)."""
    m = len(compare) if m is None else m
    if m < len(compare):
        raise ValueError("m 은 등록 규칙 수 이상")
    rows: List[HolmRow] = []
    going = True
    for k, (rule, p) in enumerate(sorted(compare.items(), key=lambda kv: (kv[1], kv[0])), start=1):
        thr = alpha / (m - k + 1)
        going = going and p <= thr
        rows.append(HolmRow(rule, p, k, thr, going))
    return rows


# ── 가짜 규칙 ─────────────────────────────────────────────────────────────
def fake_filter_keep(stocks: Sequence, f: float, rng: np.random.Generator) -> np.ndarray:
    """종목 상수 노이즈 거르기 — 종목마다 U(0,1) 1개 · U < f 인 종목의 로트 전부 filter(keep=False)."""
    s, S = _codes(stocks)
    return ~(rng.random(S) < f)[s]


def fake_rate(pvals: Sequence[float], cut: float = FAKE_CUT) -> float:
    p = np.asarray(pvals, dtype=np.float64)
    return float((p < cut).mean()) if len(p) else float("nan")


def use_twoway(rate: float, switch: float = FAKE_SWITCH) -> bool:
    """🔒 §5-3 — 가짜 규칙 p<0.05 비율 > 0.075 이면 그 분류의 판정 p 를 2원 군집 p 로."""
    return bool(rate > switch)


# ── IPW ──────────────────────────────────────────────────────────────────
@dataclass
class IpwOut:
    weights: np.ndarray            # 보유 로트 순서(`held` 가 참인 로트) · 상한 적용 뒤
    ess: float
    n_capped: int


def ipw_weights(held: Sequence[bool], bucket: Sequence, month: Sequence, cap: float = IPW_CAP) -> IpwOut:
    """P(보유 | 순위 구간, 월) = 칸 보유 비율 → 보유 로트 가중 1/P · 상한 cap · ESS."""
    h = np.asarray(held, dtype=bool)
    cells = [f"{b}|{m}" for b, m in zip(bucket, month)]
    c, C = _codes(cells)
    n = np.bincount(c, minlength=C).astype(np.float64)
    nh = np.bincount(c, weights=h.astype(float), minlength=C)
    p = nh[c[h]] / n[c[h]]
    w = 1.0 / p
    n_capped = int((w > cap).sum())
    w = np.minimum(w, cap)
    return IpwOut(w, ess(w), n_capped)


def ess(w: Sequence[float]) -> float:
    w = np.asarray(w, dtype=np.float64)
    return float(w.sum() ** 2 / (w ** 2).sum()) if len(w) and (w ** 2).sum() > 0 else 0.0
