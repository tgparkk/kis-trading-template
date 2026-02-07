"""
Data Utilities Module
=====================

Utility functions for OHLCV data manipulation:
- merge_ohlcv_dataframes: Merge two OHLCV DataFrames
- resample_ohlcv: Resample OHLCV data to different timeframe
- dataframe_to_ohlcv_list: Convert DataFrame to list of OHLCV objects
"""

from typing import List
import pandas as pd

from ..utils import now_kst
from .models import OHLCV


def merge_ohlcv_dataframes(
    df1: pd.DataFrame,
    df2: pd.DataFrame
) -> pd.DataFrame:
    """
    Merge two OHLCV DataFrames, removing duplicates.

    Args:
        df1: First DataFrame
        df2: Second DataFrame

    Returns:
        DataFrame: Merged and deduplicated DataFrame
    """
    if df1 is None or df1.empty:
        return df2 if df2 is not None else pd.DataFrame()

    if df2 is None or df2.empty:
        return df1

    # Concatenate
    merged = pd.concat([df1, df2], ignore_index=True)

    # Remove duplicates based on datetime
    if 'datetime' in merged.columns:
        merged = merged.drop_duplicates(subset=['datetime'], keep='last')
        merged = merged.sort_values('datetime')
    elif 'date' in merged.columns and 'time' in merged.columns:
        merged = merged.drop_duplicates(subset=['date', 'time'], keep='last')
        merged = merged.sort_values(['date', 'time'])

    return merged.reset_index(drop=True)


def resample_ohlcv(
    df: pd.DataFrame,
    period: str = '3min'
) -> pd.DataFrame:
    """
    Resample OHLCV data to different timeframe.

    Args:
        df: OHLCV DataFrame with datetime column
        period: Resample period ('1min', '3min', '5min', '15min', '30min', '1h')

    Returns:
        DataFrame: Resampled OHLCV data
    """
    if df is None or df.empty or 'datetime' not in df.columns:
        return df

    df = df.set_index('datetime')

    resampled = df.resample(period).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()

    return resampled.reset_index()


def dataframe_to_ohlcv_list(df: pd.DataFrame) -> List[OHLCV]:
    """
    Convert DataFrame to list of OHLCV objects.

    Args:
        df: DataFrame with standardized columns

    Returns:
        List[OHLCV]: List of OHLCV objects
    """
    if df is None or df.empty:
        return []

    result = []
    for _, row in df.iterrows():
        try:
            dt = row.get('datetime')
            if dt is None and 'date' in df.columns and 'time' in df.columns:
                dt = pd.to_datetime(
                    f"{row['date']} {str(row['time']).zfill(6)}",
                    format='%Y%m%d %H%M%S'
                )

            ohlcv = OHLCV(
                datetime=dt if pd.notna(dt) else now_kst(),
                open=float(row.get('open', 0)),
                high=float(row.get('high', 0)),
                low=float(row.get('low', 0)),
                close=float(row.get('close', 0)),
                volume=int(row.get('volume', 0))
            )
            result.append(ohlcv)
        except Exception:
            continue

    return result
