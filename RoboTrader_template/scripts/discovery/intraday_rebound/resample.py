"""1분봉 → N분봉 리샘플.

버킷 경계는 datetime.floor(f'{n}min'). 빈 버킷은 행을 만들지 않는다 (ffill 금지).
입력은 사전 정렬되어 있지 않아도 된다 — 함수 내부에서 datetime 기준 정렬한다.
라이브 TimeFrameConverter 와 OHLCV 가 일치하는지는
tests/.../test_resample.py::test_matches_live_converter_on_a_full_session 이 감시한다.
"""
from __future__ import annotations

import pandas as pd

_EMPTY_DTYPES = {
    "datetime": "datetime64[ns]",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
    "amount": "float64",
    "bar_count": "int64",
}

OUT_COLUMNS = list(_EMPTY_DTYPES.keys())


def resample_ohlcv(minute_df: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
    if minute_df is None or minute_df.empty:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in _EMPTY_DTYPES.items()})

    df = minute_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime", kind="mergesort")
    bucket = df["datetime"].dt.floor(f"{timeframe_minutes}min")

    out = df.groupby(bucket, sort=True).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        amount=("amount", "sum"),
        bar_count=("close", "size"),
    ).rename_axis("datetime").reset_index()
    return out[OUT_COLUMNS]
