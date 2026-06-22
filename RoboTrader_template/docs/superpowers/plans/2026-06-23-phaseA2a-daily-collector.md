# Phase A2a — 일봉 수집기 (kis_template DB 적재) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전체시장(~2,601종목) 일봉을 KIS에서 받아 `kis_template` DB `daily_prices`에 적재(OHLCV+trading_value+market_cap)하고, 파생(returns/volatility)·adj_factor를 채우는 일봉 수집기 + 교차 DB 비교(일봉)를 구축한다.

**Architecture:** Phase A1의 `KisDbConnection`(새 DB)·시딩된 `daily_prices`/`corp_events` 위에 얹는다. KIS `get_inquire_daily_itemchartprice`(FHKST03010100)로 당일 일봉을, `get_stock_market_cap`로 시총을 받아 새 DB에 UPSERT한다. 파생은 기존 `SQL_UPDATE_RETURNS`(윈도우 함수)를 새 DB에 실행, adj_factor는 기존 `compute_adj_factors`(corp_events 기반)를 재사용한다. 수집은 항상 새 DB에 쓰고(드롭인), 읽기 경로 전환은 후속(A2 훅 계획)의 `KIS_DATA_SOURCE`가 제어한다.

**Tech Stack:** Python 3.9, psycopg2, pandas, KIS REST API, PostgreSQL(localhost:5433), pytest.

## Global Constraints

- 적재 대상 DB: `kis_template` (Phase A1 `KisDbConnection`). 절대 레거시(robotrader_quant)에 쓰지 않는다.
- `daily_prices.date`는 **TEXT**, 형식 `YYYY-MM-DD`. close는 KIS 수정주가가 아닌 **원주가 흐름이라도 레거시와 동일 규약 유지**(adj_prc 기본 "1"=원주가; 레거시 동일값 사용, adj_factor 별도 컬럼). PK `(stock_code, date)`.
- KIS 일봉 output2 필드: `stck_bsop_date`(YYYYMMDD)·`stck_clpr`(종가)·`stck_oprc`(시가)·`stck_hgpr`(고가)·`stck_lwpr`(저가)·`acml_vol`(거래량)·`acml_tr_pbmn`(거래대금).
- market_cap = `close × listed_shares`, `listed_shares = get_stock_market_cap(code)['market_cap'] / current_price` (rt_quant 동일). 시총 미확보 종목은 market_cap NULL 허용.
- 모든 적재 멱등(UPSERT). 파생/adj는 재실행 안전.
- 콘솔 한글: `PYTHONIOENCODING=utf-8 python -X utf8`.
- spec: `docs/superpowers/specs/2026-06-22-data-collection-migration-design.md` (Phase A).

---

### Task 1: 일봉 파서 + 새 DB UPSERT 라이터

**Files:**
- Create: `collectors/__init__.py` (빈 파일)
- Create: `collectors/daily_writer.py`
- Test: `tests/collectors/test_daily_writer.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_connection()` (Phase A1, `db/kis_db_connection.py`)
- Produces:
  - `parse_kis_daily_row(item: dict, market_cap: float | None) -> dict | None` — KIS output2 1건 → `{stock_code?, date, open, high, low, close, volume, trading_value, market_cap}` (stock_code는 호출측이 주입하므로 여기선 OHLCV+date만; 잘못된/0 종가는 None).
  - `DAILY_UPSERT_SQL: str`
  - `upsert_daily_rows(conn, rows: list[dict]) -> int` — `(stock_code, date)` 충돌 시 OHLCV·trading_value·market_cap 갱신. 반환=처리 행수.

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_daily_writer.py
from collectors.daily_writer import parse_kis_daily_row


def test_parse_converts_yyyymmdd_to_dash_date_and_casts():
    item = {
        "stck_bsop_date": "20260623", "stck_clpr": "70500", "stck_oprc": "70000",
        "stck_hgpr": "71000", "stck_lwpr": "69000", "acml_vol": "1234567",
        "acml_tr_pbmn": "88000000000",
    }
    row = parse_kis_daily_row(item, market_cap=4.2e14)
    assert row["date"] == "2026-06-23"
    assert row["open"] == 70000.0
    assert row["high"] == 71000.0
    assert row["low"] == 69000.0
    assert row["close"] == 70500.0
    assert row["volume"] == 1234567
    assert row["trading_value"] == 88000000000
    assert row["market_cap"] == 4.2e14


