# DB Consolidation — Phase A + Phase B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `kis_template` schema parity for the bot's operational tables and provide idempotent, verifiable migration + equivalence tooling so the paper bot can later flip to a single DB without losing open-position / cash-ledger continuity.

**Architecture:** Phase A extends the existing `scripts/kis_db/schema.py` idempotent DDL registry with the six operational tables (verbatim columns/indexes/constraints from `init-scripts/01-init.sql` + `05-vtr-source-column.sql`, plus the promoted `paper_strategy_equity` DDL). Phase B adds three new operational scripts under `scripts/kis_db/`: a re-runnable data-migration copier (`robotrader` → `kis_template`, our rows only), an offline market-data equivalence report (explainable-diff gate), and a StateRestorer smoke that proves restored positions/cash/candidates match the `robotrader` baseline. All logic that can be unit-tested is factored into pure functions tested with fake cursors/fixtures; DB-touching entry points read production DBs read-only and write only to `kis_template`.

**Tech Stack:** Python 3.9, `psycopg2` (+ `psycopg2.extras.execute_values`), pytest. TimescaleDB/PostgreSQL 16 on port 5433. Existing helpers: `db.kis_db_connection.KisDbConnection` (writes to `kis_template`), `db.connection.DatabaseConnection` (default pool, `TIMESCALE_DB`).

## Global Constraints

- **Worktree only.** All dev/test/smoke run in `D:/GIT/kis-consolidate` (branch `feat/db-consolidate-kis-template`), code under `RoboTrader_template/`. NEVER run tests or smoke against the live tree `D:/GIT/kis-trading-template` (memory rule: no test/smoke in live tree; no intraday branch switch).
- **kis_template is the only write target.** Migration/report/smoke scripts may READ `robotrader` and `robotrader_quant` but MUST NOT write to them. Writes go only to `kis_template` via `KisDbConnection`.
- **No DELETE, no retention policy.** All copies are additive UPSERT / `ON CONFLICT DO NOTHING`. Never add a TimescaleDB retention policy or drop/truncate any table.
- **Do not modify research trees.** `scripts/` is touched ONLY to add the new `scripts/kis_db/` operational modules. Do NOT touch `multiverse/`, `books/`, `council/`, `archive/`, `backtest/`. `tools/paper_strategy_equity.py` is operational and may be edited (Task 2) to remove DDL drift.
- **Our rows only (sibling-bot isolation).** `virtual_trading_records` copies `WHERE source = 'kis_template'` only. `robotrader` sibling rows (`source='robotrader'`, e.g. `macd_cross_alt`) are never copied.
- **Preserve PKs + bump sequences.** Copy explicit `id` values for SERIAL tables and `setval` the sequence after copy so the bot's next insert cannot collide. `buy_record_id` self-FK integrity is preserved by inserting in ascending `id` order.
- **TDD, bite-sized, frequent commits.** Failing test first; each task ends with an independently testable deliverable + a commit. No placeholders, no `test.skip`, no stubbed branches.
- **Tests must not mutate production DBs.** Unit tests use fake cursors / injected fixtures or a disposable test schema. Only the CLI entry points touch real DBs, and only `kis_template` is written.
- **Source-of-truth for operational DDL** = `init-scripts/01-init.sql` + `init-scripts/05-vtr-source-column.sql`. Copy columns/types/indexes verbatim (SERIAL, `NUMERIC(15,2)`, `TIMESTAMPTZ`, self-FK, partial unique sell index). Do not "improve" types.

---

## File Structure

**Modified:**
- `RoboTrader_template/scripts/kis_db/schema.py` — add operational tables to `EXPECTED_TABLES` and `DDL_STATEMENTS`; expose `PAPER_STRATEGY_EQUITY_DDL` constant. Single source of truth for all `kis_template` DDL.
- `RoboTrader_template/tests/kis_db/test_schema.py` — update `EXPECTED_TABLES` equality assertion; add operational-DDL parity assertions.
- `RoboTrader_template/tools/paper_strategy_equity.py` — `_ensure_table` reuses the schema constant (kill DDL drift).

**Created:**
- `RoboTrader_template/scripts/kis_db/migrate_operational_data.py` — B1 idempotent copier (`robotrader` → `kis_template`, our rows only).
- `RoboTrader_template/scripts/kis_db/report_equivalence.py` — B2 offline explainable-diff report (daily vs `robotrader_quant`, minute vs `robotrader`).
- `RoboTrader_template/scripts/kis_db/smoke_state_restore.py` — B3 StateRestorer smoke + pure summary/compare helpers.
- `RoboTrader_template/tests/kis_db/test_migrate_operational_data.py` — B1 unit tests.
- `RoboTrader_template/tests/kis_db/test_report_equivalence.py` — B2 unit tests.
- `RoboTrader_template/tests/kis_db/test_smoke_state_restore.py` — B3 unit tests.

Each new module follows the established `scripts/kis_db/` pattern (module-level `sys.path.insert`, pure helpers + a `__main__` CLI, `KisDbConnection` for writes, raw `psycopg2.connect` for legacy reads) so it reads like `seed_from_legacy.py`.

---

### Task 1: Phase A — operational table DDL parity in `schema.py`

Add the five init-scripts operational tables to the `kis_template` schema registry, verbatim from source DDL, plus the `source` column/index from migration 05. (`paper_strategy_equity` is added in Task 2.)

**Files:**
- Modify: `RoboTrader_template/scripts/kis_db/schema.py` (`EXPECTED_TABLES` at lines 12-15; `DDL_STATEMENTS` list ends line 111)
- Test: `RoboTrader_template/tests/kis_db/test_schema.py`

**Interfaces:**
- Consumes: existing `EXPECTED_TABLES: set[str]`, `DDL_STATEMENTS: list[str]`, `create_all(conn)`.
- Produces: `EXPECTED_TABLES` now also contains `{"virtual_trading_records", "real_trading_records", "paper_trading_state", "candidate_stocks", "screener_snapshots"}`; `DDL_STATEMENTS` gains matching `CREATE TABLE IF NOT EXISTS` + index statements. (`paper_strategy_equity` added Task 2.)

- [ ] **Step 1: Update the failing table-set test**

Edit `tests/kis_db/test_schema.py::test_expected_tables_present` to the new set (this test now fails against the un-extended module):

```python
def test_expected_tables_present():
    assert EXPECTED_TABLES == {
        "minute_candles", "daily_prices", "index_daily",
        "corp_events", "collection_reconciliation", "foreign_flow",
        "virtual_trading_records", "real_trading_records",
        "paper_trading_state", "paper_strategy_equity",
        "candidate_stocks", "screener_snapshots",
    }
```

- [ ] **Step 2: Add operational-DDL parity assertions**

Append to `tests/kis_db/test_schema.py`:

```python
def test_virtual_trading_records_has_source_and_tpsl_columns():
    vtr = [s for s in DDL_STATEMENTS
           if "create table if not exists virtual_trading_records" in s.lower()][0].lower()
    assert "source varchar(50)" in vtr
    assert "target_profit_rate numeric(10, 6)" in vtr
    assert "stop_loss_rate numeric(10, 6)" in vtr
    assert "buy_record_id integer references virtual_trading_records(id)" in vtr
    assert "is_test boolean default true" in vtr
    joined = "\n".join(DDL_STATEMENTS).lower()
    # 중복 매도 방지 partial unique index (init-scripts/01-init.sql)
    assert "idx_virtual_trading_unique_sell" in joined
    assert "idx_virtual_trading_source" in joined


def test_real_trading_records_is_like_template_base():
    # 동적 real_trading_{instance} 는 CREATE TABLE ... (LIKE real_trading_records INCLUDING ALL)
    # 로 만들어지므로 base 테이블이 반드시 스키마에 존재해야 한다.
    rtr = [s for s in DDL_STATEMENTS
           if "create table if not exists real_trading_records" in s.lower()][0].lower()
    assert "buy_record_id integer references real_trading_records(id)" in rtr
    assert "id serial primary key" in rtr


def test_paper_trading_state_and_candidate_and_screener_present():
    joined = "\n".join(DDL_STATEMENTS).lower()
    assert "create table if not exists paper_trading_state" in joined
    assert "trade_date  date primary key" in joined or "trade_date date primary key" in joined
    assert "create table if not exists candidate_stocks" in joined
    assert "create table if not exists screener_snapshots" in joined
    assert "params_json jsonb not null" in joined
    assert "unique (strategy, scan_date, params_hash, stock_code)" in joined
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_schema.py -v`
Expected: FAIL — `test_expected_tables_present` (set mismatch) and the three new tests (`IndexError: list index out of range` because the DDL is not present yet).

