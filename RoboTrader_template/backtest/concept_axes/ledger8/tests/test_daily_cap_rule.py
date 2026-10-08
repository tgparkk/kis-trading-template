"""일일 한도(max_daily_trades)가 «무엇을 세나» — 날짜별 이력(10-07 까지 매수+매도 · 10-08 부터 매수만 · main 1e62298).

같은 하루 모양 「09:00 보유 3 → 매도 3 → 매수 3」(K=10 · 한도 5)을 10-07 과 10-08 에 넣는다:
  10-07 — 매도 3 + 매수 2 = 5 ⇒ 두 번째 매수(09:06)에서 일일 한도 도달 → 빈자리 닫힘(daily_cap)
  10-08 — 매수 3 < 5 ⇒ 도달 안 함 → 장 끝까지 빈자리(session_end)
"""
from __future__ import annotations

from datetime import date, datetime, time

import pytest

from backtest.concept_axes.ledger8 import fidelity8 as F
from backtest.concept_axes.ledger8 import registry as R
from backtest.concept_axes.minervini.cap_skip_ledger import classify as C

D_OLD = date(2026, 10, 7)
D_NEW = date(2026, 10, 8)
K, MDT = 10, 5


def _sell3_buy3(d: date):
    """09:00 보유 3(전날 매수) → 09:01:00·09:01:10·09:01:20 매도 3 → 09:05·09:06·09:07 매수 3."""
    prev = datetime(2026, 10, 1, 9, 30)
    at = lambda h, m, s=0: datetime.combine(d, time(h, m, s))  # noqa: E731
    rows = [(1, "000001", "BUY", 100, prev, "", None),
            (2, "000002", "BUY", 100, prev, "", None),
            (3, "000003", "BUY", 100, prev, "", None),
            (4, "000001", "SELL", 101, at(9, 1, 0), "익절", 1),
            (5, "000002", "SELL", 99, at(9, 1, 10), "손절", 2),
            (6, "000003", "SELL", 100, at(9, 1, 20), "보유기간", 3),
            (7, "000011", "BUY", 100, at(9, 5), "", None),
            (8, "000012", "BUY", 100, at(9, 6), "", None),
            (9, "000013", "BUY", 100, at(9, 7), "", None)]
    return C.build_trades(rows)


def test_rule_history_split_at_1008():
    assert C.daily_cap_rule_for(D_OLD)[0] == C.CAP_COUNTS_BUY_SELL
    assert C.daily_cap_rule_for(D_NEW)[0] == C.CAP_COUNTS_BUY_ONLY
    assert "1e62298" in C.daily_cap_rule_for(D_NEW)[1]
    assert C.counts_toward_daily_cap(D_OLD, is_buy=False) is True
    assert C.counts_toward_daily_cap(D_NEW, is_buy=False) is False
    assert C.counts_toward_daily_cap(D_NEW, is_buy=True) is True
    with pytest.raises(ValueError):
        C.daily_cap_rule_for(date(2026, 1, 1))


def test_registry_reexports_the_one_table():
    assert R.DAILY_CAP_RULE_HISTORY is C.DAILY_CAP_RULE_HISTORY
    assert R.daily_cap_rule_for(D_NEW) == C.daily_cap_rule_for(D_NEW)
    assert R.mdt_for("book_pullback_ma20", D_NEW)[0] == MDT          # 한도 값 5 는 불변


def test_1007_sell3_then_buy3_hits_daily_cap():
    n0, w = C.slot_windows_detail(_sell3_buy3(D_OLD), D_OLD, K, MDT)
    assert n0 == 3
    assert w == [(time(9, 0), time(9, 6), "daily_cap")]               # 매도 3 + 매수 2 = 5/5


def test_1008_sell3_then_buy3_does_not_hit_daily_cap():
    n0, w = C.slot_windows_detail(_sell3_buy3(D_NEW), D_NEW, K, MDT)
    assert n0 == 3
    assert w == [(time(9, 0), time(15, 30), "session_end")]           # 매수 3/5 — 매도는 안 센다


def test_free_slot_after_cap_time_follows_rule_by_date():
    """09:06 뒤(예: 09:10 on_tick)에 자리가 있었나 — 10-07 은 한도에 막혀 없음 · 10-08 은 있음(slot_verdict 메모에도 남는다)."""
    t = time(9, 10)
    _, w_old = C.slot_windows_detail(_sell3_buy3(D_OLD), D_OLD, K, MDT)
    _, w_new = C.slot_windows_detail(_sell3_buy3(D_NEW), D_NEW, K, MDT)
    assert not any(a <= t < b for a, b, _ in w_old)
    assert any(a <= t < b for a, b, _ in w_new)
    order = ["000011", "000012", "000013", "000099"]
    note_old = F.slot_verdict(_sell3_buy3(D_OLD), D_OLD, K, MDT, "000099", order, ["09:10:00"]).note
    note_new = F.slot_verdict(_sell3_buy3(D_NEW), D_NEW, K, MDT, "000099", order, ["09:10:00"]).note
    assert "빈자리=09:00:00-09:06:00" in note_old
    assert "빈자리=09:00:00-15:30:00" in note_new
