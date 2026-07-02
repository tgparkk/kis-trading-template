# 연구/운영 경계정리 Phase 1 — 라이브 엣지 승격 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/`에 대한 라이브 의존 엣지 9개(정적 8 + 동적 1)를 전부 운영 트리로 승격해 0으로 만들고, lint 도구를 셋업하고, 연구 파일 전수 인벤토리(`docs/INVENTORY.md`)를 생성한다. **동작 보존(behavior-preserving)** — 전략 로직·매매 행동 변경 없음.

**Architecture:** 이동 1건 = 커밋 1개, 매 커밋 전체 테스트 스위트. 승격 방식은 두 가지: (a) 파일 통째 `git mv`(blame 보존) 후 모든 importer 갱신, (b) 심볼만 운영 위치로 추출하고 원래 연구 파일이 **역방향 re-import**(연구→운영 의존은 허용)해 연구 코드·테스트를 무변경 유지. 죽은 코드 정리(스펙 §4 item 6)는 INVENTORY 결과가 나온 뒤 **별도 후속 계획**으로 분리한다.

**Tech Stack:** Python 3.9 (venv `venv\Scripts\python`), pytest, git mv, ruff/vulture/deptry (신규 설치).

## Global Constraints

- **동작 보존**: 전략 로직·매매 행동·SQL·수치 변경 금지. 이동/재배선만.
- **이동 1건 = 커밋 1개**, 매 커밋 전 `venv\Scripts\python -m pytest tests/ -q` 전체 통과 (baseline은 Task 0에서 캡처).
- **기지 실패(known-fail) 1건**: `tests/test_discovery.py::test_bb_reversion_triggers` — main 기존 결함(연구 전용 bb_reversion 룰의 ADX 경계선 취약 테스트, 06-30 venv 패키지 갱신으로 수치 이동, 라이브 무관). 이 계획에서 고치지 않는다. 모든 태스크의 통과 기준 = **baseline passed 수 유지 + 실패는 정확히 이 1건만**(신규 실패 0). 사장님 결정 후 별도 수정.
- repo 루트 = `D:\GIT\kis-trading-template\RoboTrader_template` (모든 경로·명령의 cwd).
- 브랜치: `feat/research-production-separation-phase1` (main에서 분기). main 머지·push는 사용자 승인 후.
- Python 3.9 호환: `X | None` 파라미터 문법이 있는 코드를 옮길 때 `from __future__ import annotations`를 반드시 동반.
- 스펙: `docs/superpowers/specs/2026-06-30-research-production-separation-design.md` §4 Phase 1 + 가드레일.
- 완료 후 `docs/CODE_MAP.md`·`CLAUDE.md` 라우팅 블록 갱신(Task 11) — 갱신 전까지 두 문서는 이동 전 상태 기준.

---

### Task 0: 브랜치 + 그린 baseline + 동적 import 카탈로그

**Files:**
- Create: 없음 (검증·기록만, baseline 로그는 `scratchpad/`에)

**Interfaces:**
- Produces: 그린 baseline(통과 개수), 이후 모든 Task가 이 개수와 비교.

- [ ] **Step 1: 브랜치 생성**

```bash
git checkout -b feat/research-production-separation-phase1
```

- [ ] **Step 2: 전체 테스트 그린 baseline 캡처**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -5`
Expected: `NNNN passed` (0 failed). 통과 개수 NNNN을 기록 — 이후 모든 Task의 Expected 기준값. **실패가 있으면 STOP하고 보고** (baseline이 깨진 상태에서 이동 금지).

- [ ] **Step 3: .gitignore 가드 (`git add -A` 안전화)**

작업트리에 untracked `venv_broken_quantcopy/`(venv 백업)·`scratchpad/`가 있어 이후 태스크들의 `git add -A`가 통째로 스테이징할 위험. `.gitignore`에 두 줄 추가:

```
venv_broken_quantcopy/
scratchpad/
```

Run: `git status --short | grep -v "^??" ; git check-ignore venv_broken_quantcopy scratchpad && echo ignored-OK`
Expected: `ignored-OK`. 커밋: `git add .gitignore && git commit -m "chore(git): venv 백업·scratchpad ignore 가드"`

- [ ] **Step 4: 동적 import 전수 카탈로그 (가드레일 §4-②)**

```bash
grep -rn "import_module\|__import__" --include="*.py" . | grep -v __pycache__ | grep -v tests/
grep -rn "scripts" *.bat *.ps1 2>/dev/null
```
Expected: 동적 import 라이브 = `collectors/daily_adj.py:8` 1건뿐(연구 내부의 `scripts/book_rebalance_multiverse.py`, `scripts/book_param_multiverse.py`는 이번 이동 대상과 무관하므로 확인만). `.bat`은 `매일_분석_실행.bat:23`·`장마감_자동분석.bat:14` 2건. 예상 밖 항목이 나오면 기록하고, 이동 대상과 겹치면 STOP.

---

### Task 1: rs_leader 진입룰 승격 (`scripts/rs_leader/rule.py` → `strategies/rs_leader/rule.py`)

**Files:**
- Move: `scripts/rs_leader/rule.py` → `strategies/rs_leader/rule.py` (git mv, 40줄, 내부 import는 pandas·`strategies.base`뿐이라 무수정)
- Modify: `strategies/rs_leader/strategy.py:16`, `strategies/rs_leader/screener.py:14`, `scripts/multiverse4_returns_export.py:76`, `scripts/rs_leader_validation.py:29`, `tests/rs_leader/test_rule.py:5`
- 참고: `scripts/rs_leader/decompose.py`·`exit_adapter.py`는 rule을 import하지 않음(확인됨) → 잔류.

**Interfaces:**
- Produces: `strategies.rs_leader.rule.RSLeaderRule` (클래스 시그니처 무변경: `RSLeaderRule(ma_short=20, ma_long=60, abs_lb=60)`, `generate_signal(stock_code, df, timeframe="daily")`).

- [ ] **Step 1: 파일 이동**

```bash
git mv scripts/rs_leader/rule.py strategies/rs_leader/rule.py
```

- [ ] **Step 2: importer 5곳 갱신**

5개 파일에서 `from scripts.rs_leader.rule import RSLeaderRule` → `from strategies.rs_leader.rule import RSLeaderRule` 로 교체. `strategies/rs_leader/strategy.py:3`·`screener.py:5`의 docstring 내 `scripts.rs_leader.rule` 언급도 `strategies.rs_leader.rule`로 갱신.

- [ ] **Step 3: 잔존 참조 0 확인**

Run: `grep -rn "scripts.rs_leader.rule\|scripts\.rs_leader import rule" --include="*.py" . | grep -v __pycache__`
Expected: 0건.

- [ ] **Step 4: 전체 테스트**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3`
Expected: baseline과 동일 `NNNN passed`.

