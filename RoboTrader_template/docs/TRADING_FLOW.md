# 매매 흐름 (Trading Flow) — 정본 런타임 흐름 문서

> `main.py` 를 기준으로 **기동 → 메인 루프 → 하루 타임라인 → 매수/매도 경로 → 감독/종료** 를 코드 그대로 적은 문서.
> 근거 파일: `main.py` · `bot/initializer.py` · `bot/liquidation_handler.py` · `bot/system_monitor.py` · `bot/state_restorer.py` · `bot/candidate_loader.py` · `core/trading_context.py` · `core/trading_decision_engine.py` · `core/trading/position_monitor.py` · `config/market_hours.py` · `config/constants.py` · `utils/telegram/telegram_notifier.py`.
> 숫자(초·시각·횟수)는 전부 위 파일에서 읽은 값이다. 옛 `SYSTEM_FLOW.md` 는 `docs/archive/` 로 내렸고(2026-09-17), 이 문서가 그 자리를 대신한다.
> 운영 설정(전략 on/off·자본)은 [PAPER_STRATEGIES.md](PAPER_STRATEGIES.md), 소유권 규칙은 [OWNERSHIP_MODEL.md](OWNERSHIP_MODEL.md), 모듈 목록은 [code/MODULES.md](code/MODULES.md).

---

## 0. 한눈에

```
07:40  Windows 작업 스케줄러 → run_robotrader.bat → python main.py   (평일 자동 · 수동 기동 불필요)
  │     env_guard → DayTradingBot.__init__ → initialize() → run_daily_cycle()
  │
  ├─ 장외(09:00 전 · 15:30 후)  메인 루프는 30초 idle · SystemMonitor 5초 루프는 계속 돈다
  ├─ 09:00  첫 반복: 스크리너 스냅샷(D-1) 소비 → 후보 등록 → on_market_open()
  ├─ 09:00~15:30  3초 루프 5단계 (수집 → 미체결 확인 → 보유 체크 → on_tick 라운드로빈 → EOD 체크)
  ├─ 09:00~09:05  손절 판정 정지(익절만)
  ├─ 15:00  EOD 일괄청산(swing 전략 보유분은 건너뜀) → on_market_close()
  ├─ 15:20  마감 동시호가 → can_place_order() False (매수·매도 주문 차단, EOD force 만 예외)
  ├─ 15:35+ SystemMonitor 후장 체인(리포트 → equity 스냅샷 → EOD 데이터 수집 → 재스냅샷 → 벤치마크)
  └─ 자동 종료 없음 — SIGINT/SIGTERM · 텔레그램 /stop · critical 태스크 재시도 소진 시에만 shutdown()
```

---

## 1. 기동 (Startup)

### 1.1 `main()` 진입

| 순서 | 코드 | 하는 일 |
|---|---|---|
| 1 | `bot.env_guard.assert_correct_environment(프로젝트 루트)` | `sys.prefix` 가 `<루트>/venv` 인지, `finance-datareader >= 0.9.202` 인지 검사. 실패 시 stderr 출력 후 `sys.exit(1)`. `ALLOW_FOREIGN_VENV=1` 이면 경고만 |
| 2 | `DayTradingBot()` | 아래 1.2 |
| 3 | `await bot.initialize()` | 아래 1.3. `False` → `sys.exit(1)`. 실전 모드에서 `LiveStartupAbort` → 텔레그램 긴급 경보 후 `sys.exit(2)` |
| 4 | `utils.holiday_kis_sync.sync_today()` | KIS `chk-holiday` 휴장일 동기화(하루 1회 캐시 가드 · 실패해도 경고만) |
| 5 | `await bot.run_daily_cycle()` | §2 |

`.env` 는 그보다 앞서 `config.env_bootstrap.bootstrap()` 이 `os.environ` 으로 올린다(`main.py` 상단, config/db import 보다 먼저).

### 1.2 `DayTradingBot.__init__` — 생성 순서 (의존 순서 고정)

