# 기업행위 가격 보정 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** KIS 수정주가 피드로 `daily_prices` 의 미조정 가격과 틀린 `adj_factor` 를 고친다 — **계수를 한 번도 추론하지 않고.**

**Architecture:** 순수 계산(`collectors/adj_repair.py`)과 부작용(백업·UPSERT·CLI)을 가른다.
KIS 두 피드(`adj_prc="0"`/`"1"`)를 받아 OHLC 는 조정본, `volume` 은 원본, `adj_factor` 는 두 거래량의 비로 만든다.
**기존 저장 규약을 한 글자도 안 바꾸므로 읽기 계층·소비자 변경이 0줄이다.**

**Tech Stack:** Python 3.9 · pandas · psycopg2 · pytest

**Spec:** `RoboTrader_template/docs/superpowers/specs/2026-08-20-corp-action-price-repair-design.md`

## Global Constraints

- 🔴 **`adj_factor = vol_adj / vol_raw`** (= `raw_close / adj_close`). **방향을 뒤집지 말 것** —
  사양 §4-1 초안이 뒤집혀 있었고 그대로 썼으면 25배 틀렸다.
- 🔴 **`volume` 은 항상 `adj_prc="1"`(원본)** · **OHLC 는 항상 `adj_prc="0"`(조정)**. 섞지 말 것.
- 🔴 **백업 없이는 한 행도 UPDATE 하지 않는다.**
- 🔴 **라이브 코드(`core/` `bot/` `strategies/` `db/` `api/`)는 이 계획에서 0줄 수정.**
  수집 경로(사양 §7)는 **별도 승인 사안**이라 여기 없다.
- 🔴 **테스트는 워크트리에서만.** 라이브 트리(`D:\GIT\kis-trading-template`)에서 pytest 금지.
  워크트리는 `superpowers:using-git-worktrees` 로 만든다.
- 신규 테스트는 **DB·KIS 에 붙지 않는다** (순수 함수 + 가짜 입력만).
- 테스트 실행: repo 루트에서
  `& "C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe" -m pytest -q`
- 회귀 판정은 **실패 «집합»의 양방향 차분**. 실패 «수» 비교 금지.
  베이스라인 = `c39578e` 기준 `11 failed, 4738 passed`.
- 기존 기계검사 2개를 깨뜨리지 말 것: `tests/test_adj_factor_no_arithmetic.py`(가격에 산술 금지·volume 허용) ·
  `tests/test_adj_factor_volume_units.py`.

## File Structure

| 파일 | 책임 |
|---|---|
| `collectors/adj_repair.py` (신규) | **순수 계산.** 두 피드 → 보정행·계수. DB·API 접근 없음 |
| `db/adj_backup.py` (신규) | 백업 테이블 DDL · 저장 · 복원. SQL 만 |
| `scripts/repair_corp_action_prices.py` (신규) | CLI 오케스트레이션(수집→계산→백업→UPSERT→검증) |
| `tests/test_adj_repair.py` (신규) | 순수 함수 테스트 |
| `tests/test_adj_backup_sql.py` (신규) | 백업 SQL 문자열 계약 테스트 |

---

### Task 1: 계수 산출 순수 함수

**Files:**
- Create: `RoboTrader_template/collectors/adj_repair.py`
- Test: `RoboTrader_template/tests/test_adj_repair.py`

**Interfaces:**
- Consumes: 없음
- Produces: `derive_factors(raw: dict, adj: dict) -> tuple[dict, dict]`
  - `raw`/`adj`: `{date_iso: (open, high, low, close, volume)}`
  - 반환 `({date_iso: factor_float}, diag_dict)`
  - `diag` 키: `n_dates`, `n_derived`, `n_zero_vol`, `n_filled`
  - 🔑 **사양 §4-3 의 「구간 내 계수 충돌 → ERROR」 체크는 넣지 않는다** — 날짜별로 각자의 거래량 비를 쓰므로 «구간» 개념 자체가 불필요하고, 충돌이 원리적으로 안 생긴다. **재는 양이 상수인 가드는 가드가 아니라 장식이다**(이 저장소 계열 규칙). 그 조항은 계수를 «추론»하던 초안의 잔재다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_adj_repair.py
"""adj_repair 순수 함수 — DB·KIS 에 붙지 않는다."""
from collectors.adj_repair import derive_factors


def _row(close, vol):
    return (close, close, close, close, vol)


