# 게이트 리포트 — mean_reversion_ma20

- 사양: 레포 템플릿 verbatim (미검증 자산 재활용).
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL +21.9% · Sharpe 0.37 · MaxDD 22.3% · 거래 514 · 신호 1907

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=+21.9% sharpe=0.37 trades=514 |
| G3 | ❌ FAIL | corr=0.54 lift=3.16 ΔSharpe=+0.001 |
| G4_walkforward | ✅ PASS | pos=8/11 worst=-10.3% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.235 |
| G4_cost | ✅ PASS | slip30bp pnl=+3.9% |
| G5_perturb | ✅ PASS | pnls=+21.8%,+23.4%,+21.9%,+27.8%,+32.2% |
| G5_oos | ✅ PASS | train=0.24 test=0.62 |

**판정: REJECT (G2, G3, G4_bootstrap)**
