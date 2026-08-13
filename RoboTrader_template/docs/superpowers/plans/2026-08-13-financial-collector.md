# 재무 수집기 (DART as-filed + KIS 분기비율) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DART 분기 재무를 **접수건 단위 append-only 원장**으로 수집해 정정공시가 원본을 덮어쓰지 못하게 하고, 2026 1Q·반기를 적재한다.

**Architecture:** 집 규약 3분할(`collector` 오케스트레이션 / `fetcher` 외부호출 / `writer` DB쓰기). 신규 4테이블 + 뷰 1개. `eod_collection.py` 에 2줄 등록. 라이브 매매 동작 0줄.

**Tech Stack:** Python 3.8+ · `requests` · `psycopg2` · PostgreSQL 16(`kis_template`, port **5433**) · pytest

**설계문서:** `docs/superpowers/specs/2026-08-13-financial-collector-design.md` (커밋 `9576682`)

## Global Constraints

- **DB 는 `kis_template` 단일.** DB명 하드코딩 금지 — `db.kis_db_connection.KisDbConnection.get_connection()` 경유. port **5433**.
- **연구 트리 import 금지.** `collectors/` 는 운영 코드다. `scripts/dart_mcap_common.py` 를 import 하지 말고 필요한 최소 클라이언트를 **재구현**한다 (`corp_events_collector.py:5-6` 이 명시한 규약).
- **`lib/universe_filter.py` import 금지** — 연구 전용. 술어는 `config.constants.SQL_STOCK_ONLY` 하나만 쓴다.
- **동시 요청 금지.** opendart 는 순차 + `min_interval` 유지. 2026-08-06 에 4스레드로 IP 차단당한 전례.
- **파싱 실패는 `None`. 절대 `0` 아님.**
- **빈 응답을 성공으로 처리하지 않는다.** 모든 호출의 `status` 를 검사·집계한다.
- **무징후 절단 금지.** 페이지·목록·상한에 걸려 못 읽은 게 있으면 **반드시 WARNING**.
- **라이브 테이블 무변경**: `daily_prices` · `minute_candles` · `virtual_trading_records` 에 쓰지 않는다.
- **로거**: `utils.logger.setup_logger(__name__)`. **시간**: `utils.korean_time.now_kst()`.
- 전체 스위트는 **repo 루트 + VS 번들 Python** 에서만 완주한다(venv 엔 `pykrx` 없음). 회귀 판정은 **실패 «집합» 차분**.

## File Structure

| 파일 | 책임 | 신규/수정 |
|---|---|---|
| `collectors/dart_corp_code.py` | corpCode.xml → `dart_corp_code` 테이블 | 신규 |
| `collectors/dart_financial_fetcher.py` | `fnlttSinglAcntAll` 호출 · status · 원본 append | 신규 |
| `collectors/kis_financial_fetcher.py` | `get_financial_ratio(div_cls="1")` 래핑 | 신규 |
| `collectors/financial_writer.py` | DDL · 파싱 · UPSERT (**DB 쓰기는 여기만**) | 신규 |
| `collectors/financial_metrics.py` | `account_id` → 13지표 매핑표 + 뷰 DDL | 신규 |
| `collectors/financial_collector.py` | 창 판정 · 대상 산출 · collect/reconcile · 백필 CLI | 신규 |
| `collectors/eod_collection.py` | **+2줄** 등록 | 수정 |
| `tests/collectors/test_*.py` | 6개 신규 테스트 파일 | 신규 |

**경계**: fetcher 는 DB 를 모르고, writer 는 HTTP 를 모른다. collector 만 둘 다 안다.

---

## ✅ 스펙 대비 편차 2건 — **2026-08-13 사장님 승인, 스펙 반영 완료**(§3.2 · §3.5)

**편차 1 — `thstrm_add_amount` 컬럼 추가.** 스펙 §3.2 에 없다.
분기 손익계산서에서 `thstrm_amount` 는 **당분기 3개월**이고 `thstrm_add_amount` 가 **누계**다.
이 컬럼이 없으면 ***분기 매출액·영업이익을 만들 수 없다*** — 이 수집기의 목적이 절반 무너진다.
연간 보고서엔 이 필드가 없으므로 `NULL` 이다.

**편차 2 — `dart_corp_code` 테이블 신설.** 스펙에 없다.
`corp_code ↔ stock_code` 매핑이 지금 **`scratchpad/mcap_dart/a1_corpcode_map.json`(2,556건) 파일에만** 있고
그 디렉토리는 **git 미추적**이다. 운영 수집기가 거기 의존하면 `git clean -xdf` 한 번에 죽는다.
🔑 이번에 백업한 `f2_raw` 와 **정확히 같은 형태의 위험**이다.

---

## Task 1: `dart_corp_code` 매핑 테이블

**Files:**
- Create: `collectors/dart_corp_code.py`
- Test: `tests/collectors/test_dart_corp_code.py`

**Interfaces:**
- Consumes: (없음 — 첫 태스크)
- Produces:
  - `DDL: str` — `CREATE TABLE IF NOT EXISTS dart_corp_code (...)`
  - `ensure_table(conn) -> None`
  - `upsert_map(conn, mapping: dict, names: dict = None) -> int` — `{stock_code: corp_code}` → 적재 행수
  - `load_map(conn) -> dict` — `{stock_code: corp_code}`
  - `parse_corpcode_xml(xml_bytes: bytes) -> dict` — corpCode.xml → `{stock_code: corp_code}`
  - `refresh_from_dart(conn, key: str) -> int` — corpCode.xml 1회 다운로드 후 적재

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/collectors/test_dart_corp_code.py
import pytest
from collectors import dart_corp_code as m

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list><corp_code>00126380</corp_code><corp_name>samsung</corp_name>
        <stock_code>005930</stock_code><modify_date>20260101</modify_date></list>
  <list><corp_code>00164779</corp_code><corp_name>sk</corp_name>
        <stock_code>000660</stock_code><modify_date>20260101</modify_date></list>
  <list><corp_code>00999999</corp_code><corp_name>nonlisted</corp_name>
        <stock_code>     </stock_code><modify_date>20260101</modify_date></list>
</result>"""


def test_parse_skips_nonlisted():
    """stock_code 가 공백인 비상장사는 매핑에서 빠져야 한다."""
    out = m.parse_corpcode_xml(SAMPLE_XML)
    assert out == {"005930": "00126380", "000660": "00164779"}


def test_parse_rejects_empty_result():
    """빈 결과를 «성공»으로 돌려주면 안 된다 — 매핑 전멸이 조용히 통과한다."""
    with pytest.raises(ValueError):
        m.parse_corpcode_xml(b"<?xml version='1.0'?><result></result>")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/collectors/test_dart_corp_code.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collectors.dart_corp_code'`

- [ ] **Step 3: 최소 구현**

```python
# collectors/dart_corp_code.py
"""DART corp_code ↔ stock_code 매핑 테이블.

🔴 이 매핑이 예전엔 scratchpad/mcap_dart/a1_corpcode_map.json 파일에만 있었다.
   그 디렉토리는 gitignore 대상이라 `git clean -xdf` 한 번에 사라진다.
   운영 수집기가 의존하는 데이터는 DB 에 있어야 한다.
"""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS dart_corp_code (
    stock_code varchar(20) PRIMARY KEY,
    corp_code  varchar(8)  NOT NULL,
    corp_name  text,
    updated_at timestamp   NOT NULL DEFAULT now()
)
"""

_UPSERT = """
INSERT INTO dart_corp_code (stock_code, corp_code, corp_name, updated_at)
VALUES (%(stock_code)s, %(corp_code)s, %(corp_name)s, now())
ON CONFLICT (stock_code) DO UPDATE SET
    corp_code=EXCLUDED.corp_code, corp_name=EXCLUDED.corp_name, updated_at=now()
"""


def parse_corpcode_xml(xml_bytes: bytes) -> dict:
    """corpCode.xml → {stock_code: corp_code}. 비상장(stock_code 공백)은 제외.

    🔴 결과가 비면 ValueError. 빈 매핑을 «성공»으로 돌려주면 수집 대상이 0이 되고
       그게 «오늘은 받을 게 없었다»로 보인다.
    """
    root = ET.fromstring(xml_bytes)
    out = {}
    for node in root.iter("list"):
        sc = (node.findtext("stock_code") or "").strip()
        cc = (node.findtext("corp_code") or "").strip()
        if not sc or not cc:
            continue
        out[sc] = cc
    if not out:
        raise ValueError("corpCode.xml 파싱 결과가 0건 — 응답 형식이 바뀌었거나 빈 응답이다")
    return out
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest tests/collectors/test_dart_corp_code.py -v`
Expected: 2 passed

- [ ] **Step 5: 나머지 함수 4개 추가**

```python
def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def upsert_map(conn, mapping: dict, names: dict = None) -> int:
    names = names or {}
    with conn.cursor() as cur:
        for sc, cc in mapping.items():
            cur.execute(_UPSERT, {"stock_code": sc, "corp_code": cc,
                                  "corp_name": names.get(sc)})
    conn.commit()
    return len(mapping)


def load_map(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT stock_code, corp_code FROM dart_corp_code")
        return {r[0]: r[1] for r in cur.fetchall()}


def refresh_from_dart(conn, key: str) -> int:
    """corpCode.xml 1회 다운로드 → 적재. 호출 1건이라 한도 영향 미미."""
    import io
    import zipfile
    import requests
    r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                     params={"crtfc_key": key}, timeout=120)
    r.raise_for_status()
    body = r.content
    # 🔴 zip 이 아니면 즉시 실패. 에러 JSON 을 xml 로 파싱하면 0건이 «성공»이 된다.
    if body[:2] != b"PK":
        raise RuntimeError(f"corpCode.xml 이 zip 이 아님 (len={len(body)}): {body[:200]!r}")
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        xmls = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not xmls:
            raise RuntimeError(f"zip 안에 xml 없음: {z.namelist()}")
        data = z.read(xmls[0])
    mapping = parse_corpcode_xml(data)
    ensure_table(conn)
    n = upsert_map(conn, mapping)
    logger.info("[dart_corp_code] 매핑 갱신 %d건", n)
    return n
```

- [ ] **Step 6: 테이블 생성 + 기존 JSON 으로 시드**

```bash
cd D:/GIT/kis-trading-template/RoboTrader_template
python -c "
import json, sys
sys.path.insert(0,'.')
from db.kis_db_connection import KisDbConnection
from collectors import dart_corp_code as m
mp = json.load(open('scratchpad/mcap_dart/a1_corpcode_map.json', encoding='utf-8'))
with KisDbConnection.get_connection() as conn:
    m.ensure_table(conn)
    print('seeded:', m.upsert_map(conn, mp))
    print('loaded:', len(m.load_map(conn)))
