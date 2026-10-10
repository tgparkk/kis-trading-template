import re
from datetime import date

import pytest

from backtest.concept_axes.dtflow_shadow import settings as S
from backtest.concept_axes.dtflow_shadow import store as ST


def _cand(code="000001", D=date(2026, 10, 8)):
    r = {c: None for c in ST.CAND_COLS}
    r.update(rule_v="v1", scan_date=D, stock_code=code, rank=1, score=2.5, code_sha="x", late=False)
    r["row_sha"] = ST.row_sha(r, ST.CAND_COLS)
    return r


def _run(D=date(2026, 10, 8), status="ok"):
    r = {c: None for c in ST.RUN_COLS}
    r.update(rule_v="v1", scan_date=D, run_kind="record", run_at="2026-10-12T07:52:00+09:00", status=status, code_sha="x")
    return r


def test_ddl_columns_match_lists():
    ddl = (S.PKG / "ddl.sql").read_text(encoding="utf-8")
    for table, cols in (("trial_candidates", ST.CAND_COLS), ("trial_raw", ST.RAW_COLS), ("trial_run", ST.RUN_COLS)):
        body = re.search(rf"CREATE TABLE dtflow_shadow\.{table} \((.*?)PRIMARY KEY", ddl, re.S).group(1)
        names = [p.strip().split()[0] for p in body.split(",") if p.strip()]
        assert names == cols, table


def test_memory_store_atomic_and_conflict():
    s = ST.MemoryStore()
    s.write_day("trial", [_cand()], [], _run())
    assert len(s.cands("trial", date(2026, 10, 8))) == 1 and s.runs("trial")[0]["status"] == "ok"
    with pytest.raises(RuntimeError):
        s.write_day("trial", [_cand()], [], _run())                     # 같은 PK = 충돌
    assert len(s.runs("trial")) == 1                                   # 실패한 트랜잭션은 흔적 없음


def test_row_sha_deterministic_and_csv_sorted():
    a, b = _cand("000002"), _cand("000001")
    assert ST.row_sha(a, ST.CAND_COLS) == ST.row_sha(dict(a), ST.CAND_COLS)
    csv = ST.to_csv([a, b], ST.CAND_COLS).decode("utf-8").splitlines()
    assert csv[1].count("000001") == 1


def test_table_names():
    assert ST.table("trial", "run") == "dtflow_shadow.trial_run"
    assert ST.table("sealed", "candidates") == "dtflow_shadow.candidates"
    with pytest.raises(ValueError):
        ST.table("x", "run")


# ---- final fix: I5 · I6 · I7 · M6 ----
def _ddl():
    return (S.PKG / "ddl.sql").read_text(encoding="utf-8")


def _ddl_sql_lines():
    return [ln for ln in _ddl().splitlines() if ln.strip() and not ln.lstrip().startswith("--")]


def test_ddl_owner_is_nologin_role_not_writer():
    ddl = _ddl()
    assert re.search(r"CREATE ROLE dtflow_shadow_owner NOLOGIN;", ddl)
    assert "CREATE SCHEMA dtflow_shadow AUTHORIZATION dtflow_shadow_owner;" in ddl
    assert "AUTHORIZATION dtflow_shadow_writer" not in ddl
    assert "SET ROLE dtflow_shadow_writer" not in ddl                 # 쓰기 역할은 표를 소유하지 않는다
    sql = "\n".join(_ddl_sql_lines())
    i_set, i_reset = sql.index("SET ROLE dtflow_shadow_owner;"), sql.index("RESET ROLE;")
    creates = [m.start() for m in re.finditer(r"CREATE TABLE dtflow_shadow\.", sql)]
    assert len(creates) == 6 and all(i_set < c < i_reset for c in creates)


