# Trading Template Design Document

## 1. 개요

기존 RoboTrader_quant 프로젝트를 확장 가능한 템플릿 구조로 재설계합니다.
새로운 전략 추가 시 `strategies/` 폴더에 새 전략 폴더만 추가하면 되는 구조입니다.

---

## 2. 목표 구조

```
project/
├── framework/                # 공통 프레임워크 (건드리지 않음)
│   ├── __init__.py
│   ├── broker.py             # 한투 API 래퍼 (인증, 계좌 조회)
│   ├── executor.py           # 주문 실행 (매수/매도/정정/취소)
│   ├── data.py               # 시장 데이터 (분봉, 일봉, 실시간)
│   └── utils.py              # 유틸리티 (로깅, 시간, 가격 단위)
│
├── strategy/                 # 전략 인터페이스
│   ├── __init__.py
│   ├── base.py               # BaseStrategy 추상 클래스
│   └── config.py             # 전략 설정 로더 (YAML)
│
├── strategies/               # 전략별 폴더 (이것만 추가)
│   └── pullback/             # Pullback 전략 예시
│       ├── __init__.py
│       ├── strategy.py       # PullbackStrategy(BaseStrategy)
│       ├── config.yaml       # 전략 파라미터
│       └── analyzers/        # 전략 전용 분석기 (선택적)
│           ├── __init__.py
│           ├── candle.py
│           ├── volume.py
│           └── bisector.py
│
├── config/                   # 글로벌 설정
│   ├── key.ini               # API 키 (gitignore)
│   └── trading_config.json   # 공통 거래 설정
│
├── tests/                    # 테스트
│   ├── test_framework/
│   ├── test_strategy/
│   └── test_strategies/
│
└── main.py                   # 진입점 (--strategy 인자)
```

---

## 3. 파일 매핑 테이블

### 3.1 framework/ 매핑

| 현재 파일 | 새 위치 | 설명 |
|-----------|---------|------|
| `api/kis_auth.py` | `framework/broker.py` | 인증, 토큰 관리 |
| `api/kis_chart_api.py` | `framework/data.py` | 분봉/일봉 데이터 조회 |
| `api/kis_order_api.py` | `framework/executor.py` | 주문 실행 |
| `api/kis_api_manager.py` | `framework/broker.py` | API 매니저 통합 |
| `core/data_collector.py` | `framework/data.py` | 실시간 데이터 수집 |
| `core/fund_manager.py` | `framework/broker.py` | 자금 관리 |
| `utils/logger.py` | `framework/utils.py` | 로깅 |
| `utils/korean_time.py` | `framework/utils.py` | 한국 시간 유틸 |
| `utils/price_utils.py` | `framework/utils.py` | 호가 단위 처리 |
| `config/market_hours.py` | `framework/utils.py` | 장 시간 관리 |

### 3.2 strategy/ 매핑

| 현재 파일 | 새 위치 | 설명 |
|-----------|---------|------|
| 신규 | `strategy/base.py` | BaseStrategy 추상 클래스 |
| `config/settings.py` | `strategy/config.py` | 전략 설정 로더 |

### 3.3 strategies/pullback/ 매핑

| 현재 파일 | 새 위치 | 설명 |
|-----------|---------|------|
| `core/indicators/pullback/*.py` | `strategies/pullback/analyzers/` | 분석기 모듈들 |
| `core/trading_decision_engine.py` | `strategies/pullback/strategy.py` | 전략 로직 통합 |
| 신규 | `strategies/pullback/config.yaml` | 전략 파라미터 |

---

## 4. Framework 모듈 설계

### 4.1 framework/broker.py

```python
"""
한국투자증권 API 브로커 래퍼
"""
from dataclasses import dataclass
from typing import Optional, Dict, List
from abc import ABC, abstractmethod


@dataclass
class AccountInfo:
    """계좌 정보"""
    account_no: str
    total_balance: float
    available_cash: float
    invested_amount: float
    positions: List['Position']


@dataclass
class Position:
    """보유 포지션"""
    stock_code: str
    stock_name: str
    quantity: int
    avg_price: float
    current_price: float
    profit_loss: float
    profit_loss_rate: float


class BaseBroker(ABC):
    """브로커 추상 클래스"""

    @abstractmethod
    def initialize(self) -> bool:
        """API 초기화"""
        pass

    @abstractmethod
    def get_account_info(self) -> Optional[AccountInfo]:
        """계좌 정보 조회"""
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """보유 포지션 조회"""
        pass


class KISBroker(BaseBroker):
    """한국투자증권 브로커 구현"""

    def __init__(self, config_path: str = "config/key.ini"):
        self.config_path = config_path
        self._token = None
        self._initialized = False

    def initialize(self) -> bool:
        # 기존 kis_auth.py 로직 통합
        pass

    def get_account_info(self) -> Optional[AccountInfo]:
        # 기존 kis_api_manager.py의 get_account_balance 통합
        pass

    def get_positions(self) -> List[Position]:
        # 기존 잔고 조회 로직 통합
        pass
```

