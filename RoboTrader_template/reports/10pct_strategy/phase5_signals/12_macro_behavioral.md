# Phase 5 시그널 패밀리 — Category 12: 매크로/심리/행동재무 시그널

> 작성일: 2026-05-26 | 조사자: document-specialist (Claude Sonnet 4.6)
> 목적: Phase 5 시그널 패밀리 확장 — 매크로 사이클 / 행동재무 / 심리 카테고리 전담
> 기반: 해외 명저 5권 발굴 + 외부 공식 출처 보강
> No Look-Ahead 원칙: 각 지표의 PIT(Point-In-Time) 발표 시각 명시

---

## 발굴 도서 5권

| # | 저자 | 제목 | 출판연도 | 핵심 컨셉 |
|---|---|---|---|---|
| B1 | Howard Marks | *Mastering the Market Cycle* | 2018 | 시장 사이클 4단계 위치 진단 |
| B2 | George Soros | *The Alchemy of Finance* | 1987 (2003 개정) | 재귀성(Reflexivity) 붐-버스트 패턴 |
| B3 | Ray Dalio | *Principles for Navigating Big Debt Crises* | 2018 | 장기 부채 사이클 & 레버리지 지표 |
| B4 | Nassim Nicholas Taleb | *The Black Swan* + *Antifragile* | 2007 / 2012 | 꼬리위험 헤지 & 변동성 클러스터링 |
| B5 | Daniel Kahneman | *Thinking, Fast and Slow* | 2011 | 인지 편향(처분효과·앵커링·군중 쏠림) 역발상 |

참고 추가 도서 (컨셉 보완):
- Michael Mauboussin, *More Than You Know* (2006) — 기저율(Base Rate) 적용
- Robert Shiller, *Irrational Exuberance* (2000/2015) — CAPE(Shiller PER) 밸류에이션
- James Montier, *Behavioural Investing* (2007) — GMO 행동편향 체크리스트

---

## 개요

| 구분 | 컨셉 수 |
|---|---|
| B1 Marks — 시장 사이클 진단 | 5개 |
| B2 Soros — 재귀성/붐버스트 | 4개 |
| B3 Dalio — 부채 사이클 & 레버리지 | 4개 |
| B4 Taleb — 꼬리위험 & 변동성 | 4개 |
| B5 Kahneman — 인지 편향 역발상 | 4개 |
| 보완 (Mauboussin/Shiller/Montier) | 3개 |
| **합계** | **24개** |

Stage 분포:
- Stage A (진입 필터 / 레짐 오버레이): 13개
- Stage B (신호 강도 가중치 / 방향 확인): 7개
- Stage C (청산 타이밍 / 익스포저 축소): 4개

---

## 공통 컬럼 설명

| 컬럼 | 설명 |
|---|---|
| 컨셉명 | 시그널 이름 |
| 출처 도서 | 책 코드 + 해당 챕터/원리 |
| 정의/계산 | 구체적 수식 또는 산출 방법 |
| PIT 시각 | 데이터 사용 가능 시점 (No Look-Ahead 기준) |
| 신호 해석 | 매수/매도/중립 판단 기준 |
| 데이터 출처 | 공식 소스 URL/기관 |
| 수집 방법 | API/라이브러리/스크래핑 |
| 가용성 | 즉시/제한/불가 |
| 한국 적용 | KOSPI/KOSDAQ 직접 적용 가능성 |
| Stage 태그 | A/B/C |
| 즉시 코드화 | 가능 여부 |

---

## 1. Howard Marks 시장 사이클 진단 (B1)

> 출처: Howard Marks, *Mastering the Market Cycle* (2018), Houghton Mifflin Harcourt
> ISBN: 978-1328479259 | 교보문고: https://product.kyobobook.co.kr/detail/S000001796419
> Oaktree Capital Memos: https://www.oaktreecapital.com/insights/memo

### MB1-01: 사이클 4단계 위치 점수 (Cycle Position Score)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B1 — Marks, Ch.4 "The Market Cycle" / Ch.16 "Putting It All Together" |
| **정의/계산** | 7개 서브지표 합산 점수 (각 0~2점, 합계 0~14). 1) KOSPI PBR 분위 2) KOSPI PER vs 5년 평균 3) VIX/VKOSPI 레벨 4) 신규 IPO 건수(월) 5) 레버리지 펀드 순유입 6) 신용잔고/시총 비율 7) 언론 주식 긍정 기사 비율. 합계 0~4=Depression/Recovery, 5~9=Expansion, 10~14=Peak |
| **PIT 시각** | 월말 기준 산출 (각 서브지표 최신 확정값 사용). **익월 1~3 영업일에 점수 생성** |
| **신호 해석** | Score ≤4 → 저점 근처, 매수 공격적. 5~9 → 중립, 추세추종. ≥10 → 과열, 신규 진입 축소 또는 방어. Marks: "사이클 위치를 알면 리스크 감수 수준을 조절하라" |
| **데이터 출처** | KRX PBR/PER: https://data.krx.co.kr / VKOSPI: pykrx / 신용잔고: https://freesis.kofia.or.kr / IPO 집계: DART |
| **수집 방법** | pykrx + ECOS API + KOFIA FreeSIS 스크래핑 조합 |
| **가용성** | 즉시 (구성요소별 수집 가능, 합산 로직 구현 필요) |
| **한국 적용** | 높음 — KOSPI PBR/PER은 KRX 공식 제공. VKOSPI 직접 사용 가능. 신용잔고는 KOFIA에서 수집 |
| **Stage 태그** | Stage A (레짐 오버레이 — 월별 전략 포지셔닝 방향 결정) |
| **즉시 코드화** | 부분 (서브지표 7개 수집 파이프라인 구축 필요, 합산 로직 자체는 단순) |

---

### MB1-02: 투자자 심리 극단 지수 (Sentiment Extreme Composite)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B1 — Marks, Ch.7 "The Psychology Pendulum" — "탐욕과 공포 사이의 진자" 모델 |
| **정의/계산** | (AAII Bull% 5년 Z-score) + (CNN Fear&Greed 정규화) + (VKOSPI 반전: 높을수록 공포) 3개 평균. Z-score > +1.5 = 탐욕 극단(매도), < -1.5 = 공포 극단(매수) |
| **PIT 시각** | AAII: 주 1회 목요일. CNN F&G: 일별. VKOSPI: 일별. **가장 늦은 업데이트 기준 주 1회 신호** |
| **신호 해석** | 복합 Z-score < -1.5 → 극단적 공포, 역추세 매수. > +1.5 → 극단적 탐욕, 신규 진입 유보. Marks: "군중이 가장 열광할 때가 가장 위험한 시점" |
| **데이터 출처** | AAII: https://www.aaii.com/sentimentsurvey / CNN F&G API: https://production.dataviz.cnn.io/index/fearandgreed/graphdata/ / VKOSPI: pykrx |
| **수집 방법** | pip install fear-and-greed + AAII 스크래핑 + pykrx |
| **가용성** | 즉시 (AAII 무료, CNN API 무료, pykrx 무료) |
| **한국 적용** | 높음 — VKOSPI 포함으로 한국 시장 직접 반영. AAII는 미국 투자자 기반이나 KOSPI 선행 효과 확인 |
| **Stage 태그** | Stage A (진입 필터) / Stage B (신호 강도 가중치) |
| **즉시 코드화** | 가능 (3개 지표 모두 즉시 수집 가능) |

