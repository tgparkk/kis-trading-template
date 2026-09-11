"""외국인수급 fetcher 실패 경보의 «정직화» 회귀 테스트 (2026-09-11).

두 가지를 못박는다.

① **리다이렉트를 따라가지 않는다** — `allow_redirects=True`(requests 기본)면
   302 가 200 으로 세탁돼 `status_code != 200` 가드를 못 지나가고, 대신
   「표를 못 찾음」으로 둔갑한다. 원인을 못 보는 게 아니라 **틀리게 본다**.
   그래서 `allow_redirects=False` 를 호출 인자 수준에서 단언한다.

② **로그 억제** — 유니버스 2,796 종목을 도는 EOD 수집기에서 실패 사유가
   종목당 한 줄씩 나오면 WARNING 2,796 줄이 되고, 그건 경보가 아니라 소음이다.
   ⇒ 사유 종류당 **첫 1회만 WARNING, 이후는 DEBUG**.
   ⚠️ 「억제」는 **세지 않는다」가 아니다** — 이후 줄도 DEBUG 로 남아야 하고,
   첫 사유는 `get_first_fail_reason()` 으로 요약에 실려 나가야 한다.
"""
import logging

import pytest

from collectors import foreign_flow_fetcher as ff


class _Resp:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class _Session:
    """`requests.Session` 목 — get 호출 인자를 전부 기록한다."""

    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._resp


@pytest.fixture(autouse=True)
def _reset():
    ff.reset_fail_suppression()
    yield
    ff.reset_fail_suppression()


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING]


def _debugs(caplog):
    return [r for r in caplog.records if r.levelno == logging.DEBUG]


def test_redirect_is_not_followed():
    """302 를 따라가면 원인이 사라진다 — 따라가지 않는다."""
    sess = _Session(_Resp(302, headers={"Location": "https://finance.naver.com/"}))
    ff.fetch_foreign_naver("005930", max_pages=2, session=sess)

    assert sess.calls, "get 이 호출되지 않았다"
    _, kwargs = sess.calls[0]
    assert kwargs.get("allow_redirects") is False


def test_redirect_yields_zero_rows_and_logs_location_once(caplog):
    """302 → rows 0 · WARNING 1회(Location 포함) · 두 번째 종목은 DEBUG."""
    caplog.set_level(logging.DEBUG, logger=ff.logger.name)
    sess = _Session(_Resp(302, headers={"Location": "https://m.stock.naver.com/"}))

    df1 = ff.fetch_foreign_naver("005930", max_pages=2, session=sess)
    assert df1.empty

    warns = _warnings(caplog)
    assert len(warns) == 1, [r.getMessage() for r in warns]
    assert "302" in warns[0].getMessage()
    assert "m.stock.naver.com" in warns[0].getMessage(), warns[0].getMessage()

    caplog.clear()
    df2 = ff.fetch_foreign_naver("000660", max_pages=2, session=sess)
    assert df2.empty
    assert _warnings(caplog) == [], [r.getMessage() for r in _warnings(caplog)]
    assert len(_debugs(caplog)) >= 1, "억제가 «침묵»이 되면 안 된다 — DEBUG 로는 남아야 한다"


def test_parse_failure_is_suppressed_the_same_way(caplog):
    """200 인데 표가 없다 — 같은 억제 규약(첫 1회 WARNING, 이후 DEBUG)."""
    caplog.set_level(logging.DEBUG, logger=ff.logger.name)
    sess = _Session(_Resp(200, text="<html><body>no tables here</body></html>"))

    assert ff.fetch_foreign_naver("005930", max_pages=2, session=sess).empty
    assert len(_warnings(caplog)) == 1, [r.getMessage() for r in _warnings(caplog)]

    caplog.clear()
    assert ff.fetch_foreign_naver("000660", max_pages=2, session=sess).empty
    assert _warnings(caplog) == []
    assert len(_debugs(caplog)) >= 1


def test_first_fail_reason_is_exposed_for_the_eod_summary():
    """첫 실패 사유가 밖으로 나가야 EOD 요약이 「왜」를 말할 수 있다."""
    assert ff.get_first_fail_reason() is None

    sess = _Session(_Resp(302, headers={"Location": "https://x/"}))
    ff.fetch_foreign_naver("005930", max_pages=2, session=sess)

    reason = ff.get_first_fail_reason()
    assert reason and "302" in reason

    # 두 번째 실패가 첫 사유를 덮어쓰면 안 된다(원인 추적은 «처음»이 중요하다).
    ff.fetch_foreign_naver("000660", max_pages=2, session=_Session(_Resp(500)))
    assert ff.get_first_fail_reason() == reason
