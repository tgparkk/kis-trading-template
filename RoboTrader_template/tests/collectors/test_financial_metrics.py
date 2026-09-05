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


def test_total_equity_ignores_sce_reuse_of_account_id(conn):
    """🔴🔴 fix round 1 — SCE(자본변동표)는 ifrs-full_Equity 를 기초/기말 자본 줄에도 재사용한다.
    sj_div 스코프가 없으면 MAX() 가 더 큰 SCE 값을 집어 total_equity 를 오염시킨다(실측 17.1%).
    BS 값(1000)이 SCE 값(5000)보다 작아도 BS 값이 나와야 한다."""
    w.upsert_accounts(conn, [
        dict(rcept_no=ORIG["rcept_no"], fs_div="CFS", sj_div="BS",
             account_id="ifrs-full_Equity", ord=2, account_nm="자본총계",
             thstrm_amount=1000, thstrm_add_amount=None,
             frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW"),
        dict(rcept_no=ORIG["rcept_no"], fs_div="CFS", sj_div="SCE",
             account_id="ifrs-full_Equity", ord=1, account_nm="기말자본",
             thstrm_amount=5000, thstrm_add_amount=None,
             frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW"),
    ])
    with conn.cursor() as cur:
        cur.execute("SELECT total_equity FROM fn_financials_as_of(%s) WHERE stock_code='TEST02'",
                    ("2026-06-01",))
        rows = cur.fetchall()
    assert rows == [(1000,)], f"SCE 재사용 계정에 오염됨(BS 아닌 값이 나왔다): {rows}"


def test_interest_expense_prioritizes_is_cis_before_cf_proxy():
    """🔴 CF 조정항목(dart_AdjustmentsForInterestExpenses)은 IS/CIS 표준계정이 없을 때만 쓰는
    폴백이다 — 생성된 SQL 안에서 IS·CIS 뒤, 가장 마지막(최저 우선순위)에 와야 한다."""
    sql = fm._metric_sql("interest_expense")
    is_pos = sql.index("a.sj_div = 'IS'")
    cis_pos = sql.index("a.sj_div = 'CIS'")
    cf_pos = sql.index("a.sj_div = 'CF'")
    assert is_pos < cis_pos < cf_pos, f"우선순위가 IS < CIS < CF(폴백) 순서가 아니다: {sql}"