"
```
Expected: `seeded: 2556` / `loaded: 2556`

- [ ] **Step 7: 커밋**

```bash
git add collectors/dart_corp_code.py tests/collectors/test_dart_corp_code.py
git commit -m "feat(collectors): corp_code 매핑을 git 미추적 파일에서 DB 테이블로 승격"
```

---

## Task 2: 스키마 DDL + writer 골격

**Files:**
- Create: `collectors/financial_writer.py`
- Test: `tests/collectors/test_financial_writer.py`

**Interfaces:**
- Consumes: (없음)
- Produces:
  - `DDL_FILINGS: str` · `DDL_ACCOUNTS: str` · `DDL_KIS_RATIO: str`
  - `ensure_tables(conn) -> None`
  - `parse_amount(v) -> int | None`
  - `rows_from_dart_response(payload: dict, stock_code: str, fs_div: str) -> tuple[dict, list[dict]]`
    — `(filing_row, account_rows)`
  - `upsert_filing(conn, filing: dict) -> None`
  - `upsert_accounts(conn, rows: list) -> int`

- [ ] **Step 1: 실패하는 테스트 — 정정 보존과 `ord` 보존**

```python
# tests/collectors/test_financial_writer.py
import pytest
from collectors import financial_writer as w

RESP = {
    "status": "000", "message": "정상",
    "list": [
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Assets",
         "account_nm": "자산총계", "thstrm_amount": "1,000", "frmtrm_amount": "900",
         "bfefrmtrm_amount": "800", "ord": "1", "currency": "KRW"},
        # 같은 account_id 가 두 번 — ord 만 다르다. 표준계정코드 미사용분 16.3% 에서 실제로 난다.
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "BS", "account_id": "ifrs-full_Assets",
         "account_nm": "자산총계(주석)", "thstrm_amount": "1,001", "frmtrm_amount": "901",
         "bfefrmtrm_amount": "801", "ord": "2", "currency": "KRW"},
    ],
}


def test_ord_keeps_duplicate_account_ids():
    """같은 account_id 2건이 «둘 다» 살아남아야 한다. ord 가 키에 없으면 1건이 조용히 사라진다."""
    filing, accounts = w.rows_from_dart_response(RESP, "005930", "CFS")
    assert len(accounts) == 2
    assert {a["ord"] for a in accounts} == {1, 2}
    assert {a["thstrm_amount"] for a in accounts} == {1000, 1001}


def test_filing_carries_rcept_no_and_reprt_code():
    """지금 죽은 테이블에 없던 두 컬럼이 반드시 채워져야 한다."""
    filing, _ = w.rows_from_dart_response(RESP, "005930", "CFS")
    assert filing["rcept_no"] == "20260515000001"
    assert filing["reprt_code"] == "11013"
    assert filing["fs_div"] == "CFS"
    assert filing["stock_code"] == "005930"


def test_parse_amount_failure_is_none_not_zero():
    """🔴 파싱 실패를 0 으로 뭉개면 «부채 0원인 우량기업»이 된다."""
    assert w.parse_amount("1,234") == 1234
    assert w.parse_amount("-5,000") == -5000
    assert w.parse_amount("-") is None
    assert w.parse_amount("") is None
    assert w.parse_amount(None) is None
    assert w.parse_amount("N/A") is None


def test_quarterly_cumulative_amount_is_captured():
    """🔴 분기 IS 는 thstrm_amount(당분기)와 thstrm_add_amount(누계)가 다르다.
    누계를 안 받으면 분기 매출액을 만들 수 없다."""
    resp = {"status": "000", "list": [
        {"rcept_no": "20260515000001", "reprt_code": "11013", "bsns_year": "2026",
         "corp_code": "00126380", "sj_div": "IS", "account_id": "ifrs-full_Revenue",
         "account_nm": "매출액", "thstrm_amount": "300", "thstrm_add_amount": "300",
         "ord": "1", "currency": "KRW"}]}
    _, accounts = w.rows_from_dart_response(resp, "005930", "CFS")
    assert accounts[0]["thstrm_amount"] == 300
    assert accounts[0]["thstrm_add_amount"] == 300
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/collectors/test_financial_writer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collectors.financial_writer'`

- [ ] **Step 3: DDL + 파싱 구현**

```python
# collectors/financial_writer.py
"""DART/KIS 재무 → kis_template UPSERT. **DB 쓰기는 이 파일 한 곳뿐.**

🔑 기존 dart_financials_asfiled 가 죽은 이유는 컬럼 부족이 아니라 «키가 기간»이었기 때문이다.
   여기 키는 «접수건»(rcept_no, fs_div)이라 정정공시가 원본을 덮어쓰는 일이
   정책이 아니라 «구조적으로» 불가능하다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DDL_FILINGS = """
CREATE TABLE IF NOT EXISTS dart_financial_filings (
    rcept_no     varchar(14) NOT NULL,
    fs_div       varchar(3)  NOT NULL,
    corp_code    varchar(8)  NOT NULL,
    stock_code   varchar(20) NOT NULL,
    bsns_year    varchar(4)  NOT NULL,
    reprt_code   varchar(5)  NOT NULL,
    rcept_dt     date,
    is_amendment boolean     NOT NULL DEFAULT false,
    raw_path     text,
    collected_at timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (rcept_no, fs_div)
)
"""

DDL_FILINGS_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_dff_key ON dart_financial_filings "
    "(stock_code, bsns_year, reprt_code, rcept_dt)",
    "CREATE INDEX IF NOT EXISTS idx_dff_rcept ON dart_financial_filings (rcept_dt)",
]

DDL_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS dart_financial_accounts (
    rcept_no          varchar(14) NOT NULL,
    fs_div            varchar(3)  NOT NULL,
    sj_div            varchar(8)  NOT NULL,
    account_id        text        NOT NULL,
    ord               int         NOT NULL,
    account_nm        text,
    thstrm_amount     bigint,
    thstrm_add_amount bigint,
    frmtrm_amount     bigint,
    bfefrmtrm_amount  bigint,
    currency          text,
    PRIMARY KEY (rcept_no, fs_div, sj_div, account_id, ord)
)
"""

DDL_KIS_RATIO = """
CREATE TABLE IF NOT EXISTS kis_financial_ratio (
    stock_code  varchar(20) NOT NULL,
    stac_yymm   varchar(6)  NOT NULL,
    div_cls     varchar(1)  NOT NULL,
    roe_value               numeric,
    per                     numeric,
    eps                     numeric,
    sps                     numeric,
    bps                     numeric,
    reserve_ratio           numeric,
    liability_ratio         numeric,
    sales_growth            numeric,
    operating_income_growth numeric,
    net_income_growth       numeric,
    raw_json    jsonb,
    PRIMARY KEY (stock_code, stac_yymm, div_cls)
)
"""
# 🔴 kis_financial_ratio 에 날짜형 컬럼이 없는 것은 «의도»다.
#    KIS 응답엔 접수일이 없어 PIT 앵커를 만들 수 없다.
#    PIT 앵커가 없는 데이터에 날짜 컬럼을 붙이면 누군가 그걸 PIT 으로 쓴다.

_NUM_RE = re.compile(r"^-?[\d,]+$")


def parse_amount(v):
    """'1,234' → 1234. 실패는 None — 🔴 절대 0 이 아니다."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    if not _NUM_RE.match(s):
        return None
    try:
        return int(s.replace(",", ""))
    except ValueError:
        return None


def rows_from_dart_response(payload: dict, stock_code: str, fs_div: str):
    """fnlttSinglAcntAll 응답 → (filing_row, account_rows). 빈 list 면 (None, [])."""
    items = payload.get("list") or []
    if not items:
        return None, []
    head = items[0]
    filing = {
        "rcept_no": str(head.get("rcept_no", "")).strip(),
        "fs_div": fs_div,
        "corp_code": str(head.get("corp_code", "")).strip(),
        "stock_code": stock_code,
        "bsns_year": str(head.get("bsns_year", "")).strip(),
        "reprt_code": str(head.get("reprt_code", "")).strip(),
        "rcept_dt": None,          # list.json 또는 별도 조회로 채운다(Task 6)
        "is_amendment": False,     # 적재 후 SQL 로 재계산(Task 4 Step 7)
        "raw_path": None,          # collector 가 채운다
    }
    accounts = []
    for it in items:
        try:
            ordv = int(str(it.get("ord", "0")).strip() or 0)
        except ValueError:
            ordv = 0
        accounts.append({
            "rcept_no": filing["rcept_no"],
            "fs_div": fs_div,
            "sj_div": str(it.get("sj_div", "")).strip(),
            "account_id": str(it.get("account_id", "")).strip(),
            "ord": ordv,
            "account_nm": it.get("account_nm"),
            "thstrm_amount": parse_amount(it.get("thstrm_amount")),
            "thstrm_add_amount": parse_amount(it.get("thstrm_add_amount")),
            "frmtrm_amount": parse_amount(it.get("frmtrm_amount")),
            "bfefrmtrm_amount": parse_amount(it.get("bfefrmtrm_amount")),
            "currency": it.get("currency"),
        })
    return filing, accounts
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest tests/collectors/test_financial_writer.py -v`
Expected: 4 passed

- [ ] **Step 5: UPSERT 3종 + `ensure_tables` 추가**

