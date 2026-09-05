import os
from datetime import date

import pytest
import requests

from collectors import financial_collector as c
from db.kis_db_connection import KisDbConnection


def test_window_boundaries_are_business_dates():
    """🔴 초안이 08/15 로 잡았다가 «토요일(광복절)»이라 EOD 가 안 도는 걸 놓쳤다.
    합의된 창은 08/17 이다."""
    assert c.active_reports(date(2026, 8, 16)) == []      # 창 열리기 전
    assert c.active_reports(date(2026, 8, 17)) == ["11012"]  # 반기 창 첫날
    assert c.active_reports(date(2026, 9, 20)) == ["11012"]  # 마지막날 포함
    assert c.active_reports(date(2026, 9, 21)) == []      # 창 밖
    assert c.active_reports(date(2026, 6, 20)) == ["11013"]  # 1Q 창
    assert c.active_reports(date(2026, 7, 1)) == []       # 창 사이 공백


def test_out_of_window_makes_zero_dart_calls(monkeypatch):
    """창 밖이면 DART 를 «한 번도» 부르지 않아야 한다."""
    calls = {"n": 0}

    class FakeFetcher:
        def __init__(self, *a, **kw):
            self.calls, self.status_counts, self.conn_resets = 0, {}, 0

        def fetch(self, *a, **kw):
            calls["n"] += 1
            return "000", {"list": []}

    monkeypatch.setattr(c, "DartFinancialFetcher", FakeFetcher)
    monkeypatch.setattr(c, "_load_dart_key", lambda: "dummy")
    out = c.collect_financials("2026-07-01")   # 창 사이 공백
    assert calls["n"] == 0
    assert out["skipped"] == "out_of_window"


def test_missing_key_skips_without_blocking(monkeypatch):
    """키가 없으면 EOD 를 막지 않고 스킵한다 (corp_events 전례)."""
    monkeypatch.setattr(c, "_load_dart_key", lambda: "")
    out = c.collect_financials("2026-08-17")
    assert out["skipped"] == "no_dart_key"


def test_report_nm_to_reprt_code_no_guessing():
    """판별 불가한 공시명에 «추측»으로 코드를 붙이면 안 된다 — 엉뚱한 분기에 적재된다."""
    assert c._reprt_code_from_report_nm("[기재정정]분기보고서 (2026.03)") == "11013"
    assert c._reprt_code_from_report_nm("[기재정정]분기보고서 (2026.09)") == "11014"
    assert c._reprt_code_from_report_nm("[기재정정]반기보고서 (2026.06)") == "11012"
    assert c._reprt_code_from_report_nm("[기재정정]사업보고서 (2025.12)") == "11011"
    assert c._reprt_code_from_report_nm("분기보고서") is None          # 월 없음
    assert c._reprt_code_from_report_nm("[기재정정]주요사항보고서") is None


# ── fix round 1 (2026-09-06, Task 6 review) — 공용 헬퍼 ──────────────────────

class _DummyCM:
    """KisDbConnection.get_connection() 을 대체하는 무해 컨텍스트 매니저.
    이 안에서 쓰이는 conn 은 전부 monkeypatch 된 함수로만 소비돼야 한다(직접 커서 호출 없음)."""

    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


class _NoCallFetcher:
    """pending target 이 없어서 fetch() 가 호출되면 안 되는 테스트용 페처."""

    def __init__(self, *a, **kw):
        self.calls = 0
        self.status_counts = {}
        self.conn_resets = 0

    def fetch(self, *a, **kw):
        raise AssertionError("fetch 가 호출되면 안 된다 — pending target 이 없어야 하는 테스트다")


