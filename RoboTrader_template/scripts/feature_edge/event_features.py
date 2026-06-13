"""기업이벤트 플래그 (corp_events). 증자/분할/관리종목 ±window 윈도우."""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


def compute_event_flags(daily: pd.DataFrame, events: List[Tuple[pd.Timestamp, str]],
                        window: int = 3) -> pd.DataFrame:
    dates = pd.to_datetime(daily["date"]).reset_index(drop=True)
    flag = np.zeros(len(dates), dtype=int)
    ev_dates = [pd.Timestamp(e[0]) for e in events]
    for i, d in enumerate(dates):
        for ed in ev_dates:
            if abs((d - ed).days) <= window:
                flag[i] = 1
                break
    out = pd.DataFrame({"date": dates.values, "event_within_n": flag})
    return out
