# 새 전략 추가 가이드

RoboTrader Quant 시스템에 새로운 트레이딩 전략을 추가하는 방법을 설명합니다.

---

## 목차

1. [개요](#1-개요)
2. [전략 구조](#2-전략-구조)
3. [단계별 가이드](#3-단계별-가이드)
4. [BaseStrategy 인터페이스](#4-basestrategy-인터페이스)
5. [설정 파일 (config.yaml)](#5-설정-파일-configyaml)
6. [예제: 모멘텀 전략 구현](#6-예제-모멘텀-전략-구현)
7. [테스트 방법](#7-테스트-방법)
8. [체크리스트](#8-체크리스트)

---

## 1. 개요

### 전략 템플릿 시스템

RoboTrader Quant는 플러그인 방식의 전략 시스템을 제공합니다. 모든 전략은 `BaseStrategy` 클래스를 상속하여 구현하며, 프레임워크가 전략의 라이프사이클을 자동으로 관리합니다.

**핵심 특징:**
- 표준화된 인터페이스로 일관된 전략 구현
- 설정 파일(config.yaml)을 통한 파라미터 관리
- 브로커/데이터/실행기 컴포넌트 자동 주입
- 로깅 및 모니터링 자동 지원

### 디렉토리 구조

```
RoboTrader_quant/
├── strategy/
│   └── base.py              # BaseStrategy 클래스 정의
├── strategies/
│   ├── __init__.py
│   └── pullback/            # 예시: Pullback 전략
│       ├── __init__.py
│       ├── strategy.py      # 전략 구현
│       ├── config.yaml      # 파라미터 설정
│       ├── types.py         # 타입 정의
│       └── analyzers/       # 분석 모듈
│           ├── __init__.py
│           ├── candle.py
│           ├── volume.py
│           └── ...
└── tests/
    └── test_*.py            # 테스트 파일
```

---

## 2. 전략 구조

새 전략을 추가할 때 생성해야 하는 파일 구조입니다.

```
strategies/{your_strategy}/
├── __init__.py          # 모듈 초기화 및 export
├── strategy.py          # BaseStrategy 상속 구현
├── config.yaml          # 전략 파라미터 설정
├── types.py             # (선택) 데이터 타입 정의
└── analyzers/           # (선택) 분석 모듈
    ├── __init__.py
    └── ...
```

### 각 파일의 역할

| 파일 | 필수 여부 | 설명 |
|------|----------|------|
| `__init__.py` | 필수 | 전략 클래스와 주요 타입을 외부로 export |
| `strategy.py` | 필수 | `BaseStrategy`를 상속한 전략 클래스 구현 |
| `config.yaml` | 필수 | 전략 파라미터, 리스크 관리 설정 등 |
| `types.py` | 선택 | Enum, dataclass 등 타입 정의 |
| `analyzers/` | 선택 | 기술적 분석 모듈 (복잡한 전략인 경우) |

---

## 3. 단계별 가이드

### Step 1: 전략 폴더 생성

```bash
# 전략 디렉토리 생성
mkdir strategies/momentum
mkdir strategies/momentum/analyzers  # 필요한 경우
```

### Step 2: config.yaml 작성

전략의 파라미터와 설정을 정의합니다.

```yaml
# strategies/momentum/config.yaml

strategy:
  name: momentum
  timeframe: 3min

parameters:
  # 모멘텀 지표
  roc_period: 10              # Rate of Change 기간
  momentum_threshold: 0.02     # 진입 모멘텀 임계값 (2%)

  # 이동평균
  fast_ma_period: 5
  slow_ma_period: 20

  # 볼륨 필터
  volume:
    min_ratio: 1.5            # 평균 대비 최소 거래량 배수

# 시그널 임계값
signals:
  strong_buy_threshold: 85
  buy_threshold: 70

# 리스크 관리
risk_management:
  target_profit_rate: 0.03    # 목표 수익률 3%
  stop_loss_rate: 0.02        # 손절률 2%
  max_position_ratio: 0.10    # 최대 포지션 비율 10%
  max_total_investment: 0.90  # 최대 총 투자 비율 90%

# 거래 시간
trading_hours:
  entry_start: "090500"
  entry_end: "150000"
  exit_deadline: "152000"

# 추가 필터
filters:
  min_price: 1000
  max_price: 500000
  min_daily_volume: 100000
```

### Step 3: strategy.py 구현

`BaseStrategy`를 상속하여 전략 클래스를 구현합니다.

```python
# strategies/momentum/strategy.py

"""
Momentum Strategy Implementation
================================

모멘텀 기반 트레이딩 전략.
"""

from typing import Optional, Dict, Any
import pandas as pd

from strategies.base import BaseStrategy, Signal, SignalType, OrderInfo


class MomentumStrategy(BaseStrategy):
    """
    모멘텀 기반 트레이딩 전략.

    진입 조건:
    1. ROC가 임계값 이상
    2. 빠른 이평선 > 느린 이평선
    3. 거래량이 평균의 1.5배 이상
    """

    # 전략 메타데이터
    name = "Momentum Strategy"
    version = "1.0.0"
    description = "Rate of Change 기반 모멘텀 전략"
    author = "Your Name"

    def __init__(self, config: Dict[str, Any] = None):
        """전략 초기화."""
        super().__init__(config)

        # 파라미터 로드
        self.params = config.get('parameters', {}) if config else {}
        self.risk_config = config.get('risk_management', {}) if config else {}

        # 내부 상태
        self._positions = {}
        self._daily_trades = 0

    def on_init(self, broker, data_provider, executor) -> bool:
        """
        프레임워크 컴포넌트로 초기화.

        Args:
            broker: 브로커 인스턴스
            data_provider: 데이터 제공자
            executor: 주문 실행기

        Returns:
            bool: 초기화 성공 여부
        """
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        # 브로커 연결 확인
        try:
            account = broker.get_account_info()
            if not account:
                if self.logger:
                    self.logger.error("계좌 정보 조회 실패")
                return False

            if self.logger:
                self.logger.info(
                    f"모멘텀 전략 초기화 완료 - "
                    f"가용 자금: {account.available_cash:,.0f}원"
                )
        except Exception as e:
            if self.logger:
                self.logger.error(f"초기화 오류: {e}")
            return False

        self._is_initialized = True
        return True

    def on_market_open(self) -> None:
        """장 시작 시 호출."""
        self._daily_trades = 0
        self._positions = {}

        if self.logger:
            self.logger.info("장 시작 - 모멘텀 전략 활성화")

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> Optional[Signal]:
        """
        트레이딩 시그널 생성.

        Args:
            stock_code: 종목 코드
            data: OHLCV 데이터프레임

        Returns:
            Signal: 시그널 객체 또는 None
        """
        # 데이터 검증
        if data is None or len(data) < 30:
            return None

        # 지표 계산
        roc = self._calculate_roc(data)
        fast_ma = self._calculate_ma(data, self.params.get('fast_ma_period', 5))
        slow_ma = self._calculate_ma(data, self.params.get('slow_ma_period', 20))
        volume_ratio = self._calculate_volume_ratio(data)

        # 조건 확인
        momentum_threshold = self.params.get('momentum_threshold', 0.02)
        min_volume_ratio = self.params.get('volume', {}).get('min_ratio', 1.5)

        has_momentum = roc > momentum_threshold
        has_ma_crossover = fast_ma > slow_ma
        has_volume = volume_ratio >= min_volume_ratio

        # 시그널 생성
        if has_momentum and has_ma_crossover and has_volume:
            current_price = float(data['close'].iloc[-1])

            # 목표가/손절가 계산
            tp_rate = self.risk_config.get('target_profit_rate', 0.03)
            sl_rate = self.risk_config.get('stop_loss_rate', 0.02)

            target_price = current_price * (1 + tp_rate)
            stop_price = current_price * (1 - sl_rate)

            # 신뢰도 계산
            confidence = self._calculate_confidence(roc, volume_ratio)

            # 시그널 타입 결정
            signal_type = SignalType.STRONG_BUY if confidence >= 85 else SignalType.BUY

            return Signal(
                signal_type=signal_type,
                stock_code=stock_code,
                confidence=confidence,
                target_price=target_price,
                stop_loss=stop_price,
                reasons=[
                    f"ROC: {roc*100:.2f}%",
                    f"이평선 정배열",
                    f"거래량 {volume_ratio:.1f}배"
                ],
                metadata={
                    'roc': roc,
                    'fast_ma': fast_ma,
                    'slow_ma': slow_ma,
                    'volume_ratio': volume_ratio
                }
            )

        return None

    def on_order_filled(self, order: OrderInfo) -> None:
        """주문 체결 시 호출."""
        if order.is_buy:
            self._positions[order.stock_code] = {
                'quantity': order.quantity,
                'entry_price': order.price,
                'entry_time': order.filled_at
            }
            self._daily_trades += 1

            if self.logger:
                self.logger.info(
                    f"매수 체결: {order.stock_code} "
                    f"{order.quantity}주 @ {order.price:,.0f}원"
                )
        else:
            if order.stock_code in self._positions:
                position = self._positions[order.stock_code]
                entry_price = position['entry_price']
                pnl_pct = (order.price - entry_price) / entry_price * 100

                del self._positions[order.stock_code]

                if self.logger:
                    self.logger.info(
                        f"매도 체결: {order.stock_code} "
                        f"{order.quantity}주 @ {order.price:,.0f}원 "
                        f"손익: {pnl_pct:+.2f}%"
                    )

    def on_market_close(self) -> None:
        """장 마감 시 호출."""
        if self.logger:
            self.logger.info(
                f"장 마감 - "
                f"일일 거래: {self._daily_trades}건, "
                f"미결 포지션: {len(self._positions)}개"
            )

    # ========================================================================
    # Private Methods
    # ========================================================================

    def _calculate_roc(self, data: pd.DataFrame) -> float:
        """Rate of Change 계산."""
        period = self.params.get('roc_period', 10)
        if len(data) < period + 1:
            return 0.0

        current = float(data['close'].iloc[-1])
        past = float(data['close'].iloc[-period-1])

        if past == 0:
            return 0.0

        return (current - past) / past

    def _calculate_ma(self, data: pd.DataFrame, period: int) -> float:
        """이동평균 계산."""
        if len(data) < period:
            return float(data['close'].iloc[-1])

        return float(data['close'].tail(period).mean())

    def _calculate_volume_ratio(self, data: pd.DataFrame) -> float:
        """거래량 비율 계산."""
        if len(data) < 20:
            return 1.0

        current_vol = float(data['volume'].iloc[-1])
        avg_vol = float(data['volume'].tail(20).mean())

        if avg_vol == 0:
            return 0.0

        return current_vol / avg_vol

    def _calculate_confidence(self, roc: float, volume_ratio: float) -> float:
        """신뢰도 계산."""
        base_score = 50

        # ROC 기반 점수 (최대 30점)
        roc_score = min(30, roc * 1000)

        # 거래량 기반 점수 (최대 20점)
        volume_score = min(20, (volume_ratio - 1) * 20)

        return min(100, base_score + roc_score + volume_score)
```

### Step 4: __init__.py 작성

모듈의 public API를 정의합니다.

```python
# strategies/momentum/__init__.py

"""
Momentum Strategy
=================

모멘텀 기반 트레이딩 전략.

진입 조건:
1. ROC(Rate of Change)가 임계값 이상
2. 빠른 이평선 > 느린 이평선 (정배열)
3. 거래량이 평균의 1.5배 이상

청산 조건:
1. 목표 수익률 도달: +3%
2. 손절: -2%
"""

from .strategy import MomentumStrategy

__all__ = [
    'MomentumStrategy',
]
```

### Step 5: 테스트

테스트 파일을 작성하여 전략을 검증합니다.

```python
# tests/test_momentum_strategy.py

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from strategies.momentum import MomentumStrategy


class TestMomentumStrategy:
    """모멘텀 전략 테스트."""

    @pytest.fixture
    def config(self):
        """테스트용 설정."""
        return {
            'parameters': {
                'roc_period': 10,
                'momentum_threshold': 0.02,
                'fast_ma_period': 5,
                'slow_ma_period': 20,
                'volume': {'min_ratio': 1.5}
            },
            'risk_management': {
                'target_profit_rate': 0.03,
                'stop_loss_rate': 0.02,
                'max_position_ratio': 0.10
            }
        }

    @pytest.fixture
    def strategy(self, config):
        """전략 인스턴스 생성."""
        return MomentumStrategy(config)

    @pytest.fixture
    def sample_data(self):
        """테스트용 OHLCV 데이터 생성."""
        dates = pd.date_range(end=datetime.now(), periods=50, freq='3min')

        # 상승 추세 데이터 생성
        base_price = 10000
        prices = base_price * (1 + np.cumsum(np.random.uniform(0.001, 0.003, 50)))

        return pd.DataFrame({
            'datetime': dates,
            'open': prices * 0.998,
            'high': prices * 1.005,
            'low': prices * 0.995,
            'close': prices,
            'volume': np.random.randint(100000, 500000, 50)
        })

    def test_strategy_initialization(self, strategy):
        """초기화 테스트."""
        assert strategy.name == "Momentum Strategy"
        assert strategy.version == "1.0.0"
        assert not strategy.is_initialized

    def test_generate_signal_with_momentum(self, strategy, sample_data):
        """모멘텀 시그널 생성 테스트."""
        # 마지막 거래량을 높여서 조건 충족
        sample_data.loc[sample_data.index[-1], 'volume'] = 1000000

        signal = strategy.generate_signal("005930", sample_data)

        # 시그널이 생성되거나 None (조건 미충족 시)
        if signal is not None:
            assert signal.stock_code == "005930"
            assert signal.confidence > 0
            assert len(signal.reasons) > 0

    def test_generate_signal_insufficient_data(self, strategy):
        """데이터 부족 시 None 반환 테스트."""
        short_data = pd.DataFrame({
            'datetime': pd.date_range(end=datetime.now(), periods=5, freq='3min'),
            'open': [100] * 5,
            'high': [101] * 5,
            'low': [99] * 5,
            'close': [100] * 5,
            'volume': [1000] * 5
        })

        signal = strategy.generate_signal("005930", short_data)
        assert signal is None
```

### Step 6: 실행

전략을 실제로 실행하는 방법입니다.

```python
# main.py (예시)

import yaml
from strategies.momentum import MomentumStrategy
from framework.broker import KISBroker
from framework.data import DataProvider
from framework.executor import OrderExecutor

def main():
    # 설정 로드
    with open('strategies/momentum/config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 전략 생성
    strategy = MomentumStrategy(config)

    # 컴포넌트 초기화
    broker = KISBroker()
    data_provider = DataProvider()
    executor = OrderExecutor(broker)

    # 전략 초기화
    if not strategy.on_init(broker, data_provider, executor):
        print("전략 초기화 실패")
        return

    # 장 시작
    strategy.on_market_open()

    # 시그널 생성 루프 (실제로는 스케줄러가 관리)
    for stock_code in ['005930', '000660', '035720']:
        data = data_provider.get_intraday_data(stock_code, timeframe='3min')
        signal = strategy.generate_signal(stock_code, data)

        if signal and signal.is_buy:
            print(f"매수 시그널: {signal}")

    # 장 마감
    strategy.on_market_close()

if __name__ == '__main__':
    main()
```

---

## 4. BaseStrategy 인터페이스

### 클래스 속성 (메타데이터)

| 속성 | 타입 | 설명 | 필수 |
|-----|------|------|------|
| `name` | str | 전략 이름 | 권장 |
| `version` | str | 버전 (예: "1.0.0") | 권장 |
| `description` | str | 전략 설명 | 선택 |
| `author` | str | 개발자 이름 | 선택 |

### 필수 메서드

#### `on_init(broker, data_provider, executor) -> bool`

**호출 시점:** API 연결 후 최초 1회

**목적:**
- 브로커/데이터/실행기 컴포넌트 저장
- 초기 데이터 로드
- 리소스 초기화

**매개변수:**
| 매개변수 | 타입 | 설명 |
|---------|------|------|
| `broker` | object | 계좌 정보, 포지션 조회용 |
| `data_provider` | object | 시장 데이터 조회용 |
| `executor` | object | 주문 실행용 |

**반환값:** `bool` - 초기화 성공 여부

```python
def on_init(self, broker, data_provider, executor) -> bool:
    self._broker = broker
    self._data_provider = data_provider
    self._executor = executor

    # 초기 데이터 로드
    self.historical = data_provider.get_daily_ohlcv("005930", days=60)

    self._is_initialized = True
    return True
```

---

#### `on_market_open() -> None`

**호출 시점:** 장 시작 (09:00 KST)

**목적:**
- 일일 카운터 리셋
- 워치리스트 준비
- 일일 상태 초기화

```python
def on_market_open(self) -> None:
    self._daily_trades = 0
    self._positions = {}
    self.logger.info("장 시작 - 전략 활성화")
```

---

#### `generate_signal(stock_code, data) -> Optional[Signal]`

**호출 시점:** 장중 주기적으로 호출 (예: 매 캔들마다)

**목적:**
- 트레이딩 시그널 생성
- 진입/청산 조건 판단

**매개변수:**
| 매개변수 | 타입 | 설명 |
|---------|------|------|
| `stock_code` | str | 종목 코드 (6자리, 예: "005930") |
| `data` | pd.DataFrame | OHLCV 데이터 |

**데이터프레임 컬럼:**
```
['datetime', 'open', 'high', 'low', 'close', 'volume']
```

**반환값:** `Signal` 객체 또는 `None`

```python
def generate_signal(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
    if len(data) < 20:
        return None

    if self._check_buy_condition(data):
        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=80,
            target_price=data['close'].iloc[-1] * 1.03,
            stop_loss=data['close'].iloc[-1] * 0.98,
            reasons=["매수 조건 충족"]
        )

    return None
```

---

#### `on_order_filled(order) -> None`

**호출 시점:** 주문 체결 시

**목적:**
- 포지션 추적
- 거래 기록
- 통계 업데이트

**매개변수:**
| 매개변수 | 타입 | 설명 |
|---------|------|------|
| `order` | OrderInfo | 체결 정보 |

```python
def on_order_filled(self, order: OrderInfo) -> None:
    if order.is_buy:
        self._positions[order.stock_code] = {
            'quantity': order.quantity,
            'entry_price': order.price,
            'entry_time': order.filled_at
        }
    else:
        if order.stock_code in self._positions:
            del self._positions[order.stock_code]
```

---

#### `on_market_close() -> None`

**호출 시점:** 장 마감 (15:30 KST)

**목적:**
- 일일 리포트 생성
- 상태 정리
- 데이터 저장

```python
def on_market_close(self) -> None:
    self.logger.info(f"일일 거래: {self._daily_trades}건")
    self._save_daily_report()
```

### 선택 메서드

#### `should_exit(stock_code, data) -> bool`

포지션 청산 여부를 판단합니다.

```python
def should_exit(self, stock_code: str, data: pd.DataFrame) -> bool:
    if stock_code not in self._positions:
        return False

    entry_price = self._positions[stock_code]['entry_price']
    current_price = float(data['close'].iloc[-1])

    # 목표 수익률 도달
    if current_price >= entry_price * 1.03:
        return True

    # 손절 조건
    if current_price <= entry_price * 0.98:
        return True

    return False
```

#### `get_param(key, default) -> Any`

설정 파라미터를 조회합니다. 점(.) 표기법으로 중첩 키 접근이 가능합니다.

```python
# config.yaml의 risk_management.stop_loss_rate 조회
stop_loss = self.get_param('risk_management.stop_loss_rate', 0.02)
```

---

## 5. 설정 파일 (config.yaml)

### 기본 구조

```yaml
# 전략 메타정보
strategy:
  name: strategy_name
  timeframe: 3min          # 1min, 3min, 5min, 10min, 30min, 60min

# 전략 파라미터
parameters:
  param1: value1
  nested:
    param2: value2

# 시그널 임계값
signals:
  strong_buy_threshold: 85
  buy_threshold: 70
  wait_threshold: 40

# 리스크 관리
risk_management:
  target_profit_rate: 0.025    # 목표 수익률
  stop_loss_rate: 0.015        # 손절률
  max_position_ratio: 0.09     # 종목당 최대 투자 비율
  max_total_investment: 0.90   # 전체 최대 투자 비율
  trailing_stop: false         # 추적 손절 사용 여부
  trailing_stop_trigger: 0.02  # 추적 손절 시작점
  trailing_stop_distance: 0.01 # 추적 손절 거리

# 거래 시간
trading_hours:
  entry_start: "090500"        # 진입 시작 시간
  entry_end: "150000"          # 진입 종료 시간
  exit_deadline: "152000"      # 강제 청산 시간

# 필터
filters:
  min_price: 1000              # 최소 주가
  max_price: 500000            # 최대 주가
  min_daily_volume: 100000     # 최소 일일 거래량
  max_gap_up: 0.10             # 최대 갭상승률
  max_gap_down: 0.05           # 최대 갭하락률
```

### 파라미터 접근 방법

```python
class MyStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)

        # 직접 접근
        self.params = config.get('parameters', {})

        # get_param 사용 (점 표기법 지원)
        self.stop_loss = self.get_param('risk_management.stop_loss_rate', 0.02)
```

### 설정 파일 로드 예시

```python
import yaml

def load_strategy_config(strategy_name: str) -> dict:
    """전략 설정 파일 로드."""
    config_path = f'strategies/{strategy_name}/config.yaml'

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
```

---

## 6. 예제: 모멘텀 전략 구현

### 전체 프로젝트 구조

```
strategies/momentum/
├── __init__.py
├── strategy.py
├── config.yaml
└── analyzers/
    ├── __init__.py
    └── momentum_analyzer.py
```

### config.yaml

```yaml
# strategies/momentum/config.yaml

strategy:
  name: momentum
  timeframe: 3min
  description: "ROC 기반 모멘텀 전략"

parameters:
  # 모멘텀 지표
  roc:
    period: 10
    threshold: 0.02

  # 이동평균
  moving_average:
    fast_period: 5
    slow_period: 20

  # RSI
  rsi:
    period: 14
    oversold: 30
    overbought: 70

  # 볼륨 필터
  volume:
    min_ratio: 1.5
    lookback: 20

signals:
  strong_buy_threshold: 85
  buy_threshold: 70

risk_management:
  target_profit_rate: 0.03
  stop_loss_rate: 0.02
  max_position_ratio: 0.10
  max_total_investment: 0.90

trading_hours:
  entry_start: "090500"
  entry_end: "150000"
  exit_deadline: "152000"

filters:
  min_price: 5000
  max_price: 300000
  min_daily_volume: 200000
```

### analyzers/momentum_analyzer.py

```python
# strategies/momentum/analyzers/momentum_analyzer.py

"""모멘텀 분석기."""

from dataclasses import dataclass
from typing import Dict, Any
import pandas as pd
import numpy as np


@dataclass
class MomentumAnalysis:
    """모멘텀 분석 결과."""
    roc: float                    # Rate of Change
    rsi: float                    # RSI
    fast_ma: float                # 빠른 이평선
    slow_ma: float                # 느린 이평선
    volume_ratio: float           # 거래량 비율
    is_uptrend: bool              # 상승 추세 여부
    is_volume_confirmed: bool     # 거래량 확인 여부

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환."""
        return {
            'roc': self.roc,
            'rsi': self.rsi,
            'fast_ma': self.fast_ma,
            'slow_ma': self.slow_ma,
            'volume_ratio': self.volume_ratio,
            'is_uptrend': self.is_uptrend,
            'is_volume_confirmed': self.is_volume_confirmed
        }


class MomentumAnalyzer:
    """모멘텀 분석기."""

    def __init__(self, config: Dict[str, Any] = None):
        """
        초기화.

        Args:
            config: 분석기 설정
        """
        config = config or {}

        self.roc_period = config.get('roc', {}).get('period', 10)
        self.roc_threshold = config.get('roc', {}).get('threshold', 0.02)
        self.fast_ma = config.get('moving_average', {}).get('fast_period', 5)
        self.slow_ma = config.get('moving_average', {}).get('slow_period', 20)
        self.rsi_period = config.get('rsi', {}).get('period', 14)
        self.volume_lookback = config.get('volume', {}).get('lookback', 20)
        self.min_volume_ratio = config.get('volume', {}).get('min_ratio', 1.5)

    def analyze(self, data: pd.DataFrame) -> MomentumAnalysis:
        """
        모멘텀 분석 수행.

        Args:
            data: OHLCV 데이터프레임

        Returns:
            MomentumAnalysis: 분석 결과
        """
        # ROC 계산
        roc = self._calculate_roc(data)

        # RSI 계산
        rsi = self._calculate_rsi(data)

        # 이평선 계산
        fast_ma_value = self._calculate_sma(data, self.fast_ma)
        slow_ma_value = self._calculate_sma(data, self.slow_ma)

        # 거래량 비율 계산
        volume_ratio = self._calculate_volume_ratio(data)

        return MomentumAnalysis(
            roc=roc,
            rsi=rsi,
            fast_ma=fast_ma_value,
            slow_ma=slow_ma_value,
            volume_ratio=volume_ratio,
            is_uptrend=fast_ma_value > slow_ma_value,
            is_volume_confirmed=volume_ratio >= self.min_volume_ratio
        )

    def _calculate_roc(self, data: pd.DataFrame) -> float:
        """Rate of Change 계산."""
        if len(data) < self.roc_period + 1:
            return 0.0

        current = float(data['close'].iloc[-1])
        past = float(data['close'].iloc[-self.roc_period - 1])

        if past == 0:
            return 0.0

        return (current - past) / past

    def _calculate_rsi(self, data: pd.DataFrame) -> float:
        """RSI 계산."""
        if len(data) < self.rsi_period + 1:
            return 50.0

        close = data['close'].tail(self.rsi_period + 1)
        delta = close.diff().dropna()

        gains = delta.where(delta > 0, 0)
        losses = (-delta).where(delta < 0, 0)

        avg_gain = float(gains.mean())
        avg_loss = float(losses.mean())

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calculate_sma(self, data: pd.DataFrame, period: int) -> float:
        """단순 이동평균 계산."""
        if len(data) < period:
            return float(data['close'].iloc[-1])

        return float(data['close'].tail(period).mean())

    def _calculate_volume_ratio(self, data: pd.DataFrame) -> float:
        """거래량 비율 계산."""
        if len(data) < self.volume_lookback:
            return 1.0

        current = float(data['volume'].iloc[-1])
        avg = float(data['volume'].tail(self.volume_lookback).mean())

        if avg == 0:
            return 0.0

        return current / avg
```

### analyzers/__init__.py

```python
# strategies/momentum/analyzers/__init__.py

"""모멘텀 전략 분석기."""

from .momentum_analyzer import MomentumAnalyzer, MomentumAnalysis

__all__ = [
    'MomentumAnalyzer',
    'MomentumAnalysis'
]
```

### strategy.py (분석기 사용 버전)

```python
# strategies/momentum/strategy.py

"""
Momentum Strategy Implementation
================================

ROC(Rate of Change) 기반 모멘텀 전략.

진입 조건:
1. ROC > 2%
2. 빠른 이평선 > 느린 이평선 (정배열)
3. RSI < 70 (과매수 아님)
4. 거래량 > 평균의 1.5배

청산 조건:
1. 목표 수익률: +3%
2. 손절: -2%
"""

from typing import Optional, Dict, Any
import pandas as pd

from strategies.base import BaseStrategy, Signal, SignalType, OrderInfo
from .analyzers import MomentumAnalyzer, MomentumAnalysis


class MomentumStrategy(BaseStrategy):
    """모멘텀 기반 트레이딩 전략."""

    # 전략 메타데이터
    name = "Momentum Strategy"
    version = "1.0.0"
    description = "ROC 기반 모멘텀 전략"
    author = "RoboTrader Quant"

    def __init__(self, config: Dict[str, Any] = None):
        """전략 초기화."""
        super().__init__(config)

        # 파라미터 로드
        self.params = config.get('parameters', {}) if config else {}
        self.risk_config = config.get('risk_management', {}) if config else {}
        self.signal_config = config.get('signals', {}) if config else {}

        # 분석기 초기화
        self.momentum_analyzer = MomentumAnalyzer(self.params)

        # 내부 상태
        self._positions = {}
        self._daily_trades = 0

    def on_init(self, broker, data_provider, executor) -> bool:
        """프레임워크 컴포넌트로 초기화."""
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        try:
            account = broker.get_account_info()
            if not account:
                if self.logger:
                    self.logger.error("계좌 정보 조회 실패")
                return False

            if self.logger:
                self.logger.info(
                    f"모멘텀 전략 초기화 - "
                    f"가용 자금: {account.available_cash:,.0f}원"
                )
        except Exception as e:
            if self.logger:
                self.logger.error(f"초기화 오류: {e}")
            return False

        self._is_initialized = True
        return True

    def on_market_open(self) -> None:
        """장 시작."""
        self._daily_trades = 0
        self._positions = {}

        if self.logger:
            tp = self.risk_config.get('target_profit_rate', 0.03)
            sl = self.risk_config.get('stop_loss_rate', 0.02)
            self.logger.info(
                f"장 시작 - 목표수익: {tp*100:.1f}%, 손절: {sl*100:.1f}%"
            )

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> Optional[Signal]:
        """트레이딩 시그널 생성."""
        # 데이터 검증
        min_candles = max(
            self.params.get('roc', {}).get('period', 10),
            self.params.get('moving_average', {}).get('slow_period', 20)
        ) + 5

        if data is None or len(data) < min_candles:
            return None

        # 모멘텀 분석
        analysis = self.momentum_analyzer.analyze(data)

        # 진입 조건 확인
        roc_threshold = self.params.get('roc', {}).get('threshold', 0.02)
        rsi_overbought = self.params.get('rsi', {}).get('overbought', 70)

        has_momentum = analysis.roc > roc_threshold
        has_uptrend = analysis.is_uptrend
        not_overbought = analysis.rsi < rsi_overbought
        has_volume = analysis.is_volume_confirmed

        if has_momentum and has_uptrend and not_overbought and has_volume:
            return self._create_buy_signal(stock_code, data, analysis)

        return None

    def _create_buy_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        analysis: MomentumAnalysis
    ) -> Signal:
        """매수 시그널 생성."""
        current_price = float(data['close'].iloc[-1])

        # 목표가/손절가 계산
        tp_rate = self.risk_config.get('target_profit_rate', 0.03)
        sl_rate = self.risk_config.get('stop_loss_rate', 0.02)

        target_price = current_price * (1 + tp_rate)
        stop_price = current_price * (1 - sl_rate)

        # 신뢰도 계산
        confidence = self._calculate_confidence(analysis)

        # 시그널 타입 결정
        strong_threshold = self.signal_config.get('strong_buy_threshold', 85)
        signal_type = SignalType.STRONG_BUY if confidence >= strong_threshold else SignalType.BUY

        return Signal(
            signal_type=signal_type,
            stock_code=stock_code,
            confidence=confidence,
            target_price=target_price,
            stop_loss=stop_price,
            reasons=[
                f"ROC: {analysis.roc*100:.2f}%",
                f"RSI: {analysis.rsi:.1f}",
                f"이평선 정배열",
                f"거래량 {analysis.volume_ratio:.1f}배"
            ],
            metadata=analysis.to_dict()
        )

    def _calculate_confidence(self, analysis: MomentumAnalysis) -> float:
        """신뢰도 계산."""
        base = 50

        # ROC 점수 (최대 20점)
        roc_score = min(20, analysis.roc * 500)

        # RSI 점수 (최대 15점) - 50 근처가 최적
        rsi_score = max(0, 15 - abs(analysis.rsi - 50) * 0.3)

        # 거래량 점수 (최대 15점)
        vol_score = min(15, (analysis.volume_ratio - 1) * 10)

        return min(100, base + roc_score + rsi_score + vol_score)

    def on_order_filled(self, order: OrderInfo) -> None:
        """주문 체결."""
        if order.is_buy:
            self._positions[order.stock_code] = {
                'quantity': order.quantity,
                'entry_price': order.price,
                'entry_time': order.filled_at
            }
            self._daily_trades += 1

            if self.logger:
                self.logger.info(
                    f"매수: {order.stock_code} "
                    f"{order.quantity}주 @ {order.price:,.0f}원"
                )
        else:
            if order.stock_code in self._positions:
                entry = self._positions[order.stock_code]['entry_price']
                pnl = (order.price - entry) / entry * 100

                del self._positions[order.stock_code]

                if self.logger:
                    self.logger.info(
                        f"매도: {order.stock_code} "
                        f"손익: {pnl:+.2f}%"
                    )

    def on_market_close(self) -> None:
        """장 마감."""
        if self.logger:
            self.logger.info(
                f"장 마감 - 거래: {self._daily_trades}건, "
                f"미결 포지션: {len(self._positions)}개"
            )

    def should_exit(self, stock_code: str, data: pd.DataFrame) -> bool:
        """청산 조건 확인."""
        if stock_code not in self._positions:
            return False

        entry_price = self._positions[stock_code]['entry_price']
        current_price = float(data['close'].iloc[-1])

        tp_rate = self.risk_config.get('target_profit_rate', 0.03)
        sl_rate = self.risk_config.get('stop_loss_rate', 0.02)

        # 목표 수익률 도달
        if current_price >= entry_price * (1 + tp_rate):
            return True

        # 손절
        if current_price <= entry_price * (1 - sl_rate):
            return True

        return False
```

### __init__.py

```python
# strategies/momentum/__init__.py

"""
Momentum Strategy
=================

ROC(Rate of Change) 기반 모멘텀 전략.

진입 조건:
1. ROC > 2%
2. 빠른 이평선 > 느린 이평선 (정배열)
3. RSI < 70 (과매수 아님)
4. 거래량 > 평균의 1.5배

청산 조건:
1. 목표 수익률: +3%
2. 손절: -2%
"""

from .strategy import MomentumStrategy

__all__ = [
    'MomentumStrategy',
]
```

---

## 7. 테스트 방법

### 단위 테스트 작성

```python
# tests/test_momentum_strategy.py

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from strategies.momentum import MomentumStrategy
from strategies.momentum.analyzers import MomentumAnalyzer


class TestMomentumAnalyzer:
    """모멘텀 분석기 테스트."""

    @pytest.fixture
    def analyzer(self):
        return MomentumAnalyzer({
            'roc': {'period': 10, 'threshold': 0.02},
            'moving_average': {'fast_period': 5, 'slow_period': 20},
            'rsi': {'period': 14},
            'volume': {'lookback': 20, 'min_ratio': 1.5}
        })

    @pytest.fixture
    def uptrend_data(self):
        """상승 추세 데이터."""
        dates = pd.date_range(end=datetime.now(), periods=50, freq='3min')
        base = 10000
        prices = [base * (1 + 0.002 * i) for i in range(50)]

        return pd.DataFrame({
            'datetime': dates,
            'open': [p * 0.998 for p in prices],
            'high': [p * 1.005 for p in prices],
            'low': [p * 0.995 for p in prices],
            'close': prices,
            'volume': [200000 + i * 10000 for i in range(50)]
        })

    def test_roc_calculation(self, analyzer, uptrend_data):
        """ROC 계산 테스트."""
        analysis = analyzer.analyze(uptrend_data)
        assert analysis.roc > 0  # 상승 추세이므로 양수

    def test_uptrend_detection(self, analyzer, uptrend_data):
        """상승 추세 감지 테스트."""
        analysis = analyzer.analyze(uptrend_data)
        assert analysis.is_uptrend is True


class TestMomentumStrategy:
    """모멘텀 전략 테스트."""

    @pytest.fixture
    def config(self):
        return {
            'parameters': {
                'roc': {'period': 10, 'threshold': 0.02},
                'moving_average': {'fast_period': 5, 'slow_period': 20},
                'rsi': {'period': 14, 'overbought': 70},
                'volume': {'lookback': 20, 'min_ratio': 1.5}
            },
            'signals': {
                'strong_buy_threshold': 85,
                'buy_threshold': 70
            },
            'risk_management': {
                'target_profit_rate': 0.03,
                'stop_loss_rate': 0.02,
                'max_position_ratio': 0.10
            }
        }

    @pytest.fixture
    def strategy(self, config):
        return MomentumStrategy(config)

    def test_strategy_metadata(self, strategy):
        """전략 메타데이터 테스트."""
        assert strategy.name == "Momentum Strategy"
        assert strategy.version == "1.0.0"

    def test_insufficient_data_returns_none(self, strategy):
        """데이터 부족 시 None 반환."""
        short_data = pd.DataFrame({
            'datetime': pd.date_range(end=datetime.now(), periods=5, freq='3min'),
            'open': [100] * 5,
            'high': [101] * 5,
            'low': [99] * 5,
            'close': [100] * 5,
            'volume': [1000] * 5
        })

        signal = strategy.generate_signal("005930", short_data)
        assert signal is None
```

### 테스트 실행

```bash
# 전체 테스트 실행
pytest tests/ -v

# 특정 테스트 파일 실행
pytest tests/test_momentum_strategy.py -v

# 커버리지 측정
pytest tests/ --cov=strategies/momentum --cov-report=html
```

### Dry-run 모드 사용

실제 주문 없이 전략을 테스트할 수 있습니다.

```python
# dry_run_test.py

import yaml
from strategies.momentum import MomentumStrategy


class MockBroker:
    """테스트용 Mock 브로커."""

    class AccountInfo:
        available_cash = 10_000_000
        total_equity = 10_000_000

    def get_account_info(self):
        return self.AccountInfo()


class MockDataProvider:
    """테스트용 Mock 데이터 제공자."""

    def get_intraday_data(self, stock_code, timeframe):
        import pandas as pd
        import numpy as np
        from datetime import datetime

        dates = pd.date_range(end=datetime.now(), periods=50, freq='3min')
        base = 10000
        prices = [base * (1 + np.random.uniform(-0.01, 0.02)) for _ in range(50)]

        return pd.DataFrame({
            'datetime': dates,
            'open': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'close': prices,
            'volume': np.random.randint(100000, 500000, 50)
        })


class MockExecutor:
    """테스트용 Mock 실행기."""

    def place_order(self, order):
        print(f"[DRY-RUN] 주문: {order}")


def run_dry_test():
    """Dry-run 테스트 실행."""
    # 설정 로드
    with open('strategies/momentum/config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 전략 초기화
    strategy = MomentumStrategy(config)

    # Mock 컴포넌트로 초기화
    broker = MockBroker()
    data_provider = MockDataProvider()
    executor = MockExecutor()

    if not strategy.on_init(broker, data_provider, executor):
        print("전략 초기화 실패")
        return

    # 장 시작
    strategy.on_market_open()

    # 시그널 테스트
    test_stocks = ['005930', '000660', '035720']

    for stock_code in test_stocks:
        data = data_provider.get_intraday_data(stock_code, '3min')
        signal = strategy.generate_signal(stock_code, data)

        if signal:
            print(f"\n[시그널] {stock_code}")
            print(f"  타입: {signal.signal_type.value}")
            print(f"  신뢰도: {signal.confidence:.1f}")
            print(f"  사유: {signal.reasons}")
        else:
            print(f"\n[{stock_code}] 시그널 없음")

    # 장 마감
    strategy.on_market_close()


if __name__ == '__main__':
    run_dry_test()
```

---

## 8. 체크리스트

새 전략을 추가할 때 아래 항목을 확인하세요.

### 필수 항목

- [ ] `strategies/{전략명}/` 폴더 생성
- [ ] `BaseStrategy` 클래스 상속
- [ ] 필수 메서드 구현
  - [ ] `on_init()`
  - [ ] `on_market_open()`
  - [ ] `generate_signal()`
  - [ ] `on_order_filled()`
  - [ ] `on_market_close()`
- [ ] `config.yaml` 작성
  - [ ] 전략 파라미터
  - [ ] 리스크 관리 설정
  - [ ] 거래 시간 설정
- [ ] `__init__.py` 작성
  - [ ] 전략 클래스 export

### 테스트 항목

- [ ] 단위 테스트 작성
- [ ] 데이터 부족 시 None 반환 확인
- [ ] 시그널 생성 로직 검증
- [ ] Dry-run 테스트 통과

### 문서화

- [ ] 전략 docstring 작성
- [ ] 진입/청산 조건 명시
- [ ] 파라미터 설명 추가

### 코드 품질

- [ ] 타입 힌트 사용
- [ ] 로깅 추가
- [ ] 예외 처리 구현
- [ ] 코드 리뷰 완료

---

## 참고 자료

### Signal 클래스

```python
@dataclass
class Signal:
    signal_type: SignalType    # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    stock_code: str            # 종목 코드
    confidence: float          # 신뢰도 (0-100)
    target_price: float        # 목표가
    stop_loss: float           # 손절가
    reasons: List[str]         # 시그널 사유
    metadata: Dict[str, Any]   # 추가 데이터
```

### OrderInfo 클래스

```python
@dataclass
class OrderInfo:
    order_id: str              # 주문 ID
    stock_code: str            # 종목 코드
    side: str                  # "buy" or "sell"
    quantity: int              # 수량
    price: float               # 체결가
    filled_at: datetime        # 체결 시간
```

### 기존 전략 참조

- `strategies/pullback/` - Pullback 패턴 기반 데이 트레이딩 전략
  - 복잡한 분석기 구조 참고
  - config.yaml 상세 설정 참고
  - 타입 정의 (types.py) 참고

---

*문서 작성일: 2024-02*
*RoboTrader Quant Team*