def test_factor_is_adj_over_raw_not_the_inverse():
    """🔴 방향 고정 — 054940 실측(2026-05-29 raw vol 357,326 / adj vol 71,465).

    저장 규약은 adj_close = raw_close / adj_factor 이고 읽기 계층은 volume * adj_factor 다.
    따라서 factor = vol_adj / vol_raw = 0.2 여야 한다. 5.0 이면 25배 틀린다.
    """
    raw = {"2026-05-29": _row(760, 357326)}
    adj = {"2026-05-29": _row(3800, 71465)}
    f, diag = derive_factors(raw, adj)
    assert abs(f["2026-05-29"] - 0.2) < 1e-9
    assert diag["n_derived"] == 1


def test_zero_volume_day_is_filled_from_neighbour_with_same_factor():
    """거래정지 패딩(vol=0)은 계수를 못 구한다 → 같은 값을 가진 이웃에서 채운다."""
    raw = {"2026-08-10": _row(760, 1000), "2026-08-11": _row(760, 0),
           "2026-08-12": _row(3815, 2000)}
    adj = {"2026-08-10": _row(3800, 200), "2026-08-11": _row(3800, 0),
           "2026-08-12": _row(3815, 2000)}
    f, diag = derive_factors(raw, adj)
    assert abs(f["2026-08-10"] - 0.2) < 1e-9
    assert abs(f["2026-08-12"] - 1.0) < 1e-9
    assert abs(f["2026-08-11"] - 0.2) < 1e-9   # 이전 유효값(같은 구간)
    assert diag["n_zero_vol"] == 1 and diag["n_filled"] == 1


def test_no_derivable_factor_returns_empty_and_flags():
    """계수를 하나도 못 구하면 «빈 결과» 다 — 1.0 으로 때우지 않는다(fail-closed)."""
    raw = {"2026-08-11": _row(760, 0)}
    adj = {"2026-08-11": _row(3800, 0)}
    f, diag = derive_factors(raw, adj)
    assert f == {}
    assert diag["n_derived"] == 0


def test_date_present_in_only_one_feed_is_skipped():
    raw = {"2026-05-29": _row(760, 100), "2026-05-30": _row(770, 100)}
    adj = {"2026-05-29": _row(3800, 20)}
    f, diag = derive_factors(raw, adj)
    assert set(f) == {"2026-05-29"}
    assert diag["n_dates"] == 1
```

- [ ] **Step 2: 테스트가 «실패»하는지 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'collectors.adj_repair'`

- [ ] **Step 3: 최소 구현**

```python
# collectors/adj_repair.py
"""기업행위 가격 보정 — 순수 계산. DB·KIS 에 접근하지 않는다.

🔴 방향 고정: 저장 규약은 `adj_close = raw_close / adj_factor` 이고
읽기 계층은 `volume * adj_factor` 를 한다(`db/quant_daily_reader.py`).
⇒ **adj_factor = vol_adj / vol_raw = raw_close / adj_close.**
사양 초안은 `vol_raw / vol_adj` 로 «뒤집혀» 있었다 — 그대로 썼으면 25배 틀렸다.
"""
from typing import Dict, Tuple


def _volume(row):
    return float(row[4])


def derive_factors(raw: Dict[str, tuple], adj: Dict[str, tuple]) -> Tuple[dict, dict]:
    """두 피드의 «거래량 비» 로 날짜별 adj_factor 를 구한다.

    거래량을 쓰는 이유: **배당의 영향을 안 받는다.** 가격 비로 구하면 KIS 수정주가가
    배당까지 조정하므로 순수 분할/병합 배수가 안 나온다(실측 15종목이 그 형태).
    """
    dates = sorted(set(raw) & set(adj))
    diag = dict(n_dates=len(dates), n_derived=0, n_zero_vol=0, n_filled=0)

    out: Dict[str, float] = {}
    for d in dates:
        vr, va = _volume(raw[d]), _volume(adj[d])
        if vr <= 0 or va <= 0:
            diag["n_zero_vol"] += 1
            continue
        out[d] = va / vr
        diag["n_derived"] += 1

    if not out:
        return {}, diag

    # 빈 날짜를 «이전 유효값» 으로 채운다. 정지 구간은 이벤트 «전» 에 속하므로
    # 앞에서 가져오는 것이 맞다. 앞이 없으면 뒤에서 가져온다.
    prev = None
    for d in dates:
        if d in out:
            prev = out[d]
            continue
        if prev is not None:
            out[d] = prev
            diag["n_filled"] += 1
    nxt = None
    for d in reversed(dates):
        if d in out:
            nxt = out[d]
        elif nxt is not None:
            out[d] = nxt
            diag["n_filled"] += 1
    return out, diag
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/collectors/adj_repair.py RoboTrader_template/tests/test_adj_repair.py
git commit -m "feat(adj-repair): 거래량 비로 adj_factor 산출 (방향 고정)"
```