### 4.2 framework/executor.py

```python
"""
주문 실행 모듈
"""
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class OrderType(Enum):
    MARKET = "01"  # 시장가
    LIMIT = "00"   # 지정가


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """주문 정보"""
    order_id: str
    stock_code: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float
    status: str
    filled_quantity: int = 0
    filled_price: float = 0.0


class OrderExecutor:
    """주문 실행기"""

    def __init__(self, broker):
        self.broker = broker

    def buy(self, stock_code: str, quantity: int,
            price: float = 0, order_type: OrderType = OrderType.LIMIT) -> Optional[Order]:
        """매수 주문"""
        pass

    def sell(self, stock_code: str, quantity: int,
             price: float = 0, order_type: OrderType = OrderType.LIMIT) -> Optional[Order]:
        """매도 주문"""
        pass

    def cancel(self, order_id: str) -> bool:
        """주문 취소"""
        pass

    def modify(self, order_id: str, new_price: float, new_quantity: int) -> bool:
        """주문 정정"""
        pass

    def get_pending_orders(self) -> List[Order]:
        """미체결 주문 조회"""
        pass
```

### 4.3 framework/data.py

```python
"""
시장 데이터 모듈
"""
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
import pandas as pd


@dataclass
class OHLCV:
    """OHLCV 데이터"""
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketData:
    """시장 데이터 제공자"""

    def __init__(self, broker):
        self.broker = broker

    def get_minute_data(self, stock_code: str,
                        date: str = None,
                        minutes: int = 30) -> Optional[pd.DataFrame]:
        """분봉 데이터 조회"""
        pass

    def get_daily_data(self, stock_code: str,
                       days: int = 100) -> Optional[pd.DataFrame]:
        """일봉 데이터 조회"""
        pass

    def get_current_price(self, stock_code: str) -> Optional[float]:
        """현재가 조회"""
        pass

    def get_realtime_data(self, stock_code: str) -> Optional[OHLCV]:
        """실시간 데이터 (WebSocket)"""
        pass
```

### 4.4 framework/utils.py

```python
"""
유틸리티 모듈
"""
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path


# 한국 시간대
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """현재 한국 시간"""
    return datetime.now(KST)


def is_market_open(dt: datetime = None) -> bool:
    """장 운영 시간 확인"""
    if dt is None:
        dt = now_kst()

    # 주말 체크
    if dt.weekday() >= 5:
        return False

    # 장 시간 체크 (09:00 ~ 15:30)
    market_open = dt.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = dt.replace(hour=15, minute=30, second=0, microsecond=0)

    return market_open <= dt <= market_close


def round_to_tick(price: float) -> int:
    """KRX 호가 단위로 반올림"""
    if price <= 0:
        return 0

    # KRX 호가단위 테이블
    if price < 1000:
        tick = 1
    elif price < 5000:
        tick = 5
    elif price < 10000:
        tick = 10
    elif price < 50000:
        tick = 50
    elif price < 100000:
        tick = 100
    elif price < 500000:
        tick = 500
    else:
        tick = 1000

    return int(round(price / tick) * tick)


def setup_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """로거 설정"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"trading_{today}.log"

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 파일 핸들러
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
```

---

## 5. Strategy Interface 설계

### 5.1 strategy/base.py

