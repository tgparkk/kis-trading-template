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
    """🔴 UPDATE/DELETE/DROP/TRUNCATE/INSERT 가 기존 테이블을 향하면 안 된다.

    값싼 트립와이어다 — 보증이 아니다. 줄바꿈을 우회하는 것 같은 패턴을 수기로 찾아야 한다.
    """
    for verb in (r"UPDATE", r"DELETE", r"DROP\s+TABLE", r"TRUNCATE", r"ALTER\s+TABLE", r"INSERT"):
        for m in re.finditer(rf"{verb}\s+", _SRC, re.IGNORECASE):
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


def test_every_inserted_column_is_refreshed_on_conflict():
    """🔴 INSERT 에 있는데 SET 에 없는 컬럼은 재적재 때 옛 값이 남는다."""
    m = re.search(r"INSERT\s+INTO\s+\S+\s*\(([^)]*)\)", f4.UPSERT, re.IGNORECASE | re.DOTALL)
    assert m is not None
    cols = [c.strip() for c in m.group(1).split(",")]
    key = {"stock_code", "bsns_year"}
    set_part = f4.UPSERT.split("DO UPDATE SET", 1)[1]
    missing = [c for c in cols
               if c not in key
               and not re.search(rf"\b{c}\s*=\s*EXCLUDED\.{c}\b", set_part, re.IGNORECASE)]
    assert missing == [], f"SET 에서 빠진 컬럼: {missing}"


def test_fingerprint_covers_whole_row_not_a_column_subset():
    """🔴 컬럼을 골라 해싱하면 고르지 않은 컬럼의 변경을 못 잡는다."""
    assert "d::text" in f4.DP_FINGERPRINT
    for col in ("close", "market_cap", "adj_factor", "volume"):
        assert f"{col}::text" not in f4.DP_FINGERPRINT
