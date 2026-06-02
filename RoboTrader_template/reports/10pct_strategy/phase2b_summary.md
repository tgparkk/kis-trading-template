# Phase 2B 요약 — 시그널 멀티버스 결과

생성일: 2026-05-24
소요: 2.2분

## 처리 결과
- 전체 평가 셀: **10,380**
- 합격 셀: **271** (2.6%)
- 합격선: lift ≥ 1.2 AND IS > 0 AND OOS > 0 AND |IS_OOS_diff| < |IS_mean| AND n ≥ 50

## 18 매트릭스 합격 수 (6 국면 × 3 버킷)

| 국면\버킷 | 스윙 | 미드 | 포지션 |
|-----------|------|------|--------|
| BULL_HIGH_VOL | 83 | 11 | 4 |
| BULL_LOW_VOL | 36 | 90 | 7 |
| BEAR_HIGH_VOL | 12 | 2 | 6 |
| BEAR_LOW_VOL | 0 | 0 | 0 |
| SIDEWAYS_HIGH_VOL | 0 | 0 | 0 |
| SIDEWAYS_LOW_VOL | 18 | 0 | 2 |

## BULL_HIGH_VOL × Position 최강 시그널 Top 3

| rank | family | params | lift | IS_mean | OOS_mean | n |
|------|--------|--------|------|---------|----------|---|
| 1 | ema200_trend | {'hold_days': 20, 'slope_min': 0.001} | 2.106 | N/A | 0.4829 | 65 |
| 2 | ema200_trend | {'hold_days': 20, 'slope_min': 0.0} | 2.070 | N/A | 0.4745 | 66 |
| 3 | ema200_trend | {'hold_days': 60, 'slope_min': 0.001} | 1.929 | N/A | 0.4533 | 50 |

## IS/OOS 정합 분석
- IS 강(>1%) OOS 약(<0%) 시그널 비율: **0.7%** (29/3898)
- 과적합 위험: 낮음

## Stage C 진입 판단
- **OK** — 합격 셀 271개, 조합 커버 9/18

### 판정 기준
- OK: 합격 셀 ≥ 50 AND (regime, bucket) 조합 커버 ≥ 9/18
- NG: 위 기준 미달 → 합격선 완화 또는 시그널 family 보강 필요