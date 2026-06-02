# 수급 시그널 카탈로그 (Phase 5 — Category 4: Flow)

> 작성일: 2026-05-25 | 조사자: document-specialist (Claude)
> 참고: 00_kyobo_books.md (책 3권) + KIS Open API 포탈 + pykrx(KRX) + DART OpenAPI + 학술·실무 문헌
> 목적: 시그널 패밀리 37 → 100+ 확장 — 수급(Flow) 카테고리 신규 정의

---

## No Look-Ahead 원칙 (PIT 강제)

| 데이터 종류 | 공시·확정 시점 | 최초 사용 가능 시점 |
|---|---|---|
| 투자자별 매매동향 (외국인/기관 등) | T일 장 마감 후 KIS/KRX 집계 (보통 T+0 21:00 이후) | T+1 시초가 진입 시 |
| 공매도 잔고 | T+1 ~ T+2 공시 (KRX 기준) | T+2 또는 T+3 시초가 |
| 신용잔고 | 매일 장 마감 후 증권사 공시 (T+0 야간) | T+1 시초가 |
| 프로그램 매매 (당일 실시간) | 장중 실시간 / EOD 집계 | 장중 실시간 사용 가능 (PIT 안전) |
| DART 5% 지분 공시 | 공시 접수 후 즉시 (수 시간 이내) | 공시 확인 시각 이후 즉시 |
| DART 임원 주식 변동 | 분기 보고서 또는 수시 공시 | 공시 확인 시각 이후 즉시 |
| 호가창·체결강도 | 장중 실시간 | 장중 실시간 (PIT 안전) |
| 시간외 단일가 | 15:30~16:00 실시간 | 16:00 이후 / 익일 시초가 |

---

## 1. 투자자별 순매수 시그널 (일별)

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-01 | 외국인 순매수 (일별) | T일 외국인 순매수금액 > 0, 종목별 | 매수 | T+1 시초 사용 | KIS API foreign-institution-total (FHPTJ04400000) / pykrx get_market_net_purchases_of_equities("외국인") | 조건부 (KIS 404 이슈, pykrx 가능) |
| F-02 | 기관 순매수 (일별) | T일 기관합계 순매수금액 > 0 | 매수 | T+1 시초 사용 | KIS API 동일 / pykrx "기관합계" | 조건부 |
| F-03 | 외국인+기관 동시 순매수 | T일 외국인 AND 기관 모두 순매수 | 강매수 | T+1 시초 사용 | 위 F-01, F-02 조합 | 조건부 |
| F-04 | 연기금 순매수 | T일 연기금 순매수 > 0 | 강매수 (중장기) | T+1 시초 사용 | pykrx "연기금" | pykrx 가능 |
| F-05 | 사모펀드 순매수 | T일 사모 순매수 > 0 | 매수 | T+1 시초 사용 | pykrx "사모" | pykrx 가능 |
| F-06 | 외국인 5일 누적 순매수 | 최근 5영업일 외국인 순매수금액 합계 > 0 | 추세 매수 | T+1 시초 사용 | pykrx 연속 호출 후 rolling sum | pykrx 가능 |
| F-07 | 외국인 순매수 가속도 | (T일 외국인 순매수) - (T-1일 외국인 순매수) > 임계값 | 급증 추세 | T+1 시초 사용 | pykrx | pykrx 가능 |

**pykrx 함수 시그니처:**
```python
from pykrx import stock
df = stock.get_market_net_purchases_of_equities(
    "20260520", "20260524", "KOSPI",
    "외국인"   # 금융투자/보험/투신/사모/은행/기타금융/연기금/기관합계/기타법인/개인/외국인/기타외국인/전체
)
# 반환: 종목명, 매도거래량, 매수거래량, 순매수거래량, 매도거래대금, 매수거래대금, 순매수거래대금
```

---

