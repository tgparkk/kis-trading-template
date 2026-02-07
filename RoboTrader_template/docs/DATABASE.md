# RoboTrader 데이터베이스 가이드

## 1. 개요

| 항목 | 값 |
|---|---|
| 엔진 | PostgreSQL 16 + TimescaleDB 2.24.0 |
| 설치 방식 | Windows 로컬 직접 설치 (Docker 아님) |
| 서비스명 | postgresql-x64-16 (Windows 서비스, 자동 시작) |
| Host | localhost |
| Port | **5433** |
| Database | robotrader |
| User | robotrader |
| Password | 1234 |

### 연결 코드

```python
from db.connection import DatabaseConnection

# 자동 초기화 (첫 호출 시)
with DatabaseConnection.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM daily_prices LIMIT 10")
    rows = cursor.fetchall()
```

### 환경변수 오버라이드

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| TIMESCALE_HOST | localhost | DB 호스트 |
| TIMESCALE_PORT | 5433 | DB 포트 |
| TIMESCALE_DB | robotrader | 데이터베이스명 |
| TIMESCALE_USER | robotrader | 사용자명 |
| TIMESCALE_PASSWORD | 1234 | 비밀번호 |

---

## 2. 테이블 구조

### 2.1 daily_prices (Hypertable) - 일봉 데이터

> TimescaleDB Hypertable / 청크 간격: 7일 / PK: (stock_code, date)

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| stock_code | VARCHAR(10) | NO | 종목코드 |
| date | DATE | NO | 거래일 |
| open | NUMERIC(15,2) | YES | 시가 |
| high | NUMERIC(15,2) | YES | 고가 |
| low | NUMERIC(15,2) | YES | 저가 |
| close | NUMERIC(15,2) | YES | 종가 |
| volume | BIGINT | YES | 거래량 |
| trading_value | BIGINT | YES | 거래대금 |
| market_cap | NUMERIC(20,2) | YES | 시가총액 |
| returns_1d | NUMERIC(10,6) | YES | 1일 수익률 |
| returns_5d | NUMERIC(10,6) | YES | 5일 수익률 |
| returns_20d | NUMERIC(10,6) | YES | 20일 수익률 |
| volatility_20d | NUMERIC(10,6) | YES | 20일 변동성 |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |
| updated_at | TIMESTAMPTZ | YES | 수정일시 (트리거 자동 갱신) |

**인덱스:**
- `daily_prices_pkey` - PK (stock_code, date)
- `idx_daily_prices_code` - stock_code
- `idx_daily_prices_date` - date DESC

**사용 예시:**
```sql
-- 특정 종목의 최근 일봉
SELECT * FROM daily_prices WHERE stock_code = '005930' ORDER BY date DESC LIMIT 30;

-- 특정 날짜 전체 종목
SELECT * FROM daily_prices WHERE date = '2026-01-20';
```

---

### 2.2 minute_prices (Hypertable) - 분봉 데이터

> TimescaleDB Hypertable / 청크 간격: 1일 / 압축: 7일 후 자동 압축 / **자동 삭제 없음** / PK: (stock_code, datetime)

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| stock_code | VARCHAR(10) | NO | 종목코드 |
| datetime | TIMESTAMPTZ | NO | 시각 |
| open | NUMERIC(15,2) | YES | 시가 |
| high | NUMERIC(15,2) | YES | 고가 |
| low | NUMERIC(15,2) | YES | 저가 |
| close | NUMERIC(15,2) | YES | 종가 |
| volume | BIGINT | YES | 거래량 |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |

**정책:**
- 압축(compression): 7일 경과 후 자동 압축 (데이터 유지, 용량 절감)
- 삭제(retention): **없음** - 모든 데이터 영구 보존

**인덱스:**
- `minute_prices_pkey` - PK (stock_code, datetime)
- `idx_minute_prices_code` - stock_code
- `idx_minute_prices_datetime` - datetime DESC
- `idx_minute_prices_code_date` - (stock_code, datetime DESC)

**사용 예시:**
```sql
-- 특정 종목의 특정일 분봉
SELECT * FROM minute_prices
WHERE stock_code = '005930'
  AND datetime >= '2026-01-20 09:00:00'
  AND datetime < '2026-01-21 00:00:00'
ORDER BY datetime;
```

