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
    assert not s.any_sealed()


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
