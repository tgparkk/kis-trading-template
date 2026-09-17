# 전략 추가 가이드 (Strategy Development Guide)

새 매매 전략을 만들고 프레임워크에 **등록해서 후보를 받고 청산까지 돌게** 하는 방법. 모든 서명·키 이름은 `strategies/base.py` · `strategies/config.py` · `main.py` · `core/trading_context.py` · `runners/_adapter_factory.py` 에서 읽은 값이다.
런타임 전체 흐름은 [TRADING_FLOW.md](TRADING_FLOW.md), 활성 8전략 운영은 [PAPER_STRATEGIES.md](PAPER_STRATEGIES.md), 소유권 규칙은 [OWNERSHIP_MODEL.md](OWNERSHIP_MODEL.md).

> 🔴 2026-09-05 부터 개발 초점은 3전략(`book_pullback_ma20` · `minervini_volume_dryup` · `daytrading_3methods_breakout`)이고 나머지 5전략은 관측만 한다([plan_2026-09-05_focus3_roadmap.md](plan_2026-09-05_focus3_roadmap.md)). 새 전략을 라이브 `strategies[]` 에 넣는 것은 별도 결정 사항이다.

---

## 1. 전략 구조 개요

```
strategies/
├── base.py                  # BaseStrategy · Signal · SignalType · OrderInfo (수정 금지)
├── config.py                # StrategyLoader / StrategyConfig (로드·검증)
├── screener_base.py         # ScreenerBase ABC (EOD 스크리너 공통 인터페이스)
├── _rule_screener_base.py   # RuleScreenerBase — 활성 8전략 스크리너의 공통 부모
├── sample/                  # 예제 (비활성) — 복사 시작점
└── my_strategy/             # ← 새 전략 폴더 (폴더명 = 폴더키 = trading_config.json 의 name)
    ├── __init__.py
    ├── config.yaml
    ├── strategy.py
    ├── screener.py
    ├── README.md
    └── multiverse_grid.yaml  (선택 · 파라미터 탐색용)
```

- 로더가 요구하는 **최소 파일**은 `config.yaml` + `strategy.py` 다(`StrategyLoader.validate_strategy`).
- 하지만 라이브에서 **후보를 받으려면 `screener.py` + 어댑터 팩토리 등록**이 반드시 필요하다(§2 Step 4). 없으면 그 전략은 매일 후보 0건이다.
- 등록은 폴더 안이 아니라 `config/trading_config.json` `strategies[]` 에서 한다(§2 Step 6).

---

## 2. Step by Step: 새 전략 만들기

### Step 1: 폴더 생성

```bash
mkdir strategies/my_strategy
# 또는 예제 복사: cp -r strategies/sample strategies/my_strategy  (screener.py 의 strategy_name="sample" 도 딸려오므로 Step 4 에서 바꾼다)
```

### Step 2: config.yaml 작성

활성 8전략이 실제로 쓰는 최상위 키는 `strategy` · `paper_trading` · `parameters` · `risk_management` · `target_stocks` 다(스크리너 파라미터를 `screening` 절에 두는 전략도 있다).

```yaml
strategy:
  name: "MyStrategy"        # 없으면 로더가 폴더명으로 채운다 (StrategyConfig.load)
  version: "1.0.0"

paper_trading: true

parameters:                 # 전략이 self.config["parameters"] 로 읽는 값 — 키는 자유
  ma_period: 10
  threshold: 0.03
  max_holding_days: 20      # 프레임워크 max_hold 백스톱에 쓰려면 on_init 에서 self.max_holding_days 에 대입

risk_management:            # 프레임워크가 읽는 키 (아래 표)
  take_profit_pct: 0.10
  stop_loss_pct: 0.05
  max_positions: 5          # K — 가상 자본 K분할 · ΣK 동시보유 한도
  max_daily_trades: 5

target_stocks: []
```

