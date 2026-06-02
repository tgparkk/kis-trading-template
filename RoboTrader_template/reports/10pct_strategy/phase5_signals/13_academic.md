# 학술 논문 + 공식 자료 시그널 카탈로그

> 작성일: 2026-05-26 | 조사자: document-specialist #14 (Claude Sonnet 4.6)
> 목적: Phase 5 시그널 패밀리 — 학술 논문 + 한국 KRX 공식 자료 보강
> 대상: 한국 KCI 등재지 실증 논문 + 글로벌 factor 원전 + 공식 데이터 API 가이드
> 한국 시장 정량 검증된 anomaly는 ★ 특별 마킹

---

## 범례

| 기호 | 의미 |
|------|------|
| ★ | 한국 KOSPI/KOSDAQ에서 통계적으로 검증된 anomaly (재현 우선) |
| 즉시 | 현재 DB + 외부 무료 API로 즉시 계산 가능 |
| 부분 | DB 또는 pykrx로 부분 가능, 일부 보강 필요 |
| 외부 | DART/KRX 공식 API 또는 구독 서비스 신규 연동 필요 |

| Stage | 의미 |
|-------|------|
| A | 필터 — 진입 종목 풀 스크리닝 |
| B | 신호 — 매수/매도 시그널 생성 |
| C | 청산 — 보유 중 엑시트 판단 |

---

## 카테고리 1: Fama-French 팩터 시리즈 (글로벌 원전)

### A-01: Size Factor (SMB — Small Minus Big)
- **원전**: Fama & French (1993) *Journal of Finance* 48(2):427-465
- **출처 URL**: https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1993.tb04702.x
- **정의**: 소형주 포트폴리오 수익률 - 대형주 포트폴리오 수익률 (시총 중간값 기준 분리)
- **신호 방향**: 소형주 > 대형주 → SMB 프리미엄 존재 시 소형주 편향 포트폴리오 유리
- **한국 적용**:
  - ★ KOSPI+KOSDAQ 전체 분석에서 소형주 효과 통계적으로 유의 (Park et al. 2024)
  - 단, 소형주 제외 시 대부분 anomaly 유의성 소멸 → 소형주 집중 효과 주의
  - KOSDAQ 소형주에서 size premium 상대적으로 강함
- **PIT 주의사항**: 시총 기준 → 매 리밸런싱 시점(6월말) 기준 분류. 일중 시총은 daily_prices 즉시 계산 가능.
- **DB 가용성**: 즉시 — daily_prices.market_cap (또는 close x shares 계산)
- **Stage**: A (유니버스 분류), B (소형주 편향 매수 신호)
- **즉시 코드화 가능**: 예 — 시총 중간값 계산 후 소형주 필터

---

### A-02: Value Factor (HML — High Minus Low Book-to-Market)
- **원전**: Fama & French (1992) *Journal of Finance* 47(2):427-465
- **출처 URL**: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04398.x
- **정의**: 저PBR(저밸류에이션) 포트폴리오 편향. 고BM(=저PBR 역수) = Value 주식.
- **신호 방향**: PBR 하위 30% → Value 주식 편입 (HML 롱 포지션)
- **한국 적용**:
  - ★ Han et al. (2020) 148개 anomaly 연구에서 Value 이상수익률이 가장 강건하게 복제 (69.23% 유의)
  - 단, KOSPI 대형주만 한정 시 복제율 하락
  - PBR < 1.0 한국 시장에서 청산가치 이하 → 역사적으로 안전마진 역할
- **PIT 주의사항**: 분기 발표일 이후 자기자본 사용. 일중 시총은 현재가 기준.
- **DB 가용성**: 즉시 — financial_statements.pbr, financial_data.pbr
- **Stage**: A (저PBR 필터), B (매수 신호)
- **즉시 코드화 가능**: 예

---

### A-03: Profitability Factor — RMW (Robust Minus Weak)
- **원전**: Fama & French (2015) *Journal of Financial Economics* 116(1):1-22
- **출처 URL**: https://www.sciencedirect.com/science/article/pii/S0304405X14002323
- **정의**: 고영업수익성(RMW) - 저영업수익성 포트폴리오 수익률. 수익성 = 영업이익 / (자기자본 + 부채)
- **신호 방향**: 수익성 상위 30% 종목 편향 → 초과수익 기대
- **한국 적용**:
  - Han et al. (2020): 한국 Profitability 계열 anomaly 복제율 5%(value-weighted) — 가장 취약한 범주
  - Kang (2019): 분기 기반 수익성 팩터(연간 대신 분기)로 변환 시 한국 설명력 개선
  - 연간 기반 RMW는 한국에서 유의하지 않음 → 분기 업데이트 필수
- **PIT 주의사항**: 분기 발표 후 업데이트. TTM 기준 영업이익 사용.
- **DB 가용성**: 즉시 — financial_statements.operating_profit / (total_equity + total_liabilities)
- **Stage**: A (수익성 필터), B (매수 신호 보조)
- **즉시 코드화 가능**: 예 (분기 TTM 기준으로 구현 권장)

