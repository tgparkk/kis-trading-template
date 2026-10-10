"""dart_disclosure_backfill.py 순수 함수 단위 테스트 — 네트워크·DB 없음."""
import json
import os

import scripts.dart_disclosure_backfill as ddb


# ── is_correction ────────────────────────────────────────────────────────────

def test_is_correction_detects_bracket_correction_marker():
    assert ddb.is_correction("[기재정정]단일판매ㆍ공급계약체결") is True


def test_is_correction_detects_paren_correction_marker():
    assert ddb.is_correction("(정정)주요사항보고서(유상증자결정)") is True


def test_is_correction_detects_plain_bracket_jeongjeong():
    assert ddb.is_correction("[정정]감사보고서제출") is True


def test_is_correction_false_for_ordinary_rights_issue():
    assert ddb.is_correction("주요사항보고서(유상증자결정)") is False


def test_is_correction_false_for_quarterly_report():
    assert ddb.is_correction("분기보고서") is False


def test_is_correction_false_for_share_merge():
    assert ddb.is_correction("주식병합결정") is False


def test_is_correction_false_for_empty_string():
    assert ddb.is_correction("") is False


# ── item_to_record (row → record mapping) ───────────────────────────────────

def test_item_to_record_maps_all_fields():
    item = {
        "corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930",
        "corp_cls": "Y", "report_nm": "[기재정정]단일판매ㆍ공급계약체결",
        "rcept_no": "20250304000123", "rcept_dt": "20250304", "rm": "유",
    }
    rec = ddb.item_to_record(item, "I")
    assert rec["rcept_no"] == "20250304000123"
    assert rec["stock_code"] == "005930"
    assert rec["rcept_dt"] == "2025-03-04"
    assert rec["pblntf_ty"] == "I"
    assert rec["is_correction"] is True
    assert rec["raw"] == item


def test_item_to_record_blank_stock_code_becomes_none():
    item = {"rcept_no": "20250304000999", "rcept_dt": "20250304",
            "stock_code": "", "report_nm": "분기보고서"}
    rec = ddb.item_to_record(item, "B")
    assert rec["stock_code"] is None
    assert rec["is_correction"] is False


def test_item_to_record_missing_rcept_no_returns_none():
    item = {"rcept_dt": "20250304", "stock_code": "005930", "report_nm": "x"}
    assert ddb.item_to_record(item, "B") is None


def test_item_to_record_malformed_rcept_dt_returns_none():
    item = {"rcept_no": "20250304000123", "rcept_dt": "2025-03-04", "report_nm": "x"}
    assert ddb.item_to_record(item, "B") is None


# ── pagination stop condition (mock fetch_page 응답) ─────────────────────────

class _FixedFetcher:
    """fetch_page(pblntf_ty, day, page, warnings) 를 페이지번호로 미리 정한 응답으로 답한다."""

    def __init__(self, budget, responses):
        self.budget = budget
        self.responses = responses  # {page_no: dict|None}

    def fetch_page(self, pblntf_ty, day, page, warnings):
        self.budget.used += 1
        return self.responses.get(page)


class _Budget:
    def __init__(self):
        self.used = 0


def test_fetch_day_stops_on_short_page_even_if_total_page_says_more():
    responses = {
        1: {"status": "000", "total_page": 5,
            "list": [{"rcept_no": f"r{i}", "rcept_dt": "20250304"} for i in range(ddb._PAGE_COUNT)]},
        2: {"status": "000", "total_page": 5,
            "list": [{"rcept_no": "r_last", "rcept_dt": "20250304"}]},
    }
    fetcher = _FixedFetcher(_Budget(), responses)
    warnings = ddb.Warnings()
    items, calls_made, pages, done = ddb.fetch_day(fetcher, "I", "20250304", warnings)
    assert len(items) == ddb._PAGE_COUNT + 1
    assert pages == 2
    assert done is True
    assert warnings.items == []


