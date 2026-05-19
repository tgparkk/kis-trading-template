"""
분봉 기술적 지표 계산 유틸리티 (pure function 기반)

입력 DataFrame 표준 가정:
  - 컬럼: datetime, open, high, low, close, volume, amount(선택)
  - 정렬: datetime 오름차순
  - 결손 분봉 가능 (VI/거래정지) — NaN으로 처리
"""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. VWAP
# ---------------------------------------------------------------------------

def vwap(df: pd.DataFrame) -> pd.Series:
    """당일 누적 VWAP (Volume Weighted Average Price). 날짜 변경 시 자동 리셋."""
    if df.empty:
        return pd.Series(dtype=float, index=df.index)

    df = df.copy()

    # typical_price: (H+L+C)/3 고정
    # minute_candles.amount는 당일 누적 거래대금이므로 분봉 단위 tp 계산에 사용 불가
    tp = (df["high"] + df["low"] + df["close"]) / 3

    # 날짜 그룹별 누적 — datetime 컬럼에서 날짜 추출
    if pd.api.types.is_datetime64_any_dtype(df["datetime"]):
        date_key = df["datetime"].dt.date
    else:
        date_key = pd.to_datetime(df["datetime"]).dt.date

    cum_tpv = (tp * df["volume"]).groupby(date_key).cumsum()
    cum_vol = df["volume"].groupby(date_key).cumsum()

    result = cum_tpv / cum_vol.replace(0, np.nan)
    result.index = df.index
    return result


# ---------------------------------------------------------------------------
# 2. ORB (Opening Range Breakout) levels
# ---------------------------------------------------------------------------

def orb_levels(df: pd.DataFrame, window_minutes: int = 30) -> dict[str, float]:
    """첫 window_minutes 분봉의 고가/저가/범위/거래량 반환."""
    nan_result = {
        "or_high": float("nan"),
        "or_low": float("nan"),
        "or_range": float("nan"),
        "or_volume": float("nan"),
    }
    if df.empty:
        return nan_result

    # 당일 첫 분봉 기준 시각
    dt_col = pd.to_datetime(df["datetime"])
    start_time = dt_col.iloc[0]
    cutoff = start_time + pd.Timedelta(minutes=window_minutes)

    opening = df[dt_col < cutoff]
    if opening.empty or len(opening) < 1:
        return nan_result

    or_high = float(opening["high"].max())
    or_low = float(opening["low"].min())
    or_volume = float(opening["volume"].sum())

    return {
        "or_high": or_high,
        "or_low": or_low,
        "or_range": or_high - or_low,
        "or_volume": or_volume,
    }


# ---------------------------------------------------------------------------
# 3. RSI (Wilder)
# ---------------------------------------------------------------------------

