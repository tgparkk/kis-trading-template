"""scripts/real_order_cancel_probe.py 가드·게이트 순수 함수 테스트 — KIS 호출 0."""
import json
from datetime import datetime

import pytest

from scripts import real_order_cancel_probe as p


# ── 주문가 = 기준가 x 0.75 호가 «내림» ────────────────────────────────────────
@pytest.mark.parametrize("base, expected", [
    (10_000, 7_500),
    (80_000, 60_000),
    (12_345, 9_250),      # 9,258.75 → 10원 단위 내림
    (1_333, 999),         # 999.75 → 1원 단위 내림
    (655_000, 491_000),   # 491,250 → 500원 단위 내림
    (0, 0),
])
def test_compute_order_price_floors_to_tick(base, expected):
    assert p.compute_order_price(base) == expected


def test_floor_to_tick_never_rounds_up_and_is_aligned():
    for base in range(500, 900_001, 997):
        raw = base * p.PRICE_RATIO
        price = p.compute_order_price(base)
        assert price <= raw
        assert price % p.tick_size(price) == 0
        assert raw - price < p.tick_size(raw)


# ── 시간창 08:30:00~08:50:00 ──────────────────────────────────────────────────
@pytest.mark.parametrize("hms, ok", [
    ((8, 29, 59), False), ((8, 30, 0), True), ((8, 45, 0), True), ((8, 50, 0), True),
    ((8, 50, 1), False), ((8, 58, 0), False), ((9, 0, 0), False), ((7, 30, 0), False),
])
def test_time_window(hms, ok):
    assert p.check_time_window(datetime(2026, 10, 6, *hms))[1] is ok


# ── 거래일 ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status, holiday, kis_closed, ok", [
    ("pre_market", False, None, True),
    ("pre_market", False, False, True),
    ("pre_market", False, True, False),   # KIS 캐시가 휴장이라 하면 거부
    ("holiday", True, None, False),
    ("weekend", False, None, False),
    ("market_open", False, None, False),
])
def test_trading_day(status, holiday, kis_closed, ok):
    assert p.check_trading_day(status, holiday, kis_closed)[1] is ok


# ── 가격 가드 ────────────────────────────────────────────────────────────────
def _failed(guards):
    return [name for name, ok, _ in guards if not ok]


def test_price_guards_pass_on_normal_plan():
    assert _failed(p.check_price_guards(7_500, 10_000, 10_000, 7_000)) == []


def test_price_guard_rejects_above_80pct_of_base():
    assert "주문가 ≤ 기준가 x 0.80" in _failed(p.check_price_guards(8_050, 10_000, 10_000, 7_000))


def test_price_guard_rejects_when_current_price_dropped():
    # 현재가(예상가)가 -22% 면 0.80 x 7,800 = 6,240 < 7,500 → 거부(체결 위험)
    assert "주문가 ≤ 현재가 x 0.80" in _failed(p.check_price_guards(7_500, 10_000, 7_800, 7_000))


def test_price_guard_rejects_below_lower_limit_or_missing_limit():
    assert "주문가 ≥ 하한가" in _failed(p.check_price_guards(6_900, 10_000, 10_000, 7_000))
    assert "하한가 > 0" in _failed(p.check_price_guards(7_500, 10_000, 10_000, 0))


def test_price_guard_rejects_misaligned_and_zero():
    assert "호가단위 정렬" in _failed(p.check_price_guards(7_501, 10_000, 10_000, 7_000))
    assert "기준가(전일종가) > 0" in _failed(p.check_price_guards(0, 0, 10_000, 7_000))


def test_qty_is_constant_one():
    assert p.QTY == 1


# ── 미체결 존재 거부 ─────────────────────────────────────────────────────────
def test_no_pending_guard():
    assert p.check_no_pending([])[1] is True
    assert p.check_no_pending(None)[1] is False                  # 조회 실패도 거부
    assert p.check_no_pending([{"odno": "0000000001"}])[1] is False


def test_instance_and_real_mode_guards():
    url = "https://openapi.koreainvestment.com:9443"
    assert _failed(p.check_instance("daytrading", True, url)) == []
    assert "인스턴스 = daytrading" in _failed(p.check_instance("default", True, url))
    assert "실전 도메인(openapivts 아님)" in _failed(
        p.check_instance("daytrading", True, "https://openapivts.koreainvestment.com:29443"))
    assert _failed(p.check_real_mode(True, False)) == []
    assert len(_failed(p.check_real_mode(True, True))) == 1
    assert len(_failed(p.check_real_mode(False, False))) == 1