## 2. 외국인 보유 비중 시그널

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-08 | 외국인 보유 비중 증가 추세 | 외국인보유주식수 / 상장주식수 — 최근 5일 증가 추세 | 매수 | T+1 사용 | pykrx get_market_cap() 외국인보유주식수 컬럼 | pykrx 가능 |
| F-09 | 외국인 보유 비중 임계 돌파 | 외국인 보유율 직전 고점 갱신 (신고점) | 강매수 | T+1 사용 | pykrx | pykrx 가능 |
| F-10 | 외국인 매도 가속도 (역시그널) | 최근 3일 외국인 순매도 가속화 → 매수 대기 또는 회피 | 매도 회피 | T+1 사용 | pykrx | pykrx 가능 |

**pykrx 함수 시그니처:**
```python
df = stock.get_market_cap("20260524")
# 반환: 시가총액, 거래량, 거래대금, 상장주식수, 외국인보유주식수
foreign_ratio = df["외국인보유주식수"] / df["상장주식수"]
```

---

## 3. 프로그램 매매 시그널

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-11 | 프로그램 비차익 순매수 급증 | 당일 비차익 프로그램 순매수 > N억 (임계값 설정) | 매수 (ETF 리밸런싱 편승) | 장중 실시간 PIT 안전 | KIS API comp-program-trade-today (포탈 [국내주식-114]) | KIS API (신규 구현 필요) |
| F-12 | 프로그램 매수 우위 지속 | 당일 프로그램 매수 - 매도 > 0이 N일 연속 | 추세 매수 | T+1 일별 집계 사용 | KIS API 종목별 프로그램매매추이(일별) | 신규 구현 필요 |
| F-13 | 옵션 만기일 프로그램 급변 | 매월 두 번째 목요일 (선물옵션 동시만기) 전후 프로그램 매매 급변 | 변동성 확대 경고 | 장중 실시간 | 캘린더 + KIS 프로그램 API | 캘린더 즉시 가능 |

**KIS API 엔드포인트 (포탈 메뉴 확인 기준):**
- 종목별 프로그램매매추이(체결): /uapi/domestic-stock/v1/quotations/program-trade-by-stock
- 프로그램매매 종합현황(시간): /uapi/domestic-stock/v1/quotations/comp-program-trade-today
- 프로그램매매 종합현황(일별): 별도 엔드포인트 (포탈 메뉴 [국내주식-114])
- 출처: https://apiportal.koreainvestment.com/apiservice-category

---

## 4. 공매도 시그널

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-14 | 공매도 비율 급증 | 당일 공매도 거래량 / 전체 거래량 > 임계값 (예: 5%) | 매도 압력 신호 | T+1~T+2 (KRX 공시 기준) | pykrx get_shorting_volume_top50() / KIS 공매도 일별추이 | pykrx 가능 |
| F-15 | 공매도 잔고 증가 추세 | 공매도 잔고 5일 연속 증가 → 매수 회피 | 매도 경계 | T+2 이후 | pykrx get_shorting_balance_by_ticker() | pykrx 가능 |
| F-16 | 공매도 잔고 감소 (숏커버링 기대) | 공매도 잔고 급감 → 숏커버링 매수 수요 기대 | 잠재 매수 | T+2 이후 | pykrx | pykrx 가능 |
| F-17 | 대차잔고 증가 | 대차잔고 급증 → 향후 공매도 증가 선행 지표 | 매도 압력 예고 | T+1 이후 | KIS API 종목별 일별 대차거래추이 (포탈 메뉴) | 신규 구현 필요 |

**pykrx 함수 참고:**
```python
# 공매도 잔고 (종목별, 기간)
df_short = stock.get_shorting_balance_by_ticker("20260501", "20260524", "KOSPI")
# 반환: 잔고수량, 잔고금액, 잔고비율

# 투자자별 공매도 거래량
df_inv_short = stock.get_shorting_investor_volume_by_date("20260501", "20260524")
```

