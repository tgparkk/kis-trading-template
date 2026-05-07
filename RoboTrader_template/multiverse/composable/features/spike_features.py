"""spike_precursor 피처 계산 — 일봉 데이터만 사용 (PIT 강제).

모든 함수 입력:
    daily_df: pandas DataFrame, columns=[date, open, high, low, close, volume],
              행 정렬 오름차순, 마지막 행 = D-1 (당일 데이터 미포함).

반환:
    float | None — 데이터 부족 시 None. NaN 전파 없음.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd


def _safe_series(daily_df: pd.DataFrame, col: str) -> Optional[pd.Series]:
    """컬럼 존재 여부 확인 후 Series 반환. 없으면 None."""
    if col not in daily_df.columns:
        return None
    return daily_df[col]


def vol_zscore_20(daily_df: pd.DataFrame) -> Optional[float]:
    """D-1 거래량의 직전 20일 z-score.

    최소 21행 필요 (20일 통계 + D-1 거래량).
    volume std=0 이면 0.0 반환.
    데이터 부족 시 None.
    """
    if len(daily_df) < 21:
        return None
    vol = _safe_series(daily_df, "volume")
    if vol is None:
        return None

    window = vol.iloc[-21:-1]  # 직전 20일 (D-21 ~ D-2)
    d_minus_1_vol = float(vol.iloc[-1])

    mean = float(window.mean())
    std = float(window.std(ddof=1))

    if std == 0.0 or math.isnan(std):
        return 0.0

    result = (d_minus_1_vol - mean) / std
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def ma20_dist(daily_df: pd.DataFrame) -> Optional[float]:
    """(D-1 close - MA20) / MA20.

    최소 20행 필요.
    데이터 부족 또는 MA20=0 이면 None.
    """
    if len(daily_df) < 20:
        return None
    close = _safe_series(daily_df, "close")
    if close is None:
        return None

    last_close = float(close.iloc[-1])
    ma20 = float(close.iloc[-20:].mean())

    if ma20 == 0.0 or math.isnan(ma20):
        return None

    result = (last_close - ma20) / ma20
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def atr_ratio(daily_df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """ATR(period) / D-1 close.

    ATR = period일 True Range의 평균.
    True Range = max(high-low, |high-prev_close|, |low-prev_close|).
    최소 period+1 행 필요 (prev_close 1행 + period행).
    데이터 부족 또는 close=0 이면 None.
    """
    min_rows = period + 1
    if len(daily_df) < min_rows:
        return None

    close = _safe_series(daily_df, "close")
    high = _safe_series(daily_df, "high")
    low = _safe_series(daily_df, "low")
    if close is None or high is None or low is None:
        return None

    last_close = float(close.iloc[-1])
    if last_close == 0.0 or math.isnan(last_close):
        return None

    # TR 계산: 마지막 period행 (인덱스 -period ~ -1 포함)
    tr_sum = 0.0
    for i in range(-period, 0):
        h = float(high.iloc[i])
        l = float(low.iloc[i])
        prev_c = float(close.iloc[i - 1])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        if math.isnan(tr):
            return None
        tr_sum += tr

    atr_val = tr_sum / period
    result = atr_val / last_close
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def box_squeeze(daily_df: pd.DataFrame, window: int = 10) -> Optional[float]:
    """최근 window일 (high.max - low.min) / D-1 close.

    최소 window행 필요.
    데이터 부족 또는 close=0 이면 None.
    """
    if len(daily_df) < window:
        return None

    close = _safe_series(daily_df, "close")
    high = _safe_series(daily_df, "high")
    low = _safe_series(daily_df, "low")
    if close is None or high is None or low is None:
        return None

    last_close = float(close.iloc[-1])
    if last_close == 0.0 or math.isnan(last_close):
        return None

    h_max = float(high.iloc[-window:].max())
    l_min = float(low.iloc[-window:].min())

    if math.isnan(h_max) or math.isnan(l_min):
        return None

    result = (h_max - l_min) / last_close
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def vol_trend(
    daily_df: pd.DataFrame, short: int = 5, long: int = 20
) -> Optional[float]:
    """최근 short일 거래량 평균 / 최근 long일 거래량 평균.

    최소 long행 필요.
    long 평균=0 이면 None.
    데이터 부족 시 None.
    """
    if len(daily_df) < long:
        return None
    vol = _safe_series(daily_df, "volume")
    if vol is None:
        return None

    short_mean = float(vol.iloc[-short:].mean())
    long_mean = float(vol.iloc[-long:].mean())

    if long_mean == 0.0 or math.isnan(long_mean):
        return None

    result = short_mean / long_mean
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def compute_all_features(daily_df: pd.DataFrame) -> dict[str, Optional[float]]:
    """5개 피처를 dict로 반환. 데이터 부족 항목은 None.

    Returns:
        {
            "vol_zscore_20": float | None,
            "ma20_dist":     float | None,
            "atr_ratio":     float | None,
            "box_squeeze":   float | None,
            "vol_trend":     float | None,
        }
    """
    return {
        "vol_zscore_20": vol_zscore_20(daily_df),
        "ma20_dist": ma20_dist(daily_df),
        "atr_ratio": atr_ratio(daily_df),
        "box_squeeze": box_squeeze(daily_df),
        "vol_trend": vol_trend(daily_df),
    }
