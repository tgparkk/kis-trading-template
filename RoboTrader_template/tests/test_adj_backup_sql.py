# tests/test_adj_backup_sql.py
"""백업 SQL 계약 — DB 에 붙지 않고 문자열만 검사한다.

원래 4개는 부분문자열 검사라 컬럼이 뒤바뀌어도(swap) 통과한다. 아래 구조적
테스트는 SET 절/컬럼 목록을 실제로 파싱해 위치별로 대응시켜, 리뷰어가 지적한
두 가지 결함(RESTORE_SQL 컬럼 뒤바뀜, BACKUP_SQL INSERT/SELECT 목록 어긋남)을
잡아낸다. 🆕 세 번째로 **RESTORE_SQL 의 조인 술어**도 파싱해 검사한다 —
`AND dp.date = b.date` 를 지우면 백업 한 행이 그 종목의 «모든 날짜»에 발라지는데
(복원이 아니라 이력 파괴다) 나머지 테스트는 전부 통과했다. 「이빨」 테스트들은
그 파싱 체크가 실제로 판별하는지 로컬 복사본을 일부러 망가뜨려 증명한다
(모듈 자체는 건드리지 않는다).
"""
import re

import pytest

from db.adj_backup import DDL_SQL, BACKUP_SQL, RESTORE_SQL

_DATA_COLUMNS = ("open", "high", "low", "close", "volume", "adj_factor")


def test_ddl_creates_table_if_not_exists_and_never_drops():
    assert "CREATE TABLE IF NOT EXISTS daily_prices_preadj_backup" in DDL_SQL
    for forbidden in ("DROP ", "TRUNCATE"):
        assert forbidden not in DDL_SQL.upper()


def test_backup_captures_every_column_we_may_overwrite():
    for col in _DATA_COLUMNS:
        assert col in BACKUP_SQL


def test_backup_is_insert_only_no_update():
    assert BACKUP_SQL.strip().upper().startswith("INSERT")
    assert "ON CONFLICT DO NOTHING" in BACKUP_SQL.upper()


def test_restore_writes_back_all_columns_and_is_scoped_to_batch():
    assert RESTORE_SQL.strip().upper().startswith("UPDATE")
    assert "batch_id" in RESTORE_SQL
    for col in _DATA_COLUMNS:
        assert col in RESTORE_SQL


# ---------------------------------------------------------------------------
# Structural checks — parse the actual clauses instead of substring-matching.
# ---------------------------------------------------------------------------


def _parse_set_pairs(sql):
    """Extract `col = expr` pairs from the SET ... FROM clause of an UPDATE."""
    m = re.search(r"\bSET\b(.*?)\bFROM\b", sql, re.DOTALL)
    assert m, "no SET ... FROM clause found in restore SQL"
    pairs = {}
    for chunk in m.group(1).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, sep, value = chunk.partition("=")
        assert sep, "malformed SET assignment: {!r}".format(chunk)
        pairs[key.strip()] = value.strip()
    return pairs


def _assert_restore_columns_self_mapped(sql):
    pairs = _parse_set_pairs(sql)
    for col in _DATA_COLUMNS:
        expected = "b.{}".format(col)
        actual = pairs.get(col)
        assert actual == expected, (
            "expected `{} = {}` in RESTORE_SQL SET clause, found `{} = {}`".format(
                col, expected, col, actual
            )
        )


def _parse_insert_columns(sql):
    m = re.search(
        r"INSERT INTO daily_prices_preadj_backup\s*\(([^)]*)\)", sql, re.DOTALL
    )
    assert m, "no INSERT column list found in backup SQL"
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


def _parse_select_items(sql):
    m = re.search(r"\bSELECT\b(.*?)\bFROM\s+daily_prices\b", sql, re.DOTALL)
    assert m, "no SELECT ... FROM daily_prices clause found in backup SQL"
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


def _normalize_select_item(item):
    m = re.match(r"^%\((\w+)\)s$", item)
    return m.group(1) if m else item


def _assert_backup_columns_aligned(sql):
    insert_cols = _parse_insert_columns(sql)
    select_items = [_normalize_select_item(i) for i in _parse_select_items(sql)]
    assert insert_cols == select_items, (
        "INSERT column list {} does not positionally match SELECT projection {}".format(
            insert_cols, select_items
        )
    )
    for col in _DATA_COLUMNS:
        assert col in insert_cols


