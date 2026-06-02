# 기본 분석 시그널 카탈로그

> 작성일: 2026-05-25 | 조사자: document-specialist (Claude Sonnet 4.6)
> 목적: Phase 5 시그널 패밀리 37 → 100+ 확장 — 기본 분석 범주
> No Look-Ahead 원칙: 모든 재무 데이터는 분기 발표일(공시일) 이후만 사용 (Point-in-Time 강제)

---

## 범례 (DB 가용성 컬럼)

| 기호 | 의미 |
|------|------|
| 즉시 | 우리 DB 컬럼으로 즉시 계산 가능 |
| 부분 | DB에 일부 데이터 있음, 추가 계산 필요 |
| 외부 | 외부 데이터 소스 필요 (DART API, KRX, 컨센서스 등) |

---

## 카테고리 1: 밸류에이션 단일 지표

### F-01: PER (Price/Earnings Ratio)
- **정의**: 시가총액 / 순이익 (또는 주가 / EPS)
- **신호 방향**: 낮을수록 저평가 (동일 섹터 대비 하위 30% 분위)
- **임계값 가이드**: PER < 10 → 저평가, PER > 30 → 고평가 (업종 조정 필수)
- **PIT 주의사항**: 분기 발표일 이후 EPS 사용. 추정치(Forward PER)와 혼동 금지.
- **DB 가용성**: 즉시 — financial_statements.per, financial_data.per, yearly_fundamentals.per
- **출처**: Fama & French (1992), Graham & Dodd Security Analysis (1934)

---

### F-02: Forward PER (선행 PER)
- **정의**: 현재 주가 / 향후 12개월 예상 EPS (컨센서스 기반)
- **신호 방향**: 현재 PER 대비 Forward PER이 낮으면 이익 성장 기대 내포
- **PIT 주의사항**: 컨센서스 추정치의 기준 시점 엄수. 발표일 이후 시점의 컨센서스만 사용.
- **DB 가용성**: 외부 — FnGuide/WiseFn 컨센서스 구독 필요
- **출처**: Damodaran Investment Valuation (3rd ed., 2012)

---

### F-03: Shiller PE (CAPE — Cyclically Adjusted P/E)
- **정의**: 현재 주가 / 인플레이션 조정 10년 평균 EPS
- **신호 방향**: 개별 종목보다 시장 전체 과열/저평가 판단에 유효
- **PIT 주의사항**: 10년치 연간 EPS 필요. 과거 보고 기준 EPS 사용하므로 look-ahead 없음.
- **DB 가용성**: 부분 — yearly_fundamentals 2021~2025 5개년 한정, 10년 CAPE 계산 불가. 외부 연간 EPS 보강 필요.
- **출처**: Shiller Irrational Exuberance (2000); Shiller & Campbell (1988) NBER

---

### F-04: PEG Ratio (Price/Earnings-to-Growth)
- **정의**: PER / EPS 성장률(%) — 성장 대비 밸류에이션 판단
- **신호 방향**: PEG < 1.0 → 성장 대비 저평가; PEG > 2.0 → 고평가
- **파생 버전**: PEG-1y (1년 성장), PEG-3y (3년 CAGR), PEG-5y (5년 CAGR)
- **PIT 주의사항**: 과거 성장률은 발표된 연간 EPS 시계열 사용. 추정 성장률 사용 시 컨센서스 시점 기록 필수.
- **DB 가용성**: 부분 — yearly_fundamentals.per + net_income으로 과거 성장률 기반 PEG-3y 계산 가능 (2021~2025)
- **출처**: Peter Lynch One Up on Wall Street (1989); Damodaran (2012)
- **출처 URL**: https://www.piranhaprofits.com/blog/peg-ratio-explained

---

### F-05: PBR (Price/Book Value Ratio)
- **정의**: 시가총액 / 자기자본 (장부가치)
- **신호 방향**: PBR < 1.0 → 청산가치 이하 거래 (극단적 저평가 또는 구조적 문제)
- **PIT 주의사항**: 최신 분기 자기자본 사용. 분기 발표 전 이전 분기 데이터 유지.
- **DB 가용성**: 즉시 — financial_statements.pbr, financial_data.pbr, yearly_fundamentals.pbr
- **출처**: Fama & French (1992) Journal of Finance

---

### F-06: PSR (Price/Sales Ratio)
- **정의**: 시가총액 / 연간 매출
- **신호 방향**: PSR < 1.0 → 저평가 (이익 적자 성장주 평가 유용)
- **PIT 주의사항**: TTM(Trailing Twelve Months) 매출 사용. 분기 누적합으로 계산.
- **DB 가용성**: 즉시 — financial_statements.psr, financial_data + daily_prices.market_cap 조합으로 직접 계산 가능
- **출처**: O'Shaughnessy What Works on Wall Street (1996)

