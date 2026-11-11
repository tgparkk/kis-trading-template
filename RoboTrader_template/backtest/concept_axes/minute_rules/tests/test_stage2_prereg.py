"""사전등록 §9 ⑫·⑭~⑳ 의 «실행기 수준» 판 — 합성 번들(`MinuteBundle`)로 `run.build_rows` 를 돌려 열을 본다(DB 0).

단위 수준 판은 1단계(`test_engine.py`·`test_rules.py`·`test_data.py`)에 있고 그대로 통과해야 한다.
"""
from __future__ import annotations

import csv
import hashlib
import io
from datetime import date

import numpy as np
import pytest

from backtest.concept_axes.minute_rules import data as D
from backtest.concept_axes.minute_rules import engine as E
from backtest.concept_axes.minute_rules import rules as R
from backtest.concept_axes.minute_rules import run as RUN

from .synth import flat, path, put
from .test_run import CAL, D0, D1, DT, daily_flat

D1B = CAL[6]


def lot(code, d0=D0, d1=D1, ref=10000.0, **kw):
    return RUN.Lot("A", DT, d0, d1, code, "1", ref, None, ref * 1.03, True, "", **kw)


def bundle(items, excluded=None):
    """items = [(lot, bars float64, DayMeta 덮어쓰기 dict)] → MinuteBundle(float32 · 체크섬 임의)."""
    keys = [x.key for x, _, _ in items]
    bars = np.stack([b.astype(np.float32) for _, b, _ in items])
    observed = np.nan_to_num(bars[:, :, E.F_VOL]) > 0
    metas = [D.DayMeta(code=x.code, day=x.entry_date, n_rows=380, **dict({"prev_day_volume": 50_000.0}, **kw))
             for x, _, kw in items]
    return D.MinuteBundle(keys, bars, observed, metas, dict(excluded or {}), {k: (380, 0.0, 0.0) for k in keys})


def build(items, lots_extra=(), window="E", excluded=None, fakes=0):
    lots = [x for x, _, _ in items] + list(lots_extra)
    codes = {x.code for x in lots}
    daily = {}
    for c in codes:
        daily.update(daily_flat(code=c))
    return RUN.build_rows(window, RUN.WINDOWS[window], lots, bundle(items, excluded), daily, CAL,
                          {"A": CAL[-1], "B": CAL[-1]}, {c: "KOSDAQ" for c in codes}, fakes=fakes)


def by(rows, code, arm):
    return next(r for r in rows if r["stock_code"] == code and r["arm"] == arm)


def test_14_filter_labels_both_groups_enter_at_r0_0905():
    keep_b = flat(10000.0)
    filt_b = flat(10000.0)
    path(filt_b, 1, [9950, 9900, 9850, 9790, 9790])        # 09:04 종가 9,790 ÷ 시가 10,000 − 1 = −2.1% → R4 filter
    rows, _, _ = build([(lot("000001"), keep_b, {}), (lot("000002"), filt_b, {})])
    for code, want in (("000001", E.LABEL_KEEP), ("000002", E.LABEL_FILTER)):
        r4, base = by(rows, code, "R4"), by(rows, code, "R0_0905")
        assert r4["label"] == want and r4["entered"] and r4["entry_time"] == base["entry_time"] == "090500"
        assert r4["ret"] == base["ret"] and r4["px_tick"] == base["px_tick"]
        assert by(rows, code, "R0")["entry_time"] == "090200"


def test_15_r5_undetermined_filter_and_adj_null_at_run_level():
    zero5 = flat(10000.0)
    zero5[:5, E.F_VOL] = 0.0                               # 09:00~09:04 거래 0 → filter(판단 불가 아님)
    a, b, c, d = lot("000001", corp_event=True), lot("000002"), lot("000003"), lot("000004")
    rows, _, cnt = build([(a, flat(10000.0, vol=5000.0), {}),
                          (b, flat(10000.0, vol=5000.0), {"prev_day_volume": 0.0}),
                          (c, zero5, {}),
                          (d, flat(10000.0, vol=5000.0), {"adj_null_prev": True, "adj_null_entry": True})])
    assert by(rows, "000001", "R5")["label"] == E.LABEL_UNDETERMINED and by(rows, "000001", "R5")["corp_event"]
    assert by(rows, "000002", "R5")["label"] == E.LABEL_UNDETERMINED
    assert by(rows, "000003", "R5")["label"] == E.LABEL_FILTER
    r = by(rows, "000004", "R5")
    assert r["label"] == E.LABEL_KEEP and r["adj_null_prev"] and r["adj_null_entry"]   # 25,000 ≥ 1,000 → keep
    assert cnt["adj_null_prev"] == 1 and cnt["corp_event"] == 1


