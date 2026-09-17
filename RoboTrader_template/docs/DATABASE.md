# kis-template 데이터베이스 가이드

> 기준일 **2026-09-17** · 코드 `main`@`16a8106` · DB 값은 이날 `psql`(읽기 전용) 실측.
> 이전 판(2026-08-14, `b5ea3b8`)은 은퇴 DB `robotrader` 기준이라 전면 교체했다.
> 통합 경위(2026-08-16~17)는 [DB통합_쉬운설명.md](DB통합_쉬운설명.md) · 데이터가 «언제 어떻게» 들어오는지는 [DATA_MANAGEMENT.md](DATA_MANAGEMENT.md).

---

## 1. 접속

| 항목 | 값 | 근거 |
|---|---|---|
| 엔진 | PostgreSQL **16.11** + TimescaleDB **2.24.0**(확장은 설치돼 있으나 하이퍼테이블 0 → §7) | `SELECT version()` · `pg_extension` |
| 설치 | Windows 로컬 설치(Docker 아님) · `C:\Program Files\PostgreSQL\16\bin\` | — |
| Host / Port | `localhost`(=`127.0.0.1`) / **5433** | `db/connection.py` 기본값 |
| Database | **`kis_template`** | `db/connection.py` 기본값(2026-08-17 `robotrader` → `kis_template`) |
| User | `robotrader` — **롤명**이다. 은퇴 DB 이름과 같은 글자지만 다른 뜻 | `db/connection.py` 주석 |
| Password | env `TIMESCALE_PASSWORD`(코드 기본값 있음, 문서엔 적지 않는다) | `db/connection.py` |

### 1.1 연결 풀이 «둘»이다

| 풀 | 모듈 | env 접두 | 기본 DB | 쓰는 곳(운영 코드, grep 실측) |
|---|---|---|---|---|
| **운영 풀** | `db.connection.DatabaseConnection`(ThreadedConnectionPool 싱글턴, `get_connection()` 컨텍스트가 commit/rollback) | `TIMESCALE_*` | `kis_template` | `db/repositories/base.py`(→ candidate·price·trading·quant·sector_news 모든 Repository) · `db/database_manager.py` · `bot/state_restorer.py` · `bot/system_monitor.py` · `bot/eod_benchmark.py` · `tools/daily_trading_summary.py` · `tools/paper_strategy_equity.py` · `utils/intraday_universe.py` |
| **수집기 풀** | `db.kis_db_connection.KisDbConnection`(같은 패턴 · `get_connection()` 은 commit 을 «안» 한다 — 호출자가 commit) | `KIS_DB_*` | `kis_template` | `collectors/`(corp_action_watch · corp_events_collector · daily_collector · financial_collector · foreign_flow_collector · index_collector · minute_collector · sector_collector · split_factor_infer · stock_market_collector) · `core/regime/market_classifier.py` · `signals/foreign_flow.py`(풀 대신 같은 `KIS_DB_*` 기본값으로 직접 connect) · `tools/paper_strategy_equity.py`(종가 읽기) |

두 풀은 **같은 DB**(`kis_template`)를 가리킨다. 갈라진 이유는 역사(통합 전 `robotrader` vs `kis_template`)이고, 지금은 env 접두만 다르다. `.env` 에 `TIMESCALE_DB` 를 다른 값으로 두면 운영 풀만 그리로 간다 — 라이브 `.env` 는 `kis_template` 이어야 한다.

### 1.2 풀을 안 거치는 접속(직접 `psycopg2.connect`)

| 모듈 | DB명 결정 | host/port/user/pw |
|---|---|---|
| `db/quant_daily_reader.py`(`QuantDailyReader`, 자체 풀) | `resolve_daily_source_db()` | `TIMESCALE_HOST/PORT/USER/PASSWORD` |
| `collectors/investor_trend_collector.dsn()`(`market_flow_collector` 도 import) | `resolve_daily_source_db()` | **하드코딩** `127.0.0.1:5433 robotrader` |
| `strategies/historical_data.py` | 상수 `EXT_DB_NAME="kis_template"` | `EXTERNAL_DB_HOST/PORT/USER/PASSWORD` |
| `strategies/lynch/db_manager.py` · `strategies/sawkami/db_manager.py` | `STRATEGY_DB_NAME`(기본 `kis_template`) | `STRATEGY_DB_*` → 없으면 `TIMESCALE_*` → 없으면 **user `postgres`/빈 암호**(등록 전략 아님 · §4-E) |
| `multiverse/data/pit_reader.py`(연구) | 가격 = resolver · 재무 = `QUANT_FINANCIAL_DB`(기본 `kis_template`) | — |

### 1.3 코드에서 쓰는 법

```python
from db.connection import DatabaseConnection          # 운영 풀 (commit 자동)
with DatabaseConnection.get_connection() as conn:
    cur = conn.cursor(); cur.execute("SELECT 1"); cur.fetchone()

from db.kis_db_connection import KisDbConnection      # 수집기 풀 (commit 은 호출자 몫)
with KisDbConnection.get_connection() as conn:
    ...; conn.commit()
```

NUMERIC 은 두 풀 모두 `float` 로 변환해 돌려준다(`DEC2FLOAT` 타입 등록).

---

## 2. 환경변수 전수

`.env` 는 `config/env_bootstrap.py` 가 읽는다: **OS env > `.env` > 코드 기본값**(이미 있는 키는 덮지 않음). `KEY=VALUE` 만 파싱하고 **인라인 `# 주석` 은 값에 그대로 포함된다** — 값 뒤에 주석을 달지 말 것.