---

### F-07: EV/EBITDA
- **정의**: 기업가치(EV) / EBITDA (세전이자감가상각전이익)
  - EV = 시가총액 + 순차입금(차입금 - 현금)
  - EBITDA = 영업이익 + 감가상각비
- **신호 방향**: EV/EBITDA < 6 → 저평가; 업종 평균 대비 하위 분위 선호
- **PIT 주의사항**: 차입금/현금은 최신 분기 기준. EBITDA는 TTM 사용.
- **DB 가용성**: 부분 — financial_statements: operating_profit, total_liabilities, total_equity 있음. 감가상각비·현금·차입금 세부 항목은 DART XBRL 필요.
- **출처**: Greenblatt The Little Book That Beats the Market (2005); Damodaran (2012)
- **출처 URL**: https://www.definedgesecurities.com/fundamental-library/ev-ebitda/

---

### F-08: EV/Sales
- **정의**: EV / 연간 매출
- **신호 방향**: PSR과 유사하나 자본구조 중립. EV/Sales < 1 → 저평가.
- **PIT 주의사항**: EV와 동일 시점의 TTM 매출 사용.
- **DB 가용성**: 부분 — 매출은 financial_statements.revenue 가용. EV 계산에 차입금/현금 외부 필요.
- **출처**: Damodaran Investment Valuation (2012)

---

### F-09: 배당수익률 (Dividend Yield)
- **정의**: 주당 배당금 / 현재 주가 x 100 (%)
- **신호 방향**: 배당수익률 > 3% → 인컴 투자 매력; 배당 성장 + 고수익률 조합 선호
- **한국 특수**: 연말 배당(12월 결산법인 기준) 집중 → 11~12월 배당주 수익률 효과 존재
- **PIT 주의사항**: 배당 결정 공시일 이후 사용. 배당락일(ex-dividend date) 전/후 구분 필수.
- **DB 가용성**: 즉시 — financial_statements.dividend_yield
- **출처**: Fama & French (1988) Journal of Finance

---

### F-10: FCF Yield (Free Cash Flow Yield)
- **정의**: 잉여현금흐름(FCF) / EV x 100 (%)
  - FCF = 영업현금흐름 - 자본적지출(CAPEX)
- **신호 방향**: FCF Yield > 7~8% → 고품질 저평가 (Quant Investing 기준)
- **PIT 주의사항**: FCF는 TTM 기준 현금흐름표 데이터. 현금흐름표는 별도 DART XBRL 수집 필요.
- **DB 가용성**: 외부 — 현금흐름표(영업현금흐름, CAPEX) DB 미보유. DART XBRL API 추가 수집 필요.
- **출처**: Quant Investing FCF Yield Glossary; Greenblatt (2005)
- **출처 URL**: https://www.quant-investing.com/glossary/fcf-yield-fcf-to-ev

---

## 카테고리 2: 수익성/품질 지표

### F-11: ROE (Return on Equity)
- **정의**: 순이익 / 자기자본 x 100 (%)
- **신호 방향**: ROE > 15% → 우량 기업; 지속성 중요 (3년 평균 ROE 선호)
- **PIT 주의사항**: TTM 순이익 / 최신 분기 자기자본. 연간 보고 기준 사용.
- **DB 가용성**: 즉시 — financial_statements.roe, financial_data.roe, yearly_fundamentals.roe
- **출처**: Fama & French 5-factor model (2015) — RMW 팩터; Warren Buffett 핵심 지표
- **출처 URL**: https://blog.quantinsti.com/fama-french-five-factor-asset-pricing-model/

---

### F-12: ROA (Return on Assets)
- **정의**: 순이익 / 총자산 x 100 (%)
- **신호 방향**: ROA > 5% → 양호; Piotroski F-score 구성 요소 (ROA 개선 여부 포함)
- **PIT 주의사항**: Piotroski 기준: 전년도 대비 ROA 개선 시 +1점.
- **DB 가용성**: 즉시 — financial_data.roa; financial_statements에서 net_income / total_assets로 계산 가능
- **출처**: Piotroski (2000) Journal of Accounting Research 38:1-41
- **출처 URL**: https://en.wikipedia.org/wiki/Piotroski_F-score

---

### F-13: ROIC (Return on Invested Capital)
- **정의**: NOPAT / 투하자본 x 100 (%)
  - NOPAT = EBIT x (1 - 세율)
  - 투하자본 = 유형고정자산 + 순운전자본