```python
_UPSERT_FILING = """
INSERT INTO dart_financial_filings
  (rcept_no, fs_div, corp_code, stock_code, bsns_year, reprt_code,
   rcept_dt, is_amendment, raw_path)
VALUES (%(rcept_no)s, %(fs_div)s, %(corp_code)s, %(stock_code)s, %(bsns_year)s,
        %(reprt_code)s, %(rcept_dt)s, %(is_amendment)s, %(raw_path)s)
ON CONFLICT (rcept_no, fs_div) DO UPDATE SET
    rcept_dt=COALESCE(EXCLUDED.rcept_dt, dart_financial_filings.rcept_dt),
    raw_path=COALESCE(EXCLUDED.raw_path, dart_financial_filings.raw_path)
"""

_UPSERT_ACCOUNT = """
INSERT INTO dart_financial_accounts
  (rcept_no, fs_div, sj_div, account_id, ord, account_nm,
   thstrm_amount, thstrm_add_amount, frmtrm_amount, bfefrmtrm_amount, currency)
VALUES (%(rcept_no)s, %(fs_div)s, %(sj_div)s, %(account_id)s, %(ord)s, %(account_nm)s,
        %(thstrm_amount)s, %(thstrm_add_amount)s, %(frmtrm_amount)s,
        %(bfefrmtrm_amount)s, %(currency)s)
ON CONFLICT (rcept_no, fs_div, sj_div, account_id, ord) DO UPDATE SET
    account_nm=EXCLUDED.account_nm,
    thstrm_amount=EXCLUDED.thstrm_amount,
    thstrm_add_amount=EXCLUDED.thstrm_add_amount,
    frmtrm_amount=EXCLUDED.frmtrm_amount,
    bfefrmtrm_amount=EXCLUDED.bfefrmtrm_amount,
    currency=EXCLUDED.currency
"""

_UPSERT_KIS = """
INSERT INTO kis_financial_ratio
  (stock_code, stac_yymm, div_cls, roe_value, per, eps, sps, bps,
   reserve_ratio, liability_ratio, sales_growth, operating_income_growth,
   net_income_growth, raw_json)
VALUES (%(stock_code)s, %(stac_yymm)s, %(div_cls)s, %(roe_value)s, %(per)s, %(eps)s,
        %(sps)s, %(bps)s, %(reserve_ratio)s, %(liability_ratio)s, %(sales_growth)s,
        %(operating_income_growth)s, %(net_income_growth)s, %(raw_json)s::jsonb)
ON CONFLICT (stock_code, stac_yymm, div_cls) DO UPDATE SET
    roe_value=EXCLUDED.roe_value, per=EXCLUDED.per, eps=EXCLUDED.eps,
    sps=EXCLUDED.sps, bps=EXCLUDED.bps, reserve_ratio=EXCLUDED.reserve_ratio,
    liability_ratio=EXCLUDED.liability_ratio, sales_growth=EXCLUDED.sales_growth,
    operating_income_growth=EXCLUDED.operating_income_growth,
    net_income_growth=EXCLUDED.net_income_growth, raw_json=EXCLUDED.raw_json
"""


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL_FILINGS)
        for sql in DDL_FILINGS_IDX:
            cur.execute(sql)
        cur.execute(DDL_ACCOUNTS)
        cur.execute(DDL_KIS_RATIO)
    conn.commit()


def upsert_filing(conn, filing: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(_UPSERT_FILING, filing)
    conn.commit()


def upsert_accounts(conn, rows: list) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(_UPSERT_ACCOUNT, r)
    conn.commit()
    return len(rows)


def upsert_kis_ratio(conn, rows: list) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(_UPSERT_KIS, r)
    conn.commit()
    return len(rows)
```

- [ ] **Step 6: 테이블 생성**

```bash
python -c "
import sys; sys.path.insert(0,'.')
from db.kis_db_connection import KisDbConnection
from collectors import financial_writer as w
with KisDbConnection.get_connection() as conn:
    w.ensure_tables(conn); print('ok')
"
```
Expected: `ok`

- [ ] **Step 7: DB 통합 테스트 — 🔴 정정 보존 (스펙 테스트 #1)**

```python
# tests/collectors/test_financial_writer_db.py
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import financial_writer as w  # noqa: E402

ORIG = {"rcept_no": "29999999000001", "fs_div": "CFS", "corp_code": "00000000",
        "stock_code": "TEST01", "bsns_year": "2026", "reprt_code": "11013",
        "rcept_dt": "2026-05-15", "is_amendment": False, "raw_path": None}
AMEND = dict(ORIG, rcept_no="29999999000002", rcept_dt="2026-06-30", is_amendment=True)


@pytest.fixture
def conn():
    with KisDbConnection.get_connection() as c:
        w.ensure_tables(c)
        yield c
        with c.cursor() as cur:
            cur.execute("DELETE FROM dart_financial_accounts WHERE rcept_no IN %s",
                        ((ORIG["rcept_no"], AMEND["rcept_no"]),))
            cur.execute("DELETE FROM dart_financial_filings WHERE stock_code='TEST01'")
        c.commit()


def test_amendment_does_not_overwrite_original(conn):
    """🔴 지금 죽은 테이블이 실패하는 바로 그 지점.
    같은 (stock, year, reprt) 인데 rcept_no 가 다르면 «두 행 다» 남아야 한다."""
    w.upsert_filing(conn, ORIG)
    w.upsert_accounts(conn, [dict(rcept_no=ORIG["rcept_no"], fs_div="CFS", sj_div="BS",
                                  account_id="ifrs-full_Assets", ord=1, account_nm="자산총계",
                                  thstrm_amount=1000, thstrm_add_amount=None,
                                  frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW")])
    w.upsert_filing(conn, AMEND)
    w.upsert_accounts(conn, [dict(rcept_no=AMEND["rcept_no"], fs_div="CFS", sj_div="BS",
                                  account_id="ifrs-full_Assets", ord=1, account_nm="자산총계",
                                  thstrm_amount=2000, thstrm_add_amount=None,
                                  frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW")])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dart_financial_filings "
                    "WHERE stock_code='TEST01' AND bsns_year='2026' AND reprt_code='11013'")
        assert cur.fetchone()[0] == 2, "정정공시가 원본을 덮어썼다"
        cur.execute("SELECT thstrm_amount FROM dart_financial_accounts "
                    "WHERE rcept_no IN %s ORDER BY rcept_no",
                    ((ORIG["rcept_no"], AMEND["rcept_no"]),))
        assert [r[0] for r in cur.fetchall()] == [1000, 2000]
```

- [ ] **Step 8: 테스트 실행**

Run: `python -m pytest tests/collectors/test_financial_writer_db.py -v`
Expected: 1 passed

- [ ] **Step 9: 커밋**

```bash
git add collectors/financial_writer.py tests/collectors/test_financial_writer.py tests/collectors/test_financial_writer_db.py
git commit -m "feat(collectors): 재무 원장 스키마 — 키를 «기간»에서 «접수건»으로 바꿔 정정 보존을 구조로 만든다"
```

---

## Task 3: `dart_financial_fetcher.py`

**Files:**
- Create: `collectors/dart_financial_fetcher.py`
- Test: `tests/collectors/test_dart_financial_fetcher.py`

**Interfaces:**
- Consumes: (없음 — HTTP 만)
- Produces:
  - `class DartQuotaExceeded(RuntimeError)` · `class DartBlocked(RuntimeError)`
  - `class DartFinancialFetcher:`
    - `__init__(self, key: str, min_interval: float = 0.34)`
    - `.calls: int` · `.status_counts: dict` · `.conn_resets: int`
    - `fetch(corp_code, bsns_year, reprt_code, fs_div) -> tuple[str, dict]` — `(status, payload)`
  - `append_raw(path: str, payload: dict) -> int` — 쓴 줄 번호(1-based) 반환

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/collectors/test_dart_financial_fetcher.py
import gzip
import json
import pytest
from collectors import dart_financial_fetcher as f


class _Resp:
    def __init__(self, js, code=200):
        self._js, self.status_code = js, code

    def json(self):
        return self._js


def test_quota_exceeded_raises_not_returns_empty(monkeypatch):
    """🔴 status=020 을 «0건»으로 돌려주면 조용히 빈 수집이 «성공»이 된다."""
    fetcher = f.DartFinancialFetcher("k", min_interval=0.0)
    monkeypatch.setattr(fetcher.session, "get", lambda *a, **kw: _Resp({"status": "020"}))
    with pytest.raises(f.DartQuotaExceeded):
        fetcher.fetch("00126380", "2026", "11013", "CFS")


def test_no_data_returns_013_not_exception(monkeypatch):
    """013(무자료)은 정상 종료다 — 예외로 올리면 EOD 가 매번 시끄러워진다."""
    fetcher = f.DartFinancialFetcher("k", min_interval=0.0)
    monkeypatch.setattr(fetcher.session, "get", lambda *a, **kw: _Resp({"status": "013"}))
    status, payload = fetcher.fetch("00126380", "2026", "11013", "CFS")
    assert status == "013"
    assert payload.get("list") in (None, [])


def test_append_raw_returns_line_number(tmp_path):
    """raw_path 로 원본을 역추적할 수 있어야 한다."""
    p = str(tmp_path / "dart_20260813.jsonl.gz")
    assert f.append_raw(p, {"a": 1}) == 1
    assert f.append_raw(p, {"a": 2}) == 2
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        lines = [json.loads(x) for x in fh]
    assert lines == [{"a": 1}, {"a": 2}]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/collectors/test_dart_financial_fetcher.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
# collectors/dart_financial_fetcher.py
"""DART fnlttSinglAcntAll 최소 클라이언트 (운영 EOD 경로).

🔴 scripts/dart_mcap_common.py 를 import 하지 않는다 — 연구 트리다.
   corp_events_collector.py 와 같은 규약으로 최소 재구현한다.
🔴 동시 요청 금지. 2026-08-06 실측: 4스레드 동시요청으로 opendart 전 호스트가
   리셋 상태가 됐고 루트 페이지조차 curl 로 reset 됐다.
"""
import gzip
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"
_MAX_TRIES = 6
_BACKOFF_START = 2.0
_BACKOFF_CAP = 30.0


class DartQuotaExceeded(RuntimeError):
    """status=020 — 일일 사용한도 초과. 자정에 리셋된다(2026-08-07 실측)."""


class DartBlocked(RuntimeError):
    """연결 리셋 연속 — opendart 가 IP 단위로 차단한 상태."""


class DartFinancialFetcher:
    def __init__(self, key: str, min_interval: float = 0.34):
        # 0.34s = 3 req/s. B1 시총 수집 20,241호출 동안 연결 리셋 0 을 실측한 안전값.
        self.key = key
        self.session = requests.Session()
        self.min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0
        self.status_counts = {}
        self.http_errors = 0
        self.conn_resets = 0

    def _bump(self, status):
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def _throttle(self):
        gap = time.time() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_call = time.time()

    def fetch(self, corp_code: str, bsns_year: str, reprt_code: str, fs_div: str):
        """→ (status, payload). 020 은 예외, 013 은 정상 반환."""
        url = f"{DART_BASE}/fnlttSinglAcntAll.json"
        params = {"crtfc_key": self.key, "corp_code": corp_code,
                  "bsns_year": bsns_year, "reprt_code": reprt_code, "fs_div": fs_div}
        backoff = _BACKOFF_START
        reset_streak = 0
        for _ in range(_MAX_TRIES):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=25)
                self.calls += 1
            except requests.exceptions.ConnectionError:
                self.conn_resets += 1
                reset_streak += 1
                if reset_streak >= 3:
                    raise DartBlocked("연결 리셋 3연속 — opendart IP 차단으로 판단")
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

            reset_streak = 0
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
                raise DartQuotaExceeded("DART 일일 사용한도 초과(status=020)")
            if status == "800":  # 시스템 점검
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue
            return status, js

        self._bump("HTTP_FAIL")
        return "HTTP_FAIL", {}


