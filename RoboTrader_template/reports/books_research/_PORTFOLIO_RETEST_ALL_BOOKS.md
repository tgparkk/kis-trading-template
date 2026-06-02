# 전 책 한정자본 포트폴리오 멀티버스 재검 — 종합 (2026-06-02)

모든 기구현 책 전략을 **한정자본(1천만)·종목당한도(300만)·최대보유 K** 포트폴리오 모델 위에서 4축(매수후보=진입룰·보유종목수 K·매수타이밍·매도타이밍 sl/tp/mh) 멀티버스로 재검. 드라이버: `scripts/book_portfolio_multiverse.py`(시그널-진입형 max-K)·`scripts/book_rebalance_multiverse.py`(정기리밸 N종목)·`scripts/portfolio_sim_elder.py`(Elder). 상세: `_REtest_*.md`, `_FIDELITY_AUDIT_SUMMARY.md`.

## 종합 매트릭스 (best 조합 기준)
| 책/전략 | 모델 | best K | 전구간 Sharpe / PnL | MaxDD | 국면(BULL/SIDE/BEAR) | 판정 |
|---|---|---|---|---|---|---|
| **Elder ema_pullback** | max-K(시그널) | **K↑좋음(20)** | 0.68 / +93%(K20) | **23%** | BEAR **+3%** 방어 | ✅ **채택(유일 강건)** |
| **systrader79 배분** | 연속비중 | (배분) | 0.93(월) | 19% | MDD방어 | ✅ 채택(방어형) |
| haru daily ma20_pullback | max-K | K=3 | 0.58 / +133% | 45% | (BULL추정) | ❌ 고MaxDD·K3한정 |
| 유지윤 daytrading | max-K | K=3 | 0.50 / +100% | 46% | 0.80/0.08/**−0.32** | ❌ BULL전용 |
| close_betting(taesso) | max-K | K=3 | 0.49 / +15% | 9% | BULL단독(0.93/−0.03/−0.04) | ❌ 비강건 |
| trading_legends | max-K | K=3 | 0.41 / +63% | 73% | 1.13/**−0.43**/0.51 | ❌ SIDE붕괴 |
| greenblatt | 리밸 N | K=30 | 0.37 / CAGR+5.8% | — | 1.49/0.69/**−1.88** | ❌ BEAR무방비 |
| oshaughnessy | 리밸 N | K=20 | 0.26 | — | 1.84/0.71/−2.10 | ❌ |
| moonbyungro | 리밸 N | K=20 | 0.25 | — | 1.87/0.70/−2.17 | ❌ |
| Minervini dryup | max-K | **K=3만** | 0.39(K5)~ | K↑전소 | BEAR음수 | ⚠️ K=3 권고(라이브 5→3) |
| lynch | 리밸 N | K=20 | 0.15 | — | 0.32/1.45/−1.65 | ❌ |
| hongyongchan | 리밸 N | K=10 | 0.10 | — | (신호희소) | ❌ |
| dino | max-K | K비결속 | 0.09 | — | (신호희소) | ❌ |
| **분봉군 (전멸)** | | | | | | |
| bellafiore fade_vwap | max-K(분) | K=5 | mSharpe1.70 / **mPnl+1.8%** | — | pos2/3, 2026-05 **−45%** | ❌ 비강건 |
| surge_fade(taesso) | max-K(분) | — | mPnl **−24~−32%** | — | pos1~2/3 OVERFIT | ❌ |
| aziz | max-K(분) | K=5/10 | mPnl **−35%** | — | pos1/3 OVERFIT | ❌ |
| raschke(일봉) | max-K | — | **−30%** | — | 전멸 | ❌ 일봉부적합 |
| **스킵** | | | | | | |
| weinstein | — | — | 거래0(주봉 ctx 미주입) | | | 미평가 |
| oneil | — | — | rules.py 없음 | | | 미구현 |

## ★3대 결론
1. **K=3 집중이 거의 전부의 시그널-진입 책에서 유일 건전** — top_volume:50 대형주풀은 진입신호가 희소(skip 대량)해 K를 늘리면 한계진입이 패자 위주 → **K≥5에서 MaxDD≈100% 계좌소멸**. **유일한 예외 = Elder**(신호 품질·분산성이 높아 K↑일수록 좋아짐 = 진짜 분산 가능한 전략). Minervini도 capacity 작아 K=3만 생존(라이브 max_positions 5→3 반영함).
2. **강건성(약세장 방어)은 Elder·systrader79만** — 나머지 전부 BEAR Sharpe 음수 또는 BULL/특정국면 단독. 포트폴리오 모델링이 가치책 Sharpe를 per-stock ~0.1→0.25~0.37로 끌어올렸으나(분산효과 실재 = per-stock 테스트는 불공정했음), **채택바(0.68)·약세장 방어 모두 미달**.
3. **분봉 단타군 전멸 재확인** — bellafiore fade_vwap만 pos2/3로 근접하나 한 국면 −45%로 비강건, 나머지 음수·OVERFIT.

## 순수익 (이번 재검의 의의)
- **방법론 결함 교정**: 기존 책 백테스트 대부분이 "종목별 독립 단타 평균"(보유종목수·한정자본 미모델)이었음을 발견하고, **신규 포트폴리오/리밸런싱 멀티버스로 전 책을 공정 재검**. 결론은 대체로 불변(부적격은 부적격)이나, 이제 **한정자본·K·강건성 기준으로 확정**됨.
- **실거래 액션**: Minervini `max_positions` 5→3(반영 완료). Elder는 K↑ 견고(현 max5는 보수적, 확대 여지).
- **남는 과제**: weinstein 주봉 ctx 주입 평가, oneil rule 구현, BEAR 방어 진입게이트(전 단타책 공통 약점).
