"""real_cost_inquiry — 가드 3 · 응답 모킹 → CSV · 짝짓기. KIS·DB 호출은 전부 모킹(네트워크 0)."""
import csv
import os
from datetime import datetime

import pytest

from tools import real_cost_inquiry as rci

AFTER_CLOSE = datetime(2026, 11, 5, 18, 0, tzinfo=rci.KST)   # 목 18:00
INTRADAY = datetime(2026, 11, 5, 10, 0, tzinfo=rci.KST)      # 목 10:00
WEEKEND_10 = datetime(2026, 11, 7, 10, 0, tzinfo=rci.KST)    # 토 10:00


def _no_network(*a, **k):
    raise AssertionError("네트워크 호출 금지")


def _no_db(*a, **k):
    raise AssertionError("DB 호출 금지")


def _argv(root, out):
    return ["--instance", "daytrading", "--start", "20261019", "--end", "20261105",
            "--out", str(out), "--root", str(root)]


def _write_token(root, valid="2026-11-06 07:45:00"):
    (root / "token_info_daytrading.json").write_text(f"token: TKN\nvalid-date: {valid}\n", encoding="utf-8")


def _write_key(root):
    d = root / "instances" / "daytrading"
    d.mkdir(parents=True, exist_ok=True)
    (d / "key.ini").write_text(
        '[KIS]\nKIS_BASE_URL = "https://kis.example"\nKIS_APP_KEY = "AK"\nKIS_APP_SECRET = "AS"\n'
        'KIS_ACCOUNT_NO = "1234567801"\n', encoding="utf-8")


def _run(tmp_path, now, http_get=_no_network, fetch_internal=_no_db, pid_alive=lambda p: True):
    return rci.run(_argv(tmp_path, tmp_path / "out" / "cost.csv"), now=now, http_get=http_get,
                   fetch_internal=fetch_internal, pid_alive=pid_alive, sleep=lambda s: None)


def test_guard_bot_running_exit2_and_stale_pid_passes(tmp_path, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "post", _no_network)   # tokenP 경로 0 확인
    for pid_path in (tmp_path / "robotrader_daytrading.pid",
                     tmp_path / "instances" / "daytrading" / "robotrader_daytrading.pid"):
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()))
        assert _run(tmp_path, AFTER_CLOSE) == rci.EXIT_BOT_RUNNING
        # 죽은 PID 는 막지 않는다 → 다음 가드(토큰 없음 → 3)까지 진행
        assert _run(tmp_path, AFTER_CLOSE, pid_alive=lambda p: False) == rci.EXIT_TOKEN
        pid_path.unlink()
    (tmp_path / "robotrader_daytrading.pid").write_text("garbage")
    assert _run(tmp_path, AFTER_CLOSE, pid_alive=lambda p: False) == rci.EXIT_BOT_RUNNING


def test_guard_market_hours_exit4_weekend_passes(tmp_path):
    assert _run(tmp_path, INTRADAY) == rci.EXIT_MARKET_HOURS
    assert _run(tmp_path, datetime(2026, 11, 5, 15, 40, tzinfo=rci.KST)) == rci.EXIT_MARKET_HOURS
    assert _run(tmp_path, WEEKEND_10) == rci.EXIT_TOKEN          # 장중 가드 통과 → 토큰 없음


def test_guard_token_read_only_exit3(tmp_path, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "post", _no_network)
    monkeypatch.setattr(requests, "get", _no_network)
    _write_key(tmp_path)
    assert _run(tmp_path, AFTER_CLOSE) == rci.EXIT_TOKEN                     # 파일 없음
    _write_token(tmp_path, valid="2026-11-05 17:00:00")
    assert _run(tmp_path, AFTER_CLOSE) == rci.EXIT_TOKEN                     # 만료
    _write_token(tmp_path, valid="2026-11-05 18:05:00")
    assert _run(tmp_path, AFTER_CLOSE) == rci.EXIT_TOKEN                     # 10분 안 만료
    (tmp_path / "token_info_daytrading.json").write_text("::not yaml{", encoding="utf-8")
    assert _run(tmp_path, AFTER_CLOSE) == rci.EXIT_TOKEN                     # 판독 불가
    # 응답이 토큰 만료(EGW00123)여도 재발급 없이 3
    _write_token(tmp_path)
    expired = _FakeGet({"TTTC8708R": [({"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token"}, "")]})
    assert _run(tmp_path, AFTER_CLOSE, http_get=expired, pid_alive=lambda p: False) == rci.EXIT_TOKEN
    assert len(expired.calls) == 1


