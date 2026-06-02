# 해외 가치투자 클래식 — 시그널 카탈로그

> 작성일: 2026-05-26 | 조사자: document-specialist (Claude Sonnet 4.6)
> 목적: Phase 5 시그널 패밀리 확장 — 해외 가치투자 클래식 책 5권 발굴 및 컨셉 추출
> No Look-Ahead 원칙: 모든 재무 데이터는 분기 발표일(공시일) 이후만 사용 (Point-in-Time 강제)

---

## 발굴 서적 5권

| # | 제목 | 저자 | 출판사 | 출간년도 | ISBN |
|---|------|------|--------|---------|------|
| 1 | The Intelligent Investor (현명한 투자자) | Benjamin Graham | Harper & Brothers | 1949 (개정판 1973) | 978-0-06-055566-5 |
| 2 | The Little Book That Beats the Market | Joel Greenblatt | Wiley | 2005 | 978-0-471-73306-5 |
| 3 | You Can Be a Stock Market Genius | Joel Greenblatt | Simon & Schuster | 1997 | 978-0-684-84007-9 |
| 4 | The Dhandho Investor | Mohnish Pabrai | Wiley | 2007 | 978-0-470-04389-9 |
| 5 | Common Stocks and Uncommon Profits | Philip A. Fisher | Harper & Brothers | 1958 (Wiley 재판 1996) | 978-0-471-44550-0 |

> 참고 출처: Goodreads, Amazon, Wikipedia — 각 항목별 공식 도서 정보 확인.
> Graham Security Analysis (1934), Buffett Berkshire Letters, Schloss 16 Principles, Lynch One Up on Wall Street (1989) 등도 보조 출처로 활용.

---

## 범례 (DB 가용성 컬럼)

| 기호 | 의미 |
|------|------|
| 즉시 | 우리 DB 컬럼으로 즉시 계산 가능 |
| 부분 | DB에 일부 데이터 있음, 추가 계산 필요 |
| 외부 | 외부 데이터 소스 필요 (DART API, KRX, 컨센서스 등) |

## Stage 태그 정의

| 태그 | 의미 |
|------|------|
| Stage-A | 필터/스크리닝 — 종목 유니버스 압축 |
| Stage-B | 진입 시그널 — 매수 타이밍 포착 |
| Stage-C | 청산 시그널 — 매도/홀딩 판단 |

---

## 카테고리 1: Graham 방어적 투자자 기준 (The Intelligent Investor, 1973)

### V-01: Graham Defensive 7 Criteria — 종합 점수
- **정의**: Benjamin Graham이 제시한 방어적 투자자용 7가지 정량 기준의 충족 개수 합산 (0~7점)
- **7가지 기준**:
  1. 기업 규모 — 연 매출 >= 1,000억 원 (원서: $100M 물가조정)
  2. 재무 안정성 — 유동비율 >= 2.0 (유동자산 / 유동부채)
  3. 이익 안정성 — 최근 10년간 적자 없음
  4. 배당 지속성 — 최근 20년 이상 연속 배당 지급
  5. 이익 성장 — 최근 10년 EPS CAGR >= 3.3% (10년간 1/3 이상 증가)
  6. 적정 PER — PER <= 15 (최근 3년 평균 이익 기준)
  7. 적정 PBR — PBR <= 1.5; 또는 PER x PBR <= 22.5
- **신호 방향**: 6~7점 충족 → Stage-A 통과 후보; 4점 이하 → 제외
- **Graham Number**: PER x PBR <= 22.5의 상한을 역산하면 Graham Number = sqrt(22.5 x EPS x BVPS)
- **PIT 주의사항**: EPS·BVPS는 최신 발표 연간보고서 기준. 10년 이익 안정성은 과거 발표 데이터만 사용.
- **Stage 태그**: Stage-A (유니버스 필터)
- **한국 시장 적용성**:
  - 기준 1 (규모): 중소형주 대부분 탈락 — 코스피 대형주·코스닥 일부만 통과
  - 기준 2 (유동비율 >= 2): 한국 제조업 평균 ~150%로 엄격. 약 30~40% 종목 통과 가능
  - 기준 3 (10년 무적자): KOSPI200 내 약 50% 수준 통과 예상
  - 기준 4 (20년 배당): 한국 기업 대부분 미충족 → 10년 연속으로 완화 권장
  - 기준 6 (PER <= 15): 국내 저PER 종목 다수 통과 가능 (코스피 평균 ~12)
  - 기준 7 (PBR <= 1.5): 코스피 평균 PBR ~0.8로 대부분 통과
  - **종합**: 배당 기준 완화 시 5개 기준 적용 가능. 현재 DB로 기준 2·6·7은 즉시 계산 가능.
- **DB 가용성**: 부분 — PER·PBR·유동비율은 즉시. 이익 안정성(10년 EPS)·배당 연속성은 외부 보강 필요.
- **즉시 코드화 여부**: 부분 코드화 가능 (PER/PBR/유동비율 기준 3개는 즉시)
- **출처**: Graham, B. The Intelligent Investor (1973) Ch.14; HarperCollins Publishers
- **출처 URL**: https://buffettpedia.com/2024/06/defensive-investors-portfolio-seven-criteria-of-common-stock-seletion/

---

### V-02: Graham Number (내재가치 상한선)
- **정의**: Graham Number = sqrt(22.5 x EPS x BVPS)
  - EPS: 주당순이익 (TTM 또는 최근 연간)
  - BVPS: 주당 순자산가치 (Book Value Per Share)
  - 22.5 = PER 15 x PBR 1.5 상한 곱
- **신호 방향**: 현재 주가 < Graham Number → 저평가 (매수 후보); 주가/Graham Number < 0.66 → 강력 매수
- **PIT 주의사항**: EPS·BVPS 모두 최신 발표 분기 기준. 분기 발표 전에는 이전 분기 값 유지.
- **Stage 태그**: Stage-A (필터), Stage-B (진입 시그널 — 주가 < Graham Number 시)
- **한국 시장 적용성**: EPS·BVPS 모두 DB 가용. 한국 저PBR 시장 특성상 Graham Number 하회 종목 다수 존재 (코스피 PBR ~0.8). 실용적으로 적용 가능.
- **DB 가용성**: 즉시 — financial_statements.per, financial_data.eps, financial_statements.pbr (BVPS 역산 가능)
- **즉시 코드화 여부**: 즉시 코드화 가능 (Top 1 추천)
- **출처**: Graham, B. The Intelligent Investor (1973) — revised formula; Wikipedia Graham Formula
- **출처 URL**: https://en.wikipedia.org/wiki/Benjamin_Graham_formula

