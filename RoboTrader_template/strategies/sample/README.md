# Sample Strategy — 이동평균 크로스 + RSI

## 개요

간단하지만 실제 동작하는 예제 전략입니다. 새 전략을 만들 때 이 폴더를 복사해서 시작하세요.

### 매수 조건 (2개 이상 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | 골든크로스 | 5일 MA가 20일 MA를 상향 돌파 |
| 2 | RSI 과매도 탈출 | RSI(14)가 30 아래에서 위로 복귀 |
| 3 | 거래량 급증 | 당일 거래량이 20일 평균의 1.5배 이상 |

### 매도 조건 (1개 이상 충족 시)

| # | 조건 | 설명 |
|---|------|------|
| 1 | 데드크로스 | 5일 MA가 20일 MA를 하향 돌파 |
| 2 | RSI 과매수 | RSI(14)가 70 초과 |
| 3 | 익절/손절 | 수익률 +10% 또는 -5% 도달 |

## 파일 구조

```
strategies/sample/
├── config.yaml    # 전략 파라미터 설정
├── strategy.py    # 전략 로직 구현
└── README.md      # 이 파일
```

## 설정 (config.yaml)

주요 설정값을 `config.yaml`에서 조정할 수 있습니다:

```yaml
parameters:
  ma_short_period: 5      # 단기 이동평균
  ma_long_period: 20      # 장기 이동평균
  rsi_period: 14          # RSI 기간
  min_buy_signals: 2      # 매수에 필요한 최소 조건 수

risk_management:
  stop_loss_pct: 0.05     # 손절 5%
  take_profit_pct: 0.10   # 익절 10%
  max_daily_trades: 5     # 일일 최대 거래
```

## 새 전략 만들기

### 1. 폴더 복사

```bash
cp -r strategies/sample strategies/my_strategy
```

### 2. 클래스 이름 변경

`strategy.py`에서 클래스 이름을 변경합니다 (반드시 `Strategy`로 끝나야 함):

```python
class MyStrategy(BaseStrategy):
    name = "MyStrategy"
    version = "1.0.0"
    ...
```

### 3. 전략 로직 구현

`generate_signal()` 메서드에 자신만의 매매 로직을 구현합니다.

### 4. config.yaml 수정

전략에 필요한 파라미터를 정의합니다.

### 5. 전략 활성화

프로젝트 설정 파일(config)에서 전략 이름을 지정합니다:

```yaml
strategy:
  name: "my_strategy"    # strategies/ 아래 폴더명
  enabled: true
```

## 전략 ↔ 프레임워크 연동

```
main.py (DayTradingBot)
  ├── _load_strategy()        → StrategyLoader.load_strategy("sample")
  ├── _initialize_strategy()  → strategy.on_init(broker, data_provider, executor)
  ├── _call_strategy_market_open()   → strategy.on_market_open()
  ├── TradingDecisionEngine          → strategy.generate_signal(code, data)
  └── _call_strategy_market_close()  → strategy.on_market_close()
```

- **broker**: `KISAPIManager` 인스턴스 (계좌/시세 조회)
- **data_provider**: `DataProvider` 인스턴스 (시세 데이터 조회)
- **executor**: `OrderManager` 인스턴스 (주문 실행)

## 주의사항

- `generate_signal()` 하나만 필수 구현이며, `on_init`/`on_market_open`/`on_order_filled`/`on_market_close`는 필요 시 오버라이드합니다
- 클래스 이름은 반드시 `Strategy`로 끝나야 로더가 인식합니다
- `config.yaml`과 `strategy.py`가 모두 있어야 유효한 전략으로 인식됩니다
