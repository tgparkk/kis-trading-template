# Phase 1 — Forward Return Baseline & 90-Cell Matrix

생성일: 2026-05-24 15:16

## 1. Universe PIT Meta

- 총 종목 수: **2,589**
- first_date 범위: 2021-01-12 ~ 2026-05-20
- first_date ≤ 2022-01-01 (충분한 히스토리): **1,804** 종목
- n_days 중앙값: 1307일, 평균: 1050일

## 2. Forward Returns 파켓

- 총 행 수: **2,718,959**
- 컬럼별 결측률:

  - fwd_1d: 0.1%
  - fwd_3d: 0.3%
  - fwd_5d: 0.5%
  - fwd_10d: 1.0%
  - fwd_20d: 1.9%
  - fwd_30d: 2.9%
  - fwd_60d: 5.7%

## 3. 3-버킷 베이스라인 통계

| Bucket | Mean (%) | Sharpe×√252 | Win Rate | N |
|--------|----------|-------------|----------|---|
| swing | 0.293% | 0.226 | 45.4% | 2,716,370 |
| mid | 1.705% | 0.577 | 44.7% | 2,693,085 |
| position | 3.047% | 0.840 | 43.9% | 2,641,390 |

## 4. 90-Cell Matrix — Top 5 셀 (mean forward return 기준)

| Regime | McapQ | Bucket | Mean (%) | Win Rate | N |
|--------|-------|--------|----------|----------|---|
| bull_high_vol | Q1 | position | 12.109% | 41.0% | 133,333 |
| bull_high_vol | Q5 | position | 9.345% | 57.0% | 134,019 |
| bull_high_vol | Q1 | mid | 9.061% | 40.3% | 143,270 |
| bull_high_vol | Q4 | position | 6.407% | 48.7% | 133,427 |
| bull_high_vol | Q2 | position | 5.035% | 41.3% | 133,451 |

### Bottom 5 셀 (참고)

| Regime | McapQ | Bucket | Mean (%) | Win Rate | N |
|--------|-------|--------|----------|----------|---|
| sideways_high_vol | Q4 | swing | -0.671% | 37.5% | 36,572 |
| sideways_high_vol | Q2 | mid | -0.685% | 34.6% | 36,572 |
| sideways_high_vol | Q2 | position | -1.176% | 34.6% | 36,572 |
| sideways_high_vol | Q4 | mid | -1.502% | 36.9% | 36,572 |
| sideways_high_vol | Q4 | position | -2.475% | 37.2% | 36,572 |

## 5. P2 Stage A 진입 가능 여부

- swing Sharpe×√252: 0.226
- 매트릭스 셀 수: 60
- **P2 진입: OK**

---
_자동 생성: p1_forward_return_matrix.py_