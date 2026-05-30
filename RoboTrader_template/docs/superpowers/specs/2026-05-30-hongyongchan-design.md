# 홍용찬 실전 퀀트투자 — 백테스트 설계서 (Book 12, 한국 저자 2호)

> 조사: WebSearch 기반(아래 §A 참고). 책 실물 미보유 → 공개 자료/서평/블로그 재구성.
> 작성: 2026-05-30 · 한국 시장 특화 **시스템 퀀트**(가치 다팩터 + 소형주 + 성장/마진 게이트).
> 문병로(Book 11)/O'Shaughnessy(Book 10) 횡단면 순위 인프라 재사용. book_id=`hongyongchan_quant`.
> **결정사항(사장님)**: §9 "사장님 결정 필요" 미해결 — 코드화 전 결재 요망(특히 배당 백필 여부·성장팩터 채택 범위).

---

## A. 책 조사 요약 (Book 12)

### A.1 저자·대표작 확정
- **저자**: 홍용찬(洪龍璨). 경희대 경제학과, 2006년부터 증권사 근무한 베테랑. 가치투자+퀀트투자 지향, 2013년부터 "주관적 판단 제거" 시스템 투자로 전환.
- **대표작 확정**: **『실전 퀀트투자』**(이레미디어, 2017, ISBN 9791188279333) — 한국 시장 데이터로 철저히 백테스트한 **퀀트 입문 표준서**. 후속작 『퀀트투자 처음공부』(이레미디어, 2024, 처음공부 시리즈 8).
- **중요 정정**: 의뢰 시 "가치투자 저자"로 예상했으나, 홍용찬은 **정통 가치투자(정성적 기업분석)가 아니라 계량/시스템 퀀트 저자**다. 문병로와 같은 계열(룰 기반 다팩터)이며, V차트/밸류차트류 시그니처 기법은 없다(그건 최준철·김봉수 등 다른 저자). 따라서 본 설계는 "한국 저자 2호 퀀트"로 진행한다.

### A.2 핵심 방법론 (정량 룰로 환원)
홍용찬의 골격은 **"한국 소형주 + 4선 저밸류"** 콤보다(책의 시그니처 전략).

1. **소형주 유니버스**: 시가총액 **하위 20%**(혹은 하위 N분위)로 유니버스 한정. 한국 소형주 프리미엄을 핵심 알파원으로 본다.
2. **4선 저밸류(저평가 4지표 복합)**: **PER + PBR + PCR + PSR** 4개를 각각 분위 순위화해 합산(낮을수록 저평가) → 종합 저밸류 상위 선별. 이게 홍용찬 시그니처 명칭 "4선 저밸류".
3. **성장 게이트**: 매출액·영업이익·순이익의 **전년 대비 성장(YoY)** 양수/상위.
4. **마진·수익성 게이트**: 영업이익률(OPM)·ROE 상위, 흑자(영업이익>0, 순이익>0) 필터.
5. **안전성 게이트**: 부채비율(debt_ratio) 과다 종목 제외.
6. **리밸런싱**: **분기별**(quarterly) 재구성, 종목 수 **20종목** 균등. (계절성 11~4월 한정 버전도 책에서 비교하나 기본은 연중 분기 리밸런싱.)
7. 책 전체는 흑자/적자·매출액·영업이익률·배당·PER·PBR·ROE·ROA·모멘텀을 **각각 단독 백테스트 → 콤보**로 쌓아 올리는 구성(문병로와 동일한 "팩터 단독 검증 → 결합" 서술).

**정량화 가능 부분**: 위 1~6 전부 룰로 환원 가능(분위 순위·게이트·top_n·리밸런싱).
**정성적 부분**: 거의 없음(시스템 퀀트라 정성 판단 배제가 책의 철학). 단 "재무 데이터 신뢰성/회계 이상치 수기 점검" 정도의 실무 코멘트만 정성적.