- [ ] **Step 4: Extend `EXPECTED_TABLES` in `schema.py`**

Replace the `EXPECTED_TABLES` literal (lines 12-15) with:

```python
EXPECTED_TABLES = {
    # 시장데이터 (기존)
    "minute_candles", "daily_prices", "index_daily",
    "corp_events", "collection_reconciliation", "foreign_flow",
    # 운영 테이블 (Phase A — init-scripts 01/05 + paper_strategy_equity 승격)
    "virtual_trading_records", "real_trading_records",
    "paper_trading_state", "paper_strategy_equity",
    "candidate_stocks", "screener_snapshots",
}
```

- [ ] **Step 5: Append the five operational DDL blocks to `DDL_STATEMENTS`**

Insert before the closing `]` of `DDL_STATEMENTS` (after line 110). DDL copied verbatim from `init-scripts/01-init.sql` (+ `source` column/index from `05-vtr-source-column.sql`):

```python
    # ── 운영 테이블 (init-scripts/01-init.sql 컬럼/인덱스/제약 그대로) ──────────
    # 후보 종목
    """
    CREATE TABLE IF NOT EXISTS candidate_stocks (
        id SERIAL PRIMARY KEY,
        stock_code VARCHAR(10) NOT NULL,
        stock_name VARCHAR(100),
        selection_date TIMESTAMPTZ NOT NULL,
        score NUMERIC(10, 4) NOT NULL,
        reasons TEXT,
        status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_candidate_date ON candidate_stocks(selection_date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_candidate_code ON candidate_stocks(stock_code)",
    "CREATE INDEX IF NOT EXISTS idx_candidate_status ON candidate_stocks(status)",
    # 가상 매매 기록 (source 컬럼 포함 — 05-vtr-source-column.sql)
    """
    CREATE TABLE IF NOT EXISTS virtual_trading_records (
        id SERIAL PRIMARY KEY,
        stock_code VARCHAR(10) NOT NULL,
        stock_name VARCHAR(100),
        action VARCHAR(10) NOT NULL,
        quantity INTEGER NOT NULL,
        price NUMERIC(15, 2) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        strategy VARCHAR(50),
        reason TEXT,
        is_test BOOLEAN DEFAULT TRUE,
        profit_loss NUMERIC(15, 2) DEFAULT 0,
        profit_rate NUMERIC(10, 6) DEFAULT 0,
        buy_record_id INTEGER REFERENCES virtual_trading_records(id),
        target_profit_rate NUMERIC(10, 6),
        stop_loss_rate NUMERIC(10, 6),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        source VARCHAR(50)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_code_date ON virtual_trading_records(stock_code, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_action ON virtual_trading_records(action)",
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_test ON virtual_trading_records(is_test)",
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_timestamp ON virtual_trading_records(timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_virtual_trading_source ON virtual_trading_records(source)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_virtual_trading_unique_sell
    ON virtual_trading_records(buy_record_id)
    WHERE action = 'SELL' AND buy_record_id IS NOT NULL
    """,
    # 실거래 기록 base (동적 real_trading_{instance} 의 LIKE 템플릿)
    """
    CREATE TABLE IF NOT EXISTS real_trading_records (
        id SERIAL PRIMARY KEY,
        stock_code VARCHAR(10) NOT NULL,
        stock_name VARCHAR(100),
        action VARCHAR(10) NOT NULL,
        quantity INTEGER NOT NULL,
        price NUMERIC(15, 2) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        strategy VARCHAR(50),
        reason TEXT,
        profit_loss NUMERIC(15, 2) DEFAULT 0,
        profit_rate NUMERIC(10, 6) DEFAULT 0,
        buy_record_id INTEGER REFERENCES real_trading_records(id),
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_real_trading_code_date ON real_trading_records(stock_code, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_real_trading_action ON real_trading_records(action)",
    "CREATE INDEX IF NOT EXISTS idx_real_trading_timestamp ON real_trading_records(timestamp DESC)",
    # 스크리너 시점 스냅샷 (jsonb params_json/metadata)
    """
    CREATE TABLE IF NOT EXISTS screener_snapshots (
        id BIGSERIAL PRIMARY KEY,
        strategy VARCHAR(50) NOT NULL,
        scan_date DATE NOT NULL,
        params_hash VARCHAR(40) NOT NULL,
        params_json JSONB NOT NULL,
        stock_code VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100),
        rank_in_snapshot INT,
        score DOUBLE PRECISION,
        metadata JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (strategy, scan_date, params_hash, stock_code)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_screener_snapshots_strategy_date ON screener_snapshots (strategy, scan_date)",
    "CREATE INDEX IF NOT EXISTS idx_screener_snapshots_params ON screener_snapshots (strategy, params_hash)",
    # 가상매매 EOD 잔고 이월
    """
    CREATE TABLE IF NOT EXISTS paper_trading_state (
        trade_date  DATE PRIMARY KEY,
        eod_balance NUMERIC(15, 2) NOT NULL,
        updated_at  TIMESTAMPTZ DEFAULT now()
    )
    """,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_schema.py -v`
Expected: PASS (all tests, including the three new parity tests). `test_every_expected_table_has_ddl` now also validates the five new tables have DDL.

- [ ] **Step 7: Commit**

```bash
git add RoboTrader_template/scripts/kis_db/schema.py RoboTrader_template/tests/kis_db/test_schema.py
git commit -m "feat(kis_db): Phase A operational table DDL parity in kis_template schema"
```

---

### Task 2: Phase A — promote `paper_strategy_equity` DDL into `schema.py` (kill drift)

Make `schema.py` the single source of truth for the `paper_strategy_equity` DDL and have the ad-hoc `tools/paper_strategy_equity._ensure_table` reuse it.

**Files:**
- Modify: `RoboTrader_template/scripts/kis_db/schema.py`
- Modify: `RoboTrader_template/tools/paper_strategy_equity.py:251-268` (`_ensure_table`)
- Test: `RoboTrader_template/tests/kis_db/test_schema.py`

**Interfaces:**
- Consumes: `DDL_STATEMENTS` from Task 1.
- Produces: module constant `PAPER_STRATEGY_EQUITY_DDL: str` in `scripts/kis_db/schema.py`; `tools.paper_strategy_equity._ensure_table` executes that exact constant.

- [ ] **Step 1: Write the failing consistency test**

Append to `tests/kis_db/test_schema.py`:

```python
def test_paper_strategy_equity_ddl_is_shared_between_schema_and_tool():
    from scripts.kis_db.schema import PAPER_STRATEGY_EQUITY_DDL
    ddl = PAPER_STRATEGY_EQUITY_DDL.lower()
    assert "create table if not exists paper_strategy_equity" in ddl
    assert "primary key (trade_date, strategy, source)" in ddl
    assert "source varchar(50) not null default 'kis_template'" in ddl
    # schema.DDL_STATEMENTS 에도 포함(create_all 이 생성)
    joined = "\n".join(DDL_STATEMENTS).lower()
    assert "create table if not exists paper_strategy_equity" in joined
    # tools 의 _ensure_table 가 동일 상수를 실행하는지 (드리프트 방지)
    import tools.paper_strategy_equity as pse

    class _Cur:
        def __init__(self): self.sql = None
        def execute(self, sql): self.sql = sql
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Conn:
        def __init__(self): self.cur = _Cur()
        def cursor(self): return self.cur
        def commit(self): pass

    c = _Conn()
    pse._ensure_table(c)
    assert c.cur.sql.strip() == PAPER_STRATEGY_EQUITY_DDL.strip()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_schema.py::test_paper_strategy_equity_ddl_is_shared_between_schema_and_tool -v`
Expected: FAIL with `ImportError: cannot import name 'PAPER_STRATEGY_EQUITY_DDL'`.

- [ ] **Step 3: Add the constant + DDL entry to `schema.py`**

