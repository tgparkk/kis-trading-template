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


# ── 2026-08-03: 액면병합 분류 + direction ────────────────────────────────────

def test_classify_recognizes_real_dart_merge_report_names():
    """실측 공시명(2026-08-03 opendart 확인). 병합도 event_type 은 'split' 이고
    구분은 direction 으로 한다 — daily_adj 가 'split'만 소비하므로 새 타입을 만들면
    병합이 조용히 무시된다."""
    assert cec._classify("주식병합결정") == ("split", "merge")
    assert cec._classify("[기재정정]주식병합결정") == ("split", "merge")
    assert cec._classify("주식분할결정") == ("split", "split")
    assert cec._classify("[기재정정]주식분할결정") == ("split", "split")


def test_classify_preserves_existing_matches_and_ignores_noise():
    """기존 동작 보존 — 증자류 분류가 그대로여야 하고 direction 은 없어야 한다."""
    assert cec._classify("무상증자결정") == ("bonus_issue", None)
    assert cec._classify("유상증자결정") == ("rights_issue", None)
    assert cec._classify("분기보고서") == (None, None)


def test_classify_does_not_confuse_corporate_merger_with_share_merge():
    """🔑 합병(合倂, 회사 결합)과 병합(倂合, 액면 병합)은 다른 사건이다.
    '회사분할합병결정' 은 '주식분할'에도 '주식병합'에도 걸리지 않아야 한다 —
    걸리면 회사 합병 공시가 가짜 액면병합으로 둔갑해 가격을 조정해 버린다."""
    assert cec._classify("회사분할합병결정") == (None, None)
    assert cec._classify("주요사항보고서(회사합병결정)") == (None, None)
    assert cec._classify("주요사항보고서(회사분할결정)") == (None, None)


def test_rows_from_items_carries_direction_into_meta():
    items = [
        {"stock_code": "011930", "rcept_dt": "20260220", "rcept_no": "1",
         "report_nm": "주식병합결정"},
        {"stock_code": "101930", "rcept_dt": "20260326", "rcept_no": "2",
         "report_nm": "주식분할결정"},
        {"stock_code": "035420", "rcept_dt": "20260703", "rcept_no": "3",
         "report_nm": "유상증자결정"},
    ]
    rows = cec._rows_from_items(items)
    meta_by_code = {c: m for c, _e, _d, m in rows}
    assert meta_by_code["011930"]["direction"] == "merge"
    assert meta_by_code["101930"]["direction"] == "split"
    assert "direction" not in meta_by_code["035420"]   # 증자류는 방향 개념 없음
    assert {c: e for c, e, _d, _m in rows}["011930"] == "split"


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
        calls.append((params["pblntf_ty"], params["page_no"]))
        return _Resp(pages[params["page_no"]])

    monkeypatch.setattr(cec.requests, "get", _get)
    items, status = cec.fetch_dart_events("KEY", "20260601", "20260630")
    # 유형별로 전 페이지를 돈다
    assert calls == [("B", 1), ("B", 2), ("I", 1), ("I", 2)]
    assert status == "000"
    assert len(items) == 4


def test_fetch_queries_both_b_and_i_types(monkeypatch):
    """🔑 분할·병합 공시는 pblntf_ty='I'(거래소공시)에만 있다 — 실측(2026-08-03):
    011930 '주식병합결정'·101930 '주식분할결정' 모두 B 로는 status 013(무자료).
    B 만 돌던 옛 코드는 분할·병합을 한 건도 잡은 적이 없다."""
    seen = []

    def _get(url, params=None, timeout=None):
        seen.append(params["pblntf_ty"])
        return _Resp({"status": "013"})

    monkeypatch.setattr(cec.requests, "get", _get)
    cec.fetch_dart_events("KEY", "20260601", "20260630")
    assert seen == ["B", "I"]


def test_fetch_surfaces_failure_of_any_single_type(monkeypatch):
    """한 유형만 죽어도 status 는 실패를 반환해야 한다 — I 가 조용히 죽었는데 B 가
    살아 있다는 이유로 PASS 가 나면 분할 탐지 상실이 무징후로 지나간다."""
    def _get(url, params=None, timeout=None):
        if params["pblntf_ty"] == "I":
            return _Resp({"status": "800", "message": "system error"})
        return _Resp({"status": "000", "total_page": 1, "list": [{"a": 1}]})

    monkeypatch.setattr(cec.requests, "get", _get)
    items, status = cec.fetch_dart_events("KEY", "20260601", "20260630")
    assert status == "800"


def test_fetch_backoff_on_rate_limit_020(monkeypatch):
    seq = [
        {"status": "020", "message": "요청제한"},   # 1차: rate limited
        {"status": "000", "total_page": 1, "list": [{"a": 1}]},  # 재시도 성공
        {"status": "013"},                                       # 두 번째 유형
    ]
    idx = {"i": 0}

    def _get(url, params=None, timeout=None):
        r = _Resp(seq[min(idx["i"], len(seq) - 1)])
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


def test_fetch_warns_on_page_truncation(monkeypatch):
    """페이지 상한 절단은 반드시 소리를 내야 한다(무징후 누락 금지)."""
    warnings = []
    monkeypatch.setattr(cec.logger, "warning",
                        lambda msg, *a, **kw: warnings.append(msg % a if a else msg))
    monkeypatch.setattr(cec, "_MAX_PAGES", 2)
    monkeypatch.setattr(
        cec.requests, "get",
        lambda url, params=None, timeout=None: _Resp(
            {"status": "000", "total_page": 99, "list": [{"a": 1}]}))
    cec.fetch_dart_events("KEY", "20260601", "20260630")
    assert any("절단" in w for w in warnings), warnings


def test_fetch_does_not_warn_when_no_truncation(monkeypatch):
    """변이 대조 — 절단이 없으면 경고가 없어야 한다(경고가 항상 켜져 있으면 판별력 0)."""
    warnings = []
    monkeypatch.setattr(cec.logger, "warning",
                        lambda msg, *a, **kw: warnings.append(msg % a if a else msg))
    monkeypatch.setattr(
        cec.requests, "get",
        lambda url, params=None, timeout=None: _Resp(
            {"status": "000", "total_page": 1, "list": [{"a": 1}]}))
    cec.fetch_dart_events("KEY", "20260601", "20260630")
    assert not any("절단" in w for w in warnings), warnings


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