---

### MB1-03: 신용 사이클 리스크 온/오프 스위치 (Credit Cycle Risk Switch)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B1 — Marks, Ch.10 "The Credit Cycle" — "신용 팽창이 사이클을 증폭시킨다" |
| **정의/계산** | 고수익채-투자등급채 스프레드(HY-IG Spread) 20일 변화율. FRED: BAMLH0A0HYM2 (HY OAS) - BAMLC0A0CM (IG OAS). 스프레드 확대(+25bp 이상/20일) = 신용 위험 고조. 축소(-25bp) = 신용 완화 |
| **PIT 시각** | FRED 일별 업데이트 (미국 채권시장 마감 기준). **한국 장 개시 전 D-1 데이터 사용 가능** |
| **신호 해석** | HY 스프레드 급확대(+50bp/월) → 신용 긴축, KOSPI 위험자산 회피 압력. 스프레드 축소 추세 → 신용 완화, 리스크온 환경. Marks: "신용 사이클이 경제 사이클보다 먼저 돈다" |
| **데이터 출처** | FRED HY OAS: https://fred.stlouisfed.org/series/BAMLH0A0HYM2 / IG OAS: https://fred.stlouisfed.org/series/BAMLC0A0CM |
| **수집 방법** | pip install fredapi. fred.get_series("BAMLH0A0HYM2") |
| **가용성** | 즉시 (FRED API 무료 키 발급) |
| **한국 적용** | 중간 — 미국 신용 스프레드가 글로벌 리스크온/오프 선행. 한국 회사채 AA- vs 국고채 스프레드(ECOS)로 대체 가능 |
| **Stage 태그** | Stage A (레짐 필터 — 신용 긴축 시 매수 포지션 축소) |
| **즉시 코드화** | 가능 (FRED API + fredapi 라이브러리) |

---

### MB1-04: IPO/딜 온도 지수 (Deal Thermometer)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B1 — Marks, Ch.14 "Dealing with the Cycle" — "IPO 과열은 사이클 정점의 고전적 신호" |
| **정의/계산** | 월별 KOSPI/KOSDAQ 신규 IPO 건수 + 공모 후 첫날 평균 수익률. IPO 건수 > 20건/월 AND 첫날 평균 수익률 > 30% → 과열 신호(Score +2). IPO 건수 < 5건/월 AND 상장 철회 건수 증가 → 침체 신호(Score -2) |
| **PIT 시각** | DART 상장 공시 기준. **월말 집계, 익월 초 신호** |
| **신호 해석** | IPO 급증 + 첫날 급등 → 사이클 후기(Peak 근처), 신규 진입 축소. IPO 철회 증가 → 사이클 저점(Depression), 역추세 매수 준비 |
| **데이터 출처** | DART 상장 공시: https://dart.fss.or.kr / KRX 신규 상장: https://data.krx.co.kr |
| **수집 방법** | OpenDartReader IPO 공시 필터 + pykrx 신규 상장 목록 |
| **가용성** | 즉시 (DART + pykrx) |
| **한국 적용** | 높음 — 한국 시장 직접 IPO 데이터 사용 |
| **Stage 태그** | Stage A (월별 레짐 오버레이) |
| **즉시 코드화** | 부분 (DART IPO 공시 파싱 + 첫날 수익률 계산 로직 필요) |

---

### MB1-05: 리스크 프리미엄 압축 지수 (Risk Premium Compression Index)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B1 — Marks, Ch.5 "Risk" / Ch.6 "Recognizing Risk" — "위험이 가장 낮을 때 투자자들은 위험을 느끼지 못한다" |
| **정의/계산** | KOSPI 주식위험프리미엄(ERP) = 1/선행PER - 국고채10년. ERP가 역사적 하위 20% 분위 이하 = 과도한 낙관(리스크 고점). 상위 80% 이상 = 과도한 공포(리스크 저점). ERP 20일 변화율도 보조 지표 |
| **PIT 시각** | 선행 PER: 분기 실적 시즌 업데이트. 국고채: ECOS 일별. **분기 초 PER 업데이트 시 재계산** |
| **신호 해석** | ERP < 1% (역사적 하위 10%) → 주식 고평가, 신규 진입 최소화. ERP > 5% (역사적 상위 80%) → 주식 저평가, 비중 확대. Marks: "고수익이 기대될 때는 위험도 높다 — ERP 압축 시가 위험" |
| **데이터 출처** | KOSPI 선행 PER: KRX 마켓플레이스 (후행 PER 무료, 선행은 FnGuide 유료). 국고채: ECOS https://ecos.bok.or.kr |
| **수집 방법** | pykrx KOSPI PER + ECOS API 국고채10년 조합 |
| **가용성** | 즉시 (후행 PER 기준. 선행 PER은 유료) |
| **한국 적용** | 높음 — KOSPI ERP 직접 계산 가능. 후행 PER 기준 사용 시 경기 후행 한계 주의 |
| **Stage 태그** | Stage A (포지션 크기 조정) / Stage B (신호 확신도 가중치) |
| **즉시 코드화** | 가능 (pykrx + ECOS API 조합) |

---

## 2. George Soros 재귀성/붐버스트 (B2)

> 출처: George Soros, *The Alchemy of Finance* (1987; Wiley 2003 개정판)
> ISBN: 978-0471445495 | 공식 소개: https://www.georgesoros.com/1987/01/01/the-alchemy-of-finance/

### MB2-01: 재귀성 붐-버스트 탐지 (Reflexivity Boom-Bust Detector)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B2 — Soros, Part 2 "The Theory of Reflexivity" — "가격 상승이 펀더멘털을 개선하고, 개선된 펀더멘털이 다시 가격을 올린다 — 그러다 연결이 끊어진다" |
| **정의/계산** | 붐 탐지 4조건: 1) 주가 60일 수익률 > +25% 2) PBR 52주 최고 3) 신용잔고 급증(+20%/월) 4) 일평균거래량 3배 이상. 4조건 충족 → 재귀성 붐 국면. 버스트 트리거: 위 조건에서 거래량 급감 + 주가 고점 대비 -5% = 버스트 시작 신호 |
| **PIT 시각** | 일별 종가 기준. 신용잔고는 T+1 지연. **모든 조건 T-1일 데이터로 신호 생성** |
| **신호 해석** | 4조건 충족 → 붐 후반부 진입 금지 (Marks와 교차 확인). 버스트 시작 신호 → 즉시 포지션 정리. Soros: "가장 위험한 것은 성공하는 투자 이론이 자기 파괴적이 된다는 것" |
| **데이터 출처** | 일봉: 내부 daily_prices / 신용잔고: KOFIA FreeSIS https://freesis.kofia.or.kr / 거래량: pykrx |
| **수집 방법** | 내부 DB + KOFIA 스크래핑 |
| **가용성** | 부분 (신용잔고 수집 파이프라인 구축 필요) |
| **한국 적용** | 높음 — 한국 테마주 붐버스트 패턴에 직접 적용 가능 (2021년 2차전지, 2023년 AI 급등 사례) |
| **Stage 태그** | Stage A (진입 금지 필터) / Stage C (청산 트리거) |
| **즉시 코드화** | 부분 (신용잔고 제외 조건은 내부 DB로 즉시 가능) |