| 변수 | 읽는 곳 | 기본값 | 비고 |
|---|---|---|---|
| `TIMESCALE_HOST` / `TIMESCALE_PORT` / `TIMESCALE_USER` / `TIMESCALE_PASSWORD` | `db/connection.py` · `db/quant_daily_reader.py` · `tools/paper_strategy_equity._db_conn` · lynch/sawkami(폴백) | `localhost` / `5433` / `robotrader` / (코드) | `db/config.py`(`DatabaseConfig.from_env`) 도 같은 변수를 읽지만 **운영 import 0**(`tests/` 만) 인 죽은 모듈이고 PORT 기본값이 `5432` 로 틀리다 — 쓰지 말 것 |
| `TIMESCALE_DB` | `db/connection.py` · `tools/paper_strategy_equity._db_conn` | `kis_template` | 🔴 **수동 쓰기 스크립트에선 «필수»** — `require_explicit_target_db()` 가 미설정이면 `SystemExit` |
| `KIS_DB_HOST` / `KIS_DB_PORT` / `KIS_DB_NAME` / `KIS_DB_USER` / `KIS_DB_PASSWORD` | `db/kis_db_connection.py` · `signals/foreign_flow.py` | `localhost` / `5433` / `kis_template` / `robotrader` / (코드) | |
| `QUANT_FINANCIAL_DB` | `multiverse/data/pit_reader.py`(`_FINANCIAL_DB`) — `lib/signals/roe_filter.py` 는 env 0 · `kis_template` 하드코딩 | `kis_template` | **재무 전용** 롤백 스위치. 가격 resolver 와 «분리»가 의도된 설계(`config/constants.py` 주석). 살아 있어야 한다(`tests/test_research_data_source.py`) |
| `EXTERNAL_DB_HOST` / `_PORT` / `_USER` / `_PASSWORD` | `strategies/historical_data.py` | `127.0.0.1` / `5433` / `robotrader` / (코드) | DB명은 상수 |
| `STRATEGY_DB_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_NAME` | `strategies/lynch/db_manager.py` · `strategies/sawkami/db_manager.py` | `TIMESCALE_*` 폴백 → `postgres`/`''` · `kis_template` | 등록 전략 아님 |
| `SCREENER_SNAPSHOT_ENABLED` | `config/constants.py` | `false` | `true` 일 때만 장전 스냅샷 훅이 `screener_snapshots` 를 쓴다(§5-7) |

### 2.1 폐지된 변수 — 설정해도 «아무 일도 없다»

`KIS_DATA_SOURCE` · `QUANT_DB` · `MINUTE_DB` · `CORP_EVENTS_DB` (2026-08-17 폐지). 읽기 DB 는 `config/constants.py` 의 세 resolver 가 **상수** `"kis_template"` 을 돌려준다:

| 함수 | 용도 | 호출자(운영) |
|---|---|---|
| `resolve_daily_source_db()` | `daily_prices` 읽기 | `db/quant_daily_reader.py` · `bot/eod_benchmark.py` · `collectors/investor_trend_collector.py` · `strategies/book_envelope_200d/strategy.py` · `signals/vkospi.py` · `tools/paper_strategy_equity.py` |
| `resolve_minute_source_db()` | `minute_candles` 읽기 | 연구 경로(`multiverse/` · `scripts/` · `backtest/`) |
| `resolve_corp_events_source_db()` | `corp_events` 읽기 | 연구 경로(`multiverse/data/corp_events.py` 등) |
| `require_explicit_target_db(purpose)` | **수동 쓰기 스크립트**의 대상 DB — `TIMESCALE_DB` 미설정/공백이면 `SystemExit`(기본값을 «없앤» 것) | `scripts/backfill_corp_events.py` · `backfill_daily_prices_fundamental.py` · `backfill_foreign_flow.py` · `backfill_kospi_index.py` · `backfill_operating_cash_flow.py` · `backfill_vkospi.py` · `scripts/10pct_strategy/p0_apply_adj_factor.py`(7개) |

「넣어도 무시된다」는 `tests/test_research_data_source.py` · `tests/db/test_data_source_flag.py` 가 회귀 고정한다. 🔑 resolver 함수는 지우지 말 것 — 나중에 소스를 바꿀 자리를 «한 곳»으로 유지하는 게 목적이다. **DB명 하드코딩 금지, 반드시 resolver 경유**가 SSOT 규칙.

---

## 3. 이 서버의 DB 목록 — 은퇴 DB 포함 (실측 2026-09-17)

```sql
SELECT datname, datallowconn, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE NOT datistemplate;
```

