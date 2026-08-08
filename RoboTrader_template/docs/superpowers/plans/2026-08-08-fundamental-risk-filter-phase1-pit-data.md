# 재무 PIT 데이터 파이프라인 (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DART as-filed 연간 재무제표를 수집해 「그날 알 수 있었던 재무」 테이블 `dart_financials_asfiled` 를 만든다.

**Architecture:** `scripts/discovery/fundamental_risk_filter/` 아래 단계별 스크립트 4본(f1 작업목록 → f2 수집 → f3 정규화 → f4 적재). 수집은 순차·체크포인트 재개이며 **원본 응답을 gzip 으로 보존**해 재파생에 DART 호출이 0건이 되게 한다. DB 쓰기는 f4 한 곳뿐이고 대상은 신규 테이블뿐이다.

**Tech Stack:** Python 3.8+ · `requests` · `psycopg2` · `pytest` · PostgreSQL 16 (port **5433**)

**설계 문서:** [`../specs/2026-08-08-fundamental-risk-filter-design.md`](../specs/2026-08-08-fundamental-risk-filter-design.md)

## Global Constraints

- 🔴 **라이브 코드 수정 0.** `core/ bot/ framework/ api/ strategies/ collectors/ db/ runners/ signals/ utils/ tools/` 를 건드리지 않는다. 신규는 전부 `scripts/discovery/` 아래.
- 🔴 **라이브 트리 `D:\GIT\kis-trading-template` 에서 pytest 를 실행하지 않는다.** 작업은 `git worktree add` 로 만든 별도 디렉토리에서 한다.
- 🔴 **전체 테스트 스위트 금지.** `tests/discovery/fundamental_risk_filter/` 로 한정한다.
- 🔴 **DART 병렬 요청 금지.** 2026-08-06 에 4스레드로 IP 차단당했고 운영 수집기까지 동반 사망했다. 순차 + `--interval 0.34`(3 req/s, 20,241호출 동안 연결리셋 0 실측).
- 🔴 **평일 16:00 EOD `collectors/corp_events_collector.py` 와 동시 실행 금지** — 같은 호스트다.
- 🔴 **`status=020`(사용한도 초과)은 즉시 중단**하고 체크포인트를 보존한다. 빈 데이터로 채우지 않는다.
- 🔴 **DB 쓰기는 f4 한 곳뿐**, 대상은 신규 테이블 `dart_financials_asfiled` 뿐. `daily_prices` 등 기존 테이블은 SELECT 만.
- 🔴 **TimescaleDB retention policy 를 설정하지 않는다. hypertable 로 만들지 않는다.** (프로젝트 영구 규칙 — 자동삭제 금지)
- 🔴 **결측을 `0` 으로 채우지 않는다. `NULL` 을 쓴다.** `market_cap` 결손의 대부분이 `0` 이라 `NULL` 만 세면 9.65% 로 보이던 전례가 있다.
- DB 접속: host `127.0.0.1` · port **5433** · db `kis_template` · user `robotrader` · pw `1234`.
- 실행: cwd = `RoboTrader_template`, `PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/<파일>`.
- 테스트: `python -m pytest tests/discovery/fundamental_risk_filter/ -v`
- git commit·push 는 **사장님 확인 필요**. 각 Task 의 커밋 단계는 승인 후 실행한다.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `scripts/discovery/fundamental_risk_filter/__init__.py` | 패키지 마커 |
| `.../dart_client.py` | DART HTTP 클라이언트 — status 검사·차단 판정·스로틀. **`scripts/dart_mcap_common.py` 에서 파생**(그 파일은 untracked 라 의존하지 않고 옮긴다) |
| `.../f1_worklist.py` | `(stock_code, corp_code, bsns_year)` 작업목록 산출 + 파일 저장 |
| `.../f2_collect.py` | `fnlttSinglAcntAll` 수집. 체크포인트 재개 · **원본 gzip 보존** |
| `.../f3_normalize.py` | 원본 → 표준 필드 + `rcept_dt` 추출 + 계정 커버리지 리포트 |
| `.../f4_load.py` | 신규 테이블 DDL + 멱등 적재 + `daily_prices` 불변 증명 |
| `tests/discovery/fundamental_risk_filter/test_dart_client.py` | status 처리·차단 판정 |
| `tests/discovery/fundamental_risk_filter/test_normalize.py` | 계정 매핑·`rcept_dt` 파싱·결측 규약 |
| `tests/discovery/fundamental_risk_filter/test_pit_join.py` | **as-of 조인에 look-ahead 가 없음**을 고정 |

산출물 디렉토리: `scratchpad/fund_pit/` (gitignored)

---

## Task 1: DART 클라이언트

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/__init__.py`
- Create: `scripts/discovery/fundamental_risk_filter/dart_client.py`
- Test: `tests/discovery/fundamental_risk_filter/__init__.py`, `tests/discovery/fundamental_risk_filter/test_dart_client.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces:
  - `class DartBlocked(RuntimeError)`
  - `class DartQuotaExceeded(RuntimeError)`
  - `class DartClient(key: str, min_interval: float = 0.34)` — 메서드 `fnltt_all(corp_code: str, bsns_year: str, reprt_code: str, fs_div: str) -> tuple[str, str, list[dict]]` 반환 `(status, message, rows)`
  - `load_dart_key() -> str`
  - `db_conn()` → 읽기전용 psycopg2 connection
  - 상수 `OUT_DIR: str`, `REPRT_FY = "11011"`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/discovery/fundamental_risk_filter/__init__.py` 는 빈 파일로 만든다.

```python
# tests/discovery/fundamental_risk_filter/test_dart_client.py
import os
import sys

