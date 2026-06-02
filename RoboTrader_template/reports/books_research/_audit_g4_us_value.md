# 책 전략 구현 충실도 감사 — G4: 미국 가치/계량 3책

> 감사일: 2026-06-02 · 감사관: 구현 충실도 4축 검증
> 대상: **Greenblatt Magic Formula(Book9)**, **O'Shaughnessy What Works(Book10)**, **Lynch One Up(Book8)**
> 폴더: `reports/books_research/{greenblatt_magic_formula, osullivan_what_works, lynch_one_up}` + `strategies/books/{greenblatt_magic, oshaughnessy_value, lynch_one_up}`
> 백테스트 드라이버: `scripts/run_{greenblatt_magic,oshaughnessy_value,lynch_one_up}.py` (모두 동일 아키텍처)

---

## ★ 핵심 결론 (가치전략의 N종목 분산·랭킹 구현 여부)

**랭킹은 충실히 구현·검증됨. 그러나 가치전략의 본질인 "N종목 균등 분산 포트폴리오"는 구현되지 않았다.**

- **랭킹 ✅**: Greenblatt EY+ROC rank합산, O'Shaughnessy PSR/VC1/Trending 백분위, 모두 거래일별 횡단면 dense-ordinal 순위를 no-lookahead로 precompute하고 `top_n=20` 게이트로 진입 — 원문 메커니즘 충실. (Lynch는 랭킹 아닌 절대 스크린이라 책과 일치.)
- **N종목 분산 ❌ (3책 공통 최대 결함)**: 백테스트는 `simulate_one_stock()` **종목별 독립 시뮬레이션**이다. "rank<=20"에 든 종목은 **각자 따로** 다음봉 시가매수→sl/tp/mh 청산할 뿐, **동시에 정확히 20종목을 균등비중 보유하는 포트폴리오가 없다.** max-K 캡·자본배분·리밸런싱 부재. 즉 "상위 20위 안에 들면 산다"이지 "20종목 균등 포트폴리오를 굴린다"가 아님. 가치전략의 핵심(분산·연 1회 리밸런싱·균등비중)이 측정되지 않았고, 보고 PnL은 종목별 독립거래 per-trade 평균이다.

---

## 책별 4축 표

### Book9 — Greenblatt Magic Formula
| 축 | 판정 | 근거 (1줄) |
|---|---|---|
| 매수후보(유니버스·랭킹) | ⚠️ | 랭킹(EY+ROC rank합산 상위20)은 원문 충실·no-lookahead ✅ / 단 universe가 `financial_statements` DISTINCT(magic:79, **top_volume:50 아님**)이고 금융·유틸 제외 불가(섹터 컬럼 부재)로 Greenblatt 명시 배제조건 미반영 |
| 보유종목수(N분산) | ❌ | top_n=20 게이트만 있고 **포트폴리오 N종목 균등보유·max-K 캡 없음**. 종목별 독립 시뮬 → "20종목 분산" 미구현 |
| 매수타이밍 | ⚠️ | 책=연 1회 리밸런싱 시점 일괄매수 / 구현=rank<=20 진입신호 다음봉 시가매수(상시), **리밸런싱 주기 개념 없음** |
| 매도타이밍 | ❌ | 책=매수 후 ~1년 보유 후 교체(연간 리밸런싱) / 구현=sl/tp/mh(A: sl20/tp99off/mh120, B: sl8/tp12/mh20)로 **1년 보유 철학과 무관한 기술적 청산** |