| `risk_management` 키 | 읽는 곳 | 의미 |
|---|---|---|
| `take_profit_pct` / `stop_loss_pct` (없으면 `_ratio`) | `TradingDecisionEngine.execute_virtual_buy` 3순위 | 슬롯 tp/sl. 없으면 `trading_config.json risk_management` → DEFAULT(0.15/0.10). 손절 하한 3% |
| `max_positions` | `BotInitializer._allocate_strategy_capital` | K. 가상 자본 1천만/K 균등, ΣK 로 `fund_manager.max_position_count` 정정 |
| `paper_investment_per_stock` · `max_per_stock_amount` | 같은 곳 | 종목당 투자금 고정 / 상한 (선택) |
| 임의의 `*_pct` `*_ratio` `*_size` | `StrategyConfig.validate` | **0~1 범위 강제**(퍼센트포인트 임계값은 `PCT_THRESHOLD_WHITELIST` 예외) · `max_*` 정수는 음수 금지 |

> 옛 문서의 `portfolio_size` · `stop_loss_rate` 등은 어느 코드도 읽지 않는다.

### Step 3: strategy.py 작성

**클래스 이름은 반드시 `Strategy` 로 끝나야 한다** — `StrategyLoader._load_strategy_class` 가 모듈에서 `endswith('Strategy')` 이고 `BaseStrategy` 서브클래스인 첫 클래스를 고른다.

```python
"""My Strategy — 한 줄 설명"""
from typing import Optional
import pandas as pd
from ..base import BaseStrategy, Signal, SignalType


class MyStrategy(BaseStrategy):
    name = "MyStrategy"
    version = "1.0.0"
    description = "전략 한 줄 설명"
    author = "작성자"
    holding_period = "swing"        # "intraday"(EOD 청산) | "swing"(EOD 건너뜀 · 매도 판단 일봉)
    exit_timeframe = "daily"        # swing 이면 "daily" 이거나 미설정. "intraday" 로 두면 __init__ 이 ValueError
    accepts_volume_fallback = False # 전 전략 후보 0건일 때 거래량 폴백을 받을지

    def get_min_data_length(self) -> int:
        return 22                    # 가장 긴 지표 기간 + 여유. 기본값 20

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = 'daily',
    ) -> Optional[Signal]:
        if data is None or len(data) < self.get_min_data_length():
            return None
        close = data["close"]
        ma = close.rolling(10).mean()
        if timeframe == 'daily' and close.iloc[-1] > ma.iloc[-1] * 1.03:
            return Signal(
                signal_type=SignalType.BUY,
                stock_code=stock_code,
                confidence=75,
                reasons=["MA 돌파"],
            )
        if close.iloc[-1] < ma.iloc[-1]:
            return Signal(signal_type=SignalType.SELL, stock_code=stock_code,
                          confidence=70, reasons=["MA 이탈"])
        return None
```

- `generate_signal` 은 **매수(일봉, `timeframe='daily'`)와 매도(`exit_timeframe` 에 따라 `'daily'` 또는 `'intraday'`) 둘 다** 호출된다. `timeframe` 으로 갈라 쓴다.
- tp/sl 은 Signal 이 아니라 `config.yaml risk_management` 에 둔다. `Signal.target_price`/`stop_loss` 는 2026-06-25 부터 tp/sl 결정에 쓰이지 않는다.
- `on_tick` 을 override 하려면 **반드시 `async def on_tick(self, ctx)`** — 프레임워크가 `asyncio.wait_for(strat.on_tick(ctx), timeout=30)` 으로 부르므로 동기 `def` 로 쓰면 매 tick `TypeError` 다.

**`holding_period` / `exit_timeframe` 의미**

| `holding_period` | EOD 15:00 | `exit_timeframe` 자동값 | 매도 판단 데이터 |
|---|---|---|---|
| `"intraday"` (기본) | `should_liquidate_eod()` True → 시장가 청산, 이후 그날 매수 차단 | `"intraday"` | 분봉 |
| `"swing"` | 건너뜀(전략 청산 + 백스톱만) | `"daily"` | 확정 일봉 |

