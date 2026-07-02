# 설계: god 파일 분할 (Phase 2 — 에이전트 효율 2단계)

- 날짜: 2026-07-02
- 상태: 설계 승인됨 (A안, 사장님)
- 선행: Phase 1 완료(scripts 라이브 엣지 0, origin/main `f02eefc`), 전체 스위트 완전 그린(3364 passed / 0 failed)

## 1. 목표와 비목표

**목표**: 에이전트가 자주 읽는 거대 파일 2개(`main.py` 1,014줄, `backtest/engine.py` 1,397줄)를 책임 단위로 분할해 읽기/수정 안정성을 높인다. **동작 보존** — 전략·매매·백테스트 수치 변경 없음.

**비목표**: 로직 개선·리네이밍·아키텍처 변경. multiverse/ 불가침 유지. bot/ 위임 모듈들의 내부 재구성.

## 2. 검증된 사실 (2026-07-02 직접 확인)

- **main.py**: `DayTradingBot` 단일 클래스. bot/ 위임 패턴 기확립(analyzer·liquidation·initializer·position_sync·system_monitor가 실무, main엔 thin wrapper — 예: `_analyze_buy_decision`은 2줄 위임). 잔여 비만: **후보 로딩 클러스터** `reload_candidates`(532)·`_load_screener_candidates`(546)·`_load_candidates_multi_strategy`(641) ~230줄 + 모듈함수 `should_use_volume_fallback`(889)·`apply_volume_fallback_with_filter`(899) + `_allocate_strategy_capital`(195).
- **main.py 외부 표면**: bot/ 5개 파일은 TYPE_CHECKING 역참조만. 테스트는 `pid_file_name`·`DayTradingBot`만 import, 내부 메서드는 인스턴스 patch → **메서드명 보존(위임 wrapper)이면 무수정**.
- **engine.py**: `BacktestResult`(55-110) · `BacktestEngine.__init__/run`(일봉, ~199-512) · 지표 static 4종+`_calculate_metrics`(556-679) · 분봉 `_simulate_day_minute`(750-997)+`run_minute`(998-1333) ~580줄 · `make_screener_snapshot_provider`(1334-1396).
- 🔴 **미분류 경계 결함**: `backtest/`는 CODE_MAP 미분류인데 **운영 `core/candidate_selector.py:885`가 `backtest.engine.make_screener_snapshot_provider`를 지연 import** — equity 사고(07-02)와 동클래스 지뢰. 이 팩토리가 backtest/에 대한 유일한 운영 의존.
- engine 참조 표면: backtest/ 내부 4 + core/candidate_selector 1 + 연구 2 + 테스트 7 + `backtest/__init__.py` re-export.
- 코드베이스에 Mixin 패턴 기존재(`OrderExecutorMixin` 등) — 분봉 분리에 재사용.

## 3. 설계 (A안: 경계 → 방법론 검증 → 라이브 적용)

### 단계 ① backtest 경계 정리 (운영→backtest 엣지 0)
- `make_screener_snapshot_provider`를 `core/screener_snapshot_provider.py`(신규)로 verbatim 승격. `backtest/engine.py`는 re-export(연구·테스트 호환), `backtest/__init__.py` re-export 경로 갱신. `core/candidate_selector.py:885` 지연 import를 새 운영 경로로.
- CODE_MAP/CLAUDE.md에 `backtest/`를 **연구 분류로 확정** 편입, `tools/gen_inventory.py` RESEARCH_DIRS에 backtest 추가.

### 단계 ② engine.py 분할 (방법론 검증, 연구측)
- `backtest/result.py`: `BacktestResult` verbatim 이동.
- `backtest/metrics.py`: `_calc_mdd/_calc_sharpe/_calc_calmar/_calc_sortino`(순수 static) 모듈함수로 이동, engine은 호출부만 참조 전환(시그니처·수치 불변).
- `backtest/engine_minute.py`: `BacktestMinuteMixin`에 `run_minute`·`_simulate_day_minute` verbatim 이동, `class BacktestEngine(BacktestMinuteMixin)` 상속 — self 공유 상태 그대로, 테스트의 메서드 patch 표면 불변.
- `backtest/engine.py`에 이동 심볼 전부 re-export → 외부 15개 참조처 무수정. 목표 engine.py ≤ ~700줄.

### 단계 ③ main.py 분할 (라이브, 재시작 세트)
- `bot/candidate_loader.py`(신규, 기존 bot/ 위임 패턴 미러): `CandidateLoader` 클래스로 후보 로딩 3메서드 + 거래량 폴백 2함수 이동. main.py의 원 메서드는 **2줄 위임 wrapper로 유지**(테스트 patch 표면·행동 불변). 폴백 2함수는 main.py에서 re-export.
- `_allocate_strategy_capital` → `bot/initializer.py`로 이동(초기화 책임 소속), main은 위임.
- 목표 main.py ≤ ~700줄. `pid_file_name`·`DayTradingBot`·`main()` 표면 불변.

## 4. 가드레일
- 전체 스위트 **0 failed** 게이트(각 커밋), 1책임=1커밋, verbatim 이동+re-export, git blame 보존.
- 라이브 반영은 **재시작과 세트**: 머지 타이밍은 사장님 결정 — (a) 오늘 일괄 머지→내일 07:40 Phase1+2 동시 발효, (b) ①②만 먼저·③은 Phase1 라이브 관찰(내일) 후 — 문제 시 원인 귀속 명확.
- 오늘 교훈 적용: 장중 아님(장마감 후 작업), 지연 import 대상 사전 카탈로그(①이 그 유일 엣지).

## 5. 성공 기준
- 운영→backtest 엣지 0(지연 포함), engine.py·main.py 각 ≤ ~700줄, 외부 참조·테스트 표면 무수정으로 전체 그린, 라이브 매매 행동 불변.

## 6. 조직 메모
관리자는 문서만 직접 작성, 코드 이동은 executor 서브에이전트(subagent-driven). 커밋은 브랜치 내 승인됨, main 머지·push는 사장님 별도 승인.