---

## 5. 신용잔고 시그널

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-18 | 신용잔고율 과다 (매도 압력) | 신용잔고 / 상장주식수 > 임계값 (예: 2%) → 반대매매 위험 | 매수 회피 | T+1 야간 공시 → T+1 사용 | KIS API 국내주식 신용잔고 일별추이 (포탈 시세분석 카테고리) | 신규 구현 필요 |
| F-19 | 신용잔고 감소 추세 | 신용잔고 5일 연속 감소 → 매물 부담 완화 | 매수 우호 | T+1 사용 | KIS API 동일 | 신규 구현 필요 |
| F-20 | 신용잔고 급증 (과열 경고) | 신용잔고 전일 대비 10% 이상 급증 | 과열 매수 경고 | T+1 사용 | KIS API 동일 / 순위분석: 국내주식 신용잔고 상위 | 신규 구현 필요 |

---

## 6. 거래량·거래대금 수급 시그널

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-21 | 거래량 x3배 급증 | T일 거래량 > 20일 평균 거래량 x 3 | 방향성 추종 | T+1 사용 (일별) | daily_prices.volume (DB) | DB 즉시 가능 |
| F-22 | 거래대금 xN배 급증 | T일 거래대금 > 20일 평균 거래대금 x N (N=3 기본) | 방향성 추종 | 동일 | daily_prices.trading_value (DB) | DB 즉시 가능 |
| F-23 | OBV (On-Balance Volume) | OBV = 누적합(상승일: +거래량, 하락일: -거래량). OBV 신고점 돌파 | 매수 | T+1 일봉 기준 PIT 안전 | daily_prices (DB) — close, volume 컬럼 | DB 즉시 가능 |
| F-24 | A/D Line (Accumulation/Distribution) | AD = ((close-low)-(high-close))/(high-low) * volume 누적 | 분배 vs 축적 판단 | T+1 일봉 기준 | daily_prices (DB) | DB 즉시 가능 |
| F-25 | Chaikin Money Flow (CMF) | CMF = 20일 AD 합계 / 20일 거래량 합계. 양수 = 매수 압력 | 매수 | T+1 일봉 | daily_prices (DB) | DB 즉시 가능 |

---

## 7. 호가창 수급 시그널 (장중 실시간 — PIT 무조건 안전)

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-26 | 매수 호가 잔량 우위 | 매수 5호가 잔량 합계 / 매도 5호가 잔량 합계 > 1.5 | 매수 우세 | 실시간 PIT 안전 | KIS inquire-asking-price-exp-ccn (TR: FHKST01010200) output2 호가 잔량 | KIS API 즉시 가능 |
| F-27 | 매도 호가 잔량 이탈 | 상단 매도 호가 잔량이 이전 대비 50% 이상 급감 | 저항 약화 → 매수 | 실시간 PIT 안전 | 동일 | KIS API 즉시 가능 |
| F-28 | 호가 강도 (허수 호가 탐지) | 대량 매도 호가 출현 후 즉시 취소 반복 → 세력 방향 역독 | 세력 방향 추정 | 실시간 PIT 안전 | KIS inquire-asking-price-exp-ccn 연속 폴링 | 복잡 구현 필요 |

**KIS API:**
- 주식현재가 호가 예상체결: /uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn (TR: FHKST01010200)
- output1: 예상 체결가/수량, output2: 호가별 잔량 10단계

---

## 8. 체결강도 시그널 (장중 실시간)

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-29 | 매수 체결강도 | 체결강도 = 매수체결량 / 매도체결량 x 100. > 100 = 매수 우세 | 매수 | 실시간 PIT 안전 | KIS inquire-ccnl (TR: FHKST01010300) — 체결 내역 30건 집계 | KIS API 즉시 가능 (get_inquire_ccnl 구현됨) |
| F-30 | 누적 체결강도 (당일) | 장 시작부터 현재까지 누적 매수체결 / 누적 매도체결 | 추세 강도 | 실시간 PIT 안전 | KIS 체결 API 누적 집계 | 구현 필요 (메모리 집계) |
| F-31 | 능동 매수 비율 | 매수 주도 체결(매도호가 출격) / 전체 체결 — 높을수록 매수 의지 강 | 강매수 신호 | 실시간 PIT 안전 | KIS 체결 API 체결 구분 필드 | 구현 필요 |