- **신호 방향**: ROIC > WACC(가중평균자본비용) → 가치 창출 기업
- **Greenblatt 활용**: Magic Formula의 핵심 수익성 지표 (EBIT/EV + ROIC 결합 순위)
- **PIT 주의사항**: 세율·투하자본은 최신 연간 보고서 기준.
- **DB 가용성**: 부분 — financial_statements에서 operating_profit·total_assets·current_liabilities 가용. NOPAT 계산에 세율 필요 (법인세 항목 미보유 → DART 필요).
- **출처**: Greenblatt The Little Book That Beats the Market (2005)
- **출처 URL**: https://www.wallstreetprep.com/knowledge/roic-return-on-invested-capital/

---

### F-14: ROCE (Return on Capital Employed)
- **정의**: EBIT / 사용자본 x 100 (%), 사용자본 = 총자산 - 유동부채
- **신호 방향**: ROCE > 15% → 효율적 자본 활용; ROIC와 달리 비유동자산 포함
- **DB 가용성**: 부분 — financial_statements: operating_profit(EBIT proxy), total_assets, current_liabilities 모두 가용. 직접 계산 가능.
- **출처**: Wall Street Prep ROCE
- **출처 URL**: https://www.wallstreetprep.com/knowledge/roce-return-on-capital-employed/

---

### F-15: 영업이익률 (Operating Margin)
- **정의**: 영업이익 / 매출 x 100 (%)
- **신호 방향**: 업종 평균 상위 25% 이상 + 전년 대비 개선
- **PIT 주의사항**: TTM 영업이익 / TTM 매출 사용.
- **DB 가용성**: 즉시 — financial_statements.operating_margin, yearly_fundamentals.op_margin
- **출처**: Piotroski (2000); Fama & French (2015)

---

### F-16: 순이익률 (Net Margin)
- **정의**: 순이익 / 매출 x 100 (%)
- **신호 방향**: 업종 평균 상위 25% + 추세 개선
- **DB 가용성**: 즉시 — financial_statements.net_margin; yearly_fundamentals에서 net_income / revenue로 계산 가능
- **출처**: O'Shaughnessy What Works on Wall Street (1996)

---

### F-17: 매출총이익률 (Gross Margin)
- **정의**: (매출 - 매출원가) / 매출 x 100 (%)
- **신호 방향**: Piotroski F-score 구성 (전년 대비 개선 시 +1점); Beneish M-score의 GMI 변수
- **PIT 주의사항**: 분기별 개선 여부 추적.
- **DB 가용성**: 외부 — 매출원가(COGS) 항목 DB 미보유. DART XBRL 손익계산서 수집 필요.
- **출처**: Piotroski (2000); Beneish (1999) The Detection of Earnings Manipulation

---

### F-18: 자산회전율 (Asset Turnover)
- **정의**: 매출 / 총자산
- **신호 방향**: Piotroski F-score 구성 (전년 대비 개선 시 +1점). 전년 대비 상승 = 효율 개선.
- **DB 가용성**: 즉시 — financial_statements: revenue / total_assets로 계산 가능
- **출처**: Piotroski (2000) Journal of Accounting Research 38:1-41

---

## 카테고리 3: 성장 지표

### F-19: 매출 성장률 (Revenue Growth)
- **파생 버전**:
  - QoQ (전분기 대비): (Q_t - Q_{t-1}) / Q_{t-1}
  - YoY (전년 동기 대비): (Q_t - Q_{t-4}) / Q_{t-4}
  - 3y CAGR: (현재매출/3년전매출)^(1/3) - 1
- **신호 방향**: YoY > 15% + 가속화(QoQ 개선) → 강한 성장 신호
- **PIT 주의사항**: 각 분기 발표 후 사용. 정정 공시 시 최신 값으로 대체.
- **DB 가용성**: 즉시 — financial_statements.revenue (분기 시계열), yearly_fundamentals.revenue_growth (YoY)
- **출처**: O'Shaughnessy (1996); Fama & French (2015) — CMA 투자 팩터 연관

---

### F-20: 영업이익 성장률
- **정의**: 전년 동기 대비 영업이익 증가율 (YoY)
- **신호 방향**: 매출 성장률보다 영업이익 성장률이 높으면 레버리지 효과 (마진 개선)
- **DB 가용성**: 즉시 — financial_statements.operating_profit 시계열로 계산 가능
- **출처**: O'Shaughnessy (1996)

---