def append_raw(path: str, payload: dict) -> int:
    """원본 응답을 gzip JSONL 에 append 하고 «줄 번호»(1-based)를 돌려준다.

    🔑 f2_raw 전례: DB 엔 7컬럼만 뽑혀 있었는데 원본엔 계정 2,461종이 있었다.
       원본을 남겼기 때문에 호출 0건으로 확장이 가능했다. 파싱은 틀릴 수 있다.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 0
    if os.path.exists(path):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for _ in fh:
                n += 1
    with gzip.open(path, "at", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return n + 1
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest tests/collectors/test_dart_financial_fetcher.py -v`
Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add collectors/dart_financial_fetcher.py tests/collectors/test_dart_financial_fetcher.py
git commit -m "feat(collectors): DART 재무 fetcher — 020 은 예외로 올려 조용한 빈 수집을 막는다"
```

---

## Task 4: 13지표 매핑 + `fn_financials_as_of` 뷰

**Files:**
- Create: `collectors/financial_metrics.py`
- Test: `tests/collectors/test_financial_metrics.py`

**Interfaces:**
- Consumes: `dart_financial_filings` · `dart_financial_accounts` (Task 2)
- Produces:
  - `METRIC_MAP: dict[str, list[str]]` — 지표명 → `account_id` 후보 리스트(우선순위 순)
  - `DDL_VIEW: str` — `CREATE OR REPLACE FUNCTION fn_financials_as_of(date) RETURNS TABLE(...)`
  - `ensure_view(conn) -> None`
  - `report_mapping_coverage(conn) -> dict` — `{"matched": int, "unmatched_stocks": list}`

- [ ] **Step 1: 매핑표를 «실측»으로 만든다 (구현 전 선행 작업)**

⚠️ 매핑을 추측으로 쓰면 안 된다. 이미 가진 원본에서 실제 `account_id` 빈도를 뽑는다.

```bash
python -c "
import gzip, json, collections, sys
c = collections.Counter()
with gzip.open('D:/archive/fund-pit-raw-20260813/f2_raw.jsonl.gz','rt',encoding='utf-8') as f:
    for line in f:
        rec = json.loads(line)
        for it in (rec.get('list') or []):
            c[(it.get('sj_div'), it.get('account_id'), it.get('account_nm'))] += 1
for k, n in c.most_common(120):
    print(n, k)
" > scratchpad/financials/account_freq.txt
```
결과를 보고 13지표 각각에 대응하는 `account_id` 후보를 **빈도순으로** 적는다.

- [ ] **Step 2: 실패하는 테스트 — as_of 대칭 단언 (스펙 테스트 #2·#3)**

```python
# tests/collectors/test_financial_metrics.py
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import financial_writer as w  # noqa: E402
from collectors import financial_metrics as fm  # noqa: E402

ORIG = {"rcept_no": "29999999000011", "fs_div": "CFS", "corp_code": "00000000",
        "stock_code": "TEST02", "bsns_year": "2026", "reprt_code": "11013",
        "rcept_dt": "2026-05-15", "is_amendment": False, "raw_path": None}
AMEND = dict(ORIG, rcept_no="29999999000012", rcept_dt="2026-06-30", is_amendment=True)


def _acct(rcept_no, amount):
    return [dict(rcept_no=rcept_no, fs_div="CFS", sj_div="BS",
                 account_id="ifrs-full_Assets", ord=1, account_nm="자산총계",
                 thstrm_amount=amount, thstrm_add_amount=None,
                 frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW")]


@pytest.fixture
def conn():
    with KisDbConnection.get_connection() as c:
        w.ensure_tables(c)
        fm.ensure_view(c)
        w.upsert_filing(c, ORIG);  w.upsert_accounts(c, _acct(ORIG["rcept_no"], 1000))
        w.upsert_filing(c, AMEND); w.upsert_accounts(c, _acct(AMEND["rcept_no"], 2000))
        yield c
        with c.cursor() as cur:
            cur.execute("DELETE FROM dart_financial_accounts WHERE rcept_no IN %s",
                        ((ORIG["rcept_no"], AMEND["rcept_no"]),))
            cur.execute("DELETE FROM dart_financial_filings WHERE stock_code='TEST02'")
        c.commit()


def _assets_at(conn, as_of):
    with conn.cursor() as cur:
        cur.execute("SELECT total_assets FROM fn_financials_as_of(%s) WHERE stock_code='TEST02'",
                    (as_of,))
        rows = cur.fetchall()
    return rows


def test_as_of_symmetric_before_and_after_amendment(conn):
    """🔑 대칭 단언 — 한쪽만 물으면 판별력이 0이다.
    정정 «전»에는 원본 값이, «후»에는 정정 값이 나와야 하고 «둘이 달라야» 한다."""
    before = _assets_at(conn, "2026-06-01")
    after = _assets_at(conn, "2026-07-01")
    assert before == [(1000,)], f"정정 전에 정정본이 보인다: {before}"
    assert after == [(2000,)], f"정정 후에 정정본이 안 보인다: {after}"
    assert before != after, "정정 전후가 같다 — 뷰가 as_of 를 안 쓰고 있다"


def test_no_lookahead_before_first_filing(conn):
    """🔴 최초 접수일 이전에는 «아무것도» 보이면 안 된다."""
    assert _assets_at(conn, "2026-05-14") == []
```

- [ ] **Step 3: 실패를 확인한다**

Run: `python -m pytest tests/collectors/test_financial_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collectors.financial_metrics'`

- [ ] **Step 4: 구현**

```python
# collectors/financial_metrics.py
"""account_id → 13지표 매핑 + as_of 기준 Wide 파생 함수.

🔴 as_of 필터가 이 파일의 존재 이유다. rcept_dt <= as_of 를 빼면
   백테스트가 «그날 몰랐던 재무»를 본다(look-ahead).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

# 지표 → account_id 후보(우선순위 순). Step 1 의 실측 빈도로 채운다.
# ⚠️ ifrs 표준 50.1% · dart_ 확장 33.6% · 표준계정코드 미사용 16.3% 라
#    한 지표에 여러 account_id 가 대응한다.
METRIC_MAP = {
    "total_assets":      ["ifrs-full_Assets"],
    "total_equity":      ["ifrs-full_Equity"],
    "issued_capital":    ["ifrs-full_IssuedCapital"],
    "total_liabilities": ["ifrs-full_Liabilities"],
    "revenue":           ["ifrs-full_Revenue", "ifrs-full_RevenueFromContractsWithCustomers"],
    "operating_income":  ["dart_OperatingIncomeLoss"],
    "net_income":        ["ifrs-full_ProfitLoss"],
    "interest_expense":  ["ifrs-full_InterestExpense"],
    "finance_costs":     ["ifrs-full_FinanceCosts"],
    "interest_paid_cf":  ["ifrs-full_InterestPaidClassifiedAsOperatingActivities"],
    "cf_operating":      ["ifrs-full_CashFlowsFromUsedInOperatingActivities"],
    "cf_investing":      ["ifrs-full_CashFlowsFromUsedInInvestingActivities"],
    "cf_financing":      ["ifrs-full_CashFlowsFromUsedInFinancingActivities"],
}


def _metric_sql(name: str) -> str:
    ids = ", ".join("'%s'" % i.replace("'", "''") for i in METRIC_MAP[name])
    # 분기 IS 는 thstrm_add_amount(누계)를 우선한다 — 당분기만 쓰면 연간과 비교가 안 된다.
    return (f"max(CASE WHEN a.account_id IN ({ids}) "
            f"THEN COALESCE(a.thstrm_add_amount, a.thstrm_amount) END) AS {name}")


def _build_view_sql() -> str:
    metrics = ",\n        ".join(_metric_sql(k) for k in METRIC_MAP)
    cols = ",\n    ".join(f"{k} bigint" for k in METRIC_MAP)
    return f"""
CREATE OR REPLACE FUNCTION fn_financials_as_of(p_as_of date)
RETURNS TABLE (
    stock_code varchar(20),
    bsns_year  varchar(4),
    reprt_code varchar(5),
    rcept_no   varchar(14),
    rcept_dt   date,
    {cols}
) AS $$
    WITH latest AS (
        SELECT DISTINCT ON (f.stock_code, f.bsns_year, f.reprt_code)
               f.rcept_no, f.fs_div, f.stock_code, f.bsns_year, f.reprt_code, f.rcept_dt
        FROM dart_financial_filings f
        WHERE f.rcept_dt IS NOT NULL AND f.rcept_dt <= p_as_of
        ORDER BY f.stock_code, f.bsns_year, f.reprt_code, f.rcept_dt DESC, f.rcept_no DESC
    )
    SELECT l.stock_code, l.bsns_year, l.reprt_code, l.rcept_no, l.rcept_dt,
        {metrics}
    FROM latest l
    JOIN dart_financial_accounts a
      ON a.rcept_no = l.rcept_no AND a.fs_div = l.fs_div
    GROUP BY l.stock_code, l.bsns_year, l.reprt_code, l.rcept_no, l.rcept_dt
$$ LANGUAGE sql STABLE;
"""


DDL_VIEW = _build_view_sql()


def ensure_view(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL_VIEW)
    conn.commit()
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python -m pytest tests/collectors/test_financial_metrics.py -v`
Expected: 2 passed

- [ ] **Step 6: 매핑 커버리지 리포터 추가**

```python
def report_mapping_coverage(conn) -> dict:
    """🔴 비율만 남기지 말 것 — «어느 종목이 빠졌는지» 목록으로 남긴다.
    비율은 어느 종목을 고쳐야 하는지 말해주지 않는다."""
    all_ids = [i for ids in METRIC_MAP.values() for i in ids]
    with conn.cursor() as cur:
        cur.execute("SELECT count(DISTINCT stock_code) FROM dart_financial_filings")
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT DISTINCT f.stock_code FROM dart_financial_filings f "
            "WHERE NOT EXISTS (SELECT 1 FROM dart_financial_accounts a "
            "  WHERE a.rcept_no=f.rcept_no AND a.fs_div=f.fs_div AND a.account_id = ANY(%s)) "
            "ORDER BY 1", (all_ids,))
        unmatched = [r[0] for r in cur.fetchall()]
    if unmatched:
        logger.warning("[financials] 13지표 매핑 실패 종목 %d/%d — 목록은 반환값 참조",
                       len(unmatched), total)
    return {"total_stocks": total, "unmatched_count": len(unmatched),
            "unmatched_stocks": unmatched}