| datname | allowconn | 크기 | 이 레포에서의 지위 |
|---|---|---|---|
| **`kis_template`** | t | 18 GB | **유일 SSOT** — 운영·시장데이터·재무·섹터 전부 |
| `robotrader_retired_20260817` | **f** | 11 GB | 옛 `robotrader` 를 2026-08-17 RENAME 한 것. `datallowconn=false` 라 **어떤 접속도 거부**된다(워커 재접속 차단 목적). 남은 단계 = `pg_dump` → `DROP`(사장님 결정 대기). ⚠️ `pg_dump` 도 접속이라 덤프 전엔 `ALTER DATABASE … ALLOW_CONNECTIONS true` 가 필요하다 |
| `robotrader_quant` | t | 1,404 MB | 이관 원본(재무). 운영 코드 참조 0(주석뿐) · 2026-07-10 동결 |
| `robotrader_backtest` | t | 1,519 MB | 이관 원본 후보(일봉·투자자수급·팩터). 운영 코드 참조 0. 🟢 `robotrader` 롤이 13/13 표 SELECT 가능(옛 「GRANT 못 받음」 해소) |
| `robotrader_optuna` | t | 43 MB | 최적화 실험. 운영 코드 참조 0. SELECT 13/13 |
| `strategy_analysis` | t | 7,026 MB | 이관 원본(섹터·연간재무·`daily_candles`). 운영 코드 참조 0(docstring 이력만) |
| `newsquant` | t | 175 MB | 별도 프로그램(NewsQuant)의 DB. 이 레포 참조 0 |
| `scalping` · `robotrader_orb` · `robotrader_quant_mom` · `postgres` | t | 12 GB · 1,341 MB · 23 MB · 8 MB | 이 레포 코드 참조 0(형제 프로젝트·관리 DB) |

🔴 **은퇴 DB 삭제와 롤백 스위치 폐기는 같은 작업이다** — 스위치는 이미 폐기됐다(§2.1). 삭제 전 `pg_dump` 는 사장님 확인 후.

---

## 4. 표 인벤토리 — `kis_template.public` 74표 (실측)

`pg_class`(`relkind='r'` · `public` 스키마) **74표** × 운영 코드(`db/ core/ bot/ tools/ collectors/ strategies/ signals/ utils/ config/ api/ runners/ main.py`) SQL 참조 grep 의 교차표. **행 수는 `pg_class.reltuples` 추정치**(ANALYZE 시점 · `-1` = 통계 없음).

⚠️ `information_schema.tables` 는 `robotrader` 롤에겐 **70** 만 보인다 — `postgres` 소유 4표(`backtest_signal` · `news_dart_published_at_backup` · `news_reprocessed` · `newsquant_signal_ledger`)는 권한 필터로 숨는다(「못 본다」≠「없다」). 74 는 `pg_class` 로만 재현된다:

```sql
SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind = 'r';                        -- 74
SELECT tablename, tableowner FROM pg_tables
 WHERE schemaname = 'public' AND tableowner <> 'robotrader';            -- 위 4표
```

### 4-A. 운영 원장 — 봇이 쓴다

| 표 | 쓰기(W) | 읽기(R) | 행(추정) |
|---|---|---|---|
| `virtual_trading_records` | `db/repositories/trading.py`(BUY/SELL INSERT · 항상 `source='kis_template'`) | trading.py(복원·미매칭) · `core/virtual_trading_manager.py` · `bot/state_restorer.py` · `tools/daily_trading_summary.py` · `tools/paper_strategy_equity.py` | 1,573 |
| `real_trading_records` | trading.py(`INSTANCE_ID='default'` 일 때) | trading.py `get_real_open_positions` → `bot/state_restorer.py` | 224 |
| `real_trading_<instance>` | trading.py `ensure_real_table()`(`LIKE real_trading_records INCLUDING ALL`, 멱등) — 실재: `real_trading_rs_leader` | 〃 | -1 |
| `paper_trading_state` | trading.py `upsert_paper_eod_balance` ← `core/virtual_trading_manager.save_paper_trading_state`(15:00 EOD 청산 훅 · 15:35 재저장) | vtm 기동 시 잔고 이월 · `tools/paper_strategy_equity.py` | 79 |
| `paper_strategy_equity` | `tools/paper_strategy_equity.run_daily_equity_snapshot` ← `bot/system_monitor._run_equity_snapshot`(EOD 2회) | `bot/eod_benchmark.py` | 584 |
| `candidate_stocks` | `db/repositories/candidate.save_candidate_stocks` ← `bot/candidate_loader.py` | `bot/state_restorer._restore_candidates`(오늘 날짜) · candidate.py 이력 · `utils/signal_replay_utils.py`(날짜별 조회) | 12,511 |
| `screener_snapshots` | `db/repositories/candidate.save_screener_snapshot` ← `runners/screener_snapshot_collector.run_once` ← `bot/liquidation_handler.run_screener_snapshot_hook`(`SCREENER_SNAPSHOT_ENABLED`) | `core/screener_snapshot_provider` → `core/candidate_selector`(전략별 후보의 **유일** 경로 — 예외: 8전략 «전부» 0건이면 거래량 순위 폴백 · ERROR 로그 · `bot/candidate_loader`) · `bot/system_monitor._verify_screener_snapshot` | 7,464 |
| `sector_news_rerank_log` | `db/repositories/sector_news.py`(런타임 DDL) ← `core/candidate_selector._apply_sector_news_rerank` | — | 746 |
| `daily_prices_preadj_backup` | `db/adj_backup.py`(보정 도구 `scripts/repair_corp_action_prices.py` 전용 · 「백업 없이 한 행도 안 고친다」) | 〃 | 5,826 |

### 4-B. 시장데이터 — EOD 수집기가 쓰고 봇이 읽는다