```
INSTANCE_ID 읽기 → PID 파일 이름 결정 (default → robotrader.pid · 그 외 robotrader_{id}.pid)
check_duplicate_process(pid)           ← 중복 기동 차단
load_config()                          ← config/trading_config.json → TradingConfig
KISBroker → DatabaseManager → TelegramIntegration → RealTimeDataCollector
→ OrderManager → IntradayStockManager → TradingStockManager → TradingDecisionEngine
trading_manager.set_decision_engine(decision_engine)
FundManager(max_daily_loss_ratio = config.risk_management.max_daily_loss)  → order_manager.set_fund_manager()
bot/ 핸들러: BotInitializer · TradingAnalyzer · SystemMonitor · LiquidationHandler · PositionSyncManager · CandidateLoader
_load_strategies()                     ← 아래
_allocate_strategy_capital()           ← BotInitializer 위임 (가상모드 자본 격리 + ΣK 한도 정정)
StateRestorer(... strategies=self.strategies)   ← 전략 로드 «뒤» 에 생성해야 참조 전달 가능
CandidateSelector(config, broker, db_manager)
signal.signal(SIGINT / SIGTERM → _signal_handler: is_running=False)
```

**`_load_strategies()`**

- `config.strategies`(= `trading_config.json` `strategies[]`)가 비어 있지 않으면 → `StrategyLoader.load_strategies(spec)` — `enabled: true` 항목만 로드하고 spec 의 `max_capital_pct` · `regime_index` · `regime_gate` 로 인스턴스 속성을 덮어쓴다. 키는 **폴더명**(`{폴더키: 인스턴스}`).
- `strategies[]` 가 비어 있을 때만 legacy `strategy.name` 단일 로드(`enabled: false` 면 전략 없음).
- `self.strategy` = 첫 전략(하위호환용). `on_market_open/close` 는 이 **첫 전략에게만** 간다(§3.2).
- `StrategyConfigError` 는 critical 로그 후 **재raise(기동 중단)**. `FileNotFoundError`·기타 예외는 경고 후 전략 없음(fallback 모드).

**`_allocate_strategy_capital()`** (`bot/initializer.py`)

- 가상모드 + 전략 있음 + VTM 가능일 때 전략마다 `VIRTUAL_CAPITAL_PER_STRATEGY = 10,000,000` 원을 격리 할당, `max_positions` = 각 전략 `config.yaml` `risk_management.max_positions`(K).
- 모드 무관: ΣK 로 `fund_manager.max_position_count = max(기존 20, ΣK)` 정정(좁아지지 않음). K 미상 전략은 합산 제외 + WARNING.

### 1.3 `initialize()` → `BotInitializer.initialize_system()` 단계

| 단계 | 코드 | 비고 |
|---|---|---|
| 0 | `MarketHours.get_today_info('KRX')` 로그 | 오늘 거래시간 배너(특수일 반영) |
| 1 | `broker.connect()` | KIS 인증/토큰. 실패 → `initialize_system` False → exit 1 |
| 2 | `get_market_status()` 로그 | |
| 3 | `telegram.initialize()` | `key.ini [TELEGRAM]` 의 `enabled/token/chat_id`. 비활성은 오류 아님 |
| 3.5 | `_initialize_fund_manager()` | 가상: VTM 이월 잔고(0 이면 1천만 폴백). 실전: `trading_config.json real_total_funds_cap` 필수 · `min(cap, 실계좌 총평가)` · 미설정/0 이면 `LiveStartupAbort` |
| 4 | `state_restoration_helper.restore_todays_candidates()` | `candidate_stocks` 오늘 행 복원 + 보유 복원(가상: `_restore_holdings_from_db` / 실전: `_restore_holdings_from_real_account`). 복원 tp/sl 이 NULL/NaN 이면 `DEFAULT_*` 적용 · 보유 30일↑ `is_stale=True` |
| 5 | `_crosscheck_regime_index_config()` | 급락게이트 `regime_index` 설정 대조 로그 |
| 6 | `_preload_market_mapping()` | `regime_index="auto"` 용 종목→시장 매핑 프리로드 |

이어서 `main.initialize()` 가:

