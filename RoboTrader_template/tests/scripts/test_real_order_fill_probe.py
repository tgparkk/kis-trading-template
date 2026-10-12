"""scripts/real_order_fill_probe.py — 순수 함수·게이트 + «진짜» KISBroker·kis_*_api·_url_fetch 위에 가짜 KIS 거래소(네트워크 0)."""
import io
import json
import logging
from collections import Counter
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests as _requests

from scripts import real_order_fill_probe as p

CODE = "099990"
HOST = "kis.example:9443"
B_OD, S_OD, C_OD = "0000011111", "0000022222", "0000033333"
SECRETS = ("87654321", "APPKEY-SECRET1", "APPSECRET-XYZ9", "TOKEN-ABCDEF")
ORDER_TRS = ("TTTC0012U", "TTTC0011U", "TTTC0013U", "hashkey")


# ── 순수 함수 ────────────────────────────────────────────────────────────────
def test_num_and_avg_state_keep_empty_and_zero_distinct():
    assert p.num("1,234") == 1234.0 and p.num("") is None and p.num(None) is None and p.num("x") is None
    assert p.avg_state(None) == "행 없음"
    assert p.avg_state({}) == "필드 없음"
    assert p.avg_state({"avg_prvs": ""}) == "빈값"
    assert p.avg_state({"avg_prvs": " "}) == "빈값"
    assert p.avg_state({"avg_prvs": "0"}) == "0"
    assert p.avg_state({"avg_prvs": "0.0000"}) == "0"
    assert p.avg_state({"avg_prvs": "9980"}) == "값"


def test_implied_price_and_fill_price_fallback():
    row = {"tot_ccld_qty": "1", "tot_ccld_amt": "9980", "avg_prvs": ""}
    assert p.implied_price(row) == 9980.0
    assert p.fill_price(row) == (9980.0, "tot_ccld_amt/tot_ccld_qty")
    assert p.fill_price({**row, "avg_prvs": "9975"}) == (9975.0, "avg_prvs")
    assert p.implied_price({"tot_ccld_qty": "0", "tot_ccld_amt": "0"}) is None
    assert p.is_filled({"tot_ccld_qty": "1"}) is True and p.is_filled({"tot_ccld_qty": "0"}) is False
    assert p.is_filled({"tot_ccld_qty": ""}) is None and p.is_filled(None) is None


@pytest.mark.parametrize("avg, price, code", [
    ("", 0, "P2-14"),          # 시장가 매도(Order.price=0) + avg_prvs 빈값 → 봇은 영원히 보류
    ("0", 0, "P2-14"),         # 문자열 '0' 도 같은 덫
    ("9980", 0, "FILLED"),
    ("", 9990, "FILLED"),      # 지정가 매수는 주문가로 대체
])
def test_bot_view_emulates_order_monitor_p2_14(avg, price, code):
    st = {"odno": S_OD, "tot_ccld_qty": "1", "rmn_qty": "0", "cncl_yn": "N", "ord_qty": "1", "avg_prvs": avg}
    v = p.bot_view(st, 1, price)
    assert v["code"] == code
    if code == "FILLED":
        assert v["price"] == (9980.0 if avg else 9990.0)


def test_bot_view_other_states_and_get_order_status_emulation():
    assert p.bot_view({"tot_ccld_qty": "0"}, 1, 0)["code"] == "PENDING"     # 8036R 행(rmn_qty 없음)
    assert p.bot_view({"cncl_yn": "Y"}, 1, 0)["code"] == "CANCELLED"
    assert p.bot_view(None, 1, 0)["code"] == "NONE"
    pend, daily = [{"odno": B_OD, "psbl_qty": "1"}], [{"odno": B_OD, "tot_ccld_qty": "1"}]
    assert p.emulate_get_order_status(pend, daily, B_OD)["_status"] == "pending"
    assert p.emulate_get_order_status([], daily, B_OD)["_status"] == "executed"
    assert p.emulate_get_order_status(None, None, B_OD)["status_unknown"] is True
    assert p.emulate_get_order_status([], daily, "11111")["_status"] == "unknown"     # 봇은 문자열 완전일치


def _poll(t, avg, filled=True):
    row = {"tot_ccld_qty": "1" if filled else "0", "avg_prvs": avg, "tot_ccld_amt": "9980" if filled else "0"}
    return {"t": t, "daily_row": row}


def test_avg_rule_variants():
    assert "첫 조회(+1.0s)부터" in p.avg_rule([_poll(1.0, "9980")])[0]
    msg, first = p.avg_rule([_poll(1.0, "0", False), _poll(2.0, ""), _poll(3.0, ""), _poll(4.5, "9980")])
    assert "체결 뒤 2회 빈값" in msg and first == 4.5
    assert "끝까지 안 채워짐" in p.avg_rule([_poll(1.0, "0"), _poll(2.0, "0")])[0]
    assert "판정 불가" in p.avg_rule([_poll(1.0, "0", False)])[0]


@pytest.mark.parametrize("hms, ok", [
    ((9, 29, 59), False), ((9, 30, 0), True), ((12, 0, 0), True), ((14, 50, 0), True),
    ((14, 50, 1), False), ((15, 10, 0), False), ((8, 50, 0), False),
])
def test_time_window(hms, ok):
    assert p.check_time_window(datetime(2026, 10, 8, *hms))[1] is ok


@pytest.mark.parametrize("status, holiday, kis_closed, can, ok", [
    ("market_open", False, None, True, True),
    ("market_open", False, True, True, False),
    ("pre_market", False, None, True, False),
    ("market_open", True, None, True, False),
    ("market_open", False, None, False, False),
])
def test_trading_day_open(status, holiday, kis_closed, can, ok):
    assert p.check_trading_day_open(status, holiday, kis_closed, can)[1] is ok


def _q(**kw):
    q = {"stck_prpr": "9990", "stck_mxpr": "12980", "stck_llam": "7000", "acml_tr_pbmn": "50000000000",
         "iscd_stat_cls_code": "55", "temp_stop_yn": "N", "vi_cls_code": "N", "mang_issu_cls_code": "N",
         "sltr_yn": "N", "mrkt_warn_cls_code": "00", "short_over_yn": "N", "invt_caful_yn": "N", "ssts_yn": "Y"}
    q.update(kw)
    return q


def _failed(guards):
    return [n for n, ok, _ in guards if not ok]


def test_check_quote_pass_and_each_failure():
    assert _failed(p.check_quote(_q(), 30_000)) == []
    assert "현재가 ≤ --max-price" in _failed(p.check_quote(_q(stck_prpr="31000", stck_mxpr="40000"), 30_000))
    # 15,010 은 현행 KRX 호가(10원)엔 맞지만 봇 호가표(50원)엔 안 맞는다 → 봇이 가격을 고쳐 게이트와 어긋나므로 거부
    tick = "주문가(=현재가)가 봇 호가표에 정렬(봇이 가격을 고치지 않음)"
    assert tick in _failed(p.check_quote(_q(stck_prpr="15010", stck_mxpr="19500", stck_llam="10500"), 30_000))
    assert "상·하한가에서 5% 이상 떨어짐" in _failed(p.check_quote(_q(stck_prpr="12900"), 30_000))
    assert "누적 거래대금 ≥ 10억(유동성)" in _failed(p.check_quote(_q(acml_tr_pbmn="900000000"), 30_000))
    for bad in (dict(vi_cls_code="Y"), dict(vi_cls_code=""), dict(iscd_stat_cls_code="58"), dict(temp_stop_yn="Y"),
                dict(mang_issu_cls_code="Y"), dict(sltr_yn="Y"), dict(mrkt_warn_cls_code="02"),
                dict(short_over_yn="Y"), dict(invt_caful_yn="Y"),
                dict(mang_issu_cls_code="", sltr_yn="", invt_caful_yn="", ssts_yn="")):
        assert any(n.startswith("이상 표식 없음") for n in _failed(p.check_quote(_q(**bad), 30_000))), bad
    assert "현재가 > 0" in _failed(p.check_quote({}, 30_000))


def test_cash_and_holdings_guards():
    assert p.check_cash(5_000_000, 5_000_000, 9_990)[1] is True
    assert p.check_cash(10_000, 5_000_000, 9_990)[1] is False         # 9,990 x 1.01 = 10,089.9
    assert p.check_cash(None, 5_000_000, 9_990)[1] is False
    assert p.check_cash(5_000_000, None, 9_990)[1] is False
    assert p.check_no_holdings({})[1] is True
    assert p.check_no_holdings({"005930": 0})[1] is True
    assert p.check_no_holdings({"005930": 3})[1] is False
    assert p.check_no_holdings(None)[1] is False


VENV = "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe"


