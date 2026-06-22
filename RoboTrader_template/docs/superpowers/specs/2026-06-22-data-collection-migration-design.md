# 데이터 수집 책임 kis_template 이관 — 설계 (Spec)

**작성일**: 2026-06-22
**상태**: 설계 승인됨 (구현 계획 대기)
**배경**: rt(`D:\GIT\RoboTrader`)·rt_quant(`D:\GIT\RoboTrader_quant`) 전략을 폐기. 다만 이 두 프로그램이 각각 분봉·일봉을 DB에 적재 중이라, 수집 책임을 kis_template로 이관한다. 6/19 사고(런처에서 rt 제외→분봉 수집 중단)의 재발을 막고, 유예기간 동안 병행·검증 후 안전 전환한다.

---

## 1. 목표 / 비목표

**목표**
- kis_template 봇이 **분봉(거래대금순 300종목)**·**일봉(전체시장 ~2,601종목)**을 EOD에 수집·적재한다.
- 유예기간 동안 **섀도우 테이블**에 적재하고 실테이블(rt/rt_quant 적재분)과 **매일 자동 비교**한다.
- 연속 N거래일 무결 확인 + 사장님 결재 후 **실테이블 단독 적재로 전환**, rt/rt_quant를 런처에서 제거.
- **완전 드롭인**: 다운스트림(백테스트·스크리너·라이브 봇)이 영향받지 않도록 기존과 동일한 유니버스·컬럼을 채운다.

**비목표 (YAGNI)**
- rt/rt_quant 코드 수정 (유예기간 내내 무수정·계속 가동).
- 장중 실시간 DB 적재 (EOD 배치만 — 기존 rt/rt_quant와 동일).
- 자동 전환 (전환은 수동 결재).
- 신규 KIS API 추가 (kis_template 기존 API로 완결).

---

## 2. 현행 수집 분담 (이관 대상)

| 데이터 | 현행 프로그램 | 대상 DB·테이블 | 유니버스 | 타이밍 | KIS API |
|---|---|---|---|---|---|
| 분봉 | RoboTrader | `robotrader.minute_candles` (localhost:5433) | 거래대금순 **300종목/일**(매일 갱신) | EOD ~15:45 | `FHKST03010230` (주식일별분봉, 4구간) |
| 일봉 | RoboTrader_quant | `robotrader_quant.daily_prices` (localhost:5433) | 전체시장 **~2,601종목** | EOD ~15:35 | `FHKST03010100` (국내주식기간별시세) |
| 지수 일봉 | RoboTrader | (KOSPI/KOSDAQ 지수) | 2개 지수 | EOD | FDR `KS11`/`KQ11` |

### 2.1 테이블 스키마 (드롭인 대상)

**`minute_candles`** — PK `(stock_code, trade_date, idx)`
```
stock_code VARCHAR, trade_date VARCHAR(YYYYMMDD), idx INTEGER,
date VARCHAR, time VARCHAR(HHMMSS),
close/open/high/low DOUBLE PRECISION, volume DOUBLE PRECISION,
amount DOUBLE PRECISION, datetime TIMESTAMP
```

**`daily_prices`** — `date`는 TEXT(주의). close는 **이미 수정주가**(adj_factor 곱하지 말 것).
```
stock_code VARCHAR, date TEXT, open/high/low/close DOUBLE PRECISION,
volume BIGINT, trading_value BIGINT, market_cap DOUBLE PRECISION,
returns_1d/5d/20d DOUBLE PRECISION, volatility_20d DOUBLE PRECISION,
adj_factor DOUBLE PRECISION, created_at/updated_at TIMESTAMP
```

---

## 3. 설계 결정 (확정)

| # | 결정 | 선택 |
|---|---|---|
| D1 | 수집 범위 | **완전 드롭인** — 분봉 300(거래대금순), 일봉 2,601(전체시장) |
| D2 | 일봉 컬럼 범위 | **전 컬럼(파생 포함)** — OHLCV+trading_value+market_cap+returns_1d/5d/20d+volatility_20d+adj_factor |
| D3 | 유예·전환 방식 | **섀도우 테이블 → 매일 비교 → N일 무결 후 수동 전환** |
| D4 | 실행 위치 | **봇 EOD 훅 내장** (`system_monitor._handle_postmarket_tasks`, 15:35+, 하루 1회) |

---

## 4. 재사용 자산 (kis_template 기보유 — 신규 포팅 0)