1. `_initialize_strategy()` — 전략마다 `on_init(broker, data_provider=data_collector, executor=order_manager)`. False/예외 전략은 `strategies` dict 에서 **제거**(시스템은 계속).
2. `state_restoration_helper.apply_pending_strategy_positions()` — `on_init` 이 `self.positions={}` 로 지운 복원 포지션을 `sync_positions()` 로 재주입(반드시 on_init «뒤»).
3. `state_restoration_helper.rescan_orphans_after_init()` — on_init 실패로 빠진 전략의 보유분을 ERROR 로 노출(기동은 막지 않음).
4. `decision_engine.set_strategy(첫 전략)` + `set_strategies(dict)` · `trading_manager.set_strategy` + `set_strategies` — 체결 콜백·소유 표기를 소유 전략으로 라우팅.
5. `trading_manager.set_fund_manager(fund_manager)` · `set_paper_trading(decision_engine.is_virtual_mode)`.

`is_virtual_mode` 는 `trading_config.json` 의 `paper_trading`(기본 True)에서 온다.

---

## 2. 메인 루프

### 2.1 `run_daily_cycle()` — 감독 태스크 3개

| 태스크 | 팩토리 | critical |
|---|---|---|
| 메인트레이딩루프 | `_main_trading_loop` | **True** |
| 시스템모니터링 | `system_monitor.run_system_monitoring_task` | False |
| 텔레그램 | `_telegram_task`(봇 폴링 + 주기 상태 알림) | False |

셋을 `_supervised_task` 로 감싸 `asyncio.gather` — 끝나면(어떤 이유든) `finally: shutdown()`.

### 2.2 `_main_trading_loop()` — 3초 루프 5단계

`main.py` 로컬 상수: `LOOP_INTERVAL = 3` · `ON_TICK_EVERY_N = 3` · `ON_TICK_TIMEOUT = 30`.

```
while is_running:
    if not is_market_open():  sleep(30); continue      ← 장외 idle (종료 아님)
    if not _candidates_loaded:                          ← 09:00 첫 반복 1회
        _load_screener_candidates(); _call_strategy_market_open()
    iteration += 1
    [1/5] data_collector.collect_once()                 ← 보유/관심 종목 현재가·분봉 갱신
    [2/5] order_manager.check_pending_orders_once()     ← 미체결 확인·타임아웃 (order_monitor 믹스인)
    [3/5] trading_manager.check_positions_once()        ← PositionMonitor: 체결완료 확인 → 현재가 갱신 → 매도 판정 → 미저장 매도 재시도
    [4/5] iteration % 3 == 0 이면 전략 «한 개» 의 on_tick(ctx)   ← 라운드로빈
    [5/5] _check_eod_liquidation()
    sleep(max(0, 3 - elapsed))
```

각 단계는 독립 `try/except` — 한 단계 실패가 다음 단계를 막지 않는다.

**[4/5] on_tick 라운드로빈**

- 9초(3반복)마다 `idx = (iteration // 3) % len(strategies)` 번째 전략 **하나만** 호출. 8전략이면 각 전략은 약 72초에 한 번 차례가 온다.
- 호출은 `asyncio.wait_for(strat.on_tick(ctx), timeout=30)` — 30초 초과는 ERROR 로그 후 다음 반복. `ctx` 는 `ctx_for_strategy(폴더키)` 가 전략별로 캐시한 `TradingContext`.
- 오늘 EOD 청산이 끝났고 전략이 `holding_period == "intraday"` 이면 on_tick 스킵(재매수 방지).
- 전략이 하나도 없으면 폴백 `_check_buy_signals()`(9초마다 · SELECTED 순회 · `TradingAnalyzer` 직접 호출).

**[2/5] 주문 타임아웃**: `trading_config.json order_management.buy_timeout_seconds = 300` · `sell_timeout_seconds = 180` (`core/orders/order_executor.py` 가 읽음).

### 2.3 종목 상태 (`core/models.StockState`)

```
SELECTED ──매수주문──→ BUY_PENDING ──체결──→ POSITIONED ──매도판정──→ SELL_CANDIDATE ──주문──→ SELL_PENDING ──체결──→ COMPLETED
                           └─취소/실패→ FAILED
```

슬롯은 `(종목코드, owner 전략)` 쌍이 단위다 — 같은 종목을 여러 전략이 각자 보유할 수 있다([OWNERSHIP_MODEL.md](OWNERSHIP_MODEL.md)).

---

## 3. 하루 타임라인