def rsi_minute(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder RSI (close 기준). 초기 period개는 NaN."""
    if df.empty:
        return pd.Series(dtype=float, index=df.index)

    series = df["close"]
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder smoothing = ewm alpha=1/period, min_periods=period
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

    rsi = pd.Series(index=series.index, dtype=float)
    valid = avg_gain.notna() & avg_loss.notna()
    zero_loss = valid & (avg_loss.abs() < 1e-10)
    zero_gain = valid & ~zero_loss & (avg_gain.abs() < 1e-10)
    normal = valid & ~zero_loss & ~zero_gain

    rs = avg_gain[normal] / avg_loss[normal]
    rsi[normal] = 100.0 - (100.0 / (1.0 + rs))
    rsi[zero_loss] = 100.0
    rsi[zero_gain] = 0.0
    return rsi


# ---------------------------------------------------------------------------
# 4. EMA
# ---------------------------------------------------------------------------

def ema_minute(df: pd.DataFrame, period: int) -> pd.Series:
    """close 기준 EMA. alpha=2/(period+1)."""
    if df.empty:
        return pd.Series(dtype=float, index=df.index)
    return df["close"].ewm(span=period, adjust=False).mean()


# ---------------------------------------------------------------------------
# 5. Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger_minute(
    df: pd.DataFrame, period: int = 20, std: float = 2.0
) -> dict[str, pd.Series]:
    """Bollinger Bands. 키: middle, upper, lower, bandwidth, percent_b."""
    empty = {
        k: pd.Series(dtype=float, index=df.index)
        for k in ("middle", "upper", "lower", "bandwidth", "percent_b")
    }
    if df.empty:
        return empty

    close = df["close"]
    middle = close.rolling(window=period, min_periods=period).mean()
    rolling_std = close.rolling(window=period, min_periods=period).std(ddof=1)

    upper = middle + std * rolling_std
    lower = middle - std * rolling_std
    band_range = upper - lower

    bandwidth = band_range / middle.replace(0, np.nan)
    percent_b = (close - lower) / band_range.replace(0, np.nan)

    return {
        "middle": middle,
        "upper": upper,
        "lower": lower,
        "bandwidth": bandwidth,
        "percent_b": percent_b,
    }


# ---------------------------------------------------------------------------
# 6. Volume Z-Score
# ---------------------------------------------------------------------------

def volume_zscore(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Rolling z-score of volume (window 기간 mean/std 기준)."""
    if df.empty:
        return pd.Series(dtype=float, index=df.index)

    vol = df["volume"].astype(float)
    roll_mean = vol.rolling(window=window, min_periods=window).mean()
    roll_std = vol.rolling(window=window, min_periods=window).std(ddof=1)
    return (vol - roll_mean) / roll_std.replace(0, np.nan)


# ---------------------------------------------------------------------------
# 7. Volume Surge
# ---------------------------------------------------------------------------

def volume_surge(
    df: pd.DataFrame, multiplier: float = 3.0, window: int = 20
) -> pd.Series:
    """현재 분봉 volume이 window 평균의 multiplier 배 이상이면 True."""
    if df.empty:
        return pd.Series(dtype=bool, index=df.index)

    vol = df["volume"].astype(float)
    roll_mean = vol.rolling(window=window, min_periods=window).mean()
    return (vol >= roll_mean * multiplier).fillna(False)


# ---------------------------------------------------------------------------
# 8. Flag Pattern
# ---------------------------------------------------------------------------

def flag_pattern(
    df: pd.DataFrame,
    pole_min_pct: float = 0.05,
    consolidation_bars: int = 5,
    consolidation_max_pct: float = 0.02,
) -> pd.Series:
    """
    강세 깃발 패턴 탐지.

    폴: 슬라이딩 윈도우(5~15분봉)에서 pole_min_pct 이상 상승한 구간.
    통합: 폴 이후 consolidation_bars개 분봉이 consolidation_max_pct 이내 횡보.
    신호 발생 시점(통합 구간 마지막 봉)에 True.
    """
    result = pd.Series(False, index=df.index, dtype=bool)
    if len(df) < 6:
        return result

    close = df["close"].values
    n = len(close)

    pole_lengths = range(5, 16)  # 폴 길이 5~15봉

    for i in range(n):
        # 통합 구간 끝 = i, 통합 구간 시작 = i - consolidation_bars + 1
        consol_end = i
        consol_start = i - consolidation_bars + 1
        if consol_start < 1:
            continue

        # 통합 구간 검증
        consol_prices = close[consol_start : consol_end + 1]
        if len(consol_prices) < consolidation_bars:
            continue
        consol_high = np.nanmax(consol_prices)
        consol_low = np.nanmin(consol_prices)
        consol_ref = consol_prices[0]
        if consol_ref <= 0:
            continue
        if (consol_high - consol_low) / consol_ref > consolidation_max_pct:
            continue

        # 폴 구간 검증 (통합 구간 직전)
        pole_end = consol_start - 1  # 폴의 끝 인덱스
        found_pole = False
        for pole_len in pole_lengths:
            pole_start = pole_end - pole_len + 1
            if pole_start < 0:
                continue
            pole_prices = close[pole_start : pole_end + 1]
            if len(pole_prices) < 2:
                continue
            p_start_price = pole_prices[0]
            p_end_price = pole_prices[-1]
            if p_start_price <= 0:
                continue
            pct = (p_end_price - p_start_price) / p_start_price
            if pct >= pole_min_pct:
                found_pole = True
                break

        if found_pole:
            result.iloc[i] = True

    return result


# ---------------------------------------------------------------------------
# 9. Pivot S/R Levels (Floor Trader's Pivot)
# ---------------------------------------------------------------------------

def pivot_sr_levels(
    prev_day_ohlc: Union[dict[str, float], pd.Series]
) -> dict[str, float]:
    """전일 OHLC 기반 Floor Trader's Pivot 지지/저항 레벨 계산."""
    h = float(prev_day_ohlc["high"])
    l = float(prev_day_ohlc["low"])
    c = float(prev_day_ohlc["close"])

    pivot = (h + l + c) / 3.0

    r1 = 2 * pivot - l
    s1 = 2 * pivot - h
    r2 = pivot + (h - l)
    s2 = pivot - (h - l)
    r3 = h + 2 * (pivot - l)
    s3 = l - 2 * (h - pivot)

    return {
        "pivot": pivot,
        "r1": r1,
        "r2": r2,
        "r3": r3,
        "s1": s1,
        "s2": s2,
        "s3": s3,
    }


# ---------------------------------------------------------------------------
# 10. Red-to-Green
# ---------------------------------------------------------------------------

def red_to_green(df: pd.DataFrame, prev_close: float) -> pd.Series:
    """분봉 close가 prev_close를 처음으로 위로 교차하는 시점에 True (한 번만)."""
    result = pd.Series(False, index=df.index, dtype=bool)
    if df.empty:
        return result

    close = df["close"].values
    crossed = False
    for i in range(len(close)):
        if not crossed and close[i] > prev_close:
            result.iloc[i] = True
            crossed = True
            break  # 첫 교차만

    return result


# ---------------------------------------------------------------------------
# 11. Cumulative Volume Ratio (당일 누적 / 전일 일봉)
# ---------------------------------------------------------------------------

def cumulative_volume_ratio(
    df: pd.DataFrame, prev_day_volume: Optional[float]
) -> pd.Series:
    """당일 누적 거래량 / 전일 일봉 거래량 비율 Series.

    prev_day_volume이 None/0이면 전 구간 NaN Series 반환 (필터 미적용 의도).
    NaN 거래량은 0으로 취급.
    """
    if df.empty:
        return pd.Series(dtype=float, index=df.index)
    if prev_day_volume is None or prev_day_volume <= 0:
        return pd.Series(np.nan, index=df.index, dtype=float)

    vol = df["volume"].astype(float).fillna(0.0)
    cum = vol.cumsum()
    return cum / float(prev_day_volume)
