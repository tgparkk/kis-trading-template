# 설계: 연구/운영 코드 경계 정리 (에이전트 효율 1단계)

- 날짜: 2026-06-30
- 브랜치(작성 시점): fix/regime-refresh-throttle-backoff
- 상태: 설계 승인됨 (구현 계획 대기)
- 작성 근거: 아키텍트·리스크비평가·실전파이썬엔지니어 3자 토론 + 직접 검증

## 1. 목표와 비목표

**1차 목표**: 코드베이스를 **AI 코딩 에이전트(Claude)가 안정적으로 읽고 수정**할 수 있게 만든다. 부차적으로 사람 가독성.

핵심 통증: 전체 ~126k 줄 중 `scripts/`(183파일/52k줄) + `multiverse/`(69파일/12k줄) = **약 절반이 연구/일회성 코드**인데 운영 코드와 같은 트리에 섞여 있다. 에이전트가 검색하면 죽은 실험 코드까지 걸려 ① 컨텍스트 낭비 ② **죽은 코드를 라이브로 오인**(메모리에 06-27/06-28 오판 기록 존재).

**비목표 (이 스펙에서 다루지 않음)**:
- god 파일 분할(`backtest/engine.py` 1397줄, `main.py` 1011줄 등) → **별개 워크스트림(Phase 2), 절대 섞지 않음**.
- 전략 로직·매매 행동 변경. 이 작업은 **동작 보존(behavior-preserving)** 이다.
- `multiverse/` 내부 재구성. 라우팅으로 격리만 하고 물리 이동은 안 한다.

## 2. 검증된 사실 (load-bearing, 2026-06-30 직접 확인)

### 라이브 → 연구 의존 전체 표면 = 8 엣지
**정적 import 7곳**:
| 라이브 파일 | import 대상 (연구) | 성격 |
|---|---|---|
| `bot/system_monitor.py:11` | `scripts.daily_trading_summary.print_today_trading_summary` | EOD 운영도구 |
| `bot/system_monitor.py:245` | `scripts.paper_strategy_equity.run_daily_equity_snapshot` | EOD 운영도구 |
| `collectors/daily_derived.py:3` | `scripts.etl_backfill_daily_prices.SQL_UPDATE_RETURNS` | SQL 상수 |
| `strategies/rs_leader/strategy.py:16` | `scripts.rs_leader.rule.RSLeaderRule` | **진입룰(운영 로직)** |
| `strategies/rs_leader/screener.py:14` | `scripts.rs_leader.rule.RSLeaderRule` | **진입룰** |
| `strategies/deep_mr_dev20/strategy.py:18` | `scripts.discovery.rules.MeanReversionMA20Rule` | **진입룰** |
| `strategies/deep_mr_dev20/screener.py:15` | `scripts.discovery.rules.MeanReversionMA20Rule` | **진입룰** |

**동적 import 1곳 (정적 분석 불가, 최대 지뢰)**:
- `collectors/daily_adj.py:8` → `importlib.import_module("scripts.10pct_strategy.p0_apply_adj_factor")`
- 폴더명이 숫자로 시작(`10pct_strategy`)해 정상 `import` 불가 → importlib 강제. import-linter/IDE 리팩터가 **못 본다**. 옮기면 컴파일 경고 0으로 라이브 조정계수 수집이 조용히 깨짐.

### .bat 엔트리포인트가 scripts 경로 하드코딩 (활성)
- `매일_분석_실행.bat:23` → `python scripts\daily_trading_summary.py` (활성)
- `장마감_자동분석.bat:14` → `python scripts/auto_analysis.py` (활성; 11행은 REM)

### 그 외 위험 요인
- 연구→연구 동적 import(`scripts/book_rebalance_multiverse.py:428`, `book_param_multiverse.py:90-93`)는 라이브 무관이나 이동 시 깨질 수 있음.
- **66개 테스트 파일**이 `scripts.`/`multiverse.` 참조. `tests/`에 sys.path shim용 conftest 없음 → 이동 시 수집 실패 위험.
- 도구 미설치: `pyproject.toml`/`ruff.toml` 없음, vulture·deptry·coverage 미설치. `.gitignore`는 scripts/multiverse를 (정상적으로) 무시 안 함.
- **`.claudeignore`는 Claude Code에 존재하지 않음**(Cursor 기능). CC의 Grep/Glob은 `.gitignore`만 따름(추적 코드엔 부적합), `permissions.deny`는 너무 무딤. → 올바른 스코핑 = `CLAUDE.md` 라우팅 블록.
- 현재 브랜치 및 미푸시 멀티버스4 작업이 `scripts/`를 활발히 수정 중 → 물리 이동을 지금 하면 머지 충돌.

## 3. 합의된 방향 (3자 만장일치)

- ❌ **하드 분리(전부 `research/`로 이동) VETO** — 라이브 머니 시스템에 최대 폭발 반경, 8개 라이브 엣지(특히 동적) + 66 테스트 + .bat 깨짐 위험을 보기 좋은 트리와 맞바꿈. 비용/편익 역전.
- ✅ **검색 스코핑(라우팅 문서) 먼저** — 무위험·즉효.
- ✅ **인벤토리 기반 점진 승격** 후속.

## 4. 설계: 3 Phase

### Phase 0 — 무위험·즉시 (라이브 코드 0줄 수정)
산출물 2개. 파일 이동·import 변경·.bat 수정 **전무**.