import pytest

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import dart_client as dc  # noqa: E402


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _Session:
    """호출 스크립트를 기록하는 가짜 세션."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


def _client(script):
    """🔴 세션을 «주입»한다. 대입(c.session = ...)으로는 안 된다 —
    리셋 복구가 세션을 새로 만들기 때문에 그 순간 진짜 requests.Session 이
    끼어들어 테스트가 실제 DART 로 호출을 날린다(2026-08-08 실측).
    factory 가 같은 가짜를 계속 돌려주므로 스크립트가 이어서 소비된다."""
    sess = _Session(script)
    c = dc.DartClient("KEY", min_interval=0.0, session_factory=lambda: sess)
    return c


def test_quota_exceeded_raises_immediately():
    """status=020 은 즉시 중단이다. 조용히 빈 결과로 넘기면 안 된다."""
    c = _client([_Resp({"status": "020", "message": "한도초과"})])
    with pytest.raises(dc.DartQuotaExceeded):
        c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")


def test_no_data_status_is_returned_not_raised():
    """013(무자료)은 정상 반환이다 — 손실이 아니라 사실이다."""
    c = _client([_Resp({"status": "013", "message": "무자료"})])
    status, _, rows = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert status == "013"
    assert rows == []


def test_success_returns_rows_and_counts_status():
    c = _client([_Resp({"status": "000", "message": "정상",
                        "list": [{"account_nm": "자본총계"}]})])
    status, _, rows = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert status == "000"
    assert len(rows) == 1
    assert c.status_counts["000"] == 1
    assert c.calls == 1


def test_three_consecutive_connection_resets_raise_blocked():
    """연결 리셋 3연속 = IP 차단. '0건'과 반드시 구분한다."""
    import requests
    err = requests.exceptions.ConnectionError("reset")
    c = _client([err, err, err])
    with pytest.raises(dc.DartBlocked):
        c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert c.conn_resets == 3


def test_reset_then_success_recovers():
    """리셋이 3연속이 아니면 복구한다 — 과잉 중단하지 않는다."""
    import requests
    c = _client([
        requests.exceptions.ConnectionError("reset"),
        _Resp({"status": "000", "message": "정상", "list": []}),
    ])
    status, _, _ = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert status == "000"
    assert c.conn_resets == 1


def test_fs_div_is_passed_through():
    """CFS/OFS 구분이 요청에 실제로 실려야 한다."""
    c = _client([_Resp({"status": "000", "message": "", "list": []})])
    c.fnltt_all("00126380", "2022", dc.REPRT_FY, "OFS")
    assert c.session.calls[0]["fs_div"] == "OFS"


def test_session_is_recreated_after_reset():
    """🔴 복구 동작을 «고정»한다 — 세션 교체를 지워도 다른 테스트는 다 통과한다.

    오염된 커넥션 풀을 버리는 것이 리셋 복구의 핵심이고, 원본
    scripts/dart_mcap_common.py 가 20,241 호출로 실증한 동작이다.
    """
    import requests
    made = []

    def factory():
        s = _Session([
            requests.exceptions.ConnectionError("reset"),
            _Resp({"status": "000", "message": "", "list": []}),
        ] if not made else [_Resp({"status": "000", "message": "", "list": []})])
        made.append(s)
        return s

    c = dc.DartClient("KEY", min_interval=0.0, session_factory=factory)
    status, _, _ = c.fnltt_all("00126380", "2022", dc.REPRT_FY, "CFS")
    assert status == "000"
    assert len(made) == 2, "리셋 뒤 세션이 새로 만들어져야 한다"


def test_project_root_points_at_repo_package_root():
    """🔴 조용히 틀리는 자리다. 틀리면 OUT_DIR 도 .env 경로도 함께 어긋난다."""
    assert os.path.basename(dc.PROJECT_ROOT) == "RoboTrader_template"
    assert os.path.isdir(os.path.join(dc.PROJECT_ROOT, "scripts"))
    assert dc.OUT_DIR.endswith(os.path.join("RoboTrader_template",
                                            "scratchpad", "fund_pit"))
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_dart_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dart_client'`

- [ ] **Step 3: 최소 구현을 쓴다**

`scripts/discovery/fundamental_risk_filter/__init__.py` 는 빈 파일로 만든다.

```python
# scripts/discovery/fundamental_risk_filter/dart_client.py
"""DART as-filed 재무제표 수집용 클라이언트 (연구 스크립트 — 라이브 의존 0).

🔴 이 파일은 `scripts/dart_mcap_common.py`(2026-08-06~07 시총 백필에서 실전 검증됨)
   에서 파생했다. 그 파일은 git untracked 라 의존하지 않고 옮겼다.
   실측 근거: `--interval 0.34`(3 req/s)로 20,241 호출 동안 연결리셋 0.

🔴 병렬 요청 금지. 2026-08-06 에 4스레드로 opendart 에 IP 차단당했고, 그 동안
   운영 수집기(collectors/corp_events_collector.py)도 같은 호스트라 동작 불가가 됐다.
🔴 빈 응답을 성공으로 처리하지 않는다. 모든 호출의 status 를 집계한다.
"""
import os
import sys
import time

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
# _HERE = <root>/scripts/discovery/fundamental_risk_filter → dirname 3번이 <root> 다.
# ⚠️ 원본 scripts/dart_mcap_common.py 는 scripts/ 바로 아래라 1번이면 됐다.
#    두 단계 깊어졌으므로 2번이 아니라 3번이다 — 틀리면 OUT_DIR 이
#    scripts/scratchpad 가 되고 .env 도 못 찾는다(조용히 실패한다).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
assert os.path.basename(PROJECT_ROOT) == "RoboTrader_template", PROJECT_ROOT
OUT_DIR = os.path.join(PROJECT_ROOT, "scratchpad", "fund_pit")

DART_BASE = "https://opendart.fss.or.kr/api"

REPRT_FY = "11011"  # 사업보고서(연간)


class DartBlocked(RuntimeError):
    """opendart 호스트가 IP 단위로 연결을 리셋(WAF 차단)해 진행 불가."""


class DartQuotaExceeded(RuntimeError):
    """DART 일일 사용한도 초과(status=020). 즉시 중단하고 체크포인트를 보존한다."""


def _parse_dart_key_from_lines(lines) -> str:
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


def load_dart_key() -> str:
    key = (os.getenv("OPENDART_API_KEY") or "").strip()
    if key:
        return key
    env_path = os.path.join(PROJECT_ROOT, ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            return _parse_dart_key_from_lines(f)
    except OSError:
        return ""


def db_conn():
    """kis_template 읽기 전용 접속. read-only 트랜잭션으로 쓰기 원천 차단."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        database="kis_template",
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


