"""1분봉 → N분봉 리샘플.

버킷 경계는 datetime.floor(f'{n}min'). 빈 버킷은 행을 만들지 않는다 (ffill 금지).
라이브 TimeFrameConverter 와 OHLCV 가 일치하는지는
tests/.../test_resample.py::test_matches_live_converter_on_a_full_session 이 감시한다.
"""
from __future__ import annotations

import pandas as pd

OUT_COLUMNS = ["datetime", "open", "high", "low", "close", "volume", "amount", "bar_count"]


def resample_ohlcv(minute_df: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
    if minute_df is None or minute_df.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)

    df = minute_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    bucket = df["datetime"].dt.floor(f"{timeframe_minutes}min")

    out = df.groupby(bucket, sort=True).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        amount=("amount", "sum"),
        bar_count=("close", "size"),
    ).reset_index()
    out.columns = OUT_COLUMNS
    return out