---

### A-04: Investment Factor — CMA (Conservative Minus Aggressive)
- **원전**: Fama & French (2015) *Journal of Financial Economics* 116(1):1-22
- **출처 URL**: https://www.sciencedirect.com/science/article/pii/S0304405X14002323
- **정의**: 저투자 기업 - 고투자 기업 포트폴리오. 투자율 = 총자산 증가율 (YoY)
- **신호 방향**: 총자산 증가율 하위 30% (보수적 투자) → CMA 롱 포지션
- **한국 적용**:
  - Han et al. (2020): Investment 계열 복제율 24.14% → 한국에서 상대적으로 약함
  - 과잉투자 기업 한국에서도 이후 수익률 저하 패턴 존재하나 일관성 낮음
- **PIT 주의사항**: 연간 총자산 발표 후 계산. 분기 총자산은 분기 발표일 이후.
- **DB 가용성**: 즉시 — financial_statements.total_assets (분기 시계열 YoY 계산)
- **Stage**: A (과잉투자 종목 제외 필터)
- **즉시 코드화 가능**: 예

---

## 카테고리 2: Carhart + 모멘텀 팩터

### A-05: ★ 52주 최고가 모멘텀 (52-Week High Momentum)
- **원전**: George & Hwang (2004) *Journal of Finance* 59(5):2145-2176
- **출처 URL**: https://quantpedia.com/strategies/52-weeks-high-effect-in-stocks
- **한국 실증**: Han et al. (2020) 148개 anomaly 중 52주 최고가 효과 통계적으로 유의. KAIST 석사 논문: 한국 KOSPI 52주 최고가 이상현상 확인
  - 출처: https://koasas.kaist.ac.kr/handle/10203/265711
- **정의**: 현재가 / 과거 52주(1년) 최고가 비율. 비율 상위 종목(최고가 근접) 매수.
- **신호 방향**: 현재가 / 52주 최고가 > 0.90 → 강한 업트렌드. 비율 하위(최고가 대비 괴리 큰) 종목 회피.
- **한국 특수**: 한국 148개 anomaly 연구에서 Value·Momentum 중 상대적으로 강건하게 복제된 지표
- **PIT 주의사항**: 일봉 종가 기준 rolling 252영업일 최고가 계산. T+1 사용 안전.
- **DB 가용성**: 즉시 — daily_prices.high (또는 close) 252일 rolling max
- **Stage**: A (추세 강도 필터), B (매수 신호)
- **즉시 코드화 가능**: 예

---

### A-06: Carhart 4-Factor 모멘텀 (12-1 Price Momentum)
- **원전**: Carhart (1997) *Journal of Finance* 52(1):57-82
- **출처 URL**: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1997.tb03808.x
- **정의**: 과거 12개월 수익률(최근 1개월 제외) = Return(t-12, t-1). 상위 10분위 매수.
- **신호 방향**: 12-1 수익률 상위 30% → 모멘텀 롱 포지션
- **한국 적용**:
  - 한국 시장 전통적 모멘텀은 통계적 유의성 약함 (단기 역전 현상으로 상쇄)
  - 한국 실증: 7~12개월 구간이 1~6개월보다 모멘텀 기여 높음 (Novy-Marx 2012 패턴 유사)
  - Sign momentum + Rank momentum 방식으로 변환 시 한국에서도 유의성 확인 (KAIST 2022)
  - 출처: https://koasas.kaist.ac.kr/handle/10203/294959
- **PIT 주의사항**: T-12개월 ~ T-1개월 수익률. T-1 skip으로 단기 역전 회피. T+1 시초가 진입.
- **DB 가용성**: 즉시 — daily_prices.close 252일 시계열
- **Stage**: B (매수 신호), A (종목 필터)
- **즉시 코드화 가능**: 예

---

### A-07: ★ 영업현금흐름/주가 (Operating Cash Flow to Price — OCP)
- **원전**: Sloan (1996) *Accounting Review* 71(3):289-315
- **한국 실증 출처**: Han et al. (2020) DOI: https://doi.org/10.1108/JDQS-03-2020-0004
- **한국 실증**: ★ 한국 148개 anomaly 중 OCP(영업현금흐름/주가)가 월평균 2.067%, t-statistic 4.843으로 가장 강한 유의성 — 최우선 재현 후보
- **정의**: 영업현금흐름(TTM) / 시가총액. 높을수록 현금창출력 대비 저평가.
- **신호 방향**: OCP 상위 30% → 강한 매수 신호
- **PIT 주의사항**: 현금흐름표는 분기 발표일 이후 사용. TTM = 최근 4분기 합산.
- **DB 가용성**: 외부 — 영업현금흐름 DB 미보유. DART OpenAPI 현금흐름표 수집 필요.
  - dart-fss 라이브러리: https://dart-fss.readthedocs.io/en/latest/dart_fs.html
  - OpenDartReader: https://github.com/FinanceData/OpenDartReader