def _patch_collect_no_db(monkeypatch):
    """collect_financials 가 실제 DB/네트워크를 전혀 안 건드리게 기본값을 깐다.
    개별 테스트는 이 호출 «뒤에» 필요한 부분만 다시 monkeypatch 로 덮어쓴다."""
    monkeypatch.setattr(c.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(c.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(c.fm, "ensure_view", lambda conn: None)
    monkeypatch.setattr(c, "load_map", lambda conn: {})
    monkeypatch.setattr(c, "load_universe", lambda conn: [])
    monkeypatch.setattr(c, "_pending_targets", lambda conn, codes, y, r: [])
    monkeypatch.setattr(c, "fetch_quarterly_ratio", lambda sc: [])
    monkeypatch.setattr(c.w, "recompute_amendment_flags", lambda conn: None)
    monkeypatch.setattr(c.fm, "report_mapping_coverage", lambda conn: {})
    monkeypatch.setattr(c, "_write_summary", lambda *a, **kw: None)


# ── Item 1 (PLAN DEFECT) — 사업보고서 창은 전년도 결산분 ─────────────────────

def test_annual_report_window_uses_prior_fiscal_year(monkeypatch):
    """🔴 사업보고서(11011) 창(04/03~05/10)에 접수되는 보고서는 «전년도» 결산분이다.
    `d.year` 그대로 쓰면 존재하지 않는 당해년도를 조회해 전 종목이 013 확정으로 잘못
    기록된다. 분기 창은 그대로 당해년도를 써야 한다."""
    seen = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _NoCallFetcher())
    _patch_collect_no_db(monkeypatch)

    def _spy_pending(conn, codes, bsns_year, reprt_code):
        seen.append((bsns_year, reprt_code))
        return []

    monkeypatch.setattr(c, "_pending_targets", _spy_pending)

    c.collect_financials("2026-04-15")   # 11011 창
    assert seen == [("2025", "11011")], "사업보고서 창은 FY-1(전년도) 을 써야 한다"

    seen.clear()
    c.collect_financials("2026-06-01")   # 11013(1Q) 창
    assert seen == [("2026", "11013")], "분기 창은 당해년도를 써야 한다"


def test_bsns_year_for_helper_direct():
    assert c._bsns_year_for(date(2026, 4, 15), "11011") == "2025"
    assert c._bsns_year_for(date(2026, 6, 1), "11013") == "2026"
    assert c._bsns_year_for(date(2026, 8, 17), "11012") == "2026"


# ── Item 5 — 스윕 요일 게이트를 실제 경로로 검증 ─────────────────────────────

def test_sweep_runs_only_on_monday(monkeypatch):
    """스윕은 주 1회다. 매일 돌면 창 안에서 DART 예산을 두 배로 먹는다.
    🔴 이전 버전은 키를 빈 값으로 둬 collect_financials 가 바로 스킵돼 스윕 분기
    자체를 통과하지 못했다(무결과 통과 = 판별력 없는 테스트). 키를 채우고 창 안
    날짜로 실제 로직을 태운다."""
    seen = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _NoCallFetcher())
    _patch_collect_no_db(monkeypatch)
    monkeypatch.setattr(c, "sweep_amendments", lambda *a, **kw: seen.append(1) or {})

    c.collect_financials("2026-08-18")   # 화요일, 반기 창 안
    assert seen == []

    c.collect_financials("2026-08-17")   # 월요일, 반기 창 첫날
    assert seen == [1]