| 표 | W | R | 행(추정) |
|---|---|---|---|
| `daily_prices` | `collectors/daily_writer.upsert_daily_rows` · `daily_derived`(returns/volatility) · `daily_adj`(adj_factor) · `db/repositories/price.save_daily_prices_batch`(장중 W1 · regime 지수 W3) | `db/repositories/price.get_daily_prices` · `db/quant_daily_reader.py` · `strategies/historical_data.py` · `collectors/*`(유니버스·오라클) · `tools/*` | 3,221,371 |
| `minute_candles` | `collectors/minute_writer.replace_minute_day`(DELETE 당일 + INSERT) — **장중 DB 쓰기 0** | `db/repositories/price.get_minute_prices` · `utils/intraday_universe.py`(운영 import 0) | 60,798,700 |
| `index_daily` | `collectors/index_writer.py`(KIS 업종 일봉 · FDR 폴백) | `collectors/index_collector.py`(신선도 판정) | 130 |
| `stock_market` | `collectors/stock_market_writer.py`(FDR 상장목록) | `core/regime/market_classifier.py`(시장 매핑 캐시) · `collectors/daily_collector.load_universe` · `collectors/sector_collector.py`(커버리지 분모 `U_market`) | 2,773 |
| `corp_events` | `collectors/corp_events_collector.py`(OpenDART · `DO NOTHING`) · `collectors/split_factor_infer.py`(`meta.split_factor/effective_date` 스탬프) | `collectors/daily_adj.load_split_events` · `collectors/split_factor_infer.py`(스탬프 대상 조회). ⚠️ `corp_action_watch.py` 는 이 표를 읽지 않는다 — 탐지는 가격 갭으로 하고 결과는 `logs/corp_action_refetch_queue.jsonl`(파일)에 적는다 | 1,619 |
| `foreign_flow` | `collectors/foreign_flow_writer.py`(네이버) | `signals/foreign_flow.py` | 172,158 |
| `investor_trend_daily` | `collectors/investor_trend_collector.py`(KIS · 최근 30거래일 롤링 · 신선도 가드) | — | 136,767 |
| `program_trade_daily` · `short_sale_daily` · `credit_balance_daily` · `overtime_daily` | `collectors/market_flow_collector.py`(KIS · 신선도 가드) | — | 136,707 · 162,781 · 136,192 · 137,303 |
| `collection_reconciliation` | 각 수집기의 reconcile(`dataset` 별 UPSERT) | `collectors/financial_collector.py` · `sector_collector.py` | 55 |

### 4-C. 재무 — `collectors/financial_collector.py` 계열 (DB 쓰기는 `financial_writer.py` 한 곳)

| 표 | W | R | 행(추정) |
|---|---|---|---|
| `dart_corp_code` | `collectors/dart_corp_code.py` | 〃 · `financial_collector` · `sector_collector` | 3,990 |
| `dart_financial_filings` | `financial_writer.py` | `financial_collector` · `financial_metrics` · `financial_writer` | 23,897 |
| `dart_financial_accounts` | 〃 | `financial_metrics.py`(`fn_financials_as_of`) | 3,884,576 |
| `dart_financial_nodata` | 〃 | `financial_collector` | 770 |
| `kis_financial_ratio` | 〃(`kis_financial_fetcher` · 교차검증 전용, PIT 앵커 없음) | — | 70,399 |

### 4-D. 섹터 — `collectors/sector_collector.py` 계열 (DB 쓰기는 `sector_writer.py` 한 곳)

| 표 | W | R | 행(추정) |
|---|---|---|---|
| `stock_sector_map` | `sector_writer.py`(SCD2 명부) | `fn_sector_map_as_of(date)` ← `db/repositories/sector_news.py` · `sector_collector` | 2,797 |
| `sector_daily_stats` | 〃 | `sector_collector`(reconcile) | 727,674 |
| `ksic_code_name` · `sector_ksic_nodata` | 〃 | 〃 | 158 · -1 |
| `stock_industry` | — (이관 스냅샷) | `sector_writer.py` | 2,556 |
| `sector_news_score` | **NewsQuant**(외부 프로그램) | `db/repositories/sector_news.py` | 608 |

### 4-E. 등록 전략이 아닌 코드의 표 — 코드 참조는 있으나 라이브 8전략(`config/trading_config.json strategies[]`) 경로 아님

| 표 | 참조 코드 | 행(추정) |
|---|---|---|
| `stock_sector` | `strategies/bb_reversion*/screener.py` · `strategies/sample/screener.py` · `strategies/historical_data.get_sectors` · `core/regime/market_classifier`(「market 필드 오염 — 폴백으로도 쓰지 않는다」) | 4,085 |
| `yearly_fundamentals` | `strategies/historical_data.py` · `strategies/lynch/` · `strategies/sawkami/` | 9,777 |
| `financial_statements` | `strategies/historical_data.get_quarterly_fundamentals_at` · `scripts/run_*.py`(책 전략 재현 6종 · `run_dino_surge.py` 등 · `strategies/books/dino_surge/rules.py` 는 docstring 언급뿐 · SQL 0) · `scripts/10pct_strategy/p5_stage_rerun.py` · `scripts/backfill_daily_prices_fundamental.py`(유니버스 읽기) · `lib/signals/roe_filter.py` — **운영 writer 0**(수동 `scripts/backfill_operating_cash_flow.py` 의 `UPDATE` 만 · `report_date` 최신 2026-03) | 4,350 |
| `lynch_trades` · `sawkami_candidates` · `sawkami_trades` | `strategies/lynch/db_manager.py` · `strategies/sawkami/db_manager.py`(런타임 DDL · `lynch_trades` 는 docstring 대로 「원본 0행 → 빈 표 생성」) | -1 · -1 · 315 |
| `quant_factors` · `quant_portfolio` · `financial_data` | `db/repositories/quant.py`(R/W) · `core/candidate_selector.py` 가 `get_quant_portfolio` 1곳 읽음 · **쓰기 호출자 0** | 106,728 · 2,454 · -1 |