`"position"` 이라는 값은 **처리하는 코드가 없다** — 문자열로 남아 `exit_timeframe='intraday'` 로 떨어지고 EOD 도 건너뛴다. 쓰지 말 것. 라이브 8전략은 전부 `"swing"` + `"daily"` 다.

#### 고급 예제: 라이프사이클 활용

```python
class MyAdvancedStrategy(BaseStrategy):
    name = "MyAdvancedStrategy"
    holding_period = "swing"

    def on_init(self, broker, data_provider, executor) -> bool:
        super().on_init(broker, data_provider, executor)      # _broker/_data_provider/_executor 저장 + _is_initialized
        params = self.config.get("parameters", {})
        self._ma_period = int(params.get("ma_period", 10))
        self.max_holding_days = int(params.get("max_holding_days", 20))   # PositionMonitor 백스톱 연결
        self.positions = {}          # 주의: 프레임워크가 on_init «뒤» sync_positions() 로 복원분을 다시 넣는다
        self.daily_trades = 0
        return True

    def on_market_open(self) -> None:      # 첫 전략(self.strategy)에게만 호출된다 — 아래 §3 참고
        self.daily_trades = 0

    def generate_signal(self, stock_code, data, timeframe='daily'):
        ...

    def on_order_filled(self, order) -> None:          # OrderInfo(order_id, stock_code, side, quantity, price, filled_at)
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {"quantity": order.quantity, "entry_price": order.price,
                                                "entry_time": order.filled_at}
        else:
            self.positions.pop(order.stock_code, None)

    def on_market_close(self) -> None:     # 첫 전략에게만, 15:00 EOD 직후
        self.logger.info(f"장 마감 — 거래 {self.daily_trades}건")

    def validate_config(self) -> bool:     # False 면 StrategyConfigError → 기동 중단
        return self.config.get("risk_management", {}).get("stop_loss_pct", 0) > 0
```

### Step 4: screener.py + 어댑터 등록 (후보 공급)

라이브 후보는 **각 전략의 `screener_snapshots`(scan_date = 직전 거래일) 에서만** 온다(`CandidateSelector._fetch_candidates_for_strategy`). 스냅샷은 봇이 09:00 첫 반복에서 `runners/screener_snapshot_collector.run_once(활성 전략, D-1, max=20)` 로 만들고(생성은 20 · 라이브 «소비»는 `trading_config.json` `strategy.parameters.max_candidates` = **10**), 그때 전략명 → 어댑터는 `runners/_adapter_factory.build_adapter()` 의 **if/elif** 로 찾는다. 두 가지가 다 있어야 한다.

1. `strategies/my_strategy/screener.py` — 활성 8전략처럼 `RuleScreenerBase` 를 상속해 `strategy_name = "my_strategy"`(폴더명) 을 두고 **`base_filter(universe)` 와 `match(df, params)` 를 둘 다 구현**한다(둘 다 `@abstractmethod` — 하나라도 빠지면 인스턴스화 TypeError → `build_adapter()` 의 except 가 `None` 을 돌려줘 스냅샷 0건). `default_params()` 는 선택(기본 `{"max_candidates": 10}`) · `scan()` 은 베이스가 제공한다. 일봉 유니버스는 `daily_prices`(D-1 까지 확정봉) 다.
2. `runners/_adapter_factory.py` `build_adapter()` 에 분기 추가:

```python
elif strategy_name == "my_strategy":
    from strategies.my_strategy.screener import MyStrategyScreenerAdapter
    return MyStrategyScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
```

- 등록이 없으면 `알 수 없는 전략` 경고 후 `None` → 스냅샷 0건 → 매일 미진입.
- 거래량 순위 폴백은 **전 전략이 0건일 때만** 발동하고(`bot/candidate_loader.should_use_volume_fallback`), `accepts_volume_fallback=True` 인 첫 전략 하나에만 배정된다. 「내 전략만 0건」은 폴백이 아니라 정상 미진입이다.
- `config.yaml target_stocks` 는 `SystemMonitor._register_strategy_target_stocks` 가 **첫 전략(`bot.strategy`)에 대해서만** 등록한다 — 다중 전략 후보 공급 수단이 아니다.

