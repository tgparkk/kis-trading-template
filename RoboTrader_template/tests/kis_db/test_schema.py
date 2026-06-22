from scripts.kis_db.schema import DDL_STATEMENTS, EXPECTED_TABLES


def test_expected_tables_present():
    assert EXPECTED_TABLES == {
        "minute_candles", "daily_prices", "index_daily",
        "corp_events", "collection_reconciliation",
    }


def test_every_expected_table_has_ddl():
    joined = "\n".join(DDL_STATEMENTS).lower()
    for t in EXPECTED_TABLES:
        assert f"create table if not exists {t}" in joined, f"DDL 누락: {t}"


def test_daily_prices_date_is_text_not_date():
    # 레거시 동일: date 는 TEXT(YYYY-MM-DD)
    dp = [s for s in DDL_STATEMENTS if "daily_prices" in s.lower()][0].lower()
    assert "date text" in dp


def test_minute_candles_pk_matches_legacy():
    mc = [s for s in DDL_STATEMENTS if "minute_candles" in s.lower()][0].lower()
    assert "primary key (stock_code, trade_date, idx)" in mc