| 기능 | 위치 | 비고 |
|---|---|---|
| 일봉 OHLCV fetch | `api/kis_market_api.py:101` `get_inquire_daily_itemchartprice` (FHKST03010100) | rt_quant와 동일 |
| 시가총액 fetch | `api/kis_market_api.py:740` `get_stock_market_cap` (`hts_avls`, **억원 단위→원 변환**) | rt_quant 동일 방식 |
| 분봉 fetch | `api/kis_chart_api.py` (FHKST03010230, 4구간) | 분봉 수집기에서 사용 |
| 거래대금순 유니버스 | `api/kis_market_api.py` `get_volume_rank` (콜당 30, 6밴드×2시장=12콜) | 분봉 300 선정 |
| 전종목 마스터 | `FinanceDataReader.StockListing` | 일봉 유니버스(DB-distinct는 순환이라 지양) |
| 파생 returns/volatility | `scripts/etl_backfill_daily_prices.py` `SQL_UPDATE_RETURNS` (윈도우 함수, 멱등·PIT안전) | 적재 후 SQL 1회 |
| adj_factor | `scripts/10pct_strategy/p0_apply_adj_factor.py` `compute_adj_factors/update_adj_factors` | `corp_events`(OpenDART) 기반 |
| corp_events 백필 | `scripts/backfill_corp_events.py` (OpenDART+KRX+FDR) | 분할/증자 이벤트, 일회성+증분 |
| OHLCV 배치 쓰기 | `db/repositories/price.py` `save_daily_prices_batch` | UPSERT |
| 지수 일봉 | `scripts/backfill_kospi_index.py` (FDR KS11/KQ11) | regime 게이트 의존 |
| market_cap 단위 | `hts_avls`는 억원 → `×100,000,000` | per-row `market_cap = close × (현재시총/현재가)` |

**시가총액 계산법(rt_quant 동일)**: `get_stock_market_cap`로 현재 시총·현재가 조회 → `listed_shares = 현재시총 / 현재가` → 각 일자 행에 `market_cap = close × listed_shares`.

---

## 5. 아키텍처 / 컴포넌트

각 컴포넌트는 단일 책임, `run(...) -> dict`(print 없이 결과 반환), 멱등, 예외는 훅에서 흡수.

```
bot/system_monitor._handle_postmarket_tasks (15:35+, 하루 1회)
  └─ _run_data_collection()                      ← 신규 훅 (equity 스냅샷 다음 단계)
       └─ asyncio.to_thread(...)                 ← ~10분 루프가 모니터 태스크 비차단
            ├─ collectors/daily_collector.py     ← 일봉 2,601 수집 + 파생 + adj
            ├─ collectors/minute_collector.py    ← 분봉 300 수집 (거래대금순)
            ├─ collectors/index_collector.py     ← KOSPI/KOSDAQ 지수 일봉
            └─ collectors/reconciliation.py      ← 섀도우 vs 실테이블 비교 리포트
```

- **설정 플래그** `DATA_COLLECTION_TARGET` (`shadow` | `live`, `config/constants.py`):
  `shadow`(유예) → 섀도우 테이블 적재 + 비교. `live`(전환) → 실테이블 적재(비교 생략).
- 신규 모듈은 `collectors/` 패키지에 모은다. fetch/계산/쓰기는 기존 `api/`·`scripts/` 자산을 호출.

---

## 6. 데이터 흐름 (EOD, 시장 15:30 마감 후)

1. **일봉** (`daily_collector`)
   - 유니버스 로드(FDR 전체시장 코드)
   - 각 종목 당일 일봉 OHLCV fetch (FHKST03010100) + 시총 fetch(get_stock_market_cap)
   - `target` 테이블(shadow|live) UPSERT (OHLCV·trading_value·market_cap)
   - `SQL_UPDATE_RETURNS`로 returns_1d/5d/20d·volatility_20d 계산
   - `corp_events` 기반 adj_factor 갱신
2. **분봉** (`minute_collector`)
   - 거래대금순 top 300 선정(get_volume_rank, 12콜)
   - 각 종목 당일 전체 분봉 fetch(FHKST03010230, 4구간)
   - `target` 테이블 종목·일자 단위 DELETE+INSERT (멱등)
3. **지수** (`index_collector`): KOSPI/KOSDAQ 당일 지수 일봉 적재
4. **비교** (`reconciliation`, `shadow` 모드만): 그날 섀도우 vs 실테이블 대조 → `collection_reconciliation` 테이블 + 로그 요약

---

## 7. 섀도우 테이블 / 비교 / 전환

### 7.1 섀도우 테이블
- `minute_candles_kt_shadow` (robotrader DB), `daily_prices_kt_shadow` (robotrader_quant DB) — **실테이블과 동일 스키마**.
- (지수도 필요 시 섀도우.) 전환 후 DROP.

