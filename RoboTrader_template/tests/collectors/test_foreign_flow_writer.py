import pandas as pd
from datetime import date

from collectors.foreign_flow_writer import naver_df_to_rows, upsert_foreign_rows


def test_naver_df_to_rows_maps_columns():
    df = pd.DataFrame({
        "date": [date(2026, 6, 12), date(2026, 6, 11)],
        "foreign_net_vol": [12345, -6789],
    })
    rows = naver_df_to_rows("005930", df)
    assert rows == [
        {"stock_code": "005930", "date": date(2026, 6, 12), "foreign_net_vol": 12345, "source": "naver"},
        {"stock_code": "005930", "date": date(2026, 6, 11), "foreign_net_vol": -6789, "source": "naver"},
    ]


def test_naver_df_to_rows_nan_becomes_none():
    df = pd.DataFrame({
        "date": [date(2026, 6, 12)],
        "foreign_net_vol": [float("nan")],
    })
    rows = naver_df_to_rows("000660", df)
    assert rows == [
        {"stock_code": "000660", "date": date(2026, 6, 12), "foreign_net_vol": None, "source": "naver"},
    ]


def test_naver_df_to_rows_empty():
    assert naver_df_to_rows("005930", pd.DataFrame(columns=["date", "foreign_net_vol"])) == []
    assert naver_df_to_rows("005930", None) == []


class _MockCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _MockConn:
    def __init__(self):
        self.cur = _MockCursor()
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def test_upsert_foreign_rows_executes_and_commits():
    conn = _MockConn()
    rows = [
        {"stock_code": "005930", "date": date(2026, 6, 12), "foreign_net_vol": 100, "source": "naver"},
        {"stock_code": "005930", "date": date(2026, 6, 11), "foreign_net_vol": -50, "source": "naver"},
    ]
    n = upsert_foreign_rows(conn, rows)
    assert n == 2
    assert conn.committed is True
    assert len(conn.cur.executed) == 2
    # ON CONFLICT UPSERT 사용 확인
    sql0 = conn.cur.executed[0][0].lower()
    assert "on conflict (stock_code, date) do update" in sql0


def test_upsert_foreign_rows_empty():
    conn = _MockConn()
    assert upsert_foreign_rows(conn, []) == 0
    assert conn.committed is True
