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


def test_append_raw_does_not_reread_gz_after_first_call(tmp_path, monkeypatch):
    """🔴 Task 6 review 수정 — 매 호출마다 gz 를 재압축해제하면 백필 규모(수천 호출)에서
    O(n^2) 이 된다. 두 번째 호출부터는 메모리 카운터만 증가해야 하고, 그 확인은
    두 번째 호출이 «읽기 모드로 gzip.open 을 열지 않는다»로 한다(쓰기는 매번 필요하다)."""
    p = str(tmp_path / "dart_20260901.jsonl.gz")
    assert f.append_raw(p, {"a": 1}) == 1  # 첫 호출 — 파일이 없으므로 읽기 시도 없음(정상)

    real_gzip_open = f.gzip.open
    read_modes = []

    def _spy_open(path, mode, *a, **kw):
        read_modes.append(mode)
        return real_gzip_open(path, mode, *a, **kw)

    monkeypatch.setattr(f.gzip, "open", _spy_open)
    assert f.append_raw(p, {"a": 2}) == 2
    assert "rt" not in read_modes, "캐시가 있는데도 gz 를 다시 읽었다 — O(n^2) 회귀"
    assert "at" in read_modes


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


# ── I2(a) — reset_streak 인스턴스 속성 승격 + ReadTimeout 도 전송 실패로 취급 ──

def test_readtimeout_is_treated_as_transport_failure_like_connection_error(monkeypatch):
    """🔴 ReadTimeout 은 ConnectionError 의 서브클래스가 «아니다» — 기존 코드는
    `except requests.exceptions.ConnectionError` 에서 못 잡혀 `except Exception`(http_errors)
    으로 새 나가고, reset_streak 가 절대 늘지 않아 지속 타임아웃에서도 DartBlocked 가
    영원히 안 뜬다. 3연속 ReadTimeout 이 3연속 ConnectionError 와 «똑같이» 취급돼야 한다."""
    import requests
    fetcher = f.DartFinancialFetcher("k", min_interval=0.0)

    call_count = [0]

    def mock_get(*a, **kw):
        call_count[0] += 1
        raise requests.exceptions.ReadTimeout("mock timeout")

    monkeypatch.setattr(fetcher.session, "get", mock_get)
    monkeypatch.setattr("time.sleep", lambda x: None)

    with pytest.raises(f.DartBlocked):
        fetcher.fetch("00126380", "2026", "11013", "CFS")

    assert call_count[0] == 3, "ConnectionError 와 동일하게 3연속에서 차단돼야 한다"


def test_reset_streak_persists_across_fetch_calls_and_resets_on_success(monkeypatch):
    """🔴 Item 2a — reset_streak 가 `fetch()` 지역변수면 매 호출(=매 종목) 마다 0 으로
    재초기화돼, 서로 다른 종목에 걸쳐 일어나는 연속 전송 실패가 «절대» 누적되지 않는다.
    인스턴스 속성으로 승격해야 실제 지속 장애(다음 대상에서도 이어지는 실패)를 잡는다.

    시나리오: 첫 번째 fetch() 호출은 4번의 «성공한»(그러나 상태코드 500인) 응답 뒤
    마지막 2번이 전송 실패로 끝난다(_MAX_TRIES=6 소진 → HTTP_FAIL, reset_streak=2 로 남음).
    이어지는 두 번째 fetch() 호출(다른 대상)의 «첫 시도»가 전송 실패면 2+1=3 이 돼야
    하므로, 그 자리에서 «단 한 번 만에» DartBlocked 가 떠야 한다 — 지역변수였다면 새로
    0부터 세어 3번째 시도까지 가야 떴을 것이다."""
    import requests

    fetcher = f.DartFinancialFetcher("k", min_interval=0.0)
    monkeypatch.setattr("time.sleep", lambda x: None)

    call1_responses = (
        [_Resp({"status": "500"}, code=500)] * 4
        + [requests.exceptions.ReadTimeout("t1"), requests.exceptions.ConnectionError("c1")]
    )
    idx1 = [0]

    def _get1(*a, **kw):
        item = call1_responses[idx1[0]]
        idx1[0] += 1
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(fetcher.session, "get", _get1)

    status, payload = fetcher.fetch("00000001", "2026", "11013", "CFS")
    assert status == "HTTP_FAIL"
    assert fetcher.reset_streak == 2, "마지막 2연속 전송 실패가 인스턴스 속성에 남아 있어야 한다"

    call2_count = [0]

    def _get2(*a, **kw):
        call2_count[0] += 1
        raise requests.exceptions.ReadTimeout("t2")

    monkeypatch.setattr(fetcher.session, "get", _get2)

    with pytest.raises(f.DartBlocked):
        fetcher.fetch("00000002", "2026", "11013", "CFS")
    assert call2_count[0] == 1, (
        "인스턴스에 남은 스트릭 2 + 이번 1회 = 3 — 두 번째 대상은 «첫 시도»에서 "
        "바로 차단돼야 한다(지역변수였다면 3번째 시도까지 갔을 것)")