def test_quota_abort_leaves_existing_rows_intact(monkeypatch):
    """🔴 스펙 테스트 #6 재작성 — 이전 버전은 collect 루프를 전혀 태우지 않고
    `raise/except` 만 흉내 냈다(판별력 없음). 진짜 collect_financials 를 fake
    fetcher 로 굴려서 한도 초과 «전» 처리분이 커밋된 채 남고, 반환값이 부분
    진척을 보고하는지 확인한다. 실 DB 테스트 — teardown 에서 정리."""

    class _Fetcher:
        def __init__(self, *a, **kw):
            self.calls = 0
            self.status_counts = {}
            self.conn_resets = 0

        def fetch(self, corp_code, bsns_year, reprt_code, fs_div):
            self.calls += 1
            if corp_code == "00000001":
                self.status_counts["000"] = self.status_counts.get("000", 0) + 1
                return "000", {"list": [{
                    "rcept_no": "20260818999901", "reprt_code": reprt_code,
                    "bsns_year": bsns_year, "corp_code": corp_code, "sj_div": "BS",
                    "account_id": "ifrs-full_Assets", "account_nm": "자산총계",
                    "thstrm_amount": "1,000", "ord": "1", "currency": "KRW"}]}
            self.status_counts["020"] = self.status_counts.get("020", 0) + 1
            raise c.DartQuotaExceeded("simulated")

    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _Fetcher())
    monkeypatch.setattr(c, "load_map", lambda conn: {"TESTQ1": "00000001", "TESTQ2": "00000002"})
    monkeypatch.setattr(c, "load_universe", lambda conn: ["TESTQ1", "TESTQ2"])
    monkeypatch.setattr(c, "fetch_quarterly_ratio", lambda sc: [])
    monkeypatch.setattr(c, "sweep_amendments", lambda *a, **kw: {})  # 화요일이라 방어적으로만

    try:
        out = c.collect_financials("2026-08-18")   # 화요일, 반기 창 안(bsns_year=2026)
        assert out["quota_hit"] is True
        assert out["filings"] == 1
        assert out["accounts"] == 1
        assert out["targets_total"] == 2
        assert out["targets_processed"] == 1, "TESTQ1 만 처리되고 부분 진척이 보고돼야 한다"

        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM dart_financial_filings WHERE stock_code='TESTQ1'")
                assert cur.fetchone()[0] == 1, "한도 초과 «전» 처리분이 사라지면 안 된다"
                cur.execute(
                    "SELECT count(*) FROM dart_financial_accounts WHERE rcept_no='20260818999901'")
                assert cur.fetchone()[0] == 1
                cur.execute(
                    "SELECT count(*) FROM dart_financial_filings WHERE stock_code='TESTQ2'")
                assert cur.fetchone()[0] == 0, "한도 초과된 종목은 적재되면 안 된다"
    finally:
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM dart_financial_accounts WHERE rcept_no='20260818999901'")
                cur.execute(
                    "DELETE FROM dart_financial_filings WHERE stock_code IN ('TESTQ1','TESTQ2')")
                cur.execute(
                    "DELETE FROM dart_financial_nodata WHERE stock_code IN ('TESTQ1','TESTQ2')")
            conn.commit()
        for p in (c._summary_path(date(2026, 8, 18)),
                  os.path.join(c.RAW_DIR, "dart_20260818.jsonl.gz")):
            try:
                os.remove(p)
            except OSError:
                pass


# ── Item 2(a) — 일일 상한 도달을 무징후로 넘기면 안 된다 ─────────────────────

class _CapFetcher:
    def __init__(self, *a, **kw):
        self.calls = 0
        self.status_counts = {}
        self.conn_resets = 0

    def fetch(self, corp_code, bsns_year, reprt_code, fs_div):
        self.calls += 1
        self.status_counts["000"] = self.status_counts.get("000", 0) + 1
        return "000", {"list": [{
            "rcept_no": f"2999999999{corp_code}", "reprt_code": reprt_code,
            "bsns_year": bsns_year, "corp_code": corp_code, "sj_div": "BS",
            "account_id": "ifrs-full_Assets", "account_nm": "자산총계",
            "thstrm_amount": "1,000", "ord": "1", "currency": "KRW"}]}


