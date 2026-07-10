# scripts/discovery/multiframe_chart_cnn/forward_path.py
"""진입 시각으로부터 3거래일 전방 1분봉 경로를 조립한다(날짜 경계 통과).

계약: day_bars 의 각 값은 한 종목-일의 정규장 1분봉(datetime 오름차순).
진입 체결 = 결정 시각 직후 1분봉의 시가. 그 봉이 없으면 다음 거래일 첫 봉.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_forward_path(day_bars: dict, entry_day: str, entry_dt: pd.Timestamp,
                       horizon_days: int = 3):
    days = sorted(day_bars.keys())
    if entry_day not in day_bars:
        return None
    start_i = days.index(entry_day)
    window_days = days[start_i:start_i + horizon_days]

    # 창 전체 1분봉을 시간순으로 이어붙인다.
    frames = [day_bars[d].sort_values("datetime", kind="mergesort") for d in window_days]
    cat = pd.concat(frames, ignore_index=True)
    dts = pd.to_datetime(cat["datetime"]).to_numpy()

    # 체결 봉 = entry_dt 보다 datetime 이 큰 첫 봉.
    after = np.where(dts > np.datetime64(entry_dt))[0]
    if after.size == 0:
        return None
    fill_i = int(after[0])

    o = cat["open"].to_numpy(dtype=float)
    h = cat["high"].to_numpy(dtype=float)
    l = cat["low"].to_numpy(dtype=float)
    c = cat["close"].to_numpy(dtype=float)

    entry_open = float(o[fill_i])
    fwd_open = o[fill_i + 1:]
    fwd_high = h[fill_i + 1:]
    fwd_low = l[fill_i + 1:]
    fwd_close = c[fill_i + 1:]
    return entry_open, fwd_high, fwd_low, fwd_open, fwd_close
