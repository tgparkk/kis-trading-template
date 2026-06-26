import asyncio
import types
import bot.system_monitor as sm


def test_run_data_collection_invokes_orchestrator(monkeypatch):
    captured = {}
    def fake_run(td):
        captured["td"] = td
        return {"daily": {"rows": 1}, "minute": {"rows": 2}, "index": {"KOSPI": 1}, "reconcile": {}}
    monkeypatch.setattr(sm, "run_data_collection", fake_run, raising=False)

    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)   # __init__ 우회
    mon.logger = types.SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None,
                                       warning=lambda *a, **k: None)

    class _T:
        def strftime(self, f): return "20260623"
    asyncio.run(mon._run_data_collection(_T()))
    assert captured["td"] == "20260623"


def test_run_regime_index_refresh_invokes_with_price_repo(monkeypatch):
    """EOD regime 지수 갱신이 봇 price_repo 로 refresh_regime_indices 를 호출한다
    (게이트 SSOT daily_prices KOSPI/KOSDAQ 자동 신선화, 2026-06-24)."""
    import core.regime.index_refresh as ir
    captured = {}
    def fake_refresh(repo, **kw):
        captured["repo"] = repo
        return {"KOSPI": 5, "KOSDAQ": 5}
    monkeypatch.setattr(ir, "refresh_regime_indices", fake_refresh)

    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)
    mon.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                       warning=lambda *a, **k: None,
                                       error=lambda *a, **k: None)
    sentinel_repo = object()
    mon.bot = types.SimpleNamespace(
        db_manager=types.SimpleNamespace(price_repo=sentinel_repo))

    res = mon._run_regime_index_refresh()
    assert captured["repo"] is sentinel_repo
    assert res == {"KOSPI": 5, "KOSDAQ": 5}  # 결과 dict 반환(EOD 호환·장전 가드용)


def _mk_monitor():
    mon = sm.SystemMonitor.__new__(sm.SystemMonitor)
    logs = {"info": [], "warning": [], "error": []}
    mon.logger = types.SimpleNamespace(
        info=lambda *a, **k: logs["info"].append(a),
        warning=lambda *a, **k: logs["warning"].append(a),
        error=lambda *a, **k: logs["error"].append(a),
    )
    mon.bot = types.SimpleNamespace(
        db_manager=types.SimpleNamespace(price_repo=object()))
    return mon, logs


def test_run_regime_index_refresh_warns_on_zero_rows(monkeypatch):
    """어떤 지수든 0행이면 INFO 대신 WARNING(stale 우려), dict 반환."""
    import core.regime.index_refresh as ir
    monkeypatch.setattr(ir, "refresh_regime_indices",
                        lambda repo, **kw: {"KOSPI": 5, "KOSDAQ": 0})
    mon, logs = _mk_monitor()
    res = mon._run_regime_index_refresh()
    assert res == {"KOSPI": 5, "KOSDAQ": 0}
    assert logs["warning"] and not logs["info"]


def test_run_regime_index_refresh_info_when_all_positive(monkeypatch):
    """전부 >0 이면 INFO 유지, dict 반환."""
    import core.regime.index_refresh as ir
    monkeypatch.setattr(ir, "refresh_regime_indices",
                        lambda repo, **kw: {"KOSPI": 5, "KOSDAQ": 5})
    mon, logs = _mk_monitor()
    res = mon._run_regime_index_refresh()
    assert res == {"KOSPI": 5, "KOSDAQ": 5}
    assert logs["info"] and not logs["warning"]


def test_premarket_regime_refresh_sets_guard_on_success():
    """성공(값>0)이면 가드 설정·중복호출 시 재실행 안 함."""
    mon, logs = _mk_monitor()
    calls = {"n": 0}

    def fake_refresh():
        calls["n"] += 1
        return {"KOSPI": 5, "KOSDAQ": 5}
    mon._run_regime_index_refresh = fake_refresh

    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1
    assert getattr(mon, "_regime_index_refreshed_date", None) is not None
    # 같은 날 중복호출 → 재실행 안 함(하루 1회 가드)
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1


def test_premarket_regime_refresh_no_guard_on_zero():
    """res 0/실패면 가드 미설정(다음 루프 재시도)·WARNING."""
    mon, logs = _mk_monitor()
    calls = {"n": 0}

    def fake_refresh():
        calls["n"] += 1
        return {"KOSPI": 0, "KOSDAQ": 0}
    mon._run_regime_index_refresh = fake_refresh

    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 1
    assert getattr(mon, "_regime_index_refreshed_date", None) is None
    assert logs["warning"]
    # 가드 미설정이라 재호출 시 다시 시도
    asyncio.run(mon._run_premarket_regime_index_refresh())
    assert calls["n"] == 2
