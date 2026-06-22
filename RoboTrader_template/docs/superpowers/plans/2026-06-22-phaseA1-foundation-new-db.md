# Phase A1 — kis_template 전용 DB 기반(연결·스키마·시딩) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 신규 전용 DB `kis_template`를 만들고, 전용 연결 모듈·전체 스키마·레거시 시딩(일봉·corp_events)을 구축한다. 이후 수집기(A2)·운영데이터 이관(Phase B)의 토대가 된다.

**Architecture:** 기존 `db/connection.py`(robotrader)와 동일 패턴의 전용 풀 연결 `KisDbConnection`(env `KIS_DB_*`, default db=`kis_template`)을 추가한다. 스키마는 멱등 DDL 모듈로 생성하고, 레거시(`robotrader_quant.daily_prices`, `robotrader.corp_events`)를 새 DB로 1회 시딩한다. 수집은 항상 새 DB에 적재하고, 읽기 경로 전환은 `KIS_DATA_SOURCE` 플래그가 제어한다(A2/이후).

**Tech Stack:** Python 3.9, psycopg2, PostgreSQL/TimescaleDB(localhost:5433), pytest.

## Global Constraints

- DB 서버: localhost:5433, user `robotrader`, password env(`KIS_DB_PASSWORD`, default `1234`) — 기존 인스턴스와 동일.
- 새 DB명: `kis_template` (env `KIS_DB_NAME` override 가능).
- `daily_prices.date`는 **TEXT**(레거시 동일, `YYYY-MM-DD`). close는 이미 수정주가(adj_factor 곱하지 말 것).
- 모든 DDL·시딩은 **멱등**(IF NOT EXISTS / ON CONFLICT). 재실행 안전.
- 콘솔 한글 출력 시 `PYTHONIOENCODING=utf-8 python -X utf8` (cp949 회피).
- spec: `docs/superpowers/specs/2026-06-22-data-collection-migration-design.md` (Phase A).

---

### Task 1: 전용 연결 모듈 `KisDbConnection`

**Files:**
- Create: `db/kis_db_connection.py`
- Test: `tests/db/test_kis_db_connection.py`

**Interfaces:**
- Produces:
  - `KisDbConnection.get_config() -> dict` — `{host, port, database, user, password}` (env 기반, default db=`kis_template`).
  - `KisDbConnection.get_connection()` — contextmanager, 풀에서 conn yield(반납 보장). `db/connection.py`와 동일 시맨틱.
  - `KisDbConnection.initialize(min_conn=2, max_conn=10)`, `KisDbConnection.close_all()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_kis_db_connection.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/db/test_kis_db_connection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db.kis_db_connection'`

- [ ] **Step 3: Write minimal implementation**

```python
# db/kis_db_connection.py
"""kis_template 전용 DB 연결 풀.

db/connection.py(robotrader)와 동일 패턴이나 별도 DB(kis_template)를 가리킨다.
시장데이터(분봉·일봉·지수·corp_events) + (Phase B 이후) 운영데이터의 단일 소유 DB.
"""
import os
import threading
from contextlib import contextmanager

import psycopg2.extensions
from psycopg2 import pool

from utils.logger import setup_logger

logger = setup_logger(__name__)

# NUMERIC → float (Decimal 반환 방지) — db/connection.py와 동일
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "KIS_DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)


class KisDbConnection:
    """kis_template 전용 TimescaleDB 연결 관리자 (Singleton Pool)."""

    _pool = None
    _init_lock = threading.Lock()

    @classmethod
    def get_config(cls) -> dict:
        return {
            "host": os.getenv("KIS_DB_HOST", "localhost"),
            "port": int(os.getenv("KIS_DB_PORT", 5433)),
            "database": os.getenv("KIS_DB_NAME", "kis_template"),
            "user": os.getenv("KIS_DB_USER", "robotrader"),
            "password": os.getenv("KIS_DB_PASSWORD", "1234"),
        }

    @classmethod
    def initialize(cls, min_conn=2, max_conn=10):
        with cls._init_lock:
            if cls._pool is not None:
                return
            cfg = cls.get_config()
            cls._pool = pool.ThreadedConnectionPool(min_conn, max_conn, **cfg)
            logger.info(f"kis_template DB 연결 풀 초기화: {cfg['host']}:{cfg['port']}/{cfg['database']}")

    @classmethod
    @contextmanager
    def get_connection(cls):
        if cls._pool is None:
            cls.initialize()
        conn = cls._pool.getconn()
        try:
            if conn.closed:
                cls._pool.putconn(conn, close=True)
                conn = cls._pool.getconn()
            yield conn
        finally:
            cls._pool.putconn(conn)

    @classmethod
    def close_all(cls):
        with cls._init_lock:
            if cls._pool is not None:
                cls._pool.closeall()
                cls._pool = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/db/test_kis_db_connection.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add db/kis_db_connection.py tests/db/test_kis_db_connection.py
git commit -m "feat(kis-db): kis_template 전용 DB 연결 모듈 KisDbConnection"
```

