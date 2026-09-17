# Sample Strategy — 이동평균 크로스 + RSI (예제 · 비활성)

## 개요

간단하지만 실제 동작하는 예제 전략이다. 새 전략을 만들 때 이 폴더를 복사해서 시작한다.
현재 `config/trading_config.json` `strategies[]` 에 없으므로 **라이브 봇은 로드하지 않는다**(라이브 8전략은 [../../docs/PAPER_STRATEGIES.md](../../docs/PAPER_STRATEGIES.md)).

클래스: `SampleStrategy` · `holding_period = "intraday"`(15:00 EOD 일괄청산 대상) · `accepts_volume_fallback = False`(거래량 폴백 후보를 받지 않음).

### 매수 조건 (`min_buy_signals`=1 개 이상 충족 시 · 값은 `config.yaml`)

| # | 조건 | 기준값 |
|---|------|--------|
| 1 | MA 상승 추세 | 5일 MA > 20일 MA 이고 RSI(14) < `rsi_entry_max`(60) |
| 2 | RSI 과매도 | RSI(14) < `rsi_oversold`(**40**) |
| 3 | 거래량 급증 | 당일 거래량 > 20일 평균 × `volume_multiplier`(1.5) |

공통 차단: 09:00~09:05(`market_open_skip_minutes`=5) 신규 진입 보류 · 09:05~09:08(`entry_block_window_start_min`=5 ~ `end_min`=8) 진입 차단.

### 매도 조건 (1개 이상 충족 시)

| # | 조건 | 기준값 |
|---|------|--------|
| 1 | 데드크로스 | 5일 MA 가 20일 MA 를 하향 돌파 |
| 2 | RSI 과매수 | RSI(14) > `rsi_overbought`(70) |
| 3 | 익절/손절 | `take_profit_pct` +10% · `stop_loss_pct` −5% |

프레임워크 백스톱(손절/익절·EOD 청산)은 전략과 별개로 `PositionMonitor` 가 매 3초 돌린다 — [../../docs/TRADING_FLOW.md §5](../../docs/TRADING_FLOW.md).

## 폴더 구성

```
strategies/sample/
├── __init__.py            # from .strategy import SampleStrategy
├── config.yaml            # strategy / parameters / risk_management / screening / target_stocks
├── strategy.py            # SampleStrategy(BaseStrategy)
├── screener.py            # SampleScreener + SampleScreenerAdapter(strategy_name="sample") — EOD 후보 스크리너
├── multiverse_grid.yaml   # 파라미터 최적화 그리드 (MultiverseEngine 용, 라이브 무관)
└── README.md              # 이 파일
```

로더가 요구하는 최소 파일은 `config.yaml` + `strategy.py` 다(`StrategyLoader.validate_strategy`). `screener.py` 가 없으면 후보(`screener_snapshots`)가 0건이라 라이브에서 한 종목도 평가되지 않는다.

## 설정 (config.yaml) — 현재 값

```yaml
strategy:
  name: "SampleStrategy"
  version: "1.0.0"

parameters:
  ma_short_period: 5
  ma_long_period: 20
  rsi_period: 14
  rsi_oversold: 40          # 조건2 기준선
  rsi_overbought: 70        # 매도 기준선
  rsi_entry_max: 60         # 조건1 과열 차단
  volume_multiplier: 1.5
  min_buy_signals: 1        # 매수에 필요한 최소 조건 수 (1~3)
  market_open_skip_minutes: 5
  entry_block_window_start_min: 5
  entry_block_window_end_min: 8

risk_management:
  max_position_size: 0.10   # 종목당 최대 비율
  stop_loss_pct: 0.05       # 손절 5%
  take_profit_pct: 0.10     # 익절 10%
  max_daily_trades: 5

screening:                  # screener.py 가 읽는 EOD 스크리너 파라미터
  rsi_period: 14
  rsi_max: 45.0
  rsi_trend_max: 60.0
  ma_short: 5
  ma_long: 20
  min_trading_value: 500000000
  trading_value_lookback: 20     # 거래대금 평균 산출 영업일 수
  max_candidates: 10

target_stocks: []           # 비우면 스크리너 후보를 따른다
```