### A.3 다른 가치/퀀트 책과의 차별점
| 책 | 핵심 축 | 홍용찬과의 차이 |
|----|---------|------------------|
| 문병로(Book 11) | 5팩터(PBR/PER/PSR/POR/PCR) + 저PBR 한국 민감 + 소형주 | 홍용찬은 **POR 대신 4선(PER/PBR/PCR/PSR)** + **성장·마진·부채 게이트를 명시적 결합**. 문병로는 순수 밸류 횡단면, 홍용찬은 **밸류×성장×퀄리티 멀티팩터**. |
| O'Shaughnessy(Book 10) | 미국 다팩터 밸류 + 소형주 | 동일 철학이나 홍용찬은 **한국 데이터 자체 백테스트** + 분기 리밸런싱 + 성장 결합. |
| Greenblatt 마법공식 | EY+ROC 2팩터 | 홍용찬은 밸류 4선 + 퀄리티(ROE/OPM)로 마법공식보다 **밸류 비중↑, 팩터 수↑**. |
| Lynch | PEG·정성 스토리 | 홍용찬은 **정성 완전 배제**, PEG 대신 성장YoY 게이트. |

**백테스트 가치**: 있음. (a) **성장×마진 게이트가 순수 밸류(문병로)보다 우월한지**를 동일 universe·동일 기간으로 직접 대조 가능 → 책간 A/B. (b) "소형주 하위 20%" 게이트 강도(문병로 40% vs 홍용찬 20%) 민감도. (c) **분기 리밸런싱 vs 연 1회(4월)** 효과 — 문병로 4월 게이트와 정면 비교. 차별점이 인프라상 거의 공짜로 측정되므로 가치 높음.

---

## 0. 설계 원칙

1. **다팩터 횡단면 순위 + 소형주 틸트 + 성장/퀄리티 게이트** — 문병로 `run_moonbyungro_metric.py` 복제·확장(85% 재사용). `_build_cross_sectional_ranks`에 4선 밸류·성장·마진 순위 추가, `_build_fund_by_idx`에 roe/opm/debt/net_income/growth 추가.
2. **홍용찬 핵심 명제 검증**: "소형주 + 4선 저밸류 + 성장/마진이 한국에서 초과수익"을 다년 데이터로 직접 검증/반박. 문병로 5팩터(POR 포함)와 **동일 universe·기간**으로 A/B.
3. **4선 밸류 복합**(PER+PBR+PCR+PSR). 전부 DB 직접/재구성 가능(§7 표) — **신규 백필 불필요**(PCR=ocf 백필 완료됨).
4. **소형주 효과** — market_cap 하위 **20%** 게이트(홍용찬 명시값; 문병로 40%보다 타이트). 게이트 강도 변형 측정.
5. **성장·퀄리티 게이트** — 매출/영업이익 YoY 성장(연간 재무 인접연도 차분) + OPM/ROE 상위 + 흑자/부채 필터. **부분 커버리지(roe 68종목/opm 86종목/debt 79종목)라 게이트는 "데이터 있는 종목만 적용 + 없으면 통과 또는 제외" 정책을 사장님 결정으로**(§9).
6. **분기 리밸런싱** — 진입을 분기 시작 영업일에 게이트(옵션 `--quarterly`). 상시 신호 + 분기 게이트 + 4월 게이트 3버전 측정해 비교.
7. PIT 재무조인(105일 lag, `_build_fund_by_idx`), 롱 전용, 거래비용 동일(왕복 0.41%).

---

## Phase 0. 데이터 선행작업 — (조건부) 필요

문병로와 달리 **밸류 4선·소형주는 백필 불필요**(PCR용 ocf 이미 백필 완료: 131종목 전부, 2015+ 약 11개년). 단, 홍용찬 일부 보조 전략에 다음이 걸린다.

| 항목 | 현황 | 백필 필요? | 비고 |
|------|------|-----------|------|
| **배당 전략** | `dividend_yield` 컬럼 존재하나 **0건(완전 공백)** | **사장님 결정 필요** | 홍용찬 책에 "배당" 단독 전략 챕터 있음. 배당 전략을 포함하려면 DART/KIS 배당 백필 선행. **미포함 시 배당 룰 제외하고 진행 가능**. |
| **성장 YoY** | revenue/operating_profit/net_income 존재(연간) | 불필요(재구성) | 인접 연도(report_date 차) 차분으로 YoY 산출. 분기 데이터 없으니 **YoY만**(QoQ 불가). |
| **ROE/OPM/부채** | roe(68종목)/opm(86)/net_margin(86)/debt_ratio(79) 존재, **부분** | 불필요(있는 것만 사용) | 2004~ 초기 위주. 2021+ 백테스트 구간 커버리지는 코드화 1단계에서 재확인 필요(§9). |

