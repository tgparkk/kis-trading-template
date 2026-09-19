"""fidelity8 — 신호 판정·방향별 집계·«평가 가능» 규칙(v1·v2·v3 · 반례)·빈티지 취약 표시(순수)."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backtest.concept_axes.ledger8 import fidelity8 as F
from backtest.concept_axes.minervini.cap_skip_ledger.classify import (STATE_BOUGHT, STATE_HELD, STATE_NO_SLOT,
                                                                      STATE_SLOT, Trade)


def test_signal_log_state():
    assert F.signal_log_state(True, False, False) == F.LOG_Y        # 줄이 있으면 무조건 Y
    assert F.signal_log_state(False, True, True) == F.LOG_N         # on_tick 돌았고 평가 가능했는데 줄 없음
    assert F.signal_log_state(False, True, False) == F.LOG_NA       # 보유·캡 — _check_buy 까지 못 갔을 수 있다
    assert F.signal_log_state(False, False, True) == F.LOG_NA       # 그날 on_tick 흔적 없음


def test_decide_signal_prefers_log():
    assert F.decide_signal("N", "Y") == ("Y", "log")
    assert F.decide_signal("Y", "N") == ("N", "log")
    assert F.decide_signal("Y", "NA") == ("Y", "replay")


def test_signal_outcome():
    assert F.signal_outcome("Y", "Y") == F.OUT_AGREE_Y
    assert F.signal_outcome("N", "N") == F.OUT_AGREE_N
    assert F.signal_outcome("Y", "N") == F.OUT_REPLAY_ONLY
    assert F.signal_outcome("N", "Y") == F.OUT_LOG_ONLY
    assert F.signal_outcome("Y", "NA") == F.OUT_NA


def _row(strategy, outcome, mode="", reasons_equal="", ref_equal="", slot_state=STATE_SLOT):
    return dict(strategy=strategy, mode=mode, outcome=outcome, reasons_equal=reasons_equal, ref_equal=ref_equal,
                slot_state=slot_state)


def test_signal_table_splits_directions():
    rows = ([_row("book_pullback_ma20", F.OUT_AGREE_Y, reasons_equal="Y", ref_equal="Y")] * 9
            + [_row("book_pullback_ma20", F.OUT_LOG_ONLY)]
            + [_row("daytrading_3methods_breakout", F.OUT_AGREE_N)] * 5
            + [_row("daytrading_3methods_breakout", F.OUT_REPLAY_ONLY)] * 2
            + [_row("book_envelope_200d", F.OUT_AGREE_Y, slot_state=STATE_BOUGHT)] * 6
            + [_row("rs_leader", F.OUT_NA, mode="live")] * 3)
    t = {g["group"]: g for g in F.signal_table(rows)}
    ma20 = t["book_pullback_ma20"]
    assert (ma20["y_n"], ma20["y_rate"], ma20["n_n"], ma20["n_rate"]) == (10, 0.9, 0, None)
    assert ma20["verdict"] == "ok" and "N 방향 판정 불가" in ma20["verdict_note"] and ma20["reasons_eq"] == 9
    day = t["daytrading_3methods_breakout"]
    assert day["n_rate"] == pytest.approx(5 / 7) and day["verdict"] == "LOW"            # N 방향 71% < 90%
    env = t["book_envelope_200d"]
    assert env["bought"] == 6 and env["evaluable"] == 6 and env["verdict"] == "ok"     # 전부 bought = 자명한 Y/Y
    assert t["rs_leader[live]"]["evaluable"] == 0 and t["rs_leader[live]"]["verdict"] == "판정 불가"


def test_signal_table_other_outcome_key():
    rows = [dict(strategy="a", mode="", outcome=F.OUT_NA, outcome_v1=F.OUT_AGREE_N, slot_state=STATE_SLOT)] * 5
    assert F.signal_table(rows)[0]["evaluable"] == 0
    assert F.signal_table(rows, outcome_key="outcome_v1")[0]["agree_N"] == 5


# ── «평가 가능» 규칙 — 반례: ma5 09-11 006910 형(빈자리 09:00:00~09:28:07 · 첫 신호 09:03:37) ──
D = date(2026, 9, 11)
UPPER = Trade(buy_id=1, code="A00001", buy_ts=datetime(2026, 9, 11, 9, 28, 7), buy_price=100.0)   # 앞 순위가 마지막 자리를 채움
ORDER = ["A00001", "006910"]


def test_slot_verdict_v3_reopens_when_on_tick_finished_inside_free_window():
    v = F.slot_verdict([UPPER], D, 1, 5, "006910", ORDER, ["09:03:37", "09:30:00"])
    assert v.state_v2 == STATE_NO_SLOT            # v2: 모든 빈자리가 앞 순위 매수로 닫힘
    assert v.state == STATE_SLOT                  # v3: 빈자리 동안 on_tick 이 끝났다 → 평가됐다
    assert v.eval_v1 is True and "09:03:37" in v.note


def test_slot_verdict_v3_keeps_no_slot_without_on_tick_in_window():
    v = F.slot_verdict([UPPER], D, 1, 5, "006910", ORDER, ["09:28:30", "09:30:00"])   # 소진 뒤에야 끝남
    assert v.state_v2 == STATE_NO_SLOT and v.state == STATE_NO_SLOT


def test_slot_verdict_never_free_and_held():
    old = Trade(buy_id=2, code="000002", buy_ts=datetime(2026, 9, 10, 9, 5), buy_price=10.0)   # 전날부터 K=1 채움
    v = F.slot_verdict([old], D, 1, 5, "006910", ["006910"], ["09:03:00"])
    assert v.state == STATE_NO_SLOT and v.eval_v1 is False
    mine = Trade(buy_id=3, code="006910", buy_ts=datetime(2026, 9, 10, 9, 5), buy_price=10.0)
    assert F.slot_verdict([mine], D, 5, 5, "006910", ["006910"], ["09:03:00"]).state == STATE_HELD


# ── A2(critic 2차): 요약 줄은 on_tick «끝»에 찍힌다(base.py:763-766 · 매도 루프 뒤) ─────────────────
#    장중 매도가 연 빈자리(10:00:00~10:20:00) — 그 매도가 «요약 줄을 낸 on_tick» 자신의 매도 루프였다면
#    매수 루프는 빈자리가 열리기 전에 돌았다. 직전 요약이 구간 시작 이후일 때만(= on_tick 전체가 구간 안) 인정.
SOLD = Trade(buy_id=4, code="000004", buy_ts=datetime(2026, 9, 10, 9, 5), buy_price=10.0,
             sell_ts=datetime(2026, 9, 11, 10, 0, 0), sell_price=11.0)                   # K=1 을 채우다 10:00:00 매도
FILLER = Trade(buy_id=5, code="A00001", buy_ts=datetime(2026, 9, 11, 10, 20, 0), buy_price=100.0)   # 앞 순위가 닫음


def test_slot_verdict_a2_first_summary_after_window_start_not_accepted():
    for times in (["09:59:50", "10:00:05", "10:25:00"],      # 직전 요약 09:59:50 < 구간 시작 → 매수 루프는 구간 밖일 수 있다
                  ["10:00:05", "10:25:00"]):                 # 직전 요약 없음 → 하한 = 장 시작 09:00:00 < 구간 시작
        v = F.slot_verdict([SOLD, FILLER], D, 1, 5, "006910", ORDER, times)
        assert v.state_v2 == STATE_NO_SLOT and v.state == STATE_NO_SLOT, times
        assert "10:00:00-10:20:00" in v.note


def test_slot_verdict_a2_two_summaries_inside_window_accepted():
    v = F.slot_verdict([SOLD, FILLER], D, 1, 5, "006910", ORDER, ["09:59:50", "10:00:05", "10:05:00", "10:25:00"])
    assert v.state_v2 == STATE_NO_SLOT and v.state == STATE_SLOT
    assert "10:05:00" in v.note and "10:00:05" in v.note           # 인정된 on_tick = 10:00:05~10:05:00


def test_slot_verdict_a2_previous_summary_at_window_start_is_inside():
    v = F.slot_verdict([SOLD, FILLER], D, 1, 5, "006910", ORDER, ["10:00:00", "10:05:00"])   # 경계 = 「이후」에 포함
    assert v.state == STATE_SLOT


def test_day_volume_vintage_and_fragile_direction():
    assert F.day_volume_vintage("breakout vol=100/10", "breakout vol=124/10") == pytest.approx(0.24)
    assert F.day_volume_vintage("", "vol=1/1") is None
    # daytrading(bias Y): 재현 Y 비율 2.2 · 문턱 2.0 · vmax 24.3% → 라이브 최소 1.77 < 2.0 → 취약
    assert F.vintage_fragile("Y", "Y", 2.2, 2.0, 0.243) == "Y"
    assert F.vintage_fragile("Y", "Y", 3.0, 2.0, 0.243) == "N"
    assert F.vintage_fragile("Y", "N", 1.5, 2.0, 0.243) == "N"      # 재기록은 N 을 Y 로 만들지 못한다
    # minervini(bias N): 재현 N 비율 0.80 · 문턱 0.70 → 라이브 최소 0.644 ≤ 0.70 → 취약
    assert F.vintage_fragile("N", "N", 0.80, 0.70, 0.243) == "Y"
    assert F.vintage_fragile("N", "Y", 0.60, 0.70, 0.243) == "N"
    assert F.vintage_fragile(None, "Y", 2.2, 2.0, 0.243) == "" and F.vintage_fragile("Y", "Y", None, 2.0, 0.2) == ""


# ── 청산·익절손절·진입가 ────────────────────────────────────────────────────
def test_actual_reason_mapping():
    assert F.actual_reason("목표 익절 도달 (10.12% >= 10.00%)") == "tp"
    assert F.actual_reason("손절 실행 (-8.10% <= -8.00%)") == "sl"
    assert F.actual_reason("보유기간 10일 초과 (한도: 10일)") == "max_hold"
    assert F.actual_reason("최대 보유일 초과 (10거래일)") == "max_hold"
    assert F.actual_reason("EMA13 trailing 이탈 (종가 1 < EMA13 2)") == "trail_ema"
    assert F.actual_reason("EMA65 추세반전 청산") == "trend_flip"
    assert F.actual_reason("MA20 trailing 이탈 (종가 1 < MA20 2)") == "trail_ma"
    assert F.actual_reason("MA20×0.9 회복 (종가 1 ≥ 2)") == "ma_recovery"
    assert F.actual_reason("MA20 이탈 (종가 1 < MA 2)") == "ma_break"
    assert F.actual_reason("장기보유 종목 우선 청산: 수익률 1.00% (보유 31일)") == "stale"
    assert F.actual_reason("알 수 없는 사유") == "other:알 수 없는 사유"


def test_exit_outcome():
    d1, d2 = date(2026, 9, 11), date(2026, 9, 14)
    assert F.exit_outcome("tp", d1, "tp", d1) == "Y"
    assert F.exit_outcome("tp", d1, "tp", d2) == "reason_only"
    assert F.exit_outcome("sl", d1, "tp", d1) == "N"
    assert F.exit_outcome("sl", d1, "open", None) == "actual_only_closed"
    assert F.exit_outcome("open", None, "sl", d1) == "sim_only_closed"
    assert F.exit_outcome("open", None, "open", None) == "both_open"


def test_exit_table_denominator_is_actual_closed():
    rows = ([dict(strategy="rs_leader", outcome="Y", actual_reason="ma_break", same_day_actual="N")] * 6
            + [dict(strategy="rs_leader", outcome="actual_only_closed", actual_reason="sl", same_day_actual="Y")] * 2
            + [dict(strategy="rs_leader", outcome="both_open", actual_reason="open", same_day_actual="")] * 3)
    t = F.exit_table(rows)[0]
    assert (t["closed"], t["Y"], t["same_day"]) == (8, 6, 2)
    assert t["reason_rate"] == 0.75 and t["verdict"] == "ok"


def test_tp_sl_table_and_entry_diff_stats():
    rows = [dict(strategy="book_pullback_ma5", tp_sl_match="Y")] * 3 + [dict(strategy="book_pullback_ma5", tp_sl_match="N")]
    t = F.tp_sl_table(rows)[0]
    assert (t["n"], t["match"]) == (4, 3)
    e = {g["strategy"]: g for g in F.entry_diff_stats([
        dict(strategy="a", entry_diff_pct="+1.00", first_tick="Y"),
        dict(strategy="a", entry_diff_pct="-0.50", first_tick="N"),
        dict(strategy="a", entry_diff_pct="", first_tick="N")])}
    assert e["a"]["n"] == 2 and e["a"]["positive"] == 1 and e["a"]["signed_mean"] == pytest.approx(0.25)
    assert e["a"]["signed_mean_first"] == pytest.approx(1.0) and e["(전체)"]["n"] == 2