### Step 5: \_\_init\_\_.py 작성

```python
from .strategy import MyStrategy
__all__ = ['MyStrategy']
```

`strategies/__init__.py` 에 추가 등록은 필요 없다 — 로더는 `strategies/{폴더}/strategy.py` 를 직접 import 한다.

### Step 6: 등록 — `config/trading_config.json` `strategies[]`

```json
"strategies": [
  { "name": "my_strategy", "enabled": true, "max_capital_pct": 0.10,
    "regime_index": "KOSPI", "regime_gate": "none" }
]
```

| 키 | 의미 |
|---|---|
| `name` | **폴더명**(폴더키). `StrategyLoader.load_strategies` 가 `load_strategy(name)` |
| `enabled` | false 면 로드 안 함 |
| `max_capital_pct` | 인스턴스 `max_capital_pct` 로 덮어씀(합계 > 1.0 이면 WARNING) |
| `regime_index` | 급락필터·국면게이트가 볼 지수: `"KOSPI"` / `"KOSDAQ"` / `"both"` / `"none"` / `"auto"`(종목 소속 시장) |
| `regime_gate` | `"none"` / `"exclude_bear"` / `"bull_only"` |

- `strategies[]` 가 **비어 있지 않으면** legacy `strategy.name` 은 무시된다(`main._load_strategies`). 루트 `config.yaml` 같은 파일은 없다.
- 반영은 봇 재기동(평일 07:40 자동) 때다. 라이브 트리에서 장중에 파일을 바꾸거나 브랜치를 전환하지 말 것.

---

## 3. BaseStrategy 인터페이스

### 필수 구현 메서드 (Abstract)

| 메서드 | 설명 |
|--------|------|
| `generate_signal(self, stock_code: str, data: pd.DataFrame, timeframe: str = 'daily') -> Optional[Signal]` | 매수(`'daily'`)·매도(`exit_timeframe`) 신호 생성. `None` 또는 `Signal` |

### 기본 제공 메서드 (오버라이드 가능)

| 메서드 | 기본 동작 · 호출 시점 |
|--------|------|
| `on_init(broker, data_provider, executor) -> bool` | `_broker/_data_provider/_executor` 저장 + `_is_initialized=True`. `initialize()` 에서 전략마다 1회. False/예외면 그 전략은 제거 |
| `sync_positions(positions: dict) -> None` | `self.positions.update(...)`. on_init «뒤» `StateRestorer.apply_pending_strategy_positions()` 가 호출(복원 포지션 재주입) |
| `on_market_open() -> None` | no-op. **첫 전략(`bot.strategy`)에게만** 09:00 첫 반복에서 호출(`main._call_strategy_market_open`) |
| `async on_tick(ctx: TradingContext)` | 기본 구현: SELECTED 순회 → `get_daily_data` → `generate_signal(…, 'daily')` → `ctx.buy`; POSITIONED 순회 → `exit_timeframe` 데이터 → `generate_signal` → `ctx.sell`. 9초마다 전략 하나씩 라운드로빈, 30초 타임아웃 |
| `on_order_filled(order: OrderInfo) -> None` | no-op. 가상: `TradingDecisionEngine._notify_strategy_order_filled` / 실전: `OrderCompletionHandler` 가 **소유 전략에게만** 통보 |
| `on_market_close() -> None` | no-op. **첫 전략에게만** 15:00 EOD 청산 직후(`main._check_eod_liquidation`) |
| `should_liquidate_eod(stock_code) -> bool` | `holding_period == "intraday"`. `LiquidationHandler` 가 종목마다 호출 |
| `get_min_data_length() -> int` | 20. 기본 on_tick 의 매수 평가 최소 봉 수 |
| `validate_config() -> bool` | True. False 면 `StrategyConfigError` → 기동 중단 |
| `get_config() -> dict` · `get_param(key, default)` | 설정 copy · dot notation(`'risk_management.stop_loss_pct'`) 조회 |
| `get_target_stocks() -> List[str]` | `config['target_stocks']`. 첫 전략에만 유효(§2 Step 4) |