### F-21: EPS 성장률
- **정의**: EPS(주당순이익)의 YoY 성장률
- **신호 방향**: EPS 성장 가속화(YoY 성장률 자체가 증가) → 강력 매수 신호
- **PIT 주의사항**: 희석 EPS 기준. 주식수 변동(유무상증자·자사주 소각) 조정 필수.
- **DB 가용성**: 부분 — financial_data.eps 있음. 분기별 시계열 필요.
- **출처**: PEAD 연구 (Ball & Brown 1968); Lynch One Up on Wall Street (1989)

---

### F-22: EPS 추정치 변화 (Estimate Revision)
- **정의**: 최근 30일/60일 내 컨센서스 EPS 추정치 변화율 (%)
- **신호 방향**: 상향 > 5% → 매수 신호; 하향 > 5% → 회피 신호
- **학술 근거**: Brown, Wei, Womack 등 다수 연구 — 추정치 변화가 6~12개월 수익률 예측
- **PIT 주의사항**: 컨센서스 수집 시점 기록 필수. 추정치는 발표 전 사용 가능하나 시점 타임스탬프 엄수.
- **DB 가용성**: 외부 — FnGuide/WiseFn 컨센서스 구독 필요
- **출처**: Mill Street Research — Analyst Estimate Revisions
- **출처 URL**: https://www.millstreetresearch.com/do-analyst-estimate-revisions-still-help-forecast-relative-stock-returns/

---

### F-23: 자기자본 성장률
- **정의**: 전년 대비 자기자본 증가율
- **신호 방향**: 자기자본 성장 + ROE 유지 = 내부 유보를 통한 복리 성장 (Buffett 기준)
- **PIT 주의사항**: 유상증자로 인한 외부 자본 유입 시 희석 조정.
- **DB 가용성**: 즉시 — financial_statements.total_equity 분기 시계열로 계산 가능
- **출처**: Buffett Annual Letters (1977~present)

---

## 카테고리 4: 재무 건전성 지표

### F-24: 부채비율 (Debt/Equity Ratio)
- **정의**: 총부채 / 자기자본 x 100 (%)
- **신호 방향**: Piotroski F-score 구성 (전년 대비 감소 시 +1점). < 100% 선호.
- **한국 특수**: 1997 외환위기 후 한국 기업 부채비율 200% 이하 규제 문화 정착
- **DB 가용성**: 즉시 — financial_statements.debt_ratio, yearly_fundamentals.debt_ratio
- **출처**: Piotroski (2000); Altman (1968)

---

### F-25: 유동비율 (Current Ratio)
- **정의**: 유동자산 / 유동부채
- **신호 방향**: Piotroski F-score 구성 (전년 대비 개선 시 +1점). > 1.5 → 단기 유동성 양호.
- **DB 가용성**: 즉시 — financial_statements: current_assets / current_liabilities로 계산 가능
- **출처**: Piotroski (2000) Journal of Accounting Research 38:1-41

---

### F-26: 당좌비율 (Quick Ratio)
- **정의**: (유동자산 - 재고자산) / 유동부채
- **신호 방향**: > 1.0 → 재고 제외 단기 지급능력 충분
- **DB 가용성**: 외부 — 재고자산 항목 DB 미보유. DART XBRL 재무상태표 수집 필요.
- **출처**: Graham & Dodd Security Analysis (1934)

---

### F-27: 이자보상배율 (Interest Coverage Ratio)
- **정의**: EBIT / 이자비용
- **신호 방향**: > 3 → 안전; < 1.5 → 재무 위험; Altman Z-score 연관
- **DB 가용성**: 외부 — 이자비용 항목 DB 미보유. DART XBRL 손익계산서 필요.
- **출처**: Altman (1968); Graham & Dodd (1934)

---

### F-28: Altman Z-score (부도 예측 모형)
- **정의**: Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
  - X1 = 운전자본 / 총자산
  - X2 = 이익잉여금 / 총자산
  - X3 = EBIT / 총자산
  - X4 = 시가총액 / 총부채 장부가
  - X5 = 매출 / 총자산
- **신호 방향**: Z > 2.99 → 안전지대; 1.81~2.99 → 회색지대; Z < 1.81 → 위험지대
- **매매 활용**: Z-score 하위 10% 종목 제외 필터 (리스크 스크리닝)
- **PIT 주의사항**: 재무제표 발표일 이후 계산. 시가총액은 계산일 기준.
- **DB 가용성**: 부분 — X1(운전자본), X3(EBIT proxy), X4(시총/부채), X5 계산 가능. X2(이익잉여금)는 DART 필요.
- **출처**: Altman (1968) Journal of Finance
- **출처 URL**: https://en.wikipedia.org/wiki/Altman_Z-score

