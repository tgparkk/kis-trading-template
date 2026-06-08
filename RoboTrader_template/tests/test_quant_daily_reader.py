import pandas as pd
from datetime import date
from db.quant_daily_reader import QuantDailyReader


class _FakeCur:
    def __init__(self, rows): self._rows = rows; self.queries = []
    def execute(self, q, params=None): self.queries.append((q, params))
    def fetchall(self): return self._rows
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


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


class _DateAwareCur:
    """date 별 행을 가진 daily_prices 시뮬레이션 커서.

    - 정확매칭 쿼리(``date = %s``, 서브쿼리 없음): param 날짜가 있을 때만 행 반환.
    - 'scan_date 이하 최신일' 쿼리(``max(date)`` / ``<=`` 포함): param 이하 최대 날짜의 행 반환.
    이로써 '없는 당일' 조회 시 직전 거래일로 폴백하는지를 행동으로 검증한다.
    """

    def __init__(self, table):
        self._table = table  # {date_str: [rows]}
        self._result = []
        self.queries = []

    def execute(self, q, params=None):
        self.queries.append((q, params))
        ql = " ".join(q.lower().split())
        param_date = params[0] if params else None
        if "max(date)" in ql or "<=" in ql:
            avail = sorted(d for d in self._table if d <= param_date)
            eff = avail[-1] if avail else None
            self._result = self._table.get(eff, []) if eff else []
        else:
            self._result = self._table.get(param_date, [])

    def fetchall(self):
        return self._result

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _DateAwareConn:
    def __init__(self, table):
        self.cur = _DateAwareCur(table)

    def cursor(self):
        return self.cur


def _date_aware_reader(table):
    r = QuantDailyReader()
    import contextlib

    @contextlib.contextmanager
    def _conn():
        yield _DateAwareConn(table)

    r._conn = _conn
    return r


def test_get_universe_snapshot_uses_latest_on_or_before():
    """scan_date(06-08)에 데이터가 없으면 직전 거래일(06-05) 유니버스로 폴백한다.

    EOD 스크리너가 quant 적재(15:35) 전에 돌아도 빈 유니버스가 되지 않도록 하는 방어.
    """
    table = {
        "2026-06-05": [("005930", 4.5e14, 9.0e11), ("000660", 1.0e14, 5.0e11)],
        # 2026-06-08 은 아직 적재되지 않은 상태(키 없음)
    }
    r = _date_aware_reader(table)
    out = r.get_universe_snapshot(date(2026, 6, 8))
    assert len(out) == 2, "06-08 미적재 시 직전 거래일(06-05) 유니버스로 폴백해야 함"
    assert {o["stock_code"] for o in out} == {"005930", "000660"}


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
