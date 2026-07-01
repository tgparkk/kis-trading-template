# 연구/운영 경계 정리 — Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 라이브 코드를 1줄도 건드리지 않고, 에이전트가 운영/연구 코드를 즉시 구분하도록 라우팅 문서 2종(`CLAUDE.md` 블록 + `docs/CODE_MAP.md`)을 추가한다.

**Architecture:** 순수 문서 작업. 검증된 라이브→연구 의존 8엣지(정적7+동적1)와 .bat 엔트리포인트를 지도화하고, `CLAUDE.md`에 연구 디렉토리 라우팅 규칙을 심는다. 파일 이동·import 변경·코드 수정 전무.

**Tech Stack:** Markdown, grep(ripgrep)로 검증.

## Global Constraints

- 라이브 매매 코드·테스트 영향 = **0** (문서만 추가/수정).
- 대상 repo 루트: `D:\GIT\kis-trading-template`, 코드 디렉토리: `RoboTrader_template/`.
- `CLAUDE.md` 대상 = `RoboTrader_template/CLAUDE.md` (프로젝트 라우터, 이미 존재).
- 운영 디렉토리(SSOT): `core/`, `bot/`, `framework/`, `api/`, `strategies/`, `collectors/`, `db/`, `runners/`, `signals/`, `lib/`, `utils/`. 연구 디렉토리: `scripts/`, `multiverse/`, `books/`, `council/`.
- git 커밋은 사용자 확인 후 (각 Task의 커밋 step은 사용자 승인 시 실행).
- 8엣지 사실은 스펙 §2(`docs/superpowers/specs/2026-06-30-research-production-separation-design.md`)와 일치해야 함.

---

### Task 1: CODE_MAP.md — 라이브→연구 의존 지도

**Files:**
- Create: `RoboTrader_template/docs/CODE_MAP.md`
- Verify(read-only): `collectors/daily_adj.py`, `bot/system_monitor.py`, `collectors/daily_derived.py`, `strategies/rs_leader/{strategy,screener}.py`, `strategies/deep_mr_dev20/{strategy,screener}.py`, `매일_분석_실행.bat`, `장마감_자동분석.bat`

**Interfaces:**
- Produces: `docs/CODE_MAP.md` — Task 2의 `CLAUDE.md` 블록이 이 경로를 참조한다.

- [ ] **Step 1: 엣지 사실을 재검증(드리프트 방지)**

Run (repo `RoboTrader_template/` 기준):
```bash
grep -rn "from scripts\|import scripts\|from multiverse\|import multiverse" \
  bot/system_monitor.py collectors/daily_derived.py \
  strategies/rs_leader/strategy.py strategies/rs_leader/screener.py \
  strategies/deep_mr_dev20/strategy.py strategies/deep_mr_dev20/screener.py
grep -n "import_module" collectors/daily_adj.py
grep -n "scripts" 매일_분석_실행.bat 장마감_자동분석.bat
```
Expected: 정적 import 7행 + `daily_adj.py:8` 동적 import 1행 + `.bat` 활성 경로 2행(매일:23, 장마감:14). 스펙 §2 표와 일치하면 통과. **불일치 시 멈추고 CODE_MAP을 실제값으로 작성**(코드가 진실, 스펙이 stale일 수 있음).

- [ ] **Step 2: `docs/CODE_MAP.md` 작성**

