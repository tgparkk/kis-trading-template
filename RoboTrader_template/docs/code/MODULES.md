# 코드 모듈 가이드 (MODULES)

> CLAUDE.md에서 분리된 **모듈별 상세**입니다. 빠른 개요/라우팅은 [../../CLAUDE.md](../../CLAUDE.md),
> 활성 전략 운영은 [../PAPER_STRATEGIES.md](../PAPER_STRATEGIES.md), 전략 추가 방법은 [../STRATEGY_GUIDE.md](../STRATEGY_GUIDE.md).
> 운영/연구 경계는 [../CODE_MAP.md](../CODE_MAP.md), 연구 파일 태깅은 [../INVENTORY.md](../INVENTORY.md).

> **재생성 2026-09-17** (`16a8106`). 아래 표는 각 디렉토리의 `ls` + `grep -n '^class '` 와 모듈 docstring 을 그대로 옮긴 것이다. 줄번호는 드리프트하므로 심볼명 위주로 적었다.

---

## `main.py` — 진입점 (737줄)

- `DayTradingBot` 클래스가 전체 시스템을 관장. 파일 최상단에서 `config.env_bootstrap.bootstrap()` 으로 repo-root `.env` 를 `os.environ` 에 주입한 뒤 나머지 모듈을 import 한다.
- `main()`: `bot.env_guard.assert_correct_environment()`(올바른 venv 인지 fail-fast) → `DayTradingBot()` → `initialize()`(실패 `exit 1` · `LiveStartupAbort` 는 텔레그램 경보 후 `exit 2`) → `utils.holiday_kis_sync.sync_today()`(KIS 휴장일 1회 동기화) → `run_daily_cycle()`.
- `__init__()`: PID 파일 중복실행 방지 → `load_config()`(`utils/price_utils` → `config.settings.load_trading_config` → `core.models.TradingConfig`) → 핵심 모듈(`KISBroker` → `DatabaseManager` → `TelegramIntegration` → `RealTimeDataCollector` → `OrderManager` → `IntradayStockManager` → `TradingStockManager` → `TradingDecisionEngine` → `FundManager`) → 위임 핸들러(`BotInitializer`·`TradingAnalyzer`·`SystemMonitor`·`LiquidationHandler`·`PositionSyncManager`·`CandidateLoader`) → **`_load_strategies()`** → `_allocate_strategy_capital()`(→ `BotInitializer._allocate_strategy_capital`) → `StateRestorer` → `CandidateSelector`.
- `_load_strategies()`: `config.strategies`(trading_config.json 의 리스트) 가 있으면 **다중 전략 모드** `StrategyLoader.load_strategies(spec)`; 없으면 legacy 단일 `config.strategy`; 둘 다 없으면 「전략 미설정 — fallback 모드」. `StrategyConfigError` 는 critical 로 **재raise(기동 중단)**, `FileNotFoundError`/기타 예외는 경고 후 전략 없이 진행. `self.strategy` = 첫 전략(backward compat).
- `initialize()`: ① `BotInitializer.initialize_system()`(오늘 거래시간 출력 → `broker.connect()` → 시장상태 → `telegram.initialize()` → `_initialize_fund_manager()` → `StateRestorer.restore_todays_candidates()` → `_crosscheck_regime_index_config()` → `_preload_market_mapping()`) ② `_initialize_strategy()`(전략별 `on_init(broker, data_provider, executor)` · 실패 전략은 dict 에서 제거) ③ `StateRestorer.apply_pending_strategy_positions()`(on_init 이 지운 복원 포지션 재주입) ④ `rescan_orphans_after_init()` ⑤ `decision_engine`·`trading_manager` 에 `set_strategy`(첫 전략) + `set_strategies`(전체 맵 — 체결 콜백을 소유 전략으로 라우팅) ⑥ `trading_manager.set_fund_manager`·`set_paper_trading`.
- `run_daily_cycle()`: 3개 태스크를 `_supervised_task` 로 감싸 `asyncio.gather` — **메인트레이딩루프**(critical=True) · **시스템모니터링**(`SystemMonitor.run_system_monitoring_task`, critical=False) · **텔레그램**(critical=False). 감독은 지수 백오프(`min(base·2^(n-1), max)`, 최대 `TASK_SUPERVISOR_MAX_RETRIES`=5회).
- `_main_trading_loop()`: `LOOP_INTERVAL`=3초 · `ON_TICK_EVERY_N`=3 · `ON_TICK_TIMEOUT`=30초. 장 밖이면 30초 sleep. 장 시작 후 최초 1회 `_load_screener_candidates()` + `_call_strategy_market_open()`(**첫 전략만** `on_market_open`). 이후 매 반복:
  1. `[1/5]` `data_collector.collect_once()`
  2. `[2/5]` `order_manager.check_pending_orders_once()`
  3. `[3/5]` `trading_manager.check_positions_once()`(매 반복 — 손절/익절 모니터링)
  4. `[4/5]` 전략 있으면 **라운드로빈 on_tick** — 3번째 반복마다(≈9초) 전략 **1개** 를 골라 `strat.on_tick(ctx_for_strategy(name))` 을 30초 타임아웃으로 실행. 8전략이면 한 전략이 다시 돌아오는 데 **≈72초**. EOD 청산이 끝난 뒤엔 `holding_period == "intraday"` 전략의 on_tick 을 스킵. 전략이 없으면 같은 주기로 `_check_buy_signals()` fallback(매수 판단만).
  5. `[5/5]` `_check_eod_liquidation()`
  각 단계는 독립 try/except(한 단계 실패가 다른 단계를 막지 않음). 반복 소요를 빼고 남은 시간만 sleep.

