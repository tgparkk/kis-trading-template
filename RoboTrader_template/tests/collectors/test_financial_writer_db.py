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


def test_upsert_nodata_is_idempotent(conn):
    """R1: 새 writer 함수 `upsert_nodata` 의 DB 테스트 — ON CONFLICT DO NOTHING 이라
    같은 키를 두 번 넣어도 1행이어야 한다."""
    w.upsert_nodata(conn, "TEST05", "2026", "11013")
    w.upsert_nodata(conn, "TEST05", "2026", "11013")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dart_financial_nodata WHERE stock_code='TEST05'")
        assert cur.fetchone()[0] == 1, "013 확정 기록이 중복 삽입됐다"
    with conn.cursor() as cur:
        cur.execute("DELETE FROM dart_financial_nodata WHERE stock_code='TEST05'")
    conn.commit()


def test_upsert_reconciliation_upserts_financials_dataset(conn):
    """R1: 새 writer 함수 `upsert_reconciliation` 의 DB 테스트 —
    같은 (trade_date, dataset) 에 두 번째 호출이 UPDATE 로 덮어써야 한다."""
    trade_date = "2026-08-17"
    try:
        w.upsert_reconciliation(conn, trade_date, "financials", 5, 0.0, 0.0, "FAIL")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT new_rows, value_match_rate, coverage, verdict "
                "FROM collection_reconciliation WHERE trade_date=%s AND dataset='financials'",
                (trade_date,))
            assert cur.fetchone() == (5, 0.0, 0.0, "FAIL")

        w.upsert_reconciliation(conn, trade_date, "financials", 0, 1.0, 1.0, "PASS")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM collection_reconciliation "
                "WHERE trade_date=%s AND dataset='financials'", (trade_date,))
            assert cur.fetchone()[0] == 1, "ON CONFLICT UPDATE 가 아니라 중복 행이 생겼다"
            cur.execute(
                "SELECT new_rows, value_match_rate, coverage, verdict "
                "FROM collection_reconciliation WHERE trade_date=%s AND dataset='financials'",
                (trade_date,))
            assert cur.fetchone() == (0, 1.0, 1.0, "PASS")
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM collection_reconciliation WHERE trade_date=%s AND dataset='financials'",
                (trade_date,))
        conn.commit()


def test_nodata_is_excluded_from_next_run(conn):
    """🔴 스펙 테스트 #5 — 013(무자료) 확정분을 다음 실행에서 다시 두드리면 안 된다."""
    from collectors import financial_collector as fc
    with conn.cursor() as cur:
        cur.execute("INSERT INTO dart_financial_nodata "
                    "(stock_code, bsns_year, reprt_code) VALUES ('TEST03','2026','11013') "
                    "ON CONFLICT DO NOTHING")
    conn.commit()
    codes = [("TEST03", "00000001"), ("TEST04", "00000002")]
    pending = fc._pending_targets(conn, codes, "2026", "11013")
    assert [p[0] for p in pending] == ["TEST04"], "013 확정분이 다시 대상에 들어왔다"
    with conn.cursor() as cur:
        cur.execute("DELETE FROM dart_financial_nodata WHERE stock_code='TEST03'")
    conn.commit()


def test_quota_abort_leaves_existing_rows_intact(conn):
    """🔴 스펙 테스트 #6 — 한도 초과로 중단돼도 이미 적재된 행은 무손상이어야 한다."""
    from collectors.dart_financial_fetcher import DartQuotaExceeded
    w.upsert_filing(conn, ORIG)
    w.upsert_accounts(conn, [dict(rcept_no=ORIG["rcept_no"], fs_div="CFS", sj_div="BS",
                                  account_id="ifrs-full_Assets", ord=1, account_nm="자산총계",
                                  thstrm_amount=1000, thstrm_add_amount=None,
                                  frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW")])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dart_financial_accounts WHERE rcept_no=%s",
                    (ORIG["rcept_no"],))
        before = cur.fetchone()[0]
    try:
        raise DartQuotaExceeded("simulated")
    except DartQuotaExceeded:
        pass
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dart_financial_accounts WHERE rcept_no=%s",
                    (ORIG["rcept_no"],))
        assert cur.fetchone()[0] == before, "중단이 기적재분을 훼손했다"