---

### F-29: Piotroski F-score (재무 건전성 9점 체계)
- **정의**: 9개 이진 신호 합산 (0~9점)
- **9개 기준**:
  - 수익성 (4개): ROA > 0 (+1), 영업현금흐름 > 0 (+1), ROA 전년 대비 개선 (+1), 영업현금흐름 > 순이익 (+1)
  - 레버리지/유동성 (3개): 장기부채비율 감소 (+1), 유동비율 개선 (+1), 신주 미발행 (+1)
  - 운영 효율 (2개): 매출총이익률 개선 (+1), 자산회전율 개선 (+1)
- **신호 방향**: 8~9점 → 강한 매수 후보; 0~2점 → 제외 후보
- **한국 적용**: 저PBR + 고F-score 조합이 한국 시장에서도 유효 (한국재무학회 검증)
- **PIT 주의사항**: 매 분기 발표 후 업데이트. 영업현금흐름은 DART 현금흐름표 필요.
- **DB 가용성**: 부분 — 9개 기준 중 부채비율·유동비율·신주발행·자산회전율 4개는 현재 DB로 계산 가능. 영업현금흐름·매출원가 관련 5개는 DART 필요.
- **출처**: Piotroski (2000) Journal of Accounting Research 38:1-41
- **출처 URL**: https://en.wikipedia.org/wiki/Piotroski_F-score

---

### F-30: Beneish M-score (분식회계 탐지)
- **정의**: M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI
- **8개 변수**:
  - DSRI: 매출채권 증가율 / 매출 증가율 (수익 과장 탐지)
  - GMI: 전년 대비 매출총이익률 악화 지수
  - AQI: 자산 품질 지수
  - SGI: 매출 성장 지수
  - DEPI: 감가상각 속도 감소 지수
  - SGAI: 판관비/매출 증가 지수
  - TATA: 총발생주의/총자산 (최대 계수 +4.679, 핵심 변수)
  - LVGI: 레버리지 변화 지수
- **신호 방향**: M-score > -2.22 → 분식 의심 → 매수 회피 필터
- **PIT 주의사항**: 발표 재무제표 기준. TATA 계산에 현금흐름표 필요.
- **DB 가용성**: 부분 — SGI, 일부 GMI, AQI 부분 계산 가능. TATA(현금흐름)·DSRI(매출채권)·DEPI(감가상각)는 DART 필요.
- **출처**: Beneish (1999) Financial Analysts Journal — The Detection of Earnings Manipulation
- **출처 URL**: https://en.wikipedia.org/wiki/Beneish_M-score

---

## 카테고리 5: Composite / Quant Factor

### F-31: Magic Formula (Greenblatt)
- **정의**: EBIT/EV 순위 + ROIC 순위 합산 → 합산 순위 상위 종목 선택
  - EV = 시가총액 + 순차입금
  - ROIC = EBIT / (유형고정자산 + 순운전자본)
- **선택 방법**: 유니버스 전체 순위화 → 두 순위 합산 → 상위 20~30종목 매월 2~3개 편입, 1년 보유 후 교체
- **한국 적용**: KRX 전 종목 대상 반년~1년 리밸런싱. 금융주·유틸리티 제외 권장.
- **PIT 주의사항**: 재무 데이터는 최신 발표 분기 기준. EV는 현재 시가총액 기준.
- **DB 가용성**: 부분 — financial_statements로 부분 계산 가능. 감가상각·PP&E·현금 세부 항목은 DART XBRL 필요.
- **출처**: Greenblatt The Little Book That Beats the Market (2005)
- **출처 URL**: https://www.aaii.com/stocks/screens/46

---

### F-32: Sloan Accruals Ratio (발생주의 이상 현상)
- **정의**: 발생주의 비율 = (순이익 - 영업현금흐름) / 총자산
- **신호 방향**: 발생주의 비율 낮을수록(현금이익 > 회계이익) 다음 해 수익률 높음
  - 상위 10%(고발생주의) 매수 회피, 하위 10%(저발생주의) 우선 선발 → 연 약 12% 초과수익 (Sloan 1996)
- **매매 활용**: 고발생주의 종목 필터링 (매수 회피); 저발생주의 종목 우선 선발
- **PIT 주의사항**: 영업현금흐름 필요 → DART 현금흐름표. 발표 후 사용.
- **DB 가용성**: 외부 — 영업현금흐름 DB 미보유. DART XBRL 필요.
- **출처**: Sloan (1996) Accounting Review 71(3):289-315
- **출처 URL**: https://quantpedia.com/strategies/accrual-anomaly

