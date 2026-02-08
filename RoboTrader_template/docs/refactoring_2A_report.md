# 2A단계 리팩토링 보고서 (개발자 C)

## 변경 요약

### main.py 수정 사항

#### 1. Import 변경 (라인 31-32)

**변경 전:**
```python
from api.kis_api_manager import KISAPIManager
```

**변경 후:**
```python
from framework import KISBroker
from api.kis_api_manager import KISAPIManager  # 하위 호환용 (3단계에서 제거 예정)
```

#### 2. 핵심 모듈 초기화 변경 (라인 87-92)

**변경 전:**
```python
self.api_manager = KISAPIManager()
```

**변경 후:**
```python
self.broker = KISBroker()
self.api_manager = KISAPIManager()  # 하위 호환용
self.broker._api_manager = self.api_manager  # broker와 api_manager 연결
```

#### 3. 전략 초기화에서 broker 사용 (라인 236)
```python
broker=self.broker,  # (이전: broker=self.api_manager)
```

### 하위 호환성 유지 방법

- `self.api_manager`는 KISAPIManager 인스턴스로 유지 → core/, bot/ 모듈에서 기존처럼 사용 가능
- `self.broker._api_manager = self.api_manager`로 연결하여 KISBroker가 동일 KISAPIManager 인스턴스 사용
- 하위 모듈에 전달되는 `api_manager` 객체는 변경 없음

---

## 3단계 분석: core/ 및 bot/ 전환 대상 파일

### core/ 파일

| 파일 | api_manager 사용 | 사용 메서드 |
|------|-----------------|-------------|
| `core/data_collector.py` | `from api.kis_api_manager import KISAPIManager`으로 타입 힌트, `self.api_manager` 저장 | `get_current_price()`, `get_ohlcv_data()` |
| `core/intraday_stock_manager.py` | `self.api_manager` 저장 (duck typing) | 타입 힌트 없음, 유연 |
| `core/order_manager.py` | `from api.kis_api_manager import KISAPIManager` 타입 힌트, `super().__init__`에 전달 | OrderBase에 위임 |
| `core/orders/order_base.py` | `self.api_manager` 저장 | 직접 사용 안함 (서브클래스에서 사용) |
| `core/orders/order_executor.py` | `self.api_manager` 사용 | `place_buy_order()`, `place_sell_order()`, `cancel_order()`, `get_current_price()` |
| `core/orders/order_monitor.py` | `self.api_manager` 사용 | `get_order_status()` |
| `core/trading_decision_engine.py` | `self.api_manager` 저장 및 사용 | `get_account_balance()`, virtual_trading_manager에 전달 |
| `core/virtual_trading_manager.py` | `self.api_manager` 저장 및 사용 | `get_account_balance()` |

### bot/ 파일

| 파일 | api_manager 사용 | 사용 메서드 |
|------|-----------------|-------------|
| `bot/position_sync.py` | `self.bot.api_manager` 접근 | `get_account_balance()` |
| `bot/system_monitor.py` | `self.bot.api_manager` 접근 | `get_api_statistics()`, `initialize()` |

### 3단계 전환 전략 제안

1. KISBroker에 `initialize()`, `shutdown()`, `get_api_statistics()`, `get_account_balance_quick()` 메서드 추가
2. core/ 모듈의 타입 힌트를 `KISAPIManager` → `KISBroker` (또는 Protocol)로 변경
3. `intraday_stock_manager.py`는 duck typing이라 변경 최소
4. `order_executor.py`와 `order_monitor.py`는 OrderResult import도 전환 필요
