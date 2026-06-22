import os
from db.kis_db_connection import KisDbConnection


def test_get_config_defaults_to_kis_template_db(monkeypatch):
    for k in ("KIS_DB_HOST", "KIS_DB_PORT", "KIS_DB_NAME", "KIS_DB_USER", "KIS_DB_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    cfg = KisDbConnection.get_config()
    assert cfg["host"] == "localhost"
    assert cfg["port"] == 5433
    assert cfg["database"] == "kis_template"
    assert cfg["user"] == "robotrader"
    assert cfg["password"] == "1234"


def test_get_config_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("KIS_DB_NAME", "kis_template_test")
    monkeypatch.setenv("KIS_DB_PORT", "6000")
    cfg = KisDbConnection.get_config()
    assert cfg["database"] == "kis_template_test"
    assert cfg["port"] == 6000
