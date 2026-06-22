# 게이트 리포트 — deep_mr_dev20

- 사양: 배치3-B: MA20 -20% 깊은 이탈, 청산=MA회복(sl7/tp12/mh7), top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL +51.8% · Sharpe 0.73 · MaxDD 16.2% · 거래 390 · 신호 1607
- 거래당 엣지: 그로스 +1.81% · 넷(수수료·세금 차감) +1.38% · 생존선(현물) 0.41% · 월평균 6.0회 · 무비용 PnL +67.6%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=+51.8% sharpe=0.73 trades=390 월6.0회 |
| G3 | ✅ PASS | corr=0.45 lift=3.31 ΔSharpe=+0.025 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ✅ PASS | pos=8/11 worst=-4.8% |
| G4_bootstrap | ✅ PASS | sharpe_p05=+0.218 |
| G4_cost | ✅ PASS | slip30bp pnl=+39.5% |
| G5_perturb | ✅ PASS | pnls=+19.0%,+30.5%,+51.8%,+46.7%,+34.2% |
| G5_oos | ✅ PASS | train=0.93 test=0.30 |

**판정: REJECT (G2)**
