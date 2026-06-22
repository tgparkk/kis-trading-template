# Phase A2b — 분봉 수집기 (kis_template DB 적재) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 거래대금순 top300 종목의 당일 전체 분봉을 KIS에서 받아 `kis_template` DB `minute_candles`에 적재하고, 교차 DB 비교(교집합 바 단위 일치)를 구축한다.

**Architecture:** Phase A1 `KisDbConnection` + A2a `reconcile_verdict` 재사용. 유니버스=`get_volume_rank`(거래대금순, 6가격밴드×2시장=12콜)로 top300, 분봉=`get_full_trading_day_data`(FHKST03010230, 4구간/종목)로 당일 전체. 멱등 DELETE+INSERT.

**Tech Stack:** Python 3.9, psycopg2, pandas, KIS REST API, PostgreSQL, pytest.

## Global Constraints

- 적재 대상: `kis_template.minute_candles` (PK `(stock_code, trade_date, idx)`). 레거시(robotrader)에 쓰지 않음.
- minute_candles 컬럼: stock_code, trade_date(YYYYMMDD), idx(0..N 정렬순), date(YYYYMMDD), time(HHMMSS), close, open, high, low, volume, amount, datetime.
- `get_full_trading_day_data(code, target_date, selected_time)` 반환 df 컬럼: `date`(YYYYMMDD str), `time`(HHMMSS str), `open/high/low/close`, `volume`, `amount`, `datetime`(Timestamp). 시간 오름차순 정렬됨.
- `get_volume_rank` 반환 종목코드 컬럼 = `mksc_shrn_iscd`. 거래대금순 = `fid_blng_cls_code="3"`. 콜당 최대 30건.
- 우선주 제외(코드 끝자리 '5'). top300 dedup.
- 멱등(종목·일자 DELETE 후 INSERT). 콘솔 한글 `PYTHONIOENCODING=utf-8 python -X utf8`.
- spec: `docs/superpowers/specs/2026-06-22-data-collection-migration-design.md`.

---

### Task 1: 분봉 유니버스 선정 (거래대금순 top300)

**Files:**
- Create: `collectors/minute_universe.py`
- Test: `tests/collectors/test_minute_universe.py`

**Interfaces:**
- Consumes: `api.kis_market_api.get_volume_rank`
- Produces:
  - `PRICE_BANDS: list[tuple[str,str]]` — 6개 `(low, high)` 가격밴드(문자열).
  - `parse_rank_codes(df) -> list[str]` — volume_rank df → 종목코드 리스트(우선주 '5' 제외, 6자리만).
  - `select_top_volume(top_n=300) -> list[str]` — 6밴드×2시장 호출→대금순 누적→dedup→top_n.

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_minute_universe.py
import pandas as pd
from collectors.minute_universe import parse_rank_codes, PRICE_BANDS


def test_price_bands_are_six():
    assert len(PRICE_BANDS) == 6


def test_parse_rank_codes_filters_preferred_and_nonsix():
    df = pd.DataFrame([
        {"mksc_shrn_iscd": "005930"},   # ok
        {"mksc_shrn_iscd": "005935"},   # 우선주(끝 5) 제외
        {"mksc_shrn_iscd": "12345"},    # 5자리 제외
        {"mksc_shrn_iscd": "000660"},   # ok
    ])
    assert parse_rank_codes(df) == ["005930", "000660"]