### 4-F. 운영 코드 참조 0 — 「연구/보관」(스크립트·백테스트·외부 프로그램 영역)

`backtest_signal`(owner `postgres`) · `collection_log`(컬럼 `source·news_count` — 뉴스 수집 로그 형태) · `daily_candles_raw_robotrader` · `daily_prices_recovery_20260803` · `daily_prices_recovery_20260803_gate` · `dart_financials_asfiled`(17,892 · 옛 재무 as-filed 표 — `collectors/financial_writer.py` docstring 과 `db/migrations/20260815_*.sql` 주석이 「죽은 이유(키가 기간)」로만 언급 · 현행 원장은 §4-C) · `dpr_ck_before` · `dpr_cliff_after` · `dpr_cliff_before` · `dpr_sparse_before` · `dpr_splice` · `dpr_universe_before` · `financial_account_long` · `market_cap_estimate`(1,556,342) · `market_index` · `market_regime`(둘 다 `core/regime/__init__.py` docstring 이 「사용 금지 · frozen」으로 명시) · `minute_candles_dupes` · `minute_candles_dupes_prior_20260720` · `minute_candles_gap_robotrader` · `news`(≈22만 · 레포 안 쓰기 코드 0 · 레포 밖 상시 쓰기로 `reltuples` 가 하루 안에도 움직여 고정 숫자 미기재) · `news_dart_published_at_backup`(`postgres`) · `news_reprocessed`(`postgres`) · `news_sector_hit` · `news_stock`(483,460) · `newsquant_signal_ledger`(`postgres`) · `nxt_snapshots` · `quant_balance_sheet` · `quant_financial_ratio` · `quant_income_statement`(연구 `multiverse/data/pit_reader.py` 가 `QUANT_FINANCIAL_DB` 로 읽음) · `sector_index_daily` · `stock_info`(2,115 · `api/kis_market_api.py` 의 `stock_info` 는 같은 이름의 로컬 dict 변수일 뿐 SQL 참조 아님) · `virtual_trading_records_owner_fix_bak_20260716` · `virtual_trading_records_plfix_bak_20260730` — **33표**(4-A 9 + 4-B 12 + 4-C 5 + 4-D 6 + 4-E 9 + 4-F 33 = 74).

⚠️ 「참조 0」은 이 레포 **운영 디렉토리** 기준이다. `scripts/`·`backtest/`·`multiverse/`·NewsQuant 는 조사 범위 밖 — 지우기 전엔 거기도 봐야 한다. `01-init.sql` 의 `trading_records` 와 `02-multiverse.sql` 의 `composable_*`, `06-phase5-signals.sql` 의 `foreign_flow_daily`·`vkospi_daily` 는 **DB 에 없다**.

SQL 함수(public): `fn_sector_map_as_of(date)`(`sector_writer.py`) · `fn_financials_as_of(date)`(`financial_metrics.py`) · `update_updated_at_column()`(`01-init.sql` 트리거용) · `news_stock_sync()`(이 레포 코드·SQL 참조 0 — 외부 프로그램 영역으로 추정, 미확인).

---

## 5. 핵심 표 컬럼 (`\d` 실측)

### 5-1. `daily_prices` — 일봉 (PK `stock_code, date`)

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `stock_code` | varchar | 종목코드. 정규 종목 = `SQL_STOCK_ONLY`(`^[0-9][0-9A-Z]{5}$`, `config/constants.py`) — 신형 코드(`00088K` 등)도 정규 종목이다 |
| `date` | **text** `'YYYY-MM-DD'` | DATE 가 아니다. 문자열(ISO) 비교로 쓴다(`strategies/historical_data._to_iso` 주석) |
| `open` `high` `low` `close` | double precision | **`close` 는 이미 분할 조정된 연속 시세**(규약 `adj_close = raw_close / adj_factor`, `collectors/adj_factors.py`) |
| `volume` | bigint | **원본(미조정)**. 읽기 계층이 `volume * COALESCE(adj_factor, 1)` 로 맞춘다 — `db/repositories/price.get_daily_prices` · `db/quant_daily_reader.py`. 🔴 `close` 에는 곱하면 «안 된다»(가짜 분할 절벽) · `volume` 에는 이미 곱해져 나온다(이중조정 금지). 상세 `tests/test_adj_factor_volume_units.py` |
| `trading_value` `market_cap` | bigint / double | KIS 일봉 원값 — `collectors/daily_writer.upsert_daily_rows`(`market_cap` 은 `COALESCE(EXCLUDED, 기존값)` 이라 NULL 로 덮이지 않는다). 봇 경로 `price.py` 의 W1 은 이 두 컬럼을 쓰지 않는다 |
| `returns_1d/5d/20d` `volatility_20d` | double | 파생 — `collectors/daily_derived.update_returns_volatility`(`SQL_UPDATE_RETURNS` 윈도우 함수 · 전체 재계산 · 멱등) |
| `adj_factor` | double precision, **nullable** | 분할 배수(권리락일 «이후» 이벤트의 곱). `collectors/daily_adj.update_adj_factors`. 실측 NULL 411,605 / ≠1 96,472 / 전체 3,209,019 — NULL 은 1 로 읽는다. `03-adj-factor.sql` 의 `NUMERIC NOT NULL` 은 옛 DB 기준이고 이 DB 는 `scripts/kis_db/schema.py` 가 만든 nullable 컬럼이다 |
| `created_at` `updated_at` | timestamp | 기본 `now()` · 갱신 트리거 없음 |

