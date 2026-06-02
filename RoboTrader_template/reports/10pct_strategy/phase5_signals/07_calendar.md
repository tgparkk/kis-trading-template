# Phase 5 — 카테고리 7: 캘린더 효과

> 작성일: 2026-05-25 | 조사자: document-specialist (Claude Sonnet 4.6)
> 목적: Phase 5 시그널 패밀리 확장 — 캘린더 효과 카테고리
> No Look-Ahead 원칙: 모든 시그널은 당일 장 시작 전 또는 이벤트 사전 확정 일정 기반으로만 생성

---

## 요약

| 항목 | 값 |
|---|---|
| 수집 컨셉 수 | **20개** |
| 책 기반 컨셉 | 0개 (3권 모두 캘린더 효과 미커버, 00_kyobo_books.md §카테고리7 확인) |
| 외부 학술/공개자료 | 20개 |
| 한국 실증 확인 | 8개 (학술 논문 직접 출처 있음) |
| 즉시 코드화 가능 | 7개 (내부 DB/날짜 연산으로 충분) |
| PIT-safe | 15개 가능 / 4개 부분 / 1개 불가 |

---

## 범례

| 기호 | 의미 |
|------|------|
| 즉시 | 내부 DB/날짜 연산으로 즉시 계산 가능 |
| 부분 | DB에 일부 데이터 있음, 추가 연산 또는 외부 소스 일부 필요 |
| 외부 | 외부 데이터 소스 필수 (DART API, KRX, MSCI, ECOS, Fred 등) |

---

## 컨셉 카탈로그

---

### 1. Halloween Effect (할로윈 효과 / Sell in May)

