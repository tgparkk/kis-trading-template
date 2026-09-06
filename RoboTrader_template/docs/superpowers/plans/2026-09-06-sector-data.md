# 섹터 기반 데이터 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목→업종 명부(SCD2 · KSIC 2·3·5자리)와 업종 일별 성적표를 신규 4테이블 + 함수 1개로 만들고 EOD 두 줄로 자동 갱신한다.

**Architecture:** 집 규약 3분할 — `sector_collector`(오케스트레이션·CLI·reconcile) / `krx_desc_cache`·`dart_company_fetcher`(외부 호출) / `sector_writer`(**DB 쓰기 전담**). 명부는 SCD2(값→값 변경만 줄을 닫는다), 성적표는 `fn_sector_map_as_of(d)` 로 그날 라벨을 붙여 `daily_prices` 에서 매일 재계산한다. 라이브 매매 동작 0줄 · `eod_collection.py` 는 `financials_reconcile` 바로 뒤 +2줄.

**Tech Stack:** Python 3.8/3.9 호환 · `requests` · `psycopg2`(+`extras.execute_values`) · `pandas`(CSV 파싱만) · PostgreSQL 16 (`kis_template`, port **5433**) · pytest 8

**Spec:** `docs/superpowers/specs/2026-09-06-sector-data-design.md` (v5.1 · critic 5차 APPROVE)

---

## Global Constraints

스펙에서 그대로 옮긴다 — 매 태스크에서 다시 읽을 것:

- **매매 룰 0줄**
- **라이브 3표(`daily_prices`·`minute_candles`·`virtual_trading_records`) 불변**
- **KIS 호출 0**
- **EOD +2줄(`financials_reconcile` 바로 뒤)**
- **DART ≤300/일**
- **워크트리에서 작업**(`superpowers:using-git-worktrees`)
- **라이브 트리에서 테스트 금지**
- **DB 쓰기는 `sector_writer.py` 한 곳**
  — 명시 예외 하나: `collectors.dart_corp_code.refresh_from_dart()`(기존 함수 · `dart_corp_code` 표에 스스로 쓴다).
  스펙 §2 가 「`refresh_from_dart()` 호출자가 생긴다 · 코드 변경 없음」으로 승인한 경로이며,
  이 프로젝트가 만드는 4표에는 손대지 않는다.
- **`daily_prices.date` 는 TEXT**
- **`KisDbConnection` 사용**
- **전체 스위트 실패 집합 main 과 양방향 차분 0**
- **부트스트랩·백필은 사장님 승인 후 야간/주말**
- **평일 15:30~17:00 CLI 거부**

추가 규약(집 관례 — 위반하면 리뷰에서 되돌아온다):

- 연구 트리(`scripts/`·`multiverse/`·`lib/`·`backtest/`) **import 금지**. 예외는 T9 오라클 테스트 하나뿐이며 거긴 `sys.path.insert` + `importorskip` 으로 격리한다.
- 술어는 `config.constants.SQL_STOCK_ONLY` **하나만** 쓴다(`lib/universe_filter` 금지).
- opendart **동시 요청 금지** · `min_interval=0.34`.
- 파싱 실패는 `None`. **절대 `0` 아님.**
- **무징후 절단 금지** — 상한·후퇴·미정에 걸린 건수는 반드시 summary + WARNING.
- 로거 `utils.logger.setup_logger(__name__)` · 시간 `utils.korean_time.now_kst()`.
- `adj_factor` 산술 0건(성적표는 `close`·`high` 원값을 쓴다 — 태쏘 정의 승계).

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|---|---|---|
| `collectors/sector_writer.py` | DDL 4표 + 함수 · SCD2 계획/쓰기 · 급변 가드 · 재확인 레일 · 성적표 UPSERT · 이름표 재생성 · reconcile 행 쓰기 (**DB 쓰기는 여기만**) | 신규 |
| `collectors/krx_desc_cache.py` | GitHub 캐시 CSV 날짜 지정 읽기(≤7일 후퇴) · gz 보관 · 시장 묶음별 규모 하한 | 신규 |
| `collectors/dart_company_fetcher.py` | DART `company.json` 스로틀 클라이언트(0.34s · 000/013/020/800/blocked) · jsonl 보관 | 신규 |
| `collectors/sector_collector.py` | 명부 갱신 ① · KSIC 채우기/재확인 ② · 성적표 ③ · 이름표 ④ · summary · `reconcile_sector` · CLI(`--bootstrap` `--backfill` `--regen` `--regen-map` `--delete-stats` `--dry-run` `--force`) | 신규 |
| `collectors/dart_corp_code.py` | 기존. `refresh_from_dart()` 의 **첫 호출자**가 생긴다 | 무변경(호출만) |
| `collectors/eod_collection.py` | `"sector"` · `"sector_reconcile"` **2줄**(+import 1줄), `financials_reconcile` 바로 뒤 | 수정 |
| `tests/collectors/test_sector_writer.py` | T1 우선주 규칙 · T2 SCD2 · T3 급변 가드 (순수 함수 · DB 없음) | 신규 |
| `tests/collectors/test_sector_collector.py` | T4 캐시 · T5 절단 · T6 백분위 손계산 · T7-b 결정성 · T8 DART 분기 · T14 실패경로/시간가드/재확인/레일 · fetcher 단위 | 신규 |
| `tests/collectors/test_sector_writer_db.py` | T11 DDL·CHECK·`fn_sector_map_as_of` 왕복·경계·종목당 ≤1행 · T12 이름표 · T7-a UPSERT 멱등 (`@pytest.mark.db`) | 신규 |
| `tests/collectors/test_sector_stats_oracle_db.py` | T9 오라클 — 태쏘 `run_sector.load_day`+`labels_for(N=3)` 대조 (`@pytest.mark.db`) | 신규 |
| `tests/collectors/test_sector_reconcile.py` | T13 게이트 1~9 · PASS/WARN/FAIL · summary 저장/부재/유실 | 신규 |
| `tests/collectors/test_eod_collection.py` | `_stub_flow_stages` 에 `collect_sector`·`reconcile_sector` 추가 + T10 배선/순서/격리 | 수정 |
| `pyproject.toml` (**repo 루트**) | `[tool.pytest.ini_options] markers` 에 `db` 등록(미등록 마커 경고 제거) | 수정 |
| `docs/DB통합_쉬운설명.md` | §9 에 신규 4표 목록 추가 | 수정 |
| `docs/superpowers/specs/2026-09-06-sector-data-design.md` | §6.0·§6.2 실측 갱신(부트스트랩·백필 실행 «후») | 수정 |
| `docs/섹터데이터_쉬운설명_2026-09-06.md` | 쉬운 한 장(§11-6) | 신규 |

**경계**: `krx_desc_cache`·`dart_company_fetcher` 는 DB 를 모른다. `sector_writer` 는 HTTP 를 모른다. `sector_collector` 만 둘 다 안다.

---

## 실행 환경 — 명령 원형

🔴 **이 문서의 모든 명령 블록은 Bash 도구(Git Bash)로 실행한다.** PowerShell 에서는
히어독(`cat > f <<'EOF'`)·`VAR=x cmd` 접두·`export` 가 전부 파서 오류이고 `&&`/`||` 도 없다.
`PYTHONUTF8=1 <exe> ...` 같은 줄은 Git Bash 문법이다.

**워크트리**(라이브 트리에서 테스트 금지):

```
cd D:/GIT/kis-trading-template
git worktree add -b feat/sector-data D:/tmp/kis-wt-sector main
```

**단위 테스트**(워크트리 안 · 인터프리터만 라이브 트리 venv 를 빌려 쓴다 · cwd 는 워크트리):

```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer.py -v
```

한 테스트만: 위 명령 뒤에 `::test_이름` 을 붙인다 —
`... -m pytest tests/collectors/test_sector_writer.py::test_parent_rule_copies_from_parent -v`

**전체 스위트**(회귀 판정용 · repo 루트 + VS 번들 Python 조합만 완주한다):

```
cd D:/tmp/kis-wt-sector
PYTHONUTF8=1 "C:/Program Files (x86)/Microsoft Visual Studio/Shared/Python39_64/python.exe" -m pytest -q --tb=line -m "not db"
```

- 🔑 회귀 판정은 **실패 «집합»의 양방향 차분**이다(실패 «수» 아님). 기준선은 같은 조건의 baseline 워크트리(`git worktree add --detach D:/tmp/kis-wt-sector-base <main-sha>`)에서 따로 돌린다.
- `db` 마커 테스트(T9·T11·T12·T7-a)는 **기준선 비교에서 제외**한다(워크트리 환경 차이 · 스펙 T9 규정). 결과는 따로 기록한다.
- DB 테스트는 실 DB 가 없으면 **skip** 한다(워크트리엔 `.env` 가 없지만 `KisDbConnection` 기본값이 이미 `localhost:5433/kis_template/robotrader/1234` 라 그대로 붙는다).
- venv 엔 `pykrx` 가 없어 **전체 스위트는 venv 로 돌리면 안 된다**(수집 단계에서 8파일이 깨지고 세션이 Interrupt). 단일 파일 실행만 venv 로 한다.

**커밋**(셸 따옴표 문제 회피 — 메시지는 파일로):

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
<제목 줄>

<본문>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add <파일들> && git commit -F D:/tmp/sector_commit_msg.txt
```

**모든 커밋 메시지는 위 두 트레일러 줄로 끝나야 한다.**

---

### Task 0: 워크트리 준비 (코드 0줄)

**Files:**
- Create: 워크트리 `D:/tmp/kis-wt-sector` (브랜치 `feat/sector-data`)
- Create: 기준선 워크트리 `D:/tmp/kis-wt-sector-base` (detached at main)

**Interfaces:**
- Consumes: `main` HEAD
- Produces: `D:/tmp/sector_baseline_failures.txt` — 회귀 판정의 유일한 기준

- [ ] **Step 1: 워크트리를 만든다**

Run:
```
cd D:/GIT/kis-trading-template
git worktree add -b feat/sector-data D:/tmp/kis-wt-sector main
git -C D:/tmp/kis-wt-sector status --short --branch
```
Expected: `## feat/sector-data` · 변경 없음

- [ ] **Step 2: 기준선 워크트리에서 실패 «집합»을 뜬다**

Run:
```
cd D:/GIT/kis-trading-template
git worktree add --detach D:/tmp/kis-wt-sector-base main
cd D:/tmp/kis-wt-sector-base
PYTHONUTF8=1 "C:/Program Files (x86)/Microsoft Visual Studio/Shared/Python39_64/python.exe" -m pytest -q --tb=line -m "not db" > D:/tmp/sector_baseline_raw.txt 2>&1
grep -E "^(FAILED|ERROR)" D:/tmp/sector_baseline_raw.txt | sort > D:/tmp/sector_baseline_failures.txt
wc -l < D:/tmp/sector_baseline_failures.txt
```
Expected: 실패 목록 파일 생성(환경 의존 · 2026-08-12 실측은 워크트리 12건 · 2026-09-06 재무 브랜치에선 15건). **숫자가 아니라 이 파일이 기준**이다.

- [ ] **Step 3: 라이브 트리 오염이 없는지 확인한다**

Run:
```
git -C D:/GIT/kis-trading-template status --short | head -30
```
Expected: 이 작업으로 추가된 변경 0(기존 untracked 목록만 · 새 `??` 항목 없음).

- [ ] **Step 4: 스펙 §0 이 인용한 오프라인 CSV 사본이 있는지 확인한다**

Run:
```
ls -l D:/GIT/kis-trading-template/RoboTrader_template/scratchpad/sector/desc_2026-09-04.csv 2>/dev/null || echo "없음"
```
Expected: 552,967 bytes 파일 — **없어도 진행한다**(관리자가 곧 복사한다 · 이 계획의 테스트는
전부 «인라인 CSV 픽스처»를 쓰므로 이 파일에 의존하지 않는다). 있으면 Task 3 Step 5 의
실측 열 이름·행수와 대조하는 데 쓴다.

---

### Task 1: `sector_writer` DDL 4표 + `fn_sector_map_as_of` (T11)

**Files:**
- Create: `RoboTrader_template/collectors/sector_writer.py`
- Create: `RoboTrader_template/tests/collectors/test_sector_writer_db.py`
- Modify: `pyproject.toml`(repo 루트) — `[tool.pytest.ini_options] markers` 리스트에 **1줄** 추가(그 외 변경 금지)

**Interfaces:**
- Consumes: `db.kis_db_connection.KisDbConnection`(테스트에서만) · `utils.logger.setup_logger`
- Produces:
  - `DDL_MAP: str` · `DDL_MAP_IDX: list` · `DDL_STATS: str` · `DDL_STATS_IDX: list` · `DDL_NODATA: str` · `DDL_NAMES: str` · `DDL_FN_DROP: str` · `DDL_FN_AS_OF: str`
  - `ensure_tables(conn) -> None`
  - `map_as_of(conn, as_of) -> list` — `[(stock_code, ksic_code, ksic_source, ksic3_name, valid_from, source)]`

- [ ] **Step 1: 실패하는 DB 테스트를 쓴다 (DDL 멱등 + CHECK 2건)**

```python
# tests/collectors/test_sector_writer_db.py
"""섹터 스키마 DB 테스트 (T11 · T12 · T7-a).

🔴 실 DB(kis_template)가 있어야 한다. 없으면 전부 skip — 워크트리·CI 에서 스위트를
   깨뜨리지 않는다(재무 test_financial_writer_db.py 규약 + 접속 프로브 추가).
🔴 `@pytest.mark.db` — 기준선 실패 집합 비교에서 제외한다(스펙 T9 규정 승계).
"""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import sector_writer as w  # noqa: E402


# 🔴 접속 프로브를 «모듈 최상위»에 두지 않는다 — 수집 단계에 DB 를 두드리게 되고
#    `-m "not db"` 로도 못 막는다. 픽스처 안에서만 붙고, 실패하면 skip 한다.
pytestmark = [pytest.mark.db]

TEST_CODES = ("TEST9A", "TEST9B", "TEST9C", "TEST90")
TEST_STATS_DATE = date(1999, 1, 4)


def _cleanup(c):
    try:
        with c.cursor() as cur:
            cur.execute("DELETE FROM stock_sector_map WHERE stock_code IN %s", (TEST_CODES,))
            cur.execute("DELETE FROM sector_daily_stats WHERE date=%s", (TEST_STATS_DATE,))
            # T12 합성 코드(Task 7). 실 데이터와 겹치지 않는 990/991/99 만 지운다.
            cur.execute("DELETE FROM ksic_code_name WHERE code IN ('990','991','99')")
        c.commit()
    except Exception:
        c.rollback()
        raise


@pytest.fixture
def conn():
    try:
        cm = KisDbConnection.get_connection()
        c = cm.__enter__()
        with c.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as e:  # noqa: BLE001 — 접속 실패는 skip 사유지 테스트 실패가 아니다
        pytest.skip("kis_template DB 접속 불가: %s" % e)
    try:
        w.ensure_tables(c)
        _cleanup(c)
        yield c
        _cleanup(c)
    finally:
        cm.__exit__(None, None, None)


def test_ensure_tables_is_idempotent(conn):
    """두 번 돌려도 안 죽어야 한다 — EOD 가 매일 부른다."""
    w.ensure_tables(conn)
    w.ensure_tables(conn)
    with conn.cursor() as cur:
        for t in ("stock_sector_map", "sector_daily_stats",
                  "sector_ksic_nodata", "ksic_code_name"):
            cur.execute("SELECT to_regclass(%s)", ("public." + t,))
            assert cur.fetchone()[0] is not None, t + " 이 안 만들어졌다"


def test_stats_check_rejects_key_length_mismatch(conn):
    """taxonomy 와 sector_key 자릿수가 어긋나면 «저장이 안 돼야» 한다.
    4자리 KSIC 가 ksic5 키로 들어오는 경로를 스키마가 막는다 — T5 와 한 쌍."""
    import psycopg2
    with pytest.raises(psycopg2.errors.CheckViolation):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sector_daily_stats (date, taxonomy, sector_key, n_members, g_sectors) "
                "VALUES (%s, 'ksic5', '2611', 1, 1)", (TEST_STATS_DATE,))
    conn.rollback()


def test_map_check_rejects_reversed_validity(conn):
    """valid_to < valid_from 인 역전 줄은 스키마가 막는다(§3.1 과거 날짜 재실행 사고 방지)."""
    import psycopg2
    with pytest.raises(psycopg2.errors.CheckViolation):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO stock_sector_map (stock_code, valid_from, valid_to, source) "
                "VALUES ('TEST9A', %s, %s, 'eod')", (date(2026, 2, 10), date(2026, 2, 9)))
    conn.rollback()
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer_db.py -v
```
Expected: 수집 단계 오류 — `ModuleNotFoundError: No module named 'collectors.sector_writer'`

- [ ] **Step 3: 최소 구현 — DDL + `ensure_tables` + `map_as_of`**

```python
# collectors/sector_writer.py
"""섹터 명부·성적표 → kis_template. **DB 쓰기는 이 파일 한 곳뿐.**

🔑 SCD2 의 핵심은 «값 없음은 변경이 아니다» 이다. 소스가 하루 비어도 이력이 갈라지면
   안 된다 — 갈라진 이력은 fn_sector_map_as_of 에서 종목당 2행이 되고, 그건 성적표
   n_members 의 «이중 계산»이 된다(§8-8 이 FAIL 로 잡는 사고).
🔴 fn_sector_map_as_of 는 반환 타입이 바뀌면 CREATE OR REPLACE 가 거부한다 —
   DROP 을 «먼저» 해야 DDL 이 멱등이다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DDL_MAP = """
CREATE TABLE IF NOT EXISTS stock_sector_map (
    stock_code    varchar(20) NOT NULL,
    valid_from    date        NOT NULL,
    valid_to      date,
    ksic_code     varchar(10),
    ksic_source   text,
    ksic3_name    text,
    corp_code     varchar(8),
    market        text,
    kosdaq_dept   text,
    products      text,
    listing_date  date,
    settle_month  text,
    source        text        NOT NULL,
    source_asof   date,
    ksic_checked_at timestamp,
    collected_at  timestamp   NOT NULL DEFAULT now(),
    last_seen_at  timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_code, valid_from),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
)
"""

DDL_MAP_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_ssm_open ON stock_sector_map (stock_code) WHERE valid_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_ssm_asof ON stock_sector_map (stock_code, valid_from, valid_to)",
]

DDL_STATS = """
CREATE TABLE IF NOT EXISTS sector_daily_stats (
    date         date        NOT NULL,
    taxonomy     text        NOT NULL CHECK (taxonomy IN ('ksic2','ksic3','ksic5')),
    sector_key   text        NOT NULL,
    CHECK ((taxonomy='ksic2' AND sector_key ~ '^[0-9]{2}$')
        OR (taxonomy='ksic3' AND sector_key ~ '^[0-9]{3}$')
        OR (taxonomy='ksic5' AND sector_key ~ '^[0-9]{5}$')),
    n_members    int         NOT NULL,
    g_sectors    int         NOT NULL,
    ret_median   double precision,
    ret_mean     double precision,
    up_count     int,
    pos_ratio    double precision,
    rank_median  int,
    pct_median   double precision,
    rank_up      int,
    pct_up       double precision,
    rank_pos     int,
    pct_pos      double precision,
    computed_at  timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (date, taxonomy, sector_key)
)
"""

DDL_STATS_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_sds_tax_date ON sector_daily_stats (taxonomy, date)",
]

DDL_NODATA = """
CREATE TABLE IF NOT EXISTS sector_ksic_nodata (
    stock_code  varchar(20) PRIMARY KEY,
    checked_at  timestamp   NOT NULL DEFAULT now()
)
"""

DDL_NAMES = """
CREATE TABLE IF NOT EXISTS ksic_code_name (
    level       int         NOT NULL CHECK (level = 3),
    code        varchar(5)  NOT NULL CHECK (code ~ '^[0-9]{3}$'),
    name        text        NOT NULL,
    n_stocks    int         NOT NULL,
    share       double precision NOT NULL,
    built_at    timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (level, code)
)
"""

DDL_FN_DROP = "DROP FUNCTION IF EXISTS fn_sector_map_as_of(date)"

DDL_FN_AS_OF = """
CREATE OR REPLACE FUNCTION fn_sector_map_as_of(p_as_of date)
RETURNS TABLE (stock_code varchar(20), ksic_code varchar(10), ksic_source text,
               ksic3_name text, valid_from date, source text)
LANGUAGE sql STABLE AS $$
    SELECT stock_code, ksic_code, ksic_source, ksic3_name, valid_from, source
    FROM stock_sector_map
    WHERE valid_from <= p_as_of AND (valid_to IS NULL OR p_as_of <= valid_to)
$$
"""


def ensure_tables(conn) -> None:
    """신규 4표 + 인덱스 + 함수. 멱등 — EOD 가 매일 부른다."""
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_MAP)
            for sql in DDL_MAP_IDX:
                cur.execute(sql)
            cur.execute(DDL_STATS)
            for sql in DDL_STATS_IDX:
                cur.execute(sql)
            cur.execute(DDL_NODATA)
            cur.execute(DDL_NAMES)
            cur.execute(DDL_FN_DROP)
            cur.execute(DDL_FN_AS_OF)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def map_as_of(conn, as_of) -> list:
    """그 날짜의 명부 — (stock_code, ksic_code, ksic_source, ksic3_name, valid_from, source)."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, ksic_code, ksic_source, ksic3_name, valid_from, source "
                        "FROM fn_sector_map_as_of(%s)", (as_of,))
            return cur.fetchall()
    except Exception:
        conn.rollback()
        raise
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer_db.py -v
```
Expected: 3 passed

- [ ] **Step 5: 함수 왕복·경계·«종목당 ≤ 1행» 테스트를 추가한다**

```python
# tests/collectors/test_sector_writer_db.py 끝에 추가

def _insert_row(cur, code, vf, vt, ksic, source="eod"):
    cur.execute(
        "INSERT INTO stock_sector_map (stock_code, valid_from, valid_to, ksic_code, "
        "ksic_source, ksic3_name, source) VALUES (%s,%s,%s,%s,'dart','이름',%s)",
        (code, vf, vt, ksic, source))


def test_fn_sector_map_as_of_roundtrip_and_boundaries(conn):
    """`SELECT * FROM fn_sector_map_as_of(d)` 왕복 + 경계 3개.
    valid_from 당일 포함 · valid_to 당일 포함 · 그 다음날 제외."""
    with conn.cursor() as cur:
        _insert_row(cur, "TEST9A", date(2026, 1, 10), date(2026, 2, 9), "2611")
        _insert_row(cur, "TEST9A", date(2026, 2, 10), None, "2612")
    conn.commit()

    def _codes(d):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM fn_sector_map_as_of(%s)", (d,))
            return {r[0]: r[1] for r in cur.fetchall() if r[0] == "TEST9A"}

    assert _codes(date(2026, 1, 9)) == {}, "valid_from 이전이 보인다"
    assert _codes(date(2026, 1, 10)) == {"TEST9A": "2611"}, "valid_from 당일이 안 보인다"
    assert _codes(date(2026, 2, 9)) == {"TEST9A": "2611"}, "valid_to 당일이 안 보인다"
    assert _codes(date(2026, 2, 10)) == {"TEST9A": "2612"}
    assert _codes(date(2030, 1, 1)) == {"TEST9A": "2612"}, "열린 줄이 미래에 안 보인다"

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM fn_sector_map_as_of(%s)", (date(2026, 2, 10),))
        assert [d[0] for d in cur.description] == [
            "stock_code", "ksic_code", "ksic_source", "ksic3_name", "valid_from", "source"], \
            "소비자 계약(§3.6)의 컬럼 순서가 바뀌었다"

    rows = {r[0]: r[1] for r in w.map_as_of(conn, date(2026, 2, 10))}
    assert rows.get("TEST9A") == "2612", "writer API 왕복이 함수와 다르다"


def test_no_duplicate_stock_rows_on_sample_dates(conn):
    """🔴 겹치는 유효기간 = n_members 이중 계산. 표본 날짜 10개에서 종목당 ≤ 1행."""
    with conn.cursor() as cur:
        _insert_row(cur, "TEST9B", date(2021, 1, 4), date(2026, 3, 31), "2611")
        _insert_row(cur, "TEST9B", date(2026, 4, 1), None, "2612")
    conn.commit()
    sample = [date(2021, 1, 4), date(2022, 6, 30), date(2023, 12, 29), date(2024, 3, 12),
              date(2025, 1, 2), date(2026, 3, 31), date(2026, 4, 1), date(2026, 8, 5),
              date(2026, 9, 4), date(2026, 9, 30)]
    for d in sample:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, count(*) FROM fn_sector_map_as_of(%s) "
                        "GROUP BY 1 HAVING count(*) > 1", (d,))
            dup = cur.fetchall()
        assert dup == [], "%s 에 중복 유효기간이 있다: %s" % (d, dup[:5])
```

- [ ] **Step 6: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer_db.py -v
```
Expected: 5 passed

- [ ] **Step 7: `db` 마커를 등록한다**

repo 루트 `pyproject.toml` 의 `markers` 리스트를 아래로 바꾼다(다른 키는 손대지 않는다):

```toml
markers = [
    "slow: 느린 테스트 (DB 대량 조회 등) — pytest -m 'not slow' 로 제외",
    "db: 실 DB(kis_template)가 필요한 테스트 — 기준선 실패 집합 비교에서 제외 (-m 'not db')",
]
```

- [ ] **Step 8: 마커 선택이 실제로 되는지 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest RoboTrader_template/tests/collectors/test_sector_writer_db.py -q -m "not db"
```
Expected: `5 deselected` · `PytestUnknownMarkWarning` 없음

- [ ] **Step 9: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): sector_writer DDL 4표 + fn_sector_map_as_of (Task 1)

stock_sector_map(SCD2) · sector_daily_stats · sector_ksic_nodata · ksic_code_name
+ fn_sector_map_as_of(date). DDL 은 멱등이며 함수는 DROP 후 재생성한다 —
RETURNS TABLE 이 바뀌면 CREATE OR REPLACE 가 거부하기 때문이다.
DB 테스트는 접속 불가 시 skip 하고 db 마커로 기준선 비교에서 제외한다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/sector_writer.py RoboTrader_template/tests/collectors/test_sector_writer_db.py pyproject.toml && git commit -F D:/tmp/sector_commit_msg.txt
```
Expected: 3 files changed

---

### Task 2: 우선주 부모 규칙 + SCD2 쓰기 규칙 + 5% 급변 가드 (T1 · T2 · T3)

**Files:**
- Modify: `RoboTrader_template/collectors/sector_writer.py` (Task 1 파일 끝에 이어붙인다)
- Create: `RoboTrader_template/tests/collectors/test_sector_writer.py` (DB 없음 · 순수 함수)

**Interfaces:**
- Consumes: Task 1 의 `sector_writer` 모듈
- Produces:
  - `is_blank(v) -> bool`
  - `parent_code(stock_code) -> str or None`
  - `apply_parent_rule(candidates: dict, universe: set) -> dict`
  - `plan_map_changes(open_rows: dict, candidates: dict, trade_date: date, guard: bool = True, create_missing: bool = True) -> dict` — `{"inplace","close","open_new","changed_codes","skipped_past","skipped_missing","counts","guard"}` · 5% 초과면 `RuntimeError`
    (🔴 `guard=False` 는 **분모 1~2 인 단위 테스트 전용** · `create_missing=False` 는 **KSIC 재생 전용** — 운영 경로는 둘 다 기본값)
  - `write_map(conn, plan: dict, source: str) -> dict` — `{"closed","inserted","updated"}` · **한 트랜잭션**
  - `load_open_rows(conn) -> dict` — `{stock_code: {열린 줄 컬럼들}}`
  - `open_market_counts(conn) -> dict` — `{market: n}` (규모 하한 기준선)
  - `load_stock_industry(conn) -> dict` — `{stock_code: induty_code}` (**부트스트랩에서만** 호출)
  - 상수 `CHANGE_FIELDS` · `SIDE_FIELDS` · `MAX_CHANGE_RATIO = 0.05`

- [ ] **Step 1: T1 — 우선주 부모 규칙 테스트를 쓴다 (실패)**

```python
# tests/collectors/test_sector_writer.py
"""섹터 명부 SCD2 순수 함수 테스트 (T1 · T2 · T3). DB 를 쓰지 않는다."""
import os
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from collectors import sector_writer as w  # noqa: E402

D = date(2026, 9, 7)


def test_parent_code_identifies_preferred_shares():
    """끝자리 ≠ '0' 이면 우선주 — 부모는 앞 5자리 + '0'."""
    assert w.parent_code("00104K") == "001040"
    assert w.parent_code("000087") == "000080"
    assert w.parent_code("0220WL") == "0220W0"
    assert w.parent_code("005930") is None
    assert w.parent_code("0001A0") is None, "끝자리가 '0' 이면 보통주다(신형 상장코드)"


def test_parent_rule_copies_from_parent():
    """부모가 KSIC 를 가지면 코드·회사코드·이름을 함께 받고 출처를 못박는다."""
    cands = {
        "001040": {"ksic_code": "264", "ksic3_name": "통신 및 방송 장비 제조업",
                   "corp_code": "00126380"},
        "00104K": {"ksic_code": None, "ksic3_name": None, "corp_code": None},
    }
    out = w.apply_parent_rule(cands, {"001040", "00104K"})
    assert out["00104K"]["ksic_code"] == "264"
    assert out["00104K"]["ksic_source"] == "parent:001040"
    assert out["00104K"]["corp_code"] == "00126380"
    assert out["00104K"]["ksic3_name"] == "통신 및 방송 장비 제조업"
    assert out["001040"]["ksic_code"] == "264", "보통주는 건드리지 않는다"


def test_parent_absent_leaves_all_null():
    """부모가 유니버스에 아예 없으면(가상의 0220XL) 전부 NULL 이다."""
    cands = {"0220XL": {"ksic_code": None, "ksic3_name": None, "corp_code": None}}
    out = w.apply_parent_rule(cands, {"0220XL"})
    assert out["0220XL"]["ksic_code"] is None
    assert out["0220XL"].get("ksic_source") is None
    assert out["0220XL"]["ksic3_name"] is None


def test_parent_without_ksic_copies_name_only():
    """🔴 실제 사례 0220WL → 0220W0: 부모에 KSIC 가 없으면 «코드만» NULL 이고
    이름은 KSIC 와 독립으로 복사된다(캐시엔 부모 이름이 114/114 있다)."""
    cands = {
        "0220W0": {"ksic_code": None, "ksic3_name": "부동산 임대 및 공급업",
                   "corp_code": None},
        "0220WL": {"ksic_code": None, "ksic3_name": None, "corp_code": None},
    }
    out = w.apply_parent_rule(cands, {"0220W0", "0220WL"})
    assert out["0220WL"]["ksic_code"] is None
    assert out["0220WL"].get("ksic_source") is None
    assert out["0220WL"]["ksic3_name"] == "부동산 임대 및 공급업"


def test_self_value_wins_over_parent():
    """캐시 행에 자기 값이 있으면 그것이 부모보다 우선한다."""
    cands = {
        "001040": {"ksic_code": "264", "ksic3_name": "부모이름", "corp_code": "00126380"},
        "00104K": {"ksic_code": None, "ksic3_name": "자기이름", "corp_code": None},
    }
    out = w.apply_parent_rule(cands, {"001040", "00104K"})
    assert out["00104K"]["ksic3_name"] == "자기이름"
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer.py -v
```
Expected: FAIL — `AttributeError: module 'collectors.sector_writer' has no attribute 'parent_code'`

- [ ] **Step 3: `is_blank` · `parent_code` · `apply_parent_rule` 구현**

`collectors/sector_writer.py` 끝에 이어붙인다:

```python
CHANGE_FIELDS = ("ksic_code", "ksic3_name")
# ⚠️ 부수 열은 «항상 제자리 갱신»이다(§3.1) — 그래서 캐시 CSV 의 빈 셀(_s() → None)이
#    저장된 값을 NULL 로 덮는다. 스펙 문자 그대로이며 의도된 동작이다:
#    「값 없음은 변경 아님」 규칙은 «변경 감지 필드»(CHANGE_FIELDS) 에만 적용된다.
#    캐시에 «행 자체가 없는» 종목은 키를 아예 안 넣어 보존한다(update_map 참조).
SIDE_FIELDS = ("corp_code", "market", "kosdaq_dept", "products",
               "listing_date", "settle_month", "source_asof")
MAX_CHANGE_RATIO = 0.05


def is_blank(v) -> bool:
    """None·공백 문자열 = «값 없음». 🔴 값 없음은 «변경»이 아니다 — 유지한다."""
    return v is None or (isinstance(v, str) and v.strip() == "")


def parent_code(stock_code):
    """우선주(끝자리 ≠ '0')의 부모 = 앞 5자리 + '0'. 보통주면 None."""
    s = (stock_code or "").strip()
    if len(s) != 6 or s[5] == "0":
        return None
    return s[:5] + "0"


def apply_parent_rule(candidates: dict, universe) -> dict:
    """우선주 후보에 부모 값을 «필드별로» 채운다.

    🔴 부모 규칙이 «열린 줄 값보다» 우선이다 — 부모 업종이 바뀌면 자식도 그날 바뀐다.
       그래서 호출측(collector)은 우선주 후보에 열린 줄 값을 «승계하지 않는다».
    - ksic_code·corp_code 는 부모가 ksic_code 를 가질 때만 함께 온다(한 몸).
      출처는 'parent:<부모코드>' 로 못박아 ② KSIC 채우기 대상에서 빠지게 한다.
    - ksic3_name 은 부모가 이름을 가지면 KSIC 와 «독립»으로 복사한다.
    - 자기 캐시 값이 있으면 그것이 우선한다(우선주 Industry 는 실측 전부 NULL).
    """
    universe = set(universe or ())
    out = {}
    for code, cand in candidates.items():
        p = parent_code(code)
        new = dict(cand)
        if p is not None and p in universe:
            prow = candidates.get(p) or {}
            if is_blank(new.get("ksic_code")) and not is_blank(prow.get("ksic_code")):
                new["ksic_code"] = prow.get("ksic_code")
                new["ksic_source"] = "parent:%s" % p
                new["corp_code"] = prow.get("corp_code")
            if is_blank(new.get("ksic3_name")) and not is_blank(prow.get("ksic3_name")):
                new["ksic3_name"] = prow.get("ksic3_name")
        out[code] = new
    return out
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer.py -v
```
Expected: 5 passed

- [ ] **Step 5: T2 — SCD2 규칙 테스트를 쓴다 (실패)**

`tests/collectors/test_sector_writer.py` 끝에 추가:

```python
def _open(vf=date(2026, 1, 2), **kw):
    row = {"valid_from": vf, "ksic_code": None, "ksic3_name": None,
           "ksic_source": None, "ksic_checked_at": None, "corp_code": None}
    row.update(kw)
    return row


def test_same_value_opens_no_new_row():
    """값이 같으면 새 줄 0 — 제자리 갱신(last_seen_at·부수 열)만 한다."""
    plan = w.plan_map_changes(
        {"005930": _open(ksic_code="264", ksic3_name="가")},
        {"005930": {"ksic_code": "264", "ksic3_name": "가", "source_asof": date(2026, 9, 4)}},
        D)
    assert plan["open_new"] == [] and plan["close"] == []
    assert plan["counts"]["changed"] == 0
    assert len(plan["inplace"]) == 1
    assert plan["inplace"][0]["set"]["source_asof"] == date(2026, 9, 4)
    assert "collected_at" not in plan["inplace"][0]["set"], "collected_at 은 불변이다"


