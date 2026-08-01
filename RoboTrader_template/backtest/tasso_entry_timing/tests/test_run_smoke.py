from lab.run import required_outputs


def test_all_five_mandatory_artifacts_are_declared():
    """FAIL 이어도 이 다섯은 반드시 나온다 (사전등록 §5)."""
    names = set(required_outputs())
    assert {"by_year.csv", "truncation.csv", "cells.csv",
            "by_bucket.csv", "calibration_scores.csv"} <= names


def test_truncation_is_reported_for_both_arms():
    from lab.run import TRUNCATION_COLUMNS
    assert "strategy_truncated" in TRUNCATION_COLUMNS
    assert "control_truncated" in TRUNCATION_COLUMNS


def test_pit_gate_keeps_open_windows_out_of_history():
    """아직 창이 안 닫힌 표본이 분포에 새면 그게 look-ahead 다."""
    from lab.run import flush_pending
    pending = [("2026-03-01", 0.5, 0.2), ("2026-09-01", 0.6, 0.3)]
    ready, still = flush_pending(pending, as_of="2026-06-01")
    assert ready == [(0.5, 0.2)]
    assert still == [("2026-09-01", 0.6, 0.3)]


def test_pit_gate_is_inclusive_on_the_boundary_date():
    from lab.run import flush_pending
    ready, still = flush_pending([("2026-06-01", 0.5, 0.2)], as_of="2026-06-01")
    assert ready == [(0.5, 0.2)] and still == []


def test_control_seed_is_reproducible_across_processes():
    """내장 hash() 를 쓰면 실행마다 대조군이 달라져 증거가 못 된다."""
    from lab.run import _seed
    assert _seed("064260", "2026-07-23", "pit", 0.8) == _seed("064260", "2026-07-23", "pit", 0.8)
    assert _seed("064260", "2026-07-23", "pit", 0.8) != _seed("064260", "2026-07-23", "exo", 0.8)