---

### V-03: Net-Net (NCAV — Net Current Asset Value)
- **정의**: NCAV = 유동자산 - 총부채 (우선주 포함)
  - 매수 조건: 현재 주가 <= NCAV Per Share x 0.67 (33% 할인)
  - NCAV Per Share = NCAV / 발행주식수
- **신호 방향**: 주가 < NCAV x 0.67 → 청산가치 이하 거래 → 강력 매수 후보 (Graham 원전 기준)
- **역사적 수익률**: 1970~1983년 연 29.4% (AAII 연구)
- **PIT 주의사항**: 유동자산·총부채는 최신 분기 발표 기준.
- **Stage 태그**: Stage-A (극단적 저평가 필터)
- **한국 시장 적용성**: 코스피·코스닥 소형주 중 NCAV 할인 종목 존재. 단, 조선·중공업 등 대규모 유동부채 업종 주의. 일부 지주회사·지분투자회사 적용 가능.
- **DB 가용성**: 부분 — financial_statements.current_assets, financial_statements.total_liabilities 가용. 발행주식수는 daily_prices.market_cap / 주가로 추산 가능.
- **즉시 코드화 여부**: 부분 코드화 가능 (발행주식수 직접 DB 컬럼 확인 필요)
- **출처**: Graham, B. & Dodd, D. Security Analysis (1934); AAII Net Current Asset Value Approach
- **출처 URL**: https://www.aaii.com/journal/article/benjamin-graham-s-net-current-asset-value-approach

---

### V-04: Graham Earnings Power Value (EPV)
- **정의**: EPV = Adjusted EBIT x (1 - 세율) / WACC
  - Adjusted EBIT: 비경상 항목 제거 후 정상화 영업이익 (3년 평균 활용)
  - WACC: 가중평균자본비용 (한국 코스피 기준 약 8~10% 사용 가능)
- **신호 방향**: 시가총액 < EPV → 저평가; EPV > NAV (순자산가치) 이면 경쟁우위 존재
- **확장**: EPV vs. Reproduction Value 비교로 경제적 해자(Moat) 유무 판별
- **PIT 주의사항**: EBIT는 TTM 또는 3년 평균 (발표 데이터만). WACC는 시장금리 반영 필요.
- **Stage 태그**: Stage-A (밸류에이션 기반 필터)
- **한국 시장 적용성**: 영업이익(EBIT proxy)은 financial_statements.operating_profit으로 즉시 계산. 세율은 법인세 데이터 필요 (DART). 실용적 간이 버전으로 EPV 상위 분위 필터 구현 가능.
- **DB 가용성**: 부분 — operating_profit 가용. 법인세율은 DART 필요.
- **즉시 코드화 여부**: 간이 버전(고정 세율 25% 가정) 즉시 코드화 가능
- **출처**: Graham, B. The Intelligent Investor (1973); Greenwald, B. Value Investing (2001)
- **출처 URL**: https://www.oldschoolvalue.com/investing-strategy/benjamin-graham-investing-checklist/

---

## 카테고리 2: Magic Formula (Greenblatt, The Little Book That Beats the Market, 2005)

### V-05: Magic Formula — Earnings Yield (EBIT/EV)
- **정의**: Earnings Yield = EBIT / EV
  - EV = 시가총액 + 순차입금 (총차입금 - 현금)
  - EBIT = 영업이익 (이자·세금 차감 전)
- **신호 방향**: Earnings Yield 상위 분위(높을수록 저평가) → 순위화 후 Magic Formula 합산에 활용
- **업종 제외**: 금융주(은행·증권·보험), 유틸리티 — EV/EBIT 적용 불가
- **PIT 주의사항**: EBIT는 TTM 또는 최신 연간 발표 기준. EV 계산의 차입금·현금은 최신 분기.
- **Stage 태그**: Stage-A (순위 필터)
- **한국 시장 적용성**: operating_profit(EBIT proxy) 가용. EV 계산에 현금·총차입금 세부 항목 DART 필요. 간이 버전: EV=시가총액+이자부부채(총부채 근사)로 부분 계산 가능.
- **DB 가용성**: 부분 — operating_profit·market_cap 즉시. 순차입금 계산은 DART 보강 필요.
- **즉시 코드화 여부**: 부분 코드화 가능 (총부채 근사 활용)
- **출처**: Greenblatt, J. The Little Book That Beats the Market (2005) Wiley
- **출처 URL**: https://www.quantifiedstrategies.com/the-magic-formula-strategy/

---

### V-06: Magic Formula — Return on Capital (ROIC_Greenblatt)
- **정의**: ROIC_G = EBIT / (순운전자본 + 순유형고정자산)
  - 순운전자본 = 유동자산 - 유동부채 (단, 비이자부 유동부채만)
  - 순유형고정자산 = 유형고정자산 (감가상각 누계 차감 후)
- **신호 방향**: ROIC_G 상위 분위 → Magic Formula ROIC 순위에 활용
- **주의**: Greenblatt은 감가상각 및 영업권(Goodwill) 제거 후 유형 순자산만 분모로 사용
- **PIT 주의사항**: 투하자본 구성 항목은 최신 분기 발표 기준.
- **Stage 태그**: Stage-A (품질 필터)
- **한국 시장 적용성**: current_assets·current_liabilities·total_assets 가용. PP&E(유형고정자산) 세부값은 DART XBRL 자산 명세 필요. 간이: ROIC_G 대략 EBIT / (유동자산 - 유동부채 + 총자산 - 유동자산)로 근사 가능.
- **DB 가용성**: 부분 — 근사 계산 가능. 정밀 PP&E는 외부 필요.
- **즉시 코드화 여부**: 부분 코드화 가능 (근사치)
- **출처**: Greenblatt, J. The Little Book That Beats the Market (2005) Wiley
- **출처 URL**: https://aaii.medium.com/greenblatts-magic-formula-for-beating-the-market-ccfc429287ec

---

### V-07: Magic Formula 합산 순위 (Composite Rank)
- **정의**: Composite_Rank = Rank(EBIT/EV) + Rank(ROIC_G)
  - 유니버스 전체 종목 대상 각 지표를 1위(최고)~N위로 순위화
  - 합산 순위 낮을수록 Magic Formula 우선 종목
