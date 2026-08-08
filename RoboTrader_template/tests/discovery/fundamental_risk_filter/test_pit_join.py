import os
import sys

import pytest

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


def test_boundary_same_day_is_visible_only_with_flag():
    """🔴 접수일 «당일»은 `same_day_visible=True` 일 때만 공개된 것으로 본다.

    사업보고서는 18시까지 접수될 수 있는데 시장은 15:30에 닫힌다 — 기본(False)은
    엄격하게 «전날까지»만 보이게 해 당일 look-ahead를 막는다.
    """
    got = pj.asof_financials(RECS, "2021-03-19", same_day_visible=True)
    assert got["bsns_year"] == "2020"

    got_strict = pj.asof_financials(RECS, "2021-03-19")  # 기본값 False
    assert got_strict["bsns_year"] == "2019"  # 당일은 아직 안 보인다 → 전년도로 폴백


def test_one_day_before_filing_is_not_visible_in_both_modes():
    """🔴 look-ahead 방지의 핵심. 하루 전에는 안 보여야 한다 — 두 모드 모두 동일."""
    assert pj.asof_financials(RECS, "2021-03-18")["bsns_year"] == "2019"
    assert pj.asof_financials(RECS, "2021-03-18", same_day_visible=True)["bsns_year"] == "2019"


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


def test_identical_key_first_record_wins():
    """🔴 리뷰가 찾은 「살아남는 변이」를 막는다.

    `key > best_key` 를 `>=` 로 바꾸면 «같은 (bsns_year, rcept_dt)» 를 가진
    레코드들 중 마지막 것이 이긴다 = 입력 순서 의존. 다른 어떤 테스트도
    이걸 못 잡았다 — 기존 동률 테스트는 `bsns_year` 가 «달라서» 키가 같지 않다.
    반환 객체가 입력 순서에 따라 달라지므로(=먼저 온 것이 이긴다) 이름이
    "순서 무관"이면 오해를 부른다 — 실제로 검사하는 것은 "먼저 온 것이 이긴다"다.
    """
    a = {"bsns_year": "2021", "rcept_dt": "2022-03-22", "tag": "a"}
    b = {"bsns_year": "2021", "rcept_dt": "2022-03-22", "tag": "b"}
    assert pj.asof_financials([a, b], "2023-01-01")["tag"] == "a"
    assert pj.asof_financials([b, a], "2023-01-01")["tag"] == "b"
    # 🔑 「먼저 온 것이 이긴다」가 규약이다. `>=` 로 바꾸면 둘 다 뒤엣것이 나와 실패한다.


def test_amended_old_fiscal_year_does_not_beat_newer_fiscal_year():
    """🔴 FIX2 — 선택 키는 (bsns_year, rcept_dt) 다. (rcept_dt, bsns_year) 였다면

    2021년 정정공시(2024-05-10 접수)가 2023년 원본(2024-03-20 접수)보다
    «더 늦게 접수됐다»는 이유로 이겨서, 3년 묵은 수치를 「최신」으로 잘못
    내놓았을 것이다. 사업연도를 먼저 최대화해야 이 함정을 피한다.
    """
    recs = [
        {"bsns_year": "2021", "rcept_dt": "2024-05-10", "total_equity": 111},  # 정정공시(오래된 연도)
        {"bsns_year": "2023", "rcept_dt": "2024-03-20", "total_equity": 333},  # 원본(더 최근 연도)
    ]
    got = pj.asof_financials(recs, "2024-06-01")
    assert got["bsns_year"] == "2023"


def test_malformed_date_raises_instead_of_comparing_wrong():
    """🔴 '2023-3-5' 는 사전순 비교에서 «조용히 틀린 답»을 낸다.

    '2023-3-5' > '2023-12-01' 이 참이 된다 — 3월이 12월보다 나중이 되는 것이다.
    이 모듈이 막으려는 실패 유형이 정확히 그것이므로 시끄럽게 실패해야 한다.
    """
    with pytest.raises(ValueError):
        pj._daystr("2023-3-5")
    with pytest.raises(ValueError):
        pj.asof_financials([{"bsns_year": "2022", "rcept_dt": "2023-3-5"}],
                           "2023-12-31")


def test_empty_and_missing_rcept_dt_are_skipped_not_errors():
    """빈 값·키 없음은 「모른다」라 건너뛸 대상이지 오류가 아니다."""
    recs = [
        {"bsns_year": "2020", "rcept_dt": ""},
        {"bsns_year": "2021"},                       # 키 자체가 없음
        {"bsns_year": "2019", "rcept_dt": "2020-03-30", "tag": "ok"},
    ]
    assert pj.asof_financials(recs, "2023-01-01")["tag"] == "ok"


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


def test_empty_as_of_raises_valueerror_naming_the_parameter():
    """🔴 FIX9 — `_daystr("")` 는 None 을 돌려주고, 그러면 `str > None` 비교가

    opaque `TypeError` 로 죽는다. Phase 2 가 날짜 루프에서 `as_of` 를 실수로
    빈 문자열로 넘길 수 있으므로, 시끄럽게 `ValueError` 로 실패하고 이름을
    지목해야 한다.
    """
    with pytest.raises(ValueError, match="as_of"):
        pj.asof_financials(RECS, "")
    with pytest.raises(ValueError, match="as_of"):
        pj.asof_financials(RECS, None)
