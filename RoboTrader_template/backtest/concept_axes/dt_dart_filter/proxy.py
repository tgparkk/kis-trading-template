"""시총 대리 p_L — 스펙 §3-2. 입력은 결과와 무관한 거래대금·종가뿐이다.

🔴 거래량은 로더(`replayer.loader.load_prices`)가 이미 조정한 값이다 — 여기서 조정 계수를 다시 곱하지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import settings as S


def add_proxy_features(px: pd.DataFrame, bars: int = S.TV_AVG_BARS) -> pd.DataFrame:
    out = px[["stock_code", "date", "close", "volume"]].copy()
    close = out["close"].astype(float)
    tv = close * out["volume"].astype(float)
    out["tv20"] = tv.groupby(out["stock_code"]).transform(lambda s: s.rolling(bars, min_periods=bars).mean())
    out["x1"] = np.log(out["tv20"].where(out["tv20"] > 0))
    out["x2"] = np.log(close.where(close > 0))
    return out


def design(x1, x2) -> np.ndarray:
    x1, x2 = np.asarray(x1, float), np.asarray(x2, float)
    return np.column_stack([np.ones(len(x1)), x1, x2])


def predict(beta: np.ndarray, X: np.ndarray) -> np.ndarray:
    z = np.clip(X @ np.asarray(beta, float), -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-z))


def fit_logistic(X: np.ndarray, y: np.ndarray, max_iter: int = 100, tol: float = 1e-10) -> np.ndarray:
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n_bad = int((~np.isfinite(X)).sum()) + int((~np.isfinite(y)).sum())
    if n_bad:
        raise ValueError(f"fit_logistic: 비유한 입력 (개수={n_bad})")
    beta = np.zeros(X.shape[1])
    converged = False
    for _ in range(max_iter):
        p = predict(beta, X)
        w = p * (1.0 - p)
        H = X.T @ (X * w[:, None]) + 1e-9 * np.eye(X.shape[1])
        step = np.linalg.solve(H, X.T @ (y - p))
        beta = beta + step
        if float(np.max(np.abs(step))) < tol:
            converged = True
            break
    if not converged:
        raise RuntimeError(f"fit_logistic: 수렴 실패 (max_iter={max_iter})")
    if not np.isfinite(beta).all():
        raise RuntimeError("fit_logistic: 비유한 계수")
    return beta


def auc(y, s) -> float:
    y = np.asarray(y, bool)
    r = pd.Series(np.asarray(s, float)).rank(method="average").to_numpy()
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((r[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))