```

- [ ] **Step 7: 커밋**

```bash
git add collectors/financial_metrics.py tests/collectors/test_financial_metrics.py
git commit -m "feat(collectors): as_of 기준 Wide 파생 — 정정 전후 대칭 단언으로 look-ahead 를 막는다"
```

---

## Task 5: `kis_financial_fetcher.py`

**Files:**
- Create: `collectors/kis_financial_fetcher.py`
- Test: `tests/collectors/test_kis_financial_fetcher.py`

**Interfaces:**
- Consumes: `api.kis_financial_api.get_financial_ratio` · `financial_writer.upsert_kis_ratio` (Task 2)
- Produces: `fetch_quarterly_ratio(stock_code: str) -> list[dict]` — `upsert_kis_ratio` 가 먹는 행 dict 리스트

- [ ] **Step 1: 실패하는 테스트 — 🔴 PIT 소스 격리 (스펙 테스트 #7)**

```python
# tests/collectors/test_kis_financial_fetcher.py
import inspect
from collectors import kis_financial_fetcher as k
from collectors import financial_metrics as fm


def test_quarterly_div_cls_is_1(monkeypatch):
    """div_cls 기본값은 '0'(연간)이다. 분기를 받으려면 '1' 을 «명시»해야 한다."""
    seen = {}

    def fake(code, div_cls="0", tr_cont=""):
        seen["div_cls"] = div_cls
        return []

    monkeypatch.setattr(k, "get_financial_ratio", fake)
    k.fetch_quarterly_ratio("005930")
    assert seen["div_cls"] == "1"


def test_pit_view_does_not_reference_kis_table():
    """🔴 KIS 는 접수일이 없어 PIT 을 못 준다.
    PIT 조회 경로가 이 테이블을 «참조조차» 하면 안 된다 — 주석이 아니라 구조로 막는다."""
    assert "kis_financial_ratio" not in fm.DDL_VIEW
    assert "kis_financial_ratio" not in inspect.getsource(fm)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/collectors/test_kis_financial_fetcher.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
# collectors/kis_financial_fetcher.py
"""KIS 재무비율(분기) → kis_financial_ratio 행.

🔴 이 데이터에는 접수일이 없다 ⇒ PIT 앵커가 없다 ⇒ PIT 조회에 쓰면 안 된다.
   용도는 «교차검증 전용»이다 — DART 원시계정으로 계산한 비율과 대조한다.
   봉쇄는 3겹: ①날짜형 컬럼 없음 ②PIT 경로가 참조 안 함 ③테스트가 ②를 고정.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.kis_financial_api import get_financial_ratio  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


def fetch_quarterly_ratio(stock_code: str) -> list:
    """div_cls='1'(분기) 명시 조회 → upsert_kis_ratio 용 행 리스트."""
    entries = get_financial_ratio(stock_code, div_cls="1")
    rows = []
    for e in entries or []:
        if not e.statement_ym:
            continue
        rows.append({
            "stock_code": stock_code,
            "stac_yymm": e.statement_ym,
            "div_cls": "1",
            "roe_value": e.roe_value,
            "per": e.per,
            "eps": e.eps,
            "sps": e.sps,
            "bps": e.bps,
            "reserve_ratio": e.reserve_ratio,
            "liability_ratio": e.liability_ratio,
            "sales_growth": e.sales_growth,
            "operating_income_growth": e.operating_income_growth,
            "net_income_growth": e.net_income_growth,
            "raw_json": json.dumps(e.raw, ensure_ascii=False),
        })
    return rows
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest tests/collectors/test_kis_financial_fetcher.py -v`
Expected: 2 passed

- [ ] **Step 5: 커밋**

```bash
git add collectors/kis_financial_fetcher.py tests/collectors/test_kis_financial_fetcher.py
git commit -m "feat(collectors): KIS 분기비율 fetcher — PIT 경로 참조 금지를 테스트로 고정"
```

---

## Task 6: `financial_collector.py` (창 판정 · 수집 · reconcile · 백필)

**Files:**
- Create: `collectors/financial_collector.py`
- Test: `tests/collectors/test_financial_collector.py`

**Interfaces:**
- Consumes: Task 1~5 전부
- Produces:
  - `WINDOWS: dict[str, tuple[tuple[int,int], tuple[int,int]]]` — `reprt_code → ((시작월,일),(끝월,일))`
  - `active_reports(d: date) -> list[str]` — 그 날짜에 열려 있는 `reprt_code` 목록
  - `collect_financials(target_date: str = None, daily_cap: int = 800) -> dict`
  - `reconcile_financials(trade_date: str) -> dict`
  - `backfill(year: str, reprt_code: str, interval: float = 0.34, cap: int = None) -> dict`

- [ ] **Step 1: 실패하는 테스트 — 창 판정과 창 밖 no-op (스펙 테스트 #4)**

```python
# tests/collectors/test_financial_collector.py
from datetime import date
import pytest
from collectors import financial_collector as c


def test_window_boundaries_are_business_dates():
    """🔴 초안이 08/15 로 잡았다가 «토요일(광복절)»이라 EOD 가 안 도는 걸 놓쳤다.
    합의된 창은 08/17 이다."""
    assert c.active_reports(date(2026, 8, 16)) == []      # 창 열리기 전
    assert c.active_reports(date(2026, 8, 17)) == ["11012"]  # 반기 창 첫날
    assert c.active_reports(date(2026, 9, 20)) == ["11012"]  # 마지막날 포함
    assert c.active_reports(date(2026, 9, 21)) == []      # 창 밖
    assert c.active_reports(date(2026, 6, 20)) == ["11013"]  # 1Q 창
    assert c.active_reports(date(2026, 7, 1)) == []       # 창 사이 공백


def test_out_of_window_makes_zero_dart_calls(monkeypatch):
    """창 밖이면 DART 를 «한 번도» 부르지 않아야 한다."""
    calls = {"n": 0}

    class FakeFetcher:
        def __init__(self, *a, **kw):
            self.calls, self.status_counts, self.conn_resets = 0, {}, 0

        def fetch(self, *a, **kw):
            calls["n"] += 1
            return "000", {"list": []}

    monkeypatch.setattr(c, "DartFinancialFetcher", FakeFetcher)
    monkeypatch.setattr(c, "_load_dart_key", lambda: "dummy")
    out = c.collect_financials("2026-07-01")   # 창 사이 공백
    assert calls["n"] == 0
    assert out["skipped"] == "out_of_window"


def test_missing_key_skips_without_blocking(monkeypatch):
    """키가 없으면 EOD 를 막지 않고 스킵한다 (corp_events 전례)."""
    monkeypatch.setattr(c, "_load_dart_key", lambda: "")
    out = c.collect_financials("2026-08-17")
    assert out["skipped"] == "no_dart_key"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/collectors/test_financial_collector.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 창 판정 + 스킵 경로 구현**

```python
# collectors/financial_collector.py
"""재무 수집 오케스트레이터 — DART as-filed 원장 + KIS 분기비율.

usage:
  python -m collectors.financial_collector                                  # 창 기반 증분
  python -m collectors.financial_collector --backfill --year 2026 --reprt 11013
  python -m collectors.financial_collector --reconcile-only 2026-08-17
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors.dart_corp_code import load_map  # noqa: E402
from collectors.dart_financial_fetcher import (  # noqa: E402
    DartFinancialFetcher, DartQuotaExceeded, DartBlocked, append_raw)
from collectors.kis_financial_fetcher import fetch_quarterly_ratio  # noqa: E402
from collectors import financial_writer as w  # noqa: E402
from collectors import financial_metrics as fm  # noqa: E402
from collectors.daily_collector import load_universe  # noqa: E402
from utils.korean_time import now_kst  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

# 2026-08-12 합의 창. 법정기한 +3일 여유.
# ⚠️ 창 시작은 반드시 영업일이어야 한다 — 08/15 는 토요일(광복절)이라 EOD 가 안 돈다.
WINDOWS = {
    "11011": ((4, 3), (5, 10)),    # 사업보고서 (기한 3/31)
    "11013": ((5, 18), (6, 20)),   # 1Q       (기한 5/15)
    "11012": ((8, 17), (9, 20)),   # 반기      (기한 8/14)
    "11014": ((11, 17), (12, 20)),  # 3Q       (기한 11/14)
}

RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scratchpad", "financials")


def active_reports(d: date) -> list:
    """그 날짜에 열려 있는 reprt_code 목록 (창 경계 포함)."""
    out = []
    for code, ((bm, bd), (em, ed)) in WINDOWS.items():
        if (d.month, d.day) >= (bm, bd) and (d.month, d.day) <= (em, ed):
            out.append(code)
    return sorted(out)


def _to_iso(s: str) -> str:
    return s if "-" in s else f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _parse_dart_key_from_lines(lines) -> str:
    """정확히 'OPENDART_API_KEY' 만 매칭 (corp_events_collector.py 와 동일 규약).
    startswith 로 하면 'OPENDART_API_KEY_BACKUP' 같은 변형 키를 잘못 집는다."""
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == "OPENDART_API_KEY":
            return v.strip().strip('"').strip("'")
    return ""


def _load_dart_key() -> str:
    key = (os.getenv("OPENDART_API_KEY") or "").strip()
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            return _parse_dart_key_from_lines(f)
    except OSError:
        return ""