def test_null_to_value_fills_in_place():
    """🔴 NULL→값은 «이력»이 아니라 «알게 된 것» — 새 줄을 열지 않는다."""
    plan = w.plan_map_changes(
        {"005930": _open()},
        {"005930": {"ksic_code": "264", "ksic_source": "dart", "ksic3_name": "가"}},
        D)
    assert plan["open_new"] == [] and plan["close"] == []
    assert plan["counts"]["filled"] == 1 and plan["counts"]["changed"] == 0
    s = plan["inplace"][0]["set"]
    assert s["ksic_code"] == "264" and s["ksic_source"] == "dart" and s["ksic3_name"] == "가"


def test_value_to_value_closes_and_opens():
    """값→다른 값만 줄을 닫는다. valid_to = trade_date − 1일 · 새 줄 valid_from = trade_date.

    ⚠️ guard=False — 표본이 1종목이라 5% 가드(분모 = 비-NULL 열린 줄)가 무조건 걸린다.
       가드 자체는 T3 이 «분모가 충분한» 100종목 표본으로 따로 검증한다."""
    plan = w.plan_map_changes(
        {"005930": _open(vf=date(2026, 1, 2), ksic_code="264",
                         ksic_source="dart", ksic_checked_at=datetime(2026, 8, 1, 9, 0))},
        {"005930": {"ksic_code": "265", "ksic_source": "dart"}},
        D, guard=False)
    assert plan["close"] == [{"stock_code": "005930", "valid_from": date(2026, 1, 2),
                              "valid_to": date(2026, 9, 6)}]
    assert len(plan["open_new"]) == 1
    row = plan["open_new"][0]
    assert row["valid_from"] == D and row["ksic_code"] == "265"
    assert plan["counts"]["changed"] == 1
    assert plan["changed_codes"] == ["005930"]


def test_same_day_change_updates_in_place():
    """열린 줄이 «오늘» 시작이면 값→값도 제자리 갱신이다(PK 충돌·역전 방지).
    ⚠️ guard=False — 표본 1종목(위와 같은 이유)."""
    plan = w.plan_map_changes(
        {"005930": _open(vf=D, ksic_code="264")},
        {"005930": {"ksic_code": "265"}},
        D, guard=False)
    assert plan["close"] == [] and plan["open_new"] == []
    assert plan["inplace"][0]["set"]["ksic_code"] == "265"
    assert plan["counts"]["changed"] == 1
    assert plan["changed_codes"] == ["005930"]


def test_future_open_row_is_skipped_and_counted():
    """valid_from > trade_date(과거 날짜 재실행)면 그 종목은 건너뛰고 «센다»."""
    plan = w.plan_map_changes(
        {"005930": _open(vf=date(2026, 9, 10), ksic_code="264")},
        {"005930": {"ksic_code": "265"}},
        date(2026, 9, 7))
    assert plan["skipped_past"] == ["005930"]
    assert plan["counts"]["skipped_past"] == 1
    assert plan["inplace"] == [] and plan["open_new"] == [] and plan["close"] == []


def test_blank_new_value_is_not_a_change():
    """🔴 새 값이 NULL/공백이면 그 필드는 «유지» — 소스가 비어도 이력이 갈라지면 안 된다."""
    plan = w.plan_map_changes(
        {"005930": _open(ksic_code="264", ksic3_name="가")},
        {"005930": {"ksic_code": None, "ksic3_name": "   "}},
        D)
    assert plan["open_new"] == [] and plan["close"] == []
    assert plan["counts"]["changed"] == 0
    assert "ksic_code" not in plan["inplace"][0]["set"]
    assert "ksic3_name" not in plan["inplace"][0]["set"]


def test_new_row_inherits_ksic_checked_at():
    """새 줄의 ksic_checked_at 은 닫힌 줄 값을 «승계» — NULL 로 떨어지면
    재확인 큐(ASC NULLS FIRST) 맨 앞으로 튀어 예산을 먹는다.
    ⚠️ guard=False — 표본 1종목."""
    prev = datetime(2026, 8, 1, 9, 0)
    plan = w.plan_map_changes(
        {"005930": _open(ksic_code="264", ksic_checked_at=prev)},
        {"005930": {"ksic_code": "265"}},
        D, guard=False)
    assert plan["open_new"][0]["ksic_checked_at"] == prev


def test_new_stock_opens_row_at_trade_date():
    """처음 보는 종목은 valid_from = trade_date 로 연다."""
    plan = w.plan_map_changes({}, {"999999": {"ksic_code": "264"}}, D)
    assert plan["counts"]["new"] == 1
    assert plan["open_new"][0]["valid_from"] == D


def test_parent_change_opens_new_row_for_child():
    """T1 마지막 항목 — 부모가 값→값으로 바뀌면 «자식도» 새 줄을 연다.
    (우선주 후보엔 열린 줄 값을 승계하지 않으므로 부모 값이 그대로 후보가 된다)
    ⚠️ guard=False — 표본 2종목."""
    cands = w.apply_parent_rule(
        {"001040": {"ksic_code": "265"}, "00104K": {"ksic_code": None}},
        {"001040", "00104K"})
    plan = w.plan_map_changes(
        {"001040": _open(ksic_code="264"), "00104K": _open(ksic_code="264")},
        cands, D, guard=False)
    # 정렬은 ASCII 순 — '0'(0x30) < 'K'(0x4B) 이므로 "001040" 이 먼저다
    assert sorted(r["stock_code"] for r in plan["open_new"]) == ["001040", "00104K"]
    assert all(r["valid_from"] == D for r in plan["open_new"])
    assert sorted(plan["changed_codes"]) == ["001040", "00104K"]
```

- [ ] **Step 6: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer.py -v
```
Expected: FAIL — `AttributeError: module 'collectors.sector_writer' has no attribute 'plan_map_changes'`

- [ ] **Step 7: `plan_map_changes` 구현 (가드 «없이»)**

⚠️ 시그니처에는 `guard`·`create_missing` 를 «지금» 넣는다(테스트가 이미 넘긴다).
`guard` 는 Step 11 에서 실제 동작이 붙을 때까지 아무 일도 하지 않는다.

`collectors/sector_writer.py` 끝에 이어붙인다:

```python
def plan_map_changes(open_rows: dict, candidates: dict, trade_date,
                     guard: bool = True, create_missing: bool = True) -> dict:
    """§3.1 규칙을 «쓰기 계획»으로 만든다. DB 를 만지지 않는 순수 함수다.

    open_rows  : {stock_code: {"valid_from": date, "ksic_code", "ksic3_name",
                               "ksic_source", "ksic_checked_at", ...}}
    candidates : {stock_code: {후보 값}} — 없는 키는 «새 값 없음»으로 본다.
    guard      : False 면 5% 급변 가드를 «판정만 하고 던지지 않는다».
                 🔴 운영 경로는 «항상» 기본값 True 다. False 는 분모가 1~2 인 단위
                 테스트 전용이다(표본 1종목이면 값→값 1건이 곧 100% 라 무조건 걸린다).
    create_missing : False 면 열린 줄이 없는 종목을 «새로 만들지 않고 건너뛴다».
                 🔴 KSIC 응답 재생(--regen-map)처럼 «기존 행만» 고쳐야 하는 경로용 —
                 이 플래그가 없으면 부수 열이 전부 NULL 인 유령 행이 INSERT 된다.
    반환       : {"inplace", "close", "open_new", "changed_codes", "skipped_past",
                  "skipped_missing", "counts", "guard"}
                 (`counts` 안에도 `skipped_missing` 이 있다 — 무징후 절단 금지)
    """
    from datetime import timedelta
    inplace, close, open_new, skipped, changed_codes = [], [], [], [], []
    skipped_missing = []
    changed = filled = new = unchanged = 0
    num = dict((f, 0) for f in CHANGE_FIELDS)
    den = dict((f, sum(1 for r in open_rows.values() if not is_blank(r.get(f))))
               for f in CHANGE_FIELDS)

    for code in sorted(candidates):
        cand = candidates[code]
        cur = open_rows.get(code)
        if cur is None and not create_missing:
            skipped_missing.append(code)     # 무징후 절단 금지 — 건수로 남긴다
            continue
        if cur is None:
            row = dict((f, cand.get(f)) for f in CHANGE_FIELDS + SIDE_FIELDS)
            row["stock_code"] = code
            row["ksic_source"] = cand.get("ksic_source")
            row["ksic_checked_at"] = cand.get("ksic_checked_at")
            row["valid_from"] = cand.get("valid_from") or trade_date
            open_new.append(row)
            new += 1
            continue
        vf = cur.get("valid_from")
        if vf is not None and vf > trade_date:
            skipped.append(code)
            continue
        hard = [f for f in CHANGE_FIELDS
                if not is_blank(cand.get(f)) and not is_blank(cur.get(f))
                and cand.get(f) != cur.get(f)]
        fills = [f for f in CHANGE_FIELDS
                 if not is_blank(cand.get(f)) and is_blank(cur.get(f))]
        sets = dict((f, cand.get(f)) for f in SIDE_FIELDS if f in cand)
        if hard:
            for f in hard:
                num[f] += 1
            changed += 1
            changed_codes.append(code)
        if hard and vf != trade_date:
            close.append({"stock_code": code, "valid_from": vf,
                          "valid_to": trade_date - timedelta(days=1)})
            row = {}
            for f in CHANGE_FIELDS:
                row[f] = cand.get(f) if not is_blank(cand.get(f)) else cur.get(f)
            row.update(sets)
            row["stock_code"] = code
            row["valid_from"] = trade_date
            row["ksic_source"] = (cand.get("ksic_source")
                                  if not is_blank(cand.get("ksic_code"))
                                  else cur.get("ksic_source"))
            # 🔴 승계 — NULL 로 떨어지면 재확인 큐(ASC NULLS FIRST) 맨 앞으로 튄다.
            row["ksic_checked_at"] = (cand.get("ksic_checked_at")
                                      or cur.get("ksic_checked_at"))
            open_new.append(row)
            continue
        if fills:
            filled += 1
        for f in hard + fills:
            sets[f] = cand.get(f)
        if "ksic_code" in sets:
            sets["ksic_source"] = cand.get("ksic_source")
        if cand.get("ksic_checked_at") is not None:
            sets["ksic_checked_at"] = cand.get("ksic_checked_at")
        if not hard and not fills:
            unchanged += 1
        inplace.append({"stock_code": code, "valid_from": vf, "set": sets})

    guard_stats = {}
    for f in CHANGE_FIELDS:
        if den[f] == 0:          # 분모 0 이면 생략(최초 수집)
            continue
        guard_stats[f] = {"num": num[f], "den": den[f], "ratio": float(num[f]) / den[f]}

    return {"inplace": inplace, "close": close, "open_new": open_new,
            "changed_codes": changed_codes, "skipped_past": skipped,
            "skipped_missing": skipped_missing,
            "counts": {"changed": changed, "filled": filled, "new": new,
                       "unchanged": unchanged, "skipped_past": len(skipped),
                       "skipped_missing": len(skipped_missing)},
            "guard": guard_stats}
```

⚠️ 지역변수 이름이 `guard_stats` 인 것은 «인자 `guard`(bool)와 겹치지 않게» 하려는 것이다 —
반환 dict 의 키는 그대로 `"guard"` 다(소비자 계약 불변).

- [ ] **Step 8: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer.py -v
```
Expected: 14 passed (T1 5개 + T2 9개)

- [ ] **Step 9: T3 — 급변 가드 테스트를 쓴다 (실패)**

`tests/collectors/test_sector_writer.py` 끝에 추가:

```python
def _many(n, ksic="264"):
    return dict(("%06d" % i, _open(ksic_code=ksic, ksic3_name="가")) for i in range(n))


def test_guard_raises_over_five_percent():
    """🔴 값→값이 5% 를 넘으면 한 행도 쓰지 않는다 — 소스가 통째로 바뀐 날이다."""
    opens = _many(100)
    cands = {}
    for i in range(100):
        code = "%06d" % i
        cands[code] = {"ksic_code": "265" if i < 6 else "264", "ksic3_name": "가"}
    with pytest.raises(RuntimeError) as e:
        w.plan_map_changes(opens, cands, D)
    assert "ksic_code" in str(e.value) and "6/100" in str(e.value)


def test_guard_allows_exactly_five_percent():
    """경계 — «초과»만 막는다(5.0% 는 통과)."""
    opens = _many(100)
    cands = dict(("%06d" % i,
                  {"ksic_code": "265" if i < 5 else "264", "ksic3_name": "가"})
                 for i in range(100))
    plan = w.plan_map_changes(opens, cands, D)
    assert plan["counts"]["changed"] == 5
    assert abs(plan["guard"]["ksic_code"]["ratio"] - 0.05) < 1e-9


def test_guard_ignores_null_fills():
    """NULL→값 300건은 «변경»이 아니므로 가드에 안 걸린다(분자에 안 들어간다)."""
    opens = dict(("%06d" % i, _open()) for i in range(300))
    cands = dict(("%06d" % i, {"ksic_code": "264", "ksic_source": "dart"})
                 for i in range(300))
    plan = w.plan_map_changes(opens, cands, D)
    assert plan["counts"]["filled"] == 300
    assert plan["guard"] == {}, "분모(비-NULL 열린 줄)가 0 이면 가드는 생략된다"


def test_guard_skips_when_denominator_zero():
    """분모 0 = 최초 수집. 가드를 걸면 첫 수집이 영원히 불가능해진다."""
    plan = w.plan_map_changes({}, {"005930": {"ksic_code": "264"}}, D)
    assert plan["guard"] == {}
```

- [ ] **Step 10: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer.py -v
```
Expected: FAIL — `DID NOT RAISE <class 'RuntimeError'>` (test_guard_raises_over_five_percent)

- [ ] **Step 11: 가드를 넣는다**

`plan_map_changes` 의 `guard_stats` 계산 «뒤», `return` «앞»에 삽입:

```python
    over = [f for f in sorted(guard_stats)
            if guard_stats[f]["ratio"] > MAX_CHANGE_RATIO]
    if guard and over:
        raise RuntimeError(
            "섹터 명부 소스 급변 — 한 행도 쓰지 않음(어제 명부 보존): "
            + " · ".join("%s %d/%d(%.1f%%) > %.0f%%"
                         % (f, guard_stats[f]["num"], guard_stats[f]["den"],
                            100.0 * guard_stats[f]["ratio"], 100.0 * MAX_CHANGE_RATIO)
                         for f in over))
    if over and not guard:
        logger.warning("[sector] 급변 가드 대상이지만 guard=False 로 통과: %s",
                       [(f, guard_stats[f]) for f in over])
```

🔴 `guard=False` 는 **테스트 전용**이다. 운영 경로(`update_map`·`apply_ksic_updates`·
`recopy_preferred`·`regen_map`)는 인자를 넘기지 않으므로 기본값 True 로 돈다 —
Task 2 Step 13 의 `test_guard_trip_means_zero_writes` 가 그 기본값을 고정한다.

- [ ] **Step 12: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer.py -v
```
Expected: 18 passed

- [ ] **Step 13: `write_map` · `load_open_rows` · 부수 읽기 구현 + 「가드 시 쓰기 0」 테스트**

`collectors/sector_writer.py` 끝에 이어붙인다:

```python
_UPDATABLE = frozenset(CHANGE_FIELDS + SIDE_FIELDS + ("ksic_source", "ksic_checked_at"))

_INSERT_ROW = """
INSERT INTO stock_sector_map
  (stock_code, valid_from, valid_to, ksic_code, ksic_source, ksic3_name, corp_code,
   market, kosdaq_dept, products, listing_date, settle_month, source, source_asof,
   ksic_checked_at)
VALUES (%(stock_code)s, %(valid_from)s, NULL, %(ksic_code)s, %(ksic_source)s,
        %(ksic3_name)s, %(corp_code)s, %(market)s, %(kosdaq_dept)s, %(products)s,
        %(listing_date)s, %(settle_month)s, %(source)s, %(source_asof)s,
        %(ksic_checked_at)s)
"""

_CLOSE_ROW = ("UPDATE stock_sector_map SET valid_to=%(valid_to)s "
              "WHERE stock_code=%(stock_code)s AND valid_from=%(valid_from)s")

_OPEN_ROWS_SQL = (
    "SELECT stock_code, valid_from, ksic_code, ksic_source, ksic3_name, corp_code, "
    "       market, source, source_asof, ksic_checked_at, last_seen_at "
    "FROM stock_sector_map WHERE valid_to IS NULL")


def load_open_rows(conn) -> dict:
    """열린 줄 전부. 급변 가드의 «분모»이므로 표본이 아니라 전체를 읽는다."""
    try:
        with conn.cursor() as cur:
            cur.execute(_OPEN_ROWS_SQL)
            cols = [d[0] for d in cur.description]
            return dict((r[0], dict(zip(cols, r))) for r in cur.fetchall())
    except Exception:
        conn.rollback()
        raise


def open_market_counts(conn) -> dict:
    """열린 줄의 시장별 행수 — 캐시 CSV 규모 하한의 기준선."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT market, count(*) FROM stock_sector_map "
                        "WHERE valid_to IS NULL AND market IS NOT NULL GROUP BY 1")
            return dict((str(m), int(n)) for m, n in cur.fetchall())
    except Exception:
        conn.rollback()
        raise


def load_stock_industry(conn) -> dict:
    """🔴 stock_industry 는 «부트스트랩에서만» 읽는다(스냅샷 2026-08-07 · 갱신 소스 없음).

    ⚠️ §7 — 길이 5 초과 코드는 «저장은 하되» WARN 한다(현재 실측 0건 · varchar(10)).
       DART 응답 경로에만 경고를 달면 스냅샷 경로로 들어온 이상값이 조용히 지나간다.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, induty_code FROM stock_industry "
                        "WHERE induty_code IS NOT NULL AND induty_code <> ''")
            out = dict((r[0], r[1]) for r in cur.fetchall())
    except Exception:
        conn.rollback()
        raise
    long_codes = [(c, v) for c, v in out.items() if len(v or "") > 5]
    if long_codes:
        logger.warning("[sector] stock_industry 에 길이 5 초과 induty_code %d건 - "
                       "저장은 하되 확인 필요: %s", len(long_codes), long_codes[:5])
    return out


def write_map(conn, plan: dict, source: str) -> dict:
    """계획을 «한 트랜잭션»으로 쓴다. 실패하면 통째로 롤백된다.

    ⚠️ collected_at 은 어느 경로에서도 쓰지 않는다(불변) · last_seen_at 은 «항상» 갱신.
    """
    n_close = n_new = n_up = 0
    try:
        with conn.cursor() as cur:
            for c in plan["close"]:
                cur.execute(_CLOSE_ROW, c)
                n_close += 1
            for r in plan["open_new"]:
                row = dict(r)
                for f in ("ksic_code", "ksic_source", "ksic3_name", "corp_code", "market",
                          "kosdaq_dept", "products", "listing_date", "settle_month",
                          "source_asof", "ksic_checked_at"):
                    row.setdefault(f, None)
                row["source"] = row.get("source") or source
                cur.execute(_INSERT_ROW, row)
                n_new += 1
            for u in plan["inplace"]:
                sets = dict(u["set"])
                bad = set(sets) - _UPDATABLE
                if bad:
                    raise ValueError("갱신 불가 컬럼: %s" % sorted(bad))
                cols = ", ".join("%s=%%(%s)s" % (k, k) for k in sorted(sets))
                sql = ("UPDATE stock_sector_map SET last_seen_at=now()"
                       + ((", " + cols) if cols else "")
                       + " WHERE stock_code=%(stock_code)s AND valid_from=%(valid_from)s")
                params = dict(sets)
                params["stock_code"] = u["stock_code"]
                params["valid_from"] = u["valid_from"]
                cur.execute(sql, params)
                n_up += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"closed": n_close, "inserted": n_new, "updated": n_up}
```

테스트 추가(`tests/collectors/test_sector_writer.py` 끝):

```python
class _FakeCur:
    def __init__(self, log):
        self.log = log
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))


class _FakeConn:
    def __init__(self):
        self.log = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _FakeCur(self.log)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_guard_trip_means_zero_writes():
    """🔴 가드가 걸리면 «한 행도» 안 쓴다 — 계획 단계에서 터지므로 SQL 이 0건이다."""
    conn = _FakeConn()
    opens = _many(100)
    cands = dict(("%06d" % i,
                  {"ksic_code": "265" if i < 10 else "264", "ksic3_name": "가"})
                 for i in range(100))
    with pytest.raises(RuntimeError):
        plan = w.plan_map_changes(opens, cands, D)
        w.write_map(conn, plan, "eod")
    assert conn.log == [] and conn.commits == 0


def test_write_map_always_touches_last_seen_and_never_collected_at():
    """제자리 갱신은 last_seen_at 을 «항상» 올리고 collected_at 은 절대 안 만진다."""
    conn = _FakeConn()
    plan = w.plan_map_changes(
        {"005930": _open(ksic_code="264", ksic3_name="가")},
        {"005930": {"ksic_code": "264", "ksic3_name": "가"}},
        D)
    out = w.write_map(conn, plan, "eod")
    assert out == {"closed": 0, "inserted": 0, "updated": 1}
    sql = conn.log[0][0]
    assert "last_seen_at=now()" in sql
    assert "collected_at" not in sql
```

- [ ] **Step 14: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer.py -v
```
Expected: 20 passed

- [ ] **Step 15: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): 명부 SCD2 규칙 — 우선주 부모 복사·값 없음은 변경 아님·5% 급변 가드 (Task 2)

plan_map_changes 는 순수 함수로 «쓰기 계획»만 만들고 write_map 이 한 트랜잭션으로 쓴다.
NULL→값은 제자리 채움, 비-NULL→다른 비-NULL 만 줄을 닫는다. 열린 줄이 오늘 시작이면
제자리 갱신하고 valid_from > trade_date 면 건너뛰며 센다. 새 줄은 ksic_checked_at 을
승계해 재확인 큐 맨 앞으로 튀지 않게 한다. collected_at 은 어느 경로에서도 안 만진다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/sector_writer.py RoboTrader_template/tests/collectors/test_sector_writer.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 3: `krx_desc_cache` — 날짜 지정 GitHub CSV + 후퇴 폴백 + 규모 하한 (T4)

**Files:**
- Create: `RoboTrader_template/collectors/krx_desc_cache.py`
- Create: `RoboTrader_template/tests/collectors/test_sector_collector.py`

**Interfaces:**
- Consumes: `requests`(주입 가능한 `fetcher` 로 감싼다) · `pandas`(CSV 파싱만)
- Produces:
  - `GITHUB_DESC_BASE: str` · `ARCHIVE_DIR: str` · `MAX_BACKOFF_DAYS = 7` · `MIN_SCALE_RATIO = 0.8` · `MARKET_GROUPS: dict` · `IGNORED_MARKETS = ("KONEX",)`
  - `fetch_desc_csv(trade_date, fetcher=None, max_back_days=7) -> (source_asof: date, raw: bytes)`
  - `parse_desc_csv(raw: bytes) -> (rows: list, dropped: dict)`
  - `fold_market_counts(raw_counts: dict) -> dict`
  - `market_counts(rows: list) -> dict`
  - `check_scale_floor(existing: dict, collected: dict) -> None`
  - `archive_raw(source_asof, raw: bytes) -> str`
  - `load_desc(trade_date, existing_counts=None, fetcher=None, archive=True) -> dict` — `{"source_asof","rows","counts","dropped","archive"}` (`archive=False` 면 `archive` 는 `None`)

- [ ] **Step 1: T4 테스트를 쓴다 (실패)**

```python
# tests/collectors/test_sector_collector.py
"""섹터 수집기 테스트 (T4 · T5 · T6 · T7-b · T8 · T14). DB 를 쓰지 않는다."""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from collectors import krx_desc_cache as kdc  # noqa: E402

HEADER = "Code,Name,Market,Sector,Industry,Products,ListingDate,SettleMonth,Representative,HomePage,Region"


def _csv(rows):
    """rows: [(code, name, market, sector, industry)] → 캐시 CSV 바이트."""
    body = [HEADER]
    for code, name, market, sector, industry in rows:
        body.append("%s,%s,%s,%s,%s,제품,2000-01-01,12월,대표,http://x,서울"
                    % (code, name, market, sector, industry))
    return ("\n".join(body) + "\n").encode("utf-8")


def _fake_fetcher(available):
    """available: {날짜 ISO: bytes} — 그 밖의 날짜는 404."""
    def _fn(url):
        key = url.rsplit("/", 1)[-1].replace(".csv", "")
        if key in available:
            return 200, available[key]
        return 404, b""
    return _fn


def test_backoff_records_publish_date_as_source_asof():
    """404 면 하루씩 후퇴하고, «실제로 읽은 파일의 날짜»가 source_asof 다."""
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업")])
    asof, body = kdc.fetch_desc_csv(date(2026, 9, 7),
                                    fetcher=_fake_fetcher({"2026-09-04": raw}))
    assert asof == date(2026, 9, 4)
    assert body == raw


def test_eighth_day_404_fails():
    """7일 후퇴까지 없으면 실패 — 조용히 빈 명부를 만들지 않는다."""
    with pytest.raises(RuntimeError) as e:
        kdc.fetch_desc_csv(date(2026, 9, 7), fetcher=_fake_fetcher({}))
    assert "2026-08-31" in str(e.value), "8번째 시도(7일 후퇴)까지 기록돼야 한다"


def test_konex_rows_are_ignored():
    """KONEX 는 U_all 밖이라 적재·검증 대상이 아니다."""
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업"),
                ("900001", "코넥스사", "KONEX", "", "기타")])
    rows, dropped = kdc.parse_desc_csv(raw)
    assert [r["stock_code"] for r in rows] == ["005930"]
    assert dropped["konex"] == 1


def test_kosdaq_global_folds_into_kosdaq_group():
    """소형 세그먼트(GLOBAL 50)는 KOSDAQ 묶음에 합쳐 30건 오차로 흔들리지 않게 한다."""
    raw = _csv([("035720", "카카오", "KOSPI", "", "포털"),
                ("247540", "에코프로", "KOSDAQ", "중견기업부", "전지"),
                ("196170", "알테오젠", "KOSDAQ GLOBAL", "우량기업부", "의약품")])
    rows, _ = kdc.parse_desc_csv(raw)
    assert kdc.market_counts(rows) == {"KOSPI": 1, "KOSDAQ": 2}


def test_scale_floor_blocks_partial_kosdaq(tmp_path, monkeypatch):
    """🔴 KOSDAQ 묶음만 20건 오면 한 행도 쓰지 않는다 — 보관 파일도 안 만든다."""
    monkeypatch.setattr(kdc, "ARCHIVE_DIR", str(tmp_path))
    rows = [("00%04d" % i, "n%d" % i, "KOSPI", "", "업종") for i in range(900)]
    rows += [("01%04d" % i, "m%d" % i, "KOSDAQ", "중견기업부", "업종") for i in range(20)]
    raw = _csv(rows)
    with pytest.raises(RuntimeError) as e:
        kdc.load_desc(date(2026, 9, 7), {"KOSPI": 943, "KOSDAQ": 1822},
                      fetcher=_fake_fetcher({"2026-09-07": raw}))
    assert "KOSDAQ" in str(e.value)
    assert os.listdir(str(tmp_path)) == [], "하한 미달인데 보관 파일이 생겼다"


def test_scale_floor_exempts_empty_baseline(tmp_path, monkeypatch):
    """기존 0건은 면제 — 아니면 최초 수집이 영원히 불가능하다."""
    monkeypatch.setattr(kdc, "ARCHIVE_DIR", str(tmp_path))
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업")])
    out = kdc.load_desc(date(2026, 9, 7), {}, fetcher=_fake_fetcher({"2026-09-07": raw}))
    assert out["source_asof"] == date(2026, 9, 7)
    assert len(out["rows"]) == 1
    assert os.path.basename(out["archive"]) == "krx_desc_2026-09-07.csv.gz"
    assert os.path.exists(out["archive"])


def test_zero_rows_fails():
    """0건은 성공이 아니다."""
    with pytest.raises(RuntimeError):
        kdc.parse_desc_csv((HEADER + "\n").encode("utf-8"))


def test_archive_false_writes_no_file(tmp_path, monkeypatch):
    """🔴 `--dry-run` 경로 — gz 를 안 쓰고 archive 는 None 이다.
    (로그 포맷이 basename(None) 으로 죽지 않는지도 여기서 걸린다)"""
    monkeypatch.setattr(kdc, "ARCHIVE_DIR", str(tmp_path))
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업")])
    out = kdc.load_desc(date(2026, 9, 7), {}, fetcher=_fake_fetcher({"2026-09-07": raw}),
                        archive=False)
    assert out["archive"] is None
    assert os.listdir(str(tmp_path)) == [], "dry-run 인데 보관 파일이 생겼다"
    assert len(out["rows"]) == 1 and out["source_asof"] == date(2026, 9, 7)
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 수집 단계 오류 — `ModuleNotFoundError: No module named 'collectors.krx_desc_cache'`

- [ ] **Step 3: `krx_desc_cache.py` 구현**

```python
# collectors/krx_desc_cache.py
"""KRX 상장목록 캐시 CSV 를 «날짜 지정»으로 직접 읽는다. FDR 을 부르지 않는다.

🔑 fdr.StockListing('KRX-DESC') 는 결국 이 CSV 를 읽는다
   (venv/.../FinanceDataReader/data.py:175 KrxStockListingCache). FDR 을 거치면
   ①KRX 포털 bld 호출이 1건 붙고 ②응답에 «기준일»이 안 남는다. 직접 읽으면
   호출 0 + 파일명이 그대로 source_asof 다.
🔴 파일명은 «게시일»이지 «내용 기준일»이 아니다 — 토요일 파일은 금요일 파일과
   바이트 동일하다(실측 md5 874ee3c0…). 그래서 source_asof 의 의미는
   «내용 기준일 ≤ 게시일» 이고, 매일 뒤처지면 §8-7 이 WARN 한다.
🔴 KIS 를 쓰지 않는다(앱키당 토큰 1개 — 봇 가동 중 호출은 라이브 토큰을 무효화한다).
"""
import gzip
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

GITHUB_DESC_BASE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                    "refs/heads/master/data/listing/desc")
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "scratchpad", "sector")
MAX_BACKOFF_DAYS = 7
MIN_SCALE_RATIO = 0.8
# 시장 «묶음»별로 하한을 건다 — 합계로 걸면 한쪽 붕괴를 다른 쪽이 가려준다.
MARKET_GROUPS = {"KOSPI": ("KOSPI",), "KOSDAQ": ("KOSDAQ", "KOSDAQ GLOBAL")}
IGNORED_MARKETS = ("KONEX",)


def _default_fetcher(url):
    import requests
    r = requests.get(url, timeout=30)
    return r.status_code, r.content


def fetch_desc_csv(trade_date, fetcher=None, max_back_days=MAX_BACKOFF_DAYS):
    """{trade_date}.csv 부터 하루씩 최대 max_back_days 후퇴. → (source_asof, raw)."""
    fn = fetcher or _default_fetcher
    tried = []
    for back in range(0, max_back_days + 1):
        d = trade_date - timedelta(days=back)
        status, body = fn("%s/%s.csv" % (GITHUB_DESC_BASE, d.isoformat()))
        tried.append("%s:%s" % (d.isoformat(), status))
        if status == 200 and body:
            if back:
                logger.warning("[krx_desc] %s 캐시 없음 - %d일 후퇴해 %s 사용",
                               trade_date, back, d)
            return d, body
    raise RuntimeError("KRX desc 캐시 CSV 를 %d일 후퇴까지 못 찾음: %s"
                       % (max_back_days, " · ".join(tried)))


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def parse_desc_csv(raw: bytes):
    """→ (rows, dropped). Code 6자리 정규화 · KONEX 제외(U_all 밖) · 0건이면 RuntimeError."""
    import io
    import pandas as pd
    df = pd.read_csv(io.BytesIO(raw), dtype=str)
    rows = []
    dropped = {"konex": 0, "bad_code": 0}
    for rec in df.to_dict("records"):
        code = _s(rec.get("Code"))
        market = _s(rec.get("Market"))
        if not code:
            dropped["bad_code"] += 1
            continue
        if market in IGNORED_MARKETS:
            dropped["konex"] += 1
            continue
        rows.append({
            "stock_code": code.zfill(6),
            "market": market,
            "ksic3_name": _s(rec.get("Industry")),
            "kosdaq_dept": _s(rec.get("Sector")),
            "products": _s(rec.get("Products")),
            "listing_date": _s(rec.get("ListingDate")),
            "settle_month": _s(rec.get("SettleMonth")),
        })
    if not rows:
        raise RuntimeError("KRX desc 캐시 CSV 파싱 결과 0건 — 형식이 바뀌었거나 빈 응답이다")
    return rows, dropped


def fold_market_counts(raw_counts: dict) -> dict:
    """{시장: n} → {묶음: n}. 묶음 밖 시장(KONEX 등)은 버린다."""
    out = dict((g, 0) for g in MARKET_GROUPS)
    for m, n in (raw_counts or {}).items():
        for g, members in MARKET_GROUPS.items():
            if m in members:
                out[g] += int(n)
    return out


def market_counts(rows) -> dict:
    tally = {}
    for r in rows:
        tally[r["market"]] = tally.get(r["market"], 0) + 1
    return fold_market_counts(tally)


def check_scale_floor(existing: dict, collected: dict) -> None:
    """묶음별 규모 하한. 기존 0 은 면제(최초 수집). 미달이면 RuntimeError — 쓰기 «전»에 부른다.

    ⚠️ 기준선(열린 줄)은 상폐로 줄지 않으므로 약 6년 뒤엔 정상 수집도 거부될 수 있다.
       stock_market_collector 와 같은 «소리 나는» 한계다(그때 기준을 다시 잡는다).
    """
    short = []
    for g in sorted(MARKET_GROUPS):
        prev = int((existing or {}).get(g, 0))
        if prev <= 0:
            continue
        floor = prev * MIN_SCALE_RATIO
        n = int((collected or {}).get(g, 0))
        if n < floor:
            short.append("%s %d건 < 기존 %d건의 %.0f%%(%.0f건)"
                         % (g, n, prev, MIN_SCALE_RATIO * 100, floor))
    if short:
        raise RuntimeError("KRX desc 캐시 규모 하한 미달 — 한 행도 쓰지 않음"
                           "(어제 명부 유지): " + " · ".join(short))


