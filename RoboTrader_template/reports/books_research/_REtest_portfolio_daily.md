# 일봉 책전략 — 한정자본 포트폴리오(max-K) 재검증

> 2026-06-02 · 드라이버 `scripts/book_portfolio_multiverse.py` (시그널-진입형 max-K).
> 모델: 한정자본 1천만 · 종목당 한도 300만 · 유니버스 top_volume:50 · workers 6 · no-lookahead/결정성 유지.
> 전구간 = 2021-01-01 ~ 2026-05-27. 국면 = BULL(2025-06-01~2026-05-27) / SIDE(2023-01-01~2024-12-31) / BEAR(2022-01-01~2022-12-31).
> exit 그리드 sl/tp/mh, entry 그리드는 룰 핵심필드 2~3개. K-list 3 5 10 20.
> ※ 이 모델은 종목당독립계좌 룰엣지(book_param)와 달리 **슬롯 경합·현금부족 skip·turnover 우선순위**가 반영되어 K가 결과를 바꾼다(book_param 평균과 다른 측정치).

---

## 책별 best 조합 (전구간 정렬: sharpe desc, pnl desc)

| 책 | 대표룰 | best (K, 청산) | 전구간 Sharpe/PnL | maxdd | hit | ntr |
|---|---|---|---|---:|---:|---:|
| **daytrading_3methods** (유지윤) | breakout_prev_high | **K=3** · hw20 vm2.0 · sl0.10/tp0.08/mh20 | **0.495 / +100.2%** | 46.25% | 53.8% | 290 |
| **trading_legends** | ma5_pullback | **K=3** · sp0.20 tt0.03 · sl0.05/tp0.15/mh20 | **0.407 / +62.7%** | 73.0% | 36.0% | 382 |
| **raschke_street_smarts** | holy_grail | (전 조합 음수) · best K=3 sl0.05/tp0.08/mh10 | **0.208 / −30.4%** | 72.0% | — | 204 |

> 비고
> - daytrading/legends 의 전구간 sharpe 최상위는 sl0.05/tp0.15 류로 maxdd 100%(계좌소멸) 조합이 sharpe만 근소 우위인 착시가 있어, **maxdd<0.80 sane 필터** 적용 best 를 채택(legends). daytrading best(K=3)는 sharpe·pnl 동시 최상이며 maxdd 46%로 건전.
> - raschke holy_grail 은 **128 조합 전부 PnL 음수**(최대 PnL −30.4%), sharpe 상위조합조차 maxdd 99.8%로 계좌소멸. 분봉(장중) 풀백룰을 일봉에 올린 구조적 부적합. 국면분할 불필요.

---

## K 결속 (max-K 민감도)

| 책 | best per-K (sharpe / pnl / maxdd) | K 결속 |
|---|---|---|
| daytrading_3methods | K3: 0.495/+100%/46% · K5: 0.437/−14%/100% · K10·K20: 0.437/−26%/100% | **강함** — K=3만 건전·양수. K≥5는 패자 롱테일로 희석되어 maxdd 100% 소멸 |
| trading_legends | K3: 0.407/+63%/73% · K5: 0.436/+57%/100% · K10: +57%/100% · K20: +50%/100% | **강함** — K=3만 maxdd<100%. K≥5는 PnL 양수라도 100% 소멸 경로 |
| raschke_street_smarts | 전 K 음수 (best K3 −30%) | N/A (전멸) |

핵심: 두 생존책 모두 **K=3 집중**에서만 건전. top_volume:50 대형주풀에서 진입신호가 희소하고(skip 대량) 승자가 소수 종목에 집중되므로, 슬롯을 늘리면(K↑) 한계 진입이 패자 위주가 되어 maxdd가 100%(계좌소멸)로 붕괴. = book_param의 "종목당 평균엣지"가 양수라도 포트폴리오 한정자본에선 **분산도(K)에 극도로 민감**(Elder 포트폴리오 K민감성과 동일 패턴).

---