- **선택 방법**: 합산 순위 상위 20~30종목 → 매월 2~3개 편입, 1년 보유 후 교체
- **역사적 수익률**: Greenblatt 백테스트 1988~2004 평균 33%/년 vs 시장 12%
- **PIT 주의사항**: 순위화는 최신 발표 재무 데이터 기준. 월별 리밸런싱 시 발표 시점 확인 필수.
- **Stage 태그**: Stage-A (포트폴리오 선별 필터)
- **한국 시장 적용성**: KRX 전 종목(금융·유틸리티 제외) 대상 반년/1년 리밸런싱. 코스피200 내 약 150~170종목 대상으로 구현 현실적.
- **DB 가용성**: 부분 — V-05·V-06 DB 가용성 동일 적용
- **즉시 코드화 여부**: 부분 코드화 가능 (Top 2 추천 — 근사치 버전)
- **출처**: Greenblatt, J. The Little Book That Beats the Market (2005); Quant Investing Magic Formula Backtest (2026)
- **출처 URL**: https://www.quant-investing.com/blog/magic-formula-investment-strategy-back-test

---

## 카테고리 3: Buffett Owner Earnings / Quality Compounder (Berkshire Letters, 1977~현재)

### V-08: Owner Earnings (오너 이익)
- **정의**: Owner Earnings = 순이익 + 감가상각·상각비 +/- 비현금 항목 - 유지보수 CapEx
  - Buffett 원전(1986 Berkshire Letter): (a) 보고 이익 + (b) D&A - (c) 연평균 유지보수 설비투자
  - 간소화: Owner Earnings = 영업현금흐름 - 유지보수 CapEx
- **FCF와 차이**: FCF는 총 CapEx 차감; Owner Earnings는 유지보수 CapEx만 차감 (성장 CapEx 제외)
- **신호 방향**: Owner Earnings Yield = Owner Earnings / EV > 8% → 현금 창출력 대비 저평가
- **PIT 주의사항**: 영업현금흐름은 DART 현금흐름표 필요 (분기 발표 후). CapEx 중 유지보수 vs 성장 구분은 경영진 공시 참조.
- **Stage 태그**: Stage-A (품질 필터), Stage-B (Owner Earnings Yield 기준 진입)
- **한국 시장 적용성**: 영업현금흐름·CapEx 모두 DART XBRL 현금흐름표 필요 — 현재 DB 미보유. 단, 자본적지출(CapEx) 추정을 유형자산 증감으로 근사하면 부분 계산 가능.
- **DB 가용성**: 외부 — DART 현금흐름표 수집 후 계산 가능. 현재 DB로는 순이익 부분만 가능.
- **즉시 코드화 여부**: 부분 (DART 현금흐름표 백필 후 즉시 구현 가능)
- **출처**: Buffett, W. Berkshire Hathaway Annual Letter (1986); StableBread — Owner Earnings
- **출처 URL**: https://stablebread.com/warren-buffett-owners-earnings/

---

### V-09: ROE 지속성 + 자기자본 성장 (Buffett Quality Filter)
- **정의**: Buffett 핵심 기준 — 레버리지 없이 지속적 고ROE 달성 기업 식별
  - 조건 1: ROE >= 15% (최근 3년 평균)
  - 조건 2: ROE 3년 표준편차 <= 5%p (안정성)
  - 조건 3: 자기자본 YoY 증가율 >= 10% (내부 유보를 통한 복리 성장)
  - 조건 4: 부채비율 <= 50% (레버리지 없는 ROE 확인)
- **신호 방향**: 4개 조건 모두 충족 → Buffett형 퀄리티 컴파운더 후보
- **배경**: 1987 Berkshire Letter — "고ROE를 레버리지 없이 달성하는 기업이 가장 희귀하고 가치 있다"
- **PIT 주의사항**: ROE·부채비율은 최신 연간보고서 발표 기준. 3년 시계열 일관성 확인.
- **Stage 태그**: Stage-A (퀄리티 필터)
- **한국 시장 적용성**: ROE·부채비율 모두 financial_statements 즉시 가용. 한국 코스피 상장사 중 3년 ROE >= 15% + 저부채 기업은 약 100~150종목 수준으로 추산.
- **DB 가용성**: 즉시 — financial_statements.roe, financial_data.roe, financial_statements.debt_ratio 직접 가용
- **즉시 코드화 여부**: 즉시 코드화 가능 (Top 3 추천)
- **출처**: Buffett, W. Berkshire Hathaway Letters (1977~2024); Saber Capital — 1987 ROE Analysis
- **출처 URL**: https://sabercapitalmgt.com/1987-berkshire-letter-and-buffetts-thoughts-on-high-roe/

---

### V-10: Retention Rate x ROE = 내재성장률 (Buffett Compounding Signal)
- **정의**: Sustainable Growth Rate = ROE x Retention Rate
  - Retention Rate = 1 - 배당성향 (배당금 / 순이익)
  - 예: ROE 20%, 배당성향 30% → 내재성장률 14%
- **신호 방향**: 내재성장률 >= 12% 이면서 PER이 내재성장률 이하(PEG_내재 < 1.0) → 복리 성장 저평가
- **응용**: 내재성장률 > 실제 EPS 성장률이면 이익 유보가 비효율적 (ROE 하락 가능성)
- **PIT 주의사항**: 배당성향은 최근 발표 결산 배당 기준. ROE는 최신 연간보고서.
- **Stage 태그**: Stage-A (성장 품질 필터), Stage-B (PEG_내재 기반 진입 타이밍)
- **한국 시장 적용성**: ROE(즉시)·배당수익률(즉시)·PER(즉시) 모두 가용. 배당성향 = 배당금 / EPS 계산 필요 (financial_statements.dividend_yield + financial_data.eps 조합).
- **DB 가용성**: 즉시 — financial_statements.roe + financial_statements.dividend_yield + financial_data.eps로 계산 가능
- **즉시 코드화 여부**: 즉시 코드화 가능 (Top 2 추천)
- **출처**: Buffett, W. Berkshire Letters; Jimmy's Journal — 5 Lessons from 50 Years of Berkshire Letters
- **출처 URL**: https://jimmysjournal.substack.com/p/5-lessons-i-learned-after-reading

---

### V-11: Moat Proxy — 고ROIC 지속성 스크리닝
- **정의**: 경제적 해자(Moat) 대리 지표 — 지속적 고ROIC로 정량화
  - 조건 1: ROIC(간이) >= 15% (최근 연간)
  - 조건 2: ROIC 3년 연속 유지 (하락폭 <= 3%p)
  - 간이 ROIC = 영업이익 / (총자산 - 유동부채) x (1 - 실효세율 25%)