def test_real_instance_off_guard():
    paper = [{"pid": 200, "ppid": 100, "exe": "C:/Python311/python.exe", "inst_dir": None},
             {"pid": 100, "ppid": 50, "exe": VENV, "inst_dir": None}]
    assert p.check_real_instance_off([], [], None, VENV)[1] is True
    assert p.check_real_instance_off([], paper, 200, VENV)[1] is True           # 페이퍼 봇(자식+런처)은 제외
    assert p.check_real_instance_off(["x/robotrader_daytrading.pid"], [], None, VENV)[1] is False
    assert p.check_real_instance_off([], None, None, VENV)[1] is False           # 조회 실패도 거부
    real = [{"pid": 300, "ppid": 1, "exe": VENV, "inst_dir": "D:/GIT/x/instances/daytrading"}]
    assert p.check_real_instance_off([], real, 200, VENV)[1] is False
    paper_env = [{"pid": 200, "ppid": 100, "exe": "C:/Python311/python.exe", "inst_dir": ""}]
    assert p.check_real_instance_off([], paper_env, None, VENV)[1] is True       # 환경을 읽었고 daytrading 아님
    unknown = paper + [{"pid": 400, "ppid": 1, "exe": VENV, "inst_dir": None}]
    assert p.check_real_instance_off([], unknown, 200, VENV)[1] is False         # 환경 못 읽은 다른 venv main.py


# ── HTTP 게이트 결정 ─────────────────────────────────────────────────────────
BUY = {"PDNO": CODE, "ORD_QTY": "1", "ORD_UNPR": "9990", "ORD_DVSN": "00"}
SELL = {"PDNO": CODE, "ORD_QTY": "1", "ORD_UNPR": "0", "ORD_DVSN": "01"}
CANCEL = {"ORGN_ODNO": B_OD, "RVSE_CNCL_DVSN_CD": "02", "QTY_ALL_ORD_YN": "Y"}


def _st(live=True):
    s = p.FillGateState(live)
    s.planned_buy, s.planned_sell, s.target_odno = dict(BUY), dict(SELL), B_OD
    return s


def _allowed(s, path, tr, params):
    return p.fill_gate_decision(s, "POST", path, tr, params)[0]


def test_gate_dry_run_blocks_every_order_post():
    s = _st(live=False)
    cp = p.cp
    for path, tr, prm in ((cp.PATH_ORDER_CASH, cp.TR_BUY, BUY), (cp.PATH_ORDER_CASH, cp.TR_SELL, SELL),
                          (cp.PATH_ORDER_RVSECNCL, cp.TR_CANCEL, CANCEL), (cp.PATH_HASHKEY, cp.TR_SELL, SELL)):
        assert _allowed(s, path, tr, prm) is False
    assert p.fill_gate_decision(s, "GET", "/uapi/x", "TTTC0081R", {})[0] is True
    assert _allowed(s, cp.PATH_TOKEN, "", {}) is True


def test_gate_live_buy_once_and_market_sell_once_exact():
    cp = p.cp
    s = _st()
    assert _allowed(s, cp.PATH_ORDER_CASH, cp.TR_BUY, BUY) and _allowed(s, cp.PATH_ORDER_CASH, cp.TR_SELL, SELL)
    for k, bad in (("ORD_QTY", "2"), ("ORD_UNPR", "10000"), ("PDNO", "000660"), ("ORD_DVSN", "01")):
        assert not _allowed(s, cp.PATH_ORDER_CASH, cp.TR_BUY, {**BUY, k: bad})
    for k, bad in (("ORD_QTY", "2"), ("ORD_UNPR", "9990"), ("PDNO", "000660"), ("ORD_DVSN", "00")):
        assert not _allowed(s, cp.PATH_ORDER_CASH, cp.TR_SELL, {**SELL, k: bad})
    s.buy_calls, s.sell_calls = 1, 1                       # 재전송·이중 매도 차단
    assert not _allowed(s, cp.PATH_ORDER_CASH, cp.TR_BUY, BUY)
    assert not _allowed(s, cp.PATH_ORDER_CASH, cp.TR_SELL, SELL)
    s2 = p.FillGateState(True)                             # 계획 미설정
    assert not _allowed(s2, cp.PATH_ORDER_CASH, cp.TR_SELL, SELL)
    assert not _allowed(s, cp.PATH_ORDER_CASH, "TTTC0802U", BUY)


def test_gate_cancel_only_own_buy_full_cancel():
    cp = p.cp
    s = _st()
    assert _allowed(s, cp.PATH_ORDER_RVSECNCL, cp.TR_CANCEL, CANCEL)
    assert not _allowed(s, cp.PATH_ORDER_RVSECNCL, cp.TR_CANCEL, {**CANCEL, "ORGN_ODNO": S_OD})   # 매도 취소 금지
    assert not _allowed(s, cp.PATH_ORDER_RVSECNCL, cp.TR_CANCEL, {**CANCEL, "RVSE_CNCL_DVSN_CD": "01"})
    assert not _allowed(s, cp.PATH_ORDER_RVSECNCL, cp.TR_CANCEL, {**CANCEL, "QTY_ALL_ORD_YN": "N"})
    s.cancel_calls = p.MAX_CANCEL_HTTP
    assert not _allowed(s, cp.PATH_ORDER_RVSECNCL, cp.TR_CANCEL, CANCEL)
    assert not _allowed(_st(), "/uapi/other", "X", {})


# ── 가짜 KIS 거래소 ───────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, body):
        self.status_code = 200
        self.headers = {"tr_cont": "D"}
        self._b = body
        self.text = json.dumps(body, ensure_ascii=False)

    def json(self):
        return self._b


def _ok(**kw):
    return {"rt_cd": "0", "msg_cd": "KIOK0000", "msg1": "정상처리 되었습니다.", **kw}


REJ = {"rt_cd": "1", "msg_cd": "APBK0918", "msg1": "정정/취소할 수량이 없습니다."}


def _drow(odno, side, filled, avg, amt, rmn, unpr, name, orgn="", cncl="N", cnc="0", rjct="0"):
    return {"ord_dt": "20261008", "ord_gno_brno": "91252", "odno": odno, "orgn_odno": orgn, "ord_dvsn_name": name,
            "sll_buy_dvsn_cd": side, "pdno": CODE, "prdt_name": "테스트종목", "ord_qty": "1", "ord_unpr": unpr,
            "ord_tmd": "100001", "tot_ccld_qty": filled, "avg_prvs": avg, "cncl_yn": cncl, "tot_ccld_amt": amt,
            "rmn_qty": rmn, "rjct_qty": rjct, "cncl_cfrm_qty": cnc, "excg_dvsn_cd": "02",
            "inqr_ip_addr": "10.1.2.3", "ctac_tlno": "01012345678"}