### main.py 동작 흐름

```
main()
 ├── env_guard.assert_correct_environment
 ├── DayTradingBot.__init__()  — 모듈 조립 · _load_strategies() · _allocate_strategy_capital()
 ├── bot.initialize()          — initialize_system → 전략 on_init → 포지션 재주입 → 전략 연결
 ├── holiday_kis_sync.sync_today()
 └── bot.run_daily_cycle()     — asyncio.gather(메인루프* · 시스템모니터링 · 텔레그램)  (* critical)
       메인루프 3초: [1/5]수집 → [2/5]미체결 → [3/5]보유체크 → [4/5]on_tick 라운드로빈(9초/전략) → [5/5]EOD
       └── finally bot.shutdown()
```

---

## `framework/` — 추상화 레이어

| 파일 | 핵심 클래스 | 역할 |
|------|------------|------|
| `broker.py` | `Position`, `AccountInfo`, `BaseBroker`(ABC), `KISBroker` | 계좌/포지션 조회(`connect`·`get_account_balance`·`get_holdings`·`get_current_price(s)`·`get_ohlcv_data`·`get_index_data` 등). **`FundManager` 는 여기 없다** — `core/fund_manager.py` 에 있고 `framework/__init__.py` 가 re-export 한다 |
| `executor.py` | `OrderType`·`OrderSide`·`OrderStatus`(Enum), `OrderRequest`, `OrderResult`, `Order`, `OrderExecutor` | 매수/매도 주문 실행(동기+비동기). KIS API 호출을 `ThreadPoolExecutor(max_workers=4)` 로 래핑 |
| `data.py` | Facade 모듈 | `data_providers/` 의 `DataProvider`·`RealtimeDataCollector`·`MarketData`·`OHLCV`·`PriceQuote` 등 re-export |
| `data_providers/` | `DataProvider`, `RealtimeDataCollector`, `DataStandardizer`, `CacheManager`, `SubscriptionManager`, `MarketData`(legacy), `OHLCV`·`PriceQuote`(models) | 시세 수집·표준화·캐싱·구독 관리(8모듈: `data_provider`·`realtime_collector`·`data_standardizer`·`cache_manager`·`subscription_manager`·`market_data_legacy`·`models`·`utils`) |
| `utils.py` | 함수 | `now_kst`·`is_market_open`·`get_market_status`·`get_tick_size`·`round_to_tick`·`validate_tick`·`calculate_change_rate`·`format_*`·`setup_logger`·`load_config(config_path)` |
| `__init__.py` | 패키지 export | `KISBroker`·`Position`·`AccountInfo`·`FundManager`(← core)·`OrderExecutor`·`OrderRequest`·`OrderResult`·`OrderType`·`OrderSide`·`OrderStatus`·`DataProvider`·`RealtimeDataCollector`·`OHLCV`·`PriceQuote` + utils 함수 |

---

## `strategies/` — 전략 시스템

| 파일 | 핵심 클래스 | 역할 |
|------|------------|------|
| `base.py` | `SignalType`(Enum), `Signal`, `OrderInfo`, `BaseStrategy`(ABC) | 전략 인터페이스. 추상 메서드는 `generate_signal()` 하나. `on_init`/`on_market_open`/`on_order_filled`/`on_market_close` 는 기본 구현 제공. `async on_tick(ctx)` 기본 구현 = 선정 종목 순회(일봉) 매수 신호 + 보유 종목 순회(분봉) 매도 신호 — 전략이 override 해 루프를 소유할 수 있다. 클래스 속성: `name`·`version`·`holding_period`("intraday"/"swing")·`exit_timeframe`·`max_capital_pct`·`regime_index`(기본 "both")·`regime_gate`(기본 "none")·`max_holding_days`·`accepts_volume_fallback` |
| `config.py` | `StrategyConfigError`, `StrategyConfig`, `StrategyLoader`, `load_yaml_config()` | `strategies/{name}/config.yaml` 로드 + `strategies.{name}.strategy` 를 `importlib.import_module` 로 동적 import(실패 시 파일 경로 로드 폴백) 후 `BaseStrategy` 서브클래스 자동 탐색. `load_strategies(spec 리스트)` 가 다중 전략 진입점 |
| `screener_base.py` | `ScreenerBase`(ABC) | 스크리너 스냅샷 파이프라인 공통 인터페이스 — `scan()` 구현 |
| `_rule_screener_base.py` | `RuleScreenerBase(ScreenerBase)` | 전략 진입룰을 `daily_prices` 유니버스에 적용하는 공통 EOD 스크리너(전략별 `screener.py` 가 상속) |
| `historical_data.py` | 함수 | `kis_template` 에서 과거 데이터를 읽는 stateless 헬퍼 |

### 활성 페이퍼 전략 (라이브 운영)

`config/trading_config.json` `strategies` 8개 전부 `enabled: true`(각 폴더에 `strategy.py`·`screener.py`·`config.yaml`·`README.md`):

`elder_ema_pullback` · `book_envelope_200d` · `daytrading_3methods_breakout` · `minervini_volume_dryup` · `book_pullback_ma20` · `book_pullback_ma5` · `rs_leader`(+`rule.py`·`corp_action_guard.py` — 기업행위 가드, `strategy.py`·`screener.py` 가 import · 모드 `RS_LEADER_CORP_ACTION_MODE` off/shadow/live 는 `config/constants.py` `resolve_rs_leader_corp_action_mode` 해석) · `deep_mr_dev20`(+`rule.py`) → `strategies/{name}/README.md`

