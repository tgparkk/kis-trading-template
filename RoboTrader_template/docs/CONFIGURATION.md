# 설정 가이드

> 봇이 실제로 읽는 설정 파일·환경변수·상수의 전수. 근거는 전부 코드(`config/` · `core/models.py` · `strategies/config.py` · `db/`)이며, 갱신일 2026-09-17.

설정은 서로 다른 것을 담당하는 **네 파일**이다. 우선순위 사슬 같은 것은 없다 — 같은 효력을 갖는 키가 없기 때문이다(예외: 손절/익절률 §3 · 이름만 같은 `paper_trading` — §2-1 은 모드 스위치, §3 은 로그 접두사·metadata 뿐).

| 파일 | 담당 | 읽는 코드 |
|---|---|---|
| `config/key.ini` | KIS API 키·계좌 · 텔레그램 | `config/settings.py` · `core/telegram_integration.py` |
| `config/trading_config.json` | 페이퍼/실전 스위치 · 활성 전략 목록 · 주문/리스크 전역값 | `config/settings.load_trading_config()` → `core/models.TradingConfig` |
| `strategies/<폴더키>/config.yaml` | 전략별 파라미터 · K(동시보유) · 손절/익절 | `strategies/config.StrategyConfig` |
| `.env`(선택, `RoboTrader_template/` 루트) | DB 접속 · 기능 스위치 | `config/env_bootstrap.py` → `os.environ` |

실전 인스턴스(`KIS_INSTANCE_DIR`)에서는 앞의 두 파일이 `instances/<id>/` 것으로 바뀐다 → [instances/README.md](../instances/README.md).

---

## 1. `config/key.ini` — API 키 · 텔레그램

`config/key.ini.example` 을 복사해 만든다. `.gitignore` 로 제외돼 있다(절대 커밋 금지).

```ini
[KIS]
KIS_BASE_URL="https://openapi.koreainvestment.com:9443"
KIS_APP_KEY="..."
KIS_APP_SECRET="..."
KIS_ACCOUNT_NO="..."
KIS_HTS_ID="..."

[TELEGRAM]
enabled=false
token=YOUR_BOT_TOKEN_HERE
chat_id=YOUR_CHAT_ID_HERE
```

- `[KIS]` 5개 키는 `config/settings.py` `load_config()` 가 `configparser` 로 읽어 `APP_KEY`·`SECRET_KEY`·`ACCOUNT_NUMBER`·`HTS_ID`·`KIS_BASE_URL` 모듈 상수가 된다(양끝 `"` 제거). 파일이 없으면 경고 후 빈 문자열로 진행하지만, `run_robotrader.bat` 는 그 전에 파일 부재로 중단한다.
- `[TELEGRAM]` 은 `core/telegram_integration.py` 가 같은 파일에서 읽는다(`enabled` boolean · `token` · `chat_id`). 절이 없으면 알림 비활성.
- 🔴 **KIS 키를 `.env` 로 넣는 코드는 없다.** `.env` 에 `APP_KEY=` 를 적어도 아무 일도 일어나지 않는다.

---

## 2. `config/trading_config.json` — 거래 설정

`TradingConfig.from_json()`(`core/models.py`)이 읽는 키만 효력이 있다.

### 2-1. 최상위 키