class FakeExchange:
    """봇 함수 경로(KISBroker → kis_*_api → _url_fetch → 게이트) 끝의 KIS 서버 흉내. 체결은 0081R 호출마다 진행."""
    exceptions = _requests.exceptions

    def __init__(self, price="9990", buy_fill_at=1, sell_fill_at=1, sell_avg_seq=("9980",), race_fill_on_cancel=False,
                 extra_holdings=(), extra_pending=(), quote_over=None, price_seq=None, interrupt=None,
                 interrupt_after_sell=False, sell_reject=False, balance_fail_from=None, cancel_mode="confirm",
                 unconf_rmn="1", late_fill_after=None, drop_rmn=False, pending_fail_after_cancel=False,
                 daily_fail_after_cancel=False, buy_timeout=False, buy_reject=False, pending_after_sell=False,
                 vi_after_buy=False, hold_lag=0, exchange_reject=False):
        # cancel_mode: "confirm" = 취소 확정(원주문 cncl_cfrm_qty 1) · "unconfirmed" = 취소 접수만(8036R 에선 사라짐 ·
        #   0081R 원주문 체결 0·잔량 unconf_rmn · 취소 행 cncl_yn Y·확인 0) · late_fill_after = 취소 뒤 N 번째 0081R 에
        #   «사실은 체결됐었다»가 반영(보유 1) · 응답 유실 = buy_timeout(매수 POST 타임아웃 · 접수 안 됨)
        #   "measured" = 10-08 §4-B 실측형 취소(8036R 에서 사라짐 · 원·취소 행 모두 cncl_yn '' · cncl_cfrm_qty '0')
        #   exchange_reject = 접수(ODNO) 뒤 거래소 거부(0081R 원주문 체결 0 · 잔량 0 · rjct_qty 1 · 취소 불가)
        self.exchange_reject = exchange_reject
        self.cancel_mode, self.unconf_rmn = cancel_mode, unconf_rmn
        self.late_fill_after, self.drop_rmn = late_fill_after, drop_rmn
        self.pending_fail_after_cancel = pending_fail_after_cancel
        self.daily_fail_after_cancel = daily_fail_after_cancel
        self.buy_timeout, self.buy_reject, self.pending_after_sell = buy_timeout, buy_reject, pending_after_sell
        self.vi_after_buy, self.hold_lag = vi_after_buy, hold_lag
        self.cancel_posted, self.reads_after_cancel = False, 0
        self.price, self.price_seq, self.quote_over = price, list(price_seq or []), quote_over or {}
        self.buy_fill_at, self.sell_fill_at, self.sell_avg_seq = buy_fill_at, sell_fill_at, list(sell_avg_seq)
        self.race, self.sell_reject, self.balance_fail_from = race_fill_on_cancel, sell_reject, balance_fail_from
        self.extra_holdings, self.extra_pending = list(extra_holdings), list(extra_pending)
        self.interrupt, self.interrupt_after_sell, self._ia_done = interrupt, interrupt_after_sell, False
        self.buy = self.sell = None
        self.held = 0
        self.sent, self.posts, self.calls = [], [], Counter()

    def count(self, tr):
        return sum(1 for t, _ in self.posts if t == tr)

    def _fill_buy(self):
        self.buy["filled"] = True
        self.held += 1

    def _advance(self):
        b, s = self.buy, self.sell
        if b and b.get("cancel_pending") and not b["filled"]:
            self.reads_after_cancel += 1
            if self.late_fill_after is not None and self.reads_after_cancel >= self.late_fill_after:
                self._fill_buy()
        elif b and not b["filled"] and not b["cancelled"] and not b.get("rejected"):
            b["age"] += 1
            if self.buy_fill_at is not None and b["age"] >= self.buy_fill_at:
                self._fill_buy()
        if s and s["filled"]:
            s["post"] += 1
        elif s:
            s["age"] += 1
            if self.sell_fill_at is not None and s["age"] >= self.sell_fill_at:
                s["filled"] = True
                self.held -= 1

    def _quote(self):
        n = self.calls["FHKST01010100"]
        price = self.price_seq[min(n, len(self.price_seq)) - 1] if self.price_seq else self.price
        q = _q(stck_prpr=price, stck_mxpr=str(int(int(price) * 1.3)), stck_llam=str(int(int(price) * 0.7)),
               hts_kor_isnm="테스트종목", stck_sdpr=price)
        q.update(self.quote_over)
        if self.vi_after_buy and self.buy:
            q["vi_cls_code"] = "Y"
        return q

    def _daily(self):
        rows = [_drow("0000000501", "02", "1", "9900", "9900", "0", "9900", "지정가"),    # 오늘 앞서 한 왕복(스냅샷)
                _drow("0000000502", "01", "1", "9910", "9910", "0", "0", "시장가")]
        b, s = self.buy, self.sell
        if b:
            if b.get("rejected"):
                rows.append(_drow(B_OD, "02", "0", "0", "0", "0", self.price, "지정가", rjct="1"))
            elif b["filled"]:
                rows.append(_drow(B_OD, "02", "1", self.price, self.price, "0", self.price, "지정가"))
            elif b["cancelled"]:
                measured = self.cancel_mode == "measured"
                orig = _drow(B_OD, "02", "0", "0", "0", "0", self.price, "지정가",
                             cncl="" if measured else "N", cnc="0" if measured else "1")
                if self.drop_rmn:
                    orig.pop("rmn_qty")
                rows.append(orig)
                rows.append(_drow(C_OD, "02", "0", "0", "0", "0", "0", "지정가", orgn=B_OD,
                                  cncl="" if measured else "Y"))
            elif b.get("cancel_pending"):
                rows.append(_drow(B_OD, "02", "0", "0", "0", self.unconf_rmn, self.price, "지정가"))
                rows.append(_drow(C_OD, "02", "0", "0", "0", "0", "0", "지정가", orgn=B_OD, cncl="Y", cnc="0"))
            else:
                rows.append(_drow(B_OD, "02", "0", "0", "0", "1", self.price, "지정가"))
        if s:
            if s["filled"]:
                avg = self.sell_avg_seq[min(s["post"], len(self.sell_avg_seq) - 1)]
                rows.append(_drow(S_OD, "01", "1", avg, "9980", "0", "0", "시장가"))
            else:
                rows.append(_drow(S_OD, "01", "0", "0", "0", "1", "0", "시장가"))
        return rows

    def _pending(self):
        rows = list(self.extra_pending)
        if self.pending_after_sell and self.sell and self.sell["filled"]:
            rows.append({"odno": "0000099999", "orgn_odno": "", "pdno": "005930", "sll_buy_dvsn_cd": "02",
                         "ord_qty": "1", "ord_unpr": "1000", "psbl_qty": "1"})
        for o, od, side, unpr in ((self.buy, B_OD, "02", self.price), (self.sell, S_OD, "01", "0")):
            if o and not o["filled"] and not o.get("cancelled") and not o.get("cancel_pending") \
                    and not o.get("rejected"):
                rows.append({"ord_gno_brno": "91252", "odno": od, "orgn_odno": "", "pdno": CODE, "sll_buy_dvsn_cd": side,
                             "ord_qty": "1", "ord_unpr": unpr, "psbl_qty": "1", "tot_ccld_qty": "0",
                             "tot_ccld_amt": "0", "krx_fwdg_ord_orgno": "91252", "ord_tmd": "100001"})
        return rows

    def _holdings(self):
        rows = list(self.extra_holdings)
        if self.buy and self.buy["filled"] and self.hold_lag > 0:
            self.hold_lag -= 1                                   # 체결 뒤 잔고 반영 지연
            return rows
        if self.buy and self.buy["filled"]:
            rows.append({"pdno": CODE, "prdt_name": "테스트종목", "hldg_qty": str(self.held),
                         "ord_psbl_qty": str(self.held), "pchs_avg_pric": self.price, "prpr": self.price,
                         "evlu_amt": "0", "evlu_pfls_amt": "0", "evlu_pfls_rt": "0"})
        return rows

    def _maybe_interrupt(self, tr):
        if self.interrupt and self.interrupt == (tr, self.calls[tr]):
            raise KeyboardInterrupt
        if self.interrupt_after_sell and self.sell is not None and tr == "TTTC0081R" and not self._ia_done:
            self._ia_done = True
            raise KeyboardInterrupt

    def get(self, url, **kw):
        tr = kw["headers"]["tr_id"]
        self.sent.append(tr)
        self.calls[tr] += 1
        self._maybe_interrupt(tr)
        if tr == "FHKST01010100":
            return _Resp(_ok(output=self._quote()))
        if tr == "TTTC8036R":
            if self.pending_fail_after_cancel and self.cancel_posted:
                return _Resp({"rt_cd": "1", "msg_cd": "EGW00500", "msg1": "미체결 조회 실패"})
            return _Resp(_ok(output=self._pending(), ctx_area_fk100="", ctx_area_nk100=""))
        if tr == "TTTC0081R":
            if self.daily_fail_after_cancel and self.cancel_posted:
                return _Resp({"rt_cd": "1", "msg_cd": "EGW00500", "msg1": "당일체결 조회 실패"})
            self._advance()
            return _Resp(_ok(output1=self._daily(), output2={"tot_ord_qty": "4", "tot_ccld_qty": "4",
                                                            "tot_ccld_amt": "39780", "prsm_tlex_smtl": "17"},
                             ctx_area_fk100="", ctx_area_nk100=""))
        if tr == "TTTC8434R":
            if self.balance_fail_from and self.calls[tr] >= self.balance_fail_from:
                return _Resp({"rt_cd": "1", "msg_cd": "EGW99999", "msg1": "잔고 조회 실패 계좌 87654321"})
            summ = {"dnca_tot_amt": "5000000", "nxdy_excc_amt": "5000000", "prvs_rcdl_excc_amt": "5000000",
                    "tot_evlu_amt": "5000000", "evlu_pfls_smtl_amt": "0", "pchs_amt_smtl_amt": "0",
                    "evlu_amt_smtl_amt": "0", "thdt_buy_amt": "9990", "thdt_sll_amt": "9980", "thdt_tlex_amt": "17"}
            return _Resp(_ok(output1=self._holdings(), output2=[summ], ctx_area_fk100="", ctx_area_nk100=""))
        if tr == "TTTC8908R":
            return _Resp(_ok(output={"ord_psbl_cash": "5000000", "nrcvb_buy_amt": "5000000", "nrcvb_buy_qty": "500",
                                     "max_buy_amt": "5000000", "max_buy_qty": "500"}))
        raise AssertionError(f"unexpected GET {tr}")

    def post(self, url, **kw):
        if url.endswith(p.cp.PATH_HASHKEY):
            self.sent.append("hashkey")
            return _Resp({"HASH": "h"})
        if "telegram" in url:
            self.sent.append("telegram")
            return _Resp({"ok": True})
        if url.endswith(p.cp.PATH_TOKEN):
            self.sent.append("token")
            # 만료는 «지금 + 1일»(실시각 기준) — 고정 시각이면 그 시각이 지난 뒤 캐시 토큰이 «만료»로 읽혀
            # 토큰 POST 가 2회가 된다(2026-10-09 10:00 이후 N7 시험 영구 실패 · REVIEW_RF7 F10).
            expired = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            return _Resp({"access_token": SECRETS[3], "access_token_token_expired": expired,
                          "token_type": "Bearer", "expires_in": 86400})
        tr = kw["headers"]["tr_id"]
        params = json.loads(kw.get("data") or "{}")
        self.sent.append(tr)
        self.posts.append((tr, params))
        self.calls[tr] += 1
        if tr == p.cp.TR_BUY:
            if self.buy_timeout:                                 # 응답 유실(접수 안 됨) — 봇은 무응답으로 본다
                raise _requests.exceptions.ReadTimeout("read timeout")
            if self.buy_reject:
                return _Resp({"rt_cd": "1", "msg_cd": "APBK0952", "msg1": "주문가능금액을 초과했습니다"})
            self.buy = {"filled": False, "cancelled": False, "age": 0, "rejected": self.exchange_reject}
            return _Resp(_ok(msg_cd="APBK0013", msg1="주문 전송 완료 되었습니다.",
                             output={"KRX_FWDG_ORD_ORGNO": "91252", "ODNO": B_OD, "ORD_TMD": "100001"}))
        if tr == p.cp.TR_SELL:
            if self.sell_reject or self.held < 1:            # 보유 없는 매도 = 거부(공매도 불가)
                return _Resp({"rt_cd": "1", "msg_cd": "APBK0400", "msg1": "주문가능수량을 초과했습니다."})
            self.sell = {"filled": False, "age": 0, "post": 0}
            return _Resp(_ok(msg_cd="APBK0013", msg1="주문 전송 완료 되었습니다.",
                             output={"KRX_FWDG_ORD_ORGNO": "91252", "ODNO": S_OD, "ORD_TMD": "100031"}))
        if tr == p.cp.TR_CANCEL:
            b = self.buy
            if b and not b["filled"] and not b["cancelled"] and not b.get("cancel_pending") \
                    and not b.get("rejected"):
                self.cancel_posted = True
                if self.race:
                    self._fill_buy()
                    return _Resp(REJ)
                if self.cancel_mode == "unconfirmed":
                    b["cancel_pending"] = True
                    return _Resp(_ok(msg_cd="APBK0013", msg1="주문 전송 완료 되었습니다.",
                                     output={"KRX_FWDG_ORD_ORGNO": "91252", "ODNO": C_OD, "ORD_TMD": "100105"}))
                b["cancelled"] = True
                return _Resp(_ok(msg_cd="APBK0013", msg1="주문 전송 완료 되었습니다.",
                                 output={"KRX_FWDG_ORD_ORGNO": "91252", "ODNO": C_OD, "ORD_TMD": "100105"}))
            return _Resp(REJ)
        raise AssertionError(f"unexpected POST {tr}")


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def sleep(self, s):
        self.t += s

    def monotonic(self):
        return self.t