- 2026-09-05 부터 **고도화 대상은 3전략**(`book_pullback_ma20`·`minervini_volume_dryup`·`daytrading_3methods_breakout`), 나머지 5는 관측만 — [../plan_2026-09-05_focus3_roadmap.md](../plan_2026-09-05_focus3_roadmap.md).
- `config.yaml` `max_positions`(K) 현재값 ma20 5 · minervini 3 · daytrading 5. **K 상향(10/6/10) 은 2026-09-18 07:40 발효 예정** — [../prereg_2026-09-15_focus3_K_raise.md](../prereg_2026-09-15_focus3_K_raise.md).
- 운영 허브: [../PAPER_STRATEGIES.md](../PAPER_STRATEGIES.md).

### 예제/템플릿 전략 (참고용, 비활성)

`trading_config.json` 에 없어 로드되지 않는다. `StrategyLoader` 형식(`strategy.py` + `config.yaml`)은 갖춘 것:

| 폴더 | 구성(`__init__.py`·`config.yaml`·`README.md` 는 전 폴더 공통 — 생략) | 비고 |
|------|------|------|
| `sample/` | strategy + screener + `multiverse_grid.yaml` | 기본 템플릿 |
| `momentum/` | strategy | |
| `mean_reversion/` | strategy | |
| `volume_breakout/` | strategy | |
| `bb_reversion/` | strategy + screener + `multiverse_grid.yaml` | 볼린저밴드 회귀 |
| `bb_reversion_or/` | strategy + screener + `multiverse_grid.yaml` | `bb_reversion` 의 OR 결합 변형 |
| `lynch/` | strategy + screener + `db_manager.py` | |
| `sawkami/` | strategy + screener + `db_manager.py` | |

### 하위 패키지 (`StrategyLoader` 로드 대상 아님 — 단 `books/` 는 라이브 6전략이 정적 import)

| 패키지 | 내용 | 소비자 |
|------|------|------|
| `books/` | `_base_book_strategy.py`(책 규칙을 단일/AND/OR 로 조합해 Signal 생성) + 책별 19폴더(`aziz_day_trade` … `weinstein_stages`) | 🔴 **라이브 6전략의 `strategy.py`·`screener.py` 12파일이 규칙 모듈을 정적 import** — book_envelope_200d→`trading_strategy_book.rules` · book_pullback_ma20→`haru_silijeon.rules_daily` · book_pullback_ma5→`trading_legends.rules_daily` · daytrading_3methods_breakout→`daytrading_3methods.rules` · elder_ema_pullback→`elder_triple_screen.rules` · minervini_volume_dryup→`minervini_vcp.rules`. **운영 의존 패키지(archive 금지)**. `_base_book_strategy.py` 도 그 6개 `rules*.py` 가 `Rule`·`RuleResult` 를 import 하므로 **간접 운영 의존(archive 금지)**(20/20 `rules*.py` 가 import). 책별 `strategy.py`·`strategy_daily.py`(·`weinstein_stages/weekly.py`)는 운영 import 0(소비자 `scripts/`·`tests/`·`archive/`). 그 외 소비자 `scripts/`·`backtest/`·`tests/` |
| `intraday/` | `_base_intraday.py`(T+0, EOD 15:20 청산, SL 1%/TP 2% 기본) + 11폴더(`orb`·`orb_v2`·`vwap_trade`·`bull_flag` …) | **운영 import 0** — `scripts/run_intraday_tournament.py` · `tests/`(`test_intraday_strategies_part_a/b/c.py`·`test_backtest_engine_minute.py`) · `archive/` |
| `allocation/` | `systrader79_avgmom/`(동적 자산배분·시계열 모멘텀 트랙) | **운영 import 0** — `tests/allocation/test_systrader79_avgmom.py` · `archive/scripts/run_systrader79.py` |

### `Signal` 데이터클래스 (strategies/base.py)
- `signal_type`: `STRONG_BUY`·`BUY`·`HOLD`·`SELL`·`STRONG_SELL`
- `stock_code`(str) · `confidence`(0-100, 기본 0.0) · `target_price` · `stop_loss` · **`entry_min_price`** / **`entry_max_price`**(라이브 체결가가 밴드 밖이면 진입 스킵 — 지정가 하한/상한) · `reasons`(list) · `metadata`(dict)
- 헬퍼: `is_buy()`·`is_sell()`·`is_strong()`·`to_dict()`

---

## `api/` — KIS API 래퍼

`api/__init__.py` 가 아래 8모듈을 그대로 import 한다.

| 파일 | 핵심 클래스 | 역할 |
|------|------------|------|
| `kis_auth.py` | `KISEnv`, `APIResp`, `KisAuth` | 인증/토큰 관리(공식 문서 기반). 속도제한 오류 `EGW00201` **카운터**(`_api_stats['rate_limit_errors']` — 응답 200 비즈니스 오류·HTTP 500 `_is_rate_limit_error` 두 갈래) + **지수 백오프 재시도**(`wait_time = base_delay * (2 ** attempt)` → `time.sleep` 후 재시도 · 누적 10회 초과 시 base 1.5배 · 최대 `_max_retries`) — 사전 호출 제한기는 아님 |
| `kis_order_api.py` | 함수 | 매수/매도/정정/취소 주문 |
| `kis_chart_api.py` | 함수 | 차트(일별분봉) 조회 |
| `kis_account_api.py` | 함수 | 계좌 잔고, 주문가능수량 |
| `kis_market_api.py` | 함수 | 시세 조회(현재가·투자자동향 `get_investor_trend_daily` 등) |
| `kis_financial_api.py` | `FinancialRatioEntry`, `IncomeStatementEntry`, `BalanceSheetEntry` | 재무비율/재무데이터 |
| `kis_api_manager.py` | `OrderResult`, `StockPrice`, `AccountInfo`, `KISAPIManager` | 위 모듈 통합 매니저 |
| `circuit_breaker.py` | `CircuitState`, `CircuitBreakerConfig`, `CircuitBreaker` | KIS API 장애 대응 서킷브레이커 패턴 |