> 결론: **밸류 4선 + 소형주 코어는 Phase 0 없이 즉시 코드화 가능**. 배당·풀 성장/퀄리티 게이트는 커버리지/백필 결정에 종속.

---

## 1. 팩터 (가용 컬럼 + 재구성)

```
PER  = per                                     # 직접
PBR  = pbr                                     # 직접 (홍용찬도 저PBR 강조)
PSR  = (market_cap/1e8) / revenue              # 재구성. revenue>0
PCR  = (market_cap/1e8) / operating_cash_flow  # 재구성. ocf>0 가드 + 캡 (백필 완료)
# --- 게이트(보조) ---
ROE  = roe                                     # 직접(부분 커버리지)
OPM  = operating_margin                        # 직접(부분)
DEBT = debt_ratio                              # 직접(부분) — 상한 필터
REV_YoY = revenue_t / revenue_{t-1} - 1        # 재구성(연간 차분)
OP_YoY  = operating_profit_t / operating_profit_{t-1} - 1
흑자 = operating_profit>0 AND net_income>0      # 직접 필터
small_cap = market_cap 오름차순 하위 20%         # 소형주 게이트(홍용찬 명시)
```
- 4선 밸류는 cheap=low. POR/PCR 분모 작을 때 캡(문병로 패턴 PCR_CAP=100 재사용; POR는 본 책 미사용).
- 단위 환산 1e8(원→억원) 필수(market_cap 단위버그 주의 — 문병로와 동일).
- 성장/마진 게이트는 **결측 허용 정책**을 §9 사장님 결정에 따름.

---

## 2. 횡단면 순위 (`_build_cross_sectional_ranks` 확장)

거래일 D마다, **4선 밸류** 모두 유효한 적격 교집합에서:
1. 각 팩터 백분위(cheap=high): `pct_f = 1 - (rank_asc-1)/(N-1)`. (문병로 `_pct_cheap` 재사용)
2. `v4_score = mean(pct_per, pct_pbr, pct_psr, pct_pcr)`.  # 4선 저밸류 복합
3. `v4_rank` = v4_score 내림차순 dense ordinal(1=최저평가).
4. `smallv4_rank`: market_cap **하위 20%** 게이트 → 그 부분집합에서 v4_score 내림차순 dense ordinal. (홍용찬 플래그십)
5. `hong_rank`(멀티팩터): 소형주 하위 20% ∩ 흑자 ∩ (선택)성장YoY>0 부분집합에서 v4_score 내림차순 dense ordinal.
6. `n_eligible` = 4선 적격 수. MIN_ELIGIBLE=10.

주입: `ctx_extra = {"fund":fund_by_idx[i], "v4_rank":..., "smallv4_rank":..., "hong_rank":..., "n_eligible":...}`
- no-lookahead: 거래일 D의 PIT fund(105일 lag) + 당일 market_cap + close[..D]만. (문병로와 동일 검증됨)

---

## 3. 룰 N종 (확정 후보)

### rule_value4_low (시그니처, conf 73, top_n=20, min_eligible=10)
```
v4_rank is not None AND n_eligible>=min_eligible AND v4_rank<=top_n
```
> 홍용찬 "4선 저밸류"(PER+PBR+PCR+PSR) 핵심. 문병로 5팩터(vc_rank) 직접 대조군.

### rule_small_value4 (플래그십, conf 78, top_n=20)
```
smallv4_rank is not None AND smallv4_rank<=top_n
```
> 소형주(하위 20%)×4선 밸류. 홍용찬 대표 전략. 문병로 small_value(40% 게이트, 5팩터)와 A/B.

### rule_hong_multifactor (주력, conf 80, top_n=20)
```
hong_rank is not None AND hong_rank<=top_n
```
> 소형주 ∩ 흑자 ∩ (성장YoY>0) ∩ 4선 밸류 — 홍용찬 멀티팩터 완전체.
> **성장 게이트 포함 여부는 §9 사장님 결정**(커버리지 종속).

```
ALL_RULES = [rule_value4_low, rule_small_value4, rule_hong_multifactor]
```
> (배당 룰은 §9 결정 시 `rule_high_dividend` 추가 — 현재는 dividend_yield 0건이라 보류.)

---

## 4. 청산 Variant