- **Stage**: A (현금창출 기업 필터), B (매수 신호)
- **즉시 코드화 가능**: 아니오 (DART 현금흐름표 수집 선행 필요)

---

## 카테고리 3: q-Factor 모델 (Hou-Xue-Zhang)

### A-08: q-Factor — ROE 기반 수익성 (분기 갱신)
- **원전**: Hou, Xue & Zhang (2015) *Review of Financial Studies* 28(3):650-705
- **출처 URL**: https://www.nber.org/system/files/working_papers/w26538/w26538.pdf
- **한국 실증**: Kang (2019) *Asia-Pacific Journal of Financial Studies* — 한국에서 분기 기반 수익성 팩터가 FF5보다 설명력 우수.
  - 출처: https://onlinelibrary.wiley.com/doi/10.1111/ajfs.12274
- **정의**: 수익성 = ROE (분기별 갱신). 고ROE - 저ROE 포트폴리오 스프레드.
- **신호 방향**: 분기 ROE 상위 30% → 수익성 롱 포지션 (연간보다 분기 갱신 시 한국 설명력 개선)
- **핵심 인사이트**: 한국에서 연간 기준 수익성 팩터는 유의하지 않으나 분기 기준으로 전환 시 유의성 회복 → 분기 재무제표 발표 후 즉시 업데이트 필수
- **PIT 주의사항**: 분기 발표일 이후 ROE 갱신.
- **DB 가용성**: 즉시 — financial_statements.roe (분기 시계열), yearly_fundamentals.roe
- **Stage**: A (수익성 필터), B (매수 신호)
- **즉시 코드화 가능**: 예

---

### A-09: q-Factor — 투자 팩터 (자산증가율 역)
- **원전**: Hou, Xue & Zhang (2015); q5 모델 확장 — Hou et al. (2018) NBER WP 24709
- **출처 URL**: https://www.nber.org/system/files/working_papers/w24709/w24709.pdf
- **정의**: 투자율 = (총자산_t - 총자산_t-1) / 총자산_t-1. 저투자 기업이 고투자 기업보다 수익률 높음.
- **신호 방향**: 총자산 증가율 하위 30% → 과잉투자 미실시 기업 편향
- **한국 적용**: Bae (2024) *Asia-Pacific Journal of Financial Studies* — 한국에서 q5 팩터 모델이 97개 anomaly 설명에서 FF5보다 우수.
  - 출처: https://onlinelibrary.wiley.com/doi/10.1111/ajfs.12475
- **PIT 주의사항**: 연간 총자산 발표 후 계산.
- **DB 가용성**: 즉시 — financial_statements.total_assets
- **Stage**: A (과잉투자 필터)
- **즉시 코드화 가능**: 예

---

## 카테고리 4: Quality / Profitability 팩터

### A-10: Gross Profitability (Novy-Marx)
- **원전**: Novy-Marx (2013) *Journal of Financial Economics* 108(1):1-28
- **출처 URL**: https://www.sciencedirect.com/science/article/abs/pii/S0304405X13000044
- **정의**: 매출총이익(Gross Profit = 매출 - 매출원가) / 총자산. 높을수록 자산 대비 높은 수익성.
- **신호 방향**: GP/Assets 상위 30% → Quality 롱 포지션. PBR이 높더라도 수익성이 높으면 초과수익 가능.
- **한국 적용**:
  - 신흥시장(EM) 전반에서 ROE 기반 롱-숏 전략 연평균 5.1% 초과수익 (Gordon 2013, PIMCO)
  - 한국은 DART 공시로 매출원가 데이터 확인 가능
  - 한국 Profitability 계열 전반 약세이나 Gross Profitability는 별도 검증 필요
- **PIT 주의사항**: 매출원가(COGS) 분기 발표 후 계산. TTM 사용.
- **DB 가용성**: 외부 — 매출원가(COGS) DB 미보유. DART XBRL 손익계산서 수집 필요.
- **Stage**: A (품질 필터), B (매수 신호 보조)
- **즉시 코드화 가능**: 아니오 (DART COGS 수집 필요)

---

### A-11: Quality Minus Junk — QMJ (Asness/Frazzini/Pedersen)
- **원전**: Asness, Frazzini & Pedersen (2019) *Review of Accounting Studies* 24(1):34-112
- **출처 URL**: https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk
- **AQR 데이터셋**: https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Monthly (23개국 포함)
- **정의**: 품질 점수 = 수익성(Profitability) + 성장(Growth) + 안전성(Safety) + 배당성향(Payout) 4개 차원 평균.
  - 수익성: ROE, ROA, CFOA(현금흐름ROA), GMAR(매출총이익률), 발생주의 역수
  - 안전성: BAB 베타(저베타), 레버리지 역수, Z-score, ROE 변동성 역수
  - 배당성향: 배당수익률, 주식 환매 비율, 부채 발행 역수
