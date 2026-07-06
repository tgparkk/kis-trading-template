"""Item 2/4: corp_events 증분 수집 + 헬스 reconcile 테스트 (mock DART + mock DB)."""
import collectors.corp_events_collector as cec


# ── mock DB ───────────────────────────────────────────────────────────────────

class _MockCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0

    def execute(self, sql, params=None):
        s = " ".join(sql.upper().split())
        if s.startswith("INSERT INTO CORP_EVENTS"):
            self.conn.inserts.append(params)
            self.rowcount = 1  # 신규 1건 가정
        elif s.startswith("INSERT INTO COLLECTION_RECONCILIATION"):
            self.conn.recon.append(params)
            self.rowcount = 1
        else:
            self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _MockConn:
    def __init__(self):
        self.inserts = []
        self.recon = []
        self.committed = 0

    def cursor(self):
        return _MockCursor(self)

    def commit(self):
        self.committed += 1


class _CM:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *a):
        pass


def _patch_db(monkeypatch, conn):
    monkeypatch.setattr(cec.KisDbConnection, "get_connection", lambda: _CM(conn))


# ── collect_corp_events ──────────────────────────────────────────────────────

# ── R6: .env 파싱 정확 매칭 (변형 키 오인 방지) ──────────────────────────────

def test_parse_dart_key_exact_match_not_prefix():
    """OPENDART_API_KEY_BACKUP= 같은 변형 키를 잘못 집어오지 않아야 한다."""
    lines = ["OPENDART_API_KEY_BACKUP=WRONGKEY", "OPENDART_API_KEY=REALKEY"]
    assert cec._parse_dart_key_from_lines(lines) == "REALKEY"


def test_parse_dart_key_prefers_exact_even_when_backup_appears_after():
    lines = ["OPENDART_API_KEY=REALKEY", "OPENDART_API_KEY_BACKUP=WRONGKEY"]
    assert cec._parse_dart_key_from_lines(lines) == "REALKEY"


def test_parse_dart_key_handles_export_prefix():
    lines = ["export OPENDART_API_KEY=REALKEY2"]
    assert cec._parse_dart_key_from_lines(lines) == "REALKEY2"


def test_parse_dart_key_returns_empty_when_absent():
    assert cec._parse_dart_key_from_lines(["FOO=bar", "OPENDART_API_KEY_BACKUP=X"]) == ""


def test_parse_dart_key_strips_quotes():
    assert cec._parse_dart_key_from_lines(['OPENDART_API_KEY="QUOTED"']) == "QUOTED"


def test_load_dart_key_prefers_env_var(monkeypatch):
    monkeypatch.setenv("OPENDART_API_KEY", "FROM_ENV")
    assert cec._load_dart_key() == "FROM_ENV"


def test_collect_no_key_skips_without_crash(monkeypatch):
    monkeypatch.setattr(cec, "_load_dart_key", lambda: "")
    out = cec.collect_corp_events()
    assert out == {"codes": 0, "rows": 0, "skipped": "no_dart_key"}


def test_collect_classifies_and_upserts(monkeypatch):
    monkeypatch.setattr(cec, "_load_dart_key", lambda: "KEY")
    items = [
        {"stock_code": "005930", "rcept_dt": "20260701", "rcept_no": "1", "report_nm": "주식분할결정"},
        {"stock_code": "000660", "rcept_dt": "20260702", "rcept_no": "2", "report_nm": "무상증자결정"},
        {"stock_code": "035420", "rcept_dt": "20260703", "rcept_no": "3", "report_nm": "유상증자결정"},
        {"stock_code": "111111", "rcept_dt": "20260703", "rcept_no": "4", "report_nm": "분기보고서"},  # 비매칭
        {"stock_code": "", "rcept_dt": "20260703", "rcept_no": "5", "report_nm": "주식분할"},          # code 없음
    ]
    monkeypatch.setattr(cec, "fetch_dart_events", lambda k, b, e: (items, "000"))
    monkeypatch.setattr(cec, "infer_and_stamp_split_factors", lambda conn: 0)
    conn = _MockConn()
    _patch_db(monkeypatch, conn)

    out = cec.collect_corp_events("2026-07-06", lookback_days=7)
    assert out["matched"] == 3           # split/bonus/rights 만
    assert out["rows"] == 3              # 신규 3건
    assert out["codes"] == 3
    # 분류 정확성
    etypes = {p[0]: p[1] for p in conn.inserts}
    assert etypes["005930"] == "split"
    assert etypes["000660"] == "bonus_issue"
    assert etypes["035420"] == "rights_issue"