---

## `core/` — 핵심 비즈니스 로직

`core/__init__.py` 는 **주석 1줄뿐**(`# Core modules for day trading system` · 코드·export 없음) — 서브패키지 `orders/`·`trading/`·`intraday/`·`regime/` 의 각 `__init__` 이 export 한다.

| 파일/디렉토리 | 핵심 클래스 | 역할 |
|--------------|------------|------|
| `orders/` | `OrderManagerBase`, `OrderExecutorMixin`, `OrderMonitorMixin`, `OrderTimeoutMixin`, `OrderDBHandlerMixin` | 주문 실행·미체결 모니터링·5분 타임아웃·실전 거래기록 DB 저장(믹스인 5개) |
| `order_manager.py` | `OrderManager` | 위 믹스인을 합친 Facade(하위 호환) |
| `trading/` | `StockStateManager`, `OrderExecution`, `OrderCompletionHandler`, `PositionMonitor` | 종목 상태·주문 실행·체결 후속 처리·보유 종목 손익절 모니터링 |
| `trading_stock_manager.py` | `TradingStockManager` | `trading/` 를 합친 Facade — `check_positions_once()`, `set_strategies()`(체결 콜백 owner 라우팅) |
| `intraday/` | `StockMinuteData`, `IntradayDataCollector`, `RealtimeDataUpdater`, `DataQualityChecker`, `PriceService` | 장중 분봉 수집·실시간 갱신·품질검사·매도판단용 현재가 캐시 |
| `intraday_stock_manager.py` | `IntradayStockManager` | `intraday/` 를 합친 Facade(+`dynamic_batch_calculator`·`post_market_data_saver` 사용) |
| `intraday_data_utils.py` | 함수 | 장중 데이터 검증 유틸(← `intraday/data_collector`·`data_quality`) |
| `regime/` | `DailyRegimeParams`, `IntradayRegimeParams`, `classify_daily`·`classify_intraday`·`regime_at`(export), `RegimeGate`(`regime_gate.py`), `market_classifier.py`(종목→시장·급락게이트 지수 해석·`reset_cache`), `index_refresh.py`(KOSPI/KOSDAQ 일봉 갱신) | 2-트랙 PIT 시장국면 판별 + 라이브 국면 게이트 |
| `trading_context.py` | `TradingContext` | 전략용 안전 API — `get_daily_data`·`get_intraday_data`·`get_current_price`·`get_selected_stocks`·`get_positions`·`buy`·`sell`·`get_available_funds`·`get_max_buy_amount`·`get_total_funds`·`log`. `buy()/sell()` 내부에 서킷브레이커/VI/시장방향 가드 |
| `trading_decision_engine.py` | `TradingDecisionEngine` | 매매 판단 엔진. `set_strategy`/`set_strategies` · `analyze_buy_decision`(전략 있으면 `generate_signal`) · `analyze_sell_decision` · `check_market_direction`(급락게이트) · `check_regime_gate` · `execute_real_buy/sell` · `execute_virtual_buy` · `is_virtual_mode`(= `paper_trading`) |
| `fund_manager.py` | `FundManagerProtocol`, `MockFundManager`, `FundManager` | 자금 관리(가상/실전) — `framework` 가 re-export |
| `virtual_trading_manager.py` | `VirtualTradingManager` | 가상매매(페이퍼) 잔고·매수/매도 |
| `candidate_selector.py` | `CandidateStock`, `CandidateSelector` | 매수 후보 선정(템플릿). `screener_snapshot_provider`·`sector_news_rerank` 를 여기서 사용 |
| `screener_snapshot_provider.py` | `make_screener_snapshot_provider()` | `screener_snapshots` 테이블 → 날짜별 후보 코드 콜백(2026-07-02 `backtest/engine.py` 에서 승격) |
| `sector_news_rerank.py` | `RerankRow` + 순수 함수 | 섹터 뉴스 점수로 후보 재정렬(스펙 B §5.2) — DB·로거·설정 import 0 |
| `data_collector.py` | `RealTimeDataCollector` | 실시간 데이터 수집(`collect_once`) |
| `models.py` | `OrderType`·`OrderStatus`·`PositionType`·`StockState`(Enum), `OHLCVData`, `Stock`, `Order`, `TradingSignal`, `Position`, `TradingStock`, `DataCollectionConfig`·`OrderManagementConfig`·`RiskManagementConfig`·`StrategyConfig`·`LoggingConfig`·`CandidateFiltersConfig`·`TradingConfig` | 데이터 모델 + `trading_config.json` 매핑 |
| `telegram_integration.py` | `TelegramIntegration` | 텔레그램 연동 |
| `price_calculator.py` | `PriceCalculator` | 매수/매도 가격 계산. **운영 import 0**(참조 `tests/test_price_calculator.py`·`tests/verify_imports.py` 뿐) |
| `dynamic_batch_calculator.py` | `DynamicBatchCalculator` | 종목 수에 따른 API 배치 크기·대기 계산 |
| `realtime_candle_builder.py` | `RealtimeCandle`, `RealtimeCandleBuilder` | 현재가 API 로 진행 중 1분봉 생성(← `framework/data_providers/realtime_collector`) |
| `realtime_data_logger.py` | `RealtimeDataLogger` | 장중 수집 데이터 종목별 파일 저장(← `intraday/realtime_updater`) |
| `post_market_data_saver.py` | `PostMarketDataSaver` | 장 마감 후 데이터 저장 |
| `timeframe_converter.py` | `TimeFrameConverter` | 1분봉 → 3/5분봉 변환. **운영 import 0**(소비자 `scripts/book_portfolio_multiverse.py`·archive·tests) |
| `report_generator.py` | 함수 | 성과 리포트 생성(P3-4). **운영 import 0**(참조 `tests/dryrun/test_report_generator.py` 뿐) |
| `trend_momentum_analyzer.py` | `TrendMomentumAnalyzer` | 추세 기반 적응형 청산 분석기 — **미배선**(import 는 `tests/verify_imports.py` 뿐) · 설계 문서 `docs/archive/추세기반_적응형_청산_가이드.md`(DEPRECATED) |

