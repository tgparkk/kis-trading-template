import pytest
from collectors import financial_writer as w

RESP = {
    "status": "000", "message": "정상",
    "list": [
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Assets",
         "account_nm": "자산총계", "thstrm_amount": "1,000", "frmtrm_amount": "900",
         "bfefrmtrm_amount": "800", "ord": "1", "currency": "KRW"},
        # 같은 account_id 가 두 번 — ord 만 다르다. 표준계정코드 미사용분 16.3% 에서 실제로 난다.
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Assets",
         "account_nm": "자산총계(주석)", "thstrm_amount": "1,001", "frmtrm_amount": "901",
         "bfefrmtrm_amount": "801", "ord": "2", "currency": "KRW"},
    ],
}


def test_ord_keeps_duplicate_account_ids():
    """같은 account_id 2건이 «둘 다» 살아남아야 한다. ord 가 키에 없으면 1건이 조용히 사라진다."""
    filing, accounts = w.rows_from_dart_response(RESP, "005930", "CFS")
    assert len(accounts) == 2
    assert {a["ord"] for a in accounts} == {1, 2}
    assert {a["thstrm_amount"] for a in accounts} == {1000, 1001}


def test_filing_carries_rcept_no_and_reprt_code():
    """지금 죽은 테이블에 없던 두 컬럼이 반드시 채워져야 한다."""
    filing, _ = w.rows_from_dart_response(RESP, "005930", "CFS")
    assert filing["rcept_no"] == "20260515000001"
    assert filing["reprt_code"] == "11013"
    assert filing["fs_div"] == "CFS"
    assert filing["stock_code"] == "005930"


def test_parse_amount_failure_is_none_not_zero():
    """🔴 파싱 실패를 0 으로 뭉개면 «부채 0원인 우량기업»이 된다."""
    assert w.parse_amount("1,234") == 1234
    assert w.parse_amount("-5,000") == -5000
    assert w.parse_amount("-") is None
    assert w.parse_amount("") is None
    assert w.parse_amount(None) is None
    assert w.parse_amount("N/A") is None


def test_quarterly_cumulative_amount_is_captured():
    """🔴 분기 IS 는 thstrm_amount(당분기)와 thstrm_add_amount(누계)가 다르다.
    누계를 안 받으면 분기 매출액을 만들 수 없다."""
    resp = {"status": "000", "list": [
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "IS", "account_id": "ifrs-full_Revenue",
         "account_nm": "매출액", "thstrm_amount": "300", "thstrm_add_amount": "300",
         "ord": "1", "currency": "KRW"}]}
    _, accounts = w.rows_from_dart_response(resp, "005930", "CFS")
    assert accounts[0]["thstrm_amount"] == 300
    assert accounts[0]["thstrm_add_amount"] == 300


def test_upsert_accounts_rolls_back_on_cursor_error():
    """cursor.execute가 실패하면 conn.rollback()이 호출되어야 한다."""
    class FakeCursor:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, *args, **kwargs):
            raise RuntimeError("execute failed")

    class FakeConn:
        def __init__(self):
            self.rolled_back = False
            self.committed = False
        def cursor(self):
            return FakeCursor()
        def rollback(self):
            self.rolled_back = True
        def commit(self):
            self.committed = True

    fake_conn = FakeConn()
    rows = [{"rcept_no": "29999999000001", "fs_div": "CFS", "sj_div": "BS",
             "account_id": "ifrs-full_Assets", "ord": 1, "account_nm": "자산총계",
             "thstrm_amount": 1000, "thstrm_add_amount": None,
             "frmtrm_amount": None, "bfefrmtrm_amount": None, "currency": "KRW"}]

    with pytest.raises(RuntimeError, match="execute failed"):
        w.upsert_accounts(fake_conn, rows)

    assert fake_conn.rolled_back, "rollback() should have been called"
    assert not fake_conn.committed, "commit() should not have been called"
