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


# ── 시간창 08:30:00~08:58:00 ──────────────────────────────────────────────────
@pytest.mark.parametrize("hms, ok", [
    ((8, 29, 59), False), ((8, 30, 0), True), ((8, 45, 0), True),
    ((8, 58, 0), True), ((8, 58, 1), False), ((9, 0, 0), False), ((7, 30, 0), False),
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
