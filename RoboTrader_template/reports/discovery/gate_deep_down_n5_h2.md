# 게이트 리포트 — deep_down_n5_h2

- 사양: 배치3-A: 5일 연속하락 반등, 보유=2거래일, top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -90.3% · Sharpe -0.23 · MaxDD 91.2% · 거래 2264 · 신호 10475
- 거래당 엣지: 그로스 -0.10% · 넷(수수료·세금 차감) -0.49% · 생존선(현물) 0.41% · 월평균 34.9회 · 무비용 PnL -23.2%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-90.3% sharpe=-0.23 trades=2264 월34.9회 |
| G3 | ❌ FAIL | corr=0.89 lift=3.38 ΔSharpe=-0.080 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=0/11 worst=-41.1% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.595 |
| G4_cost | ❌ FAIL | slip30bp pnl=-98.3% |
| G5_perturb | ❌ FAIL | pnls=-12.0%,-26.4%,-90.3%,-51.6%,-44.9% |
| G5_oos | ❌ FAIL | train=0.04 test=-1.36 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
