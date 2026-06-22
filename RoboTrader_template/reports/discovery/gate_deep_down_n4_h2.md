# 게이트 리포트 — deep_down_n4_h2

- 사양: 배치3-A: 4일 연속하락 반등, 보유=2거래일, top300.
- 측정: top_volume:300 · K=5 · 종목당 1,000,000원(라이브 사이징) · 풀기간 연속 백테스트
- base: PnL -26.4% · Sharpe -0.04 · MaxDD 52.4% · 거래 2943 · 신호 21778
- 거래당 엣지: 그로스 +0.31% · 넷(수수료·세금 차감) -0.10% · 생존선(현물) 0.41% · 월평균 45.4회 · 무비용 PnL +87.2%

| 게이트 | 판정 | 상세 |
|---|---|---|
| G2 | ❌ FAIL | pnl=-26.4% sharpe=-0.04 trades=2943 월45.4회 |
| G3 | ❌ FAIL | corr=0.74 lift=3.31 ΔSharpe=-0.038 (corr·lift 참고치 — 단기보유 ΔSharpe 구속) |
| G4_walkforward | ❌ FAIL | pos=5/11 worst=-17.7% |
| G4_bootstrap | ❌ FAIL | sharpe_p05=-0.711 |
| G4_cost | ❌ FAIL | slip30bp pnl=-89.7% |
| G5_perturb | ❌ FAIL | pnls=-32.6%,-12.0%,-26.4%,-90.3%,-51.6% |
| G5_oos | ❌ FAIL | train=0.02 test=-0.20 |

**판정: REJECT(현물) but ★ETF 조건부 후보 — 그로스 엣지 +0.31%/거래 ∈ [0.2%, 0.5%) (거래세 면제 상품 재검 대상). FAIL: G2, G3, G4_walkforward, G4_bootstrap, G4_cost, G5_perturb, G5_oos**