- **신호 방향**: 지속적 고ROIC 기업은 시간이 지날수록 복리 가치 창출 → 장기 보유 후보
- **배경**: Buffett — "truly great business must have an enduring moat"
- **PIT 주의사항**: 각 연도 ROIC는 해당 연도 발표 연간보고서 기준.
- **Stage 태그**: Stage-A (장기 보유 품질 필터)
- **한국 시장 적용성**: operating_profit·total_assets·current_liabilities 즉시 가용. 실효세율 25% 고정 가정 시 즉시 계산 가능.
- **DB 가용성**: 즉시 (간이 ROIC 기준) — financial_statements에서 계산 가능
- **즉시 코드화 여부**: 즉시 코드화 가능
- **출처**: Buffett, W. Berkshire Letters (2007 — moat 언급); Morningstar Wide Moat methodology
- **출처 URL**: https://spotlight.morningstarhub.com.au/boosting-the-magic-of-compounding-berkshire-has-a-way/

---

## 카테고리 4: Klarman 안전마진 / 청산가치 (Margin of Safety, 1991)

### V-12: Liquidation Value (청산가치) 할인 스크리닝
- **정의**: Klarman의 청산가치 = 보수적 유형자산 평가액 (무형자산·영업권 제외)
  - 보수적 청산가치 = 현금 x 1.0 + 매출채권 x 0.7~0.9 + 재고자산 x 0.5~0.7 + 고정자산 x 0.3~0.5 - 총부채
  - 단순 근사: NCAV (Graham Net-Net)와 유사하나 자산 할인율 적용
- **신호 방향**: 시가총액 < 청산가치 x 0.8 → 극단적 저평가 → 매수 후보
- **PIT 주의사항**: 자산 항목은 최신 분기 발표 기준. 재고·고정자산 할인율은 업종별 조정.
- **Stage 태그**: Stage-A (극단적 안전마진 필터)
- **한국 시장 적용성**: 유동자산·총부채 가용. 재고자산·고정자산 세부 항목은 DART 필요. 단순 NCAV로 대체 적용 가능.
- **DB 가용성**: 부분 — current_assets·total_liabilities 즉시. 세부 자산 구성은 외부 필요.
- **즉시 코드화 여부**: 부분 (NCAV 근사 활용)
- **출처**: Klarman, S. Margin of Safety (1991) HarperCollins; Novel Investor — Margin of Safety Notes
- **출처 URL**: https://novelinvestor.com/notes/margin-of-safety-by-seth-klarman/

---

### V-13: Distressed Securities 스크리닝 (Klarman)
- **정의**: 재무적 곤경 기업 중 과도한 할인 매물 식별
  - 조건 1: Altman Z-score < 1.81 (위험지대) 또는 이자보상배율 < 1.5
  - 조건 2: 주가 52주 신저가 대비 20% 이하 (심리적 과매도)
  - 조건 3: PBR < 0.5 (청산가치 대비 극단적 할인)
  - 조건 4: 영업이익 흑자 유지 (영업현금흐름 플러스 — 파산 위험 낮음)
- **신호 방향**: 조건 3~4개 충족 + 영업이익 흑자 유지 → 회생 가능 distressed 매수 후보
- **위험**: 파산으로 이어질 경우 원금 손실. 분산 포트폴리오(10~15종목 이상) 필수.
- **PIT 주의사항**: Altman Z-score 계산 시 최신 분기 재무제표 사용.
- **Stage 태그**: Stage-A (역발상 필터)
- **한국 시장 적용성**: PBR·52주 신저가·Altman Z-score(부분) 즉시 가용. 영업이익은 financial_statements.operating_profit 즉시. 한국 관리종목·상장적격성 실질심사 대상 종목 제외 권장.
- **DB 가용성**: 부분 — PBR·daily_prices·operating_profit 즉시. Altman Z-score 부분 계산 가능.
- **즉시 코드화 여부**: 부분 (PBR + 52주 신저가 + 영업이익 흑자 + 부분 Altman 조합)
- **출처**: Klarman, S. Margin of Safety (1991); Blog.valuesense.io — Margin of Safety Review
- **출처 URL**: https://blog.valuesense.io/margin-of-safety/

---

### V-14: Catalyst-Driven Value (촉매 기반 가치투자, Klarman)
- **정의**: 저평가 자산에 가치 실현 촉매(Catalyst)가 예정된 경우 우선 선발
  - 촉매 유형: 자사주 매입 공시, 경영진 교체, 사업부 분리·매각, 배당 시작, 소송 해결
  - 기준: PBR < 0.7 + 공시 촉매 이벤트 발생 후 20일 이내
- **신호 방향**: 저평가 + 촉매 조합 → 단순 저PBR보다 수익 실현 확률 높음 (Klarman 핵심 개념)
- **PIT 주의사항**: 공시 촉매 이벤트는 corp_events 테이블 공시일 기준. 공시 전 정보 사용 금지.
- **Stage 태그**: Stage-A (필터), Stage-B (촉매 발생 시 진입)
- **한국 시장 적용성**: corp_events 테이블(자사주 취득·분할·합병)과 PBR 결합으로 즉시 적용 가능.
- **DB 가용성**: 부분 — PBR 즉시 + corp_events 테이블 (자사주·분할 이벤트 수집 여부 확인 필요)
- **즉시 코드화 여부**: 부분 코드화 가능
- **출처**: Klarman, S. Margin of Safety (1991) Ch.7; Bourseiness — Margin of Safety Summary
- **출처 URL**: https://www.bourseiness.com/en/263/margin-of-safety-summary-seth-klarman

---

## 카테고리 5: Special Situations — Spinoff / Workout (Greenblatt, You Can Be a Stock Market Genius, 1997)

### V-15: 스핀오프 이후 초기 낙폭 매수 신호
- **정의**: 모회사로부터 분리 상장된 스핀오프 기업의 상장 직후 매수 기회 포착
  - 조건 1: 스핀오프 후 첫 30거래일 이내 (기관 강제 매도 구간)
  - 조건 2: 주가 < 스핀오프 최초 참조가 x 0.85 (15% 이상 하락)
  - 조건 3: 내부자(경영진)의 스핀오프 주식 취득·보유 증거 존재 (공시 확인)
