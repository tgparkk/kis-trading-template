# scripts/discovery/multiframe_chart_cnn/forward_path.py
"""진입 시각으로부터 3거래일 전방 1분봉 경로를 조립한다(날짜 경계 통과).

계약: day_bars 의 각 값은 한 종목-일의 정규장 1분봉(datetime 오름차순).
진입 체결 = 결정 시각 직후 1분봉의 시가. 그 봉이 없으면 다음 거래일 첫 봉.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_forward_path(
    day_bars: dict,
    entry_day: str,
    entry_dt: pd.Timestamp,
    horizon_days: int = 3,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """entry_dt 직후 체결 봉을 찾아 전방 1분봉 경로를 조립한다.

    체결(fill) 탐색은 horizon 에 의해 제한되지 않고 entry_day 이후 day_bars
    전체(정렬된 전체 거래일)를 대상으로 수행한다 — entry_day 의 마지막 봉에
    진입해도 다음 거래일 데이터가 있으면 그 첫 봉이 체결로 잡힌다.

    반환되는 fwd_* 배열은 entry_day 를 1일차로 하는 horizon_days 거래일의
    마지막 봉까지만 잘라낸다(가용 거래일이 horizon_days 보다 적으면 마지막
    가용일까지로 clamp). 체결 봉이 이 horizon 경계를 넘어서면 fwd_* 는 빈
    배열이 되지만 entry_open 은 그대로 반환된다(None 아님).

    None 은 entry_day 가 day_bars 에 없거나, entry_dt 이후 entry_day 부터
    끝까지 어디에도 체결 가능한 봉이 없을 때만 반환한다.
    """
    days = sorted(day_bars.keys())
    if entry_day not in day_bars:
        return None
    start_i = days.index(entry_day)
    full_days = days[start_i:]

    # 체결 탐색은 horizon 제한 없이 entry_day 이후 전체 구간에서 수행한다.
    frames = [day_bars[d].sort_values("datetime", kind="mergesort") for d in full_days]
    cat = pd.concat(frames, ignore_index=True)
    dts = pd.to_datetime(cat["datetime"]).to_numpy()

    # 체결 봉 = entry_dt 보다 datetime 이 큰 첫 봉.
    after = np.where(dts > np.datetime64(entry_dt))[0]
    if after.size == 0:
        return None
    fill_i = int(after[0])

    o = cat["open"].to_numpy(dtype=float)
    h = cat["high"].to_numpy(dtype=float)
    lo = cat["low"].to_numpy(dtype=float)
    c = cat["close"].to_numpy(dtype=float)

    entry_open = float(o[fill_i])

    # horizon 경계 = entry_day 를 1일차로 하는 horizon_days 번째 거래일의
    # 마지막 봉(가용 거래일 부족 시 마지막 가용일로 clamp).
    horizon_end_day_idx = min(start_i + horizon_days - 1, len(days) - 1)
    horizon_pos = horizon_end_day_idx - start_i
    boundary_end_i = sum(len(f) for f in frames[:horizon_pos + 1]) - 1

    fwd_open = o[fill_i + 1:boundary_end_i + 1]
    fwd_high = h[fill_i + 1:boundary_end_i + 1]
    fwd_low = lo[fill_i + 1:boundary_end_i + 1]
    fwd_close = c[fill_i + 1:boundary_end_i + 1]
    return entry_open, fwd_high, fwd_low, fwd_open, fwd_close
