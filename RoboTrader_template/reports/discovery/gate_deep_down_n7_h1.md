# 게이트 리포트 — deep_down_n7_h1

- 사양: 배치3-A: 7일 연속하락 반등, 보유=1거래일, top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -63.1% · Sharpe -0.00 · MaxDD 74.5% · 거래 1723 · 신호 2471
- 거래당 엣지: 그로스 +0.03% · 넷(수수료·세금 차감) -0.38% · 생존선(현물) 0.41% · 월평균 26.6회 · 무비용 PnL +3.8%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-63.1% sharpe=-0.00 trades=1723 월26.6회 |
| G3 | ❌ FAIL | corr=0.92 lift=3.16 ΔSharpe=-0.069 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=0/11 worst=-26.3% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.336 |
| G4_cost | ❌ FAIL | slip30bp pnl=-96.4% |
| G5_perturb | ❌ FAIL | pnls=-95.1%,-89.4%,-63.1%,-18.7%,-7.8% |
| G5_oos | ❌ FAIL | train=0.16 test=-1.22 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
