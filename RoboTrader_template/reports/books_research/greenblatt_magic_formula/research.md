# Joel Greenblatt — Magic Formula — 조사 노트 (Book 9)

> Book: Joel Greenblatt — *The Little Book That Beats the Market* (2006) / *...That Still Beats the Market* (2010)
> 조사: 2026-05-29 · 설계: docs/superpowers/specs/2026-05-29-greenblatt-magic-design.md
> 펀더멘털 횡단면 순위 전략. Lynch(Book 8) point-in-time 재무 조인 재사용.

---

## 1. 핵심 개념

"좋은 기업을 싼 가격에 사라" — 두 지표만 결합:
- **좋은 기업** = 높은 **자본수익률(ROC)**: 투입 자본 대비 영업이익 높음 (버핏식 — 고ROC 기업은 복리 성장)
- **싼 기업** = 높은 **이익수익률(Earnings Yield)**: 지불하는 가격(EV) 대비 영업이익 높음

둘 중 하나만으로는 불충분(좋은데 비싸거나, 싼데 형편없는 가치함정). 두 지표를 각각 순위 매겨 **합산** → 둘 다 우수한 교집합 선별.

---

## 2. 두 지표 — 정확한 공식 (Greenblatt 비표준 정의)

### 이익수익률 = EBIT / EV
- P/E 대신 EBIT/EV 사용: **자본구조 중립**(EBIT=이자前, EV=부채 가산 → 레버리지 무관) + **세금 중립**(EBIT=세前) + **실제 인수가격** 반영.
- `EV = 시가총액 + 총부채 − 잉여현금 (+ 소수지분 + 우선주)`

### 자본수익률(ROC) = EBIT / (순운전자본 + 순고정자산)
- 분모 = "투입 유형자본(tangible capital employed)"
- 순운전자본 = 영업유동자산 − 무이자유동부채 (매입채무=무이자 차입이라 차감, 단기차입금·잉여현금 제외)
- 순고정자산 = 순PP&E (영업권·무형자산 제외)
- ROE/ROA 대신 쓰는 이유: EBIT(레버리지·세금 중립) + 유형자본(영업에 실제 필요한 자본만; ROE는 레버리지로 조작 가능, ROA는 영업권·현금 포함)

### 제외 (Greenblatt 명시)
- **금융·유틸리티 제외**(회계 특수성), **외국주 제외**(미국 상장만), **최소 시총** 기본 $50M(저변동은 $1B 권장)

---

## 3. 순위 절차

1. 적격 universe 전 종목을 **이익수익률 내림차순 순위**(1=최고)
2. 별도로 **ROC 내림차순 순위**(1=최고)
3. **두 순위 합산** (예: EY 10위 + ROC 99위 = 109)
4. 합산 **오름차순 정렬** — 최소값이 최고 Magic 종목
5. 상위 20~30종목 매수 (둘 다 균형 우수한 종목이 승리; 한 지표 1위 불필요)
- 두 지표 **동일 가중**.

---

## 4. 포트폴리오·보유 룰

- **20~30종목 동일금액**. 12개월간 월 2~3종목씩 **분할 진입**(진입 타이밍 분산).
- 각 종목 **~1년 보유** 후 재스크리닝·교체. 연 회전율 ~100%.
- 세금 타이밍(미국): 수익은 1년+1일 후 매도(장기 양도), 손실은 1년 전 매도(단기 손실).

---

## 5. 성과·경고

- 원전 백테스트(1988~2004, >$50M, ~3,500종목): **연 30.8%** vs S&P 12.3%. 연수익 −4.4%~+79.9%(고변동).
- 대형주(상위 1,000 >$1B): 연 22.9% → **소형주에서 더 강함**(사이즈 틸트).
- **핵심 행동 경고(원전)**: 12개월 구간 中 ~5회 시장 하회, ~4년 中 1년 하회, 2~5년 연속 하회 가능. 3년+ 구간에선 거의 항상 승리. *대부분이 다년 하회를 못 견뎌 포기 → 그게 엣지의 원천.*
- OOS(2003~2015): 연 11.4%로 약화(차익거래 소멸 가능성).

---

## 6. 모호·논쟁 (코드화 결정 필요)

1. **ROC 분모 잉여현금 차감 여부**(원전 "NWC+NFA" vs 일부 "−잉여현금")
2. NWC 라인아이템 구성 / 잉여현금 정의
3. **EBIT vs as-reported 영업이익**(벤더별 상이)
4. EV 소수지분·우선주 포함 여부

---

## 7. ⚠️ 한국 데이터 실태 (라이브 조회 2026-05-29 — 설계 좌우)