내용(아래 그대로, 단 Step1에서 불일치가 나오면 실제값으로 교정):
```markdown
# CODE MAP — 운영 vs 연구 경계 (에이전트 라우팅)

> 목적: 에이전트가 "운영 동작"을 찾을 때 연구/일회성 코드에 오도되지 않도록.
> 최종 검증: 2026-06-30. 드리프트 의심 시 이 파일 하단의 검증 명령 재실행.

## 디렉토리 분류
- **운영(production, 라이브 매매 경로)**: `core/` `bot/` `framework/` `api/`
  `strategies/` `collectors/` `db/` `runners/` `signals/` `lib/` `utils/`
- **연구/일회성(research, 라이브 아님)**: `scripts/` `multiverse/` `books/` `council/`
  → 운영 동작을 여기서 추론하지 말 것. 단, 아래 **예외 엣지**는 라이브가 실제 의존.

## ⚠️ 라이브 → 연구 의존 엣지 (이동 시 라이브 깨짐, 총 8)

### 동적 import (정적 분석 불가 — 최우선 주의)
- `collectors/daily_adj.py:8` → `importlib.import_module("scripts.10pct_strategy.p0_apply_adj_factor")`
  - 폴더명이 숫자로 시작해 정상 import 불가. import-linter/IDE가 **못 본다**.
  - 옮기면 컴파일 경고 0으로 **라이브 조정계수 수집이 조용히 깨짐**.

### 정적 import (7)
| 라이브 파일 | 대상(연구) | 성격 |
|---|---|---|
| `bot/system_monitor.py:11` | `scripts.daily_trading_summary.print_today_trading_summary` | EOD 도구 |
| `bot/system_monitor.py:245` | `scripts.paper_strategy_equity.run_daily_equity_snapshot` | EOD 도구 |
| `collectors/daily_derived.py:3` | `scripts.etl_backfill_daily_prices.SQL_UPDATE_RETURNS` | SQL 상수 |
| `strategies/rs_leader/strategy.py:16` | `scripts.rs_leader.rule.RSLeaderRule` | 진입룰 |
| `strategies/rs_leader/screener.py:14` | `scripts.rs_leader.rule.RSLeaderRule` | 진입룰 |
| `strategies/deep_mr_dev20/strategy.py:18` | `scripts.discovery.rules.MeanReversionMA20Rule` | 진입룰 |
| `strategies/deep_mr_dev20/screener.py:15` | `scripts.discovery.rules.MeanReversionMA20Rule` | 진입룰 |

## .bat 엔트리포인트가 scripts 경로 하드코딩 (이동 시 동반 수정)
- `매일_분석_실행.bat:23` → `python scripts\daily_trading_summary.py`
- `장마감_자동분석.bat:14` → `python scripts/auto_analysis.py`

## 검증 명령 (드리프트 점검)
\`\`\`bash
grep -rn "from scripts\|from multiverse" bot/ collectors/ strategies/ | grep -v test
grep -rn "import_module" collectors/ bot/ core/
grep -rn "scripts" *.bat
\`\`\`
관련 설계: `docs/superpowers/specs/2026-06-30-research-production-separation-design.md`
```

- [ ] **Step 3: 작성 내용이 코드와 일치하는지 재확인**

Run:
```bash
grep -c "daily_adj.py:8\|system_monitor.py:11\|system_monitor.py:245\|daily_derived.py:3\|rs_leader/strategy.py:16\|deep_mr_dev20/strategy.py:18" docs/CODE_MAP.md
```
Expected: ≥6 (모든 핵심 엣지가 문서에 존재). 0이면 작성 누락 → 보강.

- [ ] **Step 4: 커밋 (사용자 승인 후)**

```bash
git add RoboTrader_template/docs/CODE_MAP.md
git commit -m "docs(map): 라이브→연구 의존 8엣지 CODE_MAP 추가"
```

---

### Task 2: CLAUDE.md — RESEARCH 라우팅 블록

**Files:**
- Modify: `RoboTrader_template/CLAUDE.md` (라우터, 기존 파일에 섹션 추가)

**Interfaces:**
- Consumes: Task 1의 `docs/CODE_MAP.md` 경로를 참조한다.

- [ ] **Step 1: CLAUDE.md 현재 구조 확인 (어디에 끼울지)**

Run:
```bash
sed -n '1,40p' RoboTrader_template/CLAUDE.md
grep -n "^#" RoboTrader_template/CLAUDE.md | head -30
```
Expected: 기존 헤딩 목록 확인. 라우팅/디렉토리 안내 섹션이 이미 있으면 그 근처, 없으면 문서 상단(제목 직후)에 삽입.

- [ ] **Step 2: RESEARCH 라우팅 블록 삽입**

