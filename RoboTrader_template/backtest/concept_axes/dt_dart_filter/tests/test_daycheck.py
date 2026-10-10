import json
from datetime import date

from backtest.concept_axes.dt_dart_filter import daycheck as C

D = date(2022, 5, 4)


def _page(raw, ty, p, items, tc, tp, status="000"):
    (raw / f"20220504_{ty}_p{p}.json").write_text(json.dumps(
        {"status": status, "total_count": tc, "total_page": tp, "list": items}), encoding="utf-8")


def test_ok_day_two_pages(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _page(raw, "B", 1, [{"rcept_no": "1"}, {"rcept_no": "2"}], 3, 2)
    _page(raw, "B", 2, [{"rcept_no": "3"}], 3, 2)
    rd = C.read_raw_day(tmp_path, "B", D)
    assert rd.state == "ok" and rd.total_count == 3 and rd.rcept_nos == ("1", "2", "3")
    assert C.judge(rd, n_member=2, dup=1, n_extra=0) and not C.judge(rd, n_member=2, dup=0, n_extra=0)


def test_missing_page_is_not_complete(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _page(raw, "I", 1, [{"rcept_no": "1"}], 2, 2)
    rd = C.read_raw_day(tmp_path, "I", D)
    assert rd.state == "missing" and not C.judge(rd, 1, 0, 0)


def test_bad_status_page(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _page(raw, "B", 1, [], 0, 1, status="020")
    assert C.read_raw_day(tmp_path, "B", D).state == "bad"


def test_013_from_call_log_counts_as_empty_day(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "call_log.jsonl").write_text(json.dumps(
        {"url": "https://x/list.json?bgn_de=20220504&end_de=20220504&pblntf_ty=A&page_no=1", "status": "013"}) + "\n",
        encoding="utf-8")
    rd = C.read_raw_day(tmp_path, "A", D)
    assert rd.state == "empty013"
    assert C.judge(rd, 0, 0, 0) and not C.judge(rd, 0, 0, 1) and not C.judge(rd, 1, 0, 0)


def test_no_raw_no_log_is_missing(tmp_path):
    (tmp_path / "raw").mkdir()
    assert C.read_raw_day(tmp_path, "B", D).state == "missing"


# --- fix round 1: membership, not count ---

def test_extra_row_cannot_offset_missing_row():
    # raw lists 1,2 (tc=2); DB has only 1 (row 2 missing) plus stray row 9 of same day/type.
    rd = C.RawDay("ok", 2, ("1", "2"))
    assert not C.judge(rd, n_member=1, dup=0, n_extra=1)


def test_extra_row_fails_even_when_members_complete():
    rd = C.RawDay("ok", 2, ("1", "2"))
    assert not C.judge(rd, n_member=2, dup=0, n_extra=1)


def test_duplicate_raw_nos_fail():
    rd = C.RawDay("ok", 2, ("1", "1"))
    assert not C.judge(rd, n_member=2, dup=0, n_extra=0)


class _FakeCur:
    """Answers each SQL by its shape: member / dup / extra / day-only."""

    def __init__(self, answers):
        self.answers = answers
        self.val = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if "pblntf_ty <> %s" in sql:
            self.val = self.answers["dup"]
        elif "NOT (" in sql:
            self.val = self.answers["extra"]
        elif "rcept_no = ANY" in sql:
            self.val = self.answers["member"]
        else:
            self.val = self.answers["day"]

    def fetchone(self):
        return (self.val,)


class _FakeConn:
    def __init__(self, answers):
        self.answers = answers
        self.rolled_back = False

    def cursor(self):
        return _FakeCur(self.answers)

    def rollback(self):
        self.rolled_back = True


def _one_ok_day(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _page(raw, "B", 1, [{"rcept_no": "1"}, {"rcept_no": "2"}], 2, 1)
    return tmp_path


def test_check_clean_day_is_complete(tmp_path):
    out = _one_ok_day(tmp_path)
    conn = _FakeConn({"member": 2, "dup": 0, "extra": 0, "day": 2})
    res = C.check(conn, out, D, D, ["B"])
    assert res == {"n_cells": 1, "n_bad": 0, "bad": [], "complete": True}
    assert conn.rolled_back


def test_check_extra_row_is_incomplete(tmp_path):
    out = _one_ok_day(tmp_path)
    conn = _FakeConn({"member": 2, "dup": 0, "extra": 1, "day": 3})
    res = C.check(conn, out, D, D, ["B"])
    assert res["complete"] is False and res["n_bad"] == 1
    bad = res["bad"][0]
    assert bad["n_extra"] == 1 and bad["n_member"] == 2 and bad["day"] == "2022-05-04" and bad["ty"] == "B"
