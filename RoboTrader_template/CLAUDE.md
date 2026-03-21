# CLAUDE.md — AI 개발 협업 가이드

> 이 문서는 Claude(AI 개발자)가 이 프로젝트에 투입될 때 빠르게 컨텍스트를 잡기 위한 가이드입니다.

## 프로젝트 개요

**KIS Trading Template** — 한국투자증권(KIS) API 기반 **범용 자동매매 프레임워크 템플릿**

핵심 아이디어: 공통 인프라(API 연동, 주문 처리, DB, 텔레그램 알림 등)를 프레임워크로 제공하고, 개발자는 **전략 로직만 작성**하면 되는 구조.

```
kis-trading-template/
├── RoboTrader (전략 A)        ← 전략만 다름
├── RoboTrader_orb (전략 B)    ← 전략만 다름
└── RoboTrader_template (이 프로젝트) ← 프레임워크 + 샘플 전략
```

---

## 아키텍처

### 레이어 구조

```
┌───────────────────────────────────────────┐
│  strategies/          전략 레이어          │
│  (BaseStrategy 상속 → generate_signal())  │
├───────────────────────────────────────────┤
│  bot/                 봇 위임 핸들러       │
│  (초기화, 분석, 모니터링, 청산, 동기화)     │
├───────────────────────────────────────────┤
│  framework/           추상화 레이어        │
│  (Broker, DataProvider, OrderExecutor)    │
├───────────────────────────────────────────┤
│  api/                 KIS API 래퍼        │
│  (인증, 주문, 차트, 계좌, 시장정보)        │
├───────────────────────────────────────────┤
│  core/                핵심 비즈니스 로직    │
│  (주문관리, 자금관리, 매매판단엔진)         │
├───────────────────────────────────────────┤
│  db/ config/ utils/   인프라              │
└───────────────────────────────────────────┘
```

### 데이터 흐름

```
[기본 경로] strategy.on_tick(ctx: TradingContext)
  → generate_signal() 호출 → Signal 반환
  → ctx.buy() / ctx.sell() (서킷브레이커·VI·시장방향 가드 내장)
  → TradingDecisionEngine이 Signal 해석 (target_price/stop_loss 활용)
  → OrderManager가 주문 실행 (KIS API)
  → 체결 모니터링 → on_order_filled 콜백
  → DB 저장 + 텔레그램 알림
```

---

## 핵심 모듈 가이드

### `main.py` — 진입점 (≈670줄)

- `DayTradingBot` 클래스가 전체 시스템을 관장
- `__init__()`: 모든 모듈 초기화 (의존 순서 중요)
- `initialize()`: 시스템 + 전략 초기화
- `run_daily_cycle()`: 3개 비동기 태스크를 `asyncio.gather`로 병렬 실행
  - **메인트레이딩루프** (critical=True): 3초 간격으로 순차 실행
    1. 데이터 수집 (collect_once)
    2. 미체결 주문 확인 (check_pending_orders_once)
    3. `check_positions_once()` (매 반복 — 손절/익절 모니터링)
    4. 전략 있으면 `strategy.on_tick(ctx)` (매 9초, 30초 타임아웃), 없으면 기존 방식 fallback
    5. EOD 일괄청산 체크
  - **시스템모니터링** (critical=False)
  - **텔레그램** (critical=False)
- `_supervised_task()`: 태스크 감독 (실패 시 지수 백오프 재시도)
- `_load_strategy()`: `strategies/config.py`의 `StrategyLoader`로 전략 동적 로드

### `framework/` — 추상화 레이어

| 파일 | 핵심 클래스 | 역할 |
|------|------------|------|
| `broker.py` | `BaseBroker`(ABC), `KISBroker`, `FundManager` | 계좌/포지션/자금 관리. `Position`, `AccountInfo` 데이터클래스 |
| `executor.py` | `OrderExecutor` | 매수/매도 주문 실행(동기+비동기). `OrderRequest` → `OrderResult`. KIS API 호출을 `ThreadPoolExecutor`로 래핑 |
| `data.py` | Facade 모듈 | `DataProvider`, `RealtimeDataCollector`, `MarketData` 등을 `data_providers/` 서브패키지에서 re-export |
| `data_providers/` | `DataProvider`, `DataStandardizer`, `CacheManager`, `SubscriptionManager` | 시세 데이터 수집·캐싱·구독 관리 |
| `utils.py` | 유틸리티 함수 | `setup_logger`, `now_kst`, `is_market_open`, `round_to_tick`, `load_config` 등 |
| `__init__.py` | 패키지 export | 모든 public API를 한곳에서 import 가능 |