### Book10 — O'Shaughnessy What Works
| 축 | 판정 | 근거 (1줄) |
|---|---|---|
| 매수후보(유니버스·랭킹) | ⚠️ | PSR/VC1(4팩터)/Trending 백분위 순위 상위20 진입 = 다팩터 랭킹 충실 ✅ / universe `factor:79`(top_volume 아님), 진짜 VC2/VC3(주주수익률·P/CF) 데이터 부재로 대체, Trending은 6개월 모멘텀 불가→3개월로 스펙 이탈 |
| 보유종목수(N분산) | ❌ | 책=각 팩터 상위 50종목 균등 포트폴리오 / 구현=top_n=20 게이트 + **종목별 독립 시뮬, N종목 균등보유 없음** |
| 매수타이밍 | ⚠️ | 책=연 1회 리밸런싱 / 구현=순위진입 상시 다음봉 시가매수, **리밸런싱 주기 없음** |
| 매도타이밍 | ❌ | 책=1년 보유 후 재랭킹 교체 / 구현=sl/tp/mh 기술적 청산 (avg_hold B≈3봉으로 1년 보유와 정반대) |

### Book8 — Lynch One Up
| 축 | 판정 | 근거 (1줄) |
|---|---|---|
| 매수후보(유니버스·스크린) | ⚠️ | PEG·성장·부채 절대 스크린 = 랭킹 아닌 책의 카테고리 스크리닝과 일치 ✅ / universe `fundamentals:131`(top_volume 아님, 사장님 승인), psr·dividend_yield 100% NULL로 자산주·PEGY 룰은 대체 구현(원문 일부 이탈) |
| 보유종목수(N분산) | ❌ | Lynch는 분산 종목수 명시 약함(정성적)이나 구현은 스크린 통과시 종목별 독립 시뮬 → 포트폴리오 개념 자체 부재 |
| 매수타이밍 | ⚠️ | 책=PEG·스토리 기반 상시 매수(fast_grower에 옵션 RSI<50 타이밍 추가) / 진입 다음봉 시가매수는 합리적이나 정성적 스토리·내부자매수 신호 미반영 |
| 매도타이밍 | ❌ | 책=PEG 정상화/스토리 훼손까지 장기 멀티배거 보유 / 구현=sl/tp/mh(B mh20봉) → **멀티배거 보유 철학과 상충**(A의 forced_close 다수가 이를 방증) |

---

## 4축 상세