- [ ] **Step 5: 커밋**

```bash
git add -A && git commit -m "refactor(rs_leader): 진입룰을 strategies/rs_leader/로 승격 (라이브 엣지 -2)"
```

---

### Task 2: MeanReversionMA20Rule 승격 (`scripts/discovery/rules.py` → `strategies/deep_mr_dev20/rule.py`)

**Files:**
- Create: `strategies/deep_mr_dev20/rule.py` — `scripts/discovery/rules.py:282-316`의 `MeanReversionMA20Rule` 클래스를 **verbatim** 이동 + 필요한 import
- Modify: `scripts/discovery/rules.py` (클래스 정의 삭제 → re-export로 대체), `strategies/deep_mr_dev20/strategy.py:18`, `strategies/deep_mr_dev20/screener.py:15`
- 무변경 유지(re-export 덕): `scripts/strategy_gate.py:49`, `scripts/multiverse4_returns_export.py:70`, `tests/test_discovery.py:27`

**Interfaces:**
- Produces: `strategies.deep_mr_dev20.rule.MeanReversionMA20Rule` (시그니처 무변경: `MeanReversionMA20Rule(ma_period=20, entry_deviation_pct=-10.0, rsi_period=14, rsi_oversold=30.0, use_rsi_filter=True)`).
- `scripts.discovery.rules.MeanReversionMA20Rule`은 re-export로 **계속 유효** (연구 코드·기존 테스트 호환).

- [ ] **Step 1: 신규 파일 작성** — `strategies/deep_mr_dev20/rule.py`:

```python
"""deep_mr_dev20 진입룰 — MA20 이탈 평균회귀 (scripts/discovery/rules.py 에서 승격).

원 정의: scripts/discovery/rules.py (2026-07-02 Phase1 승격, 동작 무변경).
"""
from __future__ import annotations

import pandas as pd

from strategies.base import Signal, SignalType
from utils.indicators import calculate_rsi


# (여기에 scripts/discovery/rules.py:282-316 의 MeanReversionMA20Rule 클래스 본문을
#  한 글자도 바꾸지 않고 그대로 붙여넣는다)
```

- [ ] **Step 2: `scripts/discovery/rules.py`에서 클래스 정의를 re-export로 대체**

282행부터의 `class MeanReversionMA20Rule:` 정의 전체(파일 끝까지)를 삭제하고, 파일의 기존 import 블록 아래(또는 삭제 지점)에 추가:

```python
# MeanReversionMA20Rule 은 라이브 전략이 소유 → strategies 로 승격 (2026-07-02 Phase1).
# 연구 코드 호환을 위한 re-export.
from strategies.deep_mr_dev20.rule import MeanReversionMA20Rule  # noqa: E402,F401
```

- [ ] **Step 3: 라이브 importer 2곳 갱신**

`strategies/deep_mr_dev20/strategy.py:18`·`screener.py:15`: `from scripts.discovery.rules import MeanReversionMA20Rule` → `from strategies.deep_mr_dev20.rule import MeanReversionMA20Rule`. `strategy.py:4` docstring의 `scripts.discovery.rules.MeanReversionMA20Rule` 언급도 갱신.

- [ ] **Step 4: 검증 — 동일 객체 + 잔존 참조**

Run: `venv\Scripts\python -c "from scripts.discovery.rules import MeanReversionMA20Rule as A; from strategies.deep_mr_dev20.rule import MeanReversionMA20Rule as B; assert A is B; print('same-object OK')"`
Expected: `same-object OK`.
Run: `grep -rn "from scripts.discovery.rules import MeanReversionMA20Rule" --include="*.py" strategies/ | grep -v __pycache__`
Expected: 0건.