`CLAUDE.md` 상단(제목 직후 또는 기존 "구조/디렉토리" 섹션 인접)에 추가:
```markdown
## 🧭 운영 vs 연구 코드 라우팅 (에이전트 필독)

이 repo는 운영(라이브 매매) 코드와 연구/일회성 코드가 한 트리에 섞여 있다.
**운영 동작을 찾을 때 연구 디렉토리를 근거로 삼지 말 것.**

- **운영(production)**: `core/` `bot/` `framework/` `api/` `strategies/`
  `collectors/` `db/` `runners/` `signals/` `lib/` `utils/`
- **연구/일회성(research, 라이브 아님)**: `scripts/` `multiverse/` `books/` `council/`
  → 검색 시 후순위. 죽은 실험 코드를 라이브로 오인하지 말 것.

**예외**: 라이브가 실제로 의존하는 연구 파일이 8엣지 존재(특히 정적분석에 안 잡히는
`collectors/daily_adj.py`의 동적 import). 이동·삭제 전 반드시 `docs/CODE_MAP.md` 확인.
```

- [ ] **Step 3: 삽입 검증**

Run:
```bash
grep -n "운영 vs 연구 코드 라우팅\|CODE_MAP.md" RoboTrader_template/CLAUDE.md
```
Expected: 라우팅 헤딩 1행 + CODE_MAP.md 참조 1행 이상.

- [ ] **Step 4: 커밋 (사용자 승인 후)**

```bash
git add RoboTrader_template/CLAUDE.md
git commit -m "docs(claude): 운영 vs 연구 코드 라우팅 블록 추가"
```

---

### Task 3: 메모리 changelog 기록

**Files:**
- Create: `C:\Users\sttgp\.claude\projects\D--GIT-kis-trading-template\memory\changelog-2026-06-30-research-production-separation-phase0.md`
- Modify: `C:\Users\sttgp\.claude\projects\D--GIT-kis-trading-template\memory\MEMORY.md` (인덱스 1줄)

**Interfaces:**
- Consumes: Task 1·2 결과(커밋 해시).

- [ ] **Step 1: changelog 작성**

내용: 배경(코드 거대·중구난방 → 에이전트 효율 개선 1단계), 3자 토론 결론(하드분리 VETO, 라우팅 먼저), Phase 0 산출물(CODE_MAP+CLAUDE 블록), 검증된 8엣지, 다음 단계(Phase 1은 브랜치 머지 후), 커밋 해시. 메모리 frontmatter 규칙 준수.

- [ ] **Step 2: MEMORY.md 인덱스 한 줄 추가**

"## 최근 메모" 최상단에:
```markdown
- [2026-06-30 연구/운영 경계정리 Phase0](changelog-2026-06-30-research-production-separation-phase0.md) — 코드 거대·중구난방 개선 1단계. 3자토론(하드분리 VETO)→라우팅 먼저. CODE_MAP(라이브→연구 8엣지=정적7+동적1, daily_adj 동적import 최주의)+CLAUDE 라우팅블록. 설계 7d8f949. Phase1(승격)은 브랜치머지 후.
```

- [ ] **Step 3: 커밋 불필요** (메모리는 git 밖). 파일 저장으로 완료.

---

## Self-Review

**1. Spec coverage (Phase 0):**
- 스펙 Phase 0 산출물 1(CLAUDE 라우팅) → Task 2 ✅
- 스펙 Phase 0 산출물 2(CODE_MAP) → Task 1 ✅
- 스펙 §7 "중요 변경 후 changelog" → Task 3 ✅
- Phase 1/2는 이 계획 범위 밖(명시), 별도 계획 예정 ✅

**2. Placeholder scan:** "구현 later"류 없음. CODE_MAP/CLAUDE 블록 전문(全文) 제공. Task 3 changelog만 항목 나열식이나, 메모리 문서라 형식 자유·내용 명시됨. ✅

**3. Type consistency:** 코드 아님(문서). 경로·헤딩·8엣지 표가 Task 1↔2↔스펙에서 동일 표기. ✅

**범위 메모:** Phase 1(잘못 놓인 모듈 승격, 도구 셋업, 죽은 코드 정리)은 **현 브랜치 churn 정리 후 별도 계획**으로 작성한다. 본 계획은 무위험 Phase 0 한정.
