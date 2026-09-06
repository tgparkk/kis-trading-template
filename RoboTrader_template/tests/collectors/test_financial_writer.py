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


def test_malformed_ord_skipped(monkeypatch):
    """🔴 malformed ord 는 PK 충돌로 침묵 덮어쓴다 — 스킵 + 경고 필수.
    ord 가 정수 아니면 계정을 드롭하고 WARNING 을 남긴다."""
    resp = {"status": "000", "list": [
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Assets",
         "account_nm": "자산총계", "thstrm_amount": "1000", "ord": "1", "currency": "KRW"},
        # malformed ord
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Liabilities",
         "account_nm": "부채총계", "thstrm_amount": "2000", "ord": "x", "currency": "KRW"},
    ]}

    # Verify logger.warning is called with the right parameters
    logger_warnings = []
    def capture_warning(msg, *args, **kwargs):
        logger_warnings.append((msg, args))

    monkeypatch.setattr(w.logger, "warning", capture_warning)
    filing, accounts = w.rows_from_dart_response(resp, "005930", "CFS")

    # 오직 good item 만 살아남음
    assert len(accounts) == 1
    assert accounts[0]["account_id"] == "ifrs-full_Assets"
    assert accounts[0]["ord"] == 1

    # WARNING 로그 호출 확인: rcept_no, account_id, 그리고 원본 ord 값 포함
    assert len(logger_warnings) == 1
    msg_template, args = logger_warnings[0]
    # msg_template = "[financial_writer] ord 무효 계정 스킵: rcept_no=%s account_id=%s ord=%r"
    # args = ("20260515000001", "ifrs-full_Liabilities", "x")
    assert args[0] == "20260515000001"  # rcept_no
    assert args[1] == "ifrs-full_Liabilities"  # account_id
    assert args[2] == "x"  # raw ord


def test_empty_and_missing_ord_skipped(monkeypatch):
    """🔴 ord 가 빈값이나 누락되어도 ord=0 폴백 금지 — 스킵 + 경고.
    missing ord, empty ord, whitespace ord 모두 같은 처리."""
    resp = {"status": "000", "list": [
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Assets",
         "account_nm": "자산총계", "thstrm_amount": "1000", "ord": "1", "currency": "KRW"},
        # missing ord (key not present)
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Liabilities",
         "account_nm": "부채총계", "thstrm_amount": "2000", "currency": "KRW"},
        # empty ord
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Equity",
         "account_nm": "자본총계", "thstrm_amount": "3000", "ord": "", "currency": "KRW"},
    ]}

    # Verify logger.warning is called
    logger_warnings = []
    def capture_warning(msg, *args, **kwargs):
        logger_warnings.append((msg, args))

    monkeypatch.setattr(w.logger, "warning", capture_warning)
    filing, accounts = w.rows_from_dart_response(resp, "005930", "CFS")

    # 오직 good item 만 살아남음
    assert len(accounts) == 1
    assert accounts[0]["account_id"] == "ifrs-full_Assets"
    assert accounts[0]["ord"] == 1

    # 두 개의 경고 로그: missing + empty
    assert len(logger_warnings) == 2

    # First warning (missing ord): args = ("20260515000001", "ifrs-full_Liabilities", "")
    msg1, args1 = logger_warnings[0]
    assert args1[0] == "20260515000001"  # rcept_no
    assert args1[1] == "ifrs-full_Liabilities"  # account_id
    assert args1[2] == ""  # raw ord (empty)

    # Second warning (empty ord): args = ("20260515000001", "ifrs-full_Equity", "")
    msg2, args2 = logger_warnings[1]
    assert args2[0] == "20260515000001"  # rcept_no
    assert args2[1] == "ifrs-full_Equity"  # account_id
    assert args2[2] == ""  # raw ord (empty)


