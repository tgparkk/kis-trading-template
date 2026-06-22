# 게이트 리포트 — turn_of_month_h1

- 사양: 월말월초 효과 (published TOM). 섭동=윈도우 내 진입 오프셋(전부 양수 기대). 캘린더는 주말+공휴일 라이브러리 근사(임시휴장 미반영 가능). 보유=1거래일(시가→익일시가).
- 측정: top_volume:50 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -3.7% · Sharpe 0.07 · MaxDD 29.9% · 거래 295 · 신호 2911

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-3.7% sharpe=0.07 trades=295 |
| G3 | ❌ FAIL | corr=0.92 lift=1.01 ΔSharpe=-0.027 |
| G4_walkforward | ❌ FAIL | pos=4/11 worst=-4.1% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.587 |
| G4_cost | ❌ FAIL | slip30bp pnl=-14.4% |
| G5_perturb | ❌ FAIL | pnls=-7.2%,-3.7%,-13.0%,-13.4%,-21.9% |
| G5_oos | ❌ FAIL | train=0.14 test=-0.35 |

**판정: REJECT (G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos)**
