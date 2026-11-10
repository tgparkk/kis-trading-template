"""합성 분봉 도우미 — 실제 데이터 없음."""
from __future__ import annotations

from typing import Optional

import numpy as np

from backtest.concept_axes.minute_rules import engine as E


def flat(px: float = 10000.0, vol: float = 100.0) -> np.ndarray:
    """09:00~15:19 전부 o=h=l=c=px · 거래량 vol · amount 누적 · 15:30 행 NaN."""
    b = np.full((E.N_SLOTS, E.N_FIELDS), np.nan)
    b[: E.N_CONT, :4] = px
    b[: E.N_CONT, E.F_VOL] = vol
    b[: E.N_CONT, E.F_AMT] = np.cumsum(np.full(E.N_CONT, vol * px))
    return b


def put(b: np.ndarray, i: int, o: float, h: float, lo: float, c: float, v: Optional[float] = None) -> np.ndarray:
    b[i, :4] = (o, h, lo, c)
    if v is not None:
        b[i, E.F_VOL] = v
    return b


def path(b: np.ndarray, start: int, closes) -> np.ndarray:
    """start 분부터 종가 경로 — 각 분 o=직전 종가 · h/l = o·c 의 최대/최소."""
    prev = float(b[start - 1, E.F_CLOSE]) if start > 0 else float(closes[0])
    for k, c in enumerate(closes):
        put(b, start + k, prev, max(prev, c), min(prev, c), c)
        prev = c
    for i in range(start + len(closes), E.N_CONT):
        put(b, i, prev, prev, prev, prev)
    return b
