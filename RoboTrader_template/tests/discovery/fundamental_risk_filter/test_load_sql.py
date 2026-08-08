import os
import re
import sys

import pytest

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


def test_expected_columns_match_ddl_columns():
    """🔴 FIX4 — EXPECTED_COLUMNS 가 DDL 에 실제 정의된 컬럼명과 정확히 같아야 한다.

    다르면 `verify_table_columns()`가 「우리 테이블이 아니다」를 오판(거짓 양성)하거나
    남의 테이블을 우리 것으로 오인(거짓 음성)한다.
    """
    m = re.search(r"CREATE TABLE IF NOT EXISTS \S+\s*\((.*?)\n\);", f4.DDL, re.DOTALL)
    assert m is not None
    cols = set()
    for line in m.group(1).splitlines():
        line = line.split("--", 1)[0].strip()
        if not line:
            continue
        if line.upper().startswith(("PRIMARY KEY", "CONSTRAINT", "UNIQUE")):
            continue
        col = line.split()[0].rstrip(",")
        cols.add(col)
    assert cols == f4.EXPECTED_COLUMNS


def test_field_order_columns_are_subset_of_expected_columns():
    """FIELD_ORDER(적재 대상)는 EXPECTED_COLUMNS(테이블 전체 컬럼)의 부분집합이어야 한다.

    차이는 정확히 `created_at`(DEFAULT now(), INSERT 대상이 아님) 하나여야 한다.
    """
    assert set(f4.FIELD_ORDER) <= f4.EXPECTED_COLUMNS
    assert f4.EXPECTED_COLUMNS - set(f4.FIELD_ORDER) == {"created_at"}


def test_insert_column_order_matches_read_rows_field_order():
    """🔴 FIX5 — 7개 숫자 컬럼이 전부 BIGINT라 두 개가 바뀌어도 타입 오류 없이

    조용히 틀린 값이 들어간다. INSERT 컬럼 순서가 `read_rows()`가 만드는 튜플
    순서(FIELD_ORDER)와 정확히 같아야 한다. `test_every_inserted_column_is_refreshed_on_conflict`
    (INSERT↔SET 짝짓기)와는 다른 변이(컬럼 «순서» 전치)를 잡는다.
    """
    m = re.search(r"INSERT\s+INTO\s+\S+\s*\(([^)]*)\)", f4.UPSERT, re.IGNORECASE | re.DOTALL)
    assert m is not None
    cols = [c.strip() for c in m.group(1).split(",")]
    assert cols == list(f4.FIELD_ORDER)


def test_verify_table_columns_exits_6_on_mismatch():
    """🔴 FIX4 — 컬럼 집합이 다르면(남의 테이블일 수 있다) exit(6)으로 중단해야 한다."""
    class _FakeCur:
        def execute(self, sql, params=None):
            pass

        def fetchall(self):
            return [("stock_code",), ("bsns_year",)]  # 기대보다 훨씬 적다 — 남의 테이블 흉내

    with pytest.raises(SystemExit) as exc:
        f4.verify_table_columns(_FakeCur())
    assert exc.value.code == 6


def test_verify_table_columns_passes_on_exact_match():
    """컬럼 집합이 정확히 같으면 예외·exit 없이 조용히 통과해야 한다."""
    class _FakeCur:
        def execute(self, sql, params=None):
            pass

        def fetchall(self):
            return [(c,) for c in f4.EXPECTED_COLUMNS]

    f4.verify_table_columns(_FakeCur())  # 예외를 내면 실패


def test_load_runs_under_repeatable_read():
    """🔴 FIX7 — READ COMMITTED 에서는 동시 커밋(EOD 수집기·라이브 봇)이 전/후

    지문을 갈라놓아 「내가 바꿨다」와 「누가 바꿨다」가 섞인다. REPEATABLE READ
    로 트랜잭션 시작 시점 스냅샷을 고정해야 한다.
    """
    assert "REPEATABLE READ" in _SRC
