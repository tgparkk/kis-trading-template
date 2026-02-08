# 시스템 아키텍처

> KIS Trading Template의 전체 아키텍처와 모듈 관계도

---

## 레이어 구조

```
┌─────────────────────────────────────────────────┐
│  strategies/             전략 레이어             │
│  BaseStrategy 상속 → generate_signal() 구현      │
├─────────────────────────────────────────────────┤
│  framework/              추상화 레이어            │
│  KISBroker · DataProvider · OrderExecutor        │
├─────────────────────────────────────────────────┤
│  core/                   핵심 비즈니스 로직       │
│  TradingDecisionEngine · OrderManager · FundMgr  │
├─────────────────────────────────────────────────┤
│  bot/                    봇 운영 모듈            │
│  Initializer · Liquidation · Monitor · Sync      │
├─────────────────────────────────────────────────┤
│  api/                    KIS API 래퍼            │
│  Auth · Order · Chart · Account · Market · Fin   │
├─────────────────────────────────────────────────┤
│  db/ · config/ · utils/  인프라 레이어            │
│  TimescaleDB · Settings · Logger · KoreanTime    │
└─────────────────────────────────────────────────┘
```

---

## 모듈 관계도

### 진입점: `main.py`

`DayTradingBot` 클래스가 전체 시스템을 관장합니다.

```
DayTradingBot (main.py, ~500줄)
├── KISBroker (framework/broker.py)         — 증권사 API 추상화
├── DatabaseManager (db/)                   — TimescaleDB 연동
├── TelegramIntegration (core/)             — 알림/명령
├── RealTimeDataCollector (core/)           — 실시간 데이터 수집
├── OrderManager (core/)                    — 주문 생성/관리
├── IntradayStockManager (core/)            — 장중 종목 관리
├── TradingStockManager (core/)             — 매매 종목 상태 관리
├── TradingDecisionEngine (core/)           — 매매 판단
├── FundManager (core/)                     — 자금/포지션 관리
├── BotInitializer (bot/)                   — 시스템 초기화
├── TradingAnalyzer (bot/)                  — 매수/매도 분석
├── SystemMonitor (bot/)                    — 시스템 모니터링
├── LiquidationHandler (bot/)               — EOD 일괄청산
├── PositionSyncManager (bot/)              — 포지션 동기화
├── StateRestorer (bot/)                    — 상태 복원
└── BaseStrategy (strategies/)              — 플러그인 전략
```

### framework/ — 추상화 레이어

```
framework/
├── __init__.py          — 공개 API (KISBroker, OrderExecutor, DataProvider 등)
├── broker.py            — KISBroker: 인증, 계좌, 포지션, 자금 관리
│                          Position, AccountInfo, FundManager 데이터클래스
├── executor.py          — OrderExecutor: 주문 실행 추상화
│                          OrderRequest, OrderResult, OrderType/Side/Status
├── data.py              — DataProvider: 시장 데이터 제공 추상화
│                          RealtimeDataCollector, OHLCV, PriceQuote
├── utils.py             — 공통 유틸 (로깅, 시간, 가격 등)
└── data_providers/      — 데이터 제공자 구현체들
    ├── data_provider.py       — 메인 데이터 제공자
    ├── realtime_collector.py  — 실시간 데이터 수집
    ├── cache_manager.py       — 캐시 관리
    ├── data_standardizer.py   — 데이터 표준화
    ├── subscription_manager.py — 구독 관리
    └── models.py              — 데이터 모델
```

### api/ — KIS API 래퍼

```
api/
├── kis_auth.py          — 인증 + 토큰 관리 + Rate Limiting
├── kis_api_manager.py   — API 매니저 (공통 HTTP 호출)
├── kis_order_api.py     — 주문 API (매수/매도/취소/조회)
├── kis_chart_api.py     — 차트 API (분봉/일봉 OHLCV)
├── kis_account_api.py   — 계좌 API (잔고/포지션)
├── kis_market_api.py    — 시장 정보 API (호가/체결)
└── kis_financial_api.py — 재무 데이터 API
```

### core/ — 비즈니스 로직

```
core/
├── models.py                    — 공통 데이터 모델 (StockState, Stock, OHLCVData 등)
├── trading_decision_engine.py   — 매매 판단 엔진 (Strategy 연동)
├── order_manager.py             — 주문 관리
├── fund_manager.py              — 자금 관리 (가상/실전)
├── data_collector.py            — 실시간 데이터 수집
├── trading_stock_manager.py     — 매매 종목 상태 관리
├── intraday_stock_manager.py    — 장중 종목 관리
├── price_calculator.py          — 가격 계산
├── telegram_integration.py      — 텔레그램 봇 연동
├── virtual_trading_manager.py   — 가상매매 관리
├── trend_momentum_analyzer.py   — 추세/모멘텀 분석
│
├── orders/                      — 주문 서브모듈
│   ├── order_base.py            — 주문 기본 클래스
│   ├── order_executor.py        — 주문 실행
│   ├── order_monitor.py         — 체결 모니터링
│   ├── order_timeout.py         — 주문 타임아웃 처리
│   └── order_db_handler.py      — 주문 DB 기록
│
├── trading/                     — 매매 서브모듈
│   ├── order_execution.py       — 주문 실행 흐름
│   ├── order_completion_handler.py — 체결 완료 처리
│   ├── position_monitor.py      — 포지션 모니터링
│   └── stock_state_manager.py   — 종목 상태 관리
│
└── intraday/                    — 장중 데이터 서브모듈
    ├── data_collector.py        — 장중 데이터 수집
    ├── price_service.py         — 가격 서비스
    ├── realtime_updater.py      — 실시간 업데이트
    ├── data_quality.py          — 데이터 품질 검증
    └── models.py                — 장중 데이터 모델
```

### db/ — 데이터베이스

```
db/
├── config.py            — DB 설정
├── connection.py        — 커넥션 관리
├── database_manager.py  — Facade (하위 Repository 통합)
└── repositories/        — Repository 패턴
    ├── base.py          — 기본 Repository
    ├── candidate.py     — 후보 종목
    ├── price.py         — 가격 데이터
    ├── trading.py       — 거래 기록
    └── quant.py         — 퀀트 데이터
```

DB: **TimescaleDB** (PostgreSQL 확장) — `docker-compose.yml`로 실행

---

## 주요 의존성

| 패키지 | 용도 |
|--------|------|
| pandas / numpy | 데이터 처리, 지표 계산 |
| requests / aiohttp | KIS API HTTP 호출 |
| psycopg2-binary | PostgreSQL 연결 |
| python-telegram-bot | 텔레그램 봇 |
| PyYAML | 전략 설정 파일 |
| matplotlib | 차트 시각화 |
| psutil | 시스템 모니터링 |
| pytz / python-dateutil | 시간대 처리 |

---

## 설계 원칙

1. **전략-인프라 분리**: `strategies/`는 `framework/` 추상화만 의존, `api/`를 직접 호출하지 않음
2. **Facade 패턴**: `DatabaseManager`가 하위 Repository들을 통합
3. **Task Supervisor**: 메인 루프의 태스크들은 지수 백오프 재시도로 자동 복구
4. **가상매매 모드**: `VirtualTradingManager`로 실제 주문 없이 시뮬레이션
5. **플러그인 전략**: `BaseStrategy` 상속 + YAML 설정으로 전략 교체