- [ ] **Step 5: 전체 테스트 + 커밋**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3` → Expected: `NNNN passed`.

```bash
git add -A && git commit -m "refactor(deep_mr): MeanReversionMA20Rule을 strategies/deep_mr_dev20/으로 승격 (라이브 엣지 -2)"
```

---

### Task 3: `tools/` 신설 + daily_trading_summary 이동

**Files:**
- Create: `tools/__init__.py` (내용: `"""운영 도구(EOD 리포트·equity 스냅샷) — 라이브 봇이 import하는 비(非)전략 운영 코드."""`)
- Move: `scripts/daily_trading_summary.py` → `tools/daily_trading_summary.py` (git mv; `sys.path.insert(0, dirname(dirname(__file__)))` 패턴은 tools/도 깊이 1이라 무수정으로 유효)
- Modify: `bot/system_monitor.py:11`, `매일_분석_실행.bat:23`

**Interfaces:**
- Produces: `tools.daily_trading_summary.print_today_trading_summary()` (시그니처 무변경, 인자 없음).

- [ ] **Step 1: tools 패키지 생성 + 파일 이동**

```bash
mkdir tools
git mv scripts/daily_trading_summary.py tools/daily_trading_summary.py
```
`tools/__init__.py`를 위 docstring 한 줄로 생성 후 `git add tools/__init__.py`.

- [ ] **Step 2: importer 갱신**

- `bot/system_monitor.py:11`: `from scripts.daily_trading_summary import print_today_trading_summary` → `from tools.daily_trading_summary import print_today_trading_summary`
- `매일_분석_실행.bat:23`: `python scripts\daily_trading_summary.py` → `python tools\daily_trading_summary.py`

- [ ] **Step 3: 검증**

```bash
grep -rn "scripts.daily_trading_summary\|scripts\\\\daily_trading_summary" --include="*.py" --include="*.bat" . | grep -v __pycache__
venv\Scripts\python -c "from tools.daily_trading_summary import print_today_trading_summary; print('import OK')"
```
Expected: grep 0건, `import OK`.

- [ ] **Step 4: 전체 테스트 + 커밋**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3` → Expected: `NNNN passed`.

```bash
git add -A && git commit -m "refactor(tools): daily_trading_summary를 tools/로 승격 + .bat 경로 동반수정 (라이브 엣지 -1)"
```

---

### Task 4: paper_strategy_equity 이동 (`scripts/` → `tools/`)

**Files:**
- Move: `scripts/paper_strategy_equity.py` → `tools/paper_strategy_equity.py` (git mv; sys.path 패턴 동일 깊이라 무수정)
- Modify: `bot/system_monitor.py:245`, `tests/test_paper_strategy_equity.py:14`, `tests/test_trading_flow.py:491,512` (patch 문자열), `scripts/fix_079650_fictional_fill.py:19,98` (안내 문자열 — 기능 무관이지만 오도 방지)

**Interfaces:**
- Produces: `tools.paper_strategy_equity.run_daily_equity_snapshot(conn, epoch=None, ...)` · `replay_strategy_equity(...)` · `_load_closes(...)` (전부 시그니처 무변경).

- [ ] **Step 1: 파일 이동**

```bash
git mv scripts/paper_strategy_equity.py tools/paper_strategy_equity.py
```

- [ ] **Step 2: importer·patch 문자열 갱신**

- `bot/system_monitor.py:245`: `from scripts.paper_strategy_equity import run_daily_equity_snapshot` → `from tools.paper_strategy_equity import run_daily_equity_snapshot`
- `tests/test_paper_strategy_equity.py:14`: `from scripts.paper_strategy_equity import replay_strategy_equity, _load_closes` → `from tools.paper_strategy_equity import replay_strategy_equity, _load_closes`
- `tests/test_trading_flow.py:491,512`: `patch('scripts.paper_strategy_equity.run_daily_equity_snapshot')` → `patch('tools.paper_strategy_equity.run_daily_equity_snapshot')`
- `scripts/fix_079650_fictional_fill.py:19,98`: 문자열 내 `python scripts/paper_strategy_equity.py` → `python tools/paper_strategy_equity.py`

- [ ] **Step 3: 검증**

Run: `grep -rn "scripts.paper_strategy_equity" --include="*.py" . | grep -v __pycache__`
Expected: 0건.