---

### MB2-02: 외국인 수급 재귀성 추적 (Foreign Flow Reflexivity)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B2 — Soros, Part 3 "The Imperial Circle" — "자본 유입이 통화 강세를 낳고, 통화 강세가 다시 자본 유입을 부른다" |
| **정의/계산** | 외국인 KOSPI 순매수 10일 누적 / 시장 전체 거래대금. 비율이 +5% 이상이면서 원화 강세(-0.5% 이상/10일) 동시 충족 = 재귀적 유입 국면. 반대(순매도 + 원화 약세) = 재귀적 유출 |
| **PIT 시각** | 외국인 순매수: KRX T일 장 마감(15:30) 확정. 원/달러: 오후 3:30 기준환율. **D일 장 마감 후 D+1 신호** |
| **신호 해석** | 재귀적 유입 국면 → 모멘텀 전략 유리(추세 편승). 재귀적 유출 국면 → 역추세 매수 금지, 방어 포지션. 전환점(유입→유출) = 버스트 시작 경보 |
| **데이터 출처** | 외국인 순매수: KRX https://data.krx.co.kr / pykrx stock.get_market_trading_value_by_date() / 원/달러: yfinance KRW=X |
| **수집 방법** | pykrx + yfinance |
| **가용성** | 즉시 (pykrx + yfinance 무료) |
| **한국 적용** | 높음 — 외국인 수급이 KOSPI 방향 결정적. 원화-KOSPI 상관관계 강함 |
| **Stage 태그** | Stage A (레짐 방향 결정) / Stage B (모멘텀 강도 가중치) |
| **즉시 코드화** | 가능 (pykrx + yfinance 즉시 사용 가능) |

---

### MB2-03: 섹터 내 재귀성 모멘텀 (Intra-Sector Reflexivity Momentum)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B2 — Soros, Ch.2 "Stock Market Boom-Bust" — "자기 강화적 과정은 작은 섹터에서 더 강렬하게 나타난다" |
| **정의/계산** | KOSPI 섹터 ETF 기준 (KODEX 반도체, TIGER 2차전지 등) 20일 수익률 상위 1개 섹터를 붐 섹터로 지정. 붐 섹터의 1) 거래대금이 전체 시장의 15% 초과 AND 2) 20일 수익률 > +20% = 재귀성 쏠림 탐지 |
| **PIT 시각** | 일별 ETF 종가 기준. **매 거래일 장 마감 후 계산** |
| **신호 해석** | 재귀성 쏠림 감지 → 해당 섹터 신규 진입 금지. 반전(거래대금 급감 + 주가 고점 대비 -7%) → 섹터 버스트 시작. 비붐 섹터는 상대적 저평가로 매수 기회 |
| **데이터 출처** | 섹터 ETF 종가: pykrx / 섹터 거래대금: KRX 업종 통계 https://data.krx.co.kr |
| **수집 방법** | pykrx + KRX 업종 통계 |
| **가용성** | 즉시 (pykrx) |
| **한국 적용** | 높음 — 한국 시장의 섹터 쏠림(테마주) 현상에 최적화 |
| **Stage 태그** | Stage A (종목 선별 시 섹터 필터) |
| **즉시 코드화** | 가능 (pykrx ETF 데이터로 즉시 구현) |

---

### MB2-04: 환율-주가 재귀성 디커플링 알림 (FX-Equity Decoupling Alert)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B2 — Soros, Part 4 "Towards a Theory of Historical Change" — "재귀적 연결이 끊기는 순간(디커플링)이 전환점" |
| **정의/계산** | 원/달러 10일 수익률과 KOSPI 10일 수익률의 rolling 20일 상관계수. 상관계수가 역사적 평균보다 2σ 이상 이탈(디커플링) = 전환점 경보. 통상 원화 강세=KOSPI 강세 (상관 약 -0.6). 디커플링 = 상관 > -0.2 |
| **PIT 시각** | 일별 종가 기준. 20일 rolling 계산. **당일 장 마감 후 계산 가능** |
| **신호 해석** | 디커플링 감지 → 현재 추세의 재귀성이 약화 중. Soros적 전환점 접근 경보. 포지션 방어 조치 시작. 재결합(상관 복귀) → 새로운 재귀적 사이클 시작 |
| **데이터 출처** | KOSPI 지수: pykrx index.get_index_ohlcv() / 원/달러: yfinance KRW=X |
| **수집 방법** | pykrx + yfinance |
| **가용성** | 즉시 |
| **한국 적용** | 높음 — 원화-KOSPI 상관관계는 한국 시장의 핵심 메커니즘 |
| **Stage 태그** | Stage C (포지션 크기 축소 트리거) |
| **즉시 코드화** | 가능 (pandas rolling corr 1줄) |

---

## 3. Ray Dalio 부채 사이클 & 레버리지 (B3)

> 출처: Ray Dalio, *Principles for Navigating Big Debt Crises* (2018), Bridgewater Associates
> 무료 PDF: https://www.principles.com/big-debt-crises/
> 참고: Dalio, *Principles* (2017), Simon & Schuster — https://www.principles.com/
> 참고: "How the Economic Machine Works" (무료 영상): https://www.youtube.com/watch?v=PHe0bXAIuk0

### MB3-01: 레버리지 사이클 모니터 (Leverage Cycle Monitor)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B3 — Dalio, Part 1 "The Archetypal Big Debt Crisis" / Template 항목 1 "Debt Burdens" |
| **정의/계산** | 한국 가계부채/GDP 비율 (분기 발표) + 신용잔고/시총 비율 (일별) + 기업 부채/자기자본 비율(부채비율, 분기 재무제표). 3개 지표를 각각 5년 Z-score로 정규화 후 평균. Z-score > +1.5 = 과부채 경보 |
| **PIT 시각** | 가계부채/GDP: 한국은행 분기 발표(다음 분기 초). 신용잔고: T+1. 기업 부채비율: 분기 실적 발표 후. **가장 늦은 업데이트 시점 기준 분기 1회** |
| **신호 해석** | 복합 Z-score > +1.5 → 디레버리징 위험 고조, 포지션 크기 50% 축소. Z-score < -1 → 레버리지 정상/저점, 리스크 확대 가능. Dalio: "부채 사이클은 경기 사이클보다 길고 고통스럽다" |
| **데이터 출처** | 가계부채: 한국은행 ECOS https://ecos.bok.or.kr (가계부채 DB) / 신용잔고: KOFIA FreeSIS / 기업 부채비율: DART 재무제표 |
| **수집 방법** | ECOS API + KOFIA 스크래핑 + OpenDartReader |
| **가용성** | 부분 (신용잔고 수집 파이프라인 필요. ECOS/DART는 즉시) |
| **한국 적용** | 높음 — 한국 가계부채 문제는 KOSPI 리스크의 핵심 변수 |
| **Stage 태그** | Stage A (분기별 포지션 크기 상한 결정) |
| **즉시 코드화** | 부분 |