---

## 9. VWAP 수급 시그널 (장중)

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-32 | VWAP 위 매매 | 현재가 > VWAP (ΣPV / ΣV, 장 개시부터 누적) → 기관 매수 구간 편승 | 매수 | 실시간 PIT 안전 | minute_candles (DB) 또는 KIS 분봉 API로 실시간 계산 | minute_candles DB 즉시 계산 가능 |
| F-33 | VWAP 하향 이탈 | 현재가 < VWAP → 기관 분배 구간, 매도 신호 | 매도 | 실시간 PIT 안전 | 동일 | 즉시 가능 |
| F-34 | VWAP 반등 매수 (Bounce) | 하락 후 VWAP 재터치 → 반등 첫 분봉 매수 | 매수 | 실시간 PIT 안전 | 동일 | 즉시 가능 |

**계산 예시:**
```python
# minute_candles 기준 당일 VWAP 계산
vwap = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
signal_long = df["close"] > vwap
```

---

## 10. 동시호가·시간외 시그널

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-35 | 시초가 동시호가 매수 우위 | 08:30~09:00 동시호가 잔량 — 매수 잔량 >> 매도 잔량 | 갭상승 예측 | 호가 집계 시점 이후 PIT 안전 | KIS 호가 API (시간외 동시호가 잔량) | 구현 필요 |
| F-36 | 시간외 단일가 상승 → 익일 갭 예측 | 시간외 단일가(15:30~16:00) 전일 종가 대비 N% 이상 상승 | 익일 갭상승 기대 | 16:00 이후 데이터 → T+1 시초 사용 | KIS 시간외 단일가 API | 구현 필요 |
| F-37 | 마감 동시호가 대량 매수 잔량 | 15:20~15:30 마감 동시호가 매수 잔량 급증 | 종가 베팅 세력 감지 | 실시간 (15:20 이후) | KIS 호가 API | 구현 필요 |

---

## 11. 공시 기반 수급 시그널 (DART)

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-38 | 임원 주식 매수 공시 | DART elestock API — 임원 순매수 공시 (sp_stock_lmp_irds_cnt > 0) | 매수 (내부자 정보) | 공시 접수 즉시 PIT 안전 | DART OpenAPI https://opendart.fss.or.kr/api/elestock.json | DART API 신규 구현 필요 |
| F-39 | 임원 주식 대량 매도 공시 | 임원 순매도 공시 → 매도 압력 선행 신호 | 매도 경계 | 공시 즉시 | DART 동일 | 신규 구현 필요 |
| F-40 | 5% 지분 신규 취득 공시 | 대량보유보고 — 신규 5% 이상 취득 (보고 후 5영업일 이내) | 강매수 | 공시 즉시 | DART majorstock.json | 신규 구현 필요 |
| F-41 | 5% 지분 추가 취득 (+1% 이상) | 기존 5% 이상 보유자의 추가 1% 취득 | 추세 매수 | 공시 즉시 | DART 동일 | 신규 구현 필요 |
| F-42 | 자기주식 취득 결의 공시 | 회사 자사주 매입 공시 (호재) | 매수 우호 | 공시 즉시 | DART 주요사항보고 키워드 필터 | 신규 구현 필요 |

