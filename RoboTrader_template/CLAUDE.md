# CLAUDE.md — AI 개발 협업 가이드 (라우터)

> Claude(AI 개발자)가 이 프로젝트에 컨텍스트를 잡기 위한 **얇은 라우터**. 매 세션 자동 주입되므로 규칙과 링크만 둔다.
> 링크 끝 문서가 정본이고, 문서와 코드가 어긋나면 **코드가 맞다**. 문서 색인은 [docs/README.md](docs/README.md).

## 프로젝트 개요

**kis-template**(코드 폴더 `RoboTrader_template/`) — 한국투자증권(KIS) API 기반 자동매매 프레임워크. 공통 인프라(API·주문·DB·텔레그램)는 프레임워크가 맡고 개발자는 **전략만 작성**한다. 지금은 **페이퍼 8전략을 라이브로 운영 중**(`config/trading_config.json` `paper_trading: true`). 레포 루트(git 루트, 한 단계 위)에서 라이브 코드는 `RoboTrader_template/` 아래뿐이다 — 루트엔 그 밖에 `pyproject.toml`·`README.md`·연구 잔재(`scripts/` 3파일 · `docs/superpowers/` 11)·`.github/` 가 있고 [루트 CLAUDE.md](../CLAUDE.md) 가 설명한다. 형제 레포(`D:/GIT/RoboTrader`·`_orb`·`_quant`)는 별도 저장소이며 이 트리 안에 없다.

## 🧭 운영 vs 연구 코드 라우팅 (에이전트 필독)

정본 = [docs/CODE_MAP.md](docs/CODE_MAP.md). **운영 동작을 찾을 때 연구 디렉토리를 근거로 삼지 말 것.**

- **운영(production)**: `main.py` `config/` `core/` `bot/` `framework/` `api/` `strategies/` `collectors/` `db/` `runners/` `signals/` `utils/` `tools/` `market_dashboard/`
- **연구/일회성(라이브 아님)**: `scripts/` `multiverse/` `backtest/` `lib/` `books/` `council/` `archive/` — 검색 후순위. `lib/` 는 2026-07-10 연구/테스트 지원으로 재분류(운영 import 0). `archive/` 는 무참조 확정분(검색 제외). 연구 분류 ≠ git 미추적(연구 코드도 전부 추적) — 범용 ignore 패턴(`lib/`·`data/`)이 자체 패키지를 삼킨 전례가 있다(`.gitignore` 주석).
- 🔴 **라이브→연구 엣지 1건**: `tools/paper_strategy_equity.py` `_ensure_table()` 이 `scripts.kis_db.schema` 를 import(EOD 경로, `bot/system_monitor.py` 가 호출). 승격 또는 예외 등록 결정 대기. 드리프트 점검 명령 → CODE_MAP.md §검증 · 파일별 태깅 → [docs/INVENTORY.md](docs/INVENTORY.md).
- `strategies/books/`(책 룰 패키지 19)는 라이브 6전략이 정적 import 하는 **운영 의존** — archive 금지. `strategies/intraday/`(11)·`allocation/`(1)은 운영 import 0. 셋 다 `StrategyLoader` 로드 대상은 아니다.

## 🗄️ 데이터 소스 SSOT (에이전트 필독)

가격·시장참조 데이터는 라이브·연구 모두 **`kis_template` 단일 DB**. DB명 하드코딩 금지, `config/constants.py` resolver 경유:
`resolve_daily_source_db()`(daily_prices) · `resolve_minute_source_db()`(minute_candles) · `resolve_corp_events_source_db()`(corp_events) — 셋 다 상수 `"kis_template"` 를 돌려준다.