def test_parse_returns_none_on_zero_close():
    item = {"stck_bsop_date": "20260623", "stck_clpr": "0", "stck_oprc": "0",
            "stck_hgpr": "0", "stck_lwpr": "0", "acml_vol": "0", "acml_tr_pbmn": "0"}
    assert parse_kis_daily_row(item, market_cap=None) is None


def test_parse_allows_null_market_cap():
    item = {"stck_bsop_date": "20260623", "stck_clpr": "100", "stck_oprc": "100",
            "stck_hgpr": "100", "stck_lwpr": "100", "acml_vol": "10", "acml_tr_pbmn": "1000"}
    row = parse_kis_daily_row(item, market_cap=None)
    assert row["market_cap"] is None
    assert row["close"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_daily_writer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collectors.daily_writer'`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/daily_writer.py
"""KIS 일봉 output2 파싱 + kis_template daily_prices UPSERT."""
from typing import Optional


def _f(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _i(v) -> int:
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def parse_kis_daily_row(item: dict, market_cap: Optional[float]) -> Optional[dict]:
    """KIS FHKST03010100 output2 1건 → daily_prices 행 dict. 0/결측 종가는 None."""
    close = _f(item.get("stck_clpr"))
    if close <= 0:
        return None
    raw_date = str(item.get("stck_bsop_date", ""))
    if len(raw_date) != 8:
        return None
    return {
        "date": f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}",
        "open": _f(item.get("stck_oprc")),
        "high": _f(item.get("stck_hgpr")),
        "low": _f(item.get("stck_lwpr")),
        "close": close,
        "volume": _i(item.get("acml_vol")),
        "trading_value": _i(item.get("acml_tr_pbmn")),
        "market_cap": float(market_cap) if market_cap is not None else None,
    }


DAILY_UPSERT_SQL = """
INSERT INTO daily_prices
    (stock_code, date, open, high, low, close, volume, trading_value, market_cap, updated_at)
VALUES (%(stock_code)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s,
        %(volume)s, %(trading_value)s, %(market_cap)s, now())
ON CONFLICT (stock_code, date) DO UPDATE SET
    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
    volume=EXCLUDED.volume, trading_value=EXCLUDED.trading_value,
    market_cap=COALESCE(EXCLUDED.market_cap, daily_prices.market_cap),
    updated_at=now()
"""


def upsert_daily_rows(conn, rows) -> int:
    """rows: [{stock_code, date, open, high, low, close, volume, trading_value, market_cap}]."""
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(DAILY_UPSERT_SQL, r)
            n += 1
    conn.commit()
    return n
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_daily_writer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add collectors/__init__.py collectors/daily_writer.py tests/collectors/test_daily_writer.py
git commit -m "feat(collectors): 일봉 파서 + kis_template daily_prices UPSERT 라이터"
```

---

### Task 2: 파생(returns/volatility) 갱신 — 새 DB 대상

**Files:**
- Create: `collectors/daily_derived.py`
- Test: `tests/collectors/test_daily_derived.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_connection()`; 기존 `scripts.etl_backfill_daily_prices.SQL_UPDATE_RETURNS`(검증된 윈도우 함수 SQL — `daily_prices`를 미한정 참조하므로 연결된 DB 대상으로 실행됨).
- Produces: `update_returns_volatility(conn) -> None` — 새 DB `daily_prices` 전체에 returns_1d/5d/20d·volatility_20d 재계산.

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_daily_derived.py
from collectors.daily_derived import update_returns_volatility
from scripts.etl_backfill_daily_prices import SQL_UPDATE_RETURNS


def test_uses_canonical_returns_sql():
    # 동일 SQL을 재사용(중복 정의 금지)
    import collectors.daily_derived as m
    assert m.SQL_UPDATE_RETURNS is SQL_UPDATE_RETURNS


class _Cur:
    def __init__(self): self.sql = None
    def execute(self, sql): self.sql = sql
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Conn:
    def __init__(self): self.cur = _Cur(); self.committed = False
    def cursor(self): return self.cur
    def commit(self): self.committed = True


def test_update_runs_sql_and_commits():
    c = _Conn()
    update_returns_volatility(c)
    assert "UPDATE daily_prices" in c.cur.sql
    assert c.committed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_daily_derived.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/daily_derived.py
"""파생(returns/volatility) 갱신 — 검증된 SQL_UPDATE_RETURNS 재사용, 새 DB 대상 실행."""
from scripts.etl_backfill_daily_prices import SQL_UPDATE_RETURNS


def update_returns_volatility(conn) -> None:
    """연결된 DB의 daily_prices 전체에 returns_1d/5d/20d·volatility_20d 재계산."""
    with conn.cursor() as cur:
        cur.execute(SQL_UPDATE_RETURNS)
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_daily_derived.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add collectors/daily_derived.py tests/collectors/test_daily_derived.py
git commit -m "feat(collectors): 파생 returns/volatility 갱신(SQL_UPDATE_RETURNS 재사용)"
```

---

### Task 3: adj_factor 갱신 — corp_events 기반(새 DB)

**Files:**
- Create: `collectors/daily_adj.py`
- Test: `tests/collectors/test_daily_adj.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_connection()`; 기존 `scripts.10pct_strategy.p0_apply_adj_factor.compute_adj_factors`(순수 함수: `(events, stock_dates) -> {stock: {date: factor}}`, PIT 규칙=미래 분할만 과거가에 적용).
- Produces:
  - `load_split_events(conn) -> dict` — 새 DB `corp_events`에서 `{stock_code: [(event_date: date, split_factor: float), ...]}`(오름차순).
  - `load_stock_dates(conn, stock_codes: list[str]) -> dict` — `{stock_code: [date_str, ...]}`.
  - `update_adj_factors(conn) -> int` — 분할 이벤트 보유 종목의 daily_prices.adj_factor 갱신, 반환=갱신 행수.

설명: 기존 `p0_apply_adj_factor`는 모듈 import 시 자체 DB(robotrader_quant)에 붙으므로, **순수 함수 `compute_adj_factors`만 재사용**하고 로드/쓰기는 새 DB 연결로 새로 구현한다(중복 SQL 아님 — 대상 DB가 다름).

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_daily_adj.py
from datetime import date
from collectors.daily_adj import _adj_update_rows


def test_adj_update_rows_only_nonunity_factors():
    # compute 결과 {stock: {date: factor}} → (factor, stock, date) 중 factor!=1.0만
    adj_map = {"A": {"2022-01-03": 5.0, "2022-05-02": 1.0}}
    rows = _adj_update_rows(adj_map)
    assert rows == [(5.0, "A", "2022-01-03")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_daily_adj.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/daily_adj.py
"""adj_factor 갱신 — corp_events 분할이벤트 기반(새 DB). compute_adj_factors 재사용."""
import importlib

import psycopg2.extras

# p0_apply_adj_factor 는 패키지 경로에 숫자 시작 디렉토리(10pct_strategy)라 importlib 사용
_p0 = importlib.import_module("scripts.10pct_strategy.p0_apply_adj_factor")
compute_adj_factors = _p0.compute_adj_factors


def load_split_events(conn) -> dict:
    """새 DB corp_events 에서 split_factor 보유 분할이벤트 로드."""
    from collections import defaultdict
    events = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_code, event_date, (meta->>'split_factor')::float "
            "FROM corp_events "
            "WHERE event_type = 'split' AND meta->>'split_factor' IS NOT NULL "
            "ORDER BY stock_code, event_date"
        )
        for stock_code, event_date, sf in cur.fetchall():
            events[stock_code].append((event_date, float(sf)))
    return dict(events)


def load_stock_dates(conn, stock_codes) -> dict:
    """대상 종목들의 daily_prices 날짜 목록."""
    if not stock_codes:
        return {}
    out = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_code, date FROM daily_prices WHERE stock_code = ANY(%s) ORDER BY date",
            (list(stock_codes),),
        )
        for sc, d in cur.fetchall():
            out.setdefault(sc, []).append(d)
    return out