**DART API 참고:**
- 임원·대주주 소유현황: GET https://opendart.fss.or.kr/api/elestock.json?crtfc_key=...&corp_code=...
- 출력 필드: rcept_dt, repror, isu_exctv_ofcps, sp_stock_lmp_irds_cnt(변동수량), sp_stock_lmp_rate(보유율)
- 지분공시: GET https://opendart.fss.or.kr/api/majorstock.json (대량보유보고)
- 출처: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS004&apiId=2019022

---

## 12. 투자 경보·제도 시그널

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-43 | 단기과열종목 지정 | KRX 단기과열종목 지정 → 매매 제한 (5일 단일가) | 매수 회피 | 지정일 공시 직후 | corp_events 테이블 (기존 스키마) | 즉시 가능 |
| F-44 | 투자주의·경고·위험 지정 | 거래소 이상매매 종목 지정 → 거래 위험 경고 | 매수 회피 | 지정일 즉시 | corp_events 테이블 (기존 스키마) | 즉시 가능 |
| F-45 | 투자주의·경고 해제 | end_date 도달 → 제약 해소 (반등 기대) | 잠재 매수 | end_date 이후 | corp_events.end_date (기존 스키마 04-corp-events-end-date.sql) | 즉시 가능 |

---

## 13. 시간외 대량매매·블록딜 시그널

| # | 시그널명 | 정의·계산 | 방향성 | No-LA 검증 | 데이터 출처 | 즉시 가용 |
|---|---|---|---|---|---|---|
| F-46 | 시간외 대량매매 (블록딜) 체결 | 장 마감 후 시간외 대량 매도 → 할인 공급 과잉 | 매도 압력 | 공시 즉시 | KRX 공시 / 한경·매경 블록딜 뉴스 필터 | 뉴스 파싱 필요 |
| F-47 | 블록딜 이후 저가 반등 | 블록딜 당일 저점 대비 익일 반등 패턴 | 매수 (반등) | T+1 시초 사용 | F-46 + 가격 데이터 | 복합 구현 필요 |

---

## 카테고리 합산 요약

| 서브카테고리 | 시그널 수 | 즉시 가용 건수 | 주요 데이터 소스 |
|---|---|---|---|
| 투자자별 순매수 (일별) | 7 (F-01~07) | 5 (pykrx) | pykrx / KIS API |
| 외국인 보유 비중 | 3 (F-08~10) | 3 (pykrx) | pykrx |
| 프로그램 매매 | 3 (F-11~13) | 1 (캘린더) | KIS API (신규) |
| 공매도 | 4 (F-14~17) | 3 (pykrx) | pykrx / KIS API |
| 신용잔고 | 3 (F-18~20) | 0 | KIS API (신규) |
| 거래량·거래대금 | 5 (F-21~25) | 5 (DB) | daily_prices DB |
| 호가창 | 3 (F-26~28) | 2 (KIS 구현됨) | KIS API |
| 체결강도 | 3 (F-29~31) | 1 (부분) | KIS API |
| VWAP | 3 (F-32~34) | 3 (minute_candles DB) | minute_candles DB |
| 동시호가·시간외 | 3 (F-35~37) | 0 | KIS API (신규) |
| DART 공시 | 5 (F-38~42) | 0 | DART OpenAPI (신규) |
| 투자경보·제도 | 3 (F-43~45) | 3 (corp_events 기존) | corp_events DB |
| 블록딜·대량매매 | 2 (F-46~47) | 0 | KRX/뉴스 (신규) |
| **합계** | **47** | **26** | |

---

## 즉시 활용 가능 Top 3 (데이터 가용 확인 기준)

### 1위 — OBV / CMF (F-23, F-25)
- 데이터: daily_prices DB — 이미 운영 중, volume + close 컬럼 존재 (01-init.sql 스키마 확인)
- 코드 변경: daily_prices 조회 후 pandas rolling 계산만 추가
- PIT: T+1 일봉 기준 완전 안전
- 구현 복잡도: 낮음 (수식 계산)

