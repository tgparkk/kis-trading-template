# tests/test_adj_backup_sql.py
"""백업 SQL 계약 — DB 에 붙지 않고 문자열만 검사한다."""
from db.adj_backup import DDL_SQL, BACKUP_SQL, RESTORE_SQL


def test_ddl_creates_table_if_not_exists_and_never_drops():
    assert "CREATE TABLE IF NOT EXISTS daily_prices_preadj_backup" in DDL_SQL
    for forbidden in ("DROP ", "TRUNCATE"):
        assert forbidden not in DDL_SQL.upper()


def test_backup_captures_every_column_we_may_overwrite():
    for col in ("open", "high", "low", "close", "volume", "adj_factor"):
        assert col in BACKUP_SQL


def test_backup_is_insert_only_no_update():
    assert BACKUP_SQL.strip().upper().startswith("INSERT")
    assert "ON CONFLICT DO NOTHING" in BACKUP_SQL.upper()


def test_restore_writes_back_all_columns_and_is_scoped_to_batch():
    assert RESTORE_SQL.strip().upper().startswith("UPDATE")
    assert "batch_id" in RESTORE_SQL
    for col in ("open", "high", "low", "close", "volume", "adj_factor"):
        assert col in RESTORE_SQL