- **한국 적용**: AQR QMJ 데이터셋이 한국 포함(23개국). 개별 재현 시 수익성+안전성 2개 차원만으로 단순화 가능.
- **PIT 주의사항**: 재무 항목 모두 발표 후 사용. 베타는 과거 60개월 월별 수익률.
- **DB 가용성**: 부분 — ROE, ROA, 레버리지, PBR은 즉시. 현금흐름ROA, COGS는 DART 필요.
- **Stage**: A (품질 스크리닝), B (QMJ 복합 신호)
- **즉시 코드화 가능**: 부분 (수익성+안전성 서브셋으로 단순화 버전 즉시 가능)

---

## 카테고리 5: Low Volatility / Low Beta 팩터

### A-12: ★ 저변동성 이상현상 (Low Volatility Anomaly)
- **원전 한국**: Kho & Kim (2014) *한국증권학회지* 43(3):573-603
- **출처 URL**: https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART001885142
- **글로벌 원전**: Ang, Hodrick, Xing & Zhang (2006) *Journal of Finance* 61(1):259-299
- **한국 실증**: ★
  - 표본: 1990.01 ~ 2012.12, KOSPI
  - 최저변동성 포트폴리오(P1): 거래비용 후 218% 누적수익 vs 최고변동성(P5): -98% 손실
  - 롱P1/숏P5 헤지: 월 평균 1.57% 초과수익 (거래비용 차감 후)
  - 2000년 이후 통계적 유의성 강화
  - 원인: 소음 거래자의 고변동성/고왜도 복권형 주식 선호 → 일시적 고평가 → 이후 수익률 저하
- **신호 방향**: 과거 252일 일별 수익률 표준편차 하위 30% 종목 편향 매수
- **한국 특수**: 여름(5~10월)에만 유의, 나머지 기간 약함 (계절성 주의)
- **PIT 주의사항**: T-252일 ~ T일 종가 기준 변동성 계산. T+1 시초가 진입.
- **DB 가용성**: 즉시 — daily_prices.close 252일 rolling std
- **Stage**: A (변동성 필터), B (저변동성 종목 매수 신호)
- **즉시 코드화 가능**: 예

---

### A-13: Betting Against Beta — BAB (Frazzini & Pedersen)
- **원전**: Frazzini & Pedersen (2014) *Journal of Financial Economics* 111(1):1-23
- **출처 URL**: https://pages.stern.nyu.edu/~lpederse/papers/BettingAgainstBeta.pdf
- **NBER WP**: https://www.nber.org/system/files/working_papers/w16601/w16601.pdf
- **정의**: 저베타 종목 레버리지 롱 - 고베타 종목 디레버리지 숏.
- **신호 방향**: CAPM 베타 하위 30% 종목 편향 매수
- **한국 적용**:
  - 부분 지지: 인도, 중국, 한국에서 BAB 현상 확인되나 한국에서는 약함
  - 비판: Cho & Kim (2025) *한국재무학회지* — FF-3 위험 조정 후 거래비용 차감 시 BAB 전략 수익 비유의
  - 출처: https://www.e-kjfs.org/journal/view.php?doi=10.26845%2FKJFS.2025.04.54.2.97
  - Park et al. (2024): 한국에서 베타 효과는 소형주에서만 유의, 고유동성 표본에서 사라짐
- **PIT 주의사항**: 베타 = 과거 60개월 월별 수익률 회귀. T+1 시초가 진입.
- **DB 가용성**: 즉시 — daily_prices.close + KOSPI 지수 수익률로 베타 계산
- **Stage**: A (저베타 필터), B (보조 신호)
- **즉시 코드화 가능**: 예 (단, 한국에서 유효성 제한적 — 필터 레벨만 활용 권장)

---

## 카테고리 6: 한국 시장 특화 실증 anomaly

### A-14: ★ 한국 148개 anomaly 실증 — Value 강건 anomaly 종합
- **원전**: Han, Lee & Kang (2020) *Journal of Derivatives and Quantitative Studies: 선물연구* 28(2):3-50
- **DOI**: https://doi.org/10.1108/JDQS-03-2020-0004
- **출처 URL**: https://www.emerald.com/insight/content/doi/10.1108/jdqs-03-2020-0004/full/html
- **표본**: 2000.01 ~ 2019.06, KOSPI + KOSDAQ
- **주요 발견**:
  - 148개 anomaly 중 value-weighted 기준 37.8%만 t > 1.96 달성
  - ★ Value 계열: 69.23% 유의 (가장 강건) — PBR, 배당수익률, 현금흐름/주가 포함
  - ★ Trading Friction 계열: 48.15% 유의 — 유동성 관련 지표
  - ★ Momentum 계열: 66.67% 유의 (strict 기준 26.67%로 하락)
  - Profitability 계열: 5% 유의 — 한국에서 가장 취약한 범주
  - 핵심 시사점: 데이터 마이닝이 상당 부분 설명, 소형주 포함 시 복제율 과대 측정
