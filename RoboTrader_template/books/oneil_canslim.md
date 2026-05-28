# 책 4: William O'Neil — How to Make Money in Stocks (CAN SLIM)

> 카테고리: 스윙·중기 (일봉 + 재무 + RS)  
> 데이터 입도: 일봉 + 분기 재무 + 자체 RS Rating  
> Phase A+B 완료: 2026-05-29  
> 상세 자료: [백테스트 결과](../reports/books_research/oneil_canslim/) · [조사 원본](../strategies/books/oneil_canslim/RULES_RESEARCH.md)

## 1. 책 요약

William O'Neil. IBD(Investor's Business Daily) 창립자. 가장 영향력 있는 스윙·중기 매매서 중 하나.

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

## 2. 한국 적용 정량화 매핑

| CAN SLIM | 한국 정량화 | 데이터 소스 |
|---|---|---|
| **C** (분기 EPS YoY ≥ 25%) | `net_income` YoY (financial_statements에 eps 컬럼 없음 → 대체) | financial_statements |
| **A** (ROE ≥ 17%) | financial_statements.roe (% 단위) | financial_statements |
| **L** (RS Rating ≥ 80) | 자체 계산: 2×(P/P_63) + P/P_126 + P/P_189 + P/P_252 → 백분위 | daily_prices 252일 |
| **M** (시장 상승) | KOSPI 200일 MA 위 + 우상향 | daily_candles KS11 |
| N/S/I | Phase A에서 미적용 (RS와 M으로 대체) | — |

## 3. Phase A 결과 (스크리너 — C+A+L+M 단순 매수)

**데이터 한계**:
- quant_factors 가용 기간 **38거래일** (2025-12-08 ~ 2026-02-03)
- financial_statements.eps 컬럼 없어 net_income으로 C 요소 근사
- 교집합 종목 68개 → 스크리너 통과 18~5종목

**두 가지 임계값 버전**:

| 버전 | 임계값 | 통과 종목 | 거래수 | 평균 PnL | 승률 | 수익:손실 |
|---|---|---|---|---|---|---|
| 엄격 | mom≥75, NI_YoY≥25%, ROE≥17% | 5 | 5 | -1.43% | 20.0% | 2.96 |
| **완화** | **mom≥50, NI_YoY≥0%, ROE≥10%** | **18** | **18** | **+4.84%** | **50.0%** | **2.25** |

**관찰**:
- 엄격 버전 5건은 통계 무의미
- 완화 버전 18건: 평균 +4.84%, 손익비 2.25 — 방향성 양호
- M 필터: 38일 전부 BULL → 약세장 미검증

## 4. Phase B 결과 (스크리너 + 차트 패턴)

**패턴 코드화**:
- **평평한 베이스**: 직전 25일 가격 범위 ≤ 20% + 50일 MA 위 + 다음 봉 베이스 고점 돌파
- **컵핸들 단순화**: 직전 60일 U/V 형성 (깊이 10~40%) + 핸들 10일 (범위 ≤ 15%) + 핸들 컵 상단 절반 + 핸들 고점 돌파

**완화 스크리너 + 완화 패턴 적용**:

| 메트릭 | 값 |
|---|---|
| 총 거래 | 7 |
| 승률 | **71.4%** (5/7) |
| 평균 PnL | **+7.04%** |
| 중간값 PnL | +2.46% |
| 누적 PnL | **+49.26%** |
| 평균 보유일 | 5.7일 |
| 평균 수익 (승) | +12.76% |
| 평균 손실 (패) | -7.28% |
| 수익:손실 | 1.75 |

**패턴별**: cup_handle 5건 / flat_base 2건  
**청산 사유**: end_of_data 3 / stop_loss 2 / take_profit 2

## 5. Phase A vs Phase B 비교

| Phase | 거래 | 승률 | 평균 PnL | 수익:손실 | 누적 |
|---|---|---|---|---|---|
| A (완화) | 18 | 50.0% | +4.84% | 2.25 | +87.12% |
| **B (스크리너+패턴)** | **7** | **71.4%** | **+7.04%** | 1.75 | +49.26% |