```python
"""
전략 기본 인터페이스
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum
import pandas as pd


class Signal(Enum):
    """매매 신호"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class SignalResult:
    """신호 결과"""
    signal: Signal
    confidence: float        # 0-100 신뢰도
    reason: str             # 신호 근거
    target_price: float     # 목표가 (매수 시)
    stop_loss: float        # 손절가 (매수 시)
    quantity: int           # 추천 수량
    metadata: Dict[str, Any] = None  # 추가 정보


@dataclass
class OrderInfo:
    """체결 정보"""
    order_id: str
    stock_code: str
    side: str               # 'buy' or 'sell'
    quantity: int
    price: float
    filled_at: str          # 체결 시간


class BaseStrategy(ABC):
    """
    전략 기본 추상 클래스

    모든 전략은 이 클래스를 상속받아 구현합니다.

    Life Cycle:
    1. __init__() - 전략 인스턴스 생성
    2. on_init() - 초기화 (API 연결 후)
    3. on_market_open() - 장 시작 시
    4. generate_signal() - 매매 신호 생성 (반복 호출)
    5. on_order_filled() - 체결 시
    6. on_market_close() - 장 종료 시
    """

    def __init__(self, config: Dict[str, Any]):
        """
        전략 생성자

        Args:
            config: 전략 설정 (config.yaml에서 로드)
        """
        self.config = config
        self.name = config.get('name', self.__class__.__name__)
        self.positions: Dict[str, Any] = {}
        self.is_initialized = False

    @abstractmethod
    def on_init(self, broker, data_provider, executor) -> bool:
        """
        전략 초기화

        API 연결 후 호출됩니다.
        필요한 데이터 로드, 인디케이터 초기화 등을 수행합니다.

        Args:
            broker: 브로커 인스턴스 (계좌 정보, 잔고 조회)
            data_provider: 데이터 제공자 (분봉, 일봉 조회)
            executor: 주문 실행기 (매수, 매도 주문)

        Returns:
            bool: 초기화 성공 여부
        """
        pass

    @abstractmethod
    def on_market_open(self) -> None:
        """
        장 시작 시 호출

        09:00 장 시작 시 한 번 호출됩니다.
        당일 거래 준비, 전일 데이터 분석 등을 수행합니다.
        """
        pass

    @abstractmethod
    def generate_signal(self, stock_code: str, data: pd.DataFrame) -> Optional[SignalResult]:
        """
        매매 신호 생성

        주기적으로 호출되어 매매 신호를 생성합니다.

        Args:
            stock_code: 종목 코드
            data: OHLCV 데이터 (DataFrame)
                  columns: ['datetime', 'open', 'high', 'low', 'close', 'volume']

        Returns:
            SignalResult: 매매 신호 (BUY/SELL/HOLD)
            None: 신호 없음
        """
        pass

    @abstractmethod
    def on_order_filled(self, order: OrderInfo) -> None:
        """
        체결 시 호출

        주문이 체결되면 호출됩니다.
        포지션 업데이트, 통계 기록 등을 수행합니다.

        Args:
            order: 체결된 주문 정보
        """
        pass

    @abstractmethod
    def on_market_close(self) -> None:
        """
        장 종료 시 호출

        15:30 장 종료 시 한 번 호출됩니다.
        일일 통계 정리, 리포트 생성 등을 수행합니다.
        """
        pass

    def get_config(self) -> Dict[str, Any]:
        """
        전략 설정 반환

        Returns:
            Dict: 전략 설정
        """
        return self.config.copy()

    def get_name(self) -> str:
        """전략 이름 반환"""
        return self.name

    def get_positions(self) -> Dict[str, Any]:
        """현재 포지션 반환"""
        return self.positions.copy()

    def update_position(self, stock_code: str, position_info: Dict[str, Any]) -> None:
        """포지션 업데이트"""
        self.positions[stock_code] = position_info

    def remove_position(self, stock_code: str) -> None:
        """포지션 제거"""
        if stock_code in self.positions:
            del self.positions[stock_code]
```

### 5.2 strategy/config.py

```python
"""
전략 설정 로더
"""
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class StrategyConfig:
    """전략 설정 로더"""

    @staticmethod
    def load(strategy_name: str) -> Dict[str, Any]:
        """
        전략 설정 로드

        Args:
            strategy_name: 전략 이름 (폴더명)

        Returns:
            Dict: 전략 설정
        """
        config_path = Path(f"strategies/{strategy_name}/config.yaml")

        if not config_path.exists():
            raise FileNotFoundError(f"Strategy config not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 기본값 설정
        config.setdefault('name', strategy_name)
        config.setdefault('enabled', True)
        config.setdefault('risk_management', {})

        return config

    @staticmethod
    def load_strategy_class(strategy_name: str):
        """
        전략 클래스 동적 로드

        Args:
            strategy_name: 전략 이름 (폴더명)

        Returns:
            BaseStrategy 서브클래스
        """
        import importlib

        module_path = f"strategies.{strategy_name}.strategy"
        module = importlib.import_module(module_path)

        # 모듈에서 Strategy 클래스 찾기
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                attr_name.endswith('Strategy') and
                attr_name != 'BaseStrategy'):
                return attr

        raise ValueError(f"No Strategy class found in {module_path}")
```