### 클래스 속성

| 속성 | 기본값 | 설명 |
|------|--------|------|
| `name` / `version` / `description` / `author` | `"BaseStrategy"` / `"1.0.0"` / `""` / `""` | `name` 은 DB `strategy` 컬럼·로그 표기(클래스명 관례) |
| `holding_period` | `"intraday"` | `"intraday"` \| `"swing"`. EOD 청산·매수 차단·exit_timeframe 유도의 기준 |
| `exit_timeframe` | `None` → 자동 | `"daily"` \| `"intraday"`. swing+intraday 조합은 `__init__` 에서 `ValueError` |
| `max_capital_pct` | `1.0` | `strategies[]` 가 덮어씀 |
| `regime_index` / `regime_gate` | `"both"` / `"none"` | `strategies[]` 가 덮어씀 |
| `max_holding_days` | `None` | 정수면 `PositionMonitor` 가 초과 시 매도. 활성 전략은 `on_init` 에서 `parameters.max_holding_days` 로 채운다 |
| `accepts_volume_fallback` | `True` | 전 전략 0건 폴백 수용 여부 |

### TradingContext API (`core/trading_context.py`, on_tick 에서 사용)

| 메서드 | 설명 |
|--------|------|
| `ctx.get_selected_stocks(owner=None)` | SELECTED 목록. 기본은 **자기 전략(폴더키) 소유 + 소유자 미지정** 종목만. `owner` 지정 시 그 전략 소유만 |
| `ctx.get_positions()` | POSITIONED 목록(전체) |
| `await ctx.get_daily_data(stock_code, days=None)` | `daily_prices` 일봉. `days` 미지정 = `OHLCV_LOOKBACK_DAYS`(120 달력일). **당일 미확정 봉은 제거**되어 마지막 행이 확정봉 |
| `await ctx.get_intraday_data(stock_code)` | 분봉(`intraday_manager.get_combined_chart_data`) |
| `await ctx.get_current_price(stock_code)` | 현재가(캐시 → broker) |
| `await ctx.buy(stock_code, quantity=None, signal=None)` | 매수. 가드 11개(서킷브레이커 · 시장급락 · 국면게이트 · 소유 슬롯 · 중복 소유권 · VI · 일일 손실 한도 · `entry_min_price` 매수스톱 · EOD 이후 intraday · 상한가 접근 +25% · 진입 억제 15초/3건·60초) → `TradingAnalyzer.analyze_buy_decision`. 성공 시 `stock_code`, 아니면 `None` |
| `await ctx.sell(stock_code, quantity=None, reason="", signal=None)` | 매도. 소유권 불일치 거부 · `is_selling` 중복 방지 · 하한가는 경고만 → `analyze_sell_decision` |
| `ctx.get_available_funds()` / `get_total_funds()` / `get_max_buy_amount(code)` | FundManager 값 |
| `ctx.is_market_open()` / `ctx.get_market_phase()` / `ctx.get_current_time()` | phase 문자열은 `MarketPhase.value`: `closed` `pre_market` `pre_auction` `opening_protection` `market_open` `closing_cutoff` `closing_auction` `post_market` (`'regular'` 없음) |
| `ctx.log(msg, level="info")` | 전략 로그 |

### Signal 객체 (`strategies/base.py`)