Add above `DDL_STATEMENTS` (after the imports/`EXPECTED_TABLES`):

```python
# paper_strategy_equity — tools/paper_strategy_equity._ensure_table 에서 승격(SSOT).
PAPER_STRATEGY_EQUITY_DDL = """
    CREATE TABLE IF NOT EXISTS paper_strategy_equity (
        trade_date date NOT NULL,
        strategy varchar(50) NOT NULL,
        source varchar(50) NOT NULL DEFAULT 'kis_template',
        cash numeric(15,2) NOT NULL,
        position_value numeric(15,2) NOT NULL,
        equity numeric(15,2) NOT NULL,
        realized_pnl_cum numeric(15,2) NOT NULL,
        n_open integer NOT NULL,
        updated_at timestamptz DEFAULT now(),
        PRIMARY KEY (trade_date, strategy, source)
    )
    """
```

Then add `PAPER_STRATEGY_EQUITY_DDL,` as an entry inside `DDL_STATEMENTS` (append at the end of the list, before the closing `]`).

- [ ] **Step 4: Rewire `tools/paper_strategy_equity._ensure_table` to reuse the constant**

Replace the body of `_ensure_table` (lines 251-268) with:

```python
def _ensure_table(conn):
    from scripts.kis_db.schema import PAPER_STRATEGY_EQUITY_DDL
    with conn.cursor() as cur:
        cur.execute(PAPER_STRATEGY_EQUITY_DDL)
    conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_schema.py -v`
Expected: PASS (all, including the new consistency test).

- [ ] **Step 6: Regression-check the equity tool imports cleanly**

Run: `cd RoboTrader_template && python -c "import tools.paper_strategy_equity as p; from scripts.kis_db.schema import PAPER_STRATEGY_EQUITY_DDL; print('OK', p._ensure_table.__doc__ or 'ensure_table wired')"`
Expected: prints `OK ...` with no ImportError.

- [ ] **Step 7: Commit**

```bash
git add RoboTrader_template/scripts/kis_db/schema.py RoboTrader_template/tools/paper_strategy_equity.py RoboTrader_template/tests/kis_db/test_schema.py
git commit -m "feat(kis_db): promote paper_strategy_equity DDL into schema SSOT"
```

---

### Task 3: Phase B1 — idempotent operational-data migration `robotrader` → `kis_template`

New module `migrate_operational_data.py` copying OUR rows only, preserving PKs, UPSERT/`ON CONFLICT DO NOTHING`, no DELETE, re-runnable. Mirrors `seed_from_legacy.py` structure exactly.

**Files:**
- Create: `RoboTrader_template/scripts/kis_db/migrate_operational_data.py`
- Test: `RoboTrader_template/tests/kis_db/test_migrate_operational_data.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_connection()` (write target); `psycopg2.connect(...)` for the `robotrader` source; Task 1/2 DDL (target tables must exist — the CLI calls `schema.create_all` first).
- Produces:
  - `VTR_COLUMNS: list[str]`, `REAL_COLUMNS: list[str]`, `CANDIDATE_COLUMNS: list[str]`, `SCREENER_COLUMNS: list[str]`, `PAPER_STATE_COLUMNS: list[str]` — exact column orders.
  - `build_vtr_select() -> str` — `"SELECT <cols> FROM virtual_trading_records WHERE source='kis_template' ORDER BY id"`.
  - `build_screener_rows(legacy_rows) -> list[tuple]` — json-serializes `params_json`/`metadata` dict columns.
  - `discover_real_tables(conn) -> list[str]` — names matching `^real_trading_` (base + instances) from `information_schema`.
  - `migrate_table(src_conn, select_sql, table, columns, conflict_target, apply, row_builder=None, template=None) -> dict` — returns `{"table", "source_rows", "copied"}`.
  - `bump_serial_sequence(dst_conn, table, id_col="id") -> None`.
  - `main(argv=None) -> int` CLI: `--apply`, `--instance <name>` (optional extra real table), dry-run default.

- [ ] **Step 1: Write failing unit tests**

Create `tests/kis_db/test_migrate_operational_data.py`:

```python
import json
import scripts.kis_db.migrate_operational_data as mig


def test_vtr_columns_exact_order():
    assert mig.VTR_COLUMNS == [
        "id", "stock_code", "stock_name", "action", "quantity", "price",
        "timestamp", "strategy", "reason", "is_test", "profit_loss",
        "profit_rate", "buy_record_id", "target_profit_rate", "stop_loss_rate",
        "created_at", "source",
    ]


def test_vtr_select_filters_our_source_and_orders_by_id():
    sql = mig.build_vtr_select()
    assert sql == (
        "SELECT id, stock_code, stock_name, action, quantity, price, "
        "timestamp, strategy, reason, is_test, profit_loss, profit_rate, "
        "buy_record_id, target_profit_rate, stop_loss_rate, created_at, source "
        "FROM virtual_trading_records WHERE source = 'kis_template' ORDER BY id"
    )


def test_screener_columns_and_json_serialization():
    assert mig.SCREENER_COLUMNS == [
        "id", "strategy", "scan_date", "params_hash", "params_json",
        "stock_code", "stock_name", "rank_in_snapshot", "score", "metadata",
        "created_at",
    ]
    # params_json(idx 4), metadata(idx 9) dict → JSON 문자열
    src = [(1, "elder", "2026-07-01", "abcd", {"k": 1}, "005930", "삼성", 1, 9.9, {"sector": "IT"}, "2026-07-01 09:00:00")]
    out = mig.build_screener_rows(src)
    assert out[0][4] == json.dumps({"k": 1}, ensure_ascii=False)
    assert out[0][9] == json.dumps({"sector": "IT"}, ensure_ascii=False)
    # None metadata 는 그대로 None
    src2 = [(2, "elder", "2026-07-01", "abcd", {"k": 1}, "000660", "하닉", 2, 8.8, None, "2026-07-01 09:00:00")]
    assert mig.build_screener_rows(src2)[0][9] is None


def test_discover_real_tables_filters_prefix():
    class _Cur:
        def execute(self, sql, params=None): self._sql = sql
        def fetchall(self): return [("real_trading_records",), ("real_trading_elder",)]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Conn:
        def cursor(self): return _Cur()

    assert mig.discover_real_tables(_Conn()) == ["real_trading_records", "real_trading_elder"]


def test_migrate_table_dry_run_counts_source_only(monkeypatch):
    # apply=False 면 source_rows 만 세고 copied=0 (쓰기 없음)
    class _SCur:
        itersize = None
        def execute(self, sql): pass
        def fetchmany(self, n):
            if not getattr(self, "_done", False):
                self._done = True
                return [(1, "005930")]
            return []
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Src:
        def cursor(self, name=None): return _SCur()

    out = mig.migrate_table(_Src(), "SELECT 1", "candidate_stocks",
                            ["id", "stock_code"], "(id)", apply=False)
    assert out == {"table": "candidate_stocks", "source_rows": 1, "copied": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_migrate_operational_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.kis_db.migrate_operational_data'`.

- [ ] **Step 3: Implement `migrate_operational_data.py`**

Create `scripts/kis_db/migrate_operational_data.py`:

