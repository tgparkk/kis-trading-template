"""arms — B1 로트 독립 · B2 평단 합산(추가매수 · 새 계좌 · 시계 리셋 · band_touch 추가) · 원 정수 · A_actual."""
from __future__ import annotations

from datetime import date, datetime, time

import pytest

from backtest.concept_axes.ledger8 import arms as A
from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import fidelity8 as F
from backtest.concept_axes.minervini.cap_skip_ledger.classify import Trade
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar

FOLDER = "book_pullback_ma20"
DAYS = [date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 14), date(2026, 9, 15),
        date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)]
RULES = {FOLDER: X.ExitRules(tp=0.10, sl=0.08, max_hold_days=50)}


def _bar(i, o, h, lo, c):
    return Bar(DAYS[i], float(o), float(h), float(lo), float(c))


def _path_fn(bars):
    def fn(code, d):
        i0 = DAYS.index(d)
        return [(k, dd, bars.get(dd)) for k, dd in enumerate(DAYS[i0:])]
    return fn


def _time(d):
    return datetime.combine(d, time(9, 2))


def _no_probe(folder):
    return lambda pos, day: None


def _fill(i, price, qty=10, basis=X.BASIS_D_OPEN):
    return A.Fill(FOLDER, "000001", DAYS[i], float(price), basis, qty, "amount")


# 첫 로트(100)는 3일째 손절(100×0.92=92 ≥ 저가 89), 합산 평단 96.5 는 버틴다(96.5×0.92=88.78 < 89)
BARS = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 93, 94, 92.5, 93), DAYS[2]: _bar(2, 94, 95, 89, 90)}


def test_b1_lots_are_independent():
    first, second = A.run_lots([_fill(0, 100), _fill(1, 93)], RULES, _path_fn(BARS), _no_probe, DAYS, _time, "B1")
    assert first.exit.reason == X.EXIT_SL and first.exit.exit_date == DAYS[2]
    assert second.exit.status == "open"                                   # 93×0.92=85.56 < 89
    assert (second.is_repeat_while_open, second.open_lot_seq, second.days_since_open_lot) == (True, 2, 1)
    assert (first.is_repeat_while_open, first.open_lot_seq, first.days_since_open_lot) == (False, 1, None)
    assert first.pnl_won == -80 and first.notional_won == 1000


def test_b2_averages_and_holds_where_b1_first_lot_stopped():
    fills = [_fill(0, 100), _fill(1, 93)]
    accts = A.run_accounts(fills, RULES, _path_fn(BARS), _no_probe, _time)
    assert len(accts) == 1
    a = accts[0]
    assert a.n_adds == 1 and a.qty == 20 and a.avg_price == pytest.approx(96.5)
    assert a.avg_path == [100.0, pytest.approx(96.5)]
    assert a.exit.status == "open"
    A.mark_avg_flip(accts, A.run_lots(fills, RULES, _path_fn(BARS), _no_probe, DAYS, _time, "B1"))
    assert a.avg_flip == "reason:sl→open"


def test_b2_new_account_after_full_exit_same_day():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 111, 112, 110, 111)}
    accts = A.run_accounts([_fill(0, 100), _fill(1, 111)], RULES, _path_fn(bars), _no_probe, _time)
    assert len(accts) == 2
    assert (accts[0].exit.reason, accts[0].exit.exit_date, accts[0].n_adds) == (X.EXIT_TP, DAYS[1], 0)
    assert accts[1].first_date == DAYS[1] and accts[1].avg_price == 111.0


def test_hold_clock_reset_changes_max_hold_day():
    flat = {d: Bar(d, 100.0, 101.0, 99.0, 100.0) for d in DAYS}
    rules = {FOLDER: X.ExitRules(tp=0.10, sl=0.08, max_hold_days=2)}
    fills = [_fill(0, 100), _fill(1, 100)]
    first = A.run_accounts(fills, rules, _path_fn(flat), _no_probe, _time, A.CLOCK_FIRST)
    reset = A.run_accounts(fills, rules, _path_fn(flat), _no_probe, _time, A.CLOCK_LAST_ADD)
    assert first[0].exit.exit_date == DAYS[2] and reset[0].exit.exit_date == DAYS[3]
    A.mark_clock_diff(first, reset)
    assert first[0].hold_clock_reset_diff == f"diff:max_hold@{DAYS[3]}"


def test_band_touch_add_skips_that_day_touches():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 95, 96, 85, 90)}
    accts = A.run_accounts([_fill(0, 100), _fill(1, 96, basis=X.BASIS_BAND)], RULES, _path_fn(bars), _no_probe, _time)
    assert accts[0].exit.status == "open"
    assert any(fl.startswith(X.FLAG_TOUCH_SKIPPED_ADD) for fl in accts[0].flags)


