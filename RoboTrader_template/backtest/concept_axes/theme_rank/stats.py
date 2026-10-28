"""검정 통계(스펙 §5-2 · §5-3 · §5-5) — 순수 함수 · scipy 없음.

`hac_t` 는 NewsQuant `news_scraper/backtest/metrics.hac_t`(2026-10-07 `4f833cb`)와 같은 식이다
(Bartlett 커널 · γ0 = 모집단 분산 · 정규근사 양측 p). 두 레포의 판정 통계를 맞추려고 그대로 옮겼다.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, FrozenSet, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    xs, ys = pd.Series(list(x), dtype=float), pd.Series(list(y), dtype=float)
    if xs.nunique() < 2 or ys.nunique() < 2:
        return float("nan")
    return float(xs.rank(method="average").corr(ys.rank(method="average")))


def daily_ic(df: pd.DataFrame, sig: str, ret: str, day: str = "scan_date", min_n: int = 5,
             min_distinct: int = 2) -> Tuple[pd.Series, int]:
    """날짜별 Spearman(sig, ret). 제외 = 행 < min_n ∨ sig 서로 다른 값 < min_distinct ∨ ret 상수. (IC, 제외 일수)."""
    vals: Dict[object, float] = {}
    skipped = 0
    for d, g in df.groupby(day, sort=True):
        g = g[[sig, ret]].dropna()
        if len(g) < min_n or g[sig].nunique() < min_distinct or g[ret].nunique() < 2:
            skipped += 1
            continue
        vals[d] = spearman(g[sig], g[ret])
    return pd.Series(vals, dtype=float), skipped


def hac_t(ic: pd.Series, lag: int) -> Dict[str, float]:
    nan = float("nan")
    x = pd.Series(ic, dtype=float).dropna().to_numpy(dtype=float)
    n = int(x.size)
    out = {"n_days": n, "mean_ic": nan, "se_hac": nan, "t_hac": nan, "p_hac": nan, "lag": int(lag)}
    if n == 0:
        return out
    mean = float(x.mean())
    out["mean_ic"] = mean
    if n < lag + 2:
        return out
    d = x - mean if np.ptp(x) > 0 else np.zeros_like(x)
    var = float(d @ d) / n
    for k in range(1, lag + 1):
        var += 2.0 * (1.0 - k / (lag + 1)) * float(d[k:] @ d[:-k]) / n
    if not var > 0:
        return out
    se = math.sqrt(var / n)
    t = mean / se
    out.update(se_hac=se, t_hac=t, p_hac=math.erfc(abs(t) / math.sqrt(2)))
    return out


def degree_preserving_shuffle(members: Mapping[int, FrozenSet[str]], rng: np.random.Generator,
                              swaps_per_edge: int = 10) -> Dict[int, FrozenSet[str]]:
    """테마 크기·종목별 소속 수를 보존하는 이분 그래프 간선 교환(플라시보 · 스펙 §5-5)."""
    edges: List[Tuple[int, str]] = [(t, c) for t in sorted(members) for c in sorted(members[t])]
    eset = set(edges)
    n = len(edges)
    for _ in range(swaps_per_edge * n):
        i, j = (int(v) for v in rng.integers(n, size=2))
        (t1, c1), (t2, c2) = edges[i], edges[j]
        if t1 == t2 or c1 == c2 or (t1, c2) in eset or (t2, c1) in eset:
            continue
        eset.difference_update({(t1, c1), (t2, c2)})
        eset.update({(t1, c2), (t2, c1)})
        edges[i], edges[j] = (t1, c2), (t2, c1)
    out: Dict[int, set] = {t: set() for t in members}
    for t, c in edges:
        out[t].add(c)
    return {t: frozenset(v) for t, v in out.items()}


def ar1_noise(theme_nos: Iterable[int], n_days: int, phi: float, rng: np.random.Generator) -> Dict[int, np.ndarray]:
    """테마별 정상 AR(1) 표준정규 잡음(분산 1) — 가짜 테마 신호(스펙 §5-3)."""
    out: Dict[int, np.ndarray] = {}
    s = math.sqrt(1.0 - phi * phi)
    for t in sorted(theme_nos):
        e = rng.standard_normal(n_days)
        z = np.empty(n_days)
        z[0] = e[0]
        for i in range(1, n_days):
            z[i] = phi * z[i - 1] + s * e[i]
        out[t] = z
    return out


def upper_p(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def fake_s(code: str, themes_of: Mapping[str, FrozenSet[int]], members: Mapping[int, FrozenSet[str]],
           noise_today: Mapping[int, float]) -> float:
    """실제 S 와 같은 구조(동료 있는 테마만 · 최소 p · 테마 수 보정)를 잡음 z 로 만든 가짜 S."""
    ts = [t for t in themes_of.get(code, ()) if len(members[t] - {code}) >= 1 and t in noise_today]
    if not ts:
        return 0.0
    p = min(upper_p(noise_today[t]) for t in ts)
    return -min(0.0, math.log10(len(ts)) + math.log10(max(p, 1e-300)))


def episode_first(df: pd.DataFrame, cal_idx: Mapping[date, int]) -> pd.DataFrame:
    """같은 종목의 «연속 거래일» 후보 묶음마다 첫 행만(스펙 §5-7 민감도)."""
    o = df.copy()
    o["_i"] = o["scan_date"].map(cal_idx)
    o = o.sort_values(["stock_code", "_i"], kind="mergesort")
    prev = o.groupby("stock_code")["_i"].shift(1)
    keep = prev.isna() | (o["_i"] - prev != 1)
    return o.loc[keep].drop(columns="_i").reset_index(drop=True)