### 3.1 07:40 자동 기동

- Windows 작업 스케줄러 `\RoboTrader_AutoStart` → `run_all_robotraders.bat` → `run_robotrader.bat`(평일). 사장님이 켤 필요 없다.
- `run_robotrader.bat` 는 `SCREENER_SNAPSHOT_ENABLED=true` · `PYTHONIOENCODING=utf-8` 를 세팅하고 `python -X utf8 main.py` 의 stdout/stderr 를 `logs/robotrader_template_YYYYMMDD_HHMMSS.log` 로 리다이렉트한다(콘솔 캡처라 블록 버퍼링 — 실행 중 0바이트로 보일 수 있음). 애플리케이션 로그(`logs/trading_*.log`)는 `utils/logger` 가 따로 쓴다.
- 기동 직후 09:00 까지 메인 루프는 30초 idle. `SystemMonitor` 는 5초 루프로 장전 작업을 한다(3.7).

### 3.2 09:00 — 첫 반복

`main._main_trading_loop` 첫 반복 — 1·2 는 `_load_screener_candidates()`(`bot/candidate_loader.py`) 안이고, 3 은 루프가 그 다음 줄에서 따로 호출한다:

1. `liquidation_handler.run_screener_snapshot_hook()` — `SCREENER_SNAPSHOT_ENABLED` 일 때 **하루 1회** `runners/screener_snapshot_collector.run_once(활성 전략, scan_date=직전 거래일, max=20)` 로 `screener_snapshots` 를 만든다(당일 일봉은 15:35+ 에야 적재되므로 D-1 기준). 텔레그램 `[스크리너 스냅샷] …` 알림.
2. 다중 전략(2개↑)이면 `_load_candidates_multi_strategy(max_candidates)` — `max_candidates` 는 `trading_config.json` `strategy.parameters.max_candidates`(현재 **10**), 그 키가 없을 때만 `MAX_CANDIDATES_PER_STRATEGY = 20`. 스냅샷 «생성»(1항 hook)은 20, «소비»는 10 이라 **스냅샷 11~20위는 라이브에서 쓰이지 않는다**:
   - `CandidateSelector.select_candidates_per_strategy` → 전략마다 **자기 `screener_snapshots`(D-1) 만** 조회(`_fetch_candidates_for_strategy`). 0건이면 그 전략은 그날 미진입(정상). 조회 «고장»은 fail-closed(다른 명단으로 대체 안 함).
   - 안전 필터(거래정지·VI·관리종목·정리매매) → `add_selected_stock(owner_strategy=폴더키)`.
   - **전 전략이 0건일 때만** 거래량 순위 폴백(ERROR 로그) — `accepts_volume_fallback=True` 인 첫 전략에 그 전략 스크리너 `base_filter` 를 적용해 배정.
3. `_call_strategy_market_open()`(`main.py` · candidate_loader 가 아니라 메인 루프가 호출) → **첫 전략(`self.strategy`)의 `on_market_open()` 만** 호출된다(다른 전략은 받지 않음).

### 3.3 09:00~09:05 — 손절 판정 정지

`PositionMonitor._analyze_sell_for_stock` 은 `hour == 9 and minute < 5` 동안 손절(및 stale 손절)을 건너뛴다. 익절·max_holding·전략 매도 신호는 그대로. 주문 자체는 09:00 부터 가능하다 — `opening_protection` 구간은 `can_place_order()` 가 차단하지 않는다(`config/market_hours.py` 헤더 주석).

### 3.4 장중 — 3초 루프 (§2.2) + 5초 모니터

### 3.5 15:00 — EOD 일괄청산 (`_check_eod_liquidation` → `LiquidationHandler`)

