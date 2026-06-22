# 게이트 리포트 — confluence_n4vol2_h2

- 사양: 배치3-C: 4일 연속하락 AND 거래량 ≥2×20일평균 (조건 중첩), 보유=2거래일, top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -11.8% · Sharpe -0.23 · MaxDD 18.1% · 거래 651 · 신호 888
- 거래당 엣지: 그로스 +0.21% · 넷(수수료·세금 차감) -0.20% · 생존선(현물) 0.41% · 월평균 10.0회 · 무비용 PnL +13.6%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-11.8% sharpe=-0.23 trades=651 월10.0회 |
| G3 | ❌ FAIL | corr=0.07 lift=2.33 ΔSharpe=-0.009 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=5/11 worst=-8.0% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.793 |
| G4_cost | ❌ FAIL | slip30bp pnl=-36.3% |
| G5_perturb | ❌ FAIL | pnls=-36.0%,-24.0%,-11.8%,-2.2%,-0.5% |
| G5_oos | ❌ FAIL | train=-0.35 test=-0.02 |

**판정: REJECT(현물) but ★ETF 조건부 후보 — 그로스 엣지 +0.21%/거래 ∈ [0.2%, 0.5%) (거래세 면제 상품 재검 대상). FAIL: G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos**
