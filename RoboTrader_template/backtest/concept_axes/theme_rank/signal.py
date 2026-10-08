"""테마 돌출도 S 와 인쇄 항목(스펙 §4-1 · §4-5) — 순수 함수 · DB 없음.

S_c = −log10( min(1, m_c · min_T p_T) ),  p_T = P(Bin(n_T, p0_D) ≥ k_T) (k_T ≥ 2 일 때만, 아니면 1).
꼬리 확률은 로그 공간(`math.lgamma`)으로 계산해 언더플로하지 않는다. p0 하한 = 1/(2|U_D|).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import FrozenSet, Mapping, Optional, Sequence

JUMP_THR = 0.05          # 🔒 튄 종목 = 시장 대비 +5%p 이상
K_MIN = 2                # 🔒 동료 2개 이상 튀어야 센다
LIMIT_UP_R = 0.295       # 인쇄 B′ — 상한가로 보는 당일 등락률
STREAK_LOGP = -2.0       # 인쇄 A″ — 테마 p_T < 0.01 인 날을 「강세 일차」로 센다
_LN10 = math.log(10.0)


def log10_binom_tail(n: int, p: float, k: int) -> float:
    """log10 P(X ≥ k), X ~ Bin(n, p)."""
    if k <= 0:
        return 0.0
    if k > n or p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    terms = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq
             for i in range(k, n + 1)]
    mx = max(terms)
    return min(0.0, (mx + math.log(sum(math.exp(t - mx) for t in terms))) / _LN10)


@dataclass(frozen=True)
class DayState:
    universe: FrozenSet[str]
    jumped: FrozenSet[str]
    p0: float


def day_state(excess: Mapping[str, float], thr: float = JUMP_THR) -> DayState:
    n = len(excess)
    jumped = frozenset(c for c, e in excess.items() if e >= thr)
    p0 = max(len(jumped) / n, 0.5 / n) if n else math.nan
    return DayState(frozenset(excess), jumped, p0)


@dataclass(frozen=True)
class Surprise:
    s: float
    log10_p: float
    m: int
    main_theme: Optional[int]
    k_main: int
    n_main: int
    single: bool


def surprise(code: str, themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]],
             st: DayState, k_min: int = K_MIN) -> Surprise:
    best_lp, best_t, best_k, best_n = 0.0, None, 0, 0
    m = 0
    for t in sorted(themes_of.get(code, ())):
        peers = (members[t] - {code}) & st.universe
        n = len(peers)
        if n < 1:
            continue
        m += 1
        k = len(peers & st.jumped)
        lp = log10_binom_tail(n, st.p0, k) if k >= k_min else 0.0
        if lp < best_lp:
            best_lp, best_t, best_k, best_n = lp, t, k, n
    if m == 0:
        return Surprise(0.0, 0.0, 0, None, 0, 0, True)
    lpc = min(0.0, math.log10(m) + best_lp)
    return Surprise(-lpc, lpc, m, best_t, best_k, best_n, False)


def mean_excess_max(code: str, themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]],
                    excess: Mapping[str, float]) -> Optional[float]:
    """인쇄 A — 테마별 동료(자기 제외 · 그날 수익률 있는 종목) 동일가중 초과수익의 최댓값."""
    vals = []
    for t in sorted(themes_of.get(code, ())):  # 합산 순서 고정(frozenset 순회 = 해시 무작위 → 재실행 md5 재현)
        xs = [excess[c] for c in sorted(members[t]) if c != code and c in excess]
        if xs:
            vals.append(sum(xs) / len(xs))
    return max(vals) if vals else None


def same_theme_count(code: str, theme: Optional[int], members: Mapping[int, FrozenSet[str]],
                     day_codes: FrozenSet[str]) -> int:
    """인쇄 C — 그날 조건 통과 후보 전체 중 같은 주 테마 후보 수(자기 제외)."""
    return 0 if theme is None else len((members[theme] - {code}) & day_codes)


def rank_in_theme(code: str, theme: Optional[int], members: Mapping[int, FrozenSet[str]],
                  excess: Mapping[str, float]) -> Optional[int]:
    """인쇄 B′ — 주 테마 소속 전체(자기 포함) 안에서 당일 초과수익 순위(1 = 최고). 순위 = 1 + 자기보다 큰 수."""
    if theme is None or code not in excess:
        return None
    me = excess[code]
    return 1 + sum(1 for c in members[theme] if c != code and c in excess and excess[c] > me)


def theme_logp(theme: int, members: Mapping[int, FrozenSet[str]], st: DayState, k_min: int = K_MIN) -> float:
    """테마 자체의 그날 log10 p_T(소속 전체 · 자기 제외 없음) — A″ 계산용."""
    inside = members[theme] & st.universe
    k = len(inside & st.jumped)
    return log10_binom_tail(len(inside), st.p0, k) if k >= k_min else 0.0


def streak(logps: Sequence[float], thr: float = STREAK_LOGP) -> int:
    """인쇄 A″ — 끝에서부터 연속으로 logp < thr 인 날 수."""
    n = 0
    for v in reversed(list(logps)):
        if v < thr:
            n += 1
        else:
            break
    return n