- **신호 방향**: 기관의 비자발적 매도 완료 후 내재가치 대비 할인 → 반등 후보
- **역사적 근거**: Penn State 1988 연구 — 스핀오프 후 3년간 모회사 +6%, 스핀오프 자체 +10% 초과수익
- **PIT 주의사항**: 스핀오프 공시일 기준. 공시 전 정보 사용 금지.
- **Stage 태그**: Stage-B (진입 시그널 — 상장 후 30일 이내)
- **한국 시장 적용성**: 기업분할(인적분할·물적분할) 공시 이후 분리 상장 종목. DART 기업분할결정 공시 → corp_events 연계 가능. 한국 물적분할 논란(모회사 가치 훼손)은 차별화 분석 필요.
- **DB 가용성**: 외부 — DART 분할 공시 + 분리 상장 후 daily_prices 추적
- **즉시 코드화 여부**: 외부 데이터 수집 후 가능
- **출처**: Greenblatt, J. You Can Be a Stock Market Genius (1997) Simon & Schuster
- **출처 URL**: https://www.buysidedigest.com/insights/special-situations-in-stocks-insights-from-joel-greenblatts-you-can-be-a-stock-market-genius/

---

### V-16: 모회사 Stub Value (부분 보유 지분 할인) 스크리닝
- **정의**: 상장 자회사 지분을 보유한 모회사의 Stub Value 계산
  - Stub Value = 모회사 시가총액 - (자회사 시가총액 x 보유 지분율) - 순부채
  - Stub Value < 0 → 모회사 핵심사업을 공짜로 매수하는 셈
- **신호 방향**: Stub Value/주가 할인율 > 30% → 복합기업 할인 해소 시 상승 여력
- **PIT 주의사항**: 자회사 시가총액은 당일 종가 기준. 보유 지분율은 사업보고서 공시 기준.
- **Stage 태그**: Stage-A (구조적 저평가 필터)
- **한국 시장 적용성**: 한국 지주회사 할인(Conglomerate Discount) 구조에 직접 적용 가능. 삼성·LG 등 대형 지주구조에서 Stub Value 음수 사례 빈번. daily_prices로 자회사 시가총액 즉시 계산 가능.
- **DB 가용성**: 부분 — daily_prices(시가총액 계산) 즉시. 지분율은 사업보고서 공시 참조(외부).
- **즉시 코드화 여부**: 부분 (지분율 데이터 수동 입력 후 자동화 가능)
- **출처**: Greenblatt, J. You Can Be a Stock Market Genius (1997); Acquirer's Multiple — Spinoffs and Special Situations
- **출처 URL**: https://acquirersmultiple.com/2025/07/joel-greenblatt-how-spinoffs-and-special-situations-beat-the-market/

---

### V-17: Rights Offering 내부자 초과청약 신호
- **정의**: 유상증자 권리 공모에서 경영진·내부자의 초과 청약(Oversubscription) 공시 탐지
  - 신호: 초과청약 특권 포함 + 경영진 참여 비율 > 50%
- **신호 방향**: 경영진이 자사 주식을 시장가 이하에 추가 매수 의향 → 내재가치 확신 신호
- **PIT 주의사항**: 유상증자 공시일 기준 (권리락일 전 진입).
- **Stage 태그**: Stage-B (진입 시그널 — 내부자 참여 확인 후)
- **한국 시장 적용성**: DART 유상증자결정 공시 + 대주주 청약 참여 내용 확인. corp_events와 연계 가능성 있음.
- **DB 가용성**: 외부 — DART 공시 텍스트 분석 필요
- **즉시 코드화 여부**: 외부 데이터 수집 후 가능
- **출처**: Greenblatt, J. You Can Be a Stock Market Genius (1997)
- **출처 URL**: https://www.shortform.com/blog/you-can-be-a-stock-market-genius-joel-greenblatt/

---

## 카테고리 6: Dhandho — 저위험 고불확실 투자 (Pabrai, 2007)

### V-18: 저위험-고불확실 필터 (Dhandho Framework)
- **정의**: 시장이 불확실성을 위험으로 오판하여 과도하게 할인한 종목 식별
  - 조건 1: PBR < 0.6 또는 주가 52주 신저가 대비 <= 30% (시장 공포 구간)
  - 조건 2: 부채비율 < 100% + 유동비율 > 1.5 (파산 위험 낮음 = 저위험)
  - 조건 3: 과거 3년 영업이익 흑자 유지 (영업 지속성)
  - 조건 4: 불확실성 원인 = 일시적 (소송, 단기 업황 부진, 환율 등) — 구조적 문제 아닌 것
