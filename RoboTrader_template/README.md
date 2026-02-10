# 🤖 KIS Trading Template

> 한국투자증권 API 기반 **자동매매 프레임워크 템플릿**
>
> 전략만 갈아끼우면 새로운 자동매매 봇이 탄생합니다.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Private-red.svg)]()

---

## 💡 이게 뭔가요?

주식 자동매매 프로그램을 만들 때마다 API 연동, DB 설정, 주문 처리, 텔레그램 알림 등을 **매번 새로 짜는 건 비효율적**입니다.

이 템플릿은 **공통 인프라**를 제공하고, 개발자는 **전략 로직에만 집중**할 수 있게 해줍니다.

```
kis-trading-template/          ← 공통 프레임워크
├── RoboTrader (전략 A)        ← 전략만 다름
├── RoboTrader_orb (전략 B)    ← 전략만 다름
└── RoboTrader_quant (전략 C)  ← 전략만 다름
```

---

## 📋 빠른 시작

```bash
# 1. 클론 및 설치
git clone <repository_url>
cd RoboTrader_template
pip install -r requirements.txt

# 2. API 설정
cp config/key.ini.example config/key.ini
# config/key.ini 편집 (APP_KEY, APP_SECRET, 계좌번호 입력)

# 3. 전략 작성
cp -r strategies/sample strategies/my_strategy
# strategies/my_strategy/strategy.py 수정

# 4. 실행
python main.py
```

---

## 🏗️ 아키텍처

### 프레임워크 구조

```
RoboTrader_template/
│
├── framework/              # 🔧 추상화 레이어
│   ├── broker.py          #   증권사 API 추상화 (계좌, 포지션, 자금)
│   ├── data.py            #   데이터 제공자 추상화
│   ├── executor.py        #   주문 실행 추상화
│   └── utils.py           #   공통 유틸리티
│
├── api/                    # 📡 KIS API 래퍼
│   ├── kis_auth.py        #   인증 + Rate Limiting
│   ├── kis_order_api.py   #   주문 API
│   ├── kis_chart_api.py   #   차트/시세 API
│   ├── kis_account_api.py #   계좌 API
│   ├── kis_market_api.py  #   시장 정보 API
│   └── kis_financial_api.py #  재무 데이터 API
│
├── strategies/             # 🎯 전략 모듈
│   ├── base.py            #   BaseStrategy 추상 클래스
│   ├── config.py          #   전략 설정 관리
│   └── sample/            #   예제 전략
│       ├── strategy.py
│       └── config.yaml
│
├── core/                   # ⚙️ 공통 핵심 모듈
│   ├── models.py          #   데이터 모델
│   ├── order_manager.py   #   주문 관리
│   ├── fund_manager.py    #   자금 관리 (가상/실전)
│   ├── data_collector.py  #   데이터 수집
│   ├── price_calculator.py #  가격 계산
│   ├── virtual_trading_manager.py  # 가상매매
│   └── telegram_integration.py     # 텔레그램 알림
│
├── config/                 # ⚙️ 설정
│   ├── settings.py        #   환경 설정
│   ├── constants.py       #   상수 정의
│   └── market_hours.py    #   시장 시간 관리
│
├── db/                     # 💾 데이터베이스
│   ├── connection.py      #   DB 연결
│   └── database_manager.py #  DB 인터페이스
│
├── utils/                  # 🛠️ 유틸리티
│   ├── korean_time.py     #   한국 시간 처리
│   ├── korean_holidays.py #   공휴일 캘린더
│   ├── logger.py          #   로깅
│   └── async_helpers.py   #   비동기 헬퍼
│
├── tests/                  # 🧪 테스트
├── visualization/          # 📊 차트 시각화
├── main.py                 # 🚀 진입점
└── .env.example            # 환경변수 예제
```

### 전략 개발 흐름

