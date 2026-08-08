import os
import re
import sys

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import f4_load as f4  # noqa: E402

_SRC = open(os.path.join(_SCRIPTS, "f4_load.py"), encoding="utf-8").read()


def test_no_write_statement_targets_existing_tables():
    """🔴 UPDATE/DELETE/DROP/TRUNCATE 가 기존 테이블을 향하면 안 된다."""
    for verb in ("UPDATE ", "DELETE ", "DROP TABLE", "TRUNCATE", "ALTER TABLE"):
        for m in re.finditer(verb, _SRC, re.IGNORECASE):
            tail = _SRC[m.end(): m.end() + 60]
            assert "daily_prices" not in tail
            assert "minute_candles" not in tail
            assert "virtual_trading_records" not in tail


def test_ddl_creates_only_the_new_table():
    assert "dart_financials_asfiled" in f4.DDL
    assert "daily_prices" not in f4.DDL


def test_ddl_has_no_retention_policy_or_hypertable():
    """🔴 프로젝트 영구 규칙 — 자동삭제 금지, hypertable 금지."""
    low = f4.DDL.lower()
    assert "retention" not in low
    assert "create_hypertable" not in low


def test_upsert_is_idempotent():
    assert "ON CONFLICT" in f4.UPSERT.upper()


def test_primary_key_is_stock_and_year():
    assert re.search(r"PRIMARY\s+KEY\s*\(\s*stock_code\s*,\s*bsns_year\s*\)",
                     f4.DDL, re.IGNORECASE)


def test_rcept_dt_column_exists_and_is_nullable():
    """접수일이 없는 행(013)도 남겨야 하므로 NOT NULL 이면 안 된다."""
    m = re.search(r"rcept_dt\s+\w+([^,]*),", f4.DDL, re.IGNORECASE)
    assert m is not None
    assert "NOT NULL" not in m.group(1).upper()