def test_15b_adj_none_is_one_in_data_apply_daily_and_label_kept():
    m = D.DayMeta(code="000001", day=D1)
    daily = {("000001", D1): (10000, 10000, 60_000, None), ("000001", D0): (10000, 10000, 60_000, None)}
    D.apply_daily(m, flat(), daily, D0)
    assert m.prev_day_volume == 60_000 and m.adj_null_prev and m.adj_null_entry
    ctx = E.DayCtx("000001", D1, prev_day_volume=m.prev_day_volume)
    assert E.label_day(flat(vol=100.0), ctx, R.REGISTRY["R5"].label) == E.LABEL_FILTER    # 500 < 1,200


def test_16_market_gap_day_excluded_long_gap_info_only():
    rows, _, cnt = build([(lot("000001"), flat(), {"market_gap_day": True}),
                          (lot("000002"), flat(), {"long_gap": True, "long_gap_minutes": 25})])
    a, b = by(rows, "000001", "R0"), by(rows, "000002", "R0")
    assert a["market_gap_day"] and "market_gap_day" in a["main_excl"].split(";")
    assert b["long_gap"] and b["long_gap_minutes"] == 25 and b["main_excl"] == "" and b["entered"]
    assert cnt["market_gap_day"] == 1 and cnt["long_gap"] == 1


def test_17_model_b_next_open_out_of_band_is_missing_not_cash():
    b = flat(10000.0)
    put(b, 3, 10500, 10500, 10500, 10500)
    rows, _, _ = build([(lot("000001"), b, {})])
    r = by(rows, "000001", "R0")
    assert r["entered"] and r["b_missing"] is True and r["b_ret"] is None and r["ret"] is not None
    parsed = next(csv.DictReader(io.StringIO(RUN.csv_text(RUN.LOT_COLS, [r]))))
    assert parsed["b_ret"] == "" and parsed["ret"] != ""               # 결측 = 빈 칸(0 아님)


def test_18_snapshot_lots_calendar_next_trading_day_and_order():
    sat = date(2025, 6, 7)                                 # 토요일 scan_date → 다음 거래일 월요일
    assert sat.weekday() == 5
    daily = {}
    for c in ("999999", "000001"):
        daily.update(daily_flat(code=c, days=CAL + [sat]))
    snap = [(DT, CAL[10], "000001", 2), (DT, CAL[2], "999999", 1), (DT, sat, "000001", 1), (DT, CAL[2], "999999", 3)]
    lots, counts = RUN.lots_from_snapshots(snap, [DT], CAL, daily, CAL[0], {DT: CAL[20]})
    got = sorted((x.code, x.scan_date, x.entry_date) for x in lots)
    assert got == [("000001", sat, date(2025, 6, 9)), ("000001", CAL[10], CAL[11]), ("999999", CAL[2], CAL[3])]
    assert counts["dup"] == 1
    assert all(x.band_hi == pytest.approx(x.ref_close * 1.03) and x.band_lo is None for x in lots)
    rows, _, _ = build([(lot("999999", d0=CAL[8], d1=CAL[9]), flat(), {}), (lot("000001"), flat(), {})])
    assert [r["stock_code"] for r in rows if r["arm"] == "R0"] == ["000001", "999999"]   # 날짜 순(코드 순 아님)


def _walk(seed):
    rng = np.random.default_rng(seed)
    b = flat(10000.0)
    path(b, 0, np.round(10000.0 * np.cumprod(1 + rng.normal(0, 0.012, E.N_CONT)), -1))
    return b