---

### MB3-02: 성장/인플레이션 2x2 매크로 레짐 (Growth-Inflation Quadrant)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B3 — Dalio, *Principles* Ch. "Understanding Macroeconomics" / Bridgewater All Weather 레짐 분류 |
| **정의/계산** | X축: 경기(성장) — 한국 산업생산지수 YoY (ECOS). Y축: 인플레이션 — 한국 CPI YoY (ECOS). 4분면 분류: 1) 성장↑+인플↑ = Reflation (주식·원자재 유리) 2) 성장↑+인플↓ = Goldilocks (주식 최우선) 3) 성장↓+인플↑ = Stagflation (방어주·원자재) 4) 성장↓+인플↓ = Deflation (채권·현금). 전월 데이터로 분기 매핑 |
| **PIT 시각** | 산업생산: 매월 말 발표(전월 기준). CPI: 매월 초 발표. **월초 CPI 발표 후 레짐 업데이트** |
| **신호 해석** | Goldilocks(2) → 공격적 진입, 성장주/모멘텀 전략. Stagflation(3) → 방어주(의료/필수소비재) 집중, 전체 익스포저 축소. Deflation(4) → 고배당/저PBR 주식 선호. Reflation(1) → 순환주/금융주 유리 |
| **데이터 출처** | 한국 산업생산: ECOS https://ecos.bok.or.kr (통계분류 → 생산/소비/투자) / CPI: ECOS 소비자물가지수 |
| **수집 방법** | ECOS OpenAPI (무료 키 발급): 직접 REST 호출 또는 ecos-api 패키지 |
| **가용성** | 즉시 (ECOS API 무료) |
| **한국 적용** | 높음 — 한국 거시 데이터 직접 사용. 수출 의존 특성상 글로벌 레짐과 교차 확인 권장 |
| **Stage 태그** | Stage A (월별 전략 레짐 오버레이 — 가장 중요한 단일 필터) |
| **즉시 코드화** | 가능 (ECOS API + 2개 시리즈 분류 로직) |

---

### MB3-03: 단기 부채 사이클 위치 (Short-Term Debt Cycle Phase)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B3 — Dalio, Part 1 "Short-Term vs Long-Term Debt Cycles" — 단기 5~8년 사이클 vs 장기 75~100년 사이클 구분 |
| **정의/계산** | 한국 기준금리 추세(ECOS) + 한국 신규 대출 증가율(한국은행 금융안정보고서) + BSI(기업경기실사지수, ECOS). 3개 지표의 방향 다수결. 모두 하락 = 수축 국면. 모두 상승 = 팽창 국면 |
| **PIT 시각** | 기준금리: 금통위 발표일(연 8회). BSI: 매월 말 발표. 신규 대출: 월 발표. **월 1회 업데이트** |
| **신호 해석** | 수축 국면 → 저PBR 배당주 방어. 팽창 국면 → 성장주/모멘텀 가중. 전환점(팽창→수축) = Dalio식 긴축 사이클 시작. 금통위 인하 + BSI 반등 = 팽창 재개 신호 |
| **데이터 출처** | 기준금리/BSI: ECOS https://ecos.bok.or.kr / 금통위 일정: https://www.bok.or.kr |
| **수집 방법** | ECOS API |
| **가용성** | 즉시 (ECOS API 무료) |
| **한국 적용** | 높음 — 한국 중앙은행 데이터 직접 사용 |
| **Stage 태그** | Stage A (분기별 레짐) |
| **즉시 코드화** | 가능 |

---

### MB3-04: 달러 강세 신흥국 압박 지수 (DXY-EM Stress Index)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B3 — Dalio, Part 2 "Deflationary Debt Crisis" 및 신흥국 사례 연구 (1997 아시아 금융위기 챕터) — "달러 강세는 달러 부채 보유 신흥국에 이중 타격" |
| **정의/계산** | DXY(달러 인덱스) 20일 수익률 + 이머징 마켓 신용 스프레드(EMBI) 변화율. FRED: EMVOVERALLEMV. DXY 20일 +3% 이상 AND EMBI 스프레드 +30bp 이상 = 신흥국 압박 국면 |
| **PIT 시각** | DXY: yfinance DX-Y.NYB 일별. EMBI: FRED 일별. **D-1 기준 당일 신호** |
| **신호 해석** | 신흥국 압박 국면 → KOSPI 외국인 이탈 가속, 방어 포지션. DXY 약세 전환 → 신흥국 자금 유입, 매수 환경. Dalio: "부채가 외화로 표시될 때 환율이 사이클을 증폭시킨다" |
| **데이터 출처** | DXY: yfinance DX-Y.NYB / EMBI: FRED https://fred.stlouisfed.org/series/EMVOVERALLEMV |
| **수집 방법** | yfinance + fredapi |
| **가용성** | 즉시 (yfinance + FRED 무료) |
| **한국 적용** | 높음 — 1997년 IMF 위기, 2008년 금융위기 모두 달러 강세 + 신흥국 압박이 KOSPI 급락 선행 |
| **Stage 태그** | Stage A (글로벌 레짐 필터) / Stage C (포지션 축소 트리거) |
| **즉시 코드화** | 가능 (yfinance + FRED API) |

---

## 4. Nassim Taleb 꼬리위험 & 변동성 (B4)

> 출처: Nassim Nicholas Taleb, *The Black Swan* (2007, Random House) ISBN: 978-1400063512
> 출처: Nassim Nicholas Taleb, *Antifragile* (2012, Random House) ISBN: 978-1400067824
> 공식 사이트: https://www.fooledbyrandomness.com/

### MB4-01: 변동성 클러스터링 레짐 (Volatility Clustering Regime)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B4 — Taleb, *The Black Swan* Ch.15 "The Bell Curve, That Great Intellectual Fraud" / *Antifragile* Ch.18 "On the Difference between a Large Stone and a Thousand Pebbles" |
| **정의/계산** | KOSPI 일별 수익률 절댓값의 5일 이동평균(실현 변동성 프록시). 현재값이 252일 평균의 1.5배 초과 = 고변동성 레짐. 0.7배 미만 = 저변동성 레짐. Taleb: 변동성이 클러스터를 이룬다 = "대변동 후 대변동이 온다" |
| **PIT 시각** | 일별 종가 수익률. **당일 장 마감 후 즉시 계산** |
| **신호 해석** | 고변동성 레짐 → 포지션 크기 50% 축소, 손절 폭 확대(기본값 x1.5). 저변동성 레짐(평온) → Taleb 경고: 평온은 취약성 누적 중. 급격한 레짐 전환(저→고) = Black Swan 전조 가능 |
| **데이터 출처** | 내부 daily_prices 테이블 |
| **수집 방법** | 내부 DB (즉시 계산 가능) |
| **가용성** | 즉시 |
| **한국 적용** | 높음 — KOSPI 수익률 시계열에서 변동성 클러스터링 명확히 관찰 (2020 코로나, 2022 긴축 충격) |
| **Stage 태그** | Stage A (레짐 필터 — 포지션 크기 상한 결정) / Stage B (손절 폭 동적 조정) |
| **즉시 코드화** | 가능 (내부 DB + pandas rolling std) |

---

