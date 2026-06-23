import importlib


def test_resolve_legacy_default(monkeypatch):
    monkeypatch.delenv("KIS_DATA_SOURCE", raising=False)
    monkeypatch.delenv("QUANT_DB", raising=False)
    import config.constants as c
    importlib.reload(c)
    assert c.resolve_daily_source_db() == "robotrader_quant"


def test_resolve_new_points_to_kis_template(monkeypatch):
    monkeypatch.setenv("KIS_DATA_SOURCE", "new")
    import config.constants as c
    importlib.reload(c)
    assert c.resolve_daily_source_db() == "kis_template"
