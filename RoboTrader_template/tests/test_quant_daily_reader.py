import pandas as pd
from datetime import date
from db.quant_daily_reader import QuantDailyReader


class _FakeCur:
    def __init__(self, rows): self._rows = rows; self.queries = []
    def execute(self, q, params=None): self.queries.append((q, params))
    def fetchall(self): return self._rows
    def close(self): pass


class _FakeConn:
    def __init__(self, rows): self.cur = _FakeCur(rows)
    def cursor(self): return self.cur


def _reader(rows):
    r = QuantDailyReader()
    import contextlib
    @contextlib.contextmanager
    def _conn():
        yield _FakeConn(rows)
    r._conn = _conn
    return r


def test_get_universe_snapshot_maps_rows():
    rows = [("005930", 4.5e14, 900000000000), ("000660", 1.0e14, 0)]
    r = _reader(rows)
    out = r.get_universe_snapshot(date(2026, 6, 2))
    assert out[0] == {"stock_code": "005930", "market_cap": 4.5e14, "trading_value": 9.0e11}
    assert out[1]["stock_code"] == "000660"


def test_get_daily_prices_returns_sorted_df():
    rows = [
        ("2026-06-02", 100.0, 110.0, 95.0, 105.0, 1000),
        ("2026-06-01", 90.0, 95.0, 88.0, 92.0, 800),
    ]
    r = _reader(rows)
    df = r.get_daily_prices("005930", end_date="2026-06-02", days=120)
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert df["date"].iloc[0] < df["date"].iloc[1]   # 오름차순 정렬
    assert df["close"].iloc[-1] == 105.0
