# scripts/discovery/multiframe_chart_cnn/rasterize.py
"""결정적 멀티프레임 래스터화. 3/5/15분봉 각 60봉을 64x64 로 그려 6채널 텐서.

정규화가 사활: 각 채널 세로축은 그 60봉 구간 자체의 값으로 0~1. 절대 가격·
절대 거래량·종목 정체성이 이미지에서 완전히 소거된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.discovery.intraday_rebound.resample import resample_ohlcv

BODY_UP = 1.0
BODY_DN = 0.6
WICK = 0.3


def _y(value: float, lo: float, hi: float, size: int) -> int:
    if hi <= lo:
        return size // 2
    frac = (value - lo) / (hi - lo)
    frac = min(max(frac, 0.0), 1.0)
    # y=0 을 위(고가)로: 이미지 좌표계 위쪽이 큰 값
    return int(round((1.0 - frac) * (size - 1)))


def render_frame(bars: pd.DataFrame, n_bars: int = 60, size: int = 64) -> np.ndarray:
    img = np.zeros((2, size, size), dtype=np.float32)
    if bars is None or len(bars) == 0:
        return img

    b = bars.tail(n_bars)
    if len(b) > size:
        b = b.iloc[-size:]
    o = b["open"].to_numpy(dtype=float)
    h = b["high"].to_numpy(dtype=float)
    low_arr = b["low"].to_numpy(dtype=float)
    c = b["close"].to_numpy(dtype=float)
    v = b["volume"].to_numpy(dtype=float)
    m = len(b)

    lo, hi = float(np.min(low_arr)), float(np.max(h))
    vmax = float(np.max(v)) if np.max(v) > 0 else 1.0

    # 오른쪽 정렬: 마지막 봉이 가장 오른쪽 칸.
    x_off = size - m if m < size else 0
    for k in range(m):
        x = x_off + k
        if x < 0 or x >= size:
            continue
        # 심지: 고가~저가
        y_hi = _y(h[k], lo, hi, size)
        y_lo = _y(low_arr[k], lo, hi, size)
        img[0, y_hi:y_lo + 1, x] = np.maximum(img[0, y_hi:y_lo + 1, x], WICK)
        # 몸통: open~close
        y_o = _y(o[k], lo, hi, size)
        y_c = _y(c[k], lo, hi, size)
        top, bot = min(y_o, y_c), max(y_o, y_c)
        body_val = BODY_UP if c[k] >= o[k] else BODY_DN
        img[0, top:bot + 1, x] = body_val
        # 거래량: 바닥에서 위로
        vfrac = v[k] / vmax
        vh = min(int(round(vfrac * size)), size)
        if vh > 0:
            img[1, size - vh:size, x] = vfrac
    return img


def render_multiframe(minute_bars: pd.DataFrame, n_bars: int = 60,
                      size: int = 64) -> np.ndarray:
    out = np.zeros((6, size, size), dtype=np.float32)
    for fi, tf in enumerate((3, 5, 15)):
        frame = render_frame(resample_ohlcv(minute_bars, tf), n_bars, size)
        out[2 * fi] = frame[0]
        out[2 * fi + 1] = frame[1]
    return out
