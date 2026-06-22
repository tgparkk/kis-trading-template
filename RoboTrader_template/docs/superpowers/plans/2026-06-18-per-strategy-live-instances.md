# 전략별 실전 인스턴스 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 한 코드베이스에서 환경변수(`KIS_INSTANCE_DIR`)로 설정을 분리해, 전략당 1개 실전 인스턴스(전용 계좌·프로세스·매매테이블)를 띄울 수 있게 한다.

**Architecture:** 인스턴스 식별자(`INSTANCE_ID`)를 `KIS_INSTANCE_DIR` 폴더명에서 도출해 ① 설정 디렉토리(key.ini/trading_config.json) ② PID 파일명 ③ 실거래 매매 테이블명(`real_trading_<id>`)을 결정한다. 미설정 시 기존 `config/`·`robotrader.pid`·`real_trading_records`로 동작(완전 하위호환). 시세/후보/스크리너는 공유 유지.

**Tech Stack:** Python 3.8+, psycopg2 (PostgreSQL 16 + TimescaleDB), pytest, configparser.

## Global Constraints

- 하위호환 절대 보존: `KIS_INSTANCE_DIR` 미설정 시 모든 경로/테이블/PID가 기존과 바이트 동일.
- 테이블명은 화이트리스트 검증 후에만 SQL 조립: `^real_trading_records$` 또는 `^real_trading_[a-z0-9_]+$` (SQL injection 차단).
- `INSTANCE_ID` 정규화: `KIS_INSTANCE_DIR` basename을 소문자화 + `[^a-z0-9_]`→`_`. 빈 값/미설정 → `"default"`.
- 페이퍼 경로(`virtual_trading_records`, source=`kis_template`)는 무변경.
- DB는 기존 `robotrader` 1개. 전략별은 **테이블만** 분리.
- 테스트=pytest, lint=ruff check. 커밋은 사장님 지시 시(자동 커밋 금지) — 각 Task의 "Commit" 스텝은 스테이징까지 준비하고 실제 commit은 승인 후.

---

### Task 1: settings.py — 설정 디렉토리 오버라이드 + INSTANCE_ID + 테이블명 도출

**Files:**
- Modify: `config/settings.py`
- Test: `tests/test_instance_settings.py`

**Interfaces:**
- Produces:
  - `resolve_instance_id(env: dict) -> str` — `KIS_INSTANCE_DIR` basename 정규화, 미설정→`"default"`
  - `resolve_config_dir(env: dict) -> Path` — `KIS_INSTANCE_DIR` 있으면 그 Path, 없으면 `config/` 디렉토리
  - `real_trading_table_name(instance_id: str) -> str` — `default`→`"real_trading_records"`, 그 외→`f"real_trading_{instance_id}"`
  - 모듈 전역: `INSTANCE_ID: str`, `REAL_TRADING_TABLE: str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_instance_settings.py
from pathlib import Path
from config.settings import (
    resolve_instance_id, resolve_config_dir, real_trading_table_name,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

def test_instance_id_default_when_unset():
    assert resolve_instance_id({}) == "default"
    assert resolve_instance_id({"KIS_INSTANCE_DIR": ""}) == "default"

def test_instance_id_from_dir_basename_normalized():
    assert resolve_instance_id({"KIS_INSTANCE_DIR": "instances/rs_leader"}) == "rs_leader"
    assert resolve_instance_id({"KIS_INSTANCE_DIR": "instances/Book-MA5"}) == "book_ma5"

def test_config_dir_default_is_config_folder():
    assert resolve_config_dir({}) == CONFIG_DIR

def test_config_dir_override():
    assert resolve_config_dir({"KIS_INSTANCE_DIR": "instances/rs_leader"}) == Path("instances/rs_leader")

def test_real_table_name():
    assert real_trading_table_name("default") == "real_trading_records"
    assert real_trading_table_name("rs_leader") == "real_trading_rs_leader"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_instance_settings.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_instance_id'`

- [ ] **Step 3: Write minimal implementation**

`config/settings.py` 상단(`import` 직후, `CONFIG_FILE` 정의 전)에 추가:

```python
import os
import re

def resolve_instance_id(env: dict) -> str:
    raw = (env.get("KIS_INSTANCE_DIR") or "").strip()
    if not raw:
        return "default"
    base = Path(raw).name.lower()
    norm = re.sub(r"[^a-z0-9_]", "_", base).strip("_")
    return norm or "default"

def resolve_config_dir(env: dict) -> Path:
    raw = (env.get("KIS_INSTANCE_DIR") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).parent

def real_trading_table_name(instance_id: str) -> str:
    if instance_id == "default":
        return "real_trading_records"
    return f"real_trading_{instance_id}"
```