def test_daily_cap_hit_warns_with_exact_uncovered_count(monkeypatch):
    """Item 2a — 상한 도달을 INFO 로 뭉개면 «몇 종목이 밀렸는지» 안 보인다.
    WARNING + 정확한 미수집 개수가 남아야 한다."""
    warnings = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _CapFetcher())
    _patch_collect_no_db(monkeypatch)
    monkeypatch.setattr(c, "_pending_targets",
                        lambda conn, codes, y, r: [("A", "ca"), ("B", "cb"), ("C", "cc")])
    monkeypatch.setattr(c.w, "upsert_filing", lambda conn, filing: None)
    monkeypatch.setattr(c.w, "upsert_accounts", lambda conn, rows: len(rows))
    monkeypatch.setattr(c, "append_raw", lambda path, payload: 1)
    monkeypatch.setattr(c.logger, "warning", lambda msg, *a: warnings.append((msg, a)))

    out = c.collect_financials("2026-08-17", daily_cap=1)
    assert out["cap_hit"] is True
    assert out["filings"] == 1, "A 하나만 처리돼야 한다"

    cap_msgs = [a for (m, a) in warnings if "일일 상한" in m]
    assert len(cap_msgs) == 1
    assert cap_msgs[0][-1] == 2, "미수집 개수가 정확히 2(B,C)여야 한다"


# ── Item 2(d) — corp_code 매핑 없는 종목을 무징후로 빼면 안 된다 ─────────────

def test_unmapped_corp_code_warns_and_calls_report_mapping_coverage(monkeypatch):
    """Item 2d — corp_code 매핑이 없어 대상에서 빠진 종목은 WARNING 으로 남아야 하고,
    collect 끝에 `financial_metrics.report_mapping_coverage` 가 반드시 호출돼야 한다."""
    warnings = []
    coverage_calls = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _NoCallFetcher())
    _patch_collect_no_db(monkeypatch)
    monkeypatch.setattr(c, "load_map", lambda conn: {"A": "ca"})       # B,C 매핑 없음
    monkeypatch.setattr(c, "load_universe", lambda conn: ["A", "B", "C"])

    def _coverage(conn):
        coverage_calls.append(1)
        return {"matched": 1, "total_stocks": 1, "unmatched_count": 0, "unmatched_stocks": []}

    monkeypatch.setattr(c.fm, "report_mapping_coverage", _coverage)
    monkeypatch.setattr(c.logger, "warning", lambda msg, *a: warnings.append((msg, a)))

    c.collect_financials("2026-08-17")

    unmapped_msgs = [a for (m, a) in warnings if "corp_code 매핑 없는" in m]
    assert len(unmapped_msgs) == 1
    assert unmapped_msgs[0][-1] == 2, "매핑 없는 종목이 정확히 2개(B,C)여야 한다"
    assert coverage_calls == [1], "report_mapping_coverage 가 collect 끝에 1회 호출돼야 한다"


# ── Item 2(b)/7 — KIS 상한 미조회 + 실패 집계가 무징후면 안 된다 ────────────

def test_kis_uncovered_and_failures_are_warned_with_count(monkeypatch):
    """Item 2b — universe 가 daily_cap 보다 크면 못 돈 종목 수를 WARNING 해야 한다.
    Item 7 — KIS 실패는 debug 로 묻지 않고 건수+대표 예외를 WARNING 해야 한다."""
    warnings = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _NoCallFetcher())
    _patch_collect_no_db(monkeypatch)
    codes = ["A", "B", "C"]
    monkeypatch.setattr(c, "load_map", lambda conn: {sc: sc for sc in codes})
    monkeypatch.setattr(c, "load_universe", lambda conn: codes)

    def _fail(sc):
        raise RuntimeError(f"boom-{sc}")

    monkeypatch.setattr(c, "fetch_quarterly_ratio", _fail)
    monkeypatch.setattr(c.logger, "warning", lambda msg, *a: warnings.append((msg, a)))

    out = c.collect_financials("2026-08-17", daily_cap=2)
    assert out["kis_fail"] == 2, "cap=2 이므로 회전에서 뽑힌 2종목만 시도되고 전부 실패해야 한다"

    fail_msgs = [(m, a) for (m, a) in warnings if "KIS 비율 조회 실패" in m]
    assert len(fail_msgs) == 1
    assert fail_msgs[0][1][0] == 2, "실패 건수가 정확히 2여야 한다"

    uncovered_msgs = [a for (m, a) in warnings if "KIS 비율 조회 상한" in m]
    assert len(uncovered_msgs) == 1
    assert uncovered_msgs[0][-1] == 1, "3종목 중 cap 2 를 넘는 1종목이 미조회여야 한다"