def archive_raw(source_asof, raw: bytes) -> str:
    """원본 gz 보관 — §5-4 `--regen-map` 의 원료다. 같은 게시일 파일은 덮어쓰지 않는다."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    path = os.path.join(ARCHIVE_DIR, "krx_desc_%s.csv.gz" % source_asof.isoformat())
    if not os.path.exists(path):
        with gzip.open(path, "wb") as fh:
            fh.write(raw)
    return path


def load_desc(trade_date, existing_counts=None, fetcher=None, archive=True) -> dict:
    """읽기 → 파싱 → 규모 하한 → 보관. 검증은 «반드시» 보관·쓰기보다 먼저다.

    archive=False 는 `--dry-run` 전용이다 — dry-run 이 gz 를 남기면 「쓰기 0」이 거짓이 되고,
    §5-4 재생성 원료에 «실제로는 안 쓴 날»의 파일이 섞인다.
    """
    source_asof, raw = fetch_desc_csv(trade_date, fetcher=fetcher)
    rows, dropped = parse_desc_csv(raw)
    counts = market_counts(rows)
    check_scale_floor(existing_counts or {}, counts)
    path = archive_raw(source_asof, raw) if archive else None
    logger.info("[krx_desc] %s 게시분 %d행 (%s) 보관=%s",
                source_asof, len(rows), counts,
                os.path.basename(path) if path else "(dry-run)")
    return {"source_asof": source_asof, "rows": rows, "counts": counts,
            "dropped": dropped, "archive": path}
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 8 passed

- [ ] **Step 5: 실제 GitHub 응답이 오는지 «한 번» 확인한다(네트워크 1회 · DB 쓰기 0)**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -c "import sys; sys.path.insert(0,'.'); from datetime import date; from collectors import krx_desc_cache as k; a,b=k.fetch_desc_csv(date.today()); print('source_asof=',a,'bytes=',len(b)); rows,dr=k.parse_desc_csv(b); print('rows=',len(rows),'dropped=',dr); print('counts=',k.market_counts(rows))"
```
Expected: `source_asof=` 오늘 또는 직전 게시일 · `bytes=` 약 55만 · `rows=` 약 2,765(2,873 − KONEX 108) · `counts=` KOSPI 약 943 · KOSDAQ 약 1,822

- [ ] **Step 6: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): krx_desc_cache — GitHub 캐시 CSV 날짜 지정 읽기 + 7일 후퇴 + 규모 하한 (Task 3)

FDR 을 부르지 않는다(KRX 포털 호출 0). 파일명이 그대로 source_asof(게시일)이며
내용 기준일은 그 이하다. 규모 하한은 KOSPI / KOSDAQ+GLOBAL 두 묶음에 각각 걸고
기존 0 은 면제한다. KONEX 는 U_all 밖이라 버린다. 검증은 보관·쓰기보다 먼저다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/krx_desc_cache.py RoboTrader_template/tests/collectors/test_sector_collector.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 4: `dart_company_fetcher` — `company.json` 스로틀 클라이언트

**Files:**
- Create: `RoboTrader_template/collectors/dart_company_fetcher.py`
- Modify: `RoboTrader_template/tests/collectors/test_sector_collector.py` (fetcher 단위 테스트 추가)

**Interfaces:**
- Consumes: `collectors.dart_financial_fetcher.DartQuotaExceeded` · `DartBlocked` (**같은 호스트의 같은 상태코드에 예외 두 벌을 만들지 않는다**)
- Produces:
  - `class DartCompanyFetcher: __init__(self, key: str, min_interval: float = 0.34)` · `fetch(self, corp_code: str) -> (status: str, payload: dict)` · 속성 `calls`·`status_counts`·`http_errors`·`conn_resets`·`reset_streak`
  - `append_company_raw(path: str, payload: dict) -> int` — 비압축 JSONL append · 1-based 줄 번호 반환

- [ ] **Step 1: fetcher 테스트를 쓴다 (실패)**

`tests/collectors/test_sector_collector.py` 끝에 추가:

```python
from collectors import dart_company_fetcher as dcf  # noqa: E402
from collectors.dart_financial_fetcher import DartBlocked, DartQuotaExceeded  # noqa: E402


class _Resp:
    def __init__(self, status_code=200, js=None):
        self.status_code = status_code
        self._js = js or {}

    def json(self):
        return self._js


class _Sess:
    def __init__(self, seq):
        self.seq = list(seq)
        self.gets = []
        self.closed = 0

    def get(self, url, params=None, timeout=None):
        self.gets.append(params)
        nxt = self.seq.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def close(self):
        self.closed += 1


def test_company_fetcher_raises_on_quota(monkeypatch):
    """020(한도초과)은 «예외»로 올린다 — 삼키면 조용한 빈 수집이 성공으로 보인다."""
    monkeypatch.setattr(dcf.time, "sleep", lambda s: None)
    f = dcf.DartCompanyFetcher("k")
    f.session = _Sess([_Resp(200, {"status": "020", "message": "한도초과"})])
    with pytest.raises(DartQuotaExceeded):
        f.fetch("00126380")


def test_company_fetcher_blocks_after_three_transport_failures(monkeypatch):
    """전송 실패 3연속 = IP 차단으로 판단(재무 fetcher 와 같은 규약)."""
    import requests
    monkeypatch.setattr(dcf.time, "sleep", lambda s: None)
    f = dcf.DartCompanyFetcher("k")
    f.session = _Sess([requests.exceptions.ConnectionError(),
                       requests.exceptions.Timeout(),
                       requests.exceptions.ConnectionError()])
    monkeypatch.setattr(dcf.requests, "Session", lambda: f.session)
    with pytest.raises(DartBlocked):
        f.fetch("00126380")


def test_company_fetcher_returns_induty_code(monkeypatch):
    """정상 응답은 (status, payload) 로 그대로 돌려준다 — 파싱은 호출측 몫."""
    monkeypatch.setattr(dcf.time, "sleep", lambda s: None)
    f = dcf.DartCompanyFetcher("k")
    f.session = _Sess([_Resp(200, {"status": "000", "induty_code": "2611"})])
    status, js = f.fetch("00126380")
    assert status == "000" and js["induty_code"] == "2611"
    assert f.calls == 1 and f.status_counts["000"] == 1


def test_append_company_raw_returns_line_numbers(tmp_path):
    """§5-4 재생성의 원료 — 줄 번호가 1부터 증가해야 한다."""
    p = str(tmp_path / "dart_company_2026-09-07.jsonl")
    assert dcf.append_company_raw(p, {"a": 1}) == 1
    assert dcf.append_company_raw(p, {"a": 2}) == 2
    with open(p, encoding="utf-8") as fh:
        assert len(fh.readlines()) == 2
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 수집 단계 오류 — `ModuleNotFoundError: No module named 'collectors.dart_company_fetcher'`

- [ ] **Step 3: `dart_company_fetcher.py` 구현**

```python
# collectors/dart_company_fetcher.py
"""DART company.json 최소 클라이언트 (운영 EOD 경로).

🔴 DartFinancialFetcher(collectors/dart_financial_fetcher.py) 의 «미러»다 —
   min_interval=0.34(3 req/s · B1 20,241호출 동안 리셋 0 실측) · 020 은 예외로 올리고
   800(점검)·HTTP 실패는 백오프 재시도 · 전송 실패 3연속이면 DartBlocked.
🔴 예외 클래스는 재무 fetcher 것을 그대로 import 한다. 같은 호스트의 같은 상태코드에
   예외가 두 벌 있으면 호출측이 한쪽만 잡아 «차단»이 «성공»으로 흘러간다.
🔴 동시 요청 금지(2026-08-06 실측: 4스레드로 opendart 전 호스트가 리셋 상태).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from collectors.dart_financial_fetcher import DartBlocked, DartQuotaExceeded  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"
_MAX_TRIES = 6
_BACKOFF_START = 2.0
_BACKOFF_CAP = 30.0


class DartCompanyFetcher:
    def __init__(self, key: str, min_interval: float = 0.34):
        self.key = key
        self.session = requests.Session()
        self.min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0
        self.status_counts = {}
        self.http_errors = 0
        self.conn_resets = 0
        self.reset_streak = 0

    def _bump(self, status):
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def _throttle(self):
        gap = time.time() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_call = time.time()

    def fetch(self, corp_code: str):
        """→ (status, payload). 020 은 예외, 013(무자료)은 정상 반환."""
        url = "%s/company.json" % DART_BASE
        params = {"crtfc_key": self.key, "corp_code": corp_code}
        backoff = _BACKOFF_START
        for _ in range(_MAX_TRIES):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=25)
                self.calls += 1
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                self.conn_resets += 1
                self.reset_streak += 1
                if self.reset_streak >= 3:
                    logger.error("DartBlocked: 전송 실패 3연속 (corp_code=%s)", corp_code)
                    raise DartBlocked("전송 실패 3연속 - opendart IP 차단으로 판단")
                self.session.close()
                self.session = requests.Session()
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue
            except Exception:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue

            self.reset_streak = 0
            if r.status_code != 200:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue
            try:
                js = r.json()
            except ValueError:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue

            status = js.get("status")
            self._bump(status)
            if status == "020":
                logger.error("DartQuotaExceeded: 일일사용한도초과 (corp_code=%s)", corp_code)
                raise DartQuotaExceeded("DART 일일 사용한도 초과(status=020)")
            if status == "800":       # 시스템 점검
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue
            if status not in ("000", "013"):
                logger.warning("Unexpected DART status=%s (corp_code=%s, message=%s)",
                               status, corp_code, js.get("message", ""))
            return status, js

        self._bump("HTTP_FAIL")
        logger.warning("HTTP_FAIL: retry loop exhausted (corp_code=%s, attempts=%d)",
                       corp_code, _MAX_TRIES)
        return "HTTP_FAIL", {}


def append_company_raw(path: str, payload: dict) -> int:
    """원본 응답을 «비압축» JSONL 에 append 하고 1-based 줄 번호를 돌려준다.

    🔑 f2_raw 전례 — 원본을 남겨 뒀기 때문에 호출 0건으로 확장이 가능했다.
       여기 원본은 §5-4 `--regen-map` 이 ksic_code·ksic_source·ksic_checked_at 을
       되살리는 «유일한» 원료다(캐시 CSV 엔 코드 열이 없다).
    """
    abspath = os.path.abspath(path)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    n = 0
    if os.path.exists(abspath):
        with open(abspath, encoding="utf-8") as fh:
            for _ in fh:
                n += 1
    with open(abspath, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return n + 1
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 12 passed

- [ ] **Step 5: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): DART company.json 스로틀 클라이언트 (Task 4)

DartFinancialFetcher 미러 — min_interval=0.34 · 020 은 예외 · 800/HTTP 실패는 백오프 ·
전송 실패 3연속이면 DartBlocked. 예외 클래스는 재무 fetcher 것을 그대로 쓴다
(같은 호스트에 예외가 두 벌이면 호출측이 한쪽만 잡는다).
원본은 비압축 JSONL 로 남긴다 — --regen-map 이 KSIC 계열을 되살리는 유일한 원료다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/dart_company_fetcher.py RoboTrader_template/tests/collectors/test_sector_collector.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 5: KSIC 채우기(a) + 재확인 순환(b) + 레일 + 우선주 재복사(c) + nodata + corp_code 주 1회 (T8 · T14 일부)

**Files:**
- Modify: `RoboTrader_template/collectors/sector_writer.py` (뒤에 이어붙인다)
- Create: `RoboTrader_template/collectors/sector_collector.py`
- Modify: `RoboTrader_template/tests/collectors/test_sector_collector.py`

**Interfaces:**
- Consumes: `sector_writer.plan_map_changes`·`write_map`·`load_open_rows`·`apply_parent_rule`·`parent_code`·`is_blank` · `dart_company_fetcher.DartCompanyFetcher`·`append_company_raw` · `dart_corp_code.refresh_from_dart` · `financial_collector._load_dart_key`
- Produces (writer):
  - `RECHECK_RAIL_RATIO = 0.20` · `RECHECK_RAIL_COUNT = 30`
  - `check_recheck_rail(n_responses: int, n_changed: int) -> None`
  - `apply_ksic_updates(conn, responses: list, trade_date, rail=False, source="eod", create_missing=True) -> dict`
  - `upsert_nodata(conn, stock_code: str) -> None` · `load_nodata(conn) -> dict`
- Produces (collector):
  - `SECTOR_DIR: str` · `DART_DAILY_CAP = 300` · `RECHECK_MAX = 200` · `NODATA_RETRY_DAYS = 30` · `CORP_CODE_REFRESH_DAYS = 7`
  - `class SectorStageError(RuntimeError)` — `.partial: dict`
  - `_fill_targets(open_rows: dict, nodata: dict, now) -> list`
  - `_recheck_targets(open_rows: dict, exclude: set, limit: int) -> list`
  - `fill_ksic(conn, trade_date, fetcher=None, cap=300, recheck_max=200, key=None, raw_path=None) -> dict`
  - `recopy_preferred(conn, trade_date, source="eod") -> dict`
  - `maybe_refresh_corp_code(conn, key, days=7) -> bool`

- [ ] **Step 1: 레일·대상 선정 테스트를 쓴다 (실패)**

`tests/collectors/test_sector_collector.py` 끝에 추가:

```python
from datetime import datetime, timedelta  # noqa: E402

from collectors import sector_collector as sc  # noqa: E402
from collectors import sector_writer as w  # noqa: E402

TD = date(2026, 9, 7)
NOW = datetime(2026, 9, 7, 16, 5)


def _row(**kw):
    r = {"valid_from": date(2026, 1, 2), "ksic_code": None, "ksic_source": None,
         "ksic3_name": None, "corp_code": None, "ksic_checked_at": None}
    r.update(kw)
    return r


def test_fill_targets_need_corp_code_and_missing_ksic():
    """(a) 대상 = corp_code 있고 ksic_code 없는 열린 줄."""
    opens = {"AAAAA1": _row(corp_code="00000001"),
             "BBBBB1": _row(corp_code="00000002", ksic_code="264"),
             "CCCCC1": _row()}
    assert sc._fill_targets(opens, {}, NOW) == ["AAAAA1"]


def test_parent_copied_rows_are_never_dart_targets():
    """🔴 부모 코드로 자식을 묻지 않는다 — ksic_source LIKE 'parent:%' 는 대상 밖."""
    opens = {"00104K": _row(corp_code="00126380", ksic_source="parent:001040")}
    assert sc._fill_targets(opens, {}, NOW) == []


def test_nodata_within_30_days_is_not_called():
    """「없다」고 답한 지 30일이 안 됐으면 호출 0."""
    opens = {"AAAAA1": _row(corp_code="00000001")}
    assert sc._fill_targets(opens, {"AAAAA1": NOW - timedelta(days=29)}, NOW) == []


def test_nodata_older_than_30_days_is_retried():
    """🔑 「없다」는 답도 틀릴 수 있다(재무 082660 교훈) — 30일 지나면 다시 두드린다."""
    opens = {"AAAAA1": _row(corp_code="00000001")}
    assert sc._fill_targets(opens, {"AAAAA1": NOW - timedelta(days=31)}, NOW) == ["AAAAA1"]


def test_recheck_order_is_checked_at_asc_nulls_first():
    """재확인 순환 커서 = ksic_checked_at ASC NULLS FIRST · 대상은 dart/snapshot 만 ·
    corp_code 가 없으면 물을 수단이 없으므로 대상이 아니다."""
    opens = {
        "AAAAA1": _row(ksic_code="264", ksic_source="dart", corp_code="0000000A",
                       ksic_checked_at=datetime(2026, 8, 20, 9, 0)),
        "BBBBB1": _row(ksic_code="264", ksic_source="snapshot_20260807",
                       corp_code="0000000B"),
        "CCCCC1": _row(ksic_code="264", ksic_source="dart", corp_code="0000000C",
                       ksic_checked_at=datetime(2026, 8, 1, 9, 0)),
        "DDDDD1": _row(ksic_code="264", ksic_source="parent:DDDDD0",
                       corp_code="0000000D"),
        "EEEEE1": _row(ksic_code="264", ksic_source="dart"),      # corp_code 없음
    }
    assert sc._recheck_targets(opens, set(), 10) == ["BBBBB1", "CCCCC1", "AAAAA1"]
    assert sc._recheck_targets(opens, {"BBBBB1"}, 10) == ["CCCCC1", "AAAAA1"]
    assert sc._recheck_targets(opens, set(), 2) == ["BBBBB1", "CCCCC1"]


def test_recheck_rail_trips_on_count_and_ratio():
    """🔴 표본 기준 레일 — 30건 초과 «또는» 20% 초과."""
    w.check_recheck_rail(200, 30)          # 경계: 30건·15% → 통과
    with pytest.raises(RuntimeError):
        w.check_recheck_rail(200, 31)      # 건수 초과
    with pytest.raises(RuntimeError):
        w.check_recheck_rail(100, 25)      # 비율 초과(25%)
    w.check_recheck_rail(0, 0)             # 응답 0 이면 무판정
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 수집 단계 오류 — `ModuleNotFoundError: No module named 'collectors.sector_collector'`

- [ ] **Step 3: writer 에 레일·KSIC 반영·nodata 를 넣는다**

`collectors/sector_writer.py` 끝에 이어붙인다:

```python
RECHECK_RAIL_RATIO = 0.20
RECHECK_RAIL_COUNT = 30


def check_recheck_rail(n_responses: int, n_changed: int) -> None:
    """재확인 «표본» 기준 레일.

    🔴 §3.1 의 5% 가드는 분모가 열린 줄 «전체»라 200건 표본에선 139건이 바뀌어야
       걸린다 — 표본 기준 레일이 따로 필요하다.
    """
    if n_responses <= 0:
        return
    ratio = float(n_changed) / n_responses
    if n_changed > RECHECK_RAIL_COUNT or ratio > RECHECK_RAIL_RATIO:
        raise RuntimeError(
            "KSIC 재확인 급변 — 그날 재확인분 전부 롤백 (%d/%d = %.1f%% · 문턱 %d건 또는 %.0f%%)"
            % (n_changed, n_responses, 100.0 * ratio, RECHECK_RAIL_COUNT,
               100.0 * RECHECK_RAIL_RATIO))


def apply_ksic_updates(conn, responses, trade_date, rail=False, source="eod",
                       create_missing=True) -> dict:
    """DART 응답을 §3.1 규칙으로 반영한다. 계획 → (레일) → 쓰기가 «한 트랜잭션»이다.

    responses: [{"stock_code", "ksic_code"(None 가능), "recheck": bool}]
    🔴 급변 가드의 «분모»는 열린 줄 «전체»여야 한다 — 그래서 open_rows 는 전부 읽고
       candidates 만 응답분으로 좁힌다.
    🔴 빈 응답은 «변경 아님» — ksic_checked_at 커서만 밀어 큐가 멈추지 않게 한다.
    🔴 create_missing=False 는 --regen-map 재생 전용이다 — 열린 줄이 없는 종목에
       KSIC 만 있는 «유령 행»(부수 열 전부 NULL)을 만들지 않는다.
    """
    from utils.korean_time import now_kst
    open_rows = load_open_rows(conn)
    now = now_kst().replace(tzinfo=None)
    cands = {}
    for r in responses:
        code = r["stock_code"]
        if is_blank(r.get("ksic_code")):
            cands[code] = {"ksic_checked_at": now}
        else:
            cands[code] = {"ksic_code": r["ksic_code"], "ksic_source": "dart",
                           "ksic_checked_at": now}
    plan = plan_map_changes(open_rows, cands, trade_date, create_missing=create_missing)
    if plan["counts"].get("skipped_missing"):
        logger.warning("[sector] 열린 줄이 없어 건너뛴 KSIC 응답 %d건",
                       plan["counts"]["skipped_missing"])
    if rail:
        sample = set(r["stock_code"] for r in responses if r.get("recheck"))
        check_recheck_rail(len(sample), len(set(plan["changed_codes"]) & sample))
    res = write_map(conn, plan, source)
    res["counts"] = plan["counts"]
    res["guard"] = plan["guard"]
    res["changed_codes"] = plan["changed_codes"]
    return res