def test_find_rows_normalizes_leading_zeros():
    rows = [{"odno": "0000012345"}, {"odno": "0000099999", "orgn_odno": "12345"}]
    assert len(p.find_rows(rows, "12345")) == 1
    assert len(p.find_rows(rows, "0000012345", keys=("odno", "orgn_odno"))) == 2
    assert p.find_rows(None, "1") == [] and p.find_rows(rows, "") == []


# ── HTTP 게이트 ──────────────────────────────────────────────────────────────
BUY = {"PDNO": "005930", "ORD_QTY": "1", "ORD_UNPR": "60000", "ORD_DVSN": "00"}
CANCEL = {"ORGN_ODNO": "0000012345", "RVSE_CNCL_DVSN_CD": "02", "QTY_ALL_ORD_YN": "Y"}


def _live_state():
    s = p.GateState(live=True)
    s.planned = dict(BUY)
    s.target_odno = "12345"
    return s


def test_gate_dry_run_blocks_every_order_post():
    s = p.GateState(live=False)
    s.planned, s.target_odno = dict(BUY), "12345"   # 설정돼 있어도 dry-run 은 막는다
    assert p.gate_decision(s, "POST", p.PATH_ORDER_CASH, p.TR_BUY, BUY)[0] is False
    assert p.gate_decision(s, "POST", p.PATH_ORDER_CASH, p.TR_SELL, BUY)[0] is False
    assert p.gate_decision(s, "POST", p.PATH_ORDER_RVSECNCL, p.TR_CANCEL, CANCEL)[0] is False
    assert p.gate_decision(s, "POST", p.PATH_HASHKEY, "", BUY)[0] is False
    assert p.gate_decision(s, "GET", "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl", "TTTC8036R", {})[0]
    assert p.gate_decision(s, "POST", p.PATH_TOKEN, "", {})[0] is True


def test_gate_live_allows_only_exact_planned_buy_once():
    s = _live_state()
    assert p.gate_decision(s, "POST", p.PATH_ORDER_CASH, p.TR_BUY, BUY)[0] is True
    for k, bad in (("ORD_QTY", "2"), ("ORD_UNPR", "60100"), ("PDNO", "000660"), ("ORD_DVSN", "01")):
        assert p.gate_decision(s, "POST", p.PATH_ORDER_CASH, p.TR_BUY, {**BUY, k: bad})[0] is False
    assert p.gate_decision(s, "POST", p.PATH_ORDER_CASH, p.TR_SELL, BUY)[0] is False
    s.buy_calls = 1
    assert p.gate_decision(s, "POST", p.PATH_ORDER_CASH, p.TR_BUY, BUY)[0] is False
    s2 = p.GateState(live=True)                     # 계획 미설정
    assert p.gate_decision(s2, "POST", p.PATH_ORDER_CASH, p.TR_BUY, BUY)[0] is False


def test_gate_live_cancel_only_own_order_full_cancel():
    s = _live_state()
    assert p.gate_decision(s, "POST", p.PATH_ORDER_RVSECNCL, p.TR_CANCEL, CANCEL)[0] is True
    assert p.gate_decision(s, "POST", p.PATH_ORDER_RVSECNCL, p.TR_CANCEL, {**CANCEL, "ORGN_ODNO": "777"})[0] is False
    assert p.gate_decision(s, "POST", p.PATH_ORDER_RVSECNCL, p.TR_CANCEL,
                           {**CANCEL, "RVSE_CNCL_DVSN_CD": "01"})[0] is False
    assert p.gate_decision(s, "POST", p.PATH_ORDER_RVSECNCL, p.TR_CANCEL, {**CANCEL, "QTY_ALL_ORD_YN": "N"})[0] is False
    s.target_odno = ""
    assert p.gate_decision(s, "POST", p.PATH_ORDER_RVSECNCL, p.TR_CANCEL, CANCEL)[0] is False
    assert p.gate_decision(_live_state(), "POST", "/uapi/other", "X", {})[0] is False


class _FakeResp:
    def __init__(self, body):
        self.status_code = 200
        self.headers = {"tr_cont": "D"}
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class _FakeRequests:
    exceptions = object()

    def __init__(self):
        self.sent = []

    def get(self, url, **kw):
        self.sent.append(("GET", url))
        return _FakeResp({"rt_cd": "0", "msg_cd": "OK", "msg1": "ok",
                          "output": [{"odno": "1", "CANO": "12345678", "memo": "acct 12345678 x"}]})

    def post(self, url, **kw):
        self.sent.append(("POST", url))
        return _FakeResp({"rt_cd": "0", "access_token": "SECRET-TOKEN"})


