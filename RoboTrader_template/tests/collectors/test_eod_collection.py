import collectors.eod_collection as eod


def test_run_data_collection_calls_all_stages(monkeypatch):
    calls = []
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: calls.append("daily") or {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: calls.append("minute") or {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: calls.append("index") or {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: calls.append("foreign_flow") or {"rows": 3})
    monkeypatch.setattr(eod, "reconcile_daily", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_minute", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_index", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_foreign_flow", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "legacy")
    out = eod.run_data_collection("20260623")
    assert calls == ["daily", "minute", "index", "foreign_flow"]
    assert out["daily"] == {"rows": 1}
    assert out["foreign_flow"] == {"rows": 3}
    assert out["reconcile"]["daily"]["verdict"] == "PASS"
    assert out["reconcile"]["foreign_flow"]["verdict"] == "PASS"


def test_stage_exception_is_isolated(monkeypatch):
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "reconcile_daily", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_minute", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_index", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_foreign_flow", lambda td: {"verdict": "PASS"})
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
    monkeypatch.setattr(
        eod, "collect_foreign_flow",
        lambda d=None: (_ for _ in ()).throw(RuntimeError("naver blocked")))
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
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 0})
    monkeypatch.setattr(eod, "reconcile_daily", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_minute", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_index", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "reconcile_foreign_flow", lambda td: {"verdict": "PASS"})
    monkeypatch.setattr(eod, "KIS_DATA_SOURCE", "legacy")
    out = eod.run_data_collection("2026-06-26")
    assert "index" in out["reconcile"]
    assert out["reconcile"]["index"]["verdict"] == "PASS"
    assert "foreign_flow" in out["reconcile"]
    assert out["reconcile"]["foreign_flow"]["verdict"] == "PASS"