| 키 | 타입 · 기본값 | 효력 |
|---|---|---|
| `paper_trading` | bool · `true` | **페이퍼/실전 스위치.** `core/trading_decision_engine.py` 의 `is_virtual_mode` 가 이 값이다. 라이브 = `true` |
| `strategies` | list · `null` | **활성 전략 목록(§2-2).** 비어 있지 않으면 다중 전략 모드 |
| `strategy` | `{name, enabled, parameters}` · `simple_momentum`/`true`/`{}` | legacy 단일 전략 블록. `strategies[]` 가 비어 있을 때만 `main._load_strategies()` 가 이걸로 1개 로드. 코드 기본값 `simple_momentum`(`core/models.StrategyConfig`)은 폴더가 없다(아래 참조) · 라이브 JSON 값은 `sample`. 단, `parameters.max_candidates` 는 다중 모드에서도 `bot/candidate_loader.py` 가 **전략당 후보 소비 상한**으로 읽는다(라이브 JSON `10`, 없으면 `MAX_CANDIDATES_PER_STRATEGY`=20) |
| `real_total_funds_cap` | number · `null` | 실전 총자금 상한(원). `paper_trading=false` 일 때 **필수** — 없거나 0 이하면 `bot/initializer.py` 가 `LiveStartupAbort`. 라이브 JSON 에는 없다(페이퍼라 불필요) |
| `rebalancing_mode` | bool · `false` | `true` 면 `core/intraday_stock_manager.py` 가 종목 등록 시 분봉 대신 `collect_daily_data_only()` 만 수집. 라이브 = `true` |
| `risk_management` | `{max_position_count, max_position_ratio, stop_loss_ratio, take_profit_ratio, max_daily_loss}` | `stop_loss_ratio`/`take_profit_ratio` 는 손절/익절 **4순위 기본값**(§3). `max_position_count` 는 기동 시 `bot/initializer._apply_total_k_position_limit()` 이 `fund_manager.max_position_count` 를 `max(기존값, ΣK)` 로 올려 잡는다(완화 방향만 — ΣK 가 기존값보다 작으면 그대로) |
| `order_management` | `{buy_timeout_seconds, sell_timeout_seconds, max_adjustments, adjustment_threshold_percent, market_order_threshold_percent, buy_budget_ratio, buy_cooldown_minutes}` | 주문 타임아웃·정정·쿨다운 |
| `data_collection` | `{interval_seconds, candidate_stocks}` | 수집 주기 · 고정 후보 |
| `logging` | `{level, file_retention_days}` | — |
| `duplicate_signal_prevention` | — | JSON 에 있으나 `from_json()` 이 **읽지 않는다** |

- `portfolio_size` 라는 키는 **없다**(`TradingConfig` 필드 아님 · JSON 에도 없음). `config/constants.py` 의 `PORTFOLIO_SIZE`(15)와 무관.
- 파일이 없거나 파싱 실패면 `config/settings.load_trading_config()` 가 경고 후 `TradingConfig()` 기본값을 돌려준다 → `strategies=None` → legacy `strategy.name="simple_momentum"` 로드 시도 → `strategies/simple_momentum/` 폴더가 없어 `StrategyLoader.validate_strategy()` 실패 → `StrategyConfigError` → `main._load_strategies()` 가 critical 로그(「전략 설정 오류 (시스템 중단)」) 후 재발생 = **기동 중단**. JSON 없이 「기본값으로 굴러가는」 경로는 없다.

### 2-2. `strategies[]` 항목 — 전략 on/off 는 여기서

```json
{ "name": "book_pullback_ma20", "enabled": true, "max_capital_pct": 0.16,
  "regime_index": "KOSPI", "regime_gate": "exclude_bear" }
```

| 키 | 효력 (`strategies/config.StrategyLoader.load_strategies()`) |
|---|---|
| `name` | `strategies/<name>/` 폴더키. 폴더·`config.yaml`·`Strategy` 접미 클래스가 있어야 로드 |
| `enabled` | `false` 면 건너뜀(기본 `true`) |
| `max_capital_pct` | 인스턴스 속성에 저장. 활성 전략 합계 > 1.0 이면 WARNING 로그 **뿐** — `core/fund_manager.py` 의 `strategy_max_pct_provider` 콜백을 봇이 주입하지 않아 배분 강제는 없다 |
| `regime_index` | 급락 게이트 판정 지수. 라이브 값 `"KOSPI"` · `"auto"`(daytrading). 기동 시 `bot/initializer._crosscheck_regime_index_config()` 가 설정↔인스턴스 대조 |
| `regime_gate` | `"none"` / `"exclude_bear"` / `"bull_only"`(`core/trading_decision_engine.check_regime_gate`). 라이브 값 `none`·`exclude_bear` |

라이브(2026-09-17) = 8종 전부 `enabled: true`: `elder_ema_pullback` · `book_envelope_200d` · `daytrading_3methods_breakout` · `minervini_volume_dryup` · `book_pullback_ma20` · `book_pullback_ma5` · `rs_leader` · `deep_mr_dev20`. 전략 교체 = 이 배열 편집 + 재기동(봇 가동 중 편집은 다음 07:40 기동에 발효).

---

## 3. `strategies/<폴더키>/config.yaml` — 전략별 설정

`StrategyConfig.load()` 가 YAML 을 dict 로 읽고 `name` 이 없으면 폴더명을 채운다. `enabled` 키는 **없다**(on/off 는 §2-2). 활성 8전략의 최상위 키는 다섯 개다.