def upsert_nodata(conn, stock_code: str) -> None:
    """DART 가 「업종 없음」이라 답한 종목. 이미 있으면 checked_at 을 지금으로 갱신 —
    🔑 30일 뒤 «다시» 두드리기 위해서다(재무 082660 교훈)."""
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO sector_ksic_nodata (stock_code, checked_at) "
                        "VALUES (%s, now()) ON CONFLICT (stock_code) DO UPDATE "
                        "SET checked_at=now()", (stock_code,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def load_nodata(conn) -> dict:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, checked_at FROM sector_ksic_nodata")
            return dict((r[0], r[1]) for r in cur.fetchall())
    except Exception:
        conn.rollback()
        raise
```

- [ ] **Step 4: `sector_collector.py` 뼈대 + ② 채우기/재확인/재복사 구현**

```python
# collectors/sector_collector.py
"""섹터 수집 오케스트레이터 — 명부·성적표·이름표 + reconcile + 수동 CLI.

usage:
  python -m collectors.sector_collector                                # EOD 판(오늘)
  python -m collectors.sector_collector --bootstrap --date 2026-09-13 [--dry-run]
  python -m collectors.sector_collector --backfill --from 2021-01-04 --to 2026-09-12
  python -m collectors.sector_collector --regen --from D1 --to D2 [--taxonomy ksic3]
  python -m collectors.sector_collector --regen-map --from D1
  python -m collectors.sector_collector --delete-stats --from D1 --to D2
  python -m collectors.sector_collector --reconcile-only 2026-09-07

🔴 DB 쓰기는 sector_writer.py 한 곳뿐이다. 이 파일은 오케스트레이션·판정·CLI 만 맡는다.
🔴 KIS 호출 0 · 매매 룰 0줄 · 라이브 3표는 «읽기»만 한다.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import SQL_STOCK_ONLY  # noqa: E402
from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import krx_desc_cache as kdc  # noqa: E402
from collectors import sector_writer as w  # noqa: E402
from collectors.daily_collector import load_universe  # noqa: E402
from collectors.dart_company_fetcher import DartCompanyFetcher, append_company_raw  # noqa: E402
from collectors.dart_corp_code import load_map, refresh_from_dart  # noqa: E402
from collectors.dart_financial_fetcher import DartBlocked, DartQuotaExceeded  # noqa: E402
from collectors.financial_collector import _load_dart_key  # noqa: E402
from utils.korean_time import now_kst  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

# 🔑 보관 디렉토리는 «한 곳»에서만 정의한다(krx_desc_cache.ARCHIVE_DIR).
#    두 벌로 두면 한쪽만 고쳐 gz 와 summary 가 다른 디렉토리로 갈라진다.
SECTOR_DIR = kdc.ARCHIVE_DIR
DART_DAILY_CAP = 300          # ≈ 102초 (0.34s × 300)
RECHECK_MAX = 200             # 한 바퀴 ≈ 13~14 거래일 (대상 풀 ≈ 2,658)
NODATA_RETRY_DAYS = 30
CORP_CODE_REFRESH_DAYS = 7
BOOTSTRAP_VALID_FROM = date(2021, 1, 4)
_MIN_DT = datetime(1970, 1, 1)      # ksic_checked_at NULLS FIRST 정렬용 하한

_U_MARKET_SQL = "SELECT stock_code FROM stock_market WHERE " + SQL_STOCK_ONLY + " ORDER BY 1"


class SectorStageError(RuntimeError):
    """단계 실패 — 부분 집계(partial)를 들고 올라간다.

    🔴 summary 는 «어떤 경우에도» 써야 §8-5·§8-9 게이트가 그날을 볼 수 있다.
       예외만 던지면 그 날의 recheck_calls·written 이 통째로 사라진다.
    """

    def __init__(self, msg, partial=None):
        RuntimeError.__init__(self, msg)
        self.partial = partial or {}


def _to_iso(s: str) -> str:
    return s if "-" in s else "%s-%s-%s" % (s[0:4], s[4:6], s[6:8])


def load_u_market(conn) -> list:
    """U_market = stock_market ∩ SQL_STOCK_ONLY (커버리지 게이트의 분모)."""
    with conn.cursor() as cur:
        cur.execute(_U_MARKET_SQL)
        return [r[0] for r in cur.fetchall()]


def _fill_targets(open_rows: dict, nodata: dict, now) -> list:
    """(a) 채우기 대상 — corp_code 有 ∧ ksic_code 無 ∧ 부모복사 아님 ∧ nodata 30일 경과."""
    out = []
    for code in sorted(open_rows):
        r = open_rows[code]
        if w.is_blank(r.get("corp_code")) or not w.is_blank(r.get("ksic_code")):
            continue
        if (r.get("ksic_source") or "").startswith("parent:"):
            continue
        ck = nodata.get(code)
        if ck is not None and (now - ck).days < NODATA_RETRY_DAYS:
            continue
        out.append(code)
    return out


def _recheck_targets(open_rows: dict, exclude, limit: int) -> list:
    """(b) 재확인 대상 — ksic_source ∈ {dart, snapshot_20260807} · checked_at ASC NULLS FIRST.

    🔴 코드가 «쓰기 한 번»으로 굳지 않게 하는 장치다. 한 바퀴 ≈ 13~14 거래일.
    """
    exclude = set(exclude or ())
    cands = []
    for code, r in open_rows.items():
        if code in exclude:
            continue
        if r.get("ksic_source") not in ("dart", "snapshot_20260807"):
            continue
        # 🔴 corp_code 가 없으면 물을 수단이 없다 — 대상에 넣으면 예산만 먹고
        #    ksic_checked_at 커서만 전진해 «정말 물어야 할» 종목이 뒤로 밀린다.
        if w.is_blank(r.get("corp_code")):
            continue
        ck = r.get("ksic_checked_at")
        cands.append(((ck is not None), ck, code))
    cands.sort(key=lambda t: (t[0], t[1] or _MIN_DT, t[2]))
    return [c[2] for c in cands[:max(0, limit)]]


def maybe_refresh_corp_code(conn, key, days=CORP_CODE_REFRESH_DAYS) -> bool:
    """주 1회 corpCode.xml 1호출. 🔑 이 함수가 refresh_from_dart 의 «첫 호출자»다
    (지금까지 grep 0건 — 매핑이 2,556행에 얼어 있었다). 재무 「미매핑 239」도 같이 풀린다."""
    if not key:
        return False
    with conn.cursor() as cur:
        cur.execute("SELECT max(updated_at) FROM dart_corp_code")
        row = cur.fetchone()
    last = row[0] if row else None
    if last is not None and (now_kst().replace(tzinfo=None) - last).days < days:
        return False
    refresh_from_dart(conn, key)
    return True


def fill_ksic(conn, trade_date, fetcher=None, cap=DART_DAILY_CAP,
              recheck_max=RECHECK_MAX, key=None, raw_path=None) -> dict:
    """② KSIC 채우기(a) + 재확인 순환(b). 하루 총 상한 = cap(=300).

    반환 summary: fill_calls·recheck_calls·recheck_changed·filled·nodata·status_counts
    """
    out = {"fill_calls": 0, "recheck_calls": 0, "recheck_changed": 0, "filled": 0,
           "nodata": 0, "status_counts": {}, "quota_hit": False, "blocked": False,
           "rail_tripped": False, "skipped": None, "fill_targets": 0, "recheck_targets": 0}
    key = key if key is not None else _load_dart_key()
    if not key:
        logger.warning("[sector] OPENDART_API_KEY 미설정 - KSIC 채우기 스킵(EOD 비차단)")
        out["skipped"] = "no_dart_key"
        return out
    f = fetcher if fetcher is not None else DartCompanyFetcher(key)
    raw_path = raw_path or os.path.join(
        SECTOR_DIR, "dart_company_%s.jsonl" % trade_date.isoformat())

    open_rows = w.load_open_rows(conn)
    nodata = w.load_nodata(conn)
    now = now_kst().replace(tzinfo=None)

    def _ask(code, recheck):
        status, js = f.fetch(open_rows[code]["corp_code"])
        append_company_raw(raw_path, {"stock_code": code, "corp_code": open_rows[code]["corp_code"],
                                      "status": status, "payload": js})
        induty = ""
        if status == "000":
            induty = (js.get("induty_code") or "").strip()
        if induty and len(induty) > 5:
            logger.warning("[sector] %s induty_code 길이 %d(>5) - 저장은 하되 확인 필요: %s",
                           code, len(induty), induty)
        return {"stock_code": code, "ksic_code": induty or None, "recheck": recheck}

    # (a) 채우기
    targets_a = _fill_targets(open_rows, nodata, now)
    out["fill_targets"] = len(targets_a)
    resp_a = []
    for code in targets_a:
        if f.calls >= cap:
            logger.warning("[sector] DART 일일 상한 %d 도달 - 채우기 %d종목 오늘 미수집(내일 재개)",
                           cap, len(targets_a) - len(resp_a) - out["nodata"])
            break
        try:
            r = _ask(code, False)
        except DartQuotaExceeded:
            logger.warning("[sector] DART 일일 한도 초과 - KSIC 채우기 중단")
            out["quota_hit"] = True
            break
        except DartBlocked:
            logger.error("[sector] opendart 차단 - KSIC 채우기 중단")
            out["blocked"] = True
            break
        if r["ksic_code"]:
            resp_a.append(r)
        else:
            w.upsert_nodata(conn, code)
            out["nodata"] += 1
    calls_after_a = f.calls
    out["fill_calls"] = calls_after_a
    if resp_a:
        res = w.apply_ksic_updates(conn, resp_a, trade_date)
        out["filled"] = res["counts"]["filled"]

    # (b) 재확인 순환 — 잔여 예산으로
    resp_b = []
    if not (out["quota_hit"] or out["blocked"]):
        budget = min(recheck_max, max(0, cap - f.calls))
        targets_b = _recheck_targets(open_rows, set(targets_a), budget)
        out["recheck_targets"] = len(targets_b)
        for code in targets_b:
            try:
                resp_b.append(_ask(code, True))
            except DartQuotaExceeded:
                out["quota_hit"] = True
                break
            except DartBlocked:
                out["blocked"] = True
                break
    out["recheck_calls"] = f.calls - calls_after_a
    out["status_counts"] = dict(f.status_counts)
    if resp_b:
        try:
            res = w.apply_ksic_updates(conn, resp_b, trade_date, rail=True)
        except RuntimeError as e:
            out["rail_tripped"] = True
            out["error"] = str(e)
            logger.error("[sector] 재확인 레일 발동 - 그날 재확인분 전부 롤백: %s", e)
            raise SectorStageError(str(e), partial=out)
        out["recheck_changed"] = len(res["changed_codes"])
        if out["recheck_changed"] > 10:
            logger.warning("[sector] 재확인 값→값 %d건 - 레일 아래지만 이례적이다",
                           out["recheck_changed"])
    return out


def recopy_preferred(conn, trade_date, source="eod") -> dict:
    """(c) 우선주 재복사 — (a)(b) 로 부모가 바뀐 자식을 받는다.
    🔑 부트스트랩 3b 와 «같은 함수»다(정의가 둘로 갈리지 않게)."""
    open_rows = w.load_open_rows(conn)
    cands = {}
    for code in sorted(open_rows):
        p = w.parent_code(code)
        if p is None or p not in open_rows:
            continue
        prow = open_rows[p]
        c = {}
        if not w.is_blank(prow.get("ksic_code")):
            c["ksic_code"] = prow.get("ksic_code")
            c["ksic_source"] = "parent:%s" % p
            c["corp_code"] = prow.get("corp_code")
        if not w.is_blank(prow.get("ksic3_name")):
            c["ksic3_name"] = prow.get("ksic3_name")
        if c:
            cands[code] = c
    if not cands:
        return {"closed": 0, "inserted": 0, "updated": 0,
                "counts": {"changed": 0, "filled": 0, "new": 0, "unchanged": 0,
                           "skipped_past": 0}}
    plan = w.plan_map_changes(open_rows, cands, trade_date)
    res = w.write_map(conn, plan, source)
    res["counts"] = plan["counts"]
    return res
```

- [ ] **Step 5: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 18 passed

- [ ] **Step 6: T8 — DART 분기 테스트를 추가한다**

`tests/collectors/test_sector_collector.py` 끝에 추가:

```python
class _DummyCM:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


class _FakeFetcher:
    """corp_code → 응답을 미리 정해 둔다. quota=<n> 이면 n번째 호출에서 020."""

    def __init__(self, answers=None, quota_at=None):
        self.answers = answers or {}
        self.quota_at = quota_at
        self.calls = 0
        self.status_counts = {}
        self.asked = []

    def fetch(self, corp_code):
        self.calls += 1
        self.asked.append(corp_code)
        if self.quota_at is not None and self.calls >= self.quota_at:
            raise DartQuotaExceeded("020")
        induty = self.answers.get(corp_code)
        st = "000" if induty else "013"
        self.status_counts[st] = self.status_counts.get(st, 0) + 1
        return st, ({"status": "000", "induty_code": induty} if induty
                    else {"status": "013"})


def _patch_fill(monkeypatch, open_rows, nodata=None, capture=None):
    monkeypatch.setattr(w, "load_open_rows", lambda conn: dict(open_rows))
    monkeypatch.setattr(w, "load_nodata", lambda conn: dict(nodata or {}))
    monkeypatch.setattr(w, "upsert_nodata",
                        lambda conn, code: (capture or {}).setdefault("nodata", []).append(code))
    monkeypatch.setattr(sc, "append_company_raw", lambda p, payload: 1)

    def _apply(conn, responses, trade_date, rail=False, source="eod"):
        (capture or {}).setdefault("applied", []).append((list(responses), rail))
        changed = [r["stock_code"] for r in responses if r.get("ksic_code") == "999"]
        if rail:
            w.check_recheck_rail(len([r for r in responses if r.get("recheck")]), len(changed))
        return {"closed": 0, "inserted": 0, "updated": len(responses),
                "counts": {"changed": len(changed), "filled": len(responses) - len(changed),
                           "new": 0, "unchanged": 0, "skipped_past": 0},
                "changed_codes": changed, "guard": {}}

    monkeypatch.setattr(w, "apply_ksic_updates", _apply)


def test_no_dart_key_skips_fill(monkeypatch):
    """키가 없으면 EOD 를 막지 않고 스킵한다(corp_events·재무 전례)."""
    out = sc.fill_ksic(object(), TD, key="")
    assert out["skipped"] == "no_dart_key" and out["fill_calls"] == 0


def test_quota_stops_fill_and_records(monkeypatch):
    """020 이면 채우기를 중단하고 «기록»한다 — 재확인도 안 돈다."""
    cap = {}
    opens = dict(("AAAA%02d" % i, _row(corp_code="0000000%d" % i)) for i in range(5))
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(quota_at=3)
    out = sc.fill_ksic(object(), TD, fetcher=f, key="k")
    assert out["quota_hit"] is True
    assert out["recheck_calls"] == 0, "한도 초과 뒤에 재확인을 또 돌리면 안 된다"


def test_nodata_response_is_recorded(monkeypatch):
    """induty_code 가 비면 nodata 기록 — 30일 뒤 재시도용 커서다."""
    cap = {}
    opens = {"AAAAA1": _row(corp_code="00000001")}
    _patch_fill(monkeypatch, opens, capture=cap)
    out = sc.fill_ksic(object(), TD, fetcher=_FakeFetcher({}), key="k")
    assert out["nodata"] == 1 and cap["nodata"] == ["AAAAA1"]


def test_recheck_budget_is_cap_minus_fill(monkeypatch):
    """재확인 예산 = 300 − 채우기 호출 수."""
    cap = {}
    opens = {}
    for i in range(3):
        opens["AAAA%02d" % i] = _row(corp_code="000000A%d" % i)
    for i in range(10):
        opens["BBBB%02d" % i] = _row(ksic_code="264", ksic_source="dart",
                                     corp_code="000000B%d" % i)
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(dict(("000000A%d" % i, "264") for i in range(3)))
    out = sc.fill_ksic(object(), TD, fetcher=f, cap=8, recheck_max=200, key="k")
    assert out["fill_calls"] == 3
    assert out["recheck_calls"] == 5, "예산은 cap(8) − 채우기(3) = 5 여야 한다"


def test_recheck_rail_rolls_back_and_raises(monkeypatch):
    """🔴 값→값 31건이면 그날 재확인분 전부 롤백 + RuntimeError(부분 집계는 보존)."""
    cap = {}
    opens = dict(("BBBB%03d" % i,
                  _row(ksic_code="264", ksic_source="dart", corp_code="00000%03d" % i))
                 for i in range(40))
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(dict(("00000%03d" % i, "999") for i in range(40)))
    with pytest.raises(sc.SectorStageError) as e:
        sc.fill_ksic(object(), TD, fetcher=f, key="k")
    assert e.value.partial["rail_tripped"] is True
    assert e.value.partial["recheck_calls"] == 40, "부분 집계가 보존돼야 §8-4 가 그날을 본다"
```

- [ ] **Step 7: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 23 passed

- [ ] **Step 8: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): KSIC 채우기 + 재확인 순환 + 표본 레일 + 우선주 재복사 (Task 5)

(a) corp_code 있고 KSIC 없는 열린 줄을 company.json 으로 채운다(부모복사 행 제외).
(b) 잔여 예산으로 dart/snapshot 행을 checked_at ASC NULLS FIRST 로 최대 200건 재확인 —
    코드가 «쓰기 한 번»으로 굳지 않게 하는 장치다(한 바퀴 13~14 거래일).
    표본 기준 레일(30건 또는 20% 초과)이 그날 재확인분을 통째로 롤백한다.
(c) 부모가 바뀐 우선주를 재복사한다(부트스트랩 3b 와 같은 함수).
「없다」는 답은 30일 뒤 다시 두드린다 · corp_code 는 주 1회 갱신한다(첫 호출자).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/sector_writer.py RoboTrader_template/collectors/sector_collector.py RoboTrader_template/tests/collectors/test_sector_collector.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 6: 성적표 계산 — 20 달력일 창 · 라벨 절단 · 백분위 · UPSERT (T5 · T6 · T7)

**Files:**
- Modify: `RoboTrader_template/collectors/sector_writer.py`
- Modify: `RoboTrader_template/collectors/sector_collector.py`
- Modify: `RoboTrader_template/tests/collectors/test_sector_collector.py` (T5·T6·T7-b)
- Modify: `RoboTrader_template/tests/collectors/test_sector_writer_db.py` (T7-a)

**Interfaces:**
- Consumes: `config.constants.SQL_STOCK_ONLY` · `sector_writer.map_as_of`
- Produces (collector):
  - `STATS_WINDOW_DAYS = 20` · `UP_MULT = 1.15` · `TAXONOMIES = (("ksic2",2),("ksic3",3),("ksic5",5))` · `_STATS_SQL: str`
  - `load_day_rows(conn, d) -> list` — `[(stock_code, high, close, prev_close)]`
  - `sector_label(ksic_code, n) -> str or None`
  - `rank_and_pct(values: list) -> list` — `[(rank:int, pct:float or None)]`
  - `compute_day_stats(rows: list, labels: dict) -> (stat_rows: list, undefined: dict)`
  - `compute_stats(conn, d) -> dict` — `{"date","rows","G","undefined"}`
- Produces (writer):
  - `upsert_stats(conn, rows: list) -> int`
  - `delete_stats(conn, d_from, d_to, taxonomy=None) -> int`

- [ ] **Step 1: T6 — 백분위 손계산 테스트를 쓴다 (실패)**

`tests/collectors/test_sector_collector.py` 끝에 추가:

```python
def test_rank_pct_hand_computed_with_ties():
    """T6 ① 동률: G=4 중앙값 [3,1,1,−2] → rank [0,2,2,3] · pct [100, 33.3, 33.3, 0].
    «좋거나 같은»(≥) 다른 업종 수 = 태쏘 rank_pct(side='left') 와 동치."""
    out = sc.rank_and_pct([3.0, 1.0, 1.0, -2.0])
    assert [r for r, _ in out] == [0, 2, 2, 3]
    assert [round(p, 1) for _, p in out] == [100.0, 33.3, 33.3, 0.0]


def test_rank_pct_hand_computed_without_ties():
    """T6 ② 동률 없음: [3,1,0,−2] → [0,1,2,3] · [100, 66.7, 33.3, 0]."""
    out = sc.rank_and_pct([3.0, 1.0, 0.0, -2.0])
    assert [r for r, _ in out] == [0, 1, 2, 3]
    assert [round(p, 1) for _, p in out] == [100.0, 66.7, 33.3, 0.0]


def test_rank_pct_single_sector_gives_null():
    """T6 ③ G=1 → 백분위 NULL(0 이 아니다 — 0 은 «최하위»라는 뜻이 된다)."""
    out = sc.rank_and_pct([0.5])
    assert out == [(0, None)]
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -k rank_pct -v
```
Expected: FAIL — `AttributeError: module 'collectors.sector_collector' has no attribute 'rank_and_pct'`

- [ ] **Step 3: `rank_and_pct` · `sector_label` 구현**

`collectors/sector_collector.py` 에 추가:

```python
STATS_WINDOW_DAYS = 20        # 달력일(태쏘 load_day 와 같은 창)
UP_MULT = 1.15                # 태쏘 run_sector.py:123 «승계»(새 문턱 아님)
TAXONOMIES = (("ksic2", 2), ("ksic3", 3), ("ksic5", 5))

_STATS_SQL = (
    "WITH w AS ("
    "  SELECT stock_code, date, high, close,"
    "         LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS prev_close"
    "  FROM daily_prices"
    "  WHERE date BETWEEN %s AND %s AND close > 0 AND " + SQL_STOCK_ONLY +
    ") SELECT stock_code, high, close, prev_close FROM w WHERE date = %s ORDER BY stock_code")


def load_day_rows(conn, d) -> list:
    """그날 대상 행 — 창 «안»에 close>0 과 술어를 걸고 LAG 로 prev_close 를 구한 뒤
    date=d 만 남긴다(태쏘 load_day 와 «같은 순서»).

    🔴 daily_prices.date 는 TEXT(YYYY-MM-DD)라 비교는 문자열이다.
    🔴 태쏘의 market_cap > 0 조건은 «넣지 않는다» — 시총은 사실상 2024-03-13 부터라
       그 전 구간이 통째로 비어 버린다(§3.2).
    """
    lo = (d - timedelta(days=STATS_WINDOW_DAYS)).isoformat()
    hi = d.isoformat()
    with conn.cursor() as cur:
        cur.execute(_STATS_SQL, (lo, hi, hi))
        return cur.fetchall()


def sector_label(ksic_code, n):
    """앞 n 자리. 길이 < n 이거나 접두가 숫자가 아니면 None(그 taxonomy 에서 미정).

    🔑 3자리 코드의 left(,5) 는 «그 코드 자신»이라 ksic5 에선 미정이 맞다.
       비숫자는 실측 0건이지만 CHECK 위반으로 ③이 죽지 않게 여기서 거른다.
    """
    s = (ksic_code or "").strip()
    if len(s) < n:
        return None
    head = s[:n]
    if not head.isdigit():
        return None
    return head


def rank_and_pct(values):
    """세 통계량 각각의 섹터간 순위·백분위.

    rank = «자기 제외, 통계량이 좋거나 같은(≥) 다른 업종 수»(동률 포함) —
    태쏘 rank_pct 의 side="left" 와 동치다. pct = 100·(G−1−rank)/(G−1) · G<2 면 None.
    """
    import bisect
    srt = sorted(values)
    g = len(values)
    out = []
    for v in values:
        ge = g - bisect.bisect_left(srt, v)     # v 이상인 개수(자기 포함)
        rank = ge - 1
        pct = (100.0 * (g - 1 - rank) / (g - 1)) if g >= 2 else None
        out.append((rank, pct))
    return out
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -k rank_pct -v
```
Expected: 3 passed

- [ ] **Step 5: T5 · T7-b 테스트를 쓴다 (실패)**

`tests/collectors/test_sector_collector.py` 끝에 추가:

```python
def test_sector_label_truncation():
    """T5 — 길이 3·4 코드는 ksic5 에서 미정(4자리 키는 CHECK 를 통과하지 못한다)."""
    assert sc.sector_label("264", 2) == "26"
    assert sc.sector_label("264", 3) == "264"
    assert sc.sector_label("264", 5) is None
    assert sc.sector_label("2611", 5) is None
    assert sc.sector_label("26110", 5) == "26110"
    assert sc.sector_label(None, 2) is None
    assert sc.sector_label("A1234", 2) is None, "비숫자 접두는 미정(CHECK 위반 방지)"


def test_no_prev_close_is_counted_not_dropped():
    """T5 — 20일 창 안에 직전 봉이 없으면 r 미정. 조용히 빼지 말고 «세어» 남긴다."""
    rows = [("AAAAA1", 110.0, 105.0, 100.0), ("BBBBB1", 50.0, 50.0, None)]
    labels = {"AAAAA1": "264", "BBBBB1": "264"}
    stat, und = sc.compute_day_stats(rows, labels)
    assert und["no_prev"] == 1
    k3 = [r for r in stat if r["taxonomy"] == "ksic3"]
    assert len(k3) == 1 and k3[0]["n_members"] == 1


def test_unlabeled_stock_is_counted_not_dropped():
    """T5 — 라벨 없는 종목은 fail-closed(빼고 «센다»)."""
    rows = [("AAAAA1", 110.0, 105.0, 100.0), ("BBBBB1", 50.0, 55.0, 50.0)]
    labels = {"AAAAA1": "264"}
    stat, und = sc.compute_day_stats(rows, labels)
    assert und["no_label"] == 1
    assert und["short_code"]["ksic5"] == 1, "264 는 ksic5 에서 미정이라 «센다»"


def test_stats_window_sql_filters_inside_the_window():
    """🔴 창 «안»에 close>0 과 술어를 건다 — 창 밖에서 걸면 0원 봉이 prev_close 후보로
    남아 수익률이 무한대가 된다(태쏘 load_day 와 같은 순서)."""
    head = sc._STATS_SQL.split(") SELECT")[0]
    assert "close > 0" in head
    assert "stock_code ~ " in head
    assert "LAG(close)" in head


def test_day_stats_hand_computed_sector():
    """중앙값·급등·상승비율·G·순위를 한 번에 손계산으로 고정한다."""
    rows = [
        # (code, high, close, prev_close) — r = close/prev − 1
        ("AAAAA1", 120.0, 103.0, 100.0),   # r=+3%   up: 120 >= 115 → True
        ("AAAAA2", 101.0, 101.0, 100.0),   # r=+1%   up: 101 >= 115 → False
        ("BBBBB1", 100.0,  98.0, 100.0),   # r=−2%   up False
    ]
    labels = {"AAAAA1": "26110", "AAAAA2": "26110", "BBBBB1": "27110"}
    stat, und = sc.compute_day_stats(rows, labels)
    by = dict(((r["taxonomy"], r["sector_key"]), r) for r in stat)
    a = by[("ksic5", "26110")]
    b = by[("ksic5", "27110")]
    assert a["n_members"] == 2 and b["n_members"] == 1
    assert a["g_sectors"] == 2 and b["g_sectors"] == 2
    assert abs(a["ret_median"] - 0.02) < 1e-9      # (0.03 + 0.01)/2
    assert a["up_count"] == 1 and b["up_count"] == 0
    assert abs(a["pos_ratio"] - 1.0) < 1e-9 and abs(b["pos_ratio"] - 0.0) < 1e-9
    assert a["rank_median"] == 0 and b["rank_median"] == 1
    assert abs(a["pct_median"] - 100.0) < 1e-9 and abs(b["pct_median"] - 0.0) < 1e-9
    # 같은 종목이 ksic2·ksic3 에도 들어간다
    assert by[("ksic2", "26")]["n_members"] == 2
    assert by[("ksic3", "261")]["n_members"] == 2
    assert und["no_label"] == 0 and und["no_prev"] == 0


def test_compute_day_stats_is_deterministic():
    """T7-b — 같은 입력이면 «완전히 같은» 행이 나온다(UPSERT 멱등의 전제)."""
    rows = [("AAAAA1", 120.0, 103.0, 100.0), ("BBBBB1", 100.0, 98.0, 100.0)]
    labels = {"AAAAA1": "26110", "BBBBB1": "27110"}
    one, u1 = sc.compute_day_stats(rows, labels)
    two, u2 = sc.compute_day_stats(rows, labels)
    assert one == two and u1 == u2
```

- [ ] **Step 6: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: FAIL — `AttributeError: ... has no attribute 'compute_day_stats'`

- [ ] **Step 7: `compute_day_stats` · `compute_stats` 구현**

`collectors/sector_collector.py` 에 추가:

```python
def compute_day_stats(rows, labels):
    """그날 행 + 라벨 → (성적표 행들, 미정 건수).

    미정 3종(no_prev · no_label · short_code)은 «항상» 세어 summary 로 올린다 —
    「0건」에 두 종류가 있다(안 돌았다 / 돌았는데 0).

    ⚠️ 스펙 §6.2 는 「pandas 벡터」라고 적었지만 여기서는 **순수 파이썬**(statistics)을
       쓴다. 하루 대상이 ~2,700행 · 그룹 ~550개라 벡터화 이득이 작고, 손계산 테스트(T6)와
       오라클(T9)이 읽어야 하는 코드라 «읽히는 쪽»을 택했다. 병목은 집계가 아니라 일자별
       20일 창 SQL 이다(1,392일 × ~55k행). **백필 예상 소요 = 수 분 ~ 15분**이며,
       15분을 넘기면 그때 창 SQL 을 한 번에 읽는 방식으로 바꾼다(집계는 그대로 둔다).
       ⚠️ 이 15분은 **측정치가 아니라 추정**이다(실측 근거 없음) — 백필 리포트의
       `elapsed_sec` 가 첫 실측이며, 크게 벗어나면 스펙 §6.2 와 함께 갱신한다.
    """
    import statistics
    undefined = {"no_prev": 0, "no_label": 0, "short_code": {}}
    recs = []
    for code, high, close, prev in rows:
        if prev is None or float(prev) <= 0 or close is None:
            undefined["no_prev"] += 1
            continue
        prev = float(prev)
        r = float(close) / prev - 1.0
        up = (high is not None) and (float(high) >= prev * UP_MULT)
        ks = labels.get(code)
        if w.is_blank(ks):
            undefined["no_label"] += 1
            continue
        recs.append((code, ks, r, up))

    out = []
    for tax, n in TAXONOMIES:
        buckets = {}
        short = 0
        for _code, ks, r, up in recs:
            key = sector_label(ks, n)
            if key is None:
                short += 1
                continue
            buckets.setdefault(key, []).append((r, up))
        undefined["short_code"][tax] = short
        if not buckets:
            continue
        keys = sorted(buckets)
        g = len(keys)
        med = [statistics.median([x[0] for x in buckets[k]]) for k in keys]
        mean = [statistics.mean([x[0] for x in buckets[k]]) for k in keys]
        upc = [sum(1 for x in buckets[k] if x[1]) for k in keys]
        pos = [float(sum(1 for x in buckets[k] if x[0] > 0)) / len(buckets[k]) for k in keys]
        rp_med = rank_and_pct(med)
        rp_up = rank_and_pct([float(u) for u in upc])
        rp_pos = rank_and_pct(pos)
        for i, k in enumerate(keys):
            out.append({
                "taxonomy": tax, "sector_key": k,
                "n_members": len(buckets[k]), "g_sectors": g,
                "ret_median": med[i], "ret_mean": mean[i],
                "up_count": upc[i], "pos_ratio": pos[i],
                "rank_median": rp_med[i][0], "pct_median": rp_med[i][1],
                "rank_up": rp_up[i][0], "pct_up": rp_up[i][1],
                "rank_pos": rp_pos[i][0], "pct_pos": rp_pos[i][1],
            })
    return out, undefined


def compute_stats(conn, d) -> dict:
    """③ 성적표. 그날 일봉 0행이면 스킵(휴장일 정상 · WARNING)."""
    rows = load_day_rows(conn, d)
    if not rows:
        logger.warning("[sector] %s 일봉 0행 - 성적표 스킵(휴장일이면 정상)", d)
        return {"date": d.isoformat(), "rows": 0, "skipped": "no_daily",
                "G": {}, "undefined": {}}
    labels = dict((r[0], r[1]) for r in w.map_as_of(conn, d))
    if not labels:
        logger.error("[sector] %s fn_sector_map_as_of 0행 - 성적표 스킵(부트스트랩 전인가)", d)
        return {"date": d.isoformat(), "rows": 0, "skipped": "empty_map",
                "G": {}, "undefined": {}}
    stat_rows, undefined = compute_day_stats(rows, labels)
    for r in stat_rows:
        r["date"] = d
    n = w.upsert_stats(conn, stat_rows)
    g = {}
    for tax, _ in TAXONOMIES:
        g[tax] = len([r for r in stat_rows if r["taxonomy"] == tax])
    logger.info("[sector] %s 성적표 %d행 G=%s 미정=%s", d, n, g, undefined)
    return {"date": d.isoformat(), "rows": n, "G": g, "undefined": undefined}
```

`collectors/sector_writer.py` 에 추가:

```python
_UPSERT_STATS = """
INSERT INTO sector_daily_stats
  (date, taxonomy, sector_key, n_members, g_sectors, ret_median, ret_mean, up_count,
   pos_ratio, rank_median, pct_median, rank_up, pct_up, rank_pos, pct_pos, computed_at)
VALUES %s
ON CONFLICT (date, taxonomy, sector_key) DO UPDATE SET
    n_members=EXCLUDED.n_members, g_sectors=EXCLUDED.g_sectors,
    ret_median=EXCLUDED.ret_median, ret_mean=EXCLUDED.ret_mean,
    up_count=EXCLUDED.up_count, pos_ratio=EXCLUDED.pos_ratio,
    rank_median=EXCLUDED.rank_median, pct_median=EXCLUDED.pct_median,
    rank_up=EXCLUDED.rank_up, pct_up=EXCLUDED.pct_up,
    rank_pos=EXCLUDED.rank_pos, pct_pos=EXCLUDED.pct_pos, computed_at=now()
"""

_STATS_TEMPLATE = ("(%(date)s, %(taxonomy)s, %(sector_key)s, %(n_members)s, %(g_sectors)s, "
                   "%(ret_median)s, %(ret_mean)s, %(up_count)s, %(pos_ratio)s, "
                   "%(rank_median)s, %(pct_median)s, %(rank_up)s, %(pct_up)s, "
                   "%(rank_pos)s, %(pct_pos)s, now())")


def upsert_stats(conn, rows) -> int:
    """성적표 배치 UPSERT — 같은 날 두 번 돌려도 행수·값이 그대로다(멱등)."""
    if not rows:
        return 0
    from psycopg2.extras import execute_values
    try:
        with conn.cursor() as cur:
            execute_values(cur, _UPSERT_STATS, rows, template=_STATS_TEMPLATE, page_size=1000)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows)


def delete_stats(conn, d_from, d_to, taxonomy=None) -> int:
    """§6.2 데이터 롤백 — 삭제 «건수»를 돌려준다(무징후 삭제 금지)."""
    sql = "DELETE FROM sector_daily_stats WHERE date BETWEEN %s AND %s"
    params = [d_from, d_to]
    if taxonomy:
        sql += " AND taxonomy=%s"
        params.append(taxonomy)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            n = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    logger.warning("[sector] 성적표 삭제 %d행 (%s ~ %s · taxonomy=%s)", n, d_from, d_to, taxonomy)
    return n
```

- [ ] **Step 8: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 32 passed

- [ ] **Step 9: T7-a — UPSERT 멱등 DB 테스트를 추가한다**

`tests/collectors/test_sector_writer_db.py` 끝에 추가:

```python
def test_upsert_stats_is_idempotent(conn):
    """T7-a — 같은 날 두 번 실행해도 행수·값이 그대로여야 한다."""
    rows = [{"date": TEST_STATS_DATE, "taxonomy": "ksic3", "sector_key": "261",
             "n_members": 3, "g_sectors": 2, "ret_median": 0.01, "ret_mean": 0.02,
             "up_count": 1, "pos_ratio": 0.67, "rank_median": 0, "pct_median": 100.0,
             "rank_up": 0, "pct_up": 100.0, "rank_pos": 0, "pct_pos": 100.0},
            {"date": TEST_STATS_DATE, "taxonomy": "ksic2", "sector_key": "26",
             "n_members": 3, "g_sectors": 1, "ret_median": 0.01, "ret_mean": 0.02,
             "up_count": 1, "pos_ratio": 0.67, "rank_median": 0, "pct_median": None,
             "rank_up": 0, "pct_up": None, "rank_pos": 0, "pct_pos": None}]
    assert w.upsert_stats(conn, [dict(r) for r in rows]) == 2
    w.upsert_stats(conn, [dict(r) for r in rows])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), sum(n_members) FROM sector_daily_stats WHERE date=%s",
                    (TEST_STATS_DATE,))
        assert cur.fetchone() == (2, 6), "재실행이 멱등하지 않다"
    assert w.delete_stats(conn, TEST_STATS_DATE, TEST_STATS_DATE) == 2
```

- [ ] **Step 10: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer_db.py -v
```
Expected: 6 passed

- [ ] **Step 11: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): 업종 일별 성적표 — 20 달력일 창·라벨 절단·자기제외 백분위·멱등 UPSERT (Task 6)

수익률은 창 «안»에 close>0 과 술어를 걸고 LAG 로 구한다(태쏘 load_day 와 같은 순서).
태쏘의 market_cap>0 조건은 넣지 않는다 — 시총은 사실상 2024-03-13 부터라 그 전 구간이
통째로 비기 때문이다. 라벨은 앞 N자리이며 길이 부족·비숫자는 그 taxonomy 에서 미정으로
«세어» 남긴다. 순위는 «좋거나 같은» 다른 업종 수(동률 포함) = 태쏘 side='left' 와 동치다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/sector_writer.py RoboTrader_template/collectors/sector_collector.py RoboTrader_template/tests/collectors/test_sector_collector.py RoboTrader_template/tests/collectors/test_sector_writer_db.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 7: `ksic_code_name` 이름표 재생성 (T12)

**Files:**
- Modify: `RoboTrader_template/collectors/sector_writer.py`
- Modify: `RoboTrader_template/tests/collectors/test_sector_writer_db.py`

**Interfaces:**
- Consumes: `stock_sector_map` 열린 줄
- Produces: `rebuild_ksic_names(conn) -> dict` — `{"codes": int, "low_share": [(code, name, share)]}`

- [ ] **Step 1: T12 테스트를 쓴다 (실패)**

`tests/collectors/test_sector_writer_db.py` 끝에 추가:

```python
def test_rebuild_ksic_names_picks_mode_and_warns_on_low_share(conn):
    """T12 — ksic_code NULL/길이<3 은 제외 · 최빈 이름 · 점유율 < 0.8 은 WARNING 목록 ·
    부모복사 우선주도 «종목»으로 센다.

    ⚠️ 라이브 표를 쓰므로 합성 코드는 실 데이터와 겹치면 안 된다 — 겹치면 skip 한다
       (부트스트랩 후 재실행 대비)."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stock_sector_map WHERE valid_to IS NULL "
                    "AND left(ksic_code,3) IN ('990','991')")
        if cur.fetchone()[0]:
            pytest.skip("실 데이터에 990/991 코드가 있어 합성 테스트를 격리할 수 없다")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ksic_code_name WHERE code IN ('990','991','99')")
        # 990: '합성A'(2) vs '합성B'(1) → 최빈 '합성A' · share 2/3 = 0.667 < 0.8 → 경고
        _insert_named(cur, "TEST9A", "9901", "합성A")
        _insert_named(cur, "TEST9B", "99011", "합성A")
        _insert_named(cur, "TEST9C", "9902", "합성B")
        # 길이 2 코드는 3자리 집계에서 빠진다
        _insert_named(cur, "TEST90", "99", "짧은코드")
    conn.commit()
    out = w.rebuild_ksic_names(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT name, n_stocks, share FROM ksic_code_name WHERE code='990'")
        name, n, share = cur.fetchone()
    assert name == "합성A" and n == 2
    assert abs(share - 2.0 / 3.0) < 1e-9
    assert any(c == "990" for c, _n, _s in out["low_share"]), "점유율 0.667 이 경고 목록에 없다"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ksic_code_name WHERE code='99'")
        assert cur.fetchone()[0] == 0, "길이 2 코드가 3자리 이름표에 들어왔다"
```

`_insert_named` 헬퍼도 같은 파일에 추가:

```python
def _insert_named(cur, code, ksic, name):
    cur.execute(
        "INSERT INTO stock_sector_map (stock_code, valid_from, valid_to, ksic_code, "
        "ksic_source, ksic3_name, source) VALUES (%s, %s, NULL, %s, 'dart', %s, 'eod')",
        (code, date(2021, 1, 4), ksic, name))
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer_db.py -k rebuild -v
```
Expected: FAIL — `AttributeError: module 'collectors.sector_writer' has no attribute 'rebuild_ksic_names'`

- [ ] **Step 3: `rebuild_ksic_names` 구현**

`collectors/sector_writer.py` 에 추가:

```python
_NAMES_SRC = """
WITH src AS (
    SELECT left(ksic_code, 3) AS code, ksic3_name AS name, count(*)::int AS n
    FROM stock_sector_map
    WHERE valid_to IS NULL
      AND ksic_code IS NOT NULL AND length(ksic_code) >= 3
      AND ksic3_name IS NOT NULL AND left(ksic_code, 3) ~ '^[0-9]{3}$'
    GROUP BY 1, 2
), tot AS (
    SELECT code, sum(n) AS total FROM src GROUP BY 1
)
SELECT DISTINCT ON (s.code) s.code, s.name, s.n, s.n::float8 / t.total AS share
FROM src s JOIN tot t ON t.code = s.code
ORDER BY s.code, s.n DESC, s.name
"""

_UPSERT_NAME = """
INSERT INTO ksic_code_name (level, code, name, n_stocks, share, built_at)
VALUES (3, %s, %s, %s, %s, now())
ON CONFLICT (level, code) DO UPDATE SET
    name=EXCLUDED.name, n_stocks=EXCLUDED.n_stocks, share=EXCLUDED.share, built_at=now()
"""


def rebuild_ksic_names(conn) -> dict:
    """④ 이름표 재생성 — 열린 줄의 (앞3자리, ksic3_name) 최빈 이름.

    ⚠️ PIT 가 아니다(매일 재생성 · 표시 전용). 과거 성적표에 조인해도 «오늘 이름»이 붙는다.
    🔑 부모복사 우선주도 «종목»으로 센다 — 화면 라벨의 대표성이 목적이기 때문이다.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(_NAMES_SRC)
            rows = cur.fetchall()
            keep = set(r[0] for r in rows)
            for code, name, n, share in rows:
                cur.execute(_UPSERT_NAME, (code, name, int(n), float(share)))
            if keep:
                cur.execute("DELETE FROM ksic_code_name WHERE level=3 AND NOT (code = ANY(%s))",
                            (sorted(keep),))
            else:
                cur.execute("DELETE FROM ksic_code_name WHERE level=3")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    low = [(r[0], r[1], float(r[3])) for r in rows if float(r[3]) < 0.8]
    if low:
        logger.warning("[sector] 이름표 점유율 < 0.8 인 코드 %d개: %s", len(low), low[:10])
    logger.info("[sector] 이름표 재생성 %d코드 (점유율<0.8 %d개)", len(rows), len(low))
    return {"codes": len(rows), "low_share": low}
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer_db.py -v
```
Expected: 7 passed

- [ ] **Step 5: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): KSIC 3자리 이름표 재생성 — 데이터에서 최빈 이름 (Task 7)

캐시 Industry(KSIC 소분류명) 와 DART induty_code 앞 3자리를 2,527개 회사로 대조한
결과 158 코드 ↔ 158 이름이고 코드별 지배 이름 점유율 ≥ 0.9 가 158/158 이다.
그래도 화면 라벨은 「코드 + 이름」으로 쓴다. 점유율 0.8 미만은 WARNING 으로 남긴다.
⚠️ PIT 가 아니다 — 매일 재생성되는 표시 전용 표다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/sector_writer.py RoboTrader_template/tests/collectors/test_sector_writer_db.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 8: ① 명부 갱신 + summary 영속화 + `collect_sector` 오케스트레이션 (T14 일부 · T8 나머지)

**Files:**
- Modify: `RoboTrader_template/collectors/sector_collector.py`
- Modify: `RoboTrader_template/tests/collectors/test_sector_collector.py`

**Interfaces:**
- Consumes: `krx_desc_cache.load_desc`·`fold_market_counts` · `sector_writer.load_open_rows`·`open_market_counts`·`load_stock_industry`·`apply_parent_rule`·`plan_map_changes`·`write_map`·`rebuild_ksic_names` · `daily_collector.load_universe` · `dart_corp_code.load_map`
- Produces:
  - `_summary_path(d) -> str` · `_write_summary(d, summary: dict) -> None` · `_read_summary(d) -> dict or None`
  - `_stale_trading_days(conn, source_asof, trade_date) -> int`
  - `update_map(conn, trade_date, source="eod", fetcher=None, use_snapshot=False, valid_from=None) -> dict`
  - `collect_sector(trade_date: str = None) -> dict`

- [ ] **Step 1: T14 실패 경로 테스트를 쓴다 (실패)**

`tests/collectors/test_sector_collector.py` 끝에 추가:

```python
def _patch_collect(monkeypatch, calls, map_exc=None, fill_exc=None):
    """collect_sector 가 DB·네트워크를 전혀 안 타게 기본값을 깐다."""
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(sc, "maybe_refresh_corp_code", lambda conn, key, **kw: False)
    monkeypatch.setattr(sc, "_write_summary",
                        lambda d, s: calls.append(("summary", dict(s))))

    def _map(conn, d, **kw):
        calls.append(("map", d))
        if map_exc:
            raise map_exc
        return {"written": True, "source_asof": "2026-09-07", "matched": 2772}

    def _fill(conn, d, **kw):
        calls.append(("fill", d))
        if fill_exc:
            raise fill_exc
        return {"fill_calls": 1, "recheck_calls": 2, "recheck_changed": 0}

    monkeypatch.setattr(sc, "update_map", _map)
    monkeypatch.setattr(sc, "fill_ksic", _fill)
    monkeypatch.setattr(sc, "recopy_preferred",
                        lambda conn, d, **kw: calls.append(("recopy", d)) or {"counts": {}})
    monkeypatch.setattr(sc, "compute_stats",
                        lambda conn, d: calls.append(("stats", d)) or {"rows": 547, "G": {}})
    monkeypatch.setattr(sc.w, "rebuild_ksic_names",
                        lambda conn: calls.append(("names", None)) or {"codes": 158,
                                                                       "low_share": []})


def test_map_failure_does_not_stop_other_stages(monkeypatch):
    """🔴 ①이 터져도 ②③④ 는 돈다 — _safe 까지 올라가면 summary 가 안 써져
    §8-5 가 그날을 못 본다."""
    calls = []
    _patch_collect(monkeypatch, calls, map_exc=RuntimeError("캐시 404"))
    out = sc.collect_sector("2026-09-07")
    names = [c[0] for c in calls]
    assert names[:5] == ["map", "fill", "recopy", "stats", "names"]
    assert out["map"]["written"] is False and "캐시 404" in out["map"]["error"]
    assert out["stats"]["rows"] == 547


def test_summary_is_always_written(monkeypatch):
    """summary 는 «어떤 경우에도» 쓴다 — 게이트들이 파일을 읽기 때문이다."""
    calls = []
    _patch_collect(monkeypatch, calls, map_exc=RuntimeError("boom"),
                   fill_exc=RuntimeError("dart down"))
    sc.collect_sector("2026-09-07")
    written = [c for c in calls if c[0] == "summary"]
    assert len(written) == 1
    s = written[0][1]
    assert s["trade_date"] == "2026-09-07"
    assert s["map"]["written"] is False
    assert "dart down" in s["ksic_fill"]["error"]


def test_dart_quota_does_not_stop_stats(monkeypatch):
    """T8 — 020 으로 ②가 끊겨도 성적표는 진행한다."""
    calls = []
    _patch_collect(monkeypatch, calls,
                   fill_exc=sc.SectorStageError("quota", partial={"quota_hit": True,
                                                                  "recheck_calls": 0}))
    out = sc.collect_sector("2026-09-07")
    assert out["ksic_fill"]["quota_hit"] is True
    assert out["ksic_fill"]["recheck_calls"] == 0, "부분 집계가 보존돼야 한다"
    assert ("stats", date(2026, 9, 7)) in calls


def test_summary_roundtrip(tmp_path, monkeypatch):
    """summary 파일 저장·읽기 — 없으면 None(그 게이트가 WARN 으로 처리한다)."""
    monkeypatch.setattr(sc, "SECTOR_DIR", str(tmp_path))
    d = date(2026, 9, 7)
    assert sc._read_summary(d) is None
    sc._write_summary(d, {"trade_date": "2026-09-07", "map": {"written": True}})
    assert os.path.basename(sc._summary_path(d)) == "sector_summary_2026-09-07.json"
    assert sc._read_summary(d)["map"]["written"] is True
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: FAIL — `AttributeError: module 'collectors.sector_collector' has no attribute 'update_map'`

- [ ] **Step 3: summary 영속화 + `update_map` + `collect_sector` 구현**

`collectors/sector_collector.py` 에 추가:

```python
def _summary_path(d) -> str:
    return os.path.join(SECTOR_DIR, "sector_summary_%s.json" % d.isoformat())


def _write_summary(d, summary: dict) -> None:
    """🔴 §8 의 «전일 대비»·«N일 연속» 게이트는 이 파일들을 읽는다.
    저장이 없으면 그 게이트들은 「한 번도 발동 안 함」이 된다."""
    path = _summary_path(d)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, default=str)
    except OSError as e:
        logger.warning("[sector] summary 파일 기록 실패(비차단): %s", e)


def _read_summary(d):
    try:
        with open(_summary_path(d), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _stale_trading_days(conn, source_asof, trade_date) -> int:
    """source_asof «다음»부터 trade_date 까지의 거래일 수(daily_prices 고유 날짜)."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(DISTINCT date) FROM daily_prices "
                    "WHERE date > %s AND date <= %s",
                    (source_asof.isoformat(), trade_date.isoformat()))
        return int(cur.fetchone()[0])


