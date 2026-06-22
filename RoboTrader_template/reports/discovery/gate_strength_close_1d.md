# 게이트 리포트 — strength_close_1d

- 사양: 강세마감 익일보유. mh=0 → 시가→익일시가 1거래일(최소 실현가능 보유).
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -82.4% · Sharpe -1.10 · MaxDD 83.6% · 거래 2450 · 신호 2854

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-82.4% sharpe=-1.10 trades=2450 |
| G3 | ❌ FAIL | corr=0.11 lift=2.26 ΔSharpe=-0.056 |
| G4_walkforward | ❌ FAIL | pos=1/11 worst=-40.1% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.768 |
| G4_cost | ❌ FAIL | slip30bp pnl=-99.2% |
| G5_perturb | ❌ FAIL | pnls=-83.0%,-71.3%,-82.4%,-72.2%,-37.9% |
| G5_oos | ❌ FAIL | train=-1.13 test=-1.29 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
