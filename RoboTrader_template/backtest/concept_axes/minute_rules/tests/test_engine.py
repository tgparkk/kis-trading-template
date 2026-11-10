"""engine — 진입(밴드·반올림·민감도) · 룩어헤드 계약 · 당일 분 단위 익절·손절 · 미청산 Pos."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pytest

from backtest.concept_axes.minute_rules import engine as E
from backtest.concept_axes.minute_rules import rules as R

from .synth import flat, path, put

DAY = date(2026, 11, 10)
CTX = E.DayCtx("000001", DAY, band_hi=10300.0, prev_close=10000.0, prev_day_volume=50_000.0)
TP, SL = 0.10, 0.08


def _walk(seed: int, n: int = E.N_CONT) -> np.ndarray:
    rng = np.random.default_rng(seed)
    b = flat(10000.0)
    closes = np.round(10000.0 * np.cumprod(1 + rng.normal(0, 0.01, n)), -1)
    path(b, 0, closes)
    b[: E.N_CONT, E.F_VOL] = rng.integers(0, 2000, E.N_CONT)
    return b


def test_time_index_roundtrip_and_off_grid():
    assert E.idx_to_time(0) == "090000" and E.idx_to_time(379) == "151900" and E.idx_to_time(380) == "153000"
    for i in (0, 5, 61, 379, 380):
        assert E.time_to_idx(E.idx_to_time(i)) == i
    for bad in ("152000", "152900", "085900", "090030", "0900", "abcdef"):
        assert E.time_to_idx(bad) is None


def test_view_upto_hides_current_minute_and_copies():
    b = flat()
    put(b, 7, 10010, 10500, 9500, 10200, v=999)
    v = E.view_upto(b, 7)
    assert v.shape == (8, E.N_FIELDS)
    assert v[7, E.F_CLOSE] == 10200
    assert np.isnan(v[7, [E.F_OPEN, E.F_HIGH, E.F_LOW, E.F_VOL, E.F_AMT]]).all()
    assert v[6, E.F_HIGH] == 10000            # 완성 봉은 그대로
    v[0, 0] = -1
    assert b[0, 0] == 10000                   # 사본


def test_baseline_enters_first_minute_0902():
    r = E.run_day(flat(), CTX, R.r0_baseline, TP, SL)
    assert r.entered and r.entry.idx == 2 and r.entry.time == "090200" and r.entry.px == 10000


def test_band_wait_then_enter_with_sensitivity_columns():
    b = flat(10500.0)                         # 밴드 상한 10300 위
    path(b, 6, [10250, 10260])                # 09:06 첫 밴드 안
    r = E.run_day(b, CTX, R.r0_baseline, TP, SL)
    assert r.entry.idx == 6 and r.entry.px == 10250
    assert r.entry.px_next_open == 10250      # 09:07 시가 = 09:06 종가
    assert (r.band_edge.idx, r.band_edge.px) == (6, 10250)   # 종가가 밴드 안 → 종가


def test_band_edge_touch_earlier_than_close_entry():
    b = flat(10500.0)
    put(b, 4, 10500, 10500, 10290, 10500)     # 09:04 저가만 상한에 닿고 종가는 밖
    path(b, 8, [10200])
    r = E.run_day(b, CTX, R.r0_baseline, TP, SL)
    assert r.entry.idx == 8
    assert (r.band_edge.idx, r.band_edge.px, r.band_edge.px_raw) == (4, 10300.0, 10500)
    nb = flat(10500.0)
    put(nb, 4, 10500, 10500, 10290, 10500)
    r2 = E.run_day(nb, CTX, R.r0_baseline, TP, SL)            # 종가는 끝내 밴드 밖
    assert not r2.entered and r2.band_edge.idx == 4


def test_next_open_none_when_out_of_band():
    """민감도 (b) — 다음 분 시가가 밴드 밖이면 None(결측) · 다음 분으로 넘기지 않는다(리뷰 A4)."""
    b = flat(10000.0)
    put(b, 3, 10500, 10500, 10500, 10500)     # 09:03 시가가 밴드 밖
    r = E.run_day(b, CTX, R.r0_baseline, TP, SL)
    assert r.entry.idx == 2 and r.entry.px_next_open is None
    assert r.entry.px == 10000                # 본 진입은 그대로


def test_next_open_none_at_1519_entry():
    b = flat(20000.0)                         # 15:18 까지 밴드 밖
    b[E.IDX_ENTRY_END, :4] = 10000
    r = E.run_day(b, CTX, R.r0_baseline, TP, SL)
    assert r.entry.idx == E.IDX_ENTRY_END and r.entry.px_next_open is None   # 다음 분 없음


def test_band_edge_low_side_and_close_inside_wins():
    """민감도 (c) — 그 분 고저가 밴드에 닿으면 경계값 · 종가가 밴드 안이면 종가(성적 상한 · 리뷰 A3)."""
    ctx = E.DayCtx("000001", DAY, band_lo=9800.0, band_hi=10300.0)
    b = flat(9500.0)
    put(b, 3, 9500, 9850, 9500, 9500)          # 종가 하한 밖 · 고가가 하한에 닿음 → 경계값 9,800
    r = E.run_day(b, ctx, R.r0_baseline, TP, SL)
    assert (r.band_edge.idx, r.band_edge.px) == (3, 9800.0) and not r.entered
    b2 = flat(10000.0)
    put(b2, 2, 10000, 10600, 9000, 10100)      # 고저가가 양쪽 경계 넘어도 종가 안 → 종가
    r2 = E.run_day(b2, ctx, R.r0_baseline, TP, SL)
    assert (r2.band_edge.idx, r2.band_edge.px) == (2, 10100) and r2.entry.idx == 2


def test_half_tick_rounding_and_band_check_after_rounding():
    b = flat(26825.0)                         # 호가 50 의 반 호가(EXPERT_SYSTEM Q9 예)
    r = E.run_day(b, E.DayCtx("082740", DAY), R.r0_baseline, TP, SL)
    assert r.entry.px_raw == 26825 and r.entry.px == 26850
    r2 = E.run_day(b, E.DayCtx("082740", DAY, band_hi=26840.0), R.r0_baseline, TP, SL)
    assert not r2.entered and r2.skip_reason == E.SKIP_NO_ENTRY   # 반올림 뒤 26,850 > 상한


def test_no_price_vs_no_entry():
    b = np.full((E.N_SLOTS, E.N_FIELDS), np.nan)
    assert E.run_day(b, CTX, R.r0_baseline, TP, SL).skip_reason == E.SKIP_NO_PRICE
    assert E.run_day(flat(20000.0), CTX, R.r0_baseline, TP, SL).skip_reason == E.SKIP_NO_ENTRY


PRED_IDS = sorted(k for k, r in R.REGISTRY.items() if r.pred is not None)
TIMING_IDS = sorted(k for k, r in R.REGISTRY.items() if r.kind == "timing")
FILTER_IDS = sorted(k for k, r in R.REGISTRY.items() if r.kind == "filter")
LA_CTX = E.DayCtx("000001", DAY, prev_close=10000.0, prev_day_volume=20_000.0)
LA_T_END = 120


@pytest.mark.parametrize("rid", PRED_IDS)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_lookahead_future_perturbation_does_not_change_decision(rid, seed):
    pred = R.REGISTRY[rid].pred
    b = _walk(seed)
    rng = np.random.default_rng(100 + seed)
    for t in range(E.IDX_ENTRY_START, LA_T_END):
        d0 = pred(E.view_upto(b, t), LA_CTX)
        p = b.copy()
        p[t + 1:] = rng.uniform(1000, 50000, p[t + 1:].shape)
        p[t, [E.F_OPEN, E.F_HIGH, E.F_LOW, E.F_VOL, E.F_AMT]] = rng.uniform(1000, 50000, 5)
        assert pred(E.view_upto(p, t), LA_CTX) == d0, (rid, t)


@pytest.mark.parametrize("rid", TIMING_IDS)
def test_lookahead_not_degenerate_timing_rules_take_both_values(rid):
    """퇴화 검사(리뷰 A5) — 같은 합성 경로에서 시점 규칙 판정이 참·거짓 둘 다 나와야 위 불변 검사가 의미 있다."""
    pred = R.REGISTRY[rid].pred
    seen = {pred(E.view_upto(_walk(seed), t), LA_CTX) for seed in (1, 2, 3) for t in range(E.IDX_ENTRY_START, LA_T_END)}
    assert True in seen and False in seen, (rid, seen)


@pytest.mark.parametrize("rid", FILTER_IDS)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_lookahead_filter_label_ignores_0905_hidden_fields_and_later_bars(rid, seed):
    lab = R.REGISTRY[rid].label
    b = _walk(seed)
    l0 = E.label_day(b, LA_CTX, lab)
    p = b.copy()
    t = E.IDX_FILTER_AT
    p[t + 1:] = np.random.default_rng(200 + seed).uniform(1000, 50000, p[t + 1:].shape)
    p[t, [E.F_OPEN, E.F_HIGH, E.F_LOW, E.F_VOL, E.F_AMT]] = 1.0
    assert E.label_day(p, LA_CTX, lab) == l0


@pytest.mark.parametrize("rid", FILTER_IDS)
def test_filter_labels_not_degenerate(rid):
    """퇴화 검사(리뷰 A5) — 합성 경로·전일 거래량 두 값에서 keep·filter 가 둘 다 나와야 한다."""
    lab = R.REGISTRY[rid].label
    ctxs = [E.DayCtx("000001", DAY, prev_day_volume=v) for v in (20_000.0, 2_000_000.0)]
    seen = {E.label_day(_walk(seed), c, lab) for seed in range(40) for c in ctxs}
    assert E.LABEL_KEEP in seen and E.LABEL_FILTER in seen, (rid, seen)


@pytest.mark.parametrize("rid", PRED_IDS)
def test_lookahead_entry_unchanged_when_bars_after_entry_shaken(rid):
    rule = R.REGISTRY[rid]
    ctx = E.DayCtx("000001", DAY, band_hi=10400.0, prev_close=10000.0, prev_day_volume=20_000.0)
    start = E.BASE_ARMS[rule.base]
    found = [(b, f) for b in map(_walk, range(7, 60)) for f in [E.find_entry(b, ctx, rule.pred, start)]
             if f is not None]
    assert found, "합성 경로 53개 중 진입 0 — 테스트 경로를 바꿀 것"
    b, f0 = found[0]
    p = b.copy()
    p[f0.idx + 1:] = np.random.default_rng(9).uniform(1000, 50000, p[f0.idx + 1:].shape)
    p[f0.idx, [E.F_OPEN, E.F_HIGH, E.F_LOW, E.F_VOL, E.F_AMT]] = 1.0
    f1 = E.find_entry(p, ctx, rule.pred, start)
    assert (f1.idx, f1.px) == (f0.idx, f0.px)


def test_base_arm_r0_0905_starts_at_0905():
    r = E.run_day(flat(), CTX, R.r0_baseline, TP, SL, base=E.BASE_R0_0905)
    assert r.entered and r.entry.idx == 5 and r.entry.time == "090500" and r.base == E.BASE_R0_0905
    with pytest.raises(KeyError):
        E.run_day(flat(), CTX, R.r0_baseline, TP, SL, base="R9")


def test_tp_at_line_and_gap_tp_at_open():
    b = flat()
    put(b, 20, 10000, 11050, 10000, 10500)
    ex = E.run_day(b, CTX, R.r0_baseline, TP, SL).exit
    assert ex.closed and ex.reason == E.EXIT_TP and ex.idx == 20 and ex.px == pytest.approx(11000)
    assert ex.ret_pct == pytest.approx(10.0) and E.FLAG_GAP_TP not in ex.flags
    b2 = flat()
    put(b2, 20, 11200, 11300, 11100, 11200)
    ex2 = E.run_day(b2, CTX, R.r0_baseline, TP, SL).exit
    assert ex2.px == 11200 and E.FLAG_GAP_TP in ex2.flags


def test_same_minute_tp_and_sl_stop_loss_wins():
    b = flat()
    put(b, 10, 10000, 11100, 9100, 10000)
    ex = E.run_day(b, CTX, R.r0_baseline, TP, SL).exit
    assert ex.reason == E.EXIT_SL and ex.px == pytest.approx(9200) and E.FLAG_SL_TP_SAME in ex.flags


def test_same_minute_gap_tp_open_but_low_hits_sl_still_stop_loss():
    """사전등록 결정 — 시가 ≥ 익절선(갭 익절 조건)이어도 같은 분 저가가 손절선이면 손절(k≥1 일봉 경로와 다름 · A2)."""
    b = flat()
    put(b, 10, 11200, 11300, 9100, 9500)
    ex = E.run_day(b, CTX, R.r0_baseline, TP, SL).exit
    assert ex.reason == E.EXIT_SL and ex.px == pytest.approx(9200)
    assert E.FLAG_SL_TP_SAME in ex.flags and E.FLAG_GAP_TP not in ex.flags
    assert E.FLAG_GAP_TP_OVERRIDDEN in ex.flags                 # 시가 갭 익절이었던 건 — 따로 셈(초안 §3 · N4)


def test_same_minute_sl_without_gap_open_has_no_override_flag():
    b = flat()
    put(b, 10, 10000, 11100, 9100, 10000)     # 고가만 익절선 · 시가는 아래
    ex = E.run_day(b, CTX, R.r0_baseline, TP, SL).exit
    assert E.FLAG_SL_TP_SAME in ex.flags and E.FLAG_GAP_TP_OVERRIDDEN not in ex.flags


def test_sl_ignored_before_0905_then_gap_sl_at_0905_open():
    b = flat()
    path(b, 3, [9000, 9000])                  # 09:03·09:04 선(9,200) 아래 — 손절 안 함
    ex = E.run_day(b, CTX, R.r0_baseline, TP, SL).exit
    assert ex.reason == E.EXIT_SL and ex.idx == 5 and ex.time == "090500" and ex.px == 9000
    assert E.FLAG_SL_DEFERRED in ex.flags and E.FLAG_SL_GAP in ex.flags


def test_exit_starts_minute_after_entry():
    b = flat()
    put(b, 2, 10000, 10000, 8000, 10000)      # 진입 분 자체의 저가는 안 본다
    ex = E.run_day(b, CTX, R.r0_baseline, TP, SL).exit
    assert not ex.closed


def test_1530_row_ignored_and_open_position_returned():
    b = flat()
    b[E.IDX_1530, :4] = (20000, 20000, 20000, 20000)
    r = E.run_day(b, CTX, R.r0_baseline, TP, SL)
    assert not r.exit.closed and r.exit.reason is None
    assert r.pos is not None and r.pos.entry_basis == E.BASIS_M_CLOSE and r.pos.qty == 100
    assert r.pos.entry_time == datetime(2026, 11, 10, 9, 2) and r.pos.entry_price == 10000
