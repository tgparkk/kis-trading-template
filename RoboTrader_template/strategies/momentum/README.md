# Momentum Strategy — N일 연속 상승 모멘텀 추세 추종

## 개요

N일 연속 상승 모멘텀을 포착하여 추세 추종 매매를 수행하는 전략입니다.

- **클래스**: `MomentumStrategy`
- **버전**: 1.0.0

### 매수 조건 (모두 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | N일 연속 종가 상승 | 기본 5일 연속 종가가 전일 대비 상승 |
| 2 | 누적 상승률 충족 | 누적 상승률이 최소 기준(기본 3%) 이상 |

### 매도 조건 (1개 이상 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | 익절 | 수익률 +10% 도달 |
| 2 | 손절 | 수익률 -5% 도달 |
| 3 | 보유기간 초과 | 보유일 10일 초과 |
| 4 | 하락 전환 | 2일 연속 하락 발생 |

## 파일 구조

```
strategies/momentum/
├── config.yaml    # 전략 파라미터 설정
├── strategy.py    # 전략 로직 구현
└── README.md      # 이 파일
```

## 설정 (config.yaml)

주요 설정값을 `config.yaml`에서 조정할 수 있습니다:

```yaml
parameters:
  consecutive_up_days: 5    # 연속 상승일 수
  min_daily_change_pct: 0.0 # 최소 일별 상승률 (%)
  min_total_change_pct: 3.0 # 최소 누적 상승률 (%)
  max_holding_days: 10      # 최대 보유일

risk_management:
  stop_loss_pct: 0.05       # 손절 5%
  take_profit_pct: 0.10     # 익절 10%
  max_daily_trades: 5       # 일일 최대 거래
```

## 전략 ↔ 프레임워크 연동

```
main.py (DayTradingBot)
  ├── _load_strategy()        → StrategyLoader.load_strategy("momentum")
  ├── _initialize_strategy()  → strategy.on_init(broker, data_provider, executor)
  ├── _call_strategy_market_open()   → strategy.on_market_open()
  ├── TradingDecisionEngine          → strategy.generate_signal(code, data)
  └── _call_strategy_market_close()  → strategy.on_market_close()
```

- **broker**: `KISAPIManager` 인스턴스 (계좌/시세 조회)
- **data_provider**: 현재 `None` 전달 (추후 `DataProvider` 연결 예정)
- **executor**: `OrderManager` 인스턴스 (주문 실행)

## 주의사항

- `BaseStrategy`의 추상 메서드 5개를 **모두** 구현해야 합니다
- 클래스 이름은 반드시 `Strategy`로 끝나야 로더가 인식합니다
- `config.yaml`과 `strategy.py`가 모두 있어야 유효한 전략으로 인식됩니다