| 사실 | 값 | 영향 |
|------|-----|------|
| financial_statements | 131종목 | Lynch와 동일 |
| operating_profit non-null | ~100% | **EBIT proxy 견고** |
| total_assets/total_liabilities | 61% | ROC 분모·부채 |
| current_liabilities | 57% | ROC·EV 제약 |
| **market_cap 날짜 범위** | **2025-07-31 ~ 2026-02-02만** | **~124일(6개월) — 진짜 천장** |
| market_cap 보유 종목 | **79/131** | 52종목 영구 순위불가 |
| 종목당 market_cap 봉 평균 | 67.4 | |
| 종목당 전체 봉 평균 | 120 (중앙 107) | 짧은 이력 |
| **일자별 적격 universe** | **평균 66.5, 중앙 74, 최소 26** | **순위 산출 충분(전 124일 ≥20)** |

**결정적 귀결**:
1. 순위 변형(magic_formula_top)은 **6개월 단일 국면**(124일)만 신호. 79종목만 순위. **이전 8권과 기간 비교성 단절.** universe tag `magic:79`.
2. EBIT=operating_profit. **EV = market_cap + total_liabilities**(현금 컬럼 없음 → EV 상향 편향 → EY 과소). ROC = operating_profit/(total_assets − current_liabilities).
3. report_date VARCHAR — `report_date::date` 캐스팅 + 정규식 필터(마이그레이션 잔존 오류). point-in-time **105일 lag**(Lynch와 동일).
4. **금융·유틸리티 제외 불가**(섹터 컬럼 없음) → 순위 오염 가능, 명시.

---

## 8. ROC 대수 (확인)

```
NWC + 순고정자산 = (current_assets − current_liabilities) + (total_assets − current_assets)
                 = total_assets − current_liabilities
```
→ `TA − CL`이 대수적으로 정확 + current_assets 불필요(상쇄). 단 영업권·무형자산이 "고정자산"에 포함됨(Greenblatt는 제외) → ROC 하향 편향(보수적).

---

## 9. 코드화 대상 룰 3종

> ctx 주입: 횡단면 순위(magic_rank, n_eligible) + fund(원시 재무). Minervini RS 주입 + Lynch PIT 조인 결합.

### rule_magic_formula_top (순위 기반, 주력, conf 75)
```
적격 AND n_eligible >= 10 AND magic_rank <= N (기본 20; sweep 10/20/30)
```

### rule_magic_formula_threshold (per-stock, 순위 불필요, conf 70)
```
EY = op/EV > 0.10  AND  ROC = op/(TA−CL) > 0.25
(Greenblatt: 좋은기업 ROC 25%+, 싼 EY 10%+. EY는 market_cap 필요 → 6개월 창 내)
```

### rule_high_roc_value (품질 틸트, conf 68)
```
EY > 0.08  AND  ROC > 0.40
```

```
ALL_RULES = [rule_magic_formula_top, rule_magic_formula_threshold, rule_high_roc_value]
```

---

## 10. 청산 Variant

| Variant | sl | tp | trail | mh | 비고 |
|---------|-----|-----|-------|-----|------|
| **A** (Greenblatt 의도) | 0.20 (넓은 안전망) | 0.99(off) | 없음 | 120 | 1년 보유→재조정. mh 250은 forced_close 지배 → 120 타협 |
| **B** (획일) | 0.08 | 0.12 | 없음 | 20 | 책간 비교 |

- ROC 폭주 가드: (TA−CL) 작을 때 ROC 폭발 → ROC > 5.0 캡 추가.

---

## 11. 리스크

1. **6개월 천장(최악)**: market_cap 124일만 → 순위 변형은 6개월 단일 국면. 79종목만 순위
2. EV 상향 편향(현금 차감 불가) → EY 과소, 현금부자 종목 불리
3. 연간 데이터 staleness(12월 91%) + 105일 lag → 최대 ~15개월 stale
4. 영업권/무형자산 분모 포함 → ROC 하향
5. **섹터 제외 불가**(금융·유틸 오염)
6. 순위 불안정(적격 26~74 변동), 생존편향, BULL 편향
7. forced_close 지배(이력 짧음), ROC 작은 분모 폭주

---

## 12. 참고 자료

### 1차
- Greenblatt, Joel. *The Little Book That (Still) Beats the Market*. 2006/2010.

### 2차
| 제목 | URL |
|------|-----|
| Magic Formula Investing — Wikipedia | https://en.wikipedia.org/wiki/Magic_formula_investing |
| magicformulainvesting.com (screener/FAQ) | https://www.magicformulainvesting.com/ |
| Greenblatt EY & ROC — GuruFocus | https://www.gurufocus.com/tutorial/article/57/greenblatts-earnings-yield-and-return-on-capital |
| Saber Capital — Return on Capital | https://sabercapitalmgt.com/thoughts-on-return-on-capital-and-greenblatts-magic-formula-part-1/ |
| Reasonable Deviations — critical look | https://reasonabledeviations.com/2020/06/08/greenblatt-magic-formula/ |
| StableBread — Magic Formula | https://stablebread.com/magic-formula-investing/ |
| AAII — Greenblatt's Magic Formula | https://www.aaii.com/journal/article/greenblatts-magic-formula |

---

*Phase 1 완료. 다음: Phase 2 설계서 (횡단면 순위 주입 + 3룰 잠금).*