def test_kis_rotation_covers_all_codes_across_cycles():
    """Item 2b — 고정 접두(`codes[:cap]`)면 앞쪽 종목만 매일 도니, 날짜 기반 순환으로
    ⌈N/cap⌉ 회 안에 전 종목이 한 번씩 커버돼야 한다."""
    codes = [(str(i), str(i)) for i in range(10)]
    cap = 3
    seen = set()
    for day in range(1, 5):  # ceil(10/3) = 4
        batch = c._kis_rotation(codes, cap, day)
        assert len(batch) == cap
        seen.update(sc for sc, _ in batch)
    assert seen == {str(i) for i in range(10)}, "4회 순환 안에 전 종목이 커버돼야 한다"


def test_kis_rotation_empty_codes_returns_empty():
    assert c._kis_rotation([], 800, 123) == []


# ── Item 6 — DartBlocked 는 quota_hit 으로 뭉개면 안 된다 ────────────────────

class _BlockedFetcher:
    def __init__(self, *a, **kw):
        self.calls = 0
        self.status_counts = {}
        self.conn_resets = 0

    def fetch(self, *a, **kw):
        self.calls += 1
        raise c.DartBlocked("simulated block")


def test_dart_blocked_reraises_and_marks_summary_blocked(monkeypatch):
    """Item 6 — DartBlocked 는 ERROR 로그 + summary blocked=True 기록 후 재발생해야
    EOD 의 `_safe` 래퍼가 이걸 에러로 잡는다. quota_hit 으로 접으면 EOD 가 성공으로 본다."""
    written = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _BlockedFetcher())
    _patch_collect_no_db(monkeypatch)
    monkeypatch.setattr(c, "_pending_targets", lambda conn, codes, y, r: [("A", "ca")])
    monkeypatch.setattr(c, "_write_summary", lambda d, summary: written.append(summary))

    with pytest.raises(c.DartBlocked):
        c.collect_financials("2026-08-17")

    assert len(written) == 1, "재발생 «전» summary 가 기록돼야 한다"
    assert written[0]["blocked"] is True
    assert written[0]["quota_hit"] is False, "차단은 quota_hit 과 별개 플래그여야 한다"


# ── Item 2(c)/8 — 스윕 cap 절단 경고 + fetcher 재사용 ────────────────────────

class _RespJS:
    def __init__(self, js):
        self._js = js
        self.encoding = None

    def json(self):
        return self._js


def test_sweep_drops_over_cap_candidates_and_reuses_fetcher(monkeypatch):
    """Item 2c — cap 초과분을 조용히 버리면 무징후 절단이다. WARNING 필수.
    Item 8 — `fetcher=` 로 넘긴 인스턴스를 재사용해야 한다(calls 가 한 곳에 누적)."""
    warnings = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(c.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(c.w, "recompute_amendment_flags", lambda conn: None)
    monkeypatch.setattr(c, "load_map", lambda conn: {})   # 아무 종목도 안 걸려 fetch 방지
    monkeypatch.setattr(c.logger, "warning", lambda msg, *a: warnings.append((msg, a)))

    items = [
        {"report_nm": "[기재정정]분기보고서 (2026.03)", "stock_code": "111111"},
        {"report_nm": "[기재정정]분기보고서 (2026.03)", "stock_code": "222222"},
        {"report_nm": "[기재정정]분기보고서 (2026.03)", "stock_code": "333333"},
    ]
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **kw: _RespJS({"status": "000", "total_page": 1, "list": items}))

    class _SharedFetcher:
        def __init__(self):
            self.calls = 5   # 본 수집에서 이미 5호출을 쓴 상태를 흉내
            self.status_counts = {"000": 5}
            self.min_interval = 0.0

        def fetch(self, *a, **kw):
            raise AssertionError("cmap 이 비어있으니 fetch 가 호출되면 안 된다")

    shared = _SharedFetcher()
    out = c.sweep_amendments(cap=1, fetcher=shared)

    assert out["calls"] == 5, "주어진 fetcher 인스턴스를 재사용해야 한다(새로 만들면 0부터 시작한다)"
    assert out["candidates"] == 3

    dropped_msgs = [a for (m, a) in warnings if "cap(" in m and "미처리" in m]
    assert len(dropped_msgs) == 1