---

## 6. Pullback 전략 구조 설계

### 6.1 strategies/pullback/config.yaml

```yaml
# Pullback 전략 설정
name: "Pullback"
description: "눌림목 패턴 기반 단타 전략"
enabled: true

# 전략 파라미터
parameters:
  # 선행 상승 조건
  prior_uptrend:
    min_gain_from_first: 0.04     # 첫봉 대비 최소 상승률 (4%)
    min_gain: 0.03                 # 구간 내 최소 상승률 (3%)
    lookback_period: 20            # 최대 탐색 봉 개수

  # 거래량 조건
  volume:
    low_volume_threshold: 0.25     # 저거래량 기준 (25%)
    recovery_threshold: 0.50       # 거래량 회복 기준 (50%)
    min_low_volume_candles: 2      # 최소 저거래량 캔들 개수

  # 이등분선 조건
  bisector:
    support_tolerance: 0.005       # 이등분선 지지 허용 범위 (0.5%)

  # 캔들 조건
  candle:
    min_body_pct: 0.5              # 최소 실체 크기 (0.5%)

# 리스크 관리
risk_management:
  take_profit_ratio: 0.03          # 익절 비율 (3%)
  stop_loss_ratio: 0.02            # 손절 비율 (2%)
  max_position_ratio: 0.10         # 종목당 최대 투자 비율 (10%)
  max_total_investment: 0.90       # 전체 최대 투자 비율 (90%)
  trailing_stop: false             # 트레일링 스탑 사용 여부

# 신호 임계값
signal_thresholds:
  strong_buy: 85                   # 강매수 신뢰도 기준
  cautious_buy: 70                 # 일반매수 신뢰도 기준
  wait: 40                         # 대기 신뢰도 기준
```

### 6.2 strategies/pullback/strategy.py (골격)

