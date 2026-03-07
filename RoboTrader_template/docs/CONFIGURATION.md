# 설정 가이드

> KIS Trading Template의 설정 파일과 환경 변수 안내

---

## 설정 파일 구조

```
config/
├── key.ini              — KIS API 인증 정보 (비공개, .gitignore)
├── key.ini.example      — key.ini 예제
├── trading_config.json  — 거래 파라미터 (포트폴리오, 리스크 등)
├── settings.py          — 설정 로더 모듈
├── constants.py         — 시스템 상수
├── market_hours.py      — 시장별 거래시간
└── visualization_strategies.yaml — 차트 시각화 전략 설정
```

---

## 1. KIS API 인증 (`config/key.ini`)

```ini
[KIS]
KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
KIS_APP_KEY = "발급받은_APP_KEY"
KIS_APP_SECRET = "발급받은_APP_SECRET"
KIS_ACCOUNT_NO = "계좌번호-상품코드"
KIS_HTS_ID = "HTS_ID"
```

**발급 방법:**
1. [한국투자증권 Open API](https://apiportal.koreainvestment.com/) 가입
2. APP_KEY, APP_SECRET 발급
3. `key.ini.example`을 `key.ini`로 복사 후 입력

> ⚠️ `key.ini`는 `.gitignore`에 포함되어야 합니다 (절대 커밋 금지)

---

## 2. 데이터베이스 (PostgreSQL + TimescaleDB)

**PostgreSQL 16 + TimescaleDB 2.24.0** (Windows 로컬 직접 설치, Docker 아님):

```
# 접속 정보
Host: localhost
Port: 5433          ← 기본 5432가 아님!
Database: robotrader
User: robotrader
Password: 1234
서비스명: postgresql-x64-16 (Windows 서비스, 자동 시작)
```

`.env` 파일 (또는 `.env.example` 참고):
```
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5433
TIMESCALE_DB=robotrader
TIMESCALE_USER=robotrader
TIMESCALE_PASSWORD=1234
```

DB 초기화 스크립트: `init-scripts/01-init.sql` 수동 적용. 상세 스키마는 `docs/DATABASE.md` 참고

---

## 3. 거래 설정 (`config/trading_config.json`)

`TradingConfig` 데이터 모델로 로드됩니다. 주요 설정:

| 설정 | 설명 | 기본값 |
|------|------|--------|
| `paper_trading` | 가상매매 모드 | `true` |
| `portfolio_size` | 포트폴리오 종목 수 | 15 |
| `strategy.name` | 사용할 전략 이름 | `"sample"` |
| `strategy.enabled` | 전략 시스템 활성화 | `true` |

---

## 4. 시스템 상수 (`config/constants.py`)

코드에서 직접 변경하는 상수들:

### 포트폴리오/스크리닝
| 상수 | 값 | 설명 |
|------|---|------|
| `PORTFOLIO_SIZE` | 15 | 포트폴리오 종목 수 |
| `QUANT_CANDIDATE_LIMIT` | 50 | 퀀트 후보 종목 최대 수 |

### API Rate Limiting
| 상수 | 값 | 설명 |
|------|---|------|
| `API_CALL_INTERVAL` | 0.06초 | 기본 API 호출 간격 (초당 ~17회) |
| `API_MAX_RETRIES` | 3 | API 재시도 횟수 |

### 주문 관련
| 상수 | 값 | 설명 |
|------|---|------|
| `ORDER_MONITOR_INTERVAL` | 3초 | 체결 확인 주기 |
| `SELL_ORDER_WAIT_TIMEOUT` | 300초 | 매도 체결 대기 최대 시간 |

### 손절/익절 기본값
| 상수 | 값 | 설명 |
|------|---|------|
| `DEFAULT_TARGET_PROFIT_RATE` | 0.15 | 기본 익절률 15% |
| `DEFAULT_STOP_LOSS_RATE` | 0.10 | 기본 손절률 10% |

---

## 5. 시장 거래시간 (`config/market_hours.py`)

`MarketHours` 클래스로 시장별 거래시간 관리:

- **기본**: 09:00~15:30 (KRX)
- **매수 마감**: 12:00
- **EOD 일괄청산**: 15:00
- **특수일**: 수능일 등 1시간 지연 (special_days에 등록)

해외 시장(NYSE 등) 확장 구조 준비되어 있음

---

## 6. 전략 설정 (`strategies/<name>/config.yaml`)

각 전략별 YAML 설정 파일:

```yaml
# strategies/sample/config.yaml 예시
strategy:
  name: SampleStrategy
  description: "이동평균 크로스 + RSI 전략"

parameters:
  ma_short_period: 5
  ma_long_period: 20
  rsi_period: 14
  rsi_oversold: 30
  rsi_overbought: 70
  volume_multiplier: 1.5
  min_buy_signals: 2

risk_management:
  stop_loss_pct: 0.05
  take_profit_pct: 0.10
  max_position_size: 0.10
  max_daily_trades: 5
```

`StrategyConfig` 클래스로 로드:
```python
config = StrategyConfig('sample')
config.load()
value = config.get('risk_management.stop_loss_pct', 0.05)
```

---

## 설정 우선순위

1. 전략 `config.yaml` (전략별 파라미터)
2. `trading_config.json` (전역 거래 설정)
3. `constants.py` (시스템 상수, 하드코딩)
4. `key.ini` / `.env` (인증/환경)