class DartClient:
    def __init__(self, key: str, min_interval: float = 0.34, session_factory=None):
        # 🔴 session_factory 는 테스트 이음매다. 리셋 복구가 세션을 «새로 만들기»
        #    때문에, 이 이음매가 없으면 테스트가 주입한 가짜 세션이 복구 순간
        #    진짜 requests.Session 으로 갈아치워지고 **실제 DART 로 호출이 나간다**
        #    (2026-08-08 에 실측으로 확인됨 — status=010 응답을 받았다).
        self.key = key
        self._session_factory = session_factory or requests.Session
        self.session = self._session_factory()
        self.min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0
        self.status_counts = {}
        self.http_errors = 0
        self.conn_resets = 0

    def _bump(self, status):
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def _throttle(self):
        if self.min_interval <= 0:
            return
        gap = time.time() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_call = time.time()

    def fnltt_all(self, corp_code: str, bsns_year: str, reprt_code: str, fs_div: str):
        """단일회사 전체 재무제표. 반환 (status, message, rows).

        rows 의 각 원소에 `rcept_no` 가 들어 있고 앞 8자리가 접수일(YYYYMMDD)이다.
        """
        url = f"{DART_BASE}/fnlttSinglAcntAll.json"
        params = {
            "crtfc_key": self.key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        }
        reset_streak = 0
        backoff = 2.0
        for _ in range(6):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=30)
                self.calls += 1
            except requests.exceptions.ConnectionError:
                self.conn_resets += 1
                reset_streak += 1
                if reset_streak >= 3:
                    raise DartBlocked("연결 리셋 3연속 — opendart IP 차단으로 판단")
                self.session.close()
                self.session = self._session_factory()  # 오염된 커넥션 풀 폐기
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            except Exception:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            reset_streak = 0
            if r.status_code != 200:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            try:
                js = r.json()
            except ValueError:
                self.http_errors += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            status = js.get("status")
            self._bump(status)
            if status == "020":
                raise DartQuotaExceeded("DART 사용한도 초과(status=020) — 즉시 중단")
            if status == "800":
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            return status, js.get("message", ""), js.get("list") or []
        self._bump("HTTP_FAIL")
        return "HTTP_FAIL", "retries exhausted", []
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_dart_client.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: 커밋** (사장님 승인 후)

```bash
git add scripts/discovery/fundamental_risk_filter/ tests/discovery/fundamental_risk_filter/
git commit -m "feat(fund-pit): DART as-filed 클라이언트 — 020 즉시중단, 리셋 3연속만 차단 판정"
```

---

## Task 2: 작업목록 산출

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/f1_worklist.py`
- Test: `tests/discovery/fundamental_risk_filter/test_worklist.py`

**Interfaces:**
- Consumes: `dart_client.db_conn`, `dart_client.OUT_DIR`
- Produces:
  - `build_worklist(rows: list[tuple[str, str]], years: list[str]) -> list[dict]` — 각 원소 `{"stock_code","corp_code","bsns_year"}`
  - 파일 `scratchpad/fund_pit/f1_worklist.jsonl`
  - 상수 `YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]` (**7개**)

**왜 2019 부터인가:** 타겟 구간이 2021-01-04 부터다. 2021-01 에 「그날 알 수 있었던 최신 연간 재무」는
**2019 사업연도 보고서**(2020-03 접수)다 — 2020 사업연도 보고서는 2021-03 에나 접수된다.
2019 를 빼면 **2021-01~03 구간이 통째로 비고**, 그 구간은 타겟 발생률이 낮은(6.97%) 정상 구간이라
빠지면 표본이 편향된다.

**규모 추정:** 종목 ≈2,556 × 연도 7 = **약 17,900 작업**. CFS 무자료 시 OFS 재시도가 붙으므로
**실제 DART 호출은 약 18,000~23,000건** = 일일 한도 기준 **1~2일**이다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/discovery/fundamental_risk_filter/test_worklist.py
import os
import sys

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import f1_worklist as f1  # noqa: E402


def test_years_start_at_2019():
    """타겟이 2021-01 부터이고 그때 알 수 있던 최신 연간재무는 2019 사업연도다."""
    assert f1.YEARS[0] == "2019"
    assert "2025" in f1.YEARS


def test_worklist_is_cross_product_of_stocks_and_years():
    rows = [("005930", "00126380"), ("000660", "00164779")]
    wl = f1.build_worklist(rows, ["2019", "2020"])
    assert len(wl) == 4
    assert {w["stock_code"] for w in wl} == {"005930", "000660"}
    assert {w["bsns_year"] for w in wl} == {"2019", "2020"}


def test_worklist_is_deterministically_ordered():
    """재개가 성립하려면 순서가 매 실행 같아야 한다."""
    rows = [("000660", "00164779"), ("005930", "00126380")]
    a = f1.build_worklist(rows, ["2020", "2019"])
    b = f1.build_worklist(list(reversed(rows)), ["2019", "2020"])
    assert a == b
    assert [w["stock_code"] for w in a][:2] == ["000660", "000660"]


def test_rows_without_corp_code_are_dropped():
    """corp_code 가 없으면 호출 자체가 불가능하다 — 조용히 빈 문자열로 부르지 않는다."""
    rows = [("005930", "00126380"), ("900300", ""), ("900301", None)]
    wl = f1.build_worklist(rows, ["2019"])
    assert [w["stock_code"] for w in wl] == ["005930"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_worklist.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'f1_worklist'`

- [ ] **Step 3: 최소 구현을 쓴다**

```python
# scripts/discovery/fundamental_risk_filter/f1_worklist.py
"""F(1) 수집 작업목록 산출 — (stock_code, corp_code, bsns_year).

읽기 전용. DART 호출 0건.

corp_code 는 `stock_industry`(2026-08-07 적재, 커버리지 100%/2,556종목)에서 가져온다.
⚠️ 우선주 36종목은 corp_code 매핑이 구조적으로 불가하므로 여기서 자동 제외된다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f1_worklist.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR, db_conn  # noqa: E402

# 🔑 2019 부터인 이유: 타겟 시작이 2021-01-04 이고, 그 시점에 공개돼 있던 최신
#    연간재무는 2019 사업연도 보고서(2020-03 접수)다. 2020 사업연도는 2021-03 에나
#    접수되므로 2021-01~03 구간이 비게 된다.
YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]

WORKLIST_JSONL = os.path.join(OUT_DIR, "f1_worklist.jsonl")

UNIVERSE_SQL = """
SELECT si.stock_code, si.corp_code
FROM stock_industry si
WHERE si.corp_code IS NOT NULL AND si.corp_code <> ''
  AND si.stock_code IN (
      SELECT DISTINCT stock_code FROM daily_prices
      WHERE stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')
  )
"""


def build_worklist(rows, years):
    """(stock_code, corp_code) 목록 × 연도 → 결정적 순서의 작업목록."""
    out = []
    for code, corp in sorted(rows):
        if not corp:
            continue
        for y in sorted(years):
            out.append({"stock_code": code, "corp_code": corp, "bsns_year": y})
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(UNIVERSE_SQL)
    # ⚠️ str(None) == "None" 은 진리값이 True 라 build_worklist 의 `if not corp`
    #    가드를 그대로 통과한다. SQL 이 이미 NULL 을 막고 있지만, 두 겹 중
    #    파이썬 쪽만 남는 날 조용히 샌다. None 은 None 으로 넘긴다.
    rows = [(str(a), None if b is None else str(b)) for a, b in cur.fetchall()]
    cur.close()
    conn.close()

    wl = build_worklist(rows, YEARS)
    with open(WORKLIST_JSONL, "w", encoding="utf-8") as f:
        for item in wl:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"종목 {len(rows)} × 연도 {len(YEARS)} = 작업 {len(wl)}건")
    print(f"→ {WORKLIST_JSONL}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_worklist.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 실제로 돌려 규모를 확인한다**

Run: `PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f1_worklist.py`
Expected: `종목 2,5xx × 연도 7 = 작업 17,xxx건` 이 출력되고 `f1_worklist.jsonl` 이 생긴다.

🔴 **작업 건수가 예상(≈17,900)에서 ±15% 넘게 벗어나면 멈추고 보고한다.**
- **크게 적으면** → `stock_industry` 조인이 종목을 떨어뜨리고 있다(커버리지 100% 가 깨졌다는 뜻).
- **크게 많으면** → 유니버스에 의사티커나 중복이 섞였다.
🔑 ***기대값을 상수로 적어두면 정상을 결함으로 읽는다*** — 그래서 고정값이 아니라 범위와 «해석»을 적는다.

- [ ] **Step 6: 커밋** (사장님 승인 후)

```bash
git add scripts/discovery/fundamental_risk_filter/f1_worklist.py tests/discovery/fundamental_risk_filter/test_worklist.py
git commit -m "feat(fund-pit): 수집 작업목록 — 2019 부터인 이유를 코드에 고정"
```

---

## Task 3: 수집기

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/f2_collect.py`
- Test: `tests/discovery/fundamental_risk_filter/test_collect.py`

