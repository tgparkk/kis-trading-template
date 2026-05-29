# Minervini VCP — 조사 노트

> Book: Mark Minervini — *Trade Like a Stock Market Wizard* (2013) / *Think & Trade Like a Champion* (2017)
> 조사 시작: 2026-05-29
> 설계: [docs/superpowers/specs/2026-05-29-minervini-vcp-design.md](../../../docs/superpowers/specs/2026-05-29-minervini-vcp-design.md)

## 1. 핵심 개념
(SEPA = Specific Entry Point Analysis. Fundamental + Technical + RS + Pattern 4축.)

## 2. SEPA Trend Template (8조건)

| # | 조건 | 책 본문 정의 | 외부 인터뷰 차이 |
|---|---|---|---|
| 1 | Price > 150 MA, Price > 200 MA | 종가 기준 | (확인) |
| 2 | 150 MA > 200 MA | 종가 기준 | (확인) |
| 3 | 200 MA 1개월(20거래일)+ 상승 추세 | MA200(today) > MA200(20일 전) | "최소 5개월 우상향" 발화 있음 → 보조 조건 |
| 4 | 50 MA > 150 MA > 200 MA | 다단 정렬 | (확인) |
| 5 | Price > 50 MA | 종가 기준 | (확인) |
| 6 | 52주 신고가 −25% 이내 | (52W high - close) / 52W high ≤ 0.25 | 일부 발화 "−15% 이내" 더 보수적 |
| 7 | 52주 신저가 +30% 이상 | (close - 52W low) / 52W low ≥ 0.30 | (확인) |
| 8 | RS Rating ≥ 70 (희망 80+) | IBD RS Rating | IBD 미사용 시 자체 계산 필요 |

## 3. VCP Pattern

| 요소 | 책 본문 정의 |
|---|---|
| 베이스 길이 | 7주~수개월 (≥ 25 거래일) |
| 수축 단계 | 2~6단계 |
| 각 단계 진폭 | 직전 단계의 50% 이내로 좁아짐 |
| 거래량 dry-up | 수축 단계 일평균 거래량 < 베이스 시작 시점 직전 20일 평균 |
| 피벗 포인트 | 베이스 직전 고점 |
| 돌파 트리거 | 종가 > 피벗 + RVOL ≥ 1.5x |

## 4. RS 자체 계산

### 방식 1 (IBD 근사)
RS_raw = 0.40 × R(12W) + 0.20 × R(26W) + 0.20 × R(39W) + 0.20 × R(52W)
→ universe 전체에서 백분위 (0~99). RS ≥ 70 → 통과.

### 방식 2 (단순)
RS_raw = R(12W) → universe 백분위. 1차 구현 채택.

### 한국 시장 RS 기준 종목 풀
- universe = top_volume:50 일봉 평균 거래대금 상위 50.
- 백분위는 universe 내부 비교 (시장 전체 미사용).

## 5. 청산 룰

| Variant | sl | tp | trail | mh | 출처 |
|---|---|---|---|---|---|
| A (책 의도) | 7~8% (책 stop) | 2~3R (=14~24%) | 50 MA 이탈 | 35거래일 | 책 본문 / 인터뷰 |
| B (책간 획일) | 8% | 12% | (없음) | 20거래일 | 분봉 sl3/tp5/mh120 일봉 환산 |

### Variant A 본 plan 구현
- sl = 0.08
- tp = 0.20 (≈ 2.5R)
- trail = 50일 MA 이탈 (종가 < MA50)
- mh = 35 (max_hold_bars)

### Variant B
- sl = 0.08
- tp = 0.12
- trail = 없음
- mh = 20

## 6. 셋업 카탈로그

| # | 셋업 | 코드화 | 비고 |
|---|---|---|---|
| 1 | Trend Template 통과 (스크리너) | O | 8조건 |
| 2 | VCP 베이스 + 피벗 돌파 | O | 본 plan 핵심 |
| 3 | Power Play (90일 +100% 후 3~6주 횡보) | △ | 표본 부족 가능 |
| 4 | 3주 Tight Closes (3주 변동폭 ≤ 1.5%) | O | 보조 셋업 |
| 5 | Pocket Pivot (50 MA 위 거래량 폭증) | △ | 거래량 정의 필요 |
| 6 | Episodic Pivot (어닝 갭 + RVOL) | X | 분기 발표 데이터 필요 |
| 7 | Earnings Gap | X | 동상 |
| 8 | Industry Group Leader | X | 섹터 분류 없음 |
| 9 | Volume Dry-Up + Tightness | O | VCP 부분집합 |
| 10 | Stage 2 Uptrend (Weinstein 기반) | O | TT 1~5 부분집합 |

본 plan 코드화 대상: 1, 2, 4, 9 (단독 + AND 조합).

## 7. 한국 시장 적용 시 주의점

## 8. 참고 자료