---

### Task 2: 데이터베이스 생성 스크립트 (`kis_template` DB)

**Files:**
- Create: `scripts/kis_db/__init__.py` (빈 파일)
- Create: `scripts/kis_db/create_database.py`
- Test: `tests/kis_db/test_create_database.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_config()` (Task 1)
- Produces:
  - `database_exists(conn, dbname: str) -> bool`
  - `create_database_if_absent() -> bool` (생성 시 True, 이미 있으면 False; `postgres` DB에 autocommit 연결해 `CREATE DATABASE` 실행)

설명: `CREATE DATABASE`는 트랜잭션/대상DB 내부에서 불가하므로, 관리DB(`postgres`)에 **autocommit** 연결해 실행한다.

- [ ] **Step 1: Write the failing test**

```python
# tests/kis_db/test_create_database.py
from scripts.kis_db.create_database import database_exists


class _FakeCur:
    def __init__(self, exists): self._exists = exists; self.executed = None
    def execute(self, sql, params=None): self.executed = (sql, params)
    def fetchone(self): return (1,) if self._exists else None
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _FakeConn:
    def __init__(self, exists): self._exists = exists
    def cursor(self): return _FakeCur(self._exists)


def test_database_exists_true_when_row_returned():
    assert database_exists(_FakeConn(True), "kis_template") is True


def test_database_exists_false_when_no_row():
    assert database_exists(_FakeConn(False), "kis_template") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/kis_db/test_create_database.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/kis_db/create_database.py
"""kis_template DB 생성(멱등). postgres 관리DB에 autocommit 연결해 CREATE DATABASE.

usage: python -m scripts.kis_db.create_database
"""
import os
import sys

import psycopg2
from psycopg2 import sql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402


def database_exists(conn, dbname: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        return cur.fetchone() is not None


def create_database_if_absent() -> bool:
    cfg = KisDbConnection.get_config()
    dbname = cfg["database"]
    admin = dict(cfg, database="postgres")
    conn = psycopg2.connect(**admin)
    try:
        conn.autocommit = True
        if database_exists(conn, dbname):
            print(f"DB 이미 존재: {dbname}")
            return False
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        print(f"DB 생성 완료: {dbname}")
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    create_database_if_absent()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/kis_db/test_create_database.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 실제 DB 생성(통합 실행·검증)**

Run: `python -m scripts.kis_db.create_database`
Expected: `DB 생성 완료: kis_template` (재실행 시 `DB 이미 존재: kis_template`)

검증:
Run: `python -c "from db.kis_db_connection import KisDbConnection; c=KisDbConnection.get_connection().__enter__(); print('connected', c.closed)"`
Expected: `connected 0` (연결 성공)

- [ ] **Step 6: Commit**

```bash
git add scripts/kis_db/__init__.py scripts/kis_db/create_database.py tests/kis_db/test_create_database.py
git commit -m "feat(kis-db): kis_template DB 생성 스크립트(멱등)"
```

---

### Task 3: 스키마 생성 (시장데이터·corp_events·reconciliation 테이블)

**Files:**
- Create: `scripts/kis_db/schema.py`
- Test: `tests/kis_db/test_schema.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_connection()` (Task 1), `kis_template` DB 존재(Task 2)
- Produces:
  - `DDL_STATEMENTS: list[str]` — 멱등 CREATE TABLE 문 목록.
  - `EXPECTED_TABLES: set[str]` — `{minute_candles, daily_prices, index_daily, corp_events, collection_reconciliation}`.
  - `create_all(conn) -> None` — 모든 DDL 실행 + commit.

DDL은 레거시 스키마와 동일 컬럼/PK를 따른다(드롭인). `index_daily`·`collection_reconciliation`은 신규.

- [ ] **Step 1: Write the failing test**

```python
# tests/kis_db/test_schema.py
from scripts.kis_db.schema import DDL_STATEMENTS, EXPECTED_TABLES


def test_expected_tables_present():
    assert EXPECTED_TABLES == {
        "minute_candles", "daily_prices", "index_daily",
        "corp_events", "collection_reconciliation",
    }