def test_parse_rank_codes_handles_empty():
    assert parse_rank_codes(pd.DataFrame()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_minute_universe.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/minute_universe.py
"""분봉 유니버스 — 거래대금순(fid_blng_cls_code=3) top300, 6가격밴드×2시장."""
import time
from api import kis_market_api

PRICE_BANDS = [
    ("5000", "15000"), ("15000", "30000"), ("30000", "60000"),
    ("60000", "120000"), ("120000", "250000"), ("250000", "500000"),
]
MARKETS = ["0001", "1001"]  # KOSPI, KOSDAQ


def parse_rank_codes(df) -> list:
    if df is None or len(df) == 0:
        return []
    out = []
    for _, row in df.iterrows():
        code = str(row.get("mksc_shrn_iscd", "")).strip()
        if len(code) == 6 and code.isdigit() and not code.endswith("5"):
            out.append(code)
    return out


def select_top_volume(top_n: int = 300) -> list:
    """거래대금순으로 6밴드×2시장 수집→등장순(=대금상위) dedup→top_n."""
    seen = []
    seen_set = set()
    for market in MARKETS:
        for lo, hi in PRICE_BANDS:
            df = kis_market_api.get_volume_rank(
                fid_input_iscd=market, fid_div_cls_code="1",
                fid_blng_cls_code="3", fid_input_price_1=lo, fid_input_price_2=hi)
            for code in parse_rank_codes(df):
                if code not in seen_set:
                    seen_set.add(code); seen.append(code)
            time.sleep(0.08)
    return seen[:top_n]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_minute_universe.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 통합 확인 (실제 유니버스 — 인증 필요)**

Run: `PYTHONIOENCODING=utf-8 python -X utf8 -c "from collectors.minute_universe import select_top_volume; u=select_top_volume(); print('universe', len(u), u[:5])"`
Expected: ~수백 종목(장중/직후 데이터 의존), 6자리·끝자리 '5' 없음. (KIS 인증 없으면 이 스텝 보류 — 단위테스트로 충분히 검증됨)

- [ ] **Step 6: Commit**

```bash
git add collectors/minute_universe.py tests/collectors/test_minute_universe.py
git commit -m "feat(collectors): 분봉 유니버스(거래대금순 top300)"
```

---

### Task 2: 분봉 파서 + 새 DB DELETE+INSERT 라이터

**Files:**
- Create: `collectors/minute_writer.py`
- Test: `tests/collectors/test_minute_writer.py`

**Interfaces:**
- Consumes: `KisDbConnection.get_connection()`
- Produces:
  - `df_to_minute_rows(code, df) -> list[dict]` — get_full_trading_day_data df → minute_candles 행(idx=정렬순 0..N).
  - `replace_minute_day(conn, code, trade_date, rows) -> int` — `(stock_code, trade_date)` DELETE 후 INSERT(멱등). 반환=행수.

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_minute_writer.py
import pandas as pd
from collectors.minute_writer import df_to_minute_rows


def test_df_to_minute_rows_builds_idx_and_fields():
    df = pd.DataFrame([
        {"date": "20260623", "time": "090100", "open": 100.0, "high": 101.0,
         "low": 99.0, "close": 100.5, "volume": 10.0, "amount": 1000.0},
        {"date": "20260623", "time": "090200", "open": 100.5, "high": 102.0,
         "low": 100.0, "close": 101.5, "volume": 20.0, "amount": 2000.0},
    ])
    rows = df_to_minute_rows("005930", df)
    assert len(rows) == 2
    assert rows[0]["stock_code"] == "005930"
    assert rows[0]["trade_date"] == "20260623"
    assert rows[0]["idx"] == 0
    assert rows[1]["idx"] == 1
    assert rows[0]["time"] == "090100"
    assert rows[1]["close"] == 101.5


def test_df_to_minute_rows_empty():
    assert df_to_minute_rows("005930", pd.DataFrame()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_minute_writer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/minute_writer.py
"""분봉 df → minute_candles 행 + 새 DB 멱등 적재(DELETE+INSERT)."""
import pandas as pd

_INSERT = """
INSERT INTO minute_candles
    (stock_code, trade_date, idx, date, time, close, open, high, low, volume, amount, datetime)
VALUES (%(stock_code)s, %(trade_date)s, %(idx)s, %(date)s, %(time)s, %(close)s, %(open)s,
        %(high)s, %(low)s, %(volume)s, %(amount)s, %(datetime)s)
ON CONFLICT (stock_code, trade_date, idx) DO NOTHING
"""


def df_to_minute_rows(code: str, df) -> list:
    if df is None or len(df) == 0:
        return []
    rows = []
    for idx, (_, r) in enumerate(df.iterrows()):
        d = str(r.get("date", ""))
        dt = r.get("datetime")
        rows.append({
            "stock_code": code,
            "trade_date": d,
            "idx": idx,
            "date": d,
            "time": str(r.get("time", "")),
            "close": float(r.get("close", 0) or 0),
            "open": float(r.get("open", 0) or 0),
            "high": float(r.get("high", 0) or 0),
            "low": float(r.get("low", 0) or 0),
            "volume": float(r.get("volume", 0) or 0),
            "amount": float(r.get("amount", 0) or 0),
            "datetime": (dt.to_pydatetime() if isinstance(dt, pd.Timestamp) else None),
        })
    return rows


def replace_minute_day(conn, code: str, trade_date: str, rows) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM minute_candles WHERE stock_code=%s AND trade_date=%s",
                    (code, trade_date))
        for r in rows:
            cur.execute(_INSERT, r)
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_minute_writer.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add collectors/minute_writer.py tests/collectors/test_minute_writer.py
git commit -m "feat(collectors): 분봉 파서 + minute_candles DELETE+INSERT 라이터"
```

---

### Task 3: 분봉 수집 오케스트레이터 + CLI + 교차비교(교집합)

**Files:**
- Create: `collectors/minute_collector.py`
- Test: `tests/collectors/test_minute_collector.py`

**Interfaces:**
- Consumes: Task1 `select_top_volume`, Task2 `df_to_minute_rows`/`replace_minute_day`, `KisDbConnection`, `api.kis_chart_api.get_full_trading_day_data`, A2a `collectors.daily_collector.reconcile_verdict`.
- Produces:
  - `collect_minute(target_date=None, top_n=300, limit=None) -> dict` — 유니버스 수집→종목별 fetch→적재. 반환 `{codes, rows}`.
  - `reconcile_minute(trade_date) -> dict` — 새 DB vs 레거시(robotrader) minute_candles **교집합 종목**의 바 일치율 → `collection_reconciliation`(dataset='minute') 기록.
  - CLI: `--limit N`, `--date YYYYMMDD`, `--reconcile-only DATE`.

- [ ] **Step 1: Write the failing test (교집합 일치율 판정)**

```python
# tests/collectors/test_minute_collector.py
from collectors.minute_collector import minute_match_rate


def test_minute_match_rate_on_intersection():
    # 교집합 종목만, 바 일치 비율
    new = {"A": {("090100", 100.0), ("090200", 101.0)},
           "B": {("090100", 50.0)}}
    legacy = {"A": {("090100", 100.0), ("090200", 101.0)},
              "C": {("090100", 9.0)}}
    rate, overlap = minute_match_rate(new, legacy)
    # 교집합 종목 = {A}; A 바 2개 모두 일치 → 1.0
    assert overlap == 1
    assert rate == 1.0


def test_minute_match_rate_no_overlap():
    rate, overlap = minute_match_rate({"A": set()}, {"B": set()})
    assert overlap == 0
    assert rate == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/collectors/test_minute_collector.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# collectors/minute_collector.py
"""분봉 수집 오케스트레이터 — top300 → 당일 분봉 fetch → minute_candles → 교차비교.

usage:
  python -m collectors.minute_collector --limit 5
  python -m collectors.minute_collector
  python -m collectors.minute_collector --reconcile-only 20260623
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.minute_universe import select_top_volume  # noqa: E402
from collectors.minute_writer import df_to_minute_rows, replace_minute_day  # noqa: E402
from collectors.daily_collector import reconcile_verdict  # noqa: E402
from api import kis_chart_api  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


def collect_minute(target_date: str = None, top_n: int = 300, limit: int = None) -> dict:
    codes = select_top_volume(top_n)
    if limit:
        codes = codes[:limit]
    total = 0
    with KisDbConnection.get_connection() as conn:
        for code in codes:
            df = kis_chart_api.get_full_trading_day_data(code, target_date or "", "153000")
            if df is None or len(df) == 0:
                continue
            rows = df_to_minute_rows(code, df)
            if rows:
                total += replace_minute_day(conn, code, rows[0]["trade_date"], rows)
    return {"codes": len(codes), "rows": total}


def _load_bars(conn, trade_date: str) -> dict:
    """{stock_code: {(time, close), ...}} for trade_date."""
    out = {}
    with conn.cursor() as cur:
        cur.execute("SELECT stock_code, time, close FROM minute_candles WHERE trade_date=%s", (trade_date,))
        for sc, t, c in cur.fetchall():
            out.setdefault(sc, set()).add((str(t), float(c) if c is not None else None))
    return out


def minute_match_rate(new: dict, legacy: dict):
    """교집합 종목의 바(time,close) 일치율. 반환 (rate, overlap_stock_count)."""
    inter = set(new) & set(legacy)
    if not inter:
        return 0.0, 0
    matched_bars = total_bars = 0
    for sc in inter:
        nb, lb = new[sc], legacy[sc]
        total_bars += len(lb)
        matched_bars += len(nb & lb)
    rate = (matched_bars / total_bars) if total_bars else 0.0
    return rate, len(inter)


def reconcile_minute(trade_date: str) -> dict:
    legacy = psycopg2.connect(
        host=os.getenv("KIS_DB_HOST", "localhost"), port=int(os.getenv("KIS_DB_PORT", 5433)),
        dbname="robotrader", user=os.getenv("KIS_DB_USER", "robotrader"),
        password=os.getenv("KIS_DB_PASSWORD", "1234"))
    try:
        legacy_bars = _load_bars(legacy, trade_date)
        with KisDbConnection.get_connection() as conn:
            new_bars = _load_bars(conn, trade_date)
            rate, overlap = minute_match_rate(new_bars, legacy_bars)
            real_rows = sum(len(v) for v in legacy_bars.values())
            new_rows = sum(len(v) for v in new_bars.values())
            coverage = (len(new_bars) / len(legacy_bars)) if legacy_bars else (1.0 if not new_bars else 0.0)
            verdict = "PASS" if (coverage >= 0.9 and rate >= 0.95 and overlap > 0) else (
                "EMPTY" if real_rows == 0 and new_rows == 0 else "FAIL")
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO collection_reconciliation "
                    "(trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict) "
                    "VALUES (%s,'minute',%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (trade_date, dataset) DO UPDATE SET "
                    "real_rows=EXCLUDED.real_rows, new_rows=EXCLUDED.new_rows, overlap=EXCLUDED.overlap, "
                    "value_match_rate=EXCLUDED.value_match_rate, coverage=EXCLUDED.coverage, verdict=EXCLUDED.verdict",
                    (trade_date, real_rows, new_rows, overlap, rate, coverage, verdict))
            conn.commit()
        return {"trade_date": trade_date, "real_rows": real_rows, "new_rows": new_rows,
                "overlap": overlap, "value_match_rate": rate, "coverage": coverage, "verdict": verdict}
    finally:
        legacy.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--reconcile-only", default=None)
    args = ap.parse_args()
    if args.reconcile_only:
        print(reconcile_minute(args.reconcile_only))
    else:
        print(collect_minute(args.date, limit=args.limit))
```

> `reconcile_verdict` import는 dataset 공통 판정 재사용 의도지만 분봉은 교집합 특화라 `minute_match_rate`로 별도 판정(import는 일관성 위해 유지하되 사용 안 하면 제거 — 구현자 판단). 구현 시 미사용 import는 정리할 것.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/collectors/test_minute_collector.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 통합(소수)·교차비교 — 인증/EOD 의존**

Run(소수): `PYTHONIOENCODING=utf-8 python -X utf8 -m collectors.minute_collector --limit 3`
Expected: `{'codes': 3, 'rows': >0}` (KIS 인증 + 당일 분봉 가용 시; 미가용이면 보류)

- [ ] **Step 6: 전체 테스트 + Commit**

Run: `python -m pytest tests/collectors/ -v`
Expected: 전부 PASS

```bash
git add collectors/minute_collector.py tests/collectors/test_minute_collector.py
git commit -m "feat(collectors): 분봉 수집 오케스트레이터 + CLI + 교집합 교차비교"
```

---

## Self-Review (작성자 체크)

- **Spec 커버리지(분봉)**: 거래대금순 top300(Task1)·당일 전체분봉 적재(Task2,3)·교집합 교차비교(Task3 reconcile_minute) — spec §7 "분봉=교집합 값 일치율" 충족.
- **Placeholder 스캔**: 모든 스텝 실제 코드·명령·기대출력. 미사용 import 정리 지시 명시.
- **타입 일관성**: Task1 `select_top_volume()->list`·`parse_rank_codes(df)->list` → Task3 사용. Task2 `df_to_minute_rows(code,df)->list[dict]`·`replace_minute_day(conn,code,trade_date,rows)->int` → Task3 사용. `minute_match_rate(new,legacy)->(rate,overlap)` 테스트·reconcile 일치.