| Variant | sl | tp | trail | mh | 비고 |
|---------|-----|-----|-------|-----|------|
| **Q** | 0.20 | 0.99(off) | 없음 | **63** | 분기 리밸런싱 근사(≈1분기 거래일). 홍용찬 분기 보유 |
| K | 0.175 | 0.99(off) | 없음 | 250 | 문병로 비교용(연 1회) |
| B | 0.08 | 0.12 | 없음 | 20 | 빠른 청산 비교용 |

- warmup 20. forced_close 지배 명시.
- **리밸런싱 게이트**(옵션): `--quarterly`(분기 시작 월 1,4,7,10 영업일) / `--april-only`(연 1회). 기본은 상시 + 둘 다 측정.

---

## 5. 코드 산출물

```
strategies/books/hongyongchan_quant/
├── __init__.py
├── rules.py      # _num + 룰 3종(value4_low/small_value4/hong_multifactor) + ALL_RULES
└── strategy.py   # HongYongchanQuantStrategy(BookStrategy) + BOOK_META + build_strategy
scripts/run_hongyongchan_quant.py   # 문병로 복제 + 4선(POR 제거) + 성장/마진/부채 게이트 + 소형주20% + 분기게이트
```

- strategy.py: holding_period="swing". BOOK_META id="hongyongchan_quant", name="홍용찬 실전 퀀트투자", category="fundamental_multifactor_kr", data_granularity="daily".
- run 스크립트(문병로 복제 후 수정):
  - `_FS_NUM_COLS` 교체: `per,pbr,revenue,operating_cash_flow` 유지 + `roe,operating_margin,debt_ratio,operating_profit,net_income` 추가, `operating_profit`는 POR 미사용이나 흑자 필터에 사용.
  - `_build_fund_by_idx`: por 제거, pcr 유지, roe/opm/debt/net_income/흑자/REV_YoY/OP_YoY 추가. YoY는 fs_rows 인접 연도 차분(같은 종목 직전 report_date).
  - `_build_cross_sectional_ranks`: vc(5팩터)→v4(4선) 교체, smallcap 게이트 40%→**20%**, hong_rank(소형주∩흑자∩성장) 추가.
  - simulate ctx_extra 키 교체(v4_rank/smallv4_rank/hong_rank/n_eligible). warmup 20.
  - `--quarterly` 게이트 추가(월 ∈ {1,4,7,10} & 분기 첫 영업일 근사).
  - leaderboard book_id="hongyongchan_quant", universe=f"factor_kr:{n_with_mc}"(문병로와 동일 131 → **책간 비교성 유지**), period="daily_full", reports-dir "reports/books_research/hongyongchan_quant".
- **실행 RoboTrader_template/ cwd**.

---

## 6. 백테스트 실행
```
python scripts/run_hongyongchan_quant.py --variant Q --all-modes
python scripts/run_hongyongchan_quant.py --variant Q --all-modes --quarterly
python scripts/run_hongyongchan_quant.py --variant K --all-modes        # 문병로 대조(연1회)
python scripts/run_hongyongchan_quant.py --variant Q --all-modes --april-only
python scripts/run_hongyongchan_quant.py --variant B --all-modes
```

## 7. 데이터 가용성 분류 (있음 / 재구성 / 백필필요)

| 지표 | DB 상태 | 분류 | 비고 |
|------|---------|------|------|
| PER | `per` 직접 | **있음** | 1473~ rows |
| PBR | `pbr` 직접 | **있음** | |
| PSR | `psr` 또는 mc/revenue | **재구성** | revenue 2676 rows |
| PCR | mc/`operating_cash_flow` | **재구성(백필완료)** | ocf 131종목 전부·2015+ |
| ROE | `roe` 직접 | **있음(부분)** | 1473 rows / 68종목 |
| 영업이익률 | `operating_margin` | **있음(부분)** | 1788 rows / 86종목 |
| 순이익률 | `net_margin` | **있음(부분)** | 1788 rows / 86종목 |
| 부채비율 | `debt_ratio` | **있음(부분)** | 1632 rows / 79종목 |
| 흑자/적자 | operating_profit·net_income | **있음** | 2676~2677 rows |
| 매출/이익 YoY 성장 | revenue/op/ni 연간 차분 | **재구성** | 연간만(QoQ 불가) |
| 시가총액(소형주) | daily_prices.`market_cap` | **있음** | 84% rows, 2021~2026 |
| **배당수익률** | `dividend_yield` 컬럼만, **0건** | **백필필요** | 배당 전략 포함 시 DART/KIS 백필 |
| 이자보상배율 | 이자비용 컬럼 부재 | **백필필요(or 제외)** | 문병로와 동일 한계 |
| 분기 재무(QoQ) | report_date 91% 연간(12월) | **부재** | YoY로 대체 |