```

- [ ] **Step 4: `collect_financials` 본체**

```python
def _pending_targets(conn, codes, bsns_year: str, reprt_code: str) -> list:
    """아직 안 받은 (stock_code, corp_code). 이미 적재분과 «013 확정분»을 뺀다.

    🔑 013(무자료)을 기록하지 않으면 매일 같은 것을 두드린다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT stock_code FROM dart_financial_filings "
            "WHERE bsns_year=%s AND reprt_code=%s", (bsns_year, reprt_code))
        done = {r[0] for r in cur.fetchall()}
        cur.execute(
            "SELECT stock_code FROM dart_financial_nodata "
            "WHERE bsns_year=%s AND reprt_code=%s", (bsns_year, reprt_code))
        nodata = {r[0] for r in cur.fetchall()}
    return [(sc, cc) for sc, cc in codes if sc not in done and sc not in nodata]


def collect_financials(target_date: str = None, daily_cap: int = 800) -> dict:
    """창 안이면 미수집분을 daily_cap(=DART 호출 기준)까지 수집. 창 밖이면 no-op."""
    key = _load_dart_key()
    if not key:
        logger.warning("[financials] OPENDART_API_KEY 미설정 — 수집 스킵(EOD 비차단)")
        return {"skipped": "no_dart_key", "dart_calls": 0, "filings": 0, "accounts": 0}

    d = date.fromisoformat(_to_iso(target_date)) if target_date else now_kst().date()
    reports = active_reports(d)
    if not reports:
        logger.info("[financials] %s 는 수집 창 밖 — no-op", d)
        return {"skipped": "out_of_window", "dart_calls": 0, "filings": 0, "accounts": 0}

    bsns_year = str(d.year)
    fetcher = DartFinancialFetcher(key)
    n_filings = n_accounts = n_kis = 0
    quota_hit = False
    raw_path = os.path.join(RAW_DIR, f"dart_{d.strftime('%Y%m%d')}.jsonl.gz")

    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        fm.ensure_view(conn)
        cmap = load_map(conn)
        universe = load_universe(conn)
        codes = [(sc, cmap[sc]) for sc in universe if sc in cmap]

        for reprt_code in reports:
            targets = _pending_targets(conn, codes, bsns_year, reprt_code)
            logger.info("[financials] %s/%s 대상 %d종목 (cap %d)",
                        bsns_year, reprt_code, len(targets), daily_cap)
            for stock_code, corp_code in targets:
                if fetcher.calls >= daily_cap:
                    logger.info("[financials] 일일 상한 %d 도달 — 남은 %d종목은 내일",
                                daily_cap, len(targets))
                    break
                try:
                    got = _fetch_and_store(conn, fetcher, raw_path,
                                           stock_code, corp_code, bsns_year, reprt_code)
                except DartQuotaExceeded:
                    logger.warning("[financials] DART 일일 한도 초과 — 중단(체크포인트는 DB 자체)")
                    quota_hit = True
                    break
                except DartBlocked as e:
                    logger.error("[financials] opendart 차단 — 중단: %s", e)
                    quota_hit = True
                    break
                n_filings += got[0]
                n_accounts += got[1]
            if quota_hit:
                break

        # KIS 는 DART 한도와 무관하다. DART 가 막혀도 돌린다.
        for stock_code, _ in codes[:daily_cap]:
            try:
                rows = fetch_quarterly_ratio(stock_code)
            except Exception as e:  # noqa: BLE001 — 종목 하나 실패가 전체를 막지 않는다
                logger.debug("[financials] KIS 비율 실패 %s: %s", stock_code, e)
                continue
            n_kis += w.upsert_kis_ratio(conn, rows)

        _recompute_amendment_flags(conn)

    out = {"reports": reports, "dart_calls": fetcher.calls,
           "status_counts": fetcher.status_counts, "filings": n_filings,
           "accounts": n_accounts, "kis_rows": n_kis, "quota_hit": quota_hit}
    logger.info("[financials] %s", out)
    return out


def _fetch_and_store(conn, fetcher, raw_path, stock_code, corp_code, bsns_year, reprt_code):
    """CFS 시도 → 013 이면 OFS 재시도. 반환 (filings, accounts)."""
    for fs_div in ("CFS", "OFS"):
        status, payload = fetcher.fetch(corp_code, bsns_year, reprt_code, fs_div)
        if status == "013":
            continue
        if status != "000":
            logger.warning("[financials] %s %s/%s/%s status=%s",
                           stock_code, bsns_year, reprt_code, fs_div, status)
            return 0, 0
        line_no = append_raw(raw_path, payload)
        filing, accounts = w.rows_from_dart_response(payload, stock_code, fs_div)
        if filing is None:
            return 0, 0
        filing["raw_path"] = f"{os.path.basename(raw_path)}#L{line_no}"
        filing["rcept_dt"] = _rcept_dt_from_no(filing["rcept_no"])
        w.upsert_filing(conn, filing)
        return 1, w.upsert_accounts(conn, accounts)

    # CFS·OFS 둘 다 013 = 무자료 확정. 기록해서 내일 다시 안 두드린다.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dart_financial_nodata (stock_code, bsns_year, reprt_code, checked_at) "
            "VALUES (%s,%s,%s, now()) ON CONFLICT DO NOTHING",
            (stock_code, bsns_year, reprt_code))
    conn.commit()
    return 0, 0


def _rcept_dt_from_no(rcept_no: str):
    """접수번호 앞 8자리가 접수일이다 (DART 규약). 형식이 어긋나면 None."""
    s = (rcept_no or "").strip()
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None


def _recompute_amendment_flags(conn) -> None:
    """is_amendment 를 rcept_dt 순서로 재계산.

    ⚠️ 파생값이다. 옛 접수건을 뒤늦게 받으면 뒤집히므로 «매번 다시» 계산한다.
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE dart_financial_filings f SET is_amendment = sub.amend
            FROM (
                SELECT rcept_no, fs_div,
                       (row_number() OVER (PARTITION BY stock_code, bsns_year, reprt_code
                                           ORDER BY rcept_dt, rcept_no) > 1) AS amend
                FROM dart_financial_filings WHERE rcept_dt IS NOT NULL
            ) sub
            WHERE f.rcept_no = sub.rcept_no AND f.fs_div = sub.fs_div
              AND f.is_amendment IS DISTINCT FROM sub.amend
        """)
    conn.commit()
```

⚠️ 이 코드는 `dart_financial_nodata` 테이블을 쓴다. **Step 5 를 먼저 적용하지 않으면 실행이 안 된다** —
Step 4 는 코드 작성만이고, 실행 검증은 Step 6 에서 한다.

- [ ] **Step 5: `dart_financial_nodata` DDL 추가**

`collectors/financial_writer.py` 에 추가하고 `ensure_tables` 에서 실행:

```python
DDL_NODATA = """
CREATE TABLE IF NOT EXISTS dart_financial_nodata (
    stock_code varchar(20) NOT NULL,
    bsns_year  varchar(4)  NOT NULL,
    reprt_code varchar(5)  NOT NULL,
    checked_at timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_code, bsns_year, reprt_code)
)
"""
```
`ensure_tables` 안에 `cur.execute(DDL_NODATA)` 한 줄 추가.

- [ ] **Step 6: 테스트 실행**

Run: `python -m pytest tests/collectors/test_financial_collector.py -v`
Expected: 3 passed

- [ ] **Step 7: `reconcile_financials` — 🔴 진척률 게이트**

```python
def reconcile_financials(trade_date: str) -> dict:
    """창 밖은 PASS(out_of_window). 창 안은 도달성 AND 진척률.

    🔑 도달성만 보면 «호출은 성공하는데 잔량이 안 줄어드는» 상태를 못 잡는다.
       일봉 결손 49,252행이 2년 5개월간 무경보였던 게 정확히 그 형태다.
    """
    d = date.fromisoformat(_to_iso(trade_date))
    reports = active_reports(d)
    if not reports:
        _write_recon(trade_date, 0, "PASS")
        return {"trade_date": trade_date, "verdict": "PASS", "reason": "out_of_window"}

    key = _load_dart_key()
    if not key:
        _write_recon(trade_date, 0, "WARN")
        return {"trade_date": trade_date, "verdict": "WARN", "reason": "no_dart_key"}

    bsns_year = str(d.year)
    with KisDbConnection.get_connection() as conn:
        cmap = load_map(conn)
        universe = load_universe(conn)
        codes = [(sc, cmap[sc]) for sc in universe if sc in cmap]
        remaining = sum(len(_pending_targets(conn, codes, bsns_year, rc)) for rc in reports)
        # 최근 3영업일 잔량이 «전혀» 안 줄었으면 FAIL
        with conn.cursor() as cur:
            cur.execute(
                "SELECT new_rows FROM collection_reconciliation "
                "WHERE dataset='financials' AND trade_date < %s "
                "ORDER BY trade_date DESC LIMIT 3", (trade_date,))
            prev = [r[0] for r in cur.fetchall()]

    stalled = len(prev) == 3 and remaining > 0 and all(p == remaining for p in prev)
    verdict = "FAIL" if stalled else "PASS"
    if stalled:
        logger.error("[financials] 진척 정지 — 잔량 %d 가 3회 연속 동일. "
                     "호출은 성공하는데 데이터가 안 들어오고 있다", remaining)
    _write_recon(trade_date, remaining, verdict)
    return {"trade_date": trade_date, "verdict": verdict,
            "remaining": remaining, "prev": prev}


def _write_recon(trade_date: str, remaining: int, verdict: str) -> None:
    passed = 1.0 if verdict == "PASS" else 0.0
    with KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO collection_reconciliation "
                "(trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, "
                " coverage, verdict) VALUES (%s,'financials',0,%s,0,%s,%s,%s) "
                "ON CONFLICT (trade_date, dataset) DO UPDATE SET "
                "new_rows=EXCLUDED.new_rows, value_match_rate=EXCLUDED.value_match_rate, "
                "coverage=EXCLUDED.coverage, verdict=EXCLUDED.verdict",
                (trade_date, remaining, passed, passed, verdict))
        conn.commit()
```

- [ ] **Step 8: 백필 + CLI**

```python
def backfill(year: str, reprt_code: str, interval: float = 0.34, cap: int = None) -> dict:
    """창을 무시하고 미수집분만 채운다. 수동 실행 전용.

    ⚠️ 평일 16:00 EOD 와 겹치면 안 된다 — corp_events_collector 가 같은 호스트다.
    """
    key = _load_dart_key()
    if not key:
        return {"skipped": "no_dart_key"}
    fetcher = DartFinancialFetcher(key, min_interval=interval)
    raw_path = os.path.join(RAW_DIR, f"dart_backfill_{year}_{reprt_code}.jsonl.gz")
    n_f = n_a = 0
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        fm.ensure_view(conn)
        cmap = load_map(conn)
        codes = [(sc, cmap[sc]) for sc in load_universe(conn) if sc in cmap]
        targets = _pending_targets(conn, codes, year, reprt_code)
        logger.info("[backfill] %s/%s 대상 %d종목 interval=%.2f", year, reprt_code,
                    len(targets), interval)
        for i, (sc, cc) in enumerate(targets, 1):
            if cap and fetcher.calls >= cap:
                logger.warning("[backfill] cap %d 도달 — 남은 %d종목 미수집",
                               cap, len(targets) - i + 1)
                break
            try:
                f_, a_ = _fetch_and_store(conn, fetcher, raw_path, sc, cc, year, reprt_code)
            except (DartQuotaExceeded, DartBlocked) as e:
                logger.warning("[backfill] 중단(%s) — 남은 %d종목. 자정 이후 재실행",
                               type(e).__name__, len(targets) - i + 1)
                break
            n_f += f_
            n_a += a_
            if i % 100 == 0:
                logger.info("[backfill] %d/%d calls=%d", i, len(targets), fetcher.calls)
        _recompute_amendment_flags(conn)
    return {"year": year, "reprt": reprt_code, "calls": fetcher.calls,
            "status_counts": fetcher.status_counts, "filings": n_f, "accounts": n_a}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--daily-cap", type=int, default=800)
    ap.add_argument("--reconcile-only", default=None)
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--year", default=None)
    ap.add_argument("--reprt", default=None)
    ap.add_argument("--interval", type=float, default=0.34)
    ap.add_argument("--cap", type=int, default=None)
    args = ap.parse_args()
    if args.reconcile_only:
        print(reconcile_financials(args.reconcile_only))
    elif args.backfill:
        if not (args.year and args.reprt):
            ap.error("--backfill 은 --year 와 --reprt 가 필요하다")
        print(backfill(args.year, args.reprt, args.interval, args.cap))
    else:
        print(collect_financials(args.date, args.daily_cap))
```

- [ ] **Step 9: 🔴 정정 스윕 (스펙 §6.3 — 창만으로는 정정·지연공시를 놓친다)**

실측: 3월 외 접수 **16.1%** · 지연 **p99 735일**. 2019 사업연도 건이 2026-04-29 에 접수된 예가 실재한다.
⇒ 창 기반 증분만으로는 **구조적으로 놓친다.**

```python
def sweep_amendments(lookback_days: int = 14, cap: int = 200) -> dict:
    """최근 lookback_days 의 정정보고서를 list.json 으로 찾아 그 접수건만 재수집.

    창과 «무관하게» 돈다. 주 1회 호출 상정.
    🔑 창 기반 증분은 정정·지연공시를 구조적으로 놓친다 —
       3월 외 접수 16.1%, 지연 p99 735일.
    """
    import requests
    key = _load_dart_key()
    if not key:
        return {"skipped": "no_dart_key"}

    end = now_kst().date()
    bgn = end - timedelta(days=max(1, min(lookback_days, 90)))
    fetcher = DartFinancialFetcher(key)
    raw_path = os.path.join(RAW_DIR, f"dart_sweep_{end.strftime('%Y%m%d')}.jsonl.gz")

    items, page, total_page = [], 1, 1
    while page <= total_page and page <= 100:
        r = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=15, params={
            "crtfc_key": key, "bgn_de": bgn.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"), "pblntf_ty": "A",  # A = 정기공시
            "page_count": 100, "page_no": page})
        r.encoding = "utf-8"
        js = r.json()
        st = js.get("status")
        if st == "013":
            break
        if st != "000":
            logger.warning("[sweep] list.json status=%s msg=%s", st, js.get("message"))
            break
        total_page = int(js.get("total_page") or 1)
        items.extend(js.get("list") or [])
        page += 1
    # 무징후 절단 금지
    if total_page > 100:
        logger.warning("[sweep] 페이지 절단: total_page=%d > 100 — 창을 좁힐 것(누락 발생)",
                       total_page)

    # 정정본만: report_nm 에 '기재정정' 이 붙는다
    targets = []
    for it in items:
        nm = it.get("report_nm", "")
        sc = (it.get("stock_code") or "").strip()
        if "정정" not in nm or not sc:
            continue
        rc = _reprt_code_from_report_nm(nm)
        yr = _bsns_year_from_report_nm(nm)
        if rc and yr:
            targets.append((sc, rc, yr))

    n_f = n_a = 0
    with KisDbConnection.get_connection() as conn:
        w.ensure_tables(conn)
        cmap = load_map(conn)
        for sc, rc, yr in targets[:cap]:
            if sc not in cmap:
                continue
            try:
                f_, a_ = _fetch_and_store(conn, fetcher, raw_path, sc, cmap[sc], yr, rc)
            except (DartQuotaExceeded, DartBlocked) as e:
                logger.warning("[sweep] 중단(%s)", type(e).__name__)
                break
            n_f += f_
            n_a += a_
        _recompute_amendment_flags(conn)
    logger.info("[sweep] 정정 후보 %d건 → filings=%d accounts=%d calls=%d",
                len(targets), n_f, n_a, fetcher.calls)
    return {"candidates": len(targets), "filings": n_f, "accounts": n_a,
            "calls": fetcher.calls}


def _reprt_code_from_report_nm(nm: str):
    """'[기재정정]분기보고서 (2026.03)' → 11013. 판별 불가면 None(추측하지 않는다)."""
    if "사업보고서" in nm:
        return "11011"
    if "반기보고서" in nm:
        return "11012"
    if "분기보고서" not in nm:
        return None
    # 분기보고서는 1Q/3Q 를 괄호 안 월로 가른다: (YYYY.03)=1Q, (YYYY.09)=3Q
    import re as _re
    m = _re.search(r"\((\d{4})\.(\d{2})\)", nm)
    if not m:
        return None
    return {"03": "11013", "09": "11014"}.get(m.group(2))


def _bsns_year_from_report_nm(nm: str):
    import re as _re
    m = _re.search(r"\((\d{4})\.\d{2}\)", nm)
    return m.group(1) if m else None
```

CLI 에 플래그 추가:
```python
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--sweep-lookback", type=int, default=14)
```
그리고 분기 처리에 한 갈래 추가 (`--reconcile-only` 다음):
```python
    elif args.sweep:
        print(sweep_amendments(args.sweep_lookback))
```

**주 1회 자동 실행** — `collect_financials` 끝에 붙인다. EOD 등록은 그대로 2줄로 유지된다.

```python
    # 주 1회(월요일) 정정 스윕. 창과 무관하게 돈다 — 정정·지연공시는 창 밖에도 온다.
    sweep = None
    if d.weekday() == 0:
        try:
            sweep = sweep_amendments()
        except Exception as e:  # noqa: BLE001 — 스윕 실패가 본 수집을 막지 않는다
            logger.warning("[financials] 정정 스윕 실패(비차단): %s", e)
            sweep = {"error": str(e)}
    out["sweep"] = sweep
```
⚠️ `out` dict 를 만든 «뒤», `return out` «앞»에 넣어야 한다.

테스트 1개 추가:
```python
def test_sweep_runs_only_on_monday(monkeypatch):
    """스윕은 주 1회다. 매일 돌면 창 안에서 DART 예산을 두 배로 먹는다."""
    seen = []
    monkeypatch.setattr(c, "_load_dart_key", lambda: "")     # 본 수집은 즉시 스킵
    monkeypatch.setattr(c, "sweep_amendments", lambda *a: seen.append(1) or {})
    c.collect_financials("2026-08-18")                        # 화요일
    assert seen == []
    # 월요일이라도 키가 없으면 본 수집 스킵이 먼저라 스윕도 안 돈다 — 그게 맞다.
    # 키가 있을 때의 월요일 동작은 Step 6 의 FakeFetcher 경로로 확인한다.
    assert c.active_reports(__import__("datetime").date(2026, 8, 17)) == ["11012"]
```

- [ ] **Step 10: 누락 테스트 2개 (스펙 테스트 #5·#6)**

```python
# tests/collectors/test_financial_collector.py 에 추가
def test_report_nm_to_reprt_code_no_guessing():
    """판별 불가한 공시명에 «추측»으로 코드를 붙이면 안 된다 — 엉뚱한 분기에 적재된다."""
    assert c._reprt_code_from_report_nm("[기재정정]분기보고서 (2026.03)") == "11013"
    assert c._reprt_code_from_report_nm("[기재정정]분기보고서 (2026.09)") == "11014"
    assert c._reprt_code_from_report_nm("[기재정정]반기보고서 (2026.06)") == "11012"
    assert c._reprt_code_from_report_nm("[기재정정]사업보고서 (2025.12)") == "11011"
    assert c._reprt_code_from_report_nm("분기보고서") is None          # 월 없음
    assert c._reprt_code_from_report_nm("[기재정정]주요사항보고서") is None
```

```python
# tests/collectors/test_financial_writer_db.py 에 추가
def test_nodata_is_excluded_from_next_run(conn):
    """🔴 스펙 테스트 #5 — 013(무자료) 확정분을 다음 실행에서 다시 두드리면 안 된다."""
    from collectors import financial_collector as fc
    with conn.cursor() as cur:
        cur.execute("INSERT INTO dart_financial_nodata "
                    "(stock_code, bsns_year, reprt_code) VALUES ('TEST03','2026','11013') "
                    "ON CONFLICT DO NOTHING")
    conn.commit()
    codes = [("TEST03", "00000001"), ("TEST04", "00000002")]
    pending = fc._pending_targets(conn, codes, "2026", "11013")
    assert [p[0] for p in pending] == ["TEST04"], "013 확정분이 다시 대상에 들어왔다"
    with conn.cursor() as cur:
        cur.execute("DELETE FROM dart_financial_nodata WHERE stock_code='TEST03'")
    conn.commit()