### 7.1.1 일봉 섀도우 시딩 (중요)
- 일봉 파생 컬럼(`returns_5d/20d`, `volatility_20d`)과 `adj_factor`는 **과거 이력이 있어야** 계산된다(`SQL_UPDATE_RETURNS`·adj는 이전 행/이벤트를 읽음). 섀도우 테이블이 비어 있으면 grace 초기 ~20거래일간 NULL → 검증 불가.
- **해결**: shadow 모드 시작 시 **실 `daily_prices`의 과거분을 `daily_prices_kt_shadow`로 1회 시딩(복사)**한다. 이후 매일 당일 행만 append → 파생·adj가 첫날부터 유효, 비교도 첫날부터 의미 있음.
- 분봉은 일자 독립(교차일 윈도우 없음)이라 시딩 불필요.
- 일봉 fetch는 당일 1행이면 충분하나(이력은 시딩분), gap 복원력을 위해 소폭 lookback(예: 최근 5거래일)을 UPSERT한다.

### 7.2 비교 규칙 (중요 뉘앙스)
- **일봉(전체시장)**: 거의 정확 일치 기대. 비교 항목 = 행수·종목 커버리지·종가/거래량 값 일치율, 불일치 종목 목록. 허용오차: 부동소수 epsilon.
- **분봉(거래대금순 300)**: rt와 kis_template가 **각자 독립적으로 top300을 시점차 두고 선정**하므로 유니버스가 완전 동일하지 않다. 따라서 판정 = ① 커버리지 ~300 충족 ② **교집합 종목의 바 단위 값 일치율**. (완전 동일 강요 X.)
- 결과를 `collection_reconciliation(trade_date, dataset, real_rows, shadow_rows, overlap, value_match_rate, coverage, verdict)`에 기록.

### 7.3 전환 기준 / 절차
- **기준**: 연속 **≥5 거래일** 비교 무결(일봉 값 일치율≈100%, 분봉 교집합 일치율 높음·커버리지 충족) + **사장님 결재**(자동 아님).
- **절차**: `DATA_COLLECTION_TARGET=live`로 변경 + 봇 재시작 → kis_template 실테이블 단독 적재 → rt/rt_quant를 `run_all_robotraders.bat`에서 제거 → 섀도우 테이블 DROP.

---

## 8. 에러 처리 / 안전

- 훅 전체 try/except로 **EOD 흐름 비차단**(equity 스냅샷 훅과 동일 패턴). 섀도우 모드라 실패해도 실데이터 무영향.
- **멱등**: 재시작/재실행 안전(분봉 DELETE+INSERT, 일봉 UPSERT). 부분 실패는 로그 + 다음 거래일 재수집.
- **비차단 실행**: `asyncio.to_thread`로 ~10분 루프가 시스템 모니터 태스크를 막지 않게 한다.
- **Rate-limit**: 봇 토큰버킷 재사용. EOD 버스트 ≈ 6,400콜(~7–11분). 봇은 이미 ~217K콜/일 처리 → 쿼터 비이슈. 장후 거래 API 유휴라 여유.
- **봇 생존**: 봇은 마감 후 ≥18:47까지 가동(검증됨) → EOD 수집 윈도우 충분.

---

## 9. 테스트 전략

- **단위**: 시총 단위변환(억원→원)·per-row market_cap 계산, 분봉 idx/time 매핑, reconciliation 판정(일치율·커버리지·교집합) 로직.
- **재사용 검증 자산**: 파생 SQL·adj_factor 공식은 기존 검증(스팟체크·PIT 회귀) 보유 → 회귀로 묶음.
- **통합(dry-run)**: 소수 종목(예: 5)으로 섀도우 적재→비교 e2e 1거래일.

---

## 10. 미해결 (계획단계 세부, 블로커 아님)

- N(전환 무결일수) 기본 5 — 사장님 조정 가능.
- 분봉 4구간 시각 경계(08:00 NXT vs 09:00 KRX) — kis_template는 KRX 기준 09:00–15:30.
- corp_events 증분 갱신 주기(분할 이벤트는 드묾 — 주1회/이벤트 트리거).

---

## 부록: 핵심 파일 레퍼런스

- rt 분봉: `D:\GIT\RoboTrader\core\expanded_minute_collector.py`(top300), `utils/data_cache.py`(스키마·INSERT)
- rt_quant 일봉: `D:\GIT\RoboTrader_quant\core\helpers\screening_task_runner.py:217`(전종목 루프), `core/ml_data_collector.py:206`(market_cap 역산)
- kis_template 훅: `bot/system_monitor.py._handle_postmarket_tasks`