---

### Task 2: 보정행 조립 + 멱등 판정

**Files:**
- Modify: `RoboTrader_template/collectors/adj_repair.py`
- Test: `RoboTrader_template/tests/test_adj_repair.py`

**Interfaces:**
- Consumes: `derive_factors`
- Produces:
  - `build_repair_rows(code, raw, adj, factors) -> list[dict]`
    dict 키: `stock_code, date, open, high, low, close, volume, adj_factor`
  - `needs_repair(db_rows, new_rows, rel_tol=0.01) -> list[dict]` — 이미 같은 행은 제외

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from collectors.adj_repair import build_repair_rows, needs_repair


def test_ohlc_comes_from_adjusted_feed_volume_from_raw_feed():
    """🔴 컬럼별 출처를 섞지 않는다 — OHLC=조정, volume=원본."""
    raw = {"2026-05-29": (750, 770, 740, 760, 357326)}
    adj = {"2026-05-29": (3750, 3850, 3700, 3800, 71465)}
    rows = build_repair_rows("054940", raw, adj, {"2026-05-29": 0.2})
    r = rows[0]
    assert (r["open"], r["high"], r["low"], r["close"]) == (3750.0, 3850.0, 3700.0, 3800.0)
    assert r["volume"] == 357326          # 원본
    assert r["adj_factor"] == 0.2
    assert r["stock_code"] == "054940" and r["date"] == "2026-05-29"


def test_row_without_factor_is_dropped():
    raw = {"2026-05-29": (0, 0, 0, 760, 100), "2026-05-30": (0, 0, 0, 770, 100)}
    adj = {"2026-05-29": (0, 0, 0, 3800, 20), "2026-05-30": (0, 0, 0, 3850, 20)}
    rows = build_repair_rows("X", raw, adj, {"2026-05-29": 0.2})
    assert [r["date"] for r in rows] == ["2026-05-29"]


def test_already_correct_rows_are_skipped():
    """멱등 — 가격이 이미 조정본이면 건드리지 않는다."""
    new = [{"stock_code": "A", "date": "2026-05-29", "open": 3750.0, "high": 3850.0,
            "low": 3700.0, "close": 3800.0, "volume": 357326, "adj_factor": 0.2}]
    db_same = {"2026-05-29": (3750.0, 3850.0, 3700.0, 3800.0, 357326, 0.2)}
    assert needs_repair(db_same, new) == []


def test_wrong_factor_alone_still_triggers_repair():
    """🔴 가격이 맞아도 계수가 틀리면 고쳐야 한다 — 004710 형태(큐가 못 잡는 부류)."""
    new = [{"stock_code": "A", "date": "2026-05-29", "open": 3750.0, "high": 3850.0,
            "low": 3700.0, "close": 3800.0, "volume": 357326, "adj_factor": 0.2}]
    db_badfactor = {"2026-05-29": (3750.0, 3850.0, 3700.0, 3800.0, 357326, 5.0)}
    assert len(needs_repair(db_badfactor, new)) == 1
```

- [ ] **Step 2: 테스트가 «실패»하는지 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_repair_rows'`

- [ ] **Step 3: 최소 구현 (`collectors/adj_repair.py` 에 «추가»)**

