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


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _Session:
    """호출 스크립트를 기록하는 가짜 세션."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


def _client(script):
    """🔴 세션을 «주입»한다. 대입(c.session = ...)으로는 안 된다 —
    리셋 복구가 세션을 새로 만들기 때문에 그 순간 진짜 requests.Session 이
    끼어들어 테스트가 실제 DART 로 호출을 날린다(2026-08-08 실측).
    factory 가 같은 가짜를 계속 돌려주므로 스크립트가 이어서 소비된다.
    sleep_fn 도 주입해 재시도 경로가 실제 지연을 건너뛰게 한다."""
    sess = _Session(script)
    c = dc.DartClient("KEY", min_interval=0.0, session_factory=lambda: sess,
                      sleep_fn=lambda s: None)
    return c


def test_quota_exceeded_raises_immediately():
    """status=020 은 즉시 중단이다. 조용히 빈 결과로 넘기면 안 된다."""
    c = _client([_Resp({"status": "020", "message": "한도초과"})])
    with pytest.raises(dc.DartQuotaExceeded):
        c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")


def test_no_data_status_is_returned_not_raised():
    """013(무자료)은 정상 반환이다 — 손실이 아니라 사실이다."""
    c = _client([_Resp({"status": "013", "message": "무자료"})])
    status, _, rows = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert status == "013"
    assert rows == []


def test_success_returns_rows_and_counts_status():
    c = _client([_Resp({"status": "000", "message": "정상",
                        "list": [{"account_nm": "자본총계"}]})])
    status, _, rows = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert status == "000"
    assert len(rows) == 1
    assert c.status_counts["000"] == 1
    assert c.calls == 1


def test_three_consecutive_connection_resets_raise_blocked():
    """연결 리셋 3연속 = IP 차단. '0건'과 반드시 구분한다."""
    import requests
    err = requests.exceptions.ConnectionError("reset")
    c = _client([err, err, err])
    with pytest.raises(dc.DartBlocked):
        c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert c.conn_resets == 3


def test_reset_then_success_recovers():
    """리셋이 3연속이 아니면 복구한다 — 과잉 중단하지 않는다."""
    import requests
    c = _client([
        requests.exceptions.ConnectionError("reset"),
        _Resp({"status": "000", "message": "정상", "list": []}),
    ])
    status, _, _ = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert status == "000"
    assert c.conn_resets == 1


def test_fs_div_is_passed_through():
    """CFS/OFS 구분이 요청에 실제로 실려야 한다."""
    c = _client([_Resp({"status": "000", "message": "", "list": []})])
    c.fnltt_all("00126380", "2022", dc.REPRT_FY, "OFS")
    assert c.session.calls[0]["fs_div"] == "OFS"


def test_session_is_recreated_after_reset():
    """🔴 복구 동작을 «고정»한다 — 세션 교체를 지워도 다른 테스트는 다 통과한다.

    오염된 커넥션 풀을 버리는 것이 리셋 복구의 핵심이고, 원본
    scripts/dart_mcap_common.py 가 20,241 호출로 실증한 동작이다.
    """
    import requests
    made = []

    def factory():
        s = _Session([
            requests.exceptions.ConnectionError("reset"),
            _Resp({"status": "000", "message": "", "list": []}),
        ] if not made else [_Resp({"status": "000", "message": "", "list": []})])
        made.append(s)
        return s

    c = dc.DartClient("KEY", min_interval=0.0, session_factory=factory)
    status, _, _ = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert status == "000"
    assert len(made) == 2, "리셋 뒤 세션이 새로 만들어져야 한다"


def test_db_conn_opens_readonly_session(monkeypatch):
    """🔴 하드 제약. set_session 줄을 지우면 이 테스트가 실패해야 한다.

    read-only 트랜잭션으로 쓰기를 원천 차단하는 것이 핵심 보호다.
    """
    call_log = []

    class FakeConn:
        def set_session(self, readonly=False, autocommit=False):
            call_log.append(("set_session", readonly, autocommit))

    class FakePsycopg2Module:
        @staticmethod
        def connect(**kwargs):
            call_log.append(("connect", kwargs))
            return FakeConn()

    fake_psycopg2 = FakePsycopg2Module()
    monkeypatch.setattr("psycopg2.connect", fake_psycopg2.connect)

    conn = dc.db_conn()
    assert len(call_log) == 2
    assert call_log[0][0] == "connect"
    assert call_log[1] == ("set_session", True, True), \
        f"readonly=True, autocommit=True 이어야 한다. 실제: {call_log[1]}"


def test_retries_exhausted_returns_http_fail():
    """200 아닌 응답 6회 후 HTTP_FAIL 을 반환한다.

    HTTP_FAIL 은 "000"(빈결과) 과 «구별되는» 값이어야 한다 —
    수집기가 다시 시도해야 할지를 판단해야 하기 때문이다.
    """
    # 모든 응답이 200 이 아님 (예: 503 Service Unavailable)
    c = _client([_Resp({"status": "000"}, status_code=503)] * 6)
    status, message, rows = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")

    assert status == "HTTP_FAIL", "6회 비-200 응답은 HTTP_FAIL"
    assert message == "retries exhausted"
    assert rows == []
    assert c.status_counts["HTTP_FAIL"] == 1
    assert c.http_errors == 6
    # 중요: "000" 과 "HTTP_FAIL" 이 다름
    assert "000" not in c.status_counts


def test_malformed_json_is_not_treated_as_empty_success():
    """JSON 파싱 실패 6회 후 HTTP_FAIL 을 반환한다.

    .json() 이 ValueError 를 내는 응답을 받으면 "000" 이 아니라
    "HTTP_FAIL" 이 나와야 한다 — 상태 불명인 것이 성공이 아니다.
    """
    class BadJsonResp:
        status_code = 200

        def json(self):
            raise ValueError("Invalid JSON")

    c = _client([BadJsonResp()] * 6)
    status, message, rows = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")

    assert status == "HTTP_FAIL", "JSON 파싱 실패 6회는 HTTP_FAIL"
    assert message == "retries exhausted"
    assert rows == []
    assert c.status_counts["HTTP_FAIL"] == 1
    assert c.http_errors == 6


def test_project_root_points_at_repo_package_root():
    """🔴 조용히 틀리는 자리다. 틀리면 OUT_DIR 도 .env 경로도 함께 어긋난다."""
    assert os.path.basename(dc.PROJECT_ROOT) == "RoboTrader_template"
    assert os.path.isdir(os.path.join(dc.PROJECT_ROOT, "scripts"))
    assert dc.OUT_DIR.endswith(os.path.join("RoboTrader_template",
                                            "scratchpad", "fund_pit"))
