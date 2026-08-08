import os
import sys

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import f3_normalize as f3  # noqa: E402


def _row(sj_div, account_id, account_nm, amount, rcept_no="20230315000123"):
    return {
        "rcept_no": rcept_no,
        "sj_div": sj_div,
        "account_id": account_id,
        "account_nm": account_nm,
        "thstrm_amount": amount,
    }


def test_parse_amount_handles_commas_and_negatives():
    assert f3.parse_amount("5,969,782,550") == 5969782550
    assert f3.parse_amount("-1,234") == -1234


def test_parse_amount_returns_none_not_zero_on_failure():
    """🔴 결측을 0 으로 뭉개면 안 된다 — market_cap 결손 오판의 재발이다."""
    assert f3.parse_amount("") is None
    assert f3.parse_amount("-") is None
    assert f3.parse_amount(None) is None
    assert f3.parse_amount("해당사항없음") is None


def test_rcept_dt_is_extracted_from_rcept_no():
    rows = [_row("BS", "ifrs-full_Equity", "자본총계", "100", "20230315000123")]
    assert f3.rcept_dt_from(rows) == "2023-03-15"


def test_rcept_dt_is_none_when_absent():
    assert f3.rcept_dt_from([]) is None
    assert f3.rcept_dt_from([{"sj_div": "BS"}]) is None


def test_pick_account_prefers_account_id_over_name():
    """account_id 가 있으면 그것을 쓴다 — 이름은 회사마다 다르다."""
    rows = [
        _row("BS", "ifrs-full_Equity", "자본총계합계", "500"),
        _row("BS", "", "자본총계", "999"),
    ]
    got = f3.pick_account(rows, ("BS",), ("ifrs-full_Equity",), ("자본총계",))
    assert got == 500


def test_pick_account_falls_back_to_name_hint():
    rows = [_row("BS", "", "자본총계", "777")]
    got = f3.pick_account(rows, ("BS",), ("ifrs-full_Equity",), ("자본총계",))
    assert got == 777


def test_pick_account_respects_sj_div():
    """같은 이름이 재무상태표와 손익계산서에 다 있을 수 있다."""
    rows = [_row("IS", "", "자본총계", "111")]
    assert f3.pick_account(rows, ("BS",), (), ("자본총계",)) is None


def test_operating_income_found_in_cis_only():
    """🔴 단일 포괄손익계산서만 낸 회사는 영업이익이 CIS 에만 있다.

    「IS」로만 찾으면 그 회사들이 조용히 결측이 되고, 커버리지 표에서
    「계정이 원래 없다」로 오독된다 — 실제로는 우리가 안 본 것이다.
    """
    rec = {
        "stock_code": "005930", "bsns_year": "2022", "fs_div": "CFS",
        "status": "000",
        "rows": [_row("CIS", "dart_OperatingIncomeLoss", "영업이익", "1234")],
    }
    out = f3.normalize(rec)
    assert out["operating_income"] == 1234


def test_finance_costs_and_interest_paid_are_captured():
    """🔑 `ifrs-full_InterestExpense` 는 국내 46건 실측 **0.0%** 였다.

    한국 상장사가 실제로 쓰는 것은 금융원가(CIS)와 이자지급(CF)이다.
    이 테스트가 없으면 「계정이 없다」는 잘못된 결론으로 축 하나를 통째로 버린다.
    """
    rec = {
        "stock_code": "005930", "bsns_year": "2022", "fs_div": "CFS",
        "status": "000",
        "rows": [
            _row("CIS", "ifrs-full_FinanceCosts", "금융원가", "500"),
            _row("CF", "ifrs-full_InterestPaidClassifiedAsOperatingActivities",
                 "이자지급", "300"),
        ],
    }
    out = f3.normalize(rec)
    assert out["finance_costs"] == 500
    assert out["interest_paid_cf"] == 300
    assert out["interest_expense"] is None   # 국내 태그가 아니다 — None 이 정상


def test_cf_only_account_is_not_found_in_income_statements():
    """CF 전용 항목을 IS/CIS 에서 찾으면 안 된다 — 표 구분이 살아 있어야 한다."""
    rows = [_row("CF", "ifrs-full_InterestPaidClassifiedAsOperatingActivities",
                 "이자지급", "300")]
    assert f3.pick_account(rows, ("IS", "CIS"),
                           ("ifrs-full_InterestPaidClassifiedAsOperatingActivities",),
                           ("이자지급",)) is None


def test_normalize_missing_account_is_none():
    rec = {
        "stock_code": "005930", "bsns_year": "2022", "fs_div": "CFS",
        "status": "000",
        "rows": [_row("BS", "ifrs-full_Equity", "자본총계", "1000")],
    }
    out = f3.normalize(rec)
    assert out["total_equity"] == 1000
    assert out["interest_expense"] is None      # 없으면 None
    assert out["rcept_dt"] == "2023-03-15"


def test_normalize_of_empty_record_keeps_the_row():
    """013(무자료)도 행을 남긴다 — 어느 종목·연도가 왜 비었는지가 기록이어야 한다."""
    rec = {"stock_code": "900300", "bsns_year": "2022", "fs_div": None,
           "status": "013", "rows": []}
    out = f3.normalize(rec)
    assert out["stock_code"] == "900300"
    assert out["total_equity"] is None
    assert out["rcept_dt"] is None