---

### 2.3 candidate_stocks - 매수 후보 종목

> 일반 테이블 / PK: id (SERIAL)

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| id | SERIAL | NO | PK |
| stock_code | VARCHAR(10) | NO | 종목코드 |
| stock_name | VARCHAR(100) | YES | 종목명 |
| selection_date | TIMESTAMPTZ | NO | 선정일시 |
| score | NUMERIC(10,4) | NO | 점수 |
| reasons | TEXT | YES | 선정 사유 |
| status | VARCHAR(20) | YES | 상태 (기본: 'active') |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |

**인덱스:**
- `idx_candidate_date` - selection_date DESC
- `idx_candidate_code` - stock_code
- `idx_candidate_status` - status

---

### 2.4 virtual_trading_records - 가상 매매 기록

> 일반 테이블 / PK: id (SERIAL) / FK: buy_record_id → 자기참조

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| id | SERIAL | NO | PK |
| stock_code | VARCHAR(10) | NO | 종목코드 |
| stock_name | VARCHAR(100) | YES | 종목명 |
| action | VARCHAR(10) | NO | 'BUY' 또는 'SELL' |
| quantity | INTEGER | NO | 수량 |
| price | NUMERIC(15,2) | NO | 가격 |
| timestamp | TIMESTAMPTZ | NO | 거래일시 |
| strategy | VARCHAR(50) | YES | 전략명 |
| reason | TEXT | YES | 사유 |
| is_test | BOOLEAN | YES | 테스트 여부 (기본: true) |
| profit_loss | NUMERIC(15,2) | YES | 손익금액 (기본: 0) |
| profit_rate | NUMERIC(10,6) | YES | 수익률 (기본: 0) |
| buy_record_id | INTEGER | YES | 매수 레코드 참조 (FK → 자기 테이블) |
| target_profit_rate | NUMERIC(10,6) | YES | 목표 수익률 |
| stop_loss_rate | NUMERIC(10,6) | YES | 손절률 |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |

**제약:**
- FK: `buy_record_id` → `virtual_trading_records(id)`
- Partial Unique: SELL 레코드의 buy_record_id 중복 방지

**인덱스:**
- `idx_virtual_trading_code_date` - (stock_code, timestamp DESC)
- `idx_virtual_trading_action` - action
- `idx_virtual_trading_test` - is_test
- `idx_virtual_trading_timestamp` - timestamp DESC
- `idx_virtual_trading_unique_sell` - buy_record_id (WHERE action='SELL' AND buy_record_id IS NOT NULL)

---

### 2.5 real_trading_records - 실거래 매매 기록

> 일반 테이블 / PK: id (SERIAL) / FK: buy_record_id → 자기참조

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| id | SERIAL | NO | PK |
| stock_code | VARCHAR(10) | NO | 종목코드 |
| stock_name | VARCHAR(100) | YES | 종목명 |
| action | VARCHAR(10) | NO | 'BUY' 또는 'SELL' |
| quantity | INTEGER | NO | 수량 |
| price | NUMERIC(15,2) | NO | 가격 |
| timestamp | TIMESTAMPTZ | NO | 거래일시 |
| strategy | TEXT | YES | 전략명 |
| reason | TEXT | YES | 사유 |
| profit_loss | NUMERIC(15,2) | YES | 손익금액 (기본: 0) |
| profit_rate | NUMERIC(10,6) | YES | 수익률 (기본: 0) |
| buy_record_id | INTEGER | YES | 매수 레코드 참조 (FK → 자기 테이블) |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |

**인덱스:**
- `idx_real_trading_code_date` - (stock_code, timestamp DESC)
- `idx_real_trading_action` - action
- `idx_real_trading_timestamp` - timestamp DESC

---

### 2.6 financial_data - 재무 데이터

