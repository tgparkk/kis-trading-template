import pandas as pd
from collectors.stock_market_writer import fdr_df_to_market_rows


def test_fdr_df_to_market_rows_maps_code_and_market():
    df = pd.DataFrame({"Code": ["005930", "000660"], "Name": ["삼성전자", "SK하이닉스"]})
    rows = fdr_df_to_market_rows("KOSPI", df)
    assert rows == [
        {"stock_code": "005930", "market": "KOSPI"},
        {"stock_code": "000660", "market": "KOSPI"},
    ]


def test_fdr_df_to_market_rows_empty():
    assert fdr_df_to_market_rows("KOSPI", pd.DataFrame()) == []
    assert fdr_df_to_market_rows("KOSPI", None) == []


def test_fdr_df_to_market_rows_zero_pads_short_codes():
    # FDR 이 정수로 준 코드를 6자리로 복원해야 daily_prices 와 조인된다
    df = pd.DataFrame({"Code": [5930], "Name": ["삼성전자"]})
    assert fdr_df_to_market_rows("KOSPI", df) == [{"stock_code": "005930", "market": "KOSPI"}]


def test_fdr_df_to_market_rows_skips_blank_codes():
    df = pd.DataFrame({"Code": ["005930", None, ""], "Name": ["a", "b", "c"]})
    assert fdr_df_to_market_rows("KOSDAQ", df) == [{"stock_code": "005930", "market": "KOSDAQ"}]