- 🔴 **롤백 스위치는 «없다»**(2026-08-17 폐지): `KIS_DATA_SOURCE`·`QUANT_DB`·`MINUTE_DB`·`CORP_EVENTS_DB` 는 설정해도 무시된다(`tests/test_research_data_source.py` 가 회귀 고정). 새 env 로 되살리지 말 것. 레거시 DB 는 `robotrader_retired_20260817`(접속 차단)로 은퇴.
- 수동 백필 스크립트의 **«쓰기»만** `require_explicit_target_db()` 로 `TIMESCALE_DB` 필수(미지정 시 중단). **«읽기»는 resolver.** 같은 스크립트 안에서도 읽기·쓰기 연결을 가른다.
- ⚠️ 가격(`open/high/low/close`)에 `adj_factor` 를 곱하지 말 것 — 이미 분할조정된 값이다. 🔑 `volume` 은 원본 저장이라 읽기 계층(`db/repositories/price.py`·`db/quant_daily_reader.py`)이 곱해 준다 — 소비자가 다시 곱하면 이중조정. 기계검사 `tests/test_adj_factor_no_arithmetic.py` · `tests/test_adj_factor_volume_units.py`.
- 재무도 `kis_template`(2026-08-16 이관). 재무 롤백은 가격과 분리된 `QUANT_FINANCIAL_DB`(`multiverse/data/pit_reader.py`) 하나. 일봉은 `daily_prices` — `kis_template` 에 `daily_candles` 표는 없다(이관 원본 `strategy_analysis` 쪽 이름 · `strategies/historical_data.py` 의 `get_daily_candles_range()` 는 함수명만 남고 SQL 은 `daily_prices` 를 읽으며, 운영 디렉토리 안 호출자는 비활성 lynch/sample/sawkami screener 뿐). 환경변수 전수·표 인벤토리·은퇴 DB → [docs/DATABASE.md](docs/DATABASE.md) · 통합 경위 → [docs/DB통합_쉬운설명.md](docs/DB통합_쉬운설명.md).

## 아키텍처 · 데이터 흐름

레이어 그림 정본 = [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)(strategies → bot → framework → api → core → 인프라). 모듈별 표 = [docs/code/MODULES.md](docs/code/MODULES.md) · 런타임 흐름·하루 타임라인·매도 체인 = [docs/TRADING_FLOW.md](docs/TRADING_FLOW.md).

```
[기본 경로] main._main_trading_loop → 전략 on_tick(ctx: TradingContext) 라운드로빈(≈9초마다 한 전략)
  → generate_signal() → Signal → ctx.buy() / ctx.sell()  (서킷브레이커·시장방향 가드 내장)
  → TradingDecisionEngine 판단 → OrderManager 주문(KIS API · 페이퍼는 VirtualTradingManager)
  → 체결 → 전략 on_order_filled 콜백 → DB 저장 + 텔레그램
```

## 전략 시스템

### 활성 페이퍼 전략 8종 — SSOT = `config/trading_config.json` `strategies[]`

항목 = `{name, enabled, max_capital_pct, regime_index, regime_gate}` · K(`max_positions`)·손절·익절은 각 `strategies/<name>/config.yaml`. 운영 허브 = [docs/PAPER_STRATEGIES.md](docs/PAPER_STRATEGIES.md).

| # | 전략 (폴더키) | 성격 | 상세 |
|---|---|---|---|
| 1 | `elder_ema_pullback` | 추세추종 | [README](strategies/elder_ema_pullback/README.md) |
| 2 | `book_envelope_200d` | 돌파 모멘텀 | [README](strategies/book_envelope_200d/README.md) |
| 3 | `daytrading_3methods_breakout` | 돌파 | [README](strategies/daytrading_3methods_breakout/README.md) |
| 4 | `minervini_volume_dryup` | 매집/dry-up | [README](strategies/minervini_volume_dryup/README.md) |
| 5 | `book_pullback_ma20` | 눌림목 (MA20) | [README](strategies/book_pullback_ma20/README.md) |
| 6 | `book_pullback_ma5` | 눌림목 (MA5) | [README](strategies/book_pullback_ma5/README.md) |
| 7 | `rs_leader` | RS 리더 | [README](strategies/rs_leader/README.md) |
| 8 | `deep_mr_dev20` | 평균회귀 | [README](strategies/deep_mr_dev20/README.md) |

