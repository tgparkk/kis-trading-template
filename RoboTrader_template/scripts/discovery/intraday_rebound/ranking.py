"""특징 랭킹. 변동성 프록시를 죽이는 세 겹 방어:
1) 층화 AUC (ATR 5분위 안에서 비교)
2) 방향성 AUC = AUC(hit_up) - AUC(hit_down)
3) 날짜 블록 부트스트랩 (유효 표본은 봉이 아니라 날짜)
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def stratified_auc(score: np.ndarray, label: np.ndarray, strata: np.ndarray) -> float:
    score = np.asarray(score, dtype=float)
    label = np.asarray(label, dtype=float)
    strata = np.asarray(strata)

    ok = np.isfinite(score) & np.isfinite(label)
    score, label, strata = score[ok], label[ok], strata[ok]
    if len(score) == 0:
        return float("nan")

    total_w, acc = 0.0, 0.0
    for s in np.unique(strata):
        m = strata == s
        y = label[m]
        if y.min() == y.max():      # 한 클래스만 있는 층은 건너뛴다
            continue
        w = float(m.sum())
        acc += w * roc_auc_score(y, score[m])
        total_w += w

    return acc / total_w if total_w > 0 else float("nan")


def directional_auc(score, hit_up, hit_down, strata) -> float:
    up = stratified_auc(score, hit_up, strata)
    dn = stratified_auc(score, hit_down, strata)
    if np.isnan(up) or np.isnan(dn):
        return float("nan")
    return up - dn


def date_block_bootstrap_ci(fn: Callable[[np.ndarray], float],
                            dates: np.ndarray,
                            n_boot: int = 1000,
                            seed: int = 42,
                            alpha: float = 0.05) -> tuple[float, float]:
    """날짜를 복원추출해 fn 의 신뢰구간을 낸다. fn 은 행 인덱스 배열을 받는다."""
    dates = np.asarray(dates)
    uniq = np.unique(dates)
    idx_by_date = {d: np.flatnonzero(dates == d) for d in uniq}

    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n_boot):
        picked = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_date[d] for d in picked])
        v = fn(idx)
        if np.isfinite(v):
            stats.append(v)

    if not stats:
        return (float("nan"), float("nan"))
    lo = float(np.quantile(stats, alpha / 2))
    hi = float(np.quantile(stats, 1 - alpha / 2))
    return lo, hi


def rank_features(df: pd.DataFrame,
                  feature_names: list[str],
                  strata_col: str = "atr_quintile",
                  date_col: str = "trade_date",
                  n_boot: int = 500,
                  seed: int = 42) -> pd.DataFrame:
    dates = df[date_col].to_numpy()
    strata = (df[strata_col].astype(str) + "|" + df["is_full_lookback"].astype(str)).to_numpy()
    up = df["hit_up"].to_numpy(dtype=float)
    dn = df["hit_down"].to_numpy(dtype=float)

    rows = []
    for feat in feature_names:
        score = df[feat].to_numpy(dtype=float)

        auc_up = stratified_auc(score, up, strata)
        auc_dn = stratified_auc(score, dn, strata)
        d = auc_up - auc_dn if np.isfinite(auc_up) and np.isfinite(auc_dn) else np.nan

        def _fn(idx, _s=score):
            return directional_auc(_s[idx], up[idx], dn[idx], strata[idx])

        lo, hi = date_block_bootstrap_ci(_fn, dates, n_boot=n_boot, seed=seed)

        rows.append({
            "feature": feat, "auc_up": auc_up, "auc_down": auc_dn,
            "directional_auc": d, "ci_lo": lo, "ci_hi": hi,
            "n_dates": len(np.unique(dates)),
        })

    out = pd.DataFrame(rows)
    return out.reindex(out["directional_auc"].abs().sort_values(ascending=False).index).reset_index(drop=True)
