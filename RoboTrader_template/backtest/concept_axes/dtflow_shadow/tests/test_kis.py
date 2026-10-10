from datetime import date, datetime

import pytest

from backtest.concept_axes.dtflow_shadow import kis as K


def test_read_token_ok_and_expiring(tmp_path):
    p = tmp_path / "token_info.json"
    p.write_text("token: abc\nvalid-date: 2026-10-12 15:35:08\n", encoding="utf-8")
    assert K.read_token(p, datetime(2026, 10, 12, 7, 52)) == "abc"
    with pytest.raises(K.TokenUnavailable):
        K.read_token(p, datetime(2026, 10, 12, 15, 20))


def test_read_token_expiring_raises(tmp_path):
    p = tmp_path / "t.json"
    p.write_text("token: abc\n", encoding="utf-8")
    with pytest.raises(K.TokenUnavailable):
        K.read_token(p, datetime(2026, 10, 12, 7, 52))
    with pytest.raises(K.TokenUnavailable):
        K.read_token(tmp_path / "none.json", datetime(2026, 10, 12, 7, 52))


def test_params_for_each_kind():
    D, T = date(2026, 10, 8), date(2026, 10, 12)
    assert K.params_for("investor", "005930", D, T) == {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"}
    assert K.params_for("credit", "005930", D, T)["FID_COND_SCR_DIV_CODE"] == "20476"
    sh = K.params_for("short", "005930", D, T)
    assert sh["FID_INPUT_DATE_2"] == "20261008" and sh["FID_INPUT_DATE_1"] == "20260918"


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


class _Sess:
    def __init__(self, seq):
        self.seq, self.calls = list(seq), []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, headers, params))
        return self.seq.pop(0)


def test_client_headers_throttle_and_retry_201():
    s = _Sess([_Resp(200, {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과"}),
               _Resp(200, {"rt_cd": "0", "output": []})])
    slept = []
    c = K.Client("https://h", "tok", "ak", "as", session=s, sleep=slept.append, clock=lambda: 0.0)
    body, at = c.get("investor", {"FID_INPUT_ISCD": "1"})
    assert body["rt_cd"] == "0" and c.calls == 2 and 1.5 in slept
    url, h, _ = s.calls[0]
    assert url.endswith("/inquire-investor") and h["tr_id"] == "FHKST01010900" and h["authorization"] == "Bearer tok"
    assert h["custtype"] == "P"


def test_client_token_expired_raises_no_reissue():
    s = _Sess([_Resp(200, {"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다"})])
    c = K.Client("https://h", "tok", "ak", "as", session=s, sleep=lambda x: None, clock=lambda: 0.0)
    with pytest.raises(K.TokenUnavailable):
        c.get("credit", {})
    assert all("/oauth2" not in u for u, _, _ in s.calls)


def test_read_kis_conf_percent_is_literal(tmp_path):
    p = tmp_path / "key.ini"
    p.write_text('[KIS]\nKIS_BASE_URL = "https://h"\nKIS_APP_KEY = ak\nKIS_APP_SECRET = s%cr%(et)s\n', encoding="utf-8")
    conf = K.read_kis_conf(p)
    assert conf == {"base_url": "https://h", "appkey": "ak", "appsecret": "s%cr%(et)s"}
