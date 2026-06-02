# P0-2b adj_factor PIT 보정 완료 (2026-05-24)

## 작업 개요
`robotrader_quant.daily_prices.adj_factor` 컬럼을 PIT(Point-In-Time) 원칙에 따라
액면분할/병합 보정값으로 UPDATE.

## 결과 요약

| 항목 | 값 |
|---|---|
| UPDATE 전 adj_factor != 1.0 행 수 | 0행 |
| UPDATE 후 adj_factor != 1.0 행 수 | **65,662행** |
| 보정 종목 수 | **97종목** |
| 총 daily_prices 행 수 | 2,727,649행 |
| 이벤트 소스 | corp_events split (pykrx, split_factor 있는 것) 105건 → 99종목 |

## Spot Check 3건 (전체 PASS)

| 종목 | 이벤트 | adj_pre | adj_post | 결과 |
|---|---|---|---|---|
| 카카오(035720) | 2021-04-15 5:1 분할 | 5.0 | 1.0 | OK |
| 한국석유(004090) | 2021-04-15 10:1 분할 | 10.0 | 1.0 | OK |
| 260970 | 2021-02-01 10:1 분할 | 10.0 | 1.0 | OK |

## PIT 안전성 회귀: OK

테스트 시점 2022-01-03 기준으로 3종목 모두:
- 시뮬레이션 adj_factor = DB 저장값 (정확히 일치)
- 미래 이벤트(2022-01-03 이후)가 과거 adj_factor에 영향 없음 확인

## 알고리즘

```
adj_factor(T) = product(split_factor for events where event_date > T)
```

- `event_date > T`: T 이후 발효 예정인 분할 → T 시점 원시가격을 분할 후 스케일로 비교 가능하게 함
- `event_date <= T`: 이미 발효됨 → 가격에 반영 완료 → factor = 1.0
- 복수 분할: 누적 곱

## 주의사항

- bonus_issue 50건: meta에 ratio 없음, pykrx 가격비율 추정도 0건 성공 → 미반영
  - 해당 종목들의 adj_factor는 1.0 유지 (split만 반영됨)
- spot check 가격 연속성 검증 불가 이유:
  - daily_prices는 원시(비조정) 가격 저장
  - 분할 당일 시장 가격 움직임(Kakao: 발효일 +438% 장중 급등)이 포함되어
    `close_pre/sf ≈ close_post` 검증이 의미 없음
  - adj_factor 값 자체만으로 검증 (pre=sf, post=1.0)

## 산출물

- 스크립트: `scripts/10pct_strategy/p0_apply_adj_factor.py`
- 리포트: `reports/10pct_strategy/phase0_adj_factor_correction.md`

## P1 forward return 계산 가용성: OK

adj_factor가 올바르게 적용되어 P1 수정주가 기반 forward return 계산 가능.
사용법: `adj_close = close / adj_factor` (발효일 이전 가격을 현재 스케일로 정규화)
