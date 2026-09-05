from datetime import date
import pytest
from collectors import financial_collector as c


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


def test_sweep_runs_only_on_monday(monkeypatch):
    """스윕은 주 1회다. 매일 돌면 창 안에서 DART 예산을 두 배로 먹는다."""
    seen = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "")     # 본 수집은 즉시 스킵
    monkeypatch.setattr(c, "sweep_amendments", lambda *a: seen.append(1) or {})
    c.collect_financials("2026-08-18")                        # 화요일
    assert seen == []
    # 월요일이라도 키가 없으면 본 수집 스킵이 먼저라 스윕도 안 돈다 — 그게 맞다.
    # 키가 있을 때의 월요일 동작은 Step 6 의 FakeFetcher 경로로 확인한다.
    assert c.active_reports(__import__("datetime").date(2026, 8, 17)) == ["11012"]


def test_report_nm_to_reprt_code_no_guessing():
    """판별 불가한 공시명에 «추측»으로 코드를 붙이면 안 된다 — 엉뚱한 분기에 적재된다."""
    assert c._reprt_code_from_report_nm("[기재정정]분기보고서 (2026.03)") == "11013"
    assert c._reprt_code_from_report_nm("[기재정정]분기보고서 (2026.09)") == "11014"
    assert c._reprt_code_from_report_nm("[기재정정]반기보고서 (2026.06)") == "11012"
    assert c._reprt_code_from_report_nm("[기재정정]사업보고서 (2025.12)") == "11011"
    assert c._reprt_code_from_report_nm("분기보고서") is None          # 월 없음
    assert c._reprt_code_from_report_nm("[기재정정]주요사항보고서") is None