```
BaseStrategy 상속 → generate_signal() 구현 → 끝!

┌─────────────────────────────────────────────┐
│  Your Strategy (전략만 작성)                  │
│  ├── generate_signal() → BUY / SELL / HOLD  │
│  ├── on_market_open()                        │
│  └── on_market_close()                       │
├─────────────────────────────────────────────┤
│  Framework (프레임워크가 알아서 처리)          │
│  ├── API 인증 & Rate Limiting               │
│  ├── 주문 실행 & 체결 확인                    │
│  ├── 포지션 관리 & DB 저장                    │
│  ├── 텔레그램 알림                            │
│  └── 에러 핸들링 & 재시도                     │
└─────────────────────────────────────────────┘
```

---

## 🎯 전략 만들기

### 1. BaseStrategy 상속

```python
from strategies.base import BaseStrategy, Signal, SignalType

class MyStrategy(BaseStrategy):
    name = "MyStrategy"
    version = "1.0.0"
    description = "나만의 매매 전략"
    author = "taegeon"

    def on_init(self, broker, data_provider, executor):
        self._broker = broker
        self._data = data_provider
        self._executor = executor
        self._is_initialized = True
        return True

    def generate_signal(self, stock_code, data):
        """핵심! 여기에 매매 로직을 작성합니다."""
        
        # 예: 단순 이동평균 크로스
        ma5 = data['close'].rolling(5).mean().iloc[-1]
        ma20 = data['close'].rolling(20).mean().iloc[-1]
        
        if ma5 > ma20:
            return Signal(
                signal_type=SignalType.BUY,
                stock_code=stock_code,
                confidence=75,
                reasons=["5일선이 20일선 상향 돌파"]
            )
        elif ma5 < ma20:
            return Signal(
                signal_type=SignalType.SELL,
                stock_code=stock_code,
                confidence=70,
                reasons=["5일선이 20일선 하향 돌파"]
            )
        
        return None  # HOLD
```

### 2. 전략 설정 (config.yaml)

```yaml
strategy:
  name: MyStrategy
  portfolio_size: 15
  check_interval_sec: 60

risk:
  max_loss_per_day: -0.03      # 일일 최대 손실 3%
  stop_loss_rate: 0.08          # 종목당 손절 8%
  target_profit_rate: 0.15      # 종목당 익절 15%

screening:
  min_market_cap: 100000000000  # 시가총액 1,000억 이상
  min_volume: 100000            # 최소 거래량
```

### 3. 실행

```bash
python main.py --strategy my_strategy
```

---

## 🔧 주요 기능

| 기능 | 설명 |
|------|------|
| **KIS API 래퍼** | 인증, Rate Limiting, 재시도 자동 처리 |
| **가상매매** | 실제 주문 없이 DB에서 시뮬레이션 |
| **포지션 복원** | 프로그램 재시작 시 DB에서 자동 복원 |
| **텔레그램 알림** | 매수/매도/에러 실시간 알림 |
| **데이터 수집** | 일봉, 재무제표 자동 수집 및 저장 |
| **시장 시간 관리** | 장 시작/종료, 공휴일 자동 판단 |
| **로깅** | 일별 로그 파일 자동 생성 |

---

## 🛡️ 안전 운영 가이드

### 1단계: 가상매매로 검증

```json
// config/trading_config.json
"paper_trading": true  // 최소 1개월 테스트
```

### 2단계: 소액 실전

```json
// config/trading_config.json
"paper_trading": false  // 소액(100만원)부터 시작
```

### 3단계: 점진적 증액

검증된 후 자금을 늘려가세요.

---

## ⚠️ 주의사항

- 이 소프트웨어는 **교육 및 연구 목적**입니다
- 실제 투자 시 **모든 손실은 사용자 책임**입니다
- 과거 성과 ≠ 미래 수익 보장
- 반드시 **충분한 테스트 후** 실제 운영하세요

---

## 📚 관련 문서

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — 시스템 아키텍처, 모듈 관계도
- **[docs/TRADING_FLOW.md](docs/TRADING_FLOW.md)** — 매매 흐름 (초기화→루프→청산)
- **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** — 설정 가이드
- **[SYSTEM_FLOW.md](SYSTEM_FLOW.md)** — 시스템 동작 흐름 상세
- **[CLAUDE.md](CLAUDE.md)** — AI 개발 협업 가이드

---

**마지막 업데이트**: 2026-02-10
