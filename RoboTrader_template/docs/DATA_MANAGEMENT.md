# 📦 데이터 관리 가이드

> kis-template 시스템의 데이터 저장, 복원, 활용 방법을 설명합니다.

---

## 📋 목차

1. [DB 저장 동작](#1-db-저장-동작)
2. [프로그램 재시작 시 포지션 복원](#2-프로그램-재시작-시-포지션-복원)
3. [OHLCV 및 재무데이터 활용](#3-ohlcv-및-재무데이터-활용)

---

## 1. DB 저장 동작

### 1.1 일봉 가격 데이터 (daily_prices)

#### 📊 daily_prices 테이블

**저장 시각**: 08:30 (ML 데이터 수집 시 - 전일 데이터)

**저장 대상**:
- 퀀트 포트폴리오 상위 30개 종목 (퀀트 전략 사용 시)
- 현재 보유 중인 종목 (포트폴리오 외 종목도 포함)

**저장 내용**:
```sql
daily_prices 테이블:
- stock_code: 종목코드
- date: 날짜 (YYYY-MM-DD)
- open, high, low, close: OHLC 가격
- volume: 거래량
- trading_value: 거래대금
- market_cap: 시가총액 (현재 시총 기준 역산)
- returns_1d: 1일 수익률 (%)
- returns_5d: 5일 수익률 (%)
- returns_20d: 20일 수익률 (%)
- volatility_20d: 20일 변동성 (%)
```

**데이터 수집 범위**:
- 기본적으로 **전 영업일까지**만 수집 (`core/ml_data_collector.py`)
- 이유: 리밸런싱(09:05)은 전날 확정 데이터로 판단
- 당일 데이터는 다음날 아침에 "전 영업일"로 수집됨

**예시**:
```
12/26(목) 08:30 실행 → 12/25(수) 데이터까지 수집
12/27(금) 08:30 실행 → 12/26(목) 데이터 수집 (어제 종가)
12/30(월) 08:30 실행 → 12/27(금) 데이터 수집 (주말 건너뛰기)
```

**코드 위치**: `core/data_collector.py`

---

### 1.2 재무제표 데이터 (financial_statements)

#### 💼 financial_statements 테이블

**저장 시각**: 08:30 (ML 데이터 수집 시 - 전일 데이터)

**저장 대상**: 일봉 수집 대상과 동일 (퀀트 포트폴리오 + 보유 종목)

**저장 내용**:
```sql
financial_statements 테이블:
- stock_code: 종목코드
- report_date: 재무제표 기준일 (YYYY-MM-DD)

[밸류에이션 지표]
- per: PER (주가수익비율)
- pbr: PBR (주가순자산비율)
- psr: PSR (주가매출액비율)
- dividend_yield: 배당수익률 (%)

[수익성 지표]
- roe: ROE (자기자본이익률, %)
- operating_margin: 영업이익률 (%)
- net_margin: 순이익률 (%)

[재무건전성 지표]
- debt_ratio: 부채비율 (%)
- current_assets: 유동자산
- current_liabilities: 유동부채
- total_equity: 자기자본

[손익 지표]
- revenue: 매출액
- operating_profit: 영업이익
- net_income: 순이익
- total_assets: 총자산
```

**API 호출**:
1. `get_financial_ratio()`: 재무비율 (PER, PBR, ROE, 부채비율 등)
2. `get_income_statement()`: 손익계산서 (매출, 영업이익, 순이익 등)
3. `get_balance_sheet()`: 대차대조표 (자산, 부채, 자본 등)

**PER/PBR 계산 로직** (`core/data_collector.py`):
```python
# API에서 직접 제공하지 않는 경우 자체 계산
if not per and ratio.eps > 0:
    current_price = get_stock_market_cap(stock_code)['current_price']
    per = current_price / ratio.eps  # PER = 주가 / EPS

if not pbr and ratio.bps > 0:
    current_price = get_stock_market_cap(stock_code)['current_price']
    pbr = current_price / ratio.bps  # PBR = 주가 / BPS
```

**저장 전략** (원자성 보장):
```python
# 1) 레코드 생성 (없을 경우만)
INSERT OR IGNORE INTO financial_statements (stock_code, report_date, ...)

# 2) NULL이 아닌 값만 업데이트 (기존 데이터 보존)
UPDATE financial_statements
SET per = ?, pbr = ?, roe = ?, ...
WHERE stock_code = ? AND report_date = ?
```

**코드 위치**: `core/data_collector.py`

---

### 1.3 매매 기록 (virtual_trading_records / real_trading_records)

#### 📝 매매 기록 테이블

**저장 시각**: 매수/매도 주문 체결 시 즉시

**저장 내용**:
```sql
virtual_trading_records / real_trading_records 테이블:
- action: 'BUY' 또는 'SELL'
- stock_code, stock_name: 종목 정보
- quantity: 수량
- price: 체결가
- timestamp: 체결 시각

[매수 시 추가 정보]
- target_profit_rate: 목표 익절률 (0.15 = 15%)
- stop_loss_rate: 목표 손절률 (0.10 = 10%)
- strategy: 전략명
- reason: 선정 이유

[매도 시 추가 정보]
- buy_record_id: 매수 기록 ID (참조)
- profit_loss: 손익금 (원)
- profit_rate: 수익률 (%)
```

**저장 예시**:
```python
# 매수 시 (09:05 리밸런싱)
db_manager.save_virtual_buy(
    stock_code="005930",
    stock_name="삼성전자",
    quantity=100,
    price=70000,
    target_profit_rate=0.20,  # S등급 20%
    stop_loss_rate=0.08,      # S등급 8%
    strategy="Quant Rebalancing",
    reason="S등급 (복합점수 75점)"
)

# 매도 시 (익절 도달)
db_manager.save_virtual_sell(
    buy_record_id=1234,
    stock_code="005930",
    stock_name="삼성전자",
    quantity=100,
    price=84000,
    profit_loss=1400000,  # +140만원
    profit_rate=0.20,     # +20%
    strategy="Stop Profit",
    reason="목표 익절 도달 (20%)"
)
```

**코드 위치**: `db/database_manager.py`

---

### 1.4 퀀트 포트폴리오 및 팩터 점수

> ⚠️ 이 섹션은 **퀀트 전략 구현 시 참고 문서**입니다. 기본 템플릿에는 퀀트 모듈이 포함되어 있지 않습니다.

> 퀀트 전략 사용 시 적용됩니다.

#### 🎯 quant_portfolio / quant_factor_scores 테이블

**저장 시각**: 08:55 (퀀트 스크리닝 시)

**저장 테이블**:
1. `quant_portfolio`: 포트폴리오 구성
2. `quant_factor_scores`: 팩터 점수 상세

```sql
quant_portfolio 테이블:
- calc_date: 계산일 (YYYYMMDD)
- stock_code, stock_name: 종목 정보
- rank: 순위 (1~30)
- total_score: 종합 점수 (0~100)
- selection_reason: 선정 이유

quant_factor_scores 테이블:
- calc_date: 계산일
- stock_code: 종목코드
- value_score: Value 팩터 점수 (0~100)
- momentum_score: Momentum 팩터 점수 (0~100)
- quality_score: Quality 팩터 점수 (0~100)
- growth_score: Growth 팩터 점수 (0~100)
- total_score: 종합 점수 (0~100)
- factor_rank: 팩터 순위
```

**코드 위치**: 퀀트 전략 구현 시 별도 모듈 작성 필요

---

## 2. 프로그램 재시작 시 포지션 복원

프로그램이 재시작되면 DB에서 자동으로 보유 종목과 익절/손절률을 복원하여 모니터링을 재개합니다.

### 🔄 복원 프로세스

**실행 시각**: 프로그램 시작 시 (`main.py`)

**복원 단계**:

```
프로그램 시작
    ↓
┌──────────────────────────────────────┐
│ 1. 오늘 후보 종목 복원                │
│  - candidate_stocks 테이블 조회       │
│  - 오늘 날짜(DATE) 기준               │
│  - TradingStockManager에 추가         │
└──────────────────────────────────────┘
    ↓
┌──────────────────────────────────────┐
│ 2. 보유 포지션 복원 ⭐                │
│  - virtual_trading_records 조회      │
│  - 미체결 포지션만 (BUY만 있고 SELL 없음)│
└──────────────────────────────────────┘
    ↓
┌──────────────────────────────────────┐
│ 3. 포지션 정보 메모리 복원            │
│  - 수량, 매수가 설정                  │
│  - 목표 익절률, 손절률 설정           │
│  - 상태를 POSITIONED로 변경           │
└──────────────────────────────────────┘
    ↓
매도 모니터링 시작 (1분마다 체크)
```

### 📊 복원 쿼리

**미체결 포지션 조회** (`db/database_manager.py`):

```sql
SELECT
    b.id,
    b.stock_code,
    b.stock_name,
    b.quantity,
    b.price as buy_price,
    b.timestamp as buy_time,
    b.strategy,
    b.reason as buy_reason,
    b.target_profit_rate,  -- ⭐ 복원 핵심
    b.stop_loss_rate       -- ⭐ 복원 핵심
FROM virtual_trading_records b
WHERE b.action = 'BUY'
    AND b.is_test = 1
    AND NOT EXISTS (
        SELECT 1 FROM virtual_trading_records s
        WHERE s.buy_record_id = b.id AND s.action = 'SELL'
    )
ORDER BY b.timestamp DESC
```

### 🔧 복원 코드

**복원 로직** (`core/helpers/state_restoration_helper.py`):

```python
for _, holding in holdings.iterrows():
    stock_code = holding['stock_code']
    quantity = int(holding['quantity'])
    buy_price = float(holding['buy_price'])

    # ⭐ DB에서 익절/손절률 복원
    target_profit_rate = holding.get('target_profit_rate', 0.15)
    stop_loss_rate = holding.get('stop_loss_rate', 0.10)

    # TradingStock 추가
    trading_stock = await trading_manager.add_selected_stock(...)

    # ⭐ 포지션 정보 메모리 복원
    trading_stock.set_position(quantity, buy_price)
    trading_stock.target_profit_rate = target_profit_rate
    trading_stock.stop_loss_rate = stop_loss_rate

    # ⭐ 상태 변경: POSITIONED → 매도 모니터링 활성화
    trading_manager._change_stock_state(
        stock_code,
        StockState.POSITIONED,
        f"DB 복원: {quantity}주 @{buy_price:,.0f}원 "
        f"(익절:{target_profit_rate*100:.1f}% 손절:{stop_loss_rate*100:.1f}%)"
    )
```

**복원 결과 예시**:
```
✅ 보유 종목 3/3개 복원 완료
📊 005930 포지션 복원: 100주 @70,000원, 익절가 84,000원, 손절가 64,400원
📊 035720 포지션 복원: 80주 @50,000원, 익절가 59,000원, 손절가 45,500원
📊 035420 포지션 복원: 120주 @200,000원, 익절가 236,000원, 손절가 182,000원
```

**핵심**: 프로그램이 종료되어도 아침에 설정한 동적 목표값이 DB에 저장되어 있어, 재시작 시에도 동일한 익절/손절률로 모니터링 재개 가능!

---

## 3. OHLCV 및 재무데이터 활용

### 📈 OHLCV 데이터 활용

**수집 데이터**:
- **O** (Open): 시가
- **H** (High): 고가
- **L** (Low): 저가
- **C** (Close): 종가
- **V** (Volume): 거래량
- **추가**: 거래대금, 시가총액, 수익률, 변동성

**활용 목적**:

1. **퀀트 스크리닝** (08:55, 퀀트 전략 사용 시):
   - Momentum 팩터: 1일/5일/20일 수익률 계산
   - Size 팩터: 시가총액 기준 필터링 (1,000억 이상)
   - 변동성: 리스크 평가

2. **전략 시그널 생성**:
   - 과거 OHLCV 패턴 분석
   - 기술적 지표 계산
   - 매수/매도 시그널 판단

3. **백테스팅**:
   - 과거 전략 성과 검증
   - 리스크 분석
   - 최적 파라미터 탐색

**코드 위치**: `core/data_collector.py`

---

### 💰 재무데이터 활용

**수집 데이터 및 활용**:

| 지표 | API 필드 | 퀀트 팩터 | 용도 |
|------|---------|----------|------|
| **PER** | `per` or 계산 | Value | 저평가 종목 발굴 (낮을수록 좋음) |
| **PBR** | `pbr` or 계산 | Value | 저평가 종목 발굴 (낮을수록 좋음) |
| **PSR** | `psr` | Value | 매출 대비 주가 평가 |
| **ROE** | `roe_value` | Quality | 수익성 평가 (높을수록 좋음) |
| **부채비율** | `liability_ratio` | Quality | 재무건전성 (낮을수록 좋음) |
| **영업이익률** | `operating_margin` | Quality | 수익성 평가 |
| **매출액** | `revenue` | Growth | 성장성 평가 (증가율) |
| **영업이익** | `operating_profit` | Growth | 수익성 개선 추세 |
| **순이익** | `net_income` | Growth | 순이익 증가율 |

**퀀트 팩터 점수 계산 예시** (퀀트 전략 사용 시):

```python
# Value Score 계산
value_score = 0
if per and per > 0:
    # PER이 낮을수록 높은 점수 (상위 25% → 100점)
    value_score += score_per(per)

if pbr and pbr > 0:
    # PBR이 낮을수록 높은 점수
    value_score += score_pbr(pbr)

value_score = value_score / 2  # 평균

# Quality Score 계산
quality_score = 0
if roe and roe > 0:
    # ROE가 높을수록 높은 점수 (상위 25% → 100점)
    quality_score += score_roe(roe)

if debt_ratio:
    # 부채비율이 낮을수록 높은 점수
    quality_score += score_debt_ratio(debt_ratio)

quality_score = quality_score / 2  # 평균

# Momentum Score 계산 (OHLCV 사용)
momentum_score = 0
if returns_20d:
    # 20일 수익률이 높을수록 높은 점수
    momentum_score = score_momentum(returns_20d)
```

**종합 점수**:
```python
total_score = (
    value_score * 0.25 +
    quality_score * 0.25 +
    momentum_score * 0.30 +
    growth_score * 0.20
)
```

**코드 위치**: 퀀트 전략 구현 시 별도 모듈 작성 필요

---

**마지막 업데이트**: 2026-03-22