## 국면 분할 (best 조합, K=3)

| 책 | BULL Sharpe/PnL | SIDE Sharpe/PnL | BEAR Sharpe/PnL |
|---|---|---|---|
| daytrading_3methods | 0.795 / +34.1% | 0.081 / −1.9% | −0.315 / −15.7% |
| trading_legends | 1.130 / +92.2% | −0.433 / −36.7% | 0.511 / +11.6% |
| raschke_street_smarts | (전멸 — 국면분할 생략) | | |

해석:
- **daytrading_3methods (돌파 타법)**: 전형적 **BULL 전용 추세추종** — BULL 강세(0.795/+34%), SIDE 무수익(−1.9%), BEAR 손실(−15.7%). 전구간 +100% PnL은 사실상 BULL 기여.
- **trading_legends (ma5 눌림목)**: BULL 압도(1.13/+92%) + 의외로 **BEAR 양수(+11.6%)** 인데 **SIDE에서 −36.7% 붕괴**. 약세장보다 횡보장이 독. 전구간 +63%도 BULL 집중. (book_param 국면노트의 "ma5_pullback B = BULL 청산 의존·BEAR exit −4.19%"와 일관 — 여기선 max-K 슬롯 경합이 BEAR 진입거래를 BULL까지 끌고가 +11.6%로 보이나 SIDE 노출이 상쇄.)

---

## 스킵 / 룰 미구현

| 책 | 사유 |
|---|---|
| **weinstein_stages** | **스킵 (거래 0)** — 룰(ma30w_bounce 등)이 ctx 주입 주봉 시리즈(ma30w_series/stage_series/mrs_series)를 요구하나, 이 드라이버의 `_precompute_signals`는 평이한 `generate_signal(code, window, tf)`만 호출 → ctx 미주입 → 전 룰 `triggered=False`. 스모크(2024 full, K=5) **n_trades=0** 확인. 주봉 ctx 의존 구조라 max-K 일봉드라이버 부적합(과제 지시 "주봉 variant 거래0이면 스킵"). |
| **oneil_canslim** | **룰 미구현** — `strategies/books/oneil_canslim/`에 `rules.py` 없음(RULES_RESEARCH.md만). 코드화된 매수룰 부재로 백테스트 불가. |

---

## 판정 변화 (기존 book_param/리포트 대비)

| 책 | 기존 결론 | max-K 재검 | 변화? |
|---|---|---|---|
| daytrading_3methods | breakout_prev_high B = CANDIDATE 부적격 (종목당 Sharpe 0.17) | 포트폴리오 K=3 Sharpe **0.495**·+100% (BULL 전용) | **수치 상향 but 판정 불변** — BULL 의존·BEAR 음수·K=3 외 소멸로 강건성 부족. 여전히 부적격. |
| trading_legends | ma5_pullback B = 부적격 (신규알파 아님, BULL 의존) | 포트폴리오 K=3 Sharpe 0.407·+63%, **BEAR +11.6%** but **SIDE −37%**·maxdd 73% | **판정 불변** — SIDE 붕괴·고maxdd·K=3 외 소멸. 기존 "BULL 의존·강건성 약함" 재확인. |
| raschke_street_smarts | (일봉 미검증) | 전 조합 PnL 음수 (최대 −30%) | **신규 확정: 일봉 부적합** — holy_grail은 분봉(장중) 풀백룰, 일봉 환원 시 전멸. |

---

## 산출물 (TSV)
- `D:/tmp/rebal_remain/daytrading_3methods/book_portfolio_daytrading_3methods_breakout_prev_high.tsv` (288 조합)
- `D:/tmp/rebal_remain/trading_legends/book_portfolio_trading_legends_ma5_pullback.tsv` (192 조합)
- `D:/tmp/rebal_remain/raschke_street_smarts/book_portfolio_raschke_street_smarts_holy_grail.tsv` (128 조합)
- 국면: 각 책 `reg_{BULL,SIDE,BEAR}/` 하위 TSV.