- 시각: `MarketHours.is_eod_liquidation_time()` — KRX 기본 `eod_liquidation_hour=15, minute=0`(특수일 config 로 바뀔 수 있음 · 예: 2025-11-13 수능일 16:00). 평일만 · 하루 1회(`_last_eod_liquidation_date`).
- `execute_end_of_day_liquidation()`: POSITIONED 전 종목 순회 → owner 전략의 `should_liquidate_eod(code)` 가 False 면 **건너뜀**(기본 구현 = `holding_period == "intraday"` 만 True). **라이브 8전략은 전부 `holding_period="swing"`** 이라 실제 청산 0건이 정상이다. intraday 보유분은 가상: `execute_virtual_sell(마지막 분봉 종가)` / 실전: `move_to_sell_candidate` → `execute_sell_order(market=True, force=True)`.
- 실패 종목은 `(코드, owner)` 로 `_eod_failed_stocks` 에 남고, 메인 루프가 **10초 간격**으로 `retry_failed_eod_liquidation()` — `EOD_LIQUIDATION_MAX_RETRIES = 3` 회 초과 시 `_force_complete_failed_stocks()`: 상태 **COMPLETED 강제** + 자금 회수 + **`[CRITICAL] EOD 청산 3회 실패 - 강제 완료 처리` 텔레그램**(수동 매도 안내 포함).
- 이어서 `_save_paper_eod_balance_if_virtual()`(가상 잔고 → `paper_trading_state`) → `_call_strategy_market_close()` → **첫 전략의 `on_market_close()` 만**.
- 15:00 이후: intraday 전략은 on_tick 스킵(§2.2) + `ctx.buy` 차단(§4). swing 전략은 영향 없음.
- (`liquidate_all_positions_end_of_day` 도 존재하지만 `main._liquidate_all_positions_end_of_day` 위임 외 호출자는 없다.)

### 3.6 15:20 — 신규 주문 차단 · 15:30 장 마감

- `get_market_phase()` 가 `closing_auction_start = 15:20` 부터 `CLOSING_CUTOFF` → `can_place_order()` False → `place_buy_order` · `place_sell_order(force=False)` 둘 다 거부. EOD 청산의 `force=True` 만 예외.
- `buy_cutoff_hour=12`(`should_stop_buying`/`is_new_buy_blocked`)는 **프로덕션 호출자 0건 — 결선 안 됨**. 12시 이후에도 산다.
- 15:30 이후 `is_market_open()` False → 메인 루프 30초 idle. **자동 종료 없음.**

### 3.7 SystemMonitor (`run_system_monitoring_task`, 5초 루프)

| 시점 | 코드 | 내용 |
|---|---|---|
| 매 루프(시각 게이트 없음 · 각 항목이 하루 1회 래치) | `_handle_premarket_tasks` | ① `_register_strategy_target_stocks` — **첫 전략** `get_target_stocks()` 만 하루 1회 등록 ② 장전 regime 지수(KOSPI/KOSDAQ) 갱신(하루 1회 · 성공 시만 가드) ③ 장전 브리핑(하루 1회) |
| 15:35+ (hour==15, minute>=35) 하루 1회 | `_handle_postmarket_tasks` | 휴장일이면 전체 스킵. 순서: EOD 자금 정합성 검증 → (실전 인스턴스는 여기서 끝) → 일일 매매 리포트 `tools/daily_trading_summary.print_today_trading_summary` → 게이트지수 해석 집계 → 스크리너 스냅샷 검증 → **equity 스냅샷**(`paper_strategy_equity`) → EOD regime 지수 갱신 → **EOD 데이터 수집** `collectors/eod_collection.run_data_collection`(일봉·분봉·지수·시장매핑·외국인수급·기업행위·재무·…, 수분) → **equity 재스냅샷**(T 종가로 재평가) → EOD 벤치마크(맨 끝) |
| 24시간마다 | `_refresh_api` | API 재초기화 + 텔레그램 상태 알림 |
| 30분마다(장중) | `_save_portfolio_snapshot` | **미구현** — debug 로그 한 줄만 남기고 아무것도 저장하지 않는다(30분 게이트만 살아 있음) |
| 30분마다 | `_log_system_status` | 상태 로그 |

메모리/CPU 감시는 없다(`psutil` 은 PID 중복 검사에만 쓰인다).

### 3.8 종료 (`shutdown()`)

트리거는 세 가지뿐: **SIGINT/SIGTERM**(`_signal_handler` → `is_running=False`), **텔레그램 `/stop`**(같은 플래그), **critical 태스크 재시도 소진**(§6). 시각 기반 자동 종료는 없다.