### ① 매수후보 (유니버스 vs 책 스크리닝/랭킹)
- **랭킹 메커니즘은 정확**: `_build_cross_sectional_ranks`(Greenblatt) 등에서 거래일 D의 데이터만으로 적격종목 수집→팩터별 순위→합산/백분위→dense ordinal `magic_rank/vc_rank/psr_rank` 부여. no-lookahead 가드 명시. 룰(`rule_magic_formula_top` 등)은 `rank<=top_n AND n_eligible>=min_eligible(10)`만 본다. **랭킹 기반 진입은 원문 충실하게 이식됨.**
- **유니버스가 top_volume:50이 아님 — 의도적·정당**: 가치/계량 랭킹은 넓은 풀에서 횡단면 비교가 본질이므로 `financial_statements` DISTINCT(재무 보유 전종목, Greenblatt magic:79/O'Sh factor:79/Lynch 131)를 사용. **랭킹 전략에 top_volume:50을 쓰면 오히려 틀림** → 이 선택은 타당. 단 이전 책들과 책간 PnL 비교성이 깨짐(리포트에 명시됨 ✅).
- **결함**: ①Greenblatt/O'Sh 모두 금융·유틸 섹터 제외 불가(섹터 컬럼 부재) → 원문 명시 배제조건 미반영, 순위 오염 가능. ②절대 임계값 룰(ROC>25% 등)은 미국 캘리브레이션이라 한국 대형주서 0거래(리포트가 정확히 진단). ③6개월 단일 국면(market_cap 창) — 단 다년 재검증(daily_candles 백필, n_dates 124→1241)으로 보완됨.

### ② 보유종목수 (N종목 균등분산 — **3책 공통 최대 결함**)
- **구현 안 됨**: 세 드라이버 모두 `for code in universe: simulate_one_stock(...)` 구조. 각 종목이 자기 시계열에서 독립적으로 "rank<=20일 때 진입→sl/tp/mh 청산"을 반복. **동시 보유 종목수 상한(max-K)도, 종목당 자본배분(균등 1/N)도, 포트폴리오 NAV도 없다.**
- **의미**: 가치전략의 핵심 알파원천(분산 + 정기 리밸런싱으로 평균회귀 수확)이 측정되지 않음. 보고된 per-trade 평균(+4.88% 등)과 집계 universe-mean PnL은 **포트폴리오 수익률이 아니라 독립 거래들의 산술평균**이다. 실제 20종목 균등 포트폴리오의 CAGR/Sharpe/MDD와는 다른 수치 (특히 Sharpe는 포트폴리오 분산효과로 달라짐).
- 참고: 같은 저장소의 systrader79(allocation 트랙)·exit_multiverse(portfolio_sim)는 포트폴리오 모델을 갖췄으나, 이 3책 드라이버는 그 트랙을 쓰지 않음.

### ③ 매수타이밍 (리밸런싱 주기 vs 책)
- 세 책 모두 원문은 **정기(연 1회) 리밸런싱**(Lynch는 덜 기계적)인데, 구현은 **리밸런싱 주기 개념이 없다.** 종목이 top_n 안에 드는 날이면 (미보유 시) 다음봉 시가에 매수. 사실상 "상시 신호 기반 진입"이라 책의 연간 일괄 매수/교체 리듬과 다름. 다음봉 시가체결·슬리피지 0.1%·왕복비용 0.41% 반영은 적절 ✅.

### ④ 매도타이밍 (보유기간/리밸런싱 vs 책)
- **가장 큰 이탈**: 세 책 모두 원문 청산=**~1년 보유 후 재랭킹 교체**(Lynch는 스토리 훼손/PEG 정상화까지 장기보유, 멀티배거 의도). 구현은 **sl/tp/mh 기술적 청산**(Variant A sl20/tp99off/mh120, B sl8/tp12/mh20). 
  - B는 avg_hold ≈3봉(O'Sh)/3봉(Greenblatt)로 **수일 단타**가 되어 가치전략 보유철학과 정반대.
  - A는 tp 사실상 off·mh120이라 forced_close가 지배(Greenblatt A 31/38, Lynch A value 15/34) — 데이터 종료까지 끌고가 buy-and-hold 베타에 가까워짐(리포트가 과대평가 경고 ✅).
  - 즉 "1년 보유 후 리밸런싱"이라는 청산 규칙이 어느 variant로도 구현되지 않음.

---

## 종합 판정

| 책 | ①매수후보 | ②N분산 | ③매수타이밍 | ④매도타이밍 |
|---|---|---|---|---|
| Greenblatt | ⚠️ | ❌ | ⚠️ | ❌ |
| O'Shaughnessy | ⚠️ | ❌ | ⚠️ | ❌ |
| Lynch | ⚠️ | ❌ | ⚠️ | ❌ |

- **랭킹/스크리닝 로직 자체는 충실히 구현·검증**(no-lookahead 횡단면 순위, top_n 게이트). 유니버스를 top_volume:50 대신 재무 보유 전종목으로 둔 것도 랭킹 전략엔 옳은 선택.
- **그러나 가치전략을 가치전략답게 만드는 3요소 — N종목 균등 분산 포트폴리오, 정기 리밸런싱, 1년 보유 청산 — 이 모두 미구현.** 백테스트는 종목별 독립 sl/tp/mh 시뮬이라 사실상 "랭킹 신호를 단타로 트레이딩"한 것에 가깝고, 보고 성과는 포트폴리오 수익률이 아님.
- 세 리포트 모두 6개월·단일국면·universe 단절을 명시하고 CANDIDATE 보류/부적격으로 결론냈으며, 다년 재검증에서 Sharpe 붕괴(0.4→0.1대)를 확인 — **결론(부적격) 자체는 방어적이고 타당.** 단 "포트폴리오 미구현"은 리포트들이 명시적으로 짚지 않은 한계라 본 감사에서 보강.
