"""Universe-wide z-score 정규화 공통 유틸."""
from __future__ import annotations

import math


def z_normalize(values: list[float]) -> list[float]:
    """Universe-wide z-score 정규화. std=0이면 0 반환."""
    finite = [v for v in values if not math.isnan(v)]
    if not finite:
        return [0.0] * len(values)
    mean = sum(finite) / len(finite)
    variance = sum((v - mean) ** 2 for v in finite) / len(finite)
    std = math.sqrt(variance)
    if std == 0:
        return [0.0] * len(values)
    return [(v - mean) / std if not math.isnan(v) else 0.0 for v in values]
