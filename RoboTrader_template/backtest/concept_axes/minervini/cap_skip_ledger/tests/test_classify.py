"""상태 분류 — bought > held > no_slot / slot_available, K 이력, 교차 증거."""
from datetime import date, datetime, time

import pytest

from backtest.concept_axes.minervini.cap_skip_ledger import classify as C

D = date(2026, 9, 9)


def _dt(h, m, s=0, d=D):
    return datetime.combine(d, time(h, m, s))


def _rows_0909():
    """2026-09-09 실측 순서를 본뜬 체결 원장(minervini · K=3).

    09:00 보유 = 073240(08-28) · 119850(09-03) · 279570(08-11) → 3/3
    09:01:10 119850 매도 · 09:01:12 279570 매도 → 1/3
    09:02:43 317400 매수 · 09:07:35 241710 매수 → 3/3
    10:48:12 317400 매도 → 2/3
    """
    return [
        (1, "279570", "BUY", 5590, datetime(2026, 8, 11, 9, 9), "", None),
        (2, "073240", "BUY", 7040, datetime(2026, 8, 28, 9, 27), "", None),
        (3, "119850", "BUY", 42050, datetime(2026, 9, 3, 9, 2), "", None),
        (4, "119850", "SELL", 48000, _dt(9, 1, 10), "익절", 3),
        (5, "279570", "SELL", 5820, _dt(9, 1, 12), "보유기간", 1),
        (6, "317400", "BUY", 10600, _dt(9, 2, 43), "", None),
        (7, "241710", "BUY", 124500, _dt(9, 7, 35), "", None),
        (8, "317400", "SELL", 9750, _dt(10, 48, 12), "손절", 6),
    ]


def test_k_history():
    assert C.k_for(date(2026, 9, 17))[0] == 3
    assert C.k_for(date(2026, 9, 18))[0] == 6
    with pytest.raises(ValueError):
        C.k_for(date(2026, 1, 1))


def test_build_trades_links_by_buy_record_id():
    tr = C.build_trades(_rows_0909())
    by = {t.buy_id: t for t in tr}
    assert by[3].sell_ts == _dt(9, 1, 10) and by[3].link == "buy_record_id"
    assert by[2].sell_ts is None


def test_build_trades_fifo_when_link_missing():
    rows = [(1, "000001", "BUY", 100, _dt(9, 5), "", None),
            (2, "000001", "SELL", 90, _dt(10, 0), "손절", None)]
    t = C.build_trades(rows)[0]
    assert t.sell_price == 90 and t.link == "fifo"


def test_slot_windows_0909():
    tr = C.build_trades(_rows_0909())
    n0, w = C.slot_windows(tr, D, k=3, max_daily_trades=5)
    assert n0 == 3
    # 09:01:10 에 빈자리 → 09:07:35 에 다시 참 → 10:48:12 매도로 빈자리(체결 5번째라 daily_trades 5/5 → 막힘)
    assert w == [(time(9, 1, 10), time(9, 7, 35))]


def test_slot_windows_daily_trades_cap_not_binding():
    tr = C.build_trades(_rows_0909())
    _, w = C.slot_windows(tr, D, k=3, max_daily_trades=99)
    assert w == [(time(9, 1, 10), time(9, 7, 35)), (time(10, 48, 12), time(15, 30))]


def test_classify_states():
    tr = C.build_trades(_rows_0909())
    _, w = C.slot_windows(tr, D, k=3, max_daily_trades=5)
    assert C.classify_candidate("317400", D, tr, w)[0] == C.STATE_BOUGHT
    assert C.classify_candidate("073240", D, tr, w)[0] == C.STATE_HELD
    held_sold = C.classify_candidate("119850", D, tr, w)
    assert held_sold[0] == C.STATE_HELD and "당일 매도" in held_sold[1]
    assert C.classify_candidate("041830", D, tr, w)[0] == C.STATE_SLOT


