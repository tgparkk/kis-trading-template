from scripts.kis_db.seed_from_legacy import build_daily_insert_rows, DAILY_COLUMNS


def test_daily_columns_order_matches_schema():
    assert DAILY_COLUMNS == [
        "stock_code", "date", "open", "high", "low", "close",
        "volume", "trading_value", "market_cap",
        "returns_1d", "returns_5d", "returns_20d", "volatility_20d", "adj_factor",
    ]


def test_build_daily_insert_rows_passthrough_tuples():
    src = [("005930", "2026-06-22", 70000.0, 71000.0, 69000.0, 70500.0,
            1000, 70_000_000, 4.2e14, 0.01, 0.02, 0.03, 0.15, 1.0)]
    out = build_daily_insert_rows(src)
    assert out == src
    assert len(out[0]) == len(DAILY_COLUMNS)