> 일반 테이블 / PK: id (SERIAL) / UNIQUE: (stock_code, base_year, base_quarter)

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| id | SERIAL | NO | PK |
| stock_code | VARCHAR(10) | NO | 종목코드 |
| base_year | VARCHAR(4) | NO | 기준연도 |
| base_quarter | VARCHAR(2) | NO | 기준분기 |
| report_date | VARCHAR(10) | YES | 리포트일 |
| per | NUMERIC(15,4) | YES | PER |
| pbr | NUMERIC(15,4) | YES | PBR |
| eps | NUMERIC(15,2) | YES | EPS |
| bps | NUMERIC(15,2) | YES | BPS |
| roe | NUMERIC(10,4) | YES | ROE |
| roa | NUMERIC(10,4) | YES | ROA |
| debt_ratio | NUMERIC(10,4) | YES | 부채비율 |
| operating_margin | NUMERIC(10,4) | YES | 영업이익률 |
| sales | NUMERIC(20,2) | YES | 매출액 |
| net_income | NUMERIC(20,2) | YES | 순이익 |
| market_cap | NUMERIC(20,2) | YES | 시가총액 |
| industry_code | VARCHAR(20) | YES | 업종코드 |
| retrieved_at | TIMESTAMPTZ | YES | 조회일시 |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |
| updated_at | TIMESTAMPTZ | YES | 수정일시 (트리거 자동 갱신) |

---

### 2.7 financial_statements - ML용 재무제표

> 일반 테이블 / PK: id (SERIAL) / UNIQUE: (stock_code, report_date)

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| id | SERIAL | NO | PK |
| stock_code | VARCHAR(10) | NO | 종목코드 |
| report_date | VARCHAR(10) | NO | 리포트일 |
| fiscal_quarter | VARCHAR(10) | YES | 회계분기 |
| per | NUMERIC(15,4) | YES | PER |
| pbr | NUMERIC(15,4) | YES | PBR |
| psr | NUMERIC(15,4) | YES | PSR |
| dividend_yield | NUMERIC(10,4) | YES | 배당수익률 |
| roe | NUMERIC(10,4) | YES | ROE |
| debt_ratio | NUMERIC(10,4) | YES | 부채비율 |
| operating_margin | NUMERIC(10,4) | YES | 영업이익률 |
| net_margin | NUMERIC(10,4) | YES | 순이익률 |
| revenue | NUMERIC(20,2) | YES | 매출액 |
| operating_profit | NUMERIC(20,2) | YES | 영업이익 |
| net_income | NUMERIC(20,2) | YES | 순이익 |
| total_assets | NUMERIC(20,2) | YES | 총자산 |
| current_assets | NUMERIC(20,2) | YES | 유동자산 |
| current_liabilities | NUMERIC(20,2) | YES | 유동부채 |
| total_liabilities | NUMERIC(20,2) | YES | 총부채 |
| total_equity | NUMERIC(20,2) | YES | 총자본 |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |
| updated_at | TIMESTAMPTZ | YES | 수정일시 (트리거 자동 갱신) |

---

### 2.8 quant_factors - 팩터 점수

> 일반 테이블 / PK: id (SERIAL) / UNIQUE: (calc_date, stock_code)

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| id | SERIAL | NO | PK |
| calc_date | VARCHAR(10) | NO | 산출일 |
| stock_code | VARCHAR(10) | NO | 종목코드 |
| value_score | NUMERIC(10,4) | YES | 가치 점수 |
| momentum_score | NUMERIC(10,4) | YES | 모멘텀 점수 |
| quality_score | NUMERIC(10,4) | YES | 퀄리티 점수 |
| growth_score | NUMERIC(10,4) | YES | 성장 점수 |
| total_score | NUMERIC(10,4) | YES | 종합 점수 |
| factor_rank | INTEGER | YES | 순위 |
| factor_details | TEXT | YES | 상세 (JSON 형태) |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |
| updated_at | TIMESTAMPTZ | YES | 수정일시 (트리거 자동 갱신) |

**인덱스:**
- `idx_quant_factors_date` - calc_date
- `idx_quant_factors_rank` - (calc_date, factor_rank)
- `idx_quant_factors_code` - stock_code

---

### 2.9 quant_portfolio - 상위 포트폴리오

> 일반 테이블 / PK: id (SERIAL) / UNIQUE: (calc_date, stock_code)

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| id | SERIAL | NO | PK |
| calc_date | VARCHAR(10) | NO | 산출일 |
| stock_code | VARCHAR(10) | NO | 종목코드 |
| stock_name | VARCHAR(100) | YES | 종목명 |
| rank | INTEGER | YES | 순위 |
| total_score | NUMERIC(10,4) | YES | 종합 점수 |
| reason | TEXT | YES | 사유 |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |
| updated_at | TIMESTAMPTZ | YES | 수정일시 (트리거 자동 갱신) |