`BotInitializer.shutdown()` 순서: `data_collector.stop_collection()` → `order_manager.stop_monitoring()` → `_flush_state_to_db()` → `telegram.shutdown()` → `_cancel_pending_orders()` → `broker.disconnect()` → PID 파일 삭제.

---

## 4. 매수 경로

```
BaseStrategy.on_tick(ctx)  [기본 구현 · 전략이 override 가능]
  for stock in ctx.get_selected_stocks():            ← 자기 전략 소유 + 공용 SELECTED 만
      data = await ctx.get_daily_data(code)          ← daily_prices, days 기본 120(달력일), 당일 미확정봉 제거
      len(data) < get_min_data_length()(기본 20) → 스킵 · 불가능봉(±30% 초과 하락) → 스킵
      signal = generate_signal(code, data, timeframe='daily')
      BUY/STRONG_BUY → await ctx.buy(code, signal=signal)
```

**`TradingContext.buy()` 가드 (순서대로, 하나라도 걸리면 None)**

1. 시장 전체 서킷브레이커(`get_circuit_breaker_state().is_market_halted()`)
2. 시장급락 필터 `decision_engine.check_market_direction(regime_index)` — 전략 `regime_index`(`auto` 면 종목 소속 시장으로 해석) · 임계 KOSPI −2.5% / KOSDAQ −3.0%(`constants`)
3. PIT 국면 게이트 `check_regime_gate(regime_index, regime_gate)`(`none`/`exclude_bear`/`bull_only`)
4. 자기 소유 슬롯 조회 실패(종목 정보 없음)
5. 중복 소유권 — 같은 종목이 이미 POSITIONED/BUY_PENDING
6. 종목 VI — 라이브 종목정보로 VI arm 후 `is_vi_active`
7. 일일 손실 한도 `fund_manager.is_daily_loss_limit_hit()`
8. `Signal.entry_min_price` 매수스톱 — 현재가 < entry_min 이면 미돌파 스킵
9. EOD 청산 시각 이후 + `holding_period == "intraday"` 전략
10. 상한가 접근 — 전일종가 대비 `PRICE_LIMIT_GUARD_RATE = +25%` 이상
11. 진입 억제 — 사이클(15초) 당 최대 3건(`MAX_NEW_ENTRIES_PER_CYCLE`) · 종목 간 60초 쿨다운(`ENTRY_COOLDOWN_SECONDS`)

통과하면 `TradingAnalyzer.analyze_buy_decision(trading_stock, signal, strategy_name=폴더키)`:

- 보유 중 재확인 → 25분 매수 쿨다운(`buy_cooldown_minutes`) → `daily_prices` 140일 조회 → `CANDIDATE_MIN_DAILY_DATA = 22` 봉 미만이면 중단
- `TradingDecisionEngine.analyze_buy_decision(..., owner_signal=signal)` — 급락 재검사 → **owner_signal 을 그대로 신뢰**(다중전략에서 첫 전략으로 재판정하지 않음; 신호가 없을 때만 `self.strategy.generate_signal`) → 실시간 현재가 필수(일봉 종가 폴백 금지 · 없으면 보류)
- 가상: `execute_virtual_buy` — tp/sl 결정(§5.3) · 손절 하한 3% · 수량 = VTM 전략 원장(`get_max_quantity`) · `execute_virtual_buy` 기록 · owner 전략 `on_order_filled` 통보
- 실전: `execute_real_buy` → `order_manager.place_buy_order` (`can_place_order()` 게이트 · 체결 모니터링 → `OrderCompletionHandler` 가 owner 전략에 `on_order_filled`)

체결 뒤 `ctx.buy` 는 `owner_strategy_name`/`owner_strategy` 를 슬롯에 기록하고 진입 억제 카운터를 갱신한다(거부·실패한 시도는 쿨다운을 무장시키지 않는다).

---

## 5. 매도 체인

### 5.1 프레임워크 백스톱 — `PositionMonitor._analyze_sell_for_stock` (매 3초 · POSITIONED 전부)

현재가(실시간)로 `profit_rate` 를 계산한 뒤 **아래 순서**로 첫 조건에서 매도하고 return:

