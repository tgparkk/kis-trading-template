# RoboTrader_quant 프로젝트 분석 리포트

## 문서 정보
- 분석 일자: 2026-02-03
- 분석 대상: `D:\GIT\kis-trading-template\RoboTrader_quant - 복사본`
- 목적: 프로젝트 구조 분석 및 템플릿화를 위한 권장사항 도출

---

## 1. 현재 프로젝트 구조 다이어그램

```
RoboTrader_quant/
├── main.py                           # 메인 진입점 (DayTradingBot 클래스)
│
├── api/                              # [공통 인프라] KIS API 래퍼
│   ├── __init__.py
│   ├── kis_auth.py                   # 인증/토큰 관리
│   ├── kis_api_manager.py            # API 통합 관리자 (Facade)
│   ├── kis_chart_api.py              # 차트/분봉 데이터 조회
│   ├── kis_order_api.py              # 주문 실행 (매수/매도/정정/취소)
│   ├── kis_account_api.py            # 계좌 정보 조회
│   ├── kis_market_api.py             # 시장 정보 조회
│   └── kis_financial_api.py          # 재무제표 조회
│
├── config/                           # [공통 인프라] 설정 관리
│   ├── settings.py                   # API 인증 정보 로더
│   ├── constants.py                  # 시스템 상수 정의
│   ├── market_hours.py               # 시장 시간/휴일 관리
│   ├── ml_settings.py                # ML 관련 설정
│   ├── key.ini                       # API 키 (비공개)
│   ├── trading_config.json           # 거래 설정
│   └── trend_exit_config.json        # 청산 설정
│
├── core/                             # 핵심 거래 로직
│   ├── models.py                     # [공통] 데이터 모델 정의
│   ├── data_collector.py             # [공통] 실시간 데이터 수집
│   ├── order_manager.py              # [공통] 주문 관리
│   ├── fund_manager.py               # [공통] 자금 관리
│   ├── intraday_stock_manager.py     # [공통] 장중 종목 관리
│   ├── trading_stock_manager.py      # [공통] 종목 상태 통합 관리
│   ├── trading_decision_engine.py    # [전략] 매매 판단 엔진 ★
│   ├── candidate_selector.py         # [전략] 후보 종목 선정 ★
│   ├── virtual_trading_manager.py    # [공통] 가상매매 관리
│   ├── telegram_integration.py       # [공통] 텔레그램 알림
│   ├── timeframe_converter.py        # [공통] 타임프레임 변환
│   ├── trend_momentum_analyzer.py    # [전략] 추세/모멘텀 분석 ★
│   ├── dynamic_profit_loss.py        # [전략] 동적 익절/손절 ★
│   │
│   ├── indicators/                   # [전략] 기술적 지표
│   │   ├── bollinger_bands.py        # 볼린저 밴드
│   │   ├── multi_bollinger_bands.py  # 멀티 볼린저
│   │   ├── bisector_line.py          # 이등분선
│   │   ├── price_box.py              # 가격 박스
│   │   ├── pullback_candle_pattern.py # 눌림목 캔들 패턴
│   │   └── pullback/                 # 눌림목 전략 모듈
│   │       ├── types.py              # 타입 정의
│   │       ├── volume_analyzer.py    # 거래량 분석
│   │       ├── candle_analyzer.py    # 캔들 분석
│   │       ├── bisector_analyzer.py  # 이등분선 분석
│   │       ├── risk_detector.py      # 위험 감지
│   │       └── signal_calculator.py  # 신호 계산
│   │
│   ├── quant/                        # [전략] 퀀트 시스템
│   │   ├── quant_screening_service.py     # 퀀트 스크리닝
│   │   ├── quant_rebalancing_service.py   # 리밸런싱 서비스
│   │   └── target_profit_loss_calculator.py # 목표가 계산
│   │
│   ├── factors/                      # [전략] 팩터 분석
│   │   ├── value_factor.py           # 가치 팩터
│   │   ├── momentum_factor.py        # 모멘텀 팩터
│   │   ├── quality_factor.py         # 퀄리티 팩터
│   │   └── growth_factor.py          # 성장 팩터
│   │
│   ├── helpers/                      # [공통] 헬퍼 모듈
│   │   ├── notification_helper.py    # 알림 헬퍼
│   │   ├── order_wait_helper.py      # 주문 대기 헬퍼
│   │   ├── keep_list_updater.py      # 보유 목록 갱신
│   │   ├── rebalancing_executor.py   # 리밸런싱 실행
│   │   ├── screening_task_runner.py  # 스크리닝 태스크 실행
│   │   └── state_restoration_helper.py # 상태 복원
│   │
│   └── tasks/                        # 비동기 태스크
│
├── db/                               # [공통 인프라] 데이터베이스
│   ├── database_manager.py           # DB 관리자 (SQLite)
│   └── cleanup_old_tables.py         # 테이블 정리
│
├── utils/                            # [공통 인프라] 유틸리티
│   ├── logger.py                     # 로깅
│   ├── korean_time.py                # 한국 시간 처리
│   ├── korean_holidays.py            # 한국 공휴일
│   ├── price_utils.py                # 가격 유틸리티
│   ├── data_cache.py                 # 데이터 캐시
│   ├── unified_data_loader.py        # 통합 데이터 로더
│   ├── signal_replay_utils.py        # 신호 리플레이
│   └── telegram/                     # 텔레그램 유틸
│
├── visualization/                    # [공통 인프라] 시각화
│   ├── chart_generator.py            # 차트 생성
│   ├── chart_renderer.py             # 차트 렌더링
│   ├── data_processor.py             # 데이터 처리
│   ├── signal_calculator.py          # 신호 계산
│   └── strategy_manager.py           # 전략 관리
│
├── strategies/                       # [전략] 전략 모듈 (현재 비어있음)
│   └── __init__.py
│
├── scripts/                          # 유틸리티 스크립트
│   ├── auto_analysis.py              # 자동 분석
│   ├── daily_trading_summary.py      # 일일 거래 요약
│   ├── save_portfolio_snapshot.py    # 포트폴리오 스냅샷
│   └── ...
│
├── backtests/                        # 백테스트
│   └── quant_monthly_backtest.py
│
├── tests/                            # 테스트
├── data/                             # 데이터 (SQLite DB)
├── logs/                             # 로그 파일
├── cache/                            # 캐시 데이터
└── reports/                          # 리포트
```