---

### F-33: Value Composite Score
- **정의**: PER + PBR + PSR + EV/EBITDA 각각 분위(percentile) 순위 평균
  - 각 지표별 낮을수록 좋은 방향으로 분위 변환 후 산술 평균
- **신호 방향**: Value Composite 상위 20% → 다차원 저평가 후보
- **DB 가용성**: 부분 — PER·PBR·PSR은 즉시 가능. EV/EBITDA는 DART 보강 필요.
- **출처**: O'Shaughnessy What Works on Wall Street (1996); AQR factor research

---

### F-34: Quality Composite Score
- **정의**: ROE + ROIC + 영업이익률 안정성(3년 표준편차 역수) 분위 평균
- **신호 방향**: Quality 상위 20% + Value 상위 20% 교집합 → QMJ (Quality Minus Junk) 전략
- **DB 가용성**: 부분 — ROE·영업이익률은 즉시. ROIC는 DART 세율 항목 보강 필요.
- **출처**: Asness, Frazzini & Pedersen AQR (2019) Quality Minus Junk; Fama & French (2015)
- **출처 URL**: https://www.robeco.com/en-int/insights/2024/10/fama-french-5-factor-model-five-major-concerns

---

## 카테고리 6: 실적 서프라이즈 / 추정치

### F-35: Earnings Surprise (실적 서프라이즈)
- **정의**: (실제 EPS - 컨센서스 EPS) / |컨센서스 EPS| x 100 (%)
  - SUE(Standardized Unexpected Earnings) = 서프라이즈 / 표준편차
- **신호 방향**: SUE 상위 10% → 향후 60일 추가 상승 기대 (PEAD)
- **PIT 주의사항**: 실적 발표일 당일 또는 다음 영업일부터 사용. 발표 전 컨센서스 시점 기록 필수.
- **DB 가용성**: 외부 — FnGuide/WiseFn 컨센서스 + 실적 발표 데이터 필요
- **출처**: Ball & Brown (1968) Journal of Accounting Research
- **출처 URL**: https://en.wikipedia.org/wiki/Post%E2%80%93earnings-announcement_drift

---

### F-36: PEAD (Post-Earnings Announcement Drift)
- **정의**: 실적 서프라이즈 후 30~60일 추세 추종 전략
  - 긍정 서프라이즈 후 매수, 부정 서프라이즈 후 매도/회피
- **신호 방향**: 발표 후 주가 반응이 미약(< 3% 상승)한 대형 긍정 서프라이즈 → drift 강도 더 높음
- **한국 적용**: 분기 실적 발표 후 1~2개월 추세 추종. 비유동성 소형주 PEAD 효과 큼 (거래비용 주의).
- **PIT 주의사항**: 발표일 D+1 기준으로 포지션 진입.
- **DB 가용성**: 외부 — 컨센서스 데이터 + DART 실적 발표 연동 필요
- **출처**: Ball & Brown (1968); Bernard & Thomas (1989)
- **출처 URL**: https://quantpedia.com/strategies/post-earnings-announcement-effect

---

### F-37: Earnings Revision Ratio
- **정의**: 최근 30일 내 추정치 상향 애널리스트 수 / (상향 + 하향 + 유지) x 100 (%)
- **신호 방향**: Revision Ratio > 70% → 강한 상향 모멘텀; < 30% → 하향 압력
- **학술 근거**: 투자자 과소반응(underreaction) — 추정치 변화가 6~12개월 초과수익 예측
- **DB 가용성**: 외부 — FnGuide/WiseFn 애널리스트 추정치 이력 필요
- **출처**: Mill Street Research; Causeway Capital Management (Aug 2018)
- **출처 URL**: https://www.millstreetresearch.com/do-analyst-estimate-revisions-still-help-forecast-relative-stock-returns/

---

### F-38: Guidance Change (경영진 가이던스 변화)
- **정의**: 실적 발표 콘퍼런스콜·공시에서 경영진의 연간 가이던스 상향/하향/유지
- **신호 방향**: 가이던스 상향 → 매수 신호; 하향 → 매도/회피
- **한국 특수**: 한국 기업은 명시적 가이던스 공시 적음. IR 자료·실적 발표 공시 분석 필요.
- **PIT 주의사항**: 공시 기준일 이후 사용.
- **DB 가용성**: 외부 — DART 공시 텍스트 분석(NLP) 또는 컨센서스 서비스 필요
- **출처**: Damodaran Investment Valuation (2012)

---

## 카테고리 7: 공시 이벤트

