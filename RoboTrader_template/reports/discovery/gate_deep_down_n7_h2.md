# 게이트 리포트 — deep_down_n7_h2

- 사양: 배치3-A: 7일 연속하락 반등, 보유=2거래일, top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -44.9% · Sharpe -0.03 · MaxDD 61.3% · 거래 1065 · 신호 2471
- 거래당 엣지: 그로스 -0.03% · 넷(수수료·세금 차감) -0.44% · 생존선(현물) 0.41% · 월평균 16.4회 · 무비용 PnL -3.5%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-44.9% sharpe=-0.03 trades=1065 월16.4회 |
| G3 | ❌ FAIL | corr=0.92 lift=3.31 ΔSharpe=-0.058 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=2/11 worst=-16.5% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.065 |
| G4_cost | ❌ FAIL | slip30bp pnl=-80.3% |
| G5_perturb | ❌ FAIL | pnls=-90.3%,-51.6%,-44.9%,-8.3%,-6.3% |
| G5_oos | ❌ FAIL | train=0.11 test=-0.89 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
