# 책 4: William O'Neil — How to Make Money in Stocks (CAN SLIM)

> 카테고리: 스윙·중기 (일봉 + 재무 + RS)  
> 데이터 입도: 일봉 + 분기 재무 + 자체 RS  
> 조사 완료: 2026-05-29  
> 코드화: 진행 예정  
> 조사 원본: [strategies/books/oneil_canslim/RULES_RESEARCH.md](../strategies/books/oneil_canslim/RULES_RESEARCH.md)

## 1. 책 요약

William O'Neil. IBD(Investor's Business Daily) 창립자. 가장 영향력 있는 스윙 매매서 중 하나.

CAN SLIM 시스템 = **펀더멘털 7요소 필터** + **차트 패턴 진입**.

| 요소 | 정의 |
|---|---|
| C | 분기 EPS YoY ≥ 25% |
| A | 3~5년 연간 EPS 25%+, ROE 17%+ |
| N | 52주 신고가 ±10% |
| S | 거래량 돌파 시 50%+ |
| L | RS Rating ≥ 80 |
| I | 기관 보유 매집 |
| M | 시장 상승추세 |

이전 책들(아지즈/Bellafiore/Raschke 분봉)과 데이터 요구 매우 다름 — 일봉 + 분기재무 + 시장지수.

## 2. 10개 셋업·룰

### 펀더 + 시장 필터 (3개)
- CAN SLIM 스크리너 (C+A+L+M)
- 시장 방향 + 팔로스루 데이
- 8주 보유 / 피라미딩 / 클라이맥스 매도 (보조 룰)

### 차트 패턴 (5개)
- 컵핸들 (Cup with Handle)
- 평평한 베이스 (Flat Base)
- 더블 바텀 (W 패턴)
- 상승 베이스 (Ascending Base)
- 베이스 온 베이스

상세: [RULES_RESEARCH.md](../strategies/books/oneil_canslim/RULES_RESEARCH.md)

## 3. 이전 책들과 비교

| 항목 | 아지즈 | Bellafiore | Raschke | **O'Neil** |
|---|---|---|---|---|
| 데이터 | 분봉 | 분봉 | 분봉+일봉 | **일봉+재무+RS** |
| 보유 | intraday | intraday | 1~수일 | **수주~수개월** |
| 필터 | 패턴 | RVOL | ADX/Stoch | **펀더+RS+시장** |
| 한국 적용 난이도 | 쉬움 | 쉬움 | 중간 | **복잡 — 재무/시장 데이터 필요** |

## 4. 한국 적용 데이터 요구사항

- ✅ daily_prices / daily_candles 일봉 OHLCV
- ✅ financial_statements 분기 EPS, ROE
- ✅ KOSPI 일봉 (KS11) 시장 방향
- ⚠️ 기관 보유 — 외국인+기관 순매수로 대안 (foreign_flow 등)
- ⚠️ 분기 시기차 — 1Q 5월 공시, 2Q 8월 등 (PIT-safe 주의)

## 5. 진행 계획

### Phase A — CAN SLIM 스크리너 (펀더+RS+시장)
- C/A/L/M 4요소 정량 스크리너
- 일별 통과 종목 리스트 생성
- 백테스트: 통과 종목을 다음 봉 시가 매수, -7% 손절 / +20% 익절 / 40일 max_hold

### Phase B — 차트 패턴 추가
- 평평한 베이스 + 컵핸들 단순화
- 스크리너 통과 종목 + 패턴 충족 시만 진입

### Phase C — 통합 + 리포트
- A vs B PnL 비교
- KOSPI 분배일·팔로스루 필터 효과

예상 시간: A 1시간, B 1.5시간, C 30분 = 총 3시간

## 6. 산출물 (현재까지)

| 종류 | 경로 |
|---|---|
| 조사 원본 | `strategies/books/oneil_canslim/RULES_RESEARCH.md` |
| 코드 | 진행 예정 |
| 백테스트 결과 | 진행 예정 |