def test_a_actual_rows():
    closed = Trade(buy_id=1, code="000001", buy_ts=datetime(2026, 9, 10, 9, 3), buy_price=100.0,
                   sell_ts=datetime(2026, 9, 11, 9, 1), sell_price=110.0, sell_reason="목표 익절 도달 (10.00% >= 10.00%)")
    held = Trade(buy_id=2, code="000002", buy_ts=datetime(2026, 9, 11, 9, 4), buy_price=50.0)
    old = Trade(buy_id=3, code="000003", buy_ts=datetime(2026, 9, 1, 9, 4), buy_price=10.0)
    rows = A.a_actual({FOLDER: [closed, held, old]}, lambda i: {1: 10, 2: 20, 3: 5}[i], DAYS,
                      lambda code: (DAYS[-1], 55.0), F.actual_reason)
    assert [r.trade.buy_id for r in rows] == [1, 2]
    assert (rows[0].exit_status, rows[0].exit_reason, rows[0].pnl_won, rows[0].notional_won) == ("closed", "tp", 100, 1000)
    assert (rows[1].exit_status, rows[1].exit_price, rows[1].pnl_won) == ("open", 55.0, 100)
    assert rows[1].ret_pct == pytest.approx(10.0)


def test_open_phase_exit_is_not_open_for_same_day_signal():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 111, 112, 110, 111)}   # 1일째 09:00 갭 익절
    fills = [_fill(0, 100), _fill(1, 111)]
    lots = A.run_lots(fills, RULES, _path_fn(bars), _no_probe, DAYS, _time, "B1")
    assert lots[0].exit.phase == X.PHASE_OPEN and lots[1].is_repeat_while_open is False
    accts = A.run_accounts(fills, RULES, _path_fn(bars), _no_probe, _time)
    assert sum(lot.is_repeat_while_open for lot in lots) == sum(a.n_adds for a in accts) == 0


def test_after_phase_exit_same_day_counts_as_open_like_b2_add():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 100, 101, 99, 100)}
    probe = lambda folder: (lambda pos, day: "trail_ma" if day == DAYS[1] else None)   # noqa: E731  1일째 09:02 데이터 청산
    fills = [_fill(0, 100), _fill(1, 100)]
    lots = A.run_lots(fills, RULES, _path_fn(bars), probe, DAYS, _time, "B1")
    accts = A.run_accounts(fills, RULES, _path_fn(bars), probe, _time)
    assert lots[1].is_repeat_while_open is True and len(accts) == 1 and accts[0].n_adds == 1


def test_lift_fill_uses_post_entry_bar_and_same_day_exit_comes_first():
    tb = Bar(DAYS[1], 100.0, 101.0, 91.0, 95.0)             # 해제 뒤 분봉만 모은 봉 — 저가 91
    lift = A.Fill(FOLDER, "000001", DAYS[1], 100.0, X.BASIS_LIFT, 10, "amount",
                  entry_time=datetime(2026, 9, 11, 9, 24), touch_bar=tb, lift_time="09:24:00")
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 100, 101, 80, 95)}
    probe = lambda folder: (lambda pos, day: "trail_ma" if (day == DAYS[1] and pos.entry_date == DAYS[0]) else None)  # noqa: E731
    fills = [_fill(0, 100), lift]
    lots = A.run_lots(fills, RULES, _path_fn(bars), probe, DAYS, _time, "B1")
    assert lots[0].exit.reason == "trail_ma" and lots[1].is_repeat_while_open is False
    assert (lots[1].exit.reason, lots[1].exit.hold_days) == (X.EXIT_SL, 0)      # 일봉 저가 80 이 아니라 진입 뒤 91
    accts = A.run_accounts(fills, RULES, _path_fn(bars), probe, _time)
    assert len(accts) == 2 and accts[1].fills[0].basis == X.BASIS_LIFT


# --- A3/A4 (critic 2차 검수 amendments) -------------------------------------------------------------
FLAT = {d: Bar(d, 100.0, 101.0, 99.0, 100.0) for d in DAYS}


def _upper(i, price, tier="lift_ub", lift_time="", entry_time=None):
    """A3 상한 민감도 체결 — 분봉 없는 해제 뒤 진입(시각 불명 · touch_bar 없음) · 본 집계 밖 tier."""
    return A.Fill(FOLDER, "000001", DAYS[i], float(price), X.BASIS_UPPER, 10, "amount", tier=tier,
                  crash_blocked=True, lift_time=lift_time, entry_time=entry_time)