```python
"""
Pullback 전략 구현
"""
from typing import Optional, Dict, Any
import pandas as pd

from strategies.base import BaseStrategy, Signal, SignalResult, OrderInfo
from .analyzers.candle import CandleAnalyzer
from .analyzers.volume import VolumeAnalyzer
from .analyzers.bisector import BisectorAnalyzer


class PullbackStrategy(BaseStrategy):
    """
    눌림목 패턴 기반 단타 전략

    진입 조건:
    1. 선행 상승 (4% 이상)
    2. 저거래량 조정 (기준거래량의 25% 이하)
    3. 이등분선 지지
    4. 거래량 회복 양봉 출현

    청산 조건:
    1. 익절: 매수가 대비 +3%
    2. 손절: 매수가 대비 -2%
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # 분석기 초기화
        self.candle_analyzer = CandleAnalyzer()
        self.volume_analyzer = VolumeAnalyzer()
        self.bisector_analyzer = BisectorAnalyzer()

        # 설정 로드
        self.params = config.get('parameters', {})
        self.risk_config = config.get('risk_management', {})
        self.signal_thresholds = config.get('signal_thresholds', {})

    def on_init(self, broker, data_provider, executor) -> bool:
        """전략 초기화"""
        self.broker = broker
        self.data = data_provider
        self.executor = executor

        # 계좌 정보 확인
        account = broker.get_account_info()
        if not account:
            return False

        self.is_initialized = True
        return True

    def on_market_open(self) -> None:
        """장 시작 시"""
        # 전일 데이터 로드, 종목 리스트 갱신 등
        pass

    def generate_signal(self, stock_code: str, data: pd.DataFrame) -> Optional[SignalResult]:
        """매매 신호 생성"""
        if data is None or len(data) < 20:
            return None

        # 1. 선행 상승 확인
        if not self._check_prior_uptrend(data):
            return None

        # 2. 거래량 분석
        volume_analysis = self.volume_analyzer.analyze(data)

        # 3. 이등분선 분석
        bisector_status = self.bisector_analyzer.analyze(data)

        # 4. 캔들 분석
        candle_analysis = self.candle_analyzer.analyze(data)

        # 5. 신호 강도 계산
        confidence = self._calculate_confidence(
            volume_analysis, bisector_status, candle_analysis
        )

        # 6. 신호 결정
        if confidence >= self.signal_thresholds.get('cautious_buy', 70):
            signal = Signal.BUY
            reason = self._format_buy_reason(volume_analysis, bisector_status)

            current_price = float(data['close'].iloc[-1])
            target_price = current_price * (1 + self.risk_config.get('take_profit_ratio', 0.03))
            stop_loss = current_price * (1 - self.risk_config.get('stop_loss_ratio', 0.02))

            return SignalResult(
                signal=signal,
                confidence=confidence,
                reason=reason,
                target_price=target_price,
                stop_loss=stop_loss,
                quantity=self._calculate_quantity(stock_code, current_price),
                metadata={'volume_ratio': volume_analysis.volume_ratio}
            )

        return None

    def on_order_filled(self, order: OrderInfo) -> None:
        """체결 시"""
        if order.side == 'buy':
            self.update_position(order.stock_code, {
                'quantity': order.quantity,
                'avg_price': order.price,
                'filled_at': order.filled_at
            })
        else:
            self.remove_position(order.stock_code)

    def on_market_close(self) -> None:
        """장 종료 시"""
        # 일일 통계 정리
        pass

    def _check_prior_uptrend(self, data: pd.DataFrame) -> bool:
        """선행 상승 확인"""
        return self.candle_analyzer.check_prior_uptrend(
            data,
            min_gain=self.params.get('prior_uptrend', {}).get('min_gain', 0.03)
        )

    def _calculate_confidence(self, volume, bisector, candle) -> float:
        """신호 신뢰도 계산"""
        confidence = 0

        # 거래량 회복: +25
        if volume.is_high_volume:
            confidence += 25

        # 이등분선 지지: +20
        if bisector.is_holding:
            confidence += 20

        # 회복 양봉: +20
        if candle.is_bullish and candle.is_meaningful_body:
            confidence += 20

        # 거래량 급증: +10
        if volume.is_volume_surge:
            confidence += 10

        return min(100, confidence)

    def _calculate_quantity(self, stock_code: str, price: float) -> int:
        """매수 수량 계산"""
        account = self.broker.get_account_info()
        if not account:
            return 0

        max_ratio = self.risk_config.get('max_position_ratio', 0.10)
        max_amount = account.available_cash * max_ratio

        return int(max_amount / price)

    def _format_buy_reason(self, volume, bisector) -> str:
        """매수 근거 포맷팅"""
        reasons = []

        if volume.is_high_volume:
            reasons.append("거래량회복")
        if bisector.is_holding:
            reasons.append("이등분선지지")

        return " | ".join(reasons)
```

### 6.3 strategies/pullback/analyzers/ 구조

현재 `core/indicators/pullback/` 의 파일들을 이동:

- `candle_analyzer.py` → `strategies/pullback/analyzers/candle.py`
- `volume_analyzer.py` → `strategies/pullback/analyzers/volume.py`
- `bisector_analyzer.py` → `strategies/pullback/analyzers/bisector.py`
- `signal_calculator.py` → `strategies/pullback/strategy.py`에 통합
- `types.py` → `strategies/pullback/types.py`

---

## 7. main.py 설계

