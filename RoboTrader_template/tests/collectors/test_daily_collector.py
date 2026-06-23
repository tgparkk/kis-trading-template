# tests/collectors/test_daily_collector.py
from collectors.daily_collector import reconcile_verdict


def test_reconcile_verdict_pass_when_full_coverage_and_match():
    v = reconcile_verdict(real_rows=2600, new_rows=2600, value_match=2598)
    assert v["coverage"] >= 0.99
    assert v["value_match_rate"] >= 0.99
    assert v["verdict"] == "PASS"


def test_reconcile_verdict_fail_on_low_coverage():
    v = reconcile_verdict(real_rows=2600, new_rows=1500, value_match=1500)
    assert v["verdict"] == "FAIL"


def test_reconcile_verdict_handles_zero_real():
    v = reconcile_verdict(real_rows=0, new_rows=0, value_match=0)
    assert v["verdict"] in ("PASS", "EMPTY")
