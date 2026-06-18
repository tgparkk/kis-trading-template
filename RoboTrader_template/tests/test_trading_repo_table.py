import pytest
from db.repositories.trading import TradingRepository

def test_default_table_backward_compat():
    repo = TradingRepository()
    assert repo._real_table == "real_trading_records"

def test_custom_table_name():
    repo = TradingRepository(real_table_name="real_trading_rs_leader")
    assert repo._real_table == "real_trading_rs_leader"

def test_validate_rejects_injection():
    with pytest.raises(ValueError):
        TradingRepository(real_table_name="real_trading_x; DROP TABLE foo")
    with pytest.raises(ValueError):
        TradingRepository(real_table_name="random_table")

def test_validate_accepts_default_and_prefixed():
    assert TradingRepository._validate_table_name("real_trading_records") == "real_trading_records"
    assert TradingRepository._validate_table_name("real_trading_rs_leader") == "real_trading_rs_leader"

def test_queries_use_custom_table(monkeypatch):
    captured = []
    class FakeCursor:
        def execute(self, sql, params=None): captured.append(sql)
        def fetchone(self): return [0]
    class FakeConn:
        def cursor(self): return FakeCursor()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    repo = TradingRepository(real_table_name="real_trading_rs_leader")
    monkeypatch.setattr(repo, "_get_connection", lambda: FakeConn())
    repo.get_today_real_loss_count("005930")
    assert any("real_trading_rs_leader" in s for s in captured)
    assert not any("FROM real_trading_records" in s for s in captured)
