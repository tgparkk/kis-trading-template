# god 파일 분할 (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `backtest/engine.py`(1,397줄)·`main.py`(1,014줄)를 책임 단위로 분할(각 ≤ ~700줄)하고 운영→backtest 지연 import 엣지를 0으로 만든다. 동작 보존.

**Architecture:** 스펙 `docs/superpowers/specs/2026-07-02-god-file-split-design.md` §3의 3단계. 모든 이동은 verbatim + 원 위치 re-export(외부 참조 15곳·테스트 표면 무수정), 분봉 로직은 Mixin 상속으로 self 상태 공유 유지, main.py 메서드는 2줄 위임 wrapper 잔류(테스트 인스턴스 patch 호환).

**Tech Stack:** Python 3.9, pytest, git mv 불가 케이스(파일 내 심볼 이동)라 diff 최소화 + 커밋단위 보존.

## Global Constraints

- **동작 보존**: 로직·수치·시그니처 무변경. 이동/재배선/상속 재구성만.
- 전체 스위트 게이트 = **3364 passed / 0 failed / 3 skipped** (매 태스크 커밋 전).
- 이동 심볼은 원 모듈에서 **re-export로 계속 유효** (`from X import Y  # noqa: F401`).
- 브랜치 `feat/phase2-god-file-split` (main에서 분기). main 머지·push는 사장님 별도 승인(스태거 옵션 있음).
- repo 루트 = `D:\GIT\kis-trading-template\RoboTrader_template`.
- 각 태스크 후 스모크: `venv\Scripts\python -c "from main import DayTradingBot, pid_file_name; from backtest.engine import BacktestEngine, BacktestResult, make_screener_snapshot_provider; print('surface OK')"`.

---

### Task 1: backtest 경계 정리 — 스냅샷 provider 승격 (스펙 §3-①)

**Files:**
- Create: `core/screener_snapshot_provider.py` — `backtest/engine.py:1334-1396`의 `make_screener_snapshot_provider` verbatim 이동(+해당 함수가 쓰는 import만 동반: 함수 본문을 읽고 실제 사용 모듈 확인)
- Modify: `backtest/engine.py`(정의 삭제→re-export), `backtest/__init__.py:28`(re-export 소스 갱신), `core/candidate_selector.py:885`(지연 import 경로 갱신)
- 참고: `tools/gen_inventory.py:14-15` RESEARCH_DIRS에 `"backtest"` 추가 + `docs/INVENTORY.md` 재생성은 Task 4에서 일괄.

**Interfaces:**
- Produces: `core.screener_snapshot_provider.make_screener_snapshot_provider(...)` 시그니처 무변경. `backtest.engine.make_screener_snapshot_provider`는 re-export로 유효.

- [ ] **Step 1:** `backtest/engine.py:1334-1396` 함수를 읽고 본문이 사용하는 import(예: db 커넥션, typing)를 파악 → `core/screener_snapshot_provider.py` 생성(모듈 docstring: backtest/engine.py에서 승격, 운영 candidate_selector가 사용, 2026-07-02 Phase2). 함수 본문 verbatim.
- [ ] **Step 2:** `backtest/engine.py`의 정의 삭제 자리에 `from core.screener_snapshot_provider import make_screener_snapshot_provider  # noqa: E402,F401` (파일 하단 위치 그대로 가능). `backtest/__init__.py:28`의 import 소스는 그대로 두어도 re-export로 동작하지만, 명시적으로 `from core.screener_snapshot_provider import ...`로 바꾸지 **않는다**(외부 표면 최소 변경 원칙 — engine 경유 유지).
- [ ] **Step 3:** `core/candidate_selector.py:885` → `from core.screener_snapshot_provider import make_screener_snapshot_provider`.
- [ ] **Step 4:** 검증 — same-object + 운영 엣지 0:
```bash
venv\Scripts\python -c "from backtest.engine import make_screener_snapshot_provider as A; from core.screener_snapshot_provider import make_screener_snapshot_provider as B; assert A is B; print('same-object OK')"
grep -rn "backtest" core/ bot/ collectors/ api/ framework/ db/ runners/ signals/ tools/ --include="*.py" | grep -v __pycache__ | grep "import"
```
Expected: same-object OK · 운영 디렉토리에서 backtest import는 `core/screener_snapshot_provider` 결과 0건(candidate_selector가 core 경로로 전환됨).
- [ ] **Step 5:** 전체 스위트(3364/0/3) + 표면 스모크 → 커밋 `refactor(core): screener snapshot provider 승격 — 운영→backtest 지연 import 엣지 제거`.

