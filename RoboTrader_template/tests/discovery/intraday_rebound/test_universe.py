# tests/discovery/intraday_rebound/test_universe.py
"""유니버스 정의/고정(freeze) 검증. 냉동 경로는 DB 접속 없이 동작해야 한다."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.discovery.intraday_rebound import universe as universe_module
from scripts.discovery.intraday_rebound.universe import (
    _SQL_BOUNDED,
    _SQL_OPEN_ENDED,
    load_frozen_universe,
    load_universe,
)

_PACKAGE_DIR = Path(universe_module.__file__).parent
_SNAPSHOT_PATH = _PACKAGE_DIR / "universe_snapshot.json"


# ---------------------------------------------------------------------------
# load_frozen_universe: DB 미접속 보장
# ---------------------------------------------------------------------------

def test_load_frozen_universe_returns_199_sorted_unique_codes():
    codes = load_frozen_universe()
    assert len(codes) == 199
    assert codes == sorted(codes)
    assert len(set(codes)) == len(codes)


def test_load_frozen_universe_never_touches_db(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("load_frozen_universe must not query the DB")

    monkeypatch.setattr(universe_module, "read_sql", _boom)
    codes = load_frozen_universe()
    assert len(codes) == 199


# ---------------------------------------------------------------------------
# 스냅샷 JSON 자체의 무결성
# ---------------------------------------------------------------------------

def test_snapshot_json_parses_and_is_internally_consistent():
    with open(_SNAPSHOT_PATH, encoding="utf-8") as f:
        snapshot = json.load(f)

    codes = snapshot["codes"]
    assert snapshot["n"] == len(codes)
    assert all(isinstance(c, str) and len(c) == 6 for c in codes)
    assert codes == sorted(codes)
    assert len(set(codes)) == len(codes)


# ---------------------------------------------------------------------------
# load_universe: end_date 지정 시 BETWEEN 으로 상한이 걸린 SQL 사용
# ---------------------------------------------------------------------------

def test_bounded_sql_constant_contains_between_twice():
    assert _SQL_BOUNDED.count("BETWEEN") == 2


def test_open_ended_sql_constant_has_no_upper_bound():
    assert "BETWEEN" not in _SQL_OPEN_ENDED


def test_load_universe_uses_bounded_sql_when_end_date_given(monkeypatch):
    captured = {}

    def _fake_read_sql(sql, params, dbname):
        captured["sql"] = sql
        captured["params"] = params
        captured["dbname"] = dbname
        return pd.DataFrame({"stock_code": ["000001", "000002"]})

    monkeypatch.setattr(universe_module, "read_sql", _fake_read_sql)
    codes = load_universe(dbname="robotrader", start_date="20250401",
                          end_date="20260630", min_coverage=0.9)

    assert captured["sql"].count("BETWEEN") == 2
    assert captured["params"] == ("20250401", "20260630", "20250401", "20260630", 0.9)
    assert codes == ["000001", "000002"]


def test_load_universe_uses_open_ended_sql_when_end_date_none(monkeypatch):
    captured = {}

    def _fake_read_sql(sql, params, dbname):
        captured["sql"] = sql
        captured["params"] = params
        return pd.DataFrame({"stock_code": ["000002", "000001"]})

    monkeypatch.setattr(universe_module, "read_sql", _fake_read_sql)
    codes = load_universe(dbname="robotrader")

    assert "BETWEEN" not in captured["sql"]
    assert captured["params"] == ("20250401", "20250401", 0.9)
    assert codes == ["000001", "000002"]


# ---------------------------------------------------------------------------
# grep 가드: 패키지 내 어떤 모듈도 load_universe() 를 인자 없이 호출하지 않는다
# ---------------------------------------------------------------------------

def test_no_module_calls_load_universe_with_zero_arguments():
    offenders = []
    for path in sorted(_PACKAGE_DIR.glob("*.py")):
        if path.name == "universe.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "load_universe()" in text:
            offenders.append(path.name)
    assert offenders == [], f"load_universe() called with no args in: {offenders}"
