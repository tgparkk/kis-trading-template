# 게이트 리포트 — bb_reversion

- 사양: 레포 템플릿 verbatim (미검증 자산 재활용). 라이브는 저변동 섹터 대상이나 게이트는 top50 공통 풀.
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -6.3% · Sharpe -0.14 · MaxDD 11.8% · 거래 377 · 신호 513

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-6.3% sharpe=-0.14 trades=377 |
| G3 | ❌ FAIL | corr=0.10 lift=3.16 ΔSharpe=-0.006 |
| G4_walkforward | ❌ FAIL | pos=5/11 worst=-4.0% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.662 |
| G4_cost | ❌ FAIL | slip30bp pnl=-20.1% |
| G5_perturb | ❌ FAIL | pnls=-10.7%,-7.6%,-6.3%,+3.3%,+3.5% |
| G5_oos | ❌ FAIL | train=-0.21 test=-0.07 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