인덱스는 PK 뿐. **하이퍼테이블 아님**(§7).

**의사티커**(`SQL_STOCK_ONLY` 에 걸리지 않아 유니버스 쿼리에서 자동 제외):

| `stock_code` | 행 | 기간(실측) | 갱신 |
|---|---|---|---|
| `KOSPI` · `KOSDAQ` | 1,400 · 1,400 | 2021-01-04 ~ 당일 | `core/regime/index_refresh.refresh_regime_indices`(KIS 업종 `0001`/`1001`, FDR 폴백) ← `bot/system_monitor` 장전+EOD. 급락게이트 SSOT |
| `KS11` · `KQ11` | 601 · 601 | 2024-01-02 ~ **2026-07-08 동결** | 갱신 경로 없음(레거시 잔재) — 쓰지 말 것 |

**봇 경로**(`db/repositories/price.py`)의 쓰기 SQL 은 그 파일 상단 두 상수뿐: `DAILY_UPSERT_SQL`(OHLCV 덮어쓰기) · `DAILY_INSERT_ONLY_SQL`(`DO NOTHING`, 사전등록 E′ — 장중 W1 은 `W1_PAST_ROWS_INSERT_ONLY=True` 로 과거 행을 «빈 칸만» 채우고 당일 행만 UPSERT). 수집기 쪽 쓰기(`daily_writer` · `daily_derived` · `daily_adj` · `db/adj_backup`)는 별도 SQL — §4-B 참조.

### 5-2. `virtual_trading_records` — 페이퍼 매매 원장 (PK `id` serial)

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `action` | varchar(10) | `'BUY'` / `'SELL'` (❌ `trade_type` 아님) |
| `strategy` | varchar(50) | owner 전략 키(❌ `strategy_name` 아님). `TradingRepository._sanitize_strategy` 가 매매 사유 문자열이 들어오면 `unknown` 으로 치환 |
| `quantity` `price` `timestamp` | int · numeric(15,2) · timestamptz | 체결 |
| `is_test` | boolean, 기본 true | **페이퍼는 항상 true 가 정상**(실측 09-17 ≈1,753행 전부 true · 매매마다 는다). 리포트는 `source` 필터만 쓴다 |
| `source` | varchar(50) | 출처 프로젝트. 이 레포의 모든 INSERT/SELECT 는 `'kis_template'`(`TradingRepository.SOURCE_KIS_TEMPLATE`). 옛 `robotrader` 공유 시절 `05-vtr-source-column.sql` 로 도입 |
| `is_overflow` | boolean | 컬럼만 있다 — **운영 코드 참조 0**(이관 스크립트 컬럼 목록에만). 실측 09-17 ≈ f 695 / NULL 1,058 — 두 값만 |
| `profit_loss` `profit_rate` | numeric | 🔴 **gross** — `(매도가−매수가)×수량`(`trading.py save_virtual_sell`). 수수료·거래세 미반영. net 은 `core/fund_manager` 로그 「매매 손익 반영」에만 있고 **어느 표에도 없다**(`tools/daily_trading_summary.py` 상단 주석). ⇒ 실현손익 보고는 net 기준으로 따로 계산 |
| `buy_record_id` | int, self-FK | SELL → BUY. `idx_virtual_trading_unique_sell` = SELL 당 buy_record_id UNIQUE(부분) |
| `target_profit_rate` `stop_loss_rate` | numeric(10,6) | BUY 에만. 복원 시 NULL/NaN 이면 `DEFAULT_*`(`bot/state_restorer.py`) |

미매도 포지션 술어(`get_virtual_open_positions`): `action='BUY' AND is_test=true AND source=%s AND NOT EXISTS(SELL)` — 존재성 술어는 페이퍼(원자 체결)에서만 안전하다는 주석이 붙어 있다.

### 5-3. `paper_strategy_equity` — 전략별 일별 자산곡선 (PK `trade_date, strategy, source`)

`cash` · `position_value` · `equity`(=현금+보유평가) · `realized_pnl_cum`(= 위 gross `profit_loss` 의 SUM) · `n_open` · `updated_at`. 에포크 2026-06-01 · 실측 8전략 · `source` 기본 `'kis_template'`. writer 는 `tools/paper_strategy_equity.py` 뿐(EOD 15:35 1차 + 수집 후 T 종가로 재스냅샷 · 전구간 UPSERT 멱등). ⚠️ `paper_trading_state.eod_balance` 는 **현금만**이라 자산곡선엔 못 쓴다(`bot/eod_benchmark.py`).

### 5-4. `minute_candles` — 1분봉