def test_http_gate_blocks_dry_run_order_without_network_and_masks(caplog):
    import logging
    fake = _FakeRequests()
    m = p.Masker()
    m.add("12345678")
    log = logging.getLogger("probe.test")
    gate = p.HttpGate(fake, p.GateState(live=False), "kis.example:9443", log, log, m)
    host = "https://kis.example:9443"

    r = gate.post(host + p.PATH_ORDER_CASH, headers={"tr_id": p.TR_BUY}, data=json.dumps(BUY))
    assert r.json()["msg_cd"] == "PROBE_BLOCKED" and fake.sent == []          # 실제 전송 0

    gate.get(host + "/uapi/x", headers={"tr_id": "TTTC8036R"}, params={"CANO": "12345678"})
    gate.post(host + p.PATH_TOKEN, headers={}, data=json.dumps({"appkey": "K", "appsecret": "S"}))
    assert [c["blocked"] for c in gate.calls] == [True, False, False]
    dumped = json.dumps(gate.calls, ensure_ascii=False)
    assert "12345678" not in dumped and "SECRET-TOKEN" not in dumped
    assert '"appkey": "***"' in dumped
    assert gate.last("TTTC8036R")["rt_cd"] == "0"


def test_masker_masks_keys_and_secret_substrings():
    m = p.Masker()
    m.add("ABCDEFGH", "", None, "xy")       # 4자 미만·빈 값은 무시
    out = m.obj({"Cano": "11112222", "nested": [{"msg": "key ABCDEFGH here", "inqr_ip_addr": "1.2.3.4"}]})
    assert out == {"Cano": "***", "nested": [{"msg": "key *** here", "inqr_ip_addr": "***"}]}


# ── 실행 위치·기대 기준가·NEW-B1 판정 ────────────────────────────────────────
def test_cwd_guard_rejects_live_tree_only():
    from pathlib import Path
    assert p.check_cwd(Path("D:/GIT/kis-trading-template"))[1] is False
    assert p.check_cwd(Path("D:/GIT/kis-trading-template/RoboTrader_template"))[1] is False
    assert p.check_cwd(Path("D:/tmp/kis-wt-real-cancel-probe/RoboTrader_template"))[1] is True
    assert p.check_cwd(Path("D:/GIT/kis-trading-template2"))[1] is True


def test_expect_base_guard_optional():
    assert p.check_expect_base(None, 276_000) is None
    assert p.check_expect_base(276_000, 276_000)[1] is True
    assert p.check_expect_base(276_000, 275_500)[1] is False


B1_MSG = "Cancel failed: Unknown error"


@pytest.mark.parametrize("c1, raw, remain, verdict", [
    ({"success": False, "message": B1_MSG}, {"rt_cd": "0"}, False, "재현"),
    ({"success": True, "message": "Order cancelled"}, {"rt_cd": "0"}, False, "비재현"),
    ({"success": False, "message": B1_MSG}, {"rt_cd": "0"}, True, "판정불가"),      # KIS 는 OK 인데 남음
    ({"success": False, "message": "Cancel API returned no response"}, {"rt_cd": "1"}, False, "판정불가"),
    ({"success": False, "message": "Order 1 not found in cancellable list"}, None, None, "판정불가"),
    (None, None, None, "판정불가"),
])
def test_judge_new_b1_three_way(c1, raw, remain, verdict):
    assert p.judge_new_b1(c1, raw, remain)[0] == verdict


# ── 게이트: 외부 호스트·다른 requests 경로 ───────────────────────────────────
def test_gate_blocks_external_hosts_and_other_request_paths():
    import logging
    fake = _FakeRequests()
    log = logging.getLogger("probe.test.ext")
    gate = p.HttpGate(fake, p.GateState(live=True), "kis.example:9443", log, log, p.Masker())
    r = gate.get("https://evil.example/x", headers={})
    assert r.json()["msg_cd"] == "PROBE_BLOCKED" and fake.sent == []
    gate.post("https://api.telegram.org/botTOKEN/sendMessage", json={"text": "x"})   # 장애 알림만 허용
    assert fake.sent == [("POST", "https://api.telegram.org/botTOKEN/sendMessage")]
    assert gate.request("PUT", "https://kis.example:9443/uapi/x", headers={}).json()["msg_cd"] == "PROBE_BLOCKED"
    with pytest.raises(AttributeError):
        gate.Session()
    assert gate.exceptions is fake.exceptions


