"""체결·청산 시뮬. 전략과 대조군이 이 함수를 공유한다."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from lab.bands import WEIGHTS


@dataclass
class Trade:
    code: str
    entry_date: str
    avg_cost: float
    exit_date: str
    exit_px: float
    ret_net: float
    filled_n: int
    truncated: bool


def simulate(bars: pd.DataFrame, levels, hold_days: int = 20,
             cost: float = 0.0021, code: str = "",
             max_fill_bars: int | None = None,
             weights=None) -> Trade | None:
    """레벨을 순서대로 체결하고, 마지막 체결일 + hold_days 종가에 청산한다.

    ⚠️ 기산점(마지막 체결일)은 전략·대조군이 동일해야 한다.
       달리 잡으면 3차의 기한 비대칭이 재발한다.

    ⚠️ `max_fill_bars` 는 사전등록의 **유효기간 D** 다. 이걸 주지 않으면
       보유기간용 구간에서까지 체결이 일어나 청산이 창 밖으로 밀리고,
       절단율이 구조적으로 부풀려진다(실측 54%). 유효기간은 진입 창이지
       보유 창이 아니다.

    `weights` 는 5차 대조군 C2(비중 순열)용이다. 생략하면 사전등록된
    10/13/17/25/35 를 쓴다 — 전략 팔은 항상 생략한다.
    """
    w = list(WEIGHTS if weights is None else weights)[: len(levels)]
    fills: list[tuple[float, float]] = []
    last_pos = None
    fill_limit = len(bars) if max_fill_bars is None else min(max_fill_bars, len(bars))
    for pos in range(fill_limit):
        row = bars.iloc[pos]
        for i, lv in enumerate(levels):
            if i < len(fills):
                continue
            if row["open"] < lv:
                fills.append((float(row["open"]), w[i]))
                last_pos = pos
            elif row["low"] <= lv:
                fills.append((float(lv), w[i]))
                last_pos = pos
        if len(fills) == len(levels):
            break
    if not fills:
        return None

    tot_w = sum(x[1] for x in fills)
    avg_cost = sum(px * wi for px, wi in fills) / tot_w

    exit_pos = last_pos + hold_days
    truncated = exit_pos >= len(bars)
    if truncated:
        exit_pos = len(bars) - 1
    exit_row = bars.iloc[exit_pos]
    ret_net = float(exit_row["close"]) / avg_cost - 1.0 - cost

    return Trade(
        code=code,
        entry_date=str(bars.iloc[last_pos]["date"]),
        avg_cost=avg_cost,
        exit_date=str(exit_row["date"]),
        exit_px=float(exit_row["close"]),
        ret_net=ret_net,
        filled_n=len(fills),
        truncated=truncated,
    )
