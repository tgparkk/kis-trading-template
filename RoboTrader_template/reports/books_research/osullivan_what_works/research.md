# James O'Shaughnessy — What Works on Wall Street — 조사 노트 (Book 10, 최종)

> Book: James P. O'Shaughnessy — *What Works on Wall Street* (4th ed., 2011)
> 조사: 2026-05-29 · 설계: docs/superpowers/specs/2026-05-29-oshaughnessy-design.md
> 대규모 팩터 순위 전략. Greenblatt(Book 9) 횡단면 순위 인프라 확장.
> ⚠️ book_id는 레거시 `osullivan_what_works` 유지(인덱스 표기).

---

## 1. 핵심 방법론

대규모 단일/복합 팩터 백테스트(Compustat 1926~2009, 주력 1964~2009 45년). 절차: universe를 팩터(또는 복합)로 **순위→데실** 분할, 최저(최저평가) 데실 또는 상위 25~50종목 **동일가중** 매수, **1년 보유·연 재조정**, 장기 CAGR·base rate 측정.

- **All Stocks**(시총 ≥ 물가조정 하한 ~$150M) vs **Large Stocks**(시총 > DB 평균, ~상위 15%).
- All Stocks 벤치마크 ≈ 11.2% CAGR(1964~2009).

---

## 2. 단일 팩터 — 되는 것/안 되는 것

### 되는 가치 팩터 (최저 데실 매수)
| 팩터 | 비고 |
|------|------|
| **저 P/S (PSR)** | O'Shaughnessy "가치 팩터의 왕". 가장 일관된 가치 비율, P/E보다 약간 우수 |
| **저 EV/EBITDA** | 4판에서 P/S와 단일 최고 자리 경쟁 |
| **저 P/E** | 최저 데실 작동 |
| **저 P/CF** | 작동 |

> 모순(c): P/S 초과수익 측정은 ~1.5%로 "왕" 헤드라인과 충돌 → 결론: *어느 단일 가치 팩터도 전 구간 최고는 아님* → **복합(Composite)** 권장.

### 기타 되는 것
- **주주수익률(Shareholder Yield = 배당+자사주)**: 4판 헤드라인 신규 팩터. 상위 데실 +2.25~2.75%/yr.
- **6개월 모멘텀**: 강함. 단 *최악 데실 회피*가 핵심(나머지 9데실 비슷). 단독은 top 전략 아님 — 가치와 결합해야.

### 안 되는 것
- 고 P/E·P/B·P/S(글래머), 저 P/B 단독(약함), 배당 단독(약함), 순수 성장 단독.

---

## 3. Value Composite (VC1/VC2/VC3) — 4판 핵심 기여

단일 팩터는 10년+ 부진 가능 → 복합이 훨씬 안정(82% 롤링 10년 구간서 최고 단일팩터 상회).

**구성**: 각 비율을 1~100 백분위 순위(1=최저평가) → 결측=50 중립 → 평균 → 재순위 → 최저 데실 매수.

| 복합 | 팩터 | All Stocks CAGR |
|------|------|----------------|
| **VC1** | P/E, P/B, P/S, EV/EBITDA, P/CF (5) | 17.18% |
| **VC2** | VC1 + 주주수익률 (6) | 17.3% (낮은 σ) |
| **VC3** | VC2의 주주수익률→자사주수익률 | 17.39% |

---

## 4. Trending Value — 플래그십

"시장이 알아보기 시작한 싼 주식". ① VC2로 **최저 데실**(상위 10%) ② 그 안에서 **6개월 모멘텀** 상위 25~50 매수, 동일가중, 연 재조정.

| 전략 | CAGR (1964~2009) |
|------|------------------|
| All Stocks | 11.2% |
| 모멘텀 단독 | 14.5% |
| VC2 단독 | 17.3% |
| **Trending Value 50종목** | **19.85%** |
| **Trending Value 25종목** | **~21.2%** |

---

## 5. 포트폴리오 룰
- 25(최대수익)~50(저변동)종목 동일가중, 연 재조정. 부진 ~19~20% 구간을 기계적으로 견디는 규율이 엣지(Greenblatt와 동일 행동 메시지).

---

## 6. ⚠️ 한국 데이터 실태 (라이브 조회 2026-05-29)

