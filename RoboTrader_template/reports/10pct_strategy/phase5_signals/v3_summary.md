# Phase 5 v3 — OBV+VWAP Swing Portfolio Walk-Forward (1-page)

생성: 2026-05-26 (직원 #9)

---

## 1. v3 재설계 핵심

| 항목 | v2 (직원 #6/#7) | v3 (직원 #9) |
|------|----------------|--------------|
| Universe | ROE Q4+ ∩ phase2a swing_pool top-3 (표본 붕괴) | mcap top 500 + tv 5d median > 10억 |
| Signal | OBV / VWAP / OBV_OR_VWAP x regime split | 동일 (regime 분리 제거) |
| Exit | SL[-1.5~-5%] TP[3~15%] TM[1~60]d | SL[-5,-7,-10%] TP[3,5,10%] TM[1,3,5]d |
| 평가 | trade-level mean + IS/OOS cut | trade-level + portfolio 5포지션 sim |
| Walk-forward | 252/63 x 6 windows | 252/63 x 16 windows (단독 동일) |

---

## 2. 합격 셀 / Family 분포

- 전체 grid: 81 cells (3 family x 3 SL x 3 TP x 3 TM)
- 합격 게이트: mean>0 AND IS>0 AND OOS>0 AND sharpe>0.3 AND n_is/n_oos>=10
- 합격 셀: **0 / 81** (전 family 게이트 미통과)

Family별 합격: OBV=0, VWAP=0, OBV_OR_VWAP=0

Top cell (합격 없음 — mean_pnl 최상위 선택):

| family | sl | tp | tm | mean_pnl | sharpe | n |
|--------|----|----|----|----------|--------|---|
| OBV | -10% | +10% | 5d | -0.248% | -0.56 | 55,094 |
| VWAP | -10% | +10% | 5d | +0.590% | 1.36 | 39,021 |
| OBV_OR_VWAP | -10% | +10% | 5d | +0.054% | 0.12 | 86,798 |

---

## 3. Cross-section vs Trade-level 정합성

- 단독 OBV cross-section: +172.36bps (5/25 walk-forward, 16/16 양수)
- v3 OBV trade-level: -24.8bps (회수율 -14.4%)
- 단독 검증 = "OBV signal 종목군 평균 - 비신호군 평균" (alpha 방향 측정)
- v3 = "T+1 시가 진입 → SL/TP/TM exit, fee 0.3% 편도" (실전 매매 시뮬)
- 회수율 음수 = SL이 1d 이내 빈번 발동 → cross-section alpha 전액 소멸 + 추가 손실
- VWAP trade-level +0.59% 양수이나 IS 분봉 기간(2025-02 이후) 제약으로 게이트 미통과

---

## 4. 월별 PnL (1차 vs v3)

> v3_monthly_pnl.csv 누적 equity는 전기간 합산 설계 제약으로 의미 없음.
> 아래 수치는 WF window별 독립 portfolio 시뮬 monthly_mean 평균 (신뢰 수치).

| 지표 | 1차 (P3) | v3 |
|------|----------|----|
| 월평균 (WF window별) | +0.23% | **-4.37%** |
| 양수 윈도우 | 3/6 (50%) | 2/16 (12.5%) |
| Sharpe (연환산) | 0.38 | -3.64 |
| MDD (WF window 누적) | -6.55% | -48.25% |
| 합격 셀 | - | 0 / 81 |

---

## 5. 목표 10% 진척률

- 1차: +0.23% / 10% = 2.3%
- v3: -4.37% / 10% = **-43.7%** (역방향)

---

## 6. Walk-Forward 16 윈도우 OOS

양수 윈도우: 2 / 16 (12.5%)

| W | Test 기간 | n_sig | n_acc | monthly_mean | sharpe | mdd |
|---|----------|-------|-------|--------------|--------|-----|
| 1 | 2022-01-03~2022-03-30 | 2,796 | 101 | -6.87% | -1.78 | -3.56% |
| 2 | 2022-03-31~2022-06-27 | 3,598 | 97 | -1.24% | -0.38 | -21.50% |
| 3 | 2022-06-28~2022-09-22 | 3,216 | 100 | -10.55% | -4.69 | -19.23% |
| 4 | 2022-09-23~2022-12-20 | 3,306 | 105 | -8.97% | -3.18 | -21.58% |
| 5 | 2022-12-21~2023-03-17 | 3,252 | 91 | +0.62% | 0.40 | -7.75% |
| 6 | 2023-03-20~2023-06-14 | 4,540 | 93 | -2.72% | -0.81 | -19.77% |
| 7 | 2023-06-15~2023-09-11 | 3,636 | 99 | -4.21% | -1.84 | -21.88% |
| 8 | 2023-09-12~2023-12-07 | 2,378 | 94 | -4.92% | -9.41 | -16.50% |
| 9 | 2023-12-08~2024-03-05 | 3,202 | 96 | -3.07% | -1.29 | -20.63% |
| 10 | 2024-03-06~2024-05-31 | 6,254 | 95 | -4.60% | -1.65 | -17.63% |
| 11 | 2024-06-03~2024-08-28 | 6,268 | 99 | -13.12% | -6.35 | -35.45% |
| 12 | 2024-08-29~2024-11-25 | 4,116 | 94 | +4.53% | 12.47 | 0.00% |
| 13 | 2024-11-26~2025-02-20 | 5,534 | 81 | -3.79% | -2.23 | -18.06% |
| 14 | 2025-02-21~2025-05-20 | 10,605 | 87 | -6.66% | -2.65 | -25.66% |
| 15 | 2025-05-21~2025-08-15 | 24,415 | 84 | -2.45% | -2.46 | -11.13% |
| 16 | 2025-08-18~2025-11-12 | 22,977 | 88 | -1.87% | -2.13 | -4.55% |

---

## 7. 판정: 최종 종결

현재 알파(OBV+VWAP)로 월 10% 도달 불가. Phase 5 v3 종결.

근거:
1. 합격 셀 0/81
2. WF window 월평균 -4.37% (1차 +0.23% 대비 -4.60%p 악화)
3. 양수 WF 2/16 (12.5%) — 구조적 음수 편향
4. Sharpe -3.64

핵심 원인 사슬:
- OBV cross-section alpha +172bps (신호 방향 맞음)
- SL[-5%] intraday 빈번 발동 → trade-level -24.8bps
- portfolio FIFO 5포지션 선택 시 음수 trade 랜덤 진입
- VWAP 단독 +0.59% 양수이나 IS 기간 부족 (분봉 2025-02 이후만)
- 결론: 신호 방향은 맞으나 exit rule이 alpha를 완전 소멸

---

## 8. 다음 단계 권고

| 우선순위 | 항목 | 근거 |
|---------|------|------|
| P1 | VWAP 단독 paper 5영업일 시뮬 | trade-level +0.59% 유일 양수 |
| P2 | OBV exit 재설계 (ATR-based adaptive SL) | 고정 SL이 intraday noise에 피격 |
| P3 | 분봉 2023~2024 추가 백필 | VWAP IS 샘플 확보 |
| P4 | OBV_OR_VWAP 폐기 | OBV 음수 dominate |
| P5 | 외부 시그널 탐색 (외국인순매수, 공매도비율) | 현 alpha 한계 도달 |

---

## 9. 산출물

- scripts/10pct_strategy/p5_obv_swing_walkforward.py (신설)
- reports/10pct_strategy/phase5_signals/v3_grid_all.csv (81 cells)
- reports/10pct_strategy/phase5_signals/v3_walkforward.csv (16 windows)
- reports/10pct_strategy/phase5_signals/v3_monthly_pnl.csv (47 months, 설계 제약)
- reports/10pct_strategy/phase5_signals/v3_summary.md (이 파일)

## 10. 제약 / 한계

- VWAP: 분봉 2025-02 이후만 → IS window 대부분 n_is<10 → 게이트 미통과
- Portfolio sim: 전기간 합산 equity 음수 전락 (WF window별 독립값이 신뢰 수치)
- OBV SL 발동: 1d intraday low -5% 이상 종목 다수 → 즉시 청산 편향
