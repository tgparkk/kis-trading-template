# 전략 추가 가이드 (Strategy Development Guide)

새로운 매매 전략을 만들고 프레임워크에 등록하는 방법을 안내합니다.

---

## 1. 전략 구조 개요

```
strategies/
├── base.py              # BaseStrategy ABC (수정 금지)
├── config.py            # StrategyLoader / StrategyConfig
├── __init__.py          # 모듈 export
├── sample/              # 예제: MA 크로스 + RSI
├── momentum/            # 예제: 5일 연속 상승 모멘텀
├── mean_reversion/      # 예제: MA20 이탈 평균회귀
├── volume_breakout/     # 예제: 거래량 폭증 돌파
└── my_strategy/         # ← 새 전략 폴더
    ├── __init__.py
    ├── config.yaml
    └── strategy.py
```

각 전략은 **독립된 폴더**로 존재하며, 최소 3개 파일이 필요합니다:
- `strategy.py` — 전략 로직 (BaseStrategy 상속)
- `config.yaml` — 전략 파라미터 설정
- `__init__.py` — 모듈 export

---

## 2. Step by Step: 새 전략 만들기

### Step 1: 폴더 생성

```bash
mkdir strategies/my_strategy
```

### Step 2: config.yaml 작성

```yaml
strategy:
  name: "MyStrategy"
  version: "1.0.0"

parameters:
  ma_period: 10
  threshold: 0.03

risk_management:
  stop_loss_pct: 0.05
  take_profit_pct: 0.10
  max_daily_trades: 5

target_stocks: []
```

### Step 3: strategy.py 작성

**최소 구현** — `generate_signal()` 하나만 구현하면 동작합니다:

```python
"""
My Strategy — 간단한 설명
"""
from typing import Optional
import pandas as pd
from ..base import BaseStrategy, Signal, SignalType


class MyStrategy(BaseStrategy):
    """내 전략 설명"""

    name = "MyStrategy"
    version = "1.0.0"
    description = "전략 한줄 설명"
    author = "작성자"

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = 'daily',
    ) -> Optional[Signal]:
        if data is None or len(data) < 12:
            return None

        close = data["close"]
        ma = close.rolling(10).mean()

        if close.iloc[-1] > ma.iloc[-1] * 1.03:
            return Signal(
                signal_type=SignalType.BUY,
                stock_code=stock_code,
                confidence=75,
                target_price=float(close.iloc[-1]) * 1.10,
                stop_loss=float(close.iloc[-1]) * 0.95,
                reasons=["MA 돌파"],
            )

        return None
```

> `on_init`, `on_market_open`, `on_order_filled`, `on_market_close`는 기본 구현이 제공되므로 필요할 때만 오버라이드하세요.

**스윙 전략 예시** — `holding_period`만 선언하면 EOD 청산을 자동으로 건너뜁니다:

```python
class MySwingStrategy(BaseStrategy):
    name = "MySwingStrategy"
    holding_period = "swing"       # "intraday" | "swing" | "position"

    def generate_signal(self, stock_code, data, timeframe='daily'):
        ...
```

#### 고급 예제: 전체 라이프사이클 활용

```python
class MyAdvancedStrategy(BaseStrategy):
    name = "MyAdvancedStrategy"
    version = "1.0.0"

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._ma_period = params.get("ma_period", 10)

        risk = self.config.get("risk_management", {})
        self._stop_loss_pct = risk.get("stop_loss_pct", 0.05)
        self._take_profit_pct = risk.get("take_profit_pct", 0.10)

        self.positions = {}
        self.daily_trades = 0
        self._is_initialized = True
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0

    def generate_signal(self, stock_code, data, timeframe='daily'):
        if data is None or len(data) < self._ma_period + 2:
            return None
        # ... 전략 로직 ...
        return None

    def on_order_filled(self, order) -> None:
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {"entry_price": order.price}
        elif order.stock_code in self.positions:
            del self.positions[order.stock_code]

    def on_market_close(self) -> None:
        self.logger.info(f"장 마감 — 거래 {self.daily_trades}건")

    def validate_config(self) -> bool:
        """설정 유효성 커스텀 검증. False 반환 시 시스템 종료."""
        risk = self.config.get("risk_management", {})
        if risk.get("stop_loss_pct", 0) <= 0:
            self.logger.error("stop_loss_pct는 0보다 커야 합니다")
            return False
        return True
```