```python
"""운영 데이터 이관(멱등): robotrader → kis_template. 우리 행만, PK 보존, DELETE 없음.

- virtual_trading_records: WHERE source='kis_template' 만.
- real_trading_records / real_trading_{instance}: 우리 인스턴스 테이블만.
- paper_trading_state · candidate_stocks · screener_snapshots: 전량(우리 봇 소유).
UPSERT/ON CONFLICT DO NOTHING 로 재실행 안전. 복사 후 SERIAL 시퀀스를 setval 로 올려
봇의 다음 INSERT 가 이관된 id 와 충돌하지 않게 한다.

usage: python -m scripts.kis_db.migrate_operational_data            # dry-run
       python -m scripts.kis_db.migrate_operational_data --apply    # 실제 복사
"""
import argparse
import json
import os
import sys

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from scripts.kis_db import schema  # noqa: E402

BATCH = 5000
SOURCE_DB = "robotrader"

VTR_COLUMNS = [
    "id", "stock_code", "stock_name", "action", "quantity", "price",
    "timestamp", "strategy", "reason", "is_test", "profit_loss",
    "profit_rate", "buy_record_id", "target_profit_rate", "stop_loss_rate",
    "created_at", "source",
]
REAL_COLUMNS = [
    "id", "stock_code", "stock_name", "action", "quantity", "price",
    "timestamp", "strategy", "reason", "profit_loss", "profit_rate",
    "buy_record_id", "created_at",
]
CANDIDATE_COLUMNS = [
    "id", "stock_code", "stock_name", "selection_date", "score",
    "reasons", "status", "created_at",
]
SCREENER_COLUMNS = [
    "id", "strategy", "scan_date", "params_hash", "params_json",
    "stock_code", "stock_name", "rank_in_snapshot", "score", "metadata",
    "created_at",
]
PAPER_STATE_COLUMNS = ["trade_date", "eod_balance", "updated_at"]

# screener_snapshots 의 jsonb 컬럼 위치 (params_json=4, metadata=9)
_SCREENER_JSON_IDX = (4, 9)
# execute_values 템플릿: params_json/metadata 를 ::jsonb 로 캐스팅
_SCREENER_TEMPLATE = (
    "(%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s)"
)


def _source_conn():
    return psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"),
        port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname=SOURCE_DB,
        user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "1234"),
    )


def build_vtr_select() -> str:
    cols = ", ".join(VTR_COLUMNS)
    return (
        f"SELECT {cols} FROM virtual_trading_records "
        f"WHERE source = 'kis_template' ORDER BY id"
    )


def build_screener_rows(legacy_rows):
    """params_json/metadata dict 컬럼을 JSON 문자열로 직렬화(psycopg2 jsonb 적응)."""
    out = []
    for row in legacy_rows:
        row = list(row)
        for i in _SCREENER_JSON_IDX:
            if isinstance(row[i], (dict, list)):
                row[i] = json.dumps(row[i], ensure_ascii=False)
        out.append(tuple(row))
    return out


def _passthrough(rows):
    return list(rows)


def discover_real_tables(conn):
    """robotrader 소스에서 real_trading_* 테이블명을 오름차순으로 반환(base+instances)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name LIKE 'real_trading_%' "
            "ORDER BY table_name"
        )
        return [r[0] for r in cur.fetchall()]


def migrate_table(src_conn, select_sql, table, columns, conflict_target,
                  apply=False, row_builder=None, template=None) -> dict:
    """멱등 스트리밍 복사. apply=False 면 source_rows 만 카운트(쓰기 없음)."""
    if row_builder is None:
        row_builder = _passthrough
    cols_csv = ", ".join(columns)
    conflict = f"ON CONFLICT {conflict_target} DO NOTHING" if conflict_target else "ON CONFLICT DO NOTHING"
    upsert = f"INSERT INTO {table} ({cols_csv}) VALUES %s {conflict}"
    copied = 0
    source_rows = 0
    with src_conn.cursor(name=f"mig_{table}") as scur:
        scur.itersize = BATCH
        scur.execute(select_sql)
        dst_cm = KisDbConnection.get_connection() if apply else None
        dst = dst_cm.__enter__() if dst_cm else None
        try:
            while True:
                rows = scur.fetchmany(BATCH)
                if not rows:
                    break
                source_rows += len(rows)
                if apply:
                    with dst.cursor() as dcur:
                        execute_values(dcur, upsert, row_builder(rows), template=template)
                    dst.commit()
                    copied += len(rows)
        finally:
            if dst_cm:
                dst_cm.__exit__(None, None, None)
    return {"table": table, "source_rows": source_rows, "copied": copied}


def bump_serial_sequence(dst_conn, table, id_col="id") -> None:
    """복사한 명시적 id 이후로 SERIAL 시퀀스를 올린다(봇 다음 INSERT 충돌 방지). 멱등."""
    with dst_conn.cursor() as cur:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence(%s, %s), "
            f"COALESCE((SELECT MAX({id_col}) FROM {table}), 1))",
            (table, id_col),
        )
    dst_conn.commit()


def run(apply=False, extra_instances=None) -> dict:
    results = {}
    # 대상 스키마 보장(멱등)
    if apply:
        with KisDbConnection.get_connection() as conn:
            schema.create_all(conn)
    src = _source_conn()
    try:
        # 1) virtual_trading_records (우리 source 만)
        results["virtual_trading_records"] = migrate_table(
            src, build_vtr_select(), "virtual_trading_records",
            VTR_COLUMNS, "(id)", apply)
        # 2) candidate_stocks (전량)
        results["candidate_stocks"] = migrate_table(
            src, f"SELECT {', '.join(CANDIDATE_COLUMNS)} FROM candidate_stocks ORDER BY id",
            "candidate_stocks", CANDIDATE_COLUMNS, "(id)", apply)
        # 3) screener_snapshots (전량, jsonb 직렬화)
        results["screener_snapshots"] = migrate_table(
            src, f"SELECT {', '.join(SCREENER_COLUMNS)} FROM screener_snapshots ORDER BY id",
            "screener_snapshots", SCREENER_COLUMNS, "(id)", apply,
            row_builder=build_screener_rows, template=_SCREENER_TEMPLATE)
        # 4) paper_trading_state (전량, PK=trade_date)
        results["paper_trading_state"] = migrate_table(
            src, f"SELECT {', '.join(PAPER_STATE_COLUMNS)} FROM paper_trading_state ORDER BY trade_date",
            "paper_trading_state", PAPER_STATE_COLUMNS, "(trade_date)", apply)
        # 5) real_trading_* (우리 인스턴스 테이블들)
        real_tables = discover_real_tables(src)
        for name in (extra_instances or []):
            if name not in real_tables:
                real_tables.append(name)
        for rt in real_tables:
            if apply:
                # 대상에 인스턴스 테이블 보장(base LIKE)
                with KisDbConnection.get_connection() as conn:
                    with conn.cursor() as c:
                        c.execute(
                            f"CREATE TABLE IF NOT EXISTS {rt} "
                            f"(LIKE real_trading_records INCLUDING ALL)")
                    conn.commit()
            results[rt] = migrate_table(
                src, f"SELECT {', '.join(REAL_COLUMNS)} FROM {rt} ORDER BY id",
                rt, REAL_COLUMNS, "(id)", apply)
    finally:
        src.close()
    # 시퀀스 bump (apply 시에만)
    if apply:
        with KisDbConnection.get_connection() as conn:
            for t in ["virtual_trading_records", "candidate_stocks", "screener_snapshots"]:
                bump_serial_sequence(conn, t)
            for rt in discover_real_tables(src) if not src.closed else []:
                bump_serial_sequence(conn, rt)
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="운영 데이터 robotrader→kis_template 이관(멱등)")
    ap.add_argument("--apply", action="store_true", help="실제 복사(미지정=dry-run)")
    ap.add_argument("--instance", action="append", default=None,
                    help="추가 real_trading_{instance} 테이블명(반복 가능)")
    args = ap.parse_args(argv)
    results = run(apply=args.apply, extra_instances=args.instance)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] 운영 데이터 이관 결과:")
    for table, r in results.items():
        print(f"  {table:28s} source={r['source_rows']:>7} copied={r['copied']:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: the `for rt in discover_real_tables(src) if not src.closed else []` guard in `run` — since `src` is closed in the `finally` above, move the real-table sequence bump to reuse the `real_tables` list captured earlier. Correct the `run` function so the post-copy sequence bump iterates the already-captured `real_tables` list (not a re-query on a closed connection):

```python
    # (inside run, replace the sequence-bump block)
    if apply:
        with KisDbConnection.get_connection() as conn:
            for t in ["virtual_trading_records", "candidate_stocks", "screener_snapshots"]:
                bump_serial_sequence(conn, t)
            for rt in real_tables:
                bump_serial_sequence(conn, rt)
