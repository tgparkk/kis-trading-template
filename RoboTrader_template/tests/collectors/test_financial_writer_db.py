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
    같은 (stock, year, reprt) 인데 rcept_no 가 다르면 «두 행 다» 남아야 한다.

    2026-09-06: upsert_accounts 가 account_detail 을 무조건 INSERT 하므로, 이 테스트도
    (SCE 전용 테스트와 같은 이유로) 라이브 테이블이 재생성되기 전에는 UndefinedColumn 으로
    깨진다 — 같은 스킵 가드를 붙인다(컨트롤러 재생성 전까지는 통과할 수 없음)."""
    if not _account_detail_column_exists(conn):
        pytest.skip("live table not yet recreated with account_detail — controller step")
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
    # 실제 운영에서 쓰는 날짜(예: 08-17 반기 창 첫날)와 겹치면 진짜 reconcile 이력과
    # 충돌할 수 있다 — 합성 과거 날짜로 격리한다(Task 6 review 지적).
    trade_date = "1999-01-04"
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


def _account_detail_column_exists(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='dart_financial_accounts' AND column_name='account_detail'")
        return cur.fetchone()[0] > 0


def test_sce_rows_all_persist_and_upsert_is_idempotent(conn):
    """🔴 Task 8 Step 2 원본↔DB 대조 실패의 재현/회귀 방지 — SCE 4행(3 SCE + 1 BS,
    account_id/ord 공유·account_detail 만 다름)이 UPSERT 후 «전부» 남아야 하고
    (실측: PK 에 account_detail 없으면 SCE 그룹이 1행으로 접혔었다), 같은 행을
    다시 넣어도 개수가 그대로여야(멱등) 한다.

    NOTE: 라이브 테이블이 account_detail 컬럼을 아직 갖지 않으면(컨트롤러가 테이블을
    재생성하기 전) 이 테스트는 skip 한다 — 여기서 테이블을 ALTER/DROP 하지 않는다.
    """
    if not _account_detail_column_exists(conn):
        pytest.skip("live table not yet recreated with account_detail — controller step")

    rcept_no = "29999999000003"
    w.upsert_filing(conn, dict(ORIG, rcept_no=rcept_no, stock_code="TEST02"))
    rows = [
        dict(rcept_no=rcept_no, fs_div="CFS", sj_div="SCE", account_id="ifrs-full_Equity",
             ord=1, account_detail="자본금", account_nm="자본변동", thstrm_amount=100,
             thstrm_add_amount=None, frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW"),
        dict(rcept_no=rcept_no, fs_div="CFS", sj_div="SCE", account_id="ifrs-full_Equity",
             ord=1, account_detail="이익잉여금", account_nm="자본변동", thstrm_amount=200,
             thstrm_add_amount=None, frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW"),
        dict(rcept_no=rcept_no, fs_div="CFS", sj_div="SCE", account_id="ifrs-full_Equity",
             ord=1, account_detail="기타포괄손익누계액", account_nm="자본변동", thstrm_amount=300,
             thstrm_add_amount=None, frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW"),
        dict(rcept_no=rcept_no, fs_div="CFS", sj_div="BS", account_id="ifrs-full_Assets",
             ord=1, account_nm="자산총계", thstrm_amount=1000,
             thstrm_add_amount=None, frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW"),
    ]
    try:
        w.upsert_accounts(conn, [dict(r) for r in rows])
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM dart_financial_accounts "
                        "WHERE rcept_no=%s AND fs_div='CFS'", (rcept_no,))
            assert cur.fetchone()[0] == 4, "SCE 자본 항목 열별 행이 UPSERT 로 접혔다"

        # 같은 행을 다시 upsert — 멱등이어야 한다(개수 불변).
        w.upsert_accounts(conn, [dict(r) for r in rows])
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM dart_financial_accounts "
                        "WHERE rcept_no=%s AND fs_div='CFS'", (rcept_no,))
            assert cur.fetchone()[0] == 4, "재실행이 멱등하지 않다"
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dart_financial_accounts WHERE rcept_no=%s", (rcept_no,))
            cur.execute("DELETE FROM dart_financial_filings WHERE rcept_no=%s", (rcept_no,))
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


# 🔴 Task 6 review (fix round 1, 2026-09-06): `test_quota_abort_leaves_existing_rows_intact`
# 이 자리에 있었지만 실제로는 collector 코드를 전혀 태우지 않는 vacuous 테스트였다
# (raise/except 만 흉내). collect_financials 를 fake fetcher 로 실제로 굴리는 버전으로
# 재작성해 tests/collectors/test_financial_collector.py 로 옮겼다.
