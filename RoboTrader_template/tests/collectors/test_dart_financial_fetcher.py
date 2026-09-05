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


def test_three_connection_resets_raise_blocked(monkeypatch):
    """3연속 ConnectionError 는 DartBlocked 를 raise 하고 monkeypatch seam 을 유지한다."""
    import requests
    fetcher = f.DartFinancialFetcher("k", min_interval=0.0)

    # Track how many times the mocked get was called
    call_count = [0]
    def mock_get(*a, **kw):
        call_count[0] += 1
        raise requests.exceptions.ConnectionError("mock reset")

    monkeypatch.setattr(fetcher.session, "get", mock_get)
    monkeypatch.setattr("time.sleep", lambda x: None)  # no-op sleep

    with pytest.raises(f.DartBlocked):
        fetcher.fetch("00126380", "2026", "11013", "CFS")

    # Verify the same session.get was called (not a new unpatched session)
    assert call_count[0] == 3


def test_throttle_enforces_min_interval(monkeypatch):
    """min_interval 을 _throttle 이 준수하는지 확인한다."""
    import time as time_module
    fetcher = f.DartFinancialFetcher("k", min_interval=0.2)

    # Track sleep calls
    sleep_args = []
    def mock_sleep(seconds):
        sleep_args.append(seconds)

    monkeypatch.setattr("time.sleep", mock_sleep)
    monkeypatch.setattr(fetcher.session, "get", lambda *a, **kw: _Resp({"status": "013"}))

    # Make two back-to-back fetches
    fetcher.fetch("00126380", "2026", "11013", "CFS")
    fetcher.fetch("00126380", "2026", "11014", "CFS")

    # Verify sleep was called with a value between 0 and min_interval
    assert len(sleep_args) > 0
    assert all(0 < s <= 0.2 for s in sleep_args)