def test_mask_filter_masks_exception_traceback():
    import io
    import logging
    m = p.Masker()
    m.add("SECRETVALUE9")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter("%(message)s"))
    h.addFilter(p._MaskFilter(m))
    lg = logging.getLogger("probe.test.maskexc")
    lg.handlers, lg.propagate = [h], False
    try:
        raise ValueError("boom SECRETVALUE9")
    except ValueError:
        lg.exception("ctx SECRETVALUE9")
    out = buf.getvalue()
    assert "SECRETVALUE9" not in out and "ValueError: boom ***" in out and "ctx ***" in out


# ── live 경로 시나리오: «진짜» KISBroker·kis_order_api·_url_fetch + 가짜 KIS HTTP(네트워크 0) ──────────
import io  # noqa: E402
import logging  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import requests as _requests  # noqa: E402

OD = "0000012345"
HOST = "kis.example:9443"
ROW = {"odno": OD, "orgn_odno": "", "pdno": "005930", "sll_buy_dvsn_cd": "02", "ord_qty": "1",
       "ord_unpr": "207000", "psbl_qty": "1", "krx_fwdg_ord_orgno": "91252", "ord_gno_brno": "91252"}
ORIG_CANCELLED = {"odno": OD, "orgn_odno": "", "pdno": "005930", "ord_qty": "1", "cncl_yn": "N",
                  "rmn_qty": "0", "cncl_cfrm_qty": "1", "tot_ccld_qty": "0"}
ORIG_LIVE = {**ORIG_CANCELLED, "rmn_qty": "1", "cncl_cfrm_qty": "0"}
CANCEL_ROW = {"odno": "0000012399", "orgn_odno": OD, "pdno": "005930", "ord_qty": "1", "cncl_yn": "Y",
              "rmn_qty": "0", "cncl_cfrm_qty": "0", "tot_ccld_qty": "0"}
CANCEL_OK = {"rt_cd": "0", "msg_cd": "APBK0013", "msg1": "주문 전송 완료 되었습니다.",
             "output": {"KRX_FWDG_ORD_ORGNO": "91252", "ODNO": "0000012399", "ORD_TMD": "083502"}}
CANCEL_REJ = {"rt_cd": "1", "msg_cd": "APBK0918", "msg1": "정정/취소할 수량이 없습니다.", "output": {}}


class _KisResp:
    def __init__(self, body):
        self.status_code = 200
        self.headers = {"tr_cont": "D"}
        self._b = body
        self.text = json.dumps(body, ensure_ascii=False)

    def json(self):
        return self._b


class _FakeKIS:
    """KIS 서버 흉내 — 미체결(TTTC8036R) 응답은 호출 순서대로 꺼낸다(cancel_order 내부 조회 포함)."""
    exceptions = _requests.exceptions

    def __init__(self, psbl_seq, cancel_bodies, daily_rows, interrupt_on_psbl=None):
        self.psbl, self.cancels, self.daily = list(psbl_seq), list(cancel_bodies), daily_rows
        self.interrupt_on_psbl, self.n_psbl, self.sent = interrupt_on_psbl, 0, []

    def get(self, url, **kw):
        tr = kw["headers"]["tr_id"]
        self.sent.append(tr)
        if tr == "TTTC8036R":
            self.n_psbl += 1
            if self.n_psbl == self.interrupt_on_psbl:
                raise KeyboardInterrupt
            return _KisResp({"rt_cd": "0", "msg_cd": "KIOK0000", "msg1": "ok", "output": self.psbl.pop(0),
                             "ctx_area_fk100": "", "ctx_area_nk100": ""})
        if tr == "TTTC0081R":
            return _KisResp({"rt_cd": "0", "msg_cd": "KIOK0000", "msg1": "ok", "output1": self.daily,
                             "output2": {}, "ctx_area_fk100": "", "ctx_area_nk100": ""})
        raise AssertionError(f"unexpected GET {tr}")

    def post(self, url, **kw):
        if url.endswith(p.PATH_HASHKEY):
            self.sent.append("hashkey")
            return _KisResp({"HASH": "h"})
        tr = kw["headers"]["tr_id"]
        self.sent.append(tr)
        if tr == p.TR_BUY:
            return _KisResp({"rt_cd": "0", "msg_cd": "APBK0013", "msg1": "주문 전송 완료 되었습니다.",
                             "output": {"KRX_FWDG_ORD_ORGNO": "91252", "ODNO": OD, "ORD_TMD": "083500"}})
        if tr == p.TR_CANCEL:
            return _KisResp(self.cancels.pop(0))
        raise AssertionError(f"unexpected POST {tr}")


