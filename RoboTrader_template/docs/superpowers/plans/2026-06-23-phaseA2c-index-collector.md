# Phase A2c — 지수 일봉 수집기 (KOSPI/KOSDAQ → kis_template) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** KOSPI/KOSDAQ 종합지수 일봉을 FinanceDataReader로 받아 `kis_template` DB `index_daily`에 적재한다(regime 게이트 의존 데이터의 드롭인).

**Architecture:** Phase A1 `KisDbConnection` + `index_daily` 테이블 위에 얹는다. 소스=FDR `KS11`(KOSPI)·`KQ11`(KOSDAQ), 기존 `scripts/backfill_kospi_index.py` 패턴 재사용. 멱등 UPSERT.

**Tech Stack:** Python 3.9, psycopg2, pandas, FinanceDataReader, PostgreSQL, pytest.

## Global Constraints

- 적재 대상: `kis_template.index_daily` (PK `(index_code, date)`). `date` TEXT `YYYY-MM-DD`.
- index_code: `KOSPI`(KS11), `KOSDAQ`(KQ11).
- 컬럼: index_code, date, open, high, low, close, volume.
- 멱등 UPSERT. 콘솔 한글 `PYTHONIOENCODING=utf-8 python -X utf8`.
- spec: `docs/superpowers/specs/2026-06-22-data-collection-migration-design.md`.

---

### Task 1: 지수 파서 + 새 DB UPSERT 라이터

**Files:**
- Create: `collectors/index_writer.py`
- Test: `tests/collectors/test_index_writer.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_connection()`
- Produces:
  - `fdr_df_to_index_rows(index_code, df) -> list[dict]` — FDR df(Date 인덱스, Open/High/Low/Close/Volume) → index_daily 행.
  - `upsert_index_rows(conn, rows) -> int` — `(index_code, date)` UPSERT.

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_index_writer.py
import pandas as pd
from collectors.index_writer import fdr_df_to_index_rows


def test_fdr_df_to_index_rows_maps_and_formats_date():
    df = pd.DataFrame(
        {"Open": [2500.0], "High": [2520.0], "Low": [2490.0], "Close": [2510.0], "Volume": [1.0e9]},
        index=pd.to_datetime(["2026-06-23"]),
    )
    rows = fdr_df_to_index_rows("KOSPI", df)
    assert rows == [{
        "index_code": "KOSPI", "date": "2026-06-23",
        "open": 2500.0, "high": 2520.0, "low": 2490.0, "close": 2510.0, "volume": 1.0e9,
    }]


def test_fdr_df_to_index_rows_empty():
    assert fdr_df_to_index_rows("KOSPI", pd.DataFrame()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_index_writer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/index_writer.py
"""FDR 지수 df → index_daily 행 + 새 DB UPSERT."""

_UPSERT = """
INSERT INTO index_daily (index_code, date, open, high, low, close, volume)
VALUES (%(index_code)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s)
ON CONFLICT (index_code, date) DO UPDATE SET
    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
    close=EXCLUDED.close, volume=EXCLUDED.volume
"""


def fdr_df_to_index_rows(index_code: str, df) -> list:
    if df is None or len(df) == 0:
        return []
    rows = []
    for idx, r in df.iterrows():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        rows.append({
            "index_code": index_code, "date": d,
            "open": float(r["Open"]), "high": float(r["High"]),
            "low": float(r["Low"]), "close": float(r["Close"]),
            "volume": float(r.get("Volume", 0) or 0),
        })
    return rows


def upsert_index_rows(conn, rows) -> int:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(_UPSERT, r)
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_index_writer.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add collectors/index_writer.py tests/collectors/test_index_writer.py
git commit -m "feat(collectors): 지수 파서 + index_daily UPSERT 라이터"
```

---

### Task 2: 지수 수집 오케스트레이터 + CLI

**Files:**
- Create: `collectors/index_collector.py`
- Test: `tests/collectors/test_index_collector.py`

**Interfaces:**
- Consumes: Task1 `fdr_df_to_index_rows`/`upsert_index_rows`, `KisDbConnection`, `FinanceDataReader`.
- Produces:
  - `INDEX_TICKERS: dict` — `{"KOSPI": "KS11", "KOSDAQ": "KQ11"}`.
  - `collect_index(start: str = None) -> dict` — 두 지수 FDR fetch→UPSERT. 반환 `{KOSPI: n, KOSDAQ: n}`.
  - CLI: `--start YYYY-MM-DD`(기본=최근 10일).

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_index_collector.py
from collectors.index_collector import INDEX_TICKERS


def test_index_tickers_map():
    assert INDEX_TICKERS == {"KOSPI": "KS11", "KOSDAQ": "KQ11"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_index_collector.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/index_collector.py
"""지수 일봉 수집 — FDR KS11/KQ11 → index_daily.

usage:
  python -m collectors.index_collector
  python -m collectors.index_collector --start 2026-06-01
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.index_writer import fdr_df_to_index_rows, upsert_index_rows  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)
INDEX_TICKERS = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}


def collect_index(start: str = None) -> dict:
    import FinanceDataReader as fdr
    if start is None:
        start = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
    result = {}
    with KisDbConnection.get_connection() as conn:
        for name, ticker in INDEX_TICKERS.items():
            df = fdr.DataReader(ticker, start)
            rows = fdr_df_to_index_rows(name, df)
            result[name] = upsert_index_rows(conn, rows)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    args = ap.parse_args()
    print(collect_index(args.start))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_index_collector.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 통합 수집·검증 (FDR 네트워크 필요)**

Run: `PYTHONIOENCODING=utf-8 python -X utf8 -m collectors.index_collector`
Expected: `{'KOSPI': >0, 'KOSDAQ': >0}`

검증:
```bash
PYTHONIOENCODING=utf-8 python -X utf8 -c "
from db.kis_db_connection import KisDbConnection
with KisDbConnection.get_connection() as c:
    cur=c.cursor(); cur.execute(\"select index_code, count(*), max(date) from index_daily group by index_code\"); print(cur.fetchall())
"
```
Expected: KOSPI/KOSDAQ 행수 > 0, 최신일 = 직전 거래일

- [ ] **Step 6: Commit**

```bash
git add collectors/index_collector.py tests/collectors/test_index_collector.py
git commit -m "feat(collectors): 지수 일봉 수집 오케스트레이터(FDR KS11/KQ11)"
```

---

## Self-Review (작성자 체크)

- **Spec 커버리지(지수)**: KOSPI/KOSDAQ 일봉 FDR 수집→index_daily 적재(드롭인). regime 게이트 의존 데이터 확보.
- **Placeholder 스캔**: 실제 코드·명령·기대출력. TODO 없음.
- **타입 일관성**: `fdr_df_to_index_rows(index_code, df)->list[dict]`·`upsert_index_rows(conn, rows)->int`(Task1) → Task2 `collect_index` 사용. `INDEX_TICKERS` 테스트·구현 일치.
