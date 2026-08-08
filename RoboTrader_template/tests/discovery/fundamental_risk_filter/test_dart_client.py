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
    factory 가 같은 가짜를 계속 돌려주므로 스크립트가 이어서 소비된다."""
    sess = _Session(script)
    c = dc.DartClient("KEY", min_interval=0.0, session_factory=lambda: sess)
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


def test_project_root_points_at_repo_package_root():
    """🔴 조용히 틀리는 자리다. 틀리면 OUT_DIR 도 .env 경로도 함께 어긋난다."""
    assert os.path.basename(dc.PROJECT_ROOT) == "RoboTrader_template"
    assert os.path.isdir(os.path.join(dc.PROJECT_ROOT, "scripts"))
    assert dc.OUT_DIR.endswith(os.path.join("RoboTrader_template",
                                            "scratchpad", "fund_pit"))
