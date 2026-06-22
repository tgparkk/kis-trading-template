# 게이트 리포트 — deep_down_n5_h1

- 사양: 배치3-A: 5일 연속하락 반등, 보유=1거래일, top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -95.1% · Sharpe -0.45 · MaxDD 95.6% · 거래 3545 · 신호 10475
- 거래당 엣지: 그로스 +0.05% · 넷(수수료·세금 차감) -0.35% · 생존선(현물) 0.41% · 월평균 54.7회 · 무비용 PnL +19.2%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-95.1% sharpe=-0.45 trades=3545 월54.7회 |
| G3 | ❌ FAIL | corr=0.85 lift=3.01 ΔSharpe=-0.080 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=1/11 worst=-53.1% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.823 |
| G4_cost | ❌ FAIL | slip30bp pnl=-99.9% |
| G5_perturb | ❌ FAIL | pnls=-85.3%,-92.6%,-95.1%,-89.4%,-63.1% |
| G5_oos | ❌ FAIL | train=-0.20 test=-1.29 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
