"""가상 진입·청산 — 밴드 판정 · 손절 우선 · 갭 · 보유기한."""
from datetime import date

import pytest

from backtest.concept_axes.minervini.cap_skip_ledger import sim as S

D = date(2026, 9, 16)


def _bar(day, o, h, lo, c):
    return S.Bar(date(2026, 9, day), o, h, lo, c)


def _never(_k):
    return False


def _later(*bars):
    return [(i + 1, b) for i, b in enumerate(bars)]


# ── 진입 ─────────────────────────────────────────────────────────────────
def test_entry_open_inside_band():
    e = S.simulate_entry(_bar(16, 100, 104, 98, 101), None, 103.0)
    assert (e.status, e.price, e.basis) == (S.ENTRY_FILLED, 100, "D_open")


def test_entry_band_touch_after_gap_up():
    e = S.simulate_entry(_bar(16, 105, 106, 102, 104), None, 103.0)
    assert (e.status, e.price, e.basis) == (S.ENTRY_FILLED, 103.0, "band_touch")


def test_entry_unfillable_all_day_above_band():
    e = S.simulate_entry(_bar(16, 105, 110, 104, 108), None, 103.0)
    assert e.status == S.ENTRY_UNFILLABLE


def test_entry_no_bar():
    assert S.simulate_entry(None, None, 103.0).status == S.ENTRY_NO_BAR


# ── 청산: 손절 우선 ───────────────────────────────────────────────────────
def test_same_bar_both_hit_stop_loss_first():
    # entry 100 · sl 92 · tp 112 · D+1 봉이 91~113 → 순서 불명 → 손절
    ex = S.simulate_exit(100.0, "D_open", _bar(16, 100, 101, 99, 100),
                         _later(_bar(17, 100, 113, 91, 105)), 0.08, 0.12, _never)
    assert ex.reason == S.EXIT_SL and ex.price == pytest.approx(92.0)
    assert ex.ret_pct == pytest.approx(-8.0) and ex.hold_days == 1
    assert any("손절 우선" in n for n in ex.notes)


def test_entry_day_both_hit_stop_loss_first():
    ex = S.simulate_exit(100.0, "D_open", _bar(16, 100, 112.5, 91.5, 100), [], 0.08, 0.12, _never)
    assert ex.reason == S.EXIT_SL and ex.hold_days == 0


def test_tp_only():
    ex = S.simulate_exit(100.0, "D_open", _bar(16, 100, 101, 99, 100),
                         _later(_bar(17, 101, 112.0, 99, 111)), 0.08, 0.12, _never)
    assert ex.reason == S.EXIT_TP and ex.price == pytest.approx(112.0)


def test_gap_up_open_above_tp_is_tp_at_open_even_if_low_breaks_sl():
    # 시가가 첫 가격이라 순서가 확실하다 — 익절(시가)
    ex = S.simulate_exit(100.0, "D_open", _bar(16, 100, 101, 99, 100),
                         _later(_bar(17, 115, 116, 90, 95)), 0.08, 0.12, _never)
    assert ex.reason == S.EXIT_TP and ex.price == 115


def test_gap_down_open_below_sl_is_sl_at_open():
    ex = S.simulate_exit(100.0, "D_open", _bar(16, 100, 101, 99, 100),
                         _later(_bar(17, 89, 95, 88, 94)), 0.08, 0.12, _never)
    assert ex.reason == S.EXIT_SL and ex.price == 89 and ex.ret_pct == pytest.approx(-11.0)


def test_band_touch_skips_entry_day_range():
    # 진입 시각 불명 → D 당일 저가 90 은 쓰지 않는다
    ex = S.simulate_exit(103.0, "band_touch", _bar(16, 105, 106, 90, 104),
                         _later(_bar(17, 104, 105, 100, 104)), 0.08, 0.12, _never)
    assert ex.status == "open" and ex.reason == S.EXIT_OPEN


def test_max_hold_exits_at_open_before_tp_sl():
    bars = [_bar(17, 100, 101, 99, 100)] * 3
    ex = S.simulate_exit(100.0, "D_open", _bar(16, 100, 101, 99, 100),
                         _later(*bars), 0.08, 0.12, lambda k: k >= 3)
    assert ex.reason == S.EXIT_MAX_HOLD and ex.hold_days == 3 and ex.price == 100


def test_open_position_marks_to_last_close():
    ex = S.simulate_exit(100.0, "D_open", _bar(16, 100, 101, 99, 100),
                         _later(_bar(17, 100, 104, 98, 103)), 0.08, 0.12, _never)
    assert ex.status == "open" and ex.ret_pct == pytest.approx(3.0) and ex.hold_days == 1


def test_missing_bar_on_max_hold_day_defers_to_next_bar():
    ex = S.simulate_exit(100.0, "D_open", _bar(16, 100, 101, 99, 100),
                         [(1, None), (2, _bar(18, 97, 99, 96, 98))], 0.08, 0.12, lambda k: k >= 1)
    assert ex.reason == S.EXIT_MAX_HOLD and ex.price == 97
