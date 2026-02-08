# 매매 흐름 (Trading Flow)

> 시스템 시작부터 장 마감까지의 전체 매매 흐름

---

## 전체 흐름 개요

```
시스템 시작
  ↓
초기화 (BotInitializer)
  ├── KISBroker 연결 (인증/토큰)
  ├── DB 연결 확인
  ├── 텔레그램 봇 시작
  ├── 전략 로드 (StrategyLoader)
  └── 상태 복원 (StateRestorer)
  ↓
일일 거래 사이클 (run_daily_cycle)
  ├── 메인 트레이딩 루프 (필수, 3초 간격)
  ├── 시스템 모니터링 (비필수)
  └── 텔레그램 (비필수)
  ↓
장 마감 → 정리 → shutdown
```

---

## 1. 시스템 초기화

```python
DayTradingBot.__init__()
├── 중복 프로세스 검사 (PID 파일)
├── 설정 로드 (config/key.ini + trading_config.json)
├── 핵심 모듈 초기화 (의존 순서)
│   KISBroker → DatabaseManager → TelegramIntegration
│   → DataCollector → OrderManager → IntradayManager
│   → TradingStockManager → TradingDecisionEngine → FundManager
├── bot/ 핸들러 초기화
└── 전략 로드 (_load_strategy)

await bot.initialize()
├── BotInitializer.initialize_system()
├── KISBroker.connect() — 토큰 발급
├── Strategy.on_init(broker, data_provider, executor)
└── DecisionEngine에 전략 연결
```

---

## 2. 메인 트레이딩 루프

3초 간격으로 순차 실행되는 핵심 루프:

```
while is_running and 장중:
  ┌─ 1. 데이터 수집 ──────────────────────┐
  │  data_collector.collect_once()          │
  │  → 보유/관심 종목 현재가 업데이트       │
  └────────────────────────────────────────┘
           ↓
  ┌─ 2. 미체결 주문 확인 ─────────────────┐
  │  order_manager.check_pending_orders()   │
  │  → 체결 확인, 타임아웃 처리             │
  └────────────────────────────────────────┘
           ↓
  ┌─ 3. 보유종목 체크 ────────────────────┐
  │  trading_manager.check_positions()      │
  │  → 현재가 업데이트                     │
  │  → 손절/익절 판단 (PositionMonitor)    │
  │  → 매도 시그널 시 주문 생성             │
  └────────────────────────────────────────┘
           ↓
  ┌─ 4. 매수 판단 (매 9초, 3회 중 1회) ──┐
  │  SELECTED 상태 종목 순회               │
  │  → 쿨다운 확인                         │
  │  → Strategy.generate_signal()          │
  │  → BUY Signal → 주문 실행              │
  └────────────────────────────────────────┘
           ↓
  ┌─ 5. EOD 일괄청산 체크 ────────────────┐
  │  15:00 도달 시 모든 포지션 시장가 매도  │
  │  (일 1회만 실행)                       │
  └────────────────────────────────────────┘
```

---

## 3. 종목 상태 흐름 (StockState)

```
SELECTED ──매수 주문──→ BUY_PENDING ──체결──→ POSITIONED
    ↑                      │                      │
    │                   취소/실패              매도 판단
    │                      ↓                      ↓
    │                   FAILED          SELL_CANDIDATE
    │                                         │
    │                                      매도 주문
    │                                         ↓
    └───── 재거래 가능 ──── COMPLETED ←── SELL_PENDING
```

**상태 설명:**
- `SELECTED`: 조건검색(스크리닝)으로 선정된 매수 후보
- `BUY_PENDING`: 매수 주문 제출 → 체결 대기
- `POSITIONED`: 매수 완료, 포지션 보유 중
- `SELL_CANDIDATE`: 매도 조건 충족, 매도 대기
- `SELL_PENDING`: 매도 주문 제출 → 체결 대기
- `COMPLETED`: 매매 사이클 완료
- `FAILED`: 주문 실패 또는 오류

---

## 4. 매매 판단 흐름

### 매수 판단

```
TradingAnalyzer.analyze_buy_decision(trading_stock)
  ↓
TradingDecisionEngine
  ├── Strategy 있음 → strategy.generate_signal(stock_code, data)
  │   └── Signal(BUY) 반환 시 → 매수 주문 실행
  └── Strategy 없음 → 매수 안함 (기본 동작)
  ↓
OrderManager.create_buy_order()
  ↓
KIS API 주문 실행 (api/kis_order_api.py)
  ↓
체결 모니터링 (order_monitor)
  ↓
on_order_filled() 콜백 → DB 저장 + 텔레그램 알림
```

### 매도 판단

```
PositionMonitor.check_position()
  ├── 손절 체크: 현재가 < 매수가 × (1 - stop_loss_rate)
  ├── 익절 체크: 현재가 > 매수가 × (1 + target_profit_rate)
  └── Strategy.generate_signal() → SELL Signal
  ↓
매도 주문 실행 → 체결 → COMPLETED
```

---

## 5. Task Supervisor (자동 복구)

모든 비동기 태스크는 `_supervised_task()`로 감싸져 실행:

```
supervised_task(name, factory, critical)
  └── 실패 시:
      ├── critical=True  → 최대 5회 재시도 (지수 백오프 10s~300s) → 실패 시 시스템 종료
      └── critical=False → 최대 5회 재시도 → 실패 시 포기 (시스템 계속 운영)
```

| 태스크 | critical | 설명 |
|--------|----------|------|
| 메인 트레이딩 루프 | ✅ | 핵심 매매 루프 |
| 시스템 모니터링 | ❌ | 메모리/CPU 감시 |
| 텔레그램 | ❌ | 알림/명령 처리 |

---

## 6. 장 마감 처리

```
15:00 (EOD 일괄청산)
  → LiquidationHandler.execute_end_of_day_liquidation()
  → 모든 보유 종목 시장가 매도
  → 체결 대기 → DB 기록

장 종료 (15:30)
  → Strategy.on_market_close() 콜백
  → 일일 매매 리포트 생성
  → shutdown()
      ├── KISBroker 연결 해제
      └── 리소스 정리
```

---

## 7. 가상매매 모드

`VirtualTradingManager`를 통해 실제 API 주문 없이 시뮬레이션:

- DB에 가상 주문/포지션 기록
- 현재가 기반으로 체결 시뮬레이션
- 동일한 전략 로직으로 검증 가능
- 설정: `config.paper_trading = True`