```python
def build_repair_rows(code: str, raw: Dict[str, tuple], adj: Dict[str, tuple],
                      factors: Dict[str, float]) -> list:
    """OHLC ← 조정 피드 · volume ← 원본 피드 · adj_factor ← factors.

    🔑 컬럼별 출처를 섞으면 규약이 깨진다(`CLAUDE.md` — 가격은 조정 저장, volume 은 원본 저장).
    """
    rows = []
    for d in sorted(set(raw) & set(adj) & set(factors)):
        a, r = adj[d], raw[d]
        rows.append(dict(
            stock_code=code, date=d,
            open=float(a[0]), high=float(a[1]), low=float(a[2]), close=float(a[3]),
            volume=int(_volume(r)),
            adj_factor=float(factors[d]),
        ))
    return rows


def needs_repair(db_rows: Dict[str, tuple], new_rows: list,
                 rel_tol: float = 0.01) -> list:
    """DB 와 «이미 같은» 행은 뺀다 (멱등).

    db_rows: {date_iso: (open, high, low, close, volume, adj_factor)}
    🔑 `adj_factor` 도 비교 대상이다 — 가격이 맞아도 계수가 틀린 종목이 실측 9건 있다.
    """
    def same(a, b):
        if a is None or b is None:
            return False
        if b == 0:
            return a == 0
        return abs(a / b - 1.0) <= rel_tol

    out = []
    for n in new_rows:
        cur = db_rows.get(n["date"])
        if cur is None:
            out.append(n)
            continue
        o, h, l, c, v, f = cur
        if (same(n["open"], o) and same(n["high"], h) and same(n["low"], l)
                and same(n["close"], c) and same(float(n["volume"]), float(v))
                and same(n["adj_factor"], f)):
            continue
        out.append(n)
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: 8 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/collectors/adj_repair.py RoboTrader_template/tests/test_adj_repair.py
git commit -m "feat(adj-repair): 보정행 조립 + 멱등 판정"
```

---

### Task 3: 백업 테이블 SQL

**Files:**
- Create: `RoboTrader_template/db/adj_backup.py`
- Test: `RoboTrader_template/tests/test_adj_backup_sql.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `DDL_SQL: str`
  - `backup_rows(conn, code, dates, batch_id) -> int`
  - `restore_batch(conn, batch_id) -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_adj_backup_sql.py
"""백업 SQL 계약 — DB 에 붙지 않고 문자열만 검사한다."""
from db.adj_backup import DDL_SQL, BACKUP_SQL, RESTORE_SQL


def test_ddl_creates_table_if_not_exists_and_never_drops():
    assert "CREATE TABLE IF NOT EXISTS daily_prices_preadj_backup" in DDL_SQL
    for forbidden in ("DROP ", "TRUNCATE"):
        assert forbidden not in DDL_SQL.upper()


def test_backup_captures_every_column_we_may_overwrite():
    for col in ("open", "high", "low", "close", "volume", "adj_factor"):
        assert col in BACKUP_SQL


def test_backup_is_insert_only_no_update():
    assert BACKUP_SQL.strip().upper().startswith("INSERT")
    assert "ON CONFLICT DO NOTHING" in BACKUP_SQL.upper()


def test_restore_writes_back_all_columns_and_is_scoped_to_batch():
    assert RESTORE_SQL.strip().upper().startswith("UPDATE")
    assert "batch_id" in RESTORE_SQL
    for col in ("open", "high", "low", "close", "volume", "adj_factor"):
        assert col in RESTORE_SQL
```

- [ ] **Step 2: 테스트가 «실패»하는지 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_backup_sql.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'db.adj_backup'`

- [ ] **Step 3: 최소 구현**