- [ ] **Step 4: 전체 테스트 + 커밋**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3` → Expected: `NNNN passed` (특히 `tests/test_trading_flow.py`·`tests/test_paper_strategy_equity.py` 그린 필수).

```bash
git add -A && git commit -m "refactor(tools): paper_strategy_equity를 tools/로 승격 (라이브 엣지 -1)"
```

---

### Task 5: SQL_UPDATE_RETURNS 상수 승격 (`scripts/etl_backfill_daily_prices.py` → `collectors/daily_derived.py`)

**Files:**
- Modify: `collectors/daily_derived.py` (상수 정의를 이 파일로 이전 — 유일한 운영 소비처), `scripts/etl_backfill_daily_prices.py:101` (정의 삭제 → 역방향 import), `tests/collectors/test_daily_derived.py:3`

**Interfaces:**
- Produces: `collectors.daily_derived.SQL_UPDATE_RETURNS` (SQL 문자열, 내용 **한 글자도 무변경**).
- `scripts.etl_backfill_daily_prices.SQL_UPDATE_RETURNS`는 역방향 import로 계속 유효(연구 스크립트 내부 사용처 `:471` 무수정).

- [ ] **Step 1: 상수 verbatim 이전**

`scripts/etl_backfill_daily_prices.py`의 `SQL_UPDATE_RETURNS = """..."""` 블록(101행 시작, 다음 상수 `SQL_VERIFY_RANGE`(166행) 직전까지)을 **그대로 잘라내어** `collectors/daily_derived.py`의 기존 import 아래·함수 위에 붙여넣는다. `collectors/daily_derived.py:3`의 `from scripts.etl_backfill_daily_prices import SQL_UPDATE_RETURNS` 행은 삭제.

- [ ] **Step 2: 연구 스크립트에 역방향 import 추가**

`scripts/etl_backfill_daily_prices.py`의 상수 삭제 지점에:

```python
# SQL_UPDATE_RETURNS 는 운영 수집기가 소유 → collectors 로 승격 (2026-07-02 Phase1).
from collectors.daily_derived import SQL_UPDATE_RETURNS  # noqa: E402
```

⚠️ **역방향 import 공통 함정**: 이 스크립트는 `python scripts/etl_backfill_daily_prices.py`로 직접 실행되며, 이때 sys.path[0]=scripts/라 `collectors`가 안 잡힌다. 기존 `_ROOT`(line 37) 계산 직후에 `sys.path.insert(0, _ROOT)`를 추가한 뒤 역방향 import를 배치할 것. 검증: `venv\Scripts\python scripts/etl_backfill_daily_prices.py --help`가 ModuleNotFoundError 없이 usage 출력.

- [ ] **Step 3: 테스트 import 갱신**

`tests/collectors/test_daily_derived.py:3`: `from scripts.etl_backfill_daily_prices import SQL_UPDATE_RETURNS` → `from collectors.daily_derived import SQL_UPDATE_RETURNS`

- [ ] **Step 4: 검증 — 동일 객체 + SQL 무변경**

Run: `venv\Scripts\python -c "from collectors.daily_derived import SQL_UPDATE_RETURNS as A; from scripts.etl_backfill_daily_prices import SQL_UPDATE_RETURNS as B; assert A is B; print(len(A), 'same-object OK')"`
Expected: `same-object OK` (길이 출력은 이동 전 `git show HEAD:scripts/etl_backfill_daily_prices.py` 기준 상수 길이와 대조).

- [ ] **Step 5: 전체 테스트 + 커밋**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3` → Expected: `NNNN passed`.

```bash
git add -A && git commit -m "refactor(collectors): SQL_UPDATE_RETURNS를 daily_derived로 승격 (라이브 엣지 -1)"
```

---

### Task 6: 동적 import 정상화 (`compute_adj_factors` → `collectors/adj_factors.py`) — **최대 지뢰, 전용 가드**

**Files:**
- Create: `collectors/adj_factors.py` — `scripts/10pct_strategy/p0_apply_adj_factor.py:137-160`의 `compute_adj_factors` 함수를 verbatim 이동 (의존: `math`, `datetime.date` 뿐인 순수 함수)
- Modify: `collectors/daily_adj.py:1-9` (importlib 제거 → 정상 import), `scripts/10pct_strategy/p0_apply_adj_factor.py` (함수 삭제 → 역방향 import)
- Test: `tests/collectors/test_adj_factors.py` (신규 characterization 테스트)

**Interfaces:**
- Produces: `collectors.adj_factors.compute_adj_factors(events: dict, stock_dates: dict) -> dict` — `{stock: [(event_date, split_factor)]}` × `{stock: [date_str]}` → `{stock: {date_str: adj_factor}}`, `adj_factor(T) = ∏(sf for (ed,sf) if ed > T)`. 시그니처·수치 무변경.

- [ ] **Step 1: characterization 테스트 먼저 작성 (이동 전 현행 동작 고정)**

`tests/collectors/test_adj_factors.py`:

```python
"""compute_adj_factors 승격(동적 import 정상화) characterization — 동작 보존 검증."""
import datetime as dt


def test_compute_adj_factors_behavior_preserved():
    from collectors.adj_factors import compute_adj_factors
    events = {"005930": [(dt.date(2026, 3, 2), 0.02)]}
    stock_dates = {"005930": ["2026-02-27", "2026-03-02", "2026-03-03"]}
    out = compute_adj_factors(events, stock_dates)
    assert out["005930"]["2026-02-27"] == 0.02   # 이벤트 이전 날짜 → 분할계수 적용
    assert out["005930"]["2026-03-02"] == 1.0    # ed > T 조건: 당일은 미적용
    assert out["005930"]["2026-03-03"] == 1.0


def test_daily_adj_uses_promoted_function():
    """daily_adj가 importlib 없이 승격된 함수를 바인딩하는지."""
    import collectors.daily_adj as da
    from collectors.adj_factors import compute_adj_factors
    assert da.compute_adj_factors is compute_adj_factors


def test_research_script_reimports_same_object():
    """연구 스크립트(p0)의 역방향 import가 같은 객체인지 (숫자 시작 디렉토리라 importlib)."""
    import importlib
    p0 = importlib.import_module("scripts.10pct_strategy.p0_apply_adj_factor")
    from collectors.adj_factors import compute_adj_factors
    assert p0.compute_adj_factors is compute_adj_factors
```