@pytest.fixture
def run_live(monkeypatch):
    import api.circuit_breaker as cbm
    import api.kis_auth as ka
    from config.market_hours import KST
    from framework.broker import KISBroker

    monkeypatch.setattr(ka, "_TRENV", ka.KISEnv("app", "sec", "12345678", "01", "Bearer t", "https://" + HOST))
    monkeypatch.setattr(ka, "_autoReAuth", False)
    cb = SimpleNamespace(can_execute=lambda: True, record_success=lambda: None, record_failure=lambda: None,
                         record_blocked=lambda: None)
    monkeypatch.setattr(cbm, "get_circuit_breaker", lambda: cb)
    monkeypatch.setattr(p._time, "sleep", lambda s: None)

    def _run(fake, name):
        buf = io.StringIO()
        h = logging.StreamHandler(buf)
        h.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        log = logging.getLogger("probe.test.live." + name)
        log.handlers, log.propagate = [h], False
        log.setLevel(logging.INFO)
        state = p.GateState(live=True)
        gate = p.HttpGate(fake, state, HOST, log, log, p.Masker())
        monkeypatch.setattr(ka, "requests", gate)            # 봇 코드의 모든 HTTP 가 게이트 → 가짜 KIS
        broker = KISBroker()
        broker._connected = True

        def now():
            return KST.localize(datetime(2026, 10, 6, 8, 35, 0))

        try:
            rc = p._run_live(SimpleNamespace(code="005930"), broker, gate, state, log, p.Masker(), 207_000, now)
        except KeyboardInterrupt:
            rc = "interrupted"
        return rc, buf.getvalue(), fake

    return _run


def test_live_s1_b1_reproduced_and_verified(run_live):
    fake = _FakeKIS([[ROW], [ROW], []], [CANCEL_OK], [ORIG_CANCELLED, CANCEL_ROW])
    rc, out, _ = run_live(fake, "s1")
    assert rc == 0
    assert "NEW-B1 = 재현" in out and "CRITICAL" not in out
    assert fake.sent.count(p.TR_BUY) == 1 and fake.sent.count(p.TR_CANCEL) == 1


def test_live_s2_remains_after_two_cancels_is_critical(run_live):
    fake = _FakeKIS([[ROW]] * 5, [CANCEL_OK, CANCEL_OK], [ORIG_LIVE])
    rc, out, _ = run_live(fake, "s2")
    assert rc == 4 and "CRITICAL **🔴 HTS 에서 즉시 수동 취소" in out
    assert "NEW-B1 = 판정불가" in out and fake.sent.count(p.TR_CANCEL) == 2


def test_live_s3_first_cancel_b1_then_list_lag_second_rejected(run_live):
    # 1차 취소 rt_cd 0(B1 형태) · 목록 반영 지연으로 2차 취소 rt_cd 1 · 결국 0건 → «1차» 기준으로 재현
    fake = _FakeKIS([[ROW], [ROW], [ROW], [ROW], []], [CANCEL_OK, CANCEL_REJ], [ORIG_CANCELLED, CANCEL_ROW])
    rc, out, _ = run_live(fake, "s3")
    assert rc == 0 and "NEW-B1 = 재현" in out
    assert "2차 cancel_order 반환" in out


def test_live_s4_never_visible_is_unknown_and_critical(run_live):
    # 미체결 목록에 한 번도 안 보임 → cancel_order 는 취소 TR 을 안 보낸다 → 잔존 «미상»
    fake = _FakeKIS([[]] * 5, [], [ORIG_LIVE])
    rc, out, _ = run_live(fake, "s4")
    assert rc == 4 and p.TR_CANCEL not in fake.sent
    assert "잔존 미상" in out and "원주문 잔량>0" in out and "NEW-B1 = 판정불가" in out
    assert "재조회 잔존 0 ?" in out


def test_live_s5_daily_shows_remaining_qty_is_critical(run_live):
    fake = _FakeKIS([[ROW], [ROW], []], [CANCEL_OK], [ORIG_LIVE])
    rc, out, _ = run_live(fake, "s5")
    assert rc == 4 and "CRITICAL **🔴 당일조회 원주문 잔량>0" in out


def test_live_s6_interrupt_triggers_one_emergency_cancel(run_live):
    # 주문 직후 미체결 조회 중 Ctrl+C → 그 주문 전량 취소 1회 시도 → HTS 안내 → 예외 재전파
    fake = _FakeKIS([[ROW]], [CANCEL_OK], [], interrupt_on_psbl=1)
    rc, out, _ = run_live(fake, "s6")
    assert rc == "interrupted"
    assert fake.sent.count(p.TR_CANCEL) == 1 and "비상 취소 1회 시도" in out
    assert "HTS 에서 즉시 미체결 확인·수동 취소" in out
