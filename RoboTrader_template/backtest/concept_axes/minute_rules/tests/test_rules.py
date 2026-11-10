"""rules — 초안 표식 · 레지스트리(기준 arm 2 · 주 6 · 독립 2) · 규칙 참/거짓/판단 불가 사례(합성 view)."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from backtest.concept_axes.minute_rules import engine as E
from backtest.concept_axes.minute_rules import rules as R

from .synth import flat, put

CTX = E.DayCtx("000001", date(2026, 11, 10), prev_close=10000.0, prev_day_volume=100_000.0)


def _v(b, t, close=None):
    if close is not None:
        b = b.copy()
        b[t, E.F_CLOSE] = close
    return E.view_upto(b, t)


def test_registry_draft_ids_kinds_families():
    assert R.DRAFT is True
    assert R.rule_ids() == ["R0", "R0_0905", "R1", "R3", "R7", "R6", "R4", "R5", "H2_HIST", "H_PLUS2"]
    assert all(r.draft for r in R.REGISTRY.values())
    assert R.BASELINE.kind == "baseline" and R.BASELINE.base == E.BASE_R0
    assert R.BASELINE_0905.kind == "baseline" and R.BASELINE_0905.base == E.BASE_R0_0905
    fam = {rid: r.family for rid, r in R.REGISTRY.items()}
    assert [k for k, f in fam.items() if f == R.FAMILY_MAIN] == ["R1", "R3", "R7", "R6", "R4", "R5"]
    assert [k for k, f in fam.items() if f == R.FAMILY_INDEPENDENT] == ["H2_HIST", "H_PLUS2"]
    for rid in ("R4", "R5"):
        r = R.REGISTRY[rid]
        assert r.kind == "filter" and r.label is not None and r.pred is None and r.base == E.BASE_R0_0905
    for rid in ("R1", "R3", "R7", "R6", "H2_HIST", "H_PLUS2"):
        r = R.REGISTRY[rid]
        assert r.kind == "timing" and r.pred is not None and r.label is None and r.base == E.BASE_R0
    with pytest.raises(ValueError):
        R.register(R.Rule("R1", "timing", "dup", R.r0_baseline))
    with pytest.raises(ValueError):
        R.register(R.Rule("X_BAD", "filter", "pred 만 준 거르기", R.r0_baseline))


def test_r1_above_open_and_exact_tie_allowed():
    b = flat(10000.0)
    assert R.r1_above_open(_v(b, 10, 10300), CTX) is False
    assert R.r1_above_open(_v(b, 10, 10150), CTX) is True
    assert R.r1_above_open(_v(b, 10, 10200), CTX) is True     # p = O × 1.02 정확히 → 허용(엄격 >)
    assert R.r1_above_open(_v(b, 10, 10210), CTX) is False


def test_r1_unknown_open_is_undetermined():
    b = np.full((E.N_SLOTS, E.N_FIELDS), np.nan)
    b[3, E.F_CLOSE] = 10000                   # 첫 거래 = 지금 분 → 시가 모름(라이브 stck_oprc 는 앎)
    assert R.r1_above_open(E.view_upto(b, 3), CTX) is None


def test_r3_orb_breakout_window():
    b = flat(10000.0)
    put(b, 2, 10000, 10100, 9950, 10050)      # 09:00~09:04 고가 = 10,100
    assert R.r3_orb_breakout(_v(b, 4, 10200), CTX) is False   # 09:04 진입 금지
    assert R.r3_orb_breakout(_v(b, 6, 10150), CTX) is True
    assert R.r3_orb_breakout(_v(b, 6, 10100), CTX) is False   # 같으면 돌파 아님
    assert R.r3_orb_breakout(_v(b, 30, 10150), CTX) is True   # 09:30 포함
    assert R.r3_orb_breakout(_v(b, 31, 10150), CTX) is False  # 09:31 뒤 skip
    nb = np.full((E.N_SLOTS, E.N_FIELDS), np.nan)
    nb[6, E.F_CLOSE] = 10000
    assert R.r3_orb_breakout(E.view_upto(nb, 6), CTX) is None  # 09:00~09:04 고가 모름


def test_r3_skip_day_through_engine_when_no_breakout():
    r = E.run_day(flat(10000.0), CTX, R.r3_orb_breakout, 0.1, 0.1)
    assert not r.entered and r.skip_reason == E.SKIP_NO_ENTRY and r.undetermined_minutes == 0


def test_r7_off_high():
    b = flat(10000.0)
    put(b, 5, 10000, 11000, 10000, 10500)
    assert R.r7_off_high(_v(b, 10, 10440), CTX) is False      # ≤ 11,000 × 0.95 = 10,450
    assert R.r7_off_high(_v(b, 10, 10450), CTX) is False      # 정확히 = 선 → skip(≤)
    assert R.r7_off_high(_v(b, 10, 10500), CTX) is True


def test_r6_spike_over_prior_5min_low_and_exact_tie():
    b = flat(10000.0)
    put(b, 4, 10000, 10000, 9900, 10000)      # 직전 5분(행 5..9) 밖 — 영향 없음
    assert R.r6_spike(_v(b, 10, 10310), CTX) is False
    assert R.r6_spike(_v(b, 10, 10290), CTX) is True
    assert R.r6_spike(_v(b, 10, 10300), CTX) is False         # 정확히 +3% → skip(≥)
    put(b, 7, 10000, 10000, 9950, 10000)      # 창 안 최저 9,950 → 10,290 / 9,950 = +3.4%
    assert R.r6_spike(_v(b, 10, 10290), CTX) is False


def test_r6_window_clipped_at_0900_and_undetermined():
    b = flat(10000.0)
    put(b, 0, 10000, 10000, 9700, 10000)      # 09:00 저가 9,700
    assert R.r6_spike(_v(b, 3, 10000), CTX) is False          # 09:03 창 = 09:00~09:02 → +3.09%
    assert R.r6_spike(_v(b, 6, 10000), CTX) is True           # 09:06 창 = 09:01~09:05 → 09:00 빠짐
    nb = np.full((E.N_SLOTS, E.N_FIELDS), np.nan)
    nb[3, E.F_CLOSE] = 10000
    assert R.r6_spike(E.view_upto(nb, 3), CTX) is None        # 창에 저가 없음


def _label(fn, b, ctx=CTX):
    return E.label_day(b, ctx, fn)


def test_r4_label_keep_filter_undetermined():
    b = flat(10000.0)
    put(b, 4, 10000, 10000, 9800, 9800)                        # −2.0% 정확히 → filter(≤)
    assert _label(R.r4_first5_drop, b) == E.LABEL_FILTER
    put(b, 4, 10000, 10000, 9810, 9810)
    assert _label(R.r4_first5_drop, b) == E.LABEL_KEEP
    nb = np.full((E.N_SLOTS, E.N_FIELDS), np.nan)              # 09:00~09:04 거래 0 → 시가·09:04 종가 모름
    nb[5:, :] = flat(10000.0)[5:]
    assert _label(R.r4_first5_drop, nb) == E.LABEL_UNDETERMINED
    with pytest.raises(ValueError):
        R.r4_first5_drop(E.view_upto(b, 4), CTX)               # 09:05 전 view 금지


def test_r5_label_keep_filter_undetermined():
    b = flat(10000.0, vol=100.0)              # 5분 합 500 < 100,000 × 2%
    assert _label(R.r5_first5_volume, b) == E.LABEL_FILTER
    b2 = flat(10000.0, vol=400.0)             # 2,000 = 2,000 → 미만 아님 → keep
    assert _label(R.r5_first5_volume, b2) == E.LABEL_KEEP
    U = E.LABEL_UNDETERMINED
    assert _label(R.r5_first5_volume, b2, E.DayCtx("000001", CTX.day)) == U                  # 전일 거래량 모름
    assert _label(R.r5_first5_volume, b2, E.DayCtx("000001", CTX.day, prev_day_volume=0.0)) == U
    assert _label(R.r5_first5_volume, b2, E.DayCtx("000001", CTX.day, prev_day_volume=1e5, corp_event=True)) == U


def test_h2_hist_enters_first_band_minute_from_0910():
    b = flat(10000.0)
    assert R.h2_hist(_v(b, 9), CTX) is False and R.h2_hist(_v(b, 10), CTX) is True
    r = R.run_rule(b, CTX, R.REGISTRY["H2_HIST"], 0.1, 0.1)
    assert r.entry.idx == 10 and r.entry.time == "091000"
    hb = flat(10500.0)                        # 09:10 은 밴드 밖 → 그 뒤 첫 밴드 안 분
    hb[12:E.N_CONT, :4] = 10200
    r2 = R.run_rule(hb, E.DayCtx("000001", CTX.day, band_hi=10300.0), R.REGISTRY["H2_HIST"], 0.1, 0.1)
    assert r2.entry.idx == 12


def test_h_plus2_skip_above_prev_close_2pct():
    b = flat(10000.0)
    assert R.h_plus2(_v(b, 5, 10210), CTX) is False
    assert R.h_plus2(_v(b, 5, 10200), CTX) is True            # 정확히 +2% → 허용(엄격 >)
    assert R.h_plus2(_v(b, 5, 10000), E.DayCtx("000001", CTX.day)) is None   # 전일 종가 모름


def test_run_rule_filter_uses_r0_0905_for_both_labels():
    keep = flat(10000.0, vol=5000.0)
    filt = flat(10000.0, vol=1.0)
    rk = R.run_rule(keep, CTX, R.REGISTRY["R5"], 0.1, 0.1)
    rf = R.run_rule(filt, CTX, R.REGISTRY["R5"], 0.1, 0.1)
    assert (rk.label, rf.label) == (E.LABEL_KEEP, E.LABEL_FILTER)
    assert rk.entered and rf.entered and rk.entry.idx == rf.entry.idx == 5   # 두 군 모두 09:05 진입
    assert rk.base == rf.base == E.BASE_R0_0905
    r0 = R.run_rule(keep, CTX, R.BASELINE, 0.1, 0.1)
    assert r0.entry.idx == 2 and r0.label is None


def test_undetermined_minutes_counted_per_lot():
    b = np.full((E.N_SLOTS, E.N_FIELDS), np.nan)
    b[2:E.N_CONT, E.F_CLOSE] = 10000.0        # 종가만 있고 저가 없음 → R6 창 저가 모름(행 2..6 판단 불가)
    b[2:E.N_CONT, E.F_LOW] = np.nan
    b[7:E.N_CONT, :4] = 10000.0               # 09:07 부터 완성 봉 → 09:08 창(09:03~09:07)에 저가 있음
    r = R.run_rule(b, CTX, R.REGISTRY["R6"], 0.1, 0.1)
    assert r.entry.idx == 8 and r.undetermined_minutes == 6   # 09:02~09:07
    assert R.run_rule(flat(), CTX, R.REGISTRY["R6"], 0.1, 0.1).undetermined_minutes == 0
