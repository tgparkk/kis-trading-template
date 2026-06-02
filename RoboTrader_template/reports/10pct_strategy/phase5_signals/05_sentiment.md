# Phase 5 시그널 패밀리 — Category 5: 시장 심리/Sentiment 시그널

> 작성일: 2026-05-25 | 조사자: document-specialist (Claude)
> 목적: 매매 시그널 family 37 → 100+ 확장 (Phase 5) — 심리/Sentiment 카테고리 전담
> 기반: 교보문고 3권 (00_kyobo_books.md) + 외부 공식 출처 보강
> No Look-Ahead 원칙: 각 지표의 PIT(Point-In-Time) 발표 시각 명시

---

## 개요

| 구분 | 컨셉 수 |
|---|---|
| 미국 sentiment (KOSPI 영향) | 8개 |
| 한국 특수 sentiment | 6개 |
| 거시/금리 sentiment | 5개 |
| 대체/텍스트 sentiment | 5개 |
| 내부자/공시 sentiment | 5개 |
| 캘린더 sentiment | 4개 |
| **합계** | **33개** |

책 3권 출처: 5개 (테마주 모멘텀, 재료 유효기간, 뉴욕·해외선물 연동, Float 변동성, 오버나잇 금지 원칙)
외부 출처: 28개

---

## 공통 컬럼 설명

| 컬럼 | 설명 |
|---|---|
| 컨셉명 | 시그널 이름 |
| 정의/계산 | 구체적 수식 또는 산출 방법 |
| PIT 시각 | 데이터 사용 가능 시점 (No Look-Ahead 기준) |
| 신호 해석 | 매수/매도/중립 판단 기준 |
| 데이터 출처 | 공식 소스 URL/기관 |
| 수집 방법 | API/라이브러리/스크래핑 |
| 가용성 | 즉시/제한/불가 |
| 비고 | 주의사항 |

---

## 1. 미국 Sentiment (KOSPI 영향)

### S1-01: VIX (CBOE Volatility Index)

