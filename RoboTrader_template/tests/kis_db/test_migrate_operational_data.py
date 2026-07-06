import json
import scripts.kis_db.migrate_operational_data as mig


def test_vtr_columns_exact_order():
    assert mig.VTR_COLUMNS == [
        "id", "stock_code", "stock_name", "action", "quantity", "price",
        "timestamp", "strategy", "reason", "is_test", "profit_loss",
        "profit_rate", "buy_record_id", "target_profit_rate", "stop_loss_rate",
        "created_at", "source",
    ]


def test_vtr_select_filters_our_source_and_orders_by_id():
    sql = mig.build_vtr_select()
    assert sql == (
        "SELECT id, stock_code, stock_name, action, quantity, price, "
        "timestamp, strategy, reason, is_test, profit_loss, profit_rate, "
        "buy_record_id, target_profit_rate, stop_loss_rate, created_at, source "
        "FROM virtual_trading_records WHERE source = 'kis_template' ORDER BY id"
    )


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
    # apply=False 면 source_rows 만 세고 copied=0 (쓰기 없음)
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
