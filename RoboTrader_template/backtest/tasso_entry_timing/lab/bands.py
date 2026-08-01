"""하락폭 분포 → 5분할 매수 사다리.

역설계 근거: 삼성 화면 Q1 35.3 / Q3 56.0 → 레벨 5개가
37.33 / 41.48 / 45.63 / 49.78 / 53.93 % 하락 지점에 4.15%p 등간격으로 놓임.
중심 = (Q1+Q3)/2 = 45.65, 전체폭 = 16.60 = 0.802 × IQR(20.7).
⚠️ 이 계수는 삼성 1건에서만 검증됐다(다날은 Q1/Q3 미관측).
"""
from __future__ import annotations

import math

import numpy as np

WEIGHTS: tuple[float, ...] = (0.10, 0.13, 0.17, 0.25, 0.35)

# 상승폭 버킷 하한 (설계 §7)
BUCKETS = (0.20, 0.50, 1.00, 2.00, 4.00)

# 외생 상수 2점: (상승폭, 밴드중심) — 삼성/다날 화면 실측
_EXO = ((0.298, 0.1590), (6.143, 0.4565))
_EXO_IQR_RATIO = 0.207 / 0.4565   # 삼성 IQR / 중심 → 중심에 비례해 IQR 추정


def ladder(peak: float, q1: float, q3: float, c: float = 0.8) -> list[float]:
    """5분할 매수 지정가. 1차가 최고가(하락폭 최소), 5차가 최저가."""
    center = (q1 + q3) / 2.0
    width = c * (q3 - q1)
    return [peak * (1.0 - (center + (k - 3) * width / 4.0)) for k in range(1, 6)]


def _bucket(gain: float) -> int:
    idx = 0
    for i, lo in enumerate(BUCKETS):
        if gain >= lo:
            idx = i
    return idx


def pit_quantiles(history, gain: float, min_n: int = 30, trim: float = 0.025):
    """과거 (상승폭, 하락폭) 표본에서 같은 버킷의 Q1/Q3. 표본 부족이면 None."""
    b = _bucket(gain)
    dd = np.array([d for g, d in history if _bucket(g) == b], dtype=float)
    if dd.size < min_n:
        return None
    lo, hi = np.quantile(dd, [trim, 1.0 - trim])
    dd = dd[(dd >= lo) & (dd <= hi)]
    if dd.size < min_n:
        return None
    q1, q3 = np.quantile(dd, [0.25, 0.75])
    return float(q1), float(q3)


def exogenous_quantiles(gain: float) -> tuple[float, float]:
    """삼성·다날 2점을 log(상승폭) 상에서 선형보간해 밴드를 고정한다.

    ⚠️ 2점 보간이라 상승폭 29.8% 미만과 614% 초과는 외삽이다.
    """
    (g0, c0), (g1, c1) = _EXO
    x0, x1, x = math.log(g0), math.log(g1), math.log(max(gain, 1e-6))
    t = (x - x0) / (x1 - x0)
    center = c0 + t * (c1 - c0)
    iqr = center * _EXO_IQR_RATIO
    return center - iqr / 2.0, center + iqr / 2.0