def test_every_expected_table_has_ddl():
    joined = "\n".join(DDL_STATEMENTS).lower()
    for t in EXPECTED_TABLES:
        assert f"create table if not exists {t}" in joined, f"DDL 누락: {t}"


def test_daily_prices_date_is_text_not_date():
    # 레거시 동일: date 는 TEXT(YYYY-MM-DD)
    dp = [s for s in DDL_STATEMENTS if "daily_prices" in s.lower()][0].lower()
    assert "date text" in dp


def test_minute_candles_pk_matches_legacy():
    mc = [s for s in DDL_STATEMENTS if "minute_candles" in s.lower()][0].lower()
    assert "primary key (stock_code, trade_date, idx)" in mc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/kis_db/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/kis_db/schema.py
"""kis_template DB 스키마(멱등). 레거시 스키마와 동일 컬럼/PK(드롭인) + 신규 2테이블.

usage: python -m scripts.kis_db.schema
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402

EXPECTED_TABLES = {
    "minute_candles", "daily_prices", "index_daily",
    "corp_events", "collection_reconciliation",
}

DDL_STATEMENTS = [
    # 분봉 (robotrader.minute_candles 동일)
    """
    CREATE TABLE IF NOT EXISTS minute_candles (
        stock_code VARCHAR NOT NULL,
        trade_date VARCHAR NOT NULL,
        idx INTEGER NOT NULL,
        date VARCHAR,
        time VARCHAR,
        close DOUBLE PRECISION,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        volume DOUBLE PRECISION,
        amount DOUBLE PRECISION,
        datetime TIMESTAMP,
        PRIMARY KEY (stock_code, trade_date, idx)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_minute_candles_code_date ON minute_candles(stock_code, trade_date)",
    # 일봉 (robotrader_quant.daily_prices 동일 — date 는 TEXT)
    """
    CREATE TABLE IF NOT EXISTS daily_prices (
        stock_code VARCHAR NOT NULL,
        date TEXT NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        volume BIGINT,
        trading_value BIGINT,
        market_cap DOUBLE PRECISION,
        returns_1d DOUBLE PRECISION,
        returns_5d DOUBLE PRECISION,
        returns_20d DOUBLE PRECISION,
        volatility_20d DOUBLE PRECISION,
        adj_factor DOUBLE PRECISION,
        created_at TIMESTAMP DEFAULT now(),
        updated_at TIMESTAMP DEFAULT now(),
        PRIMARY KEY (stock_code, date)
    )
    """,
    # 지수 일봉 (신규 — KOSPI/KOSDAQ)
    """
    CREATE TABLE IF NOT EXISTS index_daily (
        index_code VARCHAR NOT NULL,
        date TEXT NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        volume DOUBLE PRECISION,
        created_at TIMESTAMP DEFAULT now(),
        PRIMARY KEY (index_code, date)
    )
    """,
    # corp_events (robotrader.corp_events 동일)
    """
    CREATE TABLE IF NOT EXISTS corp_events (
        stock_code TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_date DATE NOT NULL,
        end_date DATE,
        meta JSONB,
        PRIMARY KEY (stock_code, event_type, event_date)
    )
    """,
    # 교차 DB 비교 결과 (신규)
    """
    CREATE TABLE IF NOT EXISTS collection_reconciliation (
        trade_date TEXT NOT NULL,
        dataset VARCHAR NOT NULL,
        real_rows INTEGER,
        new_rows INTEGER,
        overlap INTEGER,
        value_match_rate DOUBLE PRECISION,
        coverage DOUBLE PRECISION,
        verdict VARCHAR,
        created_at TIMESTAMP DEFAULT now(),
        PRIMARY KEY (trade_date, dataset)
    )
    """,
]


def create_all(conn) -> None:
    with conn.cursor() as cur:
        for ddl in DDL_STATEMENTS:
            cur.execute(ddl)
    conn.commit()


if __name__ == "__main__":
    with KisDbConnection.get_connection() as conn:
        create_all(conn)
    print(f"스키마 생성 완료: {sorted(EXPECTED_TABLES)}")
```

- [ ] **Step 4: Run unit test to verify it passes**

Run: `python -m pytest tests/kis_db/test_schema.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 실제 스키마 생성(통합 실행·검증)**

Run: `python -m scripts.kis_db.schema`
Expected: `스키마 생성 완료: ['collection_reconciliation', 'corp_events', 'daily_prices', 'index_daily', 'minute_candles']`