def update_map(conn, trade_date, source="eod", fetcher=None,
               use_snapshot=False, valid_from=None) -> dict:
    """① 명부 갱신 — 캐시 CSV + 열린 줄 + corp_code + 우선주 규칙 → SCD2 쓰기.

    🔴 보통주 후보의 ksic_code 는 «열린 줄 값 승계»다(캐시엔 코드 열이 없다).
       부트스트랩(use_snapshot=True)에서만 stock_industry 스냅샷으로 시드한다.
    🔴 우선주 후보엔 열린 줄 값을 «승계하지 않는다» — 부모 규칙이 우선이라야
       부모가 바뀔 때 자식도 같이 바뀐다(§3.1).
    🔴 순회는 «캐시 CSV 행»이 아니라 «U_all» 이다. 캐시엔 없는데 U_all 엔 있는 종목이
       실재한다(실측: 상장목록 KOSPI 945 vs 캐시 943 · KOSDAQ 1,827 vs 1,822).
       CSV 행만 돌면 그 종목은 명부 행이 «영영» 안 생기고 stock_industry 스냅샷 KSIC 도
       버려져 부트스트랩 커버리지가 100% 에 못 닿는다 — 무징후 절단이다.
       캐시에 없으면 «아는 키만» 후보에 넣고 CSV 부수 열 키는 «생략»한다
       (plan_map_changes 의 `if f in cand` 가 기존 값을 보존한다 — NULL 로 덮지 않는다).
    """
    open_rows = w.load_open_rows(conn)
    universe = set(load_universe(conn))
    existing = kdc.fold_market_counts(w.open_market_counts(conn))
    desc = kdc.load_desc(trade_date, existing, fetcher=fetcher)
    cmap = load_map(conn)
    snap = w.load_stock_industry(conn) if use_snapshot else {}

    by_code = dict((r["stock_code"], r) for r in desc["rows"])
    cands = {}
    matched = 0                      # CSV ∩ U_all — null_rate 의 «분모»
    no_csv = []                      # U_all 에 있는데 CSV 에 없는 종목(건수로 남긴다)
    for code in sorted(universe):
        row = by_code.get(code)
        if row is None:
            no_csv.append(code)
            cand = {"source_asof": desc["source_asof"]}
        else:
            matched += 1
            cand = {"ksic3_name": row["ksic3_name"], "market": row["market"],
                    "kosdaq_dept": row["kosdaq_dept"], "products": row["products"],
                    "listing_date": row["listing_date"],
                    "settle_month": row["settle_month"],
                    "source_asof": desc["source_asof"]}
        if w.parent_code(code) is None:
            cur = open_rows.get(code) or {}
            ks = cur.get("ksic_code")
            src = cur.get("ksic_source")
            if w.is_blank(ks) and code in snap:
                ks, src = snap[code], "snapshot_20260807"
            cand["ksic_code"] = ks
            cand["ksic_source"] = src
            cand["corp_code"] = cmap.get(code) or cur.get("corp_code")
        if valid_from is not None:
            cand["valid_from"] = valid_from
        cands[code] = cand
    if no_csv:
        logger.warning("[sector] 캐시 CSV 에 없는 U_all 종목 %d개 - 아는 값만 넣고 "
                       "부수 열은 «보존»한다(예: %s)", len(no_csv), no_csv[:5])

    cands = w.apply_parent_rule(cands, universe)
    # §4 summary — null_rate 의 분모는 «U_all 과 매칭된 캐시 행» 이다(no_csv 는 뺀다).
    matched_codes = [c for c in cands if c in by_code]
    null_code = sum(1 for c in matched_codes if w.is_blank(cands[c].get("ksic_code")))
    null_name = sum(1 for c in matched_codes if w.is_blank(cands[c].get("ksic3_name")))

    plan = w.plan_map_changes(open_rows, cands, trade_date)   # 급변 가드가 여기서 터진다
    if plan["counts"]["skipped_past"]:
        logger.warning("[sector] valid_from > %s 인 열린 줄 %d종목 건너뜀(과거 날짜 재실행)",
                       trade_date, plan["counts"]["skipped_past"])
    res = w.write_map(conn, plan, source)

    stale_days = _stale_trading_days(conn, desc["source_asof"], trade_date)
    stale = stale_days > 5
    if stale:
        logger.warning("[sector] 캐시 게시일 %s 가 %s 보다 %d 거래일 낡았다",
                       desc["source_asof"], trade_date, stale_days)
    out = {"source_asof": desc["source_asof"].isoformat(),
           "open_rows": len(open_rows), "matched": matched,
           "changed": plan["counts"]["changed"], "filled": plan["counts"]["filled"],
           "new": plan["counts"]["new"], "skipped_past": plan["counts"]["skipped_past"],
           "null_rate": {
               "ksic_code": (float(null_code) / matched) if matched else None,
               "ksic3_name": (float(null_name) / matched) if matched else None},
           "guard": plan["guard"], "written": True,
           "counts_by_market": desc["counts"], "dropped": desc["dropped"],
           "archive": os.path.basename(desc["archive"]) if desc.get("archive") else None,
           "no_csv": len(no_csv), "universe": len(universe),
           "stale": stale, "stale_days": stale_days, "db": res}
    logger.info("[sector] 명부 갱신 %s", out)
    return out


def collect_sector(trade_date: str = None) -> dict:
    """EOD ①②③④. 🔴 한 단계가 터져도 나머지는 돌고 summary 는 «항상» 쓴다.

    `_safe`(eod_collection) 는 최후 방어선일 뿐이다 — 거기까지 올라가면 summary 가
    안 써져 §8-5·§8-9 가 그날을 못 본다.
    """
    d = date.fromisoformat(_to_iso(trade_date)) if trade_date else now_kst().date()
    summary = {"trade_date": d.isoformat(), "map": {"written": False},
               "corp_code_refreshed": False, "ksic_fill": {}, "stats": {}, "names": {}}
    key = _load_dart_key()
    try:
        with KisDbConnection.get_connection() as conn:
            w.ensure_tables(conn)
            try:
                summary["corp_code_refreshed"] = maybe_refresh_corp_code(conn, key)
            except Exception as e:  # noqa: BLE001 — 매핑 갱신 실패가 나머지를 막지 않는다
                logger.warning("[sector] corp_code 주간 갱신 실패(비차단): %s", e)
            try:
                summary["map"] = update_map(conn, d, source="eod")
            except Exception as e:  # noqa: BLE001
                logger.error("[sector] ① 명부 갱신 실패 - 어제 명부 유지: %s", e)
                partial = dict(getattr(e, "partial", None) or {})
                partial["written"] = False
                partial["error"] = str(e)
                summary["map"] = partial
            try:
                summary["ksic_fill"] = fill_ksic(conn, d, key=key)
                summary["ksic_fill"]["recopy"] = recopy_preferred(conn, d)["counts"]
            except Exception as e:  # noqa: BLE001
                logger.error("[sector] ② KSIC 채우기 실패: %s", e)
                partial = dict(getattr(e, "partial", None) or {})
                partial["error"] = str(e)
                summary["ksic_fill"] = partial
            try:
                summary["stats"] = compute_stats(conn, d)
            except Exception as e:  # noqa: BLE001
                logger.error("[sector] ③ 성적표 실패: %s", e)
                summary["stats"] = {"date": d.isoformat(), "rows": 0, "error": str(e)}
            try:
                summary["names"] = w.rebuild_ksic_names(conn)
            except Exception as e:  # noqa: BLE001
                logger.error("[sector] ④ 이름표 실패: %s", e)
                summary["names"] = {"error": str(e)}
    except Exception as e:  # noqa: BLE001 — DB 연결 자체가 실패해도 summary 는 남긴다
        logger.error("[sector] 수집 실패(연결 계층): %s", e)
        summary["error"] = str(e)
    _write_summary(d, summary)
    logger.info("[sector] %s", summary)
    return summary
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 36 passed

- [ ] **Step 5: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): 명부 갱신 ① + summary 영속화 + collect_sector 오케스트레이션 (Task 8)

①이 실패해도 ②③④ 는 계속 돌고 summary 는 어떤 경우에도 쓴다 — _safe 까지 올라가면
그날 summary 가 없어 §8-5(얼어붙은 명부)·§8-9(요약 부재) 게이트가 그날을 못 본다.
보통주 후보의 KSIC 는 열린 줄 승계(부트스트랩만 stock_industry 시드)이고 우선주는
열린 줄을 승계하지 않는다 — 부모 규칙이 우선이라야 부모가 바뀔 때 자식도 바뀐다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/sector_collector.py RoboTrader_template/tests/collectors/test_sector_collector.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 9: `reconcile_sector` — 게이트 1~9 · PASS/WARN/FAIL · recon 행 쓰기 (T13)

**Files:**
- Modify: `RoboTrader_template/collectors/sector_writer.py` (recon 행 쓰기 — 자체 SQL)
- Modify: `RoboTrader_template/collectors/sector_collector.py`
- Create: `RoboTrader_template/tests/collectors/test_sector_reconcile.py`
- Modify: `RoboTrader_template/tests/collectors/test_sector_writer_db.py` (M4 — §8-1 분자·분모가 U_market 한정임을 실 DB 로 고정)

**Interfaces:**
- Consumes: `_read_summary`(Task 8) · `sector_writer.upsert_reconciliation` · `config.constants.SQL_STOCK_ONLY`
- Produces:
  - writer: `upsert_reconciliation(conn, trade_date: str, real_rows: int, new_rows: int, overlap: int, coverage, value_match_rate, verdict: str) -> None`
    (🔴 `financial_writer.upsert_reconciliation` 엔 `real_rows` 인자가 없다 — 그래서 자체 SQL 이다)
  - collector: `COVERAGE_MIN = 0.98` · `G_FLOORS = {"ksic2": 40, "ksic3": 100, "ksic5": 200}` · `NO_PREV_FLOOR = 20` · `_FACTS_COVERAGE_SQL`
  - `_prev_trading_days(conn, d, n) -> list` (ISO 문자열 · 최신순)
  - `_db_facts(conn, d, prev_days) -> dict` — `prev_days` 는 호출측이 «한 번만» 구한 20일치
  - `evaluate_gates(trade_date, today, prev_summaries, facts) -> dict` — `{"verdict","fails","warns","notes","real_rows","new_rows","overlap","coverage","value_match_rate"}`
  - `reconcile_sector(trade_date: str = None) -> dict`

**판정 어휘 배정**(스펙 §8 이 명시한 것 + 명시가 없던 1·2 는 여기서 못박는다):

| 게이트 | 판정 | 근거 |
|---|---|---|
| 1 커버리지 < 98% | **FAIL** | 부트스트랩 게이트와 같은 문턱 — 운영 중 미달은 회귀다 |
| 2 성적표 0행(거래일) · G 하한 미달 | **FAIL** | 조인 붕괴 |
| 2 G 전일 대비 ±20% 밖 | WARN | 급증 = 잘못된 코드 주입으로 파편화 |
| 3 `no_label` +50 · `no_prev` 문턱 초과 | WARN | 일봉 결손 신호 |
| 4 정체(`new_rows` 3연속 동일 · `recheck_calls` 20일 0 · `recheck_changed` > 10) | WARN | KSIC 는 내일 또 물을 수 있다(재무와 다르다) |
| 5 `written=false` 2연속 · `last_seen_at` 3거래일 정체 | **FAIL** | 얼어붙은 명부 |
| 6 NULL 비율 급증 · `stale` | WARN | 소스 이상 |
| 7 게시 지연 3연속 | WARN | EOD 자리 재검토 신호 |
| 8 명부 중복 | **FAIL** | `n_members` 이중 계산 |
| 9 summary 부재 1일 / 3연속 | WARN / **FAIL** | 재무 `no_summary` 규칙 승계 |

- [ ] **Step 1: T13 테스트를 쓴다 (실패)**

```python
# tests/collectors/test_sector_reconcile.py
"""섹터 reconcile 게이트 테스트 (T13). DB 를 쓰지 않는다 — 게이트는 순수 함수다."""
import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from collectors import sector_collector as sc  # noqa: E402

D = date(2026, 9, 7)


def _facts(**kw):
    f = {"u_market": 2772, "ksic_code_nonnull": 2772, "ksic3_name_nonnull": 2765,
         "new_rows": 0, "stats_rows": 547, "g": {"ksic2": 61, "ksic3": 159, "ksic5": 324},
         "duplicates": 0, "max_last_seen": datetime(2026, 9, 7, 16, 5),
         "is_trading_day": True, "last_seen_deadline": date(2026, 9, 2),
         "prev_days": ["2026-09-04", "2026-09-03", "2026-09-02"],
         "prev_new_rows": [], "prev_recon_dates": []}
    f.update(kw)
    return f


def _summary(**kw):
    s = {"trade_date": "2026-09-07",
         "map": {"written": True, "source_asof": "2026-09-07", "stale": False,
                 "null_rate": {"ksic_code": 0.0, "ksic3_name": 0.003}},
         "ksic_fill": {"fill_calls": 0, "recheck_calls": 200, "recheck_changed": 0},
         "stats": {"rows": 547, "G": {"ksic2": 61, "ksic3": 159, "ksic5": 324},
                   "undefined": {"no_label": 5, "no_prev": 1,
                                 "short_code": {"ksic2": 0, "ksic3": 0, "ksic5": 1370}}},
         "names": {"codes": 158, "low_share": []}}
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k] = dict(s[k], **v)
        else:
            s[k] = v
    return s


def test_healthy_day_is_pass():
    out = sc.evaluate_gates(D, _summary(), [_summary(), _summary()], _facts())
    assert out["verdict"] == "PASS", (out["fails"], out["warns"])
    assert out["real_rows"] == 547 and out["overlap"] == 5
    assert abs(out["coverage"] - 1.0) < 1e-9
    assert out["value_match_rate"] > 0.99, "value_match_rate 는 «높을수록 좋다»(비-NULL 비율)"


def test_gate1_coverage_below_98_is_fail():
    out = sc.evaluate_gates(D, _summary(), [], _facts(ksic_code_nonnull=2700))
    assert out["verdict"] == "FAIL" and any("gate1" in f for f in out["fails"])


def test_gate2_g_floor_is_fail_and_swing_is_warn():
    out = sc.evaluate_gates(D, _summary(), [], _facts(g={"ksic2": 61, "ksic3": 40, "ksic5": 324}))
    assert out["verdict"] == "FAIL" and any("gate2" in f for f in out["fails"])
    prev = _summary(stats={"G": {"ksic2": 61, "ksic3": 159, "ksic5": 100}})
    out2 = sc.evaluate_gates(D, _summary(), [prev], _facts())
    assert out2["verdict"] == "WARN" and any("ksic5" in x for x in out2["warns"])


def test_gate3_no_prev_threshold_is_not_a_doubling_rule():
    """🔴 기저가 0~3 이라 「전일의 2배」 규칙은 1건에 걸린다.
    문턱 = max(20, 3 × 직전 20거래일 중앙값)."""
    prevs = [_summary(stats={"undefined": {"no_label": 5, "no_prev": 0,
                                           "short_code": {}}}) for _ in range(20)]
    ok = _summary(stats={"undefined": {"no_label": 5, "no_prev": 1, "short_code": {}}})
    assert sc.evaluate_gates(D, ok, prevs, _facts())["verdict"] == "PASS"
    bad = _summary(stats={"undefined": {"no_label": 5, "no_prev": 189, "short_code": {}}})
    out = sc.evaluate_gates(D, bad, prevs, _facts())
    assert out["verdict"] == "WARN" and any("no_prev" in x for x in out["warns"])


def test_gate3_no_label_jump_is_warn():
    prev = _summary(stats={"undefined": {"no_label": 5, "no_prev": 0, "short_code": {}}})
    today = _summary(stats={"undefined": {"no_label": 60, "no_prev": 0, "short_code": {}}})
    out = sc.evaluate_gates(D, today, [prev], _facts())
    assert out["verdict"] == "WARN" and any("no_label" in x for x in out["warns"])


def test_gate4_zero_remaining_is_not_stalled():
    """0=0=0 은 정상 — 채울 게 없는 것이다."""
    out = sc.evaluate_gates(D, _summary(), [_summary(), _summary()],
                            _facts(new_rows=0, prev_new_rows=[0, 0, 0]))
    assert out["verdict"] == "PASS"


def test_gate4_stalled_positive_remaining_is_warn():
    out = sc.evaluate_gates(D, _summary(), [_summary(), _summary()],
                            _facts(new_rows=7, prev_new_rows=[7, 7, 7]))
    assert out["verdict"] == "WARN" and any("정체" in x for x in out["warns"])


def test_gate4_recheck_stopped_20_days_is_warn():
    """재확인 순환이 20거래일 연속 0 이면 정지 의심."""
    prevs = [_summary(ksic_fill={"recheck_calls": 0}) for _ in range(19)]
    today = _summary(ksic_fill={"recheck_calls": 0})
    out = sc.evaluate_gates(D, today, prevs, _facts())
    assert out["verdict"] == "WARN" and any("recheck" in x for x in out["warns"])


def test_gate5_written_false_two_days_is_fail():
    """🔴 얼어붙은 명부 — 2거래일 연속 미갱신은 FAIL."""
    today = _summary(map={"written": False})
    prev = _summary(map={"written": False})
    out = sc.evaluate_gates(D, today, [prev], _facts())
    assert out["verdict"] == "FAIL" and any("gate5" in f for f in out["fails"])


def test_gate5_last_seen_stale_is_fail():
    """「값 없음은 변경 아님」이 만든 사각 — 소스가 통째로 NULL 이 돼도 커버리지는 통과한다."""
    out = sc.evaluate_gates(D, _summary(), [],
                            _facts(max_last_seen=datetime(2026, 9, 1, 16, 0),
                                   last_seen_deadline=date(2026, 9, 2)))
    assert out["verdict"] == "FAIL" and any("last_seen" in f for f in out["fails"])


def test_gate6_null_rate_spike_is_warn():
    prev = _summary(map={"null_rate": {"ksic_code": 0.001, "ksic3_name": 0.003}})
    today = _summary(map={"null_rate": {"ksic_code": 0.02, "ksic3_name": 0.003}})
    out = sc.evaluate_gates(D, today, [prev], _facts())
    assert out["verdict"] == "WARN" and any("null_rate" in x for x in out["warns"])


def test_gate7_publish_delay_three_days_is_warn():
    late = _summary(map={"source_asof": "2026-09-04"})
    out = sc.evaluate_gates(D, late, [late, late], _facts())
    assert out["verdict"] == "WARN" and any("게시" in x for x in out["warns"])


def test_gate8_duplicate_map_rows_is_fail():
    out = sc.evaluate_gates(D, _summary(), [], _facts(duplicates=3))
    assert out["verdict"] == "FAIL" and any("gate8" in f for f in out["fails"])


def test_gate9_missing_summary_warn_then_fail():
    """오늘 summary 없음 = 1일 WARN · 3거래일 연속이면 FAIL."""
    one = sc.evaluate_gates(D, None, [_summary(), _summary()], _facts())
    assert one["verdict"] == "WARN"
    three = sc.evaluate_gates(D, None, [None, None], _facts())
    assert three["verdict"] == "FAIL" and any("gate9" in f for f in three["fails"])


def test_gate9_history_absent_passes_with_reason_but_lost_warns():
    """이력 «부족»은 PASS + 사유 · 이력 «유실»(그 «날짜의» recon 행은 있는데 파일이 없다)은 WARN."""
    absent = sc.evaluate_gates(D, _summary(), [], _facts())
    assert absent["verdict"] == "PASS" and any("이력 부족" in n for n in absent["notes"])
    # 🔴 [None]*20 도 「이력 부족」이다 — `not prev_summaries` 로 재면 사유가 안 찍힌다
    none20 = sc.evaluate_gates(D, _summary(), [None] * 20, _facts(prev_recon_dates=[]))
    assert any("이력 부족" in n for n in none20["notes"])
    lost = sc.evaluate_gates(D, _summary(), [None],
                             _facts(prev_days=["2026-09-04"],
                                    prev_recon_dates=["2026-09-04"]))
    assert lost["verdict"] == "WARN" and any("유실" in x for x in lost["warns"])
    # 「그 날짜」가 아닌 recon 행에는 발동하지 않는다
    other = sc.evaluate_gates(D, _summary(), [None],
                              _facts(prev_days=["2026-09-04"],
                                     prev_recon_dates=["2026-08-31"]))
    assert not any("유실" in x for x in other["warns"])


def test_verdict_vocabulary_and_iso_trade_date(monkeypatch):
    """판정 어휘는 PASS/WARN/FAIL 셋뿐 · recon 행의 trade_date 는 ISO 다
    (minute 의 'YYYYMMDD' 와 섞지 않는다)."""
    written = {}

    class _CM:
        def __enter__(self):
            return object()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _CM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_db_facts", lambda conn, d, prev_days: _facts())
    monkeypatch.setattr(sc, "_read_summary", lambda d: _summary())
    monkeypatch.setattr(sc, "_prev_trading_days", lambda conn, d, n: [])
    monkeypatch.setattr(
        sc.w, "upsert_reconciliation",
        lambda conn, td, rr, nr, ov, cov, vmr, verdict: written.update(
            {"td": td, "rr": rr, "nr": nr, "ov": ov, "cov": cov, "vmr": vmr, "v": verdict}))
    out = sc.reconcile_sector("20260907")
    assert out["verdict"] in ("PASS", "WARN", "FAIL")
    assert written["td"] == "2026-09-07"
    assert written["rr"] == 547 and written["ov"] == 5
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_reconcile.py -v
```
Expected: FAIL — `AttributeError: module 'collectors.sector_collector' has no attribute 'evaluate_gates'`

- [ ] **Step 3: writer 에 recon 행 쓰기를 넣는다**

`collectors/sector_writer.py` 에 추가:

```python
_UPSERT_RECON = """
INSERT INTO collection_reconciliation
  (trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict)
VALUES (%s, 'sector', %s, %s, %s, %s, %s, %s)
ON CONFLICT (trade_date, dataset) DO UPDATE SET
    real_rows=EXCLUDED.real_rows, new_rows=EXCLUDED.new_rows, overlap=EXCLUDED.overlap,
    value_match_rate=EXCLUDED.value_match_rate, coverage=EXCLUDED.coverage,
    verdict=EXCLUDED.verdict
"""


def upsert_reconciliation(conn, trade_date: str, real_rows: int, new_rows: int,
                          overlap: int, coverage, value_match_rate, verdict: str) -> None:
    """섹터 reconcile 행. 🔴 financial_writer 것을 못 쓴다 — 거긴 real_rows 인자가 없다.
    trade_date 는 ISO 'YYYY-MM-DD'(재무와 같은 형식 · minute 의 'YYYYMMDD' 와 섞지 않는다)."""
    try:
        with conn.cursor() as cur:
            cur.execute(_UPSERT_RECON, (trade_date, real_rows, new_rows, overlap,
                                        value_match_rate, coverage, verdict))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

- [ ] **Step 4: `evaluate_gates` · `_db_facts` · `reconcile_sector` 구현**

`collectors/sector_collector.py` 에 추가:

```python
COVERAGE_MIN = 0.98
G_FLOORS = {"ksic2": 40, "ksic3": 100, "ksic5": 200}
NO_PREV_FLOOR = 20


def _undef(summary, key, default=0):
    if not summary:
        return default
    u = ((summary.get("stats") or {}).get("undefined") or {})
    v = u.get(key)
    return default if v is None else v


def evaluate_gates(trade_date, today, prev_summaries, facts) -> dict:
    """§8 게이트 1~9. 순수 함수 — DB 를 만지지 않는다(테스트가 가짜 사실로 굴린다).

    prev_summaries: 직전 «거래일» summary 목록(최신순 · 없는 날은 None).
    """
    import statistics
    fails, warns, notes = [], [], []
    prev1 = prev_summaries[0] if prev_summaries else None
    umkt = facts.get("u_market") or 0
    cov = (float(facts.get("ksic_code_nonnull", 0)) / umkt) if umkt else 0.0
    vmr = (float(facts.get("ksic3_name_nonnull", 0)) / umkt) if umkt else 0.0

    # 1. 커버리지 (U_market 소속 열린 줄만 — U_all 의 상폐 23 은 분자·분모 모두 제외)
    if not umkt:
        notes.append("U_market 0 — 커버리지 판정 불가")
    else:
        if cov < COVERAGE_MIN:
            fails.append("gate1 ksic_code 커버리지 %.4f < %.2f" % (cov, COVERAGE_MIN))
        if vmr < COVERAGE_MIN:
            fails.append("gate1 ksic3_name 커버리지 %.4f < %.2f" % (vmr, COVERAGE_MIN))

    # 2. 성적표 존재 · G 하한 · 전일 대비
    g = facts.get("g") or {}
    if facts.get("is_trading_day"):
        if not facts.get("stats_rows"):
            fails.append("gate2 거래일인데 성적표 0행")
        for tax in sorted(G_FLOORS):
            if g.get(tax, 0) < G_FLOORS[tax]:
                fails.append("gate2 %s G=%d < %d (조인 붕괴 신호)"
                             % (tax, g.get(tax, 0), G_FLOORS[tax]))
        pg = ((prev1 or {}).get("stats") or {}).get("G") or {}
        for tax in sorted(G_FLOORS):
            if pg.get(tax):
                if not (pg[tax] * 0.8 <= g.get(tax, 0) <= pg[tax] * 1.2):
                    warns.append("gate2 %s G %d 가 전일 %d 대비 ±20%% 밖"
                                 % (tax, g.get(tax, 0), pg[tax]))
    else:
        notes.append("휴장일 — 성적표 게이트 생략")

    # 3. 미정 급증
    no_label = _undef(today, "no_label")
    no_prev = _undef(today, "no_prev")
    if prev1 is not None and no_label - _undef(prev1, "no_label") >= 50:
        warns.append("gate3 no_label 이 전일 대비 +%d" % (no_label - _undef(prev1, "no_label")))
    hist = [_undef(s, "no_prev") for s in prev_summaries if s]
    med = statistics.median(hist) if hist else 0
    thr = max(NO_PREV_FLOOR, 3 * med)
    if no_prev > thr:
        warns.append("gate3 no_prev %d > 문턱 %d (일봉 결손 신호 · 중앙값 %s)"
                     % (no_prev, thr, med))

    # 4. 정체 — 「3거래일 연속 동일」은 «오늘 포함» 3일이다(오늘 + 직전 2일).
    new_rows = facts.get("new_rows", 0)
    prev_nr = facts.get("prev_new_rows") or []
    if new_rows > 0 and len(prev_nr) >= 2 and all(p == new_rows for p in prev_nr[:2]):
        warns.append("gate4 정체 — 잔량 %d 가 3거래일 연속 동일(오늘 포함)" % new_rows)
    rc_hist = [((s or {}).get("ksic_fill") or {}).get("recheck_calls", 0)
               for s in ([today] + list(prev_summaries))[:20]]
    if len(rc_hist) >= 20 and all((c or 0) == 0 for c in rc_hist):
        warns.append("gate4 recheck_calls 가 20거래일 연속 0 — 재확인 순환 정지 의심")
    rchg = ((today or {}).get("ksic_fill") or {}).get("recheck_changed", 0) or 0
    if rchg > 10:
        warns.append("gate4 recheck_changed %d > 10 (레일 아래지만 이례적)" % rchg)

    # 5. 얼어붙은 명부
    def _written(s):
        return bool(((s or {}).get("map") or {}).get("written"))

    if today is not None and not _written(today) and prev1 is not None and not _written(prev1):
        fails.append("gate5 map.written=false 가 2거래일 연속")
    mls = facts.get("max_last_seen")
    dl = facts.get("last_seen_deadline")
    if mls is not None and dl is not None:
        mls_d = mls.date() if hasattr(mls, "date") else mls
        if mls_d < dl:
            fails.append("gate5 last_seen_at 최댓값 %s 가 %s 보다 오래됐다" % (mls_d, dl))

    # 6. 소스 이상
    nr_today = ((today or {}).get("map") or {}).get("null_rate") or {}
    nr_prev = ((prev1 or {}).get("map") or {}).get("null_rate") or {}
    for f in ("ksic_code", "ksic3_name"):
        v = nr_today.get(f)
        if v is None:
            continue
        p = nr_prev.get(f)
        if v > 0.10 or (p is not None and p > 0 and v > 2 * p):
            warns.append("gate6 null_rate[%s] %.4f (전일 %s)" % (f, v, p))
    if ((today or {}).get("map") or {}).get("stale"):
        warns.append("gate6 stale=true — 캐시 게시일이 5거래일 넘게 낡았다")

    # 7. 게시 지연
    iso = trade_date.isoformat()
    delayed = []
    for s in [today] + list(prev_summaries)[:2]:
        sa = ((s or {}).get("map") or {}).get("source_asof")
        delayed.append(bool(sa) and sa < iso)
    if len(delayed) == 3 and all(delayed):
        warns.append("gate7 게시 지연 — source_asof < trade_date 가 3거래일 연속")

    # 8. 명부 중복
    if facts.get("duplicates"):
        fails.append("gate8 명부 중복 %d종목 — 유효기간이 겹친다(n_members 이중 계산)"
                     % facts["duplicates"])

    # 9. summary 부재 / 이력 부족 vs 유실
    if today is None:
        if len(prev_summaries) >= 2 and all(s is None for s in prev_summaries[:2]):
            fails.append("gate9 summary 가 3거래일 연속 없음")
        else:
            warns.append("gate9 오늘 summary 없음")
    # 🔴 「이력 부족」은 «파일이 하나도 없을 때»다 — `not prev_summaries` 로 재면
    #    [None]*20 이 참이 아니라서 사유가 영영 안 찍힌다.
    if not [s for s in prev_summaries if s]:
        notes.append("이력 부족 — 전일 대비 게이트는 판정하지 않았다(첫 EOD 면 정상)")
    # 「유실」은 «그 날짜의» recon 행이 있는데 «그 날짜의» summary 파일이 없을 때만이다
    # (아무 recon 행에나 발동하면 첫날부터 매일 WARN 이 뜬다).
    prev_days = facts.get("prev_days") or []
    recon_dates = set(facts.get("prev_recon_dates") or [])
    lost = [prev_days[i] for i, s in enumerate(prev_summaries)
            if s is None and i < len(prev_days) and prev_days[i] in recon_dates]
    if lost:
        warns.append("gate9 이력 유실 — recon 행은 있는데 summary 파일이 없는 날: %s" % lost[:3])

    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"verdict": verdict, "fails": fails, "warns": warns, "notes": notes,
            "real_rows": facts.get("stats_rows", 0), "new_rows": new_rows,
            "overlap": no_label, "coverage": cov, "value_match_rate": vmr}


_FACTS_COVERAGE_SQL = (
    "SELECT count(*) FILTER (WHERE ksic_code IS NOT NULL),"
    "       count(*) FILTER (WHERE ksic3_name IS NOT NULL),"
    "       count(*) FILTER (WHERE corp_code IS NOT NULL AND ksic_code IS NULL) "
    "FROM stock_sector_map "
    "WHERE valid_to IS NULL AND stock_code IN "
    "      (SELECT stock_code FROM stock_market WHERE " + SQL_STOCK_ONLY + ")")