---

## 2. 전략 로직으로 분류되는 부분

### 2.1 핵심 전략 모듈 (core/)

| 파일 | 역할 | 전략 의존성 |
|------|------|-------------|
| `trading_decision_engine.py` | 매매 판단 핵심 엔진 | 퀀트 점수 기반 매수/매도 판단 |
| `candidate_selector.py` | 후보 종목 선정 | 기본 필터링 + 점수 기반 선정 |
| `trend_momentum_analyzer.py` | 추세/모멘텀 분석 | 추세 기반 청산 전략 |
| `dynamic_profit_loss.py` | 동적 익절/손절 | 익절/손절 비율 동적 계산 |

### 2.2 퀀트 시스템 (core/quant/)

| 파일 | 역할 | 설명 |
|------|------|------|
| `quant_screening_service.py` | 퀀트 스크리닝 | 일간 퀀트 포트폴리오 생성 |
| `quant_rebalancing_service.py` | 리밸런싱 | 09:05 시장가 리밸런싱 실행 |
| `target_profit_loss_calculator.py` | 목표가 계산 | 순위/점수 기반 익절/손절률 |

### 2.3 팩터 분석 (core/factors/)

| 파일 | 역할 |
|------|------|
| `value_factor.py` | PER, PBR, PSR 기반 가치 점수 |
| `momentum_factor.py` | 수익률, RSI 기반 모멘텀 점수 |
| `quality_factor.py` | ROE, ROA, 부채비율 기반 퀄리티 점수 |
| `growth_factor.py` | 매출/이익 성장률 기반 성장 점수 |

### 2.4 기술적 지표 (core/indicators/)

| 파일 | 역할 |
|------|------|
| `bollinger_bands.py` | 볼린저 밴드 계산 |
| `multi_bollinger_bands.py` | 멀티 볼린저 밴드 |
| `bisector_line.py` | 이등분선 지표 |
| `price_box.py` | 가격 박스 패턴 |
| `pullback_candle_pattern.py` | 눌림목 캔들 패턴 |
| `pullback/` | 눌림목 전략 하위 모듈 |

### 2.5 전략 설정