def test_classify_no_slot_full_day():
    d = date(2026, 9, 16)
    rows = [(1, "073240", "BUY", 1, datetime(2026, 8, 28, 9), "", None),
            (2, "006360", "BUY", 1, datetime(2026, 9, 10, 9), "", None),
            (3, "241710", "BUY", 1, datetime(2026, 9, 9, 9), "", None)]
    tr = C.build_trades(rows)
    n0, w = C.slot_windows(tr, d, k=3, max_daily_trades=5)
    assert n0 == 3 and w == []
    assert C.classify_candidate("002990", d, tr, w)[0] == C.STATE_NO_SLOT
    # 같은 날 K=6 이었다면 자리 있음(장 전체)
    _, w6 = C.slot_windows(tr, d, k=6, max_daily_trades=5)
    assert w6 == [(time(9, 0), time(15, 30))]
    assert C.classify_candidate("002990", d, tr, w6)[0] == C.STATE_SLOT


def test_bought_beats_held():
    # 보유 중 매도 → 같은 날 재매수 = bought
    rows = [(1, "000001", "BUY", 1, datetime(2026, 9, 1, 9), "", None),
            (2, "000001", "SELL", 1, _dt(9, 30), "", 1),
            (3, "000001", "BUY", 1, _dt(11, 0), "", None)]
    tr = C.build_trades(rows)
    _, w = C.slot_windows(tr, D, k=3, max_daily_trades=5)
    assert C.classify_candidate("000001", D, tr, w)[0] == C.STATE_BOUGHT


def test_cap_log_flag_and_evidence():
    assert C.cap_log_flag(date(2026, 9, 15), "002990", {"002990": 1}) == "NA"
    assert C.cap_log_flag(date(2026, 9, 16), "002990", {"002990": 1}) == "Y"
    assert C.cap_log_flag(date(2026, 9, 16), "005090", {"002990": 1}) == "N"
    full = [(C.SESSION_OPEN, C.SESSION_CLOSE)]
    assert C.evidence_check(C.STATE_SLOT, "Y", full).startswith("conflict")
    assert C.evidence_check(C.STATE_NO_SLOT, "N", []).startswith("note")
    assert C.evidence_check(C.STATE_NO_SLOT, "Y", []) == "ok"


def test_window_consumed_by_higher_rank_is_no_slot():
    """09-10 실측형: 09:00 보유 2/3 → 09:02:50 목록 2위 006360 매수로 만석 → 3위 119850 은 자리 없음."""
    d = date(2026, 9, 10)
    rows = [(1, "073240", "BUY", 1, datetime(2026, 8, 28, 9), "", None),
            (2, "241710", "BUY", 1, datetime(2026, 9, 9, 9, 7), "", None),
            (3, "006360", "BUY", 1, datetime(2026, 9, 10, 9, 2, 50), "", None)]
    tr = C.build_trades(rows)
    n0, w = C.slot_windows_detail(tr, d, k=3, max_daily_trades=5)
    assert n0 == 2 and w == [(time(9, 0), time(9, 2, 50), "buy:006360")]
    order = ["073240", "006360", "119850", "098120"]
    st, note = C.classify_candidate("119850", d, tr, w, list_order=order)
    assert st == C.STATE_NO_SLOT and "상위 순위 매수로 소진" in note
    # 목록에서 매수 종목보다 «앞» 순위였다면 자리는 있었다(다른 사유로 못 산 것)
    st2, _ = C.classify_candidate("119850", d, tr, w, list_order=["119850", "006360"])
    assert st2 == C.STATE_SLOT


def test_window_closed_by_daily_cap_cause():
    tr = C.build_trades(_rows_0909())
    _, w = C.slot_windows_detail(tr, D, k=3, max_daily_trades=5)
    assert [x[2] for x in w] == ["buy:241710"]
    _, w2 = C.slot_windows_detail(tr, D, k=9, max_daily_trades=5)
    # K 가 커서 보유 수로는 안 막히고, 5번째 체결(10:48:12)에서 체결 수 한도로 닫힌다
    assert w2 == [(time(9, 0), time(10, 48, 12), "daily_cap")]