def _prev_trading_days(conn, d, n) -> list:
    """직전 거래일 n개(최신순 · ISO 문자열)."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date < %s "
                    "ORDER BY date DESC LIMIT %s", (d.isoformat(), n))
        return [r[0] for r in cur.fetchall()]


def _db_facts(conn, d, prev_days) -> dict:
    """게이트가 볼 DB 사실을 «한 번에» 모은다.

    prev_days 는 호출측이 이미 구한 직전 거래일 20개(최신순 ISO)다 — 여기서 다시
    조회하면 같은 쿼리를 두 번 돌린다(경미 13).
    """
    iso = d.isoformat()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stock_market WHERE " + SQL_STOCK_ONLY)
        u_market = int(cur.fetchone()[0])
        cur.execute(_FACTS_COVERAGE_SQL)
        code_nn, name_nn, remaining = [int(x) for x in cur.fetchone()]
        cur.execute("SELECT count(*) FROM sector_daily_stats WHERE date=%s", (d,))
        stats_rows = int(cur.fetchone()[0])
        cur.execute("SELECT taxonomy, count(*) FROM sector_daily_stats WHERE date=%s "
                    "GROUP BY 1", (d,))
        g = dict((r[0], int(r[1])) for r in cur.fetchall())
        cur.execute("SELECT count(*) FROM (SELECT stock_code FROM fn_sector_map_as_of(%s) "
                    "GROUP BY 1 HAVING count(*) > 1) t", (d,))
        dups = int(cur.fetchone()[0])
        cur.execute("SELECT max(last_seen_at) FROM stock_sector_map WHERE valid_to IS NULL")
        max_ls = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM daily_prices WHERE date=%s", (iso,))
        is_td = int(cur.fetchone()[0]) > 0
        cur.execute("SELECT trade_date, new_rows FROM collection_reconciliation "
                    "WHERE dataset='sector' AND trade_date < %s "
                    "ORDER BY trade_date DESC LIMIT 3", (iso,))
        prev_recon = cur.fetchall()
    return {"u_market": u_market, "ksic_code_nonnull": code_nn,
            "ksic3_name_nonnull": name_nn, "new_rows": remaining,
            "stats_rows": stats_rows, "g": g, "duplicates": dups,
            "max_last_seen": max_ls, "is_trading_day": is_td,
            "last_seen_deadline": (date.fromisoformat(prev_days[2])
                                   if len(prev_days) >= 3 else None),
            "prev_days": list(prev_days),
            "prev_new_rows": [int(r[1] or 0) for r in prev_recon],
            "prev_recon_dates": [r[0] for r in prev_recon]}


def reconcile_sector(trade_date: str = None) -> dict:
    """§8 건강 판정. 결과는 collection_reconciliation(dataset='sector')에 남긴다."""
    d = date.fromisoformat(_to_iso(trade_date)) if trade_date else now_kst().date()
    iso = d.isoformat()
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        prev_days = _prev_trading_days(conn, d, 20)      # 한 번만 조회한다
        facts = _db_facts(conn, d, prev_days)
    today = _read_summary(d)
    prev_summaries = [_read_summary(date.fromisoformat(x)) for x in prev_days]
    out = evaluate_gates(d, today, prev_summaries, facts)
    with KisDbConnection.get_connection() as conn:
        w.upsert_reconciliation(conn, iso, out["real_rows"], out["new_rows"],
                                out["overlap"], out["coverage"], out["value_match_rate"],
                                out["verdict"])
    log = logger.error if out["verdict"] == "FAIL" else (
        logger.warning if out["verdict"] == "WARN" else logger.info)
    log("[sector] reconcile %s = %s · fails=%s · warns=%s · notes=%s",
        iso, out["verdict"], out["fails"], out["warns"], out["notes"])
    out["trade_date"] = iso
    return out
```

- [ ] **Step 5: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_reconcile.py -v
```
Expected: 16 passed

- [ ] **Step 6: §8-1 「분자가 U_market 한정」을 실 DB 로 고정한다 (M4)**

T13 은 합성 `_facts()` 로만 굴리므로 **SQL 자체는 검증되지 않는다**. `test_sector_writer_db.py`
끝에 추가(Task 7 의 `_insert_named` 헬퍼를 그대로 쓴다):

```python
def test_coverage_numerator_is_limited_to_u_market(conn):
    """§8-1 — 커버리지 분자·분모는 «U_market 소속 열린 줄»만 센다.

    🔴 U_all 에만 있는 상폐 23 종목이 분자에 섞이면 커버리지가 부풀어 98% 게이트를
       «거짓으로» 통과한다. stock_market 에 없는 코드로 열린 줄을 하나 만들어 두고
       분자·분모가 «둘 다» 안 움직이는지 본다.
    """
    from collectors import sector_collector as sc2
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stock_market WHERE stock_code='TEST9C'")
        assert cur.fetchone()[0] == 0, "합성 코드가 실제 상장목록에 있다 - 다른 코드를 쓸 것"
        cur.execute("SELECT count(*) FROM stock_market WHERE " + sc2.SQL_STOCK_ONLY)
        den_before = int(cur.fetchone()[0])
        cur.execute(sc2._FACTS_COVERAGE_SQL)
        num_before = cur.fetchone()

    with conn.cursor() as cur:
        _insert_named(cur, "TEST9C", "2611", "합성")
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stock_market WHERE " + sc2.SQL_STOCK_ONLY)
        den_after = int(cur.fetchone()[0])
        cur.execute(sc2._FACTS_COVERAGE_SQL)
        num_after = cur.fetchone()
    assert num_after == num_before, "U_market 밖 종목이 커버리지 «분자»에 들어갔다"
    assert den_after == den_before, "U_market 밖 종목이 커버리지 «분모»를 움직였다"
```

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_writer_db.py -v
```
Expected: 8 passed

- [ ] **Step 7: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): reconcile_sector — §8 게이트 1~9 · PASS/WARN/FAIL (Task 9)

게이트 판정은 순수 함수(evaluate_gates)로 떼어 가짜 사실로 굴릴 수 있게 했다.
얼어붙은 명부(written=false 2연속 · last_seen_at 3거래일 정체)와 명부 중복은 FAIL,
정체·게시 지연·NULL 급증은 WARN 이다 — KSIC 는 재무와 달리 내일 또 물을 수 있다.
no_prev 문턱은 「전일의 2배」가 아니라 max(20, 3×직전 20거래일 중앙값)이다
(기저가 0~3 이라 2배 규칙은 1건에 걸린다). recon 행은 자체 SQL 로 쓴다 —
financial_writer 것엔 real_rows 인자가 없다.
커버리지 SQL 이 U_market 한정임은 합성 _facts 가 아니라 실 DB 테스트로 고정한다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/sector_writer.py RoboTrader_template/collectors/sector_collector.py RoboTrader_template/tests/collectors/test_sector_reconcile.py RoboTrader_template/tests/collectors/test_sector_writer_db.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 10: CLI — `--bootstrap` · `--backfill` · `--regen` · `--regen-map` · `--delete-stats` · `--dry-run` · 시간 가드 (T14 나머지)

**Files:**
- Modify: `RoboTrader_template/collectors/sector_writer.py` (재생성용 DB 쓰기 4개 — **DELETE/UPDATE 도 여기서만**)
- Modify: `RoboTrader_template/collectors/sector_collector.py`
- Modify: `RoboTrader_template/tests/collectors/test_sector_collector.py`

**Interfaces:**
- Consumes:
  - Task 5: `load_u_market`·`fill_ksic`·`recopy_preferred`·`maybe_refresh_corp_code` · `sector_writer.apply_ksic_updates`·`load_open_rows`·`load_stock_industry`·`open_market_counts`
  - Task 6: `compute_stats` · `sector_writer.delete_stats`
  - Task 7: `sector_writer.rebuild_ksic_names`
  - Task 8: `update_map`·`_report`·`_live_three_table_counts`
  - Task 9: `_FACTS_COVERAGE_SQL`·`COVERAGE_MIN`
  - Task 3: `krx_desc_cache.load_desc`·`fold_market_counts`·`ARCHIVE_DIR`
- Produces (writer — B3):
  - `MAP_SNAPSHOT_TABLE = "stock_sector_map_regen_bak"`
  - `reset_map_from(conn, d_from) -> dict` — `{"deleted","reopened"}` · 겹침 발생 시 `RuntimeError`
  - `snapshot_map(conn) -> int` · `restore_map(conn) -> int` · `drop_map_snapshot(conn) -> None`
- Produces (collector):
  - `_guard_window(force=False, now=None) -> None` — 평일 15:30~17:00 이면 `RuntimeError`
  - `_trading_days_between(conn, d_from, d_to) -> list`
  - `_gz_fetcher() -> callable` — 보관 gz 를 캐시 CSV 처럼 돌려준다
  - `bootstrap(trade_date, dry_run=False, force=False) -> dict`
  - `backfill(d_from, d_to, dry_run=False, force=False) -> dict`
  - `regen_stats(d_from, d_to, taxonomy=None, dry_run=False, force=False) -> dict`
  - `regen_map(d_from, dry_run=False, force=False) -> dict`
  - `delete_stats_cli(d_from, d_to, taxonomy=None, dry_run=False, force=False) -> dict`
  - `__main__` argparse 블록

**공유 테스트 헬퍼와 정의 태스크** — 이 태스크의 테스트는 앞 태스크가 만든 헬퍼를 그대로 쓴다:
`_csv`·`_fake_fetcher`(Task 3 Step 1) · `_DummyCM`·`_row`·`_FakeFetcher`·`_patch_fill`(Task 5 Step 1·6) ·
`_patch_collect`(Task 8 Step 1). 같은 파일(`test_sector_collector.py`) 안이라 import 는 필요 없다.

- [ ] **Step 1: 시간 가드 · dry-run 테스트를 쓴다 (실패)**

`tests/collectors/test_sector_collector.py` 끝에 추가:

```python
def test_weekday_eod_window_is_refused():
    """§5-5 — 평일 15:30~17:00 은 EOD 와 겹친다. --force 없이는 거부."""
    with pytest.raises(RuntimeError) as e:
        sc._guard_window(force=False, now=datetime(2026, 9, 7, 16, 0))   # 월요일
    assert "15:30" in str(e.value)
    sc._guard_window(force=True, now=datetime(2026, 9, 7, 16, 0))        # --force 는 통과
    sc._guard_window(force=False, now=datetime(2026, 9, 7, 15, 29))      # 창 전
    sc._guard_window(force=False, now=datetime(2026, 9, 7, 17, 0))       # 창 끝(포함 안 함)
    sc._guard_window(force=False, now=datetime(2026, 9, 5, 16, 0))       # 토요일


def _patch_backfill(monkeypatch, calls, rows=550):
    """backfill 이 DB·파일을 안 타게 한다(라이브 3표 대조·리포트도 스텁)."""
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_live_three_table_counts",
                        lambda conn: {"daily_prices": 1, "minute_candles": 2,
                                      "virtual_trading_records": 3})
    monkeypatch.setattr(sc, "_report", lambda name, lines: "(report)")
    monkeypatch.setattr(sc, "_trading_days_between",
                        lambda conn, a, b: ["2026-09-04", "2026-09-07"])
    monkeypatch.setattr(sc, "compute_stats",
                        lambda conn, d: calls.append(d) or {"rows": rows,
                                                            "G": {"ksic3": 159},
                                                            "undefined": {}})


def test_backfill_dry_run_writes_nothing(monkeypatch):
    """--dry-run 은 쓰기 0 · 리포트만."""
    calls = []
    _patch_backfill(monkeypatch, calls)
    out = sc.backfill(date(2026, 9, 4), date(2026, 9, 7), dry_run=True, force=True)
    assert calls == [], "dry-run 인데 성적표를 계산·적재했다"
    assert out["dry_run"] is True and out["days"] == 2


def test_backfill_writes_each_trading_day(monkeypatch):
    """거래일마다 한 번씩 돈다 · 라이브 3표 전후가 같아야 통과한다."""
    calls = []
    _patch_backfill(monkeypatch, calls)
    out = sc.backfill(date(2026, 9, 4), date(2026, 9, 7), force=True)
    assert calls == [date(2026, 9, 4), date(2026, 9, 7)]
    assert out["rows"] == 1100 and out["days_with_rows"] == 2


def test_gz_fetcher_reads_archive(tmp_path, monkeypatch):
    """--regen-map 은 «보관 gz» 를 캐시 CSV 처럼 읽는다(네트워크 0)."""
    import gzip
    monkeypatch.setattr(kdc, "ARCHIVE_DIR", str(tmp_path))
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업")])
    with gzip.open(os.path.join(str(tmp_path), "krx_desc_2026-09-04.csv.gz"), "wb") as fh:
        fh.write(raw)
    fn = sc._gz_fetcher()
    assert fn("x/2026-09-05.csv") == (404, b"")
    status, body = fn("x/2026-09-04.csv")
    assert status == 200 and body == raw
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: FAIL — `AttributeError: module 'collectors.sector_collector' has no attribute '_guard_window'`

- [ ] **Step 3: 시간 가드 · 거래일 · gz 폴백 구현**

`collectors/sector_collector.py` 에 추가:

```python
def _guard_window(force=False, now=None) -> None:
    """§5-5 — 평일 15:30~17:00 은 EOD 와 겹치므로 수동 CLI 를 거부한다(--force 로만 통과).

    🔑 재무 백필이 EOD 와 겹치면 같은 opendart 호스트를 두 프로세스가 두드린다.
    """
    if force:
        return
    t = now or now_kst()
    if t.weekday() < 5 and (15, 30) <= (t.hour, t.minute) < (17, 0):
        raise RuntimeError(
            "평일 15:30~17:00 에는 실행할 수 없다(EOD 충돌). 야간/주말에 돌리거나 --force 를 쓸 것. "
            "현재 %s" % t)


def _trading_days_between(conn, d_from, d_to) -> list:
    """구간의 거래일(daily_prices 고유 날짜) — ISO 문자열 오름차순."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN %s AND %s "
                    "ORDER BY date", (d_from.isoformat(), d_to.isoformat()))
        return [r[0] for r in cur.fetchall()]


def _gz_fetcher():
    """보관 gz(`scratchpad/sector/krx_desc_*.csv.gz`)를 캐시 CSV 응답처럼 돌려준다.

    🔑 fetch_desc_csv 의 «7일 후퇴»가 그대로 동작하므로 그날 보관본이 없으면
       가장 가까운 이전 보관본을 쓴다(원래 수집이 그랬던 것과 같은 규칙).
    """
    import gzip as _gzip

    def _fn(url):
        key = url.rsplit("/", 1)[-1].replace(".csv", "")
        path = os.path.join(kdc.ARCHIVE_DIR, "krx_desc_%s.csv.gz" % key)
        if os.path.exists(path):
            with _gzip.open(path, "rb") as fh:
                return 200, fh.read()
        return 404, b""

    return _fn
```

- [ ] **Step 4: `backfill` · `regen_stats` · `delete_stats_cli` 구현**

```python
def _report(name, lines) -> str:
    """리포트 파일 — 실행 근거를 파일로 남긴다(스펙 §6.0-5 · §6.2)."""
    os.makedirs(SECTOR_DIR, exist_ok=True)
    stamp = now_kst().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SECTOR_DIR, "%s_%s.txt" % (name, stamp))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(str(x) for x in lines) + "\n")
    logger.info("[sector] 리포트: %s", path)
    return path


def _live_three_table_counts(conn) -> dict:
    """라이브 3표 전후 대조 — 이 작업은 «읽기»만 한다는 증거."""
    out = {}
    with conn.cursor() as cur:
        for t in ("daily_prices", "minute_candles", "virtual_trading_records"):
            cur.execute("SELECT count(*) FROM " + t)
            out[t] = int(cur.fetchone()[0])
    return out