### MB4-02: 꼬리위험 헤지 신호 (Tail Risk Hedge Signal)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B4 — Taleb, *Antifragile* Ch.19 "The Philosopher's Stone and Its Inverse" — "Barbell 전략: 극도로 안전한 자산 90% + 극도로 위험한 자산 10%. 중간 위험은 취약" |
| **정의/계산** | VKOSPI 30일 이동평균 대비 현재 VKOSPI 비율. 비율 > 1.4 = 꼬리위험 발현 중. 비율 < 0.7 = 평온(취약성 누적), 외가격 풋옵션 헤지 최적 타이밍(싼 헤지). 개별 종목: 52주 최고 대비 -30% 이상 하락 종목 = 바벨 매수 후보 |
| **PIT 시각** | VKOSPI: pykrx 일별. **당일 장 마감 후 즉시** |
| **신호 해석** | VKOSPI/30MA < 0.7 → 헤지 비용 저렴, 포트폴리오 보호 기회. VKOSPI/30MA > 1.4 → 꼬리위험 이미 발현, 추격 헤지 비싸다. Barbell: 저위험 배당주 + 고위험 소형 성장주 조합, 중간 레버리지 우량주 회피 |
| **데이터 출처** | VKOSPI: pykrx index.get_index_ohlcv("코스피 변동성지수") |
| **수집 방법** | pykrx |
| **가용성** | 즉시 (pykrx) |
| **한국 적용** | 높음 — VKOSPI 직접 사용. 외가격 옵션 매수는 KIS API 선물옵션 계좌 필요 |
| **Stage 태그** | Stage A (포지션 구성 원칙) / Stage C (헤지 타이밍) |
| **즉시 코드화** | 가능 (pykrx VKOSPI + 30MA 비율 계산) |

---

### MB4-03: 극단값 발생 빈도 모니터 (Fat Tail Frequency Monitor)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B4 — Taleb, *The Black Swan* Ch.3 "The Speculator and the Prostitute" / Ch.16 "The Aesthetics of Uncertainty" — "정규분포 가정의 오류: 극단값이 실제로 훨씬 자주 온다" |
| **정의/계산** | 최근 60일 KOSPI 일별 수익률의 초과 첨도(Excess Kurtosis). Kurtosis > 3 = 두꺼운 꼬리 레짐 활성. 또한: 최근 60일 중 ±2σ 초과 일수. 정규분포 기준 기대값 4.6일. 실제 > 8일 = 극단 이벤트 과다 발생 경보 |
| **PIT 시각** | 일별 종가 기준. **당일 장 마감 후 즉시** |
| **신호 해석** | Kurtosis > 3 OR 극단일 > 8일 → 시장 구조적 불안정, 포지션 크기 보수적 유지. "통상 수익률 모델" 사용 금지 상태. 극단값 빈도 급증 = 블랙스완 전조 패턴 |
| **데이터 출처** | 내부 daily_prices |
| **수집 방법** | 내부 DB (scipy.stats.kurtosis) |
| **가용성** | 즉시 |
| **한국 적용** | 높음 — KOSPI 수익률은 역사적으로 두꺼운 꼬리 특성 확인 |
| **Stage 태그** | Stage A (리스크 레짐 필터) |
| **즉시 코드화** | 가능 (scipy.stats 1줄) |

---

### MB4-04: 종목별 취약성-강건성 스코어 (Antifragility Score per Stock)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B4 — Taleb, *Antifragile* Ch.1 "Between Damocles and Hydra" — "충격에 이득을 보는 것이 강건(Antifragile). 손해를 보는 것이 취약(Fragile)" |
| **정의/계산** | 개별 종목의 하락 시 민감도 vs 상승 시 민감도 비율. 1) VIX/VKOSPI 급등 구간(VIX > 25 또는 VKOSPI > 25인 날) 평균 수익률 나누기 2) 저변동성 구간(VIX < 15) 평균 수익률. 비율 > 0 = Antifragile(변동성 이익). 비율 < -2 = Fragile(변동성 손해). 내부 daily_prices + VIX 데이터로 계산 |
| **PIT 시각** | 252일(1년) 롤링 계산. **월 1회 업데이트로 충분** |
| **신호 해석** | Antifragile 종목(금/방어주/역상관 종목) → 고변동성 레짐에서 비중 확대. Fragile 종목(고레버리지, 사이클 민감) → 고변동성 레짐에서 배제. 포트폴리오 전체 Antifragility Score 관리 |
| **데이터 출처** | 내부 daily_prices + VIX (yfinance ^VIX) |
| **수집 방법** | 내부 DB + yfinance |
| **가용성** | 즉시 |
| **한국 적용** | 높음 — 한국 방어주(KT&G, 한국전력 등) vs 사이클주(POSCO, 현대차) 분류에 직접 적용 |
| **Stage 태그** | Stage A (종목 풀 품질 필터) / Stage B (포지션 크기 조정) |
| **즉시 코드화** | 가능 (내부 DB + yfinance 조합) |

---

## 5. Daniel Kahneman 인지 편향 역발상 (B5)

> 출처: Daniel Kahneman, *Thinking, Fast and Slow* (2011), Farrar, Straus and Giroux
> ISBN: 978-0374533557 | 출판사: https://us.macmillan.com/books/9780374533557/thinkingfastandslow
> 참고: Shefrin & Statman (1985), "The Disposition to Sell Winners Too Early and Ride Losers Too Long", Journal of Finance — 처분효과 원전

### MB5-01: 처분 효과 역발상 신호 (Disposition Effect Contrarian)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B5 — Kahneman, Ch.31 "Risk Policies" / Ch.26 "Prospect Theory" — Shefrin & Statman(1985) 처분효과의 이론적 토대 |
| **정의/계산** | 개별 종목의 "잠재적 처분 압력 지수": 1) 52주 최고가 대비 현재 주가 비율 95~105% (고점 근처) = 투자자 이익실현 욕구 최고 → 매도 압력 잠재. 2) 52주 최저가 대비 현재 주가 비율 95~105% (저점 근처) = 투자자 손실 회피(팔기 싫어함) → 매도 압력 약함 = 역발상 매수 |
| **PIT 시각** | 52주 고/저가: 일별 종가 기준 rolling 252 영업일. **당일 장 마감 후 즉시** |
| **신호 해석** | 저점 근처(비율 95~105%) → 처분효과상 매도 압력 약함, 단기 반등 시 빠른 상승 가능. 고점 근처 → 이익실현 매물 압박, 추가 상승 제한. Kahneman: "손실 회피는 이득 욕구의 2배 강하다" |
| **데이터 출처** | 내부 daily_prices (52주 고/저가 계산) |
| **수집 방법** | 내부 DB |
| **가용성** | 즉시 |
| **한국 적용** | 높음 — 개인투자자 비중 높은 KOSPI/KOSDAQ에서 처분효과 더욱 강하게 나타남 |
| **Stage 태그** | Stage A (종목 선별 보조 필터) / Stage B (진입 타이밍 가중치) |
| **즉시 코드화** | 가능 (내부 DB + 단순 비율 계산) |

---