기존 `CONFIG_FILE`/`TRADING_CONFIG_FILE` 라인을 교체:

```python
INSTANCE_ID = resolve_instance_id(os.environ)
_CONFIG_DIR = resolve_config_dir(os.environ)
CONFIG_FILE = _CONFIG_DIR / "key.ini"
TRADING_CONFIG_FILE = _CONFIG_DIR / "trading_config.json"
REAL_TRADING_TABLE = real_trading_table_name(INSTANCE_ID)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_instance_settings.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Regression — 기존 import 무영향 확인**

Run: `python -c "import config.settings as s; print(s.INSTANCE_ID, s.REAL_TRADING_TABLE, s.CONFIG_FILE.name)"`
Expected: `default real_trading_records key.ini`

- [ ] **Step 6: Commit**

```bash
git add config/settings.py tests/test_instance_settings.py
git commit -m "feat(instance): settings에 KIS_INSTANCE_DIR 오버라이드 + INSTANCE_ID/REAL_TRADING_TABLE"
```

---

### Task 2: TradingRepository — 실거래 테이블명 파라미터화 + 검증 + 자동생성

**Files:**
- Modify: `db/repositories/trading.py` (line 24 `__init__`, 9곳의 `real_trading_records`)
- Test: `tests/test_trading_repo_table.py`

**Interfaces:**
- Consumes: `config.settings.REAL_TRADING_TABLE` (Task 1)
- Produces:
  - `TradingRepository(db_path=None, real_table_name=None)` — `real_table_name=None`이면 `settings.REAL_TRADING_TABLE` 사용
  - `self._real_table: str` — 검증 통과한 실거래 테이블명
  - `TradingRepository._validate_table_name(name: str) -> str` — 화이트리스트 위반 시 `ValueError`
  - `self.ensure_real_table()` — 비기본 테이블이면 `CREATE TABLE IF NOT EXISTS <t> (LIKE real_trading_records INCLUDING ALL)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trading_repo_table.py
import pytest
from db.repositories.trading import TradingRepository

def test_default_table_backward_compat():
    repo = TradingRepository()
    assert repo._real_table == "real_trading_records"

def test_custom_table_name():
    repo = TradingRepository(real_table_name="real_trading_rs_leader")
    assert repo._real_table == "real_trading_rs_leader"

def test_validate_rejects_injection():
    with pytest.raises(ValueError):
        TradingRepository(real_table_name="real_trading_x; DROP TABLE foo")
    with pytest.raises(ValueError):
        TradingRepository(real_table_name="random_table")

def test_validate_accepts_default_and_prefixed():
    assert TradingRepository._validate_table_name("real_trading_records") == "real_trading_records"
    assert TradingRepository._validate_table_name("real_trading_rs_leader") == "real_trading_rs_leader"