```

(Define `real_tables = []` before the `try` so it is in scope for the bump block; assign it inside the `try` where discovered.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_migrate_operational_data.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Dry-run against production (READ-only, no writes)**

Run: `cd RoboTrader_template && python -m scripts.kis_db.migrate_operational_data`
Expected: prints `[DRY-RUN] ...` with non-zero `source=` counts for `virtual_trading_records` / `candidate_stocks` / `paper_trading_state` and `copied=0` everywhere (dry-run performs no writes to any DB).

- [ ] **Step 6: Commit**

```bash
git add RoboTrader_template/scripts/kis_db/migrate_operational_data.py RoboTrader_template/tests/kis_db/test_migrate_operational_data.py
git commit -m "feat(kis_db): B1 idempotent operational-data migration robotrader->kis_template"
```

---

### Task 4: Phase B2 — offline market-data equivalence report (explainable-diff gate)

New module `report_equivalence.py`. Compares `kis_template.daily_prices` vs `robotrader_quant.daily_prices` and `kis_template.minute_candles` vs `robotrader.minute_candles`: coverage + column presence (`market_cap`, `trading_value`) + value diffs, classifying each diff. Gate = "all diffs explained" (split-adjustment diffs are acceptable improvements), not "zero diff". READ-only on all DBs.

**Files:**
- Create: `RoboTrader_template/scripts/kis_db/report_equivalence.py`
- Test: `RoboTrader_template/tests/kis_db/test_report_equivalence.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_connection()` (read kis_template); `psycopg2.connect(...)` for `robotrader_quant` / `robotrader` (read-only).
- Produces:
  - `classify_diff(legacy: float|None, new: float|None, tol: float = 0.005) -> str` — one of `"match"`, `"split_adjust"`, `"coverage_gap"`, `"unexplained"`. Uses GENERAL near-integer ratio detection (no fixed factor set): after `match` and `coverage_gap`, computes `ratio = max/min` and accepts as `"split_adjust"` when `ratio` is within relative `tol` of an integer in `[2, 150]` (or of `2.5`), consistent with `collectors/split_factor_infer.py`. This correctly explains the verified 001130 1:11 split and any future integer ratio.
  - `build_equivalence_report(dataset: str, legacy_map: dict, new_map: dict, tol: float = 0.005) -> dict` — pure; returns `{"dataset", "coverage", "counts": {match, split_adjust, coverage_gap, unexplained}, "verdict", "unexplained_samples"}`. `verdict = "PASS"` iff `unexplained == 0`.
  - `main(argv=None) -> int` CLI reading real DBs and printing per-dataset reports.

- [ ] **Step 1: Write failing unit tests**

Create `tests/kis_db/test_report_equivalence.py`:

```python
import scripts.kis_db.report_equivalence as rep


def test_classify_exact_match():
    assert rep.classify_diff(70000.0, 70050.0, tol=0.005) == "match"  # 0.07% < 0.5%


def test_classify_split_adjust_half():
    # 액면분할 1:2: 레거시 미조정 100000 vs 조정 50000 (÷2) → 설명 가능(개선)
    assert rep.classify_diff(100000.0, 50000.0) == "split_adjust"


def test_classify_split_adjust_tenth():
    assert rep.classify_diff(50000.0, 5000.0) == "split_adjust"


def test_classify_split_11x_explained():
    # 001130: 검증된 1:11 분할(DART "주식분할결정", kis adj_factor=11). 156500/11≈14227.
    # 고정 배수 집합에는 11 이 없어 예전엔 오탐 FAIL 이었음 — 일반 정수비 검출로 설명 가능.
    assert rep.classify_diff(156500.0, 14227.0) == "split_adjust"
    assert rep.classify_diff(14227.0, 156500.0) == "split_adjust"  # 역방향(대소 무관)


def test_classify_split_2_5x_explained():
    # 단주/액면 2.5 배 분할도 설명 가능
    assert rep.classify_diff(25000.0, 10000.0) == "split_adjust"


def test_classify_coverage_gap_when_one_missing():
    assert rep.classify_diff(None, 5000.0) == "coverage_gap"
    assert rep.classify_diff(5000.0, None) == "coverage_gap"


def test_classify_unexplained_random_diff():
    assert rep.classify_diff(10000.0, 12345.0) == "unexplained"  # 1.23x 불규칙(정수비 아님)


def test_build_report_pass_when_no_unexplained():
    legacy = {"A": 70000.0, "B": 100000.0, "C": 5000.0}
    new = {"A": 70050.0, "B": 50000.0, "C": None}  # A match, B split, C coverage_gap
    r = rep.build_equivalence_report("daily", legacy, new)
    assert r["counts"] == {"match": 1, "split_adjust": 1, "coverage_gap": 1, "unexplained": 0}
    assert r["verdict"] == "PASS"
    assert r["coverage"] == 2 / 3  # new 에 값이 있는 비율(교집합 종가 존재)