| 파일 | 역할 |
|------|------|
| `config/trading_config.json` | 거래 파라미터 |
| `config/trend_exit_config.json` | 청산 전략 파라미터 |
| `config/ml_settings.py` | ML 관련 설정 |

---

## 3. 공통 인프라로 분류되는 부분

### 3.1 API 레이어 (api/)

```
api/
├── kis_auth.py              # 인증/토큰 관리
├── kis_api_manager.py       # API 통합 Facade
├── kis_chart_api.py         # 차트 데이터 조회
├── kis_order_api.py         # 주문 실행
├── kis_account_api.py       # 계좌 조회
├── kis_market_api.py        # 시장 정보
└── kis_financial_api.py     # 재무제표
```

**특징:**
- KIS(한국투자증권) API 래퍼
- 재시도 로직, 속도 제한 처리 포함
- 전략과 독립적인 순수 인프라

### 3.2 데이터 관리 (db/)

```
db/
├── database_manager.py      # SQLite 관리자
└── cleanup_old_tables.py    # 테이블 정리
```

**특징:**
- SQLite 기반 데이터 저장
- 후보 종목, 가격 데이터, 거래 기록 관리
- 퀀트 포트폴리오 저장/조회

### 3.3 핵심 공통 모듈 (core/)

| 파일 | 역할 |
|------|------|
| `models.py` | 공통 데이터 모델 (Stock, Order, Position 등) |
| `data_collector.py` | 실시간 데이터 수집 |
| `order_manager.py` | 주문 상태 관리 및 실행 |
| `fund_manager.py` | 자금 배분 관리 |
| `intraday_stock_manager.py` | 장중 종목 관리 |
| `trading_stock_manager.py` | 종목 상태 통합 관리 |
| `virtual_trading_manager.py` | 가상매매 지원 |
| `telegram_integration.py` | 텔레그램 알림 |
| `timeframe_converter.py` | 타임프레임 변환 |

### 3.4 유틸리티 (utils/)

| 파일 | 역할 |
|------|------|
| `logger.py` | 로깅 설정 |
| `korean_time.py` | KST 시간 처리, 장 상태 확인 |
| `korean_holidays.py` | 한국 공휴일 관리 |
| `price_utils.py` | 호가 단위 처리 |
| `data_cache.py` | 데이터 캐싱 |
| `unified_data_loader.py` | 통합 데이터 로더 |

### 3.5 설정 (config/)

| 파일 | 역할 |
|------|------|
| `settings.py` | API 키 로더 |
| `constants.py` | 시스템 상수 |
| `market_hours.py` | 시장 시간 관리 |

---

## 4. 현재 의존성 문제점

### 4.1 main.py 과부하 문제

`main.py`의 `DayTradingBot` 클래스가 **1,042줄**로 과도하게 비대화됨:

```python
class DayTradingBot:
    def __init__(self):
        # 20개 이상의 모듈 직접 초기화
        self.api_manager = KISAPIManager()
        self.db_manager = DatabaseManager()
        self.telegram = TelegramIntegration()
        self.data_collector = RealTimeDataCollector()
        self.order_manager = OrderManager()
        self.intraday_manager = IntradayStockManager()
        self.trading_manager = TradingStockManager()
        self.decision_engine = TradingDecisionEngine()
        self.candidate_selector = CandidateSelector()
        self.fund_manager = FundManager()
        self.quant_screening_service = QuantScreeningService()
        self.ml_data_collector = MLDataCollector()
        self.ml_screening_service = MLScreeningService()
        self.rebalancing_service = QuantRebalancingService()
        # ... 6개 이상의 헬퍼 클래스
```

**문제점:**
- 단일 클래스에 모든 책임 집중
- 전략 변경 시 main.py 수정 필요
- 테스트 어려움

### 4.2 전략과 인프라의 강결합

```
TradingDecisionEngine
    ├── db_manager (인프라)
    ├── telegram (인프라)
    ├── trading_manager (인프라)
    ├── api_manager (인프라)
    ├── VirtualTradingManager (인프라)
    ├── TrendMomentumAnalyzer (전략) ★ 직접 import
    └── MLFactorCalculator (전략) ★ 직접 import
```

**문제점:**
- 전략 모듈이 인프라 모듈에 직접 의존
- 전략 교체 시 코드 수정 필요
- 인터페이스 없이 구체 클래스 직접 사용

