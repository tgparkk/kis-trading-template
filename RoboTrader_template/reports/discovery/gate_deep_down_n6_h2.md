# 게이트 리포트 — deep_down_n6_h2

- 사양: 배치3-A: 6일 연속하락 반등, 보유=2거래일, top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -51.6% · Sharpe -0.24 · MaxDD 55.5% · 거래 1710 · 신호 5061
- 거래당 엣지: 그로스 +0.11% · 넷(수수료·세금 차감) -0.30% · 생존선(현물) 0.41% · 월평균 26.4회 · 무비용 PnL +15.2%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-51.6% sharpe=-0.24 trades=1710 월26.4회 |
| G3 | ❌ FAIL | corr=0.87 lift=3.53 ΔSharpe=-0.056 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=4/11 worst=-16.6% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.144 |
| G4_cost | ❌ FAIL | slip30bp pnl=-87.1% |
| G5_perturb | ❌ FAIL | pnls=-26.4%,-90.3%,-51.6%,-44.9%,-8.3% |
| G5_oos | ❌ FAIL | train=0.02 test=-1.13 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
