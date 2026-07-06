import scripts.kis_db.report_equivalence as rep


def test_classify_exact_match():
    assert rep.classify_diff(70000.0, 70050.0, tol=0.005) == "match"  # 0.07% < 0.5%


def test_classify_split_adjust_half():
    # 액면분할 1:2: 레거시 미조정 100000 vs 조정 50000 (÷2) → 설명 가능(개선)
    assert rep.classify_diff(100000.0, 50000.0) == "split_adjust"


def test_classify_split_adjust_tenth():
    assert rep.classify_diff(50000.0, 5000.0) == "split_adjust"


def test_classify_split_11x_explained():
    # 001130: 검증된 1:11 분할(DART "주식분할결정", kis adj_factor=11). 156500/11≈14227.
    # 고정 배수 집합에는 11 이 없어 예전엔 오탐 FAIL 이었음 — 일반 정수비 검출로 설명 가능.
    assert rep.classify_diff(156500.0, 14227.0) == "split_adjust"
    assert rep.classify_diff(14227.0, 156500.0) == "split_adjust"  # 역방향(대소 무관)


def test_classify_split_2_5x_explained():
    # 단주/액면 2.5 배 분할도 설명 가능
    assert rep.classify_diff(25000.0, 10000.0) == "split_adjust"


def test_classify_coverage_gap_when_one_missing():
    assert rep.classify_diff(None, 5000.0) == "coverage_gap"
    assert rep.classify_diff(5000.0, None) == "coverage_gap"


def test_classify_unexplained_random_diff():
    assert rep.classify_diff(10000.0, 12345.0) == "unexplained"  # 1.23x 불규칙(정수비 아님)


def test_build_report_pass_when_no_unexplained():
    legacy = {"A": 70000.0, "B": 100000.0, "C": 5000.0}
    new = {"A": 70050.0, "B": 50000.0, "C": None}  # A match, B split, C coverage_gap
    r = rep.build_equivalence_report("daily", legacy, new)
    assert r["counts"] == {"match": 1, "split_adjust": 1, "coverage_gap": 1, "unexplained": 0}
    assert r["verdict"] == "PASS"
    assert r["coverage"] == 2 / 3  # new 에 값이 있는 비율(교집합 종가 존재)


def test_build_report_fail_on_unexplained():
    legacy = {"A": 10000.0}
    new = {"A": 12345.0}
    r = rep.build_equivalence_report("daily", legacy, new)
    assert r["counts"]["unexplained"] == 1
    assert r["verdict"] == "FAIL"
    assert r["unexplained_samples"][:1] == [("A", 10000.0, 12345.0)]


def test_normalize_trade_date_hyphenated():
    assert rep._normalize_trade_date("2026-07-03") == "20260703"


def test_normalize_trade_date_already_compact():
    assert rep._normalize_trade_date("20260703") == "20260703"


def test_normalize_trade_date_year_end():
    assert rep._normalize_trade_date("2026-12-31") == "20261231"