def _adj_update_rows(adj_map: dict):
    """{stock: {date: factor}} → [(factor, stock, date)] (factor != 1.0 만)."""
    rows = []
    for sc, date_adj in adj_map.items():
        for ds, af in date_adj.items():
            if abs(af - 1.0) > 1e-9:
                rows.append((af, sc, ds))
    return rows


def update_adj_factors(conn) -> int:
    events = load_split_events(conn)
    if not events:
        return 0
    stock_dates = load_stock_dates(conn, list(events.keys()))
    adj_map = compute_adj_factors(events, stock_dates)
    rows = _adj_update_rows(adj_map)
    if not rows:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur,
            "UPDATE daily_prices SET adj_factor = %s, updated_at = now() "
            "WHERE stock_code = %s AND date = %s",
            rows, page_size=1000,
        )
    conn.commit()
    return len(rows)
```

> 주의: `compute_adj_factors`의 `stock_dates` 날짜 키 타입(문자열 vs date)이 `load_stock_dates` 반환과 일치해야 한다. 기존 p0는 `date_str`(문자열)을 쓰므로, `load_stock_dates`가 TEXT `date`를 그대로(문자열) 반환하면 정합. 구현 후 Step 5 통합검증에서 실제 스팟체크로 확인한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_daily_adj.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 통합 스팟체크(실제 새 DB)**

Run:
```bash
PYTHONIOENCODING=utf-8 python -X utf8 -c "
from db.kis_db_connection import KisDbConnection
from collectors.daily_adj import update_adj_factors
with KisDbConnection.get_connection() as c:
    print('adj rows updated:', update_adj_factors(c))
    cur=c.cursor(); cur.execute(\"select count(*) from daily_prices where adj_factor is not null and adj_factor<>1.0\"); print('non-unity adj rows:', cur.fetchone()[0])
"
```
Expected: 갱신 행수 > 0, non-unity adj rows > 0 (시딩된 corp_events 분할 종목 존재 시). 0이면 corp_events에 split 이벤트 없는지 확인.

- [ ] **Step 6: Commit**

```bash
git add collectors/daily_adj.py tests/collectors/test_daily_adj.py
git commit -m "feat(collectors): adj_factor 갱신(corp_events 분할, compute_adj_factors 재사용)"
```

---

### Task 4: 일봉 수집 오케스트레이터 + CLI + 교차비교(일봉)

**Files:**
- Create: `collectors/daily_collector.py`
- Test: `tests/collectors/test_daily_collector.py`

**Interfaces:**
- Consumes: Task 1 `parse_kis_daily_row`/`upsert_daily_rows`, Task 2 `update_returns_volatility`, Task 3 `update_daily_adj`(=`update_adj_factors`), `KisDbConnection`, `api.kis_market_api.get_inquire_daily_itemchartprice`/`get_stock_market_cap`.
- Produces:
  - `load_universe(conn) -> list[str]` — 새 DB `daily_prices`의 distinct stock_code(시딩분, ~2,601). (전종목 마스터 = 시딩된 유니버스)
  - `collect_one(code, lookback_days) -> list[dict]` — 한 종목 일봉 fetch+파싱(stock_code 주입, market_cap 1회 조회 재사용).
  - `collect_daily(target_date, limit=None) -> dict` — 전체 수집→UPSERT→파생→adj. 반환 `{codes, rows, derived, adj}`.
  - `reconcile_daily(trade_date) -> dict` — 새 DB vs 레거시(robotrader_quant) 당일 행 비교 → `collection_reconciliation` 기록 + 반환 요약.
  - CLI: `--limit N`(소수 테스트), `--reconcile-only DATE`, `--date YYYYMMDD`.

- [ ] **Step 1: Write the failing test (순수 로직: reconcile 판정)**

```python
# tests/collectors/test_daily_collector.py
from collectors.daily_collector import reconcile_verdict


def test_reconcile_verdict_pass_when_full_coverage_and_match():
    v = reconcile_verdict(real_rows=2600, new_rows=2600, value_match=2598)
    assert v["coverage"] >= 0.99
    assert v["value_match_rate"] >= 0.99
    assert v["verdict"] == "PASS"


def test_reconcile_verdict_fail_on_low_coverage():
    v = reconcile_verdict(real_rows=2600, new_rows=1500, value_match=1500)
    assert v["verdict"] == "FAIL"


def test_reconcile_verdict_handles_zero_real():
    v = reconcile_verdict(real_rows=0, new_rows=0, value_match=0)
    assert v["verdict"] in ("PASS", "EMPTY")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_daily_collector.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/daily_collector.py
"""일봉 수집 오케스트레이터 — KIS fetch → kis_template UPSERT → 파생 → adj → 교차비교.

usage:
  python -m collectors.daily_collector --limit 5            # 소수 dry-ish 수집
  python -m collectors.daily_collector                      # 전종목 수집
  python -m collectors.daily_collector --reconcile-only 2026-06-23
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.daily_writer import parse_kis_daily_row, upsert_daily_rows  # noqa: E402
from collectors.daily_derived import update_returns_volatility  # noqa: E402
from collectors.daily_adj import update_adj_factors  # noqa: E402
from api import kis_market_api  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)
COVERAGE_MIN = 0.99
VALUE_MATCH_MIN = 0.99


def load_universe(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT stock_code FROM daily_prices WHERE stock_code ~ '^[0-9]{6}$' ORDER BY stock_code")
        return [r[0] for r in cur.fetchall()]


def collect_one(code: str, lookback_days: int = 7) -> list:
    """한 종목 최근 일봉 fetch+파싱 (market_cap 1회 조회 재사용)."""
    df = kis_market_api.get_inquire_daily_itemchartprice(output_dv="2", div_code="J", itm_no=code)
    if df is None or df.empty:
        return []
    mc = kis_market_api.get_stock_market_cap(code)
    market_cap = None
    if mc and mc.get("current_price"):
        shares = mc["market_cap"] / mc["current_price"] if mc["current_price"] else 0
        # per-row market_cap은 close*shares 로 daily_collector가 보정(여기선 shares 전달용)
        market_cap = shares
    rows = []
    for _, item in df.iterrows():
        parsed = parse_kis_daily_row(dict(item), market_cap=None)
        if parsed is None:
            continue
        parsed["stock_code"] = code
        parsed["market_cap"] = (parsed["close"] * market_cap) if market_cap else None
        rows.append(parsed)
    return rows[-lookback_days:] if lookback_days else rows


def collect_daily(target_date: str = None, limit: int = None) -> dict:
    with KisDbConnection.get_connection() as conn:
        codes = load_universe(conn)
        if limit:
            codes = codes[:limit]
        total = 0
        for code in codes:
            rows = collect_one(code)
            if rows:
                total += upsert_daily_rows(conn, rows)
        update_returns_volatility(conn)
        adj = update_adj_factors(conn)
    return {"codes": len(codes), "rows": total, "adj": adj}


def reconcile_verdict(real_rows: int, new_rows: int, value_match: int) -> dict:
    if real_rows == 0 and new_rows == 0:
        return {"coverage": 1.0, "value_match_rate": 1.0, "verdict": "EMPTY"}
    coverage = new_rows / real_rows if real_rows else 0.0
    value_match_rate = value_match / new_rows if new_rows else 0.0
    verdict = "PASS" if coverage >= COVERAGE_MIN and value_match_rate >= VALUE_MATCH_MIN else "FAIL"
    return {"coverage": coverage, "value_match_rate": value_match_rate, "verdict": verdict}


def reconcile_daily(trade_date: str) -> dict:
    """새 DB vs 레거시(robotrader_quant) 당일 일봉 비교 + collection_reconciliation 기록."""
    legacy = psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"), port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname="robotrader_quant", user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "1234"))
    try:
        with legacy.cursor() as lc:
            lc.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (trade_date,))
            real_rows = lc.fetchone()[0]
        with KisDbConnection.get_connection() as conn:
            with conn.cursor() as nc:
                nc.execute("SELECT count(*) FROM daily_prices WHERE date = %s", (trade_date,))
                new_rows = nc.fetchone()[0]
            # 교집합 종가 일치 수 (cross-DB라 새DB 행을 끌어와 레거시와 대조)
            with conn.cursor() as nc:
                nc.execute("SELECT stock_code, close FROM daily_prices WHERE date = %s", (trade_date,))
                new_closes = dict(nc.fetchall())
            value_match = 0
            with legacy.cursor() as lc:
                lc.execute("SELECT stock_code, close FROM daily_prices WHERE date = %s", (trade_date,))
                for sc, close in lc.fetchall():
                    if sc in new_closes and new_closes[sc] is not None and close is not None \
                       and abs(float(new_closes[sc]) - float(close)) < 0.5:
                        value_match += 1
            v = reconcile_verdict(real_rows, new_rows, value_match)
            with conn.cursor() as nc:
                nc.execute(
                    "INSERT INTO collection_reconciliation "
                    "(trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict) "
                    "VALUES (%s,'daily',%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (trade_date, dataset) DO UPDATE SET "
                    "real_rows=EXCLUDED.real_rows, new_rows=EXCLUDED.new_rows, overlap=EXCLUDED.overlap, "
                    "value_match_rate=EXCLUDED.value_match_rate, coverage=EXCLUDED.coverage, verdict=EXCLUDED.verdict",
                    (trade_date, real_rows, new_rows, value_match, v["value_match_rate"], v["coverage"], v["verdict"]))
            conn.commit()
        v.update({"trade_date": trade_date, "real_rows": real_rows, "new_rows": new_rows, "value_match": value_match})
        return v
    finally:
        legacy.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--reconcile-only", default=None)
    args = ap.parse_args()
    if args.reconcile_only:
        print(reconcile_daily(args.reconcile_only))
    else:
        print(collect_daily(args.date, args.limit))
```

> 설계 메모: `collect_one`의 market_cap은 현재가 기준 listed_shares를 close에 곱해 per-row 시총을 만든다(rt_quant 동일). `parse_kis_daily_row`에는 market_cap=None을 넘기고 호출측이 보정한다(파서는 순수 유지).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_daily_collector.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 통합 수집(소수)·교차비교 검증**

Run(소수 5종목 수집):
`PYTHONIOENCODING=utf-8 python -X utf8 -m collectors.daily_collector --limit 5`
Expected: `{'codes': 5, 'rows': >0, 'adj': >=0}`

Run(직전 거래일 교차비교 — 시딩으로 양쪽에 데이터 있는 날짜, 예 2026-06-22):
`PYTHONIOENCODING=utf-8 python -X utf8 -m collectors.daily_collector --reconcile-only 2026-06-22`
Expected: `verdict=PASS`(시딩 직후라 new==legacy), `coverage≈1.0`, `value_match_rate≈1.0`

- [ ] **Step 6: 전체 테스트 + Commit**

Run: `python -m pytest tests/collectors/ -v`
Expected: 전부 PASS

```bash
git add collectors/daily_collector.py tests/collectors/test_daily_collector.py
git commit -m "feat(collectors): 일봉 수집 오케스트레이터 + CLI + 교차비교(일봉)"
```

---

## Self-Review (작성자 체크)

- **Spec 커버리지(Phase A 일봉)**: 전종목 일봉 fetch(Task4 collect_one/load_universe)·OHLCV+trading_value+market_cap 적재(Task1)·파생(Task2)·adj_factor(Task3)·교차비교+기록(Task4 reconcile_daily) — Phase A 일봉 드롭인 완료. 분봉/지수/EOD훅/읽기경로전환은 후속 A2 서브계획(아래).
- **Placeholder 스캔**: 모든 스텝에 실제 코드·명령·기대출력. TODO 없음. adj 날짜키 타입 정합은 Step5 통합 스팟체크로 명시 검증(미해결 아님).
- **타입 일관성**: Task1 `parse_kis_daily_row(item, market_cap)->dict|None`·`upsert_daily_rows(conn, rows)->int` → Task4에서 동일 사용. Task2 `update_returns_volatility(conn)`·Task3 `update_adj_factors(conn)->int` → Task4 collect_daily에서 호출. reconcile_verdict 반환 키(coverage/value_match_rate/verdict) = 테스트·DB 기록 일치.
- **재사용**: `SQL_UPDATE_RETURNS`(Task2)·`compute_adj_factors`(Task3)는 기존 검증 자산 직접 재사용(중복 정의 아님, 대상 DB만 새 DB).

## 다음 A2 서브계획 (별도 문서)
- `phaseA2b-minute-collector`: 거래대금순 top300(get_volume_rank) + 당일 분봉(FHKST03010230 4구간) → 새 DB minute_candles + 교집합 교차비교.
- `phaseA2c-index-collector`: KOSPI/KOSDAQ 지수 일봉(FDR) → index_daily.
- `phaseA2d-eod-hook-and-source-flag`: `system_monitor._handle_postmarket_tasks`에 `_run_data_collection`(daily→minute→index→reconcile, asyncio.to_thread) + `KIS_DATA_SOURCE`(legacy|new) 읽기경로 전환(quant_daily_reader 등).