**Interfaces:**
- Consumes: `dart_client.DartClient`, `dart_client.DartQuotaExceeded`, `dart_client.DartBlocked`, `dart_client.REPRT_FY`, `f1_worklist.WORKLIST_JSONL`
- Produces:
  - `collect_one(client, item: dict) -> dict` — `{"stock_code","corp_code","bsns_year","status","fs_div","rows"}`
  - `load_done(path: str) -> set[tuple[str, str]]` — 완료된 `(stock_code, bsns_year)` 집합
  - 파일 `scratchpad/fund_pit/f2_raw.jsonl.gz` (append, 재개 가능)

**🔑 원본을 보존하는 이유:** 수집이 1~2일 걸리고 일일 한도가 있다. 수집 시점에 필드를 골라 버리면 나중에 계정 하나가 더 필요해질 때 **전체 재수집**이 된다. 원본을 gzip 으로 남기면 재파생 비용이 0이다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/discovery/fundamental_risk_filter/test_collect.py
import gzip
import json
import os
import sys

import pytest

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import dart_client as dc  # noqa: E402
import f2_collect as f2  # noqa: E402


class _FakeClient:
    """호출 순서를 기록하고 미리 정한 응답을 돌려주는 클라이언트."""

    def __init__(self, responses):
        self.responses = responses
        self.seen = []

    def fnltt_all(self, corp_code, bsns_year, reprt_code, fs_div):
        self.seen.append((corp_code, bsns_year, fs_div))
        return self.responses.pop(0)


ITEM = {"stock_code": "005930", "corp_code": "00126380", "bsns_year": "2022"}


def test_cfs_is_tried_first():
    c = _FakeClient([("000", "", [{"account_nm": "자본총계"}])])
    out = f2.collect_one(c, ITEM)
    assert c.seen[0][2] == "CFS"
    assert out["fs_div"] == "CFS"
    assert out["status"] == "000"


def test_falls_back_to_ofs_when_cfs_has_no_data():
    """연결재무제표가 없는 회사는 별도로 떨어진다 — 013 을 결측으로 확정하지 않는다."""
    c = _FakeClient([
        ("013", "무자료", []),
        ("000", "", [{"account_nm": "자본총계"}]),
    ])
    out = f2.collect_one(c, ITEM)
    assert [s[2] for s in c.seen] == ["CFS", "OFS"]
    assert out["fs_div"] == "OFS"
    assert out["status"] == "000"


def test_both_missing_records_013_not_an_empty_success():
    """둘 다 없으면 013 으로 «기록»한다. 성공으로 위장하지 않는다."""
    c = _FakeClient([("013", "무자료", []), ("013", "무자료", [])])
    out = f2.collect_one(c, ITEM)
    assert out["status"] == "013"
    assert out["rows"] == []
    assert out["fs_div"] is None


def test_quota_exceeded_propagates():
    """한도 초과는 삼키지 않는다 — 위로 올려 즉시 중단시킨다."""
    class _Q:
        def fnltt_all(self, *a, **k):
            raise dc.DartQuotaExceeded("020")

    with pytest.raises(dc.DartQuotaExceeded):
        f2.collect_one(_Q(), ITEM)


def test_load_done_reads_checkpoint(tmp_path):
    p = tmp_path / "raw.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"stock_code": "005930", "bsns_year": "2022"}) + "\n")
        f.write(json.dumps({"stock_code": "000660", "bsns_year": "2021"}) + "\n")
    done = f2.load_done(str(p))
    assert done == {("005930", "2022"), ("000660", "2021")}


def test_load_done_on_missing_file_is_empty(tmp_path):
    assert f2.load_done(str(tmp_path / "nope.jsonl.gz")) == set()


def test_load_done_tolerates_truncated_last_line(tmp_path):
    """중단 시점에 마지막 줄이 잘려 있을 수 있다. 그 한 줄만 버리고 재개한다."""
    p = tmp_path / "raw.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"stock_code": "005930", "bsns_year": "2022"}) + "\n")
        f.write('{"stock_code": "0006')
    done = f2.load_done(str(p))
    assert done == {("005930", "2022")}
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_collect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'f2_collect'`

- [ ] **Step 3: 최소 구현을 쓴다**

```python
# scripts/discovery/fundamental_risk_filter/f2_collect.py
"""F(2) DART as-filed 연간 재무제표 수집 (순차, 체크포인트 재개).

읽기 전용 + 외부 API. DB 쓰기 없음.

🔴 병렬 금지 — 2026-08-06 IP 차단 전례.
🔴 status=020 은 즉시 중단하고 체크포인트를 보존한다.
🔑 원본 응답을 gzip 으로 그대로 남긴다. 수집이 1~2일이라 필드를 골라 버리면
   나중에 계정 하나 때문에 전체 재수집이 된다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --limit 300
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --status
"""
import argparse
import gzip
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import (  # noqa: E402
    OUT_DIR, REPRT_FY, DartBlocked, DartClient, DartQuotaExceeded,
    eprint, load_dart_key,
)
from f1_worklist import WORKLIST_JSONL  # noqa: E402