---

### Task 2: engine.py 분할 (스펙 §3-②)

**Files:**
- Create: `backtest/result.py`(`BacktestResult` 55-110 verbatim), `backtest/metrics.py`(`_calc_mdd` 620·`_calc_sharpe` 630·`_calc_calmar` 642·`_calc_sortino` 661 → 모듈 함수 `calc_mdd/calc_sharpe/calc_calmar/calc_sortino`로 **이름만 언더스코어 제거**, 본문 verbatim), `backtest/engine_minute.py`(`BacktestMinuteMixin` 클래스에 `_simulate_day_minute` 750-997·`run_minute` 998-1333 verbatim)
- Modify: `backtest/engine.py` — 이동분 삭제, `class BacktestEngine(BacktestMinuteMixin):`로 상속 추가, 지표 호출부를 `metrics.calc_*`로 전환, **하위호환 static 별칭 유지**(`_calc_mdd = staticmethod(metrics.calc_mdd)` 4종 — 테스트/연구가 `BacktestEngine._calc_mdd`를 부를 수 있으므로), 상단 re-export `from backtest.result import BacktestResult  # noqa: F401`.

**Interfaces:**
- Produces: `backtest.result.BacktestResult` · `backtest.metrics.calc_*` · `backtest.engine_minute.BacktestMinuteMixin`. 기존 `backtest.engine.BacktestResult`·`BacktestEngine.run_minute`·`BacktestEngine._calc_*` 전부 표면 불변.

- [ ] **Step 1:** 이동 전 참조 카탈로그: `grep -rn "_calc_mdd\|_calc_sharpe\|_calc_calmar\|_calc_sortino\|BacktestResult\|run_minute\|_simulate_day_minute" --include="*.py" . | grep -v __pycache__ | grep -v "^./backtest/engine.py"` → 외부에서 쓰는 표면 목록 기록(전부 보존 대상).
- [ ] **Step 2:** `backtest/result.py` 생성(BacktestResult verbatim + 필요한 import). engine.py에서 삭제 + re-export.
- [ ] **Step 3:** `backtest/metrics.py` 생성(4함수 verbatim, 모듈 레벨). engine.py의 4 static 정의 삭제 → `_calc_mdd = staticmethod(calc_mdd)` 형태 별칭 4줄 + 내부 호출부(`self._calc_mdd(...)` 또는 `BacktestEngine._calc_...`)는 그대로 동작 확인(별칭이라 무수정도 가능 — 무수정 우선).
- [ ] **Step 4:** `backtest/engine_minute.py` 생성 — `class BacktestMinuteMixin:` 안에 두 메서드 verbatim(들여쓰기 유지), 메서드 본문이 참조하는 모듈 import 동반. engine.py에서 두 메서드 삭제, `from backtest.engine_minute import BacktestMinuteMixin` + `class BacktestEngine(BacktestMinuteMixin):`.
- [ ] **Step 5:** 줄수 확인 `wc -l backtest/engine.py` → ≤ ~750 기대. 검증:
```bash
venv\Scripts\python -m pytest tests/test_backtest_engine.py tests/test_backtest_engine_minute.py tests/test_multiverse.py -q
venv\Scripts\python -m pytest tests/ -q --tb=short   # 3364/0/3
venv\Scripts\python -m ruff check .
```
- [ ] **Step 6:** 커밋 3개(1책임=1커밋): `refactor(backtest): BacktestResult → result.py` / `지표 4종 → metrics.py (별칭 보존)` / `분봉 엔진 → BacktestMinuteMixin (engine_minute.py)`. 각 커밋 전 전체 스위트.

---

### Task 3: main.py 분할 (스펙 §3-③, 라이브)

**Files:**
- Create: `bot/candidate_loader.py` — `class CandidateLoader:`(bot/ 위임 패턴 미러: `__init__(self, bot)`로 역참조 보관, TYPE_CHECKING `from main import DayTradingBot`). main.py에서 verbatim 이동: `reload_candidates`(532)·`_load_screener_candidates`(546)·`_load_candidates_multi_strategy`(641) 본문(내부 `self.` → `self._bot.` 치환), 모듈함수 `should_use_volume_fallback`(889)·`apply_volume_fallback_with_filter`(899) verbatim.
- Modify: `main.py` — 3메서드를 2줄 위임 wrapper로 교체(기존 `_analyze_buy_decision` 패턴 그대로: 메서드명·시그니처 보존), `__init__`에 `self.candidate_loader = CandidateLoader(self)` 배선, 폴백 2함수 정의 삭제 → `from bot.candidate_loader import should_use_volume_fallback, apply_volume_fallback_with_filter  # noqa: F401` re-export.
- Modify: `bot/initializer.py` — `_allocate_strategy_capital`(main.py:195-240) 본문을 initializer로 이동(기존 패턴에 맞는 메서드로), main.py는 위임 wrapper.

