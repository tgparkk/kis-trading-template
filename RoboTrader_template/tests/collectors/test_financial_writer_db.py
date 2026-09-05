import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import financial_writer as w  # noqa: E402

ORIG = {"rcept_no": "29999999000001", "fs_div": "CFS", "corp_code": "00000000",
        "stock_code": "TEST01", "bsns_year": "2026", "reprt_code": "11013",
        "rcept_dt": "2026-05-15", "is_amendment": False, "raw_path": None}
AMEND = dict(ORIG, rcept_no="29999999000002", rcept_dt="2026-06-30", is_amendment=True)


@pytest.fixture
def conn():
    with KisDbConnection.get_connection() as c:
        w.ensure_tables(c)
        yield c
        with c.cursor() as cur:
            cur.execute("DELETE FROM dart_financial_accounts WHERE rcept_no IN %s",
                        ((ORIG["rcept_no"], AMEND["rcept_no"]),))
            cur.execute("DELETE FROM dart_financial_filings WHERE stock_code='TEST01'")
        c.commit()


def test_amendment_does_not_overwrite_original(conn):
    """🔴 지금 죽은 테이블이 실패하는 바로 그 지점.
    같은 (stock, year, reprt) 인데 rcept_no 가 다르면 «두 행 다» 남아야 한다."""
    w.upsert_filing(conn, ORIG)
    w.upsert_accounts(conn, [dict(rcept_no=ORIG["rcept_no"], fs_div="CFS", sj_div="BS",
                                  account_id="ifrs-full_Assets", ord=1, account_nm="자산총계",
                                  thstrm_amount=1000, thstrm_add_amount=None,
                                  frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW")])
    w.upsert_filing(conn, AMEND)
    w.upsert_accounts(conn, [dict(rcept_no=AMEND["rcept_no"], fs_div="CFS", sj_div="BS",
                                  account_id="ifrs-full_Assets", ord=1, account_nm="자산총계",
                                  thstrm_amount=2000, thstrm_add_amount=None,
                                  frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW")])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dart_financial_filings "
                    "WHERE stock_code='TEST01' AND bsns_year='2026' AND reprt_code='11013'")
        assert cur.fetchone()[0] == 2, "정정공시가 원본을 덮어썼다"
        cur.execute("SELECT thstrm_amount FROM dart_financial_accounts "
                    "WHERE rcept_no IN %s ORDER BY rcept_no",
                    ((ORIG["rcept_no"], AMEND["rcept_no"]),))
        assert [r[0] for r in cur.fetchall()] == [1000, 2000]
