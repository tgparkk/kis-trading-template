# tests/collectors/test_daily_writer.py
from collectors.daily_writer import parse_kis_daily_row


def test_parse_converts_yyyymmdd_to_dash_date_and_casts():
    item = {
        "stck_bsop_date": "20260623", "stck_clpr": "70500", "stck_oprc": "70000",
        "stck_hgpr": "71000", "stck_lwpr": "69000", "acml_vol": "1234567",
        "acml_tr_pbmn": "88000000000",
    }
    row = parse_kis_daily_row(item, market_cap=4.2e14)
    assert row["date"] == "2026-06-23"
    assert row["open"] == 70000.0
    assert row["high"] == 71000.0
    assert row["low"] == 69000.0
    assert row["close"] == 70500.0
    assert row["volume"] == 1234567
    assert row["trading_value"] == 88000000000
    assert row["market_cap"] == 4.2e14


def test_parse_returns_none_on_zero_close():
    item = {"stck_bsop_date": "20260623", "stck_clpr": "0", "stck_oprc": "0",
            "stck_hgpr": "0", "stck_lwpr": "0", "acml_vol": "0", "acml_tr_pbmn": "0"}
    assert parse_kis_daily_row(item, market_cap=None) is None


def test_parse_allows_null_market_cap():
    item = {"stck_bsop_date": "20260623", "stck_clpr": "100", "stck_oprc": "100",
            "stck_hgpr": "100", "stck_lwpr": "100", "acml_vol": "10", "acml_tr_pbmn": "1000"}
    row = parse_kis_daily_row(item, market_cap=None)
    assert row["market_cap"] is None
    assert row["close"] == 100.0