### `strategies/` — 전략 시스템

| 파일 | 핵심 클래스 | 역할 |
|------|------------|------|
| `base.py` | `BaseStrategy`(ABC), `Signal`, `SignalType`, `OrderInfo` | 전략 인터페이스 정의. 필수 추상 메서드: `generate_signal()`만. `on_init`/`on_market_open`/`on_order_filled`/`on_market_close`는 기본 구현 제공. `on_tick(ctx: TradingContext)`로 매매 루프 소유 가능. `holding_period` 속성으로 EOD 청산 제어 |
| `config.py` | `StrategyConfig`, `StrategyLoader` | YAML 설정 로드, 전략 클래스 동적 import. `strategies/{name}/strategy.py`에서 `BaseStrategy` 서브클래스를 자동 탐색 |
| `sample/` | `SampleStrategy` | MA5/20 크로스 + RSI 예제 |
| `momentum/` | `MomentumStrategy` | 연속 상승 모멘텀 |
| `mean_reversion/` | `MeanReversionStrategy` | MA 이탈 평균회귀 |
| `volume_breakout/` | `VolumeBreakoutStrategy` | 거래량 폭증 돌파 |
| `bb_reversion/` | `BBReversionStrategy` | 볼린저밴드 회귀 |
| `lynch/` | `LynchStrategy` | 피터 린치 스크리닝 |
| `sawkami/` | `SawkamiStrategy` | 사와카미 스크리닝 |

#### `Signal` 데이터클래스 (strategies/base.py)
- `signal_type`: `STRONG_BUY`, `BUY`, `HOLD`, `SELL`, `STRONG_SELL`
- `stock_code`, `confidence` (0-100), `target_price`, `stop_loss`, `reasons`, `metadata`

### `api/` — KIS API 래퍼

| 파일 | 역할 |
|------|------|
| `kis_auth.py` | OAuth 인증, 토큰 관리, Rate Limiting |
| `kis_order_api.py` | 매수/매도/정정/취소 주문 |
| `kis_chart_api.py` | 차트(분봉/일봉) 데이터 |
| `kis_account_api.py` | 계좌 잔고, 주문가능수량 |
| `kis_market_api.py` | 시장정보, 현재가, 보유종목 |
| `kis_financial_api.py` | 재무제표 데이터 |
| `kis_api_manager.py` | 위 모듈들의 통합 매니저 (`KISAPIManager`) |

### `core/` — 핵심 비즈니스 로직

| 파일/디렉토리 | 역할 |
|--------------|------|
| `orders/` | 주문 서브모듈 (order_base, order_executor, order_monitor, order_timeout, order_db_handler) |
| `trading/` | 매매 서브모듈 (order_execution, order_completion_handler, position_monitor, stock_state_manager) |
| `intraday/` | 장중 데이터 서브모듈 (data_collector, price_service, realtime_updater, data_quality, models) |
| `order_manager.py` | Facade — 실제 구현은 `orders/` 서브모듈 |
| `trading_context.py` | `TradingContext` — 전략용 안전 API 래퍼. `on_tick(ctx)`에서 사용. buy()/sell() 내부에 서킷브레이커/VI/시장방향 가드 내장 |
| `trading_decision_engine.py` | 매매 판단 엔진. Strategy가 있으면 `generate_signal()` 호출, Signal의 target_price/stop_loss 활용. 없으면 기본 손절/익절만 동작 |
| `fund_manager.py` | 자금 관리 (가상/실전) |
| `data_collector.py` | 실시간 데이터 수집 |
| `models.py` | `TradingConfig`, `StockState` 등 데이터 모델 |
| `telegram_integration.py` | 텔레그램 알림 연동 |
| `virtual_trading_manager.py` | 가상매매 시뮬레이션 |
| `price_calculator.py` | 가격 계산 유틸리티 |