| 순위 | 조건 | 출처 |
|---|---|---|
| 1 | `is_stale`(보유 30일↑) 이고 수익률 > 0 → 매도 · 손실 ≥ 3% → 매도(09:00~09:05 제외) | `STALE_POSITION_DAYS=30` · `STALE_SELL_PROFIT_THRESHOLD=0.0` · `STALE_SELL_LOSS_THRESHOLD=0.03` |
| 2 | `days_held >= owner.max_holding_days` | 전략 속성(`config.yaml parameters.max_holding_days`) |
| 3 | 레거시 트레일링 스톱 — **슬롯 owner 도 없고 `PositionMonitor._strategy` 도 None 일 때만**(= 전략이 하나도 안 실린 레거시 모드 · 라이브 8전략에선 발동하지 않는다) (+5% 활성 · 최고가 −3% 매도) | `TRAILING_STOP_ACTIVATION_RATE=0.05` · `TRAILING_STOP_CALLBACK_RATE=0.03` |
| 4 | `profit_rate >= target_profit_rate`(양수일 때만) | 슬롯 tp |
| 5 | `profit_rate <= -stop_loss_rate` — 09:00~09:05 제외 | 슬롯 sl |
| 6 | owner 전략 `generate_signal(code, 분봉, timeframe='intraday')` 가 SELL/STRONG_SELL | 실시간 수집 분봉 |

`owner_strategy` 는 슬롯의 `owner_strategy` → 없으면 `PositionMonitor._strategy`(`set_strategy` 로 받은 첫 전략).

### 5.2 전략 고유 청산 — `on_tick` 매도 루프

```
for stock in ctx.get_positions():
    exit_timeframe == 'daily'  → data = ctx.get_daily_data(code), timeframe='daily'
    else                       → data = ctx.get_intraday_data(code), timeframe='intraday'
    generate_signal(code, data, timeframe) 가 SELL → await ctx.sell(code, reason, signal=signal)
```

`ctx.sell` 가드: 자기 소유 슬롯 조회 → **소유권 불일치면 거부** → `is_selling` 중복 방지 → 하한가 접근은 경고만(매도는 진행) → `TradingAnalyzer.analyze_sell_decision(trading_stock, signal)` → 가상 `execute_virtual_sell` / 실전 `execute_real_sell`. 매도 후 `fund_manager` 갱신은 `execute_virtual_sell` 안에서 일원화.

`exit_timeframe` 은 미설정 시 `holding_period` 로 유도(swing→`daily`, intraday→`intraday`); swing 인데 `intraday` 로 명시하면 `BaseStrategy.__init__` 이 `ValueError` 로 거부한다.

### 5.3 tp/sl 출처 체인 (`execute_virtual_buy`)

| 순위 | 출처 | 값 |
|---|---|---|
| 1 | 호출자가 명시한 `target_profit_rate`/`stop_loss_rate` 인자 | |
| ~~2~~ | ~~`Signal.target_price`/`stop_loss` 역산~~ | **2026-06-25 제거** — Signal 절대가는 더 이상 tp/sl 에 쓰이지 않는다 |
| 3 | 소유 전략 `config.yaml` `risk_management.take_profit_pct` / `stop_loss_pct`(없으면 `_ratio` 키) | 전략별 |
| 4 | `trading_config.json` `risk_management.take_profit_ratio` / `stop_loss_ratio` | 0.15 / 0.10 |
| 4′ | 그것도 없으면 `constants.DEFAULT_TARGET_PROFIT_RATE` / `DEFAULT_STOP_LOSS_RATE` (+ WARNING `config tp/sl 누락 → DEFAULT 적용`) | 0.15 / 0.10 |
| 후처리 | 손절률 하한 `STOP_LOSS_FLOOR = 0.03` | 3% 미만이면 3% 로 올림 |

---

## 6. Task Supervisor (`_supervised_task`)

`config/constants.py`: `TASK_SUPERVISOR_MAX_RETRIES = 5` · `TASK_SUPERVISOR_BASE_DELAY = 10` · `TASK_SUPERVISOR_MAX_DELAY = 300`.