class _Resp:
    def __init__(self, body, tr_cont):
        self._body = body
        self.headers = {"tr_cont": tr_cont}
        self.status_code = 200

    def json(self):
        return self._body


class _FakeGet:
    """tr_id 별 응답 큐. 호출 헤더·파라미터를 기록한다."""

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def __call__(self, url, headers, params, timeout):
        self.calls.append((url, dict(headers), dict(params)))
        body, tr_cont = self.script[headers["tr_id"]].pop(0)
        return _Resp(body, tr_cont)


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_mocked_responses_to_csv(tmp_path):
    _write_token(tmp_path)
    _write_key(tmp_path)
    fake = _FakeGet({
        "TTTC8708R": [
            ({"rt_cd": "0", "output1": [{"trad_dt": "20261019", "fee": "150", "tl_tax": "1800",
                                         "buy_amt": "1000000", "sll_amt": "1000000", "zz_unknown": "x"}],
              "output2": {"tot_fee": "150"}, "ctx_area_fk100": "FK", "ctx_area_nk100": "NK"}, "F"),
            ({"rt_cd": "0", "output1": [{"trad_dt": "20261020", "fee": "75", "tl_tax": "0",
                                         "buy_amt": "500000", "sll_amt": "0"}], "output2": {}}, "D"),
        ],
        "TTTC0081R": [
            ({"rt_cd": "0", "output1": [
                {"ord_dt": "20261019", "pdno": "396300", "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "100",
                 "tot_ccld_amt": "1000000", "avg_prvs": "10000", "odno": "1"},
                {"ord_dt": "20261019", "pdno": "396300", "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "100",
                 "tot_ccld_amt": "1000000", "avg_prvs": "10000", "odno": "2"},
                {"ord_dt": "20261020", "pdno": "101360", "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "50",
                 "tot_ccld_amt": "500000", "avg_prvs": "10000", "odno": "3"},
            ], "output2": {"tot_ccld_amt_smtl": "2500000"}}, "D"),
        ],
    })
    internal = [{"id": 4037, "stock_code": "396300", "stock_name": "A", "quantity": 100, "price": 10000,
                 "trade_date": "20261019", "trade_time": "09:15:26", "fee_amount": None}]
    out = tmp_path / "out" / "cost.csv"
    rc = rci.run(_argv(tmp_path, out), now=AFTER_CLOSE, http_get=fake,
                 fetch_internal=lambda i, s, e: internal, pid_alive=lambda p: False, sleep=lambda s: None)
    assert rc == rci.EXIT_OK

    # 요청: GET 만 · 토큰 파일 값 그대로 · 계좌 8+2 분해 · 페이징 연속키 전달
    assert all(u.startswith("https://kis.example/uapi/") for u, _, _ in fake.calls)
    assert fake.calls[0][1]["authorization"] == "Bearer TKN"
    assert fake.calls[0][2]["CANO"] == "12345678" and fake.calls[0][2]["ACNT_PRDT_CD"] == "01"
    assert fake.calls[1][1]["tr_cont"] == "N" and fake.calls[1][2]["CTX_AREA_FK100"] == "FK"

    # 원본: 모르는 열도 그대로
    raw = _read(tmp_path / "out" / "cost_raw_8708_output1.csv")
    assert len(raw) == 2 and raw[0]["zz_unknown"] == "x"
    assert _read(tmp_path / "out" / "cost_raw_8708_output2.csv")[0]["tot_fee"] == "150"
    assert len(_read(tmp_path / "out" / "cost_raw_0081_output1.csv")) == 3
    assert all(r["status"] == "ok" for r in _read(tmp_path / "out" / "cost_field_check.csv"))

    daily = {r["date"]: r for r in _read(out)}
    d19 = daily["20261019"]
    assert float(d19["actual_cost"]) == 1950.0
    assert float(d19["assumed_cost"]) == pytest.approx(1_000_000 * 0.00015 + 1_000_000 * 0.00195)
    assert float(d19["actual_cost_over_sell_pct"]) == pytest.approx(0.195)
    assert float(d19["assumed_rate_pct"]) == pytest.approx(0.21)
    assert d19["matched_rows"] == "1" and d19["internal_fee_amount_sum"] == ""
    assert daily["20261020"]["actual_cost_over_sell_pct"] == ""             # 매도 0 → 비율 없음
    assert float(daily["TOTAL"]["actual_cost"]) == 2025.0
    assert len(_read(tmp_path / "out" / "cost_pairs.csv")) == 1


