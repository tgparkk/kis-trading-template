# 게이트 리포트 — deep_mr_dev15

- 사양: 배치3-B: MA20 -15% 깊은 이탈, 청산=MA회복(sl7/tp12/mh7), top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL +24.0% · Sharpe 0.31 · MaxDD 28.1% · 거래 700 · 신호 4968
- 거래당 엣지: 그로스 +0.77% · 넷(수수료·세금 차감) +0.37% · 생존선(현물) 0.41% · 월평균 10.8회 · 무비용 PnL +50.3%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=+24.0% sharpe=0.31 trades=700 월10.8회 |
| G3 | ❌ FAIL | corr=0.66 lift=3.16 ΔSharpe=-0.003 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ✅ PASS | pos=7/11 worst=-11.8% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.282 |
| G4_cost | ❌ FAIL | slip30bp pnl=-6.7% |
| G5_perturb | ✅ PASS | pnls=+1.1%,+20.1%,+24.0%,+26.1%,+30.5% |
| G5_oos | ✅ PASS | train=0.42 test=0.06 |

**판정: REJECT (G2, G3, G4_bootstrap, G4_cost)**