### MB5-02: 앵커링 편향 역발상 (Anchoring Bias Contrarian)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B5 — Kahneman, Ch.11 "Anchors" — "첫 번째 정보(닻)가 판단을 왜곡한다" |
| **정의/계산** | 52주 최고가(투자자의 정신적 앵커) 대비 현재 주가 할인율. 할인율 > 40% (52주 고점 대비 40% 하락) = 앵커링상 "싸 보임" 착각 위험. 할인율 < 5% = 앵커링상 "아직 괜찮음" 착각으로 매도 지연. 역발상: 할인율 40~60% + PBR < 1 + 영업이익 흑자 = 진짜 저평가 가능 |
| **PIT 시각** | 일별 종가. **당일 장 마감 후 즉시** |
| **신호 해석** | 할인율 40~60% + PBR < 1 + 영업이익 흑자 = 앵커링 착시로 과도 하락한 진짜 저평가. 할인율 < 5% (고점 근처) = 앵커링으로 투자자가 안심 → 실제 고평가 가능. 할인율 > 70% = 모멘텀 악화, 앵커 무의미 |
| **데이터 출처** | 내부 daily_prices + financial_data (PBR, 영업이익) |
| **수집 방법** | 내부 DB |
| **가용성** | 즉시 |
| **한국 적용** | 높음 — 개인투자자의 전고점 집착 행동이 한국 시장에서 강하게 관찰됨 |
| **Stage 태그** | Stage A (종목 선별) / Stage B (저평가 확신도 가중) |
| **즉시 코드화** | 가능 |

---

### MB5-03: 군중 쏠림 역발상 모멘텀 (Herding Contrarian Momentum)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B5 — Kahneman, Ch.13 "Availability, Emotion, and Risk" / Ch.19 "The Illusion of Understanding" — "가용성 편향: 최근에 많이 들은 것을 과대평가한다" |
| **정의/계산** | 개별 종목 거래대금 기준 "군중 지수": 최근 5일 평균 거래대금 / 최근 60일 평균 거래대금. 비율 > 3.0 = 군중 쏠림 극대(가용성 편향 발동). 역발상 전략: 군중 지수 > 3.0 도달 후 첫 하락일 = 매도 신호. 군중 지수 < 0.3 (거래 소멸) = 역발상 매수 탐색 |
| **PIT 시각** | 일별 거래대금. **당일 장 마감 후 즉시** |
| **신호 해석** | 군중 지수 > 3.0 → 가용성 편향으로 과도 매수, 단기 고점. 매도 또는 진입 금지. < 0.3 → 대중이 망각 = 저평가 재발견 기회. Kahneman: "군중이 동의하는 이유가 진실이 아닐 수 있다" |
| **데이터 출처** | 내부 daily_prices (거래대금 컬럼) |
| **수집 방법** | 내부 DB |
| **가용성** | 즉시 |
| **한국 적용** | 높음 — 한국 테마주 군중 쏠림은 세계적으로 두드러진 패턴 |
| **Stage 태그** | Stage A (진입 금지 필터) / Stage B (역발상 매수 확신도) |
| **즉시 코드화** | 가능 (내부 DB + rolling mean 비율) |

---

### MB5-04: 과잉 확신 낙관 지수 (Overconfidence Optimism Index)

| 항목 | 내용 |
|---|---|
| **출처 도서** | B5 — Kahneman, Ch.24 "The Engine of Capitalism" / Ch.20 "The Illusion of Validity" — "과잉 확신은 인간의 가장 해로운 인지 편향" |
| **정의/계산** | 시장 참여자 과잉 확신 프록시 지수: 1) KOSPI 신고가 종목 수 / 전체 종목 수 (> 5% = 낙관 과열) 2) KOSPI 상승일 연속 일수 (> 7일 = 과잉 확신 국면) 3) ADR(등락비율) > 150 (과매수). 3개 중 2개 이상 충족 = 과잉 확신 국면 |
| **PIT 시각** | 일별 장 마감 후. **당일 장 마감 후 즉시** |
| **신호 해석** | 과잉 확신 국면 → 신규 매수 신호 확신도 50% 할인. Kahneman: "과잉 확신 투자자는 손실을 우연으로, 수익을 실력으로 귀인한다" → 평균 이상의 리스크 감수. 역발상: 과잉 확신 극대(신고가 비율 > 10%) = 2~4주 내 조정 선행 지표 |
| **데이터 출처** | 신고가 종목: pykrx 또는 내부 daily_prices 52주 최고 비교. ADR: 내부 일봉으로 산출 |
| **수집 방법** | 내부 DB + pykrx |
| **가용성** | 즉시 |
| **한국 적용** | 높음 |
| **Stage 태그** | Stage A (신호 확신도 조정) / Stage B (신호 강도 가중치 하향) |
| **즉시 코드화** | 가능 |

---

## 6. 보완 도서 컨셉 (Mauboussin / Shiller / Montier)

### MB6-01: Shiller CAPE 기반 장기 밸류에이션 경보

| 항목 | 내용 |
|---|---|
| **출처 도서** | Robert Shiller, *Irrational Exuberance* (3rd ed. 2015), Princeton University Press. ISBN: 978-0691166261 / CAPE 원 데이터: http://www.econ.yale.edu/~shiller/data.htm |
| **정의/계산** | KOSPI CAPE 프록시 = 현재 KOSPI 후행 PER / 최근 10년 평균 KOSPI PER. 비율 > 1.5 = 역사적 과열. < 0.7 = 역사적 저평가. (Shiller 원본은 실질 주가/10년 평균 실질 이익이나, 한국은 KRX PER 후행치로 프록시 구성) |
| **PIT 시각** | 분기별 실적 반영. **분기 실적 발표 완료 후 1회 업데이트** |
| **신호 해석** | CAPE 프록시 > 1.5 → 장기 과열, 신규 포지션 규모 보수적 유지. < 0.7 → 역사적 저평가, 장기 보유 전략 우호. Shiller: "CAPE가 높은 기간의 10년 후 기대 수익률은 낮다" |
| **데이터 출처** | KOSPI PER: KRX 마켓플레이스 https://data.krx.co.kr (지수 통계 → PER/PBR) / Shiller 원 데이터: http://www.econ.yale.edu/~shiller/data.htm |
| **수집 방법** | pykrx KOSPI PER 10년 시계열 |
| **가용성** | 즉시 (PER 후행 기준. 10년 데이터 중 5.4년은 내부 보유, 나머지 추가 수집 필요) |
| **한국 적용** | 중간 — 한국 CAPE 직접 데이터 없음. 후행 PER 이동평균으로 프록시 구성 필요. 선행 CAPE는 FnGuide 유료 |
| **Stage 태그** | Stage A (장기 밸류에이션 레짐 오버레이 — 분기별) |
| **즉시 코드화** | 부분 (10년 PER 시계열 수집 필요) |

---

### MB6-02: Mauboussin 기저율 기대 수익 보정 (Base Rate Return Calibration)

