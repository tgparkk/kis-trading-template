import pandas as pd
from collectors.index_writer import fdr_df_to_index_rows


def test_fdr_df_to_index_rows_maps_and_formats_date():
    df = pd.DataFrame(
        {"Open": [2500.0], "High": [2520.0], "Low": [2490.0], "Close": [2510.0], "Volume": [1.0e9]},
        index=pd.to_datetime(["2026-06-23"]),
    )
    rows = fdr_df_to_index_rows("KOSPI", df)
    assert rows == [{
        "index_code": "KOSPI", "date": "2026-06-23",
        "open": 2500.0, "high": 2520.0, "low": 2490.0, "close": 2510.0, "volume": 1.0e9,
    }]


def test_fdr_df_to_index_rows_empty():
    assert fdr_df_to_index_rows("KOSPI", pd.DataFrame()) == []
