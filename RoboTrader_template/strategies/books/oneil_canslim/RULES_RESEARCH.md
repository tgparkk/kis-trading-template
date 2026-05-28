# William O'Neil — How to Make Money in Stocks (CAN SLIM): 매매 셋업 조사

> 조사일: 2026-05-29
> 출처: 하단 URL 목록

## 요약

William O'Neil의 CAN SLIM 시스템은 펀더멘털 필터(7요소) + 차트 패턴 진입의 결합. 분기 EPS 25%+/연간 25%+ 성장, RS Rating 80+, 시장 상승추세 확인 후 컵핸들·더블바텀·평평한 베이스 패턴이 완성된 종목의 피벗 포인트(베이스 고점 +0.10)를 거래량 50%+ 증가와 함께 돌파할 때 매수. 손절 -7~-8% 절대 준수, 익절 +20~25%, 초강세 종목(3주 내 +20%)은 8주 보유. "3/4 종목은 시장 방향을 따른다"는 M 요소 가장 중요.

## CAN SLIM 7요소

| 요소 | 정의 | 한국 정량화 |
|------|------|------|
| **C** | 최근 분기 EPS YoY ≥ 25% | financial_statements 분기 EPS |
| **A** | 3~5년 연간 EPS 25%+ 성장, ROE 17%+ | quant_factors |
| **N** | 52주 신고가 또는 ±10% 이내 + 신제품 | daily_prices 252일 max |
| **S** | 유통주식 작음, 돌파 시 거래량 50%+ 증가 | volume z-score |
| **L** | RS Rating ≥ 80 | 자체 RS 계산 (2×3M + 6M + 9M + 12M 가중) |
| **I** | 기관 보유 5~35%, 기관 수 10+ 증가 | 외국인+기관 순매수 (대안) |
| **M** | KOSPI 상승추세, 분배일 ≤ 3일/4주 | KOSPI 200일 MA + 분배일 |

## 셋업·차트 패턴 목록

### 1. CAN SLIM 스크리너 (펀더 필터)
- C: 분기 EPS YoY ≥ 25%
- A: 3년 EPS CAGR ≥ 25%, ROE ≥ 17%
- N: 52주 고가의 90%+ 위치
- L: RS Rating ≥ 80
- M: KOSPI 200일 MA 우상향 + 분배일 ≤ 3/4주
- 손절 -7~-8%, 익절 +20~25%, 보유 8주

### 2. 컵핸들 돌파 (Cup with Handle)
- 컵: 7~65주 기간, 깊이 -12~-33% (U자), 선행 상승 30%+
- 핸들: 4일~4주, 깊이 -10~-15%, 컵 상단 절반 위치, 거래량 감소
- 진입: 핸들 고가 + 0.10원, 거래량 50%+ 증가, 돌파 5% 이내
- 손절 -7%, 익절 +20%, 8주

### 3. 더블 바텀 돌파 (W 패턴)
- 7주+ 기간, 두 번째 저점 < 첫 저점 (살짝)
- 진입: 중간 고점 + 0.10, 거래량 50%+
- 손절 -7%, 익절 +20%

### 4. 평평한 베이스 돌파
- 4~7주 횡보, 깊이 ≤ 15%, 50일 MA 위
- 진입: 베이스 고점 + 0.10, 거래량 50%+

### 5. 상승 베이스 돌파
- 9~16주, 3회 조정 + 3회 신고가 (계단식)
- 진입: 세 번째 조정 고점 + 0.10

### 6. 베이스 온 베이스
- 1차 베이스 돌파 후 +20% 없이 곧바로 2차 베이스
- 진입: 2차 베이스 고점 + 0.10

### 7. 시장 방향 + 팔로스루 데이
- 시장 급락 후 4일째 이후 +1%+ + 거래량 증가 = 팔로스루
- 4~5주 내 분배일 4~6일 → 전체 청산 검토

### 8. 피라미딩
- 1차: 피벗 돌파 시 50%
- 2차: +2~2.5% 시 25%
- 3차: +2% 시 25%
- 평균 매수가 피벗 +5% 이내