```python
Signal(
    signal_type=SignalType.BUY,   # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    stock_code="005930",
    confidence=80.0,              # 0~100
    target_price=None,            # 참고값. tp 결정에는 쓰이지 않음 (2026-06-25 제거)
    stop_loss=None,               # 참고값. sl 결정에는 쓰이지 않음
    entry_min_price=None,         # 매수스톱 하한 — 현재가 < 이 값이면 ctx.buy 가 미돌파 스킵
    entry_max_price=None,         # 진입 상한 (갭/추격 차단)
    reasons=["사유1", "사유2"],
    metadata={},
)
```

속성: `is_buy` · `is_sell` · `is_strong` · `to_dict()`.

### generate_signal 의 data 파라미터

- 일봉(`ctx.get_daily_data` → `db/repositories/price.get_daily_prices`): 컬럼 **`date`**, `open`, `high`, `low`, `close`, `volume`. `date` 는 `pd.Timestamp`. 가격은 이미 분할조정, `volume` 은 읽기 시 `adj_factor` 를 곱한 값.
- 분봉(`ctx.get_intraday_data` / PositionMonitor 백스톱): `open/high/low/close/volume` 로 정규화된 프레임(`datetime` 계열 컬럼 포함 여부는 소스에 따라 다르므로 컬럼 존재를 확인하고 쓴다).
- `timeframe='daily'` = 매수 평가, `timeframe='intraday'` = intraday 전략의 매도 평가 + `PositionMonitor` 백스톱(모든 전략, 분봉). swing 전략의 on_tick 매도는 `'daily'` 로 온다 — `intraday` 로 게이트한 매도 로직은 swing 전략에서 절대 타지 않는다.

---

## 4. 제공 예제 전략 (비활성 · 참고용)

| 전략 | 폴더 | 핵심 로직 | holding |
|------|------|-----------|---|
| `SampleStrategy` | `sample/` | MA5/20 + RSI(14) + 거래량 ([README](../strategies/sample/README.md)) | intraday |
| `MomentumStrategy` | `momentum/` | N일 연속 상승 모멘텀 추세 추종 | swing |
| `MeanReversionStrategy` | `mean_reversion/` | MA20 대비 과도한 이탈 매수 · 평균 복귀 매도 | swing |
| `VolumeBreakoutStrategy` | `volume_breakout/` | 거래량 10배 폭증 + 양봉 돌파 | intraday |
| `BBReversionStrategy` · `LynchStrategy` · `SawkamiStrategy` | `bb_reversion/` `lynch/` `sawkami/` | BB 역추세 · 피터 린치 · 사와카미 (lynch/sawkami/sample 은 `api/` 직접 import — 신규 전략의 본보기로 삼지 말 것) | swing |

활성 8전략(라이브 운영)은 [PAPER_STRATEGIES.md](PAPER_STRATEGIES.md) 와 각 폴더 README.

---

## 5. 테스트 작성

### 규약

- 위치: **평면** `tests/test_<name>.py`(예: `tests/test_daytrading_3methods_breakout.py`, `tests/test_book_envelope_200d.py`) 가 현행 규약. 등록 검증은 선택적으로 `tests/strategies/<name>/test_registration.py`(현재 `rs_leader` · `deep_mr_dev20` 두 개 — `build_adapter()` 가 어댑터를 돌려주는지, `trading_config.json` 항목이 맞는지 단언).
- 마커·경로는 **레포 루트 `pyproject.toml`** 이 정한다: `testpaths = ["RoboTrader_template/tests"]` · `asyncio_mode = "auto"` · 마커 `slow`(느린 DB 조회) · `db`(실 DB `kis_template@5433` 필요 — 없으면 skip). DB 없는 곳에서는 `-m 'not db'`.
- `utils/logger` 는 pytest 아래에서 `logs/test_trading_YYYYMMDD.log` 로 분리한다. 그러나 `tests/dryrun/` · `tests/healthcheck/` 는 pytest 가 아닌 스크립트라 그 분리가 없다.
- 🔴 **라이브 트리(봇이 실제로 도는 체크아웃)에서 봇이 도는 동안 테스트·스모크를 돌리지 말 것** — `logs/` 오염·DB 풀 경합. `git worktree add` 로 별도 트리를 만들어 거기서 실행한다(회귀 판정은 실패 «집합» 차분).