PK **`(stock_code, trade_date, idx)`** + UNIQUE `(stock_code, datetime)` + 인덱스 `(stock_code, trade_date)`. 컬럼 `trade_date`·`date` 둘 다 `'YYYYMMDD'` varchar(같은 값) · `time` `'HHMMSS'` · `idx`(당일 순번) · OHLC/`volume`/`amount` double · `datetime` timestamp. 🔑 **집계는 PK 의 `trade_date` 로** — 비-PK `date` 로 묶으면 없는 중복이 보인다. writer `collectors/minute_writer.replace_minute_day` = `DELETE … WHERE stock_code AND trade_date` 후 `INSERT … ON CONFLICT (stock_code, datetime) DO NOTHING`(휴장일에 돌리면 T-1 을 지우고 부분 재적재할 수 있어 EOD 블록이 `is_holiday` 게이트를 건다). 유니버스 = 거래대금 top300(`collectors/minute_universe.select_top_volume`, KIS 순위 API).

### 5-5. `index_daily` — 지수 일봉 (PK `index_code, date` text)

`KOSPI`/`KOSDAQ` 각 66행(2026-06-15~, 실측) · OHLC/volume double. writer `collectors/index_writer.py`(KIS 업종 일봉 · «날짜» 기준 신선도 판정 · FDR 폴백). ⚠️ 5.5년 지수는 여기가 아니라 `daily_prices` 의사티커 `KOSPI`/`KOSDAQ`.

### 5-6. `foreign_flow` — 외국인 순매매량 (PK `stock_code, date` **DATE**)

`foreign_net_vol` bigint(주) · `source` 기본 `'naver'`. T 일 저녁 발표분을 T+1 판단에 쓴다(`signals/foreign_flow.py`). 실측 `source='naver'` 단일.

### 5-7. `screener_snapshots` — 전략별 후보 스냅샷

UNIQUE `(strategy, scan_date, params_hash, stock_code)` · `params_json` jsonb · `rank_in_snapshot` · `score` · `metadata` jsonb. 전략당 상한 `MAX_CANDIDATES_PER_STRATEGY = 20`(`config/constants.py` — 생성·소비 공통 SSOT). `scan_date` = **직전 거래일**(당일 일봉은 EOD 뒤에야 있으므로, `bot/liquidation_handler.run_screener_snapshot_hook`). 라이브 후보는 **자기 전략의 이 표에서만** 온다(`core/candidate_selector` · 예외: 8전략 «전부» 0건이면 거래량 순위 폴백 — ERROR 로그, `bot/candidate_loader`). 실측 09-16: 6전략 적재(minervini 11 · 나머지 20).

### 5-8. `stock_sector_map` — 종목→KSIC 명부 (SCD2 · PK `stock_code, valid_from`)

`valid_to`(NULL = 현행) · `ksic_code` · `ksic3_name` · `corp_code` · `market` · `source`(NOT NULL) · `source_asof` · CHECK `valid_to >= valid_from` · 부분 인덱스 `idx_ssm_open`(`valid_to IS NULL`). 「그날 업종」은 `fn_sector_map_as_of(date)` 로 묻는다. ⚠️ 구축일 이전 구간 라벨은 현행 명부의 **소급**이다.

### 5-9. `real_trading_records` / `real_trading_<instance>` — 실거래 원장

`vtr` 과 달리 `is_test`·`source`·`target_profit_rate`·`stop_loss_rate` **없음**, 대신 `fee_amount`·`net_profit`·`net_profit_rate`(double). 표 이름은 `config/settings.real_trading_table_name(INSTANCE_ID)` — `default` 면 `real_trading_records`, 아니면 `real_trading_<id>`(정규식 검증 · `LIKE … INCLUDING ALL` 로 생성, 시퀀스 `real_trading_records_id_seq` 공유). 실재 인스턴스 표: `real_trading_rs_leader`. 복원은 `get_real_open_positions` 의 **잔량 술어**(`BUY.quantity − Σ SELL.quantity > 0`, 부분매도 대응).

### 5-10. `paper_trading_state` (PK `trade_date`) · `candidate_stocks` (PK `id`) · `corp_events` (PK `stock_code, event_type, event_date`)

`eod_balance` numeric = **현금만** · `candidate_stocks(selection_date timestamptz, score, reasons, status)` 는 복원용 당일 후보 · `corp_events(end_date date, meta jsonb)` — `meta.split_factor`·`meta.direction`·`meta.effective_date`(권리락일) 를 `daily_adj` 가 읽는다.

---

## 6. DDL 이 있는 곳

