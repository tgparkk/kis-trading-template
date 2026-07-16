# tests/discovery/intraday_rebound/test_db_config.py
"""db.py 모듈설정 검증. DB 접속 없이 순수 import/env 동작만 확인한다."""
from __future__ import annotations

import importlib
from pathlib import Path

from scripts.discovery.intraday_rebound import db as db_module

_PACKAGE_DIR = Path(db_module.__file__).parent


def test_minute_db_defaults_to_kis_template():
    assert db_module.MINUTE_DB == "kis_template"


def test_daily_db_defaults_to_kis_template():
    assert db_module.DAILY_DB == "kis_template"


def test_db_names_come_from_shared_resolver(monkeypatch):
    """롤백 스위치가 공용 resolver(KIS_DATA_SOURCE) 하나로 수렴했는지 확인.

    2026-07-16 이전엔 이 모듈만의 REBOUND_MINUTE_DB/REBOUND_DAILY_DB 로
    kis_template 을 개별 지정했다. 소스 스위치가 여러 env 로 갈라져 있으면
    일부 경로만 레거시로 새는 사고가 나므로 공용 resolver 로 통일했다.
    """
    monkeypatch.setenv("KIS_DATA_SOURCE", "legacy")
    importlib.reload(db_module)
    try:
        assert db_module.MINUTE_DB == "robotrader"
        assert db_module.DAILY_DB == "robotrader_quant"
    finally:
        # reset explicitly (not just via monkeypatch teardown) so the reload
        # happens *after* the env var is gone, leaving the module back at
        # its default state for any test that runs after this one.
        monkeypatch.delenv("KIS_DATA_SOURCE", raising=False)
        importlib.reload(db_module)


def test_no_legacy_rebound_specific_env(monkeypatch):
    """폐지된 자체 env 는 더 이상 소스를 바꾸지 못한다(중복 스위치 제거 확인)."""
    monkeypatch.setenv("REBOUND_MINUTE_DB", "robotrader")
    importlib.reload(db_module)
    try:
        assert db_module.MINUTE_DB == "kis_template", (
            "REBOUND_MINUTE_DB 는 폐지됨 — KIS_DATA_SOURCE 로만 전환돼야 함"
        )
    finally:
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
