"""대조군 — 진입 '가격'만 무작위. 비중·청산은 전략과 동일하게 붙는다."""
from __future__ import annotations

import numpy as np


def control_levels(peak: float, low_bound: float, rng: np.random.Generator, n: int = 5) -> list[float]:
    """[low_bound, peak] 구간에서 무작위 5개를 뽑아 내림차순으로 놓는다.

    전략과 같은 개수·같은 비중·같은 청산을 쓰므로,
    남는 차이는 '어느 가격에 걸었는가' 뿐이다.
    """
    px = rng.uniform(low_bound, peak, size=n)
    return sorted(px.tolist(), reverse=True)
