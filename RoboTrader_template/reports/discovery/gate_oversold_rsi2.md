# 게이트 리포트 — oversold_rsi2

- 사양: Connors RSI-2 verbatim. 청산=SMA5 회복(+mh20 가드), 손익절 없음(사양).
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL +14.8% · Sharpe 0.23 · MaxDD 25.5% · 거래 761 · 신호 2796

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=+14.8% sharpe=0.23 trades=761 |
| G3 | ❌ FAIL | corr=0.89 lift=4.36 ΔSharpe=-0.015 |
| G4_walkforward | ❌ FAIL | pos=6/11 worst=-10.8% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.180 |
| G4_cost | ❌ FAIL | slip30bp pnl=-12.9% |
| G5_perturb | ✅ PASS | pnls=+7.3%,+6.8%,+14.8%,+21.5%,+19.2% |
| G5_oos | ✅ PASS | train=0.29 test=0.04 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost)**