```yaml
strategy:
  name: "BookPullbackMa20Strategy"
  version: "1.0.0"
paper_trading: true
parameters:
  min_daily_bars: 35
risk_management:
  take_profit_pct: 0.10
  stop_loss_pct: 0.08
  max_hold_days: 50
  trail_ma: 20
  max_positions: 5
  max_daily_trades: 5
  max_per_stock_amount: 3000000
target_stocks: []
```

| 키 | 누가 읽나 | 효력 |
|---|---|---|
| `strategy.name` / `version` | 전략 클래스 | 표시용 |
| `paper_trading` | 각 전략 `strategy.py`(`self._paper_trading`) | `[PAPER]` 로그 접두사 + 시그널 metadata `paper_only`. **모드 스위치가 아니다** — 실주문 여부는 §2-1 `paper_trading` 이 정한다 |
| `parameters.*` | 전략 클래스 `get_param()` | 전략 고유 파라미터 |
| `risk_management.max_positions` | 전략 `strategy.py`(K) · `bot/initializer._allocate_strategy_capital()` | **동시보유 한도 K**. 기동 시 `VIRTUAL_CAPITAL_PER_STRATEGY / K` 가 종목당 기본 예산(`core/virtual_trading_manager.py`) |
| `risk_management.max_daily_trades` | 전략 `strategy.py` | 일일 체결 상한(매수·매도 합산 카운트) |
| `risk_management.take_profit_pct` / `stop_loss_pct` | `core/trading_decision_engine.py` | 손절/익절 **3순위**(`_ratio` 접미도 허용). 사슬 = 1순위 호출자 명시값 → 3순위 이 값 → 4순위 `trading_config.json risk_management` → `constants.DEFAULT_*` |
| `risk_management.max_per_stock_amount` | `bot/initializer.py` → `VirtualTradingManager` | 종목당 매수 상한(원) |
| `risk_management.max_hold_days` / `trail_ma` | 전략 `strategy.py` | 전략별 청산 룰 |
| `target_stocks` | `BaseStrategy.get_target_stocks()` → `bot/system_monitor.py` | 고정 후보. 비우면 스냅샷 경로 |

- `max_position_size` 는 활성 8전략 config.yaml 에 없고 비활성 템플릿(`sample`·`mean_reversion`·`momentum`·`sawkami`·`volume_breakout`)에만 남아 있다. `core/`·`bot/`·`strategies/base.py` 어디서도 읽지 않는다(`strategies/sample/strategy.py` 만 자체 소비).
- `StrategyConfig.validate()` 는 `risk_management` 의 `_pct`/`_ratio`/`_size` 접미 키를 0~1 로 검사한다(`PCT_THRESHOLD_WHITELIST` 예외).
- 집중 3전략 현재 K(2026-09-17 config.yaml) = ma20 **5** · minervini **3** · daytrading **5**. 09-18 07:40 재기동에 10/6/10 으로 올리는 것이 **예정**돼 있다 → [prereg_2026-09-15_focus3_K_raise.md](prereg_2026-09-15_focus3_K_raise.md).

---

## 4. `.env` · 환경변수

### 4-1. 읽는 방식 (`config/env_bootstrap.py`)

- 위치는 `RoboTrader_template/.env`(CWD 무관). `main.py` 가 최상단에서 `bootstrap()` 을 부른다. python-dotenv 는 쓰지 않는다(표준 라이브러리 파서).
- **우선순위 = OS 환경변수 > `.env` > 코드 기본값.** `.env` 는 「아직 없는 키」만 넣는다 — `run_robotrader.bat` 가 `set` 한 값(`SCREENER_SNAPSHOT_ENABLED=true` 등)을 `.env` 로 덮을 수 없다.
- 파싱 = `KEY=VALUE` 만. 빈 줄·`#` 으로 **시작하는** 줄·`=` 없는 줄은 무시, `export ` 접두·양끝 따옴표 제거.
- 🔴 **인라인 주석은 값에 포함된다.** `RS_LEADER_CORP_ACTION_MODE=shadow  # off|shadow|live` 라고 쓰면 값은 `shadow  # off|shadow|live` 가 되고, `config/constants.py` 의 `resolve_rs_leader_corp_action_mode()` 가 미지값으로 보고 **`off` 로 강등**한다(WARNING 은 resolver 가 아니라 호출자가 찍는다 — `strategies/rs_leader/strategy.py` 2곳 · `screener.py` 1곳). `SECTOR_NEWS_BOOST_MODE` 도 같은 규약. 주석은 반드시 **별도 줄**에.
- `.env` 가 없어도 `kis_template@localhost:5433` 에 붙는다 — 호스트·포트·DB·user 기본값이 라이브 접속 정보와 같다(암호는 `.env` 값이 다를 수 있다).