- **신호 방향**: Value 계열 복합 점수 상위 종목 편향 (PBR + 현금흐름/주가 + 배당수익률 복합)
- **DB 가용성**: 부분 — PBR, 배당수익률은 즉시. 영업현금흐름은 DART 필요.
- **Stage**: A (다차원 Value 필터)
- **즉시 코드화 가능**: 부분

---

### A-15: ★ 한국 팩터 투자 전략 성과 분석 (1990~2021)
- **원전**: 박종원, 엄윤성, 엄철준 (2024) *재무관리연구* 41(1):99-136
- **출처 URL**: https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003056534
- **표본**: 1990.01 ~ 2021.12, KOSPI + KOSDAQ 전종목
- **주요 발견**:
  - ★ 비유동성(Illiquidity) 롱-숏: 통계적으로 유의한 양(+) 성과
  - ★ 공왜도(Coskewness) 롱-숏: 통계적으로 유의한 양(+) 성과
  - 베타 효과: 통계적으로 유의한 음(-) — 고베타 = 저수익 확인
  - 고유변동성(Idiosyncratic Volatility): 음(-) 성과 — 고유변동성 높을수록 수익률 낮음
  - MAX 효과(최대일간수익률): 음(-) — 복권형 주식 회피 신호
  - 소형주 제외 시 비유동성, 베타 효과 유의성 소멸 → 소형주 집중 현상
- **DB 가용성**: 즉시 — daily_prices로 비유동성(Amihud ratio), 고유변동성, 베타, MAX 모두 계산 가능
- **Stage**: A (복권형 종목 제외 필터), B (비유동성 프리미엄 신호)
- **즉시 코드화 가능**: 예

---

### A-16: ★ 저변동성 이상현상 + 계절성 (여름 효과)
- **원전**: 서울대학교 석사 논문 — 주식 수익률의 계절적 특성과 저변동성 이상현상 연구
- **출처 URL**: https://s-space.snu.ac.kr/handle/10371/124659
- **한국 실증**: ★ 저변동성 이상현상이 5~10월(여름)에만 통계적으로 유의. 11~4월(겨울)에는 비유의.
- **신호 방향**: 5월~10월 구간 — 저변동성 종목 추가 가중치 부여. 11~4월에는 저변동성 bias 약화.
- **한국 특수**: 한국 시장 고유 계절성 패턴으로 글로벌 low-vol 전략 단순 적용 대비 성과 개선 가능
- **PIT 주의사항**: 당월 월초 기준 계절 판단. 변동성은 T-252일 rolling.
- **DB 가용성**: 즉시 — daily_prices.close
- **Stage**: B (계절성 가중 신호), A (계절 필터 조건)
- **즉시 코드화 가능**: 예

---

### A-17: 한국 모멘텀 — 잔차 모멘텀 (Residual Momentum)
- **원전 한국**: KAIST 석사 논문 — 국내 주식시장 잔차 모멘텀 전략 실증 분석
- **출처 URL**: https://koasas.kaist.ac.kr/handle/10203/242768
- **글로벌 원전**: Blitz, Huij & Martens (2011) *Journal of Financial and Quantitative Analysis*
- **정의**: 원시 수익률 모멘텀이 아닌 FF-3 팩터 제거 후 잔차(알파) 기준 모멘텀.
- **한국 적용**: 전통적 가격 모멘텀 한국에서 유의성 약하나, 잔차 모멘텀은 추가 설명력 보유 가능성
- **신호 방향**: 과거 6~12개월 FF-3 알파 상위 30% → 잔차 모멘텀 롱
- **PIT 주의사항**: 팩터 회귀에 발표된 재무 데이터만 사용.
- **DB 가용성**: 부분 — daily_prices.close 있음. FF-3 팩터 재현에 시총, PBR 필요.
- **Stage**: B (매수 신호 보조)
- **즉시 코드화 가능**: 부분 (FF-3 팩터 계산 구현 선행 필요)

---

### A-18: ★ 한국 발생주의 이상현상 (Accrual Anomaly — 필터로 활용)
- **원전 한국**: Kim & Kim (2015) *Pacific-Basin Finance Journal* 33:75-88
- **출처 URL**: https://www.sciencedirect.com/article/abs/pii/S0927538X15000293
- **글로벌 원전**: Sloan (1996) *Accounting Review* 71(3):289-315
- **한국 실증**: ★ 이익 발생여부 무관(흑자, 적자 모두)하게 한국에서 발생주의 이상현상 존재.
  - 단, 2011년 헤지펀드 도입 이후 발생주의 anomaly 급격히 약화 → 현재는 거의 소멸
  - 따라서 발생주의 신호는 알파 소스보다 고발생주의 종목 제외 필터로 활용 권장
- **정의**: 발생주의 비율 = (순이익 - 영업현금흐름) / 총자산. 낮을수록 현금이익 비중 높음.
- **신호 방향**: 발생주의 비율 하위 30% → 현금 기반 이익 우량 기업 (필터 활용)
- **PIT 주의사항**: 영업현금흐름 분기 발표 후 계산. DART 현금흐름표 수집 필요.
- **DB 가용성**: 외부 — 영업현금흐름 DB 미보유. DART 필요.
- **Stage**: A (고발생주의 종목 제외 필터)
- **즉시 코드화 가능**: 아니오 (DART 현금흐름 수집 선행)