- [ ] **Step 2: 실행해 실패 확인**

Run: `venv\Scripts\python -m pytest tests/collectors/test_adj_factors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collectors.adj_factors'`

- [ ] **Step 3: `collectors/adj_factors.py` 작성**

```python
"""분할이벤트 → adj_factor 계산 (scripts/10pct_strategy/p0_apply_adj_factor.py 에서 승격).

승격 사유: collectors/daily_adj.py 가 라이브 EOD 경로에서 사용하는데, 원 위치가
숫자 시작 디렉토리(10pct_strategy)라 importlib 동적 import 를 강제 — 정적 분석 불가
지뢰였음 (2026-07-02 Phase1, 동작 무변경).
"""
import math
from datetime import date


# (여기에 p0_apply_adj_factor.py:137-160 의 compute_adj_factors 함수 본문을
#  한 글자도 바꾸지 않고 그대로 붙여넣는다)
```

- [ ] **Step 4: `collectors/daily_adj.py` importlib 제거**

1~9행을 다음으로 교체 (나머지 함수들 무수정):

```python
# collectors/daily_adj.py
"""adj_factor 갱신 — corp_events 분할이벤트 기반(새 DB). compute_adj_factors 재사용."""
import psycopg2.extras

from collectors.adj_factors import compute_adj_factors
```

- [ ] **Step 5: p0에 역방향 import**

`scripts/10pct_strategy/p0_apply_adj_factor.py:137-160`의 함수 정의를 삭제하고 그 자리에:

```python
# compute_adj_factors 는 라이브 수집기가 소유 → collectors 로 승격 (2026-07-02 Phase1).
from collectors.adj_factors import compute_adj_factors  # noqa: E402
```

⚠️ **역방향 import 공통 함정**(Task 5 리뷰에서 발견): 직접 실행(`python scripts/10pct_strategy/p0_apply_adj_factor.py`) 시 sys.path[0]가 스크립트 디렉토리라 `collectors`가 안 잡힌다. 파일 상단 import 블록(기존 `import sys/os` 이후)에 repo 루트 부트스트랩을 추가할 것 — **깊이 2이므로 dirname 3중**:
```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
```
검증: `venv\Scripts\python scripts/10pct_strategy/p0_apply_adj_factor.py --help 2>&1 | head -3`가 ModuleNotFoundError 없이 동작(인자 파서가 없으면 DB 접속 전 단계까지 import 성공 확인으로 갈음 — DB 쓰기 실행 금지).

- [ ] **Step 6: 테스트 통과 + 라이브 동등성 스모크**

Run: `venv\Scripts\python -m pytest tests/collectors/test_adj_factors.py -v` → Expected: 3 PASS.
Run: `venv\Scripts\python -c "from collectors.daily_adj import update_adj_factors; print('live import chain OK')"` → Expected: `live import chain OK`.

- [ ] **Step 7: 전체 테스트 + 커밋**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3` → Expected: `NNNN+3 passed`.

```bash
git add -A && git commit -m "refactor(collectors): compute_adj_factors 승격 — daily_adj 동적 import 지뢰 제거 (라이브 엣지 -1)"
```

---

### Task 7: fetch_foreign_naver 승격 (`scripts/backfill_foreign_flow.py` → `collectors/foreign_flow_fetcher.py`)

**Files:**
- Create: `collectors/foreign_flow_fetcher.py` — `scripts/backfill_foreign_flow.py:66-163`의 `_make_session`·`fetch_foreign_naver`를 verbatim 이동
- Modify: `collectors/foreign_flow_collector.py:19`, `scripts/backfill_foreign_flow.py` (두 함수 삭제 → 역방향 import)
- 무변경 확인: `tests/collectors/test_foreign_flow_collector.py`는 `ffc.fetch_foreign_naver` **모듈 속성**을 monkeypatch(80·93·104행)하므로 collector가 `from ... import fetch_foreign_naver`로 이름을 바인딩하는 한 무수정.

**Interfaces:**
- Produces: `collectors.foreign_flow_fetcher.fetch_foreign_naver(code: str, max_pages: int = 40, session=None) -> pd.DataFrame` (시그니처·PIT 규칙 무변경), `_make_session() -> requests.Session`.

- [ ] **Step 1: 신규 파일 작성**

```python
"""네이버 금융 외국인 순매매량 fetch (scripts/backfill_foreign_flow.py 에서 승격).

라이브 EOD 수집기(collectors/foreign_flow_collector.py)가 사용 (2026-07-02 Phase1, 동작 무변경).
PIT 강제: T일 데이터를 T일로 저장, shift(-N) 절대 금지.
"""
from __future__ import annotations

from io import StringIO

import pandas as pd
import requests