def test_upper_bound_fill_ignores_entry_day_touches():
    bars = {DAYS[0]: _bar(0, 100, 101, 85, 90)}                     # D 저가 85 — D_open 이면 그날 손절(92)
    d_open, = A.run_lots([_fill(0, 100)], RULES, _path_fn(bars), _no_probe, DAYS, _time, "B1")
    assert (d_open.exit.reason, d_open.exit.exit_date) == (X.EXIT_SL, DAYS[0])
    lot, = A.run_lots([_upper(0, 100)], RULES, _path_fn(bars), _no_probe, DAYS, _time, "B1")
    assert lot.exit.status == "open" and X.FLAG_NO_D_TOUCH in lot.exit.flags
    acct, = A.run_accounts([_upper(0, 100)], RULES, _path_fn(bars), _no_probe, _time)
    assert acct.exit.status == "open" and X.FLAG_NO_D_TOUCH in acct.flags


def test_upper_bound_add_into_open_b2_account_sets_add_unknown():
    fills = [_fill(0, 100), _upper(1, 100)]                          # main 계좌 + 상한(tier=lift_ub) 추가
    accts = A.run_accounts(fills, RULES, _path_fn(FLAT), _no_probe, _time)
    assert len(accts) == 1 and accts[0].n_adds == 1 and accts[0].fills[1].tier == "lift_ub"
    assert f"{A.FLAG_ADD_UNKNOWN}:{DAYS[1]}" in accts[0].flags
    assert not any(fl.startswith(X.FLAG_LIFT_ADD) for fl in accts[0].flags)
    lots = A.run_lots(fills, RULES, _path_fn(FLAT), _no_probe, DAYS, _time, "B1")
    assert lots[1].is_repeat_while_open is True and lots[1].fill.tier == "lift_ub"
    assert X.FLAG_NO_D_TOUCH in lots[1].exit.flags


def test_upper_bound_same_day_exit_comes_first_like_after_lift():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 100, 101, 91, 95)}   # 1일째 기존 로트 손절(92)
    fills = [_fill(0, 100), _upper(1, 95)]
    lots = A.run_lots(fills, RULES, _path_fn(bars), _no_probe, DAYS, _time, "B1")
    assert lots[0].exit.phase == X.PHASE_AFTER and lots[1].is_repeat_while_open is False
    assert lots[1].exit.status == "open"                                                  # 진입일 저가 91 안 씀
    accts = A.run_accounts(fills, RULES, _path_fn(bars), _no_probe, _time)
    assert len(accts) == 2 and (accts[0].exit.reason, accts[0].exit.exit_date) == (X.EXIT_SL, DAYS[1])
    assert accts[1].fills[0].basis == X.BASIS_UPPER and accts[1].exit.status == "open"
    assert all(f"{A.FLAG_ADD_UNKNOWN}:{DAYS[1]}" in a.flags for a in accts)        # fix 1: 장중 손절과 상한 체결 순서 불명 → 둘 다
    assert sum(lot.is_repeat_while_open for lot in lots) == sum(a.n_adds for a in accts) == 0


def test_lift_add_into_open_b2_account_exposes_lift_add_flag():
    tb = Bar(DAYS[1], 100.0, 101.0, 99.0, 100.0)
    lift = A.Fill(FOLDER, "000001", DAYS[1], 100.0, X.BASIS_LIFT, 10, "amount",
                  entry_time=datetime(2026, 9, 11, 9, 24), touch_bar=tb, lift_time="09:24:00")
    fills = [_fill(0, 100), lift]
    accts = A.run_accounts(fills, RULES, _path_fn(FLAT), _no_probe, _time)
    assert len(accts) == 1 and accts[0].n_adds == 1
    assert f"{X.FLAG_LIFT_ADD}:{DAYS[1]}" in accts[0].flags
    assert not any(fl.startswith(A.FLAG_ADD_UNKNOWN) for fl in accts[0].flags)
    lots = A.run_lots(fills, RULES, _path_fn(FLAT), _no_probe, DAYS, _time, "B1")
    assert lots[1].is_repeat_while_open is True


def _live(i, price):
    """과제 10 fix 1 — 분봉 없는 급락 해제 뒤 라이브 실제 체결(시각·가격 앎 · 진입 뒤 고저 모름)."""
    return A.Fill(FOLDER, "000001", DAYS[i], float(price), X.BASIS_LIVE_FILL, 10, "amount", crash_blocked=True,
                  entry_time=datetime.combine(DAYS[i], time(9, 25, 38)), lift_time="09:23:09")