def test_unknown_fields_leave_calc_blank(tmp_path):
    _write_token(tmp_path)
    _write_key(tmp_path)
    fake = _FakeGet({
        "TTTC8708R": [({"rt_cd": "0", "output1": [{"trad_dt": "20261019", "commission_x": "150"}]}, "D")],
        "TTTC0081R": [({"rt_cd": "0", "output1": []}, "D")],
    })
    out = tmp_path / "cost.csv"
    rc = rci.run(_argv(tmp_path, out), now=AFTER_CLOSE, http_get=fake, fetch_internal=lambda i, s, e: [],
                 pid_alive=lambda p: False, sleep=lambda s: None)
    assert rc == rci.EXIT_OK
    check = {r["field"]: r["status"] for r in _read(tmp_path / "cost_field_check.csv")}
    assert check["8708.fee"] == "미확인" and check["8708.date"] == "ok"
    assert _read(out)[0]["actual_cost"] == ""
    assert _read(tmp_path / "cost_raw_8708_output1.csv")[0]["commission_x"] == "150"


def test_pair_sells_matched_and_unmatched():
    fmap = rci.resolve_fields([{"ord_dt": 1, "pdno": 1, "sll_buy_dvsn_cd": 1, "tot_ccld_qty": 1,
                                "tot_ccld_amt": 1, "avg_prvs": 1, "odno": 1}], "0081")
    kis = [
        {"ord_dt": "20261019", "pdno": "396300", "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "52",
         "tot_ccld_amt": "488800", "avg_prvs": "9400", "odno": "11"},
        {"ord_dt": "20261019", "pdno": "396300", "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "52",
         "tot_ccld_amt": "480000", "avg_prvs": "9230", "odno": "10"},                  # 매수 — 짝 대상 아님
        {"ord_dt": "20261020", "pdno": "088280", "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "0",
         "tot_ccld_amt": "0", "avg_prvs": "0", "odno": "12"},                          # 미체결 — 제외
        {"ord_dt": "20261020", "pdno": "45226K", "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "80",
         "tot_ccld_amt": "400000", "avg_prvs": "5000", "odno": "13"},
    ]
    internal = [
        {"id": 4037, "stock_code": "396300", "quantity": 52, "price": 9400, "trade_date": "20261019"},
        {"id": 4044, "stock_code": "088280", "quantity": 97, "price": 5070, "trade_date": "20261020"},
        {"id": 4045, "stock_code": "45226K", "quantity": 79, "price": 5000, "trade_date": "20261020"},  # 수량 다름
    ]
    pairs, unmatched = rci.pair_sells(internal, kis, fmap)
    assert [(p["internal_id"], p["kis_odno"]) for p in pairs] == [(4037, "11")]
    assert pairs[0]["amount_diff"] == 0.0
    sides = sorted((u["side"], str(u["code"])) for u in unmatched)
    assert sides == [("internal_only", "088280"), ("internal_only", "45226K"), ("kis_only", "45226K")]
