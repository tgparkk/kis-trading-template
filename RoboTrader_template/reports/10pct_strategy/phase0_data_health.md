# P0-1 데이터 위생 점검 — 2026-05-24

## 요약 (1줄)

`robotrader_quant.daily_prices` 5.4년 273만 행은 EDA에 충분. 손상 117행 정규식 필터로 즉시 정리 가능. 단 **survivorship bias 차단(P1 시작 전 PIT universe 필수)**, **corp_events 백필 미완(P0-2 차단 요인)**, **2024-03 데이터 점프(시계열 끊김 주의)** 3가지가 향후 Phase 진입 전 처리 필요.

---

## 1. 메인 데이터 자산: `robotrader_quant.daily_prices`

| 항목 | 값 |
|---|---|
| 기간 | 2021-01-12 ~ 2026-05-22 (5.4년) |
| 총 행 수 | 2,727,649 |
| 종목 수 | 2,601 |
| 컬럼 | stock_code, date(text), open, high, low, close, volume, trading_value, market_cap, returns_1d/5d/20d, volatility_20d, adj_factor, created_at, updated_at |
| 인덱스 | PK(stock_code, date), idx(stock_code, date) |

### 컬럼 결측률 (유효 날짜 2,727,532행 기준)

| 컬럼 | 채움률 | 결측 | 비고 |
|---|---|---|---|
| open / close / volume / trading_value | 100.0% | 0 | 완전 |
| market_cap | 98.9% | 29,643 | 1.1% 결측 |
| returns_1d | 99.9% | 2,629 | 종목 첫날 자연 결측 |
| returns_5d | 99.5% | 13,030 | 종목 첫 5일 자연 결측 |
| returns_20d | 98.1% | 51,992 | 종목 첫 20일 자연 결측 |
| volatility_20d | 99.8% | 5,246 | |
| **adj_factor** | **100% but = 1.0** | — | **⚠️ 액면분할 미반영, P0-2 보정 필수** |

### 손상 데이터 (Q-1)

| 항목 | 값 |
|---|---|
| 손상 날짜 행 | **117 / 2,727,649 (0.0043%)** |
| 패턴 | `2026--0-3-` (51) / `2026--0-4-` (53) / `2026--0-5-` (13) |
| 영향 종목 | 53 |
| 처리 방법 | `WHERE date ~ '^\d{4}-\d{2}-\d{2}$'` 필터 (PIT 헬퍼 내장) |

---

## 2. 종목 universe 구조 (Survivorship 평가)

### 데이터 시작 연도 분포 (상장 시점/백필 시점)

| 시작 연도 | 종목 수 | 비고 |
|---|---|---|
| 2021 | 1,813 | 풀 트랙 후보(5.4년) |
| 2022 | 62 | 신규 상장 |
| 2023 | 82 | 신규 상장 |
| **2024** | **559** | **⚠️ 2024-03 백필 점프** (아래) |
| 2025 | 75 | 신규 상장 |
| 2026 | 10 | 신규 상장 |
| 합계 | 2,601 | |

### 데이터 종료 연도 분포 (상장폐지 추정)

| 종료 연도 | 종목 수 | 비고 |
|---|---|---|
| 2024 | 100 | **상장폐지(추정), survivorship 차단 대상** |
| 2025 | 4 | 상장폐지(추정) |
| 2026 | 2,497 | 현존 |
| 합계 | 2,601 | |

### 종목별 거래일수 분포 (5.4년 풀 ≈ 1,330 영업일)

| 거래일수 구간 | 종목 수 | % |
|---|---|---|
| 3 ~ 99 | 13 | 0.5% |
| 100 ~ 297 | 59 | 2.3% |
| 300 ~ 499 | 89 | 3.4% |
| 500 ~ 598 | 501 | 19.3% |
| 600 ~ 697 | 39 | 1.5% |
| 700 ~ 797 | 119 | 4.6% |
| 800 ~ 1,194 | 102 | 3.9% |
| 1,210 ~ 1,298 | 38 | 1.5% |
| **1,300 ~ 1,314** | **1,641** | **63.1% (풀 트랙)** |

→ **풀 5.4년 트랙 가능 종목 = 1,641개 (63%)**. 나머지는 부분 트랙, universe 빌드 시 PIT 가용 시점 명확히.

---

## 3. 거래일 / 활성 종목 시계열 (이상점)

월별 활성 종목 수 (요약):

| 시점 | 활성 종목 | 변화 |
|---|---|---|
| 2021-01 | 1,735 | (시작) |
| 2024-02 | 1,968 | (정상 누적 증가) |
| **2024-03** | **1,582 → 2,343** | **⚠️ 백필 점프** (월 첫날 min=170, 평균 1,582로 끊김) |
| 2024-04 | 2,346 | (안정 회복) |
| 2026-05 | 2,485 | (현재) |

→ **2024-03 ~ 04은 백필 이벤트로 시계열 끊김**. P0-3 No-Look-Ahead 헬퍼는 이 시점도 chronological 안전성 확보 필요. 백필 종목이 2024-03 이전 시점에 universe에 등장하지 않도록 PIT 시작일 강제.

---

## 4. 보조 데이터 인벤토리

### 4-1. `robotrader.corp_events` (P0-2 의존)

| 항목 | 값 |
|---|---|
| 스키마 | stock_code, event_type, event_date, meta(jsonb), end_date |
| event_type | split / rights_issue / bonus_issue / dividend_ex / administrative / caution / warning / halt |
| 행 수 | **94 (⚠️ 백필 미완)** |
| 기간 | 2025-07-29 ~ 2026-05-03 (10개월) |