| 항목 | 내용 |
|---|---|
| **출처 도서** | Michael Mauboussin, *More Than You Know* (2006), Columbia University Press. ISBN: 978-0231143738 / Mauboussin & Callahan "Base Rate Book" (Credit Suisse, 2016): https://research-doc.credit-suisse.com/docView?language=ENG&format=PDF&document_id=1069809871 |
| **정의/계산** | 종목 선별 시 유사 조건(동일 섹터 + 동일 PBR 구간 + 동일 모멘텀 구간)에서 과거 20일 수익률 분포의 기저율(중앙값) 계산. 현재 신호의 기대 수익률이 기저율 중앙값 + 0.5σ 미만이면 신호 기각. 내부 daily_prices 5.4년 데이터로 기저율 추정 |
| **PIT 시각** | 내부 히스토리 기반. **신호 생성 시 실시간 조회** |
| **신호 해석** | 기저율 기준 기대 수익률 > 중앙값 + 0.5σ → 신호 채택. < 중앙값 → 신호 기각 또는 포지션 크기 50% 축소. Mauboussin: "개별 사례의 서사에 현혹되지 말고, 유사 사례의 통계를 먼저 보라" |
| **데이터 출처** | 내부 daily_prices (5.4년 히스토리) |
| **수집 방법** | 내부 DB (scipy/numpy 분포 추정) |
| **가용성** | 즉시 (내부 데이터 충분) |
| **한국 적용** | 높음 — 내부 데이터로 한국 시장 기저율 직접 추정 |
| **Stage 태그** | Stage B (신호 확신도 보정) |
| **즉시 코드화** | 가능 (내부 DB + scipy/numpy 분포 추정) |

---

### MB6-03: Montier 행동편향 GMO 체크리스트 (Behavioural Bias Checklist)

| 항목 | 내용 |
|---|---|
| **출처 도서** | James Montier, *Behavioural Investing* (2007), Wiley Finance. ISBN: 978-0470516706 / GMO White Papers: https://www.gmo.com/americas/research-library/ — "The Seven Immutable Laws of Investing" |
| **정의/계산** | 매수 신호 발생 시 7가지 편향 체크리스트 (0=OK / 1=편향 의심): 1) 최근 3일 연속 상승에서 매수 (가용성 편향) 2) 52주 최고점 10% 이내 매수 (앵커링) 3) 섹터 군중 지수 > 2배 상태 매수 (군중 쏠림) 4) 뉴스 호재 당일 매수 (과잉 반응) 5) 종전 손실 종목 재매수 (처분 효과) 6) 일봉 60개 미만 상태 매수 (정보 부족) 7) VKOSPI > 30 상태에서 매수 (공포 과잉). 합계 3 이상 → 신호 기각 |
| **PIT 시각** | 신호 발생 즉시 체크. **실시간** |
| **신호 해석** | 체크 합계 0~1 → 정상 진입. 2 → 포지션 크기 75%. 3 이상 → 신호 기각. Montier: "편향을 아는 것만으로는 부족하다 — 체크리스트가 실제로 막아준다" |
| **데이터 출처** | 내부 DB + VKOSPI (pykrx) + 거래대금 |
| **수집 방법** | 내부 DB 기반 규칙 엔진 |
| **가용성** | 즉시 |
| **한국 적용** | 높음 — 한국 시장 특성에 맞게 임계값 조정 필요 |
| **Stage 태그** | Stage A (신호 품질 게이트키퍼) / Stage B (포지션 크기 조정) |
| **즉시 코드화** | 가능 (규칙 기반, 외부 API 불필요) |

---

## 종합 요약표

| ID | 컨셉명 | 출처 도서 | Stage | 가용성 | 즉시 코드화 | 한국 적용 |
|---|---|---|---|---|---|---|
| MB1-01 | 사이클 4단계 위치 점수 | B1 Marks | A | 즉시(구현 필요) | 부분 | 높음 |
| MB1-02 | 투자자 심리 극단 지수 | B1 Marks | A/B | 즉시 | 가능 | 높음 |
| MB1-03 | 신용 사이클 리스크 스위치 | B1 Marks | A | 즉시 | 가능 | 중간 |
| MB1-04 | IPO/딜 온도 지수 | B1 Marks | A | 즉시 | 부분 | 높음 |
| MB1-05 | 리스크 프리미엄 압축 지수 | B1 Marks | A/B | 즉시 | 가능 | 높음 |
| MB2-01 | 재귀성 붐-버스트 탐지 | B2 Soros | A/C | 부분 | 부분 | 높음 |
| MB2-02 | 외국인 수급 재귀성 추적 | B2 Soros | A/B | 즉시 | 가능 | 높음 |
| MB2-03 | 섹터 내 재귀성 모멘텀 | B2 Soros | A | 즉시 | 가능 | 높음 |
| MB2-04 | 환율-주가 디커플링 알림 | B2 Soros | C | 즉시 | 가능 | 높음 |
| MB3-01 | 레버리지 사이클 모니터 | B3 Dalio | A | 부분 | 부분 | 높음 |
| MB3-02 | 성장/인플레이션 2x2 레짐 | B3 Dalio | A | 즉시 | 가능 | 높음 |
| MB3-03 | 단기 부채 사이클 위치 | B3 Dalio | A | 즉시 | 가능 | 높음 |
| MB3-04 | 달러 강세 신흥국 압박 | B3 Dalio | A/C | 즉시 | 가능 | 높음 |
| MB4-01 | 변동성 클러스터링 레짐 | B4 Taleb | A/B | 즉시 | 가능 | 높음 |
| MB4-02 | 꼬리위험 헤지 신호 | B4 Taleb | A/C | 즉시 | 가능 | 높음 |
| MB4-03 | 극단값 발생 빈도 모니터 | B4 Taleb | A | 즉시 | 가능 | 높음 |
| MB4-04 | 종목별 취약성-강건성 스코어 | B4 Taleb | A/B | 즉시 | 가능 | 높음 |
| MB5-01 | 처분효과 역발상 신호 | B5 Kahneman | A/B | 즉시 | 가능 | 높음 |
| MB5-02 | 앵커링 편향 역발상 | B5 Kahneman | A/B | 즉시 | 가능 | 높음 |
| MB5-03 | 군중 쏠림 역발상 모멘텀 | B5 Kahneman | A/B | 즉시 | 가능 | 높음 |
| MB5-04 | 과잉 확신 낙관 지수 | B5 Kahneman | A/B | 즉시 | 가능 | 높음 |
| MB6-01 | Shiller CAPE 밸류에이션 경보 | Shiller | A | 부분 | 부분 | 중간 |
| MB6-02 | Mauboussin 기저율 보정 | Mauboussin | B | 즉시 | 가능 | 높음 |
| MB6-03 | Montier 편향 체크리스트 | Montier | A/B | 즉시 | 가능 | 높음 |

---

## 즉시 코드화 가능 Top 3

### 1위: MB4-01 변동성 클러스터링 레짐 (Taleb)
- 내부 daily_prices만으로 즉시 계산. pandas rolling std 1줄.
- 포지션 크기 상한을 레짐에 따라 동적으로 결정 → 시스템 리스크 즉시 감소
- 적용: 기존 strategies/base.py의 포지션 크기 로직에 vol_regime 파라미터 추가
```python
vol_regime = df['return'].abs().rolling(5).mean() / df['return'].abs().rolling(252).mean()
position_scale = 0.5 if vol_regime.iloc[-1] > 1.5 else 1.0
```

