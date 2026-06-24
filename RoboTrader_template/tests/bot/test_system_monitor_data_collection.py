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

    mon._run_regime_index_refresh()
    assert captured["repo"] is sentinel_repo
