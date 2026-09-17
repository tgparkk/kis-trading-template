# CODE MAP — 운영 vs 연구 경계 (에이전트 라우팅)

> 목적: 에이전트가 "운영 동작"을 찾을 때 연구/일회성 코드에 오도되지 않도록.
> 최종 검증: **2026-09-17** (`16a8106` 기준 · 하단 검증 명령을 실제 실행한 결과를 그대로 붙였다). 드리프트 의심 시 하단 검증 명령 재실행.
> 이전 판(2026-07-02)의 「엣지 0건」은 2026-07-06 `8a02cb2` 로 깨졌다 — 아래 「엣지 1건」 절 참조.

## 디렉토리 분류

### 운영(production, 라이브 매매 경로)
`main.py` · `config/` · `core/` · `bot/` · `framework/` · `api/` · `strategies/` · `collectors/` · `db/` · `runners/` · `signals/` · `utils/` · `tools/` · `market_dashboard/`

- `main.py` — `DayTradingBot` 진입점(737줄). 모듈 상세는 [code/MODULES.md](code/MODULES.md).
- `config/` — `settings.py`(key.ini + trading_config.json 로더) · `constants.py` · `market_hours.py` · `env_bootstrap.py`(repo-root `.env` → `os.environ`, main.py 최상단에서 호출) · `trading_config.json`(8전략 목록) · `key.ini.example` · `visualization_strategies.yaml`(← `visualization/strategy_manager.py` 전용).
- `market_dashboard/` — 6파일. `bot/system_monitor.py` `_init_dashboard()` 가 `market_dashboard.dashboard/global_market/domestic_market` 를 지연 import(프리마켓 브리핑 `_run_premarket_briefing` · 장중 상태 로그 `_run_market_dashboard`, 장중에만 갱신).
- `tools/` — 모듈 4(+docstring 뿐인 `__init__.py`) 중 **라이브 import 2개**: `daily_trading_summary.py`(← `bot/system_monitor.py` 상단 import, EOD 요약 출력) · `paper_strategy_equity.py`(← `bot/system_monitor.py` `_run_equity_snapshot` 지연 import, `bot/eod_benchmark.py` 상단 import). `gen_inventory.py`·`gen_archive_candidates.py` 는 개발 도구(운영 import 0).
- `runners/` — 4파일(빈 `__init__.py` 포함) 중 **라이브 지연 import 2개**: `_adapter_factory.py`(← `bot/candidate_loader.py` 폴백 컨셉 필터) · `screener_snapshot_collector.py`(← `bot/liquidation_handler.py` EOD 스냅샷 `run_once`). `_adjacent_grid.py` 는 연구 전용(참조 `tests/test_adjacent_grid.py` 뿐 · scripts/backtest/multiverse 참조 0).
- `signals/` — `foreign_flow.py`·`vkospi.py`. 운영 디렉토리로 분류돼 있고 `tools/gen_inventory.py` PROD_DIRS 에도 들어 있으나 **운영 import 0**(실측: 소비자 = `scripts/multiverse4_returns_export.py` · `tests/`).
- `strategies/` — 라이브 로드는 `strategies/{name}/strategy.py` + `config.yaml` 형태만(`StrategyLoader` 가 `strategies.{name}.strategy` 를 `importlib.import_module`). 하위 패키지 `books/`·`intraday/`·`allocation/` 은 `StrategyLoader` 로드 대상이 아니다(연구·테스트 소비자 = scripts/backtest/tests 56파일). `intraday/`·`allocation/` 은 **운영 import 0**(연구·백테스트 전용). 🔴 `books/` 는 다르다 — **라이브 8전략 중 6전략(book_envelope_200d·book_pullback_ma20·book_pullback_ma5·daytrading_3methods_breakout·elder_ema_pullback·minervini_volume_dryup)의 `strategy.py`·`screener.py` 12파일이 `strategies.books.<책>.rules*` 를 정적 import** 한다(예: `strategies/book_pullback_ma20/strategy.py` `from strategies.books.haru_silijeon.rules_daily import _ma, rule_daily_ma20_pullback` · `strategies/minervini_volume_dryup/screener.py` `from strategies.books.minervini_vcp.rules import (…)`). **운영 의존 패키지 — archive 금지.** `strategies/books/_base_book_strategy.py` 도 그 6개 `rules*.py` 가 `Rule`·`RuleResult` 를 import 하므로 간접 운영 의존(책별 `strategy.py`·`weinstein_stages/weekly.py` 는 운영 import 0). 분류표는 [code/MODULES.md](code/MODULES.md).

