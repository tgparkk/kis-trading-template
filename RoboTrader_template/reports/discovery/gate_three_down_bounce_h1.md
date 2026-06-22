# 게이트 리포트 — three_down_bounce_h1

- 사양: Connors 연속하락 반등 verbatim (n=3). 섭동=연속일수 1~5. 보유=1거래일(시가→익일시가).
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -75.3% · Sharpe 0.43 · MaxDD 99.8% · 거래 3905 · 신호 7086

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-75.3% sharpe=0.43 trades=3905 |
| G3 | ❌ FAIL | corr=0.81 lift=3.61 ΔSharpe=-0.082 |
| G4_walkforward | ❌ FAIL | pos=3/11 worst=-40.8% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.221 |
| G4_cost | ❌ FAIL | slip30bp pnl=-99.4% |
| G5_perturb | ❌ FAIL | pnls=-90.8%,-90.7%,-75.3%,-55.1%,-11.4% |
| G5_oos | ❌ FAIL | train=0.54 test=-0.33 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
