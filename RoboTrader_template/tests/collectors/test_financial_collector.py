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


# ── Item 2(b) — HTTP_FAIL 연속 5회를 무징후로 계속 두드리면 안 된다 ─────────

class _HttpFailFetcher:
    def __init__(self, *a, **kw):
        self.calls = 0
        self.status_counts = {}
        self.conn_resets = 0

    def fetch(self, corp_code, bsns_year, reprt_code, fs_div):
        self.calls += 1
        self.status_counts["HTTP_FAIL"] = self.status_counts.get("HTTP_FAIL", 0) + 1
        return "HTTP_FAIL", {}


def test_http_fail_streak_aborts_after_five_consecutive(monkeypatch):
    """Item 2b — 매 대상이 HTTP_FAIL 이면 opendart 가 사실상 응답 불능이다.
    5연속이면 중단하고 정확한 미수집 개수를 WARNING 해야 한다."""
    warnings = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _HttpFailFetcher())
    _patch_collect_no_db(monkeypatch)
    targets = [(f"T{i}", f"C{i}") for i in range(8)]
    monkeypatch.setattr(c, "_pending_targets", lambda conn, codes, y, r: targets)
    monkeypatch.setattr(c.logger, "warning", lambda msg, *a: warnings.append((msg, a)))

    out = c.collect_financials("2026-08-17")
    assert out["targets_processed"] == 5, "5연속 HTTP_FAIL 뒤 중단돼야 한다"
    assert out["aborted"] == "http_fail_streak"

    streak_msgs = [a for (m, a) in warnings if "HTTP_FAIL" in m and "연속" in m]
    assert len(streak_msgs) == 1
    assert streak_msgs[0][-1] == 3, "8종목 중 처리된 5개를 뺀 3개가 미수집이어야 한다"


# ── Item 2(c) — 실행 시간 상한(45분)을 넘기면 다음 대상 «전»에 멈춰야 한다 ────

def test_deadline_hit_stops_before_next_target(monkeypatch):
    """Item 2c — 시간 상한을 넘기고도 계속 돌면 EOD 파이프라인 전체를 물고 늘어진다.
    time.monotonic 을 첫 대상 처리 «후» 상한 너머로 점프시켜 정확히 1개만 처리되고
    중단되는지 확인한다."""
    warnings = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _CapFetcher())
    _patch_collect_no_db(monkeypatch)
    targets = [(f"T{i}", f"C{i}") for i in range(4)]
    monkeypatch.setattr(c, "_pending_targets", lambda conn, codes, y, r: targets)
    monkeypatch.setattr(c.w, "upsert_filing", lambda conn, filing: None)
    monkeypatch.setattr(c.w, "upsert_accounts", lambda conn, rows: len(rows))
    monkeypatch.setattr(c, "append_raw", lambda path, payload: 1)
    monkeypatch.setattr(c.logger, "warning", lambda msg, *a: warnings.append((msg, a)))

    calls = {"n": 0}

    def fake_monotonic():
        calls["n"] += 1
        # 1회차(t0)·2회차(첫 대상 검사)는 상한 이전, 3회차(둘째 대상 검사)부터 상한 초과.
        if calls["n"] <= 2:
            return 1000.0
        return 1000.0 + c.COLLECT_DEADLINE_SEC + 1

    monkeypatch.setattr(c.time, "monotonic", fake_monotonic)

    out = c.collect_financials("2026-08-17")
    assert out["targets_processed"] == 1
    assert out["deadline_hit"] is True

    deadline_msgs = [a for (m, a) in warnings if "실행 시간 상한" in m]
    assert len(deadline_msgs) == 1
    assert deadline_msgs[0][-1] == 3, "4종목 중 1개 처리 후 3개가 미수집이어야 한다"


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


# ── Item 4 — KIS 빈 응답([])은 성공이 아니다 ─────────────────────────────────

