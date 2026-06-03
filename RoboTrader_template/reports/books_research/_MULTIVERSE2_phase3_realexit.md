# 2차 멀티버스 Phase 3 — 진입필터 2건 실청산(트레일링) 재검 (2026-06-03)

> Phase 2(단순 sl/tp 드라이버)에서 강건해 보인 진입필터 2건이 **라이브 실청산(트레일/추세반전)에서도 유지되는지** 검증. 필터 로직은 `scripts/entry_filters.py` 재사용. ★라이브 전략 무수정. 윈도우 2021H2/2022/2024H2/BULL/FULL.

## ① Book15 ma5_pullback + ma_slope — 실청산(MA5 트레일), K=3
신규 측정 하네스 `scripts/multiverse3_real_exit.py`(MA5 트레일 청산 + 필터). ma5는 별도 정본 실청산 드라이버가 없어 이 하네스가 실청산 근사.

| 윈도우 | none Sharpe/PnL/MaxDD | ma_slope Sharpe/PnL/MaxDD | 판정 |
|---|---|---|---|
| 2021H2 | −1.07/−17%/26% | −0.24/−5%/16% | 개선 |
| 2022 | −0.96/−36%/38% | **+0.06/−2%/18%** | 손실·MaxDD 급감 |
| 2024H2 | −0.81/−19%/21% | **+0.76/+8%/9%** | **양수 전환** |
| BULL | +0.88/−8.5%/88% | +0.57/+0.3%/55% | Sharpe↓·PnL↑·MaxDD 반토막 |
| FULL | +0.10/**−99.6%**/99.8% | +0.38/**−87.5%**/98% | ⚠️ 둘 다 전소 |

→ **ma_slope 필터는 실청산에서도 약세장 방어를 명확히 개선**(드로다운 대폭↓, 2024H2 양수전환, 거래 ~50%↓). **★단 ma5 자체는 FULL 5.4년서 필터 있어도 −87% 전소** — 필터는 국면별 방어를 만들지만 ma5 장기 생존성은 못 살림. 필터는 유효, 전략은 여전히 약함.

## ② Elder + mkt_rs — ★정본 실청산 `portfolio_sim_elder.py`(EMA13트레일+ema65반전), K=20
★직전 시도(별도 하네스, BULL MaxDD98.5% 충실도 실패) 폐기 후 **정본 드라이버 자체를 확장**(`--entry-filter`, gate=None시 바이트동일, no-lookahead·회귀 테스트 19 passed).

**충실도 검증 통과**: baseline(none) K=20 = BULL Sharpe **3.877**(정본 3.88), FULL Sharpe **1.024**/+**86.9%**/MaxDD **22.9%**(정본 1.02/+87%/23%) 일치. 정본 청산 그대로 살아있음 확인.

| 윈도우 | Sharpe none→mkt_rs (d) | PnL none→mkt_rs | MaxDD | 거래 |
|---|---|---|---|---|
| 2021H2 | 1.21→1.43 (+0.22) | +4.65%→+5.55% | 3.7→3.0% | 44→39 |
| 2022(BEAR) | −1.27→−1.19 (+0.09) | −13.7%→−11.9% | 15.0→13.5% | 135→119 |
| 2024H2 | −0.94→−1.29 (**−0.35**) | −3.4%→−4.3% | 7.0→7.6% | 53→53 |
| BULL | 3.88→3.80 (−0.08) | **+72.8%→+58.7%** | 6.8→5.1% | 119→87 |
| FULL | 1.02→0.93 (−0.10) | **+86.9%→+59.8%** | 22.9→22.6% | 830→669 |

→ **mkt_rs는 Elder를 개선하지 않음 = 라이브 비권고.** 약세장(2022) 미미 개선(+1.82%p, 여전 음수) vs **BULL −14%p·FULL −27%p 대폭 악화**. Elder 정본 청산이 이미 자기방어하므로 mkt_rs 진입게이트는 상승장 진입만 깎아 순손해. **Phase 2 "전 윈도우 개선"은 단순드라이버 착시 — 정본 실청산서 소멸/역전.**

## ★Phase 3 결론
- **ma5 + ma_slope = 실청산 검증 통과(방어 필터로 유효)** — 단 ma5 전략 자체 장기 전소는 별개(필터로 미해결).
- **Elder + mkt_rs = 기각** — 단순드라이버 착시, 정본 실청산서 BULL/FULL 악화. **재검이 라이브 오적용을 막음.**

## ★★2차 멀티버스 전체(Phase 1+2+3) 최종 결론
1. **확정 수익 레버 = Elder K 5→20** (Phase 1, 라이브 적용·커밋 완료). 유일하게 Sharpe·수익·MaxDD 동시 순개선.
2. **ma5 + ma_slope = 유효한 약세장 방어 필터**(실청산 통과) — 단 ma5 장기 생존성 별개 문제. 라이브 적용은 "ma5를 계속 쓸지" 판단과 함께.
3. **Elder + mkt_rs = 기각**(실청산 착시). RS랭크·진입 임계값 재튜닝도 무익.
4. **교훈**: 단순 sl/tp 드라이버의 필터 개선은 **반드시 정본 실청산으로 재검**해야 함(Elder+mkt_rs가 그 함정의 표본). 충실도 검증(baseline=정본 anchor 일치)이 필수 가드레일.

## 산출물·도구
- `scripts/portfolio_sim_elder.py`(+`--entry-filter`), `scripts/multiverse3_real_exit.py`, `scripts/_run_elder_mkt_rs_sweep.py`, 테스트 `tests/regime/test_portfolio_sim_elder_mkt_rs.py`·`test_multiverse3_real_exit.py`.
- TSV: `D:/tmp/multiverse3_elder/elder_mkt_rs_K20.tsv`, `D:/tmp/multiverse3/realexit_book_pullback_ma5_K3.tsv`.