def test_19_timing_rules_not_degenerate_across_lots():
    """퇴화 검사(리뷰 A5)의 실행기판 — 규칙마다 «R0 과 같은 진입» 로트와 «다른 진입(또는 현금)» 로트가 둘 다 나온다."""
    r1 = flat(10000.0)
    put(r1, 2, 10000, 10250, 10000, 10250)                  # +2.5% > 시가 × 1.02 → R1 skip(뒤도 10,250 → 현금)
    path(r1, 3, [10250])
    r3 = flat(10000.0)
    path(r3, 6, [10100])                                    # 09:06 시가 범위 고가 돌파 → R3 진입
    r7 = flat(10000.0)
    put(r7, 1, 10000, 10600, 10000, 10000)                  # 그때까지 고가 10,600 × 0.95 = 10,070 ≥ 현재가 → R7 skip
    r6 = flat(10000.0)
    put(r6, 1, 10000, 10000, 9700, 10000)                   # 현재가 ÷ 직전 5분 최저 9,700 − 1 = +3.1% → R6 skip
    items = [(lot("000000"), flat(10000.0), {})]
    items += [(lot(f"00000{i}"), b, {}) for i, b in enumerate((r1, r3, r7, r6), 1)]
    rows, _, _ = build(items)
    for rid in ("R1", "R3", "R7", "R6"):
        kinds = {(by(rows, x.code, rid)["entered"], by(rows, x.code, rid).get("entry_time") ==
                  by(rows, x.code, "R0").get("entry_time")) for x, _, _ in items}
        assert len(kinds) >= 2, (rid, kinds)


def test_20_r1_tie_allowed_r6_exact_3pct_skipped_at_run_level():
    b = flat(10000.0)
    put(b, 2, 10000, 10300, 10000, 10200)                  # 09:02 종가 = 시가 × 1.02 정확히 → R1 허용
    c = flat(10000.0)
    put(c, 2, 10000, 10300, 10000, 10300)                  # 09:02 종가 ÷ 직전 최저 10,000 − 1 = +3% → R6 skip
    rows, _, _ = build([(lot("000001"), b, {}), (lot("000002"), c, {})])
    assert by(rows, "000001", "R1")["entry_time"] == "090200"
    assert by(rows, "000002", "R6")["entry_time"] != "090200" and by(rows, "000002", "R0")["entry_time"] == "090200"


def test_12_same_input_same_bytes_and_fakes_deterministic():
    items = [(lot(f"{i:06d}", d0=CAL[i % 5], d1=CAL[i % 5 + 1]), _walk(i), {}) for i in range(12)]
    r1, f1, _ = build(items, fakes=3)
    r2, f2, _ = build(list(reversed(items)), fakes=3)
    t1, t2 = RUN.csv_text(RUN.LOT_COLS, r1), RUN.csv_text(RUN.LOT_COLS, r2)
    assert hashlib.sha256(t1.encode()).hexdigest() == hashlib.sha256(t2.encode()).hexdigest()
    assert RUN.csv_text(RUN.FAKE_COLS, f1) == RUN.csv_text(RUN.FAKE_COLS, f2)
    assert len(f1) == 3 * 12 and all(RUN.FAKE_U_LO <= r["u_idx"] <= RUN.FAKE_U_HI for r in f1)
    for r in f1:
        if r["entered"]:
            assert int(r["entry_time"][:2]) * 60 + int(r["entry_time"][2:4]) - 540 >= r["u_idx"]


def test_excluded_lots_keep_rows_with_daily_fallback_and_plumbing_counts():
    nm = lot("000009")
    rows, _, cnt = build([(lot("000001"), flat(), {})], lots_extra=[nm],
                         excluded={nm.key: D.EXCL_NO_MINUTE})
    r = by(rows, "000009", "R0")
    assert r["daily_fallback"] and r["excl_reason"] == D.EXCL_NO_MINUTE and "ret" not in r
    assert cnt["lots"] == 2 and cnt["minute_lots"] == 1 and cnt[f"excl_{D.EXCL_NO_MINUTE}"] == 1
    lots = [lot("000001"), nm]
    rows2, _, cnt2 = RUN.build_rows("E", RUN.WINDOWS["E"], lots, bundle([(lots[0], flat(), {})],
                                    {nm.key: D.EXCL_NO_MINUTE}), daily_flat(), CAL, {"A": CAL[-1]},
                                    {}, simulate=False)
    assert cnt2["minute_lots"] == 1 and not any("ret" in x for x in rows2)


def test_u_window_print_only_from_0601_and_independent_arms():
    late = lot("000001", d0=date(2026, 6, 1), d1=date(2026, 6, 2))
    cal = CAL + [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    rows, _, cnt = RUN.build_rows("U", RUN.WINDOWS["U"], [late], bundle([(late, flat(), {})]),
                                  daily_flat(days=cal), cal, {"A": cal[-1]}, {"000001": "KOSPI"})
    assert {r["arm"] for r in rows} == {"R0", "H2_HIST", "H_PLUS2"} and all(r["print_only"] for r in rows)
    assert by(rows, "000001", "H2_HIST")["entry_time"] == "091000" and cnt["print_only"] == 1
