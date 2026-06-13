"""타이밍 측정: 트레이드 요약·baseline 델타·부트스트랩 p05·기간내 OOS."""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def summarize_trades(trades: pd.DataFrame, col: str = "ret_net") -> Dict[str, float]:
    if col not in trades.columns:   # 체결 0건 → 컬럼 없는 빈 프레임 방어
        return {"n": 0, "mean": float("nan"), "hit_rate": float("nan"), "sharpe": float("nan")}
    r = trades[col].dropna()
    if len(r) == 0:
        return {"n": 0, "mean": float("nan"), "hit_rate": float("nan"), "sharpe": float("nan")}
    sharpe = r.mean() / r.std() if r.std() > 0 else float("nan")
    return {"n": int(len(r)), "mean": float(r.mean()),
            "hit_rate": float((r > 0).mean()), "sharpe": float(sharpe)}


def delta_vs_baseline(alt: pd.DataFrame, base: pd.DataFrame, col: str = "ret_net") -> Dict[str, float]:
    a, b = summarize_trades(alt, col), summarize_trades(base, col)
    return {"delta_mean": a["mean"] - b["mean"],
            "delta_hit": a["hit_rate"] - b["hit_rate"],
            "alt_n": a["n"], "base_n": b["n"], "alt_mean": a["mean"], "base_mean": b["mean"]}


def bootstrap_delta_p05(alt: pd.DataFrame, base: pd.DataFrame, col: str = "ret_net",
                        n_iter: int = 1000) -> float:
    """alt 평균 − base 평균 의 부트스트랩 분포 p05 (>0이면 개선 견고)."""
    if col not in alt.columns or col not in base.columns:
        return float("nan")
    a = alt[col].dropna().to_numpy()
    b = base[col].dropna().to_numpy()
    if len(a) < 10 or len(b) < 10:
        return float("nan")
    rng = np.random.RandomState(42)
    deltas = []
    for _ in range(n_iter):
        sa = rng.choice(a, len(a), replace=True)
        sb = rng.choice(b, len(b), replace=True)
        deltas.append(sa.mean() - sb.mean())
    return float(np.percentile(deltas, 5))


def oos_delta_signs(alt: pd.DataFrame, base: pd.DataFrame, split: str, col: str = "ret_net") -> Dict[str, float]:
    """기간내 OOS: split 기준 train/test 각 델타 평균 부호."""
    if "date" not in alt.columns or "date" not in base.columns:
        return {"train_delta": float("nan"), "test_delta": float("nan"), "consistent": False}
    da = pd.to_datetime(alt["date"]); db = pd.to_datetime(base["date"])
    tr = delta_vs_baseline(alt[da < split], base[db < split], col)["delta_mean"]
    te = delta_vs_baseline(alt[da >= split], base[db >= split], col)["delta_mean"]
    return {"train_delta": tr, "test_delta": te,
            "consistent": bool(pd.notna(tr) and pd.notna(te) and (tr > 0) == (te > 0))}