| 위치 | 만드는 것 | 비고 |
|---|---|---|
| `init-scripts/01-init.sql` | `daily_prices`(+`create_hypertable` 호출) · `candidate_stocks` · `virtual_trading_records` · `real_trading_records` · `financial_data` · `financial_statements` · `quant_factors` · `quant_portfolio` · `trading_records` · `screener_snapshots` · `paper_trading_state` · `update_updated_at_column()` | 옛 `robotrader` 초기화본. `kis_template` 실물과 다르다(`date` text · double · 하이퍼테이블 아님 · `trading_records` 없음) |
| `init-scripts/02-multiverse.sql` | `composable_paramset` · `composable_position`(DB 에 없음) · `corp_events` | |
| `init-scripts/03-adj-factor.sql` · `04-corp-events-end-date.sql` · `05-vtr-source-column.sql` | `daily_prices.adj_factor` · `corp_events.end_date` · `vtr.source`(+backfill) | ⚠️ 02~06 헤더의 적용 명령은 `-d robotrader`(옛 이름) |
| `init-scripts/06-phase5-signals.sql` | `foreign_flow_daily` · `vkospi_daily` | **DB 에 없음**(현행은 `foreign_flow`) |
| `scripts/kis_db/schema.py` | `kis_template` 초기 스키마(멱등) · `EXPECTED_TABLES` 16 · `PAPER_STRATEGY_EQUITY_DDL` | 실제 `kis_template` 의 원형. 하이퍼테이블 생성 없음 |
| `db/migrations/20260815_*.sql`(3) · `20260907_sector_news_rerank_log.sql` | `investor_trend_daily` · `credit_balance_daily`+`overtime_daily` · `short_sale_daily`+`program_trade_daily` · `sector_news_rerank_log`(기록용, SSOT 는 코드) | 수동 적용 |
| 런타임 `CREATE TABLE IF NOT EXISTS`(코드) | `db/repositories/trading.ensure_real_table` · `db/repositories/sector_news.RERANK_LOG_DDL` · `db/adj_backup.DDL_SQL` · `collectors/dart_corp_code.py` · `collectors/financial_writer.py`(4표) · `collectors/financial_metrics.py`(`fn_financials_as_of`) · `collectors/sector_writer.py`(4표 + `fn_sector_map_as_of` + 재생성 스냅샷표) · `strategies/lynch/db_manager.py` · `tools/paper_strategy_equity._ensure_table` | 봇 기동·수집기 실행 시 자동 |

봇 기동 시 `db/database_manager._verify_tables` 가 8개 필수 표(`candidate_stocks`·`vtr`·`real_trading_records`·`financial_data`·`quant_factors`·`quant_portfolio`·`daily_prices`·`paper_trading_state`)를 확인하고, `daily_prices` 하이퍼테이블이 없다고 **매번 WARNING**(「Hypertable 미설정」)을 남긴다 — 비치명 · 설계상 정상.

---

## 7. TimescaleDB 현황

```sql
SELECT hypertable_name FROM timescaledb_information.hypertables;   -- 0행 (2026-09-17)
SELECT job_id, proc_name, hypertable_name FROM timescaledb_information.jobs;
```

- **하이퍼테이블 0개.** `daily_prices`·`minute_candles` 전부 평범한 테이블(`scripts/kis_db/schema.py` 가 그렇게 만들었다). 청크·압축·연속집계 없음.
- 잡 2개는 TimescaleDB **내부용**(`policy_telemetry` · `policy_job_stat_history_retention`, 자체 잡 이력 1개월 정리) — 사용자 표 대상 아님.
- 🔴 **retention policy 는 어떤 표에도 절대 걸지 않는다**(`add_retention_policy` 호출 금지 · `drop_chunks` 금지). 자동삭제 0 이 운영 규칙이다. `db/database_manager.cleanup_old_data`(candidate_stocks 90일 DELETE)는 존재하나 **호출자 0**(테스트만).

---

## 8. 명령

```powershell
# 접속 (읽기 전용 점검은 항상 -d kis_template)
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h 127.0.0.1 -p 5433 -U robotrader -d kis_template
# 한 줄 조회
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h 127.0.0.1 -p 5433 -U robotrader -d kis_template -At -c "SELECT count(*) FROM paper_strategy_equity"
# 스키마 확인
\d daily_prices          \d+ virtual_trading_records          \df fn_*
# 백업 / 복원 (custom 포맷)
& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"    -h 127.0.0.1 -p 5433 -U robotrader -d kis_template -F c -f kis_template_YYYYMMDD.dump
& "C:\Program Files\PostgreSQL\16\bin\pg_restore.exe" -h 127.0.0.1 -p 5433 -U robotrader -d kis_template --no-owner kis_template_YYYYMMDD.dump
# 서비스 (관리자)
net stop postgresql-x64-16 ; net start postgresql-x64-16
```

bash(Git Bash)에서는 `PGPASSWORD=… "/c/Program Files/PostgreSQL/16/bin/psql.exe" -h 127.0.0.1 -p 5433 -U robotrader -d kis_template -At -c "…"`. 🔴 봇 가동 중(평일 07:40~) 라이브 DB 에 **쓰기 쿼리·DDL 금지** — SELECT 만.

---

## 9. 규칙

1. **DB 는 `kis_template` 하나.** 코드에 DB명을 적지 말고 `config.constants` resolver 를 거친다. 폐지 env(`KIS_DATA_SOURCE` 등)를 되살리지 말 것.
2. **수동 쓰기 스크립트는 `TIMESCALE_DB` 를 명시**해야 돈다(`require_explicit_target_db`). 기본값을 `kis_template` 으로 «되돌리면» 실수가 라이브 쓰기가 된다 — 일부러 없앤 것.
3. **retention policy·자동삭제 금지.** 보존은 영구.
4. **`adj_factor`**: `close` 에 곱하지 말 것(이미 조정) · `volume` 은 읽기 계층이 곱해 준다(이중조정 금지).
5. **페이퍼 원장** = `virtual_trading_records`(`is_test=true`·`source='kis_template'` 정상) · `profit_loss` 는 gross · 실현손익 보고는 net 로 따로.
6. **분봉 집계는 `trade_date`(PK)** 로. `date` 로 묶지 말 것.
7. **의사티커 `KOSPI`/`KOSDAQ`** 는 `daily_prices` 에 산다 · `KS11`/`KQ11` 은 동결 잔재.
8. 은퇴 DB 삭제 순서: 사장님 결정 → `ALLOW_CONNECTIONS true` → `pg_dump` → `DROP DATABASE robotrader_retired_20260817`.