**Interfaces:**
- Produces: `bot.candidate_loader.CandidateLoader` · main.py 표면 전부 불변(`DayTradingBot` 메서드명·`pid_file_name`·`main()`·폴백 2함수 re-export).

- [ ] **Step 1:** 이동 전 표면 카탈로그: `grep -rn "should_use_volume_fallback\|apply_volume_fallback_with_filter\|_load_candidates_multi_strategy\|_load_screener_candidates\|reload_candidates\|_allocate_strategy_capital" --include="*.py" . | grep -v __pycache__ | grep -v "^./main.py"` → 호출·patch 위치 전수 기록(wrapper·re-export가 전부 커버하는지 대조).
- [ ] **Step 2:** `bot/candidate_loader.py` 작성(위 명세). ⚠️ `self.` 치환은 기계적으로: 이동 본문 내 `self.X` → `self._bot.X` 전부(로거 제외 — 새 모듈은 자체 `setup_logger(__name__)`).
- [ ] **Step 3:** main.py wrapper 교체 + 배선 + re-export. `_allocate_strategy_capital` → initializer 이동 + wrapper.
- [ ] **Step 4:** 검증:
```bash
wc -l main.py bot/candidate_loader.py   # main ≤ ~750 기대
venv\Scripts\python -m pytest tests/test_main_loop.py tests/test_main_smoke.py tests/test_instance_pid.py tests/test_intraday_universe.py -q
venv\Scripts\python -m pytest tests/ -q --tb=short   # 3364/0/3
venv\Scripts\python -m ruff check .
venv\Scripts\python -c "from main import DayTradingBot, pid_file_name, should_use_volume_fallback, apply_volume_fallback_with_filter; print('main surface OK')"
```
- [ ] **Step 5:** 커밋 2개: `refactor(bot): 후보 로딩 → CandidateLoader 위임 (main.py 슬림화)` / `refactor(bot): 자본배분 → initializer 위임`. 각 커밋 전 전체 스위트.

---

### Task 4: 문서·인벤토리 갱신

**Files:**
- Modify: `tools/gen_inventory.py`(RESEARCH_DIRS에 `"backtest"` 추가, PROD_DIRS 유지 확인), `docs/INVENTORY.md` 재생성, `docs/CODE_MAP.md`(backtest/ 연구 분류 + 승격 이력 1행 추가), `CLAUDE.md`(연구 목록에 `backtest/` 추가)

- [ ] **Step 1:** gen_inventory RESEARCH_DIRS 갱신 → `PYTHONIOENCODING=utf-8 venv/Scripts/python tools/gen_inventory.py > docs/INVENTORY.md` → **LIVE-DEP=0 확인**(Task 1이 성공했으면 backtest 편입에도 0 — 0 아니면 STOP·누락 엣지 보고).
- [ ] **Step 2:** CODE_MAP: 연구 분류에 `backtest/`(단, `core/screener_snapshot_provider.py`로 승격된 팩토리 이력 1행), CLAUDE.md 연구 나열 갱신. 두 문서의 검증 명령 grep 대상에 backtest 유지.
- [ ] **Step 3:** 전체 스위트 + 커밋 `docs(map): backtest/ 연구 분류 확정 + Phase2 분할 반영`.

---

## Self-Review

**1. Spec coverage:** §3-①→Task1 ✅ ②→Task2 ✅ ③→Task3 ✅ 분류·인벤토리→Task4 ✅ §4 가드레일(0 failed·1책임 1커밋·re-export·스모크) 각 태스크 Step에 반영 ✅ 머지 스태거 옵션은 실행 밖(사장님 결정) ✅
**2. Placeholder scan:** 모든 이동에 원 줄범위·대상 파일·검증 명령 명시. "필요한 import 동반"은 verbatim 이동의 표준 지시(Task 구현자가 본문 읽고 확인) ✅
**3. Type consistency:** `CandidateLoader(bot)` 역참조·`BacktestMinuteMixin` 상속·`calc_*`/`_calc_*` 별칭 — Task 간 명칭 일치, 외부 표면 카탈로그 Step이 각 태스크 선두에 배치 ✅
