"""Weinstein Stage Analysis — 일봉→주봉 집계 헬퍼.

주봉 집계 규칙:
- 주 마감: ISO 주(월~일) 기준 W-FRI 그루핑 → 그 주의 마지막 실거래일 라벨
- open   = 그 주 첫 거래일 open
- high   = max(high)
- low    = min(low)
- close  = 그 주 마지막 거래일 close
- volume = sum(volume)
- n_days = 그 주 거래일 수
- n_days < min_days_per_week 인 주는 제외 (공휴일 다발 주 배제)
"""
from __future__ import annotations

import pandas as pd


def resample_daily_to_weekly(
    daily_df: pd.DataFrame,
    min_days_per_week: int = 3,
) -> pd.DataFrame:
    """일봉 DataFrame을 주봉으로 집계한다.

    Args:
        daily_df: columns = [datetime, open, high, low, close, volume].
                  datetime 열은 pd.Timestamp 또는 date-like.
        min_days_per_week: 거래일 수가 이 값 미만인 주는 dropna (기본 3).
                           추후 데이터 누적 후 재검토.

    Returns:
        weekly DataFrame. columns = [datetime, open, high, low, close, volume, n_days].
        datetime = 그 주의 마지막 실거래일.
        index는 0-based RangeIndex (reset).
    """
    if daily_df is None or len(daily_df) == 0:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume", "n_days"])

    df = daily_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    # W-FRI 그루핑: 월~금 한 주를 금요일 날짜로 라벨링
    df = df.set_index("datetime")
    grp = df.groupby(pd.Grouper(freq="W-FRI"))

    agg = grp.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        n_days=("close", "count"),
    )

    # 거래일 < min_days_per_week 인 주 제거 (빈 주·공휴일 다발 주 포함)
    agg = agg[agg["n_days"] >= min_days_per_week]
    agg = agg.dropna(subset=["open", "high", "low", "close"])

    # datetime 열 = 실제 마지막 거래일 (W-FRI label이 아닌 실거래일)
    last_trade_day = grp["close"].apply(lambda s: s.index[-1] if len(s) >= min_days_per_week else pd.NaT)
    last_trade_day = last_trade_day[agg.index]  # 동일 필터 적용

    agg["datetime"] = last_trade_day.values
    agg = agg.reset_index(drop=True)

    # 컬럼 순서 정렬
    return agg[["datetime", "open", "high", "low", "close", "volume", "n_days"]].copy()
