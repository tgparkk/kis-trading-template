import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import financial_writer as w  # noqa: E402
from collectors import financial_metrics as fm  # noqa: E402

ORIG = {"rcept_no": "29999999000011", "fs_div": "CFS", "corp_code": "00000000",
        "stock_code": "TEST02", "bsns_year": "2026", "reprt_code": "11013",
        "rcept_dt": "2026-05-15", "is_amendment": False, "raw_path": None}
AMEND = dict(ORIG, rcept_no="29999999000012", rcept_dt="2026-06-30", is_amendment=True)


def _acct(rcept_no, amount):
    return [dict(rcept_no=rcept_no, fs_div="CFS", sj_div="BS",
                 account_id="ifrs-full_Assets", ord=1, account_nm="자산총계",
                 thstrm_amount=amount, thstrm_add_amount=None,
                 frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW")]


@pytest.fixture
def conn():
    with KisDbConnection.get_connection() as c:
        w.ensure_tables(c)
        fm.ensure_view(c)
        w.upsert_filing(c, ORIG);  w.upsert_accounts(c, _acct(ORIG["rcept_no"], 1000))
        w.upsert_filing(c, AMEND); w.upsert_accounts(c, _acct(AMEND["rcept_no"], 2000))
        yield c
        with c.cursor() as cur:
            cur.execute("DELETE FROM dart_financial_accounts WHERE rcept_no IN %s",
                        ((ORIG["rcept_no"], AMEND["rcept_no"]),))
            cur.execute("DELETE FROM dart_financial_filings WHERE stock_code='TEST02'")
        c.commit()


def _assets_at(conn, as_of):
    with conn.cursor() as cur:
        cur.execute("SELECT total_assets FROM fn_financials_as_of(%s) WHERE stock_code='TEST02'",
                    (as_of,))
        rows = cur.fetchall()
    return rows


def test_as_of_symmetric_before_and_after_amendment(conn):
    """🔑 대칭 단언 — 한쪽만 물으면 판별력이 0이다.
    정정 «전»에는 원본 값이, «후»에는 정정 값이 나와야 하고 «둘이 달라야» 한다."""
    before = _assets_at(conn, "2026-06-01")
    after = _assets_at(conn, "2026-07-01")
    assert before == [(1000,)], f"정정 전에 정정본이 보인다: {before}"
    assert after == [(2000,)], f"정정 후에 정정본이 안 보인다: {after}"
    assert before != after, "정정 전후가 같다 — 뷰가 as_of 를 안 쓰고 있다"


def test_no_lookahead_before_first_filing(conn):
    """🔴 최초 접수일 이전에는 «아무것도» 보이면 안 된다."""
    assert _assets_at(conn, "2026-05-14") == []