```python
# db/adj_backup.py
"""기업행위 가격 보정 전 원본 스냅샷. **백업 없이는 한 행도 고치지 않는다.**"""

DDL_SQL = """
CREATE TABLE IF NOT EXISTS daily_prices_preadj_backup (
    batch_id     text        NOT NULL,
    stock_code   text        NOT NULL,
    date         text        NOT NULL,
    open         double precision,
    high         double precision,
    low          double precision,
    close        double precision,
    volume       bigint,
    adj_factor   double precision,
    backed_up_at timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_id, stock_code, date)
)
"""

BACKUP_SQL = """
INSERT INTO daily_prices_preadj_backup
    (batch_id, stock_code, date, open, high, low, close, volume, adj_factor)
SELECT %(batch_id)s, stock_code, date, open, high, low, close, volume, adj_factor
FROM daily_prices
WHERE stock_code = %(code)s AND date = ANY(%(dates)s)
ON CONFLICT DO NOTHING
"""

RESTORE_SQL = """
UPDATE daily_prices dp SET
    open = b.open, high = b.high, low = b.low, close = b.close,
    volume = b.volume, adj_factor = b.adj_factor, updated_at = now()
FROM daily_prices_preadj_backup b
WHERE b.batch_id = %(batch_id)s
  AND dp.stock_code = b.stock_code AND dp.date = b.date
"""


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL_SQL)
    conn.commit()


def backup_rows(conn, code: str, dates: list, batch_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(BACKUP_SQL, dict(batch_id=batch_id, code=code, dates=dates))
        n = cur.rowcount
    conn.commit()
    return n


def restore_batch(conn, batch_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(RESTORE_SQL, dict(batch_id=batch_id))
        n = cur.rowcount
    conn.commit()
    return n
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_backup_sql.py -q`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/db/adj_backup.py RoboTrader_template/tests/test_adj_backup_sql.py
git commit -m "feat(adj-repair): 백업 테이블 DDL + 저장/복원 SQL"
```

---

### Task 4: KIS 두 피드 수신 어댑터

**Files:**
- Modify: `RoboTrader_template/collectors/adj_repair.py`
- Test: `RoboTrader_template/tests/test_adj_repair.py`

**Interfaces:**
- Consumes: 없음 (KIS 호출은 주입받는다)
- Produces: `fetch_both(code, start, end, fetcher) -> tuple[dict, dict]`
  - `fetcher(code, start, end, adj_prc) -> list[dict]` 를 **주입**받는다 (테스트가 DB·API 없이 돈다)
  - 반환 `(raw, adj)` — 각각 `{date_iso: (o,h,l,c,v)}`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from collectors.adj_repair import fetch_both


def test_fetch_both_requests_raw_and_adjusted_and_keys_by_iso_date():
    calls = []

    def fake(code, start, end, adj_prc):
        calls.append(adj_prc)
        px = 760 if adj_prc == "1" else 3800
        vol = 357326 if adj_prc == "1" else 71465
        return [{"stck_bsop_date": "20260529", "stck_oprc": px, "stck_hgpr": px,
                 "stck_lwpr": px, "stck_clpr": px, "acml_vol": vol}]

    raw, adj = fetch_both("054940", "20210101", "20260820", fake)
    assert sorted(calls) == ["0", "1"]
    assert raw["2026-05-29"][3] == 760.0
    assert adj["2026-05-29"][3] == 3800.0


def test_rows_with_bad_date_or_nonpositive_close_are_dropped():
    def fake(code, start, end, adj_prc):
        return [{"stck_bsop_date": "2026", "stck_clpr": 100, "acml_vol": 1},
                {"stck_bsop_date": "20260529", "stck_clpr": 0, "acml_vol": 1},
                {"stck_bsop_date": "20260530", "stck_oprc": 10, "stck_hgpr": 10,
                 "stck_lwpr": 10, "stck_clpr": 10, "acml_vol": 5}]

    raw, adj = fetch_both("X", "1", "2", fake)
    assert list(raw) == ["2026-05-30"]
```

- [ ] **Step 2: 테스트가 «실패»하는지 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: FAIL — `ImportError: cannot import name 'fetch_both'`

- [ ] **Step 3: 최소 구현 (`collectors/adj_repair.py` 에 «추가»)**

```python
def _f(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _parse_feed(items) -> Dict[str, tuple]:
    out = {}
    for it in items or []:
        d = str(it.get("stck_bsop_date", ""))
        if len(d) != 8 or not d.isdigit():
            continue
        c = _f(it.get("stck_clpr"))
        if c <= 0:
            continue
        iso = "%s-%s-%s" % (d[0:4], d[4:6], d[6:8])
        out[iso] = (_f(it.get("stck_oprc")), _f(it.get("stck_hgpr")),
                    _f(it.get("stck_lwpr")), c, _f(it.get("acml_vol")))
    return out


def fetch_both(code: str, start: str, end: str, fetcher) -> Tuple[dict, dict]:
    """`(raw, adj)` — `fetcher` 를 «주입» 받아 테스트가 API 없이 돈다.

    🔴 `adj_prc="1"` = 원주가 · `"0"` = 수정주가. 우리 수집기 전부가 기본값 `"1"` 을 써서
    이 결함이 생겼다(사양 §2-2). 여기서는 **둘 다 명시**한다.
    """
    raw = _parse_feed(fetcher(code, start, end, "1"))
    adj = _parse_feed(fetcher(code, start, end, "0"))
    return raw, adj
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: 10 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/collectors/adj_repair.py RoboTrader_template/tests/test_adj_repair.py
git commit -m "feat(adj-repair): KIS 두 피드 수신 어댑터 (fetcher 주입)"
```

---

### Task 5: 검증 지표 — 불가능봉 카운터

**Files:**
- Modify: `RoboTrader_template/collectors/adj_repair.py`
- Test: `RoboTrader_template/tests/test_adj_repair.py`

**Interfaces:**
- Consumes: 없음
- Produces: `count_impossible(rows, up=0.31, down=-0.35) -> int`
  - `rows`: `[(date_iso, close_float)]` 오름차순

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from collectors.adj_repair import count_impossible


