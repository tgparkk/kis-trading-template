# 시스템 아키텍처

> kis-template(코드 폴더 `RoboTrader_template/`)의 레이어 구조 · 기동 시 조립 관계 · 패키지 역할 · 의존성 · 설계 원칙.
> **레이어 그림은 이 문서가 정본**이다(다른 문서는 여기로 링크). 모듈·파일 단위 목록은 [code/MODULES.md](code/MODULES.md), 런타임 흐름은 [TRADING_FLOW.md](TRADING_FLOW.md), 설정은 [CONFIGURATION.md](CONFIGURATION.md), DB 는 [DATABASE.md](DATABASE.md).

---

## 레이어 구조

```
┌──────────────────────────────────────────────────────────────────┐
│  strategies/         전략 레이어                                  │
│  BaseStrategy 상속 · on_tick(ctx) / generate_signal() · screener.py │
├──────────────────────────────────────────────────────────────────┤
│  bot/                봇 위임 핸들러 (DayTradingBot 의 팔다리)       │
│  initializer · trading_analyzer · system_monitor · liquidation    │
│  position_sync · state_restorer · candidate_loader · env_guard    │
├──────────────────────────────────────────────────────────────────┤
│  framework/          추상화 레이어                                │
│  KISBroker · DataProvider · OrderExecutor  (api/ 를 감싼다)        │
├──────────────────────────────────────────────────────────────────┤
│  api/                KIS REST 래퍼                                │
│  auth · order · chart · account · market · financial · circuit_breaker │
├──────────────────────────────────────────────────────────────────┤
│  core/               매매 엔진 (위 네 층이 모두 소비)               │
│  TradingContext · TradingDecisionEngine · OrderManager · FundManager │
│  TradingStockManager · PositionMonitor · VirtualTradingManager    │
│  CandidateSelector · regime/ · intraday/                          │
├──────────────────────────────────────────────────────────────────┤
│  db/ · config/ · utils/ · collectors/ · tools/ · runners/   인프라·수집·운영 도구 │
└──────────────────────────────────────────────────────────────────┘
```

읽는 법 두 줄: **전략은 `TradingContext`(core) 와 `framework` 추상화만 보고**, `bot/` 은 `main.DayTradingBot` 이 초기화·분석·감시·청산·복원을 위임하는 핸들러 묶음이라 전략 바로 아래에 둔다. `framework/` 는 `api/` 를 감싸는 얇은 층이고, `core/` 는 그 둘을 소비해 실제 매매 판단·주문·자금·상태를 굴리는 엔진이라 인프라 바로 위에 놓인다(전략·bot·framework 어느 층에서도 import 된다).

---

## 기동 시 조립 (`main.py`, 737줄)

`main()` → `bot.env_guard.assert_correct_environment()` → `DayTradingBot()` → `initialize()` → `run_daily_cycle()`.

```
main()
└── env_guard.assert_correct_environment(루트)   — venv 경로·finance-datareader ≥ 0.9.202 검사, 실패 시 exit 1
DayTradingBot.__init__ (생성 순서 = 의존 순서)
├── check_duplicate_process(PID)                 — utils/price_utils (psutil)
├── load_config()                                — config/trading_config.json → core.models.TradingConfig
├── KISBroker (framework/broker.py)              — 인증·계좌·시세 (api/ 래핑)
├── DatabaseManager (db/database_manager.py)     — Repository Facade (candidate·price·trading·quant·sector_news)
├── TelegramIntegration (core/)                  — key.ini [TELEGRAM] · utils/telegram/telegram_notifier
├── RealTimeDataCollector (core/data_collector)  — 인메모리 실시간 시세 (전략 on_init 의 data_provider)
├── OrderManager (core/order_manager)            — orders/ 믹스인 Facade (실행·감시·타임아웃·DB)
├── IntradayStockManager (core/)                 — 장중 분봉·현재가 캐시 (intraday/)
├── TradingStockManager (core/)                  — 종목 상태(StockState)·PositionMonitor·완료 핸들러
├── TradingDecisionEngine (core/)                — 매수/매도 판단 · VirtualTradingManager · tp/sl 결정
├── FundManager (core/fund_manager)              — 자금·예약·일일 손실 한도 (framework/broker 는 재export 만)
├── bot/ 핸들러: BotInitializer · TradingAnalyzer · SystemMonitor · LiquidationHandler
│               · PositionSyncManager · CandidateLoader
├── _load_strategies()                           — strategies/config.StrategyLoader (trading_config.json strategies[])
├── _allocate_strategy_capital()                 — 가상 자본 격리 + ΣK 한도 정정 (BotInitializer)
├── StateRestorer (bot/)                         — 후보·보유·tp/sl 복원 (전략 로드 뒤 생성)
└── CandidateSelector (core/candidate_selector)  — 전략별 screener_snapshots 소비 · 안전 필터
initialize()
├── BotInitializer.initialize_system()           — API 연결 → 텔레그램 → 자금 → 복원 → regime 대조/프리로드
├── _initialize_strategy() → on_init(...)        — 실패 전략은 제거
├── StateRestorer.apply_pending_strategy_positions() · rescan_orphans_after_init()
└── decision_engine/trading_manager.set_strategies() · set_fund_manager() · set_paper_trading()
run_daily_cycle()
└── _supervised_task × 3 : 메인트레이딩루프(critical) · SystemMonitor · 텔레그램
```

