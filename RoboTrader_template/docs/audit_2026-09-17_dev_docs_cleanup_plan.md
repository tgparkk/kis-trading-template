---
name: audit-2026-09-17-dev-docs-cleanup-plan
description: 개발 문서(CLAUDE.md·README·docs/*.md·전략 README) 전수 감사 + 정리 계획 초안. 워크플로 27 에이전트(감사 13 · 반박검증 13 · 종합 1) · 확정 결함 304 · 반박 9. 관리자 스팟체크 5/5 일치(키=key.ini · VIRTUAL_MODE 부재 · DB 기본값 5433/kis_template · .env.example 인라인 주석 → 가드 off 강등 · tools→scripts 엣지 1건). 실행은 사장님 묶음 선택 후.
metadata:
  type: project
  status: draft — 실행 전 (사장님 결정 대기)
  source: scratchpad/docs_cleanup_plan_2026-09-17.md (워크플로 wf_55b94990-7de 산출)
---

> **관리자 주석(2026-09-17)**: 아래 본문은 감사 워크플로가 쓴 초안 그대로다. 관리자가 코드로 직접 재확인한 것: ① `config/settings.py:61,97-98,145-146` 키는 `key.ini` ② `VIRTUAL_MODE` 를 읽는 운영 코드 0파일 ③ `db/connection.py:41-42` 기본값 `5433`/`kis_template` ④ `config/env_bootstrap.py:50-66` 은 인라인 `#` 을 값에 포함 → `constants.py:281-283` 이 미지값을 `off` 로 강등(`.env.example:6` 을 그대로 복사하면 발생 · 오늘 라이브 로그는 `mode=live (startup)` 정상) ⑤ `tools/paper_strategy_equity.py:257` → `scripts.kis_db.schema` 엣지 실재 ⑥ `config/market_hours.py:18` buy_cutoff 호출자 0 · `CONFIGURATION.md:117` 「12:00」 거짓.

# 개발 문서 정리 계획 (초안) — 2026-09-17

> 근거 = 13개 감사 클러스터(claude_md · readme_changelog · modules_md · flow_docs · strategy_guide · configuration · database_docs · risk_ownership · codemap_inventory · paper_strategies · docs_organization · repo_hygiene · gap_finder)의 검증 결과. `confirmed`·`found_by_skeptic` 만 사실로 채택, `refuted` 는 부록 B 에만, 미확정은 부록 A 에만. 경로는 별도 표기 없으면 `RoboTrader_template/` 기준. 이 계획은 문서만 다루며 코드·bat·라이브 트리는 건드리지 않는다.

## 0. 한눈에

- 감사 대상: 정식 개발 문서 **13종** + 부속 문서 약 30종(전략 README 9 · 위험/소유권 5 · DB 설명 1 · 인스턴스·env 2 · 레거시 4 · CLAUDE.md) + `docs/` 최상위 71개 파일(추적 50 · 미추적 21) + 저장소 위생(워크트리 16 등).
- 확정 결함(클러스터 간 중복 제거 후): **high 60 · medium 89 · low 114 = 263건** · 반박 9건 · 미확정은 부록 A.
- 결론 1 — 라이브 운영 사실 3가지(API 키 = `config/key.ini` · DB = `kis_template`@5433 · 전략 on/off = `trading_config.json strategies[]`)가 어느 문서에도 정확히 없고, `CLAUDE.md:171-172`·`.env.example:2-3`·`docs/CONFIGURATION.md:50,60`·`docs/STRATEGY_GUIDE.md:188-196` 은 반대로 적혀 있다. 따라 하면 기동 실패(env_guard exit 1) 또는 죽은 DB 접속이다.
- 결론 2 — 흐름·DB·위험관리 문서 6종(`SYSTEM_FLOW.md`·`docs/TRADING_FLOW.md`·`docs/DATA_MANAGEMENT.md`·`docs/DYNAMIC_RISK_MANAGEMENT.md`·`docs/PORTFOLIO_SNAPSHOT_GUIDE.md`·`docs/추세기반_적응형_청산_가이드.md`)은 존재하지 않는 파일·메서드·테이블·설정을 설명한다. 3종 재작성(통합)·3종 보관이 답이다.
- 결론 3 — `docs/CODE_MAP.md:24` 「라이브→연구 엣지 0건」은 2026-07-06 부터 거짓(`tools/paper_strategy_equity.py:258`)이고 자체 검증 명령(:46)은 `backtest` 엣지를 구조적으로 못 본다. `docs/` 재배치는 동결 사전등록 13본·태쏘 판정 보고 2본 등 「옮기면 안 되는 것」을 먼저 고정한 뒤 진행한다.
- 실행 원칙: 코드 0줄 · 문서만 · 봇 가동 중 테스트 금지 · 라이브 트리 장중 브랜치 전환 금지 · 커밋/푸시/삭제(추적 파일)는 전부 사장님 확인.

## 1. CLAUDE.md (`RoboTrader_template/CLAUDE.md` · 마지막 커밋 adc84b3 2026-08-17 · 195줄)

### 1-1 점수표 (루브릭 6항목 · 합계 46/100)

| 항목 | 점수 | 근거 |
|---|---|---|
| 명령·워크플로 | 4/20 | run/test/lint/DB 포트/로그 경로 명령 0건, resolver 3줄 스니펫뿐 |
| 아키텍처 명료성 | 13/20 | 레이어·데이터흐름·디렉토리 라우팅은 코드와 일치; :12-17 트리 오류; 전략 패키지 약 25개 미분류 |
| 비자명 패턴 | 10/15 | resolver SSOT·adj_factor 규칙·holding_period 가드·Facade/Mixin 이름 전부 검증 일치; :171-172 두 「주의사항」은 거짓 |
| 간결성 | 6/15 | 195줄 중 약 45줄이 날짜 박힌 정정 서사(:28-35, :37-39, :51-61, :68-75, :195) |
| 최신성 | 7/15 | 푸터 07-02 · 마지막 커밋 08-17 · 오늘 09-17; 09-05 집중 3전략 계획·prereg 체제·live env 플래그·K 상향 0줄 |
| 실행 가능성 | 6/15 | 따라 하면 키를 안 읽는 파일에 쓰고 no-op env 를 설정하며 포트·테스트·lint 를 모른다 |

### 1-2 확정 결함 목록 (9건 · high 3 / medium 3 / low 3)

| # | 줄 | 현재 문구 | 실제 | 근거 | 심각도 |
|---|---|---|---|---|---|
| 1 | :171 | 「`.env`에 `APP_KEY`, `APP_SECRET` 등 API 키 설정 필수」 | KIS 키는 `config/key.ini` `[KIS]` 만 읽음; `.env.example` 에 APP_KEY 항목 없음; env 로 읽는 코드 0건 | config/settings.py:61,97-98,145-146 · api/kis_auth.py:16-17 · run_robotrader.bat:46-52 · docs/audit_2026-09-14_real_trading_switch.md:590 | high |
| 2 | :172 | 「가상매매 모드: `VIRTUAL_MODE=true`」 | 그런 env 를 읽는 코드가 운영·연구 어디에도 없음; 유일한 스위치 = `config/trading_config.json` `paper_trading` | core/trading_decision_engine.py:49 · core/models.py:379,417 · config/trading_config.json:100 | high |
| 3 | :171 | 「(`.env.example` 참고)」 | `.env.example:2-3` = `TIMESCALE_PORT=5432`·`TIMESCALE_DB=robotrader`(죽은 DB·틀린 포트); env_bootstrap 이 코드 기본값(5433/kis_template)을 덮음 | db/connection.py:41-42 · config/env_bootstrap.py:19,63-65 · config/constants.py:298-300 | high |
| 4 | :12-17 | 트리 `RoboTrader`·`RoboTrader_orb` 가 kis-trading-template 안 | 형제는 `D:/GIT/` 아래 별도 레포이고 2026-07-10 자동실행 중단; 레포 루트에는 `RoboTrader_template/` 만 | `ls -d` 결과 · D:/GIT/run_all_robotraders.bat:14,23 | medium |
| 5 | :137-140 | 예제 전략 7개 | `bb_reversion_or/`·`intraday/`(11)·`books/`(19, 라이브 3전략이 import)·`allocation/` 미언급; MODULES.md:86-96 도 동일 누락 | `ls -d strategies/*/` 20개 · strategies/book_pullback_ma20/strategy.py(books import) | medium |
| 6 | :37 | 「예외 없음 … 라이브 의존 엣지 0」 | 엣지 1건: `tools/paper_strategy_equity.py:258` → `scripts.kis_db.schema`(8a02cb2 2026-07-06), `bot/system_monitor.py:593` 이 EOD 마다 호출 | docs/CODE_MAP.md:46 명령 실행 → 1건 | medium |
| 7 | :155 | 「Python 3.8+ 호환」 | 루트 pyproject `requires-python >=3.9` · ruff py39 · CI 3.9/3.11/3.12 · venv 3.9.13 | pyproject.toml:6 · RoboTrader_template/pyproject.toml:3 · .github/workflows/test.yml:14 | low |
| 8 | :195 | 「마지막 업데이트: 2026-07-02」 | 마지막 커밋 adc84b3 2026-08-17; 본문 :51,:57,:63,:70 이 08-15~17 사건 인용 | git log -- CLAUDE.md | low |
| 9 | :173 | 「PID 파일 (`robotrader.pid`)」 | 기본 인스턴스만; 다른 INSTANCE_ID 는 `robotrader_<id>.pid` | main.py:71-76,86 · instances/README.md:17 | low |

### 1-3 「얇은 라우터」로 되돌리기 — 절 단위 개정안 (목표 약 90줄)

| 현재 절(줄) | 처리 | 이동처 / 남길 것 |
|---|---|---|
| :12-17 프로젝트 트리 | 삭제 → 1줄 | 「레포 루트에는 `RoboTrader_template/` 만 있다; 형제 레포(D:/GIT/RoboTrader·_orb·_quant)는 2026-07-10 자동실행 중단」 |
| :19-26 운영/연구 디렉토리 목록 | 유지(2줄) + 링크 | 정본 = `docs/CODE_MAP.md`; 단 CODE_MAP.md:8 의 `lib/` 를 연구로 정정해 일치시킨다 |
| :28-30 lib/ 재분류 서사 | 1줄로 압축 | 「`lib/` = 연구/테스트 지원(운영 import 0)」; 상세 → CODE_MAP.md |
| :31-35 multiverse/data gitignore 사고(d89d0b6·726febf) | 1줄로 압축 | 「범용 ignore 패턴(`data/`,`lib/`)이 자체 패키지를 삼킨 전례 있음 → CODE_MAP.md」 |
| :37-39 「예외 없음」 | 정정 후 1줄 | 「라이브→연구 엣지 1건(`tools/paper_strategy_equity.py:258`) — 승격 또는 예외 등록 결정 대기; 검증 명령 → CODE_MAP.md §검증」 |
| :41-77 데이터 소스 SSOT | 규칙 6~8줄만 | resolver 3개 이름(constants.py:327/335/343) · 폐지 env 4종은 설정해도 무시 · 쓰기 스크립트만 `require_explicit_target_db()` · 가격에 adj_factor 곱하지 말 것/volume 은 읽기 계층 적용(tests 2건) · 재무 롤백 `QUANT_FINANCIAL_DB` · `daily_candles` 없음→`daily_prices` |
| :51-54, :57-61, :63-67, :68-75 정정 서사 | 이동 | 재작성될 `docs/DATABASE.md`; `docs/PAPER_STRATEGIES.md:55-65` 가 이미 verbatim 보유 |
| :81-101 레이어 다이어그램 | 이동 | `docs/ARCHITECTURE.md` 만 유지(두 그림의 레이어 순서 불일치 해소), CLAUDE.md 는 링크 |
| :104-114 데이터 흐름 8줄 | 유지 | 기본 on_tick 경로와 일치 검증됨(라이브 8전략 중 on_tick override 0) |
| :121-135 활성 8전략 표 | 유지 + 1줄 | 「SSOT = `config/trading_config.json strategies[].enabled`; K·max_capital_pct 도 거기」; (최강)/(탐색)/(관찰) 수식어 제거 |
| :137-140 예제 전략 | 교체 | 「비활성 패키지: sample/momentum/mean_reversion/volume_breakout/bb_reversion/bb_reversion_or/lynch/sawkami + `intraday/`(11) · `books/`(19) · `allocation/`(1) → MODULES.md」 |
| :142-151 새 전략 추가·holding_period/exit_timeframe 가드 | 유지 | strategies/base.py:298-372 와 일치 |
| :155 | 정정 | Python 3.9+ |
| :171-173 주의사항 | 전면 교체 | §1-4 초안의 「설정 파일」·「전략 on/off」·「PID」 항목 |
| :176-191 문서 지도 | 보강 | CODE_MAP·INVENTORY·DB통합_쉬운설명·instances/README·plan/prereg/report 명명 규약 추가; DYNAMIC_RISK·PORTFOLIO_SNAPSHOT·추세기반 행은 보관 후 제거 |
| :195 푸터 | 정정 | 날짜만 |

### 1-4 신설 절 초안 — 「개발 시작 가이드」 (gap_finder 검증 사실만 · 각 줄 실측 근거 병기)

- **코드 루트** `D:/GIT/kis-trading-template/RoboTrader_template` (git 루트는 한 단계 위). venv = `RoboTrader_template/venv` Python 3.9.13.
- **운영 vs 연구**: production = `core/ bot/ framework/ api/ strategies/ collectors/ db/ runners/ signals/ utils/ tools/ config/ main.py` · research = `scripts/ multiverse/ books/ council/ archive/ backtest/ lib/`. 연구 코드를 라이브 동작 근거로 쓰지 말 것.
- **봇 기동** = Windows 작업 스케줄러 `\RoboTrader_AutoStart`(월~금 07:40) → `D:\GIT\run_all_robotraders.bat` [5/5] → `run_robotrader.bat`(venv 활성화 → 매 기동 `pip install -r requirements.txt` → `config\key.ini` 없으면 중단 → `PYTHONIOENCODING=utf-8`·`SCREENER_SNAPSHOT_ENABLED=true` → `python -X utf8 main.py`). `python main.py` 직접 실행은 `bot/env_guard.py` 가 프로젝트 venv 가 아니면 exit 1(`ALLOW_FOREIGN_VENV=1` 은 경고만). main.py 에 argparse 없음.
- **실전 인스턴스** `run_instance.bat <id>` = `KIS_INSTANCE_DIR=instances\<id>` → key.ini·trading_config.json·`robotrader_<id>.pid`·`token_info_<id>.json`·`logs/<id>/`·`real_trading_<id>` 5중 분리, `SCREENER_SNAPSHOT_ENABLED=false`. 실전 모드는 `real_total_funds_cap` 미설정 시 `LiveStartupAbort`(bot/initializer.py:711-715). 페이퍼 기본 PID = `robotrader.pid`.
- **로그 두 갈래**(`logs/`): ① `trading_YYYYMMDD.log` = `utils/logger.py` RotatingFileHandler(10MB×7) ② `robotrader_template_YYYYMMDD_HHMMSS.log` = bat 의 stdout/stderr 캡처(①의 상위집합 · 블록 버퍼링이라 가동 중 0바이트 가능). pytest 중엔 ①이 `test_trading_` 접두사; 스크립트 직접 실행(run_dryrun.py 등)은 접두사 없이 라이브 로그에 섞인다. 레벨 = `LOG_LEVEL` env.
- **설정 파일**: KIS 키·`[TELEGRAM]` = `config/key.ini`(`key.ini.example` 복사) — `.env` 가 아님. 거래·전략 = `config/trading_config.json`. `.env`(RoboTrader_template 루트)는 `config/env_bootstrap.py` 가 stdlib 로 읽어 os.environ 에 넣되 **이미 있는 OS env 는 덮지 않는다**; 인라인 `#` 주석은 값에 포함된다(python-dotenv 미설치).
- **DB**: PostgreSQL 16.11 + TimescaleDB 2.24.0, 서비스 `postgresql-x64-16`, **port 5433**, DB `kis_template`, user `robotrader` = `db/connection.py:40-44` 기본값(`.env` 없이도 접속). `robotrader` DB 는 `robotrader_retired_20260817`(접속 차단)로 은퇴. 컬렉터·regime 은 두 번째 풀 `KIS_DB_*`(db/kis_db_connection.py:35-39) 를 쓴다. DB명은 resolver 경유; 가격에 `adj_factor` 곱하지 말 것.
- **운영 env 전수**: `TIMESCALE_HOST/PORT/DB/USER/PASSWORD` · `KIS_DB_*` · `KIS_INSTANCE_DIR` · `SCREENER_SNAPSHOT_ENABLED` · `SECTOR_NEWS_BOOST_MODE`·`RS_LEADER_CORP_ACTION_MODE`(off|shadow|live, 기본 shadow) · `OPENDART_API_KEY` · `LOG_LEVEL` · `ALLOW_FOREIGN_VENV` · `CORP_ACTION_QUEUE_PATH` · (비활성 템플릿 전략만) `STRATEGY_DB_*`·`EXTERNAL_DB_*`. 폐지 = `KIS_DATA_SOURCE`·`QUANT_DB`·`MINUTE_DB`·`CORP_EVENTS_DB`(설정해도 무시 · 되살리면 tests/test_research_data_source.py:560 실패). `VIRTUAL_MODE` 는 존재하지 않는다.
- **전략 on/off** = `config/trading_config.json` `strategies[]` 항목 `{name, enabled, max_capital_pct, regime_index, regime_gate}`; 비어 있을 때만 legacy `strategy.name` 사용. 전략 폴더 `config.yaml` 최상위 키 = `strategy / paper_trading / parameters / risk_management / target_stocks`(enabled 키 없음). 루트 `config.yaml` 은 없다. 새 전략은 `runners/_adapter_factory.py` if/elif 등록이 없으면 후보 0.
- **테스트**: 설정은 **repo-root** `pyproject.toml`(`testpaths=RoboTrader_template/tests`, `asyncio_mode=auto`, 마커 `slow`·`db`). 예: `cd RoboTrader_template && venv\Scripts\python -m pytest tests -q -m "not db"`. `tests/conftest.py` autouse 가 `TIMESCALE_DB`·이벤트 루프 원복. pytest 8.4·pytest-asyncio 1.2·ruff 0.15 는 requirements.txt 에 없고 venv 에만 있다. 회귀 판정 = 실패 «집합» 양방향 차분(기준선 `D:/tmp/minfix_baseline_clean_52169d8.txt`).
- 🔴 **라이브 트리에서 전체 스위트·DB 스모크(`tests/healthcheck`, `tests/dryrun/run_dryrun.py`, `scripts/kis_db/smoke_state_restore.py`) 실행 금지 · 장중 브랜치 전환 금지**. 작업은 `git worktree add D:/tmp/kis-wt-<topic> -b <type>/<topic>`; 라이브 트리는 항상 `main`. 봇 가동 중 머지의 발효일 = 다음 07:40 재기동.
- **lint**: `venv\Scripts\ruff check .` — `RoboTrader_template/pyproject.toml`(E9·F63·F7·F82, line-length 120, py39, `scripts/ multiverse/ books/ council/ archive/ venv*` 제외; `backtest/`·`lib/` 는 제외 목록에 없음).
- **git**: 커밋 = `type(scope): 한국어 요약`(최근 200 커밋 접두사 없음 0) · 브랜치 `feat/ fix/ docs/ test/ research/` · 머지 `--no-ff` + `merge(scope): … (<branch> N커밋)` · 신원 `tgparkk <sttgpark@gmail.com>` · 귀속 확인 `gh api repos/<o>/<r>/commits/<sha> --jq .author.login`(null 이면 실패) · 커밋/푸시는 사장님 확인. `commit_and_push.sh` 는 다른 레포(RoboTrader_quant)를 가리키는 폐기 스크립트.
- **문서 위치·이름**: 사전등록 `docs/prereg_YYYY-MM-DD_<topic>.md`(동결 = 커밋) · EOD `docs/report_YYYY-MM-DD_장마감.md` · `plan_ / review_ / audit_ / design_ / verdict_` 접두사 · 쉬운설명 `docs/<주제>_쉬운설명_YYYY-MM-DD.md` · 설계 `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` · 계획 `docs/superpowers/plans/` · 경계 `docs/CODE_MAP.md` · 인벤토리 `docs/INVENTORY.md`(`tools/gen_inventory.py`, `PYTHONUTF8=1` 필수).
- **세션 메모리·changelog** 는 레포 밖 `C:\Users\sttgp\.claude\projects\D--GIT-kis-trading-template\memory\`(SessionStart 훅 `.claude/settings.local.json:122-134` 가 백업). 레포 안 `RoboTrader_template/memory/`(50파일, 2026-06-03 이후 미갱신)는 사본이 아니라 그 시기 고유 원본이니 삭제 금지·참조 금지.

### 1-5 루트 `D:/GIT/kis-trading-template/CLAUDE.md` 신설 초안 (현재 부재 · 약 15줄)

- 코드는 전부 `RoboTrader_template/` 아래; 상세 라우터 = `RoboTrader_template/CLAUDE.md`.
- pytest 설정은 이 루트 `pyproject.toml`(`[tool.pytest.ini_options]`); `.claude/settings.local.json` SessionStart 훅이 메모리 백업.
- 봇은 월~금 07:40 자동 기동 — 라이브 트리에서 테스트·브랜치 전환 금지; 워크트리는 `D:/tmp/kis-wt-*` 또는 `.claude/worktrees/`.
- 루트 `README.md:30` 의 `cp .env.example .env # API 키 설정` 은 틀림(키 = `RoboTrader_template/config/key.ini`).
- `agents/`·`cache/`·`logs/`·`scratchpad/`(루트)는 무시/잔재 디렉토리이며 라이브 봇과 무관.

## 2. 정식 개발 문서 13종

점수는 감사 클러스터 점수(문서별 점수가 별도 산출된 경우만 병기). 마지막 커밋은 감사가 실측한 값.

| # | 문서 | 마지막 커밋 | 점수 | 판정 | 근거 1줄 |
|---|---|---|---|---|---|
| 1 | `README.md`(프레임워크) | 88c9912 2026-03-22 | 28 | rewrite | `python main.py` 는 env_guard 로 exit 1 · generate_signal 서명이 TypeError · 등록 단계 없음 |
| 2 | `../README.md`(레포 루트) | 0ca93b9 2026-02-07 | 28 | rewrite(15줄) | 유일한 실행 줄 `cp .env.example .env` 가 키·DB 두 번 틀림 · `agents/` 는 gitignore |
| 3 | `CHANGELOG.md` | 549fad2 2026-02-11 | 28 | archive → `docs/archive/CHANGELOG_2026-02.md` | 1,179 커밋 미기록 · 태그 2개 · version 0.9.0 고정 |
| 4 | `SYSTEM_FLOW.md` | 0f55984 2026-05-15 | 약 30%(flow 42) | merge → `docs/TRADING_FLOW.md` 후 `docs/archive/` | 없는 스크립트·없는 config.yaml·없는 EOD 설정·없는 텔레그램 명령 |
| 5 | `docs/ARCHITECTURE.md` | 2026-03-22 | 약 80%(flow 42) | update | 원칙·DB 정확; 모듈 목록 core 11·db 5·api 1·data_providers 2 누락 → MODULES.md 로 이전 |
| 6 | `docs/TRADING_FLOW.md` | 2026-02-09 | 약 45%(flow 42) | rewrite(정본 흐름 문서로) | 15:30 자동 종료·EOD 전량 매도 high 2 + 죽은 메서드명 5 |
| 7 | `docs/CONFIGURATION.md` | dccca90 2026-03-07 | 35 | rewrite | 은퇴 DB · 12:00 매수 마감 · `portfolio_size` · 「우선순위」 절 허구 · 운영 env 11개 미기재 |
| 8 | `docs/DATABASE.md` | 2026-08-14 | 30 | rewrite | psql/pg_dump/pg_restore 전부 `-d robotrader` · 스키마는 01-init.sql 전사(라이브와 불일치) · `adj_factor`·`source` 없음 |
| 9 | `docs/DATA_MANAGEMENT.md` | 88c9912 2026-03-22 | 30 | rewrite(짧게) 또는 archive+TRADING_FLOW 통합 | 없는 모듈 2 · SQLite 구문 · TypeError 예제 · 1분 주기 |
| 10 | `docs/STRATEGY_GUIDE.md` | 4a5aabb 2026-03-07 | 40 | rewrite(§3 골격 유지) | config.yaml 전략 교체·intraday 매도·스크리너 미언급 → 로드도 후보도 청산도 안 됨 |
| 11 | `docs/code/MODULES.md` | 6694e14 2026-06-24 | 55 | update(표는 `ls`+`grep ^class` 로 재생성) | 골격 유효 · collectors/signals/tools/runners 절 0 · 테스트 트리 약 3% |
| 12 | `docs/CODE_MAP.md` | 6b0a79c 2026-07-02 | 38 | update | 「엣지 0건」 거짓 · 검증 명령 결함 · 재생성 명령 cp949 크래시+0바이트 |
| 13 | `docs/INVENTORY.md` | e354ed5 2026-07-02 | 38 | rewrite(도구 재생성) | 187/436 파일 · LIVE-DEP 행 오태그 |

### 2-1 부속 문서 (감사 범위 내 · 같은 형식)

| 문서 | 마지막 커밋 | 점수 | 판정 | 근거 1줄 |
|---|---|---|---|---|
| `docs/PAPER_STRATEGIES.md` | af45e7c 2026-09-10 | 62 | update | 숫자 전부 검증 일치; daytrading `auto`·minervini TT `on` 미반영 · §0.2 64줄이 DB 서사 |
| `docs/OWNERSHIP_MODEL.md` | b5ea3b8 2026-08-14 | 35(클러스터) | update | 실체 정확; P1-2(a758fac) 이후 단일전략 owner 라벨 변경 미반영 · 줄번호 드리프트 |
| `docs/DYNAMIC_RISK_MANAGEMENT.md` | (미확인) | 35 | archive(+DEPRECATED 배너) | 없는 메서드 2·없는 테이블·1분 주기 · 미배선 퀀트 파이프라인 |
| `docs/PORTFOLIO_SNAPSHOT_GUIDE.md` | c2c38ef 2026-02-07 | 35 | archive(삭제 가) | 스크립트 2·테이블·main.py 로직·SQLite 전부 부재 |
| `docs/추세기반_적응형_청산_가이드.md` | c2c38ef 2026-02-07 | 35 | archive(+DEPRECATED 배너) | 분석기 미배선 · config 파일·플래그·로그 문자열 부재 |
| `docs/2026-07_전략고유청산_공백_재해석.md` | 961337e 2026-08-21 | 35 | update(후기 5줄) | 1810cd2·70d6183 반영 · base.py:693→:739 |
| `docs/DB통합_쉬운설명.md` | 2026-09-07 | 30 | update(상태 박스) | GRANT·푸시·쓰기 가드·RENAME 완료가 「미결」로 남아 있음 |
| `strategies/{8활성}/README.md` | rs_leader 4a84a06 09-10 · minervini 7fe700c 08-19 · daytrading c17de86 08-15 | 62 | keep 4(elder·envelope·ma5·deep_mr) / update 4(daytrading·minervini·ma20·rs_leader) | daytrading `auto` · minervini TT 절 stale · K 상향 09-18 · rs_leader live 09-17 |
| `strategies/bb_reversion_or/README.md` | — | 62 | update | 폴더명 복붙 오류 · multiverse_grid.yaml 누락 |
| `strategies/sample/README.md` | — | 40 | update | 값 불일치(min_buy_signals 2 vs 1 · RSI 30 vs 40) · `_load_strategy()` · 폴더 구성 누락 |
| `instances/README.md` | 4ffab77 2026-06-18 | 35 | rewrite | 은퇴 DB · `real_total_funds_cap` 누락(따라 하면 첫 기동 abort) · 3중 vs 5중 |
| `.env.example` | 1-5줄 c2c38ef 02-07 · 6줄 f80cae0 09-15 | 35 | update(값 3개 + 인라인 주석 제거) | 5432/robotrader · 6줄 인라인 `#` 가 값에 포함돼 guard 가 `off` 로 강등 |
| `docs/quant_strategy_plan.md` | 2026-02-07 | 45 | archive | 대상 파일 8개 전부 부재 · 인바운드 0 |
| `docs/refactoring_2A_report.md` | 2026-02 | 45 | archive | 일회성 역사 기록 · 인바운드 0 |
| `docs/reference/*.md`(2) | 2026-03-07 | 45 | archive → `docs/archive/reference/` | 코드 언급 0 · 인바운드 0 |
| `docs/TODO_2026-08-27.md` | e004f2c 2026-09-15 | 45 | update(:19,:136 · :27-29) | rs_leader 겹침 브랜치는 45c5a5d 로 08-27 머지 완료 · 사이징 fe02983 |
| `docs/N1_수리_로드맵_쉬운설명_2026-09-03.md` | — | 45 | update(:42) | 같은 머지 완료 미반영 |

### 2-2 문서별 확정 결함 (high 먼저)

#### README.md (프레임워크)
- high :149 `def generate_signal(self, stock_code, data):` — 추상 서명은 `timeframe: str = 'daily'` 포함, 모든 호출이 키워드로 넘겨 첫 tick 에 TypeError. strategies/base.py:454-459,708,749 · core/trading/position_monitor.py:359-361.
- high :43-44 `python main.py` — 운영 런처는 `run_robotrader.bat`(venv·`-X utf8`·`SCREENER_SNAPSHOT_ENABLED=true`·로그 리다이렉트); 직접 실행은 스냅샷 off → 거래량 순위 폴백. run_robotrader.bat:80-83 · config/constants.py:225 · bot/liquidation_handler.py:591-592.
- high :33,44(,195) `pip install` → `python main.py` — venv 생성·활성화 단계가 없어 시스템 파이썬이면 env_guard 가 exit 1. main.py:694-697 · bot/env_guard.py:26-33,52-59.
- medium :176-190 config.yaml 예시 7개 키(`portfolio_size`·`stop_loss_rate` 등) — 어느 코드도 읽지 않음; 실제 스키마 `risk_management.{max_position_size,stop_loss_pct,take_profit_pct,max_daily_trades}`. strategies/sample/config.yaml:43-47 · strategies/config.py:14,63.
- medium :39-44 폴더 복사만으로 로드 — `trading_config.json strategies[]` 등록 없이는 로드 안 됨. main.py:168-176 · config/trading_config.json:32-88.
- medium :18-23 형제 트리(RoboTrader_quant 포함) — 이 레포 자체가 8전략 라이브 봇이고 형제는 import 0; 세 문서가 세 가지 트리. CLAUDE.md:12-17 · docs/superpowers/specs/2026-06-22-data-collection-migration-design.md:5.
- medium :53-105 트리 34경로는 실재하나 `bot/ collectors/ signals/ runners/ tools/ market_dashboard/` 등 약 50 운영 모듈 누락. `ls -p` · CLAUDE.md:24-25.
- low :7 Python 3.8+ 배지 · :8 License Private(pyproject 는 MIT) · :31-32 `cd RoboTrader_template`(clone 후 경로는 `kis-trading-template/RoboTrader_template`) · :246-250 관련 문서 5개뿐(PAPER_STRATEGIES·MODULES·OWNERSHIP·CODE_MAP·DATABASE·STRATEGY_GUIDE 없음) · :255 「2026-03-22」.

#### README.md (레포 루트)
- high :30 `cp .env.example .env # API 키 설정` — 키는 `config/key.ini`; `.env.example` 에 키 항목 없음. config/settings.py:61,97-98 · run_robotrader.bat:46-53.
- high :30 같은 줄 — 복사하면 5432/`robotrader`(포트 거부, DB 없음). .env.example:2-3 · db/connection.py:41-42 · pg_database 실측.
- medium :36-40 RoboTrader 「운영 중」 — 2026-06-22 spec 이 rt·rt_quant 전략 폐기; 세 문서 세 표. specs/2026-06-22:5 · `git -C D:/GIT/RoboTrader log -1` 2026-06-04.
- medium :20 `agents/` — 루트 .gitignore:15 로 무시, 클론에 없음. `git ls-files agents` 0.
- low :10-19 트리 — bot/ collectors/ signals/ runners/ tools/ docs/ scripts/ 누락.

#### CHANGELOG.md
- medium :5 `[0.9.0] 2026-02-10` 이 최신 — 이후 1,179 커밋 미기록, 태그 2개, 루트 pyproject version 0.9.0. git log 실측.
- low :61 「1014 passed」 — 372 파일·5,012 `def test_`(정적 집계). · low :28-30 예제 4전략 — 지금은 비활성, 라이브 8종은 다름. CLAUDE.md:137-139.

#### SYSTEM_FLOW.md
- high L423 `python scripts/daily_trading_summary.py` — 파일은 `tools/`. bot/system_monitor.py:12.
- high L359-364 `config.yaml` 로 전략 지정 — 그런 파일 없음; `trading_config.json strategies[]`. main.py:168-172 · strategies/config.py:87,104.
- high L95,219-221 EOD 「(설정 시)」 — on/off 설정 없음; 매 거래일 1회 무조건 실행하되 `should_liquidate_eod()` False(swing) 는 건너뛰고 라이브 8/8 이 swing. config/market_hours.py:200-201,450-477 · bot/liquidation_handler.py:267-270 · strategies/base.py:825.
- high L370,L171 Signal `target_price`/`stop_loss` 사용 — 2026-06-25 제거; tp/sl = 호출자 → 전략 config.yaml `risk_management` → trading_config.json → DEFAULT. core/trading_decision_engine.py:575-581,583-600.
- medium L410 텔레그램 수동 매수/매도·종목 추가 — 명령은 /status /positions /orders /virtual /help /stop 뿐, /reload 는 TODO. utils/telegram/telegram_notifier.py:100-107 · bot/candidate_loader.py:32-33.
- medium L108-114,L276-279 08:30 수집·08:55 스크리닝 게이트 — 없음; 수집은 15:35+ 후장, 후보는 09:00 첫 반복에서 스냅샷 소비. bot/system_monitor.py:117-127,248,364 · main.py:438-440.
- medium L60-62,L271-286 메모리/CPU 감시 — psutil 은 PID 중복검사만; 5초 주기는 맞음. bot/system_monitor.py:106,950-999.
- medium L71,L155-161,L260-261 [4/5] `generate_signal()` 직접 — 실제 `on_tick(ctx)` 라운드로빈(8전략이면 전략당 약 72초), 문서에 on_tick·TradingContext 0회. main.py:465-500.
- medium L366 사용 가능 전략 7개 — 비활성 템플릿; 라이브 8종은 다른 이름. config/trading_config.json.
- medium L121-123 후보를 `generate_signal()` 이 결정 — SELECTED 풀은 CandidateLoader/screener_snapshots 가 만들고 generate_signal 은 그 안만 평가. bot/candidate_loader.py:44-95,181-186 · core/candidate_selector.py:1010.
- low L192-217 매도 순서(stale→max_hold→레거시 trailing→tp→sl(09:00-09:05 제외)→전략신호) · L83 08:50 시작(07:40 자동) · L89-90 15:20 루프 종료(15:30) · L35-40 복원이 별도 단계(initialize_system 4단계 내부 + on_init 후 재주입) · L345-347 수집=장전(15:35+) · L413 CLAUDE.md 「전략 개발 방법」 절 없음(「새 전략 추가」) · L430-431 2026-03-22(마지막 커밋 05-15).

#### docs/ARCHITECTURE.md
- medium L40-57 구성 트리 — `CandidateLoader`·`CandidateSelector`·`env_guard` 누락. main.py:30,57-58,131,153,696-697.
- medium L96-130 core/ 목록 — candidate_selector·dynamic_batch_calculator·intraday_data_utils·post_market_data_saver·realtime_candle_builder·realtime_data_logger·regime/·report_generator·screener_snapshot_provider·sector_news_rerank·timeframe_converter 누락. `ls core/`.
- medium L134-145 db/ 목록 — kis_db_connection·quant_daily_reader·adj_backup·migrations/·repositories/sector_news 누락. `ls db/`.
- low L40 「~670줄」(737) · L65-66 FundManager 가 broker.py 데이터클래스(core/fund_manager.py:167, broker.py:854-855 는 재export) · L72-78,L83-91 market_data_legacy·utils·circuit_breaker 누락 · L153-162 의존성 표에 yfinance·holidays·finance-datareader·beautifulsoup4 없음 · L168 「api/ 직접 호출 안 함」은 lynch/sawkami/sample 5파일이 위반(비활성).

#### docs/TRADING_FLOW.md
- high L19-24,L167-181 15:30 `shutdown()` — 자동 종료 없음(장외 30초 idle); `shutdown()` 은 SIGINT/SIGTERM 또는 critical 재시도 소진 시; `on_market_close` 는 15:00 EOD 직후; 리포트는 15:35+ SystemMonitor. main.py:433-435,337-338,607-610 · bot/initializer.py:742-761.
- high L81-84,L170-173 15:00 「모든 포지션 시장가 매도」 — swing 소유 포지션은 건너뜀(라이브 8/8), 재시도 3×10초 → 강제 COMPLETED+CRITICAL 텔레그램 미기재. bot/liquidation_handler.py:24-25,267-270,366-372 · main.py:587-592.
- medium L40 `_load_strategy` → `_load_strategies`(main.py:136,165) · L63 `check_pending_orders()` → `check_pending_orders_once()`(main.py:455) · L68 `check_positions()` → `check_positions_once()`(main.py:461) · L126 `OrderManager.create_buy_order()` 없음(`ctx.buy`→TradingAnalyzer→DecisionEngine→`execute_virtual_buy`/`place_buy_order`, core/trading_context.py:313,521) · L138-143 `PositionMonitor.check_position()` 없음(`_analyze_sell_for_stock`, 우선순위·09:00-09:05 손절 정지·`<=`, core/trading/position_monitor.py:200-366).
- medium L74-79 「매수 판단 매 9초」 — no-strategy 폴백 설명; 실제 on_tick 라운드로빈이며 매도도 포함. main.py:465-500 · strategies/base.py:641-757.
- medium L162 시스템 모니터링 「메모리/CPU」 — 실제 24h API 재초기화·장전 작업·15:35+ 후장 체인·30분 상태 로그. bot/system_monitor.py:76-111.
- low L14 「DB 연결 확인」 단계 없음(bot/initializer.py:582-627) · L42-46 connect 는 initialize_system 내부, on_init 후 `apply_pending_strategy_positions`·`rescan_orphans_after_init`·`set_strategies`·`set_fund_manager` 누락(main.py:269-310) · L119-124 엔진이 generate_signal 호출(라이브는 owner_signal 전달, core/trading_decision_engine.py:375-384) · L12-16 전략 로드가 BotInitializer 안(`__init__` 의 `_load_strategies`, main.py:136).

#### docs/CONFIGURATION.md
- high :50 「Database: robotrader」 — kis_template; robotrader 는 `robotrader_retired_20260817`(datallowconn=f). db/connection.py:42 · pg_database 실측.
- high :60 `TIMESCALE_DB=robotrader` — env 가 코드 기본값을 덮어 없는 DB 접속. config/env_bootstrap.py:63-65.
- high :117 「매수 마감 12:00」 — `buy_cutoff_hour` 호출자 0(결선 안 됨); 실제 신규 매수 차단 15:20; 08-06 실측 최대 15:09 매수. config/market_hours.py:18,205,621-624.
- medium :76 `portfolio_size` — TradingConfig 필드 아님, JSON 에도 없음. core/models.py:370-381 · config/constants.py:6.
- medium :77-78 `strategy.name`/`enabled` — `strategies[]` 가 비어 있을 때만 쓰는 legacy; `strategies[]` 스키마·`real_total_funds_cap`·`rebalancing_mode` 미기재. core/models.py:376,381 · main.py:170-173.
- medium :95 `API_CALL_INTERVAL` 0.06 → 0.10. config/constants.py:76.
- medium :160-165 「설정 우선순위」 4단 — 네 소스는 서로소; 실제 체인은 OS env > `.env` > 코드 기본값뿐. config/env_bootstrap.py:34,63-65.
- medium :65 `01-init.sql` 만 — 02~06 + `db/migrations/` 4 + 런타임 DDL(sector_writer·financial_writer·sector_news 등) 필요. `ls init-scripts` · db/repositories/price.py:148-149.
- low :130-142 sample config 예시(rsi_oversold 30·min_buy_signals 2 vs 실제 40·1) · :10-18 트리에 `env_bootstrap.py` 없음(main.py:22-27) · :11,22-31 key.ini `[TELEGRAM]` 절 미기재(config/key.ini.example:9-13 · core/telegram_integration.py:70-73).

#### docs/DATABASE.md
- high :12 `Database robotrader` · :34 `TIMESCALE_DB` 기본 robotrader · :347 `psql -d robotrader` · :359 `pg_dump -d robotrader` · :364 `pg_restore -d robotrader` — 전부 은퇴 DB. db/connection.py:34-42 · pg_database 실측.
- high :46-62 `adj_factor` 행 없음 — close 는 이미 조정(adj_close = raw/adj_factor), volume 만 읽기 시 곱함. db/repositories/price.py:146-162 · collectors/adj_factors.py:16,29.
- high :106-123 vtr 에 `source`·`is_overflow` 없음 — 모든 read/write 가 `source='kis_template'` 필터. db/repositories/trading.py:24,270-272,447-450 · init-scripts/05.
- medium :44 Hypertable·7일 청크 — kis_template 하이퍼테이블 0. `timescaledb_information.hypertables`.
- medium :48-62 타입 — `date` text·double precision·트리거 없음. `\d daily_prices`.
- medium :144-162 `real_trading_records` 고정명 — 인스턴스별 `real_trading_<id>`(실재 `real_trading_rs_leader`); fee_amount/net_profit 미기재. config/settings.py:38-41 · trading.py:26-52.
- medium :171-196 `financial_data` 라이브 표 — 0행·호출자 0. db/repositories/quant.py:48.
- medium :200-227 `financial_statements` — 4,350행 2026-03-01 동결·writer 0·`operating_cash_flow` 컬럼 누락.
- medium :275-277 `trading_records` — 존재하지 않음(`to_regclass` NULL).
- medium :336 01-init.sql 만 · :338 `post_market_data_saver` 저장 로직(2026-09-03 제거, 분봉 덤프만; core/post_market_data_saver.py:5,26).
- medium :28-36 env 표 — 두 번째 풀 `KIS_DB_*`(11파일)·폐지 env·`QUANT_FINANCIAL_DB` 미기재. db/kis_db_connection.py:33-39.
- medium :292-317 관계도 9표 — 운영 참조 약 40표(minute_candles·stock_sector_map·screener_snapshots·paper_strategy_equity 등), DB 에 76표.
- low :66-67 인덱스 2개 없음 · :337 `scripts/migrate_to_timescaledb.py` 없음 · :102 §2.3 결번(0f55984) · :1 「RoboTrader」 제목 · :231-253 quant_factors 타입·timing_score/hybrid_score 누락 · :257-271 quant_portfolio 타입·인덱스 누락.

#### docs/DATA_MANAGEMENT.md
- high :21 「08:30 ML 수집」 — daily_prices 는 16:01 EOD 수집(전 유니버스)+장중 upsert. bot/system_monitor.py:399 · collectors/eod_collection.py:48-49.
- high :43 `core/ml_data_collector.py` — 없음(형제 RoboTrader_quant 파일). specs/2026-06-22:151.
- high :54(:101,:124,:358) `core/data_collector.py` — 인메모리 RealTimeDataCollector, SQL 0줄. core/data_collector.py:17.
- high :62 financial_statements 08:30 — writer 0, 2026-03-01 동결; 라이브 재무는 dart_*·kis_financial_ratio. collectors/financial_writer.py:18,47,65,88.
- high :136-152 vtr 컬럼에 `source` 없음. db/repositories/trading.py:270-272.
- high :169-180 `save_virtual_sell(profit_loss=…, profit_rate=…)` — 파라미터 없음 → TypeError; P/L 은 내부 계산. trading.py:289-291,364-365.
- high :262-284 `b.is_test = 1` — boolean=integer 연산자 오류; `source` 필터 누락. trading.py:431-461.
- high :288 `core/helpers/state_restoration_helper.py` — 없음; `bot/state_restorer.py`. main.py:140 · state_restorer.py:586.
- medium :23-25 「상위 30종목」(전 유니버스, collectors/daily_collector.py:33,41) · :116 `INSERT OR IGNORE`(SQLite, collectors/daily_writer.py:41-48) · :193-218 `quant_factor_scores`·`selection_reason`(실제 `quant_factors`·`reason`, init-scripts/01-init.sql:184,214) · :257 「1분마다」(3초, main.py:422 · position_monitor.py:66).
- low :183 코드 위치 database_manager.py(파사드; SQL 은 repositories/trading.py) · :297-298 복원 tp/sl(NaN 가드·DEFAULT·stale 오버라이드, bot/state_restorer.py:621-632,708-712) · :426 2026-03-22 · :245-248 복원이 paper 경로만(실전은 `get_real_open_positions` 잔량 술어, state_restorer.py:588-594).

#### docs/STRATEGY_GUIDE.md
- high :188-196 및 :355-362 「메인 `config.yaml` 로 자동 로드/교체」 — 루트 config.yaml 없음; `trading_config.json strategies[]` 가 비어 있지 않으면 `strategy.name` 은 무시. config/settings.py:62 · main.py:170-172 · trading_config.json:32-89.
- high :275-276 「`timeframe='intraday'` → 매도 판단」 — swing 이면 `exit_timeframe='daily'` 로 매도 루프도 daily 봉·`timeframe='daily'`; intraday 로 게이트한 매도 로직은 절대 안 탄다(라이브 8/8 swing). strategies/base.py:365,739-747.
- high :60,:372 「generate_signal 하나만 구현하면 동작」 — 후보는 자기 전략의 screener_snapshots 에서만 오고 어댑터는 `runners/_adapter_factory.py` if/elif 등록 필요; 거래량 폴백은 전 전략 후보 0일 때만. runners/_adapter_factory.py:23-61 · core/candidate_selector.py:1044-1051 · bot/candidate_loader.py:185-186.
- medium :364 `_load_strategy()`(→`_load_strategies`, main.py:165) · :256-257 Signal target_price/stop_loss 엔진 활용(2026-06-25 제거, core/trading_decision_engine.py:575-581) · :239 `days=60`(기본 None→120, core/trading_context.py:176,193-194) · :111,:229 `"position"` 값(처리 코드 0; exit_timeframe='intraday' 로 떨어짐, base.py:365,825) · :213,:215 on_market_open/close(첫 로드 전략만 받음, main.py:246-263,193-194) · :216 on_tick 동기 서명(실제 async·라운드로빈; sync 로 override 하면 매 tick TypeError, main.py:486-487) · :265-273 일봉 컬럼 `datetime`(실제 `date`, db/repositories/price.py:160,177).
- medium strategies/sample/config.yaml:66-70 `target_stocks` — 다중전략에서 첫 전략만 등록. bot/system_monitor.py:168-181.
- low :9-27 트리(20폴더·screener.py·README 필수) · :242 ctx.buy 가드 3개(실제 약 10개, core/trading_context.py:313-500) · :237 get_selected_stocks(owner 필터) · :247 `'regular'` 없음(config/market_hours.py:27-36) · :373 `strategy.name 필수`(최상위 `name` 자동 채움, strategies/config.py:118-119) · :183-184,:372 클래스명 `Strategy` 접미 필수 미기재(config.py:527-542) · :330-336 테스트 예제가 최소 MyStrategy 에서 AttributeError(base.py:351-397).
- strategies/sample/README.md — medium :78-84,:90 config 방식·`_load_strategy` · low :7,:12,:41 값 불일치 · low :25-30 `__init__.py`·`screener.py`·`multiverse_grid.yaml` 누락(복사 시 `strategy_name="sample"` 어댑터가 딸려감).

#### docs/code/MODULES.md
- high :211-216 `pytest tests/ -v` / `python tests/dryrun/run_dryrun.py` — 라이브 트리에서 치면 `logs/` 에 로그 오염(run_dryrun 은 pytest 가 아니라 `trading_` 접두사로 라이브 로그에 직접 섞임), healthcheck 는 라이브 DB 풀; 마커 `-m 'not db'`·루트 pyproject·워크트리 규칙 0줄. utils/logger.py:59-69 · tests/healthcheck/run_healthcheck.py:68-69 · tests/dryrun/dry_run_bot.py:14,28.
- medium :23,:33 `_load_strategy()`(→`_load_strategies`, main.py:136,165) · :18,:46 on_tick 「매 9초」(라운드로빈, 8전략이면 약 72초, main.py:465-469) · :118-133 core/ 13모듈+regime/ 누락(3개는 `__init__` 배선) · :137-148 bot/ candidate_loader·env_guard·eod_benchmark 누락 · :156 settings.py 「.env 기반」(key.ini+trading_config.json; .env 는 env_bootstrap) · :152-158 config/ 에 env_bootstrap·trading_config.json·key.ini·visualization_strategies.yaml 없음 · :162-169 db/ kis_db_connection·quant_daily_reader·adj_backup·migrations 누락(`db/config.py` 는 운영 import 0 · port 5432) · :185-209 테스트 트리 17항목 vs 372파일·26폴더 · 전체(58-183) collectors(33)/signals(2)/tools(4)/runners(3) 절 0.
- low :8 「≈670줄」(737, 작성 시점 920) · :47 폴백 설명 · :42-48 루프 전 단계 누락 · :28-33 `__init__` 배선 4개 누락 · :62 FundManager 위치 · :98-100 Signal `entry_min/max_price` 누락 · :77 ScreenerBase 미기재 · :86-96 템플릿 목록 · :104-114 circuit_breaker 누락 · :158 market_hours 의 CB/VI 상태 · :169 repositories/sector_news 누락 · :175-181 utils 12모듈+telegram/ 누락 · :64-65 data_providers 8클래스 중 4 · :35-38 initialize() 3단계 누락 · :67 `__init__` 이 BaseBroker 등 미export · :147 position_sync 사실상 휴면.

#### docs/CODE_MAP.md
- high :24 「엣지 0건」 — 1건(tools/paper_strategy_equity.py:258, 8a02cb2 2026-07-06, EOD 경로).
- high :51-52 재생성 명령 — Python 3.9.13 리다이렉트 시 cp949 로 `—` 인코딩 실패, 쉘이 먼저 `docs/INVENTORY.md` 를 0바이트로 열어 truncate; `PYTHONUTF8=1` 필요, LIVE-DEP=1.
- high :46 검증 명령 끝의 `grep -v test` 가 `from backtest`/`import backtest` 매치를 전부 제거 — 자기 패턴의 1/3 을 구조적으로 못 본다.
- medium :7-8 `lib/` 운영(2026-07-10 연구 재분류, 운영 import 0) · :16-18 줄번호 252→313·432→601, 연구 전용 `_adjacent_grid.py` 미언급 · :41 `매일_분석_실행.bat` :13,:18 대상 파일 부재(이력에도 없음) · :7-10 `market_dashboard/`(라이브 import, bot/system_monitor.py:59-61) 미분류.
- low :47 dir 범위 좁음(strategies/utils/lib/config 제외) · :38 `:885`→`:1082` · :4 최종 검증 07-02(07-06 깨짐) · :6-22 cache/charts/data/htmlcov/init-scripts/instances/memory/output/reports/scratchpad/visualization/venv_broken_quantcopy/config/main.py 미분류 · :9 tools/ 4개 중 2개만 라이브 import · :10 ruff extend-exclude 에 backtest·lib 없음(pyproject.toml:5-6).

#### docs/INVENTORY.md
- high :149 `scripts\kis_db\schema.py` TEST-ONLY → 실제 LIVE-DEP.
- medium 전체 — 187행 vs 연구 .py 436(backtest 222·scripts 145·multiverse 69), 249파일 미기재; 187경로는 전부 실재, 태그 3건 변경.
- low :42 `multiverse\data\corp_events.py`·:44 `pit_reader.py` UNREFERENCED → TEST-ONLY.

#### docs/PAPER_STRATEGIES.md
- high :142 daytrading regime idx 「KOSDAQ」 — 09-11 부터 `auto`(9ab3c37). config/trading_config.json:48-52.
- medium :143 minervini 진입·유니버스에 TT 없음(08-25 부터 dryup ∧ TT, screener.py:42,162-171) · :113-115 사이징 = 자본÷K 만(재기동마다 복리 재산정 + `max_per_stock_amount` 캡, core/virtual_trading_manager.py:300,358-360,591-616) · :116 max_capital_pct 「FundManager reserve 비율」(provider 미주입 → StrategyLoader 합계 WARNING 만, core/fund_manager.py:183,297 · main.py:119) · :149 `max_candidates=10`(스냅샷 20 · 소비 10, constants.py:200) · :37 adj_factor NULL 44,923(오늘 411,488).
- low :23-25 스냅샷 수치 undated(현재 3,208,902행·2,800종목) · :4 「최종 갱신 06-24」(6회 편집) · :130,:133 줄번호 드리프트 · :146/rs_leader README:25,42 「기본 shadow」(09-17 live 발효 사전등록 미언급) · 전 문서 focus-3/관측 지정 0 · :83 「rules.py 에 없다」(re-export 로 남음).
- strategies/minervini_volume_dryup/README.md — high :49,:69,:79,:106 「현재 shadow」(08-25 부터 `on`, 86ff02d) · low :73-74 rules.py:52/:66 → :55-56/:69-70.
- strategies/daytrading_3methods_breakout/README.md — high :23 「index KOSDAQ」(`auto`).
- strategies/bb_reversion_or/README.md — low :43-49 폴더명 `bb_reversion/` 복붙, multiverse_grid.yaml 누락.

#### docs/OWNERSHIP_MODEL.md
- medium :16 「단일전략 모드 후보 등록 = 클래스명(candidate_loader.py:100)」 — a758fac(2c045de 머지·09-16 발효) 이후 전략 1개면 폴더키; 클래스 :23.
- low :15 :186→:235-240 · :19,:23,:33,:35 :529→:535-537 · :81 +6줄(:475/:508/:488) · :83 +6줄(:431/:451) · :72 :100→:128.

#### docs/DYNAMIC_RISK_MANAGEMENT.md
- high :58-77 `db_manager.get_factor_scores()` 없음(`get_quant_factors`, db/database_manager.py:232) · :86-97 `from api.kis_market_api import get_current_price` ImportError(`get_inquire_price`; `get_current_price` 는 KISAPIManager 메서드, api/kis_api_manager.py:291).
- medium :306-311 `quant_factor_scores`(→`quant_factors`) · :329-330 「1분마다」(3초) · :287-292 `update_virtual_buy_targets` 없음 · :29,:335-336 08:55 스크리닝·09:05 리밸런싱 실행자 없음(`rebalancing_mode:true` 는 수집 모드만).
- low :139,:160 「퀀트 구현 시 작성」 — 티어 표가 이미 config/constants.py:132-138 에 죽은 상수로 존재.

#### docs/PORTFOLIO_SNAPSHOT_GUIDE.md
- high :55,:218,:237 `scripts/save_portfolio_snapshot.py` 없음 · :70,:98,:238 `view_portfolio_snapshot.py` 없음 · :25-46 `portfolio_snapshots` 표 없음 · :103-116,:177-180,:239 main.py:551-559 로직 없음(bot/system_monitor.py:946-948 은 「미구현」 스텁) · :240,:228-231 SQLite(`data/robotrader.db`, 운영 sqlite3 0).

#### docs/추세기반_적응형_청산_가이드.md
- high :117-124,:248 「분석기 통합·자동 활성화」(import 는 tests/verify_imports.py:39 뿐) · :123,:187-205,:269 `config/trend_exit_config.json` 없음 · :209-212,:255-259 `use_trend_based_exit` 없음.
- medium :250-253 「추세 기반 청산: ON」 로그 없음 · :42-60,:93-100,:293 트레일링 — 유일한 라이브 트레일링(+5%/-3%)은 소유 전략 없는 포지션만(position_monitor.py:287-293).
- low :5,:284-288 20%/10% 예시(기본 15%/10%, 전략별 config.yaml) · :120 · :239 로그 예시 도달 불가.

#### docs/2026-07_전략고유청산_공백_재해석.md
- low :14 base.py:693→:739-742, 1810cd2 로 전략 sl/tp 판정 자체가 제거됐음을 추기 · :87 rs_leader README 는 70d6183 로 이미 정정(config.yaml:21 주석만 남음).

#### docs/DB통합_쉬운설명.md
- medium :159-160,:247 「GRANT SELECT 못 받음」(현재 26표 전부 SELECT 가능) · :249-251 백필 중단 제안(`require_explicit_target_db` 구현·7스크립트 채택) · :163-164 「이름만 바꿔서」 계획(실행됨: `robotrader_retired_20260817`, 새 이름 미기재).
- low :248 「커밋 4개 미푸시」(origin/main 포함).

#### instances/README.md · .env.example · 기타
- high instances/README.md:10 「robotrader DB」(kis_template) · :8-10 `real_total_funds_cap` 누락(bot/initializer.py:711-715 abort).
- high .env.example:2 `TIMESCALE_PORT=5432`(5432 접속 거부) · :3 `TIMESCALE_DB=robotrader` · :6 인라인 `#` 주석이 값에 포함돼 `RS_LEADER_CORP_ACTION_MODE` 가 미지값 → `off` 강등(config/env_bootstrap.py:51,57-61 · constants.py:280-283).
- low instances/README.md:6-8 예제 파일 위치 미기재(instances/rs_leader/ 만) · :3 「3중」(5중) · :13 「전체 gitignore」(*.example 2건 추적).
- medium docs/TODO_2026-08-27.md:19,:136 · N1_수리_로드맵:42 「rs_leader 겹침 미머지」(45c5a5d 08-27 머지) · low TODO:27-29 「코드 0줄」(fe02983 08-27).
- low 깨진 링크: reports/books_research/index.md:4-5(2026-05-27 spec/plan 없음) · backtest/tasso_entry_timing/README.md:80,:127(2026-08-01 spec 없음) · reports/books_research/{lynch_one_up,elder_triple_screen}/research.md 자리표시자 · superpowers/plans/2026-06-18:486 체크리스트 미생성 · backtest/concept_fidelity_audit/RESULTS.md:88,:312 PAPER_STRATEGIES:51 앵커 이동(:81-82) · docs/prereg_2026-09-14_{fund_distress_warning:863,news_disclosure_surge:592,news_event_curve:514} `../../docs/` 링크(동결 문서 → 편집 금지, 기록만) · report_2026-09-04:29·09-05:29 메모리 상대링크 · superpowers/specs/2026-08-20:4 `../../../../memory/` · superpowers/plans/2026-08-03:957 `superpowers/specs/…`(→`../specs/`) · superpowers/specs/2026-05-30:3 research.md 미작성 · reports/books_research/minervini_vcp/{report:9,research:5} 없는 spec.
- 코드 주석·docstring 이 같은 오류를 품은 곳(문서 아님 · 별건): config/env_bootstrap.py:7-8 · api/kis_auth.py:15 · strategies/base.py:29,:273 · bot/system_monitor.py:93 · minervini screener.py:37-38 · bot/state_restorer.py:805-807 · rs_leader/config.yaml:21 · db/database_manager.py:261 · run_robotrader.bat:69-71(`robotrader_template.pid`) · 매일_분석_실행.bat:13,18.

## 3. 중복·모순

| 주제 | 같은 내용을 담은 문서 묶음 | 정본 후보 | 모순(서로 다른 값) |
|---|---|---|---|
| DB 접속 정보 | CONFIGURATION.md:48-63 · DATABASE.md:11-14,32-36,347-364 · .env.example:1-5 · instances/README.md:10 · CLAUDE.md:43-58 · PAPER_STRATEGIES §0.2 | 재작성 DATABASE.md §1(코드 기본값 db/connection.py:40-44) | 포트 **5433**(CONFIGURATION·DATABASE·코드) vs **5432**(.env.example) · DB **kis_template**(CLAUDE·코드) vs **robotrader**(나머지 4곳) · 암호 `1234`(코드·문서) vs `robotrader_secure_pw_2024`(.env.example, 기능상 무해) |
| API 키 위치 | CONFIGURATION §1·README:36-37(**key.ini** ✓) vs CLAUDE.md:171·MODULES.md:156·env_bootstrap.py:7-8·루트 README:30(**.env** ✗) | CONFIGURATION §1 | key.ini vs .env |
| 전략 활성화 메커니즘 | STRATEGY_GUIDE:186-196,353-362 · sample/README:76-84 · README:174-190 · CONFIGURATION:69-78 · SYSTEM_FLOW:359 | `config/trading_config.json strategies[]`(PAPER_STRATEGIES.md:3 만 명시) → CONFIGURATION §3 재작성 | 5문서가 5가지 stale 방식(config.yaml / strategy.name / 폴더 복사) |
| 운영 vs 연구 경계 | CLAUDE.md:19-39 · CODE_MAP.md:6-22 · tools/gen_inventory.py:14-17 · pyproject.toml:6(ruff) | CODE_MAP.md | `lib/`: CLAUDE 연구 / CODE_MAP·gen_inventory 운영 / ruff lint 대상 · `backtest/`: 문서 연구 / ruff lint 대상 · `config/`+`main.py`: gen_inventory 운영 / 문서 미기재 |
| 형제 프로젝트 트리 | README:18-23 · 루트 README:36-40 · CLAUDE.md:12-17 | 삭제(CLAUDE.md 1줄) | 세 문서 세 목록(quant 포함/불포함, 「운영 중」) |
| 메인 루프 5단계·초기화 | SYSTEM_FLOW §1/§2/§8 · TRADING_FLOW §1/§2/§5 · MODULES.md:13-51 · CLAUDE.md:104-114 · ARCHITECTURE L35-58 | TRADING_FLOW(재작성) | on_tick 9초/전략 vs 라운드로빈 · 복원 위치 |
| Task Supervisor | TRADING_FLOW §5 · MODULES.md:22,51 · ARCHITECTURE L170 · SYSTEM_FLOW:58-62 | TRADING_FLOW §5(정확: constants.py:109-111) | 없음 |
| 매수/매도 결정 흐름 | SYSTEM_FLOW §4-6 · TRADING_FLOW §4 · CLAUDE.md:104-114 | TRADING_FLOW §4 | 손절/익절 순서·09:00-09:05 정지 |
| EOD·장마감·일일 타임라인 | SYSTEM_FLOW §3/§6/§8 · TRADING_FLOW §2/§6 · CLAUDE.md:148 · CONFIGURATION:118 | TRADING_FLOW §6 + 신설 「하루 타임라인」 | 「모든 포지션」 vs swing skip · 15:30 종료 vs idle · 08:30/08:55 vs 15:35+ |
| 레이어 다이어그램 | ARCHITECTURE L7-29 · CLAUDE.md:81-101 | ARCHITECTURE | 레이어 순서(strategies/framework/core/bot/api vs strategies/bot/framework/api/core) |
| 모듈·디렉토리 목록 | ARCHITECTURE L60-145 · MODULES.md:58-182 · SYSTEM_FLOW:374-386 · README:53-105 · 루트 README:9-21 | MODULES.md(재생성) | 누락 집합이 문서마다 다름 |
| 예제 전략 표 | MODULES.md:86-96 · STRATEGY_GUIDE:280-287 · CLAUDE.md:139 | MODULES.md | 셋 다 동일하게 불완전 |
| 활성 8전략 수치(K/sl/tp/regime) | CLAUDE.md:126-135 · PAPER_STRATEGIES:138-147 · 8 README · config.yaml · trading_config.json | config.yaml+trading_config.json(허브 표는 파생) | daytrading regime KOSDAQ(허브·README) vs auto(JSON) |
| config.yaml 스키마 예시 | README:174-190 · CONFIGURATION:125-149 · STRATEGY_GUIDE:39-56 | 활성 8전략 실측 키 1벌 | 세 문서 세 스키마 |
| 테스트 실행법 | MODULES.md:211-216 · STRATEGY_GUIDE:339-349 · 루트 pyproject.toml:9-15 | CLAUDE.md 신설 절(또는 docs/DEVELOPMENT.md) | 둘 다 마커·워크트리 규칙 없음 |
| Signal 필드 | STRATEGY_GUIDE:249-261 · MODULES.md:98-100 | STRATEGY_GUIDE | 둘 다 entry_min/max_price 누락·tp/sl 사용 주장 |
| holding_period/exit_timeframe | STRATEGY_GUIDE:106-115,217,229 · CLAUDE.md:147-151 | STRATEGY_GUIDE 전문 + CLAUDE.md 포인터 | `"position"` 값 |
| Python 버전 | README:7 · CLAUDE.md:155(3.8) vs pyproject(3.9) | pyproject | 3.8 vs 3.9 |
| PID 파일명 | CLAUDE.md:173·instances/README:17(`robotrader.pid`/`robotrader_<id>.pid` ✓) vs run_robotrader.bat:69-71(`robotrader_template.pid` ✗) | main.py:68-76 | bat 이 죽은 이름 |
| 매수 마감 시각 | CONFIGURATION:117(12:00) vs market_hours.py:205(15:20) | 코드 | 12:00 vs 15:20 |
| 모니터링 주기 | DYNAMIC_RISK:329-330·DATA_MANAGEMENT:257(1분) vs position_monitor.py:66(3초) | 코드 | 1분 vs 3초 |
| 트레일링 스톱 | 추세기반 가이드(미배선 분석기) vs position_monitor(+5/-3, 비전략 포지션만) | TRADING_FLOW/신설 청산 체인 절 | 두 구현 |
| tp/sl 저장·복원·감시 | DYNAMIC_RISK §2/§6 · 추세기반 FAQ Q1 · 2026-07 §1 | 신설 청산 체인 절 | 없음(위치만 분산) |
| 데이터 소스 SSOT 서사 | CLAUDE.md:41-77 · PAPER_STRATEGIES §0.2 · constants.py:280-325 · DB통합 | DATABASE.md(현재 사실) + DB통합(역사) | 없음(중복만) |
| memory/ 위치 | superpowers/specs/2026-06-30:108(`memory/`) vs 레포 밖 실제 경로 | CLAUDE.md 신설 절 | 레포 안 vs 밖 |
| 시스템 모니터링 역할 | TRADING_FLOW L162 · SYSTEM_FLOW L60-62,271-286(메모리/CPU) vs bot/system_monitor.py | TRADING_FLOW | 감시 대상 |

## 4. docs/ 디렉토리 재배치안

### 4-1 분류표 (최상위 71 · 추적 50 / 미추적 21)

| 범주 | 파일 | tracked |
|---|---|---|
| canonical-dev(11) | ARCHITECTURE · CODE_MAP · CONFIGURATION · DATABASE · DATA_MANAGEMENT · DYNAMIC_RISK_MANAGEMENT · INVENTORY · OWNERSHIP_MODEL · STRATEGY_GUIDE · TRADING_FLOW · DB통합_쉬운설명 | 전부 T |
| strategy-hub(2) | PAPER_STRATEGIES · RS리더_쉬운설명 | T |
| prereg(13) | prereg_2026-08-25_d1close_tp_phantom · 08-25_n1_merge_reverse_split · 08-27_n1_correction_plan · 08-27_…_v1_rejected · 08-28_slot_cap_removal_api_budget · 08-31_corp_events_049470_fix · 09-03_write_path_rawprice_upsert · 09-11_daytrading_regime_auto · 09-14_fund_distress_warning · 09-14_news_disclosure_surge · 09-14_news_event_curve · 09-15_focus3_K_raise · 09-16_rsleader_exclusion_live | 전부 T |
| report(17) | report_2026-08-30_n1_53a(U) · 09-04(T) · 09-05_8strategies_august(U) · 09-05_tasso_post6(T) · 09-07/08/09/10/11_장마감(U) · 09-11_전략별(U) · 09-14_장마감(U) · 09-15_tasso_post7(T) · 09-15_장마감(T) · 09-16_장마감(T) · verdict_2026-09-10(T) · 전략요약_3전략_태쏘_2026-09-16(T) · 태쏘_분석_현황_2026-08-29(T) | 혼재 |
| plan/design(3) | plan_2026-09-05_focus3_roadmap(**U**) · plan_…_amendment_2026-09-15(T) · design_2026-09-10(T) | 혼재 |
| panel-explainer(13) | 3전략_고도화_계획_쉬운설명(U) · ma20_daytrade_3축(U) · ma20_daytrade_자문종합(U) · 뉴스분류(T) · 산업연쇄(T) · 섹터데이터(T) · 재무뉴스_전문가패널(T) · 재무뉴스_패널2차(T) · 재무수집기_머지결정(U) · 재무수치_적용방법(U) · 전문가자문_재무섹터(U) · 전략진단_쉬운설명(T) · 태쏘_전략분석_쉬운설명(T) | 혼재 |
| audit/review(6) | audit_2026-09-14(U) · review_2026-09-14(U) · ma20_진입룰_점검(U) · daytrade_진입밴드_조사(U) · 포지션사이징_결함(U) · 2026-07_전략고유청산(T) | 혼재 |
| todo/legacy(6) | TODO_2026-08-27(T) · N1_수리_로드맵(T) · quant_strategy_plan(T) · refactoring_2A_report(T) · PORTFOLIO_SNAPSHOT_GUIDE(T) · 추세기반_적응형_청산_가이드(T) | T |
| 하위 디렉토리 | code/MODULES.md(T) · reference/ 2(T) · archive/ 2(T) · audit_2026-08-23/ 7(**U**) · audit_2026-08-24/ 11(**U**) · superpowers/plans 46(T) · superpowers/specs 40(T) · `.omc/` 4곳 30파일(ignored) | — |

### 4-2 제안 트리

```
docs/
  README.md                ← 신설: 색인 + 명명·배치 규약 + 「동결 문서는 편집·이동 금지」
  ARCHITECTURE.md · CODE_MAP.md · CONFIGURATION.md · DATABASE.md · DATA_MANAGEMENT.md(또는 archive) · INVENTORY.md · OWNERSHIP_MODEL.md · STRATEGY_GUIDE.md · TRADING_FLOW.md
  PAPER_STRATEGIES.md · DB통합_쉬운설명.md · RS리더_쉬운설명.md · 전략진단_쉬운설명.md · TODO_2026-08-27.md
  prereg_*.md (13, 이동 금지)
  report_2026-09-05_tasso_post6_verdicts.md · report_2026-09-15_tasso_post7_verdicts.md · 태쏘_분석_현황_2026-08-29.md · 2026-07_전략고유청산_공백_재해석.md · N1_수리_로드맵_쉬운설명_2026-09-03.md (동결 문서가 인용 → 이동 금지)
  code/MODULES.md · superpowers/{plans,specs}/ (불변)
  plans/       ← plan_2026-09-05_focus3_roadmap.md + amendment + design_2026-09-10
  reports/2026-09/ ← 장마감 보고·전략별 성과·전략요약·verdict(조건부)
  panels/2026-09/  ← *_쉬운설명_2026-09-*.md
  audits/2026-08-23/ · audits/2026-08-24/ · audits/2026-09-14/
  archive/     ← 기존 2 + CHANGELOG_2026-02 + quant_strategy_plan + refactoring_2A + PORTFOLIO_SNAPSHOT_GUIDE + 추세기반 + DYNAMIC_RISK_MANAGEMENT + SYSTEM_FLOW + reference/
```

### 4-3 이동 목록과 각 이동이 깨뜨리는 참조 수

| 단계 | 이동 | 깨지는 참조(레포 안) | 비고 |
|---|---|---|---|
| (1) 안전 | report_2026-09-07/08/10/11/14/16_장마감 · report_2026-09-11_전략별 · 전략요약_3전략_태쏘 → `reports/2026-09/` | 0 | 메모리 dir 포인터(105줄/37파일, git 밖)만 별도 sed |
| (1) 안전 | 뉴스분류 · 산업연쇄 · 재무뉴스_전문가패널 · 재무뉴스_패널2차 · 재무수집기_머지결정 · 재무수치_적용방법 · 태쏘_전략분석 → `panels/2026-09/` | 0 | 미추적 2본은 먼저 git add |
| (1) 안전 | reference/*.md 2 → `archive/reference/` · quant_strategy_plan · refactoring_2A · PORTFOLIO_SNAPSHOT_GUIDE · 추세기반 · DYNAMIC_RISK_MANAGEMENT · CHANGELOG · SYSTEM_FLOW → `archive/`(DEPRECATED 배너) | 0 (단 CLAUDE.md:180,191 · README.md:250 · CHANGELOG.md:56 포인터 갱신) | SYSTEM_FLOW 는 TRADING_FLOW 병합 후 |
| (1) 안전 | audit_2026-08-23/ + audit_2026-08-24/ → `audits/` (같이) | 0 (내부 `../audit_2026-08-23/SUMMARY.md` 링크는 동반 이동 시 유지) | 18파일 미추적 → git add 선행 |
| (1) 안전 | `.omc/` 4곳(30파일) 삭제 | 0 | git 밖·ignored |
| (2) 포인터 재작성 | report_2026-09-09_장마감 | 2 (verdict_2026-09-10:43,174) | |
| (2) | report_2026-09-15_장마감 | 2 (amendment:33 `:337` 앵커 · K_raise) | 앵커는 이동엔 살고 편집엔 죽음 |
| (2) | report_2026-09-04 | 3 (plan_09-05 · report_09-05_aug · report_tasso_post6=동결 → 스텁 남기거나 보류) | |
| (2) | report_2026-09-05_8strategies_august | 3 (plan_09-05 · report_09-11_전략별) | 미추적 |
| (2) | report_2026-08-30_n1_53a | 3 (plan_09-05 · prereg_08-31 · prereg_09-03:273 — 둘 다 동결) | **보류 권장** |
| (2) | plan_2026-09-05_focus3_roadmap + amendment + design_2026-09-10 → `plans/` | 8+1 (3전략_쉬운설명:4,132 · K_raise:518 · specs/2026-09-11 · backtest/concept_axes/ma20/PREREG_PULLBACK_DEPTH_DURATION.md:4 — 동결 여부 확인 필요) | plan 본체 미추적 → git add 선행 |
| (2) | 섹터데이터_쉬운설명 · 전문가자문_재무섹터 · 3전략_고도화_계획_쉬운설명 → `panels/2026-09/` | 1 · 4(3 PREREG_FUNDAMENTAL_RANK + 1 spec) · 1(PULLBACK:123) | |
| (2) | audit_2026-09-14 · review_2026-09-14 → `audits/2026-09-14/` | 2(tests/test_live_min_fix_set_20260915.py:4 docstring · review) · 1(K_raise) | 테스트 docstring 수정은 코드 파일 → 사장님 결정 |
| (2) | ma20_진입룰_점검 · daytrade_진입밴드_조사 · 포지션사이징_결함 · ma20_daytrade_3축 · ma20_daytrade_자문종합 → `audits/2026-08-23/` | 5 · 2 · 5(SHADOW_LOG:71 + 4, 앵커 :21,:75) · 6 · 2 | backtest 측 파일은 md5 미동결 |
| 전체 접두사 이동 시 | prereg_ 전부 | 31줄/26파일 레포(운영 코드 14) + 37/17 docs 내부 + 97/28 메모리 | 하지 않음 |
| | report_ 전부 | 6/4 레포(전부 동결 태쏘 문서) + 21/10 내부 + 105/37 메모리 | 조건부 |
| | plan_ 전부 | 1 + 9/4 + 28/18 | |
| | 같은 폴더 상대링크 10건 | 3전략_쉬운설명:4,132→plan · prereg_09-03:699→verdict · news_disclosure_surge:34,151↔news_event_curve:29 · verdict:5,171→prereg_09-03 · verdict:43,174→report_09-09 | 한쪽만 옮기면 깨짐 |

총 포인터 약 335(레포 안 docs 밖 38). 이동 전 미추적 39본 git add 가 선행 조건(미추적 이동은 이력 없음).

### 4-4 🔴 옮기면 안 되는 것 (동결·md5·운영 코드 인용)

- **prereg_* 13본 전부** — 동결(커밋 SHA = 동결); prereg_2026-09-03 은 운영 코드 6곳(config/constants.py:20 · core/intraday/data_collector.py:106 · core/post_market_data_saver.py:9 · db/repositories/price.py:15,72 · utils/unified_data_loader.py:208)이 인용; prereg_2026-08-25_d1close 는 8 전략 strategy.py 주석이 인용; 09-14 3본은 backtest/concept_axes/REGISTRY.md:50-52 가 `../../docs/` 로 링크.
- **report_2026-09-15_tasso_post7_verdicts.md** — md5 동결 `backtest/tasso_program_journal/PREREG_POST8.md:6,29,888` 이 줄 앵커(:318,:324,:326-339)로 인용 → 이동·리플로 금지.
- **report_2026-09-05_tasso_post6_verdicts.md** — MANUAL_DOCS 등재 동결 문서(PREREG_GRADE_TIERS.md:7 · PREREG_ANCHOR_REDESIGN.md:103 · PREDECISION_2026-09-15_post7.md:319)가 인용.
- **태쏘_분석_현황_2026-08-29.md** — PREREG_RANKING.md:6,43 · PREREG_WEIGHTED_RECON.md:7,336,841,888 인용.
- **TODO_2026-08-27.md**(REGISTRY.md:275) · **전략진단_쉬운설명.md**(CLAUDE.md:183 · stop_path_minute/PREREG.md:6,54) · **N1_수리_로드맵**(prereg_09-03 동결 인용) · **2026-07_전략고유청산**(prereg_08-25 동결 인용).
- **PAPER_STRATEGIES.md**(33 외부 참조 · 8 README:3 · 줄 앵커 :33,:51,:115,:141-146) · **STRATEGY_GUIDE.md**(22 참조) · **code/MODULES.md** · **superpowers/plans·specs**(운영 코드 12곳+테스트 4곳 인용, `tools/gen_archive_candidates.py:11` 이 출력 경로 하드코딩).
- 동결 문서 안의 깨진 링크(prereg_2026-09-14 ×3 `../../docs/`, prereg_2026-09-03:699 등)는 **기록만** 하고 고치지 않는다.

## 5. 저장소 위생

| 항목 | 판정 | 근거 | 실행 명령(실행하지 않음) |
|---|---|---|---|
| `.claude/worktrees/agent-a4683dcffa7f47ad3 · a4c7791dc0d0139d5 · a575297939f0cbc5e · a9ff273f9dc02733b · af9ef98f034ef8ce0` | 안전삭제 | 5 브랜치 전부 main 조상(ahead 0), 2026-08-17, dirty 0, 63~74M | `git -C D:/GIT/kis-trading-template worktree remove <경로>` ×5 → `git branch -d worktree-agent-…` ×5 |
| `.claude/worktrees/minervini-tt-wiring` | 안전삭제(로컬) / 원격 삭제는 사장님 결정 | 머지됨(68b542f 08-18), dirty 0, 74M, origin 브랜치도 머지 | `git worktree remove …/minervini-tt-wiring && git branch -d worktree-minervini-tt-wiring` (`git push origin --delete …` 는 승인 후) |
| `D:/GIT/kis-template-wt-adjrepair` [test/adj-repair-cli] | 안전삭제 | 머지(1605e7e 08-20), dirty 0, 76M | `git worktree remove D:/GIT/kis-template-wt-adjrepair && git branch -d test/adj-repair-cli` |
| `D:/GIT/kis-template-wt-baseb` (detached 1cc7d73) | 안전삭제 | 조상 커밋, dirty 2(`_b.txt`,`_base.txt`), 74M | `git worktree remove --force D:/GIT/kis-template-wt-baseb` |
| `D:/GIT/kis-template-wt-breakout` [feat/breakout-axis-runner] | 안전삭제 | 머지(d5366b4 08-20), dirty 0, 75M | `git worktree remove … && git branch -d feat/breakout-axis-runner` |
| `D:/tmp/kis-wt-gate4` [fix/strategy-tpsl-delegate] | 안전삭제(한 번 훑기) | 머지(1810cd2 08-25), 77M, dirty 8 = pytest/probe 캡처 txt | `git worktree remove --force D:/tmp/kis-wt-gate4 && git branch -d fix/strategy-tpsl-delegate` |
| `D:/tmp/kis-wt-index-kis` [feat/index-kis-freshness] | 안전삭제 | 머지(5799508 09-10), dirty 0, 83M | `git worktree remove … && git branch -d feat/index-kis-freshness` |
| `D:/tmp/kis-wt-rsleader-excl` [feat/rsleader-corp-action-exclusion] | 안전삭제 | 머지(4a84a06 09-10), dirty 0, 85M | `git worktree remove … && git branch -d feat/rsleader-corp-action-exclusion` |
| `D:/tmp/kis-wt-tasso-p6s5` [fix/tasso-post6-s5-fixes] | 사장님 결정 | 머지됨이나 dirty 3 = `post_224401108114.{html,txt,_images.json}`(제3자 원문); D:\archive\tasso-program-journal-20260904\ 에 같은 post 보관 확인됨 | 보관 확인 후 `git worktree remove --force D:/tmp/kis-wt-tasso-p6s5 && git branch -d fix/tasso-post6-s5-fixes` |
| `D:/tmp/kis-wt-n1-53a` [fix/n1-volume-gate-p3ab] | 보존 | 미머지 1커밋(77fb2c8 08-30), origin 도 미머지 | — |
| `D:/tmp/wt-fund-pit` [feat/fundamental-risk-filter-pit] | 보존 | 미머지 43커밋, 240M, 메모리 「main 미병합」 | — |
| `D:/tmp/kis-wt-batch1-logs · kis-wt-fin-sce · kis-wt-fincollector · kis-wt-sector` | 안전삭제 | 워크트리 아님(`.git` 없음, `git worktree list` 미등록); txt 33개 · `.omc/` 만 · 빈 폴더 · `.omc/` 만 | `rm -rf D:/tmp/kis-wt-batch1-logs D:/tmp/kis-wt-fin-sce D:/tmp/kis-wt-fincollector D:/tmp/kis-wt-sector` |
| 머지된 로컬 브랜치 14(docs/minervini-concept-audit · docs/tasso-overview-0809 · feat/adj-repair · feat/financial-collector · feat/instrumentation-reject-log-benchmark · feat/minervini-tt-on · fix/daily-collector-universe · fix/financial-accounts-sce-pk · fix/rs-leader-entry-exit-overlap · fix/screener-provider-fail-closed · fix/stock-safety-info-supplier · fix/w1-insert-only-eprime · fix/wire-max-per-stock-amount · research/tasso-account-readings) | 사장님 결정 | 전부 main 에 머지, 워크트리 없음 | `git branch -d <이름>` |
| `RoboTrader_template/D:tmpmultiverseregime_gate_trackB{aziz,bellafiore,surge_fade}_run.log` | 안전삭제 | 백슬래시 벗겨진 경로명 파일 3개, 2026-06-02, 연구 로그, ignored(`*.log`) | Git Bash: `rm "D:/GIT/kis-trading-template/RoboTrader_template/D:tmpmultiverseregime_gate_trackBaziz_run.log"` 등 3건 |
| `RoboTrader_template/minervini_A_full.log · minervini_B_full.log` | 안전삭제 | 1,300B 씩, 2026-05-29, ignored | `rm …/minervini_A_full.log …/minervini_B_full.log` |
| `RoboTrader_template/.coverage · htmlcov/`(196파일 18M) | 안전삭제 | 2026-03-02, ignored | `rm -rf …/.coverage …/htmlcov` |
| 루트 `test_output.txt · test_output2.txt` | 안전삭제 | 2026-02-12 동일 pytest 요약, ignored | `rm D:/GIT/kis-trading-template/test_output*.txt` |
| 루트 `.pytest_cache/` · `RoboTrader_template/.pytest_cache/` | 안전삭제 | ignored, 재생성됨 | `rm -rf …/.pytest_cache` ×2 |
| `RoboTrader_template/venv_broken_quantcopy/`(12,265파일 278M) | 안전삭제 | ignored, 0 추적, 라이브 프로세스(PID 35288)는 `venv\Scripts\python.exe` 사용 | `rm -rf …/venv_broken_quantcopy` |
| 중첩 `.omc/` 52곳(docs/ 4곳 포함) | 안전삭제(단 `./.omc`, `RoboTrader_template/.omc`, `RoboTrader_template/logs/.omc` 제외) | 전부 ignored, 0 추적, 에이전트 cwd 별 상태 파일 | `find . -mindepth 2 -type d -name .omc -not -path './RoboTrader_template/.omc' -not -path '*/venv*' -not -path './.claude/*' -not -path '*/logs/*' -print` 확인 후 `-exec rm -rf {} +` |
| 루트 `.claude/settings.local.json.bak.20260908` | 안전삭제 | 09-08 훅 추가 전 백업, diff = hooks 블록 14줄만 | `rm D:/GIT/kis-trading-template/.claude/settings.local.json.bak.20260908` |
| `RoboTrader_template/charts/` | 안전삭제 | 빈 폴더, ignored | `rmdir …/charts` |
| `RoboTrader_template/output/` 73 ignored 파일 | 안전삭제(ignored 만) / 추적 2본 이동은 사장님 결정 | `multiverse_dashboard.py` 는 tests/test_multiverse_dashboard.py:126 가 import(추적, 219680d) | `git clean -ndX RoboTrader_template/output` 확인 후 `-fdX` |
| 루트 `start_claude_OLD_kis.bat` | 사장님 결정(추적 파일) | 87B 개인 런처, 참조 0 | `git rm start_claude_OLD_kis.bat` + 커밋 |
| 루트 `token_info.json` | 사장님 결정 | 2026-05-31, ignored, 사용처 미확인 / `RoboTrader_template/token_info.json` 은 라이브 토큰 캐시 → 보존 | 확인 후 `rm D:/GIT/kis-trading-template/token_info.json` |
| `RoboTrader_template/memory/`(50파일 추적) | 사장님 결정(git mv) | 클로드 메모리와 겹치는 파일 1/50; 49본은 고유 원본; reports/books_research/index.md:595,611,679,703 이 링크 | `git mv RoboTrader_template/memory RoboTrader_template/docs/archive/memory-2026-05` + 링크 4곳 수정 + 커밋 |
| 루트 `cache/`(161파일 2.4M) · 루트 `logs/`(34파일 26M) | 사장님 결정 | 루트에서 실행한 흔적, ignored; 라이브 `RoboTrader_template/{cache,logs}` 는 별개(보존) | `rm -rf D:/GIT/kis-trading-template/cache D:/GIT/kis-trading-template/logs` |
| 루트 `scratchpad/`(175파일, **미ignore**) | ignore 추가 = 사장님 결정(커밋) / 내용 삭제 = 사장님 결정 | `git status` 209건 중 약 160건이 여기 | 루트 `.gitignore` 에 `scratchpad/` 추가 후 커밋 |
| 루트 `agents/`(11파일) | 사장님 결정 | 2026-02-04 레거시 역할 프롬프트, ignored | `rm -rf D:/GIT/kis-trading-template/agents` |
| 루트 `.superpowers/`(추적 2 / 79) | 사장님 결정 | .gitignore:54 와 추적 2본 모순 | `git rm --cached .superpowers/sdd/progress.md .superpowers/sdd/walkforward-preregistration.md` 또는 ignore 줄 삭제 |
| `docs/` 미추적 39본(최상위 21 + audit 18) | 사장님 결정(커밋) | plan_2026-09-05·audit_2026-08-2x·전문가자문 등은 추적 문서가 인용 | `git add RoboTrader_template/docs/plan_2026-09-05_focus3_roadmap.md RoboTrader_template/docs/audit_2026-08-23 RoboTrader_template/docs/audit_2026-08-24 …` + 커밋 |
| `backtest/tasso_program_journal/post_224385784257·224393392105·224409404744.{html,txt,_images.json}` 9본 | 사장님 결정(우선) | 미추적·**미ignore**(규칙은 없는 `raw/` 만); D:/archive/tasso-program-journal-20260822/-20260829/-20260915 사본과 md5 동일 | `rm` 9본 + `RoboTrader_template/.gitignore` 에 `backtest/tasso_program_journal/post_*.html` `post_*.txt` `post_*_images.json` 추가(커밋); post8 수집 전 필수 |
| `backtest/concept_axes/rs_leader/PREREG_PREVDAY_CRASH_GUARD.md` | 사장님 결정 | 09-11 미추적 사전등록(동결 = 커밋) | `git add …` + 커밋, 또는 삭제 |
| `RoboTrader_template/reports/` ignored 145(parquet·log 약 300M) | 사장님 결정 | 추적 533본은 운영 docstring 이 인용 → 보존; 재생성 가능 여부 미확인 | `git clean -ndX RoboTrader_template/reports` 확인 후 |
| `.claude/settings.local.json`(루트, 훅 있음) · `RoboTrader_template/.claude/settings.local.json`(02-02, 훅 없음) | 보존 / 통합은 사장님 결정 | 어느 것이 로드되는지 미확인 | — |

## 6. 실행 순서 제안

공통 규칙: 코드·bat·.py docstring·테스트 파일은 건드리지 않는다(별건 목록 §6-끝). 문서 편집은 워크트리(`D:/tmp/kis-wt-docs-cleanup`) 또는 15:30 이후 라이브 트리에서 하되 브랜치 전환은 장중 금지. 봇 가동 중 pytest·스모크 실행 금지(문서 작업엔 불필요). 모든 커밋·푸시·추적 파일 삭제는 사장님 확인.

| 묶음 | 무엇을 | 위험 | 승인 필요 |
|---|---|---|---|
| **A. 「따라 하면 망가지는」 high 결함 봉합** | `CLAUDE.md` 재작성(§1-3·§1-4) + 루트 `CLAUDE.md` 신설(§1-5) + 프레임워크/루트 `README.md` 재작성 + `docs/CONFIGURATION.md` 재작성 + `instances/README.md` 재작성 + `.env.example` 값 3개·6줄 인라인 주석 정정 | 낮음(문서만). `.env.example` 은 템플릿이라 라이브 `.env` 무영향 | 커밋 시 ✓ · `.env.example` 은 설정 파일이므로 사장님 확인 |
| **B. 흐름·전략 문서 통합** | `docs/TRADING_FLOW.md` 재작성(main.py@dbf999f 기준; SYSTEM_FLOW §3 타임라인·Q4·Q5 흡수·swing skip·재시도·라운드로빈·청산 체인) → `SYSTEM_FLOW.md` archive → `ARCHITECTURE.md` 모듈 목록 이전+포인터 → `docs/STRATEGY_GUIDE.md` 재작성(§3 골격 유지; strategies[]·screener/adapter·exit_timeframe·registration test) → `strategies/sample/README.md` 갱신 | 낮음; SYSTEM_FLOW 인바운드 4곳(CLAUDE.md:180 · README.md:250 · CHANGELOG.md:56 · audit_2026-08-23/…:281,321 역사) 갱신 | 커밋 시 ✓ |
| **C. DB 문서 3종** | `docs/DATABASE.md` 재작성(kis_template 연결·두 env 풀·resolver·표 인벤토리 소유자별·DDL 위치·은퇴 DB명·adj_factor·source) → `docs/DATA_MANAGEMENT.md` 짧게 재작성(EOD 수집 13단계·시각·복원 포인터) 또는 archive → `docs/DB통합_쉬운설명.md` 상태 박스 | 낮음; 값은 감사 실측(psql 읽기 전용)만 사용 | 커밋 시 ✓ |
| **D. 보관** | `docs/archive/` 로: CHANGELOG(헤더 2줄) · DYNAMIC_RISK_MANAGEMENT · PORTFOLIO_SNAPSHOT_GUIDE · 추세기반 · quant_strategy_plan · refactoring_2A_report · reference/ 2 (DEPRECATED 배너) + CLAUDE.md:191·README 포인터 제거 + `docs/code/MODULES.md` 에 「core/trend_momentum_analyzer.py 미배선」 1줄 | 낮음(인바운드 0 확인됨) | 커밋 시 ✓ |
| **E. 코드 지도·인벤토리·모듈 표 재생성** | 워크트리에서 `PYTHONUTF8=1 venv/Scripts/python -B tools/gen_inventory.py > <임시>` 성공 후 `docs/INVENTORY.md` 로 이동(인플레이스 리다이렉트 금지) · `docs/CODE_MAP.md` 갱신(엣지 1건 명시·lib/ 연구·market_dashboard·config/·main.py 분류·:46 명령을 `grep -v '/tests/'` 류로 교체·재생성 명령에 PYTHONUTF8·:16-18 줄번호·_adjacent_grid·매일_분석_실행.bat 결함) · `docs/code/MODULES.md` 표를 `ls`+`grep -n '^class '` 로 재생성 + collectors/signals/tools/runners 절 + pytest 마커·라이브 트리 경고 | 중간: 도구 실행은 읽기 전용이나 봇 트리에서 `__pycache__` 생성 가능 → 워크트리·`-B` 필수 | 엣지 1건 처리(승격 vs 예외 등록) = 사장님 결정 · 커밋 ✓ |
| **F. 전략 허브·부속 갱신** | `docs/PAPER_STRATEGIES.md`(daytrading auto·minervini TT on·사이징 복리/캡·max_capital_pct 실상·스냅샷 20/소비 10·§0.2 축약·헤더 날짜) · 4 README(daytrading·minervini·ma20·rs_leader) · `OWNERSHIP_MODEL.md` P1-2 후기·줄번호 · `2026-07_…` 후기 · `TODO_2026-08-27.md`·`N1_…:42` 머지 완료 | 낮음; K 상향(5/3/5→10/10/6, 09-18 07:40 발효)은 「예정」으로만 적고 현재값으로 쓰지 말 것 | 커밋 시 ✓ |
| **G. docs/ 재배치** | 순서: (G1) 미추적 39본 git add → (G2) §4-3 (1) 안전 이동 + `.omc/` 삭제 + `docs/README.md` 신설 → (G3) §4-3 (2) 포인터 재작성 동반 이동(동결 문서를 건드려야 하는 이동은 보류) → (G4) 메모리 dir 포인터 일괄 sed(git 밖) | 중간: 링크 파손. §4-4 목록은 절대 이동 금지 | G1·G3 은 사장님 결정 · 커밋 ✓ |
| **H. 저장소 위생** | §5 「안전삭제」 행부터(워크트리 12 · 잔재 파일 · venv_broken_quantcopy · .omc 중첩 · 캐시류) → 「사장님 결정」 행은 개별 승인 → 태쏘 post_* 9본은 post8 수집(9/19~20) 전에 처리 | 낮음~중간: `git worktree remove` 사용(rm -rf 금지), `--force` 는 dirty 로 명시된 곳만, `git clean -X`(대문자)만, 라이브 트리에서 `-x/-d` 금지 | 삭제 명령 실행 자체가 사장님 확인 대상 |

범위 밖 — 코드·설정 파일 수정이 필요한 별건(문서 계획에서 제외, 사장님 결정): `run_robotrader.bat:69-71` 죽은 PID 검사 · `config/env_bootstrap.py:7-8`·`api/kis_auth.py:15`·`strategies/base.py:29,273`·`bot/system_monitor.py:93`·`minervini screener.py:37-38`·`bot/state_restorer.py:805-807`·`rs_leader/config.yaml:21`·`db/database_manager.py:261` stale 주석 · `db/config.py` 죽은 코드(port 5432) · `매일_분석_실행.bat:13,18` 없는 파일 호출 · `tools/paper_strategy_equity.py:258` 엣지 승격 · `tools/gen_inventory.py:15` lib/ 분류 · `pyproject.toml:6` ruff 제외 목록 · `docker-compose.yml`(POSTGRES_DB robotrader/5432) · `init-scripts/02-06` 헤더 `-d robotrader` · `requirements.txt` 에 pytest/ruff 없음 · `RoboTrader_template/.gitignore` 태쏘 규칙·루트 `.gitignore` scratchpad/ · `.omc-workspace` 마커 부재 · `on_market_open/close` 단일 전략 dispatch(main.py:246-263) 코드 갭 후보.

## 부록 A. 미확정 항목 (검증 안 됨 · 사실로 쓰지 말 것)

- CLAUDE.md:34-35 커밋 서사(`d89d0b6`·`726febf`·`kospi200_pit`) · :72 해시 `e321580b…` · :73 「4,350행 중 non-NULL 1,287행」(컬럼 존재만 확인) · :59 「2026-07-16 통일」.
- 루트 README:38 RoboTrader 「운영 중」 실제 프로세스 상태 · Python 3.8 로 실제 import 가능 여부 · CHANGELOG 역사적 테스트 수.
- `tests/dryrun/run_dryrun.py` 가 실 DB 에 쓰는지(로그 오염 경로는 확인됨) · `api/kis_auth.py` Rate Limiting 이 카운터 이상인지 · SYSTEM_FLOW L252-253 [2/5] 내부 · L296-307 재무 피드·표 목록 · 퀀트 「예시」 블록(가설로 표기됨).
- STRATEGY_GUIDE pytest rootdir 자동 적용(실행 안 함) · on_market_open/close 단일 dispatch 가 의도인지 · `duplicate_signal_prevention`·`candidate_filters` 소비처 · `.gitignore:3` `token_info_config.json` 주석 출처 · CONFIGURATION.md:48 localhost vs 127.0.0.1.
- 오늘 런타임 `RS_LEADER_CORP_ACTION_MODE` 값(.env 미열람) · PAPER_STRATEGIES §0.7 646/17/3% · deep_mr 「월 18.9회」 · hub:43 「~85봉」 vs README 「82봉」 · minervini README `candidate.py:134`(실제 :133).
- DB통합 L23-24 동결일 · L148-155 수치(50,953 키·538행·7GB/5.2GB) · §7 뉴스 표·L193/L244 · L52-56 · DATA_MANAGEMENT L44 「리밸런싱 09:05」.
- PORTFOLIO_SNAPSHOT:126 「KIS API 일 20,000회」 · 추세기반 :216-225 성과표 · 2026-07 가설 A 측정 여부(prereg_08-25:268 이 범위 밖으로 명시) · `bot/position_sync.py` 배선(main.py:130/687).
- `매일_분석_실행.bat` 대상 파일 의도 · `market_dashboard` import 가 라이브에서 실행되는지(플래그 미추적) · ruff 미실행 · Claude Code 가 어느 `settings.local.json` 을 로드하는지 · 루트 `token_info.json` 사용처 · `reports/` parquet 재생성 가능성 · kis-wt-gate4 pytest_*.txt 필요성 · `Co-Authored-By` 트레일러 출처(관찰: 최근 100 커밋 중 99).
- 줄 앵커 PAPER_STRATEGIES.md:33,115,141-146(audit_2026-08-2x 인용) 생존 여부 · CLAUDE.md:183 「8전략은 왜 마이너스인가」 제목 시점.

## 부록 B. 반박된 항목 (제외 · 왜 틀렸는지)

| 항목 | 이유 |
|---|---|
| STRATEGY_GUIDE:293,341-348 테스트 규약이 낡았다 | 평면 `tests/test_<name>.py` 도 현행 규약이고 루트 pyproject 마커는 자동 적용; `tests/strategies/<name>/test_registration.py` 패턴은 rs_leader·deep_mr_dev20 2개뿐 |
| .env.example:5 암호가 인증 실패한다 | loopback 5433 은 사실상 trust — 아무 암호나 통과; `1234` 와의 차이는 미용 불일치일 뿐(§3 표에 모순으로만 기재) |
| DATA_MANAGEMENT:195 「08:55 퀀트 스크리닝」 | 절 상단(:189-191)이 「퀀트 전략 구현 시 참고·기본 템플릿에 없음」이라 명시한 가설 스펙 |
| DB통합:162 「8/18 재기동 확인」 | 날짜 박힌 계획 단계이지 현재 상태 주장이 아님 |
| DB통합:134-139 「기관·개인 전부 비어 있음」 | `robotrader_backtest.investor_flow` 에 대한 서술이며 실측(institution/individual 0) 참 |
| DB통합:25 「뉴스 18만 건」 | 「원래 어떤 상태였나」 절의 과거 시점 표; kis_template.news 218,704 는 다른 DB·시점 |
| 2026-07_전략고유청산:93 `position_monitor.py:359` 분기 | 지금도 :359 에 있고 8/8 전략이 None 반환 — 「삭제 예정」은 계획 |
| PAPER_STRATEGIES:118-122 regime_index 표 | 의미·소스 정의이며 참(auto 도 같은 KIS 지수 검사); `auto`/`both` 는 누락일 뿐 모순 아님 |
| PAPER_STRATEGIES:114 `main.py::_allocate_strategy_capital` | 심볼 실재(main.py:208-210 위임) — 「bot/initializer.py:437 구현」 1줄 부기로 충분 |