def test_build_report_fail_on_unexplained():
    legacy = {"A": 10000.0}
    new = {"A": 12345.0}
    r = rep.build_equivalence_report("daily", legacy, new)
    assert r["counts"]["unexplained"] == 1
    assert r["verdict"] == "FAIL"
    assert r["unexplained_samples"][:1] == [("A", 10000.0, 12345.0)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_report_equivalence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.kis_db.report_equivalence'`.

- [ ] **Step 3: Implement `report_equivalence.py`**

Create `scripts/kis_db/report_equivalence.py`:

```python
"""시장데이터 정합 검증(오프라인, READ-only). kis_template vs 현 라이브 소스.

- daily: kis_template.daily_prices vs robotrader_quant.daily_prices
- minute: kis_template.minute_candles vs robotrader.minute_candles (표본 거래일)
게이트 = "모든 diff 가 설명됨"(분할조정 = kis 개선 = 통과 사유), "제로 diff" 아님.
미설명 diff 가 1건이라도 있으면 FAIL. 어떤 DB 에도 쓰지 않는다.

usage:
  python -m scripts.kis_db.report_equivalence                 # 최근 거래일 자동
  python -m scripts.kis_db.report_equivalence --date 2026-07-03
"""
import argparse
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402

# 분할/병합으로 설명 가능한 정수비 범위 (collectors/split_factor_infer.py 와 일관).
# 고정 배수 집합이 아니라 "정수에 가까운 비율"을 일반 검출한다 → 11(001130 검증된
# 1:11 분할), 15 등 임의 정수비와 2.5(단주/액면) 모두 설명 가능.
SPLIT_RATIO_MIN = 2
SPLIT_RATIO_MAX = 150
MAX_UNEXPLAINED_SAMPLES = 20


def classify_diff(legacy, new, tol: float = 0.005) -> str:
    """단일 종목 종가 diff 분류.

    match: 상대오차 < tol
    split_adjust: ratio=max/min 이 정수(2..150) 또는 2.5 에 상대오차 tol 이내로 근접
        (kis 가 분할조정을 정확히 반영한 개선 — 001130 1:11 등). split_factor_infer 와 일관.
    coverage_gap: 한쪽 값 없음(None/0)
    unexplained: 그 외(예: 1.23x 불규칙)
    """
    if legacy is None or new is None or legacy == 0 or new == 0:
        return "coverage_gap"
    legacy = float(legacy)
    new = float(new)
    if abs(new - legacy) / legacy < tol:
        return "match"
    hi = max(legacy, new)
    lo = min(legacy, new)
    ratio = hi / lo  # >= 1
    nearest = round(ratio)
    if SPLIT_RATIO_MIN <= nearest <= SPLIT_RATIO_MAX and abs(ratio - nearest) <= ratio * tol:
        return "split_adjust"
    if abs(ratio - 2.5) <= 2.5 * tol:  # 단주/액면 2.5 배 분할
        return "split_adjust"
    return "unexplained"


def build_equivalence_report(dataset: str, legacy_map: dict, new_map: dict,
                             tol: float = 0.005) -> dict:
    """순수 함수: 레거시/신규 {code: close} 맵을 분류 집계한 리포트를 반환."""
    counts = {"match": 0, "split_adjust": 0, "coverage_gap": 0, "unexplained": 0}
    unexplained_samples = []
    codes = set(legacy_map) | set(new_map)
    covered = 0
    for code in codes:
        lv = legacy_map.get(code)
        nv = new_map.get(code)
        if nv is not None and nv != 0:
            covered += 1
        verdict = classify_diff(lv, nv, tol)
        counts[verdict] += 1
        if verdict == "unexplained" and len(unexplained_samples) < MAX_UNEXPLAINED_SAMPLES:
            unexplained_samples.append((code, lv, nv))
    coverage = covered / len(codes) if codes else 1.0
    return {
        "dataset": dataset,
        "coverage": coverage,
        "counts": counts,
        "verdict": "PASS" if counts["unexplained"] == 0 else "FAIL",
        "unexplained_samples": unexplained_samples,
    }


def _legacy_conn(dbname: str):
    return psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"),
        port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname=dbname,
        user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "1234"),
    )


def _latest_kis_daily_date() -> str:
    with KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date) FROM daily_prices")
            return cur.fetchone()[0]


def _column_presence(conn, table, columns) -> dict:
    """지정 컬럼이 NULL 아닌 값을 가진 행 수(존재/충전 확인)."""
    out = {}
    with conn.cursor() as cur:
        for c in columns:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {c} IS NOT NULL")
            out[c] = cur.fetchone()[0]
    return out


def report_daily(trade_date: str) -> dict:
    legacy = _legacy_conn("robotrader_quant")
    try:
        with legacy.cursor() as lc:
            lc.execute("SELECT stock_code, close FROM daily_prices WHERE date = %s", (trade_date,))
            legacy_map = {sc: (float(c) if c is not None else None) for sc, c in lc.fetchall()}
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as nc:
                nc.execute("SELECT stock_code, close FROM daily_prices WHERE date = %s", (trade_date,))
                new_map = {sc: (float(c) if c is not None else None) for sc, c in nc.fetchall()}
            col_presence = _column_presence(conn,
                "(SELECT * FROM daily_prices WHERE date = '%s') dp" % trade_date,
                ["market_cap", "trading_value"])
    finally:
        legacy.close()
    rep = build_equivalence_report(f"daily@{trade_date}", legacy_map, new_map)
    rep["column_presence"] = col_presence
    return rep


def report_minute(trade_date: str) -> dict:
    legacy = _legacy_conn("robotrader")
    try:
        # 표본: 당일 존재하는 (stock_code, idx) 최근 종가 대조 — 종목별 마지막 idx close
        q = ("SELECT stock_code, close FROM minute_candles "
             "WHERE trade_date = %s AND idx = ("
             "  SELECT MAX(idx) FROM minute_candles m2 "
             "  WHERE m2.stock_code = minute_candles.stock_code AND m2.trade_date = %s)")
        with legacy.cursor() as lc:
            lc.execute(q, (trade_date, trade_date))
            legacy_map = {sc: (float(c) if c is not None else None) for sc, c in lc.fetchall()}
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as nc:
                nc.execute(q, (trade_date, trade_date))
                new_map = {sc: (float(c) if c is not None else None) for sc, c in nc.fetchall()}
    finally:
        legacy.close()
    return build_equivalence_report(f"minute@{trade_date}", legacy_map, new_map)


def _print_report(r: dict) -> None:
    print(f"\n== {r['dataset']} ==")
    print(f"  coverage(new): {r['coverage']:.4f}")
    print(f"  counts: {r['counts']}")
    if "column_presence" in r:
        print(f"  column_presence(non-null rows): {r['column_presence']}")
    print(f"  VERDICT: {r['verdict']}")
    if r["unexplained_samples"]:
        print("  unexplained(top):")
        for code, lv, nv in r["unexplained_samples"]:
            print(f"    {code}: legacy={lv} new={nv}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="시장데이터 정합 리포트(오프라인, READ-only)")
    ap.add_argument("--date", default=None, help="대상 거래일(YYYY-MM-DD). 미지정=kis 최신 일봉일")
    args = ap.parse_args(argv)
    trade_date = args.date or _latest_kis_daily_date()
    daily = report_daily(trade_date)
    minute = report_minute(trade_date)
    _print_report(daily)
    _print_report(minute)
    overall = "PASS" if daily["verdict"] == "PASS" and minute["verdict"] == "PASS" else "FAIL"
    print(f"\n[GATE] 모든 diff 설명됨? → {overall}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_report_equivalence.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Run the report against production (READ-only)**

Run: `cd RoboTrader_template && python -m scripts.kis_db.report_equivalence`
Expected: prints `daily@<date>` and `minute@<date>` blocks with counts and a `[GATE] ... → PASS/FAIL`. Inspect any `unexplained` samples manually; split-adjust diffs (e.g. `001130`) must land in `split_adjust`, not `unexplained`. This command writes to no DB.

- [ ] **Step 6: Commit**

```bash
git add RoboTrader_template/scripts/kis_db/report_equivalence.py RoboTrader_template/tests/kis_db/test_report_equivalence.py
git commit -m "feat(kis_db): B2 offline market-data equivalence report with explainable-diff gate"
```

---

### Task 5: Phase B3 — StateRestorer equivalence smoke (worktree/isolated env only)

New module `smoke_state_restore.py`. Runs `StateRestorer` against a chosen DB with lightweight fakes (paper mode), summarizes restored open positions / per-strategy cash ledger / candidates, and compares a `kis_template` run vs the `robotrader` baseline. Pure summary/compare helpers are TDD-tested; the live run is a smoke exercised only in the worktree.

**Files:**
- Create: `RoboTrader_template/scripts/kis_db/smoke_state_restore.py`
- Test: `RoboTrader_template/tests/kis_db/test_smoke_state_restore.py`

**Interfaces:**
- Consumes: `bot.state_restorer.StateRestorer`; `db.repositories.trading.TradingRepository` (`get_virtual_open_positions`, `get_strategy_trade_sums`); `db.connection.DatabaseConnection` (rebound per-run via `TIMESCALE_DB` env + `close_all()`); `db.repositories.candidate.CandidateRepository`.
- Produces:
  - `build_restore_summary(open_positions, strategy_sums, candidate_codes) -> dict` — pure; `open_positions` = list of `{stock_code, quantity, buy_price, strategy}`, `strategy_sums` = `{strategy: {buy_gross, sell_gross}}`, `candidate_codes` = iterable of codes. Returns `{"open_position_codes": sorted[...], "n_open": int, "per_strategy_cash": {strategy: round(float,2)}, "candidate_codes": sorted[...]}`. Per-strategy cash uses the live formula `capital - buy_gross*(1+commission) + sell_gross*(1-commission-tax)`.
  - `compare_summaries(baseline: dict, candidate: dict) -> dict` — pure; `{"open_positions_match": bool, "candidates_match": bool, "cash_max_abs_diff": float, "cash_match": bool, "verdict": "PASS"|"FAIL"}` (`cash_match` true when `cash_max_abs_diff < 1.0`).
  - `run_smoke(dbname: str, capital: float) -> dict` — sets `TIMESCALE_DB=dbname` then runs a `StateRestorer` with fakes in the CURRENT process, returns a summary dict. Intended to run in a freshly-spawned child interpreter (pristine singleton pool).
  - `_spawn_summary(dbname: str, capital: float) -> dict` — spawns `python -m scripts.kis_db.smoke_state_restore --emit-db <dbname>` as a SUBPROCESS and parses its JSON stdout. This is the isolation boundary: each DB is read in its own process so the module-level `DatabaseConnection` singleton pool is never rebound in-place.
  - `main(argv=None) -> int` CLI: `--capital`; `--emit-db <dbname>` (child mode: run_smoke + print JSON, exit); no `--emit-db` (parent mode: spawn a child per DB via `--baseline-db`/`--candidate-db`, compare, print verdict).

- [ ] **Step 1: Write failing unit tests**

Create `tests/kis_db/test_smoke_state_restore.py`:

```python
import scripts.kis_db.smoke_state_restore as smk
from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE


def test_build_summary_positions_and_candidates_sorted():
    ops = [
        {"stock_code": "000660", "quantity": 5, "buy_price": 100.0, "strategy": "elder"},
        {"stock_code": "005930", "quantity": 3, "buy_price": 200.0, "strategy": "ma5"},
    ]
    s = smk.build_restore_summary(ops, {}, ["005930", "000660", "000660"])
    assert s["open_position_codes"] == ["000660", "005930"]
    assert s["n_open"] == 2
    assert s["candidate_codes"] == ["000660", "005930"]  # dedup + sorted


def test_build_summary_cash_uses_live_formula():
    sums = {"elder": {"buy_gross": 1000.0, "sell_gross": 500.0}}
    s = smk.build_restore_summary([], sums, [], capital=10000.0)
    expected = 10000.0 - 1000.0 * (1 + COMMISSION_RATE) + 500.0 * (1 - COMMISSION_RATE - SECURITIES_TAX_RATE)
    assert s["per_strategy_cash"]["elder"] == round(expected, 2)


def test_compare_summaries_pass_when_identical():
    base = {"open_position_codes": ["A"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.0}}
    cand = {"open_position_codes": ["A"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.4}}  # 0.4 < 1.0 → 일치
    c = smk.compare_summaries(base, cand)
    assert c["open_positions_match"] is True
    assert c["candidates_match"] is True
    assert c["cash_match"] is True
    assert c["verdict"] == "PASS"


def test_compare_summaries_fail_on_position_mismatch():
    base = {"open_position_codes": ["A", "B"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.0}}
    cand = {"open_position_codes": ["A"], "candidate_codes": ["X"],
            "per_strategy_cash": {"elder": 100.0}}
    c = smk.compare_summaries(base, cand)
    assert c["open_positions_match"] is False
    assert c["verdict"] == "FAIL"


def test_compare_summaries_fail_on_cash_drift():
    base = {"open_position_codes": [], "candidate_codes": [],
            "per_strategy_cash": {"elder": 100.0}}
    cand = {"open_position_codes": [], "candidate_codes": [],
            "per_strategy_cash": {"elder": 250.0}}  # 150 diff
    c = smk.compare_summaries(base, cand)
    assert c["cash_max_abs_diff"] == 150.0
    assert c["cash_match"] is False
    assert c["verdict"] == "FAIL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_smoke_state_restore.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.kis_db.smoke_state_restore'`.

- [ ] **Step 3: Implement `smoke_state_restore.py`**

Create `scripts/kis_db/smoke_state_restore.py`:

```python
"""상태복원 스모크(격리 worktree 전용). StateRestorer 를 선택 DB 로 실행해
열린 포지션 / 전략별 현금원장 / 후보를 요약하고, kis_template 와 robotrader
기준(baseline)을 대조한다.

⚠️ 라이브 트리에서 실행 금지(메모리 규칙). 이 스크립트는 DB 를 읽기만 한다
(StateRestorer 는 fake trading_manager 로 주입되어 실주문/실쓰기 없음).

DB 격리: baseline(robotrader)/candidate(kis_template) 각각을 **별도 자식 프로세스**에서
읽는다. db.connection.DatabaseConnection 은 모듈 레벨 싱글턴 풀이라 한 프로세스 안에서
dbname 을 재바인딩하면(close_all + env 스왑) 취약(다른 스레드/이미 초기화된 풀 잔존)하다.
자식 프로세스는 풀이 초기화되기 전에 TIMESCALE_DB 를 세팅하므로 항상 pristine.

usage(worktree):
  python -m scripts.kis_db.smoke_state_restore --baseline-db robotrader --candidate-db kis_template
  # (내부적으로 각 DB 를 --emit-db 자식 프로세스로 실행해 JSON 요약을 대조)
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.constants import COMMISSION_RATE, SECURITIES_TAX_RATE  # noqa: E402

DEFAULT_CAPITAL = 10_000_000


def build_restore_summary(open_positions, strategy_sums, candidate_codes,
                          capital: float = DEFAULT_CAPITAL) -> dict:
    """순수 요약. 현금식은 라이브(restore_strategy_ledger_from_records)와 동일:
        cash = capital - buy_gross*(1+comm) + sell_gross*(1-comm-tax)
    """
    codes = sorted({p["stock_code"] for p in open_positions})
    per_cash = {}
    for strat, s in strategy_sums.items():
        buy_g = float(s.get("buy_gross", 0.0))
        sell_g = float(s.get("sell_gross", 0.0))
        cash = capital - buy_g * (1 + COMMISSION_RATE) + sell_g * (1 - COMMISSION_RATE - SECURITIES_TAX_RATE)
        per_cash[strat] = round(cash, 2)
    return {
        "open_position_codes": codes,
        "n_open": len(codes),
        "per_strategy_cash": per_cash,
        "candidate_codes": sorted(set(candidate_codes)),
    }


def compare_summaries(baseline: dict, candidate: dict) -> dict:
    """순수 대조. 현금은 전략별 절대차 최대치가 1원 미만이면 일치."""
    pos_match = baseline["open_position_codes"] == candidate["open_position_codes"]
    cand_match = baseline["candidate_codes"] == candidate["candidate_codes"]
    strategies = set(baseline["per_strategy_cash"]) | set(candidate["per_strategy_cash"])
    max_diff = 0.0
    for s in strategies:
        b = baseline["per_strategy_cash"].get(s, 0.0)
        c = candidate["per_strategy_cash"].get(s, 0.0)
        max_diff = max(max_diff, abs(b - c))
    cash_match = max_diff < 1.0
    verdict = "PASS" if (pos_match and cand_match and cash_match) else "FAIL"
    return {
        "open_positions_match": pos_match,
        "candidates_match": cand_match,
        "cash_max_abs_diff": max_diff,
        "cash_match": cash_match,
        "verdict": verdict,
    }


# ── 라이브 스모크 (DB 필요, worktree 전용) ──────────────────────────────────

class _FakeTradingManager:
    """add_selected_stock/get_trading_stock 를 받아 복원 포지션을 캡처하는 최소 fake."""
    def __init__(self):
        self.captured = {}  # stock_code -> {quantity, buy_price, strategy}

    async def add_selected_stock(self, stock_code, stock_name, selection_reason,
                                 prev_close=None, owner_strategy=None):
        self.captured[stock_code] = {"stock_code": stock_code, "quantity": 0,
                                     "buy_price": 0.0, "strategy": owner_strategy or ""}
        return True

    def get_trading_stock(self, stock_code, strategy=None):
        rec = self.captured.get(stock_code)
        if rec is None:
            return None
        return _FakeTradingStock(rec)

    def _change_stock_state(self, *a, **k):
        return None


class _FakeTradingStock:
    def __init__(self, rec):
        self._rec = rec
        self.stock_code = rec["stock_code"]
        self.stock_name = rec["stock_code"]
        self.owner_strategy_name = rec["strategy"]
        self.owner_strategy = None
        self.target_profit_rate = None
        self.stop_loss_rate = None
        self.is_stale = False
        self.days_held = 0

    def set_position(self, quantity, buy_price):
        self._rec["quantity"] = int(quantity)
        self._rec["buy_price"] = float(buy_price)

    def set_virtual_buy_info(self, *a, **k):
        return None


class _FakeConfig:
    paper_trading = True


def run_smoke(dbname: str, capital: float = DEFAULT_CAPITAL) -> dict:
    """현재 프로세스에서 TIMESCALE_DB=dbname 을 세팅하고 StateRestorer 를 fake 로 실행 → 요약.

    풀 초기화 전에 env 를 세팅해야 하므로 반드시 자식 프로세스(--emit-db)로 호출한다.
    부모 프로세스에서 직접 호출하면 이미 초기화된 싱글턴 풀이 남아 잘못된 DB 를 읽을 수 있다.
    """
    os.environ["TIMESCALE_DB"] = dbname
    from bot.state_restorer import StateRestorer
    from db.repositories.trading import TradingRepository
    from db.repositories.candidate import CandidateRepository
    from utils.korean_time import now_kst

    trading_repo = TradingRepository()
    candidate_repo = CandidateRepository()

    tm = _FakeTradingManager()
    restorer = StateRestorer(
        trading_manager=tm,
        db_manager=trading_repo,
        telegram_integration=None,
        config=_FakeConfig(),
        get_previous_close_callback=lambda code: None,
        broker=None,
        fund_manager=None,
        virtual_trading_manager=None,
        strategies={},
    )
    asyncio.run(restorer.restore_todays_candidates())

    open_positions = list(tm.captured.values())
    strategy_sums = trading_repo.get_strategy_trade_sums()
    today = now_kst().strftime("%Y-%m-%d")
    cand_df = candidate_repo.get_candidate_history(days=1)
    if not cand_df.empty and "stock_code" in cand_df.columns:
        cand_codes = list(cand_df["stock_code"])
    else:
        cand_codes = []
    return build_restore_summary(open_positions, strategy_sums, cand_codes, capital)


def _spawn_summary(dbname: str, capital: float) -> dict:
    """자식 프로세스로 run_smoke 를 실행하고 stdout 의 JSON 요약을 파싱(풀 격리 경계)."""
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.kis_db.smoke_state_restore",
         "--emit-db", dbname, "--capital", str(capital)],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"smoke child failed for {dbname}: {proc.stderr.strip()}")
    # 마지막 비어있지 않은 줄이 JSON 요약(로깅 라인이 앞에 섞여도 안전)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return json.loads(lines[-1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="상태복원 스모크(worktree 전용, READ-only)")
    ap.add_argument("--baseline-db", default="robotrader")
    ap.add_argument("--candidate-db", default="kis_template")
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    ap.add_argument("--emit-db", default=None,
                    help="자식 모드: 이 DB 로 run_smoke 후 JSON 요약만 출력하고 종료")
    args = ap.parse_args(argv)

    # 자식 모드: 단일 DB 요약을 JSON 으로 방출(부모가 파싱)
    if args.emit_db:
        summary = run_smoke(args.emit_db, args.capital)
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    # 부모 모드: 각 DB 를 별도 자식 프로세스로 격리 실행 후 대조
    baseline = _spawn_summary(args.baseline_db, args.capital)
    candidate = _spawn_summary(args.candidate_db, args.capital)
    result = compare_summaries(baseline, candidate)

    print(f"[baseline {args.baseline_db}] n_open={baseline['n_open']} "
          f"strategies={len(baseline['per_strategy_cash'])} candidates={len(baseline['candidate_codes'])}")
    print(f"[candidate {args.candidate_db}] n_open={candidate['n_open']} "
          f"strategies={len(candidate['per_strategy_cash'])} candidates={len(candidate['candidate_codes'])}")
    print(f"positions_match={result['open_positions_match']} "
          f"candidates_match={result['candidates_match']} "
          f"cash_max_abs_diff={result['cash_max_abs_diff']:.2f} "
          f"cash_match={result['cash_match']}")
    print(f"[SMOKE VERDICT] {result['verdict']}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/test_smoke_state_restore.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the live smoke in the worktree (requires B1 migration applied to kis_template)**

Prerequisite: Task 3 `--apply` has copied operational data into `kis_template` (so the candidate DB is populated). Then:

Run: `cd RoboTrader_template && PYTHONIOENCODING=utf-8 python -m scripts.kis_db.smoke_state_restore --baseline-db robotrader --candidate-db kis_template`
Expected: prints baseline/candidate lines with equal `n_open` and candidate counts, `cash_max_abs_diff` < 1.00, and `[SMOKE VERDICT] PASS`. If FAIL, do not proceed to cutover — investigate the divergence (this is the continuity gate). This command reads both DBs and writes to neither (StateRestorer runs against fakes).

- [ ] **Step 6: Full kis_db suite regression**

Run: `cd RoboTrader_template && python -m pytest tests/kis_db/ -v`
Expected: PASS (all Task 1-5 tests green together).

- [ ] **Step 7: Commit**

```bash
git add RoboTrader_template/scripts/kis_db/smoke_state_restore.py RoboTrader_template/tests/kis_db/test_smoke_state_restore.py
git commit -m "feat(kis_db): B3 StateRestorer equivalence smoke (kis_template vs robotrader baseline)"
```

---

## Self-Review

**1. Spec coverage** (design doc Phase A + Phase B, "첫 구현 범위"):

- Phase A schema parity (virtual_trading_records w/ source/is_test/tpsl/buy_record_id, real_trading_records + dynamic path, paper_trading_state, candidate_stocks, screener_snapshots jsonb) → Task 1. ✅
- Phase A promote paper_strategy_equity DDL from ad-hoc into schema → Task 2. ✅
- Phase A DELETE/retention 금지 → Global Constraints + all DDL is `IF NOT EXISTS`; no retention added. ✅
- B1 copy our rows only (VTR `source='kis_template'`, our real_trading_{instance}, paper_trading_state/candidate_stocks/screener_snapshots full), idempotent UPSERT, preserve PK, no DELETE → Task 3. ✅ Continuity core (open positions + cash reconstruction basis) preserved by copying full VTR history for our source + sequence bump.
- B2 daily vs robotrader_quant + minute vs robotrader, coverage + column presence (market_cap, trading_value) + value diffs, explainable-diff gate (split like 001130 acceptable) → Task 4. ✅
- B3 StateRestorer against TIMESCALE_DB=kis_template in isolated env, compare open positions / per-strategy cash ledger / candidates vs robotrader baseline → Task 5. ✅
- Worktree-only, no live-tree smoke → Global Constraints + Task 5 docstring/step warnings. ✅

Dynamic `real_trading_{instance}` path: covered indirectly — Task 1 ensures `real_trading_records` base exists (the `LIKE ... INCLUDING ALL` template that `TradingRepository.ensure_real_table` uses); Task 3 recreates each instance table on the target via the same `LIKE` before copying. No separate task needed. ✅

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N" placeholders. Every code/test/DDL step shows full content. The one prose caveat in Task 3 Step 3 (sequence-bump scope fix) is an explicit correction with the exact replacement code shown, not a placeholder. ✅

**3. Type consistency:**
- `migrate_table(...)` returns `{"table","source_rows","copied"}` — matches Task 3 test assertion exactly. ✅
- `classify_diff` return literals (`match`/`split_adjust`/`coverage_gap`/`unexplained`) consistent between impl, `build_equivalence_report` counts keys, and tests. Split detection is GENERAL near-integer-ratio (module constants `SPLIT_RATIO_MIN=2`/`SPLIT_RATIO_MAX=150` + explicit 2.5), NOT a fixed factor tuple — the old `SPLIT_FACTORS` constant is deleted and has no remaining reference. Verified against the 001130 1:11 split (`156500/14227 ≈ 11.0007`, within `11*tol` of integer 11 → `split_adjust`); random 1.23x stays `unexplained`. ✅
- `build_equivalence_report` returns `coverage`/`counts`/`verdict`/`unexplained_samples` — matches tests; `column_presence` added only by DB entry points (not asserted by pure tests). ✅
- `build_restore_summary` keys (`open_position_codes`/`n_open`/`per_strategy_cash`/`candidate_codes`) and `compare_summaries` keys (`open_positions_match`/`candidates_match`/`cash_max_abs_diff`/`cash_match`/`verdict`) consistent across impl + tests + `main`. ✅
- B3 DB isolation: each DB is read in its OWN subprocess (`--emit-db` child prints JSON; parent `_spawn_summary` parses it), NOT via in-process `close_all()`+env swap. This avoids the module-level `DatabaseConnection` singleton-pool rebind hazard (env must be set before first pool init). The pure `build_restore_summary`/`compare_summaries` unit tests are unaffected by this transport change. ✅
- Cash formula in B3 matches `paper_strategy_equity.replay_strategy_equity` / `get_strategy_trade_sums` live model (`COMMISSION_RATE`, `SECURITIES_TAX_RATE` from `config.constants`). ✅
- `PAPER_STRATEGY_EQUITY_DDL` produced by Task 2, consumed by `tools/paper_strategy_equity._ensure_table` and asserted in Task 2 test. ✅

Fixes applied inline during review: added the sequence-bump scope note in Task 3 Step 3; clarified `real_trading_{instance}` coverage in spec-coverage; noted `column_presence` is DB-only (not unit-asserted).

Post-review revisions (coordinator defect fixes): (1) Task 4 `classify_diff` replaced the fragile fixed `SPLIT_FACTORS` tuple with general near-integer-ratio detection (`SPLIT_RATIO_MIN=2`/`SPLIT_RATIO_MAX=150` + 2.5), so the verified 001130 1:11 split classifies as `split_adjust` instead of falsely failing the gate; added `test_classify_split_11x_explained` (both diff directions) and `test_classify_split_2_5x_explained`, updated the unexplained test comment, and refreshed the Task 4 `Produces` block. (2) Task 5 B3 smoke now isolates each DB in a separate subprocess (`--emit-db` child emits JSON, parent `_spawn_summary` parses) instead of in-process `DatabaseConnection.close_all()`+env swap — safer against the module-level singleton pool; docstring, imports (`json`/`subprocess`), `run_smoke`, and `main` updated accordingly.