전략이 매 tick 받는 `TradingContext` 는 `main.ctx_for_strategy(폴더키)` 가 전략별로 하나씩 만들어 캐시한다(내부에 trading_manager · decision_engine · fund_manager · data_collector · intraday_manager · trading_analyzer · db_manager · broker 참조).

---

## 패키지 역할 (요약)

파일 단위 표는 **[code/MODULES.md](code/MODULES.md)** 에만 둔다(이 문서와 중복 유지하지 않음).

- **`strategies/`** — `base.py`(`BaseStrategy` · `Signal` · `OrderInfo` · `SignalType`) · `config.py`(`StrategyLoader` · `StrategyConfig`) · `screener_base.py`/`_rule_screener_base.py`(EOD 스크리너 ABC) · 전략 폴더 15개 이상(활성 8 + 예제/템플릿 `sample` `momentum` `mean_reversion` `volume_breakout` `bb_reversion` `lynch` `sawkami` 등). 활성 8전략 스크리너는 전부 `RuleScreenerBase` 상속.
- **`bot/`** — `DayTradingBot` 의 위임 핸들러 9개: `initializer`(시스템 초기화·자본 할당·종료) · `trading_analyzer`(매수/매도 실행 전 검증) · `system_monitor`(5초 루프 · 장전/후장 체인) · `liquidation_handler`(15:00 EOD · 재시도 · 스크리너 스냅샷 훅) · `position_sync` · `state_restorer`(복원·고아 판정) · `candidate_loader`(09:00 후보 로드·폴백) · `env_guard` · `eod_benchmark`.
- **`framework/`** — `broker.py`(`KISBroker` · `Position` · `AccountInfo`) · `executor.py`(`OrderExecutor` · `OrderRequest/Result`) · `data.py` · `data_providers/`(실시간 수집·캐시·표준화·구독) · `utils.py`. `FundManager` 는 여기가 아니라 `core/fund_manager.py` 에 정의되고 `framework/__init__` 이 재export 한다.
- **`api/`** — KIS REST 래퍼 8모듈: `kis_auth`(토큰) · `kis_api_manager` · `kis_order_api` · `kis_chart_api` · `kis_account_api` · `kis_market_api` · `kis_financial_api` · `circuit_breaker`.
- **`core/`** — 매매 엔진 본체. 최상위 20여 모듈(`trading_context` · `trading_decision_engine` · `order_manager` · `fund_manager` · `trading_stock_manager` · `virtual_trading_manager` · `candidate_selector` · `data_collector` · `intraday_stock_manager` · `models` · `telegram_integration` · `screener_snapshot_provider` · `sector_news_rerank` · `post_market_data_saver` · `report_generator` 등) + 서브패키지 `orders/`(실행·감시·타임아웃·DB) · `trading/`(주문 실행·완료 핸들러·`position_monitor`·상태 관리) · `intraday/`(수집·가격 서비스·품질) · `regime/`(시장 분류·국면 게이트·지수 갱신).
- **`db/`** — `connection.py`(코드 기본값 `localhost:5433/kis_template`, user `robotrader`) · `database_manager.py`(Facade) · `repositories/`(base · candidate · price · trading · quant · sector_news) · `kis_db_connection.py` · `quant_daily_reader.py` · `adj_backup.py` · `migrations/`(SQL 4본).
- **`config/`** — `settings.py`(`key.ini` · `trading_config.json` · `INSTANCE_ID`) · `env_bootstrap.py`(`.env` → `os.environ`) · `constants.py`(운영 상수 SSOT) · `market_hours.py`(거래시간·phase·서킷브레이커 상태) · `trading_config.json`.
- **`utils/`** — `logger` · `korean_time` · `korean_holidays` · `holiday_kis_sync` · `price_utils` · `data_sanity` · `indicators` · `tick_tracer` · `telegram/`(봇 명령·알림) 등.
- **`collectors/`** — EOD 수집기 30여 모듈(일봉·분봉·지수·시장매핑·외국인/투자자 수급·기업행위·DART 재무·섹터). `eod_collection.run_data_collection` 이 15:35+ 체인에서 호출.
- **`tools/`** — 운영 도구: `daily_trading_summary`(일일 리포트) · `paper_strategy_equity`(equity 스냅샷) · `gen_inventory` · `gen_archive_candidates`.
- **`runners/`** — `screener_snapshot_collector`(EOD 스냅샷 · CLI 겸용) · `_adapter_factory`(전략명 → 스크리너 어댑터 if/elif 등록) · `_adjacent_grid`.
- **`scripts/` · `backtest/` · `multiverse/`** — 연구·일회성 코드(운영 경로 아님, [CODE_MAP.md](CODE_MAP.md) 의 경계).

