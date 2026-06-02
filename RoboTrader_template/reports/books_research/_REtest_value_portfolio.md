# 가치/퀀트 책 재검증 — 정기 리밸런싱 N종목 포트폴리오 (공정 재검)

> 작성: 2026-06-02 · 배경: `_FIDELITY_AUDIT_SUMMARY.md` 발견1 (보유종목수·한정자본 포트폴리오 미모델).
> 가치/퀀트 5책은 원문이 **N종목 균등분산 + 정기 리밸런싱 + 장기보유** 포트폴리오인데
> 기존 백테스트(`run_*.py` / `book_backtester`)는 **종목별 독립계좌 sl/tp/mh 단타**로 검증되어
> per-stock 평균이 보고됐다. 본 재검은 그 갭을 메운다 — **진짜 한정자본·max-K·정기 리밸런싱·균등비중 포트폴리오**.

---

## 사용한 모델

### 5책(리밸런싱형) — **신규 드라이버** `scripts/book_rebalance_multiverse.py`
- portfolio_engine.py(ComposableStrategy/PIT 트랙)는 이 5책의 rules.py 인터페이스와 별개 프레임워크라 부적합 → **최소 리밸런싱 시뮬 신규 작성**.
- **부품은 각 책 `scripts/run_<book>.py`의 함수를 그대로 import 재사용**(로직 무중복): `_load_fundamentals_universe`·`_load_daily_adj`·`_load_fundamentals_timeseries`·`_build_fund_by_idx`·`_build_cross_sectional_ranks`. → PIT 105d lag·no-lookahead 횡단면 순위 산정이 기존 백테스트와 **동일**.
- **포트폴리오 모델**: 거래일 합집합 단일 NAV 루프. 매 리밸런싱일(주기 스윕) primary rank 오름차순 정렬 → 상위 K 균등비중 목표 → 이탈 종목 다음봉 시가 매도, 신규 종목 다음봉 시가 매수(현재 equity/K 슬롯). 다음 리밸런싱까지 홀딩. 한정자본 1천만, 왕복비용 0.41%(commission 0.015%×2 + tax 0.18% + slippage 0.1%×2), 결정적(rank tie → code asc).
- **primary rank**: greenblatt=magic(EY+ROC rank합), oshaughnessy=vc(4팩터 백분위), moon=vc(5팩터), hong=hong(소형주20%∩게이트∩4선복합). **Lynch**=횡단면 rank 부재(절대 스크린)→garp_combo 스크린 통과=적격, PER asc tie-break.
- **스윕**: 리밸주기 {quarterly, annual} × K {10, 20, 30}. 기간 2021-01-01~2026-05-29(1238~1241 거래일, 분기 22회/연 6회 리밸). 국면 분해는 기존 `regime_label_5y.parquet`(KOSPI rolling 20d ±2%) 재사용.

### dino(시그널형) — **기존** `scripts/book_portfolio_multiverse.py` (재사용)
- 디노는 회전 시그널형(10~20종목 분산 + +10% 회전익절)이라 리밸런싱형 부적합 → 기존 시그널-진입 포트폴리오 도구로 K 스윕.
- 책 의도 반영: **surge:100 유니버스**(급등이력+중소형, 대형주풀 아님), rule=pullback_rebound(variant B), exit sl5/tp10/mh20, K{5,10,20}, max_per_stock 200만, 한정자본 1천만.

---

## 책별 결과 (전구간 best 조합)

| 책 | best (주기/K) | n_reb | 거래 | CAGR | Sharpe | MaxDD | Calmar | BULL Sh | SIDE Sh | BEAR Sh |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **greenblatt_magic** | quarterly/30 | 22 | 136 | **+5.79%** | **0.366** | 38.0% | 0.15 | 1.49 | 0.69 | -1.88 |
| **oshaughnessy_value** | annual/20 | 6 | 92 | +3.09% | 0.256 | 40.6% | 0.08 | 1.84 | 0.71 | -2.10 |
| **moonbyungro_metric** | quarterly/20 | 22 | 134 | +3.13% | 0.253 | 40.2% | 0.08 | 1.87 | 0.70 | -2.17 |
| **lynch_one_up** | quarterly/20 | 22 | 25 | +0.72% | 0.147 | **10.2%** | 0.07 | 0.32 | **1.45** | -1.65 |
| **hongyongchan** | quarterly/10 | 22 | 53 | -0.22% | 0.098 | 41.0% | -0.01 | 1.18 | **1.16** | -2.06 |
| **dino_surge** (시그널) | K=10 (surge:100) | — | 70 | +0.37%/yr* | 0.091 | 16.6% | 0.12 | — | — | — |

\* dino: 전구간 PnL +2.04%(CAGR 환산 ≈+0.37%/yr), max_concurrent 5~6(신호제한적이라 K≥5 비결속). 국면분해는 시그널 도구 미산출.

