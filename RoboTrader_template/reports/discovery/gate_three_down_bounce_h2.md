# 게이트 리포트 — three_down_bounce_h2

- 사양: Connors 연속하락 반등 verbatim (n=3). 섭동=연속일수 1~5. 보유=2거래일.
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -47.7% · Sharpe -0.02 · MaxDD 62.7% · 거래 2417 · 신호 7086

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-47.7% sharpe=-0.02 trades=2417 |
| G3 | ❌ FAIL | corr=0.92 lift=4.06 ΔSharpe=-0.060 |
| G4_walkforward | ❌ FAIL | pos=4/11 worst=-20.1% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.942 |
| G4_cost | ❌ FAIL | slip30bp pnl=-91.4% |
| G5_perturb | ❌ FAIL | pnls=-32.0%,-17.7%,-47.7%,-26.7%,-11.5% |
| G5_oos | ❌ FAIL | train=0.09 test=-0.51 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