---

## 카테고리 7: Value + Momentum 결합 및 이벤트 전략

### A-19: Value + Momentum 결합 (Asness-Moskowitz-Pedersen)
- **원전**: Asness, Moskowitz & Pedersen (2013) *Journal of Finance* 68(3):929-985
- **출처 URL**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2174501
- **정의**: Value 팩터와 Momentum 팩터를 같은 비중(50/50)으로 결합. 두 팩터 음의 상관관계 → 결합 시 다각화 효과 극대화.
- **신호 방향**: Value 점수 + Momentum 점수 가중 평균 상위 30% 종목 편향 매수
- **한국 적용**:
  - 한국에서 단독 모멘텀은 약하나, Value와 결합 시 상호 보완 가능성
  - 한국재무학회 실증: 모멘텀+가치 결합 전략이 한국 증권시장에서 유효
  - 출처: https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART002022444
- **PIT 주의사항**: Value 재무 데이터는 발표 후. Momentum은 T-12 ~ T-1.
- **DB 가용성**: 부분 — PBR, ROE는 즉시. 현금흐름/주가는 DART 필요.
- **Stage**: B (복합 매수 신호)
- **즉시 코드화 가능**: 부분 (PBR + 12-1 momentum 단순 결합으로 즉시 가능)

---

### A-20: ★ 배당 수익률 예측력 (Dividend Yield Predictability)
- **원전 한국**: 박종원 외 (2024) *재무관리연구* — 배당수익률을 통한 주식수익률 예측
- **출처 URL**: https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003234107
- **글로벌 원전**: Fama & French (1988) *Journal of Finance* 43(3):661-676
- **한국 실증**: ★ KOSPI + KOSDAQ 2010~2024.10 분석 — 배당 기준일 및 배당 공시일 기점으로 배당수익률과 주식수익률 간 통계적으로 유의한 관계 확인
- **정의**: 배당수익률 = 연간 배당금 / 현재가. 배당수익률이 높은 고배당주의 배당 공시일 전후 수익률 추종.
- **신호 방향**: 배당수익률 > 3% + 배당 공시일 D-5 ~ D+2 구간 매수 → 단기 수익 기대
- **한국 특수**: 12월 결산법인 배당 집중(연 1회). 11~12월 배당주 집중. 배당락일 전 매수 후 락일 전 청산 패턴 유효.
- **PIT 주의사항**: 배당 공시일 이후 사용. financial_statements.dividend_yield 분기 발표 기준.
- **DB 가용성**: 즉시 — financial_statements.dividend_yield; corp_events 테이블 배당 공시 연동
- **Stage**: A (배당주 필터), B (배당 공시 이벤트 매수 신호), C (배당락일 전 청산)
- **즉시 코드화 가능**: 예

---

### A-21: ★ Amihud 비유동성 프리미엄 (Illiquidity Premium)
- **원전**: Amihud (2002) *Journal of Financial Markets* 5(1):31-56
- **출처 URL**: https://www.sciencedirect.com/science/article/abs/pii/S1386418101000246
- **한국 실증**: ★ Park et al. (2024) — 한국 비유동성 롱-숏 전략 통계적으로 유의한 양(+) 성과. 소형주 집중 현상이지만 소형주 내에서 일관성 높음.
- **정의**: Amihud Ratio = |일별수익률| / 일별거래대금 (x10^6). 높을수록 비유동 종목.
- **신호 방향**: Amihud 비율 상위(비유동) 종목 → 유동성 프리미엄 획득 전략. 단, 실제 매매 시 스프레드, 시장충격 비용 반드시 차감.
- **PIT 주의사항**: 과거 21일(1개월) rolling 평균 Amihud ratio. T+1 시초가 사용.
- **DB 가용성**: 즉시 — daily_prices.close, volume, trading_value
- **Stage**: A (유동성 그룹 분류 필터), B (비유동성 프리미엄 신호)
- **즉시 코드화 가능**: 예

---

## 카테고리 8: 공식 데이터 API 가이드

### A-22: DART OpenAPI — 현금흐름표 수집 가이드
- **공식 URL**: https://opendart.fss.or.kr/intro/main.do
- **개발 가이드**: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020
- **Python 라이브러리**:
  - dart-fss (PyPI): https://pypi.org/project/dart-fss/
  - OpenDartReader (GitHub): https://github.com/FinanceData/OpenDartReader
- **제공 데이터**: 공시정보, 재무상태표, 손익계산서, 현금흐름표, 지분공시, 주요사항보고서
- **등록 방법**: 무료 가입 후 API 인증키 자동 발급. 누구든 사용 가능.
- **데이터 범위**: 2012년 이후 분기별 연결/별도 재무제표 (XBRL)
- **Stage**: 인프라 — A-07(OCP), A-10(Gross Profitability), A-18(Accrual) 구현 선행 조건
- **즉시 코드화 가능**: 예 (API 키 발급 후)