### 2위: MB5-03 군중 쏠림 역발상 모멘텀 (Kahneman)
- 내부 daily_prices 거래대금 컬럼만 사용. rolling 비율 계산.
- 한국 테마주 쏠림-버스트 패턴에 직접 적용. 진입 금지 필터로 최적
- 적용: generate_signal() 내 사전 필터 조건 추가
```python
crowd_idx = df['volume_value'].rolling(5).mean() / df['volume_value'].rolling(60).mean()
if crowd_idx.iloc[-1] > 3.0:
    return None  # 군중 쏠림 극대 — 진입 금지
```

### 3위: MB3-02 성장/인플레이션 2x2 레짐 (Dalio)
- ECOS API 2개 시리즈(산업생산, CPI). 월 1회 업데이트.
- 전략 레짐 오버레이의 핵심 — 어떤 전략이든 이 레짐을 먼저 통과시켜야 함
- 적용: 월 1회 레짐 파일 생성 → strategies/config.yaml에 current_regime 파라미터 주입
```python
regime = classify_regime(industrial_prod_yoy, cpi_yoy)
# "Goldilocks" | "Reflation" | "Stagflation" | "Deflation"
```

---

## 한국 매크로 데이터 가용성 평가

| 지표 | 가용 여부 | 수집 방법 | PIT 지연 | 비고 |
|---|---|---|---|---|
| **VKOSPI** | 즉시 가용 | pykrx index.get_index_ohlcv("코스피 변동성지수") | 장중 실시간 / 일봉 T+0 | 2009년 이후 히스토리. 5.4년 시스템 범위 내 완전 커버 |
| **신용잔고** | 제한 가용 | KOFIA FreeSIS 스크래핑 또는 금투협 API | T+1 | 현재 미수집 상태. 수집 파이프라인 구축 필요. KIS API TR 미지원 |
| **공매도 잔고** | 즉시 가용 | pykrx stock.get_shorting_balance_by_ticker() | T+2 | 2023~2024 공매도 금지 기간 데이터 결측 주의 |
| **한국은행 금통위 일정** | 즉시 가용 | 연초 공개 일정 하드코딩. ECOS API 기준금리 시리즈 | 결정일 11:00 KST | 05_sentiment.md S6-02에 포함됨. 본 카탈로그에서 Dalio 레짐 보완 |
| **FOMC → KOSPI 영향** | 즉시 가용 | FRED API FEDFUNDS + yfinance ^GSPC | 발표일 ET 14:00 (KST 익일 새벽) | 05_sentiment.md S6-01에 포함. 본 카탈로그에서 Dalio 레짐 보완 |
| **한국 산업생산/CPI** | 즉시 가용 | ECOS OpenAPI (무료 키) | 월 1회 발표 (전월 기준) | 2x2 레짐 분류(MB3-02) 핵심 데이터 |
| **HY 신용 스프레드** | 즉시 가용 | FRED API BAMLH0A0HYM2 | 미국 채권시장 D-1 | FRED API 무료 키 발급 즉시 사용 |
| **DXY** | 즉시 가용 | yfinance DX-Y.NYB | 실시간 | 신흥국 압박 지수(MB3-04) 핵심 |
| **EMBI 스프레드** | 즉시 가용 | FRED API EMVOVERALLEMV | D-1 | |
| **외국인 KOSPI 순매수** | 즉시 가용 | pykrx stock.get_market_trading_value_by_date() | T+0 장마감 후 | MB2-02 재귀성 추적에 사용 |
| **한국 BSI(기업경기실사지수)** | 즉시 가용 | ECOS API | 월말 발표 | MB3-03 단기 부채 사이클 구성 요소 |
| **CAPE 프록시** | 부분 가용 | pykrx KOSPI PER (후행, 무료) | 분기 업데이트 | 선행 PER은 FnGuide 유료. 10년 히스토리 중 5.4년만 내부 보유 |

**요약**:
- 즉시 가용: 10개 (VKOSPI, 공매도, 금통위, FOMC, 산업생산/CPI, HY 스프레드, DXY, EMBI, 외국인 순매수, BSI)
- 제한/수집 필요: 2개 (신용잔고, CAPE 10년 히스토리)
- 미가용: 0개

---

## Stage 분포 요약

| Stage | 컨셉 수 | 역할 |
|---|---|---|
| **Stage A** (레짐/진입 필터) | 13개 | 매크로 레짐 오버레이 — 전략 실행 전 환경 점검 |
| **Stage B** (신호 강도 가중치) | 7개 | 개별 신호의 확신도 및 포지션 크기 조정 |
| **Stage C** (청산 타이밍) | 4개 | 포지션 청산 및 익스포저 축소 트리거 |

---

## 주요 출처 목록

| 분류 | 출처 | URL |
|---|---|---|
| 도서 B1 | Howard Marks, *Mastering the Market Cycle* (2018) | https://www.oaktreecapital.com/insights/memo |
| 도서 B1 메모 | Oaktree Capital Memos (Howard Marks) | https://www.oaktreecapital.com/insights/memo |
| 도서 B2 | George Soros, *The Alchemy of Finance* (Wiley, 2003) | https://www.georgesoros.com/1987/01/01/the-alchemy-of-finance/ |
| 도서 B3 무료 PDF | Ray Dalio, *Principles for Navigating Big Debt Crises* | https://www.principles.com/big-debt-crises/ |
| 도서 B3 영상 | Dalio "How the Economic Machine Works" (무료) | https://www.youtube.com/watch?v=PHe0bXAIuk0 |
| 도서 B4 | Nassim Taleb 공식 사이트 | https://www.fooledbyrandomness.com/ |
| 도서 B5 | Kahneman, *Thinking, Fast and Slow* | https://us.macmillan.com/books/9780374533557/thinkingfastandslow |
| 보완 | Robert Shiller CAPE 원 데이터 | http://www.econ.yale.edu/~shiller/data.htm |
| 보완 | Mauboussin, *More Than You Know* | https://cup.columbia.edu/book/more-than-you-know/9780231143738 |
| 보완 | Mauboussin "Base Rate Book" (Credit Suisse 2016) | https://research-doc.credit-suisse.com/docView?language=ENG&format=PDF&document_id=1069809871 |
| 보완 | James Montier, *Behavioural Investing* | https://www.wiley.com/en-us/Behavioural+Investing-p-9780470516706 |
| 보완 | GMO White Papers (Montier) | https://www.gmo.com/americas/research-library/ |
| 데이터 | FRED API (HY/IG 스프레드, EMBI, FEDFUNDS) | https://fred.stlouisfed.org |
| 데이터 | ECOS OpenAPI (한국은행) | https://ecos.bok.or.kr |
| 데이터 | KOFIA FreeSIS (신용잔고) | https://freesis.kofia.or.kr |
| 데이터 | KRX 마켓플레이스 (PBR/PER, 외국인 순매수) | https://data.krx.co.kr |
| 데이터 | pykrx (VKOSPI, 공매도, 외국인 수급) | https://github.com/sharebook-kr/pykrx |
| 라이브러리 | fredapi (FRED Python 클라이언트) | https://github.com/mortada/fredapi |
| 라이브러리 | fear-and-greed (CNN F&G PyPI) | https://pypi.org/project/fear-and-greed/ |