### Step 4: \_\_init\_\_.py 작성

```python
from .strategy import MyStrategy
__all__ = ['MyStrategy']
```

### Step 5: strategies/\_\_init\_\_.py에 등록 (선택)

```python
from .my_strategy import MyStrategy
# __all__에 'MyStrategy' 추가
```

> StrategyLoader는 `strategies/{name}/strategy.py`에서 자동으로 클래스를 찾으므로,
> `__init__.py` 등록 없이도 `StrategyLoader.load_strategy("my_strategy")`로 로드 가능합니다.

### Step 6: 설정에서 전략 교체

`config.yaml` (메인 설정):

```yaml
strategy:
  name: "my_strategy"    # ← 폴더 이름
  enabled: true
```

이것만으로 프레임워크가 새 전략을 자동 로드합니다.

---

## 3. BaseStrategy 인터페이스

### 필수 구현 메서드 (Abstract)

| 메서드 | 설명 |
|--------|------|
| `generate_signal(stock_code, data, timeframe) -> Optional[Signal]` | 매매 신호 생성. 핵심 로직 |

### 기본 제공 메서드 (오버라이드 가능)

| 메서드 | 설명 |
|--------|------|
| `on_init(broker, data_provider, executor) -> bool` | 초기화. 기본 구현이 broker/data_provider/executor를 저장 |
| `on_market_open() -> None` | 장 시작 시 호출. 기본: no-op |
| `on_order_filled(order: OrderInfo) -> None` | 체결 시 호출. 기본: no-op |
| `on_market_close() -> None` | 장 마감 시 호출. 기본: no-op |
| `on_tick(ctx: TradingContext) -> None` | 매 사이클마다 호출. 기본 구현이 generate_signal 기반으로 매수/매도 판단 수행 |
| `should_liquidate_eod(stock_code) -> bool` | EOD 청산 여부. 기본: `holding_period == "intraday"`이면 True |
| `validate_config() -> bool` | 설정 유효성 검증. False 반환 시 `StrategyConfigError`로 시스템 종료 |
| `get_config() -> dict` | 전략 설정 반환 (copy) |
| `get_param(key, default)` | 설정값 조회 (dot notation 지원) |
| `get_target_stocks() -> List[str]` | 대상 종목 목록 |

### 클래스 속성

| 속성 | 기본값 | 설명 |
|------|--------|------|
| `name` | `"BaseStrategy"` | 전략 이름 |
| `version` | `"1.0.0"` | 전략 버전 |
| `holding_period` | `"intraday"` | 보유 기간. `"intraday"` \| `"swing"` \| `"position"`. `should_liquidate_eod()`로 EOD 청산 제어 |

### TradingContext API (on_tick에서 사용)

`on_tick(ctx)`를 오버라이드할 때 `ctx` 객체가 제공하는 메서드:

| 메서드 | 설명 |
|--------|------|
| `ctx.get_selected_stocks()` | SELECTED 상태 종목 목록 |
| `ctx.get_positions()` | 보유(POSITIONED) 종목 목록 |
| `ctx.get_daily_data(stock_code, days=60)` | 일봉 데이터 조회 (async) |
| `ctx.get_intraday_data(stock_code)` | 분봉 데이터 조회 (async) |
| `ctx.get_current_price(stock_code)` | 현재가 조회 (async) |
| `ctx.buy(stock_code, signal=signal)` | 매수 주문 (서킷브레이커/VI/시장방향 가드 내장, async) |
| `ctx.sell(stock_code, reason="...")` | 매도 주문 (중복 방지 내장, async) |
| `ctx.get_available_funds()` | 가용 자금 |
| `ctx.get_total_funds()` | 총 자금 |
| `ctx.is_market_open()` | 장 오픈 여부 |
| `ctx.get_market_phase()` | 시장 단계 (pre_market, regular 등) |