def test_sce_rows_keep_account_detail_others_default_dash():
    """🔴 SCE(자본변동표)는 같은 (sj_div, account_id, ord) 를 자본 항목 열마다 공유하고
    account_detail 만 다르다 — account_detail 이 없으면 ON CONFLICT 가 그룹을 한 행으로
    접는다(실측 SCE 64/160/162 → db 8/20/18). 파서는 4행 모두 살려야 하고, SCE 는
    자기 detail 문자열을, BS 는 '-' 를 가져야 한다."""
    resp = {"status": "000", "list": [
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "SCE", "account_id": "ifrs-full_Equity",
         "account_nm": "자본변동", "account_detail": "자본금",
         "thstrm_amount": "100", "ord": "1", "currency": "KRW"},
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "SCE", "account_id": "ifrs-full_Equity",
         "account_nm": "자본변동", "account_detail": "이익잉여금",
         "thstrm_amount": "200", "ord": "1", "currency": "KRW"},
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "SCE", "account_id": "ifrs-full_Equity",
         "account_nm": "자본변동", "account_detail": "기타포괄손익누계액",
         "thstrm_amount": "300", "ord": "1", "currency": "KRW"},
        # BS 행은 account_detail 자체가 없다 — 기본값 '-' 여야 한다.
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Assets",
         "account_nm": "자산총계", "thstrm_amount": "1000", "ord": "1", "currency": "KRW"},
    ]}
    _, accounts = w.rows_from_dart_response(resp, "005930", "CFS")
    assert len(accounts) == 4
    sce_rows = [a for a in accounts if a["sj_div"] == "SCE"]
    bs_rows = [a for a in accounts if a["sj_div"] == "BS"]
    assert len(sce_rows) == 3
    assert {a["account_detail"] for a in sce_rows} == {"자본금", "이익잉여금", "기타포괄손익누계액"}
    assert len(bs_rows) == 1
    assert bs_rows[0]["account_detail"] == "-"


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


class _FailingCursor:
    """execute() 가 항상 실패하는 커서 — R1: 새 writer 함수 3개의 rollback 경로 테스트용."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def execute(self, *args, **kwargs):
        raise RuntimeError("execute failed")


class _FailingConn:
    def __init__(self):
        self.rolled_back = False
        self.committed = False
    def cursor(self):
        return _FailingCursor()
    def rollback(self):
        self.rolled_back = True
    def commit(self):
        self.committed = True


def test_upsert_nodata_rolls_back_on_cursor_error():
    """Task 6/R1: dart_financial_nodata INSERT 가 writer 로 옮겨졌다 — rollback 경로 확인."""
    fake_conn = _FailingConn()
    with pytest.raises(RuntimeError, match="execute failed"):
        w.upsert_nodata(fake_conn, "TEST05", "2026", "11013")
    assert fake_conn.rolled_back, "rollback() should have been called"
    assert not fake_conn.committed, "commit() should not have been called"


def test_recompute_amendment_flags_rolls_back_on_cursor_error():
    """Task 6/R1: is_amendment 재계산 UPDATE 가 writer 로 옮겨졌다 — rollback 경로 확인."""
    fake_conn = _FailingConn()
    with pytest.raises(RuntimeError, match="execute failed"):
        w.recompute_amendment_flags(fake_conn)
    assert fake_conn.rolled_back, "rollback() should have been called"
    assert not fake_conn.committed, "commit() should not have been called"


def test_upsert_reconciliation_rolls_back_on_cursor_error():
    """Task 6/R1: collection_reconciliation UPSERT 가 writer 로 옮겨졌다 — rollback 경로 확인."""
    fake_conn = _FailingConn()
    with pytest.raises(RuntimeError, match="execute failed"):
        w.upsert_reconciliation(fake_conn, "2026-08-17", "financials", 5, 1.0, 1.0, "PASS")
    assert fake_conn.rolled_back, "rollback() should have been called"
    assert not fake_conn.committed, "commit() should not have been called"
