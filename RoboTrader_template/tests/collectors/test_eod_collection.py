"""EOD 수집 오케스트레이터 테스트.

🔴 2026-08-17 — 레거시 교차비교(reconcile) 제거에 따른 테스트 정리:
   `run_data_collection` 안의 `if KIS_DATA_SOURCE == "legacy"` 게이트와
   reconcile_daily/minute/index/foreign_flow/corp_events 호출이 사라졌다.
   따라서 "legacy 분기에서 reconcile 결과가 채워진다"를 단언하던 두 테스트
   (`test_run_data_collection_calls_all_stages` 의 reconcile 단언 ·
    `test_run_data_collection_reconcile_includes_index_key`)는 **존재하지 않는
   동작을 단언**하게 되므로 반전/제거했다.
   ⚠️ 반환 dict 의 ``"reconcile"`` 키 자체는 **유지**된다 —
      bot/system_monitor.py 가 그 키로 로그 문구를 고르는 라이브 계약이다.
      항상 빈 dict 임을 아래에서 고정한다(음성 대조).
"""
import pytest

import collectors.eod_collection as eod


@pytest.fixture(autouse=True)
def _stub_flow_stages(monkeypatch):
    """수급 3축은 실제 API/DB 를 타므로 모든 테스트에서 무해한 스텁으로 고정한다.

    🔑 이 픽스처가 없으면 새 단계가 붙는 순간 기존 테스트가 «네트워크를 타서» 깨진다 —
       단계 추가 시 테스트가 조용히 통합테스트로 변하는 걸 막는다.
    """
    for nm in ("collect_investor_trend", "collect_program_trade", "collect_short_sale",
               "collect_credit_balance", "collect_overtime"):
        monkeypatch.setattr(eod, nm, lambda d=None: {"skipped": True})


def test_run_data_collection_calls_all_stages(monkeypatch):
    calls = []
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: calls.append("daily") or {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: calls.append("minute") or {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: calls.append("index") or {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: calls.append("stock_market") or {"KOSPI": 1, "KOSDAQ": 1})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: calls.append("foreign_flow") or {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: calls.append("corp_events") or {"rows": 4})
    out = eod.run_data_collection("20260623")
    assert calls == ["daily", "minute", "index", "stock_market", "foreign_flow", "corp_events"]
    # 수급 3축은 픽스처 스텁이라 calls 에 안 들어가지만 결과 키는 있어야 한다
    assert out["investor_trend"] == {"skipped": True}
    assert out["program_trade"] == {"skipped": True}
    assert out["short_sale"] == {"skipped": True}
    assert out["credit_balance"] == {"skipped": True}
    assert out["overtime"] == {"skipped": True}
    assert out["daily"] == {"rows": 1}
    assert out["foreign_flow"] == {"rows": 3}
    assert out["corp_events"] == {"rows": 4}


def test_reconcile_key_is_present_but_always_empty(monkeypatch):
    """[계약 반전] `reconcile` 키는 남되 **항상 비어 있다**.

    이전 계약: KIS_DATA_SOURCE=legacy 를 넣으면
      out["reconcile"]["daily"|"index"|"foreign_flow"|"corp_events"] 가 채워졌다.
    새 계약: 레거시 대조 자체가 제거됐으므로 무슨 env 를 넣든 빈 dict.
      → EOD 로그는 항상 "(전환완료 비교생략)" 으로 고정된다(라이브 현행 동작과 동일).

    음성 대조: 폐지된 스위치를 «실제로 넣고» 확인한다.
    """
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: {"KOSPI": 1, "KOSDAQ": 1})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setenv("KIS_DATA_SOURCE", "legacy")
    out = eod.run_data_collection("20260623")
    assert "reconcile" in out, "system_monitor 가 읽는 키 — 지우면 안 된다"
    assert out["reconcile"] == {}


def test_reconcile_machinery_is_gone():
    """레거시 대조 심볼이 되살아나지 않도록 고정(도달 불가 코드 재유입 방지).

    이 함수들은 죽은 DB(robotrader / robotrader_quant)에 psycopg2 로 직접 붙었다.
    `robotrader` 삭제 후 되살아나면 EOD 가 매일 실패한다.
    """
    for nm in ("reconcile_daily", "reconcile_minute", "reconcile_index",
               "reconcile_foreign_flow", "KIS_DATA_SOURCE"):
        assert not hasattr(eod, nm), f"제거된 심볼이 되살아났다: {nm}"


def test_stage_exception_is_isolated(monkeypatch):
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: {"KOSPI": 1, "KOSDAQ": 1})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    out = eod.run_data_collection("20260623")
    assert "error" in out["daily"]
    assert out["minute"] == {"rows": 2}
    assert out["foreign_flow"] == {"rows": 3}
    assert out["reconcile"] == {}


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
    out = eod.run_data_collection("20260623")
    assert "error" in out["foreign_flow"]
    assert out["daily"] == {"rows": 1}
    assert out["minute"] == {"rows": 2}


def test_stock_market_stage_exception_is_isolated(monkeypatch):
    """(단계격리) 시장 매핑 수집 실패가 다른 단계·EOD 흐름을 막지 않는다.

    매핑 결측은 resolve_regime_index 가 "both"(보호 과잉) 로 흡수하지만,
    분봉은 그날 못 받으면 자가치유되지 않는다(minute_collector.py 참조).
    """
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(
        eod, "collect_stock_market",
        lambda: (_ for _ in ()).throw(RuntimeError("FDR down")))
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
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
    eod.run_data_collection("20260623")
    assert reset_calls == []