### F-39: Pre-Earnings Positioning (실적 발표 전 포지션)
- **정의**: 실적 발표일 D-5~D-1 기간 내 긍정 서프라이즈 예상 종목 매수
- **신호 방향**: 과거 연속 긍정 서프라이즈 + 추정치 상향 → D-5 진입, D+1 청산
- **PIT 주의사항**: 발표 전 기간이므로 미발표 실적 사용 금지. 과거 패턴만 활용.
- **DB 가용성**: 외부 — 실적 발표 일정 캘린더 (DART/KRX 공시 일정)
- **출처 URL**: https://www.daytrading.com/post-earnings-announcement-drift-pead-strategy

---

### F-40: 무상증자 공시 효과
- **정의**: 무상증자 결정 공시 후 주가 반응 추종
- **신호 방향**: 공시일 D+0~D+3 단기 상승 (유동성·호재 인식); 권리락 후 희석 주의
- **한국 특수**: 한국 시장에서 무상증자 공시 후 단기 급등 패턴 반복적. KRX 공시 유형: 무상증자결정(코드 B001)
- **PIT 주의사항**: 공시일 기준. 사전 정보 활용 금지.
- **DB 가용성**: 부분 — corp_events 테이블 존재. 무상증자 이벤트 수집 여부 확인 필요.
- **출처**: DART OpenAPI (https://opendart.fss.or.kr)

---

### F-41: 자기주식 취득 공시 (Stock Buyback)
- **정의**: 자사주 취득 결정 공시 후 주가 반응 추종
- **신호 방향**: 공시 후 D+0~D+5 단기 상승; 장기적으로 EPS 희석 감소 효과
- **PIT 주의사항**: 공시일 이후 사용. 취득 규모(총발행주식 대비 %) 반드시 확인.
- **DB 가용성**: 부분 — corp_events 테이블 활용 가능성 (백필 대상 확인 필요)
- **출처**: DART OpenAPI; 한국재무학회 자사주 매입 효과 연구

---

### F-42: 배당 공시 (Dividend Announcement)
- **정의**: 결산 배당 공시 후 배당수익률 + 주가 반응 추종
- **신호 방향**: 배당 증가 공시 → 단기 상승; 배당 삭감 → 하락 신호
- **한국 특수**: 한국은 12월 결산법인 배당 집중 (11~12월 배당주 전략). 배당락일 전 매수 후 락일 전 매도 패턴.
- **PIT 주의사항**: 배당 공시일 이후 사용. 배당락일 전후 구분 필수.
- **DB 가용성**: 외부 — DART 결산배당결정 공시 연동 필요
- **출처**: Fama & French (1988); DART OpenAPI

---

### F-43: M&A / 분할 공시
- **정의**: 합병·인수·분할 공시 후 피인수 기업 프리미엄 + 인수 기업 단기 반응
- **신호 방향**: 피인수 기업: 공시 당일 급등 (프리미엄 20~30%); 인수 기업: 단기 약세 경향
- **PIT 주의사항**: 공시일 이후 사용.
- **DB 가용성**: 외부 — DART 공시 API 필요
- **출처**: DART OpenAPI (https://englishdart.fss.or.kr)

---

## 카테고리 8: 한국 특수 지표

### F-44: 코스피200 편입 효과
- **정의**: KOSPI200 정기 리밸런싱(6월·12월) 편입 예상 종목 사전 매수
- **신호 방향**: 편입 확정 후 D-5~D+2 일시 상승 (패시브 ETF 추종 매수 수요). passive 충격 0.7~21x ADV.
- **메커니즘**: KRX는 6개월 평균 시총 기준 편입 결정 → 편입 확정 공고 → 편입 실효일 passive 매수
- **PIT 주의사항**: 편입 확정 공고(KRX 발표) 이후 사용. 예상 단계는 추정이므로 신중.
- **DB 가용성**: 외부 — KRX 지수 편출입 공고 + daily_prices 조합 필요
- **출처**: SmartKarma KOSPI200 Rebalance; ResearchGate Korean stock market index constitution
- **출처 URL**: https://www.smartkarma.com/insights/kospi200-index-rebalance-nearly-perfect

---

### F-45: MSCI Korea 편입/편출 효과
- **정의**: MSCI Korea 지수 정기 리뷰(2월·5월·8월·11월) 편입/편출 예상 종목 대응
- **신호 방향**: 편입 → 글로벌 패시브 자금 유입; 편출 → 외국인 매도 압력
- **PIT 주의사항**: MSCI 공식 발표(리뷰 결과 발표일) 이후 사용.
- **DB 가용성**: 외부 — MSCI 발표 데이터 + 외국인 수급 연동 필요
- **출처**: MSCI Global Investable Market Indexes Methodology

---

### F-46: FnGuide 컨센서스 업사이드
- **정의**: FnGuide 컨센서스 기반 목표주가 대비 현재가 괴리율
  - 업사이드 = (컨센서스 목표가 - 현재가) / 현재가 x 100 (%)
- **신호 방향**: 업사이드 > 30% → 애널리스트 매수 의견 집중 (단, 낙관 편향 주의)
- **PIT 주의사항**: 목표가 발행일 기준. 3개월 이상 된 목표가는 신뢰도 하락.
- **DB 가용성**: 외부 — FnGuide 구독 필요
- **출처**: FnGuide (https://www.fnguide.com)

---

## DB 즉시 가용 Top 5

| 순위 | 시그널 ID | 시그널명 | DB 컬럼 | 즉시 가능 이유 |
|------|-----------|---------|---------|--------------|
| 1 | F-11 | ROE | financial_statements.roe, yearly_fundamentals.roe | 직접 컬럼 존재 |
| 2 | F-01 | PER | financial_statements.per, yearly_fundamentals.per | 직접 컬럼 존재 |
| 3 | F-15 | 영업이익률 | financial_statements.operating_margin, yearly_fundamentals.op_margin | 직접 컬럼 존재 |
| 4 | F-19 | 매출 성장률 | financial_statements.revenue (분기 시계열), yearly_fundamentals.revenue_growth | 분기 시계열 YoY 계산 |
| 5 | F-25 | 유동비율 | financial_statements.current_assets / current_liabilities | 컬럼 조합 계산 |

---

## 외부 데이터 필요 컨셉 요약

| 데이터 소스 | 필요 시그널 |
|------------|-----------|
| DART XBRL 현금흐름표 | F-10(FCF Yield), F-29(Piotroski 현금흐름 기준), F-30(Beneish TATA), F-32(Sloan Accruals) |
| DART XBRL 손익계산서 세부 | F-17(Gross Margin/COGS), F-27(이자비용), F-28(이익잉여금) |
| DART 공시 API | F-39(실적발표일정), F-40(무상증자), F-41(자사주), F-42(배당), F-43(M&A) |
| FnGuide/WiseFn 컨센서스 | F-02(Forward PER), F-22(EPS Revision), F-35(Earnings Surprise), F-36(PEAD), F-37(Revision Ratio), F-38(Guidance), F-46(목표가 업사이드) |
| KRX 지수 데이터 | F-44(KOSPI200 편출입) |
| MSCI 발표 | F-45(MSCI 편출입) |

---

## No Look-Ahead 체크리스트

1. 재무제표: 분기별 report_date 기준 — 항상 발표일(공시일) 이후 데이터만 참조
2. 컨센서스 추정치: 조회 시점의 타임스탬프 기록 필수; 과거 시점 백테스트 시 해당 시점의 컨센서스 사용
3. 공시 이벤트: corp_events 테이블의 공시일 기준; 공시 전 정보 사용 절대 금지
4. 지수 편출입: KRX/MSCI 공식 발표일 이후만 사용; 예상 단계는 추정 데이터로 명시
5. Shiller CAPE(F-03): 현재 DB 5년치(2021~2025)로는 10년 CAPE 계산 불가 — 제외 또는 5년 PE로 대체

---

## 출처 요약

| 원전 | 인용 시그널 |
|------|-----------|
| Piotroski (2000) Journal of Accounting Research 38:1-41 | F-12, F-17, F-18, F-25, F-29 |
| Beneish (1999) Financial Analysts Journal | F-30 |
| Greenblatt (2005) The Little Book That Beats the Market | F-07, F-13, F-31 |
| Altman (1968) Journal of Finance | F-28 |
| Sloan (1996) Accounting Review 71(3):289-315 | F-32 |
| Fama & French (1992, 2015) Journal of Finance | F-01, F-05, F-11, F-15 |
| Ball & Brown (1968) Journal of Accounting Research | F-35, F-36 |
| O'Shaughnessy (1996) What Works on Wall Street | F-06, F-16, F-19, F-33 |
| Lynch (1989) One Up on Wall Street | F-04, F-21 |
| AQR / Asness, Frazzini & Pedersen (2019) | F-34 |
| KRX SmartKarma / ResearchGate Korean index research | F-44 |
| Mill Street Research / Causeway Capital | F-37 |
| Damodaran Investment Valuation (2012) | F-02, F-07, F-08, F-38 |