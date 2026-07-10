# tests/discovery/intraday_rebound/test_db_config.py
"""db.py 모듈설정 검증. DB 접속 없이 순수 import/env 동작만 확인한다."""
from __future__ import annotations

import importlib
from pathlib import Path

from scripts.discovery.intraday_rebound import db as db_module

_PACKAGE_DIR = Path(db_module.__file__).parent


def test_minute_db_defaults_to_kis_template():
    assert db_module.MINUTE_DB == "kis_template"


def test_minute_db_env_override_reload(monkeypatch):
    monkeypatch.setenv("REBOUND_MINUTE_DB", "robotrader")
    importlib.reload(db_module)
    try:
        assert db_module.MINUTE_DB == "robotrader"
    finally:
        # reset explicitly (not just via monkeypatch teardown) so the reload
        # happens *after* the env var is gone, leaving the module back at
        # its default state for any test that runs after this one.
        monkeypatch.delenv("REBOUND_MINUTE_DB", raising=False)
        importlib.reload(db_module)


def test_no_hardcoded_robotrader_literal_outside_db_py():
    offenders = []
    for path in sorted(_PACKAGE_DIR.glob("*.py")):
        if path.name == "db.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "'robotrader'" in text or '"robotrader"' in text:
            offenders.append(path.name)
    assert offenders == [], f"hardcoded robotrader literal found in: {offenders}"