def test_quota_abort_leaves_existing_rows_intact(conn):
    """🔴 스펙 테스트 #6 — 한도 초과로 중단돼도 이미 적재된 행은 무손상이어야 한다."""
    from collectors.dart_financial_fetcher import DartQuotaExceeded
    w.upsert_filing(conn, ORIG)
    w.upsert_accounts(conn, [dict(rcept_no=ORIG["rcept_no"], fs_div="CFS", sj_div="BS",
                                  account_id="ifrs-full_Assets", ord=1, account_nm="자산총계",
                                  thstrm_amount=1000, thstrm_add_amount=None,
                                  frmtrm_amount=None, bfefrmtrm_amount=None, currency="KRW")])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dart_financial_accounts WHERE rcept_no=%s",
                    (ORIG["rcept_no"],))
        before = cur.fetchone()[0]
    try:
        raise DartQuotaExceeded("simulated")
    except DartQuotaExceeded:
        pass
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dart_financial_accounts WHERE rcept_no=%s",
                    (ORIG["rcept_no"],))
        assert cur.fetchone()[0] == before, "중단이 기적재분을 훼손했다"
```

- [ ] **Step 11: 전체 테스트 + 커밋**

Run: `python -m pytest tests/collectors/ -v`
Expected: 기존 테스트 전부 + 신규 통과

```bash
git add collectors/financial_collector.py collectors/financial_writer.py tests/collectors/test_financial_collector.py tests/collectors/test_financial_writer_db.py
git commit -m "feat(collectors): 재무 수집 오케스트레이터 — 창 밖 no-op·013 확정 기록·정정 스윕·진척률 게이트"
```

---

## Task 7: EOD 등록 (라이브 2줄)

**Files:**
- Modify: `collectors/eod_collection.py:11-18` (import) · `:32-56` (호출)
- Test: `tests/collectors/test_eod_collection.py` (기존 파일에 추가)

**Interfaces:**
- Consumes: `collect_financials` · `reconcile_financials` (Task 6)
- Produces: `run_data_collection()` 반환 dict 에 `"financials"` 키

- [ ] **Step 1: 실패하는 테스트 — 🔑 진입점 «실호출» (스펙 테스트 #10)**

```python
# tests/collectors/test_eod_collection.py 에 추가
def test_run_data_collection_actually_calls_financials(monkeypatch):
    """🔑 소스 문자열 단언은 죽은 경로에서도 통과한 전례가 있다
    (9b82eec 의 **kwargs 삼킴 · 8238f91 의 순서 역전).
    배선은 «실제로 돌려서» 단언한다."""
    from collectors import eod_collection as eod
    called = []
    for name in ("collect_daily", "collect_minute", "collect_index",
                 "collect_stock_market", "collect_foreign_flow", "collect_corp_events"):
        monkeypatch.setattr(eod, name, lambda *a, _n=name: called.append(_n) or {})
    monkeypatch.setattr(eod, "reset_market_cache", lambda: None)
    monkeypatch.setattr(eod, "collect_financials",
                        lambda *a: called.append("collect_financials") or {"skipped": "test"})

    out = eod.run_data_collection("2026-08-17")
    assert "collect_financials" in called, "financials 가 EOD 호출열에 없다"
    assert "financials" in out
    # 순서: corp_events 다음이어야 한다 (같은 opendart 호스트, 순차 필수)
    assert called.index("collect_financials") > called.index("collect_corp_events")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tests/collectors/test_eod_collection.py::test_run_data_collection_actually_calls_financials -v`
Expected: FAIL — `AttributeError: module 'collectors.eod_collection' has no attribute 'collect_financials'`

- [ ] **Step 3: 2줄 추가**

`collectors/eod_collection.py` — import 블록에 1줄:
```python
from collectors.financial_collector import collect_financials, reconcile_financials  # noqa: E402
```

`run_data_collection` 의 dict 에 1줄 (**`corp_events` 다음**):
```python
        "corp_events": _safe(collect_corp_events, trade_date),
        "financials": _safe(collect_financials, trade_date),
        "reconcile": {},