### K·주기 민감도 (요지)
- **greenblatt**: K↑가 단조 개선(quarterly K10 0.066 → K20 0.144 → **K30 0.366**). 분산효과 명확, 넓을수록 좋다.
- **moon/osh**: **K20이 최적**(K10은 음수 Sharpe·MaxDD 50%+로 붕괴, K30은 희석). 중간 분산 sweet-spot.
- **hong**: K↑가 MaxDD를 41%→16%로 강하게 낮추나 Sharpe도 0.098→0.036으로 동반 하락(거래 53건 고정=신호 희소). quarterly만 양(annual 전부 음수).
- **lynch**: quarterly K20 최적(Sharpe 0.147, MaxDD 10%). annual 전멸(음수). 표본 희소(25거래).
- **공통**: **quarterly > annual** (annual은 대부분 음수 Sharpe — 연1회는 진입 타이밍 분산 부족). primary rank 신호가 적은 책일수록 K가 포화.

---

## per-stock 단타 대비 판정 변화

| 책 | per-stock(기존) | portfolio(재검) best Sharpe | 판정 변화 | 약세장 견고성 |
|---|---|--:|---|---|
| greenblatt | per-trade +4.88%/Sh~(붕괴군) | **0.366** | **개선폭 최대** — 포트폴리오 Sharpe가 펀더멘털 붕괴군(0.1)을 넘어 0.37로 상승. 그래도 Elder 0.68 미달 | BEAR Sh -1.88 (전책 음수) |
| oshaughnessy | per-trade +4.63%(low_psr) | 0.256 | 소폭 개선(0.1대→0.26) | BEAR -2.10 |
| moonbyungro | +13.68%/Sharpe 0.09(per-stock) | 0.253 | 개선(0.09→0.25), but BULL 의존 | BEAR -2.17 |
| hongyongchan | +12.87%/Sharpe 0.11(per-stock) | 0.098 | **개선 없음/오히려↓** — 신호 희소(53거래)로 분산 불충분 | BEAR -2.06 |
| lynch | per-trade +2.84%(value_bs) | 0.147 | 소폭 개선 + **MaxDD 10%·SIDE Sharpe 1.45 신규 발견** | BEAR -1.65(최선) |
| dino | per-stock Sharpe 0.078~0.092 | 0.091 | **불변** — 포트폴리오로 굴려도 0.09. 신호제한(max 5~6 동시보유)으로 분산효과 없음 | (저DD 16.6%는 유지) |

### 핵심 결론
1. **판정이 근본적으로 바뀐 책은 없다 — 전부 여전히 CANDIDATE 부적격.** 포트폴리오 모델로 공정 재검 시 Sharpe가 0.1대→0.25~0.37로 **개선되긴 했으나**(분산효과 실재), 어느 책도 채택 기준(추세추종 Elder 0.68 / Minervini 0.64) 근처에 못 미친다. 즉 **"포트폴리오 미모델이 가치책을 부당하게 죽였다"는 가설은 기각** — 모델을 갖춰도 약한 알파는 약하다.
2. **약세장(BEAR) 견고성: 6책 전부 BEAR Sharpe 음수**(-1.65 ~ -2.38). 가치/퀀트 분산 포트폴리오는 약세장 방어가 안 된다(Elder ema_pullback A의 BEAR +3.01% 방어와 정반대). lynch가 -1.65로 그나마 덜 나쁘고 MaxDD도 10%로 최저지만 양(+)은 아님.
3. **개선폭 1위 = greenblatt(quarterly K30 Sharpe 0.366, CAGR +5.79%)** — 넓은 분산(K30)에서 EY+ROC 랭킹이 BULL(1.49)+SIDE(0.69) 양수. 가치/퀀트 5책 중 유일하게 "portfolio로 보면 그래도 쓸만함" 후보지만 BEAR 음수·Calmar 0.15로 단독 채택은 부적격.
4. **moon/osh = K20 sweet-spot**(0.25), BULL Sharpe 1.8대로 강하나 SIDE 0.7·BEAR 음수 = 폭등장 베타. **hong은 포트폴리오로도 개선 안 됨**(신호 희소).
5. **dino: 불변(0.09)** — surge:100 유니버스·+10% 회전으로 굴려도 신호가 동시 5~6종목만 채워 K 분산이 결속되지 않음. 책의 "10~20종목 회전" 효과는 신호 빈도 부족으로 미실현(audit_g2의 "23/50종목만 거래·자본활용률 극히 낮음" 자인과 일치).

---

## 산출물·재현
- 드라이버: `scripts/book_rebalance_multiverse.py`(신규) · `scripts/book_portfolio_multiverse.py`(dino, 기존 재사용).
- TSV(전 조합): `reports/books_research/_rebalance_tmp/<book>/` 및 실행시 `--out`(본 재검은 `D:/tmp/rebal/<book>/`).
- 재현(예): `python scripts/book_rebalance_multiverse.py --book greenblatt_magic --freqs quarterly,annual --K-list 10 20 30 --start 2021-01-01 --end 2026-05-29`
- no-lookahead(PIT 105d lag, df.iloc[:i+1] rank)·결정성(rank tie→code asc) 유지. 다른 책 폴더·전략 로직 무수정.