---

### 2.10 stock_prices (레거시) - 기존 호환용

> 일반 테이블 / PK: id (SERIAL) / UNIQUE: (stock_code, date_time) / 현재 비어있음

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| id | SERIAL | NO | PK |
| stock_code | VARCHAR(10) | NO | 종목코드 |
| date_time | TIMESTAMPTZ | NO | 일시 |
| open_price | NUMERIC(15,2) | YES | 시가 |
| high_price | NUMERIC(15,2) | YES | 고가 |
| low_price | NUMERIC(15,2) | YES | 저가 |
| close_price | NUMERIC(15,2) | YES | 종가 |
| volume | BIGINT | YES | 거래량 |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |

---

### 2.11 trading_records (레거시) - 기존 호환용

> 일반 테이블 / PK: id (SERIAL) / 현재 비어있음

| 컬럼 | 타입 | Nullable | 설명 |
|---|---|---|---|
| id | SERIAL | NO | PK |
| stock_code | VARCHAR(10) | NO | 종목코드 |
| action | VARCHAR(10) | NO | 매매구분 |
| quantity | INTEGER | NO | 수량 |
| price | NUMERIC(15,2) | NO | 가격 |
| timestamp | TIMESTAMPTZ | NO | 거래일시 |
| profit_loss | NUMERIC(15,2) | YES | 손익 (기본: 0) |
| created_at | TIMESTAMPTZ | YES | 생성일시 (자동) |

---

## 3. 테이블 관계도

```
daily_prices (Hypertable)          minute_prices (Hypertable)
    PK: stock_code + date              PK: stock_code + datetime
                                       압축: 7일 후 자동

candidate_stocks
    PK: id
    선정된 매수 후보 종목 관리

virtual_trading_records             real_trading_records
    PK: id                              PK: id
    FK: buy_record_id → 자기(id)         FK: buy_record_id → 자기(id)
    SELL.buy_record_id → BUY.id          SELL.buy_record_id → BUY.id
    (가상 매매)                           (실거래 매매)

financial_data                      financial_statements
    PK: id                              PK: id
    UNIQUE: stock_code +                UNIQUE: stock_code +
            base_year +                         report_date
            base_quarter

quant_factors                       quant_portfolio
    PK: id                              PK: id
    UNIQUE: calc_date + stock_code      UNIQUE: calc_date + stock_code
```

---

## 4. TimescaleDB 정책

### 압축 정책
- **대상**: minute_prices
- **조건**: 7일 경과 후 자동 압축
- **효과**: 저장 공간 60~90% 절약, 읽기 성능 유지
- **세그먼트**: stock_code 기준

### 보존 정책 (삭제)
- **없음**: 모든 데이터 영구 보존
- **주의**: retention policy 절대 설정하지 않을 것

---

## 5. 관련 소스 파일

| 파일 | 설명 |
|---|---|
| `db/connection.py` | DB 연결 풀 관리 (ThreadedConnectionPool) |
| `db/repositories/base.py` | Repository 베이스 클래스 |
| `db/repositories/price.py` | 가격 데이터 Repository |
| `init-scripts/01-init.sql` | 스키마 초기화 SQL |
| `scripts/migrate_to_timescaledb.py` | SQLite→PostgreSQL 마이그레이션 |
| `core/post_market_data_saver.py` | 장 마감 후 데이터 저장 로직 |
| `utils/data_cache.py` | 데이터 캐시 (Deprecated, PriceRepository로 위임) |

---

## 6. 운영 참고

### psql 접속
```powershell
# PowerShell에서 직접 접속
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U robotrader -p 5433 -d robotrader
```

### 서비스 관리
```powershell
# 관리자 PowerShell 필요
net stop postgresql-x64-16     # 중지
net start postgresql-x64-16    # 시작
```

### 백업
```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -U robotrader -p 5433 -d robotrader -F c -f backup.dump
```

### 복원
```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_restore.exe" -U robotrader -p 5433 -d robotrader backup.dump
```
