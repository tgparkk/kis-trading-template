import pandas as pd
from lab.data import drop_bad_ohlc, load_daily
from lab.data import resolve_daily_source_db


def test_resolver_points_at_kis_template():
    assert resolve_daily_source_db() == "kis_template"


def test_drop_bad_ohlc_removes_zero_open_even_when_close_is_valid():
    """close 만 검사하면 살아남는 행을 잡는지 — 18,147행 클래스."""
    df = pd.DataFrame({
        "stock_code": ["A", "B"],
        "date": ["2026-01-02", "2026-01-02"],
        "open": [0.0, 100.0],
        "high": [0.0, 110.0],
        "low": [0.0, 95.0],
        "close": [1000.0, 105.0],
        "volume": [0, 10],
        "trading_value": [0, 1000],
        "market_cap": [1e9, 1e9],
    })
    out = drop_bad_ohlc(df)
    assert list(out["stock_code"]) == ["B"]


def test_loader_sql_never_selects_adj_factor():
    """가격에 adj_factor 를 곱하면 분할일 가짜 절벽이 생겨 거짓 MaxDD 를 만든다.

    SQL 상수만 검사한다 — 독스트링·주석에서 adj_factor 를 '언급'하는 것은
    막지 않는다. 그 용어는 미래의 독자가 검색할 단어다.
    """
    from lab.data import DAILY_SQL
    assert "adj_factor" not in DAILY_SQL
