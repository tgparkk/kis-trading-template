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