→ **5.4년 액면분할/병합 본 적재 안 됨**. 메모리 5/3 changelog 확인 — 인프라만 구축, 본 적재 결재 대기 상태. P0-2 시작 전 pykrx로 2021~2025 추가 수집 필요.

### 4-2. `strategy_analysis` DB (postgres 권한, 매우 유용)

14개 테이블 확인:

| 테이블 | 활용 단계 | 비고 |
|---|---|---|
| `stock_sector` | Stage A 섹터 필터 | 4,085종목 등록, **단 market 컬럼이 전부 "KOSPI" — 데이터 품질 이슈** (시장구분 직접 사용 불가, 섹터명만 활용) |
| `stock_info` | universe 매칭 | 미점검 |
| `market_index` | P1 베이스라인 | KOSPI/KOSDAQ 지수 시계열로 추정 |
| **`market_regime`** | **P0-4 재사용** | **68,342행, 2021-01-04~2026-02-12, regime + regime_score, method 다중**. 우리 5.4년 중 96% 커버. 2026-02-12 이후 3.4개월만 자체 백필. **PK = (date, index_code, method)** — index/method별 분류 있음 |
| `sector_index_daily` | Stage B 섹터 모멘텀 family | 미점검 |
| `daily_candles` / `daily_candles_rt` | 보조 일봉 | 메모리에 2.4M 행 명시 (별도) |
| `yearly_fundamentals` | 포지션 버킷 가치 family | 2021~2025, 2,110종목 (메모리) |
| `financial_data` | 포지션 버킷 가치 family | 미점검 |
| `sawkami_*` / `lynch_*` | 참조 | 기존 전략 산출물, 직접 사용 없음 |

### 4-3. `robotrader.minute_candles` (Stage B 스윙 분봉 family용)

- 2025-02-24 ~ 2026-05-22 (1.3년)
- 1,364종목, **5,170만 행, 10GB**
- 스윙 버킷 분봉 모멘텀 family / 진입 캔들 정밀 측정에 활용

### 4-4. 비어있는 DB

- `robotrader_orb`: 0 tables (메모리 line 286 명시와 일치)
- `strategy_analysis` as `robotrader` user: 0 tables (권한 차단, postgres 유저로 접속해야 보임)

---

## 5. PIT / Look-Ahead 위험 평가

| 위험 | 상태 | 대응 |
|---|---|---|
| ① 손상 날짜 117행 | LOW | 정규식 필터 PIT 헬퍼 내장 (P0-3) |
| ② **survivorship bias** | **HIGH** | 상장폐지 104종목을 그 시점엔 universe에 포함하는 PIT 빌더 필수 (P0-3 + Stage A) |
| ③ **2024-03 백필 점프** | **HIGH** | 종목별 데이터 시작일을 stocks_pit_meta 테이블/파켓에 기록, 해당 시작일 이전엔 universe에서 제외 |
| ④ **adj_factor=1.0 (액면분할 미반영)** | **HIGH** | P0-2에서 corp_events 백필 + pykrx 보조로 5.4년 split 수집 후 adj_close 계산 |
| ⑤ market_regime 96% 커버 | MEDIUM | P0-4에서 2026-02-12 이후 자체 백필 + 기존 method 검증 |
| ⑥ stock_sector market 컬럼 오염 | MEDIUM | 시장구분(KOSPI/KOSDAQ)은 종목코드 + 별도 소스로 재구축, 섹터명만 활용 |
| ⑦ corp_events 본 적재 미완 | HIGH | P0-2 시작 전 pykrx 5.4년 split/right/bonus 백필 (별도 ticket) |

---

## 6. 다음 Phase 의존성

| Phase | 의존 사항 | 처리 |
|---|---|---|
| **P0-2** | corp_events 본 적재 필요 | pykrx 백필 후 진행. 일단 보정 없이 P1~P2 진행 가능 (단 보고서 lift 해석 시 보수적 처리) |
| **P0-3** | 본 점검 결과 위험 ②③④을 헬퍼/테스트로 잠금 | 풀 트랙 1,641종목 + 부분 트랙 960종목 PIT 메타 파켓 의무 |
| **P0-4** | market_regime 재사용 + 3.4개월 자체 백필 | postgres 유저 접속 자동화 헬퍼 작성 |
| **P1** | survivorship-safe universe + PIT meta | Stage A 진입 전 universe 빌더 완성 |
| **P2 Stage A** | 시장 구분 직접 사용 불가 | stock_sector 섹터명 + 종목코드 분류 보조 |

---

## 7. 결정 사항 / 권고

1. **즉시 처리**: P0-1 완료 표시. P0-3(No-Look-Ahead 잠금 인프라)을 직원에게 위임 — 위험 ②③ 잠금 헬퍼 필요.
2. **P0-2 차단**: corp_events 본 적재 미완 — 사장님 결재 필요 (pykrx 백필 진행할지 / 일단 보정 없이 진행할지). 보정 없이 진행 시 P1 lift 수치는 액면분할로 인한 1회성 점프 오염 가능성 있음.
3. **P0-4 재사용**: market_regime 기존 테이블 96% 커버 → 자체 구축 시간 절약. 단 method 컬럼이 다중이라 어떤 method를 채택할지 비교 분석 필요.
4. **strategy_analysis DB 권한**: postgres 유저로만 접근 — Phase 작업 시 helper 모듈에 자격증명 분리 필요 (`EXTERNAL_DB_USER=postgres`).