---

## 8. 검증
- pytest tests/books/ 통과. no-lookahead: 순위가 D 데이터만(문병로 검증 로직 그대로).
- **책간 A/B 핵심**: 동일 universe(131)·동일 기간(2021~2026)에서
  - 홍용찬 `small_value4`(20% 게이트, 4선) vs 문병로 `small_value`(40% 게이트, 5팩터) → 게이트 강도·POR 효과 분리 측정.
  - `hong_multifactor`(성장/퀄리티 게이트 포함) vs `value4_low`(순수 밸류) → 게이트가 알파 추가하는지.
  - 분기 리밸런싱 vs 연 1회(K/april) → 회전율·비용 대비 효과.
- 다년·다국면(2021~2026 BULL/BEAR/SIDEWAYS) Sharpe 붕괴율을 Elder/Minervini/문병로와 같은 잣대로 평가.
- 게이트 결측 정책(§9) 적용 후 적격 종목수·n_eligible 분포 로깅.

## 9. 사장님 결정 필요 (코드화 전 결재)

1. **배당 전략 포함 여부 (백필 선행)** — `dividend_yield` **완전 공백(0건)**. 홍용찬 "배당" 챕터를 재현하려면 DART/KIS 배당 백필이 선행돼야 함. **결정지: (a) 배당 제외하고 4선+소형주+성장만 (백필 불필요, 즉시 가능) / (b) 배당 백필 후 배당 룰 포함.** 권장=우선 (a)로 코어 검증, 효과 확인 후 (b).
2. **성장/퀄리티 게이트 채택 범위** — roe/opm/debt가 **부분 커버리지**(68~86종목, 초기연도 위주). 2021~2026 백테스트 구간의 실제 커버리지가 낮으면 게이트가 표본을 과하게 줄일 수 있음. **결정지: (a) 게이트는 "데이터 있는 종목만 적용, 없으면 통과"(완화) / (b) "게이트 지표 없으면 부적격"(엄격, 표본↓) / (c) 성장/마진 게이트 자체를 코어에서 빼고 순수 4선+소형주만.** (코드화 1단계에서 2021+ 커버리지 실측 후 재확인 권장.)
3. **universe 선택** — 문병로와 **동일 131종목 유지(책간 비교성 ↑)** vs 더 넓은 universe로 확장(소형주 효과 강화하나 비교성 ↓). 권장=동일 131 유지.
4. **소형주 게이트 강도** — 홍용찬 명시 **하위 20%** 채택 vs 문병로 40%와 통일. 권장=홍용찬 20% 채택 + 변형 측정.

---

## 10. 한계 (전면)
- **책 실물 미보유** — 공개 자료/서평 재구성. "4선 저밸류·소형주 하위20%·분기 리밸런싱"은 다수 출처 일치하나, 책의 정확한 분위 임계·종목수(20 가정)·게이트 조합은 실물 확인 시 미세 조정 필요.
- **배당·이자보상배율 불가** — dividend_yield 0건, 이자비용 컬럼 부재(문병로와 동일).
- **성장은 YoY만**(분기 재무 부재로 QoQ 불가) — 홍용찬이 강조하는 분기 성장 모멘텀 일부 미재현.
- **ROE/OPM/부채 부분 커버리지** — 게이트 적용 시 표본 축소·시대 편향(2004~ 초기 위주) 가능.
- 131종목 한정 universe, 금융/유틸 제외 불가(industry 컬럼 부재). 진성 마이크로캡 부재(최소 시총 587억) → 소형주 효과 약화 가능(문병로와 동일).
- 분기/4월 리밸런싱은 캘린더 근사(종목별 실제 공시일 미반영). 연간 재무 105일 lag 근사.
- 책간 A/B는 universe/기간 통일 시에만 유효 — universe 변경 결정 시 비교성 무효(리포트 명시).