- 🎯 2026-09-05 부터 **집중 3전략** = `book_pullback_ma20`·`minervini_volume_dryup`·`daytrading_3methods_breakout`, 나머지 5는 관측만 → [docs/plan_2026-09-05_focus3_roadmap.md](docs/plan_2026-09-05_focus3_roadmap.md).
- ⏰ K 상향(ma20 5→10 · daytrading 5→10 · minervini 3→6)은 **2026-09-18 07:40 발효 예정** — 오늘 `config.yaml` 은 5/3/5 → [prereg](docs/prereg_2026-09-15_focus3_K_raise.md).
- 🛡 `RS_LEADER_CORP_ACTION_MODE=live` 2026-09-17 07:40 발효(`.env` 한 줄 · 코드 기본값은 `shadow`) → [prereg](docs/prereg_2026-09-16_rsleader_exclusion_live.md).
- 비활성 패키지: `sample`·`momentum`·`mean_reversion`·`volume_breakout`·`bb_reversion`·`bb_reversion_or`·`lynch`·`sawkami` + 하위 `books/`·`intraday/`·`allocation/` → [MODULES.md](docs/code/MODULES.md).

**새 전략 추가** → [docs/STRATEGY_GUIDE.md](docs/STRATEGY_GUIDE.md). 핵심만:
- 로드 = `strategies/<name>/strategy.py` 의 `*Strategy` 클래스(`StrategyLoader` 가 `strategies.<name>.strategy` 를 import) + `trading_config.json strategies[]` 등록. 폴더 복사만으로는 로드되지 않는다.
- 후보는 자기 전략의 `screener.py` 스냅샷에서만 온다 — `runners/_adapter_factory.py` if/elif 에 등록이 없으면 후보 0.
- `holding_period = "swing"` 이면 EOD 일괄청산을 건너뛴다(라이브 8/8 swing). `exit_timeframe` 미설정 시 자동 유도(swing→`"daily"`, intraday→`"intraday"`); swing + `"intraday"` 조합은 `BaseStrategy.__init__` 이 거부.

## 개발 시작 가이드 (2026-09-17 코드 실측)