### 4.3 순환 참조 위험

```python
# core/trading_stock_manager.py
class TradingStockManager:
    def set_decision_engine(self, decision_engine):
        """순환 참조 방지를 위해 별도 메서드"""
        self.decision_engine = decision_engine
```

- `TradingStockManager` <-> `TradingDecisionEngine` 상호 참조
- 별도 setter로 우회하고 있으나 근본적 해결 아님

### 4.4 strategies/ 디렉토리 미사용

```
strategies/
└── __init__.py  # 빈 파일
```

- 전략 디렉토리가 있으나 실제 전략은 `core/`에 분산
- 구조적 혼란 초래

### 4.5 전략별 설정 분산

- `config/trading_config.json`: 기본 거래 설정
- `config/trend_exit_config.json`: 청산 설정
- `core/quant/quant_rebalancing_service.py`: 하드코딩된 임계값
  ```python
  self.hard_stop_score = 70.0  # 하드코딩
  self.soft_stop_score = 72.0
  self.safe_score = 75.0
  ```

---

## 5. 템플릿화를 위한 권장사항

### 5.1 전략 인터페이스 정의

```python
# strategies/base_strategy.py
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, List
import pandas as pd

class BaseStrategy(ABC):
    """전략 기본 인터페이스"""

    @abstractmethod
    def get_name(self) -> str:
        """전략 이름"""
        pass

    @abstractmethod
    def analyze_buy_decision(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """매수 판단"""
        pass

    @abstractmethod
    def analyze_sell_decision(
        self,
        stock_code: str,
        position: Any,
        data: pd.DataFrame
    ) -> Tuple[bool, str]:
        """매도 판단"""
        pass

    @abstractmethod
    def screen_candidates(self, universe: List[str]) -> List[Dict[str, Any]]:
        """후보 종목 스크리닝"""
        pass

    @abstractmethod
    def calculate_position_size(
        self,
        stock_code: str,
        available_funds: float
    ) -> int:
        """포지션 크기 계산"""
        pass
```

### 5.2 프로젝트 구조 재편

```
trading_template/
├── main.py                      # 심플한 진입점
├── app/                         # 애플리케이션 코어
│   ├── trading_bot.py           # 메인 봇 클래스 (경량화)
│   ├── dependency_container.py  # 의존성 주입 컨테이너
│   └── task_manager.py          # 태스크 관리
│
├── infrastructure/              # 공통 인프라 (전략 독립)
│   ├── api/                     # 브로커 API
│   │   ├── base_broker.py       # 브로커 인터페이스
│   │   └── kis/                 # KIS 구현체
│   ├── db/                      # 데이터베이스
│   ├── messaging/               # 알림 (텔레그램 등)
│   └── utils/                   # 유틸리티
│
├── domain/                      # 도메인 모델
│   ├── models.py                # 핵심 모델
│   ├── events.py                # 이벤트 정의
│   └── enums.py                 # Enum 정의
│
├── strategies/                  # 전략 모듈
│   ├── base_strategy.py         # 전략 인터페이스
│   ├── quant/                   # 퀀트 전략 구현
│   │   ├── quant_strategy.py
│   │   ├── screening.py
│   │   ├── rebalancing.py
│   │   └── factors/
│   └── pullback/                # 눌림목 전략 구현
│       ├── pullback_strategy.py
│       └── indicators/
│
├── services/                    # 비즈니스 서비스
│   ├── order_service.py
│   ├── data_service.py
│   └── fund_service.py
│
├── config/                      # 설정
│   ├── base_config.py           # 공통 설정
│   ├── strategy_config/         # 전략별 설정
│   │   ├── quant_config.yaml
│   │   └── pullback_config.yaml
│   └── secrets/                 # 비밀 키
│
└── scripts/                     # 유틸리티 스크립트
```

### 5.3 의존성 주입 패턴 적용