| 항목 | 내용 |
|---|---|
| **정의/계산** | S&P500 옵션의 30일 내재변동성 가중평균. VIX > 30 = 공포, 20~30 = 주의, < 20 = 탐욕 |
| **PIT 시각** | 미국 장중 실시간 (ET 09:30~16:00), 한국 기준 D-1 22:30~익일 06:00. **한국 장 진입 신호로 사용 시 D-1 미국 종가 기준** |
| **신호 해석** | VIX > 30 & 급등 → KOSPI 하락 압력 강함, 매수 신중. VIX < 15 & 하락추세 → 위험선호 환경, 매수 우호. VIX spike 후 반전(mean-reversion) → 단기 반등 시그널 |
| **데이터 출처** | CBOE 공식: https://www.cboe.com/us/indices/dashboard/VIX-VIX1Y-VIX3M-VIX6M-VIX9D/ |
| **수집 방법** | `yfinance`: `yf.download("^VIX")` / FRED API: series `VIXCLS` (https://fred.stlouisfed.org/series/VIXCLS) |
| **가용성** | 즉시 (yfinance/FRED 무료) |
| **비고** | FRED VIXCLS는 일봉 종가만 제공. 장중 실시간은 CBOE 대시보드 또는 유료 데이터 필요 |

---

### S1-02: VIX Term Structure (Contango/Backwardation)

| 항목 | 내용 |
|---|---|
| **정의/계산** | VIX9D(9일) / VIX(30일) / VIX3M(91일) / VIX6M / VIX1Y 5개 지점의 상대 구조. Contango(VIX < VIX3M) = 정상, Backwardation(VIX > VIX3M) = 공포 신호 |
| **PIT 시각** | 미국 장중 15초 갱신. 한국 사용 시 D-1 종가 기준 |
| **신호 해석** | VIX/VIX3M 비율 > 1.0 (Backwardation) → 단기 공포 고조, 역추세 매수 준비. VIX9D/VIX > 1.0 → 초단기 변동성 > 30일 → 급박한 이벤트 우려 |
| **데이터 출처** | CBOE: https://www.cboe.com/tradable-products/vix/term-structure/ |
| **수집 방법** | yfinance 티커: `^VIX9D`, `^VIX3M`, `^VIX6M`, `^VIX1Y`. VIX Central(vixcentral.com) 스크래핑으로 히스토리 보완 |
| **가용성** | 즉시 (yfinance) |
| **비고** | VIX9D 히스토리는 비교적 짧음 (2011년 이후). Contango 기울기 자체를 피처로 활용 권장 |

---

### S1-03: VVIX (Volatility of VIX)

| 항목 | 내용 |
|---|---|
| **정의/계산** | VIX 옵션 가격에서 산출한 VIX의 30일 내재변동성. "공포의 공포 지수". VVIX > 120 = 극단적 불안, 80~100 = 보통 |
| **PIT 시각** | 미국 장중 실시간. D-1 종가 사용 |
| **신호 해석** | VVIX 급등 & VIX 정상 → VIX 상승 예고 선행 신호. VVIX > 130 → 시장 꼬리리스크 급증 경보 |
| **데이터 출처** | CBOE: https://www.cboe.com/us/indices/dashboard/vvix/ |
| **수집 방법** | yfinance: `^VVIX` |
| **가용성** | 즉시 |
| **비고** | VVIX는 VIX보다 선행하는 경향. VIX와 VVIX 양쪽 급등 시 매도 신호 강화 |

---

### S1-04: CBOE Put/Call Ratio (PCR)

| 항목 | 내용 |
|---|---|
| **정의/계산** | 일별 풋옵션 거래량 / 콜옵션 거래량. 총합(Total), 주식형(Equity), 지수형(Index) 3종. Equity PCR > 0.8 = 과도한 비관, < 0.5 = 과도한 낙관 |
| **PIT 시각** | 미국 장 마감 후 (D-1 ET 16:00 이후) 발표. 한국 장 개장 전(09:00 KST) 활용 가능 |
| **신호 해석** | Total PCR > 1.2 → 극단적 공포, 역추세 매수 신호. PCR < 0.6 → 낙관 과열, 매도 주의. 5일 이동평균 사용 권장 |
| **데이터 출처** | CBOE 공식 CSV: https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/indexpcarchive.csv / FRED: https://fred.stlouisfed.org/release?rid=200 |
| **수집 방법** | CBOE CSV 직접 다운로드 (무료). MacroMicro 차트: https://en.macromicro.me/charts/449/us-cboe-options-put-call-ratio |
| **가용성** | 즉시 (CSV 무료, 2006년~) |
| **비고** | Index PCR는 헤지 목적 비율 높아 해석 다름. Equity PCR 위주 활용 권장. 2019년 이후 업데이트는 CBOE DataShop 또는 일별 페이지 스크래핑 필요 |

---

### S1-05: AAII 투자자 심리 서베이

| 항목 | 내용 |
|---|---|
| **정의/계산** | 미국 개인투자자협회(AAII) 주간 설문. Bull%(강세) / Neutral%(중립) / Bear%(약세) 비율. Bull-Bear Spread = Bull% - Bear%. 1987년 이후 Bull 평균 38%, Bear 평균 30.5% |
| **PIT 시각** | **매주 목요일 조기 발표** (미국 ET 기준). 한국 기준 목요일 저녁~금요일 새벽 공개. **주간 데이터이므로 발표 목요일 이후 주(weekly bar)부터 사용** |
| **신호 해석** | Bull > 60% → 극단적 낙관, 역추세 매도 신호. Bear > 50% → 극단적 공포, 역추세 매수 신호. Bull-Bear Spread < -20%p → 저점 형성 가능성 |
| **데이터 출처** | AAII 공식: https://www.aaii.com/sentimentsurvey / 과거 데이터: https://www.aaii.com/sentimentsurvey/sent_results |
| **수집 방법** | AAII 공식 페이지 스크래핑 또는 YCharts 무료 조회: https://ycharts.com/indicators/us_investor_sentiment_bull_bear_spread |
| **가용성** | 즉시 (무료, 1987~) |
| **비고** | 개인투자자 기반 서베이로 제도권 서베이(II)와 구분. 비정기적으로 응답자 수 적은 주는 노이즈 주의 |

---

### S1-06: Investors Intelligence (II) 서베이

| 항목 | 내용 |
|---|---|
| **정의/계산** | 약 140개 투자 뉴스레터 필진 대상 주간 서베이. Bull%/Bear%/Correction 기대% 3구분. Bull > 55% = 과열 경보, Bull < 35% = 역추세 매수 |
| **PIT 시각** | 매주 화요일 발표. **발표일 이후 데이터만 사용** |
| **신호 해석** | 전문가 컨센서스 역발상 지표. Bull/Bear 비율 > 3.0 (Bull이 Bear의 3배) → 시장 천장 경보. Bear > Bull → 저점 근처 |
| **데이터 출처** | Chartcraft/Investors Intelligence (유료 구독). 무료 차트: https://www.mcoscillator.com/learning_center/weekly_chart/investors_intelligence_sentiment_extreme/ |
| **수집 방법** | 유료 구독 필요 (chartcraft.com). 무료 차트만 시각 확인 가능 |
| **가용성** | 제한 (유료 구독 필요) |
| **비고** | 개인투자자(AAII)와 달리 전문가 뉴스레터 기반. 두 지표 동시 극단 시 신뢰도 상승 |

---

### S1-07: CNN Fear & Greed Index

| 항목 | 내용 |
|---|---|
| **정의/계산** | 7개 미국 시장 지표의 복합 0~100 스코어. 구성요소: ① S&P500 vs 125일 MA (시장 모멘텀) ② NYSE 52주 고가/저가 비율 ③ NYSE 거래량 등락 비율 ④ PUT/CALL 비율 ⑤ VIX ⑥ 정크본드-투자등급 스프레드 ⑦ 주식 vs 국채 수익률 차이 |
| **PIT 시각** | 장중 실시간 갱신. **일봉 종가 기준 사용 시 미국 ET 16:00 이후 값** |
| **신호 해석** | 0~25 = 극단적 공포(역추세 매수), 25~45 = 공포, 55~75 = 탐욕, 75~100 = 극단적 탐욕(역추세 매도). KOSPI에 1~3일 선행 경향 |
| **데이터 출처** | CNN 공식: https://www.cnn.com/markets/fear-and-greed / CNN API: https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{YYYY-MM-DD} |
| **수집 방법** | PyPI 패키지: `pip install fear-and-greed` (https://pypi.org/project/fear-and-greed/). CNN API 직접 호출 가능 |
| **가용성** | 즉시 (무료 API, PyPI 패키지) |
| **비고** | CNN 내부 API 기반이므로 구조 변경 위험. PyPI 패키지 버전 업데이트 확인 필요. 7개 서브지표 개별 수집 가능 |

---

### S1-08: NYSE McClellan Oscillator & TRIN (Arms Index)

| 항목 | 내용 |
|---|---|
| **정의/계산** | **McClellan Oscillator**: NYSE 등락 종목 수 차이(A-D)의 19일EMA - 39일EMA. 0선 위=강세, 아래=약세, ±100 초과=과매수/과매도. **TRIN(Arms Index)**: (등락종목수비율) / (등락거래량비율) = (상승수/하락수) / (상승거래량/하락거래량). TRIN < 1 = 매수 우위, > 1 = 매도 우위 |
| **PIT 시각** | 미국 장중 실시간. D-1 종가 기준 활용 |
| **신호 해석** | McClellan > +100 → 단기 과열. McClellan < -100 → 단기 과매도, 반등 신호. TRIN > 2.0 → 패닉 셀링, 역추세 매수 기회. TRIN < 0.5 → 과도한 매수, 조정 경보 |
| **데이터 출처** | StockCharts: `$NYMO`(McClellan), `$TRIN`(TRIN). 공식 데이터: https://www.mcoscillator.com/market_breadth_data/ |
| **수집 방법** | yfinance/Yahoo Finance 심볼: `^TICK`, `^TRIN`. MarketInOut.com 무료 차트 |
| **가용성** | 즉시 (Yahoo Finance) |
| **비고** | KOSPI 직접 McClellan은 별도 계산 필요 (KRX 등락종목수 데이터로 산출 가능) |

---

## 2. 한국 특수 Sentiment

### S2-01: VKOSPI (한국 변동성지수)

| 항목 | 내용 |
|---|---|
| **정의/계산** | 코스피200 옵션 가격 기반 30일 내재변동성. 미국 VIX와 동일 방법론. 한국거래소가 2009년 4월 도입. VKOSPI > 30 = 공포, 20~30 = 주의 |
| **PIT 시각** | 장중 실시간 (09:00~15:30 KST). **동일 일 장중 사용 가능** |
| **신호 해석** | VKOSPI 급등(전일 대비 +20% 이상) → 패닉 국면, 단기 저점 신호 가능성. VKOSPI < 15 & 하락 → 안정 국면, 모멘텀 전략 유리. VKOSPI와 KOSPI 괴리 관찰 (VKOSPI 급등 후 KOSPI 급반등) |
| **데이터 출처** | KRX 공식: https://data.krx.co.kr/ / Investing.com: https://kr.investing.com/indices/kospi-volatility |
| **수집 방법** | pykrx 또는 KRX 데이터 마켓플레이스 직접 다운로드 |
| **가용성** | 즉시 (pykrx 또는 KRX 마켓플레이스) |
| **비고** | KRX 데이터마켓플레이스는 당일 데이터 지연(T+1 제공 가능). 장중 실시간은 KIS API 또는 증권사 HTS에서 수집 |

---

### S2-02: KOSPI/KOSDAQ 등락비율 (ADR)

| 항목 | 내용 |
|---|---|
| **정의/계산** | ADR = (N일 누적 상승종목수) / (N일 누적 하락종목수) x 100. 통상 20일 사용. ADR > 150 = 과매수, < 70 = 과매도 |
| **PIT 시각** | **장 마감 후 (15:30 KST 이후) D일 데이터 확정**. 익일 신호로 사용 |
| **신호 해석** | 20일 ADR < 70 → 저점 근처, 반등 가능. ADR > 150 → 단기 과열, 매도 주의. KOSPI 지수 상승에도 ADR 하락 = 괴리(Negative Divergence) → 상승 지속력 약함 |
| **데이터 출처** | adrinfo.kr (무료 시각화). KRX 데이터마켓플레이스 등락종목 통계 |
| **수집 방법** | pykrx 종목별 등락 데이터로 직접 계산. 또는 KIS OpenAPI 국내주식 시세 활용 |
| **가용성** | 즉시 (pykrx로 산출 가능) |
| **비고** | KOSPI/KOSDAQ 각각 산출 권장. 코스피200 편입 종목 한정 ADR이 더 의미 있을 수 있음 |

---

### S2-03: 한국 PUT/CALL Ratio (KOSPI200 옵션)

| 항목 | 내용 |
|---|---|
| **정의/계산** | KOSPI200 풋옵션 일별 거래량 / 콜옵션 일별 거래량. KRX 파생상품 통계에서 산출 |
| **PIT 시각** | **장 마감 후 (15:30 이후) 당일 데이터 확정** |
| **신호 해석** | P/C Ratio > 1.5 → 헤지 수요 급증, 하락 우려 과도 → 역추세 매수 검토. P/C Ratio < 0.5 → 낙관 과열 → 조정 경보. 5일 이동평균 활용 권장 |
| **데이터 출처** | KRX 파생상품 통계: https://data.krx.co.kr (파생상품 -> 옵션 -> 거래실적) |
| **수집 방법** | KRX 데이터마켓플레이스 일별 다운로드 (로그인 필요). pykrx derivatives 모듈 지원 여부 확인 필요 |
| **가용성** | 즉시 (KRX 마켓플레이스, 수동/자동화 필요) |
| **비고** | KOSPI200 옵션 P/C는 기관·외국인 헤지 비중 높아 미국보다 해석 복잡. 만기 주간은 롤오버 영향으로 비정상적 급등 가능 |

---

### S2-04: 신용잔고/총거래대금 비율

| 항목 | 내용 |
|---|---|
| **정의/계산** | 신용공여잔고(증거금 대출 매수 잔액) / 최근 N일 평균 거래대금. 과도한 레버리지 투자 척도. 비율 급등 = 과열 신호 |
| **PIT 시각** | 신용잔고는 T+1 발표 (전일 기준). **익일 장 개장 전 신호 생성 가능** |
| **신호 해석** | 신용잔고 급증 + 지수 상승 → 레버리지 과열, 단기 조정 위험. 신용잔고 급감 + 지수 하락 → 반대매매 물량 소화 중, 저점 형성 가능 |
| **데이터 출처** | 금융투자협회 종합통계: https://freesis.kofia.or.kr/stat/FreeSIS.do (신용공여 잔고 추이) |
| **수집 방법** | 금융투자협회(KOFIA) FreeSIS 스크래핑. 공공데이터포털 API (data.go.kr) |
| **가용성** | 즉시 (스크래핑 가능) |
| **비고** | KOSPI/KOSDAQ 시장별 분리 데이터도 제공. 거래대금과 조합 시 레버리지 비율(%)로 정규화 권장 |

---

### S2-05: 시장경보 (단기과열/투자경고/투자위험)

| 항목 | 내용 |
|---|---|
| **정의/계산** | 한국거래소 3단계 경보 시스템. ① 단기과열종목 지정 (단기 급등 종목) ② 투자경고종목 (비정상 급등 지속) ③ 투자위험종목 (최고 단계). 경보 지정 = 매매 제한 적용 |
| **PIT 시각** | **장중 실시간 공표** (KRX 홈페이지). 단기과열은 당일 09:00 장 개시 전 결정 공표 |
| **신호 해석** | 단기과열 지정 → 해당 종목 단기 추가 상승 제한. 매매 주의. 투자경고/위험 지정 → 해당 종목 진입 회피. 경보 해제 후 첫 거래일 = 매수 재개 신호 가능 |
| **데이터 출처** | KRX 공식: https://data.krx.co.kr / KIS OpenAPI에서 개별 종목 조회 가능 |
| **수집 방법** | KIS OpenAPI 종목 기본조회 내 투자유의/경고 필드. 또는 KRX 홈페이지 스크래핑 |
| **가용성** | 즉시 (KIS API 또는 KRX 스크래핑) |
| **비고** | 시스템에 이미 CB/VI 체크 내장됨. 단기과열 지정 종목 리스트는 별도 수집 필요 |

---

### S2-06: 외국인 KOSPI200 선물 누적 순포지션

| 항목 | 내용 |
|---|---|
| **정의/계산** | 외국인 KOSPI200 선물 일별 순매수(매수-매도) 누적합. 누적 순매수 전환 = 강세 신호, 순매도 전환 = 약세 신호. 임계값: +-10,000계약 전환점 의미 있음 (증권사 리서치 기준) |
| **PIT 시각** | **장 마감 후 (T일 15:30 이후) 당일 확정**. 익일 신호 |
| **신호 해석** | 외국인 선물 누적 10,000계약 이상 순매수 → 지수 상승 동조. 누적 10,000계약 이상 순매도 → 베이시스 약화, 프로그램 매도 압력. 방향 전환 시 추세 변화 포착 |
| **데이터 출처** | KRX 파생상품 투자자별 통계: https://data.krx.co.kr (통계 -> 파생상품 -> 투자자별) |
| **수집 방법** | KRX 데이터마켓플레이스 일별 다운로드. pykrx derivatives 기능 활용 |
| **가용성** | 즉시 (KRX 마켓플레이스) |
| **비고** | 만기일 주간 롤오버로 인한 일시적 방향 왜곡 주의. 만기 효과 제거 후 분석 권장 |

---

## 3. 거시/금리 Sentiment

### S3-01: 원/달러 환율 (USD/KRW)

| 항목 | 내용 |
|---|---|
| **정의/계산** | 원/달러 현물 환율. 5일, 20일 이동평균 대비 수준. 환율 급등 = 외국인 자금 이탈 신호 |
| **PIT 시각** | 외환시장 실시간 (09:00~15:30 KST). **전일 종가(오후 3:30 기준환율)** |
| **신호 해석** | 원/달러 > 1,380원 & 급등 → KOSPI 외국인 이탈 압력. 원/달러 하락(원화 강세) → 외국인 유입 환경. 환율 변화율 > 1% → 당일 외국인 수급 변동 선행 지표 |
| **데이터 출처** | 한국은행 ECOS: https://ecos.bok.or.kr/ / Yahoo Finance: `KRW=X` |
| **수집 방법** | yfinance: `yf.download("KRW=X")`. 한국은행 ECOS API (무료 키 발급) |
| **가용성** | 즉시 (yfinance 무료) |
| **비고** | 야간 NDF 환율(역외 선물환)도 익일 KOSPI에 영향. NDF는 Bloomberg/Reuters 유료 |

---

### S3-02: 한미 금리차 (Fed Funds Rate - 한국기준금리)

| 항목 | 내용 |
|---|---|
| **정의/계산** | 미국 연방기금금리(FFR) - 한국 기준금리. 역전(한국 > 미국) = 자본 이탈 압력 감소. 한미 역전 심화 = 원화 약세 → 외국인 이탈 가능성 |
| **PIT 시각** | FOMC 발표일 (연 8회), 금통위 발표일 (연 8회) 이후 변경. **정책 결정일 이후 즉시 반영 가능** |
| **신호 해석** | 한미 금리차 > 1.0%p (한국 高) → 채권 대비 주식 매력도 상대적 우위. 금리차 역전 축소 방향 → 원화 강세 + KOSPI 우호 |
| **데이터 출처** | FRED: https://fred.stlouisfed.org/series/FEDFUNDS (미국) / 한국은행 ECOS: 기준금리 series |
| **수집 방법** | FRED API: `pip install fredapi` + `FEDFUNDS`. ECOS OpenAPI (무료 키) |
| **가용성** | 즉시 (FRED API 무료) |
| **비고** | 정책금리 외에 3개월 국채금리 차이(시장금리 기준)도 보조 지표로 활용 |

---

### S3-03: 한국 국고채 10년 금리 & 회사채 스프레드

| 항목 | 내용 |
|---|---|
| **정의/계산** | 국고채 10년물 금리 수준 + 회사채(AA-, BBB+) - 국고채 스프레드. 스프레드 확대 = 신용위험 증가 = 위험회피 심화 |
| **PIT 시각** | 채권시장 마감 (15:30 KST). **당일 종가 기준** |
| **신호 해석** | 국고채 10년 금리 급등(+20bp 이상/주) → 채권에서 주식 자금 이동 우려 또는 인플레 공포. 회사채 스프레드 > 200bp → 크레딧 시장 긴장, 주식 하락 압력. 스프레드 축소 = 위험선호 복귀 |
| **데이터 출처** | 한국은행 ECOS: https://ecos.bok.or.kr/ (통화금융/채권/금리 항목) / 금융투자협회 FreeSIS |
| **수집 방법** | ECOS OpenAPI (무료). 금투협 스크래핑 |
| **가용성** | 즉시 (ECOS API) |
| **비고** | BBB+ 스프레드는 경기 선행 지표로도 활용. 스프레드 데이터는 T+1 지연 가능 |

---

### S3-04: KOSPI ERP (주식 위험 프리미엄)

| 항목 | 내용 |
|---|---|
| **정의/계산** | ERP = KOSPI 기대수익률 - 국고채 10년 금리. 기대수익률 = 1/PER(선행). ERP > 5% = 주식 저평가/매수 우호. ERP < 2% = 주식 고평가 |
| **PIT 시각** | 선행 PER은 분기 실적 시즌에 업데이트. 국고채 금리는 일별. **분기별 업데이트 + 금리 일별 조정** |
| **신호 해석** | ERP 역사적 고점 근처 → 주식 절대 매수 구간. ERP 급락(PER 급등 또는 금리 급등) → 밸류에이션 부담 경보 |
| **데이터 출처** | KOSPI PER: KRX 마켓플레이스 / 국고채: ECOS / 참고: https://toggle.ai/ko/investing/fundamental-valuation-indicators_ko/equity-risk_ko |
| **수집 방법** | pykrx: KOSPI PER 조회 가능. ECOS API로 국고채 금리 조합 |
| **가용성** | 즉시 (pykrx + ECOS 조합) |
| **비고** | 선행 PER 대신 후행 PER 사용 시 경기 후행 위험. Damodaran 방법론의 implied ERP 권장 (월별 업데이트) |

---

### S3-05: 비트코인/위험자산 Sentiment 프록시

| 항목 | 내용 |
|---|---|
| **정의/계산** | 비트코인(BTC) 24시간 수익률 또는 비트코인/금 비율. 위험선호(Risk-On) 환경의 프록시. BTC 급락 = 글로벌 위험회피 선행 신호 |
| **PIT 시각** | 24시간 실시간 (암호화폐 시장은 상시 운영). **한국 장 개시(09:00) 직전 BTC 수익률 사용** |
| **신호 해석** | BTC 전일 대비 -10% 이상 → 글로벌 위험회피 심화, KOSPI 하락 압력. BTC 급등 (> +5%) + KOSPI 상관관계 고점 → 위험선호 확인 |
| **데이터 출처** | yfinance: `BTC-USD`. CoinGecko API (무료) |
| **수집 방법** | `yf.download("BTC-USD")` 또는 CoinGecko 무료 API |
| **가용성** | 즉시 (yfinance/CoinGecko 무료) |
| **비고** | BTC-KOSPI 상관관계는 기간별 변동성 큼. rolling 상관계수로 동적 가중치 적용 권장. 원자재(WTI, 구리)도 동일 방식으로 활용 가능 |

---

## 4. 대체/텍스트 Sentiment

### S4-01: 구글 트렌드 (Google Trends)

| 항목 | 내용 |
|---|---|
| **정의/계산** | 구글 검색어 상대적 관심도 (0~100). 대상 키워드: "주식", "코스피", "주식 폭락", "주식 사야 하나" 등. 급등 = 대중 관심 극대화 = 역추세 신호 |
| **PIT 시각** | 주간 데이터 (매주 갱신). 실시간은 72시간 지연 있음. **주간 데이터 사용 시 당주 데이터 확정 시점 확인 필요** |
| **신호 해석** | "주식 폭락" 검색 급증 → 공포 극대화 → 역추세 매수 신호. "주식 추천" 급증 → 개인투자자 관심 과열 → 단기 조정 가능성 |
| **데이터 출처** | 구글 트렌드: https://trends.google.co.kr/trends/ |
| **수집 방법** | `pip install pytrends`. `TrendReq().build_payload(["코스피"])` |
| **가용성** | 즉시 (pytrends 무료, 단 일별 데이터는 1주일 이내만 제공) |
| **비고** | 장기 히스토리는 주간 해상도만 가능. 일별 데이터는 최근 7일만 제공 (일관성 제한) |

---

### S4-02: 네이버 데이터랩 검색량

| 항목 | 내용 |
|---|---|
| **정의/계산** | 네이버 검색어 상대적 트렌드 (0~100). 한국 내 최대 포털 검색 기반. 키워드: "주식", "코스피", 특정 종목명 |
| **PIT 시각** | 일별 데이터 제공 (전날 기준 1일 지연). **T-1일 데이터 T일 장 전 사용 가능** |
| **신호 해석** | 특정 종목명 검색 급등 → 테마 재료 확산 → 진입 적기 또는 고점 근처. "코스피 전망" 급등 = 시장 불안감 |
| **데이터 출처** | 네이버 데이터랩: https://datalab.naver.com/ |
| **수집 방법** | 네이버 데이터랩 Open API (API 키 발급 필요): `https://openapi.naver.com/v1/datalab/search`. 무료 일별 데이터 제공 |
| **가용성** | 즉시 (API 키 무료 발급) |
| **비고** | 구글 트렌드와 상호 보완적. 한국 시장에서는 네이버 비중이 더 높음. 개인투자자 행동 선행 지표 |

---

### S4-03: 한국어 뉴스 Sentiment (KR-FinBERT)

| 항목 | 내용 |
|---|---|
| **정의/계산** | 한국어 금융 뉴스 제목/본문을 KR-FinBERT 모델로 Positive/Negative/Neutral 분류 후 일별 Sentiment Score 산출. Score = (Positive - Negative) / Total |
| **PIT 시각** | 뉴스 발행 시각 기준. **장 시작 전(08:00~09:00) 수집 뉴스만 당일 신호로 사용** |
| **신호 해석** | 일별 Sentiment Score < -0.3 → 부정 뉴스 우세, 하락 압력. Score > 0.3 → 긍정 우세, 상승 모멘텀. 3일 이동평균으로 노이즈 제거 |
| **데이터 출처** | KR-FinBERT 모델: https://huggingface.co/snunlp/KR-FinBert-SC (서울대 NLP 연구실). 뉴스 소스: 네이버 금융/연합뉴스 RSS |
| **수집 방법** | `pip install transformers`. `snunlp/KR-FinBert-SC` 모델 로드 후 뉴스 제목 inference. GPU 없이도 CPU로 작동 가능 |
| **가용성** | 즉시 (Hugging Face 모델 무료) |
| **비고** | 뉴스 수집 자동화(RSS/크롤링) 별도 구현 필요. 종목별 sentiment로 세분화 가능. CPU inference 약 200ms/건 |

---

### S4-04: 테마주 모멘텀 & 재료 유효기간 (책 2 출처)

| 항목 | 내용 |
|---|---|
| **정의/계산** | 정책/뉴스 테마 출현 후 관련 종목군의 상승 지속 기간. **책 2 (이시이 카츠토시): "신선한 재료는 최대 2일 시장 주도"** (Rule 33~35). 이후 포지션 청산 원칙 |
| **PIT 시각** | 재료 최초 출현일 D-day 기준. D+1, D+2 이후 청산 고려 |
| **신호 해석** | 테마 재료 첫 출현 D-day: 진입 적기. D+1: 추세 확인 후 유지. D+2 이후: 포지션 정리 준비. 재료 재점화 없으면 익절 |
| **데이터 출처** | 책 2 원전: https://product.kyobobook.co.kr/detail/S000001014275 (Rule 33~35) |
| **수집 방법** | 뉴스 크롤링 + 종목 연관성 매핑. DART 테마 공시 필터링 |
| **가용성** | 즉시 (로직 구현 필요) |
| **비고** | 재료 유효기간 2일은 단타 기준. 중대형 정책(예: 반도체 지원법)은 수주 지속 가능. 테마 강도 평가 필요 |

---

### S4-05: 뉴욕/해외선물 연동 지수 (책 2 출처)

| 항목 | 내용 |
|---|---|
| **정의/계산** | 미국 3대 지수(S&P500, 나스닥, 다우) 전일 수익률 + 야간 선물(E-Mini S&P500) 동향. **책 2: "해외선물/미국 지수가 국내 장초반 70% 이상 영향"** (Rule 15~17) |
| **PIT 시각** | 미국 ET 16:00 마감 기준. 한국 기준 익일 06:00 (T-1일 미국 종가). 선물은 한국 장 개시 직전까지 실시간 확인 가능 |
| **신호 해석** | S&P500 전일 > +1% → KOSPI 갭업 출발 예상. S&P500 전일 < -2% → KOSPI 하락 출발 예상. 선물 방향이 현물 종가와 다를 경우 갭 조정 가능성 |
| **데이터 출처** | yfinance: `^GSPC`, `^IXIC`, `^DJI`, `ES=F` (E-Mini 선물). 책 2: https://product.kyobobook.co.kr/detail/S000001014275 |
| **수집 방법** | `yf.download(["^GSPC", "^IXIC", "ES=F"])`. 실시간 야간 선물 모니터링 가능 |
| **가용성** | 즉시 (yfinance 무료) |
| **비고** | 유가(WTI), 달러 인덱스(DXY), 금 가격도 보조 지표로 추가 권장 |

---

## 5. 내부자/공시 Sentiment

### S5-01: 임원/대주주 장내 매수 (DART)

| 항목 | 내용 |
|---|---|
| **정의/계산** | DART 임원·주요주주 소유보고에서 장내 매수 건 추출. 임원 매수 = 내부자 저평가 신호. 매수 금액 기준 임계값 설정 (예: 1억원 이상) |
| **PIT 시각** | **공시 접수일 기준**. 소유 변동 후 5영업일 이내 공시 의무. **공시일 이후 신호 사용** |
| **신호 해석** | 대표이사/주요 임원 장내 매수 → 경영진 자신감 시그널. 복수 임원 동시 매수 → 강도 높음. 임원 매도는 세금/유동성 목적 가능 → 약한 신호 |
| **데이터 출처** | OpenDART: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS004&apiId=2019021 |
| **수집 방법** | `pip install OpenDartReader`. `dart.major_shareholders(corp_code)`. 무료 API 키 발급 필요 |
| **가용성** | 즉시 (OpenDartReader 무료) |
| **비고** | 대량보유(5% 이상) 보고와 임원 소유보고 구분 필요. 소규모 임원 매수는 신호 강도 낮음 |

---

### S5-02: 5% 보유 보고서 변동

| 항목 | 내용 |
|---|---|
| **정의/계산** | 발행주식 5% 이상 보유자의 보유량 변동 보고. 보유량 증가 = 대형 투자자 매수 신호. 감소 = 이탈 신호 |
| **PIT 시각** | 공시 접수일. 보유 변동 후 5영업일 이내 공시. **공시일 이후 신호** |
| **신호 해석** | 기관/PE 대형 투자자 5% 지분 신규 취득 → 강한 매수 신호. 기존 5% 보유자 지분 축소 → 이탈 주의 |
| **데이터 출처** | OpenDART: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS004&apiId=2019021 |
| **수집 방법** | OpenDartReader: `dart.major_shareholders()` 또는 공시 유형 필터 |
| **가용성** | 즉시 (OpenDartReader) |
| **비고** | 국내 기관보다 외국인의 5% 취득 공시 더 강한 신호 경향 |

---

### S5-03: 자기주식 취득/처분 공시

| 항목 | 내용 |
|---|---|
| **정의/계산** | 기업의 자사주 취득 결정 공시 = 주가 지지 의지 표명. 처분 결정 = 주가에 부정적. 취득 규모 / 시가총액 비율이 핵심 |
| **PIT 시각** | **공시 접수 당일**. 이사회 결의 직후 즉시 공시. 장중 공시 시 당일 신호로 사용 가능 |
| **신호 해석** | 자사주 취득 결정 + 규모 > 시총 1% → 단기 주가 지지. 반복 취득(3회 이상 연속) → 경영진 강한 의지. 자사주 처분 → 단기 오버행(매물) 부담 |
| **데이터 출처** | OpenDART 공시 유형: "자기주식취득결정". https://opendart.fss.or.kr/ |
| **수집 방법** | OpenDartReader: `dart.list(corp_code)` 후 보고서명 필터 |
| **가용성** | 즉시 (OpenDartReader) |
| **비고** | 취득 결정과 실제 취득 사이 시차 있음. 취득 완료 공시 별도 확인 필요 |

---

### S5-04: 공매도 잔고 변화

| 항목 | 내용 |
|---|---|
| **정의/계산** | 개별 종목 공매도 잔고(주수) 일별 변화. 잔고 증가 = 숏 포지션 축적 = 하락 베팅. 잔고 감소 = 숏 커버링 = 상승 압력 가능 |
| **PIT 시각** | **T+2 지연 공시** (공매도 체결 후 2영업일 후 발표). **T일 신호는 T-2일 공매도 데이터 기준** |
| **신호 해석** | 공매도 잔고 급증 + 주가 상승 = 숏스퀴즈 잠재력. 공매도 잔고 > 발행주식 5% → 강한 숏 포지션, 반등 시 급등 가능. 잔고 급감 = 숏 커버링 = 단기 상승 압력 |
| **데이터 출처** | KRX 공매도 전용: https://short.krx.co.kr/ / KRX 마켓플레이스: https://data.krx.co.kr |
| **수집 방법** | pykrx `stock.get_shorting_balance_by_ticker()` |
| **가용성** | 즉시 (pykrx 지원) |
| **비고** | 공매도 금지 기간(2023~2024) 데이터 제외 필요. T+2 지연으로 최신 신호 한계 |

---

### S5-05: 대차거래 잔고 변화

| 항목 | 내용 |
|---|---|
| **정의/계산** | 대차거래 = 기관이 주식 빌려서 공매도하기 위한 전단계. 대차잔고 증가 = 향후 공매도 증가 선행 신호. 대차잔고/시총 비율로 정규화 |
| **PIT 시각** | **T+1 발표** (전일 기준). **익일 장 전 신호 생성 가능** |
| **신호 해석** | 대차잔고 급증 + 주가 고점 → 향후 공매도 압력 예고. 대차잔고 급감 → 기관 대여 회수, 공매도 축소 예상 → 숏 커버링 |
| **데이터 출처** | 금융위원회 공공데이터: https://www.data.go.kr/data/15124865/openapi.do (주식대차거래정보). 한국증권금융 Seibro: https://seibro.or.kr/ |
| **수집 방법** | 공공데이터포털 API 키 발급 후 REST 호출. 금융투자협회 FreeSIS 스크래핑 |
| **가용성** | 즉시 (공공데이터포털 API 무료) |
| **비고** | 대차거래 → 공매도 전환 비율은 100%가 아님. 대차 이후 실제 공매도 여부 별도 확인 필요 |

---

## 6. 캘린더 Sentiment

### S6-01: FOMC 이벤트 드리프트

| 항목 | 내용 |
|---|---|
| **정의/계산** | FOMC 회의 발표일 전후 수익률 패턴. 발표 전 1~3일: 불확실성 증가. 발표 당일: 결과에 따라 급변. 발표 후 D+1~D+3: 방향 확정 후 드리프트. 연 8회 정해진 일정 |
| **PIT 시각** | FOMC 성명서 발표 (ET 14:00, 한국 KST 익일 04:00). 한국 다음 영업일부터 신호 반영 |
| **신호 해석** | 예상보다 비둘기(금리 인하/동결) → KOSPI 갭업. 예상보다 매파(금리 인상/긴축 강화) → KOSPI 하락. 결과가 컨센서스와 일치 → 변동성 빠른 정상화 |
| **데이터 출처** | Fed 공식: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm / 한국어 정리: https://kbthink.com/us-economy.html |
| **수집 방법** | FOMC 일정 하드코딩 또는 Fed 공식 RSS. 금리 결과: FRED `FEDFUNDS` 당일 업데이트 |
| **가용성** | 즉시 (일정 하드코딩) |
| **비고** | FOMC 이전 2주간 "블랙아웃 기간" — Fed 위원 발언 없음. 직전 CME FedWatch 금리 기대치 대비 서프라이즈 강도 계산 권장 |

---

### S6-02: 한국 금통위 이벤트

| 항목 | 내용 |
|---|---|
| **정의/계산** | 한국은행 금통위 기준금리 결정 발표일 전후 KOSPI 수익률 패턴. 연 8회. 발표 당일 11:00 KST 결정 공표 |
| **PIT 시각** | 금통위 발표일 11:00 KST. **발표 전까지는 기대치(시장 컨센서스) 기반 포지셔닝** |
| **신호 해석** | 예상 동결 vs 실제 인하 → KOSPI 강하게 반응. 예상 인상 vs 실제 동결 → 부정적 서프라이즈. 금통위 이전 7일 → 변동성 증가 패턴 |
| **데이터 출처** | 한국은행 공식 금통위 일정: https://www.bok.or.kr/ |
| **수집 방법** | 금통위 일정 하드코딩. 결과는 한국은행 기준금리 ECOS API |
| **가용성** | 즉시 (일정 하드코딩) |
| **비고** | 한미 금통위가 같은 주에 겹칠 경우 이중 불확실성. 실증 연구: KDI 참조 |

---

### S6-03: 한국 어닝 시즌 캘린더

| 항목 | 내용 |
|---|---|
| **정의/계산** | 분기 실적 발표 집중 기간. 1Q: 4월 중순~5월 초. 2Q: 7월 중순~8월 초. 3Q: 10월 중순~11월 초. 4Q: 1월 중순~2월 (잠정) + 2~3월 (확정) |
| **PIT 시각** | 실적 발표일 당일 장 전 또는 장 후. **발표 전 컨센서스 대비 서프라이즈 방향이 핵심** |
| **신호 해석** | 어닝 시즌 직전 → 변동성 증가, 개별 종목 리스크 주의. 서프라이즈 > 10% → 당일 갭업, 모멘텀 편승 가능. 실망 실적 → 갭다운, 역추세 매수 주의 |
| **데이터 출처** | DART 실적발표 일정: https://opendart.fss.or.kr/ |
| **수집 방법** | DART OpenAPI 실적발표 공시 필터. FnGuide API (유료) |
| **가용성** | DART 무료 / 컨센서스는 유료 |
| **비고** | 삼성전자 등 대형주 실적 발표일 = 시장 방향 결정적. 실적 발표 시간(장 전/장 후) 확인 필수 |

---

### S6-04: 옵션/선물 만기일 효과

| 항목 | 내용 |
|---|---|
| **정의/계산** | KOSPI200 옵션 만기: 매월 두 번째 목요일. 선물 만기: 3/6/9/12월 두 번째 목요일. 만기 주간(D-4~D-day) 및 만기일 당일 프로그램 매매 증가 |
| **PIT 시각** | 만기 일정은 사전 확정. **만기일 D-4부터 포지션 롤오버 거래 증가** |
| **신호 해석** | 만기일 D-1 오후 → 롤오버 프로그램 매매 방향 주목. 만기일 당일 장 마감 동시호가(14:50~15:00) → 프로그램 대규모 청산. 만기 후 첫 거래일 → 수급 정상화 |
| **데이터 출처** | KRX 파생상품 만기일 캘린더: https://global.krx.co.kr/ / KDI 실증 연구: https://kdijep.org/assets/pdf/591/jep-25-2-137.pdf |
| **수집 방법** | 만기일 캘린더 하드코딩 또는 KRX API에서 월별 조회 |
| **가용성** | 즉시 (일정 하드코딩) |
| **비고** | KDI 연구: 일봉 데이터로는 만기 효과 통계적으로 미미. 장중 분봉 레벨에서 유의미. 외국인 선물 포지션과 결합 시 신뢰도 상승 |

---

## 종합 요약표

| ID | 컨셉명 | 카테고리 | 데이터 출처 | 수집 방법 | 가용성 | PIT 시각 |
|---|---|---|---|---|---|---|
| S1-01 | VIX | 미국 sentiment | CBOE/FRED | yfinance/FRED API | 즉시 | 미국 장 마감(ET 16:00) |
| S1-02 | VIX Term Structure | 미국 sentiment | CBOE | yfinance | 즉시 | 미국 장 마감 |
| S1-03 | VVIX | 미국 sentiment | CBOE | yfinance | 즉시 | 미국 장 마감 |
| S1-04 | CBOE Put/Call Ratio | 미국 sentiment | CBOE CSV | CSV 다운로드 | 즉시 | 미국 장 마감 |
| S1-05 | AAII 투자자 서베이 | 미국 sentiment | AAII 공식 | 웹 스크래핑 | 즉시 | 매주 목요일 |
| S1-06 | Investors Intelligence | 미국 sentiment | Chartcraft | 유료 구독 | 제한 | 매주 화요일 |
| S1-07 | CNN Fear & Greed | 미국 sentiment | CNN API | PyPI 패키지 | 즉시 | 장중 실시간 |
| S1-08 | NYSE McClellan/TRIN | 미국 sentiment | mcoscillator/Yahoo | yfinance | 즉시 | 미국 장 마감 |
| S2-01 | VKOSPI | 한국 특수 | KRX | pykrx | 즉시 | 장중 실시간 |
| S2-02 | KOSPI/KOSDAQ ADR | 한국 특수 | pykrx/KRX | pykrx 산출 | 즉시 | 장 마감(15:30) |
| S2-03 | 한국 P/C Ratio | 한국 특수 | KRX 파생상품 | KRX 마켓플레이스 | 즉시 | 장 마감 |
| S2-04 | 신용잔고/거래대금 | 한국 특수 | KOFIA FreeSIS | 스크래핑/공공API | 즉시 | T+1 발표 |
| S2-05 | 시장경보 | 한국 특수 | KRX/KIS API | KIS API | 즉시 | 장 개시 전 |
| S2-06 | 외국인 선물 포지션 | 한국 특수 | KRX 파생상품 | KRX 마켓플레이스 | 즉시 | 장 마감 |
| S3-01 | 원/달러 환율 | 거시/금리 | ECOS/yfinance | yfinance | 즉시 | 장중 실시간 |
| S3-02 | 한미 금리차 | 거시/금리 | FRED/ECOS | FRED API | 즉시 | 정책결정일 |
| S3-03 | 국고채/회사채 스프레드 | 거시/금리 | ECOS/KOFIA | ECOS API | 즉시 | 장 마감 |
| S3-04 | KOSPI ERP | 거시/금리 | pykrx/ECOS | 산출 조합 | 즉시 | 분기별+일별 |
| S3-05 | 비트코인/위험자산 프록시 | 거시/금리 | yfinance/CoinGecko | yfinance | 즉시 | 24시간 실시간 |
| S4-01 | 구글 트렌드 | 대체 sentiment | Google Trends | pytrends | 즉시 | 주간(72시간 지연) |
| S4-02 | 네이버 데이터랩 | 대체 sentiment | 네이버 Open API | REST API | 즉시 | T-1일 |
| S4-03 | KR-FinBERT 뉴스 | 대체 sentiment | Hugging Face | transformers | 즉시 | 장 전 뉴스 기준 |
| S4-04 | 테마주 재료 유효기간 | 대체 sentiment | 책 2 (Rule 33~35) | 뉴스 크롤링 | 즉시(구현 필요) | 재료 출현일 |
| S4-05 | 해외선물 연동 | 대체 sentiment | 책 2 (Rule 15~17) | yfinance | 즉시 | 미국 장 마감 |
| S5-01 | 임원 장내 매수 | 내부자/공시 | OpenDART | OpenDartReader | 즉시 | 공시일 |
| S5-02 | 5% 보유 보고 변동 | 내부자/공시 | OpenDART | OpenDartReader | 즉시 | 공시일 |
| S5-03 | 자기주식 취득/처분 | 내부자/공시 | OpenDART | OpenDartReader | 즉시 | 공시일(당일 장중) |
| S5-04 | 공매도 잔고 변화 | 내부자/공시 | KRX 공매도 | pykrx | 즉시 | T+2 지연 |
| S5-05 | 대차거래 잔고 변화 | 내부자/공시 | 공공데이터포털 | 공공API | 즉시 | T+1 지연 |
| S6-01 | FOMC 이벤트 드리프트 | 캘린더 | Fed 공식 일정 | 하드코딩 | 즉시 | 결정 발표일 |
| S6-02 | 금통위 이벤트 | 캘린더 | 한국은행 공식 | 하드코딩 | 즉시 | 발표일 11:00 KST |
| S6-03 | 어닝 시즌 캘린더 | 캘린더 | DART/FnGuide | DART API | DART 무료 | 실적발표일 |
| S6-04 | 옵션/선물 만기일 효과 | 캘린더 | KRX 캘린더 | 하드코딩 | 즉시 | 만기일 D-4~ |

---

## 즉시 활용 가능 Top 3

### 1위: CNN Fear & Greed Index (S1-07)
- PyPI 패키지 `fear-and-greed` 1줄 설치, CNN API 직접 호출
- 7개 서브지표 복합 스코어로 시장 심리 단일 숫자 요약
- KOSPI와 높은 동행성. 한국 장 개시 전 미국 종가 기준 즉시 사용 가능
- 코드: `import fear_and_greed; data = fear_and_greed.get()`

### 2위: VKOSPI (S2-01)
- 한국 장중 실시간 데이터. pykrx로 일봉 히스토리 수집 가능
- 한국 시장 전용 "공포 지수" — VIX보다 KOSPI와 직접 연관
- 기존 시스템의 VIX 기반 로직을 VKOSPI로 교체/보완 즉시 가능

### 3위: 공매도 잔고 변화 (S5-04)
- pykrx `stock.get_shorting_balance_by_ticker()` 직접 지원
- 종목별 숏 포지션 집중도 측정 → 개별 종목 신호에 직접 결합 가능
- T+2 지연이지만 5일 변화율 추세로 활용 시 충분

---

## 데이터 미가용 또는 제한 컨셉 목록

| ID | 컨셉명 | 이유 | 대안 |
|---|---|---|---|
| S1-06 | Investors Intelligence | 유료 구독 (Chartcraft) 필요 | AAII (S1-05)로 대체 |
| S4-03 | KR-FinBERT 뉴스 | 뉴스 크롤링 자동화 별도 구현 필요 | 네이버 데이터랩(S4-02)으로 부분 대체 |
| S6-03 | 어닝 컨센서스 서프라이즈 | FnGuide/에프앤가이드 유료 | DART 잠정실적 공시로 부분 대체 |
| S1-04 | CBOE P/C (2019년 이후) | 공식 CSV는 2019년까지. 이후는 DataShop 유료 | CBOE 일별 페이지 스크래핑으로 보완 |
| 야간 NDF 환율 | - | Bloomberg/Reuters 유료 | yfinance KRW=X 현물로 대체 |

---

## 주요 출처 참고 목록

| 출처 | URL |
|---|---|
| CBOE VIX 대시보드 | https://www.cboe.com/us/indices/dashboard/VIX-VIX1Y-VIX3M-VIX6M-VIX9D/ |
| CBOE P/C Ratio 히스토리 | https://www.cboe.com/us/options/market_statistics/historical_data/ |
| FRED VIXCLS | https://fred.stlouisfed.org/series/VIXCLS |
| AAII 공식 서베이 | https://www.aaii.com/sentimentsurvey |
| CNN Fear & Greed API | https://production.dataviz.cnn.io/index/fearandgreed/graphdata/ |
| fear-and-greed PyPI | https://pypi.org/project/fear-and-greed/ |
| KRX 데이터마켓플레이스 | https://data.krx.co.kr/ |
| KRX 공매도 전용 | https://short.krx.co.kr/ |
| pykrx GitHub | https://github.com/sharebook-kr/pykrx |
| OpenDART | https://opendart.fss.or.kr/ |
| OpenDartReader GitHub | https://github.com/FinanceData/OpenDartReader |
| KR-FinBERT Hugging Face | https://huggingface.co/snunlp/KR-FinBert-SC |
| 한국은행 ECOS | https://ecos.bok.or.kr/ |
| 공공데이터포털 대차거래 | https://www.data.go.kr/data/15124865/openapi.do |
| KOFIA FreeSIS 신용잔고 | https://freesis.kofia.or.kr/ |
| 네이버 데이터랩 | https://datalab.naver.com/ |
| McClellan Financial | https://www.mcoscillator.com/ |
| KDI 만기일 연구 | https://kdijep.org/assets/pdf/591/jep-25-2-137.pdf |
| 교보문고 책 2 (이시이) | https://product.kyobobook.co.kr/detail/S000001014275 |