---

## 데이터베이스

- **PostgreSQL 16 + TimescaleDB 확장** — Windows 로컬 직접 설치(Docker 아님). **Port 5433**, DB **`kis_template`**, user `robotrader`. 코드 기본값은 `db/connection.py`, 덮어쓰기는 `.env`(`TIMESCALE_*`) → `config/env_bootstrap`.
- 가격 SSOT 는 `kis_template` 단일. 옛 `robotrader` DB 는 `robotrader_retired_20260817` 로 이름이 바뀌고 접속 차단(`datallowconn=false`) 상태다 — `.env` 에 `TIMESCALE_DB=robotrader` 를 두면 죽은 DB 를 가리킨다.
- `daily_prices` 의 가격은 이미 분할 조정값이다(`adj_factor` 를 가격에 곱하지 말 것). 거래량은 원본이라 읽기 계층(`db/repositories/price.py get_daily_prices`)이 `volume × adj_factor` 로 맞춘다.
- 스키마·표 목록 → [DATABASE.md](DATABASE.md) · 통합 경위 → [DB통합_쉬운설명.md](DB통합_쉬운설명.md).

---

## 주요 의존성 (`requirements.txt`)

| 패키지 | 용도 (운영 코드에서 확인된 사용처) |
|--------|------|
| pandas / numpy | 데이터 처리·지표 계산 |
| requests / aiohttp | KIS API HTTP 호출 |
| psycopg2-binary (≥2.9.9) | PostgreSQL 연결 (`db/connection.py`) |
| python-telegram-bot | 텔레그램 봇·알림 (`utils/telegram/telegram_notifier.py`) |
| PyYAML | 전략 `config.yaml` 로드 (`strategies/config.py`) |
| matplotlib | 차트 시각화 |
| psutil | 프로세스 중복 검사 (`utils/price_utils.check_duplicate_process`) — 메모리/CPU 감시 용도 아님 |
| pytz / python-dateutil | KST 시간대 처리 |
| holidays | KRX 휴장일 판정 (`utils/korean_holidays`, `config/market_hours._is_holiday`) |
| finance-datareader (≥0.9.202) | regime 지수(KOSPI/KOSDAQ) 갱신 · 시장 매핑 (`core/regime/index_refresh`, `collectors/`); 구버전은 `bot/env_guard` 가 기동을 막는다 |
| yfinance | 글로벌 시장 대시보드 (`market_dashboard/global_market.py`) |
| beautifulsoup4 | 운영 모듈이 직접 import 하지 않음(연구 스크립트·의존 라이브러리용) |

---

## 설계 원칙

1. **전략-인프라 분리**: 전략은 `TradingContext` 와 `framework/` 추상화만 쓴다. `api/` 직접 import 는 비활성 예제(`lynch` · `sawkami` · `sample` 의 strategy/screener 5파일)에만 남아 있고, 활성 8전략은 위반하지 않는다.
2. **Facade**: `DatabaseManager` 가 `repositories/` 를, `OrderManager` 가 `orders/` 믹스인을 묶는다.
3. **Task Supervisor**: 메인 루프·모니터·텔레그램 3태스크를 지수 백오프 **10 · 20 · 40 · 80초**(4회 대기 · 5번째 실패는 대기 없이 소진 · 상수 상한 300초는 현 설정에서 미도달)로 자동 복구. critical(메인 루프) 소진 시에만 시스템 종료.
4. **가상매매 모드**: `trading_config.json paper_trading: true` 면 `VirtualTradingManager` 가 체결을 시뮬레이션하고 전략별 격리 원장에 기록한다. 실주문 경로(`execute_real_buy/sell`)는 코드가 같은 엔진 안에 있으나 페이퍼에서는 타지 않는다.
5. **플러그인 전략**: `BaseStrategy` 상속 + 폴더 `config.yaml` + `trading_config.json strategies[]` 등록. `generate_signal()` 이 유일한 추상 메서드지만, 후보를 받으려면 `screener.py` + `runners/_adapter_factory.py` 등록이 더 필요하다([STRATEGY_GUIDE.md](STRATEGY_GUIDE.md)).
6. **매도 자금관리 단일화**: 매도 후 `fund_manager` 갱신은 `TradingDecisionEngine.execute_virtual_sell()` 안에서만 한다.
7. **전략 루프 위임**: `on_tick(ctx)` 로 전략이 자기 매매 루프를 소유하고, 프레임워크는 가드(서킷브레이커·VI·급락·국면·소유권·진입 억제)와 백스톱(손절/익절·max_hold·EOD)만 제공한다.
8. **전략별 독립 소유권**: 슬롯·원장·후보 풀이 `(종목, 전략)` 단위로 격리된다 — [OWNERSHIP_MODEL.md](OWNERSHIP_MODEL.md).

---

**기준 코드**: `main` `16a8106` (2026-09-17) · **마지막 갱신**: 2026-09-17