def test_counts_both_directions_beyond_krx_limits():
    rows = [("2026-08-11", 760.0), ("2026-08-12", 3815.0)]   # +402%
    assert count_impossible(rows) == 1
    rows2 = [("2026-08-11", 3800.0), ("2026-08-12", 3815.0)]  # +0.4%
    assert count_impossible(rows2) == 0
    rows3 = [("2026-08-11", 1000.0), ("2026-08-12", 600.0)]   # -40%
    assert count_impossible(rows3) == 1


def test_nonpositive_previous_close_is_not_counted():
    assert count_impossible([("2026-08-11", 0.0), ("2026-08-12", 3815.0)]) == 0
```

- [ ] **Step 2: 테스트가 «실패»하는지 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: FAIL — `ImportError: cannot import name 'count_impossible'`

- [ ] **Step 3: 최소 구현 (`collectors/adj_repair.py` 에 «추가»)**

```python
def count_impossible(rows, up: float = 0.31, down: float = -0.35) -> int:
    """KRX 일일 한도(±30%)를 넘는 봉 수. 검증 지표 — 줄지 않으면 중단한다.

    🔑 위생 가드(`utils/data_sanity.py`)는 «하락» 만 보지만 실측 불가능봉의
    다수는 «상승» 이다(액면병합이 가격을 올리므로). 여기서는 **양방향**을 센다.
    """
    n = 0
    prev = None
    for _, c in rows:
        if prev is not None and prev > 0:
            r = c / prev - 1.0
            if r >= up or r <= down:
                n += 1
        prev = c
    return n
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: 12 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/collectors/adj_repair.py RoboTrader_template/tests/test_adj_repair.py
git commit -m "feat(adj-repair): 불가능봉 카운터 (양방향)"
```

---

### Task 6: 대상 목록 로더 (큐 + 큐 밖 7종목)

**Files:**
- Modify: `RoboTrader_template/collectors/adj_repair.py`
- Test: `RoboTrader_template/tests/test_adj_repair.py`

**Interfaces:**
- Consumes: 없음
- Produces: `load_targets(queue_lines, today_iso, extra=None) -> list[str]`
  - 종목코드 오름차순 유일 목록

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import json
from collectors.adj_repair import load_targets, EXTRA_CODES


def test_only_pending_and_eligible_entries_are_taken():
    lines = [
        json.dumps({"stock_code": "000001", "eligible_after": "2026-08-01", "status": "pending"}),
        json.dumps({"stock_code": "000002", "eligible_after": "2026-09-01", "status": "pending"}),
        json.dumps({"stock_code": "000003", "eligible_after": "2026-08-01", "status": "done"}),
    ]
    assert load_targets(lines, "2026-08-20", extra=[]) == ["000001"]


def test_extra_codes_are_merged_and_deduped():
    """🔴 큐가 «원리적으로» 못 잡는 7종목(사양 §5-1)을 반드시 포함한다."""
    lines = [json.dumps({"stock_code": "003620", "eligible_after": "2026-08-01",
                         "status": "pending"})]
    got = load_targets(lines, "2026-08-20")
    assert "003620" in got
    for c in EXTRA_CODES:
        assert c in got
    assert len(got) == len(set(got))


def test_extra_codes_is_exactly_the_measured_seven():
    assert sorted(EXTRA_CODES) == sorted([
        "003620", "004710", "010140", "042940", "128820", "010120", "323350"])
```

- [ ] **Step 2: 테스트가 «실패»하는지 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: FAIL — `ImportError: cannot import name 'load_targets'`

- [ ] **Step 3: 최소 구현 (`collectors/adj_repair.py` 에 «추가»)**

```python
import json

# 🔴 사양 §5-1 실측 — 큐가 «원리적으로» 못 잡는 종목.
# 큐는 「정지 해제 시 가격 점프」만 보므로 «가격은 연속인데 계수만 틀린» 경우를 놓친다.
# 계수 오류 5 (003620 004710 010140 042940 128820) + 가격 미조정 2 (010120 323350).
EXTRA_CODES = ("003620", "004710", "010140", "042940", "128820", "010120", "323350")


def load_targets(queue_lines, today_iso: str, extra=None) -> list:
    """큐(JSONL 줄들) + 큐 밖 목록 → 처리 대상 종목코드."""
    codes = set(EXTRA_CODES if extra is None else extra)
    for line in queue_lines:
        line = (line or "").strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("status") != "pending":
            continue
        if str(rec.get("eligible_after", "")) > today_iso:
            continue
        codes.add(rec["stock_code"])
    return sorted(codes)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_repair.py -q`