def test_fetch_day_single_short_page_completes_in_one_call():
    responses = {1: {"status": "000", "total_page": 1,
                      "list": [{"rcept_no": "r1", "rcept_dt": "20250304"}]}}
    fetcher = _FixedFetcher(_Budget(), responses)
    items, calls_made, pages, done = ddb.fetch_day(fetcher, "B", "20250304", ddb.Warnings())
    assert len(items) == 1
    assert pages == 1
    assert done is True


def test_fetch_day_status_013_is_normal_empty_day():
    responses = {1: {"status": "013", "list": []}}
    fetcher = _FixedFetcher(_Budget(), responses)
    items, calls_made, pages, done = ddb.fetch_day(fetcher, "B", "20250101", ddb.Warnings())
    assert items == []
    assert done is True


def test_fetch_day_none_response_marks_not_done():
    """fetch_page 가 None 을 돌려주면(예: 020 백오프 초과) 그 날은 미완료로 남긴다."""
    responses = {1: None}
    fetcher = _FixedFetcher(_Budget(), responses)
    items, calls_made, pages, done = ddb.fetch_day(fetcher, "I", "20250304", ddb.Warnings())
    assert done is False


def test_fetch_day_stops_at_page_guard_and_warns():
    class _InfiniteFetcher:
        def __init__(self):
            self.budget = _Budget()

        def fetch_page(self, pblntf_ty, day, page, warnings):
            self.budget.used += 1
            return {"status": "000", "total_page": 9999,
                    "list": [{"rcept_no": f"r{page}", "rcept_dt": "20250304"}] * ddb._PAGE_COUNT}

    warnings = ddb.Warnings()
    items, calls_made, pages, done = ddb.fetch_day(_InfiniteFetcher(), "I", "20250304", warnings)
    assert done is False
    assert pages == ddb._PAGE_GUARD
    assert any("가드" in w for w in warnings.items)


# ── resume skipping ──────────────────────────────────────────────────────────

def test_progress_is_done_false_when_no_file(tmp_path):
    progress = ddb.Progress(str(tmp_path / "progress.json"))
    assert progress.is_done("I", "20250304") is False


def test_progress_records_done_and_resume_skips_it(tmp_path):
    path = str(tmp_path / "progress.json")
    progress = ddb.Progress(path)
    progress.record("I", "20250304", calls=3, rows=10, rows_inserted=10, pages=1, done=True)
    progress.record("B", "20250304", calls=1, rows=0, rows_inserted=0, pages=1, done=False)
    reloaded = ddb.Progress(path)
    assert reloaded.is_done("I", "20250304") is True
    assert reloaded.is_done("B", "20250304") is False
    assert reloaded.is_done("I", "20250305") is False


def test_progress_record_stores_rows_inserted_separately_from_rows(tmp_path):
    """rows(수집) 와 rows_inserted(실제 삽입) 는 다를 수 있다(이미 있던 rcept_no 는
    ON CONFLICT DO NOTHING 으로 스킵) — 진행 파일에 둘을 따로 남긴다."""
    path = str(tmp_path / "progress.json")
    progress = ddb.Progress(path)
    progress.record("I", "20250304", calls=5, rows=10, rows_inserted=7, pages=1, done=True)
    with open(path, encoding="utf-8") as f:
        on_disk = json.load(f)
    entry = on_disk["I:20250304"]
    assert entry["rows"] == 10
    assert entry["rows_inserted"] == 7


# ── progress-file atomic write ───────────────────────────────────────────────

def test_atomic_write_json_writes_full_content_and_leaves_no_tmp_file(tmp_path):
    path = str(tmp_path / "out.json")
    ddb.atomic_write_json(path, {"a": 1, "b": [1, 2, 3]})
    with open(path, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == {"a": 1, "b": [1, 2, 3]}
    leftovers = [n for n in os.listdir(tmp_path) if ".tmp." in n]
    assert leftovers == []


def test_atomic_write_json_overwrites_existing_file(tmp_path):
    path = str(tmp_path / "out.json")
    ddb.atomic_write_json(path, {"v": 1})
    ddb.atomic_write_json(path, {"v": 2})
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"v": 2}


# ── key redaction ─────────────────────────────────────────────────────────────

