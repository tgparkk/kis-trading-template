"""spike_precursor 라벨 계산.

라벨 정의:
    is_spike_d: D-day 고가 >= D-1 종가 × (1 + threshold) 이면 True.
    학습 라벨용 — T+0(D-day) 시점에는 알 수 없음.
"""
from __future__ import annotations

import math

import pandas as pd


def is_spike_d(
    d_minus_1_close: float,
    d_high: float,
    threshold: float = 0.05,
) -> bool:
    """D-day 고가가 D-1 종가 대비 threshold 이상 상승했는가.

    Args:
        d_minus_1_close: D-1 종가 (선행 시점).
        d_high:          D-day 고가 (라벨 시점).
        threshold:       상승 임계값 (기본 0.05 = +5%).

    Returns:
        True if d_high >= d_minus_1_close * (1 + threshold).
    """
    return d_high >= d_minus_1_close * (1.0 + threshold)


def label_dataframe(
    daily_df: pd.DataFrame,
    threshold: float = 0.05,
) -> pd.Series:
    """daily_df 각 행에 대해 다음날 고가 +threshold% 도달 여부 binary Series 반환.

    Args:
        daily_df:  pandas DataFrame, columns 최소 [close, high].
                   행 정렬 오름차순 (오래된 날짜 먼저).
        threshold: 상승 임계값 (기본 0.05 = +5%).

    Returns:
        pd.Series (bool, float) — 각 행 i에 대해:
            - i < len-1: 다음날(i+1) high >= 현재(i) close * (1 + threshold) 이면 True, 아니면 False.
            - 마지막 행: NaN (다음날 데이터 없음).

    dtype: object (bool + NaN 혼재).
    """
    close = daily_df["close"]
    high = daily_df["high"]
    n = len(daily_df)

    labels: list = []
    for i in range(n - 1):
        c = float(close.iloc[i])
        h = float(high.iloc[i + 1])
        if math.isnan(c) or math.isnan(h):
            labels.append(float("nan"))
        else:
            labels.append(h >= c * (1.0 + threshold))
    labels.append(float("nan"))  # 마지막 행: 미래 미지

    return pd.Series(labels, index=daily_df.index)