1. **`CLAUDE.md` 라우팅 블록 추가**
   - 내용: "`scripts/`·`multiverse/`는 RESEARCH(연구·일회성). 운영 동작은 `core/`·`bot/`·`framework/`·`api/`·`strategies/`·`collectors/`·`db/`·`runners/`에서 찾을 것. 라이브가 의존하는 **예외 8엣지**는 `docs/CODE_MAP.md` 참조."
   - 효과: 에이전트가 매 세션 로드 → 검색 잡음 즉시 감소.

2. **`docs/CODE_MAP.md` 작성 (읽기전용 지도)**
   - §2의 8엣지 표 + .bat 엔트리포인트 + "운영 vs 연구" 디렉토리 분류를 못박음.
   - 동적 import(`daily_adj.py`)를 **굵게 경고** 표기 — 이동 시 정적 분석으로 안 잡힘.

**완료 기준**: 두 문서 커밋. 테스트/라이브 영향 0(문서만).

### Phase 1 — 근거 기반·저위험 (현재 브랜치 머지 후 착수)
> 선행조건: fix/regime-refresh-throttle-backoff 및 미푸시 멀티버스4 작업이 머지/정리되어 `scripts/` churn이 멈춘 뒤 시작(머지 충돌 회피).

3. **도구·결정성 셋업**: `venv\Scripts\python -m pip install vulture deptry ruff`, `pyproject.toml`+`ruff.toml` 신설(lint/format 결정화). 동작 변경 없음.

4. **전수 인벤토리 (`docs/INVENTORY.md`)**: AST import-graph 워크(오탐 0)로 연구 파일을 `LIVE-DEP / 운영도구 / 죽음 / 테스트전용` 태깅. **동적 import 타깃은 수동 카탈로그**(§2의 daily_adj + book_* ). vulture는 "조사 목록"으로만(엔트리포인트·동적로딩·Signal 콜백이 오탐원).

5. **잘못 놓인 운영 모듈 승격 (이동 1건 = 커밋 1개, 매 커밋 전체 테스트 스위트)**:
   - `scripts/rs_leader/rule.py` → `strategies/rs_leader/` 내부로. import 갱신.
   - `scripts/discovery/rules.py`(MeanReversionMA20Rule) → `strategies/deep_mr_dev20/` 또는 공유 위치로.
   - EOD 도구(`daily_trading_summary.py`, `paper_strategy_equity.py`) → 신규 `tools/`(또는 `ops/`). **`bot/system_monitor.py` import + `매일_분석_실행.bat:23` 동반 수정.**
   - `SQL_UPDATE_RETURNS` 상수 → `db/` 또는 `collectors/`로 추출.
   - **`collectors/daily_adj.py` 동적 import**: `p0_apply_adj_factor`를 운영 위치로 옮기고 동적 경로를 정상 import로 교체(또는 명시적으로 유지 결정). **이게 가장 까다로움 — 전용 가드 필요.**
   - `장마감_자동분석.bat:14` `auto_analysis.py` 경로 점검.
   - 완료 후 `scripts/`의 라이브 엣지 = 0 → 통째 무시 가능.

6. **죽은 일회성 정리**: `_*.py`, `debug_*`, `analyze_*` 등 무참조 파일 → `archive/` 또는 삭제(git 이력 보존).

**가드레일(필수)**: ① 이동 전 전체 테스트 그린 baseline 캡처 ② `importlib`/`__import__`/f-string 모듈경로 전수 grep 카탈로그 ③ 모든 `.bat`/`.ps1`에서 `scripts\`/`scripts/` 리터럴 grep 후 lockstep 수정 ④ LIVE-DEP는 연구 밖으로 먼저 승격한 뒤에야 나머지 정리.

### Phase 2 — god 파일 분할 (별개·후순위, 이 스펙 범위 밖)
characterization 테스트로 출력 고정 → 책임 단위 분할 → 원본에 re-export shim 남겨 기존 import 보존 → `git mv` 블레임 보존 → 1책임/커밋. **1단계와 섞지 않는다.**

## 5. 위험과 완화
| 위험 | 완화 |
|---|---|
| 동적 import 이동 시 사일런트 브레이크(daily_adj) | CODE_MAP 굵게 경고 + Phase1에서 전용 가드·라이브 동등성 검증 |
| .bat 스케줄 잡 깨짐 | 이동과 lockstep으로 .bat 수정, EOD dry-run |
| 66 테스트 수집 실패 | 그린 baseline + 이동 1건/커밋 즉시 재실행 |
| 머지 충돌 | Phase 1은 현 브랜치 churn 정리 후 착수 |
| god 파일과 혼동 | Phase 2로 분리, 이 스펙 범위 밖 명시 |

## 6. 성공 기준
- **Phase 0**: 에이전트가 `CLAUDE.md`만 읽고도 운영/연구를 구분, `CODE_MAP.md`로 라이브 엣지 즉시 파악. 라이브·테스트 영향 0.
- **Phase 1**: `scripts/`의 라이브 의존 엣지 = 0(정적+동적), 전체 테스트 그린 유지, .bat EOD 잡 정상, 라이브 매매 행동 불변.

## 7. 조직·운영 메모
- 관리자(Claude)는 직접 코드 수정 안 함 → Phase 1 코드 이동은 executor 등 직원 에이전트에 지시(TDD/가드레일 동반). 본 스펙·CODE_MAP 등 문서는 관리자 직접 작성 가능.
- git 커밋/푸시는 사용자 확인 후.
- 중요 변경 후 `memory/changelog-YYYY-MM-DD-*.md` 작성.
