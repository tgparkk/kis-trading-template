"""피처 엣지 측정. Spearman IC·터사일 기대값·커버리지·OOS·부트스트랩."""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def daily_ic(panel: pd.DataFrame, feat: str, label: str) -> Dict[str, float]:
    """일별 횡단면 Spearman IC 평균과 IR."""
    ics = []
    for _, g in panel.groupby("date"):
        sub = g[[feat, label]].dropna()
        if len(sub) >= 5:
            ic = sub[feat].rank().corr(sub[label].rank())
            if pd.notna(ic):
                ics.append(ic)
    if not ics:
        return {"ic_mean": float("nan"), "ic_ir": float("nan"), "n_days": 0}
    arr = np.array(ics)
    ir = arr.mean() / arr.std() if arr.std() > 0 else float("nan")
    return {"ic_mean": float(arr.mean()), "ic_ir": float(ir), "n_days": len(arr)}


def tercile_expectancy(panel: pd.DataFrame, feat: str, label: str) -> Dict[str, float]:
    sub = panel[[feat, label]].dropna()
    if len(sub) < 30:
        return {"top_mean": float("nan"), "bottom_mean": float("nan"), "spread": float("nan")}
    q = sub[feat].quantile([1/3, 2/3])
    bottom = sub[sub[feat] <= q.iloc[0]][label].mean()
    top = sub[sub[feat] >= q.iloc[1]][label].mean()
    return {"top_mean": float(top), "bottom_mean": float(bottom),
            "spread": float(top - bottom)}


def coverage(panel: pd.DataFrame, feat: str) -> float:
    return float(panel[feat].notna().mean())


def oos_sign_consistent(panel: pd.DataFrame, feat: str, label: str, split: str) -> bool:
    d = pd.to_datetime(panel["date"])
    train = panel[d <= split]
    test = panel[d > split]
    ic_tr = daily_ic(train, feat, label)["ic_mean"]
    ic_te = daily_ic(test, feat, label)["ic_mean"]
    if pd.isna(ic_tr) or pd.isna(ic_te):
        return False
    return (ic_tr > 0) == (ic_te > 0)


def bootstrap_ic_p05(panel: pd.DataFrame, feat: str, label: str,
                     n_iter: int = 1000, block: int = 21) -> float:
    """일별 IC 시계열에 블록 부트스트랩 → 평균 IC 분포의 p05."""
    ics = []
    for dt, g in panel.groupby("date"):
        sub = g[[feat, label]].dropna()
        if len(sub) >= 5:
            ic = sub[feat].rank().corr(sub[label].rank())
            if pd.notna(ic):
                ics.append(ic)
    s = pd.Series(ics)
    if len(s) < block:
        return float("nan")
    rng = np.random.RandomState(42)
    means = []
    n_blocks = int(np.ceil(len(s) / block))
    for _ in range(n_iter):
        starts = rng.randint(0, len(s) - block + 1, n_blocks)
        sample = pd.concat([s.iloc[st:st + block] for st in starts])
        means.append(sample.mean())
    return float(np.percentile(means, 5))