def test_ddl_writer_gets_insert_select_only_on_six_tables():
    sql = "\n".join(_ddl_sql_lines())
    grants = [ln for ln in sql.splitlines() if ln.startswith("GRANT") and "dtflow_shadow_writer" in ln]
    tbl = [ln for ln in grants if "dtflow_shadow." in ln]
    assert len(tbl) == 1
    assert tbl[0].startswith("GRANT INSERT, SELECT ON ")
    for t in ("trial_candidates", "trial_raw", "trial_run", "candidates", "raw", "run"):
        assert re.search(rf"dtflow_shadow\.{t}\b", tbl[0]), t
    for bad in ("UPDATE", "DELETE", "TRUNCATE", "ALL PRIVILEGES", "GRANT ALL", "CREATE ON SCHEMA dtflow_shadow"):
        assert not any(bad in ln for ln in grants), bad
    assert "GRANT USAGE ON SCHEMA dtflow_shadow TO dtflow_shadow_writer" in sql
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA dtflow_shadow TO robotrader;" in sql


def test_ddl_stops_on_empty_password():
    sql = "\n".join(_ddl_sql_lines())
    i_check = sql.index(r"\gset")
    assert "length(btrim(:'dtflow_pw')) > 0" in sql
    m = re.search(r"\\if :dtflow_pw_ok\s*\n\\else\s*\n(.*?)\\endif", sql, re.S)
    assert m and "RAISE EXCEPTION" in m.group(1)                       # ON_ERROR_STOP 아래 오류 = 중단(종료 코드 ≠ 0)
    assert sql.index(r"\set ON_ERROR_STOP on") < i_check
    assert sql.index("CREATE ROLE") > i_check                          # 확인이 어떤 CREATE 보다 먼저


def test_rows_sha256_ignores_run_at_code_sha_row_sha():
    a = _cand("000001")
    a["run_at"] = "2026-10-12T07:52:00"
    b = dict(a, run_at="2026-10-12T07:52:00+09:00", code_sha="other", row_sha="zz")   # DB 에서 읽어 온 모양
    assert ST.rows_sha256([a]) == ST.rows_sha256([b])
    assert ST.rows_sha256([a]) != ST.rows_sha256([dict(a, f1_orgn=0.1)])
    assert ST.rows_sha256([a]) != ST.rows_sha256([dict(a, late=True)])


def test_writer_password_percent_is_literal(monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "key.ini").write_text("[DTFLOW_SHADOW]\ndb_password = ab%cd%(x)s\n", encoding="utf-8")
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_CONFIG_DIR", str(tmp_path))
    assert ST.writer_password() == "ab%cd%(x)s"


def test_any_sealed_removed():
    assert not hasattr(ST.MemoryStore, "any_sealed") and not hasattr(ST.PgStore, "any_sealed")


class _FakeCur:
    def __init__(self, rowcounts):
        self.rowcounts, self.rowcount, self.executed = list(rowcounts), None, []

    def execute(self, sql, vals=None):
        self.executed.append(sql)
        self.rowcount = self.rowcounts.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, rowcounts):
        self.cur, self.commits, self.rollbacks = _FakeCur(rowcounts), 0, 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_pgstore_tx_conflict_rolls_back_and_raises():
    conn = _FakeConn([1, 0, 1])                                        # 두 번째 INSERT 가 충돌(rowcount 0)
    with pytest.raises(RuntimeError, match="충돌"):
        ST.PgStore(conn).write_day("sealed", [_cand("000001"), _cand("000002")], [], _run())
    assert conn.rollbacks == 1 and conn.commits == 0
    assert len(conn.cur.executed) == 2                                 # 충돌 뒤 run 행은 시도조차 않는다
    assert all("ON CONFLICT DO NOTHING" in s and s.startswith("INSERT INTO dtflow_shadow.") for s in conn.cur.executed)


def test_pgstore_tx_all_inserted_commits_once():
    conn = _FakeConn([1, 1])
    ST.PgStore(conn).write_day("trial", [_cand()], [], _run())
    assert conn.commits == 1 and conn.rollbacks == 0