- **코드 루트** `RoboTrader_template/`(git 루트는 한 단계 위). Python **3.9+**(루트 `pyproject.toml` `requires-python` · CI 3.9/3.11/3.12). venv = `RoboTrader_template/venv`(미추적).
- **봇 기동** = Windows 작업 스케줄러 `\RoboTrader_AutoStart`(월~금 07:40) → `D:\GIT\run_all_robotraders.bat` → `run_robotrader.bat`(venv 활성화 → `pip install -r requirements.txt` → `config\key.ini` 없으면 중단 → `SCREENER_SNAPSHOT_ENABLED=true` → `python -X utf8 main.py`, stdout/stderr 를 `logs/robotrader_template_*.log` 로 캡처). `python main.py` 직접 실행은 `bot/env_guard.py` 가 프로젝트 venv 가 아니면 exit 1(`ALLOW_FOREIGN_VENV=1` 은 경고만). `main.py` 에 argparse 없음.
- **실전 인스턴스** `run_instance.bat <id>` = `KIS_INSTANCE_DIR=instances\<id>` → key.ini·trading_config.json·`robotrader_<id>.pid`·`token_info_<id>.json`·`logs/<id>/`·`real_trading_<id>` 분리, `SCREENER_SNAPSHOT_ENABLED=false`(스냅샷 소비 전용). 실전 모드는 `real_total_funds_cap` 미설정 시 `LiveStartupAbort`(`bot/initializer.py`). 페이퍼 기본 PID = `robotrader.pid`(`main.pid_file_name`). → [instances/README.md](instances/README.md)
- **설정 파일**: KIS 키·`[TELEGRAM]` = `config/key.ini`(`key.ini.example` 복사 · `config/settings.py` 가 읽음) — **`.env` 가 아니다**. 거래·전략 = `config/trading_config.json`. `.env`(RoboTrader_template 루트 · 선택)는 `config/env_bootstrap.py` 가 읽어 `os.environ` 에 넣되 이미 있는 OS env 는 덮지 않고 **인라인 `#` 주석이 값에 포함**된다(python-dotenv 아님). `VIRTUAL_MODE` 같은 env 는 없다 — 페이퍼/실전 스위치는 `trading_config.json` `paper_trading`. → [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- **DB**: PostgreSQL 16 + TimescaleDB · **port 5433** · DB `kis_template` · user `robotrader` = `db/connection.py` 기본값(`.env` 없이도 접속). 컬렉터 등은 두 번째 풀 `KIS_DB_*`(`db/kis_db_connection.py`, 기본값 동일). 운영 env: `TIMESCALE_*` · `KIS_DB_*` · `KIS_INSTANCE_DIR` · `SCREENER_SNAPSHOT_ENABLED` · `SECTOR_NEWS_BOOST_MODE` · `RS_LEADER_CORP_ACTION_MODE`(off|shadow|live · 기본 shadow) · `OPENDART_API_KEY` · `CORP_ACTION_QUEUE_PATH` · `LOG_LEVEL` · `ALLOW_FOREIGN_VENV` → 전수표 [docs/DATABASE.md §2](docs/DATABASE.md).
- **로그** `logs/` 두 갈래: ① `trading_YYYYMMDD.log` = `utils/logger.py` RotatingFileHandler(10MB×7 · pytest 중엔 `test_trading_` 접두사) ② `robotrader_template_YYYYMMDD_HHMMSS.log` = bat 의 콘솔 캡처(①의 상위집합 · 블록 버퍼링이라 가동 중 0바이트로 보일 수 있음). `tests/dryrun/run_dryrun.py` 같은 스크립트 직접 실행은 접두사 없이 ①에 섞인다.
- **테스트**: 설정은 **레포 루트 `pyproject.toml`**(`testpaths=RoboTrader_template/tests` · `asyncio_mode=auto` · 마커 `slow`·`db`). `cd RoboTrader_template && <python> -m pytest tests -q -m "not db"`. 🔴 **라이브 트리(`D:/GIT/kis-trading-template`)에서 pytest·`tests/healthcheck`·`tests/dryrun`·`scripts/kis_db/smoke_state_restore.py` 실행 금지 · 장중 브랜치 전환 금지** — 작업은 `git worktree add D:/tmp/kis-wt-<topic> -b <type>/<topic>`(워크트리엔 venv 없음 → [MODULES.md 테스트 절](docs/code/MODULES.md)). 봇 가동 중 머지의 발효일 = 다음 07:40 재기동. 회귀 판정 = 실패 «집합» 양방향 차분. **lint** = `ruff check .`(`RoboTrader_template/pyproject.toml` · E9/F63/F7/F82 · line-length 120 · py39 · `scripts multiverse books council archive venv*` 제외 — `backtest/`·`lib/` 는 제외 목록에 없음).
- **git**: 커밋 `type(scope): 한국어 요약` · 브랜치 `feat/ fix/ docs/ research/` · 머지 `--no-ff` · **커밋/푸시/추적 파일 삭제는 사장님 확인**. 귀속 확인 `gh api repos/<o>/<r>/commits/<sha> --jq .author.login`(null 이면 미귀속).
- **문서 위치·이름** → [docs/README.md](docs/README.md). 세션 메모리·changelog 는 **레포 밖** Claude Code 프로젝트 메모리에 있다(git 에 없음). 레포 안 `RoboTrader_template/memory/`(50파일 · 2026-06-03 이후 미갱신)는 그 시기 고유 원본 — 삭제·참조 금지.

## 개발 규칙 & 컨벤션

- 비동기 `asyncio` · 블로킹 API 호출은 `ThreadPoolExecutor`(`framework/executor.py`) · 로깅 `utils.logger.setup_logger(__name__)` · 시간 `utils.korean_time.now_kst()`.
- 패턴: **Facade** `core/order_manager.py` = `core/orders/` 믹스인 조립(`OrderExecutorMixin`·`OrderMonitorMixin`·`OrderTimeoutMixin`·`OrderDBHandlerMixin`) · **Strategy** `BaseStrategy` + `StrategyLoader` 동적 로딩 · **Repository** `db/repositories/`.
- 네이밍: 모듈 `snake_case.py` / 클래스 `PascalCase` / 상수 `UPPER_SNAKE_CASE`(`config/constants.py`) / 전략 폴더 `snake_case` · 전략 클래스명은 `Strategy` 접미 필수.

## 문서 지도

| 문서 | 내용 |
|------|------|
| [README.md](README.md) | 프로젝트 소개·빠른 시작 |
| [docs/README.md](docs/README.md) | **docs/ 색인** — 정본 목록·하위 폴더·명명 규약·동결 문서 |
| [docs/code/MODULES.md](docs/code/MODULES.md) | 코드 모듈별 상세(main.py·framework·strategies·core·bot·collectors·db·utils·테스트) |
| [docs/PAPER_STRATEGIES.md](docs/PAPER_STRATEGIES.md) | 활성 8전략 운영 허브(한눈표·자본/regime·집중 3전략) |
| `strategies/{name}/README.md` | 전략별 상세(활성 8전략) |
| [docs/STRATEGY_GUIDE.md](docs/STRATEGY_GUIDE.md) | 전략 추가 가이드(Step·어댑터 등록·테스트) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 레이어 그림(정본)·조립 관계·의존성 |
| [docs/TRADING_FLOW.md](docs/TRADING_FLOW.md) | 런타임 흐름(기동→루프→하루 타임라인→매수/매도 체인) |
| [docs/OWNERSHIP_MODEL.md](docs/OWNERSHIP_MODEL.md) | 전략 소유권 모델(폴더키/클래스명 2종 신원·실주문 게이트) |
| [docs/DATABASE.md](docs/DATABASE.md) | 접속·환경변수 전수·표 인벤토리·DDL 위치 |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | key.ini·trading_config.json·constants·market_hours |
| [docs/DATA_MANAGEMENT.md](docs/DATA_MANAGEMENT.md) | 언제 무엇이 DB 에 들어오고 재기동 때 무엇을 읽나 |
| [docs/CODE_MAP.md](docs/CODE_MAP.md) | 운영 vs 연구 경계·엣지·드리프트 검증 명령 |
| [docs/INVENTORY.md](docs/INVENTORY.md) | 연구 파일 참조 태깅(`tools/gen_inventory.py` 생성) |
| [docs/DB통합_쉬운설명.md](docs/DB통합_쉬운설명.md) | 2026-08 DB 통합 경위·현재 상태 |
| [docs/전략진단_쉬운설명.md](docs/전략진단_쉬운설명.md) | 「8전략은 왜 마이너스인가」 쉬운 설명(엄밀본 `backtest/*/RESULTS.md`) |
| [instances/README.md](instances/README.md) | 실전 인스턴스 셋업 |
| 날짜 문서 | `docs/prereg_YYYY-MM-DD_<topic>.md`(사전등록 · 동결=커밋 · **편집·이동 금지**, 최상위) · `report_YYYY-MM-DD_장마감.md`(→ `docs/reports/2026-09/`; 태쏘 판정 보고 2본은 동결·최상위) · `plan_`/`design_`/`audit_`/`review_`/`verdict_`(최상위) · `<주제>_쉬운설명_YYYY-MM-DD.md`(패널 → `docs/panels/2026-09/`) · 보관 → `docs/archive/` |

---

**마지막 업데이트**: 2026-09-17
