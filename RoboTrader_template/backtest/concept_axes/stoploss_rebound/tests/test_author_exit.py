"""ⓐ author_exit — 사전등록 §6-2·§6-5·§6-7 규칙별 경계 시험(합성 봉만)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar
from backtest.concept_axes.stoploss_rebound import author_exit as AE

D0 = date(2026, 9, 1)
R50 = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=50, source="test")


def _d(k: int) -> date:
    return D0 + timedelta(days=k)


def B(c: float, o: float = None, h: float = None, lo: float = None):
    o = c if o is None else o
    return (o, max(o, c) if h is None else h, min(o, c) if lo is None else lo, c)


def path(*bars):
    return [(k, _d(k), None if b is None else Bar(_d(k), *b)) for k, b in enumerate(bars)]


def pos(basis: str = X.BASIS_D_OPEN, touch=None, price: float = 100.0) -> X.Pos:
    return X.Pos("000001", D0, datetime(2026, 9, 1, 9, 2), price, 10, basis, touch)


def never(_p, _d):
    return None


def run(bars, pre=(), horizon=20, rules=R50, probe=never, p=None, **kw):
    return AE.author_exit(p or pos(), rules, path(*bars), probe, list(pre), horizon, **kw)


# ── (a) 손실 한도 ───────────────────────────────────────────────────────────
def test_loss20_boundary_triggers_and_splits_five_opens():
    bars = [B(100), B(104), B(80, o=100), B(81), B(82), B(83), B(84), B(85)]
    out = run(bars, horizon=10)
    assert out.trigger_k == 2 and out.triggers == (AE.TRIG_LOSS,)
    assert [(t.k, t.weight, t.price, t.kind) for t in out.tranches] == [
        (3, 0.2, 81.0, AE.KIND_SPLIT), (4, 0.2, 82.0, AE.KIND_SPLIT), (5, 0.2, 83.0, AE.KIND_SPLIT),
        (6, 0.2, 84.0, AE.KIND_SPLIT), (7, 0.2, 85.0, AE.KIND_SPLIT)]
    assert out.closed and out.reason == AE.EXIT_SPLIT and out.remaining == 0.0
    assert out.price == pytest.approx(83.0) and out.ret_pct == pytest.approx(-17.0)


def test_loss_just_above_limit_does_not_trigger():
    out = run([B(100), B(104), B(80.01, o=100), B(81), B(82)], horizon=4)
    assert out.trigger_k is None and out.status == "open" and out.remaining == 1.0


# ── 고정 손절 비활성 · 진입 당일 ────────────────────────────────────────────
def test_no_fixed_stop_even_far_below_sl():
    bars = [B(100), B(85, o=100, lo=84), B(86), B(85)]
    a = run(bars, horizon=3)
    b = X.simulate_lot(pos(), R50, path(*bars), never)
    assert b.closed and b.reason == X.EXIT_SL            # ⓑ 는 손절
    assert a.status == "open" and not a.tranches         # ⓐ 는 그대로 보유


def test_day0_d_open_tp_touch_only_no_stop():
    a = run([B(100, o=100, h=105, lo=85), B(101)], horizon=1)
    assert a.status == "open"                            # 진입 당일 저가 −15% 여도 손절 없음
    a = run([B(105, o=100, h=112, lo=99), B(101)], horizon=1)
    assert a.closed and a.reason == X.EXIT_TP and a.tranches[0].k == 0 and a.price == pytest.approx(110.0)


def test_day0_actual_basis_skips_entry_day_touch_and_flags():
    a = run([B(105, o=100, h=112, lo=99), B(101)], horizon=1, p=pos(X.BASIS_ACTUAL))
    assert a.status == "open" and X.FLAG_NO_D_TOUCH in a.flags


def test_day0_touch_bar_basis_uses_touch_bar():
    tb = Bar(D0, 100.0, 111.0, 99.0, 100.0)
    a = run([B(100, o=100, h=100.5, lo=99), B(101)], horizon=1, p=pos("after_fill_minutes", tb))
    assert a.closed and a.reason == X.EXIT_TP and a.tranches[0].k == 0


def test_day0_data_exit_is_common():
    a = run([B(100), B(101)], horizon=1, probe=lambda p, d: "trail_ma" if d == D0 else None)
    assert a.closed and a.reason == "trail_ma" and X.FLAG_K0_DATA in a.flags


def test_triggers_start_at_k1_not_entry_day():
    a = run([B(75, o=100, lo=75), B(75), B(76), B(77), B(78), B(79), B(80)], horizon=6, p=pos(X.BASIS_ACTUAL))
    assert a.trigger_k == 1 and AE.TRIG_LOSS in a.triggers


# ── (c) 무반응 ─────────────────────────────────────────────────────────────
def _flat(n: int, c: float = 100.0):
    return [B(c) for _ in range(n)]


def test_no_react_triggers_at_k10():
    out = run(_flat(16), horizon=15)
    assert out.trigger_k == 10 and out.triggers == (AE.TRIG_NOREACT,) and len(out.tranches) == 5


def test_react_at_exactly_three_percent_blocks_no_react():
    bars = _flat(16)
    bars[7] = B(103.0)
    assert run(bars, horizon=15).trigger_k is None
    bars[7] = B(102.99)
    assert run(bars, horizon=15).trigger_k == 10


def test_react_on_k10_itself_counts():
    bars = _flat(16)
    bars[10] = B(103.5)
    assert run(bars, horizon=15).trigger_k is None


def test_no_react_print_variant_k5():
    out = run(_flat(12), horizon=11, no_react_k=5)
    assert out.trigger_k == 5


def test_no_react_carried_over_padding_row():
    bars = _flat(17)
    bars[10] = None
    out = run(bars, horizon=16)
    assert out.trigger_k == 11


# ── (b) 60일선 하향 이탈 «사건» ─────────────────────────────────────────────
PRE = [100.0] * 59


def test_sma60_cross_event_triggers():
    bars = [B(101), B(99)] + _flat(6, 99)
    out = run(bars, pre=PRE, horizon=7)
    assert out.trigger_k == 1 and out.triggers == (AE.TRIG_SMA,) and out.below_sma_at_entry is False


def test_sma60_below_at_entry_needs_recovery_first():
    bars = [B(99), B(98), B(101), B(99)] + _flat(6, 99)
    out = run(bars, pre=PRE, horizon=9)
    assert out.below_sma_at_entry is True
    assert out.trigger_k == 3 and out.triggers == (AE.TRIG_SMA,)


def test_sma60_level_below_is_not_an_event():
    out = run([B(95)] + _flat(5, 95), pre=PRE, horizon=5)
    assert out.trigger_k is None and out.below_sma_at_entry is True


def test_sma60_unavailable_with_fewer_than_60_bars():
    out = run([B(101), B(99), B(99)], pre=[100.0] * 10, horizon=2)
    assert out.trigger_k is None and out.sma_na and AE.FLAG_SMA_NA in out.flags


def test_same_day_multiple_triggers_counted_once():
    bars = [B(101), B(79, o=100)] + [B(80 + i) for i in range(6)]
    out = run(bars, pre=PRE, horizon=7)
    assert out.trigger_k == 1 and set(out.triggers) == {AE.TRIG_LOSS, AE.TRIG_SMA}
    assert [t.k for t in out.tranches] == [2, 3, 4, 5, 6]


# ── 트리거 뒤 · 공통 우선 · 이월 · H ─────────────────────────────────────────
def test_after_trigger_tp_and_max_hold_suspended():
    rules = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=4)
    bars = [B(100), B(104), B(79, o=100), B(85, o=85, h=120), B(86), B(87), B(88), B(89)]
    out = run(bars, rules=rules, horizon=10)
    assert out.trigger_k == 2
    assert [t.kind for t in out.tranches] == [AE.KIND_SPLIT] * 5 and out.tranches[0].price == 85.0


def test_after_trigger_data_exit_suspended():
    bars = [B(100), B(104), B(79, o=100), B(85), B(86), B(87), B(88), B(89)]
    out = run(bars, horizon=10, probe=lambda p, d: "trail_ma" if d >= _d(3) else None)
    assert out.reason == AE.EXIT_SPLIT and len(out.tranches) == 5


def test_common_exit_same_day_beats_trigger():
    out = run([B(100), B(79, o=100, h=111, lo=79), B(80)], horizon=2)
    assert out.closed and out.reason == X.EXIT_TP and out.trigger_k is None


def test_common_data_exit_before_trigger():
    out = run([B(100), B(104), B(99), B(98)], horizon=3, probe=lambda p, d: "trail_ma" if d == _d(2) else None)
    assert out.closed and out.reason == "trail_ma" and out.tranches[0].price == 99.0


def test_max_hold_before_trigger_is_common():
    rules = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=3)
    out = run([B(100), B(104), B(99), B(98), B(97)], rules=rules, horizon=4)
    assert out.closed and out.reason == X.EXIT_MAX_HOLD and out.tranches[0].k == 3


def test_split_tranche_on_padding_row_carries_to_next_valid_bar():
    bars = [B(100), B(104), B(79, o=100), B(81), None, B(83), B(84), B(85)]
    out = run(bars, horizon=10)
    assert [(t.k, t.weight) for t in out.tranches] == [(3, 0.2), (5, 0.4), (6, 0.2), (7, 0.2)]
    assert out.closed and out.remaining == 0.0


def test_padding_row_never_triggers_loss_and_resumes_on_valid_bar():
    bars = [B(100), B(104), None, B(79), B(80), B(81), B(82), B(83), B(84)]
    out = run(bars, horizon=8)
    assert out.trigger_k == 3 and f"{X.FLAG_BAR_MISSING}:{_d(2)}" in out.flags


def test_horizon_cuts_split_and_leaves_remaining():
    bars = [B(100), B(104)] + _flat(16, 99) + [B(79, o=99), B(80), B(81), B(82), B(83)]
    out = run(bars, horizon=20)
    assert out.trigger_k == 18 and [t.k for t in out.tranches] == [19, 20]
    assert out.status == "open" and out.remaining == pytest.approx(0.6)


def test_rules_passed_unchanged_sl_disabled_inside():
    rules = X.ExitRules(tp=0.10, sl=0.08, max_hold_days=50)
    run([B(100), B(85, lo=84)], rules=rules, horizon=1)
    assert rules.sl == 0.08 and AE.SL_OFF == 1.0
