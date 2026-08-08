import os
import sys

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import p2_features as p2  # noqa: E402


def _rec(year, dt, eq=1000, cap=100, li=500, oi=50, fc=10):
    return {"bsns_year": year, "rcept_dt": dt, "total_equity": eq,
            "issued_capital": cap, "total_liabilities": li,
            "operating_income": oi, "finance_costs": fc}


def test_step_boundaries_start_the_day_after_receipt():
    """🔴 접수일 «당일»은 아직 안 보인다(장중 공시 가능). 다음 날부터 적용된다."""
    steps = p2.step_table([_rec("2020", "2021-03-19")])
    assert steps[0]["from_date"] == "2021-03-20"


def test_step_uses_latest_fiscal_year_not_latest_document():
    """🔴 Phase 1 F3 의 재발 방지. 2021년분 정정이 2023년분 원본을 이기면 안 된다."""
    recs = [_rec("2023", "2024-03-20", eq=300),
            _rec("2021", "2024-05-10", eq=100)]
    steps = p2.step_table(recs)
    last = steps[-1]
    assert last["bsns_year"] == "2023"
    assert last["from_date"] == "2024-05-11"   # 경계는 정정 접수 다음날에도 생긴다


def test_equity_impaired_is_the_only_hardcoded_rule():
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=-5)])
    assert steps[0]["equity_impaired"] is True
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=5)])
    assert steps[0]["equity_impaired"] is False


def test_equity_impaired_is_none_when_equity_is_unknown():
    """🔴 「모른다」를 「안전하다」로 읽으면 배제 필터가 그 종목을 통과시킨다."""
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=None)])
    assert steps[0]["equity_impaired"] is None
    assert steps[0]["equity_impaired"] is not False


def test_equity_impaired_zero_is_impairment_not_unknown():
    """자본총계가 정확히 0 이면 «잠식»이다 — 결측과 구별된다."""
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=0)])
    assert steps[0]["equity_impaired"] is True


def test_debt_ratio_is_none_when_equity_not_positive():
    """자본이 0 이하면 부채비율은 정의되지 않는다 — 0 이나 inf 로 만들지 않는다."""
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=0, li=500)])
    assert steps[0]["debt_ratio"] is None
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=-1, li=500)])
    assert steps[0]["debt_ratio"] is None


def test_debt_ratio_value():
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=200, li=500)])
    assert abs(steps[0]["debt_ratio"] - 2.5) < 1e-9


def test_interest_coverage_is_none_when_finance_costs_not_positive():
    steps = p2.step_table([_rec("2020", "2021-03-19", oi=50, fc=0)])
    assert steps[0]["interest_coverage"] is None
    steps = p2.step_table([_rec("2020", "2021-03-19", oi=50, fc=None)])
    assert steps[0]["interest_coverage"] is None


def test_interest_coverage_value_allows_negative_numerator():
    """영업손실이면 이자보상배율은 음수다 — 결측이 아니라 «나쁜 값»이다."""
    steps = p2.step_table([_rec("2020", "2021-03-19", oi=-40, fc=10)])
    assert abs(steps[0]["interest_coverage"] - (-4.0)) < 1e-9


def test_consec_op_loss_counts_only_visible_consecutive_years():
    recs = [_rec("2019", "2020-03-30", oi=-1),
            _rec("2020", "2021-03-19", oi=-1),
            _rec("2021", "2022-03-22", oi=5)]
    assert p2.consec_op_loss(recs, "2021-06-30") == 2   # 2019·2020 둘 다 적자
    assert p2.consec_op_loss(recs, "2023-01-01") == 0   # 2021 이 흑자라 끊긴다
    assert p2.consec_op_loss(recs, "2020-01-01") == 0   # 아무것도 안 보인다


def test_consec_op_loss_stops_at_a_missing_year():
    """중간 연도가 결측이면 «연속»이 끊긴다 — 없는 해를 적자로 세지 않는다."""
    recs = [_rec("2019", "2020-03-30", oi=-1),
            _rec("2021", "2022-03-22", oi=-1)]
    assert p2.consec_op_loss(recs, "2023-01-01") == 1


def test_step_table_of_empty_history_is_empty():
    assert p2.step_table([]) == []


def test_equity_impaired_is_none_when_equity_is_nan():
    """🔴 실데이터 경로는 None 이 아니라 NaN 을 준다(pd.read_sql).

    None 만 테스트하면 수정이 통과하고 실데이터에서 안 돈다 — 2026-08-08 실측.
    """
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=float('nan'))])
    assert steps[0]["equity_impaired"] is None


def test_consec_op_loss_does_not_count_nan_as_a_loss():
    """🔴 `nan >= 0` 은 False 라서 결측 연도가 「적자」로 세어진다."""
    recs = [_rec("2019", "2020-03-30", oi=-1),
            _rec("2020", "2021-03-19", oi=float('nan')),
            _rec("2021", "2022-03-22", oi=-1)]
    assert p2.consec_op_loss(recs, "2023-01-01") == 1   # 2021 만. 2020 은 결측이라 끊긴다
