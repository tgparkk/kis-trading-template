# 게이트 리포트 — turn_of_month_h2

- 사양: 월말월초 효과 (published TOM). 섭동=윈도우 내 진입 오프셋(전부 양수 기대). 캘린더는 주말+공휴일 라이브러리 근사(임시휴장 미반영 가능). 보유=2거래일.
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -5.1% · Sharpe 0.06 · MaxDD 30.3% · 거래 295 · 신호 2911

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-5.1% sharpe=0.06 trades=295 |
| G3 | ❌ FAIL | corr=0.92 lift=1.01 ΔSharpe=-0.028 |
| G4_walkforward | ✅ PASS | pos=7/11 worst=-7.7% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.618 |
| G4_cost | ❌ FAIL | slip30bp pnl=-15.8% |
| G5_perturb | ❌ FAIL | pnls=+0.5%,-5.1%,-14.4%,-23.0%,-12.3% |
| G5_oos | ❌ FAIL | train=0.15 test=-0.48 |

**판정: REJECT (G2, G3, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