def test_queries_use_custom_table(monkeypatch):
    captured = []
    class FakeCursor:
        def execute(self, sql, params=None): captured.append(sql)
        def fetchone(self): return [0]
    class FakeConn:
        def cursor(self): return FakeCursor()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    repo = TradingRepository(real_table_name="real_trading_rs_leader")
    monkeypatch.setattr(repo, "_get_connection", lambda: FakeConn())
    repo.get_today_real_loss_count("005930")
    assert any("real_trading_rs_leader" in s for s in captured)
    assert not any("FROM real_trading_records" in s for s in captured)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_trading_repo_table.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'real_table_name'`

- [ ] **Step 3: Write minimal implementation**

`db/repositories/trading.py`:

(a) `import re` 추가, 클래스에 검증/init 변경:

```python
import re
# ... class TradingRepository(BaseRepository):

    _TABLE_RE = re.compile(r"^real_trading_records$|^real_trading_[a-z0-9_]+$")

    @classmethod
    def _validate_table_name(cls, name: str) -> str:
        if not name or not cls._TABLE_RE.match(name):
            raise ValueError(f"허용되지 않는 실거래 테이블명: {name!r}")
        return name

    def __init__(self, db_path: str = None, real_table_name: str = None):
        super().__init__(db_path)
        self.logger = RateLimitedLogger(self.logger)
        if real_table_name is None:
            from config.settings import REAL_TRADING_TABLE
            real_table_name = REAL_TRADING_TABLE
        self._real_table = self._validate_table_name(real_table_name)
        if self._real_table != "real_trading_records":
            self.ensure_real_table()

    def ensure_real_table(self) -> None:
        """비기본 인스턴스 테이블을 real_trading_records 스키마로 생성(멱등)."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"CREATE TABLE IF NOT EXISTS {self._real_table} "
                    f"(LIKE real_trading_records INCLUDING ALL)"
                )
                conn.commit()
        except Exception as e:
            self.logger.error(f"실거래 테이블 생성 실패({self._real_table}): {e}")
```

(b) 9곳의 `real_trading_records`를 `{self._real_table}`로 치환하고 해당 SQL 문자열을 f-string으로 전환. 구체 위치(현재 라인):
- `get_today_real_loss_count`: `FROM real_trading_records` (59)
- `save_real_buy`: `INSERT INTO real_trading_records` (81)
- `save_real_sell`: `FROM real_trading_records b` (113), 서브쿼리 `FROM real_trading_records s` (116), `SELECT price FROM real_trading_records WHERE id` (125), `INSERT INTO real_trading_records` (133)
- `get_last_open_real_buy`: `FROM real_trading_records b` (155), 서브쿼리 `FROM real_trading_records s` (158)

예 (get_today_real_loss_count):

```python
                cursor.execute(f'''
                    SELECT COUNT(1) FROM {self._real_table}
                    WHERE stock_code = %s AND action = 'SELL'
                      AND profit_loss < 0
                      AND timestamp >= %s AND timestamp < %s
                ''', (stock_code, start_str, next_str))
```

나머지 8곳도 동일 패턴으로 리터럴 `real_trading_records`만 `{self._real_table}`로 치환(파라미터 바인딩 `%s`는 그대로 유지).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_trading_repo_table.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Regression — 기존 매매 repo 테스트**

Run: `pytest tests/ -k "trading" -v`
Expected: 기존 통과 테스트 유지(신규 5 포함), 신규 실패 0

- [ ] **Step 6: Commit**

```bash
git add db/repositories/trading.py tests/test_trading_repo_table.py
git commit -m "feat(instance): TradingRepository 실거래 테이블명 파라미터화 + 검증 + 자동생성"
```

---

### Task 3: DatabaseManager / candidate_selector 배선

**Files:**
- Modify: `db/database_manager.py:69`, `core/candidate_selector.py:446`
- Test: `tests/test_db_manager_instance_table.py`

**Interfaces:**
- Consumes: `config.settings.REAL_TRADING_TABLE`, `TradingRepository(real_table_name=)` (Task 1,2)
- Produces: `DatabaseManager().trading_repo._real_table == settings.REAL_TRADING_TABLE`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_manager_instance_table.py
import config.settings as settings
from db.repositories.trading import TradingRepository

def test_repo_default_uses_settings_table(monkeypatch):
    # 기본(default) 인스턴스 → real_trading_records
    repo = TradingRepository()
    assert repo._real_table == settings.REAL_TRADING_TABLE == "real_trading_records"
```

(주: `DatabaseManager` 전체 인스턴스화는 DB 연결을 요구하므로 단위테스트는 `TradingRepository`가 settings 기본을 쓰는지로 회귀를 잠근다. 비기본 테이블 배선은 Task 6 e2e에서 검증.)

- [ ] **Step 2: Run test to verify it fails (or passes trivially) — 배선 전 확인**

Run: `pytest tests/test_db_manager_instance_table.py -v`
Expected: PASS (Task2 기본동작). 이 테스트는 배선 회귀 가드. 이어서 배선 코드 추가.

- [ ] **Step 3: 배선 수정**

`db/database_manager.py:69` 교체:

```python
        from config.settings import REAL_TRADING_TABLE
        self.trading_repo = TradingRepository(real_table_name=REAL_TRADING_TABLE)
```

`core/candidate_selector.py:446` 교체:

```python
                from config.settings import REAL_TRADING_TABLE
                repo = TradingRepository(real_table_name=REAL_TRADING_TABLE)
```

- [ ] **Step 4: Run test + import 회귀**

Run: `pytest tests/test_db_manager_instance_table.py -v && python -c "import db.database_manager, core.candidate_selector"`
Expected: PASS, import 오류 없음

- [ ] **Step 5: Commit**

```bash
git add db/database_manager.py core/candidate_selector.py tests/test_db_manager_instance_table.py
git commit -m "feat(instance): DatabaseManager/candidate_selector에 인스턴스 테이블명 배선"
```

---

### Task 4: main.py — PID 파일 인스턴스별 분리

**Files:**
- Modify: `main.py:62`
- Test: `tests/test_instance_pid.py`

**Interfaces:**
- Consumes: `config.settings.INSTANCE_ID` (Task 1)
- Produces: `pid_file_name(instance_id: str) -> str` (main 모듈) — `default`→`"robotrader.pid"`, 그 외→`f"robotrader_{instance_id}.pid"`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_instance_pid.py
from main import pid_file_name

def test_default_pid_backward_compat():
    assert pid_file_name("default") == "robotrader.pid"

def test_instance_pid():
    assert pid_file_name("rs_leader") == "robotrader_rs_leader.pid"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_instance_pid.py -v`
Expected: FAIL — `ImportError: cannot import name 'pid_file_name'`

- [ ] **Step 3: Write minimal implementation**

`main.py` 모듈 레벨(클래스 밖, import 직후)에 추가:

```python
def pid_file_name(instance_id: str) -> str:
    if instance_id == "default":
        return "robotrader.pid"
    return f"robotrader_{instance_id}.pid"
```

`DayTradingBot.__init__` line 62 교체:

```python
        from config.settings import INSTANCE_ID
        self.pid_file = Path(pid_file_name(INSTANCE_ID))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_instance_pid.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_instance_pid.py
git commit -m "feat(instance): PID 파일 인스턴스별 분리(기본 robotrader.pid 유지)"
```

---

### Task 5: 배포 자산 — .gitignore 보안 + 인스턴스 템플릿 + 기동 스크립트 + 셋업 문서

**Files:**
- Modify: `.gitignore`
- Create: `instances/rs_leader/key.ini.example`
- Create: `instances/rs_leader/trading_config.json.example`
- Create: `instances/README.md` (셋업 체크리스트)
- Create: `run_instance.bat`

**Interfaces:** (코드 인터페이스 없음 — 운영 자산)

- [ ] **Step 1: .gitignore에 instances/ 추가 (보안 BLOCKING)**

`.gitignore`에 한 줄 추가(기존 `instance/` 단수 아래):

```
instances/
!instances/README.md
!instances/*/key.ini.example
!instances/*/trading_config.json.example
```

- [ ] **Step 2: 실키 커밋 차단 검증**

Run: `git check-ignore instances/rs_leader/key.ini && echo BLOCKED`
Expected: `instances/rs_leader/key.ini` + `BLOCKED` (실제 key.ini는 무시됨)

Run: `git check-ignore instances/rs_leader/key.ini.example || echo TRACKED`
Expected: `TRACKED` (예시 템플릿은 추적됨)

- [ ] **Step 3: 인스턴스 템플릿 생성**

`instances/rs_leader/key.ini.example` — `config/key.ini.example` 내용 복제(실키 자리표시자 유지):

```ini
[KIS]
KIS_BASE_URL="https://openapi.koreainvestment.com:9443"
KIS_APP_KEY="THIS_ACCOUNT_APP_KEY"
KIS_APP_SECRET="THIS_ACCOUNT_APP_SECRET"
KIS_ACCOUNT_NO="THIS_ACCOUNT_NO"
KIS_HTS_ID="THIS_ACCOUNT_HTS_ID"

[TELEGRAM]
enabled=false
token=YOUR_BOT_TOKEN_HERE
chat_id=YOUR_CHAT_ID_HERE
```

`instances/rs_leader/trading_config.json.example` — 기존 `config/trading_config.json`을 복제하되 `"paper_trading": false`로, 활성 전략을 rs_leader 단일로 설정(현 trading_config.json 구조 그대로, 전략 목록만 rs_leader 1개).

- [ ] **Step 4: 기동 스크립트 생성**

`run_instance.bat`:

```bat
@echo off
REM 사용법: run_instance.bat rs_leader
set KIS_INSTANCE_DIR=instances\%1
python main.py
```

- [ ] **Step 5: 셋업 체크리스트 문서**

`instances/README.md`:

```markdown
# 실전 인스턴스 셋업

전략당 1개 실전 인스턴스. 격리 3중: 계좌 / 프로세스 / DB 테이블.

## 새 인스턴스 추가
1. `instances/<strategy>/` 폴더 생성
2. `key.ini.example` → `key.ini` 복사 후 **그 계좌의 실 앱키/시크릿/계좌번호** 입력
3. `trading_config.json.example` → `trading_config.json` 복사, `paper_trading=false`, 활성전략=해당 1개 확인
4. 기동: `run_instance.bat <strategy>` (= `set KIS_INSTANCE_DIR=instances\<strategy>`)
5. 첫 기동 시 `real_trading_<strategy>` 테이블이 자동 생성됨(robotrader DB)

## 보안
- `instances/` 전체가 .gitignore됨 — 실 key.ini는 절대 커밋되지 않음
- 키 백업은 repo 밖 안전한 곳(비밀번호 관리자/암호화 볼륨)

## 검증
- 가동 후 `robotrader_<strategy>.pid` 생성 확인
- KIS 계좌 잔고 = 해당 전략 단독 운용 확인
- `SELECT * FROM real_trading_<strategy>` 로 기록 격리 확인
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore instances/README.md instances/rs_leader/key.ini.example instances/rs_leader/trading_config.json.example run_instance.bat
git commit -m "feat(instance): 배포 자산 — gitignore 보안 + 인스턴스 템플릿 + 기동 스크립트 + 셋업 문서"
```

---

### Task 6: 실전 경로 e2e 검증 (수동/드라이런 게이트)

**Files:**
- Create: `docs/superpowers/plans/2026-06-18-live-validation-checklist.md` (검증 절차·결과 기록)

**목적:** 실주문 코드 성숙도가 미확정(`real_trading_records` 224행 출처 불명)이므로, 실자금 투입 전 전 경로를 1회 통과시킨다. 자동 단위테스트가 아닌 **운영 검증 게이트**.

- [ ] **Step 1: 기존 실거래 레코드 출처 확인**

Run (psycopg2): `SELECT strategy, COUNT(*), MIN(created_at), MAX(created_at) FROM real_trading_records GROUP BY strategy;`
판단: 이 템플릿 전략명이면 실거래 경험 있음 / 형제 프로젝트 전략명(macd_cross_alt 등)이면 미검증 → 검증 강화.

- [ ] **Step 2: 모의계좌(또는 최소금액 실계좌)로 인스턴스 기동**

`instances/rs_leader/` 셋업(모의계좌 키) → `run_instance.bat rs_leader` → 로그에서 확인:
- 설정 로드 경로가 `instances/rs_leader/` 인지
- `real_trading_rs_leader` 테이블 생성 로그
- PID `robotrader_rs_leader.pid` 생성

- [ ] **Step 3: 매수→체결→손익절→EOD 전 경로 1회 통과 관찰**

체크: 실매수 주문 접수 로그(`실전 매수 주문 접수`), 체결 후 `real_trading_rs_leader`에 BUY 행, 손익절/EOD 매도 시 SELL 행 + profit_loss 정합.

- [ ] **Step 4: 페이퍼 인스턴스 무영향 확인**

기존 페이퍼 봇 동시 가동 상태에서 `virtual_trading_records`·`robotrader.pid` 정상, 충돌 없음 확인.

- [ ] **Step 5: 결과 기록 + 소액 1전략 실전 승인 요청**

검증 결과를 체크리스트 문서에 기록. rs_leader 소액 실전 시작 여부는 **사장님 승인** 후.

---

## Self-Review

**1. Spec coverage:**
- 설정 디렉토리 오버라이드(spec §5.1) → Task 1 ✓
- PID 파라미터화(§5.2) → Task 4 ✓
- 매매 테이블명 파라미터화 11곳(§5.3) → Task 2(trading.py 9) + Task 3(database_manager 배선 1) ✓ (database_manager.py:236의 `real_trading_records`는 `_verify_tables` 검증 리스트로, 기본 테이블 존재확인이라 무변경 — 인스턴스 테이블은 repo가 생성)
- 부팅 배선(§5.4) → Task 3 ✓
- .gitignore 보안(§5.5, §6-bis) → Task 5 ✓
- 전략별 매매 테이블 DB(§6) → Task 2 자동생성 ✓
- 키 관리 인스턴스별(§6-bis) → Task 5 템플릿 ✓
- 검증/롤아웃(§7) → Task 6 ✓
- screener_snapshots 공유 수용(§6) → 무작업(설계상 수용) ✓

**2. Placeholder scan:** 모든 코드 스텝에 실제 코드 포함. "적절히 처리" 류 없음. ✓

**3. Type consistency:** `INSTANCE_ID`/`REAL_TRADING_TABLE`(Task1) → Task2/3/4에서 동일명 사용. `_real_table`/`_validate_table_name`/`ensure_real_table`(Task2) 일관. `pid_file_name`(Task4) 일관. ✓
