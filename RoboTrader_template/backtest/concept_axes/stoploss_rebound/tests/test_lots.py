"""lots — 진입 당일 기준(①②③) · ⓑ/ⓐ arm · H 종료 평가(판 L/M · 재개) · 데이터 제외 · 창 · 에피소드 · 블록(합성)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar
from backtest.concept_axes.stoploss_rebound import author_exit as AE
from backtest.concept_axes.stoploss_rebound import lots as LT

CAL = [date(2026, 5, 1) + timedelta(days=i) for i in range(140)]
R = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=50, source="test")


def row(c: float, o: float = None, h: float = None, lo: float = None, v: float = 1000.0) -> LT.DayRow:
    o = c if o is None else o
    return LT.DayRow(o, max(o, c) if h is None else h, min(o, c) if lo is None else lo, c, v, 0.03)


def flat_rows(c: float = 100.0):
    return {d: row(c) for d in CAL}


def never(_p, _d):
    return None


def boom(_p, _d):
    raise AssertionError("시뮬 호출 금지 경로")


def ident(t):
    return t


def lot(i0: int, hhmm=(9, 2), sell_k=None, reason=None, sell_px=None, price=100.0) -> LT.LotIn:
    bt = datetime.combine(CAL[i0], time(*hhmm))
    st = datetime.combine(CAL[i0 + sell_k], time(10, 0)) if sell_k is not None else None
    return LT.LotIn(1, "book_pullback_ma20", "000001", bt, price, 10, 2 if st else None, st, reason, sell_px)


# ── 봉 · 경로 ──────────────────────────────────────────────────────────────
def test_to_bar_none_for_padding_or_missing():
    d = CAL[0]
    assert LT.to_bar(d, row(100, v=0)) is None                 # 거래량 0 = 거래 불가
    assert LT.to_bar(d, LT.DayRow(None, 101, 99, 100, 10)) is None
    assert LT.to_bar(d, LT.DayRow(100, None, 99, 100, 10)) is None
    assert LT.to_bar(d, None) is None
    assert LT.to_bar(d, row(100)).close == 100.0


def test_build_path_k_and_none():
    rows = flat_rows()
    rows[CAL[72]] = row(100, v=0)
    p = LT.build_path(rows, CAL, 70, 75)
    assert [k for k, _, _ in p] == [0, 1, 2, 3, 4, 5] and p[2][2] is None and p[0][1] == CAL[70]


# ── 진입 당일(§6-2) ─────────────────────────────────────────────────────────
def test_day0_basis_boundaries():
    mins = [("09:05:00", Bar(CAL[70], 100, 101, 99, 100)), ("09:06:00", Bar(CAL[70], 100, 120, 80, 100)),
            ("09:07:00", Bar(CAL[70], 100, 104, 97, 103)), ("09:08:00", Bar(CAL[70], 103, 105, 98, 102))]
    assert LT.day0_basis(lot(70, (9, 5)), mins) == (X.BASIS_D_OPEN, None)
    b, tb = LT.day0_basis(LT.LotIn(1, "s", "c", datetime.combine(CAL[70], time(9, 6, 30)), 100.0, 1), mins)
    assert b == LT.BASIS_TOUCH and (tb.high, tb.low, tb.close) == (105.0, 97.0, 102.0)   # 09:06 분봉(체결 분) 제외
    late = LT.LotIn(1, "s", "c", datetime.combine(CAL[70], time(9, 8, 10)), 100.0, 1)
    assert LT.day0_basis(late, mins) == (X.BASIS_ACTUAL, None)
    assert LT.day0_basis(lot(70, (9, 30)), []) == (X.BASIS_ACTUAL, None)


def test_day0_basis_hhmmss_format_from_db():
    mins = [("091000", Bar(CAL[70], 100, 101, 99, 100)), ("091100", Bar(CAL[70], 100, 102, 98, 101))]
    b, tb = LT.day0_basis(LT.LotIn(1, "s", "c", datetime.combine(CAL[70], time(9, 10, 5)), 100.0, 1), mins)
    assert b == LT.BASIS_TOUCH and tb.high == 102.0


def test_day0_live_exit_uses_db_sell_without_simulation():
    lt = lot(70, sell_k=0, reason="손절 실행 (-8.1%)", sell_px=91.9)
    b = LT.b_arm(lt, R, LT.build_path(flat_rows(), CAL, 70, 100), boom, X.BASIS_D_OPEN, None, ident)
    assert b.reason == X.EXIT_SL and b.ret_M == pytest.approx(-8.1) and LT.FLAG_DAY0_LIVE in b.flags
    assert LT.day0_class(lt, X.BASIS_D_OPEN) == LT.DAY0_LIVE


def test_day0_live_non_stop_gives_delta_zero():
    lt = lot(70, sell_k=0, reason="목표 익절 도달 (+10.0%)", sell_px=110.0)
    path = LT.build_path(flat_rows(), CAL, 70, 100)
    b = LT.b_arm(lt, R, path, boom, X.BASIS_D_OPEN, None, ident)
    a = LT.a_arm(lt, R, path, boom, X.BASIS_D_OPEN, None, ident, [100.0] * 59, b)
    assert a.ret_M == b.ret_M == pytest.approx(10.0) and a.ret_L == b.ret_L


def test_day0_live_stop_lets_author_path_continue():
    rows = flat_rows()
    for i in range(71, 95):
        rows[CAL[i]] = row(104)
    lt = lot(70, sell_k=0, reason="손절 실행 (-3.0%)", sell_px=97.0)
    path = LT.build_path(rows, CAL, 70, 100)
    b = LT.b_arm(lt, R, path, never, X.BASIS_D_OPEN, None, ident)
    a = LT.a_arm(lt, R, path, never, X.BASIS_D_OPEN, None, ident, [50.0] * 59, b)
    assert b.ret_M == pytest.approx(-3.0)
    assert a.term.kind == LT.KIND_H_CLOSE and a.ret_M == pytest.approx(4.0)     # 손절 없이 H=20 종가


# ── ⓑ H 절단 · 종료 평가 · 판 L/M ──────────────────────────────────────────
def test_b_open_at_h_valued_at_h_close():
    rows = flat_rows()
    rows[CAL[90]] = row(103)
    b = LT.b_arm(lot(70), R, LT.build_path(rows, CAL, 70, 100), never, X.BASIS_D_OPEN, None, ident)
    assert b.term.kind == LT.KIND_H_CLOSE and b.term.k == 20 and b.ret_M == pytest.approx(3.0) and b.hold == 20


def test_terminal_resume_after_suspension_is_single_panel():
    rows = flat_rows()
    for i in (89, 90, 91):
        rows[CAL[i]] = row(100, v=0)
    rows[CAL[92]] = row(95, o=96)
    t = LT.terminal(LT.build_path(rows, CAL, 70, 100), 20, 100.0)
    assert (t.kind, t.k, t.px_L, t.px_M) == (LT.KIND_RESUME, 22, 96.0, 96.0)


def test_terminal_permanent_cut_gives_two_panels():
    rows = flat_rows()
    rows[CAL[87]] = row(95)
    for i in range(88, 101):
        rows.pop(CAL[i])
    path = LT.build_path(rows, CAL, 70, 100)
    t = LT.terminal(path, 20, 100.0)
    assert (t.kind, t.k, t.px_L, t.px_M) == (LT.KIND_CUT, 17, 0.0, 95.0)
    b = LT.b_arm(lot(70), R, path, never, X.BASIS_D_OPEN, None, ident)
    assert b.cut and b.ret_L == pytest.approx(-100.0) and b.ret_M == pytest.approx(-5.0)


def test_terminal_requires_full_horizon():
    with pytest.raises(ValueError):
        LT.terminal(LT.build_path(flat_rows(), CAL, 70, 80), 20, 100.0)


def test_author_remaining_share_valued_per_panel():
    rows = flat_rows()
    rows[CAL[71]] = row(104)
    for i in range(72, 88):
        rows[CAL[i]] = row(99)
    rows[CAL[88]] = row(79, o=99)                     # k=18 손실 트리거
    rows[CAL[89]] = row(80)
    rows[CAL[90]] = row(81)                            # k=19·20 매도 2/5
    for i in range(91, 101):
        rows.pop(CAL[i])
    rows[CAL[90]] = row(81, v=0)                        # k=20 끊김 → 그 몫 이월 · 재개 없음
    path = LT.build_path(rows, CAL, 70, 100)
    b = LT.b_arm(lot(70), R, path, never, X.BASIS_D_OPEN, None, ident)
    a = LT.a_arm(lot(70), R, path, never, X.BASIS_D_OPEN, None, ident, [], b)
    assert a.tranches == [(19, 0.2, 80.0)] and a.remaining == pytest.approx(0.8) and a.cut
    assert a.ret_L == pytest.approx((0.2 * 80.0) / 100 * 100 - 100)
    assert a.ret_M == pytest.approx((0.2 * 80.0 + 0.8 * 80.0) / 100 * 100 - 100)


# ── 데이터 처리(§6-7 · §3 X3) ───────────────────────────────────────────────
def _jump_rows(i: int, ratio: float):
    rows = flat_rows()
    for j in range(i, len(CAL)):
        rows[CAL[j]] = row(100 * ratio)
    return rows


@pytest.mark.parametrize("ratio,hit", [(0.69, True), (0.6901, False), (1.31, True), (1.3099, False)])
def test_jump_thresholds(ratio, hit):
    assert LT.lot_exclusion(_jump_rows(80, ratio), CAL, 70, 90, [], [])[0] == (("jump",) if hit else ())


def test_jump_interval_is_entry_minus_60_to_end():
    # 구간 = 달력 i 10(진입 − 60봉) ~ 90 · 비율은 구간 «안» 연속 종가끼리(경계를 걸친 i 9→10 은 밖)
    assert LT.lot_exclusion(_jump_rows(11, 0.5), CAL, 70, 90, [], [])[0] == ("jump",)
    assert LT.lot_exclusion(_jump_rows(10, 0.5), CAL, 70, 90, [], [])[0] == ()
    assert LT.lot_exclusion(_jump_rows(90, 0.5), CAL, 70, 90, [], [])[0] == ("jump",)
    assert LT.lot_exclusion(_jump_rows(91, 0.5), CAL, 70, 90, [], [])[0] == ()


def test_split_bonus_excluded_rights_only_flagged():
    why, rights = LT.lot_exclusion(flat_rows(), CAL, 70, 90, [CAL[90]], [CAL[75]])
    assert why == ("split_bonus",) and rights
    why, rights = LT.lot_exclusion(flat_rows(), CAL, 70, 90, [CAL[91]], [CAL[9]])
    assert why == () and not rights


def test_lot_exclusion_needs_60_bar_lookback():
    with pytest.raises(ValueError):
        LT.lot_exclusion(flat_rows(), CAL, 59, 79, [], [])


# ── T1/T2 창(§4 · X1·X2·X3) ────────────────────────────────────────────────
def test_window_completeness_x1():
    assert not LT.window(flat_rows(), CAL, 100, 10, 109, [], []).complete
    assert LT.window(flat_rows(), CAL, 100, 10, 110, [], []).complete


def test_window_x2_half_valid_bars():
    rows = flat_rows()
    for i in (101, 102, 103):                        # h=5 창 101..105 중 3 무효 → 유효 2 < ⌈5/2⌉=3
        rows[CAL[i]] = row(100, v=0)
    w = LT.window(rows, CAL, 100, 5, 130, [], [])
    assert w.n_valid == 2 and w.x2
    rows[CAL[103]] = row(100)
    w = LT.window(rows, CAL, 100, 5, 130, [], [])
    assert w.n_valid == 3 and not w.x2


def test_window_x3_includes_t_to_t1_ratio_and_corp_on_t():
    rows = flat_rows()
    rows[CAL[100]] = row(50)                          # t 종가 50 → t+1 100: 비율 2.0
    assert LT.window(rows, CAL, 100, 5, 130, [], []).jump
    assert not LT.window(rows, CAL, 101, 5, 130, [], []).jump
    w = LT.window(flat_rows(), CAL, 100, 5, 130, [CAL[100]], [CAL[105]])
    assert w.corp and w.rights and w.x3
    assert not LT.window(flat_rows(), CAL, 100, 5, 130, [CAL[106]], []).corp


def test_window_extremes_and_sealed_mode():
    rows = flat_rows()
    rows[CAL[101]] = row(100, h=112, lo=95)
    rows[CAL[100]] = row(100, h=200, lo=10)          # t 당일은 창 밖
    w = LT.window(rows, CAL, 100, 5, 130, [], [])
    assert (w.hi, w.lo) == (112.0, 95.0)
    assert LT.rise(w, 100.0) == pytest.approx(0.12) and LT.fall(w, 100.0) == pytest.approx(-0.05)
    w0 = LT.window(rows, CAL, 100, 5, 130, [], [], extremes=False)
    assert (w0.hi, w0.lo) == (None, None) and w0.n_valid == 5


# ── 에피소드(X4) · 블록 ──────────────────────────────────────────────────────
def test_episode_keep_from_last_included_event():
    pos = {d: i for i, d in enumerate(CAL)}
    ev = [(1, "s", "A", datetime.combine(CAL[10], time(10))), (2, "s", "A", datetime.combine(CAL[15], time(10))),
          (3, "s", "A", datetime.combine(CAL[16], time(10))), (4, "s", "A", datetime.combine(CAL[21], time(10))),
          (5, "t", "A", datetime.combine(CAL[11], time(10))), (6, "s", "A", datetime.combine(CAL[10], time(11)))]
    assert LT.episode_keep(ev, pos) == {1, 3, 5}       # 2(5일 안) · 6(같은 날) · 4(3 으로부터 5일) 제외


@pytest.mark.parametrize("n,B,last", [(26, 5, 6), (25, 5, 5), (24, 4, 9), (9, 1, 9), (4, 1, 4)])
def test_blocks_merge_short_last_block(n, B, last):
    days = CAL[:n]
    bl = LT.blocks_of(days)
    assert len(set(bl.values())) == B and list(bl.values()).count(B - 1) == last


def test_author_entry_below_sma_helper():
    assert AE.entry_below_sma([100.0] * 59, 99.0) is True
    assert AE.entry_below_sma([100.0] * 59, 101.0) is False
    assert AE.entry_below_sma([100.0] * 58, 99.0) is None
    assert AE.entry_below_sma([100.0] * 59, None) is None