검증(테이블 존재):
```bash
PYTHONIOENCODING=utf-8 python -X utf8 -c "from db.kis_db_connection import KisDbConnection; \
import scripts.kis_db.schema as s; \
c=KisDbConnection.get_connection().__enter__(); cur=c.cursor(); \
cur.execute(\"select table_name from information_schema.tables where table_schema='public'\"); \
got={r[0] for r in cur.fetchall()}; print('missing:', s.EXPECTED_TABLES - got)"
```
Expected: `missing: set()`

- [ ] **Step 6: Commit**

```bash
git add scripts/kis_db/schema.py tests/kis_db/test_schema.py
git commit -m "feat(kis-db): kis_template 스키마(분봉·일봉·지수·corp_events·reconciliation)"
```

---

### Task 4: 레거시 시딩 (일봉·corp_events 복사)

**Files:**
- Create: `scripts/kis_db/seed_from_legacy.py`
- Test: `tests/kis_db/test_seed_from_legacy.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_connection()` (신규 DB, 쓰기), `db/connection.py DatabaseConnection`(robotrader, corp_events 읽기), `db/quant_daily_reader` 연결 패턴(robotrader_quant, daily_prices 읽기). 스키마 존재(Task 3).
- Produces:
  - `build_daily_insert_rows(legacy_rows: list[tuple]) -> list[tuple]` — 순수 변환(컬럼 순서 매핑). 테스트 대상.
  - `seed_daily_prices() -> dict` (`{copied, source_rows}`), `seed_corp_events() -> dict`.

설계: 대용량(일봉 ~277만 행)이라 서버사이드 커서로 배치(예: 5,000행) 읽어 `execute_values`로 새 DB에 UPSERT. 멱등(ON CONFLICT DO UPDATE).

- [ ] **Step 1: Write the failing test (순수 변환)**

```python
# tests/kis_db/test_seed_from_legacy.py
from scripts.kis_db.seed_from_legacy import build_daily_insert_rows, DAILY_COLUMNS


def test_daily_columns_order_matches_schema():
    assert DAILY_COLUMNS == [
        "stock_code", "date", "open", "high", "low", "close",
        "volume", "trading_value", "market_cap",
        "returns_1d", "returns_5d", "returns_20d", "volatility_20d", "adj_factor",
    ]


def test_build_daily_insert_rows_passthrough_tuples():
    src = [("005930", "2026-06-22", 70000.0, 71000.0, 69000.0, 70500.0,
            1000, 70_000_000, 4.2e14, 0.01, 0.02, 0.03, 0.15, 1.0)]
    out = build_daily_insert_rows(src)
    assert out == src
    assert len(out[0]) == len(DAILY_COLUMNS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/kis_db/test_seed_from_legacy.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/kis_db/seed_from_legacy.py
"""레거시 → kis_template 시딩(멱등). 일봉(robotrader_quant)·corp_events(robotrader) 1회 복사.

usage: python -m scripts.kis_db.seed_from_legacy            # dry-run(소스 행수만)
       python -m scripts.kis_db.seed_from_legacy --apply    # 실제 복사
"""
import argparse
import os
import sys

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402

DAILY_COLUMNS = [
    "stock_code", "date", "open", "high", "low", "close",
    "volume", "trading_value", "market_cap",
    "returns_1d", "returns_5d", "returns_20d", "volatility_20d", "adj_factor",
]
CORP_COLUMNS = ["stock_code", "event_type", "event_date", "end_date", "meta"]
BATCH = 5000


def _legacy_conn(dbname: str):
    return psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"),
        port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname=dbname,
        user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "1234"),
    )


def build_daily_insert_rows(legacy_rows):
    """레거시 daily_prices 행(DAILY_COLUMNS 순서 SELECT 결과)을 그대로 반환(컬럼 동일)."""
    return list(legacy_rows)


def _copy(src_dbname, select_sql, table, columns, apply: bool) -> dict:
    src = _legacy_conn(src_dbname)
    copied = 0
    source_rows = 0
    cols_csv = ", ".join(columns)
    # PK 충돌 시 스킵(멱등). 시딩은 1회성이라 DO NOTHING으로 충분.
    upsert = f"INSERT INTO {table} ({cols_csv}) VALUES %s ON CONFLICT DO NOTHING"
    try:
        with src.cursor(name=f"seed_{table}") as scur:  # 서버사이드 커서(스트리밍)
            scur.itersize = BATCH
            scur.execute(select_sql)
            with KisDbConnection.get_connection() as dst:
                while True:
                    rows = scur.fetchmany(BATCH)
                    if not rows:
                        break
                    source_rows += len(rows)
                    if apply:
                        with dst.cursor() as dcur:
                            execute_values(dcur, upsert, build_daily_insert_rows(rows))
                        dst.commit()
                        copied += len(rows)
    finally:
        src.close()
    return {"copied": copied, "source_rows": source_rows}


def seed_daily_prices(apply: bool = False) -> dict:
    sel = f"SELECT {', '.join(DAILY_COLUMNS)} FROM daily_prices"
    return _copy("robotrader_quant", sel, "daily_prices", DAILY_COLUMNS, apply)


def seed_corp_events(apply: bool = False) -> dict:
    sel = f"SELECT {', '.join(CORP_COLUMNS)} FROM corp_events"
    return _copy("robotrader", sel, "corp_events", CORP_COLUMNS, apply)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    d = seed_daily_prices(args.apply)
    e = seed_corp_events(args.apply)
    print(f"daily_prices: {d}")
    print(f"corp_events:  {e}")
```

