# tests/collectors/test_minute_writer.py
import pandas as pd
from collectors.minute_writer import df_to_minute_rows


def test_df_to_minute_rows_builds_idx_and_fields():
    df = pd.DataFrame([
        {"date": "20260623", "time": "090100", "open": 100.0, "high": 101.0,
         "low": 99.0, "close": 100.5, "volume": 10.0, "amount": 1000.0},
        {"date": "20260623", "time": "090200", "open": 100.5, "high": 102.0,
         "low": 100.0, "close": 101.5, "volume": 20.0, "amount": 2000.0},
    ])
    rows = df_to_minute_rows("005930", df)
    assert len(rows) == 2
    assert rows[0]["stock_code"] == "005930"
    assert rows[0]["trade_date"] == "20260623"
    assert rows[0]["idx"] == 0
    assert rows[1]["idx"] == 1
    assert rows[0]["time"] == "090100"
    assert rows[1]["close"] == 101.5


def test_df_to_minute_rows_empty():
    assert df_to_minute_rows("005930", pd.DataFrame()) == []
