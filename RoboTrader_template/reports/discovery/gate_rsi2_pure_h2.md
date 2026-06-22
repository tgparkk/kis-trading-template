# 게이트 리포트 — rsi2_pure_h2

- 사양: RSI(2)<10 무필터 — 배치1 corr 0.89=SMA200 필터 가설 직접 검정. 보유=2거래일.
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -26.9% · Sharpe 0.07 · MaxDD 50.4% · 거래 2469 · 신호 8613

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-26.9% sharpe=0.07 trades=2469 |
| G3 | ❌ FAIL | corr=0.93 lift=3.91 ΔSharpe=-0.051 |
| G4_walkforward | ❌ FAIL | pos=4/11 worst=-12.3% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.685 |
| G4_cost | ❌ FAIL | slip30bp pnl=-90.4% |
| G5_perturb | ❌ FAIL | pnls=-26.2%,-35.4%,-26.9%,-15.3%,-35.5% |
| G5_oos | ❌ FAIL | train=0.19 test=-0.54 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
