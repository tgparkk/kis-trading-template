"""exitsim8 — 하루 청산 순서(보유기간 → 갭 익절 → 데이터 청산 → 갭 손절 → 터치) · 평단 이동 · 09:05 플래그."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar

R10 = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=5, source="test")
DAYS = [date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 14), date(2026, 9, 15),
        date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)]
FLAT = (100.0, 101.0, 99.0, 100.0)


def _pos(price: float = 100.0, basis: str = X.BASIS_D_OPEN) -> X.Pos:
    return X.Pos("000001", DAYS[0], datetime(2026, 9, 10, 9, 2), price, 10, basis)


def _path(*ohlc):
    return [(i, DAYS[i], None if b is None else Bar(DAYS[i], *b)) for i, b in enumerate(ohlc)]


def _no_probe(pos, day):
    return None


def _probe_on(hit_day, reason="trail_ma"):
    return lambda pos, day: reason if day == hit_day else None


def test_open_position_marks_to_last_close():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, FLAT, FLAT), _no_probe)
    assert ex.status == "open" and ex.reason == X.EXIT_OPEN and ex.exit_date == DAYS[2]
    assert ex.ret_pct == 0.0 and ex.hold_days == 2 and X.FLAG_MTM in ex.flags


def test_data_exit_sells_at_that_day_open():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, FLAT, (103.0, 104.0, 102.0, 103.0)), _probe_on(DAYS[2]))
    assert (ex.reason, ex.exit_date, ex.price, ex.hold_days) == ("trail_ma", DAYS[2], 103.0, 2)


def test_gap_tp_beats_data_exit():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, (111.0, 112.0, 110.0, 111.0)), _probe_on(DAYS[1]))
    assert ex.reason == X.EXIT_TP and ex.price == 111.0 and X.FLAG_GAP_TP in ex.flags


def test_max_hold_comes_first_at_open():
    path = _path(FLAT, FLAT, FLAT, FLAT, FLAT, (120.0, 121.0, 119.0, 120.0))   # k=5 시가 +20%
    ex = X.simulate_lot(_pos(), R10, path, _no_probe)
    assert ex.reason == X.EXIT_MAX_HOLD and ex.hold_days == 5 and ex.price == 120.0


def test_gap_down_sl_flags_0905():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, (90.0, 91.0, 89.0, 90.0)), _no_probe)
    assert ex.reason == X.EXIT_SL and ex.price == 90.0 and X.FLAG_SL_GAP_0905 in ex.flags


def test_same_bar_touch_prefers_sl():
    ex = X.simulate_lot(_pos(), R10, _path(FLAT, (100.0, 111.0, 91.0, 100.0)), _no_probe)
    assert ex.reason == X.EXIT_SL and ex.price == pytest.approx(92.0) and X.FLAG_SL_TP_BOTH in ex.flags


def test_average_price_moves_the_stop():
    path = _path(FLAT, (96.0, 97.0, 91.0, 95.0))
    assert X.simulate_lot(_pos(100.0), R10, path, _no_probe).reason == X.EXIT_SL   # 100×0.92=92 ≥ 91
    assert X.simulate_lot(_pos(98.0), R10, path, _no_probe).status == "open"        # 98×0.92=90.16 < 91


def test_d_open_entry_day_uses_day_touches():
    ex = X.simulate_lot(_pos(), R10, _path((100.0, 101.0, 91.0, 95.0)), _no_probe)
    assert ex.reason == X.EXIT_SL and ex.hold_days == 0


def test_band_touch_skips_entry_day_touches_but_probes():
    path = _path((100.0, 112.0, 90.0, 100.0), FLAT)
    ex = X.simulate_lot(_pos(basis=X.BASIS_BAND), R10, path, _no_probe)
    assert ex.status == "open" and X.FLAG_NO_D_TOUCH in ex.flags
    ex2 = X.simulate_lot(_pos(basis=X.BASIS_BAND), R10, path, _probe_on(DAYS[0]))
    assert (ex2.reason, ex2.hold_days, ex2.price) == ("trail_ma", 0, 100.0) and X.FLAG_K0_DATA in ex2.flags


def test_missing_bar_defers_max_hold():
    rules = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=2)
    ex = X.simulate_lot(_pos(), rules, _path(FLAT, FLAT, None, (101.0, 102.0, 100.0, 101.0)), _no_probe)
    assert ex.reason == X.EXIT_MAX_HOLD and ex.exit_date == DAYS[3] and X.FLAG_MAXHOLD_DEFERRED in ex.flags


def test_after_open_can_skip_touches():
    bar = Bar(DAYS[1], 100.0, 100.5, 85.0, 90.0)
    assert X.after_open(_pos(), R10, 1, DAYS[1], bar, _no_probe, touches=False) is None
    assert X.after_open(_pos(), R10, 1, DAYS[1], bar, _no_probe, touches=True).reason == X.EXIT_SL


def test_exit_phase_labels():
    assert X.simulate_lot(_pos(), R10, _path(FLAT, (111.0, 112.0, 110.0, 111.0)), _no_probe).phase == X.PHASE_OPEN
    assert X.simulate_lot(_pos(), R10, _path(FLAT, (90.0, 91.0, 89.0, 90.0)), _no_probe).phase == X.PHASE_AFTER
    assert X.simulate_lot(_pos(), R10, _path((100.0, 101.0, 91.0, 95.0)), _no_probe).phase == X.PHASE_ENTRY


def _mins(*rows):
    return [(t, Bar(DAYS[0], float(o), float(h), float(lo), float(c))) for t, o, h, lo, c in rows]


def test_lift_entry_first_in_band_minute_after_lift():
    mins = _mins(("09:23:00", 100, 100, 99, 100), ("09:24:00", 105, 105, 102, 104),
                 ("09:25:00", 103, 104, 101, 102), ("09:26:00", 101, 102, 95, 96))
    le = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0)
    # 09:23 봉은 해제 전 · 09:24 시가 105 > 상한 103 이나 저가 102 ≤ 103 → 경계 103 · 터치 봉은 다음 분봉(09:25)부터
    assert (le.status, le.price, le.time, le.basis) == (X.LIFT_FILLED, 103.0, "09:24:00", "minute_band_touch")
    tb = le.touch_bar
    assert (tb.open, tb.high, tb.low, tb.close) == (103.0, 104.0, 95.0, 96.0)


def test_lift_entry_statuses():
    above = _mins(("09:30:00", 110, 111, 109, 110))
    assert X.lift_entry(DAYS[0], above, "09:23:09", None, 103.0).status == X.LIFT_UNFILLABLE
    assert X.lift_entry(DAYS[0], [], "09:23:09", None, 103.0).status == X.LIFT_NO_MINUTE
    assert X.lift_entry(DAYS[0], above, "", None, 103.0).status == X.LIFT_NOT_LIFTED


def test_lift_entry_db_minutes_with_colon_lift():
    # minute_candles.time = 'HHMMSS'(DB) · 해제 시각 = 'HH:MM:SS'(로그) — 섞여도 같은 판정
    mins = _mins(("092300", 100, 100, 99, 100), ("092400", 105, 105, 102, 104),
                 ("092500", 103, 104, 101, 102), ("092600", 101, 102, 95, 96))
    le = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0)
    assert (le.status, le.price, le.time, le.basis) == (X.LIFT_FILLED, 103.0, "09:24:00", "minute_band_touch")
    assert (le.touch_bar.open, le.touch_bar.high, le.touch_bar.low, le.touch_bar.close) == (103.0, 104.0, 95.0, 96.0)


def test_lift_entry_colon_minutes_with_db_lift_never_fills_before_lift():
    mins = _mins(("09:23:00", 100, 100, 99, 100), ("09:24:00", 105, 105, 102, 104),
                 ("09:25:00", 103, 104, 101, 102))
    le = X.lift_entry(DAYS[0], mins, "092309", None, 103.0)          # 09:23:00 봉(시가 100 · 밴드 안)은 해제 전
    assert (le.status, le.price, le.time) == (X.LIFT_FILLED, 103.0, "09:24:00")


def test_lift_entry_minute_boundary():
    mins = _mins(("092300", 100, 100, 99, 100), ("092400", 101, 102, 100, 101), ("092500", 101, 103, 98, 99))
    le = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0)         # 092300 봉 시작 < 해제 → 안 씀 · 092400 → 씀
    assert (le.status, le.price, le.time, le.basis) == (X.LIFT_FILLED, 101.0, "09:24:00", "minute_open")
    assert (le.touch_bar.high, le.touch_bar.low) == (103.0, 98.0)
    assert X.lift_entry(DAYS[0], mins, "09:24:00", None, 103.0).time == "09:24:00"   # 봉 시작 = 해제 → 씀
    assert X.lift_entry(DAYS[0], mins, "9:23:09", None, 103.0).time == "09:24:00"    # H:MM:SS
    assert X.lift_entry(DAYS[0], _mins(("92400", 101, 102, 100, 101)), "92309", None, 103.0).time == "09:24:00"


def test_lift_entry_rejects_unknown_time_format():
    with pytest.raises(ValueError):
        X.lift_entry(DAYS[0], _mins(("09:24", 101, 102, 100, 101)), "09:23:09", None, 103.0)
    with pytest.raises(ValueError):
        X.lift_entry(DAYS[0], _mins(("092400", 101, 102, 100, 101)), "9h23", None, 103.0)


def test_after_lift_entry_day_uses_post_entry_bar_only():
    tb = Bar(DAYS[0], 100.0, 101.0, 91.0, 95.0)          # 진입 뒤 저가 91 → 손절
    day_bar = (98.0, 101.0, 80.0, 95.0)                    # 일봉 저가 80 은 진입 «전» 일 수 있다 — 쓰면 안 된다
    pos = X.Pos("000001", DAYS[0], datetime(2026, 9, 10, 9, 24), 100.0, 10, X.BASIS_LIFT, touch_bar=tb)
    ex = X.simulate_lot(pos, R10, _path(day_bar), _no_probe)
    assert (ex.reason, ex.hold_days, ex.phase) == (X.EXIT_SL, 0, X.PHASE_ENTRY) and ex.price == pytest.approx(92.0)
    pos2 = X.Pos("000001", DAYS[0], datetime(2026, 9, 10, 9, 24), 100.0, 10, X.BASIS_LIFT)
    assert X.simulate_lot(pos2, R10, _path(day_bar), _no_probe).status == "open"


# ── A3(critic 2차 · 사장님 승인) — 분봉이 없는 해제 뒤 진입(LIFT_NO_MINUTE)은 「모른다」 · 상한 민감도 진입 ──

def test_lift_no_minute_is_unknown_not_unfillable():
    le = X.lift_entry(DAYS[0], [], "09:23:09", 95.0, 103.0)
    assert le.status == X.LIFT_NO_MINUTE and le.status != X.LIFT_UNFILLABLE and le.price is None


def test_lift_upper_bound_close_inside_band_uses_close():
    le = X.lift_upper_bound(Bar(DAYS[0], 105.0, 106.0, 97.0, 101.0), 95.0, 103.0)
    assert (le.status, le.price, le.basis, le.time, le.touch_bar) == (X.LIFT_FILLED, 101.0, X.BASIS_UPPER, "", None)
    # 한쪽 경계만 있는 밴드(하한 없음)
    assert X.lift_upper_bound(Bar(DAYS[0], 105.0, 106.0, 97.0, 101.0), None, 103.0).price == 101.0


def test_lift_upper_bound_close_outside_band_uses_nearest_bound():
    above = X.lift_upper_bound(Bar(DAYS[0], 100.0, 110.0, 99.0, 108.0), 95.0, 103.0)   # 종가 108 > 상한
    assert (above.status, above.price) == (X.LIFT_FILLED, 103.0)
    below = X.lift_upper_bound(Bar(DAYS[0], 100.0, 101.0, 90.0, 92.0), 95.0, 103.0)    # 종가 92 < 하한
    assert (below.status, below.price) == (X.LIFT_FILLED, 95.0)
    # 경계 포함 — 저가가 상한과 같으면 겹친 것
    assert X.lift_upper_bound(Bar(DAYS[0], 110.0, 111.0, 103.0, 109.0), None, 103.0).price == 103.0


def test_lift_upper_bound_no_overlap_or_no_bar_is_not_filled():
    assert X.lift_upper_bound(Bar(DAYS[0], 110.0, 111.0, 104.0, 110.0), 95.0, 103.0).status == X.LIFT_UNFILLABLE
    assert X.lift_upper_bound(Bar(DAYS[0], 90.0, 94.0, 89.0, 93.0), 95.0, 103.0).status == X.LIFT_UNFILLABLE
    none = X.lift_upper_bound(None, 95.0, 103.0)
    assert none.status == X.LIFT_NO_BAR and none.price is None


def test_lift_upper_bound_entry_day_touches_not_used():
    le = X.lift_upper_bound(Bar(DAYS[0], 100.0, 101.0, 80.0, 100.0), None, 103.0)       # 진입일 저가 80 = −20%
    pos = X.Pos("000001", DAYS[0], datetime(2026, 9, 10, 9, 24), le.price, 10, X.BASIS_LIFT, touch_bar=le.touch_bar)
    ex = X.simulate_lot(pos, R10, _path((100.0, 101.0, 80.0, 100.0)), _no_probe)
    assert ex.status == "open" and X.FLAG_NO_D_TOUCH in ex.flags


# ── 과제 9 I1 — 게이트가 «열려 있는» 구간(재차단 제외)에서만 진입 · 터치는 진입 뒤 전 분봉 ─────────────────────────
REBLOCK = [("09:23:09", "09:33:50"), ("09:35:03", "")]   # 09-11 형: 해제 → 재차단 → 재해제


def test_lift_entry_skips_bars_inside_a_reblocked_window():
    mins = _mins(("09:24:00", 110, 111, 109, 110),        # 열림 · 밴드 밖
                 ("09:34:00", 101, 102, 100, 101),        # 재차단 구간 안 · 밴드 안 → 안 씀
                 ("09:35:00", 101, 102, 100, 101),        # 봉 시작 < 재해제 09:35:03 → 안 씀(해제 경계 규칙 그대로)
                 ("09:36:00", 102, 102.5, 101, 102))      # 다시 열림 · 밴드 안 → 씀
    le = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0, REBLOCK)
    assert (le.status, le.price, le.time, le.basis, le.window) == \
        (X.LIFT_FILLED, 102.0, "09:36:00", "minute_open", "09:35:03~")
    old = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0)           # 첫 해제만 보면 재차단 구간에서 샀다
    assert (old.time, old.window) == ("09:34:00", "09:23:09~")


def test_lift_entry_window_end_is_exclusive_and_mixed_formats():
    mins = _mins(("093350", 101, 102, 100, 101), ("093400", 101, 102, 100, 101))
    wins = [("092309", "09:33:50"), ("09:34:00", "")]
    le = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0, wins)     # 09:33:50 시작 = 재차단 시각 → 안 씀
    assert (le.time, le.window) == ("09:34:00", "09:34:00~")
    closed = X.lift_entry(DAYS[0], _mins(("09:40:00", 101, 102, 100, 101)), "09:23:09", None, 103.0,
                          [("09:23:09", "09:33:50")])                    # 열린 구간 안 분봉 0개 → 모른다(A3 · 최종 검수 #15)
    assert closed.status == X.LIFT_NO_MINUTE
    assert X.lift_entry(DAYS[0], mins, "", None, 103.0, []).status == X.LIFT_NOT_LIFTED


def test_lift_entry_minutes_outside_every_open_window_is_unknown_not_unfillable():
    """최종 검수 #15(A3) — 분봉은 있는데 열린 구간 안(해제 뒤)에서 시작하는 봉이 하나도 없으면 해제 뒤 가격을 «못 본» 것
    = `LIFT_NO_MINUTE`(모른다). `LIFT_UNFILLABLE` 은 «구간 안 봉은 있는데 밴드 안이 없다» 뿐이다."""
    before_lift = _mins(("09:20:00", 101, 102, 100, 101), ("09:23:00", 101, 102, 100, 101))   # 전부 해제(09:23:09) 전
    assert X.lift_entry(DAYS[0], before_lift, "09:23:09", None, 103.0).status == X.LIFT_NO_MINUTE
    in_reblock_only = _mins(("09:34:00", 101, 102, 100, 101), ("09:35:00", 101, 102, 100, 101))  # 재차단 구간 안뿐
    assert X.lift_entry(DAYS[0], in_reblock_only, "09:23:09", None, 103.0, REBLOCK).status == X.LIFT_NO_MINUTE
    out_of_band = in_reblock_only + _mins(("09:36:00", 110, 111, 109, 110))                  # 구간 안 봉 · 밴드 밖
    assert X.lift_entry(DAYS[0], out_of_band, "09:23:09", None, 103.0, REBLOCK).status == X.LIFT_UNFILLABLE


def test_lift_entry_touches_after_entry_use_all_minutes_even_when_reblocked():
    """청산은 게이트가 막지 않는다 — 진입 뒤 터치 봉은 재차단 구간 분봉까지 전부 모은다."""
    mins = _mins(("09:24:00", 101, 102, 100, 101),        # 열림 · 진입(minute_open)
                 ("09:31:00", 100, 100, 80, 85),          # 재차단 구간 — 저가 80 은 터치에 들어가야 한다
                 ("09:41:00", 90, 95, 88, 94))
    le = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0, [("09:23:09", "09:30:00"), ("09:40:00", "")])
    assert (le.time, le.window) == ("09:24:00", "09:23:09~09:30:00")
    assert (le.touch_bar.open, le.touch_bar.high, le.touch_bar.low, le.touch_bar.close) == (101.0, 102.0, 80.0, 94.0)


def test_lift_entry_default_equals_single_open_ended_window():
    mins = _mins(("09:23:00", 100, 100, 99, 100), ("09:24:00", 105, 105, 102, 104),
                 ("09:25:00", 103, 104, 101, 102), ("09:26:00", 101, 102, 95, 96))
    a = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0)
    b = X.lift_entry(DAYS[0], mins, "09:23:09", None, 103.0, [("09:23:09", "")])
    assert a == b and a.window == "09:23:09~"