### 연구/일회성(research, 라이브 아님)
`scripts/` · `multiverse/` · `backtest/` · `lib/` · `books/` · `council/` · `archive/`
→ 운영 동작을 여기서 추론하지 말 것. 파일별 태깅은 [INVENTORY.md](INVENTORY.md).

- `scripts/` — 152 추적 파일. 연구 CLI·백필·검증 스크립트. 🔴 단 `scripts/kis_db/schema.py` 는 라이브 의존(아래 「엣지 1건」).
- `backtest/` — 611 추적 파일(엔진 + 개념축·사전등록 검정 결과 동결). 라이브 import 0. `core/screener_snapshot_provider.py` 의 `from backtest.engine import BacktestEngine` 은 **docstring 의 Usage 예시**이지 import 문이 아니다. `backtest/engine.py` 는 `make_screener_snapshot_provider` 를 `core/screener_snapshot_provider` 에서 re-export 만 한다(2026-07-02 Phase2 승격).
- `multiverse/` — 69 추적 파일. quant_v2 멀티버스 인프라 이식 패키지(`composable/`·`data/`·`engine/`·`labels/`·`metrics/`·`persistence/`·`runner/` + `tests/` 패키지 내 테스트 23 추적). `.gitignore` 의 `data/` 패턴 예외(`!multiverse/data/`).
- `lib/` — `pit_helpers.py`·`universe_filter.py`·`signals/`(8파일). **2026-07-10 연구/테스트 지원으로 재분류**(운영 디렉토리 import 0 — 이번에도 실측 0; 소비자 = scripts/backtest/tests 26파일). ⚠️ `tools/gen_inventory.py` PROD_DIRS 는 여전히 `lib` 를 운영으로 센다 — 도구 코드라 이번 정리에서 미수정(INVENTORY.md 머리말에 병기).
- `books/` — 책 조사 md 6본(코드 아님). 책 전략 코드는 `strategies/books/`.
- `council/` — 다중 에이전트 자문 CLI(`python -m council`). 6파일.
- `archive/` — 무참조 확정 연구코드 보관소(77 추적 · 2026-07-02 76건 이동, 판정근거 `docs/superpowers/plans/2026-07-02-archive-candidates.md`). 검색 대상 아님, 복원은 git mv 역방향.