**관찰**:
- 패턴 추가로 거래 18→7 (필터링 효과)
- 승률 50%→71% (정밀도 ↑)
- 평균 PnL +4.84%→+7.04% (개선)
- 단, 표본 7건은 매우 작음 — 통계 의미 한정

## 6. 책 4권 베스트 비교

| 책 | 데이터 | 베스트 | 평균 PnL | 평균 Sharpe | 표본 |
|---|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | -0.11 | 32T |
| Bellafiore | 분봉 | **fade_vwap** | +1.74% | **+0.37** | 964T |
| Raschke | 분봉 | **anti** | +10.24% | -2.27 | 1,860T |
| **O'Neil** | **일봉+재무+RS** | **CANSLIM+패턴** | **+7.04%** | (미계산) | **7T** |

**O'Neil의 특징**:
- 표본 7건은 책 중 가장 적음 (분봉 책들은 수백~수천 건)
- 평균 PnL +7.04% / 거래는 일봉 책 통틀어 매력적
- **데이터 기간 38일 한계**로 통계 신뢰도 가장 낮음
- 보유 평균 5.7일 → 다른 책(intraday)과 보유 단위 완전 다름

## 7. 한국 시장 적용성 — 결론

> **방향성 양호하지만 통계 미흡 — paper trading + 더 긴 데이터로 재검증 필요**

- CANSLIM 펀더+RS+M 필터: 38일 동안 18종목 통과, 평균 +4.84% / 승률 50%
- 패턴 추가 (Phase B): 7건 / 승률 71% / 평균 +7.04%
- 손익비 1.75~2.25 — CANSLIM 원칙 (손절 -7%/익절 +20%) 의 자기실현 효과
- 한국 시장에서 한국형 RS Rating 계산 가능 (252일 가중 백분위)
- 한국형 분배일 / 팔로스루 데이 (M 정밀) 미적용 — 추후 보완

## 8. 한계점

- **데이터 기간 38일** (2025-12 ~ 2026-02) — 본격 검증 불가능
- **financial_statements.eps 컬럼 없음** → net_income YoY로 대체 (C 요소 근사화)
- **약세장 미검증** — 분석 기간 전부 BULL (M=PASS)
- **N/S/I 요소 미적용** — 52주 신고가, 거래량 폭증, 기관 보유 데이터 한계
- **패턴 인식 단순화** — 컵핸들/평평한 베이스 가격 통계만, 거래량 패턴 미반영
- **표본 7~18건** — 통계 신뢰도 매우 낮음
- **Sharpe 계산 안 함** — 일봉 표본 단순 평균만, 분봉 가정과 비교 불가

## 9. 다음 검증 단계

1. **데이터 기간 확장**: quant_factors 백필 또는 financial_statements.eps 컬럼 추가
2. **약세장 포함 백테스트**: KOSPI BULL/BEAR/SIDEWAYS 모두 포함 기간
3. **N/S/I 요소 추가**: 52주 신고가 / 거래량 폭증 / 외국인+기관 순매수
4. **패턴 인식 정밀화**: 거래량 패턴 + 핸들 위치 / 컵 시간 형태
5. **paper trading 1~3개월**: 실시간 신호 추적
6. **CANSLIM은 CANDIDATE_ALPHAS 미등록** — 표본 너무 적어 후보 자격 미달. 데이터 확장 후 재평가

## 10. 산출물

| 종류 | 경로 |
|---|---|
| 코드 (스크리너) | `scripts/canslim_screener.py` |
| 코드 (Phase A 백테스트) | `scripts/canslim_backtest.py` |
| 코드 (Phase B 패턴) | `scripts/canslim_pattern_backtest.py` |
| 조사 원본 | `strategies/books/oneil_canslim/RULES_RESEARCH.md` |
| Phase A 결과 | `reports/books_research/oneil_canslim/canslim_phase_a_trades.parquet` |
| Phase B 결과 | `reports/books_research/oneil_canslim/canslim_phase_b_trades.parquet` |
| 스크리너 결과 | `reports/books_research/oneil_canslim/screener_daily*.parquet` |