### 4-2. 운영 코드가 읽는 변수 전수

`grep os.environ|getenv` 대상 = `core/ bot/ framework/ api/ strategies/ collectors/ db/ runners/ signals/ utils/ tools/ config/ main.py`.

| 변수 | 읽는 곳 | 기본값 | 비고 |
|---|---|---|---|
| `TIMESCALE_HOST` / `PORT` / `DB` / `USER` / `PASSWORD` | `db/connection.py`(주 풀) | `localhost` / `5433` / `kis_template` / `robotrader` / `1234` | `TIMESCALE_DB` 는 수동 쓰기 스크립트에서 `require_explicit_target_db()` 가 **필수**로 요구 |
| `KIS_DB_HOST` / `PORT` / `NAME` / `USER` / `PASSWORD` | `db/kis_db_connection.py`(컬렉터·regime 두 번째 풀) · `signals/foreign_flow.py` | 위와 동일 | |
| `KIS_INSTANCE_DIR` | `config/settings.py` `resolve_instance_id()`/`resolve_config_dir()` | 없음 = `default` | `run_instance.bat` 가 `instances\<id>` 로 설정 → 5중 분리 |
| `SCREENER_SNAPSHOT_ENABLED` | `config/constants.py` → `bot/liquidation_handler.py` · `bot/system_monitor.py` | `false` | `run_robotrader.bat` 가 `true`, `run_instance.bat` 는 `false`(소비 전용). 꺼지면 이 프로세스는 장 시작 후 최초 후보 로드 시 스냅샷을 만들지 않는다 — 같은 DB 에 다른 프로세스(페이퍼 봇)가 만든 직전 거래일 스냅샷도 없으면 당일 후보 0건(전 전략 0건이면 `[E6]` 거래량 폴백). 소비자 `core/candidate_selector.py` 는 이 변수를 보지 않고 스냅샷 존재만 본다 |
| `SECTOR_NEWS_BOOST_MODE` | `config/constants.py` → `core/candidate_selector.py` | `shadow` | `off` / `shadow` / `live`. 미지값 → `off` + WARNING |
| `RS_LEADER_CORP_ACTION_MODE` | `config/constants.py` → `strategies/rs_leader/corp_action_guard.py` | `shadow` | `off` / `shadow` / `live`. **라이브는 `.env` 로 `live`(2026-09-17 07:40 발효)** → [prereg_2026-09-16_rsleader_exclusion_live.md](prereg_2026-09-16_rsleader_exclusion_live.md). 롤백 = 줄 삭제(→shadow) 또는 `off` |
| `OPENDART_API_KEY` | `collectors/corp_events_collector.py`(env 우선, 없으면 `.env` 를 직접 파싱) · `financial_collector.py` · `sector_collector.py` | `''` | DART 수집기 전용 |
| `LOG_LEVEL` | `utils/logger.py` | `INFO` | 예: `DEBUG` |
| `ALLOW_FOREIGN_VENV` | `bot/env_guard.py` | 미설정 | `1` 이면 venv 가드 실패를 경고로 낮춤 |
| `CORP_ACTION_QUEUE_PATH` | `collectors/corp_action_watch.py` | `logs/corp_action_refetch_queue.jsonl` | 큐 파일 경로 override |
| `QUANT_FINANCIAL_DB` | `multiverse/data/pit_reader.py` 뿐(연구 경로) | `kis_template` | **재무 전용** 롤백 스위치. 가격 resolver 와 분리된 것이 의도된 설계. `lib/signals/roe_filter.py` 는 `_get_connection()` 이 `kis_template` 고정이라 이 env 를 보지 않는다 |
| `STRATEGY_DB_*` · `EXTERNAL_DB_*` | 비활성 템플릿 전략(`lynch` · `sawkami` · `bb_reversion*` · `strategies/historical_data.py`) | `kis_template` 등 | 라이브 8전략 경로 아님 |