def backfill(d_from, d_to, dry_run=False, force=False) -> dict:
    """§6.2 — 거래일 순회 성적표 재계산. 라이브 3표는 «읽기»만 한다.

    첫날(2021-01-04)은 20일 창 안에 직전 봉이 없어 성적표가 비므로 결과는 거래일 − 1 이다.
    """
    _guard_window(force)
    t0 = now_kst()
    rows = 0
    days_with_rows = 0
    g_hist = {}
    undef_hist = []
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        before = _live_three_table_counts(conn)
        days = _trading_days_between(conn, d_from, d_to)
        logger.info("[sector] 백필 %s ~ %s · 거래일 %d일 (dry_run=%s)",
                    d_from, d_to, len(days), dry_run)
        if not dry_run:
            for i, iso in enumerate(days, 1):
                res = compute_stats(conn, date.fromisoformat(iso))
                rows += res.get("rows", 0)
                if res.get("rows"):
                    days_with_rows += 1
                for tax, n in (res.get("G") or {}).items():
                    g_hist.setdefault(tax, []).append(n)
                undef_hist.append(res.get("undefined") or {})
                if i % 100 == 0:
                    logger.info("[sector] 백필 %d/%d rows=%d", i, len(days), rows)
        after = _live_three_table_counts(conn)
    out = {"from": str(d_from), "to": str(d_to), "days": len(days), "rows": rows,
           "days_with_rows": days_with_rows, "dry_run": dry_run,
           "live_before": before, "live_after": after,
           "elapsed_sec": (now_kst() - t0).total_seconds()}
    out["report"] = _report("backfill_report", [
        "섹터 성적표 백필 리포트", str(out), "",
        "일자별 G 분포: " + str(dict((k, {"min": min(v), "max": max(v),
                                          "median": sorted(v)[len(v) // 2]})
                                     for k, v in g_hist.items())),
        "미정 종목 수 분포(마지막 5일): " + str(undef_hist[-5:]),
        "",
        "🔴 2021-01-04 ~ 구축일 구간의 업종 라벨은 «현재 스냅샷의 소급»이다(§5-2).",
        "🔴 2024-03-12 이전 성적표는 태쏘 SEC-M1 과 «대조되지 않았다» — 시총이 사실상",
        "   2024-03-13 부터라 태쏘 유니버스가 거의 비기 때문이다(§3.2).",
        "라이브 3표 전/후: %s / %s" % (before, after),
    ])
    if before != after:
        raise RuntimeError("🔴 라이브 3표 행수가 바뀌었다 — 즉시 보고: %s → %s" % (before, after))
    return out


def regen_stats(d_from, d_to, taxonomy=None, dry_run=False, force=False) -> dict:
    """§5-4 ③ — 성적표만 재계산(명부는 안 건드린다). taxonomy 지정 시 그것만 지우고 다시 쓴다."""
    _guard_window(force)
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        days = _trading_days_between(conn, d_from, d_to)
        if dry_run:
            return {"from": str(d_from), "to": str(d_to), "days": len(days),
                    "dry_run": True, "would_delete_taxonomy": taxonomy}
        deleted = w.delete_stats(conn, d_from, d_to, taxonomy)
        rows = 0
        for iso in days:
            rows += compute_stats(conn, date.fromisoformat(iso)).get("rows", 0)
    return {"from": str(d_from), "to": str(d_to), "days": len(days),
            "deleted": deleted, "rows": rows, "dry_run": False}


def delete_stats_cli(d_from, d_to, taxonomy=None, dry_run=False, force=False) -> dict:
    """§6.2 데이터 롤백 — 건수를 리포트에 남기고 실행(승인 필수)."""
    _guard_window(force)
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        if dry_run:
            with conn.cursor() as cur:
                sql = "SELECT count(*) FROM sector_daily_stats WHERE date BETWEEN %s AND %s"
                params = [d_from, d_to]
                if taxonomy:
                    sql += " AND taxonomy=%s"
                    params.append(taxonomy)
                cur.execute(sql, params)
                n = int(cur.fetchone()[0])
            out = {"would_delete": n, "dry_run": True}
        else:
            out = {"deleted": w.delete_stats(conn, d_from, d_to, taxonomy), "dry_run": False}
    out["report"] = _report("delete_stats_report",
                            ["성적표 삭제", str(d_from), str(d_to), str(taxonomy), str(out)])
    return out
```

- [ ] **Step 5: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py -v
```
Expected: 40 passed

- [ ] **Step 6: writer 에 재생성용 쓰기 4개를 넣는다 (B3 — DELETE/UPDATE 도 writer 안에서)**

`collectors/sector_writer.py` 끝에 이어붙인다:

```python
MAP_SNAPSHOT_TABLE = "stock_sector_map_regen_bak"


def reset_map_from(conn, d_from) -> dict:
    """§5-4 `--regen-map` 전용 — d_from «이후»의 SCD2 를 되돌린다.

    ① `valid_from >= d_from` 인 줄 삭제 ② `valid_to >= d_from − 1일` 인 줄 다시 열기.
    🔴 ② 뒤에 같은 종목의 열린 줄이 2개 이상이면 즉시 실패한다 — 겹치는 유효기간은
       `fn_sector_map_as_of` 에서 종목당 2행이 되고 그건 n_members 이중 계산이다(§8-8).
    🔴 이 함수가 stock_sector_map 에 DELETE/UPDATE 를 하는 «유일한» 자리다.
    """
    from datetime import timedelta
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_sector_map WHERE valid_from >= %s", (d_from,))
            deleted = cur.rowcount
            cur.execute("UPDATE stock_sector_map SET valid_to=NULL WHERE valid_to >= %s",
                        (d_from - timedelta(days=1),))
            reopened = cur.rowcount
            cur.execute("SELECT count(*) FROM (SELECT stock_code FROM stock_sector_map "
                        "WHERE valid_to IS NULL GROUP BY 1 HAVING count(*) > 1) t")
            dup = int(cur.fetchone()[0])
            if dup:
                raise RuntimeError(
                    "reset 후 열린 줄이 2개 이상인 종목 %d개 — 재생성을 중단한다"
                    "(겹치는 유효기간 = n_members 이중 계산)" % dup)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    logger.warning("[sector] 명부 되돌리기 — 삭제 %d행 · 다시 연 줄 %d행", deleted, reopened)
    return {"deleted": deleted, "reopened": reopened}


def snapshot_map(conn) -> int:
    """재생성 전 표 «전체» 스냅샷. 일자별 재구축은 단계마다 커밋되므로 중간 실패가
    명부를 잘린 채 남긴다 — 되돌릴 원본이 있어야 한다.

    🔴 남아 있는 스냅샷을 «덮지 않는다». 스냅샷이 남아 있다는 건 직전 재생성이
       복구까지 실패했다는 뜻이고, 그때 그 표가 **유일한 복구원**이다. 무조건 DROP 하면
       그 원본을 다음 실행이 지운다 — 사람이 확인하고 손으로 지우게 한다.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", ("public." + MAP_SNAPSHOT_TABLE,))
            if cur.fetchone()[0] is not None:
                raise RuntimeError(
                    "직전 재생성의 스냅샷(%s)이 남아 있다 — 복구가 끝났는지 «확인한 뒤» "
                    "수동으로 DROP 하고 다시 실행할 것. 복구가 필요하면: "
                    "DELETE FROM stock_sector_map; "
                    "INSERT INTO stock_sector_map SELECT * FROM %s;"
                    % (MAP_SNAPSHOT_TABLE, MAP_SNAPSHOT_TABLE))
            cur.execute("CREATE TABLE " + MAP_SNAPSHOT_TABLE
                        + " AS SELECT * FROM stock_sector_map")
            cur.execute("SELECT count(*) FROM " + MAP_SNAPSHOT_TABLE)
            n = int(cur.fetchone()[0])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return n


def restore_map(conn) -> int:
    """스냅샷으로 통째 복구. 🔴 실패 경로에서만 부른다."""
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_sector_map")
            cur.execute("INSERT INTO stock_sector_map SELECT * FROM " + MAP_SNAPSHOT_TABLE)
            n = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    logger.error("[sector] 명부를 스냅샷 %d행으로 복구했다", n)
    return n


def drop_map_snapshot(conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS " + MAP_SNAPSHOT_TABLE)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

⚠️ 테이블 이름은 **모듈 상수**다(사용자 입력이 아니므로 문자열 결합이 안전하다).

🔴 **스냅샷이 남아 있을 때의 수동 복구 절차**(`snapshot_map` 이 RuntimeError 를 낼 때):

1. 남은 스냅샷과 현재 표를 «먼저 비교»한다 — 무엇을 잃었는지 모른 채 덮어쓰지 않는다.
```
export PGCLIENTENCODING=UTF8
PGPASSWORD=1234 "C:/Program Files/PostgreSQL/16/bin/psql.exe" -h 127.0.0.1 -p 5433 -U robotrader -d kis_template -A -F"|" -c "SELECT (SELECT count(*) FROM stock_sector_map) AS live, (SELECT count(*) FROM stock_sector_map_regen_bak) AS snapshot"
```
2. 복구가 필요하면(라이브가 잘려 있으면) — **사장님 승인 후**:
```
PGPASSWORD=1234 "C:/Program Files/PostgreSQL/16/bin/psql.exe" -h 127.0.0.1 -p 5433 -U robotrader -d kis_template -c "BEGIN; DELETE FROM stock_sector_map; INSERT INTO stock_sector_map SELECT * FROM stock_sector_map_regen_bak; COMMIT;"
```
3. 복구가 «필요 없다»고 확인됐으면 스냅샷만 지운다:
```
PGPASSWORD=1234 "C:/Program Files/PostgreSQL/16/bin/psql.exe" -h 127.0.0.1 -p 5433 -U robotrader -d kis_template -c "DROP TABLE stock_sector_map_regen_bak"
```
4. 그 다음에야 `--regen-map` 을 다시 돌린다.

🔴 이 절차를 «코드가 자동으로» 하지 않는 이유: 스냅샷이 남아 있다는 건 직전 복구까지
실패했다는 뜻이고, 그때 그 표가 **유일한 원본**이다. 자동 DROP 은 그 원본을 지운다.

- [ ] **Step 7: `bootstrap` · `regen_map` · `__main__` 구현**

```python
def bootstrap(trade_date, dry_run=False, force=False) -> dict:
    """§6.0 — 1회 · 머지 «전» 워크트리에서 · 야간/주말 · 사장님 승인 후.

    순서: 1)corp_code 2)명부(valid_from=2021-01-04) 3)DART 채우기 3b)우선주 재복사
          4)이름표 5)리포트 6)게이트(둘 다 ≥ 98%)
    ⚠️ --dry-run 은 «DB 쓰기 0 · DART 호출 0 · gz 0» 이다 — 대상 건수와 함께
       게이트가 볼 두 커버리지의 «예측치»(2단계 후 · 3b 후)를 인쇄한다.
    """
    _guard_window(force)
    d = date.fromisoformat(_to_iso(trade_date)) if isinstance(trade_date, str) else trade_date
    key = _load_dart_key()
    steps = {}
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        before = _live_three_table_counts(conn)
        umkt = set(load_u_market(conn))
        if dry_run:
            # 🔴 gz 도 쓰지 않는다(archive=False) — dry-run 이 파일을 남기면 「쓰기 0」이
            #    거짓이 되고 §5-4 재생성 원료에 «실제로는 안 쓴 날»이 섞인다.
            open_rows = w.load_open_rows(conn)
            desc = kdc.load_desc(d, kdc.fold_market_counts(w.open_market_counts(conn)),
                                 archive=False)
            snap = w.load_stock_industry(conn)
            cmap = load_map(conn)
            universe = set(load_universe(conn))
            by_code = dict((r["stock_code"], r) for r in desc["rows"])
            matched = [c for c in universe if c in by_code]
            would_dart = [c for c in sorted(universe)
                          if w.parent_code(c) is None and c not in snap and c in cmap]
            # 게이트가 볼 두 커버리지를 «예측»한다 — 안 내면 dry-run 이 98% 판정을 못 돕는다.
            pred_code, pred_name = set(), set()
            for c in universe:
                if w.parent_code(c) is None:
                    if c in snap or c in cmap:      # 스냅샷 시드 또는 DART 로 채워질 것
                        pred_code.add(c)
                    if by_code.get(c, {}).get("ksic3_name"):
                        pred_name.add(c)
            for c in universe:                       # 3b 우선주 재복사 예측
                p = w.parent_code(c)
                if p is None or p not in universe:
                    continue
                if p in pred_code:
                    pred_code.add(c)
                if p in pred_name:
                    pred_name.add(c)
            n = len(umkt) or 1
            # 2단계 «후»(= DART 채우기 전) 예측에서는 would_dart 로 채워질 종목뿐 아니라
            # 그 부모를 복사받는 «우선주 자식»도 빼야 한다(실제 사례 0220WL → 0220W0).
            not_yet = set(would_dart)
            for c in universe:
                p = w.parent_code(c)
                if p is not None and p in not_yet:
                    not_yet.add(c)
            steps = {"matched": len(matched),
                     "snapshot_hits": len([c for c in matched if c in snap]),
                     "would_dart_calls": len(would_dart), "open_rows": len(open_rows),
                     "predicted_coverage_after_2": {
                         "ksic_code": float(len((pred_code - not_yet) & umkt)) / n,
                         "ksic3_name": float(len(pred_name & umkt)) / n},
                     "predicted_coverage_after_3b": {
                         "ksic_code": float(len(pred_code & umkt)) / n,
                         "ksic3_name": float(len(pred_name & umkt)) / n},
                     "u_market": len(umkt)}
            after = _live_three_table_counts(conn)
            out = {"dry_run": True, "steps": steps, "live_before": before, "live_after": after}
            out["report"] = _report("bootstrap_report_dryrun", [
                "부트스트랩 dry-run (쓰기 0 · DART 0 · gz 0)", str(out), "",
                "⚠️ 예측치다 — DART 가 125건 전부 induty_code 를 준다는 가정에서 나온 값이고,",
                "   그 가정은 08-07 실행(다른 집합)에서 왔다. 본 실행 리포트가 실측으로 대체한다.",
                "⚠️ 예측은 «과대»일 수 있다 — 무자료(013) 응답·형식 이상 코드는 반영하지 않는다.",
            ])
            return out

        # 1) corp_code
        steps["corp_code"] = maybe_refresh_corp_code(conn, key, days=0)
        # 2) 명부 (소급 · valid_from = 2021-01-04)
        steps["map"] = update_map(conn, d, source="bootstrap_snapshot",
                                  use_snapshot=True, valid_from=BOOTSTRAP_VALID_FROM)
        steps["coverage_after_2"] = _coverage(conn, umkt)
        # 3) DART 채우기 (예상 125 < 상한 300)
        steps["ksic_fill"] = fill_ksic(conn, d, cap=DART_DAILY_CAP, recheck_max=0, key=key)
        # 3b) 우선주 재복사 — 3 에서 부모(0220W0 등)가 채워진 자식을 받는다
        steps["recopy"] = recopy_preferred(conn, d, source="bootstrap_snapshot")["counts"]
        steps["coverage_after_3b"] = _coverage(conn, umkt)
        # 4) 이름표
        steps["names"] = w.rebuild_ksic_names(conn)
        unlabeled = _unlabeled_list(conn, umkt)
        after = _live_three_table_counts(conn)

    cov = steps["coverage_after_3b"]
    out = {"dry_run": False, "steps": steps, "unlabeled": unlabeled,
           "live_before": before, "live_after": after}
    out["report"] = _report("bootstrap_report", [
        "섹터 명부 부트스트랩 리포트", "기준일: %s" % d, "",
        "U_market: %d" % len(umkt),
        "2단계 후 커버리지: %s" % steps["coverage_after_2"],
        "3b 후 커버리지: %s" % cov,
        "DART 응답: %s" % steps["ksic_fill"].get("status_counts"),
        "  · nodata(업종 없음): %s" % steps["ksic_fill"].get("nodata"),
        "  · 채운 종목: %s" % steps["ksic_fill"].get("filled"),
        "이름표 코드 수: %s · 점유율<0.8: %s" % (steps["names"].get("codes"),
                                                steps["names"].get("low_share")),
        "미라벨 종목 목록(%d): %s" % (len(unlabeled), unlabeled),
        "라이브 3표 전/후: %s / %s" % (before, after),
        "",
        "🔴 이 구간(2021-01-04 ~ 구축일)의 업종 라벨은 «현재 스냅샷의 소급»이다(§5-2).",
    ])
    if before != after:
        raise RuntimeError("🔴 라이브 3표 행수가 바뀌었다 — 즉시 보고: %s → %s" % (before, after))
    if cov["ksic_code"] < COVERAGE_MIN or cov["ksic3_name"] < COVERAGE_MIN:
        raise RuntimeError(
            "🔴 부트스트랩 게이트 미달 — 백필을 진행하지 말고 사장님께 보고할 것: %s" % cov)
    return out


def _coverage(conn, umkt) -> dict:
    with conn.cursor() as cur:
        cur.execute(_FACTS_COVERAGE_SQL)
        code_nn, name_nn, _rem = [int(x) for x in cur.fetchone()]
    n = len(umkt) or 1
    return {"ksic_code": float(code_nn) / n, "ksic3_name": float(name_nn) / n,
            "u_market": len(umkt)}


def _unlabeled_list(conn, umkt) -> list:
    """미라벨 = ①열린 줄은 있는데 코드/이름이 비었다 ②**열린 줄이 아예 없다**.

    🔴 ②를 빼면 「명부에 안 들어온 종목」이 목록에도 커버리지에도 안 보인다 —
       못 본 것을 없는 것으로 읽는 바로 그 형태다.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT stock_code FROM stock_sector_map WHERE valid_to IS NULL "
                    "AND (ksic_code IS NULL OR ksic3_name IS NULL)")
        partial = set(r[0] for r in cur.fetchall())
        cur.execute("SELECT stock_code FROM stock_sector_map WHERE valid_to IS NULL")
        have_row = set(r[0] for r in cur.fetchall())
    missing_row = set(umkt) - have_row
    if missing_row:
        logger.warning("[sector] 명부에 열린 줄이 «아예 없는» U_market 종목 %d개: %s",
                       len(missing_row), sorted(missing_row)[:10])
    return sorted((partial & set(umkt)) | missing_row)


def regen_map(d_from, dry_run=False, force=False) -> dict:
    """§5-4 ② — 그 날짜 «이후»의 SCD2 를 보관 gz + dart_company_*.jsonl 로 재생성한다.

    🔴 손 수정(SQL 직접 UPDATE/DELETE) 금지의 대체 경로다.
    🔴 하한 = 첫 EOD 날짜. 부트스트랩 행(valid_from=2021-01-04)은 재생성 대상이 아니다.
    🔴 캐시 CSV 엔 코드 열이 없으므로 ksic_code·ksic_source·ksic_checked_at 은 jsonl
       보관분으로만 재생성하고, 보관분이 없는 구간은 «보존»한다.
    🔴 DB 쓰기는 전부 sector_writer 를 거친다(reset_map_from·snapshot_map·restore_map).
    🔴 일자별 재구축은 단계마다 커밋된다 — 중간에 터지면 명부가 «잘린 채» 남는다.
       그래서 시작 전에 표 전체를 스냅샷 뜨고, 어디서든 터지면 통째로 되돌린다.

    ⚠️ **재생은 원본 실행과 완전히 같지 않다 — 두 가지가 다르다.**
    ① 원래 5% 급변 가드에 걸렸던 날을 재생하면 그 날 `update_map` 이 다시 RuntimeError 를
       내고 **재생 전체가 롤백**된다. 이건 의도다 — 「그날 왜 걸렸나」를 먼저 조사해야지
       재생이 조용히 통과시키면 안 된다. 조사 후 `--from` 을 그 다음 날로 올려 다시 돈다.
    ② 원래 `written=false` 였던 날(캐시 404 등)도 재생에서는 «7일 후퇴 gz»를 찾아
       **쓴다**. 즉 그날 명부가 원본보다 «더 채워진» 상태가 될 수 있다.
       리포트에 그 날짜 수를 남기고, 소급 라벨이 늘어난다는 점을 판정문에 인쇄한다.
    """
    _guard_window(force)
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT min(valid_from) FROM stock_sector_map WHERE source='eod'")
            first_eod = cur.fetchone()[0]
        if first_eod is None:
            raise RuntimeError("EOD 로 생긴 줄이 없다 — 재생성할 구간이 없다")
        if d_from < first_eod:
            raise RuntimeError("--from 은 첫 EOD 날짜(%s) 이상이어야 한다(부트스트랩 행은 "
                               "gz 가 아니라 stock_industry + 부트스트랩 날 gz 로 재현한다)"
                               % first_eod)
        days = [x for x in _trading_days_between(conn, d_from, now_kst().date())]
        jsonl_days = [x for x in days
                      if os.path.exists(os.path.join(SECTOR_DIR, "dart_company_%s.jsonl" % x))]
        if dry_run:
            return {"from": str(d_from), "days": len(days), "jsonl_days": len(jsonl_days),
                    "dry_run": True}

        snap_rows = w.snapshot_map(conn)
        logger.warning("[sector] 명부 스냅샷 %d행 — 실패하면 이걸로 되돌린다", snap_rows)
        try:
            reset = w.reset_map_from(conn, d_from)
            fetcher = _gz_fetcher()
            replayed = 0
            for iso in days:
                day = date.fromisoformat(iso)
                update_map(conn, day, source="eod", fetcher=fetcher)
                path = os.path.join(SECTOR_DIR, "dart_company_%s.jsonl" % iso)
                if os.path.exists(path):
                    open_rows = w.load_open_rows(conn)
                    resp = []
                    with open(path, encoding="utf-8") as fh:
                        for line in fh:
                            rec = json.loads(line)
                            payload = rec.get("payload") or {}
                            induty = (payload.get("induty_code") or "").strip()
                            # 🔴 열린 줄이 없는 종목은 «건너뛴다» — 재생시 새 행을 만들면
                            #    부수 열이 전부 NULL 인 유령 행이 생긴다(M3).
                            if rec["stock_code"] not in open_rows:
                                continue
                            resp.append({"stock_code": rec["stock_code"],
                                         "ksic_code": induty or None, "recheck": False})
                    if resp:
                        w.apply_ksic_updates(conn, resp, day, create_missing=False)
                        replayed += len(resp)
                recopy_preferred(conn, day)
            w.rebuild_ksic_names(conn)
        except Exception as e:  # noqa: BLE001 — 중간 실패는 «잘린 명부»를 남긴다
            # 🔴 rollback 을 «먼저» — 실패한 문장이 트랜잭션을 abort 상태로 두면
            #    restore 의 DELETE 가 InFailedSqlTransaction 으로 즉시 죽는다.
            conn.rollback()
            restored = w.restore_map(conn)
            logger.error("[sector] 재생성 실패(%s) - 스냅샷 %d행으로 되돌렸다", e, restored)
            raise
        w.drop_map_snapshot(conn)
    out = {"from": str(d_from), "days": len(days), "jsonl_days": len(jsonl_days),
           "deleted": reset["deleted"], "reopened": reset["reopened"],
           "replayed_responses": replayed, "snapshot_rows": snap_rows, "dry_run": False}
    out["report"] = _report("regen_map_report", [
        "명부 재생성", str(out), "",
        "삭제(valid_from >= %s): %d행" % (d_from, reset["deleted"]),
        "다시 연 줄(valid_to >= %s): %d행" % (d_from - timedelta(days=1), reset["reopened"]),
        "jsonl 재생 응답: %d건 (보관분 없는 날의 KSIC 계열은 «보존»)" % replayed,
    ])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--from", dest="d_from", default=None)
    ap.add_argument("--to", dest="d_to", default=None)
    ap.add_argument("--taxonomy", default=None, choices=["ksic2", "ksic3", "ksic5"])
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--regen-map", dest="regen_map", action="store_true")
    ap.add_argument("--delete-stats", dest="delete_stats", action="store_true")
    ap.add_argument("--reconcile-only", dest="reconcile_only", default=None)
    ap.add_argument("--dry-run", dest="dry_run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    def _need(v, name):
        if not v:
            ap.error("%s 가 필요하다" % name)
        return date.fromisoformat(_to_iso(v))

    if args.bootstrap:
        print(bootstrap(_need(args.date, "--date"), args.dry_run, args.force))
    elif args.backfill:
        print(backfill(_need(args.d_from, "--from"), _need(args.d_to, "--to"),
                       args.dry_run, args.force))
    elif args.regen:
        print(regen_stats(_need(args.d_from, "--from"), _need(args.d_to, "--to"),
                          args.taxonomy, args.dry_run, args.force))
    elif args.regen_map:
        print(regen_map(_need(args.d_from, "--from"), args.dry_run, args.force))
    elif args.delete_stats:
        print(delete_stats_cli(_need(args.d_from, "--from"), _need(args.d_to, "--to"),
                               args.taxonomy, args.dry_run, args.force))
    elif args.reconcile_only:
        print(reconcile_sector(args.reconcile_only))
    else:
        print(collect_sector(args.date))
```

- [ ] **Step 8: CLI 가 실제로 파싱되는지 확인한다 (쓰기 0)**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m collectors.sector_collector --help
```
Expected: `--bootstrap` `--backfill` `--regen` `--regen-map` `--delete-stats` `--dry-run` `--force` 가 모두 보인다.

- [ ] **Step 9: 전체 테스트 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_collector.py tests/collectors/test_sector_writer.py tests/collectors/test_sector_reconcile.py -v
```
Expected: 40 + 20 + 16 = 76 passed

- [ ] **Step 10: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): 섹터 CLI — bootstrap·backfill·regen·regen-map·delete-stats·dry-run (Task 10)

평일 15:30~17:00 은 EOD 와 겹치므로 --force 없이는 거부한다. 부트스트랩은
2단계·3b 후 커버리지를 둘 다 재고 하나라도 98% 미만이면 백필로 넘어가지 않고 멈춘다.
백필·부트스트랩은 라이브 3표 행수를 전후로 재서 다르면 즉시 예외를 낸다.
--regen-map 은 보관 gz 를 캐시 CSV 처럼 읽어(네트워크 0) SCD2 를 재생성하고,
jsonl 보관분이 없는 구간의 KSIC 계열은 보존한다. 재생성의 DELETE/UPDATE 도
sector_writer 안에서만 돌고(reset_map_from), 시작 전 표 전체를 스냅샷 떠
중간 실패 시 통째로 되돌린다 — 일자별 재구축은 단계마다 커밋되기 때문이다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/sector_writer.py RoboTrader_template/collectors/sector_collector.py RoboTrader_template/tests/collectors/test_sector_collector.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 11: 오라클 — 태쏘 `SEC-M1` 배선과 대조 (T9)

**Files:**
- Create: `RoboTrader_template/tests/collectors/test_sector_stats_oracle_db.py`

**Interfaces:**
- Consumes: `backtest/tasso_program_journal/run_sector.py`(`load_day`·`labels_for` 정의)·`run_selection.PSEUDO` · `sector_collector.load_day_rows`·`sector_label`·**`compute_day_stats`** · `sector_writer.map_as_of`
- Produces: (테스트만 · 운영 코드 변경 0줄) — 테스트 2개: 오라클 · §3.5 실사례 재현

- [ ] **Step 1: 오라클 테스트를 쓴다**

```python
# tests/collectors/test_sector_stats_oracle_db.py
"""T9 오라클 — 태쏘 SEC-M1 배선(run_sector.load_day + labels_for(N=3))과 대조.

🔴 연구 트리를 «테스트에서만» sys.path 로 끌어온다(운영 코드는 backtest import 0건).
   run_sector 는 패키지가 아니고 형제 모듈 5개와 run_tests.DSN 하드코딩을 끌어온다 —
   그 DSN 은 kis_template@5433 SELECT 전용이라 죽은 DB 가 아니다.
🔴 @pytest.mark.db — 기준선 실패 집합 비교에서 «제외»한다(워크트리 환경 차이).
🔴 허용 차집합 —
   ① market_cap NULL/≤0 (태쏘만 제외 · 이 날짜엔 0건 예상 · 건수를 인쇄한다)
   ② ksic_source IS DISTINCT FROM 'snapshot_20260807' (부모복사·DART 채움 — 우리만 라벨 있음)
   ③ 명부 행이 «아예 없음» — 별도로 재고(그날 «대상 행» 기준 — only_ours 로 재면 라벨이
      명부에서만 오므로 항상 ∅ 인 vacuous 단언이 된다) 인쇄하고 **실패시킨다**(②에 흡수 금지).
   그 밖의 차이가 1건이라도 있으면 실패한다.
🔴 섹터 집계는 «성적표 코드»(compute_day_stats)로 만든다 — 테스트 안에서 median 을
   다시 짜면 집계 버그가 통과한다.
⚠️ 2024-03-12 «이전»은 이 테스트가 재지 않는다 — 시총이 사실상 2024-03-13 부터라
   태쏘 유니버스가 거의 비기 때문이다(§3.2). 그 구간은 「정의만 같다」.
"""
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import date

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # RoboTrader_template
sys.path.insert(0, REPO)
TASSO = os.path.join(REPO, "backtest", "tasso_program_journal")

ORACLE_DATE = date(2026, 8, 5)
# 태쏘 load_day 의 final_pseudo — 실측상 숫자로 시작하지 않는 코드는 이 넷뿐이라
# 우리 SQL_STOCK_ONLY 술어와 «집합으로» 같다.
PSEUDO = ["KOSPI", "KOSDAQ", "KS11", "KQ11"]

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import sector_collector as sc  # noqa: E402
from collectors import sector_writer as w  # noqa: E402

# 🔴 마커만 모듈 수준. importorskip·DB 프로브를 여기 두면 «수집 단계»에 돌아
#    `-m "not db"` 로도 못 막고, ImportError 가 아닌 예외(psycopg2.OperationalError 등)는
#    skip 이 아니라 ERROR 로 기준선 실패 집합에 들어간다.
pytestmark = [pytest.mark.db]


def _load_tasso():
    """run_sector 를 «테스트 실행 시점»에 끌어온다. 무엇이 터지든 skip 이다.

    🔴 sys.path 조작도 여기서 한다 — 모듈 최상위에 두면 이 파일이 «수집되기만» 해도
       연구 트리가 다른 테스트의 import 경로에 끼어든다(형제 모듈 이름 충돌 위험).
    """
    if not os.path.isdir(TASSO):
        pytest.skip("태쏘 트리가 없다 - 오라클 생략")
    if TASSO not in sys.path:
        sys.path.insert(0, TASSO)
    try:
        import run_sector as rs
        import run_selection as rsel
    except Exception as e:  # noqa: BLE001 — 형제 모듈 5개를 끌어온다
        pytest.skip("태쏘 run_sector import 실패: %s" % e)
    return rs, rsel


def _connect():
    try:
        cm = KisDbConnection.get_connection()
        c = cm.__enter__()
        with c.cursor() as cur:
            cur.execute("SELECT 1")
        return cm, c
    except Exception as e:  # noqa: BLE001
        pytest.skip("kis_template DB 접속 불가: %s" % e)


def test_oracle_matches_tasso_sec_m1():
    run_sector, run_selection = _load_tasso()
    # 경미 7 — PSEUDO 하드코딩이 태쏘 동결값과 갈리면 «인쇄»하고 태쏘 값을 쓴다
    tasso_pseudo = list(getattr(run_selection, "PSEUDO", []) or [])
    if tasso_pseudo and set(tasso_pseudo) != set(PSEUDO):
        print("[T9] ⚠️ PSEUDO 불일치 — 우리 %s vs 태쏘 %s (태쏘 값을 쓴다)"
              % (sorted(PSEUDO), sorted(tasso_pseudo)))
    pseudo = tasso_pseudo or PSEUDO
    cm, conn = _connect()
    try:
        mp = dict((r[0], (r[1], r[2])) for r in w.map_as_of(conn, ORACLE_DATE))
        if not mp:
            pytest.skip("stock_sector_map 이 비어 있다 - 부트스트랩 전")

        # ── 우리 계산 — 🔴 «성적표 코드 그 자체»(compute_day_stats)로 만든다.
        #    테스트 안에서 median 을 다시 짜면 집계 버그가 통과한다(M1).
        rows = sc.load_day_rows(conn, ORACLE_DATE)
        labels = dict((c, v[0]) for c, v in mp.items())
        stat_rows, undefined = sc.compute_day_stats(rows, labels)
        ob = dict((r["sector_key"], r) for r in stat_rows if r["taxonomy"] == "ksic3")

        ours_all = {}
        for code, high, close, prev in rows:
            if prev is None or float(prev) <= 0 or close is None:
                continue
            ours_all[code] = float(close) / float(prev) - 1.0
        our_lbl = dict((c, sc.sector_label(labels.get(c), 3)) for c in ours_all)
        ours = dict((c, v) for c, v in ours_all.items() if our_lbl.get(c))

        # ── 태쏘 계산 (동결 함수를 «그대로» 호출) ────────────────────
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, induty_code FROM stock_industry "
                        "WHERE induty_code IS NOT NULL AND induty_code <> ''")
            sec = dict(cur.fetchall())
            rec = run_sector.load_day(cur, ORACLE_DATE.isoformat(), sec, pseudo)
        their_r = dict((c, float(v)) for c, v in zip(rec["joined"], list(rec["r"]))
                       if math.isfinite(float(v)))
        their_lbl = dict((c, (sec[c][:3] if len(sec.get(c) or "") >= 3 else None))
                         for c in their_r)
        theirs = dict((c, v) for c, v in their_r.items() if their_lbl.get(c))

        # ── 허용 차집합 ①② ──────────────────────────────────────────
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code FROM daily_prices WHERE date=%s "
                        "AND (market_cap IS NULL OR market_cap <= 0)",
                        (ORACLE_DATE.isoformat(),))
            no_mcap = set(r[0] for r in cur.fetchall())

        only_ours = set(ours) - set(theirs)
        only_theirs = set(theirs) - set(ours)
        class1 = only_ours & no_mcap
        class2 = set(c for c in only_ours if mp[c][1] != "snapshot_20260807")
        residual = only_ours - class1 - class2
        both = set(ours) & set(theirs)
        # 🔴 「명부 행이 아예 없음」은 «라벨 비교»가 아니라 «그날 대상 행» 기준으로 잰다 —
        #    only_ours 로 재면 라벨이 mp 에서만 오므로 «항상 ∅»인 vacuous 단언이 된다.
        #    이건 커버리지 결손의 직접 신호이고 undefined["no_label"] 과 같은 뿌리다.
        no_map_rows = set(ours_all) - set(mp)

        print("[T9] 교집합=%d · only_ours=%d (①market_cap %d · ②우리만 라벨 %d · 잔여 %d) "
              "· only_theirs=%d · ③명부행 없음(그날 대상 기준)=%d · 미정=%s"
              % (len(both), len(only_ours), len(class1), len(class2), len(residual),
                 len(only_theirs), len(no_map_rows), undefined))

        assert only_theirs == set(), "태쏘에만 있는 종목이 있다: %s" % sorted(only_theirs)[:10]
        assert no_map_rows == set(), \
            "그날 대상 행인데 명부에 열린 줄이 «아예 없는» 종목: %s" % sorted(no_map_rows)[:10]
        assert undefined["no_label"] == len(
            [c for c in ours_all if w.is_blank(labels.get(c))]), \
            "no_label 집계가 실제 «라벨 없음» 수와 다르다(무징후 절단 감지)"
        assert residual == set(), "허용 밖 차이: %s" % sorted(residual)[:10]

        # 교집합 종목의 r·ksic3 완전 일치
        for c in sorted(both):
            assert abs(ours[c] - theirs[c]) < 1e-12, \
                "%s r 불일치 %r vs %r" % (c, ours[c], theirs[c])
            assert our_lbl[c] == their_lbl[c], \
                "%s 라벨 불일치 %r vs %r" % (c, our_lbl[c], their_lbl[c])

        # ② 종목이 없는 업종의 ret_median·n_members 일치 · G 차이는 ②로만 생긴 업종
        members = defaultdict(set)
        tb = defaultdict(list)
        for c in ours:
            members[our_lbl[c]].add(c)
        for c, v in theirs.items():
            tb[their_lbl[c]].append(v)
        extra = class1 | class2
        for k in sorted(set(ob) & set(tb)):
            if members[k] & extra:
                continue
            assert ob[k]["n_members"] == len(tb[k]), \
                "%s n_members 불일치 %d vs %d" % (k, ob[k]["n_members"], len(tb[k]))
            assert abs(ob[k]["ret_median"] - statistics.median(tb[k])) < 1e-12, \
                "%s ret_median 불일치 %r vs %r" % (k, ob[k]["ret_median"],
                                                  statistics.median(tb[k]))
        only_our_sectors = set(ob) - set(tb)
        for k in sorted(only_our_sectors):
            assert members[k] <= extra, "우리만 있는 업종 %s 가 허용 차집합에서 오지 않았다" % k
        print("[T9] G ours=%d · theirs=%d · 우리만 있는 업종=%d(전부 ②)"
              % (len(ob), len(tb), len(only_our_sectors)))
    finally:
        cm.__exit__(None, None, None)


# §3.5 실사례 — critic 2차가 독립 재현해 일치를 확인한 5행(2026-08-05 · ksic3 · G=159).
# 🔴 라벨은 «명부»가 아니라 stock_industry 다 — 실사례를 그렇게 계산했기 때문이다.
EXPECTED_20260805 = {
    #        n    ret_median(%)  up  pos_ratio  rank  pct
    "261": (71,   5.670,         11, 0.930,     1,    99.4),
    "311": (13,   5.029,         0,  0.923,     5,    96.8),
    "264": (60,   4.053,         10, 0.867,     7,    95.6),
    "641": (5,    0.998,         0,  0.600,     84,   46.8),
    "212": (103,  0.494,         2,  0.689,     112,  29.1),
}


def test_stats_reproduce_spec_worked_example():
    """§3.5 실사례 5행을 «성적표 코드»로 재현한다 — 집계·순위·백분위를 한 번에 고정한다.

    🔑 오라클(위)은 «종목별 r·라벨»을 재고, 이 테스트는 «섹터 집계»를 잰다.
       둘을 갈라 놓지 않으면 집계 버그가 종목 대조를 통과해 지나간다.

    🔴 **이 테스트는 «동결 데이터 오라클»이다** — 라이브 `daily_prices` 의
       2026-08-05 ±20일 구간과 `stock_industry` 스냅샷에 값이 묶여 있다.
       그 데이터가 바뀌면 코드가 옳아도 깨진다. 알려진 예정 작업 둘이 정확히 그렇다:
         · 일봉 결손 49,252행 복구(원인 수정 c6dc77c · 복구 미착수)
         · `adj_factor` 보정 도구 `--apply`
       깨지면 **먼저 데이터 변경 여부를 확인하고**, 데이터가 바뀐 것이면 기대값을
       재계산해 갱신한다(코드를 고치지 말 것). 완료 리포트에도 같은 문장을 적는다.
    """
    cm, conn = _connect()
    try:
        rows = sc.load_day_rows(conn, ORACLE_DATE)
        if not rows:
            pytest.skip("2026-08-05 일봉이 없다")
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, induty_code FROM stock_industry "
                        "WHERE induty_code IS NOT NULL AND induty_code <> ''")
            labels = dict(cur.fetchall())
    finally:
        cm.__exit__(None, None, None)

    stat_rows, undefined = sc.compute_day_stats(rows, labels)
    got = dict((r["sector_key"], r) for r in stat_rows if r["taxonomy"] == "ksic3")
    print("[T9-b] 대상 행=%d · G(ksic3)=%d · 미정=%s" % (len(rows), len(got), undefined))
    assert len(got) == 159, "G(ksic3) 가 실사례(159)와 다르다: %d" % len(got)
    for key, (n, med_pct, up, pos, rank, pct) in sorted(EXPECTED_20260805.items()):
        r = got.get(key)
        assert r is not None, "%s 업종이 없다" % key
        assert r["n_members"] == n, "%s n_members %d != %d" % (key, r["n_members"], n)
        assert abs(r["ret_median"] * 100.0 - med_pct) <= 0.001, \
            "%s ret_median %.5f%% != %.3f%%" % (key, r["ret_median"] * 100.0, med_pct)
        assert r["up_count"] == up, "%s up_count %d != %d" % (key, r["up_count"], up)
        assert abs(r["pos_ratio"] - pos) <= 0.0005, \
            "%s pos_ratio %.4f != %.3f" % (key, r["pos_ratio"], pos)
        assert r["rank_median"] == rank, "%s rank %d != %d" % (key, r["rank_median"], rank)
        assert abs(r["pct_median"] - pct) <= 0.05, \
            "%s pct %.2f != %.1f" % (key, r["pct_median"], pct)
        assert r["g_sectors"] == 159
```

- [ ] **Step 2: 실행한다 (부트스트랩 «전»이면 skip 이 정상)**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_stats_oracle_db.py -v -s
```
Expected(지금): `2 skipped` — `stock_sector_map 이 비어 있다 - 부트스트랩 전`
(§3.5 재현 테스트는 `stock_industry` 를 쓰므로 부트스트랩 전에도 **돈다** — 일봉만 있으면 `1 passed 1 skipped`)
Expected(Task 14 부트스트랩 «후» 재실행): `2 passed` + `[T9] …` · `[T9-b] …` 인쇄

- [ ] **Step 3: import 경로가 실제로 뚫리는지 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -c "import sys,os; sys.path.insert(0,'.'); sys.path.insert(0, os.path.join('backtest','tasso_program_journal')); import run_sector, run_selection; print('load_day', callable(run_sector.load_day)); print('UP_MULT', run_sector.UP_MULT); print('NS', run_sector.NS); print('PSEUDO', getattr(run_selection, 'PSEUDO', None))"
```
Expected: `load_day True` · `UP_MULT 1.15` · `NS (2, 3, 5)` · `PSEUDO` 값 인쇄
🔴 여기서 실패하면 T9 는 skip 으로 남는다(운영 코드는 영향 없음) — 사유를 완료 리포트에 적을 것.

- [ ] **Step 4: 🔴 «게이트가 쓰는» 인터프리터에서 수집이 깨끗한지 확인한다 (M2)**

Step 2·3 은 venv 파이썬인데 회귀 게이트는 **VS 번들 파이썬**으로 돈다. 수집 단계에서
이 파일이 ERROR 를 내면 기준선 실패 집합에 «새 항목»이 생겨 머지가 막힌다.

Run:
```
cd D:/tmp/kis-wt-sector
PYTHONUTF8=1 "C:/Program Files (x86)/Microsoft Visual Studio/Shared/Python39_64/python.exe" -m pytest RoboTrader_template/tests/collectors/test_sector_stats_oracle_db.py --collect-only -q
PYTHONUTF8=1 "C:/Program Files (x86)/Microsoft Visual Studio/Shared/Python39_64/python.exe" -m pytest RoboTrader_template/tests/collectors/test_sector_stats_oracle_db.py -q -m "not db"
```
Expected: 첫 명령 `2 tests collected` · **errors 0** · 둘째 명령 `2 deselected`
(수집 시점에 `run_sector` 를 import 하지 않기 때문에 태쏘 트리·DB 와 무관하게 깨끗해야 한다)

- [ ] **Step 5: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
test(collectors): T9 오라클 + §3.5 실사례 재현 — 태쏘 SEC-M1 배선 대조 (Task 11)

허용 차집합은 셋 — ①market_cap NULL/≤0(태쏘만 제외) ②우리만 라벨이 있는 종목
(부모복사·DART 채움) ③명부 행이 아예 없음(별도로 인쇄하고 실패시킨다).
비교는 테스트 안에서 다시 짠 median 이 아니라 compute_day_stats 출력으로 한다 —
재집계하면 집계 버그가 종목 대조를 통과해 지나간다.
run_sector import 는 «테스트 함수 안»이다: 수집 단계에서 돌면 -m "not db" 로 못 막고
ImportError 가 아닌 예외가 기준선 실패 집합에 ERROR 로 들어간다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/tests/collectors/test_sector_stats_oracle_db.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 12: EOD 배선 — `financials_reconcile` 바로 뒤 2줄 (T10)

**Files:**
- Modify: `RoboTrader_template/collectors/eod_collection.py` — **import 1줄(25번 줄 뒤) + 단계 2줄(58번 줄 뒤)**
- Modify: `RoboTrader_template/tests/collectors/test_eod_collection.py` — `_stub_flow_stages`(26~29번 줄) + T10 테스트 3개 추가

**Interfaces:**
- Consumes: `collectors.sector_collector.collect_sector`·`reconcile_sector`
- Produces: `run_data_collection` 반환 dict 에 `"sector"`·`"sector_reconcile"` 키

- [ ] **Step 1: T10 테스트를 쓴다 (실패)**

`tests/collectors/test_eod_collection.py` 의 `_stub_flow_stages` 목록에 두 이름을 추가한다(26~29번 줄 · 실측):

```python
    for nm in ("collect_investor_trend", "collect_program_trade", "collect_short_sale",
               "collect_credit_balance", "collect_overtime",
               "collect_financials", "reconcile_financials",
               "collect_sector", "reconcile_sector"):
        monkeypatch.setattr(eod, nm, lambda d=None: {"skipped": True})
```

파일 끝에 추가:

```python
def test_run_data_collection_actually_calls_sector(monkeypatch):
    """🔑 소스 문자열 단언은 죽은 경로에서도 통과한 전례가 있다(9b82eec·8238f91).
    배선은 «실제로 돌려서» 단언한다."""
    from collectors import eod_collection as eod_mod
    called = []
    for name in ("collect_daily", "collect_minute", "collect_index",
                 "collect_stock_market", "collect_foreign_flow", "collect_corp_events"):
        monkeypatch.setattr(eod_mod, name, lambda *a, _n=name: called.append(_n) or {})
    monkeypatch.setattr(eod_mod, "reset_market_cache", lambda: None)
    monkeypatch.setattr(eod_mod, "collect_financials",
                        lambda *a: called.append("collect_financials") or {})
    monkeypatch.setattr(eod_mod, "reconcile_financials",
                        lambda *a: called.append("reconcile_financials") or {})
    monkeypatch.setattr(eod_mod, "collect_sector",
                        lambda *a: called.append("collect_sector") or {"map": {"written": True}})
    monkeypatch.setattr(eod_mod, "reconcile_sector",
                        lambda *a: called.append("reconcile_sector") or {"verdict": "PASS"})

    out = eod_mod.run_data_collection("2026-09-07")
    assert "sector" in out and "sector_reconcile" in out
    # 자리: financials_reconcile «바로 뒤» — 재무가 먼저 쓰게 한다(재무는 020 한 건에도 FAIL)
    assert called.index("collect_sector") > called.index("reconcile_financials")
    assert called.index("reconcile_sector") > called.index("collect_sector")
    # 계약 불변
    assert out["reconcile"] == {}


def test_sector_stage_exception_is_isolated(monkeypatch):
    """(단계격리) 섹터 수집 실패가 reconcile·다른 단계·EOD 흐름을 막지 않는다."""
    monkeypatch.setattr(eod, "collect_daily", lambda d=None: {"rows": 1})
    monkeypatch.setattr(eod, "collect_minute", lambda d=None: {"rows": 2})
    monkeypatch.setattr(eod, "collect_index", lambda s=None: {"KOSPI": 1})
    monkeypatch.setattr(eod, "collect_stock_market", lambda: {"KOSPI": 1, "KOSDAQ": 1})
    monkeypatch.setattr(eod, "collect_foreign_flow", lambda d=None: {"rows": 3})
    monkeypatch.setattr(eod, "collect_corp_events", lambda d=None: {"rows": 4})
    monkeypatch.setattr(eod, "collect_sector",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("github down")))
    recon = []
    monkeypatch.setattr(eod, "reconcile_sector",
                        lambda *a: recon.append(1) or {"verdict": "WARN"})
    out = eod.run_data_collection("20260623")
    assert "error" in out["sector"]
    assert recon == [1], "섹터 수집이 실패해도 reconcile 은 계속 돌아야 한다"
    assert out["daily"] == {"rows": 1}


def test_sector_stage_count_is_exactly_two_lines():
    """스펙 §10 — eod_collection.py 변경은 «2줄»(+import 1줄)이다.
    롤백은 이 두 줄을 지우는 것으로 끝나야 한다."""
    import inspect
    src = inspect.getsource(eod.run_data_collection)
    assert src.count("collect_sector") == 1 and src.count("reconcile_sector") == 1
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_eod_collection.py -v
```
Expected: FAIL — `AttributeError: <module 'collectors.eod_collection'> does not have the attribute 'collect_sector'`

- [ ] **Step 3: EOD 에 배선한다 (import 1줄 + 단계 2줄)**

`collectors/eod_collection.py` 25번 줄 «뒤»에:

```python
from collectors.sector_collector import collect_sector, reconcile_sector  # noqa: E402
```

58번 줄(`"financials_reconcile": _safe(reconcile_financials, trade_date),`) «뒤»에:

```python
        # 섹터 — financials_reconcile 바로 뒤. opendart 네트워크의 마지막 소비자는
        # collect_financials 이고 reconcile_financials 는 DB 만 읽는다. 재무는 020 한 건에도
        # 도달성 FAIL(엄격)이라 «재무가 먼저 쓰게» 뒤에 둔다. 뒤따르는 수급 5단계는 DART 참조 0.
        "sector": _safe(collect_sector, trade_date),
        "sector_reconcile": _safe(reconcile_sector, trade_date),
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_eod_collection.py -v
```
Expected: 13 passed (기존 10 + 신규 3)

- [ ] **Step 5: 라이브 계약이 안 깨졌는지 확인한다**

Run:
```
cd D:/tmp/kis-wt-sector
git diff --stat RoboTrader_template/collectors/eod_collection.py
```
Expected: `1 file changed, 6 insertions(+)` (import 1 + 주석 3 + 단계 2) · 삭제 0줄

- [ ] **Step 6: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
feat(collectors): EOD 에 섹터 수집·판정 등록 — financials_reconcile 바로 뒤 (Task 12)

opendart 네트워크의 마지막 소비자는 collect_financials 이고 reconcile_financials 는
DB 만 읽는다. 재무는 020 한 건에도 도달성 FAIL(엄격)이라 재무가 먼저 쓰게 뒤에 둔다.
뒤따르는 수급 5단계는 DART 참조가 0이다. 롤백은 이 두 줄을 지우는 것으로 끝난다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add RoboTrader_template/collectors/eod_collection.py RoboTrader_template/tests/collectors/test_eod_collection.py && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 13: 문서 — 표 목록 · 쉬운 한 장 · 리포트 자리 설명 (§11-6)

**Files:**
- Modify: `RoboTrader_template/docs/DB통합_쉬운설명.md` (§9 「지금 상태 한눈에」 바로 «앞»에 소절 추가)
- Create: `RoboTrader_template/docs/섹터데이터_쉬운설명_2026-09-06.md`
- Modify: `RoboTrader_template/docs/superpowers/specs/2026-09-06-sector-data-design.md` (§6.0·§6.2 — **실행 «후»** Task 14 에서 채운다)

**Interfaces:**
- Consumes: Task 1~12 의 산출물
- Produces: 문서 3건(코드 0줄)

- [ ] **Step 1: `DB통합_쉬운설명.md` 에 신규 표 목록을 넣는다**

`## 9. 지금 상태 한눈에` 줄 «바로 앞»에 삽입:

```markdown
## 8-1. 2026-09 신규 — 섹터 표 4개 (`kis_template`)

| 표 | 무엇이 들어 있나 | 누가 채우나 |
|---|---|---|
| `stock_sector_map` | 종목 → 업종(KSIC) **명부**. 한 줄 = 종목 × 유효기간이라 «그날 업종»을 물어볼 수 있다 | EOD 매일 (`sector_collector`) |
| `sector_daily_stats` | 업종 **일별 성적표**(중앙 수익률·급등 수·상승 비율 + 그날 업종들 사이의 백분위) | EOD 매일 |
| `ksic_code_name` | KSIC 3자리 **이름표**(코드 → 이름). 표시 전용이고 매일 다시 만든다 | EOD 매일 |
| `sector_ksic_nodata` | DART 가 「업종 없음」이라고 답한 종목 — 30일 뒤 다시 물어보려고 적어 둔다 | EOD 매일 |

읽는 법: 「그날 이 종목이 무슨 업종이었나」는 `fn_sector_map_as_of(날짜)` 로 묻는다.
「그 업종이 그날 같이 눌렸나」는 `sector_daily_stats` 의 `pct_median` 을 본다
(백분위가 낮을수록 그날 업종이 나빴다는 뜻이다).

⚠️ 2021-01-04 ~ 구축일 구간의 업종 라벨은 **지금 명부를 과거에 끼워 넣은 것**(소급)이다.
그 구간으로 판정하는 문서는 이 문장을 같이 인쇄해야 한다.
```

- [ ] **Step 2: 쉬운 한 장을 쓴다**

`docs/섹터데이터_쉬운설명_2026-09-06.md` — 아래 골자를 채운다(사장님 보고용 · 숫자는 **실행 후** Task 14 의 리포트에서 그대로 옮긴다):

```markdown
# 섹터 데이터 — 쉬운 설명 (2026-09-06)

## 한 줄 요약
「이 종목은 무슨 업종인가」와 「그 업종이 그날 어땠나」를 매일 자동으로 쌓는다.
매매 규칙은 **한 줄도 안 바뀐다.**

## 왜 필요했나
지금 섹터 데이터가 넷 있는데 **넷 다 쓸 수 없었다.**
- `stock_industry`: 코드만 있고 **날짜가 없다** — 오늘 업종을 과거에 끼워 넣게 된다
- `stock_sector`(KRX 79업종): **갱신 소스가 없다**(그 뒤 편입 98종목이 빠져 있다)
- `sector_index_daily`: 2026-02 정지 · 종목과 이어 붙일 매핑이 0
- `stock_info.sector`: 전부 빈 문자열

## 무엇을 만들었나 (표 4개 + 함수 1개)
1. **명부** — 종목 × 유효기간. 업종이 바뀌면 옛 줄을 닫고 새 줄을 연다.
2. **성적표** — 업종별 그날 중앙 수익률·급등 수·상승 비율 + 업종들 사이 백분위.
3. **이름표** — 코드에 사람이 읽는 이름을 붙인다(표시 전용).
4. **「업종 없음」 기록** — 30일 뒤 다시 물어보려고 적어 둔다.

## 어디서 가져오나 (KIS 호출 0)
- 이름·시장: GitHub 에 매일 올라오는 **상장목록 캐시 CSV** 한 개(하루 1회)
- 업종 코드: **DART `company.json`**, 하루 300건 이하
- 수익률: 우리 **일봉**(daily_prices) — 읽기만 한다

## 조심한 것 세 가지
1. **「값 없음」은 「바뀜」이 아니다.** 소스가 하루 비어도 이력이 갈라지면 안 된다.
2. **하루에 5% 넘게 바뀌면 한 줄도 안 쓴다.** 소스가 통째로 뒤집힌 날을 막는다.
3. **코드가 한 번 쓰고 굳지 않게** 매일 200종목씩 다시 물어본다(13~14 거래일에 한 바퀴).

## 지금 상태
- 커버리지: (Task 14 부트스트랩 리포트 값) — 목표 98% 이상
- 성적표: 2021-01-04 ~ 어제, (백필 리포트 값)행
- 매일 16:00 EOD 에서 자동 갱신 · 건강 판정은 `collection_reconciliation` 의 `sector` 줄

## 🔴 꼭 같이 읽어야 하는 문장 두 개
- 2021-01-04 ~ 구축일의 업종 라벨은 **현재 명부의 소급**이다.
- **2024-03-12 이전 성적표는 태쏘 SEC-M1 과 대조되지 않았다**(시총이 그때부터라
  비교 대상이 거의 비었다). 정의만 같다.
```

- [ ] **Step 3: 스펙 리포트 자리에 「무엇을 채울지」를 못박는다**

스펙 §6.0-5·§6.2 의 리포트 항목은 **실행 후** 아래 값으로 대체한다(Task 14 Step 7).

| 스펙 자리 | 채울 값 | 출처 |
|---|---|---|
| §6.0-2 「이 시점 도달 커버리지 = 95.5%」 | `steps.coverage_after_2` 실측 | `bootstrap_report_*.txt` |
| §6.0-3 「예상 125」 | `ksic_fill.fill_targets` 실측 | 〃 |
| §6.0-3b 「기대치 2,772/2,772」 | `steps.coverage_after_3b` 실측 | 〃 |
| §6.0-5 「DART 125 응답 실측(000/013/nodata)」 | `ksic_fill.status_counts` + `nodata` | 〃 |
| §6.0-5 「이름표 코드 수·점유율<0.8」 | `names.codes` · `names.low_share` | 〃 |
| §6.2 「약 76만 행 · 예상 수 분」 | `rows` · `elapsed_sec` 실측 | `backfill_report_*.txt` |
| §6.2 「1,391일」 | `days_with_rows` 실측 | 〃 |

- [ ] **Step 4: 커밋**

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
docs(sector): DB 통합 쉬운설명에 섹터 표 4개 추가 + 쉬운 한 장 (Task 13)

「그날 업종」은 fn_sector_map_as_of(날짜), 「그 업종이 그날 어땠나」는
sector_daily_stats.pct_median 으로 묻는다는 읽는 법을 같이 적었다.
소급 문장과 「2024-03-12 이전은 태쏘와 미대조」 문장은 두 문서 모두에 넣었다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add "RoboTrader_template/docs/DB통합_쉬운설명.md" "RoboTrader_template/docs/섹터데이터_쉬운설명_2026-09-06.md" && git commit -F D:/tmp/sector_commit_msg.txt
```

---

### Task 14: 부트스트랩 · 백필 실행 + 완료 판정 (§6.0 · §6.2 · §11)

> 🔴 **이 태스크는 사장님 승인 «후» 야간/주말에만 실행한다.** 평일 15:30~17:00 은 코드가 거부한다.
> 🔴 실행 위치는 **워크트리**(`D:/tmp/kis-wt-sector`)다 — 머지 «전»이다.
> 🔴 `--dry-run` 을 먼저 돌려 리포트만 보고 사장님께 보고한 뒤 본 실행한다.

**Files:**
- Modify: `RoboTrader_template/docs/superpowers/specs/2026-09-06-sector-data-design.md` (§6.0·§6.2 실측 갱신)

**Interfaces:**
- Consumes: Task 1~13 전부
- Produces: `scratchpad/sector/bootstrap_report_*.txt` · `backfill_report_*.txt` · 완료 판정 근거

- [ ] **Step 1: 전체 스위트 회귀 판정 (머지 전 필수)**

Run:
```
cd D:/tmp/kis-wt-sector
PYTHONUTF8=1 "C:/Program Files (x86)/Microsoft Visual Studio/Shared/Python39_64/python.exe" -m pytest -q --tb=line -m "not db" > D:/tmp/sector_after_raw.txt 2>&1
grep -E "^(FAILED|ERROR)" D:/tmp/sector_after_raw.txt | sort > D:/tmp/sector_after_failures.txt
diff D:/tmp/sector_baseline_failures.txt D:/tmp/sector_after_failures.txt
```
Expected: `diff` 출력 **없음**(양방향 차분 0). 다르면 그 줄이 회귀다 — 고치기 전엔 다음 단계로 가지 않는다.

- [ ] **Step 2: 부트스트랩 dry-run (쓰기 0 · DART 0)**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m collectors.sector_collector --bootstrap --date 2026-09-13 --dry-run
```
Expected: `matched` ≈ 2,760±20 · `snapshot_hits` ≈ 2,533 · `would_dart_calls` ≈ 125 · `live_before == live_after` · 리포트 파일 경로 출력

- [ ] **Step 3: 사장님 승인 후 부트스트랩 본 실행**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m collectors.sector_collector --bootstrap --date 2026-09-13
```
Expected:
- `coverage_after_2` ≈ `{"ksic_code": 0.955, "ksic3_name": 0.99x}` (아직 98% 아님 — **정상**)
- `coverage_after_3b` ≈ `{"ksic_code": 1.0, "ksic3_name": 0.9975}` — **둘 다 ≥ 0.98 이라야 통과**
- 게이트 미달이면 `RuntimeError` 로 멈춘다 → **백필로 넘어가지 말고 사장님께 보고**
- `live_before == live_after` (라이브 3표 불변)
- 리포트: `RoboTrader_template/scratchpad/sector/bootstrap_report_*.txt`

- [ ] **Step 4: 오라클(T9)을 «부트스트랩 후» 다시 돌린다**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m pytest tests/collectors/test_sector_stats_oracle_db.py -v -s
```
Expected: `1 passed` · `[T9] 교집합=… only_ours=… (①market_cap 0 · ②우리만 라벨 …)` 인쇄
🔴 `잔여` 가 0 이 아니면 실패다 — 원인을 찾기 전에는 백필하지 않는다. 인쇄된 ①②건수를 완료 리포트에 옮긴다.

- [ ] **Step 5: 백필 dry-run → 본 실행 (야간/주말)**

Run:
```
cd D:/tmp/kis-wt-sector/RoboTrader_template
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m collectors.sector_collector --backfill --from 2021-01-04 --to 2026-09-12 --dry-run
PYTHONUTF8=1 "D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe" -m collectors.sector_collector --backfill --from 2021-01-04 --to 2026-09-12
```
Expected:
- `days` ≈ 1,392 · `days_with_rows` ≈ **1,391**(첫날 2021-01-04 은 창 안에 직전 봉이 없어 비는 게 정상)
- `rows` ≈ **76만**(일자당 ksic2 ~61 + ksic3 ~159 + ksic5 ~327 ≈ 550)
- `elapsed_sec` **수 분 ~ 15분**(집계는 순수 파이썬 · 병목은 일자별 20일 창 SQL)
  — ⚠️ **추정치다**(실측 근거 없음). 15분을 넘기면 창 SQL 을 한 번에 읽는 방식으로 바꾸고
  **다시 돌린다**(집계 코드는 불변). 이 실행의 `elapsed_sec` 가 스펙 §6.2 의 첫 실측이 된다.
- `live_before == live_after` — 다르면 코드가 예외를 낸다
- 리포트: `scratchpad/sector/backfill_report_*.txt` (일자별 G 분포 · 미정 분포 · 소급 문장 2개 포함)

- [ ] **Step 6: DB 로 완료 판정을 직접 재본다 (SELECT 만)**

🔴 **날짜 범위를 반드시 `--to` 날짜로 자른다** — 안 자르면 백필 뒤 EOD 가 `daily_prices` 를
늘리는 순간 `stats_days = daily_days − 1` 이 «거짓»이 되고, 그 거짓이 완료 판정을 흔든다.

Run (psql · SELECT 만 · `<TO>` 는 백필 `--to` 날짜):
```
export PGCLIENTENCODING=UTF8
PGPASSWORD=1234 "C:/Program Files/PostgreSQL/16/bin/psql.exe" -h 127.0.0.1 -p 5433 -U robotrader -d kis_template -A -F"|" -c "SELECT (SELECT count(DISTINCT date) FROM sector_daily_stats WHERE date <= '<TO>') AS stats_days, (SELECT count(DISTINCT date) FROM daily_prices WHERE date <= '<TO>') AS daily_days, (SELECT count(*) FROM stock_sector_map WHERE valid_to IS NULL) AS open_rows, (SELECT count(*) FROM stock_sector_map WHERE valid_to IS NULL AND ksic_code IS NOT NULL) AS ksic_nonnull, (SELECT count(*) FROM ksic_code_name) AS names, (SELECT count(*) FROM (SELECT stock_code FROM fn_sector_map_as_of(current_date) GROUP BY 1 HAVING count(*)>1) t) AS dups"
```
Expected: `stats_days` = `daily_days` − 1 · `names` ≥ 155 · `dups` = **0**
(예: `--to 2026-09-12` 면 `<TO>` = `2026-09-12` · `daily_prices.date` 는 TEXT 라 문자열 비교다)

- [ ] **Step 7: 스펙 §6.0·§6.2 를 실측치로 갱신하고 커밋한다**

Task 13 Step 3 의 표대로 스펙의 예상치를 실측치로 바꾼다(예상과 다르면 **차이도 같이 적는다** — 「예상 125 → 실측 N」).

```
cat > D:/tmp/sector_commit_msg.txt <<'MSG'
docs(spec): 섹터 데이터 §6.0·§6.2 를 부트스트랩·백필 실측치로 갱신 (Task 14)

부트스트랩 2단계/3b 커버리지 · DART 응답 분포 · 이름표 코드 수 · 백필 행수와 소요를
실행 리포트 값으로 대체했다. 예상과 다른 항목은 「예상 → 실측」 형태로 남겼다.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSwgjrUPkDvXTgYo9NXXwy
MSG
cd D:/tmp/kis-wt-sector && git add "RoboTrader_template/docs/superpowers/specs/2026-09-06-sector-data-design.md" && git commit -F D:/tmp/sector_commit_msg.txt
```

- [ ] **Step 8: 완료 판정 6항목을 표로 정리해 사장님께 보고한다 (§11)**

| # | 판정 | 근거 |
|---|---|---|
| 1 | T1~T14 통과 + 스위트 실패 집합 동일 | Step 1 의 `diff` 무출력 · 각 태스크의 pytest 출력 |
| 2 | 부트스트랩 게이트 ≥ 98% (3단계 «후») | `bootstrap_report_*.txt` · 미라벨 목록 · DART 응답 실측 · 이름표 ≥ 155 · 점유율<0.8 0건 |
| 3 | 백필 날짜 수 = 일봉 고유 날짜 − 1 | `backfill_report_*.txt` + Step 6 실측 · 소급 문장 2개 포함 확인 |
| 4 | 오라클 T9 실 DB 통과 | Step 4 인쇄(교집합·①②건수) |
| 5 | 머지 후 다음 거래일 EOD 에서 `dataset='sector'` **PASS** 관측 | 첫날 허용 WARN 은 셋뿐 — §8-7(주말 `source_asof`)·§8-3(신규상장 소수)·「이력 부족」 |
| 6 | 문서 4건 | 스펙 갱신 · `DB통합_쉬운설명.md` · 쉬운 한 장 · changelog(메모리 측 — 레포 밖) |
| 7 | **알려진 한계 4가지를 완료 리포트에 그대로 옮겼다** | 부록 E — regen-map 재현 한계 2 · T9-b 동결 데이터 오라클 · 백필 15분은 추정 · dry-run 커버리지는 예측(과대 가능) |

- [ ] **Step 9: 머지는 EOD «이후»에 · 발효 확인**

```
cd D:/GIT/kis-trading-template
git merge --no-ff feat/sector-data
```
- 머지 시각: **16:00 EOD 이후**(라이브 트리 장중 브랜치 전환 금지).
- 발효: 다음 **07:40 재기동** 뒤 첫 16:00 EOD 가 첫 «유지» 실행이다(부트스트랩·백필은 이미 끝나 있다).
- 다음 거래일 EOD 후 관측:

```
SELECT trade_date, real_rows, new_rows, overlap, coverage, value_match_rate, verdict
FROM collection_reconciliation WHERE dataset='sector' ORDER BY trade_date DESC LIMIT 3;
```
Expected: `verdict='PASS'`(또는 위 3종 WARN 중 하나) · `real_rows` ≈ 550 · `coverage` ≥ 0.98

- [ ] **Step 10: 워크트리 정리**

```
cd D:/GIT/kis-trading-template
git worktree remove D:/tmp/kis-wt-sector-base
git worktree remove D:/tmp/kis-wt-sector
git worktree list
```
🔴 `scratchpad/sector/` 의 gz·jsonl·summary 는 **삭제 금지**(§5-4 재생성의 원료). 워크트리를 지우기 «전에» 라이브 트리 `RoboTrader_template/scratchpad/sector/` 로 **복사**할 것 — 워크트리와 함께 사라진다.

---

## 부록 A — 자체 검토 (writing-plans 필수 3항목)

### A-1. 스펙 커버리지 — §3~§11 전 항목 매핑

| 스펙 항목 | 태스크 | 확인 방법 |
|---|---|---|
| §3.1 `stock_sector_map` DDL · 인덱스 · CHECK | Task 1 | T11 DDL 멱등·역전 CHECK |
| §3.1 변경 감지 = (`ksic_code`,`ksic3_name`) 둘 | Task 2 | `CHANGE_FIELDS` · T2 |
| §3.1 「값 없음」은 변경 아님 · NULL→값 제자리 채움 | Task 2 | T2 `test_blank_new_value_is_not_a_change`·`test_null_to_value_fills_in_place` |
| §3.1 값→값 = 옛 줄 `valid_to=D−1` · 새 줄 `valid_from=D` | Task 2 | T2 `test_value_to_value_closes_and_opens` |
| §3.1 열린 줄 `valid_from==D` → 제자리 | Task 2 | T2 `test_same_day_change_updates_in_place` |
| §3.1 `valid_from>D` → 건너뛰고 WARN | Task 2·8 | T2 + `update_map` 의 WARNING |
| §3.1 부수 열 제자리 · `collected_at` 불변 · `last_seen_at` | Task 2 | T2 + `test_write_map_always_touches_last_seen_and_never_collected_at` |
| §3.1 부트스트랩 `valid_from=2021-01-04`·`source`·`snapshot_20260807` | Task 8·10 | `update_map(use_snapshot=True, valid_from=…)` · `bootstrap()` |
| §3.1 소급 판별은 `source='bootstrap_snapshot'` 로 | Task 10·13 | 리포트·문서 문장 |
| §3.1 상폐·캐시 이탈은 줄을 닫지 않는다 | Task 2 | 후보 없는 열린 줄은 계획에 안 들어간다(코드 경로) |
| §3.1 우선주 규칙 4분기 | Task 2 | T1 4개 테스트 |
| §3.1 소스 급변 가드 5%(필드별·분모 0 생략) | Task 2 | T3 4개 |
| §3.1 ①②③④ 각각 별도 트랜잭션 | Task 5·6·7·8 | 각 writer 함수가 자체 commit |
| §3.2 `sector_daily_stats` DDL · CHECK | Task 1 | T11 자릿수 CHECK |
| §3.2 20 달력일 창 · 창 «안» `close>0` ∧ 술어 · `market_cap` 조건 없음 | Task 6 | `_STATS_SQL` 구조 테스트 + T9 |
| §3.2 `r`·`up`(UP_MULT 1.15) | Task 6 | `test_day_stats_hand_computed_sector` |
| §3.2 라벨 절단 · 길이<N·비숫자 미정 | Task 6 | T5 |
| §3.2 순위·백분위(자기 제외 ≥ · `G<2` NULL) | Task 6 | T6 3케이스 |
| §3.2 `n_members<3` 도 저장 | Task 6 | 문턱 코드 없음(설계상 소비자 몫) |
| §3.2 미정 3종 summary·로그 | Task 6·8 | `undefined` 반환 + summary |
| §3.3 nodata 30일 재시도 | Task 5 | `_fill_targets` 2 테스트 |
| §3.4 이름표 재생성 · 점유율<0.8 WARNING · PIT 아님 | Task 7 | T12 |
| §3.5 실사례(2026-08-05) 5행 | Task 11 | `test_stats_reproduce_spec_worked_example` — n·중앙값·급등·상승비율·순위·백분위·G=159 를 `compute_day_stats` 출력으로 ±0.001%p 단언 |
| §3.6 `fn_sector_map_as_of` + 소비자 계약(컬럼 순서) | Task 1 | T11 왕복·경계·≤1행 |
| §4-① 캐시 CSV 날짜 지정·7일 후퇴·`source_asof` | Task 3 | T4 |
| §4-① 0건·규모 하한(묶음별·0 면제)·KONEX 무시 | Task 3 | T4 |
| §4-① 보통주/우선주 후보 값 규칙 | Task 8 | `update_map` + T1 조합 · **순회는 U_all**(캐시에 없는 종목도 후보를 만든다 — 부수 열 키는 생략해 보존) |
| §4-② corp_code 주 1회 | Task 5 | `maybe_refresh_corp_code` |
| §4-② (a) 채우기 대상 조건 | Task 5 | `_fill_targets` 3 테스트 |
| §4-② (b) 재확인 순환·커서·200건·레일 | Task 5 | `_recheck_targets`·`check_recheck_rail`·T14 |
| §4-② (c) 우선주 재복사 | Task 5·8 | `recopy_preferred` · collect_sector 호출 순서 |
| §4-② 상한 300 · 020/blocked 중단 · 카운터 3종 | Task 5 | T8 |
| §4-③ 0행 스킵(WARNING) | Task 6 | `compute_stats` |
| §4 실패 경로 — ① 실패해도 ②③④ 진행 · `written=false` 항상 저장 | Task 8 | T14 3 테스트 |
| §4-④ 이름표 | Task 7 | T12 |
| §4 summary 스키마 · 파일 저장 | Task 8 | `_write_summary` + T13 |
| §5-1 그날 명부만 쓴다 | Task 6 | `compute_stats` 가 `map_as_of(d)` |
| §5-2 소급 문장 2개 인쇄 | Task 10·13·14 | 백필 리포트·문서·완료 리포트 |
| §5-3 fail-closed | Task 6 | 미정 제외 + 카운트 |
| §5-4 손 수정 금지 · `--regen-map` · gz 삭제 금지 | Task 3·10·14 | `archive_raw` · `reset_map_from`(**DELETE/UPDATE 도 writer 안**) + `snapshot_map`/`restore_map` 로 중간 실패 복구 · `regen_map` · Task 14 Step 10 |
| §5-5 시간 가드 · `--dry-run` | Task 10 | T14 시간 가드·dry-run 테스트 |
| §6.0 부트스트랩 6단계 + 98% 게이트 | Task 10·14 | `bootstrap()` + 실행 |
| §6.1 EOD 자리 · 발효 | Task 12·14 | T10 순서 단언 · Step 9 |
| §6.2 백필 · 리포트 · `--delete-stats` | Task 10·14 | `backfill`·`delete_stats_cli` |
| §7 에러 표 9행 | Task 2·3·5·6·8·10·12 | 각 행이 위 태스크에 대응(아래 A-1b) |
| §8 게이트 1~9 · PASS/WARN/FAIL | Task 9 | T13 16 테스트 |
| §8-1 분자·분모가 **U_market 한정** | Task 9 Step 6 | `test_coverage_numerator_is_limited_to_u_market`(실 DB · 합성 _facts 로는 SQL 이 안 검증된다) |
| §8 recon 행 컬럼(ISO·real_rows·value_match_rate 방향) | Task 9 | T13 `test_verdict_vocabulary_and_iso_trade_date` |
| §9 T1~T14 | Task 1~12 | 아래 A-1c |
| §10 라이브 영향(2줄·KIS 0·3표 불변) | Task 12·14 | `git diff --stat` · 라이브 3표 전후 |
| §11 완료 판정 1~6 | Task 14 | Step 8 표 |

**A-1b · §7 에러 표 대응**

| §7 상황 | 구현 위치 |
|---|---|
| 캐시 7일 404 · 0건 · 규모 하한 · 급변 가드 → 명부 안 씀 | Task 3(`fetch_desc_csv`·`parse_desc_csv`·`check_scale_floor`) · Task 2(가드) · Task 8(`written=false`) |
| `valid_from>D` 대량 | 🔴 §7 과 §3.1 이 **모순**이다 — 이 계획은 §3.1(종목 단위 건너뛰기 + WARN)을 택했다. 근거는 **부록 D** |
| `source_asof < D − 5거래일` → `stale=true` | Task 8(`_stale_trading_days`) |
| DART 020·blocked → 중단, 나머지 진행 | Task 5(`fill_ksic`) · Task 8 |
| DART 800·HTTP 실패 → 백오프 재시도 | Task 4(`DartCompanyFetcher`) |
| 그날 일봉 0행 → 스킵 WARNING | Task 6(`compute_stats`) |
| `ksic_code` 길이>5 → 저장하되 WARN | Task 5(`_ask` 안의 길이 경고) |
| `fn_sector_map_as_of` 0행 → 스킵 ERROR | Task 6(`compute_stats`) |
| 부트스트랩 게이트 <98% → 중단·보고 | Task 10(`bootstrap`) |
| 오늘 summary 없음 → WARN, 3연속 FAIL | Task 9(gate9) |
| 어떤 예외든 `_safe` | Task 12 |

**A-1c · §9 테스트 대응**

| 스펙 테스트 | 파일 | 태스크 |
|---|---|---|
| T1 우선주 규칙 4분기 + 부모 값→값 | `test_sector_writer.py` | Task 2 |
| T2 SCD2 9항목 | `test_sector_writer.py` | Task 2 |
| T3 급변 가드 4항목 | `test_sector_writer.py` | Task 2 |
| T4 캐시 5항목 | `test_sector_collector.py` | Task 3 |
| T5 절단·창 4항목 | `test_sector_collector.py` | Task 6 |
| T6 백분위 손계산 3케이스 | `test_sector_collector.py` | Task 6 |
| T7 UPSERT 멱등 | T7-a `test_sector_writer_db.py`(DB) · T7-b `test_sector_collector.py`(결정성) | Task 6 |
| T8 DART 분기 3항목 | `test_sector_collector.py` | Task 5·8 |
| T9 오라클 (+ T9-b §3.5 실사례 재현) | `test_sector_stats_oracle_db.py` | Task 11 |
| T10 EOD 배선 | `test_eod_collection.py` | Task 12 |
| T11 DDL·함수·경계·≤1행 | `test_sector_writer_db.py` | Task 1 |
| T12 이름표 | `test_sector_writer_db.py` | Task 7 |
| T13 reconcile 게이트 | `test_sector_reconcile.py` | Task 9 |
| T13 「§8-1 분자가 U_market 한정」 | `test_sector_writer_db.py`(실 DB) | Task 9 Step 6 |
| T14 실패경로·시간가드·dry-run·재확인·레일·jsonl | `test_sector_collector.py` | Task 5·8·10 |

🔴 **T7 분리는 의도된 변형이다** — 스펙은 T7 을 `test_sector_collector.py` 에 뒀지만 「같은 날 두 번 실행 → 행수·값 무변경」은 DB 없이 진짜로 확인할 수 없다. 결정성(순수)과 멱등(DB)을 갈라 둘 다 건다.
🔴 **T9 도 둘로 나뉜다** — 오라클(종목별 `r`·라벨)과 §3.5 실사례 재현(섹터 집계·순위·백분위). 오라클만 두면 집계 버그가 종목 대조를 통과해 지나간다.
🔴 **T13 의 §8-1 항목은 합성 `_facts()` 로 검증되지 않는다** — SQL 자체를 재는 실 DB 테스트를 따로 뒀다.

**태스크별 기대 통과 수**(각 Step 의 Expected 와 같아야 한다):

| 파일 | Task 1 | Task 2 | Task 3 | Task 4 | Task 5 | Task 6 | Task 7 | Task 8 | Task 9 | Task 10 | Task 11 | Task 12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `test_sector_writer_db.py`(db) | 3→5 | — | — | — | — | 6 | 7 | — | 8 | — | — | — |
| `test_sector_writer.py` | — | 5→14→18→20 | — | — | — | — | — | — | — | — | — | — |
| `test_sector_collector.py` | — | — | 8 | 12 | 18→23 | 32 | — | 36 | — | 40 | — | — |
| `test_sector_reconcile.py` | — | — | — | — | — | — | — | — | 16 | — | — | — |
| `test_sector_stats_oracle_db.py`(db) | — | — | — | — | — | — | — | — | — | — | 2 | — |
| `test_eod_collection.py` | — | — | — | — | — | — | — | — | — | — | — | 13 |

Task 10 Step 9 의 3파일 합계 = **40 + 20 + 16 = 76**.

### A-2. 플레이스홀더 스캔

- `TODO` · `TBD` · `implement later` · `add validation` · 「Task N 과 같다」류 참조 — **0건**. 모든 코드 블록은 그대로 붙여 넣으면 도는 완성 코드다(같은 내용이 두 곳에 필요하면 반복해서 적었다).
- 값이 «실행 후에만» 정해지는 자리는 딱 두 곳이며 둘 다 **어디서 가져올지**를 Task 13 Step 3 의 표로 못박았다: 스펙 §6.0·§6.2 의 예상치, 쉬운 한 장의 「지금 상태」 절.
- 태스크마다 마지막 스텝은 커밋이고, 커밋 메시지는 파일로 써서 `git commit -F` 로 넣으며 두 트레일러 줄로 끝난다.

### A-3. 태스크 간 타입·시그니처 일관성

| 심볼 | 정의 | 소비 | 계약 |
|---|---|---|---|
| `is_blank(v)` | T2 writer | T2·5·6·8 | None·공백 문자열 → True |
| `parent_code(code)` | T2 writer | T2·5·8 | 6자·끝자리≠'0' 이면 `code[:5]+'0'`, 아니면 `None` |
| `apply_parent_rule(cands, universe)` | T2 writer | T8 | 입력·출력 모두 `{code: cand dict}` · 원본 불변(복사) |
| `plan_map_changes(open_rows, cands, D, guard=True, create_missing=True)` | T2 writer | T5·8·10 | 키 `inplace·close·open_new·changed_codes·skipped_past·skipped_missing·counts·guard` · 5% 초과면 `RuntimeError` · **운영 경로는 인자를 안 넘긴다**(기본값) · `guard=False` 는 분모 1~2 인 단위 테스트 전용 · `create_missing=False` 는 KSIC 재생 전용 |
| `write_map(conn, plan, source)` | T2 writer | T5·8 | `{closed,inserted,updated}` · 한 트랜잭션 |
| `load_open_rows(conn)` | T2 writer | T5·8·10 | `{code: {valid_from(date), ksic_code, ksic_source, ksic3_name, corp_code, market, source, source_asof, ksic_checked_at, last_seen_at}}` — `plan_map_changes` 의 `open_rows` 와 **같은 모양** |
| `load_stock_industry(conn)` | T2 writer | T8(부트스트랩만) | `{code: induty_code}` · 길이 5 초과면 WARN(§7) |
| `apply_ksic_updates(conn, responses, D, rail=False, source="eod", create_missing=True)` | T5 writer | T5·10 | `responses` 항목 = `{stock_code, ksic_code(None 가능), recheck(bool)}` · 반환에 `counts`·`changed_codes` 포함 |
| `check_recheck_rail(n_resp, n_changed)` | T5 writer | T5 | 30건 초과 «또는» 20% 초과면 `RuntimeError` |
| `reset_map_from(conn, d_from)` | T10 writer | T10 | `{deleted, reopened}` · 되돌린 뒤 열린 줄이 겹치면 `RuntimeError`(같은 트랜잭션이라 롤백) |
| `snapshot_map(conn)` / `restore_map(conn)` / `drop_map_snapshot(conn)` | T10 writer | T10 | 표 전체 사본 `stock_sector_map_regen_bak` — 재생성 중간 실패 복구용 |
| `upsert_stats(conn, rows)` | T6 writer | T6·10 | `rows` 항목은 `compute_day_stats` 출력 + `date` 키 |
| `delete_stats(conn, d_from, d_to, taxonomy)` | T6 writer | T10 | 삭제 «건수» 반환 |
| `rebuild_ksic_names(conn)` | T7 writer | T8·10 | `{codes, low_share}` |
| `upsert_reconciliation(conn, td, real, new, overlap, cov, vmr, verdict)` | T9 writer | T9 | `td` 는 ISO 문자열 · 인자 순서 고정(T13 이 이 순서로 단언) |
| `map_as_of(conn, d)` | T1 writer | T6·11 | 6튜플 `(stock_code, ksic_code, ksic_source, ksic3_name, valid_from, source)` |
| `load_desc(D, existing, fetcher=None, archive=True)` | T3 cache | T8·10 | `{source_asof(date), rows, counts, dropped, archive}` · `rows` 항목 키는 `update_map` 이 쓰는 7개 · `archive=False` 면 gz 를 «안 쓰고» `archive` 는 `None`(dry-run 전용) |
| `fetcher(url) -> (status:int, body:bytes)` | T3 규약 | T3·10 테스트·`_gz_fetcher` | 주입 지점 하나뿐 |
| `DartCompanyFetcher.fetch(corp_code)` | T4 | T5 | `(status:str, payload:dict)` · 020 은 예외 |
| `compute_day_stats(rows, labels)` | T6 collector | T6·10·**11** | `rows` = `load_day_rows` 4튜플 · `labels` = `{code: ksic_code}` · **T9 오라클이 이 출력을 직접 대조한다**(재집계 금지) |
| `SECTOR_DIR` | T5 collector | T5·8·10 | `krx_desc_cache.ARCHIVE_DIR` 과 «같은 값»(정의는 한 곳) |
| `_db_facts(conn, d, prev_days)` | T9 collector | T9 | `prev_days` = 직전 거래일 20개(최신순 ISO) — 호출측이 한 번만 조회해 넘긴다 |
| `evaluate_gates(D, today, prev, facts)` | T9 collector | T9 | `facts` 키 13개(u_market·ksic_code_nonnull·ksic3_name_nonnull·new_rows·stats_rows·g·duplicates·max_last_seen·is_trading_day·last_seen_deadline·**prev_days**·prev_new_rows·prev_recon_dates) · 반환 9키 |
| `maybe_refresh_corp_code(conn, key, days)` | T5 collector | T5·8·10 | 🔴 「DB 쓰기는 writer 한 곳」의 **명시 예외** — 기존 `dart_corp_code.refresh_from_dart()` 가 `dart_corp_code` 표에 직접 쓴다(스펙 §2 승인 · 신규 4표는 안 건드린다) |
| `SectorStageError.partial` | T5 collector | T5·8 | 부분 집계 dict — summary 에 그대로 들어간다 |

- `date` 객체와 ISO 문자열의 경계: **DB 파라미터·계획 계산은 `date` 객체**, **summary·recon·파일명·`facts["prev_days"]` 는 ISO 문자열**. `daily_prices.date` 만 TEXT 라 비교 시 `.isoformat()` 을 쓴다(`load_day_rows`·`_trading_days_between`·`_stale_trading_days`·`_db_facts` 의 `is_trading_day`).
- `sector_daily_stats.date` · `stock_sector_map.valid_from` 은 **date 형**이므로 `date` 객체를 그대로 넘긴다.
- 🔴 **`guard` / `create_missing` 은 운영 경로에서 «절대» False 로 넘기지 않는다.** `update_map`·`fill_ksic`·`recopy_preferred` 는 인자를 안 넘기고, `regen_map` 만 KSIC 재생에 `create_missing=False` 를 쓴다.

---

## 부록 B — 의도적으로 «넣지 않은» 것

| 항목 | 이유 |
|---|---|
| KSIC 2·5자리 이름(통계청 분류표) | 스펙 §6.3 범위 밖 |
| KRX 79업종 갱신 소스 탐색 | 스펙 §6.3·§10 범위 밖 (사장님 결정 09-06 밤: 분류체계 = KSIC 통일) |
| 뉴스·공시 섹터 집계·API·시그널 | 스펙 B(별건) — §10 범위 밖 |
| 라이브 매수 후보 표시 | 10월 말 별도 결정 — §10 범위 밖 |
| 문서 3 의 절단 자릿수 동결·`Ps` 정의·LOO 재계산 | 문서 3 사전등록 몫(§3.6 ①) |
| 종목별 LOO 성적표(≈1,100만 행) | 스펙 §10 「안 만든다」 |
| 부트스트랩 소급 편향 «크기» 측정 | 스펙 §5-2·§10 「재지 않는다」 |
| `stock_sector`·`sector_index_daily`·`stock_info.sector` 정리 | 스펙 §10 「기존 테이블 무변경」 |
| changelog 파일 | 메모리(`…/.claude/projects/…/memory/`)는 **레포 밖**이라 이 브랜치의 파일이 아니다 — 관리자가 별도로 쓴다(§11-6) |

## 부록 C — 스펙에 없지만 «더한» 것 (전부 리뷰 대상)

| 항목 | 이유 |
|---|---|
| repo 루트 `pyproject.toml` 에 `db` 마커 등록 | 지금은 `slow` 만 등록돼 있어 `@pytest.mark.db` 가 `PytestUnknownMarkWarning` 을 낸다. 스펙 T9 가 요구하는 「기준선 비교에서 제외」를 `-m "not db"` 로 하려면 등록이 필요하다 |
| §8 게이트 1·2 의 판정 어휘를 **FAIL** 로 못박음 | 스펙이 1·2 만 어휘를 안 적었다. 커버리지 미달은 부트스트랩 게이트와 같은 문턱이고 G 하한 미달은 조인 붕괴라 FAIL 로 둔다(Task 9 표에 명시) |
| `SectorStageError(partial=…)` | 「summary 는 어떤 경우에도 쓴다」(§4)와 「레일이 걸리면 RuntimeError」(§4-②b)를 동시에 만족시키려면 부분 집계를 예외에 실어 올려야 한다 |
| T7 을 T7-a(DB 멱등)/T7-b(결정성)로 분리 | A-1c 참조 |
| 백필·부트스트랩의 **라이브 3표 전후 대조 + 불일치 시 예외** | §11-2·3 이 「라이브 3표 전후」를 요구한다 — 리포트에만 적으면 사람이 봐야 하므로 코드가 스스로 막게 했다 |
| `_report()` 로 리포트 파일 생성 | §6.0-5·§6.2 가 리포트 «파일»을 요구한다 |
| `plan_map_changes(guard=…, create_missing=…)` 플래그 2개 | 표본이 1~2종목인 단위 테스트에서는 5% 가드가 무조건 걸린다(분모 1 → 100%). 가드 자체는 T3 이 100종목 표본으로 따로 검증한다. `create_missing=False` 는 KSIC 재생이 «유령 행»을 만들지 않게 한다. **둘 다 운영 경로에서는 기본값** |
| `update_map` 이 캐시 CSV 가 아니라 **U_all 을 순회** | 캐시에 없는 U_market 종목이 실재한다(KOSPI 945 vs 943 · KOSDAQ 1,827 vs 1,822). CSV 행만 돌면 그 종목은 명부 행이 영영 안 생기고 미라벨 목록에도 안 보인다 — 스펙 §4-①-3 의 「U_all 각 종목의 후보 값」을 문자 그대로 구현한 것이다 |
| `_unlabeled_list` 가 **「열린 줄이 아예 없음」도 미라벨**로 센다 | 열린 줄만 훑으면 「명부에 못 들어온 종목」이 목록에도 커버리지에도 안 보인다 |
| `load_desc(archive=False)` | dry-run 이 gz 를 남기면 「쓰기 0」이 거짓이 되고 §5-4 재생성 원료에 실제로는 안 쓴 날이 섞인다 |
| 부트스트랩 dry-run 의 **커버리지 «예측치»** | 98% 게이트를 dry-run 이 못 도우면 리포트가 결정에 쓸모없다. 예측 가정(DART 125건 전부 응답)을 리포트에 같이 인쇄한다 |
| `reset_map_from` 뒤의 **겹침 검사** | 「다시 열기」가 같은 종목에 열린 줄을 2개 만들 수 있다. 같은 트랜잭션 안에서 검사하므로 걸리면 통째로 롤백된다(열린 질문에 대한 답 — 「앞」이 아니라 「같은 트랜잭션 안 뒤」로 둔 이유는 UPDATE 결과를 봐야 판정할 수 있기 때문이다) |
| §3.5 실사례 재현 테스트(T9-b) | 오라클은 «종목별 r·라벨»만 재므로 집계 버그가 통과한다. 섹터 집계·순위·백분위를 스펙이 인쇄한 5행으로 따로 못박았다 |
| 게이트 9 「유실」을 **같은 날짜의 recon 행**이 있을 때로 좁힘 | 아무 recon 행에나 발동하면 첫날부터 매일 WARN 이 뜬다 |
| 게이트 4 정체를 **오늘 포함 3일**로 계산 | 스펙 「3거래일 연속」을 오늘+직전 3일(=4일)로 읽으면 한 박자 늦게 운다 |
| `snapshot_map` 이 남은 스냅샷을 **덮지 않고 RuntimeError** | 스냅샷이 남아 있다 = 직전 복구까지 실패했다는 뜻이고 그때 그 표가 유일한 복구원이다. 무조건 DROP 하면 다음 실행이 그 원본을 지운다. 수동 복구 절차는 Task 10 Step 6 에 적었다 |
| `_recheck_targets` 가 `corp_code` 없는 행을 제외 | 물을 수단이 없는데 대상에 넣으면 예산만 먹고 `ksic_checked_at` 커서만 전진해 «정말 물어야 할» 종목이 뒤로 밀린다 |
| `regen_map` 의 `except` 첫 줄이 `conn.rollback()` | 실패한 문장이 트랜잭션을 abort 로 두면 복구의 DELETE 가 `InFailedSqlTransaction` 으로 즉시 죽는다 — 복구 경로가 «복구 못 하는» 상태가 된다 |
| T9 의 「명부 행 없음」을 **그날 «대상 행» 기준**으로 측정 | `only_ours` 로 재면 라벨이 명부에서만 오므로 항상 ∅ 인 vacuous 단언이 된다. `undefined["no_label"]` 집계도 함께 단언한다 |

## 부록 E — 이 계획이 남기는 «알려진 한계» 4가지 (완료 리포트에 그대로 옮길 것)

1. **`--regen-map` 은 원본 실행의 재현이 아니다.** ①5% 가드에 걸렸던 날을 재생하면 그 날 다시
   RuntimeError 가 나고 재생 «전체»가 롤백된다(의도 — 조사가 먼저다). ②원래 `written=false`
   였던 날은 7일 후퇴 gz 로 «쓰이므로» 명부가 원본보다 더 채워질 수 있다.
2. **`test_stats_reproduce_spec_worked_example` 은 동결 데이터 오라클이다.** 라이브
   `daily_prices` 2026-08-05 ±20일 + `stock_industry` 스냅샷에 값이 묶여 있다. 일봉 결손
   49,252행 복구나 `adj_factor` 보정 `--apply` 가 들어오면 **코드가 옳아도 깨진다** —
   그때는 데이터 변경을 먼저 확인하고 기대값을 재계산한다(코드를 고치지 않는다).
3. **백필 「수 분 ~ 15분」은 추정이다.** 실측 근거가 없고, 첫 실측은 백필 리포트의
   `elapsed_sec` 다. 크게 벗어나면 스펙 §6.2 와 이 문장을 함께 갱신한다.
4. **부트스트랩 dry-run 의 커버리지는 예측치이며 과대일 수 있다.** DART 125건이 전부
   `induty_code` 를 준다는 가정(08-07 실행 · 다른 집합)에서 나왔고, 무자료(013)·형식 이상
   응답은 반영하지 않는다. 본 실행 리포트가 실측으로 대체한다.

## 부록 D — 스펙 안의 자기모순 하나와 이 계획의 선택

**§7 표**는 「`valid_from > trade_date` **대량** → 명부 안 씀」이라 적었고,
**§3.1**은 「그 종목은 **건너뛰고** 건수를 WARN」이라 적었다. 둘은 같은 상황에 다른 동작이다.

**이 계획은 §3.1 을 택한다** — 종목 단위로 건너뛰고 세며, 명부 쓰기 자체는 진행한다.

이유: ①과거 날짜 재실행은 «정상 운영 경로»(`run_data_collection('YYYYMMDD')`)이고 ②「대량」의
문턱이 스펙에 없으며 ③전량 중단으로 처리하면 오늘치 정상 종목의 갱신까지 막혀 §8-5(얼어붙은
명부)를 스스로 만든다. `skipped_past` 는 summary·WARNING·리포트에 남으므로 무징후가 아니다.
⚠️ 스펙을 고칠 기회가 있으면 §7 표의 그 줄을 §3.1 에 맞춰 정정할 것.
