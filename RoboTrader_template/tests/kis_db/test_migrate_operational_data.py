import json

import pytest

import scripts.kis_db.migrate_operational_data as mig


def test_vtr_columns_exact_order():
    # 드리프트 가드: 라이브 robotrader.virtual_trading_records 의 is_overflow(created_at 뒤,
    # source 앞)가 이관 컬럼 목록에서 누락됐던 회귀 방지.
    assert mig.VTR_COLUMNS == [
        "id", "stock_code", "stock_name", "action", "quantity", "price",
        "timestamp", "strategy", "reason", "is_test", "profit_loss",
        "profit_rate", "buy_record_id", "target_profit_rate", "stop_loss_rate",
        "created_at", "is_overflow", "source",
    ]


def test_vtr_select_filters_our_source_and_orders_by_id():
    sql = mig.build_vtr_select()
    assert sql == (
        "SELECT id, stock_code, stock_name, action, quantity, price, "
        "timestamp, strategy, reason, is_test, profit_loss, profit_rate, "
        "buy_record_id, target_profit_rate, stop_loss_rate, created_at, "
        "is_overflow, source "
        "FROM virtual_trading_records WHERE source = 'kis_template' ORDER BY id"
    )


def test_real_columns_exact_order():
    # 드리프트 가드: 라이브 robotrader.real_trading_records 의 fee_amount/net_profit/
    # net_profit_rate(created_at 뒤)가 이관 컬럼 목록에서 누락됐던 회귀 방지.
    assert mig.REAL_COLUMNS == [
        "id", "stock_code", "stock_name", "action", "quantity", "price",
        "timestamp", "strategy", "reason", "profit_loss", "profit_rate",
        "buy_record_id", "created_at", "fee_amount", "net_profit", "net_profit_rate",
    ]


def test_screener_columns_and_json_serialization():
    assert mig.SCREENER_COLUMNS == [
        "id", "strategy", "scan_date", "params_hash", "params_json",
        "stock_code", "stock_name", "rank_in_snapshot", "score", "metadata",
        "created_at",
    ]
    # params_json(idx 4), metadata(idx 9) dict → JSON 문자열
    src = [(1, "elder", "2026-07-01", "abcd", {"k": 1}, "005930", "삼성", 1, 9.9, {"sector": "IT"}, "2026-07-01 09:00:00")]
    out = mig.build_screener_rows(src)
    assert out[0][4] == json.dumps({"k": 1}, ensure_ascii=False)
    assert out[0][9] == json.dumps({"sector": "IT"}, ensure_ascii=False)
    # None metadata 는 그대로 None
    src2 = [(2, "elder", "2026-07-01", "abcd", {"k": 1}, "000660", "하닉", 2, 8.8, None, "2026-07-01 09:00:00")]
    assert mig.build_screener_rows(src2)[0][9] is None


def test_discover_real_tables_filters_prefix():
    class _Cur:
        def execute(self, sql, params=None): self._sql = sql
        def fetchall(self): return [("real_trading_records",), ("real_trading_elder",)]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Conn:
        def cursor(self): return _Cur()

    assert mig.discover_real_tables(_Conn()) == ["real_trading_records", "real_trading_elder"]


def test_migrate_table_dry_run_counts_source_only(monkeypatch):
    # apply=False 면 source_rows 만 세고 copied=0 (쓰기 없음) — get_connection 자체가 호출되면 안 됨
    def _fail_if_called(*a, **kw):
        raise AssertionError("get_connection must not be called when apply=False")

    monkeypatch.setattr(mig.KisDbConnection, "get_connection", _fail_if_called)

    class _SCur:
        itersize = None
        def execute(self, sql): pass
        def fetchmany(self, n):
            if not getattr(self, "_done", False):
                self._done = True
                return [(1, "005930")]
            return []
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Src:
        def cursor(self, name=None): return _SCur()

    out = mig.migrate_table(_Src(), "SELECT 1", "candidate_stocks",
                            ["id", "stock_code"], "(id)", apply=False)
    assert out == {"table": "candidate_stocks", "source_rows": 1, "copied": 0}


class _OneRowSCur:
    """소스 커서 페이크: 1 배치(1행)만 반환하고 끝."""
    itersize = None
    def execute(self, sql): pass
    def fetchmany(self, n):
        if not getattr(self, "_done", False):
            self._done = True
            return [(1, "005930")]
        return []
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _OneRowSrc:
    def cursor(self, name=None): return _OneRowSCur()


class _FakeDCur:
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _FakeDstConn:
    def __init__(self):
        self.committed = False
        self.rolledback = False

    def cursor(self):
        return _FakeDCur()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolledback = True


