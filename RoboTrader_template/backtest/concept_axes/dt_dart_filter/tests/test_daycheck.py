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
    assert C.judge(rd, n_db=2, dup=1) and not C.judge(rd, n_db=2, dup=0)


def test_missing_page_is_not_complete(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _page(raw, "I", 1, [{"rcept_no": "1"}], 2, 2)
    rd = C.read_raw_day(tmp_path, "I", D)
    assert rd.state == "missing" and not C.judge(rd, 1, 0)


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
    assert C.judge(rd, 0, 0) and not C.judge(rd, 1, 0)


def test_no_raw_no_log_is_missing(tmp_path):
    (tmp_path / "raw").mkdir()
    assert C.read_raw_day(tmp_path, "B", D).state == "missing"
