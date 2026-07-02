# 죽은 연구코드 정리 (Phase 1 후속) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** INVENTORY 기반으로 `scripts/` 계열의 진짜 무참조 파일을 `archive/`로 이동(git mv, 이력 보존)해 에이전트 검색 잡음을 줄인다. 스펙 §4 item 6 실행.

**Architecture:** ① gen_inventory 매처 개선(`from pkg import module` 포착) 후 재생성 → ② 남은 UNREFERENCED 중 scripts/ 계열만, **repo 전역 파일명 grep 0-hit**(코드·bat·문자열 포함)을 최종 판정 기준으로 ARCHIVE 목록 확정(컨트롤러 검토 게이트) → ③ `archive/` 하위로 구조 보존 git mv → 전체 스위트·ruff·INVENTORY 재검. **multiverse/는 불가침**(스펙 §1 비목표: 내부 재구성 안 함 + 상대 import라 태그 신뢰 불가).

**Tech Stack:** Python(ast), git mv, pytest, ruff.

## Global Constraints

- 삭제 금지 — **archive/ 이동만** (git 이력·blame 보존). 사장님이 후일 영구삭제 결정 가능.
- **multiverse/ · books/ · council/ 파일은 건드리지 않는다.** scripts/ 계열(UNREFERENCED 127)만 대상.
- 전체 스위트 게이트 = **3363 passed, 0 failed, 3 skipped** (2026-07-02 bb fixture fix 후 완전 그린).
- ops 화이트리스트(참조 0이어도 KEEP): `scripts/kis_db/*`(07-01 schema/seed 실사용), `backfill_*`, `preflight_*`, `seed_*`, `schema*`, `refresh_*`, `reconcile_*`.
- 판정 기준: 파일 stem이 repo 내 *.py/*.bat/*.ps1 어디에도 안 나타나야(자기 자신·archive/·__pycache__ 제외) ARCHIVE. docstring 언급도 hit로 취급(보수적).
- repo 루트 = `D:\GIT\kis-trading-template\RoboTrader_template`. 브랜치 `feat/dead-code-archive`. main 머지·push는 사용자 승인 후.

---

### Task 1: gen_inventory 매처 개선 + INVENTORY 재생성

**Files:**
- Modify: `tools/gen_inventory.py` (imports_of의 ImportFrom 처리)
- Regenerate: `docs/INVENTORY.md`
- Test: `tests/tools/test_gen_inventory.py` (신규)

**Interfaces:**
- Produces: `imports_of()`가 `from scripts.exit_multiverse import run` 을 `scripts.exit_multiverse.run` 모듈 참조로도 인식.

- [ ] **Step 1: 실패 테스트 작성** — `tests/tools/test_gen_inventory.py`:

```python
"""gen_inventory 매처 — from-import alias가 서브모듈 참조로 인식되는지."""
import textwrap


def test_from_import_module_alias_detected(tmp_path):
    from tools.gen_inventory import imports_of_source
    src = textwrap.dedent('''
        from scripts.exit_multiverse import run, walkforward
        from scripts.discovery.rules import MeanReversionMA20Rule
        import scripts.strategy_gate
    ''')
    mods = imports_of_source(src)
    assert "scripts.exit_multiverse.run" in mods          # alias 결합 (신규)
    assert "scripts.exit_multiverse.walkforward" in mods  # alias 결합 (신규)
    assert "scripts.exit_multiverse" in mods              # 기존 동작 유지
    assert "scripts.discovery.rules" in mods              # 기존 동작 유지
    assert "scripts.strategy_gate" in mods                # 기존 동작 유지
```

- [ ] **Step 2: RED 확인** — `venv\Scripts\python -m pytest tests/tools/test_gen_inventory.py -v` → FAIL (`imports_of_source` 미존재).

- [ ] **Step 3: 구현** — `tools/gen_inventory.py`의 `imports_of(relpath)`를 파일열기+`imports_of_source(text)` 2함수로 분리하고, ImportFrom 처리에 alias 결합 추가:

```python
def imports_of_source(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
            for a in node.names:  # from pkg import module 케이스 포착
                mods.add(f"{node.module}.{a.name}")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = (getattr(fn, "attr", "") or getattr(fn, "id", ""))
            if name in ("import_module", "__import__") and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                mods.add(node.args[0].value)
    return mods
```

(`imports_of(relpath)`는 파일 읽어 `imports_of_source` 호출 + UnicodeDecodeError 처리 유지. `from X import 심볼`이 심볼명까지 모듈로 추가돼도 존재하지 않는 모듈명은 매칭 대상이 없어 무해 — 과잉 KEEP 방향의 보수적 오차만 발생.)

- [ ] **Step 4: GREEN + 재생성** — 테스트 PASS 후 `venv\Scripts\python tools/gen_inventory.py > docs/INVENTORY.md` (UTF-8 주의, Task 10 방식). `grep -c "LIVE-DEP" docs/INVENTORY.md` = 0 유지 확인, UNREFERENCED 수 감소 기록(195 → N).

- [ ] **Step 5: 전체 스위트 + 커밋**

`venv\Scripts\python -m pytest tests/ -q --tb=short` → **3364 passed(신규 1) / 0 failed / 3 skipped**.
```bash
git add tools/gen_inventory.py tests/tools/ docs/INVENTORY.md && git commit -m "fix(inventory): from-import alias 매처 보강 — exit_multiverse류 오탐 제거"
```

---

### Task 2: ARCHIVE 후보 확정 (판정 스크립트 + 컨트롤러 검토 게이트)

**Files:**
- Create: `tools/gen_archive_candidates.py` (일회성 아님 — 재실행 가능 판정기)
- Produce: `docs/superpowers/plans/2026-07-02-archive-candidates.md` (판정표)

**Interfaces:**
- Consumes: Task 1의 재생성된 `docs/INVENTORY.md`.
- Produces: ARCHIVE 확정 목록(파일당 1행: path · 최종수정일 · 판정근거). **컨트롤러가 검토·승인해야 Task 3 진행.**

- [ ] **Step 1: 판정 스크립트 작성** — `tools/gen_archive_candidates.py`:

로직(정확히 이 순서):
1. `docs/INVENTORY.md`에서 태그 UNREFERENCED & 경로가 `scripts/`로 시작하는 행만 파싱.
2. ops 화이트리스트 필터(Global Constraints 패턴, 경로/파일명 매칭) → KEEP(사유 명기).
3. 나머지 각 파일: stem(확장자 뺀 파일명)을 repo 전체 `*.py, *.bat, *.ps1`에서 검색(자기 자신·`__pycache__`·`archive/`·`docs/` 제외). **1건이라도 hit → KEEP(hit 위치 1개 예시 명기), 0-hit → ARCHIVE.**
4. 출력: markdown 표 (path | git 최종커밋일(`git log -1 --format=%ad --date=short -- <path>`) | ARCHIVE/KEEP | 근거).

- [ ] **Step 2: 실행·판정표 저장**

```bash
venv\Scripts\python tools/gen_archive_candidates.py > docs/superpowers/plans/2026-07-02-archive-candidates.md
```
Expected: ARCHIVE N건 + KEEP M건 (N+M = scripts 계열 UNREFERENCED 전수). N=0이면 STOP·보고.

- [ ] **Step 3: 컨트롤러 검토 게이트** — 구현자는 여기서 보고하고 정지. 컨트롤러가 판정표를 검토·승인한 뒤 Task 3 파견.

- [ ] **Step 4: 커밋**

```bash
git add tools/gen_archive_candidates.py docs/superpowers/plans/2026-07-02-archive-candidates.md && git commit -m "chore(archive): 무참조 판정기 + 후보 판정표"
```

---

### Task 3: archive/ 이동 실행

**Files:**
- Create: `archive/README.md` (한 줄: 무참조 연구코드 보관소 — 복원은 git mv 역방향, 판정근거는 candidates 문서)
- Move: Task 2 판정표의 ARCHIVE 목록 전부 → `archive/<원경로>` (예: `scripts/diag_trail_ab.py` → `archive/scripts/diag_trail_ab.py`)

- [ ] **Step 1: 일괄 git mv** — 판정표 ARCHIVE 행을 스크립트로 처리(디렉토리 생성 + `git mv <src> archive/<src>`). 이동 후 `git status --short`에서 R(rename) 행 수 = ARCHIVE N 확인.

- [ ] **Step 2: 검증 3종**

```bash
venv\Scripts\python -m pytest tests/ -q --tb=short   # 3364 passed / 0 failed / 3 skipped
venv\Scripts\python -m ruff check .                   # All checks passed! (archive/는 exclude됨)
venv\Scripts\python tools/gen_inventory.py > docs/INVENTORY.md && grep -c "LIVE-DEP" docs/INVENTORY.md  # 0
```
하나라도 실패 → **git reset --hard로 이동 롤백 후 BLOCKED 보고** (부분 이동 상태로 두지 않음).

- [ ] **Step 3: 커밋**

```bash
git add -A && git commit -m "chore(archive): 무참조 연구 스크립트 N건 archive/ 이동 (grep 0-hit 판정, git 이력 보존)"
```

---

### Task 4: 문서·changelog

**Files:**
- Modify: `CLAUDE.md` (라우팅 블록 연구 목록에 `archive/` 추가), `docs/CODE_MAP.md` (연구 분류에 archive/ 1줄)

- [ ] **Step 1:** CLAUDE.md 연구 나열을 `scripts/ multiverse/ books/ council/ archive/`로, CODE_MAP 연구 분류에 `archive/`(무참조 보관소, [candidates 문서] 근거) 추가.
- [ ] **Step 2:** `grep -n "archive/" CLAUDE.md docs/CODE_MAP.md` → 각 1행 이상. 커밋: `docs(map): archive/ 연구 분류 편입`.

---

## Self-Review

**1. Spec coverage:** 스펙 §4 item 6(무참조 정리, archive/ or 삭제) → archive/ 채택·전 태스크 ✅. §1 비목표(multiverse 불가침) 준수 ✅. 가드레일(그린 baseline·전수 grep·롤백) ✅.
**2. Placeholder scan:** 판정 로직·명령·게이트 전부 구체화. N은 Task 2 산출값으로 결정(실행 시 확정) — 의도적 데이터 의존, placeholder 아님. ✅
**3. Type consistency:** `imports_of_source` 시그니처 Task 1 정의=테스트 사용 일치. 판정표 경로를 Task 3이 소비. ✅
