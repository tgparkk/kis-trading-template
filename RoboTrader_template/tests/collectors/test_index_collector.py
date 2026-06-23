from collectors.index_collector import INDEX_TICKERS


def test_index_tickers_map():
    assert INDEX_TICKERS == {"KOSPI": "KS11", "KOSDAQ": "KQ11"}
