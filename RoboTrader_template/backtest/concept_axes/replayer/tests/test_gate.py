"""gate.py 단위 — 설계서 §4-3(M1~M4) · §4-4-c(구간 분할) · §4-5(C1~C6) · §7 V5-a."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from backtest.concept_axes.replayer import gate


# ── §4-3 M1 일별 집합 Jaccard (마이크로 평균) ──────────────────────────────

def test_m1_micro_average_is_sum_inter_over_sum_union():
    days = [
        gate.DayPair("2026-06-05", live=["A", "B", "C"], replay=["A", "B", "C"], live_scores={}, replay_scores={}),
        gate.DayPair("2026-06-08", live=["A", "B"], replay=["A", "X"], live_scores={}, replay_scores={}),
    ]
    m = gate.compute_metrics(days)
    # 교집합 3+1=4 · 합집합 3+3=6
    assert m["M1"] == pytest.approx(4 / 6)


def test_m1_perfect_match_is_one():
    days = [gate.DayPair("d", live=["A"], replay=["A"], live_scores={}, replay_scores={})]
    assert gate.compute_metrics(days)["M1"] == pytest.approx(1.0)


# ── M2 순위 상관 (교집합 원소 2개 미만인 날은 분모에서 제외) ────────────────

def test_m2_median_spearman_and_skipped_days_counted():
    days = [
        gate.DayPair("d1", live=["A", "B", "C"], replay=["A", "B", "C"], live_scores={}, replay_scores={}),
        gate.DayPair("d2", live=["A"], replay=["A"], live_scores={}, replay_scores={}),   # 원소 1 → 제외
    ]
    m = gate.compute_metrics(days)
    assert m["M2"] == pytest.approx(1.0)
    assert m["M2_skipped_days"] == 1


def test_m2_detects_reversed_rank():
    days = [gate.DayPair("d1", live=["A", "B", "C"], replay=["C", "B", "A"],
                         live_scores={}, replay_scores={})]
    assert gate.compute_metrics(days)["M2"] == pytest.approx(-1.0)


# ── M3 상위 K=5 일치 ───────────────────────────────────────────────────────

def test_m3_top5_micro_average():
    live = ["A", "B", "C", "D", "E", "F"]
    replay = ["A", "B", "C", "D", "Z", "F"]
    days = [gate.DayPair("d1", live=live, replay=replay, live_scores={}, replay_scores={})]
    assert gate.compute_metrics(days)["M3"] == pytest.approx(4 / 5)


def test_m3_denominator_is_frozen_five_not_live_size():
    """🔒 동결 정의 = `/5`. 라이브가 2개뿐이고 둘 다 맞추어도 M3 = 2/5 다.

    🔴 이전 판은 `min(TOP_K, len(L))` 를 써서 1.0 을 돌려줬다 — «구현을 따라 쓴 테스트»라
    정의 위반을 잡을 수 없었다(리뷰 H-1).
    """
    days = [gate.DayPair("d1", live=["A", "B"], replay=["A", "B"],
                         live_scores={}, replay_scores={})]
    assert gate.compute_metrics(days)["M3"] == pytest.approx(2 / 5)


# ── M4 score 수치 일치 ─────────────────────────────────────────────────────

def test_m4_relative_error_within_1e_minus_6():
    days = [gate.DayPair("d1", live=["A", "B"], replay=["A", "B"],
                         live_scores={"A": 100.0, "B": 200.0},
                         replay_scores={"A": 100.0, "B": 200.0 * (1 + 1e-9)})]
    assert gate.compute_metrics(days)["M4"] == pytest.approx(1.0)


def test_m4_catches_data_refresh():
    days = [gate.DayPair("d1", live=["A", "B"], replay=["A", "B"],
                         live_scores={"A": 100.0, "B": 200.0},
                         replay_scores={"A": 100.0, "B": 260.0})]
    assert gate.compute_metrics(days)["M4"] == pytest.approx(0.5)


# ── §4-4-c 구간 분할 ───────────────────────────────────────────────────────

def test_split_exposed_vs_protected_at_2026_09_03():
    days = [gate.DayPair("2026-09-02", ["A"], ["A"], {}, {}),
            gate.DayPair("2026-09-03", ["A"], ["B"], {}, {})]
    parts = gate.split_windows(days)
    assert [d.scan_date for d in parts["노출(≤2026-09-02)"]] == ["2026-09-02"]
    assert [d.scan_date for d in parts["보호(≥2026-09-03)"]] == ["2026-09-03"]


def test_split_preferred_onboarding_at_2026_08_05():
    days = [gate.DayPair("2026-08-04", ["A"], ["A"], {}, {}),
            gate.DayPair("2026-08-05", ["A"], ["A"], {}, {})]
    parts = gate.split_windows(days)
    assert len(parts["우선주 온보딩 전(≤2026-08-04)"]) == 1
    assert len(parts["우선주 온보딩 후(≥2026-08-05)"]) == 1


# ── §4-5 원인 분류 C1~C6 ──────────────────────────────────────────────────

def test_classify_c5_tie_boundary():
    """불일치가 rank 19~20 에만 있고 score 가 같으면 C5(동점 경계)."""
    lab = gate.classify_mismatch(
        code="Z", side="replay_only", live_rank=None, replay_rank=20,
        score_match=True, created_late=False, hash_changed=False,
        impossible_in_window=False, at_params_boundary=False, set_swept=False)
    assert lab == "C5"


def test_classify_c1_data_refresh_by_created_at():
    lab = gate.classify_mismatch(
        code="Z", side="live_only", live_rank=3, replay_rank=None,
        score_match=False, created_late=True, hash_changed=False,
        impossible_in_window=False, at_params_boundary=False, set_swept=False)
    assert lab == "C1"


def test_classify_c2_universe_date_fallback_when_set_swept():
    lab = gate.classify_mismatch(
        code="Z", side="live_only", live_rank=3, replay_rank=None,
        score_match=False, created_late=False, hash_changed=False,
        impossible_in_window=False, at_params_boundary=False, set_swept=True)
    assert lab == "C2"


def test_classify_c3_impossible_bar_guard():
    lab = gate.classify_mismatch(
        code="Z", side="live_only", live_rank=3, replay_rank=None,
        score_match=False, created_late=False, hash_changed=False,
        impossible_in_window=True, at_params_boundary=False, set_swept=False)
    assert lab == "C3"


def test_classify_c6_unknown_when_no_signature_matches():
    lab = gate.classify_mismatch(
        code="Z", side="live_only", live_rank=3, replay_rank=None,
        score_match=False, created_late=False, hash_changed=False,
        impossible_in_window=False, at_params_boundary=False, set_swept=False)
    assert lab == "C6"


def test_classify_c7_exclusion_promotion_split_from_c6():
    """배제로 빈 슬롯만큼 밀려 올라온 건은 C6(미상)이 아니라 C7 다."""
    lab = gate.classify_mismatch(
        code="Z", side="replay_only", live_rank=None, replay_rank=3,
        score_match=False, created_late=False, hash_changed=False,
        impossible_in_window=False, at_params_boundary=False, set_swept=False,
        exclusion_promoted=True)
    assert lab == "C7"


def test_c7_does_not_swallow_earlier_signatures():
    """C7 은 **C6 에서만** 분리한다 — C1·C3 서명을 가리면 안 된다."""
    lab = gate.classify_mismatch(
        code="Z", side="replay_only", live_rank=None, replay_rank=3,
        score_match=False, created_late=True, hash_changed=False,
        impossible_in_window=False, at_params_boundary=False, set_swept=False,
        exclusion_promoted=True)
    assert lab == "C1"


# ── §4-5 C1 서명 ② — «거래일» 기준(리뷰 H-2) ─────────────────

CAL = [pd.Timestamp(x) for x in
       ["2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15"]]   # 09-12·13 = 주말


def test_next_trading_day_skips_weekend():
    assert gate.next_trading_day(CAL, "2026-09-11") == pd.Timestamp("2026-09-14")
    assert gate.next_trading_day(CAL, "2026-09-15") is None


def test_created_late_friday_is_not_late_by_trading_day_rule():
    """🔴 구 서명(달력 +3일)은 금요일을 전부 지연으로 읽었다 — 월요일 재수집은 정상이다."""
    ca = pd.Timestamp("2026-09-14 08:30")        # 금요일(09-11) 스캣의 월요일 재기록
    assert ca > pd.Timestamp("2026-09-11") + pd.Timedelta(days=3)   # 구 서명: 지연
    assert gate.created_late(ca, "2026-09-11", CAL) is False        # 신 서명: 정상


def test_created_late_true_when_past_next_trading_day_noon():
    assert gate.created_late(pd.Timestamp("2026-09-14 13:00"), "2026-09-11", CAL) is True


def test_created_late_none_or_window_end_is_not_c1():
    assert gate.created_late(None, "2026-09-11", CAL) is False
    assert gate.created_late(pd.Timestamp("2026-12-31"), "2026-09-15", CAL) is False


# ── §7 V5-a 실행 시간창 ───────────────────────────────────────────────────

def test_v5a_rejects_weekday_0900_to_0920_kst():
    # 2026-09-15 는 화요일
    assert gate.time_window_ok(dt.datetime(2026, 9, 15, 9, 10)) is False
    assert gate.time_window_ok(dt.datetime(2026, 9, 15, 9, 0)) is False
    assert gate.time_window_ok(dt.datetime(2026, 9, 15, 9, 20)) is False


def test_v5a_allows_other_hours_and_weekends():
    assert gate.time_window_ok(dt.datetime(2026, 9, 15, 8, 40)) is True
    assert gate.time_window_ok(dt.datetime(2026, 9, 15, 15, 45)) is True
    assert gate.time_window_ok(dt.datetime(2026, 9, 15, 9, 21)) is True
    # 2026-09-13 은 일요일 → 09:10 이어도 허용
    assert gate.time_window_ok(dt.datetime(2026, 9, 13, 9, 10)) is True


# ── §4-3 문턱은 «미리 고정» — 코드에 상수로 박혀 있다 ──────────────────────

def test_thresholds_are_frozen_constants():
    assert gate.THRESHOLDS == {"M1_pass": 0.98, "M1_conditional": 0.95,
                               "M2_pass": 0.98, "M3_pass": 0.95, "M4_pass": 0.99,
                               "M1_exposed_floor": 0.90, "protected_min_days": 15}


def test_verdict_fail_below_m1_095():
    v = gate.verdict({"M1": 0.90, "M2": 1.0, "M3": 1.0, "M4": 1.0})
    assert v == "FAIL"


def test_verdict_pass_requires_m1_m2_m3_m4():
    assert gate.verdict({"M1": 0.99, "M2": 1.0, "M3": 0.99, "M4": 1.0}) == "PASS"
    assert gate.verdict({"M1": 0.99, "M2": 1.0, "M3": 0.80, "M4": 1.0}) == "조건부"


def test_verdict_m2_below_threshold_blocks_pass():
    """리뷰 M-1 — M2 를 인쇄만 하고 판정에 안 쓰면 «순위가 깨졌는데 PASS» 가 난다."""
    assert gate.verdict({"M1": 0.99, "M2": 0.90, "M3": 0.99, "M4": 1.0}) == "조건부"


def test_verdict_m2_nan_is_not_a_failure_reason():
    """교집합 원소 < 2 가 전일이면 M2 는 «문턱 미달»이 아니라 «재지 불가»다."""
    assert gate.verdict({"M1": 0.99, "M2": float("nan"), "M3": 0.99,
                         "M4": 1.0}) == "PASS"
