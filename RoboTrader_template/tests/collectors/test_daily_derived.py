# tests/collectors/test_daily_derived.py
from collectors.daily_derived import update_returns_volatility
from collectors.daily_derived import SQL_UPDATE_RETURNS


def test_uses_canonical_returns_sql():
    # 동일 SQL을 재사용(중복 정의 금지)
    import collectors.daily_derived as m
    assert m.SQL_UPDATE_RETURNS is SQL_UPDATE_RETURNS
    # 연구 스크립트의 역방향 import도 동일 객체여야 한다 (승격 후 정합성)
    import scripts.etl_backfill_daily_prices as etl
    assert etl.SQL_UPDATE_RETURNS is m.SQL_UPDATE_RETURNS


class _Cur:
    def __init__(self): self.sql = None
    def execute(self, sql): self.sql = sql
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Conn:
    def __init__(self): self.cur = _Cur(); self.committed = False
    def cursor(self): return self.cur
    def commit(self): self.committed = True


def test_update_runs_sql_and_commits():
    c = _Conn()
    update_returns_volatility(c)
    assert "UPDATE daily_prices" in c.cur.sql
    assert c.committed is True
