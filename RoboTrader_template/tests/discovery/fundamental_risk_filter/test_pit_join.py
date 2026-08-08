import os
import sys

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import pit_join as pj  # noqa: E402

RECS = [
    {"bsns_year": "2019", "rcept_dt": "2020-03-30", "total_equity": 100},
    {"bsns_year": "2020", "rcept_dt": "2021-03-19", "total_equity": 200},
    {"bsns_year": "2021", "rcept_dt": "2022-03-22", "total_equity": 300},
]


def test_picks_latest_filing_on_or_before_as_of():
    got = pj.asof_financials(RECS, "2021-06-30")
    assert got["bsns_year"] == "2020"


def test_boundary_same_day_is_visible():
    """접수일 «당일»은 공개된 것으로 본다."""
    got = pj.asof_financials(RECS, "2021-03-19")
    assert got["bsns_year"] == "2020"


def test_one_day_before_filing_is_not_visible():
    """🔴 look-ahead 방지의 핵심. 하루 전에는 안 보여야 한다."""
    got = pj.asof_financials(RECS, "2021-03-18")
    assert got["bsns_year"] == "2019"


def test_before_any_filing_returns_none():
    assert pj.asof_financials(RECS, "2019-12-31") is None


def test_records_with_null_rcept_dt_are_ignored():
    """접수일을 모르는 행은 «언제 알 수 있었는지» 를 모르므로 못 쓴다."""
    recs = RECS + [{"bsns_year": "2022", "rcept_dt": None, "total_equity": 999}]
    got = pj.asof_financials(recs, "2026-01-01")
    assert got["bsns_year"] == "2021"


def test_unsorted_input_gives_same_answer():
    got = pj.asof_financials(list(reversed(RECS)), "2021-06-30")
    assert got["bsns_year"] == "2020"


def test_later_fiscal_year_filed_earlier_does_not_win_by_year():
    """정렬 키는 «사업연도» 가 아니라 «접수일» 이다."""
    recs = [
        {"bsns_year": "2021", "rcept_dt": "2022-03-22", "total_equity": 300},
        {"bsns_year": "2022", "rcept_dt": "2023-03-20", "total_equity": 400},
    ]
    got = pj.asof_financials(recs, "2022-06-01")
    assert got["bsns_year"] == "2021"


def test_empty_records_returns_none():
    assert pj.asof_financials([], "2023-01-01") is None


def test_same_rcept_dt_breaks_tie_by_fiscal_year_deterministically():
    """🔴 정정공시·재제출이 같은 날 들어올 수 있다. 입력 순서로 답이 바뀌면 안 된다."""
    a = {"bsns_year": "2021", "rcept_dt": "2022-03-22", "total_equity": 1}
    b = {"bsns_year": "2022", "rcept_dt": "2022-03-22", "total_equity": 2}
    assert pj.asof_financials([a, b], "2023-01-01")["bsns_year"] == "2022"
    assert pj.asof_financials([b, a], "2023-01-01")["bsns_year"] == "2022"


def test_accepts_date_objects_not_just_strings():
    """🔴 적재 테이블의 rcept_dt 는 DATE 컬럼이라 psycopg2 가 date 를 돌려준다.

    문자열만 받으면 「JSONL 로 읽으면 되고 DB 로 읽으면 TypeError」가 된다.
    """
    from datetime import date
    recs = [{"bsns_year": "2020", "rcept_dt": date(2021, 3, 19), "total_equity": 200}]
    got = pj.asof_financials(recs, date(2021, 6, 30))
    assert got["bsns_year"] == "2020"
    # 경계도 date 로 확인 — 하루 전에는 안 보여야 한다
    assert pj.asof_financials(recs, date(2021, 3, 18)) is None