### Signal 객체

```python
Signal(
    signal_type=SignalType.BUY,   # BUY, SELL, STRONG_BUY, STRONG_SELL, HOLD
    stock_code="005930",
    confidence=80.0,              # 0~100
    target_price=75000,           # 익절 목표가 (TradingDecisionEngine에서 활용)
    stop_loss=68000,              # 손절가 (TradingDecisionEngine에서 활용)
    reasons=["사유1", "사유2"],    # 매매 사유
    metadata={},                  # 추가 데이터
)
```

### generate_signal의 data 파라미터

```
pd.DataFrame with columns:
  - datetime: 날짜/시간
  - open: 시가
  - high: 고가
  - low: 저가
  - close: 종가
  - volume: 거래량
```

- `timeframe='daily'` → 일봉 데이터 (매수 판단)
- `timeframe='intraday'` → 분봉 데이터 (매도 판단)

---

## 4. 제공 예제 전략

| 전략 | 폴더 | 핵심 로직 |
|------|------|-----------|
| SampleStrategy | `sample/` | MA5/20 크로스 + RSI(14) + 거래량 |
| MomentumStrategy | `momentum/` | 5일 연속 상승 → 매수, TP+10%/SL-5%/10일 보유 |
| MeanReversionStrategy | `mean_reversion/` | MA20 대비 -10% 이탈 → 매수, MA 복귀 → 매도 |
| VolumeBreakoutStrategy | `volume_breakout/` | 거래량 10배 폭증 + 양봉 → 매수 |

---

## 5. 테스트 작성

`tests/test_my_strategy.py`:

```python
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock
from strategies.my_strategy.strategy import MyStrategy
from strategies.base import Signal, OrderInfo


def make_ohlcv(days=30, base_price=10000):
    dates = pd.date_range("2025-01-01", periods=days, freq="B")
    close = np.full(days, base_price, dtype=float)
    return pd.DataFrame({
        "datetime": dates,
        "open": close * 0.998,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.full(days, 100000.0),
    })


def test_init():
    s = MyStrategy({})
    assert s.on_init(MagicMock(), MagicMock(), MagicMock())
    assert s.is_initialized


def test_generate_signal_returns_none_or_signal():
    s = MyStrategy({})
    s.on_init(MagicMock(), MagicMock(), MagicMock())
    result = s.generate_signal("005930", make_ohlcv())
    assert result is None or isinstance(result, Signal)


def test_sell_on_take_profit():
    s = MyStrategy({"risk_management": {"take_profit_pct": 0.10}})
    s.on_init(MagicMock(), MagicMock(), MagicMock())
    s.positions["005930"] = {"entry_price": 10000}
    data = make_ohlcv(30, base_price=11500)
    signal = s.generate_signal("005930", data)
    assert signal is not None and signal.is_sell
```

실행:

```bash
python -m pytest tests/test_my_strategy.py -v
```

전체 테스트 (기존 + 신규):

```bash
python -m pytest tests/ -q
```

---

## 6. 설정으로 전략 교체

메인 `config.yaml`의 `strategy.name`만 변경하면 됩니다:

```yaml
# config.yaml
strategy:
  name: "momentum"          # sample, momentum, mean_reversion, volume_breakout
  enabled: true
```

`main.py`의 `_load_strategy()`가 `StrategyLoader.load_strategy(name)`을 호출하여 해당 폴더의 전략을 자동 로드합니다.

---

## 7. 체크리스트

새 전략을 배포하기 전:

- [ ] `generate_signal()` 구현 (유일한 필수 추상 메서드)
- [ ] `config.yaml` 작성 (strategy.name 필수)
- [ ] `generate_signal()`이 None 또는 Signal 반환
- [ ] 데이터 부족 시 안전하게 None 반환
- [ ] 익절/손절 로직 포함
- [ ] 테스트 작성 및 PASS
- [ ] 전체 테스트 실행하여 기존 테스트 미파손 확인
