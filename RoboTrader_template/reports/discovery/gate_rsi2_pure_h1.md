# 게이트 리포트 — rsi2_pure_h1

- 사양: RSI(2)<10 무필터 — 배치1 corr 0.89=SMA200 필터 가설 직접 검정. 보유=1거래일(시가→익일시가).
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -88.3% · Sharpe 0.34 · MaxDD 96.3% · 거래 4061 · 신호 8613

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-88.3% sharpe=0.34 trades=4061 |
| G3 | ❌ FAIL | corr=0.84 lift=3.83 ΔSharpe=-0.087 |
| G4_walkforward | ❌ FAIL | pos=1/11 worst=-38.0% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-1.468 |
| G4_cost | ❌ FAIL | slip30bp pnl=-99.5% |
| G5_perturb | ❌ FAIL | pnls=-86.1%,-90.8%,-88.3%,-88.0%,-90.5% |
| G5_oos | ❌ FAIL | train=0.47 test=-1.32 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