@pytest.fixture
def probe(monkeypatch, tmp_path):
    import api.circuit_breaker as cbm
    import api.kis_auth as ka
    from config.market_hours import KST
    from framework.broker import KISBroker

    monkeypatch.setattr(ka, "_TRENV", ka.KISEnv(SECRETS[1], SECRETS[2], SECRETS[0], "01", "Bearer " + SECRETS[3],
                                                "https://" + HOST))
    monkeypatch.setattr(ka, "_autoReAuth", False)
    monkeypatch.setattr(ka, "_min_api_interval", 0)
    cb = SimpleNamespace(can_execute=lambda: True, record_success=lambda: None, record_failure=lambda: None,
                         record_blocked=lambda: None)
    monkeypatch.setattr(cbm, "get_circuit_breaker", lambda: cb)
    clock = _Clock()
    monkeypatch.setattr(p, "_time", clock)
    handlers = []

    def _run(fake, name, *, live=True, hms=(10, 0, 0), max_price=30_000, fill_wait=60, fn=None,
             deadline=p.DEFAULT_DEADLINE):
        out = tmp_path / name
        out.mkdir()
        paths = p._paths(out, "20261008_100000")
        masker = p.cp.Masker()
        masker.add(*SECRETS)
        flt = p.cp._MaskFilter(masker)
        buf = io.StringIO()
        h = logging.StreamHandler(buf)
        h.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        h.addFilter(flt)
        jh = logging.FileHandler(paths["jsonl"], encoding="utf-8")
        jh.setFormatter(logging.Formatter("%(message)s"))
        jh.addFilter(flt)
        handlers.append(jh)
        log, raw = logging.getLogger("fill_probe.t." + name), logging.getLogger("fill_probe.t." + name + ".raw")
        for lg, hd in ((log, h), (raw, jh)):
            lg.handlers, lg.propagate = [hd], False
            lg.setLevel(logging.INFO)
        state = p.FillGateState(live=live)
        gate = p.FillHttpGate(fake, state, HOST, log, raw, masker)
        monkeypatch.setattr(ka, "requests", gate)            # 봇 코드의 모든 HTTP → 게이트 → 가짜 거래소
        broker = KISBroker()
        broker._connected = True
        args = SimpleNamespace(code=CODE, live=live, max_price=max_price, fill_wait=fill_wait, deadline=deadline)
        base, t0 = KST.localize(datetime(2026, 10, 8, *hms)), clock.t
        ctx = p.Ctx(args, tmp_path / "instances" / "daytrading", log, raw, masker,
                    lambda: base + timedelta(seconds=clock.t - t0), paths)
        ctx.gate, ctx.state, ctx.broker = gate, state, broker
        rc = p.execute(ctx, fn or p._after_connect)
        jh.flush()
        res = json.loads(Path(paths["result"]).read_text(encoding="utf-8"))
        return SimpleNamespace(rc=rc, out=buf.getvalue(), res=res, fake=fake, paths=paths, ctx=ctx)

    yield _run
    for hd in handlers:
        hd.close()


def _files_ok(r, rc):
    """모든 종결 경로: result json(exit_code 일치) · 요약 md · JSONL 이 생긴다."""
    assert Path(r.paths["result"]).exists() and r.res["exit_code"] == rc
    assert Path(r.paths["summary_md"]).exists()
    assert Path(r.paths["jsonl"]).exists()
    for k in ("exit_code", "verdict", "buy", "sell", "end_holding_qty", "end_pending_count", "emergency_sell_tried",
              "critical"):
        assert k in r.res
    for k in ("odno", "filled", "fill_price"):
        assert k in r.res["buy"] and k in r.res["sell"]


def _no_order_trs(fake):
    assert not any(t in ORDER_TRS for t in fake.sent), fake.sent


# ── 시나리오 ─────────────────────────────────────────────────────────────────
def test_dry_run_never_calls_order_trs(probe):
    r = probe(FakeExchange(), "dry", live=False)
    assert r.rc == 0
    _no_order_trs(r.fake)
    assert r.res["mode"] == "dry-run" and r.res["guards_all_pass"] is True and r.res["order_http"] == []
    _files_ok(r, 0)


@pytest.mark.parametrize("name, kw, run_kw, guard", [
    ("time", {}, {"hms": (9, 29, 59)}, "시간창 09:30:00~14:50:00 KST"),
    ("held", {"extra_holdings": [{"pdno": "005930", "hldg_qty": "3"}]}, {}, "시작 시 계좌 보유 종목 0"),
    ("bal_fail", {"balance_fail_from": 1}, {}, "시작 시 계좌 보유 종목 0"),
    ("pending", {"extra_pending": [{"odno": "0000000999", "pdno": "005930", "sll_buy_dvsn_cd": "02"}]}, {},
     "시작 시 미체결 0건"),
    ("price_cap", {"price": "31000"}, {}, "현재가 ≤ --max-price"),
    ("tick", {"price": "15010"}, {}, "주문가(=현재가)가 봇 호가표에 정렬(봇이 가격을 고치지 않음)"),
    ("vi", {"quote_over": {"vi_cls_code": "Y"}}, {}, "이상 표식 없음(거래정지·임시정지·VI·관리·정리매매·시장경고·단기과열·투자유의)"),
])
def test_live_guard_fail_sends_no_order(probe, name, kw, run_kw, guard):
    r = probe(FakeExchange(**kw), "g_" + name, **run_kw)
    assert r.rc == 2 and guard in r.res["guards_failed"]
    _no_order_trs(r.fake)
    _files_ok(r, 2)


def test_price_moves_above_cap_before_order_sends_nothing(probe):
    r = probe(FakeExchange(price_seq=["9990", "31000"]), "requote")
    assert r.rc == 2 and "현재가 ≤ --max-price" in r.res["guards_failed"]
    _no_order_trs(r.fake)
    _files_ok(r, 2)