def test_restore_set_clause_maps_each_column_to_itself():
    """Would fail on a swap like `high = b.low, low = b.high`."""
    _assert_restore_columns_self_mapped(RESTORE_SQL)


def test_backup_insert_and_select_column_lists_align():
    """Would fail if the INSERT column list and SELECT projection drift out
    of positional sync (e.g. a column added to one list but not the other,
    or reordered in only one of the two)."""
    _assert_backup_columns_aligned(BACKUP_SQL)


# ---------------------------------------------------------------------------
# Prove the structural checks above actually discriminate — mutate a local
# copy of the SQL string (never the module) and confirm the check rejects it.
# ---------------------------------------------------------------------------


def _parse_where_conditions(sql):
    """Split the trailing WHERE clause of an UPDATE into normalised conditions."""
    m = re.search(r"\bWHERE\b(.*)$", sql, re.DOTALL | re.IGNORECASE)
    assert m, "no WHERE clause found in restore SQL"
    out = []
    for cond in re.split(r"\bAND\b", m.group(1), flags=re.IGNORECASE):
        cond = re.sub(r"\s+", " ", cond).strip()
        if cond:
            out.append(cond)
    return out


def _equality_pairs(sql):
    """WHERE conditions as orientation-agnostic {lhs, rhs} pairs."""
    pairs = set()
    for cond in _parse_where_conditions(sql):
        lhs, sep, rhs = cond.partition("=")
        assert sep, "non-equality condition in restore WHERE clause: {!r}".format(cond)
        pairs.add(frozenset((lhs.strip(), rhs.strip())))
    return pairs


def _assert_restore_join_is_row_for_row(sql):
    """🔴 The restore must match ONE backup row to ONE daily_prices row.

    Dropping `dp.date = b.date` would smear a single backup row across *every*
    date of that stock — a rollback that destroys history instead of restoring
    it — and every substring/SET-clause test in this file still passes.
    Dropping `b.batch_id = %(batch_id)s` would replay *all* batches at once.
    """
    pairs = _equality_pairs(sql)
    for want in (
        frozenset(("dp.stock_code", "b.stock_code")),
        frozenset(("dp.date", "b.date")),
        frozenset(("b.batch_id", "%(batch_id)s")),
    ):
        assert want in pairs, (
            "restore WHERE clause is missing `{}` — found {}".format(
                " = ".join(sorted(want)), sorted(sorted(p) for p in pairs)
            )
        )


def test_restore_joins_on_stock_code_and_date_and_is_scoped_to_batch():
    _assert_restore_join_is_row_for_row(RESTORE_SQL)


def test_join_predicate_check_detects_missing_date_condition():
    """Proof of teeth: without this check, deleting the date join goes unnoticed."""
    mutated = RESTORE_SQL.replace(" AND dp.date = b.date", "")
    assert mutated != RESTORE_SQL, "fixture did not actually mutate — test is vacuous"
    # The pre-existing tests would all still pass on this mutant …
    _assert_restore_columns_self_mapped(mutated)
    for col in _DATA_COLUMNS:
        assert col in mutated
    # … and only the join check rejects it.
    with pytest.raises(AssertionError):
        _assert_restore_join_is_row_for_row(mutated)


def test_join_predicate_check_detects_missing_batch_scope():
    mutated = RESTORE_SQL.replace("b.batch_id = %(batch_id)s\n  AND ", "")
    assert mutated != RESTORE_SQL, "fixture did not actually mutate — test is vacuous"
    with pytest.raises(AssertionError):
        _assert_restore_join_is_row_for_row(mutated)


def test_set_clause_check_detects_swapped_columns():
    mutated = RESTORE_SQL.replace(
        "high = b.high, low = b.low",
        "high = b.low, low = b.high",
    )
    assert mutated != RESTORE_SQL, "fixture did not actually mutate — test is vacuous"
    with pytest.raises(AssertionError):
        _assert_restore_columns_self_mapped(mutated)


def test_column_alignment_check_detects_misaligned_insert_columns():
    mutated = BACKUP_SQL.replace(
        "(batch_id, stock_code, date, open, high, low, close, volume, adj_factor)",
        "(batch_id, stock_code, date, high, open, low, close, volume, adj_factor)",
    )
    assert mutated != BACKUP_SQL, "fixture did not actually mutate — test is vacuous"
    with pytest.raises(AssertionError):
        _assert_backup_columns_aligned(mutated)
