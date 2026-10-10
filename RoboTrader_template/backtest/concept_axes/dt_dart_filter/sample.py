"""분석 표본 — 스펙 §3-2 · §3-4. 체결 ∧ 대리 소형 ∧ (거른 «뒤») 에피소드 첫 행 · net 수익 = ret − 0.25."""
from __future__ import annotations

from datetime import date
from typing import Dict, Set, Tuple

import numpy as np
import pandas as pd

from . import lots as L
from . import settings as S


def analysis_frame(led: pd.DataFrame, marks: Set[Tuple[str, date]], cal_idx: Dict[date, int],
                   small_only: bool = True) -> pd.DataFrame:
    df = led[led["status"] == "filled"].copy()
    if small_only:
        df = df[df["p_L"].astype(float) < S.PL_CUT]
    df["day"] = [cal_idx[d] for d in df["scan_date"]]
    df = df.sort_values(["stock_code", "day"]).reset_index(drop=True)
    df = df[L.episode_first(df["stock_code"].to_numpy(), df["day"].to_numpy())].reset_index(drop=True)
    df["x"] = [1 if (c, d) in marks else 0 for c, d in zip(df["stock_code"], df["scan_date"])]
    df["y_sl"] = df["ret_sl"].astype(float) - S.COST_PCT
    df["y_tp"] = df["ret_tp"].astype(float) - S.COST_PCT
    df["stock"] = df["stock_code"].astype(str)
    df["block"] = df["day"] // S.BLOCK_TD
    q = pd.qcut(df["p_L"].astype(float).rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    df["quint"] = np.asarray(q, dtype=int)
    return df
