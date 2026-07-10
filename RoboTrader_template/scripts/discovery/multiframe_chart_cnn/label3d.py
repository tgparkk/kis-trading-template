# scripts/discovery/multiframe_chart_cnn/label3d.py
"""3거래일 triple-barrier 라벨러. 날짜 경계를 넘는 전방 1분봉 경로를 받아
TP/SL 선착을 판정하고, 오버나잇 갭은 다음 봉 시가로 정직하게 실현한다.

기존 intraday_rebound.outcome_from_path 와 다른 점:
  - 갭쓰루를 theta 로 낙관 실현하지 않고, 그 봉의 시가로 실현한다(realized_ret).
  - 결과 라벨이 tp/sl/timeout (3-class) 이다.
"""
from __future__ import annotations

import numpy as np


def label3d(entry_open: float,
            fwd_high: np.ndarray, fwd_low: np.ndarray,
            fwd_open: np.ndarray, fwd_close: np.ndarray,
            tp: float, sl: float) -> tuple[str, float]:
    fwd_high = np.asarray(fwd_high, dtype=float)
    fwd_low = np.asarray(fwd_low, dtype=float)
    fwd_open = np.asarray(fwd_open, dtype=float)
    fwd_close = np.asarray(fwd_close, dtype=float)

    n = min(len(fwd_high), len(fwd_low), len(fwd_open), len(fwd_close))
    tp_target = entry_open * (1.0 + tp)
    sl_target = entry_open * (1.0 - sl)

    for j in range(n):
        o = fwd_open[j]
        # 갭 우선: 시가가 이미 배리어를 넘었으면 시가에 실현.
        if o <= sl_target:
            return "sl", o / entry_open - 1.0
        if o >= tp_target:
            return "tp", o / entry_open - 1.0
        # 봉 내 고저. 양쪽 다 건드리면 SL 우선(보수적).
        if fwd_low[j] <= sl_target:
            return "sl", -sl
        if fwd_high[j] >= tp_target:
            return "tp", tp
    if n == 0:
        return "timeout", 0.0
    return "timeout", fwd_close[n - 1] / entry_open - 1.0