def test_collect_calls_stamp_after_capture(monkeypatch):
    monkeypatch.setattr(cec, "_load_dart_key", lambda: "KEY")
    monkeypatch.setattr(cec, "fetch_dart_events", lambda k, b, e: ([], "013"))
    called = {}
    monkeypatch.setattr(cec, "infer_and_stamp_split_factors",
                        lambda conn: (called.__setitem__("stamp", True), 4)[1])
    _patch_db(monkeypatch, _MockConn())
    out = cec.collect_corp_events()
    assert called.get("stamp") is True
    assert out["stamped"] == 4


def test_window_clamps_to_90_days():
    bgn, end = cec._window("2026-07-06", lookback_days=999)
    from datetime import date
    delta = (date.fromisoformat("2026-07-06") - date.fromisoformat(cec._to_iso(bgn))).days
    assert delta == 90
    assert end == "20260706"


# ── fetch_dart_events (mock HTTP) ────────────────────────────────────────────

class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.encoding = None

    def json(self):
        return self._payload


def test_fetch_paginates_via_total_page(monkeypatch):
    pages = {
        1: {"status": "000", "total_page": 2, "list": [{"a": 1}]},
        2: {"status": "000", "total_page": 2, "list": [{"a": 2}]},
    }
    calls = []

    def _get(url, params=None, timeout=None):
        calls.append(params["page_no"])
        return _Resp(pages[params["page_no"]])

    monkeypatch.setattr(cec.requests, "get", _get)
    items, status = cec.fetch_dart_events("KEY", "20260601", "20260630")
    assert calls == [1, 2]
    assert status == "000"
    assert len(items) == 2


def test_fetch_backoff_on_rate_limit_020(monkeypatch):
    seq = [
        {"status": "020", "message": "요청제한"},   # 1차: rate limited
        {"status": "000", "total_page": 1, "list": [{"a": 1}]},  # 재시도 성공
    ]
    idx = {"i": 0}

    def _get(url, params=None, timeout=None):
        r = _Resp(seq[idx["i"]])
        idx["i"] += 1
        return r

    monkeypatch.setattr(cec.requests, "get", _get)
    monkeypatch.setattr(cec.time, "sleep", lambda s: None)  # 백오프 즉시
    items, status = cec.fetch_dart_events("KEY", "20260601", "20260630")
    assert status == "000"
    assert len(items) == 1


def test_fetch_status_013_no_data(monkeypatch):
    monkeypatch.setattr(cec.requests, "get",
                        lambda url, params=None, timeout=None: _Resp({"status": "013"}))
    items, status = cec.fetch_dart_events("KEY", "20260601", "20260630")
    assert status == "013"
    assert items == []


# ── reconcile_corp_events (Item 4) ───────────────────────────────────────────

def test_reconcile_zero_events_is_pass(monkeypatch):
    """이벤트 0건이어도 DART 도달 성공(013)이면 PASS — 희소는 정상."""
    monkeypatch.setattr(cec, "_load_dart_key", lambda: "KEY")
    monkeypatch.setattr(cec, "fetch_dart_events", lambda k, b, e: ([], "013"))
    conn = _MockConn()
    _patch_db(monkeypatch, conn)
    out = cec.reconcile_corp_events("2026-07-06")
    assert out["verdict"] == "PASS"
    assert out["new_rows"] == 0
    # recon params: (trade_date, real_rows, new_rows, overlap, vmr, coverage, verdict)
    assert conn.recon and conn.recon[0][6] == "PASS"


def test_reconcile_unreachable_is_fail(monkeypatch):
    monkeypatch.setattr(cec, "_load_dart_key", lambda: "KEY")
    def _boom(k, b, e):
        raise RuntimeError("network down")
    monkeypatch.setattr(cec, "fetch_dart_events", _boom)
    conn = _MockConn()
    _patch_db(monkeypatch, conn)
    out = cec.reconcile_corp_events("2026-07-06")
    assert out["verdict"] == "FAIL"


def test_reconcile_no_key_is_warn(monkeypatch):
    monkeypatch.setattr(cec, "_load_dart_key", lambda: "")
    conn = _MockConn()
    _patch_db(monkeypatch, conn)
    out = cec.reconcile_corp_events("2026-07-06")
    assert out["verdict"] == "WARN"
    assert conn.recon[0][6] == "WARN"  # verdict 파라미터 위치


def test_reconcile_bad_status_is_fail(monkeypatch):
    monkeypatch.setattr(cec, "_load_dart_key", lambda: "KEY")
    monkeypatch.setattr(cec, "fetch_dart_events", lambda k, b, e: ([], "800"))
    _patch_db(monkeypatch, _MockConn())
    out = cec.reconcile_corp_events("2026-07-06")
    assert out["verdict"] == "FAIL"
