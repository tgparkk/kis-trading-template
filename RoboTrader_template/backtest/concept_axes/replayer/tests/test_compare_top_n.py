"""전수 저장(09-28~) 대응 — `run.segment_max_candidates` · `gate.compute_metrics` 비교 절단."""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.concept_axes.replayer import gate, run
from config.constants import MAX_CANDIDATES_PER_STRATEGY


# ── (a) max_candidates None-safe 헬퍼 ────────────────────────────────────────

def test_segment_max_candidates_none_uses_default():
    assert run.segment_max_candidates({"max_candidates": None}, 20) == 20


def test_segment_max_candidates_explicit_value_kept():
    assert run.segment_max_candidates({"max_candidates": 15}, 20) == 15


def test_segment_max_candidates_missing_key_uses_default():
    assert run.segment_max_candidates({}, 20) == 20


def test_compare_top_n_matches_live_consumption_cap():
    assert gate.COMPARE_TOP_N == MAX_CANDIDATES_PER_STRATEGY


def test_reverdict_end_is_0922():
    assert run.REVERDICT_END == "2026-09-22"


# ── (b) 라이브 35개 vs 재현 20개 → 라이브가 rank ≤ 20 으로 잘린다 ───────────

def _codes(a, b):
    return ["C{:03d}".format(i) for i in range(a, b + 1)]


def test_live_35_truncated_to_top20_for_m1():
    live = _codes(1, 35)                        # rank 1~35 (전수 저장 형식)
    replay = _codes(1, 18) + ["X1", "X2"]      # 상위 18 일치 + 재현 전용 2
    m = gate.compute_metrics([gate.DayPair("2026-09-28", live=live, replay=replay)])
    # 절단 후: 라이브 C001~C020 · 교집합 18 · 합집합 22
    assert m["n_inter"] == 18
    assert m["n_union"] == 22
    assert m["M1"] == pytest.approx(18 / 22)
    assert m["n_live"] == 20
    # 절단이 없었다면 합집합 37 → M1 18/37 (왜곡)
    assert m["M1"] != pytest.approx(18 / 37)


def test_build_day_pairs_orders_live_by_rank():
    live = pd.DataFrame({
        "scan_date": pd.to_datetime(["2026-09-28"] * 3),
        "stock_code": ["B", "C", "A"],
        "rank_in_snapshot": [2, 3, 1],
        "score": [2.0, 1.0, 3.0],
    })
    led = pd.DataFrame(columns=["scan_date", "stock_code", "score"])
    (dp,) = run.build_day_pairs(live, led)
    assert dp.live == ["A", "B", "C"]


# ── (c) 기존 형식(라이브 ≤ 20)은 절단이 항등 ─────────────────────────────────

def test_truncation_is_identity_when_live_at_most_20():
    days = [
        gate.DayPair("2026-09-01", live=_codes(1, 20), replay=_codes(3, 22),
                     live_scores={c: float(i) for i, c in enumerate(_codes(1, 20))},
                     replay_scores={c: float(i) for i, c in enumerate(_codes(3, 22))}),
        gate.DayPair("2026-09-02", live=_codes(1, 7), replay=_codes(2, 21),
                     live_scores={"C002": 1.0}, replay_scores={"C002": 1.0}),
    ]
    got = gate.compute_metrics(days)
    old_top = gate.COMPARE_TOP_N
    try:
        gate.COMPARE_TOP_N = 10 ** 9            # 사실상 절단 없음 = 수정 전 동작
        ref = gate.compute_metrics(days)
    finally:
        gate.COMPARE_TOP_N = old_top
    assert got.keys() == ref.keys()
    for k in ref:
        a, b = got[k], ref[k]
        if isinstance(b, float) and b != b:
            assert a != a, k
        else:
            assert a == b, k


# ── classify_days 도 같은 절단 ────────────────────────────────────────────────

def _classify(days):
    live = pd.DataFrame(columns=["scan_date", "created_at"])
    return run.classify_days(days, live, impossible={}, uni_info={}, boundary_dates=set())


def test_classify_days_live_35_excludes_rank_21_plus():
    days = [gate.DayPair("2026-09-28", live=_codes(1, 35), replay=_codes(1, 18) + ["X1", "X2"])]
    df = _classify(days)
    only_live = set(df.loc[df["side"] == "live_only", "stock_code"])
    assert only_live == {"C019", "C020"}
    assert set(df.loc[df["side"] == "replay_only", "stock_code"]) == {"X1", "X2"}


def test_classify_days_identity_when_live_at_most_20():
    days = [gate.DayPair("2026-09-01", live=_codes(1, 20), replay=_codes(3, 22)),
            gate.DayPair("2026-09-02", live=_codes(1, 7), replay=_codes(2, 21))]
    got = _classify(days)
    old_top = gate.COMPARE_TOP_N
    try:
        gate.COMPARE_TOP_N = 10 ** 9            # 사실상 절단 없음 = 수정 전 동작
        ref = _classify(days)
    finally:
        gate.COMPARE_TOP_N = old_top
    pd.testing.assert_frame_equal(got, ref)
    assert len(got) > 0