```

`reconcile` 블록에 1줄:
```python
            "corp_events": _safe(reconcile_corp_events, dash),
            "financials": _safe(reconcile_financials, dash),
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest tests/collectors/test_eod_collection.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 라이브 불변 증명 (스펙 테스트 #9)**

```bash
python -c "
import sys; sys.path.insert(0,'.')
from db.kis_db_connection import KisDbConnection
with KisDbConnection.get_connection() as c:
    with c.cursor() as cur:
        for t in ('daily_prices','minute_candles','virtual_trading_records'):
            cur.execute(f'SELECT count(*) FROM {t}'); print(t, cur.fetchone()[0])
"
```
수집기 실행 **전후로 이 세 값이 같아야 한다.** 기록해 둘 것.

- [ ] **Step 6: 전체 스위트 회귀 — 실패 «집합» 차분**

```bash
# 베이스라인 (변경 stash)
git stash -u
python -m pytest -q 2>&1 | tail -5 > /tmp/base.txt
git stash pop
python -m pytest -q 2>&1 | tail -5 > /tmp/after.txt
diff /tmp/base.txt /tmp/after.txt
```
⚠️ repo 루트 + VS 번들 Python 에서 실행. 캡처가 teardown 에서 터지면 `--capture=no`.
Expected: 실패 집합 동일(신규 실패 0)

- [ ] **Step 7: 커밋**

```bash
git add collectors/eod_collection.py tests/collectors/test_eod_collection.py
git commit -m "feat(collectors): EOD 에 재무 수집 등록 — corp_events 다음(같은 opendart 호스트)"
```

---

## Task 8: 2026 1Q 백필 실행 + 완료 판정

**Files:**
- Create: `scratchpad/financials/` (산출물)
- Modify: 없음 (실행 태스크)

**Interfaces:**
- Consumes: Task 1~7 전부
- Produces: 적재 리포트 (미적재 종목 «목록» 포함)

- [ ] **Step 1: 소수 dry run (10종목)**

```bash
python -m collectors.financial_collector --backfill --year 2026 --reprt 11013 --cap 10
```
Expected: `calls` 10 이하 · `status_counts` 에 `000` 존재 · `filings` ≥ 1
🔴 `filings=0` 이면 **멈추고 원인을 찾을 것.** 「0건도 정상일 수 있다」로 넘어가지 말 것.

- [ ] **Step 2: 원본 ↔ DB 대조 3건 (스펙 완료판정 #4)**

```bash
python -c "
import gzip, json, sys; sys.path.insert(0,'.')
from db.kis_db_connection import KisDbConnection
with KisDbConnection.get_connection() as c:
    with c.cursor() as cur:
        cur.execute(\"SELECT rcept_no, fs_div, raw_path FROM dart_financial_filings \"
                    \"WHERE raw_path IS NOT NULL ORDER BY collected_at DESC LIMIT 3\")
        for rcept_no, fs_div, raw_path in cur.fetchall():
            fn, ln = raw_path.split('#L'); ln = int(ln)
            with gzip.open('scratchpad/financials/'+fn,'rt',encoding='utf-8') as fh:
                line = [x for i,x in enumerate(fh,1) if i==ln][0]
            payload = json.loads(line)
            src = payload['list'][0]
            cur.execute(\"SELECT count(*) FROM dart_financial_accounts \"
                        \"WHERE rcept_no=%s AND fs_div=%s\", (rcept_no, fs_div))
            print(rcept_no, fs_div, 'raw_rows=', len(payload['list']), 'db_rows=', cur.fetchone()[0],
                  'match=', src['rcept_no']==rcept_no)
"
```
Expected: 3건 모두 `raw_rows == db_rows` · `match=True`

- [ ] **Step 3: 전량 백필**

```bash
python -m collectors.financial_collector --backfill --year 2026 --reprt 11013 --interval 0.34
```
⚠️ **평일 16:00 EOD 와 겹치지 말 것.** 예상 2,556~5,112호출 ≈ 15~29분.
`DartQuotaExceeded` 로 중단되면 **자정 이후 같은 명령을 다시** 돌린다(멱등).

- [ ] **Step 4: 적재 리포트 — 🔴 비율이 아니라 «목록»**

```bash
python -c "
import sys; sys.path.insert(0,'.')
from db.kis_db_connection import KisDbConnection
from collectors.dart_corp_code import load_map
from collectors.daily_collector import load_universe
from collectors import financial_metrics as fm
with KisDbConnection.get_connection() as c:
    cmap = load_map(c); uni = load_universe(c)
    codes = [s for s in uni if s in cmap]
    with c.cursor() as cur:
        cur.execute(\"SELECT DISTINCT stock_code FROM dart_financial_filings \"
                    \"WHERE bsns_year='2026' AND reprt_code='11013'\")
        done = {r[0] for r in cur.fetchall()}
        cur.execute(\"SELECT stock_code FROM dart_financial_nodata \"
                    \"WHERE bsns_year='2026' AND reprt_code='11013'\")
        nodata = {r[0] for r in cur.fetchall()}
    missing = [s for s in codes if s not in done and s not in nodata]
    print('대상', len(codes), '적재', len(done), '무자료확정', len(nodata), '미적재', len(missing))
    print('미적재 목록:', missing)
    print('매핑 커버리지:', {k:v for k,v in fm.report_mapping_coverage(c).items() if k!='unmatched_stocks'})
" | tee scratchpad/financials/backfill_report_2026_11013.txt
```
🔴 **`미적재 목록` 이 비어 있지 않으면 그 종목들을 개별 조사할 것.** 비율만 보고 넘어가지 말 것.

- [ ] **Step 5: OFS 폴백 비율 실측 (스펙이 미측정으로 남긴 값)**

```bash
python -c "
import sys; sys.path.insert(0,'.')
from db.kis_db_connection import KisDbConnection
with KisDbConnection.get_connection() as c:
    with c.cursor() as cur:
        cur.execute(\"SELECT fs_div, count(*) FROM dart_financial_filings \"
                    \"WHERE bsns_year='2026' AND reprt_code='11013' GROUP BY 1\")
        print(dict(cur.fetchall()))
"
```
이 값으로 설계문서 §6.1 의 호출량 표를 갱신한다(상한 계획 → 실측치).

- [ ] **Step 6: 커밋**

```bash
git add docs/superpowers/specs/2026-08-13-financial-collector-design.md
git commit -m "docs(spec): OFS 폴백 비율 실측치로 호출량 표 갱신"
```

- [ ] **Step 7: 완료 판정 체크리스트**

- [ ] 2026 1Q 적재 리포트에 **미적재 종목 목록** 포함
- [ ] 신규 테스트 전부 통과 + 전체 스위트 실패 집합 **동일**
- [ ] 원본 ↔ DB 대조 3건 일치
- [ ] `daily_prices`·`minute_candles`·`virtual_trading_records` 행수 무변경
- [ ] **8/17(월) 창 개시 후 첫 EOD 에서 `collection_reconciliation(dataset='financials')` PASS**
      (⚠️ 8/15 는 토요일·광복절이라 EOD 가 안 돈다)

---

## 남은 위험 (계획이 해결하지 않는 것)

- 🔴 **`multiverse/data/pit_reader.py:9` 공시 lag 60일** — 실측 p05(70일)보다 짧아 백테스트가
  재무를 약 20일 일찍 본다. **별건 백로그.**
- 🔴 **`dart_financials_asfiled` 폐기** — Phase 2B 종료 후 별도 판단. 이 계획은 손대지 않는다.
- 🔴 **2015~ 소급 백필** — 하네스는 Task 6 에서 완성되지만 **실행은 별도 승인**
  (≈112,000호출 · 6~7일 · 6~8GB).
- 🔴 **소비자 부재** — 「일단 모아두기」가 결정이다. ***소비자가 없으면 값의 정확성을 판정할 수 없다.***
  이 계획의 테스트는 「소비자 없이도 검증 가능한 성질」(정정 보존·look-ahead·no-op·중단 안전)에
  집중돼 있고, 값 정확성의 유일한 외부 대조는 KIS 교차검증이다. **그 대조는 아직 구현하지 않았다.**