### `bot/` — DayTradingBot 위임 핸들러

`main.py`의 `DayTradingBot`이 너무 비대해지지 않도록 기능별 분리:

| 파일 | 역할 |
|------|------|
| `initializer.py` | BotInitializer — 시스템 초기화 |
| `trading_analyzer.py` | TradingAnalyzer — 매수/매도 판단 분석 |
| `system_monitor.py` | SystemMonitor — 시스템 모니터링 |
| `liquidation_handler.py` | LiquidationHandler — 장마감 일괄청산 |
| `position_sync.py` | PositionSyncManager — 포지션 동기화 |
| `state_restorer.py` | StateRestorer — 상태 복원 |

### `config/` — 설정

| 파일 | 역할 |
|------|------|
| `settings.py` | 환경 설정 로드 (`.env` 기반) |
| `constants.py` | 상수 정의 (포트폴리오 크기, 타임아웃, 손절/익절 비율 등) |
| `market_hours.py` | 장 시작/종료 시간, 공휴일 판단 |

### `db/` — 데이터베이스

| 파일 | 역할 |
|------|------|
| `connection.py` | DB 연결 관리 |
| `database_manager.py` | DB 인터페이스 (CRUD) |
| `config.py` | DB 설정 |
| `repositories/` | 리포지토리 패턴 (base, candidate, price, trading, quant) |

### `utils/` — 유틸리티

- `korean_time.py`: 한국 시간 처리 (`now_kst`, `get_market_status`, `is_market_open`)
- `korean_holidays.py`: 공휴일 캘린더
- `logger.py`: 로깅 설정
- `async_helpers.py`: 비동기 헬퍼
- `price_utils.py`: 호가 단위 변환, 프로세스 중복 방지

---

## 전략 개발 방법

### 1. 전략 폴더 생성

```bash
cp -r strategies/sample strategies/my_strategy
```

### 2. 필수 파일 구조

```
strategies/my_strategy/
├── __init__.py
├── config.yaml      # 전략 파라미터
└── strategy.py      # BaseStrategy 상속 클래스 (클래스명은 *Strategy로 끝나야 함)
```

### 3. 최소 구현

`generate_signal()` 하나만 구현하면 됩니다 (`on_init` 등은 기본 구현 제공):

```python
from strategies.base import BaseStrategy, Signal, SignalType

class MyStrategy(BaseStrategy):
    name = "MyStrategy"
    version = "1.0.0"

    def generate_signal(self, stock_code, data, timeframe='daily'):
        # 매매 로직 구현
        ...
        return None  # 또는 Signal 반환
```

> `on_init`, `on_market_open`, `on_order_filled`, `on_market_close`는 필요 시 오버라이드.
> `on_tick(ctx: TradingContext)` 오버라이드로 매매 루프 직접 제어 가능 (고급).
> `holding_period = "swing"` 선언 시 EOD 청산 건너뜀.

### 4. Signal 반환

```python
return Signal(
    signal_type=SignalType.BUY,
    stock_code=stock_code,
    confidence=80,
    target_price=target,
    stop_loss=stop,
    reasons=["매수 이유"]
)
```

### 5. 설정에서 전략 활성화

`config.yaml` 또는 설정에서 `strategy.name`을 폴더명으로 지정하면 `StrategyLoader`가 자동 로드.

---

## main.py 동작 흐름