def test_kis_empty_response_counted_and_warned(monkeypatch):
    """Item 4 — fetch_quarterly_ratio 는 「무자료」와 「호출 실패」를 둘 다 []로 돌려준다
    (api/kis_financial_api.py 는 수정 대상 밖). 빈 응답을 그냥 성공으로 세면 실패가
    조용히 묻힌다 - 별도 집계 + WARNING 이 있어야 한다."""
    warnings = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _NoCallFetcher())
    _patch_collect_no_db(monkeypatch)
    codes = ["A", "B", "C", "D", "E"]
    monkeypatch.setattr(c, "load_map", lambda conn: {sc: sc for sc in codes})
    monkeypatch.setattr(c, "load_universe", lambda conn: codes)

    empty_for = {"A", "B", "C"}

    def _fake_fetch(sc):
        return [] if sc in empty_for else [{"stock_code": sc}]

    monkeypatch.setattr(c, "fetch_quarterly_ratio", _fake_fetch)
    monkeypatch.setattr(c.w, "upsert_kis_ratio", lambda conn, rows: len(rows))
    monkeypatch.setattr(c.logger, "warning", lambda msg, *a: warnings.append((msg, a)))

    out = c.collect_financials("2026-08-17")
    assert out["kis_empty"] == 3, "5종목 중 3종목이 빈 응답이어야 한다"

    empty_msgs = [a for (m, a) in warnings if "KIS 비율 응답 빈 값" in m]
    assert len(empty_msgs) == 1
    assert empty_msgs[0][0] == 3, "빈 응답 건수가 정확히 3이어야 한다"
    assert empty_msgs[0][1] == 5, "시도한 종목 수(attempted)가 5여야 한다"


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


# ── Item 1 — 스윕 경로의 DartBlocked 를 삼키면 안 된다 ──────────────────────

class _SweepBlockedFetcher:
    """본 수집(pending target 없음)은 안 타고, 스윕의 _fetch_and_store 에서만 호출된다."""

    def __init__(self, *a, **kw):
        self.calls = 0
        self.status_counts = {}
        self.conn_resets = 0
        self.min_interval = 0.0

    def fetch(self, *a, **kw):
        self.calls += 1
        raise c.DartBlocked("simulated sweep block")


def test_sweep_dart_blocked_propagates_and_marks_summary_blocked(monkeypatch):
    """Item 1 — `sweep_amendments` 안에서 DartBlocked 를 `DartQuotaExceeded` 처럼
    삼키면 IP 차단일에도 EOD 가 성공으로 보이고 reconcile 이 PASS 를 낸다.
    실제 sweep_amendments 경로(list.json → 대상 파싱 → _fetch_and_store)를 태워
    DartBlocked 가 collect_financials 밖으로 전파되고, summary 가 blocked=True 로
    기록된 «뒤»에 재발생하는지 확인한다."""
    written = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "DartFinancialFetcher", lambda *a, **kw: _SweepBlockedFetcher())
    _patch_collect_no_db(monkeypatch)
    # 본 수집 대상은 없음(스윕 경로만 검증) — load_map 은 스윕에서 재사용되므로 여기서 덮어쓴다.
    monkeypatch.setattr(c, "load_map", lambda conn: {"111111": "corp1"})
    monkeypatch.setattr(c, "_write_summary", lambda d, summary: written.append(summary))

    items = [{"report_nm": "[기재정정]분기보고서 (2026.03)", "stock_code": "111111"}]
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **kw: _RespJS({"status": "000", "total_page": 1, "list": items}))

    with pytest.raises(c.DartBlocked):
        c.collect_financials("2026-08-17")   # 월요일, 반기 창 안 → 스윕이 돈다

    assert len(written) == 1, "재발생 «전» summary 가 기록돼야 한다"
    assert written[0]["blocked"] is True


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


# ── Item 5 — WARN 경로가 new_rows=0 을 박아 stalled 게이트를 죽이면 안 된다 ──

def test_reconcile_no_summary_warn_writes_remaining_as_new_rows(monkeypatch):
    """Item 5 — summary 가 없어도 remaining 은 DB 읽기(DART 키 불필요)만으로 계산
    가능하다. WARN 이라고 new_rows=0 을 박으면 stalled(3일 연속 미변동) 게이트가
    영원히 못 뜬다 — 그 값을 그대로 new_rows 로 써야 한다."""
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "load_map", lambda conn: {"TESTR1": "corpr1"})
    monkeypatch.setattr(c, "load_universe", lambda conn: ["TESTR1"])
    monkeypatch.setattr(c, "_pending_targets", lambda conn, codes, y, r: [("TESTR1", "corpr1")])
    d = date(1999, 9, 11)
    trade_date = d.isoformat()
    try:
        os.remove(c._summary_path(d))
    except OSError:
        pass
    try:
        out = c.reconcile_financials(trade_date)
        assert out["verdict"] == "WARN"
        assert out["reason"] == "no_summary"
        assert out["remaining"] == 1, "가짜 pending target 1개가 그대로 remaining 에 반영돼야 한다"

        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT new_rows FROM collection_reconciliation "
                    "WHERE trade_date=%s AND dataset='financials'", (trade_date,))
                row = cur.fetchone()
        assert row is not None and row[0] == 1, "new_rows 가 0 으로 고정돼선 안 된다"
    finally:
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM collection_reconciliation "
                    "WHERE trade_date=%s AND dataset='financials'", (trade_date,))
            conn.commit()