```python
"""
Trading Template Main Entry Point
"""
import asyncio
import argparse
import signal
import sys
from pathlib import Path

from framework.broker import KISBroker
from framework.executor import OrderExecutor
from framework.data import MarketData
from framework.utils import setup_logger, now_kst, is_market_open
from strategies.config import StrategyConfig


class TradingBot:
    """트레이딩 봇"""

    def __init__(self, strategy_name: str):
        self.logger = setup_logger(__name__)
        self.strategy_name = strategy_name
        self.is_running = False

        # 컴포넌트 초기화
        self.broker = KISBroker()
        self.data = MarketData(self.broker)
        self.executor = OrderExecutor(self.broker)
        self.strategy = None

    async def initialize(self) -> bool:
        """시스템 초기화"""
        self.logger.info(f"Initializing trading system with strategy: {self.strategy_name}")

        # 1. 브로커 초기화
        if not self.broker.initialize():
            self.logger.error("Failed to initialize broker")
            return False

        # 2. 전략 로드
        try:
            config = StrategyConfig.load(self.strategy_name)
            strategy_class = StrategyConfig.load_strategy_class(self.strategy_name)
            self.strategy = strategy_class(config)
        except Exception as e:
            self.logger.error(f"Failed to load strategy: {e}")
            return False

        # 3. 전략 초기화
        if not self.strategy.on_init(self.broker, self.data, self.executor):
            self.logger.error("Failed to initialize strategy")
            return False

        self.logger.info("System initialized successfully")
        return True

    async def run(self):
        """메인 실행 루프"""
        self.is_running = True

        while self.is_running:
            current_time = now_kst()

            # 장 시작
            if current_time.hour == 9 and current_time.minute == 0:
                self.strategy.on_market_open()

            # 장중 신호 생성
            if is_market_open():
                await self._process_signals()

            # 장 종료
            if current_time.hour == 15 and current_time.minute == 30:
                self.strategy.on_market_close()

            await asyncio.sleep(60)  # 1분 대기

    async def _process_signals(self):
        """신호 처리"""
        # 후보 종목별 신호 생성 및 처리
        pass

    def stop(self):
        """시스템 종료"""
        self.is_running = False


def main():
    """진입점"""
    parser = argparse.ArgumentParser(description='Trading Template')
    parser.add_argument(
        '--strategy', '-s',
        required=True,
        help='Strategy name (folder name in strategies/)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run in simulation mode (no real orders)'
    )
    args = parser.parse_args()

    # 전략 폴더 확인
    strategy_path = Path(f"strategies/{args.strategy}")
    if not strategy_path.exists():
        print(f"Error: Strategy '{args.strategy}' not found")
        print(f"Available strategies: {[p.name for p in Path('strategies').iterdir() if p.is_dir()]}")
        sys.exit(1)

    # 봇 실행
    bot = TradingBot(args.strategy)

    # 시그널 핸들러
    def signal_handler(signum, frame):
        bot.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 비동기 실행
    try:
        loop = asyncio.get_event_loop()

        if not loop.run_until_complete(bot.initialize()):
            sys.exit(1)

        loop.run_until_complete(bot.run())

    except KeyboardInterrupt:
        print("\nShutdown requested...")
    finally:
        bot.stop()


if __name__ == "__main__":
    main()
```

---

## 8. 테스트 계획

### 8.1 단위 테스트 (Agent 6)

| 테스트 파일 | 대상 | 테스트 내용 |
|------------|------|------------|
| `test_framework/test_broker.py` | `framework/broker.py` | 인증, 계좌 조회 |
| `test_framework/test_executor.py` | `framework/executor.py` | 주문 실행, 취소 |
| `test_framework/test_data.py` | `framework/data.py` | 분봉/일봉 데이터 조회 |
| `test_framework/test_utils.py` | `framework/utils.py` | 유틸리티 함수 |
| `test_strategy/test_base.py` | `strategy/base.py` | 인터페이스 계약 |
| `test_strategy/test_config.py` | `strategy/config.py` | YAML 로드 |
| `test_strategies/test_pullback.py` | `strategies/pullback/` | Pullback 전략 |

### 8.2 통합 테스트

```python
# tests/test_integration.py

def test_strategy_lifecycle():
    """전략 생명주기 테스트"""
    # 1. 전략 로드
    # 2. 초기화
    # 3. 신호 생성
    # 4. 체결 처리
    # 5. 종료
    pass

def test_main_with_strategy_arg():
    """main.py --strategy 인자 테스트"""
    pass
```

---

## 9. 개발 일정 및 우선순위

| Phase | Agent | 작업 | 예상 시간 | 의존성 |
|-------|-------|------|----------|--------|
| 1 | Agent 1 | 설계 문서 작성 | 완료 | - |
| 2 | Agent 2 | framework/ 개발 | 2h | Phase 1 |
| 2 | Agent 3 | strategy/ 개발 | 1h | Phase 1 |
| 3 | Agent 4 | pullback/ 구현 | 2h | Phase 2 |
| 4 | Agent 5 | main.py 작성 | 1h | Phase 2, 3 |
| 5 | Agent 6 | 테스트 수행 | 1h | 각 Phase 완료 시 |

---

## 10. 확장 가이드

새로운 전략 추가 시:

1. `strategies/` 폴더에 새 전략 폴더 생성
2. `config.yaml` 작성 (전략 파라미터)
3. `strategy.py` 작성 (BaseStrategy 상속)
4. 필요 시 `analyzers/` 폴더에 분석기 추가
5. 테스트 작성
6. `python main.py --strategy <new_strategy>` 로 실행

```bash
# 예시: 새로운 "momentum" 전략 추가
strategies/
└── momentum/
    ├── __init__.py
    ├── strategy.py      # MomentumStrategy(BaseStrategy)
    └── config.yaml      # 전략 파라미터

# 실행
python main.py --strategy momentum
```
