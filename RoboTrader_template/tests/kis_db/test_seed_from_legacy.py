from scripts.kis_db.seed_from_legacy import (
    build_daily_insert_rows, DAILY_COLUMNS, FOREIGN_COLUMNS, seed_foreign_flow,
)
import scripts.kis_db.seed_from_legacy as seed


def test_daily_columns_order_matches_schema():
    assert DAILY_COLUMNS == [
        "stock_code", "date", "open", "high", "low", "close",
        "volume", "trading_value", "market_cap",
        "returns_1d", "returns_5d", "returns_20d", "volatility_20d", "adj_factor",
    ]


def test_build_daily_insert_rows_passthrough_tuples():
    src = [("005930", "2026-06-22", 70000.0, 71000.0, 69000.0, 70500.0,
            1000, 70_000_000, 4.2e14, 0.01, 0.02, 0.03, 0.15, 1.0)]
    out = build_daily_insert_rows(src)
    assert out == src
    assert len(out[0]) == len(DAILY_COLUMNS)


def test_foreign_columns_match_schema():
    assert FOREIGN_COLUMNS == ["stock_code", "date", "foreign_net_vol", "source"]


def test_seed_foreign_flow_builds_select_and_targets_quant(monkeypatch):
    """seed_foreign_flow 가 robotrader_quant.foreign_flow → kis(foreign_flow) 로 _copy 한다."""
    captured = {}

    def _fake_copy(src_dbname, select_sql, table, columns, apply, row_builder=None):
        captured.update(dict(src=src_dbname, sql=select_sql, table=table,
                             columns=columns, apply=apply))
        return {"copied": 0, "source_rows": 0}

    monkeypatch.setattr(seed, "_copy", _fake_copy)
    out = seed_foreign_flow(apply=False)
    assert out == {"copied": 0, "source_rows": 0}
    assert captured["src"] == "robotrader_quant"
    assert captured["table"] == "foreign_flow"
    assert captured["columns"] == FOREIGN_COLUMNS
    assert captured["sql"] == "SELECT stock_code, date, foreign_net_vol, source FROM foreign_flow"
    assert captured["apply"] is False