---

## `bot/` — DayTradingBot 위임 핸들러

`main.py` 의 `DayTradingBot` 이 비대해지지 않도록 기능별 분리(`bot/__init__.py` docstring).

| 파일 | 핵심 클래스 | 역할 |
|------|------------|------|
| `initializer.py` | `BotInitializer` | `initialize_system()`(위 main.py 절의 8단계) · `_allocate_strategy_capital()`(가상매매 전략별 자본 할당 + `_apply_total_k_position_limit`) · `_initialize_fund_manager()` · `shutdown()`/`_flush_state_to_db()`/`_cancel_pending_orders()` |
| `trading_analyzer.py` | `TradingAnalyzer` | 매수/매도 판단 분석 |
| `system_monitor.py` | `SystemMonitor` | `run_system_monitoring_task()` — API 24h 갱신 · 30분 포트폴리오 스냅샷/상태 로그 · 프리마켓(`_handle_premarket_tasks`: 전략 대상종목 등록·regime 지수 갱신·`market_dashboard` 브리핑) · **포스트마켓 15:35 이후 1회**(`_handle_postmarket_tasks`: 자금 무결성 검증 → `tools.daily_trading_summary` 출력 → regime 지수 해석 로그 → 스크리너 스냅샷 검증 → `_run_equity_snapshot`(→ `tools.paper_strategy_equity`) → regime 지수 갱신 → `collectors.eod_collection.run_data_collection` → equity 스냅샷 재실행 → `_log_eod_benchmark`(→ `bot/eod_benchmark.py`)) |
| `liquidation_handler.py` | `LiquidationHandler` | 장마감 일괄청산 · `get_last_eod_liquidation_date()` · EOD 스크리너 스냅샷(`runners.screener_snapshot_collector.run_once` 지연 import) |
| `candidate_loader.py` | `CandidateLoader` | 스크리너 기반 후보 로딩 + 거래량 순위 폴백(폴백은 `runners._adapter_factory.build_adapter` 의 `base_filter` 로 컨셉 필터 — 어댑터 없으면 빈 풀, fail-closed) |
| `state_restorer.py` | `StateRestorer` | 재시작 시 DB 에서 오늘 후보·보유 복원, 전략 포지션 재주입(`apply_pending_strategy_positions`)·고아 재훑기 |
| `position_sync.py` | `PositionSyncManager` | `emergency_sync_positions()` — 호출 경로가 `DayTradingBot.emergency_sync_positions()` 뿐이고 그것을 부르는 코드가 없다(**사실상 휴면**) |
| `env_guard.py` | 함수 | 기동 venv 가드(`assert_correct_environment`, 2026-06-30 sibling venv 사고 재발 방지) — `main()` 첫 줄 |
| `eod_benchmark.py` | 함수 | EOD 벤치마크 한 줄(포트 성과 vs KOSPI/KOSDAQ) — `tools.paper_strategy_equity` 의 `DEFAULT_EPOCH`·`SOURCE` 사용 |

---

## `config/` — 설정

| 파일 | 역할 |
|------|------|
| `env_bootstrap.py` | repo-root `.env` 를 표준 라이브러리만으로 파싱해 `os.environ` 에 주입(이미 있는 키는 유지). `main.py` 최상단에서 호출 — `db/connection.py` 의 `TIMESCALE_*`·KIS 키 등이 여기서 발효 |
| `settings.py` | `key.ini` → 환경변수, `trading_config.json` → `TradingConfig`(`load_trading_config`). 인스턴스 분리: `KIS_INSTANCE_DIR` → `INSTANCE_ID`·`CONFIG_FILE`·`TRADING_CONFIG_FILE`·`REAL_TRADING_TABLE`·`TOKEN_FILE`·`LOG_DIR` |
| `constants.py` | 거래 상수 — `TASK_SUPERVISOR_MAX_RETRIES`(5)·`VIRTUAL_CAPITAL_PER_STRATEGY`(10,000,000)·`MAX_CANDIDATES_PER_STRATEGY`(20, 스냅샷·소비 공통 SSOT) · DB 리졸버 `resolve_daily_source_db()`/`resolve_minute_source_db()`/`resolve_corp_events_source_db()`(항상 `kis_template`; 옛 `KIS_DATA_SOURCE` 등 롤백 플래그는 무시) · `require_explicit_target_db()`(쓰기 fail-fast) · `resolve_sector_news_mode`·`resolve_rs_leader_corp_action_mode`(`.env` 플래그 해석) |
| `market_hours.py` | `MarketPhase`(Enum)·`MarketHours`(장 시간·특수일) + `CircuitBreakerState`(종목 VI 2분 자동해제·시장 전체 매매정지 추적, `get_circuit_breaker_state()`·`arm_circuit_breaker_from_info()`) |
| `trading_config.json` | 봇 설정 본체 — `data_collection`·`order_management`·`risk_management`·`strategy`(legacy)·`strategies`(8개)·`duplicate_signal_prevention`·`logging`·`paper_trading`·`rebalancing_mode` |
| `key.ini.example` | `[KIS]`·`[TELEGRAM]` 키 템플릿(실제 `key.ini` 는 미추적) |
| `visualization_strategies.yaml` | `visualization/strategy_manager.py` 전용 차트 전략 설정(봇 미사용) |