class _FakeCM:
    """KisDbConnection.get_connection() 이 반환하는 컨텍스트매니저 페이크."""
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *a):
        return False


def test_migrate_table_apply_builds_upsert_calls_execute_values_and_commits(monkeypatch):
    dst_conn = _FakeDstConn()
    monkeypatch.setattr(mig.KisDbConnection, "get_connection", lambda: _FakeCM(dst_conn))

    calls = {}

    def fake_execute_values(cur, sql, rows, template=None):
        calls["sql"] = sql
        calls["rows"] = rows

    monkeypatch.setattr(mig, "execute_values", fake_execute_values)

    out = mig.migrate_table(_OneRowSrc(), "SELECT 1", "candidate_stocks",
                            ["id", "stock_code"], "(id)", apply=True)

    assert out == {"table": "candidate_stocks", "source_rows": 1, "copied": 1}
    assert calls["sql"] == (
        "INSERT INTO candidate_stocks (id, stock_code) VALUES %s ON CONFLICT (id) DO NOTHING"
    )
    assert calls["rows"] == [(1, "005930")]
    assert dst_conn.committed is True
    assert dst_conn.rolledback is False


def test_migrate_table_apply_bare_conflict_when_no_target(monkeypatch):
    # virtual_trading_records/screener_snapshots 처럼 conflict_target=None → 무대상 ON CONFLICT
    dst_conn = _FakeDstConn()
    monkeypatch.setattr(mig.KisDbConnection, "get_connection", lambda: _FakeCM(dst_conn))

    calls = {}

    def fake_execute_values(cur, sql, rows, template=None):
        calls["sql"] = sql

    monkeypatch.setattr(mig, "execute_values", fake_execute_values)

    mig.migrate_table(_OneRowSrc(), "SELECT 1", "virtual_trading_records",
                      ["id", "stock_code"], None, apply=True)

    assert calls["sql"] == (
        "INSERT INTO virtual_trading_records (id, stock_code) VALUES %s ON CONFLICT DO NOTHING"
    )


def test_migrate_table_apply_rollback_on_execute_values_error(monkeypatch):
    dst_conn = _FakeDstConn()
    monkeypatch.setattr(mig.KisDbConnection, "get_connection", lambda: _FakeCM(dst_conn))

    def boom(cur, sql, rows, template=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(mig, "execute_values", boom)

    with pytest.raises(RuntimeError):
        mig.migrate_table(_OneRowSrc(), "SELECT 1", "candidate_stocks",
                          ["id", "stock_code"], "(id)", apply=True)

    assert dst_conn.rolledback is True
    assert dst_conn.committed is False


def test_bump_serial_sequence_uses_setval_max_coalesce():
    class _Cur:
        def execute(self, sql, params=None):
            self.sql = sql
            self.params = params
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Conn:
        def __init__(self):
            self.committed = False
            self._cur = _Cur()

        def cursor(self):
            return self._cur

        def commit(self):
            self.committed = True

    conn = _Conn()
    mig.bump_serial_sequence(conn, "candidate_stocks")

    assert conn._cur.sql == (
        "SELECT setval(pg_get_serial_sequence(%s, %s), "
        "COALESCE((SELECT MAX(id) FROM candidate_stocks), 1))"
    )
    assert conn._cur.params == ("candidate_stocks", "id")
    assert conn.committed is True


def test_validate_instance_rejects_sql_injection_attempt():
    with pytest.raises(ValueError):
        mig.validate_instance("real; DROP")


def test_validate_instance_accepts_well_formed_name():
    assert mig.validate_instance("real_trading_elder") == "real_trading_elder"


def test_run_rejects_bad_instance_before_any_sql(monkeypatch):
    # extra_instances 의 불량값은 discover_real_tables/SQL 사용 전에 거부되어야 함.
    def _fail_if_called(*a, **kw):
        raise AssertionError("_source_conn must not be reached for a bad --instance value")

    monkeypatch.setattr(mig, "_source_conn", _fail_if_called)

    with pytest.raises(ValueError):
        mig.run(apply=False, extra_instances=["real; DROP TABLE x;--"])


def test_source_conn_sets_readonly_session(monkeypatch):
    calls = {}

    class _FakeConn:
        def set_session(self, readonly=None):
            calls["readonly"] = readonly

    monkeypatch.setattr(mig.psycopg2, "connect", lambda **kw: _FakeConn())

    conn = mig._source_conn()
    assert calls["readonly"] is True
    assert isinstance(conn, _FakeConn)