Expected: 15 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/collectors/adj_repair.py RoboTrader_template/tests/test_adj_repair.py
git commit -m "feat(adj-repair): 대상 로더 (큐 + 큐 밖 7종목)"
```

---

### Task 7: CLI 오케스트레이터 (dry-run 기본)

**Files:**
- Create: `RoboTrader_template/scripts/repair_corp_action_prices.py`

**Interfaces:**
- Consumes: `collectors.adj_repair.*` · `db.adj_backup.*` · `api.kis_market_api` · `api.kis_auth.auth`
- Produces: CLI. `--dry-run`(기본) · `--apply` · `--codes` · `--limit` · `--restore BATCH_ID`

- [ ] **Step 1: 스크립트 작성**

```python
# -*- coding: utf-8 -*-
"""기업행위 가격 보정 — 큐 + 큐 밖 7종목을 KIS 수정주가로 고친다.

사양: docs/superpowers/specs/2026-08-20-corp-action-price-repair-design.md

🔴 기본은 dry-run 이다. `--apply` 를 줘야 쓴다. 백업 없이는 한 행도 안 고친다.

    python scripts/repair_corp_action_prices.py --limit 1              # dry-run
    python scripts/repair_corp_action_prices.py --limit 1 --apply
    python scripts/repair_corp_action_prices.py --restore <BATCH_ID>
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import psycopg2  # noqa: E402

HIST0, TODAY = "20210101", date.today().strftime("%Y%m%d")


def dsn() -> dict:
    return dict(host="127.0.0.1", port=5433, user="robotrader",
                password="1234", dbname="kis_template")


def _kis_fetcher(code, start, end, adj_prc):
    from api import kis_market_api
    df = kis_market_api.get_inquire_daily_itemchartprice_extended(
        div_code="J", itm_no=code, inqr_strt_dt=start, inqr_end_dt=end,
        period_code="D", adj_prc=adj_prc, max_count=2000)
    if df is None or df.empty:
        return []
    return [dict(r) for _, r in df.iterrows()]


def _db_rows(conn, code):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT date, open, high, low, close, volume, adj_factor "
            "FROM daily_prices WHERE stock_code=%s ORDER BY date", (code,))
        return {d: (o, h, l, c, v, f) for d, o, h, l, c, v, f in cur.fetchall()}


UPSERT = """
INSERT INTO daily_prices (stock_code, date, open, high, low, close, volume, adj_factor, updated_at)
VALUES (%(stock_code)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s,
        %(volume)s, %(adj_factor)s, now())
ON CONFLICT (stock_code, date) DO UPDATE SET
    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
    volume=EXCLUDED.volume, adj_factor=EXCLUDED.adj_factor, updated_at=now()
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 dry-run)")
    ap.add_argument("--codes", default=None, help="쉼표 구분. 지정 시 큐를 무시한다")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--restore", default=None, metavar="BATCH_ID")
    a = ap.parse_args()

    from api.kis_auth import auth
    from collectors import adj_repair as R
    from db import adj_backup as B

    conn = psycopg2.connect(**dsn())

    if a.restore:
        B.ensure_table(conn)
        n = B.restore_batch(conn, a.restore)
        print(f"restored {n} rows from batch {a.restore}")
        conn.close()
        return 0

    if not auth():
        print("KIS auth failed")
        return 2

    if a.codes:
        targets = [c.strip() for c in a.codes.split(",") if c.strip()]
    else:
        qp = REPO / "logs" / "corp_action_refetch_queue.jsonl"
        lines = qp.read_text(encoding="utf-8").splitlines() if qp.exists() else []
        targets = R.load_targets(lines, date.today().isoformat())
    if a.limit:
        targets = targets[:a.limit]

    batch_id = "repair-" + date.today().isoformat() + ("-apply" if a.apply else "-dry")
    if a.apply:
        B.ensure_table(conn)

    tot_before = tot_after = tot_rows = 0
    for i, code in enumerate(targets, 1):
        raw, adj = R.fetch_both(code, HIST0, TODAY, _kis_fetcher)
        factors, diag = R.derive_factors(raw, adj)
        if not factors:
            print(f"[{i}/{len(targets)}] {code} SKIP — 계수 산출 0건 (diag {diag})")
            continue
        new_rows = R.build_repair_rows(code, raw, adj, factors)
        db = _db_rows(conn, code)
        todo = R.needs_repair(db, new_rows)

        before = R.count_impossible(sorted((d, float(v[3])) for d, v in db.items()))
        merged = dict(db)
        for r in todo:
            merged[r["date"]] = (r["open"], r["high"], r["low"], r["close"],
                                 r["volume"], r["adj_factor"])
        after = R.count_impossible(sorted((d, float(v[3])) for d, v in merged.items()))
        tot_before += before
        tot_after += after
        tot_rows += len(todo)

        print(f"[{i}/{len(targets)}] {code} rows={len(todo)} impossible {before}->{after} "
              f"derived={diag['n_derived']} filled={diag['n_filled']}")

        if not a.apply or not todo:
            continue
        if after > before:
            print(f"    ABORT — {code} 불가능봉이 늘었다({before}->{after})")
            conn.rollback()
            conn.close()
            return 3
        B.backup_rows(conn, code, [r["date"] for r in todo], batch_id)
        with conn.cursor() as cur:
            for r in todo:
                cur.execute(UPSERT, r)
        conn.commit()

    print(f"\nbatch {batch_id} · rows {tot_rows} · impossible {tot_before} -> {tot_after}")
    print("rollback: python scripts/repair_corp_action_prices.py --restore " + batch_id)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
