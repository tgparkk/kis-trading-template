"""
Data Standardizer Module
========================

Provides DataFrame standardization utilities for KIS API responses.

Converts raw API column names to standard format:
- stck_bsop_date -> date
- stck_cntg_hour -> time
- stck_oprc -> open
- stck_hgpr -> high
- stck_lwpr -> low
- stck_prpr -> close
- cntg_vol -> volume
"""

import pandas as pd
from typing import Optional


class DataStandardizer:
    """
    DataFrame standardization for KIS API responses.

    Handles both minute and daily data with appropriate column mappings.
    """

    # Column mapping for minute data
    MINUTE_COLUMN_MAPPING = {
        'stck_bsop_date': 'date',
        'stck_cntg_hour': 'time',
        'stck_oprc': 'open',
        'stck_hgpr': 'high',
        'stck_lwpr': 'low',
        'stck_prpr': 'close',
        'cntg_vol': 'volume',
        'acml_tr_pbmn': 'amount'
    }

    # Column mapping for daily data
    DAILY_COLUMN_MAPPING = {
        'stck_bsop_date': 'date',
        'stck_oprc': 'open',
        'stck_hgpr': 'high',
        'stck_lwpr': 'low',
        'stck_clpr': 'close',
        'acml_vol': 'volume',
        'acml_tr_pbmn': 'amount'
    }

    # Numeric columns to convert
    NUMERIC_COLUMNS = ['open', 'high', 'low', 'close', 'volume', 'amount']

    @classmethod
    def standardize_minute_data(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize DataFrame column names for minute data.

        Args:
            df: Raw DataFrame from KIS API

        Returns:
            DataFrame: Standardized DataFrame with datetime column
        """
        if df is None or df.empty:
            return df

        # Rename columns
        df = cls._rename_columns(df, cls.MINUTE_COLUMN_MAPPING)

        # Create datetime column if date and time exist
        df = cls._create_datetime_column(df)

        # Convert numeric columns
        df = cls._convert_numeric_columns(df)

        # Sort by datetime or date+time
        df = cls._sort_dataframe(df)

        return df.reset_index(drop=True)

    @classmethod
    def standardize_daily_data(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize DataFrame column names for daily data.

        Args:
            df: Raw DataFrame from KIS API

        Returns:
            DataFrame: Standardized DataFrame
        """
        if df is None or df.empty:
            return df

        # Rename columns
        df = cls._rename_columns(df, cls.DAILY_COLUMN_MAPPING)

        # Convert numeric columns
        df = cls._convert_numeric_columns(df)

        # Sort by date (ascending)
        if 'date' in df.columns:
            df = df.sort_values('date')

        return df.reset_index(drop=True)

    @classmethod
    def _rename_columns(cls, df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
        """Rename columns based on mapping."""
        rename_cols = {k: v for k, v in mapping.items() if k in df.columns}
        if rename_cols:
            df = df.rename(columns=rename_cols)
        return df

    @classmethod
    def _create_datetime_column(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Create datetime column from date and time columns."""
        if 'date' in df.columns and 'time' in df.columns:
            try:
                df['datetime'] = pd.to_datetime(
                    df['date'].astype(str) + ' ' + df['time'].astype(str).str.zfill(6),
                    format='%Y%m%d %H%M%S',
                    errors='coerce'
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"datetime 컬럼 생성 실패: {e}")
        return df

    @classmethod
    def _convert_numeric_columns(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Convert numeric columns to proper types."""
        for col in cls.NUMERIC_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df

    @classmethod
    def _sort_dataframe(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Sort DataFrame by datetime or date+time."""
        if 'datetime' in df.columns:
            df = df.sort_values('datetime')
        elif 'date' in df.columns and 'time' in df.columns:
            df = df.sort_values(['date', 'time'])
        return df