def test_reconcile_escalates_to_fail_after_three_consecutive_warn(monkeypatch):
    """Item 5 — 3영업일 연속 WARN(no_summary) 뒤에도 오늘 또 summary 가 없으면
    「조용히 안 돌아감」으로 보고 FAIL 로 격상해야 한다(spec §8 조건2 의 취지)."""
    monkeypatch.setattr(c, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(c, "load_map", lambda conn: {})
    monkeypatch.setattr(c, "load_universe", lambda conn: [])
    monkeypatch.setattr(c, "_pending_targets", lambda conn, codes, y, r: [])

    prior_dates = [date(1999, 8, 17), date(1999, 8, 18), date(1999, 8, 19)]
    today = date(1999, 8, 20)
    today_iso = today.isoformat()
    all_dates = [pd_.isoformat() for pd_ in prior_dates] + [today_iso]
    try:
        for pd_ in prior_dates:
            c._write_recon(pd_.isoformat(), 5, "WARN")
        try:
            os.remove(c._summary_path(today))
        except OSError:
            pass

        out = c.reconcile_financials(today_iso)
        assert out["verdict"] == "FAIL"
        assert out["reason"] == "no_summary_3d"
    finally:
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM collection_reconciliation "
                    "WHERE dataset='financials' AND trade_date IN %s", (tuple(all_dates),))
            conn.commit()


# ── I7 — 도달성 판정: 소프트 실패 1% 허용 (사장님 결정 2026-09-06) ──────────
# _is_reachable() 은 순수 함수(DB 불필요) — status_counts/calls 만 보고 판정한다.

def test_is_reachable_soft_fail_within_tolerance():
    """800(점검) 5건 / 800호출 = 0.625% ⇒ 문턱(1%) 이내라 도달 가능."""
    summary = {"blocked": False,
               "status_counts": {"000": 790, "013": 5, "800": 5}, "calls": 800}
    reachable, detail = c._is_reachable(summary)
    assert reachable is True


def test_is_reachable_soft_fail_over_tolerance():
    """HTTP_FAIL 20/720 = 2.78% ⇒ 문턱 초과 - 불허, 사유에 soft_fail_ratio 표기."""
    summary = {"blocked": False,
               "status_counts": {"000": 700, "HTTP_FAIL": 20}, "calls": 720}
    reachable, detail = c._is_reachable(summary)
    assert reachable is False
    assert "soft_fail_ratio" in detail


def test_is_reachable_quota_is_strict():
    """020(한도초과)는 비율과 무관하게 1건이라도 있으면 불허 - 엄격."""
    summary = {"blocked": False,
               "status_counts": {"000": 799, "020": 1}, "calls": 800}
    reachable, detail = c._is_reachable(summary)
    assert reachable is False
    assert detail == "quota"


def test_is_reachable_blocked_is_strict():
    """blocked 는 status_counts 와 무관하게 불허 - 엄격."""
    summary = {"blocked": True, "status_counts": {"000": 10}, "calls": 10}
    reachable, detail = c._is_reachable(summary)
    assert reachable is False
    assert detail == "blocked"


def test_is_reachable_empty_summary_is_reachable():
    """calls=0(호출 자체가 없었던 날)이면 도달성 실패로 볼 근거가 없다."""
    summary = {"blocked": False, "status_counts": {}, "calls": 0}
    reachable, detail = c._is_reachable(summary)
    assert reachable is True


def test_is_reachable_boundary_exactly_one_percent():
    """8/800 = 정확히 1% ⇒ 허용(<=), 9/800 = 1.125% ⇒ 불허."""
    ok = {"blocked": False, "status_counts": {"000": 792, "HTTP_FAIL": 8}, "calls": 800}
    reachable_ok, _ = c._is_reachable(ok)
    assert reachable_ok is True

    bad = {"blocked": False, "status_counts": {"000": 791, "HTTP_FAIL": 9}, "calls": 800}
    reachable_bad, _ = c._is_reachable(bad)
    assert reachable_bad is False