```python
# app/dependency_container.py
class DependencyContainer:
    """의존성 주입 컨테이너"""

    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self._instances = {}

    def get_broker(self) -> BaseBroker:
        if 'broker' not in self._instances:
            # 설정에 따라 적절한 브로커 생성
            broker_type = self.config.get('broker_type', 'kis')
            if broker_type == 'kis':
                from infrastructure.api.kis import KISBroker
                self._instances['broker'] = KISBroker(self.config)
        return self._instances['broker']

    def get_strategy(self) -> BaseStrategy:
        if 'strategy' not in self._instances:
            strategy_type = self.config.get('strategy_type', 'quant')
            if strategy_type == 'quant':
                from strategies.quant import QuantStrategy
                self._instances['strategy'] = QuantStrategy(
                    broker=self.get_broker(),
                    db_manager=self.get_db_manager(),
                    config=self.config.get('strategy_config')
                )
        return self._instances['strategy']
```

### 5.4 전략별 설정 분리

```yaml
# config/strategy_config/quant_config.yaml
strategy:
  name: "QuantMultiFactor"
  version: "1.0.0"

portfolio:
  size: 15
  equal_weight: true

screening:
  min_market_cap: 100000000000  # 1000억
  min_trading_value: 1000000000  # 10억
  min_price: 1000
  max_price: 500000

rebalancing:
  period: "daily"  # daily, weekly, monthly
  execution_time: "09:05"

exit_rules:
  hard_stop_score: 70.0
  soft_stop_score: 72.0
  safe_score: 75.0

factors:
  value:
    weight: 0.25
    metrics: ["per", "pbr", "psr"]
  momentum:
    weight: 0.25
    metrics: ["return_1m", "return_3m", "rsi"]
  quality:
    weight: 0.25
    metrics: ["roe", "roa", "debt_ratio"]
  growth:
    weight: 0.25
    metrics: ["revenue_growth", "profit_growth"]
```

### 5.5 이벤트 기반 아키텍처

```python
# domain/events.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TradingEvent:
    """거래 이벤트 기본 클래스"""
    timestamp: datetime
    source: str

@dataclass
class BuySignalEvent(TradingEvent):
    stock_code: str
    price: float
    quantity: int
    reason: str

@dataclass
class SellSignalEvent(TradingEvent):
    stock_code: str
    price: float
    quantity: int
    reason: str

# app/event_bus.py
class EventBus:
    def __init__(self):
        self._handlers = {}

    def subscribe(self, event_type, handler):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event):
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            await handler(event)
```

### 5.6 템플릿 체크리스트

새 전략 추가 시 필요한 작업:

1. **전략 클래스 생성**
   - [ ] `strategies/{strategy_name}/` 디렉토리 생성
   - [ ] `BaseStrategy` 인터페이스 구현
   - [ ] 전략별 지표/팩터 구현

2. **설정 파일 추가**
   - [ ] `config/strategy_config/{strategy_name}_config.yaml` 생성
   - [ ] 필요한 파라미터 정의

3. **등록**
   - [ ] `DependencyContainer`에 전략 등록
   - [ ] 설정 파일에서 `strategy_type` 지정

4. **테스트**
   - [ ] 단위 테스트 작성
   - [ ] 백테스트 수행

---

## 6. 마이그레이션 우선순위

### Phase 1: 인터페이스 정의 (1주)
1. `BaseStrategy` 인터페이스 정의
2. `BaseBroker` 인터페이스 정의
3. 기존 코드에 인터페이스 적용

### Phase 2: 인프라 분리 (1주)
1. `api/` -> `infrastructure/api/kis/` 이동
2. `db/` -> `infrastructure/db/` 이동
3. `utils/` -> `infrastructure/utils/` 이동

### Phase 3: 전략 분리 (2주)
1. 현재 퀀트 전략을 `strategies/quant/`로 이동
2. 기존 `core/indicators/pullback/`을 `strategies/pullback/`으로 이동
3. 설정 파일 분리

### Phase 4: 의존성 주입 적용 (1주)
1. `DependencyContainer` 구현
2. `main.py` 경량화
3. 순환 참조 제거

---

## 7. 결론

### 현재 상태
- 기능적으로 동작하는 퀀트 트레이딩 시스템
- 전략과 인프라가 강하게 결합되어 있음
- main.py가 God Object 안티패턴

### 템플릿화 가치
- 새로운 전략 추가가 용이해짐
- 다른 브로커 API 지원 가능
- 테스트 용이성 향상
- 코드 재사용성 증가

### 예상 작업량
- 전체 리팩토링: 약 4-5주
- 점진적 마이그레이션 권장
- 기존 기능 유지하면서 단계적 개선

---

*이 문서는 2026-02-03에 작성되었습니다.*