- **신호 방향**: 조건 1~3 충족 + 불확실성이 일시적 판단 → 비대칭 수익(Heads win, Tails don't lose much)
- **PIT 주의사항**: 재무 조건은 최신 분기 발표 기준.
- **Stage 태그**: Stage-A (역발상 필터), Stage-B (불확실성 해소 시 진입)
- **한국 시장 적용성**: PBR·부채비율·유동비율·52주 신저가 모두 즉시 가용. 불확실성 원인 구분은 뉴스·공시 분석 필요.
- **DB 가용성**: 즉시 (재무 조건) + 외부 (불확실성 원인 판별)
- **즉시 코드화 여부**: 부분 코드화 가능 (재무 조건 3개는 즉시)
- **출처**: Pabrai, M. The Dhandho Investor (2007) Wiley; WorldlyInvest — 9 Principles
- **출처 URL**: https://www.worldlyinvest.com/p/9-principles-of-the-dhandho-investor

---

### V-19: Distressed Industry + 우량 기업 콤보 (Dhandho)
- **정의**: 업종 전체가 침체된 상황에서 해당 업종 내 재무 우량 기업 발굴
  - 조건 1: 업종 전체 주가 1년 하락률 > 30% (업종 침체 확인)
  - 조건 2: 해당 기업 부채비율 < 업종 평균 x 0.5 (업종 내 상대적 우량)
  - 조건 3: 해당 기업 유동비율 > 업종 평균 x 1.3 (생존 가능성)
  - 조건 4: 시가총액 < 자기자본 x 1.0 (PBR < 1.0)
- **신호 방향**: 업종 회복 시 재무 취약 경쟁사 퇴출 → 우량 기업으로의 시장 집중 수혜 기대
- **PIT 주의사항**: 업종 분류 기준 일관성 필요 (KRX 업종 분류 기준).
- **Stage 태그**: Stage-A (업종 침체 역발상 필터)
- **한국 시장 적용성**: 업종별 daily_prices 평균 수익률 + financial_statements 업종 평균 비교로 구현 가능. candidate_stocks 업종 분류와 연계.
- **DB 가용성**: 부분 — daily_prices(업종 수익률) + financial_statements(재무비율) 결합
- **즉시 코드화 여부**: 부분 코드화 가능
- **출처**: Pabrai, M. The Dhandho Investor (2007); Anomaly Investments — Dhandho Framework
- **출처 URL**: https://anomalyinvestments.substack.com/p/mohnish-pabrai-the-dhandho-investor

---

## 카테고리 7: Philip Fisher GARP / 성장 품질 (Common Stocks and Uncommon Profits, 1958)

### V-20: Fisher 연구개발 집중도 스크리닝 (R&D Intensity)
- **정의**: Fisher 15 Points 중 Point 4 — R&D 투자 대비 성과 효율 정량화
  - R&D 강도 = R&D 비용 / 매출 x 100 (%)
  - 신호: R&D 강도 > 3% AND 최근 3년 R&D 증가율 > 매출 증가율
- **신호 방향**: 매출 성장을 상회하는 R&D 투자 → 미래 제품 파이프라인 강화 → 성장 프리미엄 정당화
- **PIT 주의사항**: R&D 비용은 연간보고서 발표 기준. 분기 집계 시 TTM 사용.
- **Stage 태그**: Stage-A (성장 품질 필터)
- **한국 시장 적용성**: R&D 비용 항목은 DART XBRL 비용명세서에서 수집 가능. 현재 DB 미보유. IT·반도체·바이오 업종 중심으로 의미 있는 필터.
- **DB 가용성**: 외부 — DART XBRL R&D 비용 수집 필요
- **즉시 코드화 여부**: 외부 데이터 수집 후 가능
- **출처**: Fisher, P. Common Stocks and Uncommon Profits (1958) Ch.3; Novel Investor — Philip Fisher's 15 Points
- **출처 URL**: https://novelinvestor.com/philip-fishers-15-points/

---

### V-21: 영업이익률 업종 상위 25% + 3년 개선 추세 (Fisher Quality Signal)
- **정의**: Fisher Point 5 — 업종 내 상위 수익성 + 장기 개선 추세 요구
  - 조건 1: 영업이익률 업종 상위 25% 분위
  - 조건 2: 영업이익률 3년 연속 개선 (YoY >= 0.5%p 이상 증가)
  - 조건 3: 매출총이익률(추정) 동일 방향 개선
- **신호 방향**: 수익성 우위 + 구조적 개선 → 경쟁우위(Fisher Moat) 존재 증거
- **PIT 주의사항**: 영업이익률은 TTM 기준. 분기별 계절성 제거를 위해 YoY 비교.
- **Stage 태그**: Stage-A (수익성 품질 필터)
- **한국 시장 적용성**: 영업이익률은 financial_statements.operating_margin으로 즉시 가용. 업종 분위 계산에 candidate_stocks 업종 분류 활용.
- **DB 가용성**: 즉시 — financial_statements.operating_margin + yearly_fundamentals.op_margin 시계열
- **즉시 코드화 여부**: 즉시 코드화 가능
- **출처**: Fisher, P. Common Stocks and Uncommon Profits (1958); Old School Value — Common Stock Checklist
- **출처 URL**: https://www.oldschoolvalue.com/investing-strategy/common-stock-checklist/

---

### V-22: Fisher 매출 성장 가속화 (Revenue Acceleration Signal)
- **정의**: Fisher Point 1 — 시장 성장 잠재력 정량 확인
  - 조건 1: 매출 YoY 성장률 > 15%
  - 조건 2: 성장 가속화 — 최근 분기 YoY > 과거 4분기 평균 YoY (가속도 양수)
  - 조건 3: 매출 성장이 이익 성장과 동반 (이익 성장률 >= 매출 성장률 x 0.8)
- **신호 방향**: 매출 성장 + 가속 + 이익 동반 → 구조적 성장 확인 (단순 경기 회복이 아닌 사업 확장)
- **PIT 주의사항**: 분기 발표일 이후 해당 분기 데이터 사용.
- **Stage 태그**: Stage-A (성장 필터), Stage-B (가속 전환 시점 진입)
- **한국 시장 적용성**: financial_statements.revenue 분기 시계열로 YoY + QoQ 모두 즉시 계산 가능.
- **DB 가용성**: 즉시 — financial_statements.revenue (분기 시계열), financial_statements.operating_profit
- **즉시 코드화 여부**: 즉시 코드화 가능
- **출처**: Fisher, P. Common Stocks and Uncommon Profits (1958); Elearnmarkets — Common Stocks Summary
- **출처 URL**: https://www.elearnmarkets.com/school/units/common-stocks-and-uncommon-profits

---

## 카테고리 8: Walter Schloss Deep Value (16 Investment Principles, 1994)

### V-23: Schloss 저PBR 신저가 스크리닝
- **정의**: Schloss의 핵심 접근 — 신저가 + 저PBR 조합으로 "충분히 싼" 종목 발굴
  - 조건 1: 주가 52주 신저가 대비 <= 20% (최근 신저가 근방)
  - 조건 2: PBR <= 0.8 (장부가치 이하 거래)
  - 조건 3: 부채비율 <= 50% (재무 안전성)
  - 조건 4: 영업 이력 >= 5년 (최소 생존력 확인)
- **신호 방향**: 충분한 시장 비관 + 낮은 파산 위험 → 평균 회귀 기대
- **Schloss 매도 기준**: 50% 수익 달성 시 매도 (단순 룰 기반 청산)
- **PIT 주의사항**: 52주 신저가는 daily_prices 시계열. PBR은 최신 분기 발표.
- **Stage 태그**: Stage-A (딥밸류 필터), Stage-C (50% 수익 달성 시 청산)
- **한국 시장 적용성**: 52주 신저가·PBR·부채비율 모두 즉시 가용. 한국 코스닥 소형주 중 신저가 + 저PBR 조합 빈번.
- **DB 가용성**: 즉시 — daily_prices(52주 고저가) + financial_statements.pbr + financial_statements.debt_ratio
- **즉시 코드화 여부**: 즉시 코드화 가능 (Top 1 추천)
- **출처**: Schloss, W. 16 Investment Principles (1994); AAII — Finding Value Among the Lows
- **출처 URL**: https://www.aaii.com/journal/article/finding-value-amoung-the-lows-the-walter-j-schloss-approach

---

### V-24: Schloss 스케일 분할 매수 신호
- **정의**: Schloss 방식의 분할 매수 — 하락 시 추가 매수 체계화
  - 기준: 초기 매수 후 -10%, -20% 하락 시 각각 동일 금액 추가 매수
  - 조건: 재무 건전성 유지 확인 (부채비율 불변 또는 개선)
  - 포트폴리오: 100개 이상 소규모 포지션 분산
- **신호 방향**: 하락에 추가 매수 → 평균 단가 낮춤 + 평균 회귀 수익 극대화
- **위험 관리**: 단일 종목 최대 포트폴리오의 3% 이하 유지 (Schloss 원칙)
- **PIT 주의사항**: 재무 건전성 재확인은 직전 분기 발표 기준.
- **Stage 태그**: Stage-B (추가 진입 타이밍), Stage-C (50% 수익 청산)
- **한국 시장 적용성**: 포지션 분산 관리는 virtual_trading_records와 연계 가능. 하락 % 트리거는 daily_prices로 구현.
- **DB 가용성**: 즉시 (daily_prices 기반 하락률 계산)
- **즉시 코드화 여부**: 즉시 코드화 가능
- **출처**: Schloss, W. 16 Investment Principles (1994); Mr. Deep Value — How to Invest Like Schloss (2026)
- **출처 URL**: https://www.mrdeepvalue.com/p/how-to-invest-like-walter-schloss

---

### V-25: Graham-Schloss NCAV 확장 (자산 커버리지 분위)
- **정의**: Schloss의 NCAV 활용 확장 — 시가총액 대비 자산 커버리지 단계별 분위
  - Level 1 (최강): 시총 < NCAV x 0.67 (Graham 순수 Net-Net)
  - Level 2 (강): NCAV x 0.67 < 시총 < NCAV (부분 NCAV 할인)
  - Level 3 (보통): NCAV < 시총 < 자기자본 x 0.8 (PBR < 0.8 영역)
- **신호 방향**: Level별 우선순위로 포트폴리오 구성 (Level 1 최우선)
- **PIT 주의사항**: 유동자산·총부채는 최신 분기 발표 기준.
- **Stage 태그**: Stage-A (딥밸류 분위 필터)
- **한국 시장 적용성**: current_assets·total_liabilities·market_cap 조합으로 Level 분류 즉시 가능. 한국 시장 특성상 Level 2·3 종목 다수.
- **DB 가용성**: 부분 — 발행주식수 직접 DB 컬럼 확인 후 즉시 계산 가능
- **즉시 코드화 여부**: 부분 코드화 가능
- **출처**: Graham, B. Security Analysis (1934); Net Net Hunter — NCAV Formula
- **출처 URL**: https://www.netnethunter.com/grahams-net-current-assets-formula/

---

## 카테고리 9: Peter Lynch GARP (One Up on Wall Street, 1989 — 보조 출처)

### V-26: Lynch PEG Ratio 강화 버전 (GARP 신호)
- **정의**: PEG = PER / EPS 성장률 (%)
  - Lynch 기준: PEG < 1.0 → 성장 대비 저평가; PEG < 0.5 → 강력 매수 신호
  - 강화 버전: (PER) / (EPS 성장률 + 배당수익률) < 1.0
- **신호 방향**: PEG < 1.0 이면서 EPS 성장 가속화(QoQ 개선) → 최우선 GARP 후보
- **Lynch 경고**: EPS 성장률이 25% 초과 시 지속 가능성 의문 → 25% 상한 적용 권장
- **PIT 주의사항**: 과거 EPS 성장률(TTM YoY)만 사용. 추정치 미사용.
- **Stage 태그**: Stage-A (GARP 필터), Stage-B (PEG < 0.5 진입 신호)
- **한국 시장 적용성**: financial_data.eps 시계열로 YoY 성장률 계산 + financial_statements.per 결합. financial_statements.dividend_yield 추가 가능.
- **DB 가용성**: 부분 — PER 즉시. EPS 분기 시계열 확인 필요(financial_data.eps).
- **즉시 코드화 여부**: 부분 코드화 가능
- **출처**: Lynch, P. One Up on Wall Street (1989) Simon & Schuster; StableBread — Lynch Stock Valuation
- **출처 URL**: https://stablebread.com/peter-lynch-stock-valuation/

---

### V-27: Lynch 6가지 종목 유형 분류 스크리닝
- **정의**: Lynch의 6가지 분류 체계를 정량 기준으로 자동화
  - Slow Grower: 매출 YoY < 5% + 배당수익률 > 3% → 배당주 평가 기준 적용
  - Stalwart: 매출 YoY 5~12% + PER < 20 → 안전한 성장주
  - Fast Grower: 매출 YoY > 20% + PEG < 1.2 → 텐배거 후보
  - Cyclical: 업종 코드(소재·에너지·화학 등) + PER 낮은 경기 고점 회피
  - Turnaround: Altman Z-score < 1.81 + 최근 2분기 연속 흑자 전환
  - Asset Play: PBR < 0.6 + 숨겨진 자산(부동산·특허) 보유 공시
- **신호 방향**: 유형별 맞춤 진입·청산 기준 적용 (단일 PER 기준의 한계 극복)
- **Stage 태그**: Stage-A (분류 필터)
- **한국 시장 적용성**: 매출 성장·PER·PBR·배당수익률 모두 즉시 가용. 업종 분류는 candidate_stocks와 연계. Turnaround는 Altman Z-score(부분) 필요.
- **DB 가용성**: 부분 — 대부분 즉시. Turnaround 완전 구현에 Altman 부분 계산 추가.
- **즉시 코드화 여부**: 부분 코드화 가능
- **출처**: Lynch, P. One Up on Wall Street (1989); ChartMill — Peter Lynch GARP Criteria
- **출처 URL**: https://www.chartmill.com/documentation/stock-screener/fundamental-analysis-investing-strategies/440-peter-lynch-investment-criteria-in-the-stock-screener

---

## DB 즉시 가용 Top 5 (Value Classics 전용)

| 순위 | 시그널 ID | 시그널명 | DB 컬럼 | 즉시 가능 이유 |
|------|-----------|---------|---------|--------------|
| 1 | V-02 | Graham Number | financial_statements.per + financial_data.eps + pbr | 직접 계산 공식 단순 |
| 2 | V-10 | 내재성장률 (ROE x 유보율) | financial_statements.roe + dividend_yield + financial_data.eps | 즉시 컬럼 조합 |
| 3 | V-09 | ROE 지속성 + 자기자본 성장 | financial_statements.roe + debt_ratio (3년 시계열) | 즉시 컬럼 존재 |
| 4 | V-23 | Schloss 저PBR 신저가 | daily_prices(52주) + financial_statements.pbr + debt_ratio | 모든 컬럼 즉시 |
| 5 | V-21 | 영업이익률 업종 상위 + 개선 | financial_statements.operating_margin 시계열 | 즉시 컬럼 존재 |

---

## 한국 시장 적용성 종합 평가

### Graham Defensive Criteria (V-01) → KRX 적용 판정

| 기준 | KRX 적용 가능성 | 통과 예상 비율 | 비고 |
|------|---------------|-------------|------|
| 기준 1 (규모 >= 매출 1,000억) | 가능 (완화 필요) | 코스피 약 60% | 원서 달러 기준 물가조정 |
| 기준 2 (유동비율 >= 2.0) | 가능 | 약 30~40% | 한국 평균 ~150%로 엄격 |
| 기준 3 (10년 무적자) | 가능 (DB 제한) | 코스피200 ~50% | 10년 EPS 시계열 외부 필요 |
| 기준 4 (20년 연속 배당) | 완화 필요 | 약 5~10% | 10년으로 완화 권장 |
| 기준 5 (10년 EPS CAGR >= 3.3%) | 가능 (DB 제한) | 코스피200 ~40% | 외부 EPS 시계열 필요 |
| 기준 6 (PER <= 15) | 즉시 가능 | 약 55~65% | 코스피 평균 PER ~12 |
| 기준 7 (PBR <= 1.5) | 즉시 가능 | 약 70~80% | 코스피 평균 PBR ~0.8 |
| **종합 (기준 6+7+2 적용)** | **즉시 가능** | **약 20~30%** | 3개 기준만으로도 유효한 필터 |

### Magic Formula (V-05~07) → 한국 financial_statements PIT-safe 적용 가능?

- **EBIT/EV (V-05)**: operating_profit(EBIT proxy) 즉시 가용. EV 계산에 순차입금 필요 → DART 보강 또는 총부채 근사 사용. **부분 적용 가능**.
- **ROIC_G (V-06)**: current_assets·current_liabilities·total_assets 즉시. PP&E 세부값 DART 필요. 간이 근사 버전으로 구현 가능. **부분 적용 가능**.
- **Composite Rank (V-07)**: 두 순위 합산 자동화는 financial_statements 즉시 데이터로 근사 버전 즉시 구현. 정밀도는 DART 수집 후 향상. **즉시(근사)/부분(정밀)**.
- **PIT-safe 원칙**: financial_statements 분기 발표일(report_date) 이후 데이터만 사용하면 Look-Ahead 없음. 시가총액은 계산일 당일 daily_prices 사용.

### Buffett Owner Earnings (V-08) → 한국 DART 데이터 가용성

- **현황**: DART XBRL 현금흐름표 미백필 상태 (기존 메모리 기록 확인). 영업현금흐름·CapEx 모두 DB 미보유.
- **단기 대안**: 순이익만으로는 불완전. 자산 증감으로 간이 CapEx 추정 가능(total_assets 증분 활용)하나 정밀도 낮음.
- **중기 해결책**: DART XBRL 현금흐름표 백필 후 Owner Earnings 정밀 계산 가능. 백필 후 V-08 즉시 코드화 가능.
- **결론**: DART 현금흐름표 백필이 Owner Earnings 구현의 필수 전제조건.

---

## Stage 분포 요약

| Stage | 해당 시그널 | 건수 |
|-------|------------|------|
| Stage-A (필터) | V-01·02·03·04·05·06·07·09·11·12·13·14·16·18·19·20·21·22·23·25·26·27 | 22건 |
| Stage-B (진입) | V-02·08·10·14·15·16·17·18·22·24·26 | 11건 |
| Stage-C (청산) | V-23·24 | 2건 |

> 중복 태그(Stage-A+B 동시) 다수 포함. 실제 단일 시그널에 여러 Stage 적용.

---

## 즉시 코드화 가능 Top 3

| 순위 | 시그널 | 핵심 로직 | DB 컬럼 |
|------|--------|----------|---------|
| 1 | V-02 Graham Number | sqrt(22.5 x EPS x BVPS) vs 현재가 | financial_data.eps, financial_statements.pbr |
| 2 | V-10 내재성장률 | ROE x (1 - 배당성향) + PEG_내재 < 1.0 | financial_statements.roe, dividend_yield, financial_data.eps, per |
| 3 | V-23 Schloss 신저가 | 52주 신저가 <= 20% + PBR <= 0.8 + 부채비율 <= 50% | daily_prices, financial_statements.pbr, debt_ratio |

---

## 외부 데이터 필요 컨셉 요약

| 데이터 소스 | 필요 시그널 |
|------------|-----------|
| DART XBRL 현금흐름표 (미백필) | V-08(Owner Earnings), V-13(Distressed 영업CF) |
| DART XBRL 손익계산서 세부 | V-12(청산가치 재고·고정자산), V-20(R&D 비용) |
| DART 공시 API | V-15(스핀오프·분할), V-17(유상증자 내부자), V-14(촉매 이벤트) |
| 장기 EPS 시계열 (10년) | V-01(Graham 10년 기준), V-03(NCAV 부분) |
| 지분율 데이터 (사업보고서) | V-16(Stub Value 자회사 지분율) |

---

## 출처 요약

| 원전 | ISBN / 출판 정보 | 인용 시그널 |
|------|----------------|-----------|
| Graham, B. The Intelligent Investor (1973) | ISBN 978-0-06-055566-5 | V-01, V-02, V-03, V-04 |
| Graham, B. & Dodd, D. Security Analysis (1934) | Columbia Business School Press | V-03, V-25 |
| Greenblatt, J. The Little Book That Beats the Market (2005) | ISBN 978-0-471-73306-5 | V-05, V-06, V-07 |
| Greenblatt, J. You Can Be a Stock Market Genius (1997) | ISBN 978-0-684-84007-9 | V-15, V-16, V-17 |
| Buffett, W. Berkshire Hathaway Annual Letters (1977~2024) | berkshirehathaway.com | V-08, V-09, V-10, V-11 |
| Klarman, S. Margin of Safety (1991) | ISBN 978-0-887-30510-8 | V-12, V-13, V-14 |
| Pabrai, M. The Dhandho Investor (2007) | ISBN 978-0-470-04389-9 | V-18, V-19 |
| Fisher, P. Common Stocks and Uncommon Profits (1958/1996) | ISBN 978-0-471-44550-0 | V-20, V-21, V-22 |
| Schloss, W. 16 Investment Principles (1994 speech) | AAII / WorldlyInvest | V-23, V-24, V-25 |
| Lynch, P. One Up on Wall Street (1989) | ISBN 978-0-671-66103-8 | V-26, V-27 |
