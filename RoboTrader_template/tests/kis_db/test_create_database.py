from scripts.kis_db.create_database import database_exists


class _FakeCur:
    def __init__(self, exists): self._exists = exists; self.executed = None
    def execute(self, sql, params=None): self.executed = (sql, params)
    def fetchone(self): return (1,) if self._exists else None
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _FakeConn:
    def __init__(self, exists): self._exists = exists
    def cursor(self): return _FakeCur(self._exists)


def test_database_exists_true_when_row_returned():
    assert database_exists(_FakeConn(True), "kis_template") is True


def test_database_exists_false_when_no_row():
    assert database_exists(_FakeConn(False), "kis_template") is False