### 2위 — 외국인 5일 누적 순매수 (F-06)
- 데이터: pykrx get_market_net_purchases_of_equities — 즉시 호출 가능
- pykrx는 이미 backfill_corp_events.py에서 사용 중 (의존성 기존 존재)
- PIT: T+1 시초 사용 → 완전 안전
- 구현 복잡도: 낮음 (pykrx rolling sum)

### 3위 — VWAP 위/아래 판단 (F-32, F-33)
- 데이터: robotrader.minute_candles — 1,347종목·318일·5,116만행 이미 존재
- 계산: 당일 분봉 누적 VWAP = cumsum(close*volume)/cumsum(volume)
- PIT: 장중 실시간 → 완전 안전
- 구현 복잡도: 낮음 (pandas cumsum)

---

## 데이터 누락 컨셉 (미해결 항목)

| 미해결 항목 | 이유 | 대안 방향 |
|---|---|---|
| KIS 투자자별 매매동향 TR (FHPTJ04400000) | 현재 코드 404 오류 — 엔드포인트 미확정 | KIS 공식 포탈에서 정확한 TR 재확인. 대안: pykrx로 동일 데이터 조달 |
| 신용잔고 일별 (F-18~20) | KIS API 엔드포인트 미구현 | KIS 포탈 국내주식 신용잔고 일별추이 메뉴 — TR코드 확인 후 구현 |
| 대차잔고 (F-17) | KIS 포탈 메뉴 존재 확인, TR코드 미확인 | KIS 포탈 직접 조회 |
| DART 공시 (F-38~42) | DART OpenAPI 신규 연동 필요 | dart-fss 또는 OpenDartReader 라이브러리 활용 |
| 블록딜·시간외 대량매매 (F-46~47) | 구조화된 공식 API 없음 | KRX 공시 스크래핑 또는 뉴스 키워드 파싱 |
| 프로그램 매매 종목별 일별 (F-11~12) | KIS 엔드포인트 미구현 | KIS 포탈 종목별 프로그램매매추이(일별) TR코드 확인 필요 |

---

## 외부 참고 출처

| 항목 | 출처 URL |
|---|---|
| KIS Open API 포탈 (투자자별/프로그램/공매도/신용잔고 메뉴 확인) | https://apiportal.koreainvestment.com/apiservice-category |
| KIS open-trading-api GitHub | https://github.com/koreainvestment/open-trading-api |
| pykrx (KRX 스크래핑 라이브러리) | https://github.com/sharebook-kr/pykrx |
| DART OpenAPI 지분공시 개발가이드 | https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS004&apiId=2019022 |
| DART OpenAPI 임원·대주주 소유현황 | https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020029 |
| KRX 정보데이터시스템 | https://data.krx.co.kr/ |
| KRX Open API | https://openapi.krx.co.kr/ |
| 책 1 (강창권, 단기 트레이딩의 정석) | https://product.kyobobook.co.kr/detail/S000217567051 |
| 책 2 (이시이 카츠토시, 데이트레이딩 100법칙) | https://product.kyobobook.co.kr/detail/S000001014275 |
| 책 3 (앤드루 아지즈, 도박꾼이 아니라 트레이더가 되어라) | https://product.kyobobook.co.kr/detail/S000001777389 |

---

## 책 vs 외부 기여 비율

| 출처 | 기여 시그널 수 | 주요 기여 영역 |
|---|---|---|
| 책 3권 (00_kyobo_books.md 기반) | 11 | 호가창(F-26~28), 체결강도(F-29~31), VWAP(F-32~34), 프로그램매수(F-11), 기관외국인EOD(F-01~03) |
| 외부 조사 (KIS/KRX/DART/pykrx) | 36 | 투자자별 세분화(F-04~10), 공매도(F-14~17), 신용잔고(F-18~20), OBV/AD/CMF(F-23~25), 공시(F-38~45), 블록딜(F-46~47) |
| **합계** | **47** | |