def test_s1_normal_buy_fill_market_sell_fill_holding_zero(probe):
    r = probe(FakeExchange(), "s1")
    assert r.rc == 0, r.out
    f = r.fake
    assert f.count("TTTC0012U") == 1 and f.count("TTTC0011U") == 1 and f.count("TTTC0013U") == 0
    buy = next(prm for t, prm in f.posts if t == "TTTC0012U")
    sell = next(prm for t, prm in f.posts if t == "TTTC0011U")
    assert (buy["ORD_DVSN"], buy["ORD_UNPR"], buy["ORD_QTY"]) == ("00", "9990", "1")
    assert (sell["ORD_DVSN"], sell["ORD_UNPR"], sell["ORD_QTY"]) == ("01", "0", "1")    # 봇 실전 시장가 매도와 같은 주문
    res = r.res
    assert res["buy"]["odno"] == B_OD and res["buy"]["filled"] is True and res["buy"]["fill_price"] == 9990.0
    assert res["sell"]["odno"] == S_OD and res["sell"]["filled"] is True and res["sell"]["fill_price"] == 9980.0
    assert res["sell"]["p2_14_condition"] is False and "첫 조회" in res["sell"]["avg_prvs_rule"]
    assert res["sell"]["avg_matches_implied"] is True
    assert res["buy"]["bot_view_last"]["code"] == "FILLED" and res["sell"]["bot_fill_confirm_sec"] is not None
    assert res["end_holding_qty"] == 0 and res["end_pending_count"] == 0 and res["critical"] == []
    assert res["end_daily_new_buy_filled"] == 1 and res["end_daily_new_sell_filled"] == 1   # 앞선 왕복은 스냅샷으로 제외
    assert res["emergency_sell_tried"] is False and res["holding_after_buy"] == 1
    md = Path(r.paths["summary_md"]).read_text(encoding="utf-8")
    assert "「P2-14 진입 조건 발생 여부」: 미발생" in md and "`ccld_unpr` 키 존재: False" in md
    _files_ok(r, 0)


def test_s2_buy_unfilled_cancel_exit3(probe):
    r = probe(FakeExchange(buy_fill_at=None), "s2")
    assert r.rc == 3, r.out
    assert r.fake.count("TTTC0013U") == 1 and r.fake.count("TTTC0011U") == 0
    res = r.res
    assert res["buy"]["filled"] is False and res["buy"]["cancel_tried"] is True
    # fix/real-flow-6(NEW-B1 수정) 뒤 반환 = 성공 모양 · 반환은 기록만(판정은 재조회로)
    assert res["buy"]["cancels"][0]["success"] is True
    assert res["buy"]["cancels"][0]["message"] == "Order cancelled"
    assert res["buy"]["cancels"][0]["raw_rt_cd"] == "0"
    assert res["end_holding_qty"] == 0 and res["end_pending_count"] == 0 and res["critical"] == []
    _files_ok(r, 3)


def test_s3_cancel_race_fill_then_sell(probe):
    r = probe(FakeExchange(buy_fill_at=None, race_fill_on_cancel=True), "s3")
    assert r.rc == 0, r.out
    assert r.fake.count("TTTC0013U") == 1 and r.fake.count("TTTC0011U") == 1
    assert r.res["buy"]["filled"] is True and r.res["end_holding_qty"] == 0
    assert "경합" in r.out
    _files_ok(r, 0)


def test_s4_sell_avg_empty_then_filled_records_p2_14_and_implied(probe):
    # 체결 뒤 0081R 3회 빈값 → 4회째 채워짐. 첫 폴링은 같은 회차 8036R 에 아직 보여 봇 판정이 PENDING(봇과 같은 순서)
    r = probe(FakeExchange(sell_avg_seq=("", "", "", "9980")), "s4")
    assert r.rc == 0, r.out
    s = r.res["sell"]
    assert s["p2_14_condition"] is True and s["p2_14_polls"] == 2
    assert "체결 뒤 3회 빈값" in s["avg_prvs_rule"] and s["avg_prvs_first_valid_sec"] is not None
    assert s["bot_fill_confirm_sec"] == s["avg_prvs_first_valid_sec"] > s["fill_latency_sec"]
    assert s["implied_price"] == 9980.0 and s["fill_price"] == 9980.0 and s["fill_price_source"] == "avg_prvs"
    md = Path(r.paths["summary_md"]).read_text(encoding="utf-8")
    assert "「P2-14 진입 조건 발생 여부」: **발생**" in md
    _files_ok(r, 0)


def test_s5_sell_avg_zero_forever_uses_implied_price(probe):
    r = probe(FakeExchange(sell_avg_seq=("0",)), "s5")
    assert r.rc == 0, r.out
    s = r.res["sell"]
    assert s["p2_14_condition"] is True and "끝까지 안 채워짐" in s["avg_prvs_rule"]
    assert s["fill_price"] == 9980.0 and s["fill_price_source"] == "tot_ccld_amt/tot_ccld_qty"
    assert s["bot_fill_confirm_sec"] is None                          # 봇은 끝까지 체결 확정 못 함(영원히 보류)
    assert r.fake.count("TTTC0011U") == 1
    _files_ok(r, 0)


def test_s6_sell_never_fills_exit4_no_resell(probe):
    r = probe(FakeExchange(sell_fill_at=None), "s6")
    assert r.rc == 4, r.out
    assert r.fake.count("TTTC0011U") == 1
    assert r.res["sell"]["filled"] is False and r.res["end_holding_qty"] == 1
    assert any("종료 확인 불일치" in m for m in r.res["critical"])
    _files_ok(r, 4)


def test_s7_sell_rejected_exit4_no_resell(probe):
    r = probe(FakeExchange(sell_reject=True), "s7")
    assert r.rc == 4, r.out
    assert r.fake.count("TTTC0011U") == 1 and r.res["sell"]["odno"] == ""
    assert r.res["end_holding_qty"] == 1
    _files_ok(r, 4)


def test_s8_ctrl_c_after_buy_fill_emergency_sell_once(probe):
    r = probe(FakeExchange(interrupt=("TTTC8434R", 2)), "s8")       # 1 = 사전 가드 · 2 = 매도 전 잔고 확인
    assert r.rc == 4, r.out
    assert r.fake.count("TTTC0011U") == 1 and r.fake.count("TTTC0013U") == 0
    res = r.res
    assert res["emergency_sell_tried"] is True and res["emergency"]["reason"].startswith("KeyboardInterrupt")
    assert res["sell"]["filled"] is True and res["end_holding_qty"] == 0
    assert any("비상 시장가 매도 1회 시도" in m for m in res["critical"])
    _files_ok(r, 4)