dart-fss 현금흐름표 추출 예시:

```python
import dart_fss as dart
dart.set_api_key('YOUR_API_KEY')
corp_list = dart.get_corp_list()
corp = corp_list.find_by_stock_code('005930')[0]
fs = corp.extract_fs(bgn_de='20230101')
cf = fs['cf']  # 현금흐름표
```

---

### A-23: 한국은행 ECOS API — 거시지표 수집 가이드
- **공식 URL**: https://ecos.bok.or.kr/api/
- **Python 라이브러리**: PublicDataReader (Ecos 클래스), ecos_api_loader
  - ecos_api_loader GitHub: https://github.com/jmlee8939/ecos_api_loader
- **주요 데이터**: 기준금리, 국고채수익률, 환율, GDP, 소비자물가, M2통화량
- **등록 방법**: 한국은행 ECOS 회원가입 후 인증키 발급 (1일 이내 활성화)
- **활용 전략**: 금리 상승 국면 → 고배당, 저부채 기업 선호 필터. 환율 급등 → 수출주 편향.
- **Stage**: A (거시 국면 필터 조건)
- **즉시 코드화 가능**: 예

```python
from PublicDataReader import Ecos
api = Ecos('YOUR_API_KEY')
# 기준금리 시계열 조회
rate = api.get_statistic_search(stat_code='722Y001', cycle='D')
```

---

### A-24: KRX Data Marketplace + KRX OpenAPI — 투자자별 매매동향
- **공식 데이터 조회**: https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020301
- **KRX OpenAPI**: https://openapi.krx.co.kr/ (2010년 이후, 지수/주식/채권/파생 가격 데이터)
- **중요 한계**: KRX OpenAPI에는 투자자별 매매동향(외국인/기관 순매수) 데이터가 없음. 가격/지수 데이터만 제공.
- **투자자별 매매동향 접근 경로**:
  1. KRX Data Marketplace 웹 조회 (data.krx.co.kr) → 수동 CSV 다운로드
  2. pykrx 라이브러리: KRX 스크래핑. get_market_net_purchases_of_equities() 제공.
  3. KIS API: /uapi/domestic-stock/v1/quotations/foreign-institution-total (장중 가집계용)
- **Stage**: 데이터 인프라 — 04_flow.md F-01~F-07 구현 전제 조건

---

## 부록: 외국인순매수 데이터 수집 대안 권고

> 배경: 직원 #3가 pykrx → FinanceDataReader → 네이버 3차 시도 실패. KIS API TR 404 오류.

### 문제 분석

| 경로 | 상태 | 실패 원인 추정 |
|------|------|--------------|
| pykrx get_market_net_purchases_of_equities() | 실패 | 파라미터 순서 오류 또는 KRX 차단 |
| FinanceDataReader | 실패 | 외국인 순매수 데이터 미지원 |
| 네이버 금융 | 실패 | 구조 변경으로 스크래핑 차단 |
| KIS API FHPTJ04400000 | 404 | 장중 가집계용 TR — 장 종료 후 미제공 |

### 권고 대안 (우선순위 순)

**1순위 — pykrx 파라미터 순서 재확인 및 최신 버전 업그레이드**

```python
from pykrx import stock
# 파라미터 순서: (시작일, 종료일, 시장, 투자자유형)
df = stock.get_market_net_purchases_of_equities(
    "20260520", "20260524",
    "KOSPI",      # 세 번째: 시장 (KOSPI / KOSDAQ / ALL)
    "외국인"      # 네 번째: 투자자 유형
)
# pip install pykrx --upgrade 후 재시도
```

**2순위 — KIS API 올바른 TR 코드 재확인**

