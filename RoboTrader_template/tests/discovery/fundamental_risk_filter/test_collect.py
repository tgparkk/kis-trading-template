import gzip
import json
import os
import sys

import pytest

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import dart_client as dc  # noqa: E402
import f2_collect as f2  # noqa: E402


class _FakeClient:
    """호출 순서를 기록하고 미리 정한 응답을 돌려주는 클라이언트."""

    def __init__(self, responses):
        self.responses = responses
        self.seen = []

    def fnltt_all(self, corp_code, bsns_year, reprt_code, fs_div):
        self.seen.append((corp_code, bsns_year, fs_div))
        return self.responses.pop(0)


ITEM = {"stock_code": "005930", "corp_code": "00126380", "bsns_year": "2022"}


def test_cfs_is_tried_first():
    c = _FakeClient([("000", "", [{"account_nm": "자본총계"}])])
    out = f2.collect_one(c, ITEM)
    assert c.seen[0][2] == "CFS"
    assert out["fs_div"] == "CFS"
    assert out["status"] == "000"


def test_falls_back_to_ofs_when_cfs_has_no_data():
    """연결재무제표가 없는 회사는 별도로 떨어진다 — 013 을 결측으로 확정하지 않는다."""
    c = _FakeClient([
        ("013", "무자료", []),
        ("000", "", [{"account_nm": "자본총계"}]),
    ])
    out = f2.collect_one(c, ITEM)
    assert [s[2] for s in c.seen] == ["CFS", "OFS"]
    assert out["fs_div"] == "OFS"
    assert out["status"] == "000"


def test_both_missing_records_013_not_an_empty_success():
    """둘 다 없으면 013 으로 «기록»한다. 성공으로 위장하지 않는다."""
    c = _FakeClient([("013", "무자료", []), ("013", "무자료", [])])
    out = f2.collect_one(c, ITEM)
    assert out["status"] == "013"
    assert out["rows"] == []
    assert out["fs_div"] is None


def test_quota_exceeded_propagates():
    """한도 초과는 삼키지 않는다 — 위로 올려 즉시 중단시킨다."""
    class _Q:
        def fnltt_all(self, *a, **k):
            raise dc.DartQuotaExceeded("020")

    with pytest.raises(dc.DartQuotaExceeded):
        f2.collect_one(_Q(), ITEM)


def test_load_done_reads_checkpoint(tmp_path):
    p = tmp_path / "raw.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"stock_code": "005930", "bsns_year": "2022"}) + "\n")
        f.write(json.dumps({"stock_code": "000660", "bsns_year": "2021"}) + "\n")
    done = f2.load_done(str(p))
    assert done == {("005930", "2022"), ("000660", "2021")}


def test_load_done_on_missing_file_is_empty(tmp_path):
    assert f2.load_done(str(tmp_path / "nope.jsonl.gz")) == set()


def test_load_done_tolerates_truncated_last_line(tmp_path):
    """중단 시점에 마지막 줄이 잘려 있을 수 있다. 그 한 줄만 버리고 재개한다."""
    p = tmp_path / "raw.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"stock_code": "005930", "bsns_year": "2022"}) + "\n")
        f.write('{"stock_code": "0006')
    done = f2.load_done(str(p))
    assert done == {("005930", "2022")}
