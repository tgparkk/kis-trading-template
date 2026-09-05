import gzip
import json
import pytest
from collectors import dart_financial_fetcher as f


class _Resp:
    def __init__(self, js, code=200):
        self._js, self.status_code = js, code

    def json(self):
        return self._js


def test_quota_exceeded_raises_not_returns_empty(monkeypatch):
    """🔴 status=020 을 «0건»으로 돌려주면 조용히 빈 수집이 «성공»이 된다."""
    fetcher = f.DartFinancialFetcher("k", min_interval=0.0)
    monkeypatch.setattr(fetcher.session, "get", lambda *a, **kw: _Resp({"status": "020"}))
    with pytest.raises(f.DartQuotaExceeded):
        fetcher.fetch("00126380", "2026", "11013", "CFS")


def test_no_data_returns_013_not_exception(monkeypatch):
    """013(무자료)은 정상 종료다 — 예외로 올리면 EOD 가 매번 시끄러워진다."""
    fetcher = f.DartFinancialFetcher("k", min_interval=0.0)
    monkeypatch.setattr(fetcher.session, "get", lambda *a, **kw: _Resp({"status": "013"}))
    status, payload = fetcher.fetch("00126380", "2026", "11013", "CFS")
    assert status == "013"
    assert payload.get("list") in (None, [])


def test_append_raw_returns_line_number(tmp_path):
    """raw_path 로 원본을 역추적할 수 있어야 한다."""
    p = str(tmp_path / "dart_20260813.jsonl.gz")
    assert f.append_raw(p, {"a": 1}) == 1
    assert f.append_raw(p, {"a": 2}) == 2
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        lines = [json.loads(x) for x in fh]
    assert lines == [{"a": 1}, {"a": 2}]