> 주의: `ON CONFLICT DO NOTHING`은 PK(daily_prices `(stock_code,date)`, corp_events `(stock_code,event_type,event_date)`) 기준 멱등. 시딩은 1회성이라 DO NOTHING으로 충분(증분은 이후 수집기가 UPSERT).

- [ ] **Step 4: Run unit test to verify it passes**

Run: `python -m pytest tests/kis_db/test_seed_from_legacy.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: dry-run(소스 행수 확인)**

Run: `PYTHONIOENCODING=utf-8 python -X utf8 -m scripts.kis_db.seed_from_legacy`
Expected: `daily_prices: {'copied': 0, 'source_rows': 2774917}` (대략 ~277만), `corp_events: {'copied': 0, 'source_rows': N}`

- [ ] **Step 6: 실제 시딩 + 행수 정합성 검증**

Run: `PYTHONIOENCODING=utf-8 python -X utf8 -m scripts.kis_db.seed_from_legacy --apply`
Expected: `copied == source_rows` (양 테이블)

검증(새 DB vs 레거시 행수 일치):
```bash
PYTHONIOENCODING=utf-8 python -X utf8 -c "
import psycopg2
def n(db,t):
    c=psycopg2.connect(host='localhost',port=5433,dbname=db,user='robotrader',password='1234');cur=c.cursor()
    cur.execute('select count(*) from '+t); v=cur.fetchone()[0]; c.close(); return v
print('daily_prices  legacy', n('robotrader_quant','daily_prices'), 'new', n('kis_template','daily_prices'))
print('corp_events   legacy', n('robotrader','corp_events'), 'new', n('kis_template','corp_events'))
"
```
Expected: legacy == new (양쪽 일치)

- [ ] **Step 7: Commit**

```bash
git add scripts/kis_db/seed_from_legacy.py tests/kis_db/test_seed_from_legacy.py
git commit -m "feat(kis-db): 레거시 일봉·corp_events 시딩 스크립트(멱등)"
```

---

## Self-Review (작성자 체크)

- **Spec 커버리지(Phase A 기반 부분)**: 새 DB 생성(Task 2)·연결(Task 1)·스키마 전부(Task 3, 시장데이터+corp_events+reconciliation)·일봉/corp_events 시딩(Task 4) — spec §2 타깃 테이블 중 시장데이터·corp_events 토대 완료. 운영테이블(virtual_trading_records 등)은 Phase B 범위라 본 계획 제외(정상). index_daily 시딩은 불요(FDR 백필, A2 수집기 담당).
- **수집기·교차비교·EOD 훅·읽기경로 전환**은 후속 계획 `2026-06-22-phaseA2-collectors.md`로 분리(연결 API가 본 계획에서 확정된 뒤 정확한 코드 작성 가능).
- **Placeholder 스캔**: 모든 스텝에 실제 코드·명령·기대출력 포함. TODO/TBD 없음.
- **타입 일관성**: `KisDbConnection.get_connection/get_config`(Task1) → Task2/3/4에서 동일 사용. `DAILY_COLUMNS`(Task4) 순서 = Task3 daily_prices DDL 컬럼 순서와 일치. `EXPECTED_TABLES`(Task3) = 테스트 기대값 일치.

## 다음 계획 (별도 문서)
- `phaseA2-collectors`: daily_collector / minute_collector / index_collector + reconciliation + EOD 훅(`_run_data_collection`) + `KIS_DATA_SOURCE` 읽기경로 전환. 본 A1의 `KisDbConnection`·스키마를 소비.
- `phaseB-operational-migration`: 운영테이블 복사·쓰기전환.
- `phaseC-retire`: rt/rt_quant 런처 제거·레거시 삭제.
