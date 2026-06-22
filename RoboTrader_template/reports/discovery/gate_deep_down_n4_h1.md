# 게이트 리포트 — deep_down_n4_h1

- 사양: 배치3-A: 4일 연속하락 반등, 보유=1거래일, top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -92.6% · Sharpe -0.32 · MaxDD 92.7% · 거래 4673 · 신호 21778
- 거래당 엣지: 그로스 +0.16% · 넷(수수료·세금 차감) -0.28% · 생존선(현물) 0.41% · 월평균 72.1회 · 무비용 PnL +81.3%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-92.6% sharpe=-0.32 trades=4673 월72.1회 |
| G3 | ❌ FAIL | corr=0.83 lift=2.78 ΔSharpe=-0.079 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=1/11 worst=-41.8% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.479 |
| G4_cost | ❌ FAIL | slip30bp pnl=-99.9% |
| G5_perturb | ❌ FAIL | pnls=-89.7%,-85.3%,-92.6%,-95.1%,-89.4% |
| G5_oos | ❌ FAIL | train=-0.27 test=-0.47 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