### 4-3. 폐지된 변수 — 설정해도 아무 일도 없다

`KIS_DATA_SOURCE` · `QUANT_DB` · `MINUTE_DB` · `CORP_EVENTS_DB` (2026-08-17 폐지). 가격 읽기 DB 는 `config/constants.py` 의 `resolve_daily/minute/corp_events_source_db()` 가 상수 `"kis_template"` 을 돌려준다. 새 env 로 되살리지 말 것. `VIRTUAL_MODE` 라는 변수는 존재한 적이 없다.

---

## 5. 알아둘 상수 (`config/constants.py`) · 거래시간 (`config/market_hours.py`)

### 5-1. 상수

| 상수 | 값 | 의미 |
|---|---|---|
| `API_CALL_INTERVAL` | `0.10` 초 | KIS API 호출 최소 간격(초당 약 10회) |
| `API_MAX_RETRIES` | `3` | API 재시도 |
| `ORDER_MONITOR_INTERVAL` | `3` 초 | 체결 확인 주기 |
| `SELL_ORDER_WAIT_TIMEOUT` | `300` 초 | 매도 체결 대기 상한 |
| `DEFAULT_TARGET_PROFIT_RATE` / `DEFAULT_STOP_LOSS_RATE` | `0.15` / `0.10` | 손절/익절 최종 기본값(§3 사슬의 끝) |
| `VIRTUAL_CAPITAL_PER_STRATEGY` | `10,000,000` 원 | 전략별 가상 초기자금. 종목당 기본 예산 = 이 값 / K |
| `MAX_CANDIDATES_PER_STRATEGY` | `20` | 스크리너 스냅샷 **저장** 상한(전략당 · 생성 시점 = 장 시작 후 최초 후보 로드, `bot/liquidation_handler.run_screener_snapshot_hook`). 라이브 **소비** 상한은 `trading_config.json strategy.parameters.max_candidates`(현재 10)가 있으면 그 값 |
| `PRICE_LIMIT_GUARD_RATE` | `0.25` | 상한가 접근(+25%) 매수 차단 |
| `SECTOR_NEWS_MAX_SHIFT` / `MIN_ABS` / `STALE_MINUTES` | `3` / `0.2` / `60` | 섹터 뉴스 재정렬 파라미터 |

### 5-2. 거래시간 (KRX `MARKET_CONFIG['KRX']['default']`)

| 시각 | 키 | 실제 효력 |
|---|---|---|
| 09:00 ~ 15:30 | `market_open` / `market_close` | `is_market_open()` |
| **15:20** | `closing_auction_start` | `get_market_phase()` 가 `CLOSING_CUTOFF` 로 넘어가고 `can_place_order()` 가 **매수·매도 주문을 전부 차단**(EOD 청산만 `force`). 이것이 실효 신규매수 마감이다 |
| 15:00 | `eod_liquidation_hour/minute` | `is_eod_liquidation_time()` — `holding_period="intraday"` 전략만 청산·신규매수 차단. **라이브 8전략은 전부 `swing`** 이라 해당 없음 |
| 12:00 | `buy_cutoff_hour` | 🔴 **결선 안 됨.** `should_stop_buying()`/`is_new_buy_blocked()` 의 프로덕션 호출자 0건. `new_buy_cutoff`(15:20) 키도 호출자 0 |
| 특수일 | `special_days` | 날짜별 override(등록 항목은 `2025-11-13` 수능일 하나: 10:00~16:30) |

---

## 6. DB 초기화

`init-scripts/01-init.sql` 하나로 끝나지 않는다.

- `init-scripts/` 6개: `01-init.sql` · `02-multiverse.sql` · `03-adj-factor.sql` · `04-corp-events-end-date.sql` · `05-vtr-source-column.sql` · `06-phase5-signals.sql`
- `db/migrations/` 4개: `20260815_credit_and_overtime.sql` · `20260815_investor_trend_daily.sql` · `20260815_short_sale_and_program_trade.sql` · `20260907_sector_news_rerank_log.sql`
- 런타임 DDL: `db/repositories/trading.py`(`CREATE TABLE IF NOT EXISTS real_trading_*`) 등 코드가 첫 사용 시 만드는 표

어느 표가 어디서 만들어지는지, 접속·풀·표 인벤토리 전수 → [DATABASE.md](DATABASE.md) §6 「DDL 이 있는 곳」.