설정 항목 설명은 [../CONFIGURATION.md](../CONFIGURATION.md).

---

## `db/` — 데이터베이스

| 파일 | 핵심 클래스 | 역할 |
|------|------------|------|
| `connection.py` | `DatabaseConnection` | TimescaleDB 연결 풀. `TIMESCALE_HOST/PORT/DB/USER/PASSWORD` env, 기본값 `localhost:5433/kis_template/robotrader` |
| `kis_db_connection.py` | `KisDbConnection` | `kis_template` 전용 풀. `KIS_DB_HOST/PORT/NAME/USER/PASSWORD` env, 기본값 동일. 사용자(운영 트리 import 실측) = `collectors/` 10파일(`daily`·`minute`·`index`·`stock_market`·`foreign_flow`·`corp_events`·`financial`·`sector` 수집기 + `corp_action_watch`·`split_factor_infer`) · `core/regime/market_classifier.py` · `tools/paper_strategy_equity.py`(`_KisTemplateDailyReader` 종가 읽기만 — 레코드 로드·적재 conn 은 별도, tools/ 표 참조) · 연구 `scripts/` 9파일(`kis_db/schema.py`·`repair_corp_action_prices.py` 등)은 별도 |
| `database_manager.py` | `CandidateRecord`, `DatabaseManager` | Facade — `CandidateRepository`·`PriceRepository`·`TradingRepository(real_table_name=REAL_TRADING_TABLE)`·`QuantRepository`·`SectorNewsRepository` 조합. 테이블은 **존재 확인만**(생성은 `init-scripts/01-init.sql`) |
| `repositories/` | `BaseRepository`, `CandidateRepository`, `PriceRepository`(+`PriceRecord`), `TradingRepository`, `QuantRepository`, `SectorNewsRepository` | 기능별 접근 클래스. `sector_news.py` 는 `sector_news_score` 읽기 + 재정렬 기록 쓰기 |
| `quant_daily_reader.py` | `QuantDailyReader` | `daily_prices` 읽기 전용 리더(스크리너 유니버스·일봉) — 대상 DB 는 `resolve_daily_source_db()` |
| `adj_backup.py` | 함수 | 기업행위 가격 보정 전 원본 스냅샷(소비자 `scripts/repair_corp_action_prices.py`) |
| `config.py` | `DatabaseConfig` | dataclass 설정(기본 port **5432**). **운영 import 0** — 실제 연결은 위 두 파일의 env 직접 읽기 |
| `migrations/` | SQL 4본 | `20260815_credit_and_overtime` · `20260815_investor_trend_daily` · `20260815_short_sale_and_program_trade` · `20260907_sector_news_rerank_log`(수동 적용 · 자동 마이그레이션 없음) |

스키마 상세는 [../DATABASE.md](../DATABASE.md), DB 통합 배경은 [../DB통합_쉬운설명.md](../DB통합_쉬운설명.md).

---

## `utils/` — 유틸리티

| 파일 | 역할 |
|------|------|
| `korean_time.py` | `now_kst`·`is_market_open`·`is_before_market_open`·`get_market_status`·`get_previous_trading_day` |
| `korean_holidays.py` | 공휴일 캘린더 |
| `holiday_kis_sync.py` | KIS `chk-holiday` 기반 휴장일 동기화(하루 1회, `sync_today`) — 런타임 휴일셋 |
| `logger.py` | 싱글톤 파일 핸들러 — `config.settings.LOG_DIR` 에 `trading_YYYYMMDD.log`; **pytest 가 `sys.modules` 에 있으면 `test_trading_` 접두사로 분리**(dryrun 등 pytest 밖 실행은 분리되지 않는다) |
| `rate_limited_logger.py` | `RateLimitedLogger` — 동일 메시지 반복 로깅 제한 |
| `price_utils.py` | `round_to_tick`·`check_duplicate_process`(PID)·`load_config()`(→ `settings.load_trading_config`) |
| `async_helpers.py` | ThreadPoolExecutor 호출 타임아웃 등 비동기 헬퍼 |
| `exceptions.py` | `LiveStartupAbort` — 실전 기동 중단 예외 |
| `indicators.py` / `intraday_indicators.py` | 일봉/분봉 기술적 지표(pure function) |
| `intraday_universe.py` | 분봉 데이트레이딩용 일별 동적 universe 빌더 |
| `minute_cache.py` | `MinuteCache` — 분봉 Parquet 디스크 캐시(`cache/minute/{date}/{code}.parquet`) + LRU |
| `unified_data_loader.py` | `UnifiedDataLoader` — DB(`PriceRepository`) 기반 통합 로더(`cache/daily`) |
| `data_sanity.py` | 일봉 위생 — 물리적으로 불가능한 봉 탐지(2026-08-15 감사) |
| `tick_tracer.py` | `TickTracer` — on_tick 이벤트 JSONL 로거(`logs/tick_trace/`) |
| `chart_cli.py` / `signal_replay_utils.py` | `visualization/` 소비 CLI·리플레이 헬퍼(봇 미사용; `signal_replay_utils` 는 import 하는 곳 0) |
| `telegram/telegram_notifier.py` | `TelegramNotifier` — 텔레그램 알림 전송 |

