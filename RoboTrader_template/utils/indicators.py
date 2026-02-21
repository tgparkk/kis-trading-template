"""
공용 기술적 지표 계산 유틸리티
"""

from typing import Optional

import pandas as pd


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI (Relative Strength Index) 계산

    Args:
        series: 종가 시리즈
        period: RSI 기간 (기본 14)

    Returns:
        RSI 시리즈 (0~100)
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    # avg_loss가 0이면 RSI=100, avg_gain이 0이면 RSI=0
    rsi = pd.Series(index=series.index, dtype=float)
    valid = avg_gain.notna() & avg_loss.notna()
    zero_loss = valid & (avg_loss.abs() < 1e-10)
    zero_gain = valid & (avg_gain.abs() < 1e-10)
    normal = valid & ~zero_loss
    rs = avg_gain[normal] / avg_loss[normal]
    rsi[normal] = 100 - (100 / (1 + rs))
    rsi[zero_loss] = 100.0
    rsi[zero_gain & ~zero_loss] = 0.0
    return rsi


def calculate_rsi_latest(series: pd.Series, period: int = 14) -> Optional[float]:
    """
    시리즈에서 최신 RSI 값만 반환

    Args:
        series: 종가 시리즈
        period: RSI 기간 (기본 14)

    Returns:
        최신 RSI 값, 계산 불가 시 None
    """
    if len(series) < period + 1:
        return None
    rsi = calculate_rsi(series, period)
    val = float(rsi.iloc[-1])
    return val if not pd.isna(val) else None
