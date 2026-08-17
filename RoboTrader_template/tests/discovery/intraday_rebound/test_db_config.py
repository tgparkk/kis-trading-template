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


def test_db_names_ignore_retired_legacy_switch(monkeypatch):
    """[계약 반전] 폐지된 KIS_DATA_SOURCE=legacy 를 넣어도 kis_template 이다.

    이력:
      2026-07-16 — 이 모듈만의 REBOUND_MINUTE_DB/REBOUND_DAILY_DB 를 공용
        resolver(KIS_DATA_SOURCE) 하나로 수렴시켰다.
      2026-08-17 — 그 공용 스위치마저 폐지됐다(레거시 동결 + `robotrader` DB 삭제).
        이전 계약은 `MINUTE_DB == "robotrader"` 를 단언했다 — 이제 정반대를 고정한다.
    """
    monkeypatch.setenv("KIS_DATA_SOURCE", "legacy")
    importlib.reload(db_module)
    try:
        assert db_module.MINUTE_DB == "kis_template"
        assert db_module.DAILY_DB == "kis_template"
    finally:
        # reset explicitly (not just via monkeypatch teardown) so the reload
        # happens *after* the env var is gone, leaving the module back at
        # its default state for any test that runs after this one.
        monkeypatch.delenv("KIS_DATA_SOURCE", raising=False)
        importlib.reload(db_module)


def test_no_legacy_rebound_specific_env(monkeypatch):
    """폐지된 자체 env 는 더 이상 소스를 바꾸지 못한다(중복 스위치 제거 확인)."""
    monkeypatch.setenv("REBOUND_MINUTE_DB", "robotrader")
    monkeypatch.setenv("MINUTE_DB", "robotrader")  # 2026-08-17 폐지된 공용 override
    importlib.reload(db_module)
    try:
        assert db_module.MINUTE_DB == "kis_template", (
            "REBOUND_MINUTE_DB · MINUTE_DB 는 둘 다 폐지됨 — 소스는 kis_template 고정"
        )
    finally:
        monkeypatch.delenv("REBOUND_MINUTE_DB", raising=False)
        monkeypatch.delenv("MINUTE_DB", raising=False)
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
