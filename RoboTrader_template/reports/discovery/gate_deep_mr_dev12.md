# 게이트 리포트 — deep_mr_dev12

- 사양: 배치3-B: MA20 -12% 깊은 이탈, 청산=MA회복(sl7/tp12/mh7), top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL +1.1% · Sharpe 0.21 · MaxDD 53.4% · 거래 1004 · 신호 9390
- 거래당 엣지: 그로스 +0.43% · 넷(수수료·세금 차감) +0.03% · 생존선(현물) 0.41% · 월평균 15.5회 · 무비용 PnL +39.5%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=+1.1% sharpe=0.21 trades=1004 월15.5회 |
| G3 | ❌ FAIL | corr=0.92 lift=3.83 ΔSharpe=-0.039 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=7/11 worst=-15.6% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.441 |
| G4_cost | ❌ FAIL | slip30bp pnl=-37.1% |
| G5_perturb | ❌ FAIL | pnls=-15.6%,-1.5%,+1.1%,+7.7%,+18.5% |
| G5_oos | ❌ FAIL | train=0.27 test=-0.02 |

**판정: REJECT(현물) but ★ETF 조건부 후보 — 그로스 엣지 +0.43%/거래 ∈ [0.2%, 0.5%) (거래세 면제 상품 재검 대상). FAIL: G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos**