def test_live_fill_is_an_after_lift_entry_without_entry_day_touches():
    bars = {DAYS[0]: _bar(0, 100, 101, 85, 90)}                     # D 저가 85 — D_open 이면 그날 손절
    lot, = A.run_lots([_live(0, 100)], RULES, _path_fn(bars), _no_probe, DAYS, _time, "B1")
    assert lot.exit.status == "open" and X.FLAG_NO_D_TOUCH in lot.exit.flags
    acct, = A.run_accounts([_live(0, 100)], RULES, _path_fn(bars), _no_probe, _time)
    assert acct.exit.status == "open" and X.FLAG_NO_D_TOUCH in acct.flags
    accts = A.run_accounts([_fill(0, 100), _live(1, 100)], RULES, _path_fn(FLAT), _no_probe, _time)
    assert len(accts) == 1 and accts[0].n_adds == 1                 # 열린 계좌 추가 = 해제 뒤 추가매수(A4)
    assert f"{X.FLAG_LIFT_ADD}:{DAYS[1]}" in accts[0].flags
    assert not any(fl.startswith(A.FLAG_ADD_UNKNOWN) for fl in accts[0].flags)
    bars2 = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 100, 101, 91, 95)}   # 1일째 기존 로트 손절(92)
    lots = A.run_lots([_fill(0, 100), _live(1, 95)], RULES, _path_fn(bars2), _no_probe, DAYS, _time, "B1")
    assert lots[1].is_repeat_while_open is False and lots[1].exit.status == "open"      # 그날 청산이 «먼저»
    accts = A.run_accounts([_fill(0, 100), _live(1, 95)], RULES, _path_fn(bars2), _no_probe, _time)
    assert len(accts) == 2 and accts[1].fills[0].basis == X.BASIS_LIVE_FILL
    assert not any(fl.startswith(A.FLAG_ADD_UNKNOWN) for a in accts for fl in a.flags)


@pytest.mark.parametrize("price", [0.0, -1.0, float("nan")])
def test_non_positive_price_fill_is_rejected(price, caplog):
    caplog.set_level("WARNING", logger=A.__name__)
    assert A.run_lots([_upper(0, price)], RULES, _path_fn(FLAT), _no_probe, DAYS, _time, "B1") == []
    assert A.run_accounts([_upper(0, price)], RULES, _path_fn(FLAT), _no_probe, _time) == []
    accts = A.run_accounts([_fill(0, 100), _upper(1, price)], RULES, _path_fn(FLAT), _no_probe, _time)
    assert len(accts) == 1 and accts[0].n_adds == 0 and accts[0].avg_price == 100.0
    assert sum("price" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records) == 3


def test_upper_bound_after_open_phase_exit_stays_unflagged():
    bars = {DAYS[0]: _bar(0, 100, 101, 99, 100), DAYS[1]: _bar(1, 111, 112, 110, 111)}   # 1일째 09:00 갭 익절
    accts = A.run_accounts([_fill(0, 100), _upper(1, 111)], RULES, _path_fn(bars), _no_probe, _time)
    assert len(accts) == 2 and accts[0].exit.phase == X.PHASE_OPEN
    assert not any(fl.startswith(A.FLAG_ADD_UNKNOWN) for a in accts for fl in a.flags)


@pytest.mark.parametrize("lift_time, entry_time, unknown", [
    ("", None, True),                                   # 체결 하한 시각 모름 → 보수적으로 표시
    ("09:23:09", None, False),                          # 해제(09:23) 뒤 체결 — 09:0x 데이터 청산이 먼저
    ("090400", None, True),                             # 09:05 전 해제 — 순서 불명
    ("", datetime(2026, 9, 11, 11, 2, 6), False),       # entry_time 우선
])
def test_upper_bound_after_probe_exit_flags_only_when_order_unknown(lift_time, entry_time, unknown):
    probe = lambda folder: (lambda pos, day: "trail_ma" if (day == DAYS[1] and pos.entry_date == DAYS[0]) else None)  # noqa: E731
    fills = [_fill(0, 100), _upper(1, 100, lift_time=lift_time, entry_time=entry_time)]
    accts = A.run_accounts(fills, RULES, _path_fn(FLAT), probe, _time)
    assert len(accts) == 2 and (accts[0].exit.reason, accts[0].exit.phase) == ("trail_ma", X.PHASE_AFTER)
    assert [f"{A.FLAG_ADD_UNKNOWN}:{DAYS[1]}" in a.flags for a in accts] == [unknown, unknown]