### 데이터·산출물·잔재 (코드 아님 — 여기서 운영 동작 추론 금지)
| 디렉토리 | 무엇이 있나 | git |
|---|---|---|
| `cache/` | 런타임 캐시 — 분봉 parquet(`utils/minute_cache.py` → `cache/minute/{date}/`) · 일봉(`utils/unified_data_loader.py` → `cache/daily`) · 연구 `cache/intraday_universe`(`scripts/run_intraday_tournament.py`) | 미추적 |
| `charts/` | `visualization/chart_generator.py` 출력 폴더 | 미추적 |
| `data/` | `.gitignore` `data/` — 워크트리엔 없음(예외 `multiverse/data/` 는 패키지) | 미추적 |
| `init-scripts/` | SQL 6본(`01-init.sql` … `06-phase5-signals.sql`) — `docker-compose.yml` initdb 마운트 · `db/database_manager.py` 는 테이블 **존재 확인만**(생성 안 함) | 추적 6 |
| `instances/` | 실전 인스턴스 셋업(`README.md` + `rs_leader/` example). `.gitignore instances/*` 예외 = `README.md`·`*/*.example` 만 | 추적 3 |
| `memory/` | md 50본(`changelog-*` 44 + note 2·plan 1·research 1·spec 2 · 2026-05-08~06-03 · 마지막 커밋 `213dd30` 2026-06-03). 레포 밖 Claude Code 프로젝트 메모리의 **오래된 사본** · 코드 참조 0(archive/ 의 절대경로 문자열 2건뿐) | 추적 50 |
| `output/` | 연구 산출(`buy_filter_grid_2026-05-01.md` · `multiverse_dashboard.py` Plotly). `scripts/param_optimizer.py`·`run_buy_filter_grid.py` 등이 쓴다 | 추적 2 |
| `reports/` | 연구 결과 27폴더(`tournament_*` · `discovery/` · `books_research/` · `10pct_strategy/` …) 533 추적. 연구 스크립트 29개(.py · `scripts/` 28 + `backtest/concept_fidelity_audit/backtest_vs_live.py`)가 쓴다 · 운영 코드 참조 0(`core/regime/__init__.py` docstring 인용만) | 추적 |
| `scratchpad/` | 임시 작업(`.gitignore scratchpad/`) | 미추적 |
| `visualization/` | 차트 생성 패키지(12 추적). 소비자 = `utils/chart_cli.py`(← `generate_charts.bat`) · `utils/signal_replay_utils.py`(import 하는 곳 0). 라이브 봇 import 0 | 추적 |
| `logs/` | 런타임 로그(`.gitignore logs/` · `utils/logger.py` 가 `config.settings.LOG_DIR` 에 `trading_YYYYMMDD.log` 작성). 🔴 **라이브 트리의 logs/ 는 봇이 쓰는 중** — 라이브 트리에서 pytest·dryrun 을 돌리면 여기가 오염된다([code/MODULES.md 테스트 절](code/MODULES.md#테스트-구조)) | 미추적 |
| `htmlcov/` · `venv_broken_quantcopy/` | coverage 산출 · venv 백업(둘 다 `.gitignore`) | 미추적 |

## 🔴 라이브 → 연구 의존 엣지: **1건** (2026-09-17 실측)

| 라이브 파일 | 연구 대상 | 경위 · 상태 |
|---|---|---|
| `tools/paper_strategy_equity.py` `_ensure_table()` — `from scripts.kis_db.schema import PAPER_STRATEGY_EQUITY_DDL` | `scripts/kis_db/schema.py` | `8a02cb2`(2026-07-06, «paper_strategy_equity DDL 을 schema SSOT 로 승격») 에서 도입. 호출 경로: `bot/system_monitor.py` `_run_equity_snapshot` → `run_daily_equity_snapshot()` → `_ensure_table()`(EOD, 15:35 이후 postmarket 작업). `INVENTORY.md` 태그 **LIVE-DEP**. **승격(DDL 을 `db/` 또는 `tools/` 로) 또는 예외 등록 — 결정 대기.** |

연구 스크립트가 운영 코드를 **역방향 import**(연구→운영)하는 것은 허용. 과거 엣지 승격 이력(2026-07-02 Phase 1·2, 줄번호는 2026-09-17 실측):

| 과거 엣지 (라이브 파일 → 연구 대상) | 새 위치 |
|---|---|
| `collectors/daily_adj.py` → 동적 import `scripts.10pct_strategy.p0_apply_adj_factor` | `collectors/adj_factors.py` `compute_adj_factors`(`daily_adj.py:5` 정적 import) |
| `bot/system_monitor.py` → `scripts.daily_trading_summary` | `tools/daily_trading_summary.py` |
| `bot/system_monitor.py` → `scripts.paper_strategy_equity` | `tools/paper_strategy_equity.py` (→ 위 신규 엣지의 당사자) |
| `collectors/daily_derived.py` → `scripts.etl_backfill_daily_prices.SQL_UPDATE_RETURNS` | `collectors/daily_derived.py` (상수 내장) |
| `collectors/foreign_flow_collector.py` → `scripts.backfill_foreign_flow.fetch_foreign_naver` | `collectors/foreign_flow_fetcher.py` |
| `strategies/rs_leader/{strategy,screener}.py` → `scripts.rs_leader.rule.RSLeaderRule` | `strategies/rs_leader/rule.py` |
| `strategies/deep_mr_dev20/{strategy,screener}.py` → `scripts.discovery.rules.MeanReversionMA20Rule` | `strategies/deep_mr_dev20/rule.py` (`scripts/discovery/rules.py:284` 가 re-export 유지) |
| `core/candidate_selector.py:1082` → `backtest.engine.make_screener_snapshot_provider` (지연 import) | `core/screener_snapshot_provider.py` (`backtest/engine.py:637` 은 re-export 만) |

같은 날 `runners/param_optimizer.py`·`run_buy_filter_grid.py` 는 연구 그리드 러너로 판정돼 `scripts/` 로 강등. `runners/` 에 남은 라이브 참조는 `_adapter_factory.py`(← `bot/candidate_loader.py:313`) · `screener_snapshot_collector.py`(← `bot/liquidation_handler.py:601`) 2개.

## .bat 엔트리포인트
- `run_robotrader.bat` — 봇 기동. 평일 07:40 Windows 작업 스케줄러 `\RoboTrader_AutoStart` → `D:\GIT\run_all_robotraders.bat` → 이 파일. `:75` 의 `scripts\preflight_strategy_validate.py` 호출은 REM(파일은 존재).
- `run_instance.bat <name>` — `instances\<name>\key.ini` 로 실전 인스턴스 기동.
- `매일_분석_실행.bat` — **`:13 python daily_analysis.py` · `:18 python check_virtual_trading_db.py` 두 대상이 저장소에 없다**(`git log --all --diff-filter=A` 에도 추가 기록 0). `:23 python tools\daily_trading_summary.py` 만 유효.
- `장마감_자동분석.bat` — **비활성**(호출 대상 `scripts/auto_analysis.py` 부재, 2026-07-02 REM 처리).
- `generate_charts.bat` / `install_visualization.bat` — `utils/chart_cli.py`(visualization/) 용.

## 검증 명령 (드리프트 점검)
```bash
cd RoboTrader_template
# ① 정적 import 엣지 (라이브 → 연구). 범위에 strategies/ utils/ lib/ config/ main.py 포함.
grep -rn "from scripts\|import scripts\|from multiverse\|import multiverse\|from backtest\|import backtest" \
  bot/ collectors/ core/ framework/ api/ db/ runners/ signals/ tools/ strategies/ utils/ lib/ config/ main.py \
  --include="*.py" | grep -v '/tests/'
# ② 동적 import
grep -rn "import_module\|__import__" \
  bot/ collectors/ core/ framework/ api/ db/ runners/ signals/ tools/ strategies/ utils/ lib/ config/ main.py \
  --include="*.py" | grep -v '/tests/' | grep -v gen_inventory
# ③ .bat
grep -rn "scripts" *.bat
```
⚠️ 옛 명령의 `| grep -v test` 는 `from backtest`/`import backtest` 행(단어 `test` 포함)까지 지워 **자기 패턴의 1/3 을 구조적으로 못 봤다** — `grep -v '/tests/'` 로 고정. (`gen_inventory.py` 는 동적 import 탐지기라 문자열 매치가 자기 소스에 걸림 — ②에서 제외.)

**2026-09-17 실행 결과**(`16a8106`, 붙여넣기):
```
① core/screener_snapshot_provider.py:37:        from backtest.engine import BacktestEngine  # 백테스트 엔진과 조합 시
   tools/paper_strategy_equity.py:258:    from scripts.kis_db.schema import PAPER_STRATEGY_EQUITY_DDL
② strategies/config.py:489:            module = importlib.import_module(module_name)
③ run_robotrader.bat:75:REM python -X utf8 scripts\preflight_strategy_validate.py --verbose
   장마감_자동분석.bat:11:REM [2026-07-02] scripts/auto_analysis.py 는 저장소에 존재하지 않아 비활성화 (Phase1).
```
판정: ① 첫 행은 docstring `Usage:` 예시(엣지 아님) · 둘째 행 = **실제 엣지 1건** ② `strategies.{name}.strategy` 동적 로드(연구 아님) ③ REM 행뿐.
Expected(다음 점검): ① 에서 위 2행 외 신규 행 = FAIL · ② 신규 행 = FAIL · ③ REM 아닌 행 = FAIL.

### 인벤토리 재생성
```bash
cd RoboTrader_template        # 🔴 워크트리에서 실행 — 라이브 트리(D:/GIT/kis-trading-template) 금지
PYTHONUTF8=1 python -B tools/gen_inventory.py > ../_inventory_tmp.md \
  && sed -i 's/\r$//' ../_inventory_tmp.md \
  && { head -4 docs/INVENTORY.md; cat ../_inventory_tmp.md; } > ../_inventory_new.md \
  && mv ../_inventory_new.md docs/INVENTORY.md && rm ../_inventory_tmp.md
```
- 🔴 **워크트리에서 실행**(라이브 트리 금지). 워크트리엔 `venv/` 가 **없다**(`.gitignore` `venv/` · 미추적) — `venv/Scripts/python …` 은 그대로 치면 실패하고, 우회하려고 라이브 트리에서 돌리면 운영 규칙 위반이다. `tools/gen_inventory.py` 는 표준 라이브러리(`ast`·`os`)만 쓰므로 **시스템 Python 3.9.13(`python`)** 으로 충분(2026-09-17 실측: 워크트리에서 시스템 Python 으로 재생성한 출력이 `docs/INVENTORY.md` 본문과 diff 0). 라이브 트리 venv 인터프리터를 절대경로로 불러도 되지만 **cwd 는 반드시 워크트리**.
- 🔴 `> docs/INVENTORY.md` 로 **직접 리다이렉트 금지** — Python 3.9.13 은 리다이렉트 시 stdout 인코딩이 cp949 라(실측 `sys.stdout.encoding`) `—` 출력이 실패하면 쉘이 이미 문서를 0바이트로 비운 뒤다(감사 계획 2026-09-17 확인 결함). `PYTHONUTF8=1` + 임시파일 → `mv`. 기대값 **LIVE-DEP = 1**(위 엣지) — 2 이상이면 신규 엣지.
- 🔴 **줄끝**: Windows Python 은 리다이렉트 시 **CRLF** 로 쓴다(2026-09-17 실측 440/440행). HEAD 의 `INVENTORY.md` 는 LF 라 그대로 `mv` 하면 `git ls-files --eol` 이 `w/mixed`(수기 머리말 LF + 본문 CRLF) 가 된다 — `sed -i 's/\r$//'` 로 LF 통일. **머리말 3줄+빈 줄은 수기**(도구 출력에 없음) — 통째 `mv` 하면 사라지므로 `head -4` 로 앞에 되붙인다.

### lint 범위 메모
`RoboTrader_template/pyproject.toml` `[tool.ruff] extend-exclude` = `scripts, multiverse, books, council, venv, venv_broken_quantcopy, archive` — **`backtest/`·`lib/` 가 빠져 있다**(연구 분류인데 lint 대상). 도구 설정이라 이번 정리에서 미수정.

관련 설계: `docs/superpowers/specs/2026-06-30-research-production-separation-design.md` · 계획: `docs/superpowers/plans/2026-07-02-research-production-separation-phase1.md` · 감사: [audit_2026-09-17_dev_docs_cleanup_plan.md](audit_2026-09-17_dev_docs_cleanup_plan.md)
