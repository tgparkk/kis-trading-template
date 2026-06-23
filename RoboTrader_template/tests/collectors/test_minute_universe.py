# tests/collectors/test_minute_universe.py
import pandas as pd
from collectors.minute_universe import parse_rank_codes, PRICE_BANDS


def test_price_bands_are_six():
    assert len(PRICE_BANDS) == 6


def test_parse_rank_codes_filters_preferred_and_nonsix():
    df = pd.DataFrame([
        {"mksc_shrn_iscd": "005930"},   # ok
        {"mksc_shrn_iscd": "005935"},   # 우선주(끝 5) 제외
        {"mksc_shrn_iscd": "12345"},    # 5자리 제외
        {"mksc_shrn_iscd": "000660"},   # ok
    ])
    assert parse_rank_codes(df) == ["005930", "000660"]


def test_parse_rank_codes_handles_empty():
    assert parse_rank_codes(pd.DataFrame()) == []