```

- [ ] **Step 2: dry-run 으로 1종목 확인 (워크트리, `--apply` 없음)**

Run: `python scripts/repair_corp_action_prices.py --codes 054940`
Expected: `054940 rows=<N>  impossible 1->0` 이 인쇄되고 **DB 는 안 변한다**

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/scripts/repair_corp_action_prices.py
git commit -m "feat(adj-repair): CLI 오케스트레이터 (dry-run 기본 + 롤백)"
```

---

### Task 8: 전체 회귀 + 인수인계

**Files:**
- Modify: `RoboTrader_template/docs/superpowers/specs/2026-08-20-corp-action-price-repair-design.md` (§9 실행 기록)

- [ ] **Step 1: 전체 pytest**

Run: `& "C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe" -m pytest -q`
Expected: 실패 **집합**이 베이스라인(`c39578e` 의 11건)과 **양방향 차분 0**.
passed 는 신규 테스트만큼 늘어난다(4,738 → 4,753 예상).

- [ ] **Step 2: 기존 기계검사 2개가 그대로 통과하는지 개별 확인**

Run: `python -m pytest RoboTrader_template/tests/test_adj_factor_no_arithmetic.py RoboTrader_template/tests/test_adj_factor_volume_units.py -q`
Expected: PASS (규약을 안 바꿨으므로)

- [ ] **Step 3: 사양서 §9 에 실행 기록 추가**

```markdown
## §10. 구현 기록 (2026-08-__)

- 구현 커밋 범위: <first>..<last> · 순수 로직 `collectors/adj_repair.py` · 백업 `db/adj_backup.py` ·
  CLI `scripts/repair_corp_action_prices.py`
- 회귀: 실패 집합 양방향 차분 0 (베이스라인 `c39578e` 11건) · passed <before> → <after>
- 🔴 **아직 적용하지 않았다** — `--apply` 실행은 사장님 승인 사항(단계 1종목 → 10종목 → 전체).
```

- [ ] **Step 4: 커밋**

```bash
git add RoboTrader_template/docs/superpowers/specs/2026-08-20-corp-action-price-repair-design.md
git commit -m "docs(adj-repair): 사양서에 구현 기록 추가"
```

---

## 실행 순서 (구현 완료 «후» · 각 단계마다 사장님 승인)

🔴 **반드시 이 순서다.**

1. `--codes 054940` **dry-run** → 사람이 전후 비교 확인
2. `--codes 054940 --apply` → 불가능봉 1 → 0 확인 · 롤백 명령이 인쇄되는지 확인
3. `--limit 10 --apply` → 불가능봉 총계 감소 확인
4. 전체(`--apply`) — **장중·EOD(16:00)와 겹치지 않는 창에서**
5. 검증 통과 후 **별도 승인**으로 사양 §7(수집 경로 `adj_prc="0"`)

⚠️ 각 단계에서 **불가능봉이 늘면 스크립트가 스스로 중단**한다(Task 7 `ABORT`).
⚠️ 되돌리기: `--restore <BATCH_ID>` (배치 ID 는 매 실행 끝에 인쇄된다).