```
1. DayTradingBot.__init__()
   ├── 프로세스 중복 실행 방지 (PID 파일)
   ├── 설정 로드 (load_config)
   ├── 핵심 모듈 초기화 (KISBroker → DB → Telegram → DataCollector → OrderManager → ...)
   ├── 리팩토링된 핸들러 초기화 (BotInitializer, TradingAnalyzer, SystemMonitor, ...)
   └── _load_strategy() — 전략 동적 로드

2. bot.initialize()
   ├── BotInitializer.initialize_system()
   ├── 전략 초기화 (strategy.on_init)
   └── DecisionEngine + TradingManager에 전략 연결

3. bot.run_daily_cycle()
   └── asyncio.gather로 3개 태스크 병렬 실행
       ├── 메인트레이딩루프 (critical=True, 3초 간격)
       │   ├── [1/5] 데이터 수집
       │   ├── [2/5] 미체결 주문 확인
       │   ├── [3/5] check_positions_once (매 반복 — 손절/익절 모니터링)
       │   ├── [4/5] 전략 있으면 on_tick(ctx) (매 9초, 30초 타임아웃)
       │   │          없으면 기존 check_positions + _check_buy_signals fallback
       │   └── [5/5] EOD 일괄청산 체크
       ├── 시스템모니터링 (critical=False)
       └── 텔레그램 (critical=False)
       * 각 태스크는 _supervised_task로 감독 (실패 시 지수 백오프 재시도)

4. bot.shutdown()
```

---

## 테스트 구조

```
tests/
├── conftest.py                  # pytest 공통 fixture
├── test_framework/              # framework/ 모듈 단위 테스트
│   ├── test_broker.py
│   ├── test_data.py
│   ├── test_executor.py
│   └── test_utils.py
├── test_api.py                  # API 연동 테스트
├── test_database.py             # DB 테스트
├── test_decision_engine.py      # 매매 판단 엔진 테스트
├── test_fund_manager.py         # 자금 관리 테스트
├── test_models.py               # 데이터 모델 테스트
├── test_order_executor.py       # 주문 실행 테스트
├── test_e2e_scenarios.py        # E2E 시나리오 테스트
├── test_daily_data_failure.py   # 일봉 데이터 실패 테스트
├── dryrun/                      # 드라이런 (모의 실행)
│   ├── dry_run_bot.py
│   ├── mock_order_manager.py
│   └── run_dryrun.py
└── healthcheck/                 # 헬스체크
    └── run_healthcheck.py
```

실행:
```bash
pytest tests/ -v
pytest tests/test_framework/ -v    # framework 모듈만
python tests/dryrun/run_dryrun.py  # 모의 실행
```

---

## 개발 규칙 & 컨벤션

### 코드 스타일
- Python 3.8+ 호환
- 비동기: `asyncio` 기반 (`async/await`)
- 블로킹 API 호출은 `ThreadPoolExecutor`로 래핑 (executor.py 참고)
- 로깅: `utils.logger.setup_logger(__name__)` 사용
- 시간: 항상 `utils.korean_time.now_kst()` 사용 (KST 기준)

### 설계 패턴
- **Facade**: `order_manager.py`는 `orders/` 서브모듈의 Facade
- **Strategy**: `BaseStrategy` 추상 클래스 + 동적 로딩
- **Repository**: `db/repositories/`
- **Mixin**: `OrderExecutorMixin`, `OrderMonitorMixin` 등

### 파일 네이밍
- 모듈: `snake_case.py`
- 클래스: `PascalCase`
- 상수: `UPPER_SNAKE_CASE` (`config/constants.py`)
- 전략 폴더: `snake_case` (`strategies/my_strategy/`)

### 주의사항
- `.env`에 `APP_KEY`, `APP_SECRET` 등 API 키 설정 필수 (`.env.example` 참고)
- 가상매매 모드: `VIRTUAL_MODE=true`로 실제 주문 없이 테스트 가능
- 프로세스 중복 실행 방지: PID 파일 (`robotrader.pid`) 사용

### 문서
- `README.md` — 프로젝트 소개 및 빠른 시작
- `SYSTEM_FLOW.md` — 시스템 동작 흐름 상세
- `docs/ARCHITECTURE.md` — 시스템 아키텍처, 모듈 관계도
- `docs/TRADING_FLOW.md` — 매매 흐름 (초기화→루프→청산)
- `docs/STRATEGY_GUIDE.md` — 전략 개발 상세 가이드
- `docs/DATABASE.md` — DB 스키마 문서
- `docs/CONFIGURATION.md` — 설정 가이드

---

**마지막 업데이트**: 2026-03-07