# (여기에 scripts/backfill_foreign_flow.py:66-163 의 _make_session 과
#  fetch_foreign_naver 를 한 글자도 바꾸지 않고 그대로 붙여넣는다.
#  ⚠️ 함수 본문이 위 import 외 모듈(time, logging 등)을 쓰면 해당 import 도 동반 이동.)
```

⚠️ `from __future__ import annotations` 필수 — `session: requests.Session | None` 문법이 Python 3.9에서 이것 없이 SyntaxError.

- [ ] **Step 2: 원 파일에 역방향 import + collector 갱신**

`scripts/backfill_foreign_flow.py`의 두 함수 삭제 지점에:

```python
# fetch_foreign_naver 는 라이브 수집기가 소유 → collectors 로 승격 (2026-07-02 Phase1).
from collectors.foreign_flow_fetcher import _make_session, fetch_foreign_naver  # noqa: E402,F401
```

⚠️ **역방향 import 공통 함정**(Task 5 리뷰에서 발견): 직접 실행(`python scripts/backfill_foreign_flow.py`, docstring line 15의 문서화된 usage) 시 sys.path[0]=scripts/라 `collectors`가 안 잡힌다. 역방향 import 직전에 부트스트랩 추가(깊이 1 = dirname 2중):
```python
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
```
검증: `venv\Scripts\python scripts/backfill_foreign_flow.py --help`가 ModuleNotFoundError 없이 usage 출력.

`collectors/foreign_flow_collector.py:19`: `from scripts.backfill_foreign_flow import fetch_foreign_naver` → `from collectors.foreign_flow_fetcher import fetch_foreign_naver`

- [ ] **Step 3: 검증**

```bash
venv\Scripts\python -c "from scripts.backfill_foreign_flow import fetch_foreign_naver as A; from collectors.foreign_flow_fetcher import fetch_foreign_naver as B; assert A is B; print('same-object OK')"
venv\Scripts\python -m pytest tests/collectors/test_foreign_flow_collector.py tests/collectors/test_foreign_flow_writer.py tests/test_phase5_foreign_flow.py -q
```
Expected: `same-object OK` + 대상 테스트 전부 PASS.

- [ ] **Step 4: 전체 테스트 + 커밋**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3` → Expected: 전부 passed.

```bash
git add -A && git commit -m "refactor(collectors): fetch_foreign_naver 승격 (라이브 엣지 -1, scripts 라이브 엣지 = 0 달성)"
```

---

### Task 8: 죽은 .bat 엔트리포인트 처리 (`장마감_자동분석.bat`)

**Files:**
- Modify: `장마감_자동분석.bat` (14행이 호출하는 `scripts/auto_analysis.py`는 **존재하지 않음** — 2026-07-02 확인된 드리프트)

**Interfaces:** 없음 (엔트리포인트 정리).

- [ ] **Step 1: 존재하지 않는 호출 비활성화**

`장마감_자동분석.bat`의 11·14행을 다음으로 교체:

```bat
REM [2026-07-02] scripts/auto_analysis.py 는 저장소에 존재하지 않아 비활성화 (Phase1).
REM 복구 시 docs/CODE_MAP.md 의 .bat 섹션도 함께 갱신할 것.
echo (auto_analysis.py 부재로 분석 스킵 — docs/CODE_MAP.md 참조)
```

- [ ] **Step 2: 검증 + 커밋**

Run: `grep -n "auto_analysis" 장마감_자동분석.bat` → Expected: REM 처리된 2행만.

```bash
git add 장마감_자동분석.bat && git commit -m "chore(bat): 존재하지 않는 auto_analysis.py 호출 비활성화"
```

---

### Task 9: lint 도구 셋업 (ruff/vulture/deptry + 설정)

**Files:**
- Create: `pyproject.toml` (도구 설정 전용 — 패키징 아님), `ruff.toml` 은 pyproject 내 `[tool.ruff]`로 갈음
- Modify: 없음 (코드 무변경, requirements.txt 도 건드리지 않음 — 개발 전용 도구라 라이브 의존성에 안 섞음)

**Interfaces:**
- Produces: `venv\Scripts\python -m ruff check .` 실행 가능 상태. 이후 인벤토리(Task 10)·후속 죽은코드 정리에서 사용.

- [ ] **Step 1: 도구 설치**

Run: `venv\Scripts\python -m pip install ruff vulture deptry`
Expected: Successfully installed. (봇 런타임 의존성 아님 — requirements.txt 미기재 의도적.)

- [ ] **Step 2: `pyproject.toml` 작성**

```toml
# lint/분석 도구 설정 전용 (패키징 아님). 동작 영향 0.
[tool.ruff]
target-version = "py39"
line-length = 120
# 연구/일회성 코드는 lint 대상 제외 (docs/CODE_MAP.md 의 경계와 일치)
extend-exclude = ["scripts", "multiverse", "books", "council", "venv", "venv_broken_quantcopy", "archive"]

[tool.ruff.lint]
select = ["E9", "F63", "F7", "F82"]  # 시작은 치명 오류만(문법·미정의명). 점진 확대.
```

- [ ] **Step 3: 검증 — 운영 트리 치명 lint 0 확인**

Run: `venv\Scripts\python -m ruff check . 2>&1 | tail -3`
Expected: `All checks passed!` (오류가 나오면 **고치지 말고 STOP·보고** — 이 Task는 도구 셋업만, 코드 수정은 범위 밖).

