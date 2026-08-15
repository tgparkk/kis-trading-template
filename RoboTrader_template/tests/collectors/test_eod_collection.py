import pytest

import collectors.eod_collection as eod


@pytest.fixture(autouse=True)
def _stub_flow_stages(monkeypatch):
    """수급 3축은 실제 API/DB 를 타므로 모든 테스트에서 무해한 스텁으로 고정한다.

    🔑 이 픽스처가 없으면 새 단계가 붙는 순간 기존 테스트가 «네트워크를 타서» 깨진다 —
       단계 추가 시 테스트가 조용히 통합테스트로 변하는 걸 막는다.
    """
    for nm in ("collect_investor_trend", "collect_program_trade", "collect_short_sale"):
        monkeypatch.setattr(eod, nm, lambda d=None: {"skipped": True})


def test_run_data_collection_calls_all_stages(monkeypatch):
    calls = []
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: calls.append("daily") or {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: calls.append("minute") or {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: calls.append("index") or {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: calls.append("stock_market") or {"KOSPI": 1, "KOSDAQ": 1})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: calls.append("foreign_flow") or {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: calls.append("corp_events") or {"rows": 4})
    monkeypatch.setattr(eod, "reconcile_daily", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_minute", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_index", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_foreign_flow", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_corp_events", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "legacy")
    out = eod.run_data_collection("20260623")
    assert calls == ["daily", "minute", "index", "stock_market", "foreign_flow", "corp_events"]
    # 수급 3축은 픽스처 스텁이라 calls 에 안 들어가지만 결과 키는 있어야 한다
    assert out["investor_trend"] == {"skipped": True}
    assert out["program_trade"] == {"skipped": True}
    assert out["short_sale"] == {"skipped": True}
    assert out["daily"] == {"rows": 1}
    assert out["foreign_flow"] == {"rows": 3}
    assert out["corp_events"] == {"rows": 4}
    assert out["reconcile"]["daily"]["verdict"] == "PASS"
    assert out["reconcile"]["foreign_flow"]["verdict"] == "PASS"
    assert out["reconcile"]["corp_events"]["verdict"] == "PASS"


def test_stage_exception_is_isolated(monkeypatch):
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: {"KOSPI": 1, "KOSDAQ": 1})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setattr(eod, "reconcile_daily", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_minute", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_index", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_foreign_flow", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_corp_events", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "new")  # 전환 후 비교 생략
    out = eod.run_data_collection("20260623")
    assert "error" in out["daily"]
    assert out["minute"] == {"rows": 2}
    assert out["foreign_flow"] == {"rows": 3}
    assert out["reconcile"] == {}  # new 모드 비교 생략


def test_foreign_flow_stage_exception_is_isolated(monkeypatch):
    """(단계격리) foreign_flow 수집 실패가 다른 단계·EOD 흐름을 막지 않는다."""
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: {"KOSPI": 1, "KOSDAQ": 1})
    monkeypatch.setattr(
        eod, "collect_foreign_flow",
        lambda d=None: (_ for _ in ()).throw(RuntimeError("naver blocked")))
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "new")
    out = eod.run_data_collection("20260623")
    assert "error" in out["foreign_flow"]
    assert out["daily"] == {"rows": 1}
    assert out["minute"] == {"rows": 2}


def test_run_data_collection_reconcile_includes_index_key(monkeypatch):
    """(e) KIS_DATA_SOURCE=='legacy'일 때 reconcile 결과에 'index'·'foreign_flow' 키가 포함되어야 한다."""
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 0})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 0})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: {"KOSPI": 1, "KOSDAQ": 1})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 0})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 0})
    monkeypatch.setattr(eod, "reconcile_daily", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_minute", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_index", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_foreign_flow", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_corp_events", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "legacy")
    out = eod.run_data_collection("2026-06-26")
    assert "index" in out["reconcile"]
    assert out["reconcile"]["index"]["verdict"] == "PASS"
    assert "foreign_flow" in out["reconcile"]
    assert out["reconcile"]["foreign_flow"]["verdict"] == "PASS"
    assert "corp_events" in out["reconcile"]
    assert out["reconcile"]["corp_events"]["verdict"] == "PASS"


def test_stock_market_stage_exception_is_isolated(monkeypatch):
    """(단계격리) 시장 매핑 수집 실패가 다른 단계·EOD 흐름을 막지 않는다.

    매핑 결측은 resolve_regime_index 가 "both"(보호 과잉) 로 흡수하지만,
    분봉은 그날 못 받으면 자가치유되지 않는다(minute_collector.py:26-38).
    """
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(
        eod, "collect_stock_market",
        lambda: (_ for _ in ()).throw(RuntimeError("FDR down")))
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "new")
    out = eod.run_data_collection("20260623")
    assert "error" in out["stock_market"]
    assert out["daily"] == {"rows": 1}
    assert out["minute"] == {"rows": 2}


def test_stock_market_success_resets_classifier_cache(monkeypatch):
    """수집 성공 시 프로세스 캐시를 무효화해야 다음 조회가 새 매핑을 본다."""
    reset_calls = []
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: {"KOSPI": 900, "KOSDAQ": 1700})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setattr(eod, "reset_market_cache", lambda: reset_calls.append(1))
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "new")
    out = eod.run_data_collection("20260623")
    assert out["stock_market"] == {"KOSPI": 900, "KOSDAQ": 1700}
    assert reset_calls == [1]


def test_stock_market_failure_does_not_reset_cache(monkeypatch):
    """수집이 실패했으면 기존 캐시를 그대로 둔다(빈 매핑으로 갈아끼우지 않는다)."""
    reset_calls = []
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(
        eod, "collect_stock_market",
        lambda: (_ for _ in ()).throw(RuntimeError("FDR down")))
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setattr(eod, "reset_market_cache", lambda: reset_calls.append(1))
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "new")
    eod.run_data_collection("20260623")
    assert reset_calls == []