- 예외마다 `retries += 1`, 텔레그램 `notify_error`, 소진 판정(`retries >= max_retries`) 뒤 대기 `min(10 × 2^(retries−1), 300)` 초 → **10 · 20 · 40 · 80**(4회 대기 · 5번째 실패는 대기 없이 소진 처리 · 300초 상한은 현 상수에서 도달하지 않음).
- critical(메인 루프): 5회 소진 → CRITICAL 로그 + 텔레그램 → `is_running = False` → 다른 태스크도 멈추고 `shutdown()`.
- non-critical(모니터링·텔레그램): 5회 소진 → 포기(시스템은 계속).
- 태스크가 정상 return(`is_running=False` 등)하면 재시작하지 않는다.

---

## 7. 텔레그램

설정: `config/key.ini` `[TELEGRAM]` `enabled` · `token` · `chat_id`(경로는 `config/settings.CONFIG_FILE` — 인스턴스 모드에서도 자기 key.ini).

**명령(실재 핸들러, `TelegramNotifier._register_commands`)**: `/status` · `/positions` · `/orders` · `/virtual` · `/help` · `/stop`. `/stop` 은 `bot.is_running = False` 로 §3.8 종료 경로를 탄다. 수동 매수/매도·종목 추가 명령은 **없다**. `/reload` 는 `candidate_loader.reload_candidates()` 에 TODO 로만 적혀 있고 핸들러가 없다.

**알림**: 시스템 시작/종료 · 주문 제출/체결/취소 · 신호 감지 · 오류(`notify_error`) · 주기 상태(`interval_minutes` 기본 30분) · 후보 등록(`후보 종목 등록: N종목` · 로그 태그는 `[E6]`) · 스크리너 스냅샷 · EOD 강제완료 CRITICAL · API 재초기화.

---

## 8. FAQ

**Q. 프로그램을 재시작하면?** — `restore_todays_candidates()` 가 `candidate_stocks` 오늘 행과 보유 종목(가상: DB / 실전: 실계좌)을 복원하고, 슬롯 tp/sl 도 DB 값으로 복원한다(NULL/NaN 은 DEFAULT). 전략 `self.positions` 는 `on_init` 뒤 `apply_pending_strategy_positions()` 로 재주입된다. 봇 가동 중 머지한 코드는 **다음 재기동(다음 07:40)** 에 발효한다.

**Q. 수동으로 개입할 수 있나?** — 텔레그램은 조회 5개 + `/stop` 뿐이다. 매수/매도/종목 추가는 코드·설정을 바꾸고 재기동하는 것이 유일한 경로다.

**Q. 15:30 에 봇이 꺼지나?** — 아니다. 장외에는 30초 idle 이고 `SystemMonitor` 가 15:35+ 후장 체인을 돌린다. 종료는 §3.8 트리거뿐이다.

**Q. 15:00 EOD 청산 로그에 「보유 포지션 없음」/청산 0건인데 보유는 40종목이다?** — 정상. 8전략 전부 `holding_period="swing"` 이라 `should_liquidate_eod()` 가 False 로 건너뛴다(스킵 종목은 `EOD 청산 스킵 (전략 X 거부)` 로그).

**Q. 12시 이후엔 안 사나?** — 산다. `buy_cutoff_hour` 는 결선되지 않았다. 실효 주문 마감은 15:20(`can_place_order`).

**Q. 후보는 어디서 오나?** — 각 전략의 `screener_snapshots`(scan_date = 직전 거래일) 뿐이다. 전략당 최대 **10**(`trading_config.json` `strategy.parameters.max_candidates` · 안전필터 통과 기준 — 스냅샷은 전략당 최대 20건 저장되지만 소비는 10). `generate_signal` 은 그 안에서만 평가한다. 0건은 「그날 조건 맞는 종목 없음」이고, 폴백은 전 전략 0건일 때만 발동한다.

**Q. 매수가 9초마다 도나?** — 전략 하나당 9초가 아니라 **전략 순서대로 9초에 하나씩**이다(8전략 ≈ 72초 주기). 매도 백스톱(손절/익절)은 매 3초다.

**Q. 왜 Signal 에 `target_price`/`stop_loss` 를 넣어도 tp/sl 이 안 바뀌나?** — 2026-06-25 부터 역산이 제거됐다(§5.3). tp/sl 은 전략 `config.yaml risk_management` 에 둔다.

---

**기준 코드**: `main` `16a8106` (2026-09-17) · **마지막 갱신**: 2026-09-17