| 팩터 | 소스 | 가용성 | 판정 |
|------|------|--------|------|
| **PSR** | **재구성** `(market_cap/1e8)/revenue` | revenue 99.9%·psr컬럼 0% | **재구성 가능** (market_cap 창) |
| P/E | per | 54% | 가능 |
| P/B | pbr | 61% | 가능 |
| EV/EBIT | `(market_cap/1e8+total_liabilities)/operating_profit` | op ~100%, tl 61% | 가능 (market_cap 창) |
| P/CF | 현금흐름 컬럼 없음 | 0% | **사망** |
| EV/EBITDA | D&A 없음(op=EBIT만) | 0% | **사망** |
| 주주/배당수익률 | dividend_yield 100% NULL | 0% | **사망 — 진짜 VC2/VC3 불가** |
| 6개월 모멘텀 | close ≥140봉 | **16종목만** | 거의 불가 |
| 3개월 모멘텀 | close ≥63봉 | 131종목 | **가능 → 채택** |

**귀결**:
- 진짜 VC2/VC3 불가(주주수익률·P/CF·EBITDA 부재) → **VC1식 4팩터 가치복합**(PSR+PE+PB+EV/EBIT)만.
- 6개월 모멘텀 불가 → **3개월(63봉)** 사용 (Trending Value 변형).
- PSR/EV-EBIT가 market_cap 필요 → VC는 **6개월 창·79종목**에 confine (Greenblatt와 동일 universe → PSR-vs-EY 비교 깨끗).
- 단위: market_cap(원)/1e8 환산(Greenblatt와 동일).

---

## 7. 코드화 대상 룰 3종

> Greenblatt `_build_cross_sectional_ranks` 확장 → vc_rank·tv_rank·psr_rank·n_eligible를 ctx 주입.

### rule_value_composite (VC1식, conf 75)
```
적격(4팩터 모두) AND n_eligible>=10 AND vc_rank <= top_n
vc_score = mean(pct_psr, pct_pe, pct_pb, pct_evebit)  (cheap=high pct), top_n 기본 20
```

### rule_trending_value (플래그십, conf 78)
```
① vc_score 상위 40%(저평가 게이트) ② 그 안에서 3개월 모멘텀(close/close[-63]-1) 상위
tv_rank <= top_n (기본 20)
```
> 책은 최저 데실+6개월. 소형 universe라 게이트 40%로 확대 + 3개월 모멘텀(데이터 강제). 명시.

### rule_low_psr (시그니처 단일, conf 70)
```
psr_rank = PSR 오름차순(1=최저=최저평가) AND n_eligible>=10 AND psr_rank <= top_n
```

```
ALL_RULES = [rule_value_composite, rule_trending_value, rule_low_psr]
```

---

## 8. 청산 Variant (Greenblatt와 동일)

| Variant | sl | tp | trail | mh |
|---------|-----|-----|-------|-----|
| **A** | 0.20 | 0.99(off) | 없음 | 120 |
| **B** | 0.08 | 0.12 | 없음 | 20 |

- warmup 20. forced_close 지배(짧은 이력).

---

## 9. 리스크
1. **6개월 단일 국면**(market_cap 창) — OOS·walk-forward 불가
2. 79종목 → 가치게이트·모멘텀 후 TV 가능종목 ~20~30/일 (얇음)
3. 6개월 모멘텀 거의 불가(16종목) → 3개월 (책 스펙 이탈)
4. **주주수익률 부재 → 진짜 VC2/VC3 불가**(4판 헤드라인 손실)
5. PSR 재구성 근사(연간 revenue vs 일별 market_cap 시점 불일치)
6. EV 상향편향(현금無), 연간 데이터(15개월 stale), 금융/유틸 제외 불가, BULL 편향

---

## 10. 참고 자료
| 제목 | URL |
|------|-----|
| Jim O'Shaughnessy — Shareholder Yield (저자 블로그) | https://jimoshaughnessy.tumblr.com/post/94453059749/the-power-of-shareholder-yield |
| Jim O'Shaughnessy — Value of Value Factors | https://jimoshaughnessy.tumblr.com/post/141103669809/the-value-of-value-factors |
| OSAM — Factor Archives: Shareholder Yield | https://osam.com/Commentary/the-factor-archives-shareholder-yield |
| Quant-Investing — Trending Value 구현 | https://www.quant-investing.com/blog/how-and-why-to-implement-james-o-shaughnessy-s-trending-value-investment-strategy-world-wide |
| ValueSignals — VC1/VC2/VC3 | https://www.valuesignals.com/Glossary/Details/O_Shaughnessy_VC2 |
| Portfolio123 — Did WWoWS stop working? | https://blog.portfolio123.com/did-what-works-on-wall-street-stop-working/ |
| Value and Opportunity — 4판 리뷰 | https://valueandopportunity.com/2012/05/30/book-review-oshaughnessy-what-works-on-wall-street-4th-edition/ |

---

*Phase 1 완료(최종 책). 다음: Phase 2 설계 → 코드 → 백테스트 → 리포트 → 10권 통합 요약.*