def test_s9_exception_after_buy_fill_emergency_sell_once(probe, monkeypatch):
    def boom(ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(p, "_sell_and_verify", boom)
    r = probe(FakeExchange(), "s9")
    assert r.rc == 4 and r.fake.count("TTTC0011U") == 1
    assert r.res["emergency_sell_tried"] is True and "RuntimeError" in r.res["emergency"]["reason"]
    _files_ok(r, 4)


def test_s10_ctrl_c_after_sell_sent_does_not_resell(probe):
    r = probe(FakeExchange(interrupt_after_sell=True), "s10")
    assert r.rc == 4, r.out
    assert r.fake.count("TTTC0011U") == 1                              # 이중 매도 없음
    assert r.res["emergency_sell_tried"] is False
    assert r.res["emergency"]["sell"] == "매도 이미 전송 → 재매도 안 함"
    assert r.res["end_holding_qty"] == 0
    _files_ok(r, 4)


def test_s11_ctrl_c_while_waiting_unfilled_buy_cancels_no_sell(probe):
    r = probe(FakeExchange(buy_fill_at=None, interrupt=("TTTC0081R", 3)), "s11")   # 1 = 사전 스냅샷
    assert r.rc == 4, r.out
    assert r.fake.count("TTTC0013U") == 1 and r.fake.count("TTTC0011U") == 0
    assert r.res["emergency"]["buy_cancel"]["odno"] == B_OD and r.res["end_holding_qty"] == 0
    _files_ok(r, 4)


def test_s12_balance_unknown_after_fill_no_sell_exit4(probe):
    r = probe(FakeExchange(balance_fail_from=2), "s12")
    assert r.rc == 4, r.out
    assert r.fake.count("TTTC0011U") == 0                              # 보유 미상이면 매도하지 않는다
    assert r.res["end_holding_qty"] is None and r.res["holding_after_buy"] is None
    _files_ok(r, 4)


def test_s13_interrupt_before_any_order_exit1(probe):
    r = probe(FakeExchange(interrupt=("FHKST01010100", 1)), "s13")
    assert r.rc == 1
    _no_order_trs(r.fake)
    _files_ok(r, 1)


def test_secrets_masked_in_result_jsonl_md(probe):
    r = probe(FakeExchange(balance_fail_from=3), "mask")        # 실패 응답 msg1 에 계좌번호 포함
    blobs = [Path(r.paths[k]).read_text(encoding="utf-8") for k in ("result", "jsonl", "summary_md")] + [r.out]
    for b in blobs:
        for sec in SECRETS + ("10.1.2.3", "01012345678"):
            assert sec not in b, sec
    lines = [json.loads(x) for x in Path(r.paths["jsonl"]).read_text(encoding="utf-8").splitlines() if x.strip()]
    kinds = {x["kind"] for x in lines}
    assert {"http", "poll", "holdings", "quote", "guards"} <= kinds
    assert any(x.get("params", {}).get("CANO") == "***" for x in lines if x["kind"] == "http")


# ── main 종결 경로(결과 파일) ────────────────────────────────────────────────
def test_main_live_tree_cwd_writes_result_exit2(monkeypatch, tmp_path):
    monkeypatch.setattr(p, "_cwd", lambda: Path("D:/GIT/kis-trading-template/RoboTrader_template"))
    assert p.main(["--code", CODE, "--out-dir", str(tmp_path)]) == 2
    res = json.loads(next(tmp_path.glob("result_*.json")).read_text(encoding="utf-8"))
    assert res["exit_code"] == 2 and "라이브 트리" in res["verdict"]


@pytest.mark.parametrize("argv", [["--live"], ["--code", "12345"], ["--code", CODE, "--max-price", "500000"],
                                  ["--code", CODE, "--fill-wait", "5"]])
def test_main_bad_args_write_result_exit2(tmp_path, argv):
    assert p.main(argv + ["--out-dir", str(tmp_path)]) == 2
    res = json.loads(next(tmp_path.glob("result_*.json")).read_text(encoding="utf-8"))
    assert res["exit_code"] == 2 and "인자 오류" in res["verdict"]


def test_main_precondition_fail_writes_result_and_restores(monkeypatch, tmp_path):
    import api.kis_auth as ka
    import config.settings  # noqa: F401  (이미 로드된 설정 그대로 — main 이 다시 읽지 않게)
    import utils.logger as ulog

    class _NoNet:
        exceptions = _requests.exceptions

        def __getattr__(self, name):
            raise AssertionError(f"네트워크 호출 시도: requests.{name}")

    nonet = _NoNet()
    monkeypatch.setattr(ka, "requests", nonet)
    monkeypatch.setattr(p, "scan_main_py_processes", lambda: [])
    inst = tmp_path / "instances" / "not_daytrading_inst"
    inst.mkdir(parents=True)
    monkeypatch.setenv("KIS_INSTANCE_DIR", str(inst.resolve()))
    root_n = len(logging.getLogger().handlers)
    shared = ulog._shared_file_handler
    rc = p.main(["--code", CODE, "--live", "--instance-dir", str(inst), "--out-dir", str(tmp_path / "out")])
    assert rc == 2
    res = json.loads(next((tmp_path / "out").glob("result_*.json")).read_text(encoding="utf-8"))
    assert res["exit_code"] == 2 and "인스턴스 = daytrading" in res["guards_failed"] and res["order_http"] == []
    assert ka.requests is nonet                                    # 게이트 원복
    assert len(logging.getLogger().handlers) == root_n and ulog._shared_file_handler is shared
    assert next((tmp_path / "out").glob("fill_probe_*_summary.md")).exists()


# ── 리뷰 반영(B1·I1·I2·I3·I4·m1~m9) ──────────────────────────────────────────
def _snap(**kw):
    s = {"pending_ok": True, "in_pending": False, "pending_count": 0, "daily_ok": True,
         "daily_row": {"tot_ccld_qty": "0", "rmn_qty": "0", "cncl_cfrm_qty": "1", "cncl_yn": "N"}, "cancel_rows": []}
    s.update(kw)
    return s


def test_settle_issues_requires_strong_evidence():
    assert p.settle_issues(_snap(), 0, 0, True, False) == []
    # 10-08 실측: 취소 접수 +2초에 원·취소 행 모두 cncl_yn '' · cncl_cfrm_qty '0' → 확인 필드는 기록만(판정 무관)
    measured = _snap(daily_row={"tot_ccld_qty": "0", "rmn_qty": "0", "cncl_cfrm_qty": "0", "cncl_yn": ""},
                     cancel_rows=[{"cncl_yn": "", "cncl_cfrm_qty": "0"}])
    assert p.settle_issues(measured, 0, 0, True, False) == []
    assert p.settle_issues(_snap(daily_row={"tot_ccld_qty": "0", "rmn_qty": "0"}), 0, 0, True, False) == []
    for row, frag in (({"tot_ccld_qty": "0", "cncl_cfrm_qty": "1"}, "잔량 미상"),            # 잔량 필드 없음
                      ({"tot_ccld_qty": "0", "rmn_qty": "", "cncl_cfrm_qty": "1"}, "잔량 미상"),
                      ({"tot_ccld_qty": "0", "rmn_qty": "1", "cncl_cfrm_qty": "1"}, "잔량 1"),
                      ({"tot_ccld_qty": "x", "rmn_qty": "0", "cncl_cfrm_qty": "1"}, "체결수량 미상"),
                      ({"tot_ccld_qty": "1", "rmn_qty": "0", "cncl_cfrm_qty": "1"}, "체결수량 1")):
        assert any(frag in x for x in p.settle_issues(_snap(daily_row=row), 0, 0, True, False)), row
    assert p.settle_issues(_snap(daily_row=None), 0, 0, True, False) == ["0081R 에 원주문 행 없음"]
    assert any("8036R" in x for x in p.settle_issues(_snap(pending_ok=False), 0, 0, True, False))
    assert any("미체결 목록에 남음" in x for x in p.settle_issues(_snap(in_pending=True), 0, 0, True, False))
    assert any("계좌 미체결 1" in x for x in p.settle_issues(_snap(pending_count=1), 0, 0, True, False))
    assert any("0081R" in x for x in p.settle_issues(_snap(daily_ok=False), 0, 0, True, False))
    assert any("보유 미상" in x for x in p.settle_issues(_snap(), None, None, True, False))
    assert any("계좌 전체 보유 2" in x for x in p.settle_issues(_snap(), 0, 2, True, False))
    # 주문번호 미상: 명시적 거부일 때만 «행 없음 = 체결 0»
    assert p.settle_issues(_snap(daily_row=None), 0, 0, False, True) == []
    assert any("명시적 거부" in x for x in p.settle_issues(_snap(daily_row=None), 0, 0, False, False))


def test_buy_explicit_reject_classification():
    assert p.buy_explicit_reject({"status": 200, "rt_cd": "1"}) is True
    assert p.buy_explicit_reject({"status": 200, "rt_cd": "0"}) is False
    assert p.buy_explicit_reject({"status": 200, "rt_cd": None}) is False
    assert p.buy_explicit_reject({"status": 500, "rt_cd": "1"}) is False
    assert p.buy_explicit_reject({"exception": "ReadTimeout: x"}) is False
    assert p.buy_explicit_reject(None) is False


def test_b1_cancel_unconfirmed_then_late_fill_goes_to_sell_not_exit3(probe):
    f = FakeExchange(buy_fill_at=None, cancel_mode="unconfirmed", late_fill_after=3)
    r = probe(f, "b1late")
    assert r.rc == 0, r.out                                     # 늦게 반영된 체결 → 보유 1 확인 → 매도
    assert f.count("TTTC0011U") == 1 and f.held == 0 and r.res["buy"]["filled"] is True
    _files_ok(r, 0)


def test_b1_cancel_unconfirmed_never_reflected_exit4(probe):
    f = FakeExchange(buy_fill_at=None, cancel_mode="unconfirmed")
    r = probe(f, "b1never")
    assert r.rc == 4, r.out
    assert f.count("TTTC0011U") == 0
    assert any("강한 증거로 확인 못 함" in m for m in r.res["critical"])
    assert len(r.res["buy"]["settle_rounds"]) == p.SETTLE_MAX_ROUNDS
    _files_ok(r, 4)


def test_1008_measured_cancel_shape_reaches_exit3(probe):
    # 10-08 §4-B 실측형(원·취소 행 cncl_yn '' · cncl_cfrm_qty '0'): 8036R 부재 + 원주문 체결 0·잔량 0 + 보유 0 이
    # 5초 간격 2라운드 연속 → exit 3(종전 «취소 확인 수량 ≥1» 조건은 실측상 영원히 거짓 → exit 3 도달 불가였다)
    r = probe(FakeExchange(buy_fill_at=None, cancel_mode="measured"), "m1008")
    assert r.rc == 3, r.out
    rounds = r.res["buy"]["settle_rounds"]
    assert len(rounds) == 2 and all(rd["issues"] == [] for rd in rounds)
    assert rounds[1]["t"] - rounds[0]["t"] >= p.SETTLE_GAP_SEC
    last = [s_ for s_ in r.ctx.polls if s_["phase"] == "settle"][-1]["daily_row"]
    assert last["cncl_cfrm_qty"] == "0" and last["cncl_yn"] == ""
    assert r.res["critical"] == [] and r.fake.count("TTTC0011U") == 0
    _files_ok(r, 3)


def test_zero_remain_one_clean_round_is_not_enough_late_fill_goes_to_sell(probe):
    # 취소 접수 뒤 1라운드 깨끗(체결 0·잔량 0·보유 0) → 2라운드째 늦은 체결 반영(보유 1) → exit 3 아니고 매도
    f = FakeExchange(buy_fill_at=None, cancel_mode="unconfirmed", unconf_rmn="0", late_fill_after=3)
    r = probe(f, "rmn0late")
    assert r.rc == 0, r.out
    assert r.res["buy"]["settle_rounds"][0]["issues"] == []
    assert f.count("TTTC0011U") == 1 and f.held == 0 and r.res["buy"]["filled"] is True
    _files_ok(r, 0)


def test_n3_exchange_reject_after_accept_exit5_not_critical(probe):
    # 접수(ODNO) 뒤 거래소 거부: 0081R 원주문 rjct_qty 1 · 체결 0 · 잔량 0 · 보유 0 연속 2라운드 → «거부» 종결 exit 5
    f = FakeExchange(buy_fill_at=None, exchange_reject=True)
    r = probe(f, "xrej")
    assert r.rc == p.EXIT_EXCHANGE_REJECT == 5, r.out
    assert r.res["buy"]["exchange_reject"] is True and r.res["critical"] == []
    assert "거부" in r.res["verdict"] and f.count("TTTC0011U") == 0
    _files_ok(r, 5)


def test_b1_remain_field_missing_exit4(probe):
    r = probe(FakeExchange(buy_fill_at=None, drop_rmn=True), "b1norm")
    assert r.rc == 4, r.out
    assert any("잔량 미상" in x for x in r.res["buy"]["settle_rounds"][-1]["issues"])
    _files_ok(r, 4)


def test_b1_pending_query_fails_after_cancel_exit4(probe):
    r = probe(FakeExchange(buy_fill_at=None, pending_fail_after_cancel=True), "b1pfail")
    assert r.rc == 4, r.out
    assert r.res["end_pending_count"] is None and r.fake.count("TTTC0011U") == 0
    _files_ok(r, 4)


def test_b1_daily_query_fails_after_cancel_with_zero_holding_exit4(probe):
    r = probe(FakeExchange(buy_fill_at=None, daily_fail_after_cancel=True), "b1dfail")
    assert r.rc == 4, r.out
    assert r.res["end_holding_qty"] == 0                       # 보유 0 이어도 체결 0 을 확인 못 했으니 4
    _files_ok(r, 4)


def test_b1_confirmed_cancel_needs_two_clean_rounds_5s_apart(probe):
    r = probe(FakeExchange(buy_fill_at=None), "b1two")
    assert r.rc == 3, r.out
    rounds = r.res["buy"]["settle_rounds"]
    assert len(rounds) == 2 and all(rd["issues"] == [] for rd in rounds)
    assert rounds[1]["t"] - rounds[0]["t"] >= p.SETTLE_GAP_SEC
    _files_ok(r, 3)


def test_i1_buy_timeout_unknown_odno_exit4(probe):
    f = FakeExchange(buy_timeout=True)
    r = probe(f, "i1to")
    assert r.rc == 4, r.out
    assert r.res["buy"]["explicit_reject"] is False and r.res["buy"]["odno"] == ""
    assert f.count("TTTC0012U") == 1 and f.count("TTTC0013U") == 0 and f.count("TTTC0011U") == 0
    assert any("명시적 거부" in x for x in r.res["buy"]["settle_rounds"][-1]["issues"])
    _files_ok(r, 4)


def test_i1_m2_explicit_reject_settles_without_wait_exit3(probe):
    f = FakeExchange(buy_reject=True)
    r = probe(f, "i1rej")
    assert r.rc == 3, r.out
    assert r.res["buy"]["explicit_reject"] is True
    assert {p_["phase"] for p_ in r.ctx.polls} == {"settle"} and len(r.ctx.polls) == 2   # 60초 대기 없음
    assert f.count("TTTC0013U") == 0 and f.count("TTTC0011U") == 0
    _files_ok(r, 3)


def test_m1_holding_reflection_lag_still_sells(probe):
    f = FakeExchange(hold_lag=5)
    r = probe(f, "m1lag")
    assert r.rc == 0, r.out
    assert f.count("TTTC0011U") == 1 and r.res["holding_after_buy"] == 1
    _files_ok(r, 0)


def test_m3_vi_extends_sell_wait(probe):
    f = FakeExchange(vi_after_buy=True, sell_fill_at=30)            # 30회째(약 75초) 체결 — 60초면 놓침
    r = probe(f, "m3vi")
    assert r.rc == 0, r.out
    assert r.res["sell"]["vi_extended"] is True and r.res["sell"]["filled"] is True
    assert f.count("TTTC0011U") == 1
    _files_ok(r, 0)


def test_m9_final_pending_nonzero_with_zero_holding_exit4(probe):
    r = probe(FakeExchange(pending_after_sell=True), "m9pend")
    assert r.rc == 4, r.out
    assert r.res["end_holding_qty"] == 0 and r.res["end_pending_count"] == 1
    _files_ok(r, 4)


@pytest.mark.parametrize("kw", [{"extra_holdings": [{"pdno": "005930", "hldg_qty": "3"}]},
                                {"extra_pending": [{"odno": "0000000999", "pdno": "005930",
                                                    "sll_buy_dvsn_cd": "02"}]}])
def test_i4_account_not_clean_flag_and_critical(probe, kw):
    r = probe(FakeExchange(**kw), "i4_" + next(iter(kw)))
    assert r.rc == 2 and r.res["account_not_clean"] is True
    assert any("깨끗하지 않음" in m for m in r.res["critical"])
    _no_order_trs(r.fake)
    _files_ok(r, 2)


def test_i4_clean_account_flag_false(probe):
    r = probe(FakeExchange(), "i4clean", live=False)
    assert r.rc == 0 and r.res["account_not_clean"] is False


def test_i3_deadline_cuts_buy_wait(probe, monkeypatch):
    from datetime import time as dtime
    monkeypatch.setattr(p, "DEADLINE_MARGIN", timedelta(0))
    r = probe(FakeExchange(buy_fill_at=None), "i3buy", deadline=dtime(10, 0, 20), fill_wait=180)
    assert r.res["deadline_hit"] is True
    assert len([x for x in r.ctx.polls if x["phase"] == "wait"]) <= 9      # 180초(72회)가 아니라 마감에서 끊김
    assert r.rc == 3, r.out                                                 # 정리는 강한 증거로 확인됨
    _files_ok(r, 3)


def test_i3_deadline_cuts_sell_wait_exit4(probe, monkeypatch):
    from datetime import time as dtime
    monkeypatch.setattr(p, "DEADLINE_MARGIN", timedelta(0))
    f = FakeExchange(sell_fill_at=None)
    r = probe(f, "i3sell", deadline=dtime(10, 0, 30))
    assert r.rc == 4 and r.res["deadline_hit"] is True and f.count("TTTC0011U") == 1
    assert len([x for x in r.ctx.polls if x["side"] == "sell"]) < 24
    _files_ok(r, 4)


def test_i3_no_market_sell_after_cutoff(probe, monkeypatch):
    from datetime import time as dtime
    monkeypatch.setattr(p, "SELL_CUTOFF", dtime(10, 0, 3))
    f = FakeExchange()
    r = probe(f, "i3cut")
    assert r.rc == 4 and f.count("TTTC0011U") == 0
    assert r.res["sell"].get("blocked_by_cutoff") is True
    assert any("시장가 매도 안 함" in m for m in r.res["critical"])
    _files_ok(r, 4)


def test_i3_emergency_sell_also_respects_cutoff(probe, monkeypatch):
    from datetime import time as dtime
    monkeypatch.setattr(p, "SELL_CUTOFF", dtime(10, 0, 3))
    f = FakeExchange(interrupt=("TTTC8434R", 2))
    r = probe(f, "i3cutem")
    assert r.rc == 4 and f.count("TTTC0011U") == 0 and r.res["emergency_sell_tried"] is False
    _files_ok(r, 4)


def test_i3_result_json_fallback_when_out_dir_unusable(monkeypatch, tmp_path):
    fb = tmp_path / "fb"
    monkeypatch.setattr(p, "_fallback_dirs", lambda: [fb])
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    inst = tmp_path / "instances" / "daytrading"
    monkeypatch.setenv("KIS_INSTANCE_DIR", str(inst.resolve()))
    rc = p.main(["--code", CODE, "--instance-dir", str(inst), "--out-dir", str(blocker / "out")])
    assert rc == 2
    res = json.loads(next(fb.glob("result_*.json")).read_text(encoding="utf-8"))
    assert res["exit_code"] == 2 and "출력 폴더·로깅 설정 실패" in res["verdict"]
    assert res["files"]["result_fallback"].startswith(str(fb))


def test_write_result_any_falls_back(monkeypatch, tmp_path):
    fb = tmp_path / "fb"
    monkeypatch.setattr(p, "_fallback_dirs", lambda: [fb])
    blocker = tmp_path / "f"
    blocker.write_text("x", encoding="utf-8")
    where = p.write_result_any(str(blocker / "result_x.json"), {"exit_code": 4})
    assert where == str(fb / "result_x.json") and json.loads(Path(where).read_text(encoding="utf-8"))["exit_code"] == 4


@pytest.mark.parametrize("argv", [["--code", CODE, "--deadline", "9:00"], ["--code", CODE, "--deadline", "15:30"],
                                  ["--code", CODE, "--deadline", "x"], ["--code", CODE, "--deadline", "15:11"],
                                  ["--code", CODE, "--deadline", "15:15"]])
def test_deadline_arg_validation(tmp_path, argv):
    assert p.main(argv + ["--out-dir", str(tmp_path)]) == 2


def test_deadline_arg_parsed():
    from datetime import time as dtime
    assert p.parse_args(["--code", CODE, "--deadline", "14:30"]).deadline == dtime(14, 30)
    assert p.parse_args(["--code", CODE]).deadline == p.DEFAULT_DEADLINE
    assert p.parse_args(["--code", CODE, "--deadline", "15:10"]).deadline == dtime(15, 10)   # 상한(N1)
    for bad in ("15:11", "15:15"):
        with pytest.raises(SystemExit):
            p.parse_args(["--code", CODE, "--deadline", bad])
    assert p.DEADLINE_MAX <= (datetime.combine(datetime(2026, 10, 8), p.SELL_CUTOFF) - timedelta(minutes=3)).time()


def test_n4_fallback_dirs_outside_script_and_live_tree(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    dirs = [d.resolve() for d in p._fallback_dirs()]
    assert (tmp_path / "lad" / "kis-fill-probe").resolve() in dirs
    for d in dirs:
        for root in (p._RT_ROOT.resolve(), Path(p.cp.LIVE_TREE_ROOT).resolve()):
            assert d != root and root not in d.parents, d


def test_n8_dry_run_records_account_not_clean(probe):
    r = probe(FakeExchange(extra_holdings=[{"pdno": "005930", "hldg_qty": "3"}]), "n8dry", live=False)
    assert r.rc == 0 and r.res["account_not_clean"] is True
    assert any("깨끗하지 않음" in m for m in r.res["critical"])
    _no_order_trs(r.fake)
    _files_ok(r, 0)


def test_n7_run_connect_path_token_gate_and_dry_run_posts_only_token(monkeypatch, tmp_path):
    """run() 접속 경로: 토큰 발급 POST 는 게이트 통과 · dry-run 에서 토큰 외 POST 0 · 실네트워크·실토큰 캐시 0."""
    import socket
    import api.circuit_breaker as cbm
    import api.kis_auth as ka
    from config import settings
    from config.market_hours import KST

    real_connect = socket.socket.connect

    def _no_net(self, addr, *a, **k):          # 루프백(asyncio 자체 소켓쌍)만 허용 · 그 밖 접속 = 실패
        if not (isinstance(addr, tuple) and addr[0] in ("127.0.0.1", "::1", "localhost")):
            raise AssertionError(f"실네트워크 접속 시도 {addr}")
        return real_connect(self, addr, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", _no_net)
    fake = FakeExchange()
    monkeypatch.setattr(ka, "requests", fake)                         # run() 이 이것을 감싸 게이트를 건다
    monkeypatch.setattr(ka, "TOKEN_FILE_PATH", str(tmp_path / "token.yaml"))   # 실제 토큰 캐시 불가침
    for mod in (ka, settings):
        monkeypatch.setattr(mod, "KIS_BASE_URL", "https://" + HOST)
        monkeypatch.setattr(mod, "APP_KEY", SECRETS[1])
        monkeypatch.setattr(mod, "SECRET_KEY", SECRETS[2])
    monkeypatch.setattr(ka, "ACCOUNT_NUMBER", SECRETS[0] + "01")
    monkeypatch.setattr(ka, "_TRENV", None)
    monkeypatch.setattr(ka, "_base_headers", dict(ka._base_headers))
    monkeypatch.setattr(ka, "_last_auth_time", ka._last_auth_time)
    monkeypatch.setattr(ka, "_autoReAuth", False)
    monkeypatch.setattr(ka, "_min_api_interval", 0)
    cb = SimpleNamespace(can_execute=lambda: True, record_success=lambda: None, record_failure=lambda: None,
                         record_blocked=lambda: None)
    monkeypatch.setattr(cbm, "get_circuit_breaker", lambda: cb)
    monkeypatch.setattr(p.cp, "check_cwd", lambda cwd: ("cwd 라이브 트리 밖", True, "test"))
    monkeypatch.setattr(p.cp, "check_instance", lambda *a: [("인스턴스", True, "test")])
    monkeypatch.setattr(p, "_real_instance_guard", lambda: ("실전 인스턴스 꺼짐", True, "test"))
    clock = _Clock()
    monkeypatch.setattr(p, "_time", clock)

    out = tmp_path / "out"
    out.mkdir()
    paths = p._paths(out, "20261008_100000")
    masker = p.cp.Masker()
    masker.add(*SECRETS)
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.addFilter(p.cp._MaskFilter(masker))
    jh = logging.FileHandler(paths["jsonl"], encoding="utf-8")
    log, raw = logging.getLogger("fill_probe.t.n7"), logging.getLogger("fill_probe.t.n7.raw")
    for lg, hd in ((log, h), (raw, jh)):
        lg.handlers, lg.propagate = [hd], False
        lg.setLevel(logging.INFO)
    args = SimpleNamespace(code=CODE, live=False, max_price=30_000, fill_wait=60, deadline=p.DEFAULT_DEADLINE)
    base, t0 = KST.localize(datetime(2026, 10, 8, 10, 0, 0)), clock.t
    ctx = p.Ctx(args, tmp_path / "instances" / "daytrading", log, raw, masker,
                lambda: base + timedelta(seconds=clock.t - t0), paths)
    try:
        rc = p.execute(ctx, p.run)
    finally:
        for fn in reversed(ctx.restore):
            fn()
        jh.close()
    assert rc == 0, buf.getvalue()
    posts = [c for c in ctx.gate.calls if c["method"] == "POST"]
    assert [c["path"] for c in posts] == [p.cp.PATH_TOKEN] and posts[0]["blocked"] is False
    assert posts[0]["reason"] == "토큰 발급"
    assert fake.sent.count("token") == 1 and not any(t in ORDER_TRS for t in fake.sent)
    assert (tmp_path / "token.yaml").exists()                         # 토큰은 임시 경로에만
    assert ka.requests is fake                                        # 게이트 원복
    res = json.loads(Path(paths["result"]).read_text(encoding="utf-8"))
    assert res["exit_code"] == 0 and res["order_http"] == [] and SECRETS[3] not in json.dumps(res)


def test_m6_telegram_secrets_masked(tmp_path):
    ini = tmp_path / "key.ini"
    ini.write_text("[TELEGRAM]\nenabled = true\ntoken = 123456789:AAFakeBotTokenValue\nchat_id = 987654321\n",
                   encoding="utf-8")
    secs = p.telegram_secrets(ini)
    assert secs == ["123456789:AAFakeBotTokenValue", "987654321"]
    m = p.cp.Masker()
    m.add(*secs)
    assert m.text("https://api.telegram.org/bot123456789:AAFakeBotTokenValue/send chat=987654321") == \
        "https://api.telegram.org/bot***/send chat=***"
    assert p.telegram_secrets(tmp_path / "missing.ini") == []


@pytest.mark.parametrize("code, name, extra, ok", [
    ("099990", "테스트종목", {}, True),
    ("035420", "NHN", {}, True),                     # 브랜드 접두는 «브랜드+공백»만
    ("195940", "HK이노엔", {}, True),
    ("005935", "삼성전자우", {}, False),               # 코드 끝자리 ≠ 0 + 이름
    ("069500", "KODEX 200", {}, False),
    ("123450", "어떤 ETN 상품", {}, False),
    ("123450", "", {"rprs_mrkt_kor_name": "ETF"}, False),
    ("123450", "", {}, True),                         # 이름 없음 → 코드·시장명만
])
def test_m4_instrument_guard(code, name, extra, ok):
    assert p.check_instrument(code, {"hts_kor_isnm": name, **extra})[1] is ok


def test_m4_etf_rejected_in_live_guard(probe):
    r = probe(FakeExchange(quote_over={"hts_kor_isnm": "TIGER 미국S&P500"}), "m4etf")
    assert r.rc == 2 and "보통주(ETF·ETN·우선주 아님)" in r.res["guards_failed"]
    _no_order_trs(r.fake)