---

## `collectors/` — EOD 데이터 수집 (33파일)

`collectors/eod_collection.py` `run_data_collection(trade_date)` 가 `bot/system_monitor.py` 포스트마켓에서 호출되며, 각 수집기를 `_safe()` 로 예외 격리해 순서대로 돈다: `daily → minute → index → stock_market → foreign_flow → corp_events → financials(+reconcile) → sector(+reconcile) → investor_trend → program_trade → short_sale → credit_balance → overtime`, 끝에 `core.regime.market_classifier.reset_cache`.

| 구분 | 파일 | 역할(docstring 요지) |
|------|------|------|
| 오케스트레이터 | `eod_collection.py` | 위 순서 실행, 단계별 예외 격리 |
| | `daily_collector.py` | 일봉 — KIS fetch → `daily_prices` UPSERT → 파생 → adj |
| | `minute_collector.py` | 분봉 — top300 → 당일 분봉 → `minute_candles` |
| | `index_collector.py` | 지수 일봉 — KIS 업종 일봉(기본)/FDR 폴백 → `index_daily` |
| | `stock_market_collector.py` | 종목→시장(KOSPI/KOSDAQ) — FDR → `stock_market` |
| | `foreign_flow_collector.py` | 외국인 순매매량 — 네이버 → `foreign_flow` |
| | `corp_events_collector.py` | `corp_events` 증분 수집 + reconcile — OpenDART(연구 트리 미import) |
| | `financial_collector.py` | 재무 — DART as-filed 원장 + KIS 분기비율 |
| | `sector_collector.py` | 섹터 명부·성적표·이름표 + reconcile + 수동 CLI |
| | `investor_trend_collector.py` | 종목별 투자자 매매동향 → `investor_trend_daily`(KIS `FHKST01010900`) |
| | `market_flow_collector.py` | 공매도·프로그램매매·신용잔고·시간외 단일가 → `short_sale_daily`/`program_trade_daily` 등 |
| fetcher | `dart_company_fetcher.py` · `dart_financial_fetcher.py` · `dart_corp_code.py` | DART company.json / fnlttSinglAcntAll 최소 클라이언트 · corp_code↔stock_code 매핑 |
| | `kis_financial_fetcher.py` | KIS 재무비율(분기) — 접수일 없음 ⇒ PIT 앵커 없음 |
| | `foreign_flow_fetcher.py` | 네이버 외국인 순매매 fetch(2026-07-02 scripts 에서 승격) |
| | `krx_desc_cache.py` | KRX 상장목록 캐시 CSV 날짜 지정 읽기 |
| writer | `daily_writer.py` · `minute_writer.py` · `index_writer.py` · `stock_market_writer.py` · `foreign_flow_writer.py` · `financial_writer.py` · `sector_writer.py` | 각 소스 → `kis_template` UPSERT(재무·섹터는 「DB 쓰기는 이 파일 한 곳뿐」) |
| 파생·보정 | `daily_derived.py` | returns/volatility 파생 갱신 |
| | `daily_adj.py` · `adj_factors.py` · `split_factor_infer.py` | `corp_events` 분할 → `adj_factor` 계산·갱신(`adj_factors.py` 만 2026-07-02 `44c0054` scripts 승격 · `daily_adj.py` 2026-06-23 `4b541a9` · `split_factor_infer.py` 2026-07-06 `47b6417` 신규) |
| | `adj_repair.py` · `corp_action_watch.py` | 기업행위 가격 보정 순수 계산 · 미조정 이력 탐지(큐 적재만) |
| | `financial_metrics.py` | account_id → 13지표 + as_of 기준 Wide 파생 |
| | `minute_universe.py` | 분봉 유니버스 — 거래대금 top300, 6가격밴드×2시장 |

데이터 계층 설명은 [../DATA_MANAGEMENT.md](../DATA_MANAGEMENT.md).

---

## `signals/` — Phase 5 시그널 (2파일)

| 파일 | 역할 |
|------|------|
| `foreign_flow.py` | 외국인 5일 누적 순매매량 시그널(F-06) |
| `vkospi.py` | VKOSPI 시그널(S2-01) |

운영 디렉토리로 분류돼 있으나 **운영 import 0**(소비자 = `scripts/multiverse4_returns_export.py`·`tests/`).

---

## `tools/` — 운영 도구 (모듈 4 + docstring 뿐인 `__init__.py`)

| 파일 | 역할 | 라이브 import |
|------|------|------|
| `daily_trading_summary.py` | 일일 매매 판단·수익률 요약(`print_today_trading_summary`) | `bot/system_monitor.py` 포스트마켓 |
| `paper_strategy_equity.py` | 전략별 일별 equity(`virtual_trading_records` 리플레이 + mark-to-market) → `paper_strategy_equity` 적재(`run_daily_equity_snapshot(conn)` — conn 은 호출측이 넘김: 봇은 `DatabaseConnection.get_connection()`, CLI `main()` 은 자체 `psycopg2.connect`+`TIMESCALE_*` env(풀 미사용) · 보유평가 종가만 `_KisTemplateDailyReader` 가 `KisDbConnection` 으로 읽음). 🔴 `_ensure_table()` 이 `scripts.kis_db.schema.PAPER_STRATEGY_EQUITY_DDL` 을 import — **유일한 라이브→연구 엣지**([../CODE_MAP.md](../CODE_MAP.md)) | `bot/system_monitor.py` `_run_equity_snapshot` · `bot/eod_benchmark.py` |
| `gen_inventory.py` | `scripts/`·`multiverse/`·`backtest/` AST import 그래프 → [../INVENTORY.md](../INVENTORY.md) | 없음(개발 도구) |
| `gen_archive_candidates.py` | INVENTORY 의 UNREFERENCED(scripts/) 재검증 → archive 후보 | 없음(개발 도구) |