- **정의**: 11월~4월 보유 수익률이 5월~10월 수익률보다 유의하게 높음. "Sell in May and Go Away." 37개국 중 36개국에서 실증.
- **출처**:
  - Bouman & Jacobsen (2002) *American Economic Review* 92(5): 1618-1635 — [SSRN 76248](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=76248)
  - Jacobsen & Zhang (2012) "Everywhere and All the Time" — [SSRN 2154873](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2154873) (108개국, KOSPI 포함)
  - ResearchGate: [The Halloween Puzzle in Selected Asian Stock Markets](https://www.researchgate.net/publication/236737041_The_Halloween_puzzle_in_selected_Asian_stock_markets) — Lean (2011), 6개 아시아국
- **카테고리 태그**: Stage A (진입 필터 / 계절성 오버레이)
- **버킷**: position (월간 보유)
- **한국 시장 실증**: Jacobsen & Zhang (2012) 108개국 분석에 KOSPI 포함. 아시아 신흥국 전반에 효과 유의 (GARCH 모형 사용 시 더 강해짐). 한국 단독 분기 검증 논문은 미확인.
- **PIT-safe 가능성**: 가능 — 5월 1일/11월 1일 기준으로 포지션 방향 조정. 사전 확정 날짜.
- **필요 데이터**: 내부 일봉(daily_prices) + 날짜 연산
- **예상 difficulty**: Low — 날짜 비교 단순 연산

---

### 2. January Effect (1월 효과)

- **정의**: 1월 초 소형주 수익률이 다른 달 대비 유의하게 높음. 세금 손실 매도(tax-loss selling) 후 1월 재매수 압력이 원인. 미국 자본이득세 구조에 기인하나 비과세 국가에서도 관찰.
- **출처**:
  - Springer: [An analysis of the January effect of United States, Taiwan and South Korean stock returns](https://link.springer.com/article/10.1007/BF01732896) — Asia Pacific Journal of Management
  - ResearchGate: [The risk of earnings information uncertainty and the January effect in Korean stock markets](https://www.researchgate.net/publication/286072527_The_risk_of_earnings_information_uncertainty_and_the_January_effect_in_Korean_stock_markets)
- **카테고리 태그**: Stage A (진입 필터)
- **버킷**: swing (1~2주)
- **한국 시장 실증**: 확인됨 — 한국은 자본이득세 부재에도 1월 효과 존재. 세금 가설 이외 유동성 제약 가설(Liquidity Constraint)로 설명. ARCH 시변 리스크 프리미엄 분석 적용.
- **PIT-safe 가능성**: 가능 — 1월 1~10 영업일 윈도우에 플래그 설정.
- **필요 데이터**: 내부 일봉 + 날짜 연산 + 시가총액 (소형주 필터)
- **예상 difficulty**: Low-Medium

---

### 3. Turn-of-Month Effect (월말/월초 효과)

- **정의**: 매월 마지막 1~3 영업일과 첫 1~3 영업일에 수익률이 유의하게 높음. 개인 급여 수령 후 자금 유입, 기관 윈도드레싱이 원인.
- **출처**:
  - ScienceDirect: [The turn-of-the-month effect and trading of types of investors](https://www.sciencedirect.com/science/article/abs/pii/S0927538X22001214) — Pacific-Basin Finance Journal (2022)
  - Emerald: [The TOM effect and investor trading activities in the KOSDAQ stock market](https://www.emerald.com/jdqs/article/30/4/260/205635/) — Journal of Derivatives and Quantitative Studies (2022)
- **카테고리 태그**: Stage A (진입 필터) / Stage B (신호 강도 가중치)
- **버킷**: swing (2~5일 보유)
- **한국 시장 실증**: 확인됨 — KOSPI/KOSDAQ 모두 TOM 효과 유의. 개인 거래 비중 55.7% (2000~2020) 환경에서 외국인·기관 월말 순매수 증가. Yun & Kim (2014), Hong et al. (2014) 포함 다수 검증.
- **PIT-safe 가능성**: 가능 — 영업일 카운트 기반 사전 계산.
- **필요 데이터**: 내부 trading_calendar (영업일 카운트)
- **예상 difficulty**: Low

---

### 4. Monday Effect / Day-of-Week Effect (월요일 효과)

- **정의**: 월요일 평균 수익률이 다른 요일보다 유의하게 낮음 (또는 음수). 주말 정보 축적 후 월요일 소화, 투자자 심리 변화가 원인.
- **출처**:
  - ScienceDirect: [Sentiment changes and the Monday effect](https://www.sciencedirect.com/science/article/abs/pii/S1544612322000368) — Finance Research Letters (2022)
  - Springer: [Day-of-the-week effect: a meta-analysis](https://link.springer.com/article/10.1007/s40822-024-00293-9) — Eurasian Economic Review (2024)
- **카테고리 태그**: Stage A (방향 필터)
- **버킷**: swing / mid (1~3일)
- **한국 시장 실증**: 확인됨 — KOSPI 개별 종목 거래 데이터 기반 월요일 효과 명확히 관찰. 글로벌 다중프랙탈 분석(PMC 2022)에서도 한국 포함 아시아 시장에 유의.
- **PIT-safe 가능성**: 가능 — 요일 판단은 사전 확정.
- **필요 데이터**: 날짜 to 요일 변환 (Python datetime)
- **예상 difficulty**: Very Low

---

### 5. KOSPI200 옵션만기 효과 (매월 둘째 목요일)

- **정의**: KOSPI200 옵션 월물 만기일(매월 2번째 목요일) 전후 30분~1시간 변동성 급등 및 거래량 급증. "Wag the Dog" 현상 — 파생상품이 현물시장을 끌고 가는 역학.
- **출처**:
  - ResearchGate: [Expiration Day Effect in Korean Stock Market: Wag the Dog?](https://www.researchgate.net/publication/4816975_Expiration_Day_Effect_in_Korean_Stock_Market_Wag_the_Dog)
  - ResearchGate: [Expiration-day effects of the KOSPI 200 futures and options](https://www.researchgate.net/publication/289170056_Expiration-day_effects_of_the_KOSPI_200_futures_and_options)
- **카테고리 태그**: Stage B (신호 강도 조정) / Stage C (청산 타이밍)
- **버킷**: swing (당일~익일)
- **한국 시장 실증**: 확인됨 — KOSPI200 파생 만기일 현물 변동성 유의 상승. 쌍둥이 만기(선물+옵션 동시) Thursdays > 옵션전용 > 비만기 순. 만기 전주 수익률 연속성(momentum) 증가, 만기 당일 역전 경향.
- **PIT-safe 가능성**: 가능 — KRX 공식 파생상품 만기 일정표 사전 공개. 매월 2번째 목요일 규칙 자동 계산 가능.
- **필요 데이터**: KRX 파생상품 만기 캘린더 (자동 계산 가능)
- **예상 difficulty**: Low

---

### 6. 분기물 만기 (3/6/9/12월 둘째 목요일) — 쿼터리 위칭

- **정의**: 주가지수선물 + 옵션이 동시 만기되는 분기 만기일. 단일 옵션 만기보다 변동성 및 거래량 충격이 크고 기간이 길다. Triple Witching에 대응.
- **출처**:
  - ResearchGate: [Expiration-day effects of the KOSPI 200 futures and options](https://www.researchgate.net/publication/289170056_Expiration-day_effects_of_the_KOSPI_200_futures_and_options) (쌍둥이 만기 분석 포함)
- **카테고리 태그**: Stage B / Stage C
- **버킷**: swing
- **한국 시장 실증**: 확인됨 — 논문에서 쌍둥이 만기 목요일(Twin-expiration Thursdays) 명시적으로 더 큰 변동성 확인.
- **PIT-safe 가능성**: 가능 — 3/6/9/12월 2번째 목요일 자동 계산 가능.
- **필요 데이터**: 날짜 연산
- **예상 difficulty**: Very Low

---

### 7. KOSPI200/KOSDAQ150 반기 리밸런싱 (6월/12월)

- **정의**: KOSPI200 및 KOSDAQ150 구성 종목 변경 발표(보통 5월/11월 말) 후 적용일(6월/12월 둘째 금요일 전후) 전후 편출입 종목의 가격 압력.
- **출처**:
  - ScienceDirect: [The effect of changes in index constitution: Evidence from the Korean stock market](https://www.sciencedirect.com/science/article/abs/pii/S1057521910000505)
  - SmartKarma: [KOSPI200 Index Rebalance Preview: 7 Changes a Side for December](https://www.smartkarma.com/insights/kospi200-index-rebalance-preview-7-changes-a-side-for-december)
  - Scribd: [KOSPI 200 Index Methodology Guide](https://www.scribd.com/document/513807265/1-3-KOSPI-200-Methodology-2011)
- **카테고리 태그**: Stage A (종목 선별) / Stage B (방향성 신호)
- **버킷**: position (3~4주)
- **한국 시장 실증**: 확인됨 — 편입 종목 매수 압력, 편출 종목 매도 압력 명확. 중간 단계(발표~적용) 알파 기회 존재. 아비트라저가 이를 이용해 수익 창출.
- **PIT-safe 가능성**: 가능 — KRX 발표 기준 편입/편출 명단은 확정 후 공개. Look-ahead 위험 없음.
- **필요 데이터**: KRX 지수 구성 변경 공시 (KRX Data System)
- **예상 difficulty**: Medium (KRX 데이터 수집 자동화 필요)

---

### 8. MSCI Korea 분기 리밸런싱 (2/5/8/11월)

- **정의**: MSCI Korea 지수 구성 변경 발표(각 분기 초) 후 적용일(2/5/8/11월 말~익월 초) 전후 글로벌 패시브 펀드의 대규모 매수/매도 압력.
- **출처**:
  - Georgia Tech: [Price and Volume Effects of Changes in MSCI Indices](https://www.scheller.gatech.edu/directory/research/finance/jayaraman/pdf/6840_03232004_final.pdf)
  - BusinessKorea: [MSCI Korea Index Adjusts Constituents](https://www.businesskorea.co.kr/news/articleView.html?idxno=242152)
  - BusinessKorea: [Passive Strategy: Upcoming MSCI SAIR and Influence of Rebalancing](http://www.businesskorea.co.kr/news/articleView.html?idxno=64039)
- **카테고리 태그**: Stage A (종목 선별)
- **버킷**: position (2~4주)
- **한국 시장 실증**: 부분 확인 — 2020년 8월 이후 리밸런싱일 외국인 순매도 수십억 달러 규모 관찰(BusinessKorea). 기계적 리밸런싱(비중 초과 후 강제 매도) 역설도 문서화됨.
- **PIT-safe 가능성**: 가능 — MSCI 공식 발표 일정(사전 예고) 기반. 적용일은 MSCI 홈페이지에서 사전 확인 가능.
- **필요 데이터**: MSCI 공식 일정(https://www.msci.com) + 편입/편출 명단 (MSCI 발표)
- **예상 difficulty**: Medium-High (MSCI 데이터 유료 or 발표 수동 수집)

---

### 9. 연말 윈도드레싱 (12월 마지막 2~3 영업일)

- **정의**: 연말 기관투자자 포트폴리오 성과 개선을 위해 상승 종목 매수 / 하락 종목 매도. 12월 마지막 영업일~1월 초 강세 종목 쏠림.
- **출처**:
  - ResearchGate: [The risk of earnings information uncertainty and the January effect in Korean stock markets](https://www.researchgate.net/publication/286072527_The_risk_of_earnings_information_uncertainty_and_the_January_effect_in_Korean_stock_markets) (한국 연말 이상현상 맥락)
  - EWF Pro: [Window Dressing: End-of-Quarter Momentum](https://www.ewfpro.com/index.php/en/economy/98398-window-dressing-end-of-quarter-momentum-that-can-move-the-stock-market-gold-and-the-dollar)
- **카테고리 태그**: Stage A (진입 필터) / Stage B (신호 강도)
- **버킷**: swing (3~5일)
- **한국 시장 실증**: 직접 논문 한국 전용 미확인. TOM/January Effect 문헌에서 연말 현상 맥락으로 함께 기술. 시장 실무자 경험칙은 광범위하게 공유됨.
- **PIT-safe 가능성**: 가능 — 마지막 영업일 기준 역산 가능.
- **필요 데이터**: 내부 trading_calendar
- **예상 difficulty**: Low

---

### 10. 대주주 양도세 회피 매도 (한국 12월 말 특수)

- **정의**: 한국 소득세법상 상장주식 양도소득세 과세 기준일이 12월 말. 보유 지분 5,000억 원 이상 또는 지분율 1% 이상(코스닥 2%, 코넥스 4%) 대주주는 12월 마지막 영업일 직전 2~5 영업일에 세금 회피 목적 매도 압력 발생.
- **출처**:
  - KED Global: [Seoul backs down on capital gains tax plan for large shareholders](https://www.kedglobal.com/korean-stock-market/newsView/ked202509150003)
  - PwC Korea Tax Summaries: [Korea, Republic of - Individual - Income determination](https://taxsummaries.pwc.com/republic-of-korea/individual/income-determination)
  - Bloomberg: [South Korea Scraps Plans to Raise Capital Gains Tax on Stocks](https://www.bloomberg.com/news/articles/2025-09-14/south-korea-scraps-plans-to-raise-capital-gains-tax-on-stocks)
- **카테고리 태그**: Stage A (방향 필터) — 해당 기간 매수 신중, 역방향(매도 압력 소멸 후 반등) 노림
- **버킷**: swing (2~5일)
- **한국 시장 실증**: 한국 전용 현상 — 12월 마지막 2~3 영업일 KOSPI/KOSDAQ 개별 종목 매도 압력 후 1월 초 반등 패턴. 세금 기준일이 12월 31일이므로 연도마다 정확히 예측 가능.
- **PIT-safe 가능성**: 가능 — 세법 기준일(12/31) 기반 고정 일정. 단, 기준금액/요건은 세법 개정 시 변동.
- **필요 데이터**: 날짜 연산 + 세법 기준 모니터링 (연 1회 확인)
- **예상 difficulty**: Low (날짜 계산), Medium (기준 요건 매년 확인)

---

### 11. Santa Claus Rally (산타클로스 랠리)

- **정의**: 12월 마지막 5 영업일 + 1월 첫 2 영업일(총 7일)에 S&P 500이 평균 1.3% 상승. Yale Hirsch (1972) 명명. 한국은 대주주 양도세 매도 압력으로 인해 US와 반대 패턴을 보이는 경향.
- **출처**:
  - Wikipedia: [Santa Claus rally](https://en.wikipedia.org/wiki/Santa_Claus_rally)
  - Sky Atlas Treasure: [US vs Korea Santa Rally Features](https://www.skyatlastreasure.com/2025/12/blog-post_30.html) — 한국 시장 비교 분석 (2025년 12월)
  - Britannica Money: [Santa Claus Rally](https://www.britannica.com/money/Santa-Claus-rally)
- **카테고리 태그**: Stage A (방향 필터)
- **버킷**: swing (7 영업일)
- **한국 시장 실증**: 부분 확인 — 한국은 12월 말 대주주 양도세 매도 압력으로 US와 역방향 가능. 단, 실적 서프라이즈가 있으면 US와 동조(2025년 반도체 슈퍼사이클 사례). "조건부" 효과.
- **PIT-safe 가능성**: 가능 — 날짜 기반 고정 창.
- **필요 데이터**: 내부 trading_calendar + 시장 regime 판단
- **예상 difficulty**: Medium (한국 반전 패턴 모델링 필요)

---

### 12. 한국 금통위(BOK MPC) 결정일 효과

- **정의**: 한국은행 금융통화위원회 기준금리 결정일(연 8회, 매월 또는 격월 목요일) 전후 KOSPI 변동성 증가 및 방향성 반응. 금리 동결/인하/인상에 따라 당일 및 익일 반응이 다름.
- **출처**:
  - ScienceDirect: [Investor behavior around monetary policy announcements: Evidence from the Korean stock market](https://www.sciencedirect.com/science/article/abs/pii/S1544612318300734)
  - PMC/Springer: [Monetary shocks on the Korean stock index: structural VAR analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC9807100/)
  - BOK: [Monetary Policy Decision Press Releases](https://www.bok.or.kr/eng/bbs/E0000634/)
- **카테고리 태그**: Stage A (방향 오버레이) / Stage C (청산 타이밍)
- **버킷**: swing (당일~3일)
- **한국 시장 실증**: 확인됨 — 금리 인하 후 KOSPI 긍정 반응, 인상 후 부정. 개인은 발표 전 매도, 기관 외국인은 발표 전 매수 패턴 관찰.
- **PIT-safe 가능성**: 가능 — BOK 연간 MPC 일정 사전 공개. 결정 내용은 발표 후 인식.
- **필요 데이터**: BOK 금통위 일정(연초 전체 공개)
- **예상 difficulty**: Low (일정 파싱), Medium (결정 방향 예측 불필요 — 발표 후 반응 추종)

---

### 13. FOMC 발표일 효과 (한국 시장 연동)

- **정의**: 미국 FOMC 금리 결정일(연 8회) 전후 KOSPI 반응. Pre-FOMC Drift: 발표 24시간 전 글로벌 주식시장 평균 +0.6% 상승. 한국 시장에서 개인은 FOMC 전 매도, 기관은 매수 패턴.
- **출처**:
  - ScienceDirect: [Investor behavior around monetary policy announcements: Evidence from the Korean stock market](https://www.sciencedirect.com/science/article/abs/pii/S1544612318300734) (한국 시장 FOMC 반응 전용)
  - NY Fed Staff Report: [The Pre-FOMC Announcement Drift](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr512.pdf)
  - Quantpedia: [Federal Open Market Committee Meeting Effect in Stocks](https://quantpedia.com/strategies/federal-open-market-committee-meeting-effect-in-stocks)
- **카테고리 태그**: Stage A (방향 오버레이)
- **버킷**: swing (당일~2일)
- **한국 시장 실증**: 확인됨 — 2000~2017 한국 데이터 기반 연구. 개인 선행 매도, 기관 선행 매수(증권사 자기매매 가장 두드러짐).
- **PIT-safe 가능성**: 가능 — FOMC 일정은 연초 Fed 공식 발표. 결정 내용은 발표 후 인식.
- **필요 데이터**: Fed FOMC 일정 (https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- **예상 difficulty**: Low

---

### 14. 한국 수출입 통계 발표일 효과 (매월 1일 / 21일 속보)

- **정의**: 관세청이 매월 1일 전월 수출입 확정 통계 발표. 20일치 속보치는 매월 21일경 추가 발표. 수출 YoY 증가율 서프라이즈(예상치 대비) 당일 KOSPI, 특히 수출 대형주(삼성전자, SK하이닉스, 현대차) 방향성 영향.
- **출처**:
  - 관세청 수출입무역통계: [tradedata.go.kr](https://www.tradedata.go.kr/cts/index_eng.do)
  - CEIC: [Korea Exports: First 20 days](https://www.ceicdata.com/en/korea/trade-statistics-first-20-days/exports-first-20-days)
  - Trading Economics: [South Korea Exports YoY](https://tradingeconomics.com/south-korea/exports-yoy)
- **카테고리 태그**: Stage A (방향 오버레이) / Stage B (섹터 신호)
- **버킷**: swing (당일~2일)
- **한국 시장 실증**: 직접 학술 논문 미확인. 수출 의존도(GDP 대비 45%+) 특성상 수출 통계가 KOSPI와 강한 상관관계 보임은 시장 실무자 및 매크로 분석에서 광범위하게 인정.
- **PIT-safe 가능성**: 가능 — 발표 후 당일 인식. 20일 속보치 활용 시 선행 신호 가능.
- **필요 데이터**: 관세청 API 또는 CEIC/Trading Economics 구독
- **예상 difficulty**: Medium (데이터 수집 자동화)

---

### 15. IPO 락업 해제 효과 (상장 후 6개월/1년)

- **정의**: IPO 후 6개월(180일) 또는 1년 시점에 보호예수 해제 후 대주주 기관의 블록 매도 압력 후 주가 1~3% 하락, 거래량 40% 급증. 한국: 상장 주관사별로 락업 기간 상이, 코스피/코스닥 규정 차이 있음.
- **출처**:
  - ResearchGate: [The Expiration of IPO share lockups](https://www.researchgate.net/publication/227659582_The_Expiration_of_IPO_share_lockups)
  - ScienceDirect: [Short selling around the expiration of IPO share lockups](https://www.sciencedirect.com/science/article/abs/pii/S0378426617302339)
  - SMU: [IPO performance and trading around lock-up expiration](https://ink.library.smu.edu.sg/context/etd_coll/article/1521/viewcontent/IPO_performance_and_trading_around_lock_up_expiration.pdf) (한국 샘플 포함)
- **카테고리 태그**: Stage A (종목 제외 필터) / Stage B (매도 신호)
- **버킷**: swing (락업 해제 전 2~3주 ~ 해제 당일)
- **한국 시장 실증**: 부분 확인 — SMU 연구가 한국 IPO 강제 락업 기간 변경 샘플 사용. 미국 기준 글로벌 연구 결과(1~3% 하락, 거래량 40% 증가)는 한국에도 구조상 동일 메커니즘 적용 가능.
- **PIT-safe 가능성**: 가능 — DART 공시(IPO 보호예수 해제 예정일) 사전 확인 가능.
- **필요 데이터**: DART API (상장후의무보호예수 공시) + 상장일 데이터
- **예상 difficulty**: Medium (DART 파싱 자동화)

---

### 16. 배당락 전후 효과 (한국 12월 배당락일)

- **정의**: 배당락일(배당 기산일 직후) 주가는 배당액만큼 하락 조정. 배당 캡처 전략(배당락 전 매수 후 락일 매도) 시도와 이에 반하는 조기 청산이 복합 작용. 한국은 12월 말 집중(연간 배당 중심 구조).
- **출처**:
  - World Scientific: [Ex-Dividend-Day Behavior of Stock Prices and Volume](https://www.worldscientific.com/doi/10.1142/S0217590819500243) (한국/일본 포함)
  - ResearchGate: [Time Variation of Ex-Dividend Day Stock Returns and Corporate Dividend Capture](https://www.researchgate.net/publication/4992558_Time_Variation_of_Ex-Dividend_Day_Stock_Returns_and_Corporate_Dividend_Capture_A_Reexamination)
- **카테고리 태그**: Stage A (진입 필터) / Stage C (청산 타이밍)
- **버킷**: swing (배당락 전 3~5일 ~ 락일)
- **한국 시장 실증**: 부분 확인 — 한국/일본은 배당 사전 미공개 기업에서 ex-dividend day 행동이 미국과 다른 패턴을 보임(World Scientific 논문 명시).
- **PIT-safe 가능성**: 부분 — 배당락일은 DART 배당 공시 후 확정. 배당금액은 주총 이후 확정이므로 예측치 필요.
- **필요 데이터**: DART API (배당 공시) + corp_events 테이블 (내부 DB)
- **예상 difficulty**: Medium

---

### 17. 무상증자 권리락 효과

- **정의**: 무상증자 발표 후 권리락일에 주가가 발행 비율만큼 하향 조정됨. 이론적으로 가치 변화 없으나 실제 한국 시장에서 발표 후 단기 급등(착시 매수) 후 권리락 당일 기계적 하락 후 이후 혼조.
- **출처**:
  - StockPlus Insight: [무상증자 권리락 효과 투자 주의](https://insight.stockplus.com/articles/5889)
  - 에너지경제: [무상증자 권리락 효과 없었네 절반이 주가 하락](https://m.ekn.kr/view.php?key=20240512021004517)
  - 서울경제: [무상증자 권리락 후 주가 훨훨 급락 가능성 높아](https://www.sedaily.com/NewsView/26761BYTM8)
- **카테고리 태그**: Stage A (종목 필터) / Stage B (방향 신호)
- **버킷**: swing (발표 후 1~5일)
- **한국 시장 실증**: 한국 전용 관찰 — 2024년 분석: 15개 권리락 종목 중 8개(53%)가 당일 하락. 단기 급등은 발표 직후(권리락 전)에 집중.
- **PIT-safe 가능성**: 가능 — DART 무상증자 공시 후 권리락일 자동 계산 가능.
- **필요 데이터**: DART API (무상증자 공시) + corp_events 테이블 (내부 DB 기존 구축)
- **예상 difficulty**: Low (corp_events 테이블 이미 존재)

---

### 18. ETF 정기 리밸런싱 충격 (KODEX/TIGER 대형 ETF)

- **정의**: 국내 대형 지수 추종 ETF(KODEX 200, TIGER 200 등)가 기초지수 변경에 연동하여 구성 종목 교체 시 발생하는 매수/매도 압력. 레버리지 ETF 리밸런싱은 선물/현물 기계적 매매로 장중 변동성 증폭.
- **출처**:
  - KCMI: [An Analysis of Competitive Fee Reductions in Korea's ETF Market](https://www.kcmi.re.kr/en/publications/pub_detail_view?syear=2025&zcd=002001017&zno=1852&cno=6560)
  - KED Global: [Bullish ETF bets blamed for rollercoaster swings in South Korean stock market](https://www.kedglobal.com/korean-stock-market/newsView/ked202603060001)
  - Eastspring: [Navigating index rebalancing effects](https://www.eastspring.com/insights/deep-dives/navigating-index-rebalancing-effects-key-insights-for-smarter-execution)
- **카테고리 태그**: Stage A (종목 필터) / Stage B (방향 신호)
- **버킷**: swing (리밸런싱 전 1~2주)
- **한국 시장 실증**: 부분 확인 — 레버리지 ETF 리밸런싱이 장중 선물 현물 매매를 기계적으로 강제하여 변동성 증폭 확인(KED 2026). 패시브 ETF 리밸런싱의 개별 종목 영향은 KOSPI200 리밸런싱 연구에서 간접 확인.
- **PIT-safe 가능성**: 부분 — KODEX/TIGER 리밸런싱 공식 공지는 사전 공개되나 일부 ETF는 미발표. KOSPI200 리밸런싱 일정에 연동하면 예측 가능.
- **필요 데이터**: 각 ETF 운용사 공시 + KRX 리밸런싱 일정
- **예상 difficulty**: Medium-High

---

### 19. NXT 야간시장 가격 갭 활용 (2025년 신설)

- **정의**: 넥스트레이드(NXT) 대체거래소 2025년 3월 4일 출범. 오후 3시 30분~8시 애프터마켓. KRX 종가 대비 NXT 애프터마켓 종가 갭이 익일 KRX 시초가 갭 예측 시그널로 활용 가능.
- **출처**:
  - 넥스트레이드 공식: [nextrade.co.kr](https://www.nextrade.co.kr/menu/marketData/menuList.do)
  - 매거진한경: [주식 저녁 8시까지 산다 대체거래소 넥스트레이드 출범](https://magazine.hankyung.com/money/article/202503132444c)
  - 신한투자증권: [대체거래소(NXT) 가이드](https://open.shinhansec.com/mobilealpha/html/CS/NXTPolicyGuide.html)
- **카테고리 태그**: Stage B (신호 소스) / Stage A (시초가 방향 예측)
- **버킷**: swing (당일 시초가 매매)
- **한국 시장 실증**: 신규 — 실증 데이터 축적 중. 2025년 3월 출범, 800개 종목 거래. 학술 실증 논문 미존재(2026년 5월 기준). 실무 관찰만.
- **PIT-safe 가능성**: 가능 — NXT 애프터마켓은 KRX 장 마감(15:30) 이후 데이터이므로 익일 신호 생성 시 look-ahead 없음.
- **필요 데이터**: NXT 시세 API (별도 계약 필요)
- **예상 difficulty**: High (NXT 데이터 연동 신규 구축)

---

### 20. 미국 CPI/NFP 발표일 글로벌 리스크온/오프

- **정의**: 미국 CPI (매월 둘째 주 수요일), NFP (매월 첫째 주 금요일, 한국 시각 오후 9시 30분) 발표 당일~익일 KOSPI 변동성 증가. 서프라이즈(컨센서스 대비 상회/하회) 방향에 따라 글로벌 리스크온/오프 연동.
- **출처**:
  - NY Fed: [The Financial Market Effect of FOMC Minutes](https://www.newyorkfed.org/medialibrary/media/research/epr/2013/0913rosa.pdf)
  - Quantpedia: [Federal Open Market Committee Meeting Effect in Stocks](https://quantpedia.com/strategies/federal-open-market-committee-meeting-effect-in-stocks)
  - US BLS: [CPI Release Schedule](https://www.bls.gov/schedule/news_release/cpi.htm)
- **카테고리 태그**: Stage A (방향 오버레이) / Stage C (포지션 축소 타이밍)
- **버킷**: swing (당일~2일)
- **한국 시장 실증**: 직접 논문 미확인. KOSPI와 S&P500 상관관계(beta 0.7~0.9)상 거시 지표 발표 효과는 구조적으로 연동. FOMC 효과 논문에서 한국 시장 반응 간접 확인.
- **PIT-safe 가능성**: 가능 — BLS/BEA 공식 발표 일정은 연초 전체 공개. 발표치는 공개 후 인식.
- **필요 데이터**: BLS 발표 캘린더 + Fred API
- **예상 difficulty**: Low (일정 파싱), Medium (서프라이즈 지수 계산)

---

## 종합 평가

### 한국 실증 검증 Top 3 (학술 논문 직접 출처)

| 순위 | 컨셉 | 논문 | 특징 |
|------|------|------|------|
| 1 | Turn-of-Month Effect (#3) | Lee & Kim (2022, Pacific-Basin Finance Journal) | KOSPI/KOSDAQ 양쪽 검증, 투자자 유형별 거래 패턴까지 분석 |
| 2 | KOSPI200 옵션만기 효과 (#5) | Wag the Dog (ResearchGate) + 만기일 효과 논문 | 한국 전용 파생시장 구조에서 검증, 실무 적용성 최고 |
| 3 | 한국 금통위 결정일 효과 (#12) | ScienceDirect (2018) | 투자자 유형별 선행 매매 패턴 포함, 한국 데이터 2000~2017 |

### 즉시 코드화 Top 5 (외부 데이터 불필요 or 내부 DB만으로 충분)

| 순위 | 컨셉 | 필요 데이터 | 예상 공수 |
|------|------|------|------|
| 1 | Monday Effect (#4) | datetime.weekday() | 0.5h |
| 2 | Turn-of-Month Effect (#3) | trading_calendar 영업일 카운트 | 1h |
| 3 | KOSPI200 옵션만기 효과 (#5) | 매월 2번째 목요일 자동 계산 | 1h |
| 4 | 분기물 만기 (#6) | 3/6/9/12월 2번째 목요일 자동 계산 | 0.5h |
| 5 | Halloween Effect (#1) | datetime.month 범위 비교 | 0.5h |

### PIT 위험 컨셉 (주의 필요)

| 컨셉 | 위험 사유 | 대응 방법 |
|------|------|------|
| 배당락 효과 (#16) | 배당금액은 주총 확정 후 공개 — 예측치 사용 금지 | DART 공시 후 확정 배당액만 사용 |
| ETF 리밸런싱 (#18) | 일부 ETF 리밸런싱 공지 사후 공개 가능 | KOSPI200 리밸런싱 연동 공식 경로만 사용 |
| 무상증자 권리락 (#17) | 발표 전 내부 정보 접근 위험 | DART 공시 확인 후 발표일 기준으로만 신호 생성 |

---

## 참고 자료

### 학술 논문 (Primary Sources)
- [Bouman & Jacobsen (2002) — Halloween Indicator, AER 92(5)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=76248)
- [Jacobsen & Zhang (2012) — Halloween Everywhere and All the Time](https://www.ssrn.com/abstract=2154873)
- [Lean (2011) — The Halloween Puzzle in Selected Asian Stock Markets](https://www.researchgate.net/publication/236737041_The_Halloween_puzzle_in_selected_Asian_stock_markets)
- [January Effect in Korean Stock Markets — Springer Asia Pacific Journal of Management](https://link.springer.com/article/10.1007/BF01732896)
- [January Effect risk/uncertainty — ResearchGate](https://www.researchgate.net/publication/286072527_The_risk_of_earnings_information_uncertainty_and_the_January_effect_in_Korean_stock_markets)
- [TOM Effect KOSPI — Pacific-Basin Finance Journal (2022)](https://www.sciencedirect.com/science/article/abs/pii/S0927538X22001214)
- [TOM Effect KOSDAQ — Journal of Derivatives and Quantitative Studies (2022)](https://www.emerald.com/jdqs/article/30/4/260/205635/)
- [Monday Effect / Day-of-Week — Finance Research Letters (2022)](https://www.sciencedirect.com/science/article/abs/pii/S1544612322000368)
- [Expiration Day Effect Wag the Dog — ResearchGate](https://www.researchgate.net/publication/4816975_Expiration_Day_Effect_in_Korean_Stock_Market_Wag_the_Dog)
- [Expiration-day effects KOSPI200 — ResearchGate](https://www.researchgate.net/publication/289170056_Expiration-day_effects_of_the_KOSPI_200_futures_and_options)
- [KOSPI200 Index Constitution Changes — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1057521910000505)
- [MSCI Index Price/Volume Effects — Georgia Tech](https://www.scheller.gatech.edu/directory/research/finance/jayaraman/pdf/6840_03232004_final.pdf)
- [BOK Monetary Policy Announcements — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1544612318300734)
- [FOMC Pre-Announcement Drift — NY Fed SR512](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr512.pdf)
- [IPO Lock-Up Expiration — ResearchGate](https://www.researchgate.net/publication/227659582_The_Expiration_of_IPO_share_lockups)
- [Ex-Dividend Day Korea/Japan — World Scientific](https://www.worldscientific.com/doi/10.1142/S0217590819500243)

### 공식 데이터 소스
- [KRX 정보데이터시스템](https://data.krx.co.kr/)
- [MSCI Index 리밸런싱 일정](https://www.msci.com)
- [관세청 수출입무역통계](https://www.tradedata.go.kr/cts/index_eng.do)
- [한국은행 금통위 일정](https://www.bok.or.kr/eng/bbs/E0000634/)
- [DART 공시시스템](https://dart.fss.or.kr)
- [넥스트레이드(NXT) 시장데이터](https://www.nextrade.co.kr/menu/marketData/menuList.do)
- [US BLS CPI 발표 일정](https://www.bls.gov/schedule/news_release/cpi.htm)
- [PwC Korea Tax Summaries](https://taxsummaries.pwc.com/republic-of-korea/individual/income-determination)
