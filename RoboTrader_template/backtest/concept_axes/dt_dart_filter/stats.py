"""날짜 고정효과 + 종목 CR1(+ 2원 클러스터) — 스펙 §3-5.

β = Σx̃ỹ/Σx̃² (x̃·ỹ = 날짜 안 평균 뺀 값 · 표식·대조가 둘 다 있는 날만) · ψ_i = x̃_i(ỹ_i − βx̃_i)/Σx̃².
small-sample 보정(CR1, Cameron–Miller/Stata areg 관례): c = G/(G−1) · (N−1)/(N−K).
  N = 날짜 필터 뒤 사용 행 수 · K = 1 + n_days (x 계수 + 흡수된 날짜 고정효과 — K 는 흡수된 날짜 FE 를 센다).
  N−K ≤ 0 또는 G < 2 이면 NaN SE.
V_CR1 = c·Σ_g(Σψ)² (종목 클러스터) · 2원 = V_종목 + V_블록 − V_종목×블록(≤0 이면 max).
  2원의 각 성분은 자기 G(G_종목·G_블록·G_종목×블록 = 비어있지 않은 셀 수)와 같은 (N−1)/(N−K) 를 쓴다.
단측 p 는 δ<0 방향. CR1 은 정규 근사 · 2원은 t(G_블록−1)(09-26 `stats_binary` 선례).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
import pandas as pd

from . import settings as S


@dataclass(frozen=True)
class FE:
    beta: float
    se_cr1: float
    se_2w: float
    p1_cr1: float
    p2_cr1: float
    p1_2w: float
    p2_2w: float
    n: int
    n1: int
    n_days: int
    g_stock: int
    g_block: int


def _ncdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _cluster_v(psi: pd.Series, keys: pd.Series, small: float):
    s = psi.groupby(keys.to_numpy()).sum()
    g = len(s)
    if g < 2 or not (small > 0):
        return float("nan"), g
    return g / (g - 1) * small * float((s * s).sum()), g


def both_arm_days_mask(x, day) -> np.ndarray:
    """그날 표식 ≥1 ∧ 대조 ≥1 인 날의 행만 True — fe_regression 과 seal 의 n₁ 이 같은 규칙을 쓴다."""
    d = pd.DataFrame({"x": np.asarray(x, float), "day": np.asarray(day)})
    g = d.groupby("day")["x"]
    return ((g.transform("max") > 0) & (g.transform("min") < 1)).to_numpy()


def fe_regression(y, x, day, stock, block) -> FE:
    df = pd.DataFrame({"y": np.asarray(y, float), "x": np.asarray(x, float), "day": np.asarray(day),
                       "stock": np.asarray(stock).astype(str), "block": np.asarray(block)})
    df = df[np.isfinite(df["y"])]
    df = df[both_arm_days_mask(df["x"], df["day"])]
    nan = float("nan")
    if df.empty:
        return FE(nan, nan, nan, nan, nan, nan, nan, 0, 0, 0, 0, 0)
    xt = df["x"] - df.groupby("day")["x"].transform("mean")
    yt = df["y"] - df.groupby("day")["y"].transform("mean")
    sxx = float((xt * xt).sum())
    beta = float((xt * yt).sum() / sxx)
    psi = xt * (yt - beta * xt) / sxx
    n_rows = len(df)
    k_par = 1 + int(df["day"].nunique())          # x 계수 + 흡수된 날짜 FE
    small = (n_rows - 1) / (n_rows - k_par) if n_rows - k_par > 0 else nan
    v_s, gs = _cluster_v(psi, df["stock"], small)
    v_b, gb = _cluster_v(psi, df["block"].astype(str), small)
    v_sb, _ = _cluster_v(psi, df["stock"] + "|" + df["block"].astype(str), small)
    v2 = v_s + v_b - v_sb
    if not (v2 > 0):
        v2 = max(v_s, v_b) if not (math.isnan(v_s) or math.isnan(v_b)) else nan
    se1 = math.sqrt(v_s) if v_s == v_s and v_s > 0 else nan
    se2 = math.sqrt(v2) if v2 == v2 and v2 > 0 else nan
    p1c = p2c = p1w = p2w = nan
    if se1 == se1:
        t1 = beta / se1
        p1c, p2c = _ncdf(t1), 2.0 * (1.0 - _ncdf(abs(t1)))
    if se2 == se2 and gb >= 2:
        from scipy.stats import t as tdist
        t2 = beta / se2
        dfree = max(1, gb - 1)
        p1w, p2w = float(tdist.cdf(t2, dfree)), float(2.0 * tdist.sf(abs(t2), dfree))
    return FE(beta, se1, se2, p1c, p2c, p1w, p2w, int(len(df)), int((df["x"] > 0).sum()),
              int(df["day"].nunique()), gs, gb)


def mde(se: float) -> float:
    return (S.Z_ALPHA + S.Z_POWER) * float(se)


def holm(ps: Sequence[float]) -> List[float]:
    """표준 Holm 조정 p. 비유한(NaN·None) p 는 1.0 으로 본다(critic B1 · 태그 표식 0 → NaN). 동점 = 입력 순서(안정 정렬)."""
    ps = [float(p) if p is not None and math.isfinite(float(p)) else 1.0 for p in ps]
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj = [0.0] * m
    run = 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (m - k) * ps[i]))
        adj[i] = round(run, 12)
    return adj