def test_sweep_list_json_error_returns_partial_without_crashing(monkeypatch):
    """Item 8 — list.json 요청/파싱 오류는 WARNING 으로 남기고 스윕만 멈춘다
    (본 수집·EOD 전체를 막지 않는다)."""
    warnings = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(c.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(c.w, "recompute_amendment_flags", lambda conn: None)
    monkeypatch.setattr(c, "load_map", lambda conn: {})
    monkeypatch.setattr(c.logger, "warning", lambda msg, *a: warnings.append((msg, a)))

    def _boom(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(requests, "get", _boom)

    out = c.sweep_amendments()   # fetcher=None → 내부에서 하나 생성
    assert out["candidates"] == 0
    assert out["filings"] == 0

    err_msgs = [a for (m, a) in warnings if "list.json 요청 실패" in m]
    assert len(err_msgs) == 1


# ── Item 3 — reconcile 의 spec §8 조건1(도달성) 게이트 ──────────────────────
# 연도만 합성(1999)으로 두고 월/일은 실제 창(11012: 08/17~09/20) 안에 둔다 —
# active_reports() 는 (month, day) 만 보므로 실제 운영 이력과 절대 안 겹친다.

def test_reconcile_warn_when_summary_missing(monkeypatch):
    """summary 파일이 없으면 원인 불명 상태를 FAIL 로 단정하지 않고 WARN 한다."""
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    d = date(1999, 9, 1)
    trade_date = d.isoformat()
    try:
        os.remove(c._summary_path(d))
    except OSError:
        pass
    try:
        out = c.reconcile_financials(trade_date)
        assert out["verdict"] == "WARN"
        assert out["reason"] == "no_summary"
    finally:
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM collection_reconciliation "
                    "WHERE trade_date=%s AND dataset='financials'", (trade_date,))
            conn.commit()


def test_reconcile_fails_when_status_counts_unreachable(monkeypatch):
    """spec §8 조건1: status_counts 에 {000,013} 밖 상태가 있으면 진척률과 무관하게 FAIL."""
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    d = date(1999, 9, 2)
    trade_date = d.isoformat()
    c._write_summary(d, {"trade_date": trade_date, "calls": 4,
                          "status_counts": {"000": 3, "020": 1}, "blocked": False})
    try:
        out = c.reconcile_financials(trade_date)
        assert out["verdict"] == "FAIL"
        assert out["reason"] == "unreachable"
        assert out["reachable"] is False
    finally:
        try:
            os.remove(c._summary_path(d))
        except OSError:
            pass
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM collection_reconciliation "
                    "WHERE trade_date=%s AND dataset='financials'", (trade_date,))
            conn.commit()


def test_reconcile_passes_when_reachable_and_not_stalled(monkeypatch):
    """도달성 통과 + 이력 3일 미만(정지 판정 불가)이면 PASS."""
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    d = date(1999, 9, 3)
    trade_date = d.isoformat()
    c._write_summary(d, {"trade_date": trade_date, "calls": 4,
                          "status_counts": {"000": 3, "013": 1}, "blocked": False})
    try:
        out = c.reconcile_financials(trade_date)
        assert out["verdict"] == "PASS"
        assert out["reachable"] is True
        assert "reason" not in out
    finally:
        try:
            os.remove(c._summary_path(d))
        except OSError:
            pass
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM collection_reconciliation "
                    "WHERE trade_date=%s AND dataset='financials'", (trade_date,))
            conn.commit()