`risk_management.*_pct` 는 로더가 0~1 범위를 검증한다(`StrategyConfig.validate`). tp/sl 은 이 섹션에서 읽힌다 — Signal 의 `target_price`/`stop_loss` 는 2026-06-25 부터 tp/sl 에 쓰이지 않는다.

## 새 전략 만들기

### 1. 폴더 복사

```bash
cp -r strategies/sample strategies/my_strategy
```

복사하면 `screener.py` 의 `SampleScreenerAdapter(strategy_name="sample")` 가 딸려온다 — 3단계에서 반드시 바꾼다.

### 2. 클래스 이름 변경

`strategy.py` 의 클래스 이름은 **반드시 `Strategy` 로 끝나야** 로더가 찾는다(`StrategyLoader._load_strategy_class`).
`__init__.py` 의 import 도 함께 바꾼다.

```python
class MyStrategy(BaseStrategy):
    name = "MyStrategy"
    version = "1.0.0"
    holding_period = "intraday"   # 또는 "swing" (EOD 청산 건너뜀 · 매도 판단 일봉)
```

### 3. 스크리너 등록

- `screener.py` 의 어댑터 클래스명과 `strategy_name = "my_strategy"`(폴더명) 를 바꾼다.
- `runners/_adapter_factory.py` 의 `build_adapter()` if/elif 에 `"my_strategy"` 분기를 추가한다. 없으면 후보 0건.

### 4. 전략 로직 구현

`generate_signal(stock_code, data, timeframe='daily')` 에 매매 로직을 쓴다. 매수는 일봉(`timeframe='daily'`), 매도 판단은 `exit_timeframe`(intraday → 분봉 / swing → 일봉)으로 호출된다.

### 5. config.yaml 수정

`strategy.name` · `parameters` · `risk_management` 를 전략에 맞게 바꾼다.

### 6. 전략 활성화 — `config/trading_config.json`

```json
"strategies": [
  { "name": "my_strategy", "enabled": true, "max_capital_pct": 0.10,
    "regime_index": "KOSPI", "regime_gate": "none" }
]
```

`name` 은 **폴더명**이다. `strategies[]` 가 비어 있지 않으면 legacy `strategy.name` 은 무시된다. 봇은 재기동(다음 07:40)해야 반영된다.

## 전략 ↔ 프레임워크 연동

```
main.py (DayTradingBot)
  ├── _load_strategies()          → StrategyLoader.load_strategies(strategies[])  (legacy: load_strategy("sample"))
  ├── _initialize_strategy()      → strategy.on_init(broker, data_provider, executor)
  ├── _call_strategy_market_open()  → 첫 전략(self.strategy)의 on_market_open() 만
  ├── _main_trading_loop [4/5]    → strategy.on_tick(ctx)  (9초마다 전략 하나씩 라운드로빈 · 30초 타임아웃)
  │       └── 기본 on_tick 이 generate_signal(...) → ctx.buy() / ctx.sell()
  ├── PositionMonitor             → generate_signal(code, 분봉, timeframe='intraday') 매도 백스톱
  └── _check_eod_liquidation()    → 첫 전략의 on_market_close()
```

- **broker**: `framework.KISBroker` 인스턴스 (인증·계좌·시세)
- **data_provider**: `core.data_collector.RealTimeDataCollector` 인스턴스
- **executor**: `core.order_manager.OrderManager` 인스턴스

## 주의사항

- 필수 구현은 `generate_signal()` 하나다. `on_init` / `on_market_open` / `on_order_filled` / `on_market_close` / `on_tick` 은 기본 구현이 있다. `on_tick` 을 override 하면 **`async def`** 여야 한다.
- 클래스 이름은 반드시 `Strategy` 로 끝나야 한다.
- `config.yaml` 과 `strategy.py` 가 둘 다 있어야 유효한 전략이다. 후보를 받으려면 `screener.py` + 어댑터 팩토리 등록까지 필요하다.
- `target_stocks` 는 `SystemMonitor` 가 **첫 전략에 대해서만** 등록한다 — 다중 전략에서는 스크리너를 쓴다.
- 상세 절차·인터페이스·테스트 규약 → [../../docs/STRATEGY_GUIDE.md](../../docs/STRATEGY_GUIDE.md).
