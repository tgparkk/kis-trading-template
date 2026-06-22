# 게이트 리포트 — deep_down_n6_h1

- 사양: 배치3-A: 6일 연속하락 반등, 보유=1거래일, top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -89.4% · Sharpe -0.21 · MaxDD 91.5% · 거래 2678 · 신호 5061
- 거래당 엣지: 그로스 +0.06% · 넷(수수료·세금 차감) -0.36% · 생존선(현물) 0.41% · 월평균 41.3회 · 무비용 PnL +13.4%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-89.4% sharpe=-0.21 trades=2678 월41.3회 |
| G3 | ❌ FAIL | corr=0.89 lift=3.46 ΔSharpe=-0.080 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=0/11 worst=-33.2% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.796 |
| G4_cost | ❌ FAIL | slip30bp pnl=-99.7% |
| G5_perturb | ❌ FAIL | pnls=-92.6%,-95.1%,-89.4%,-63.1%,-18.7% |
| G5_oos | ❌ FAIL | train=0.06 test=-1.44 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