RAW_GZ = os.path.join(OUT_DIR, "f2_raw.jsonl.gz")


def collect_one(client, item):
    """CFS 우선, 무자료면 OFS 로 재시도. 둘 다 없으면 013 을 기록한다."""
    for fs_div in ("CFS", "OFS"):
        status, message, rows = client.fnltt_all(
            item["corp_code"], item["bsns_year"], REPRT_FY, fs_div,
        )
        if status == "000" and rows:
            return {
                "stock_code": item["stock_code"],
                "corp_code": item["corp_code"],
                "bsns_year": item["bsns_year"],
                "status": status,
                "fs_div": fs_div,
                "rows": rows,
            }
        last = (status, message)
    return {
        "stock_code": item["stock_code"],
        "corp_code": item["corp_code"],
        "bsns_year": item["bsns_year"],
        "status": last[0],
        "fs_div": None,
        "rows": [],
    }


def load_done(path):
    """이미 수집한 (stock_code, bsns_year) 집합. 잘린 마지막 줄은 버린다."""
    done = set()
    if not os.path.exists(path):
        return done
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue  # 중단 시점의 잘린 줄 — 그 한 줄만 버린다
            done.add((rec["stock_code"], rec["bsns_year"]))
    return done


def load_worklist():
    items = []
    with open(WORKLIST_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--interval", type=float, default=0.34)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    items = load_worklist()
    done = load_done(RAW_GZ)
    todo = [i for i in items if (i["stock_code"], i["bsns_year"]) not in done]

    print(f"작업 {len(items)} / 완료 {len(done)} / 남음 {len(todo)}")
    if args.status:
        return

    key = load_dart_key()
    if not key:
        eprint("OPENDART_API_KEY 를 찾지 못했다 — 중단")
        sys.exit(1)

    client = DartClient(key, min_interval=args.interval)
    if args.limit:
        todo = todo[: args.limit]

    written = 0
    try:
        with gzip.open(RAW_GZ, "at", encoding="utf-8") as out:
            for item in todo:
                rec = collect_one(client, item)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                written += 1
                if written % 200 == 0:
                    print(f"  {written}/{len(todo)} · 호출 {client.calls} "
                          f"· status {dict(Counter(client.status_counts))}")
    except DartQuotaExceeded as e:
        eprint(f"🔴 {e} — 체크포인트 {written}건 보존. 자정 이후 재개할 것.")
        sys.exit(2)
    except DartBlocked as e:
        eprint(f"🔴 {e} — 체크포인트 {written}건 보존. 즉시 중단했다.")
        sys.exit(3)

    print(f"완료 {written}건 · 호출 {client.calls} · status {dict(client.status_counts)} "
          f"· 연결리셋 {client.conn_resets} · http오류 {client.http_errors}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_collect.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 소규모 파일럿을 돌린다**

Run: `PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --limit 50`
Expected: `완료 50건` 과 status 분포가 출력된다. **`000` 이 0건이면 멈추고 보고한다** — 계정 매핑을 설계할 표본 자체가 없다는 뜻이다.

- [ ] **Step 6: 커밋** (사장님 승인 후)

```bash
git add scripts/discovery/fundamental_risk_filter/f2_collect.py tests/discovery/fundamental_risk_filter/test_collect.py
git commit -m "feat(fund-pit): as-filed 수집기 — 원본 gzip 보존으로 재파생 비용 0"
```

---

## Task 4: 정규화 + 계정 커버리지

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/f3_normalize.py`
- Test: `tests/discovery/fundamental_risk_filter/test_normalize.py`

**Interfaces:**
- Consumes: `f2_collect.RAW_GZ`, `dart_client.OUT_DIR`
- Produces:
  - `parse_amount(v) -> int | None`
  - `rcept_dt_from(rows: list[dict]) -> str | None` — `YYYY-MM-DD`
  - `pick_account(rows, sj_div: str, account_ids: tuple, name_hints: tuple) -> int | None`
  - `normalize(rec: dict) -> dict` — 아래 키를 가진 dict
  - 파일 `scratchpad/fund_pit/f3_normalized.jsonl`, `scratchpad/fund_pit/f3_coverage.txt`

정규화 결과 dict 의 키:
`stock_code, bsns_year, rcept_dt, fs_div, total_equity, issued_capital, total_liabilities, operating_income, interest_expense`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/discovery/fundamental_risk_filter/test_normalize.py
import os
import sys

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import f3_normalize as f3  # noqa: E402


def _row(sj_div, account_id, account_nm, amount, rcept_no="20230315000123"):
    return {
        "rcept_no": rcept_no,
        "sj_div": sj_div,
        "account_id": account_id,
        "account_nm": account_nm,
        "thstrm_amount": amount,
    }


def test_parse_amount_handles_commas_and_negatives():
    assert f3.parse_amount("5,969,782,550") == 5969782550
    assert f3.parse_amount("-1,234") == -1234


def test_parse_amount_returns_none_not_zero_on_failure():
    """🔴 결측을 0 으로 뭉개면 안 된다 — market_cap 결손 오판의 재발이다."""
    assert f3.parse_amount("") is None
    assert f3.parse_amount("-") is None
    assert f3.parse_amount(None) is None
    assert f3.parse_amount("해당사항없음") is None


def test_rcept_dt_is_extracted_from_rcept_no():
    rows = [_row("BS", "ifrs-full_Equity", "자본총계", "100", "20230315000123")]
    assert f3.rcept_dt_from(rows) == "2023-03-15"


def test_rcept_dt_is_none_when_absent():
    assert f3.rcept_dt_from([]) is None
    assert f3.rcept_dt_from([{"sj_div": "BS"}]) is None


def test_pick_account_prefers_account_id_over_name():
    """account_id 가 있으면 그것을 쓴다 — 이름은 회사마다 다르다."""
    rows = [
        _row("BS", "ifrs-full_Equity", "자본총계합계", "500"),
        _row("BS", "", "자본총계", "999"),
    ]
    got = f3.pick_account(rows, "BS", ("ifrs-full_Equity",), ("자본총계",))
    assert got == 500


def test_pick_account_falls_back_to_name_hint():
    rows = [_row("BS", "", "자본총계", "777")]
    got = f3.pick_account(rows, "BS", ("ifrs-full_Equity",), ("자본총계",))
    assert got == 777


def test_pick_account_respects_sj_div():
    """같은 이름이 재무상태표와 손익계산서에 다 있을 수 있다."""
    rows = [_row("IS", "", "자본총계", "111")]
    assert f3.pick_account(rows, "BS", (), ("자본총계",)) is None


def test_normalize_missing_account_is_none():
    rec = {
        "stock_code": "005930", "bsns_year": "2022", "fs_div": "CFS",
        "status": "000",
        "rows": [_row("BS", "ifrs-full_Equity", "자본총계", "1000")],
    }
    out = f3.normalize(rec)
    assert out["total_equity"] == 1000
    assert out["interest_expense"] is None      # 없으면 None
    assert out["rcept_dt"] == "2023-03-15"


def test_normalize_of_empty_record_keeps_the_row():
    """013(무자료)도 행을 남긴다 — 어느 종목·연도가 왜 비었는지가 기록이어야 한다."""
    rec = {"stock_code": "900300", "bsns_year": "2022", "fs_div": None,
           "status": "013", "rows": []}
    out = f3.normalize(rec)
    assert out["stock_code"] == "900300"
    assert out["total_equity"] is None
    assert out["rcept_dt"] is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'f3_normalize'`

- [ ] **Step 3: 최소 구현을 쓴다**

```python
# scripts/discovery/fundamental_risk_filter/f3_normalize.py
"""F(3) 원본 응답 → 표준 필드 + 접수일. DART 호출 0건.

🔴 결측은 None 이다. 0 으로 채우지 않는다.
🔴 이자보상배율의 입력인 이자비용(interest_expense)은 계정 가용성이 불확실하다.
   커버리지를 실측해 리포트에 남긴다 — 낮으면 그 축을 사전등록에서 뺀다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f3_normalize.py
"""
import gzip
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR  # noqa: E402
from f2_collect import RAW_GZ  # noqa: E402

NORM_JSONL = os.path.join(OUT_DIR, "f3_normalized.jsonl")
COVERAGE_TXT = os.path.join(OUT_DIR, "f3_coverage.txt")

_NUM_RE = re.compile(r"^-?[\d,]+$")

# (필드, sj_div, account_id 후보, 계정명 힌트)
SPECS = (
    ("total_equity",       "BS", ("ifrs-full_Equity",),
     ("자본총계",)),
    ("issued_capital",     "BS", ("ifrs-full_IssuedCapital",),
     ("자본금",)),
    ("total_liabilities",  "BS", ("ifrs-full_Liabilities",),
     ("부채총계",)),
    ("operating_income",   "IS", ("dart_OperatingIncomeLoss",),
     ("영업이익", "영업손실")),
    ("interest_expense",   "IS", ("ifrs-full_InterestExpense",),
     ("이자비용",)),
)


def parse_amount(v):
    """'5,969,782,550' → 5969782550. 실패는 None (0 으로 뭉개지 말 것)."""
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


def rcept_dt_from(rows):
    """rcept_no 앞 8자리 = 접수일. 'YYYY-MM-DD' 로 돌려준다."""
    for r in rows:
        no = str(r.get("rcept_no") or "")
        if len(no) >= 8 and no[:8].isdigit():
            return f"{no[0:4]}-{no[4:6]}-{no[6:8]}"
    return None


def pick_account(rows, sj_div, account_ids, name_hints):
    """account_id 우선, 없으면 계정명 힌트. sj_div 가 다르면 보지 않는다."""
    cand = [r for r in rows if str(r.get("sj_div") or "") == sj_div]
    for aid in account_ids:
        for r in cand:
            if str(r.get("account_id") or "").strip() == aid:
                v = parse_amount(r.get("thstrm_amount"))
                if v is not None:
                    return v
    for hint in name_hints:
        for r in cand:
            nm = str(r.get("account_nm") or "").replace(" ", "")
            if nm == hint:
                v = parse_amount(r.get("thstrm_amount"))
                if v is not None:
                    return v
    return None


def normalize(rec):
    rows = rec.get("rows") or []
    out = {
        "stock_code": rec["stock_code"],
        "bsns_year": rec["bsns_year"],
        "rcept_dt": rcept_dt_from(rows),
        "fs_div": rec.get("fs_div"),
    }
    for field, sj_div, aids, hints in SPECS:
        out[field] = pick_account(rows, sj_div, aids, hints)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    total = 0
    have = {f[0]: 0 for f in SPECS}
    have["rcept_dt"] = 0
    with gzip.open(RAW_GZ, "rt", encoding="utf-8") as src, \
            open(NORM_JSONL, "w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            norm = normalize(rec)
            dst.write(json.dumps(norm, ensure_ascii=False) + "\n")
            total += 1
            for k in have:
                if norm.get(k) is not None:
                    have[k] += 1

    lines = [f"정규화 {total}행", ""]
    for k, n in have.items():
        pct = (100.0 * n / total) if total else 0.0
        lines.append(f"  {k:20s} {n:7d}  {pct:6.2f}%")
    lines.append("")
    lines.append("🔴 interest_expense 커버리지가 낮으면 이자보상배율 축을 "
                 "사전등록에서 제외할 것.")
    text = "\n".join(lines)
    with open(COVERAGE_TXT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_normalize.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: 파일럿 50건으로 커버리지를 본다**

Run: `PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f3_normalize.py`
Expected: 필드별 커버리지 표가 출력된다.

🔴 **`total_equity` 커버리지가 90% 미만이면 멈추고 보고한다** — 계정 매핑이 틀렸다는 뜻이다(자본총계는 모든 재무상태표에 있다).
🟡 `interest_expense` 는 낮게 나올 수 있다. **그건 결함이 아니라 사실이고, 사전등록에서 그 축을 뺄 근거가 된다.**

- [ ] **Step 6: 커밋** (사장님 승인 후)

```bash
git add scripts/discovery/fundamental_risk_filter/f3_normalize.py tests/discovery/fundamental_risk_filter/test_normalize.py
git commit -m "feat(fund-pit): 계정 정규화 — 결측은 None, 커버리지를 실측해 축 채택을 가린다"
```

---

## Task 5: 적재 + 불변 증명

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/f4_load.py`
- Test: `tests/discovery/fundamental_risk_filter/test_load_sql.py`

**Interfaces:**
- Consumes: `f3_normalize.NORM_JSONL`
- Produces:
  - 테이블 `dart_financials_asfiled` (PK `(stock_code, bsns_year)`)
  - `DDL: str`, `UPSERT: str`, `rw_conn()`
  - 파일 `scratchpad/fund_pit/f4_invariance_proof.txt`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

DB 없이 도는 정적 검사다 — **이 스크립트가 기존 테이블을 건드리지 않음을 SQL 문자열 수준에서 고정**한다.

```python
# tests/discovery/fundamental_risk_filter/test_load_sql.py
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
    """🔴 UPDATE/DELETE/DROP/TRUNCATE 가 기존 테이블을 향하면 안 된다."""
    for verb in ("UPDATE ", "DELETE ", "DROP TABLE", "TRUNCATE", "ALTER TABLE"):
        for m in re.finditer(verb, _SRC, re.IGNORECASE):
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_load_sql.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'f4_load'`

- [ ] **Step 3: 최소 구현을 쓴다**

```python
# scripts/discovery/fundamental_risk_filter/f4_load.py
"""F(4) PIT 재무 적재 — 이 파이프라인의 «유일한» DB 쓰기.

🔴 쓰는 대상은 신규 테이블 `dart_financials_asfiled` 뿐이다.
   기존 테이블(daily_prices 등)에는 UPDATE/DELETE 문이 이 파일에 존재하지 않는다.
🔴 retention policy 를 설정하지 않고 hypertable 로 만들지 않는다(영구 규칙).
🔴 결측은 NULL 이다. 0 으로 채우지 않는다.
🔑 013(무자료) 행도 남긴다 — 어느 종목·연도가 왜 비었는지가 기록이어야 한다.

멱등: PK(stock_code, bsns_year) 에 ON CONFLICT DO UPDATE.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f4_load.py --create
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f4_load.py --load
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2  # noqa: E402
from psycopg2.extras import execute_values  # noqa: E402

from dart_client import OUT_DIR  # noqa: E402
from f3_normalize import NORM_JSONL  # noqa: E402

TABLE = "dart_financials_asfiled"
PROOF_TXT = os.path.join(OUT_DIR, "f4_invariance_proof.txt")

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    stock_code         VARCHAR(20) NOT NULL,
    bsns_year          VARCHAR(4)  NOT NULL,
    rcept_dt           DATE,                  -- 접수일 = 이 값을 알 수 있게 된 날
    fs_div             TEXT,                  -- CFS | OFS | NULL(무자료)
    total_equity       BIGINT,
    issued_capital     BIGINT,
    total_liabilities  BIGINT,
    operating_income   BIGINT,
    interest_expense   BIGINT,
    created_at         TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_code, bsns_year)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_rcept ON {TABLE} (rcept_dt);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_code ON {TABLE} (stock_code);
"""

UPSERT = f"""
INSERT INTO {TABLE}
  (stock_code, bsns_year, rcept_dt, fs_div, total_equity,
   issued_capital, total_liabilities, operating_income, interest_expense)
VALUES %s
ON CONFLICT (stock_code, bsns_year) DO UPDATE SET
  rcept_dt          = EXCLUDED.rcept_dt,
  fs_div            = EXCLUDED.fs_div,
  total_equity      = EXCLUDED.total_equity,
  issued_capital    = EXCLUDED.issued_capital,
  total_liabilities = EXCLUDED.total_liabilities,
  operating_income  = EXCLUDED.operating_income,
  interest_expense  = EXCLUDED.interest_expense
"""

DP_FINGERPRINT = """
SELECT count(*),
       coalesce(sum(hashtext(stock_code || date ||
                             coalesce(close::text,'') ||
                             coalesce(market_cap::text,''))::bigint), 0)
FROM daily_prices
"""


def rw_conn():
    return psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        database="kis_template",
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    )


def fingerprint(cur):
    cur.execute(DP_FINGERPRINT)
    n, h = cur.fetchone()
    return {"rows": int(n), "hash": int(h)}


def read_rows():
    out = []
    with open(NORM_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out.append((
                r["stock_code"], r["bsns_year"], r.get("rcept_dt"), r.get("fs_div"),
                r.get("total_equity"), r.get("issued_capital"),
                r.get("total_liabilities"), r.get("operating_income"),
                r.get("interest_expense"),
            ))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--load", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    conn = rw_conn()
    conn.autocommit = False
    cur = conn.cursor()

    if args.create:
        cur.execute(DDL)
        conn.commit()
        print(f"{TABLE} 준비 완료")

    if args.load:
        before = fingerprint(cur)
        rows = read_rows()
        execute_values(cur, UPSERT, rows, page_size=1000)
        conn.commit()
        after = fingerprint(cur)

        cur.execute(f"SELECT count(*), count(rcept_dt) FROM {TABLE}")
        n_all, n_dt = cur.fetchone()

        ok = before == after
        text = (
            f"적재 {len(rows)}행 → {TABLE} 총 {n_all}행 (rcept_dt 있는 행 {n_dt})\n"
            f"daily_prices before: {before}\n"
            f"daily_prices after : {after}\n"
            f"불변: {'OK' if ok else '🔴 변경됨'}\n"
        )
        with open(PROOF_TXT, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        if not ok:
            sys.exit(4)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_load_sql.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 파일럿 적재 + 불변 증명**

```bash
PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f4_load.py --create
PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f4_load.py --load
```
Expected: `불변: OK` 가 출력된다. **`🔴 변경됨` 이면 즉시 중단하고 보고한다.**

- [ ] **Step 6: 커밋** (사장님 승인 후)

```bash
git add scripts/discovery/fundamental_risk_filter/f4_load.py tests/discovery/fundamental_risk_filter/test_load_sql.py
git commit -m "feat(fund-pit): 신규 테이블 적재 — daily_prices 불변을 지문으로 증명"
```

---

## Task 6: PIT 조인을 테스트로 고정

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/pit_join.py`
- Test: `tests/discovery/fundamental_risk_filter/test_pit_join.py`

**Interfaces:**
- Consumes: 없음(순수 함수)
- Produces: `asof_financials(records: list[dict], as_of: str) -> dict | None`
  - `records` 원소는 `{"bsns_year","rcept_dt", ...}`
  - `as_of` 는 `'YYYY-MM-DD'`
  - **`rcept_dt <= as_of` 인 것 중 `rcept_dt` 가 가장 늦은 행**을 돌려준다

**🔑 이 태스크가 이 계획의 핵심 안전장치다.** 스펙 §2 전체가 이 한 줄의 정확성에 걸려 있다. 여기가 틀리면 look-ahead 가 조용히 들어오고, 그러면 이후 모든 검정 결과가 무효다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/discovery/fundamental_risk_filter/test_pit_join.py
import os
import sys

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import pit_join as pj  # noqa: E402

RECS = [
    {"bsns_year": "2019", "rcept_dt": "2020-03-30", "total_equity": 100},
    {"bsns_year": "2020", "rcept_dt": "2021-03-19", "total_equity": 200},
    {"bsns_year": "2021", "rcept_dt": "2022-03-22", "total_equity": 300},
]


def test_picks_latest_filing_on_or_before_as_of():
    got = pj.asof_financials(RECS, "2021-06-30")
    assert got["bsns_year"] == "2020"


def test_boundary_same_day_is_visible():
    """접수일 «당일»은 공개된 것으로 본다."""
    got = pj.asof_financials(RECS, "2021-03-19")
    assert got["bsns_year"] == "2020"


def test_one_day_before_filing_is_not_visible():
    """🔴 look-ahead 방지의 핵심. 하루 전에는 안 보여야 한다."""
    got = pj.asof_financials(RECS, "2021-03-18")
    assert got["bsns_year"] == "2019"


def test_before_any_filing_returns_none():
    assert pj.asof_financials(RECS, "2019-12-31") is None


def test_records_with_null_rcept_dt_are_ignored():
    """접수일을 모르는 행은 «언제 알 수 있었는지» 를 모르므로 못 쓴다."""
    recs = RECS + [{"bsns_year": "2022", "rcept_dt": None, "total_equity": 999}]
    got = pj.asof_financials(recs, "2026-01-01")
    assert got["bsns_year"] == "2021"


def test_unsorted_input_gives_same_answer():
    got = pj.asof_financials(list(reversed(RECS)), "2021-06-30")
    assert got["bsns_year"] == "2020"


def test_later_fiscal_year_filed_earlier_does_not_win_by_year():
    """정렬 키는 «사업연도» 가 아니라 «접수일» 이다."""
    recs = [
        {"bsns_year": "2021", "rcept_dt": "2022-03-22", "total_equity": 300},
        {"bsns_year": "2022", "rcept_dt": "2023-03-20", "total_equity": 400},
    ]
    got = pj.asof_financials(recs, "2022-06-01")
    assert got["bsns_year"] == "2021"


def test_empty_records_returns_none():
    assert pj.asof_financials([], "2023-01-01") is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_pit_join.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pit_join'`

- [ ] **Step 3: 최소 구현을 쓴다**

```python
# scripts/discovery/fundamental_risk_filter/pit_join.py
"""PIT as-of 조인 — 「그날 알 수 있었던 재무」를 고르는 단 하나의 함수.

🔴 이 파일이 틀리면 look-ahead 가 조용히 들어오고 이후 모든 검정이 무효가 된다.
   정렬 키는 «사업연도» 가 아니라 «접수일(rcept_dt)» 이다.

⚠️ 08-07 시총 백필의 교훈(「look-ahead 규약을 과거 사실의 복원에 적용하지 말 것」)과
   방향이 «반대» 다. 여기는 복원이 아니라 예측이고, 재무는 보고서가 접수되기 전엔
   실제로 아무도 몰랐다. 두 규칙은 모순이 아니라 목적이 다르다.
"""


def asof_financials(records, as_of):
    """rcept_dt <= as_of 인 것 중 rcept_dt 가 가장 늦은 레코드. 없으면 None."""
    best = None
    for r in records:
        dt = r.get("rcept_dt")
        if not dt:
            continue  # 언제 공개됐는지 모르는 값은 쓸 수 없다
        if dt > as_of:
            continue
        if best is None or dt > best["rcept_dt"]:
            best = r
    return best
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_pit_join.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: 패키지 전체 테스트를 돌린다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/ -v`
Expected: PASS (42 passed) — T1 8 · T2 4 · T3 7 · T4 9 · T5 6 · T6 8

- [ ] **Step 6: 커밋** (사장님 승인 후)

```bash
git add scripts/discovery/fundamental_risk_filter/pit_join.py tests/discovery/fundamental_risk_filter/test_pit_join.py
git commit -m "feat(fund-pit): as-of 조인 — 접수일 하루 전에는 안 보인다를 테스트로 고정"
```

---

## Task 7: 전량 수집 실행

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/README.md`
- Modify: 없음 (실행 태스크)

- [ ] **Step 1: 실행 시각을 확인한다**

🔴 **평일 16:00 EOD `corp_events_collector` 와 겹치면 안 된다.** 주말이거나 EOD 완료 후 시작한다.
🔴 **시총 백필 B2~B4 는 DART 호출 0건**이라 동시 진행해도 무방하다. 다른 DART 수집이 도는지 확인한다.

- [ ] **Step 2: 전량 수집을 백그라운드로 시작한다**

```bash
PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --interval 0.34
```

- [ ] **Step 3: 한도 초과 시 재개한다**

`status=020` 으로 종료(exit code 2)하면 **자정 이후** 같은 명령을 다시 실행한다. 체크포인트가 남은 것부터 이어간다.
(2026-08-07 실측: 22:35 차단 → 00:10 재개 시 전량 정상. **한도 리셋은 자정이 맞다.**)

- [ ] **Step 4: 수집 완료를 확인한다**

Run: `PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f2_collect.py --status`
Expected: `남음 0`

- [ ] **Step 5: 정규화 + 적재 + 커버리지 판정**

```bash
PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f3_normalize.py
PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f4_load.py --create
PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f4_load.py --load
```

**판정 기준:**
- `total_equity` 커버리지 **90% 미만 → 중단·보고**(계정 매핑 오류)
- `rcept_dt` 커버리지 **90% 미만 → 중단·보고**(PIT 자체가 성립 안 함)
- `daily_prices` 불변 **`OK` 아니면 즉시 중단·보고**
- `interest_expense` 커버리지는 **낮아도 정상** — 사전등록에서 그 축을 뺄 근거로 기록한다

- [ ] **Step 6: README 를 쓰고 커밋** (사장님 승인 후)

`README.md` 에 담을 것: 단계별 실행 순서 · 실측 커버리지 표 · 재개 방법 · 🔴 병렬 금지와 EOD 충돌 금지 · 원본 gzip 의 위치와 **재수집 없이 재파생하는 법**.

```bash
git add scripts/discovery/fundamental_risk_filter/README.md
git commit -m "docs(fund-pit): 실행 순서·실측 커버리지·재개 방법"
```

---

## Phase 1 완료 조건

1. `tests/discovery/fundamental_risk_filter/` 전량 통과
2. `dart_financials_asfiled` 적재 완료 + `daily_prices` 불변 증명 `OK`
3. `f3_coverage.txt` 에 필드별 실측 커버리지가 기록됨
4. 🔴 **라이브 코드 변경 0** — `git diff --stat main` 에 `core/ bot/ framework/ api/ strategies/ collectors/ db/ runners/ signals/ utils/ tools/` 경로가 없음

## 다음 (Phase 2 — 별도 계획)

타겟 산출(60일 −30%, `2026-05-12` 컷) → `PREREG.md` 격자 동결 → 게이트 G0~G6 실행.
**Phase 2 계획은 `f3_coverage.txt` 의 실측값을 보고 쓴다** — 이자보상배율 축의 채택 여부가 거기서 갈린다.