KIS OpenAPI 포탈(https://apiportal.koreainvestment.com/) 로그인 후 [국내주식] → [시세분석] → 투자자별 메뉴 직접 확인. FHPTJ04400000은 장중 가집계용이므로 장 종료 후 확정 데이터는 별도 TR 필요.

**3순위 — KRX Data Marketplace CSV 수동/자동 다운로드**

data.krx.co.kr → [주식] → [투자자별 거래실적] → 날짜 선택 후 CSV 다운로드. Selenium/Playwright로 자동화 가능하나 이용약관 확인 필요.

**4순위 — KRX OpenAPI 서비스 목록 주기적 확인**

현재 KRX OpenAPI에 투자자별 매매동향 미포함. 신규 API 추가 가능성 있으므로 주기적 확인:
https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd

**5순위 — 상업용 데이터 벤더 (최후 수단)**

FnGuide Dataguide: 기관/외국인 순매수 히스토리 포함 (유료)

### 즉시 실행 체크리스트

1. pip install pykrx --upgrade 로 최신 버전 업그레이드
2. 파라미터 순서 재확인: (start, end, market, investor) 형식
3. KIS 포탈 로그인 → [국내주식] → [시세분석] → 투자자별 메뉴 TR코드 재확인
4. KRX data.krx.co.kr 수동 조회로 데이터 존재 여부 확인

---

## Stage 분포 요약

| Stage | 시그널 ID | 개수 |
|-------|-----------|------|
| A (필터) | A-01, A-02, A-04, A-05, A-09, A-12, A-13, A-14, A-15, A-16, A-18, A-20, A-21 | 13 |
| B (신호) | A-03, A-06, A-07, A-08, A-10, A-11, A-12, A-15, A-17, A-19, A-20, A-21 | 12 |
| C (청산) | A-20 | 1 |
| 인프라 | A-22, A-23, A-24 | 3 |

---

## 한국 시장 정량 검증 anomaly Top 5 (재현 우선순위)

| 순위 | ID | 명칭 | 근거 논문 | 핵심 수치 | DB 즉시 가용 |
|------|----|------|----------|----------|------------|
| 1 | A-07 | 영업현금흐름/주가 (OCP) | Han et al. (2020) | 월 2.067%, t=4.843 | 아니오 (DART 필요) |
| 2 | A-12 | 저변동성 이상현상 | Kho & Kim (2014) | 헤지 월 1.57% (비용 차감) | 예 |
| 3 | A-05 | 52주 최고가 모멘텀 | Han et al. (2020) | 한국 148개 중 유의 | 예 |
| 4 | A-02 | 저PBR Value | Han et al. (2020) | 69.23% 복제 (최고) | 예 |
| 5 | A-21 | 비유동성 프리미엄 | Park et al. (2024) | 유의한 양(+) | 예 |

---

## DB 즉시 가용 Top 5

| 순위 | ID | 시그널명 | 즉시 계산 방법 |
|------|----|---------|--------------|
| 1 | A-12 | 저변동성 이상현상 | daily_prices.close.pct_change().rolling(252).std() |
| 2 | A-05 | 52주 최고가 모멘텀 | daily_prices.close.rolling(252).max() |
| 3 | A-02 | 저PBR Value 필터 | financial_statements.pbr |
| 4 | A-21 | 비유동성 프리미엄 | abs(ret)/trading_value * 1e6 |
| 5 | A-15 | 고유변동성 제외 필터 | idiosyncratic vol = total vol - market vol |

---

## 외부 데이터 필요 컨셉 요약

| 데이터 소스 | 필요 시그널 |
|------------|-----------|
| DART 현금흐름표 (dart-fss / OpenDartReader) | A-07(OCP), A-11(QMJ CFOA), A-18(Accrual) |
| DART 손익계산서 세부(COGS) | A-10(Gross Profitability) |
| 한국은행 ECOS API | A-23(거시 국면 필터) |
| pykrx (KRX 스크래핑) | A-24 부록(외국인 순매수 대안) |

---

## 출처 요약

| 원전 | 인용 시그널 |
|------|-----------|
| Fama & French (1993) Journal of Finance | A-01 |
| Fama & French (1992) Journal of Finance | A-02 |
| Fama & French (2015) Journal of Financial Economics | A-03, A-04 |
| George & Hwang (2004) Journal of Finance | A-05 |
| Carhart (1997) Journal of Finance | A-06 |
| Sloan (1996) Accounting Review 71(3):289-315 | A-07, A-18 |
| Hou, Xue & Zhang (2015) Review of Financial Studies | A-08, A-09 |
| Hou et al. (2018) NBER WP 24709 — q5 | A-09 |
| Novy-Marx (2013) Journal of Financial Economics | A-10 |
| Asness, Frazzini & Pedersen (2019) Review of Accounting Studies | A-11 |
| Ang, Hodrick, Xing & Zhang (2006) Journal of Finance | A-12 (글로벌) |
| Kho & Kim (2014) 한국증권학회지 43(3):573-603 | A-12 (한국 실증) ★ |
| Frazzini & Pedersen (2014) Journal of Financial Economics | A-13 |
| Cho & Kim (2025) 한국재무학회지 | A-13 (한국 비판) |
| Han, Lee & Kang (2020) DOI:10.1108/JDQS-03-2020-0004 | A-14 ★ |
| 박종원, 엄윤성, 엄철준 (2024) 재무관리연구 41(1) | A-15, A-21 ★ |
| SNU 석사논문 — 저변동성 계절성 | A-16 ★ |
| KAIST 석사논문 — 잔차 모멘텀 | A-17 |
| Kim & Kim (2015) Pacific-Basin Finance Journal 33:75-88 | A-18 ★ |
| Asness, Moskowitz & Pedersen (2013) Journal of Finance | A-19 |
| 박종원 외 (2024) 재무관리연구 — 배당수익률 | A-20 ★ |
| Amihud (2002) Journal of Financial Markets 5(1):31-56 | A-21 |
| DART OpenAPI, dart-fss, OpenDartReader | A-22 |
| 한국은행 ECOS API, PublicDataReader | A-23 |
| KRX OpenAPI, KRX Data Marketplace, pykrx | A-24 |