### 예제 `tests/test_my_strategy.py`

```python
import numpy as np
import pandas as pd
from unittest.mock import MagicMock

from strategies.my_strategy.strategy import MyStrategy
from strategies.base import Signal


def make_ohlcv(days=40, base_price=10000.0):
    dates = pd.date_range("2025-01-01", periods=days, freq="B")
    close = np.full(days, base_price, dtype=float)
    return pd.DataFrame({
        "date": dates,                 # 라이브 일봉 컬럼명과 동일
        "open": close * 0.998, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.full(days, 100000.0),
    })


def test_init():
    s = MyStrategy({})
    assert s.on_init(MagicMock(), MagicMock(), MagicMock())
    assert s.is_initialized


def test_generate_signal_returns_none_or_signal():
    s = MyStrategy({})
    s.on_init(MagicMock(), MagicMock(), MagicMock())
    out = s.generate_signal("005930", make_ohlcv(), timeframe="daily")
    assert out is None or isinstance(out, Signal)


def test_swing_strategy_exits_on_daily():
    s = MyStrategy({})
    assert s.holding_period == "swing"
    assert s.exit_timeframe == "daily"
    assert s.should_liquidate_eod("005930") is False
```

`s.positions` 같은 전략 고유 속성은 `on_init` 에서 만든 경우에만 존재한다 — 최소 구현 전략에서 `s.positions[...]` 를 단언하면 `AttributeError` 다.

### 실행 (워크트리에서)

```bash
python -m pytest RoboTrader_template/tests/test_my_strategy.py -v       # 레포 루트에서
python -m pytest RoboTrader_template/tests -q -m 'not db and not slow'  # 빠른 회귀
```

---

## 6. 등록·교체는 `trading_config.json` 에서

전략 교체·on/off·자본 비율·regime 설정은 전부 `config/trading_config.json` `strategies[]` 항목이다(§2 Step 6). `main._load_strategies()` 가 `StrategyLoader.load_strategies(strategies[])` 를 호출하고, `enabled` 전략만 `{폴더키: 인스턴스}` 로 올린다. legacy `strategy.name` 경로는 `strategies[]` 가 비어 있을 때만 산다.

---

## 7. 체크리스트

새 전략을 등록하기 전:

- [ ] 클래스명이 `Strategy` 로 끝나고 `BaseStrategy` 를 상속한다
- [ ] `generate_signal(stock_code, data, timeframe='daily')` 서명 그대로 구현 · `None` 또는 `Signal` 반환 · 데이터 부족 시 `None`
- [ ] `holding_period` 를 `"intraday"` 또는 `"swing"` 으로 선언 (`"position"` 금지) · swing 이면 `exit_timeframe` 은 `"daily"` 또는 미설정
- [ ] `on_tick` 을 override 했다면 `async def`
- [ ] `config.yaml` — `strategy.name` · `risk_management.take_profit_pct/stop_loss_pct/max_positions` (0~1 범위)
- [ ] `screener.py`(`strategy_name` = 폴더명 · `base_filter` + `match` 둘 다 구현 — 둘 다 `@abstractmethod`) + `runners/_adapter_factory.py` 분기 추가
- [ ] `config/trading_config.json` `strategies[]` 에 `{name(폴더명), enabled, max_capital_pct, regime_index, regime_gate}`
- [ ] `tests/test_<name>.py` 작성 · 워크트리에서 통과 · 기존 실패 집합과 차분 0
- [ ] 폴더 `README.md` 작성(의도·진입/청산 룰·파라미터) 후 [PAPER_STRATEGIES.md](PAPER_STRATEGIES.md) 한눈표 갱신

---

**기준 코드**: `main` `16a8106` (2026-09-17) · **마지막 갱신**: 2026-09-17
