# scripts/discovery/multiframe_chart_cnn/scalars.py
"""변동성 보조 스칼라. 이미지 정규화가 지운 절대 변동폭을 모델에 복원해 준다."""
from __future__ import annotations

import numpy as np
import pandas as pd


def vol_scalars(bars3: pd.DataFrame, n_bars: int = 60) -> np.ndarray:
    if bars3 is None or len(bars3) == 0:
        return np.zeros(2, dtype=np.float32)
    b = bars3.tail(n_bars)
    high = b["high"].to_numpy(dtype=float)
    low = b["low"].to_numpy(dtype=float)
    close = b["close"].to_numpy(dtype=float)
    last = float(close[-1])
    if last == 0:
        return np.zeros(2, dtype=np.float32)
    range_pct = (float(np.max(high)) - float(np.min(low))) / last
    atr_pct = float(np.mean(high - low)) / last
    return np.array([range_pct, atr_pct], dtype=np.float32)
