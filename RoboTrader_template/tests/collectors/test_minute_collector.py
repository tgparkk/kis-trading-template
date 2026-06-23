# tests/collectors/test_minute_collector.py
from collectors.minute_collector import minute_match_rate


def test_minute_match_rate_on_intersection():
    # 교집합 종목만, 바 일치 비율
    new = {"A": {("090100", 100.0), ("090200", 101.0)},
           "B": {("090100", 50.0)}}
    legacy = {"A": {("090100", 100.0), ("090200", 101.0)},
              "C": {("090100", 9.0)}}
    rate, overlap = minute_match_rate(new, legacy)
    # 교집합 종목 = {A}; A 바 2개 모두 일치 → 1.0
    assert overlap == 1
    assert rate == 1.0


def test_minute_match_rate_no_overlap():
    rate, overlap = minute_match_rate({"A": set()}, {"B": set()})
    assert overlap == 0
    assert rate == 0.0