- [ ] **Step 4: 전체 테스트 + 커밋**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3` → Expected: 전부 passed.

```bash
git add pyproject.toml && git commit -m "chore(lint): ruff/vulture/deptry 셋업 — 운영 트리 치명 오류만 게이트"
```

---

### Task 10: 연구 파일 전수 인벤토리 (`docs/INVENTORY.md`)

**Files:**
- Create: `tools/gen_inventory.py` (AST import-graph 워커), `docs/INVENTORY.md` (생성 결과)

**Interfaces:**
- Consumes: Task 1~7 완료 상태 (scripts 라이브 엣지 = 0).
- Produces: `docs/INVENTORY.md` — `scripts/`·`multiverse/` 전 파일을 `LIVE-DEP / 운영도구 / 테스트전용 / 무참조(죽음 후보)`로 태깅. **후속 죽은코드 정리 계획의 입력.**

- [ ] **Step 1: `tools/gen_inventory.py` 작성**

```python
"""연구 디렉토리(scripts/, multiverse/) 인벤토리 생성 — AST import 그래프 기반.

분류:
  LIVE-DEP   : 운영 디렉토리 파일이 import (Phase1 이후 0이어야 정상)
  TEST-ONLY  : tests/ 만 import
  RESEARCH   : 연구 파일끼리만 import
  UNREFERENCED: 어디서도 import 안 됨 (죽음 후보 — 단, 동적 import/CLI 직접실행은 수동확인)
사용: venv\\Scripts\\python tools/gen_inventory.py > docs/INVENTORY.md
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROD_DIRS = ["core", "bot", "framework", "api", "strategies", "collectors",
             "db", "runners", "signals", "lib", "utils", "tools", "config"]
RESEARCH_DIRS = ["scripts", "multiverse"]
SKIP_DIRS = {"__pycache__", "venv", "venv_broken_quantcopy", ".git", "logs", "reports"}


def iter_py(dirs):
    for d in dirs:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            for f in filenames:
                if f.endswith(".py"):
                    yield os.path.relpath(os.path.join(dirpath, f), ROOT)


def module_name(relpath):
    return relpath[:-3].replace(os.sep, ".").replace("/", ".")


def imports_of(relpath):
    try:
        with open(os.path.join(ROOT, relpath), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (SyntaxError, UnicodeDecodeError):
        return set()
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
        elif isinstance(node, ast.Call):
            # importlib.import_module("...") / __import__("...") 리터럴 인자 포착
            fn = node.func
            name = (getattr(fn, "attr", "") or getattr(fn, "id", ""))
            if name in ("import_module", "__import__") and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                mods.add(node.args[0].value)
    return mods


def main():
    research = {module_name(p): p for p in iter_py(RESEARCH_DIRS)}
    referrers = {m: [] for m in research}  # research module -> [참조자 relpath]
    for scope, dirs in (("PROD", PROD_DIRS), ("TEST", ["tests"]), ("RESEARCH", RESEARCH_DIRS)):
        for p in iter_py(dirs):
            for m in imports_of(p):
                for rm in research:
                    if m == rm or m.startswith(rm + "."):
                        referrers[rm].append((scope, p))
    print("# INVENTORY — 연구 파일 참조 태깅 (tools/gen_inventory.py 생성)\n")
    print("| 파일 | 태그 | 참조자 |")
    print("|---|---|---|")
    for rm, path in sorted(research.items()):
        refs = [r for r in referrers[rm] if r[1] != path]
        scopes = {s for s, _ in refs}
        tag = ("LIVE-DEP" if "PROD" in scopes else
               "TEST-ONLY" if scopes == {"TEST"} else
               "RESEARCH" if scopes else "UNREFERENCED")
        ref_str = "; ".join(f"{s}:{p}" for s, p in sorted(set(refs))[:5]) or "-"
        print(f"| `{path}` | {tag} | {ref_str} |")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 생성 + 핵심 불변식 검증**

```bash
venv\Scripts\python tools/gen_inventory.py > docs/INVENTORY.md
grep -c "LIVE-DEP" docs/INVENTORY.md
```
Expected: `LIVE-DEP` **0건** (Task 1~7이 전부 성공했다는 독립 증명). 0이 아니면 STOP — 누락 엣지 발견이므로 보고 후 해당 엣지 승격 태스크 추가.

- [ ] **Step 3: 헤더에 수동 카탈로그 주석 추가**

`docs/INVENTORY.md` 상단에 수동 확인 사항 추가: 연구 내부 동적 import(`scripts/book_rebalance_multiverse.py:428`, `scripts/book_param_multiverse.py:90-93`)는 AST 리터럴 포착 한계로 수동 표기, `UNREFERENCED`여도 `.bat`/CLI 직접 실행·`__main__` 파일은 죽음 아님 — 후속 정리 계획에서 파일별 판정.

- [ ] **Step 4: 전체 테스트 + 커밋**

Run: `venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3` → Expected: 전부 passed.

```bash
git add tools/gen_inventory.py docs/INVENTORY.md && git commit -m "docs(inventory): 연구 파일 전수 인벤토리 + AST 생성기 (LIVE-DEP=0 검증)"
```

---

### Task 11: CODE_MAP·CLAUDE.md 갱신 + 최종 검증

**Files:**
- Modify: `docs/CODE_MAP.md` (9엣지 표 → "승격 완료·엣지 0" 이력으로 전환, `tools/` 운영 분류 추가, .bat 섹션 갱신), `CLAUDE.md` (라우팅 블록의 "9엣지 존재" 문구 갱신)

**Interfaces:**
- Consumes: Task 1~10 전부 완료.

- [ ] **Step 1: CODE_MAP.md 갱신**

- 운영 디렉토리 목록에 `tools/` 추가.
- "라이브 → 연구 의존 엣지" 섹션을 "**0건 (2026-07-02 Phase1 승격 완료)**"로 바꾸고, 기존 9엣지 표는 "승격 이력" 표로 유지(각 행에 새 위치 병기: rule→`strategies/rs_leader/rule.py`, MR20→`strategies/deep_mr_dev20/rule.py`, EOD 도구 2본→`tools/`, SQL 상수→`collectors/daily_derived.py`, compute_adj_factors→`collectors/adj_factors.py`, fetch_foreign_naver→`collectors/foreign_flow_fetcher.py`).
- .bat 섹션: `매일_분석_실행.bat:23` → `tools\daily_trading_summary.py`로 갱신, `장마감_자동분석.bat` → "비활성(auto_analysis.py 부재)" 표기.
- 검증 명령 섹션의 Expected를 "0건"으로 갱신.

- [ ] **Step 2: CLAUDE.md 라우팅 블록 갱신**

"예외: 라이브가 실제로 의존하는 연구 파일이 9엣지 존재…" 문단을 다음으로 교체:

```markdown
**예외 없음 (2026-07-02 Phase1 완료)**: `scripts/`·`multiverse/`에 라이브 의존 엣지 0.
운영 도구는 `tools/`(EOD 리포트·equity 스냅샷). 승격 이력·드리프트 점검 명령은 [docs/CODE_MAP.md](docs/CODE_MAP.md).
```

운영 디렉토리 나열에 `tools/` 추가.

- [ ] **Step 3: 최종 전수 검증 (스펙 §6 성공 기준)**

```bash
grep -rn "from scripts\|import scripts\|from multiverse\|import multiverse" bot/ collectors/ strategies/ core/ framework/ api/ db/ runners/ signals/ lib/ utils/ tools/ --include="*.py" | grep -v __pycache__
grep -rn "import_module\|__import__" bot/ collectors/ core/ framework/ api/ db/ runners/ signals/ tools/ --include="*.py" | grep -v __pycache__
venv\Scripts\python -m pytest tests/ -q --tb=short 2>&1 | tail -3
```
Expected: 두 grep 모두 **0건**, 전체 테스트 전부 passed (baseline NNNN + Task6 신규 3).

- [ ] **Step 4: 커밋**

```bash
git add docs/CODE_MAP.md CLAUDE.md && git commit -m "docs(map): Phase1 완료 반영 — 라이브→연구 엣지 0, tools/ 운영 편입"
```

---

## 완료 후 (계획 범위 밖, 사용자 승인 필요)

1. main 머지·push (사용자 승인).
2. **봇 재시작 필요**: `bot/system_monitor.py`·`collectors/daily_adj.py`·`foreign_flow_collector.py` import 경로가 바뀌므로 실행 중 프로세스는 구 경로 메모리 상태 — 다음 장전 재기동 시 반영. EOD 훅(`매일_분석_실행.bat`) 첫 실행 결과 관찰.
3. 죽은 코드 정리(스펙 §4 item 6): `docs/INVENTORY.md`의 `UNREFERENCED` 목록 기반 **별도 계획** 수립.
4. 메모리 changelog 작성.

## Self-Review

**1. Spec coverage (§4 Phase 1):** item 3 도구셋업→Task 9 ✅ / item 4 인벤토리→Task 10 ✅ / item 5 승격 6항목(rule·rules·EOD 2본·SQL·동적 import)+신규 9번째 엣지→Task 1~7 ✅ / `장마감_자동분석.bat` 경로 점검→Task 8 (파일 부재 확인·비활성화) ✅ / item 6 죽은코드 정리→**의도적 범위 밖**(INVENTORY 결과가 입력이므로 후속 계획, 본문 명시) ✅ / 가드레일 ①baseline→Task 0-2 ②동적 import 카탈로그→Task 0-3 ③.bat grep→Task 0-3·Task 3·8 ④LIVE-DEP 우선 승격 후 정리→태스크 순서 그대로 ✅

**2. Placeholder scan:** "verbatim 붙여넣기" 지시는 라인 범위(282-316, 66-163, 137-160, 101~166직전)와 동반 import·검증 명령(같은 객체 assert)이 명시돼 실행 모호성 없음. TBD/TODO 없음. ✅

**3. Type consistency:** `RSLeaderRule`·`MeanReversionMA20Rule`·`fetch_foreign_naver`·`compute_adj_factors`·`SQL_UPDATE_RETURNS`·`run_daily_equity_snapshot`·`print_today_trading_summary` — 시그니처 전부 원본 그대로, Task 간 참조 명칭 일치. `tools/` 패키지는 Task 3에서 생성 후 Task 4·10이 사용. ✅