### 9. 클라이맥스 런 매도
- 보유 중 최대 일봉 상승, 수주 +20~25%, 갭업+거래량 폭발
- 50일 MA 고거래량 이탈 시 매도
- 4~6 분배일 → 전체 청산

### 10. 8주 보유 룰
- 피벗 돌파 후 3주 내 +20% 시 → 8주 보유 (조기매도 금지)
- 손절 -7~-8% 유지

---

## 한국 시장 적용 시 주의점

1. **RS Rating 자체 계산**: `rs_raw = 2×(P/P_63) + P/P_126 + P/P_189 + P/P_252`, 전 종목 백분위 ≥ 80
2. **분기 EPS YoY**: financial_statements 활용, 분기 시기차 (1Q 5월 공시) 고려
3. **시장 방향**: KOSPI 일봉으로 대체, 팔로스루 1%+ → 0.8~1% 조정 검토
4. **컵핸들 최소 기간**: 7주 → 한국은 5주 가능 (변동성 큼)
5. **거래량 50% 증가**: 소형주에서 빈번한 오신호 → 거래대금 절대 하한선 병행
6. **기관 보유(I)**: 한국 실시간 어려움 → 외국인+기관 순매수 대안 또는 생략
7. **호가 단위**: +0.10달러 → +1 호가 단위 (5,000원대 +5원)
8. **베이스 깊이**: 33% → 한국 소형주 40% 완화 검토
9. **피라미딩 간격**: 2~2.5% → 한국 변동성 큰 종목 3~5%

## 코드화 우선순위 (한국 일봉 기준)

| # | 셋업 | 데이터 | 우선순위 | 비고 |
|---|---|---|---|---|
| 1 | CAN SLIM 스크리너 (C+L+M) | 일봉+재무+RS | ⭐⭐⭐ | 펀더+모멘텀 결합, 시장 필터 |
| 2 | 평평한 베이스 돌파 | 일봉 | ⭐⭐ | 가장 간단한 패턴 |
| 3 | 컵핸들 돌파 (단순화) | 일봉 | ⭐⭐ | 패턴 인식 복잡, U자 검출 |
| 4 | 더블 바텀 돌파 | 일봉 | ⭐ | W 인식 어려움 |
| 5 | 상승 베이스 | 일봉(주봉 환산) | ⭐ | 9~16주 |
| 6 | 베이스 온 베이스 | 일봉 | ⭐ | 1차 돌파 추적 |
| 7 | 시장 방향 + 팔로스루 | KOSPI 일봉 | ⭐⭐ | 필터로 활용 |
| 8 | 피라미딩 | 일봉 | (보조 룰) | 백테스트에 통합 |
| 9 | 클라이맥스 매도 | 일봉 | (보조 룰) | 청산 룰로 통합 |
| 10 | 8주 보유 | 일봉 | (보조 룰) | max_hold_bars=40 |

## 출처 URL 목록

1. https://en.wikipedia.org/wiki/CAN_SLIM
2. https://earningspike.com/canslim-method
3. https://www.chrisperruna.com/2007/01/22/how-to-calculate-a-stocks-pivot-point/
4. https://finance.yahoo.com/news/hard-spot-ascending-gives-launchpad-223600899.html
5. https://medium.com/@socialmedia_96459/selling-right-how-oneil-mastered-selling-4d5b7770119e
6. https://github.com/skyte/relative-strength
7. https://traderlion.com/trading-strategies/the-8-week-hold-rule/
8. https://www.nasdaq.com/articles/how-build-long-term-profits-stocks-take-many-gains-20-25-2017-10-25
9. https://tradingmomentum.substack.com/p/the-canslim-growth-stock-playbook
10. https://corporatefinanceinstitute.com/resources/equities/can-slim/
11. https://www.stockscreening101.com/canslim-shares.html
12. https://kingtrader.net/ascending-bases-stock-chart-pattern-and-real-examples.html