def test_redact_replaces_key_in_message():
    msg = "Connection failed for crtfc_key=SECRET123 during request"
    assert ddb.redact(msg, "SECRET123") == "Connection failed for crtfc_key=<KEY> during request"


def test_redact_handles_empty_key_without_error():
    assert ddb.redact("some error text", "") == "some error text"


def test_redact_repeats_all_occurrences():
    assert ddb.redact("KEY KEY KEY", "KEY") == "<KEY> <KEY> <KEY>"


# ── call budget hard cap ──────────────────────────────────────────────────────

def test_call_budget_raises_once_limit_reached():
    budget = ddb.CallBudget(limit=2)
    budget.check()
    budget.bump()
    budget.check()
    budget.bump()
    try:
        budget.check()
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True


# ── last_reprt_at explicit parameter ─────────────────────────────────────────

def test_fetch_page_sends_default_last_reprt_at_n(tmp_path, monkeypatch):
    sent = {}

    class _Resp:
        encoding = None

        def json(self):
            return {"status": "013", "list": []}

    def _get(url, params=None, timeout=None):
        sent.update(params)
        return _Resp()

    monkeypatch.setattr(ddb.requests, "get", _get)
    cache = ddb.RawCache(str(tmp_path / "raw"))
    budget = ddb.CallBudget(limit=10)
    fetcher = ddb.Fetcher("KEY", cache, budget, str(tmp_path / "call_log.jsonl"), sleep=0)
    fetcher.fetch_page("I", "20250304", 1, ddb.Warnings())
    assert sent["last_reprt_at"] == "N"


def test_fetch_page_honors_explicit_last_reprt_at_y(tmp_path, monkeypatch):
    sent = {}

    class _Resp:
        encoding = None

        def json(self):
            return {"status": "013", "list": []}

    def _get(url, params=None, timeout=None):
        sent.update(params)
        return _Resp()

    monkeypatch.setattr(ddb.requests, "get", _get)
    cache = ddb.RawCache(str(tmp_path / "raw"))
    budget = ddb.CallBudget(limit=10)
    fetcher = ddb.Fetcher("KEY", cache, budget, str(tmp_path / "call_log.jsonl"), sleep=0,
                           last_reprt_at="Y")
    fetcher.fetch_page("I", "20250304", 1, ddb.Warnings())
    assert sent["last_reprt_at"] == "Y"


# ── raw cache atomic write ────────────────────────────────────────────────────

def test_raw_cache_put_leaves_no_tmp_file_and_content_matches(tmp_path):
    cache = ddb.RawCache(str(tmp_path / "raw"))
    data = {"status": "000", "list": [{"rcept_no": "r1"}]}
    cache.put("I", "20250304", 1, data)
    assert cache.get("I", "20250304", 1) == data
    leftovers = [n for n in os.listdir(tmp_path / "raw") if ".tmp." in n]
    assert leftovers == []


# ── concurrency lock file ─────────────────────────────────────────────────────

def test_acquire_lock_creates_file_with_pid(tmp_path):
    lock_path = ddb.acquire_lock(str(tmp_path))
    assert os.path.exists(lock_path)
    with open(lock_path, encoding="utf-8") as f:
        assert f.read().strip() == str(os.getpid())


def test_acquire_lock_raises_when_already_held(tmp_path):
    ddb.acquire_lock(str(tmp_path))
    try:
        ddb.acquire_lock(str(tmp_path))
        raised = False
    except ddb.LockHeld:
        raised = True
    assert raised is True


def test_release_lock_allows_reacquire(tmp_path):
    lock_path = ddb.acquire_lock(str(tmp_path))
    ddb.release_lock(lock_path)
    assert not os.path.exists(lock_path)
    # 해제 뒤엔 다시 잠글 수 있다(예외 없이 통과해야 함)
    ddb.acquire_lock(str(tmp_path))


def test_release_lock_is_noop_when_file_already_gone(tmp_path):
    missing = str(tmp_path / "nope.lock")
    ddb.release_lock(missing)  # OSError 를 삼켜야 한다 — 예외 없이 통과
