# Phase 0 corp_events 백필 보고서

생성일시: 2026-05-24 12:03:58
소요시간: 16초

## 1. 백필 전후 행 수

| 구분 | 건수 |
|------|------|
| 백필 전 | 1,085 |
| 백필 후 | 1,085 |
| 신규 삽입 | 0 |

## 2. event_type별 분포 (백필 후)

| event_type | 건수 |
|------------|------|
| administrative | 2 |
| bonus_issue | 50 |
| rights_issue | 891 |
| split | 142 |

## 3. 연도별 분포

| 연도 | 건수 |
|------|------|
| 2021 | 178 |
| 2022 | 178 |
| 2023 | 147 |
| 2024 | 169 |
| 2025 | 258 |
| 2026 | 155 |

## 4. Spot Check 검증

| 결과 | 종목 | 이벤트 | 날짜 | 설명 | 메타비고 |
|------|------|--------|------|------|---------|
| PASS | 035720 | split | 2021-04-15 | 카카오 5:1 액면분할 (500->100) |  |
| PASS | 260970 | split | 2021-02-01 | 260970 10:1 액면분할 (5000->500) |  |
| PASS | 004090 | split | 2021-04-15 | 한국석유 10:1 액면분할 (5000->500) |  |

## 5. 다음 단계 (P0-2b) 사용 가능 여부

**OK** split 이벤트가 정상 적재됐고 spot check 전체 PASS. P0-2b (adj_factor 역산 적용)를 진행할 수 있습니다.

## 6. 수집 파라미터

- 유니버스 크기: 10종목
- split/merge: pykrx get_stock_major_changes, split=0, merge=0
- dividend_ex: pykrx get_market_fundamental_by_ticker, 삽입=0
- 멱등성: ON CONFLICT (stock_code, event_type, event_date) DO NOTHING
- No Look-Ahead: event_date = 실제 발효일 (pykrx 인덱스 기준)