---

## `runners/` — 러너 (4파일 · 빈 `__init__.py` 포함)

| 파일 | 역할 | 라이브 import |
|------|------|------|
| `screener_snapshot_collector.py` | 전략별 스크리너 실행 → `screener_snapshots` 저장(CLI `--strategies/--date/--max-candidates/--dry-run`, `run_once()` 재사용) | `bot/liquidation_handler.py` EOD 지연 import |
| `_adapter_factory.py` | 스크리너 어댑터 인스턴스 생성 공통 유틸(`build_adapter`) | `bot/candidate_loader.py` 지연 import |
| `_adjacent_grid.py` | Stage 1 → Stage 2 인접 격자 생성기(`build_adjacent_grid`) | 없음 — 참조 `tests/test_adjacent_grid.py` 뿐(연구 전용) |
| `__init__.py` | 빈 패키지 | |

---

## 테스트 구조

- `tests/` — `test_*.py` **372개**, 하위 폴더 **25개**(`allocation/`·`api/`·`books/`·`bot/`·`collectors/`·`db/`·`discovery/`·`dryrun/`·`exit_multiverse/`·`feature_edge/`·`fixtures/`·`healthcheck/`·`kis_db/`·`regime/`·`rs_leader/`·`strategies/`·`test_config/`·`test_framework/`·`test_kis_api/`·`test_scripts/`·`test_strategies/`·`test_strategy/`·`test_trading/`·`test_utils/`·`tools/`), 공통 fixture `tests/conftest.py`. 평면 `tests/test_<name>.py` 와 폴더형 둘 다 현행 규약.
- **pytest 설정은 레포 루트 `pyproject.toml`**(`RoboTrader_template/pyproject.toml` 은 ruff 전용): `testpaths = ["RoboTrader_template/tests"]` · `asyncio_mode = "auto"` · 마커 `slow`(DB 대량 조회 등) · `db`(실 DB `kis_template @ localhost:5433` 필요 — 없으면 skip, 기준선 실패 집합 비교에서 제외).
- `tests/verify_imports.py` — 전 모듈 import 검증 스크립트(위 `core/` 표의 「미배선」 판정 근거).
- `tests/dryrun/` — `run_dryrun.py` → `DryRunBot`(`dry_run_bot.py`, 실제 시장 데이터로 흐름을 돌리되 주문만 `MockOrderManager` 로 대체) · `dryrun_broker.py` + `test_full_cycle.py`·`test_abnormal_scenarios.py`·`test_report_generator.py`. `tests/healthcheck/run_healthcheck.py` — 설정·로그 디렉토리·패키지·**실 DB 연결**(`DatabaseConnection.initialize()` 후 `SELECT 1`) 점검.

실행 예(🔴 **워크트리에서** — 아래 참조):
```bash
cd RoboTrader_template                                  # 워크트리의 RoboTrader_template
<python> -m pytest tests -q -m "not db"                 # 실 DB 없이 (마커는 루트 pyproject 가 자동 적용)
<python> -m pytest tests -q                             # db 마커 포함 (kis_template 5433 필요)
```
`<python>` — 워크트리엔 `venv/` 가 **없다**(`.gitignore` `venv/` · 미추적)이므로 `venv\Scripts\python` 은 그대로 치면 실패한다(우회하려고 라이브 트리에서 돌리면 아래 규칙 위반). 라이브 트리 venv 인터프리터의 절대경로(`D:/GIT/kis-trading-template/RoboTrader_template/venv/Scripts/python.exe`)를 쓰되 **cwd 는 워크트리**로 — 인터프리터·site-packages 를 읽기만 하며, 그 venv 는 `.pth` 로 라이브 트리 경로를 `sys.path` 에 넣지 않는다(2026-09-17 실측 `distutils-precedence.pth` 뿐). `bot/env_guard.py` 의 venv 검사(`sys.prefix` == `<project_root>/venv`)는 `main.py` `main()` 에서만 호출되므로 pytest 엔 걸리지 않는다. 시스템 Python 3.9.13 에도 pytest 8.4.2·pandas 2.2.3 는 있으나 나머지 의존성 동일성은 미확인.

🔴 **라이브 트리(`D:/GIT/kis-trading-template`)에서 돌리지 말 것** — 워크트리에서만. 이유(코드 실측):
- `python tests/dryrun/run_dryrun.py` 는 pytest 가 아니라서 `utils/logger.py` 의 `test_trading_` 분리가 안 걸리고 **`trading_YYYYMMDD.log` 에 직접 섞인다**(`DryRunBot` 이 `setup_logger("dryrun")` 사용).
- `tests/healthcheck/run_healthcheck.py` 는 **라이브 DB 풀**(`DatabaseConnection.initialize()`)을 연다.
- pytest 도 collection 시점에 싱글톤 핸들러가 `logs/` 아래 파일을 만든다(접두사만 다르다). 라이브 트리 테스트 금지·장중 브랜치 전환 금지는 운영 규칙이다.
