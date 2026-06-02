# Phase 5 — 카테고리 2: 박스권 매매

> 작성일: 2026-05-25 | 조사자: document-specialist (Claude)
> 참고 원본: `phase5_signals/00_kyobo_books.md` (책 3권) + 외부 문헌 7종

총 **20개** 컨셉 (책 3권에서 5개 직접 추출 + 외부 문헌 15개)

---

## 컨셉 카탈로그

### 1. 횡보 후 박스 돌파 (Box Breakout with Volume)

- **정의**: N일(기본 20일) 고가/저가 범위(박스)를 종가 기준으로 돌파 + 거래량이 전일 대비 1.5× 이상 동반
  - 박스 폭 조건: `(N_high - N_low) / N_low <= 15%` (박스 노이즈 상한)
  - 진입: `close > N_high` AND `volume > volume_ma20 * 1.5`
  - 손절: 박스 상단 이탈 후 종가 재진입 시 (N_low 기준 ATR*1)
- **출처**: 책 2 (이시이 카츠토시) Rule 63~65 "횡보 후 돌파"; Donchian Channel Breakout — https://www.luxalgo.com/blog/donchian-channels-breakout-and-trend-following-strategy/
- **카테고리 태그**: Stage B→C 전환
- **버킷**: swing (2~5일 보유)
- **한국 시장 적용 사례**: KOSPI/KOSDAQ 소형주에서 자주 관찰. 거래량 조건이 없으면 세력 조작성 돌파에 노출됨
- **PIT-safe 가능성**: 가능 — `최근 N일 high/low`는 당일 종가 확정 후 계산하면 완전 PIT-safe
- **필요 데이터**: 일봉 OHLCV (N>=20일), 일봉 거래량 이동평균
- **예상 difficulty**: 중 (★★☆)

---

### 2. Donchian 채널 이중 기간 전략 (Dual-Period Donchian)

- **정의**: 진입 채널(N1=55일)과 청산 채널(N2=20일)을 분리 운용
  - 진입: `close > Donchian_high(55)` → 매수
  - 청산: `close < Donchian_low(20)` → 매도
  - 포지션 크기: `risk_per_trade / (ATR14 * 2)` (ATR 기반 동적 사이징)
- **출처**: Donchian Channel Strategy — https://blog.quantinsti.com/donchian-channel-strategy/; TrendSpider — https://trendspider.com/learning-center/donchian-channel-trading-strategies/
- **카테고리 태그**: Stage C (추세 편승)
- **버킷**: position (3주~3개월)
- **한국 시장 적용 사례**: 코스피 대형주(삼성전자, SK하이닉스) 장기 추세 추종에 적용 가능. 단기 박스 이탈 노이즈 필터에 20일 청산 채널 유효
- **PIT-safe 가능성**: 가능 — 전일 종가 기준 채널 계산
- **필요 데이터**: 일봉 OHLCV 55일+
- **예상 difficulty**: 중 (★★☆)

---

### 3. ATR 기반 박스 정의 + 목표가 계산 (ATR-Defined Box)

- **정의**: 박스를 절대가격 범위가 아닌 ATR 배수로 정의
  - 박스 높이 조건: `(N_high - N_low) <= ATR14 * 3` (3ATR 이내면 박스로 인정)
  - 박스 내 매수: `close <= N_low + ATR14 * 0.5` (하단 0.5ATR 구간 매수)
  - 목표가: 진입가 + `ATR14 * 2` (mean reversion 목표)
  - 손절: 진입가 - `ATR14 * 1.5` (chandelier stop)
- **출처**: ATR Range Trading — https://volatilitybox.com/research/atr-average-true-range/; QuantifiedStrategies — https://www.quantifiedstrategies.com/average-true-range-trading-strategy/
- **카테고리 태그**: Stage A/B (박스 확인 중)
- **버킷**: swing (1~5일)
- **한국 시장 적용 사례**: 코스닥 변동성이 높은 구간에서 ATR이 실제 가격 노이즈를 반영해 절대가격 기반보다 적합
- **PIT-safe 가능성**: 가능 — ATR14는 당일 포함 전일까지 14일 데이터로 계산
- **필요 데이터**: 일봉 OHLCV 14일+
- **예상 difficulty**: 중 (★★☆)

---

### 4. 박스 하단 매수 / 상단 매도 (Mean Reversion Box)

- **정의**: 박스 상하단을 지지/저항으로 활용한 왕복 매매
  - 박스 확인: `최근 20일 (high_max - low_min) / low_min <= 10%`이고 상단/하단 터치 횟수 >= 2회
  - 매수: `close <= box_low * 1.01` (하단 1% 이내)
  - 매도: `close >= box_high * 0.99` (상단 1% 이내)
  - 손절: `close < box_low * 0.97` (하단 3% 이탈)
- **출처**: 책 2 (이시이 카츠토시) Rule 15~23 "하락 중 기회 포착"; Bollinger Band range — https://alphasquare.co.kr/home/insight/posts/2abbd8ab-cc12-448e-9b5e-2db04a939b1b
- **카테고리 태그**: Stage B (박스 내부 매매)
- **버킷**: swing (1~3일)
- **한국 시장 적용 사례**: 횡보장 종목에서 유효. 돌파 이후 손절 필수 — 한국 시장은 세력 개입 시 박스 이탈 후 복귀 없이 급락하는 경우 있음
- **PIT-safe 가능성**: 가능 — 박스 계산은 당일 종가 후 수행
- **필요 데이터**: 일봉 OHLCV 20일+
- **예상 difficulty**: 하 (★☆☆)

---

### 5. 볼린저밴드 폭 수축 → 폭발 (Bollinger Band Squeeze)

- **정의**: BB 폭(상단-하단)이 최근 125일 최저 수준으로 수축한 후 돌파 방향 추종
  - 수축 조건: `BB_width = (BB_upper - BB_lower) / BB_mid`; `BB_width < BB_width_125day_min * 1.1`
  - 방향 확인: 수축 해소 첫 캔들 방향(양봉이면 매수, 음봉이면 관망)
  - 진입: 수축 해소 다음 봉 시가 or 되돌림 시
  - 목표가: 진입가 + 진입 시 BB_width (폭 1배 추가)
- **출처**: Bollinger Band Squeeze — https://www.xs.com/ko/blog/%EB%B3%BC%EB%A6%B0%EC%A0%80%EB%B0%B4%EB%93%9C/; 볼린저밴드 원리 — https://alphasquare.co.kr/home/insight/posts/2abbd8ab-cc12-448e-9b5e-2db04a939b1b
- **카테고리 태그**: Stage B→C 전환
- **버킷**: swing/mid (3~10일)
- **한국 시장 적용 사례**: 결산 발표 직전, M&A 재료 직전 횡보에서 자주 관찰됨. 방향이 불확실하므로 반드시 거래량 동반 여부 확인 후 진입
- **PIT-safe 가능성**: 가능 — BB는 종가 기준 계산
- **필요 데이터**: 일봉 종가 20일+, 125일 BB_width 히스토리
- **예상 difficulty**: 중 (★★☆)

---

### 6. VCP 변동성 수축 패턴 (Volatility Contraction Pattern)

- **정의**: Mark Minervini의 VCP — 각 눌림목이 이전보다 점점 좁아지는 3~4단계 수축 패턴
  - 수축 횟수: >= 3회 (예: 폭 20% → 12% → 6% → 3%)
  - 거래량: 각 수축 구간의 거래량이 이전 구간보다 감소
  - 진입: 마지막 수축 구간의 피벗(저항선) 돌파 + 거래량 급증
  - 손절: 마지막 수축 저점
- **출처**: TraderLion VCP — https://traderlion.com/technical-analysis/volatility-contraction-pattern/; TradingSim VCP 2026 — https://www.tradingsim.com/blog/volatility-contraction-pattern
- **카테고리 태그**: Stage B (압축) → Stage C (돌파)
- **버킷**: swing/mid (5~20일)
- **한국 시장 적용 사례**: 코스닥 중소형 성장주에서 수급 집중 후 VCP 형성 빈번. 볼린저밴드 스퀴즈와 병행 시 신뢰도 향상
- **PIT-safe 가능성**: 가능 — 수축 폭은 확정된 일봉 OHLC로 계산
- **필요 데이터**: 일봉 OHLCV 60일+, 거래량 이동평균
- **예상 difficulty**: 상 (★★★) — 수축 횟수 자동 감지 로직 필요

---

### 7. Wyckoff Spring (와이코프 스프링 — 가짜 하향 이탈 후 반등)

- **정의**: 박스 하단을 일시적으로 이탈(저거래량)한 후 박스 내부로 복귀하는 패턴
  - Spring 조건:
    1. `close < box_low` (하단 이탈)
    2. 이탈 구간 거래량 < 이탈 직전 5일 평균 거래량 (저량 이탈)
    3. 당일 또는 익일 `close > box_low` (복귀)
  - 진입: 복귀 확인 다음 봉 시가
  - 손절: Spring 저점 - `ATR14 * 0.5`
  - 목표: 박스 상단 (1차), 박스 상단 + 박스폭 (2차)
- **출처**: Wyckoff Analytics — https://www.wyckoffanalytics.com/wyckoff-method/; Springs & Upthrusts — https://www.financial-spread-betting.com/trading/wyckoff-spings-upthrusts.html
- **카테고리 태그**: Stage C 전환 (Phase C Accumulation)
- **버킷**: swing (2~7일)
- **한국 시장 적용 사례**: 기관 매집 구간에서 개인 투자자 손절 유발 후 반등 패턴과 일치. 프로그램 매도 출회 시 Volume이 급증하면 진짜 이탈로 간주해야 함
- **PIT-safe 가능성**: 가능 — 이탈/복귀 모두 확정 종가 기준
- **필요 데이터**: 일봉 OHLCV, 박스 정의(20일+), ATR14
- **예상 difficulty**: 상 (★★★) — 저거래량 이탈 + 복귀 동시 감지 필요

---

### 8. Wyckoff Upthrust / UTAD (가짜 상향 돌파 후 역추세)

- **정의**: 박스 상단을 일시적으로 돌파(저거래량 또는 급감)한 후 박스 내부로 복귀 → 매도 신호
  - Upthrust 조건:
    1. `close > box_high` (상단 돌파)
    2. 돌파 구간 거래량 < 직전 돌파 시도 대비 감소 (수요 고갈)
    3. 당일 또는 익일 `close < box_high` (복귀)
  - 신호: 보유 포지션 매도 또는 공매도 진입 (한국 시장 공매도 규제 주의)
  - 손절: Upthrust 고점 + `ATR14 * 0.5`
- **출처**: Wyckoff Distribution — https://alchemymarkets.com/education/guides/wyckoff-distribution/; Capital.com Wyckoff — https://capital.com/en-int/learn/technical-analysis/the-wyckoff-method
- **카테고리 태그**: Stage C (Distribution Phase C)
- **버킷**: swing (매도 신호)
- **한국 시장 적용 사례**: 공매도가 제한된 한국 시장에서는 보유 포지션 청산 신호로 주로 활용. 공매도 허용 종목(코스피 200)은 역방향 진입 가능
- **PIT-safe 가능성**: 가능 — 확정 종가 기준
- **필요 데이터**: 일봉 OHLCV, 박스 정의, ATR14
- **예상 difficulty**: 상 (★★★) — 고거래량 진짜 돌파와 구별 로직 필요

---

### 9. 페이크아웃 역추세 매매 (Fakeout Counter-Trend)

- **정의**: 박스 상단/하단 돌파 후 1~2봉 내 복귀 시 역방향 진입
  - 상단 페이크아웃: `high > box_high` 이지만 `close < box_high` → 다음 봉 매도 관점
  - 하단 페이크아웃: `low < box_low` 이지만 `close > box_low` → 다음 봉 매수 (Spring과 동일)
  - 거래량 확인: 돌파 봉의 거래량이 MA20 거래량의 2배 미만이면 페이크아웃 의심
  - 진입: 페이크아웃 확인 다음 봉 시가
  - 손절: 돌파 봉의 극값(고가 또는 저가) + `ATR14 * 0.3`
- **출처**: False Breakout Trading — https://priceaction.com/price-action-university/strategies/false-break-out/; Fakeout Guide — https://www.equiti.com/sc-en/news/trading-ideas/how-to-identify-and-trade-fakeouts-a-complete-traders-guide/
- **카테고리 태그**: Stage B/C (반전 신호)
- **버킷**: swing (1~3일)
- **한국 시장 적용 사례**: 세력 주도 종목에서 개인 손절 유발 후 재진입 패턴과 일치. 거래량 저조 돌파 → 역추세 진입은 한국 단타 커뮤니티에서 검증된 기법
- **PIT-safe 가능성**: 가능 — 모두 확정 종가 기준
- **필요 데이터**: 일봉 OHLCV, 박스 정의, ATR14, 거래량 MA
- **예상 difficulty**: 중 (★★☆)

---

### 10. N자형 눌림목 매수 (N-Shape Pullback Entry)

- **정의**: 박스 돌파 후 상승, 이전 박스 상단 수준으로 되돌린 후 재상승하는 N자형 패턴
  - 조건:
    1. 1차 상승: 박스 상단 돌파 + 거래량 급증
    2. 눌림: 되돌림 깊이 `box_high >= close >= box_high * 0.97` (3% 이내 되돌림)
    3. 거래량: 눌림 구간 거래량 < 돌파 구간 거래량 (매도세 약화)
  - 진입: 눌림목 저점 확인 후 다음 양봉 시가
  - 목표: 돌파 이후 상승폭만큼 추가 상승 (박스폭 * 1.0)
  - 손절: 눌림목 저점 - `ATR14 * 0.5`
- **출처**: 박스권 눌림목 기법 — https://ssam.teacherville.co.kr/liforu/contents/20272.edu; 책 1 (강창권) 20일선 눌림목 컨셉
- **카테고리 태그**: Stage C (추세 편승 진입)
- **버킷**: swing (2~5일)
- **한국 시장 적용 사례**: 박스 돌파 직후 거래량 급감하며 5일선까지 눌린 후 재상승하는 패턴이 코스닥에서 빈번. "눌림목 거래량 최대값의 50% 이하" 조건이 핵심
- **PIT-safe 가능성**: 가능 — 확정 일봉 기준
- **필요 데이터**: 일봉 OHLCV, 박스 정의, ATR14
- **예상 difficulty**: 중 (★★☆)

---

### 11. 박스폭 기반 목표가 계산 (Box Height Projection — Measured Move)

- **정의**: 박스 돌파 후 목표가를 박스폭 배수로 계산하는 측정된 목표값
  - 박스폭: `box_width = box_high - box_low`
  - 목표가 1차: `box_high + box_width * 1.0`
  - 목표가 2차: `box_high + box_width * 1.5`
  - 목표가 3차: `box_high + box_width * 2.0`
  - 적용: ORB 전략의 목표가 계산과 동일 논리 (책 3 Andrew Aziz 전략9)
- **출처**: 책 3 (Andrew Aziz) 전략9 ORB "측정 목표(range 높이만큼)"; Bookmap Breakout Guide — https://bookmap.com/blog/breakout-or-fakeout-the-3-point-checklist-for-confirmation
- **카테고리 태그**: Stage C (목표 설정)
- **버킷**: 모든 버킷 (목표가 계산에 범용 적용)
- **한국 시장 적용 사례**: 박스 돌파 후 1차 목표(1.0배)까지 절반 청산, 2차(1.5배) 잔량 청산이 실전 매매에서 통용
- **PIT-safe 가능성**: 가능 — 박스 정의는 돌파 전 데이터만 사용
- **필요 데이터**: 일봉 OHLCV (박스 정의 기간)
- **예상 difficulty**: 하 (★☆☆) — 목표가 계산 공식만 추가

---

### 12. 계단식 박스 누적 / Stage 분석 (Staircase Box — Weinstein Stage)

- **정의**: Stan Weinstein의 Stage 분석 기반. 박스(Stage 1/3) → 상승(Stage 2) → 박스(Stage 3) 순환 인식
  - Stage 판별 조건:
    - Stage 1 (저가 박스): 30주선(≈150일선) 기울기 ≈ 0, 가격이 30주선 상하 교차
    - Stage 2 (상승): 가격 > 30주선, 30주선 우상향
    - Stage 3 (고가 박스): 30주선 기울기 ≈ 0, 가격이 30주선 하향 교차 시작
    - Stage 4 (하락): 가격 < 30주선
  - 매수: Stage 1 → Stage 2 전환 초기
  - 매도: Stage 2 → Stage 3 전환 시
- **출처**: Weinstein Stage Analysis (Secrets for Profiting in Bull and Bear Markets, 1988); TrendSpider Donchian — https://trendspider.com/learning-center/donchian-channel-trading-strategies/
- **카테고리 태그**: Stage A/B/C/D
- **버킷**: position (수주~수개월)
- **한국 시장 적용 사례**: 코스피 대형주 장기 추세 분석에 직접 적용 가능. 30주선 = 150일선으로 근사 가능
- **PIT-safe 가능성**: 가능 — 주봉/일봉 과거 데이터 기준
- **필요 데이터**: 일봉 종가 150일+
- **예상 difficulty**: 중 (★★☆)

---

### 13. VWAP 박스 기준선 매매 (VWAP Range Signal)

- **정의**: 장중 VWAP을 박스권 중심선으로 활용 — VWAP 상단 매도, 하단 매수 (당일 평균회귀)
  - 매수: `close > VWAP` AND `close < VWAP * 1.005` (VWAP 직상 진입)
  - 매도: `close > VWAP * 1.01` (VWAP 1% 상단 도달 시 청산)
  - 손절: `close < VWAP * 0.995` (VWAP 0.5% 하향 이탈)
  - 확장: Anchored VWAP (스윙 고/저점 기준 고정) → 중기 박스 중심선으로 활용
- **출처**: 책 3 (Andrew Aziz) 전략6 VWAP; Anchored VWAP — https://trendspider.com/learning-center/anchored-vwap-trading-strategies/; ChartMini VWAP — https://chartmini.com/blog/vwap-trading-strategy
- **카테고리 태그**: Stage B (장중 mean reversion)
- **버킷**: swing/intraday
- **한국 시장 적용 사례**: 한국 HTS에서 VWAP 지표 직접 계산 가능. 기관의 VWAP 집행 알고리즘이 동일 가격대를 지지선으로 만들기 때문에 특히 대형주에서 유효
- **PIT-safe 가능성**: 가능 (장중 실시간 계산) — EOD 백테스트 시 분봉 OHLCV 필요
- **필요 데이터**: 분봉 OHLCV (VWAP 실시간 계산), 또는 일봉 기준 근사치
- **예상 difficulty**: 상 (★★★) — 분봉 데이터 필요

---

### 14. 시간외 단일가 박스 갭 매매 (After-Hours Gap from Box)

- **정의**: 장 마감(15:30) 이후 시간외 단일가(16:00~18:00)에서 박스권 상단 근접 종목 갭 형성 시 익일 연속 상승 추구
  - 조건:
    1. 정규장 종가 >= 박스 상단 * 0.97 (박스 상단 3% 이내)
    2. 시간외 단일가 거래가 > 정규장 종가 * 1.01 (1% 이상 갭업)
    3. 시간외 거래량 > 시간외 평균 거래량 * 1.5
  - 진입: 익일 시초가 (갭 유지 확인 후)
  - 손절: 시간외 단일가 거래가 이하
- **출처**: 책 1 (강창권) "시간외 단일가" 전략; NXT 제도 안내 — https://open.shinhansec.com/mobilealpha/html/CS/NXTPolicyGuide.html
- **카테고리 태그**: Stage C (돌파 직전)
- **버킷**: swing (1~2일)
- **한국 시장 적용 사례**: 한국 전용 — KRX 시간외 단일가(16:00~18:00). NXT 적용 종목은 시간외 단일가 대상 제외되므로 NXT 비해당 종목에만 적용. KIS API FHKST07010300 시간외 단일가 조회 가능
- **PIT-safe 가능성**: 가능 — 시간외 거래가는 익일 시초가 이전에 확정
- **필요 데이터**: 시간외 단일가 데이터 (KIS API), 일봉 박스 정의
- **예상 difficulty**: 상 (★★★) — KIS API 시간외 데이터 수집 파이프라인 필요

---

### 15. NXT 야간 갭 박스 매매 (NXT After-Market Gap Signal)

- **정의**: 넥스트레이드(NXT, 2025년 3월 개장) 야간 시장(15:30~20:00)에서 박스권 돌파 형성 시 익일 정규장 연속 확인
  - NXT 거래시간: 08:00~20:00 (프리마켓 08:00~09:00, 메인 09:00~15:30, 애프터 15:30~20:00)
  - 신호 조건:
    1. NXT 애프터마켓 종가 > 정규장 박스 상단 * 1.005
    2. NXT 거래량이 의미 있는 수준 (최소 1,000주 이상)
  - 진입: 익일 정규장 시초가 (갭 유지 확인)
  - 손절: 정규장 박스 상단 이탈 하향
- **출처**: 책 1 (강창권) "NXT(넥스트레이드) 전략"; NXT 제도 — https://www.nextrade.co.kr/transactionSys/content.do; 매거진한경 NXT 개장 기사 — https://magazine.hankyung.com/money/article/202503132444c
- **카테고리 태그**: Stage C (야간 선행 돌파)
- **버킷**: swing (1~2일)
- **한국 시장 적용 사례**: 한국 전용 신규 시장 (2025년 3월 개장). 현재 800종목 이하 제한적 적용. 유동성이 얇아 스프레드 확대 주의
- **PIT-safe 가능성**: 가능 — NXT 종가는 익일 정규장 시초가 이전에 확정
- **필요 데이터**: NXT 야간 시세 데이터 (KIS API 또는 HTS 별도)
- **예상 difficulty**: 최상 (★★★★) — NXT 데이터 수집 인프라 미비

---

### 16. 호가창 매수벽/매도벽 박스 경계 (Order Book Wall Box)

- **정의**: 매수/매도 잔량이 집중된 가격대를 박스 상한/하한으로 정의
  - 매도벽: 특정 가격에 매도 잔량 집중 (10호가 전체 평균의 3배 이상) → 박스 상단
  - 매수벽: 특정 가격에 매수 잔량 집중 (10호가 전체 평균의 3배 이상) → 박스 하단
  - 매수 신호: 주가가 매수벽 가격대 도달 + 매수벽 붕괴 없이 반등
  - 매도 신호: 주가가 매도벽 가격대 도달 + 매도벽 소화 안 됨
  - 페이크 벽 탐지: 대량 허수 호가(올렸다 취소) — 책 2 (이시이) Rule 82~84
- **출처**: 책 2 (이시이 카츠토시) Rule 79~84 "호가창 신호"; Order Book Wall — https://bookmap.com/blog/inside-the-market-order-books-and-what-youre-missing-out-on/; EBC Order Book — https://www.ebc.com/forex/order-book-in-trading-meaning-types-and-how-it-works
- **카테고리 태그**: Stage B (장중 박스 감지)
- **버킷**: intraday/swing
- **한국 시장 적용 사례**: HTS Level 2 호가창 직접 활용. 기관의 대량 매도벽이 일정 기간 존재하다 사라지면 돌파 신호. KIS API FHKST01010200 (실시간 호가)로 구현 가능
- **PIT-safe 가능성**: 부분 — 실시간 호가는 PIT에 해당하지 않으나 스냅샷 저장 후 사용 시 PIT-safe
- **필요 데이터**: 실시간 호가 데이터 (KIS WebSocket 또는 스냅샷), 분봉 가격
- **예상 difficulty**: 최상 (★★★★) — 실시간 호가 수집 인프라 필요

---

### 17. 오전장/오후장 박스 비교 (AM/PM Session Box Shift)

- **정의**: 오전(09:00~11:30)과 오후(13:00~15:30) 박스를 별도로 정의하고 세션 전환 시 방향 편향 확인
  - 오전 박스: 오전 세션 고가/저가 (통상 변동성 높음)
  - 오후 박스: 오후 세션 고가/저가 (통상 변동성 낮음)
  - 매수 신호: 오후 박스 저점 < 오전 박스 저점 AND 오후 종가 > 오전 박스 저점 (오전 박스 하단 지지 확인)
  - 매도 신호: 오후 박스 고점 > 오전 박스 고점 AND 급감하는 거래량 (모멘텀 소진)
- **출처**: 책 2 (이시이 카츠토시) Rule 44~50 "아침 전략 · 최적 진입 시간창"; 책 1 (강창권) "CK480 점심 단타"
- **카테고리 태그**: Stage B (장중 세션 전환)
- **버킷**: intraday
- **한국 시장 적용 사례**: 한국 점심시간(11:30~13:00) 거래량 급감 후 오후 재개 시 방향성 편향. 직장인 단타에서 13:00 이후 방향 확인 후 매수하는 기법과 일치
- **PIT-safe 가능성**: 가능 — 분봉 기준 세션 내 계산
- **필요 데이터**: 분봉 OHLCV (09:00~15:30)
- **예상 difficulty**: 상 (★★★) — 분봉 데이터 및 세션 분리 로직 필요

---

### 18. 강세 깃발형 박스 돌파 (Bull Flag Box Breakout)

- **정의**: 급등 후 좁은 횡보 채널(깃발=작은 박스) 형성 후 돌파 — 연속 상승의 2차 진입점
  - 깃발 조건:
    1. 선행 급등: `5일 전 대비 +8% 이상` 상승 (깃대)
    2. 횡보 채널: 이후 2~5일 `(high_max - low_min) / close <= 5%` (작은 박스=깃발)
    3. 깃발 거래량: 급등 구간 대비 50% 이하로 감소
  - 진입: 깃발 상단 돌파 + 거래량 급증
  - 목표: 깃대폭 * 1.0 추가 상승
  - 손절: 깃발 하단 이탈
- **출처**: 책 3 (Andrew Aziz) 전략2 "강세 깃발형 모멘텀"; Bear Bull Traders — https://traderlion.com/trading-books/how-to-day-trade-for-a-living/
- **카테고리 태그**: Stage C (연속 추세)
- **버킷**: swing (1~5일)
- **한국 시장 적용 사례**: 테마주 1차 급등 후 형성되는 눌림목 패턴과 일치. 재료 유효기간(2일 룰, 책 2) 감안하여 깃발 형성 기간이 3일 초과 시 진입 보류
- **PIT-safe 가능성**: 가능 — 확정 일봉 기준
- **필요 데이터**: 일봉 OHLCV, 거래량 MA
- **예상 difficulty**: 중 (★★☆)

---

### 19. RSI 과매도 박스 하단 반등 (RSI Oversold at Box Low)

- **정의**: 박스 하단 도달 + RSI 과매도(<=30) 동시 조건에서 mean reversion 진입
  - 조건:
    1. `close <= box_low * 1.02` (박스 하단 2% 이내)
    2. `RSI14 <= 30` (과매도)
    3. `RSI14 > RSI14_prev` (RSI 반등 시작)
  - 진입: 조건 충족 다음 봉 시가
  - 목표: 박스 중심선 `box_mid = (box_high + box_low) / 2` 1차, 박스 상단 2차
  - 손절: `box_low * 0.97` (박스 하단 3% 이탈)
- **출처**: RSI + 박스 조합 — https://alphasquare.co.kr/home/insight/posts/2abbd8ab-cc12-448e-9b5e-2db04a939b1b; 책 3 (Andrew Aziz) 전략3~4 "반전 매매 + 과매도 구간"; QuantifiedStrategies ATR — https://www.quantifiedstrategies.com/average-true-range-trading-strategy/
- **카테고리 태그**: Stage B (박스 내 반등)
- **버킷**: swing (1~3일)
- **한국 시장 적용 사례**: 코스닥 중소형주에서 외국인 매도 압력으로 박스 하단 RSI 30 이하 진입 후 기관 순매수 유입 패턴 빈번
- **PIT-safe 가능성**: 가능 — RSI14 계산은 당일 종가 기준
- **필요 데이터**: 일봉 종가 14일+, 박스 정의
- **예상 difficulty**: 중 (★★☆)

---

### 20. 박스 압축 후 기관/외국인 수급 돌파 (Volume Breadth Confirmed Breakout)

- **정의**: 박스 돌파 + 기관·외국인 순매수 동반 조건 — 수급이 돌파의 진짜 동력임을 확인
  - 조건:
    1. `close > box_high` (박스 상단 돌파)
    2. `institution_net_buy > 0` AND `foreign_net_buy > 0` (기관+외국인 동반 순매수)
    3. `volume > volume_ma20 * 2.0` (거래량 2배 이상)
  - 진입: 당일 조건 모두 충족 시 익일 시가
  - 손절: 돌파봉 저가 또는 `box_high * 0.98`
  - 목표: 박스폭 * 1.5 추가 상승
- **출처**: 책 1 (강창권) "기관·외국인 수급 분석" + "프로그램 매수 공략"; KRX Data Marketplace — https://data.krx.co.kr/
- **카테고리 태그**: Stage C (진짜 돌파 확인)
- **버킷**: swing/mid (3~10일)
- **한국 시장 적용 사례**: 한국 특화 — KIS API를 통해 기관/외국인 당일 순매수 데이터 수집 가능 (FHKST01010900). 기관+외국인 쌍방 순매수를 동시 충족하는 돌파는 이후 추세 지속성이 높음
- **PIT-safe 가능성**: 가능 — EOD 수급 데이터는 당일 장마감 후 확정
- **필요 데이터**: 일봉 OHLCV, 기관/외국인 일별 순매수 데이터 (KIS API)
- **예상 difficulty**: 상 (★★★) — 수급 데이터 수집 파이프라인 추가 필요

---

## 종합 평가

### 즉시 코드화 우선순위 Top 5

| 순위 | 컨셉 | 이유 |
|------|------|------|
| 1 | **4. 박스 하단 매수/상단 매도 (Mean Reversion Box)** | 조건 단순, 일봉 OHLCV만 필요, difficulty 낮음, 즉시 백테스트 가능 |
| 2 | **11. 박스폭 기반 목표가 계산** | 다른 전략의 청산 로직으로 즉시 재사용 가능. 코드 1줄 수준 |
| 3 | **1. 횡보 후 박스 돌파 (Box Breakout with Volume)** | 표준 Donchian 돌파. 기존 volume_breakout 전략에 박스 필터만 추가 |
| 4 | **9. 페이크아웃 역추세 매매** | 기존 박스 돌파 신호의 필터 반전으로 구현 가능 |
| 5 | **19. RSI 과매도 박스 하단 반등** | 기존 RSI 지표 + 박스 조건 결합. bb_reversion 전략과 유사 구조 |

### 박스 정의 파라미터 표준화 제안

```python
# 권장 박스 정의 표준 파라미터 (한국 시장 적용)
BOX_PARAMS = {
    "period": 20,            # 박스 관측 기간 (일봉 기준, Donchian 기본값)
    "max_width_pct": 10.0,   # 박스 최대 폭 (%) — 10% 초과 시 박스 아님
    "min_touch": 2,          # 상단/하단 각 최소 터치 횟수
    "atr_period": 14,        # ATR 계산 기간
    "atr_width_max": 3.0,    # 박스폭 <= ATR*3 조건 (ATR 기반 박스 인정)
    "noise_tolerance": 0.01, # 박스 경계 노이즈 허용 ±1%
}
```

### PIT 위험 컨셉

| 컨셉 | PIT 위험 사유 | 해결 방법 |
|------|-------------|---------|
| **16. 호가창 매수벽/매도벽** | 실시간 호가는 과거 재현 불가 | 호가 스냅샷 별도 저장 필요 |
| **17. 오전/오후 박스** | 분봉 실시간 세션 분리 필요 | minute_candles 테이블 활용 (robotrader.minute_candles 존재) |
| **15. NXT 야간 갭** | NXT 데이터 수집 인프라 미비 | NXT API 연동 전까지 보류 |
| **13. VWAP 박스** | 분봉 실시간 VWAP 계산 | minute_candles로 배치 계산 가능 (부분 PIT-safe) |

---

## 참고 자료

### 책 (필독)
- [주식투자 단기 트레이딩의 정석 — 강창권 (길벗, 2025)](https://product.kyobobook.co.kr/detail/S000217567051)
- [주식 데이트레이딩의 신 100법칙 — 이시이 카츠토시 (지상사, 2021)](https://product.kyobobook.co.kr/detail/S000001014275)
- [도박꾼이 아니라 트레이더가 되어라 — Andrew Aziz (책세상, 2022)](https://product.kyobobook.co.kr/detail/S000001777389)

### Wyckoff 원전 / 해설
- [Wyckoff Analytics — 와이코프 방법론 공식](https://www.wyckoffanalytics.com/wyckoff-method/)
- [Alchemy Markets — Wyckoff Accumulation Guide](https://alchemymarkets.com/education/guides/wyckoff-accumulation/)
- [Springs and Upthrusts 해설](https://www.financial-spread-betting.com/trading/wyckoff-spings-upthrusts.html)
- [Capital.com — Wyckoff Method Comprehensive Guide](https://capital.com/en-int/learn/technical-analysis/the-wyckoff-method)

### Donchian / ATR / VCP
- [LuxAlgo — Donchian Channel Breakout Strategy](https://www.luxalgo.com/blog/donchian-channels-breakout-and-trend-following-strategy/)
- [QuantInsti — Donchian Channel Strategy](https://blog.quantinsti.com/donchian-channel-strategy/)
- [TraderLion — VCP Volatility Contraction Pattern](https://traderlion.com/technical-analysis/volatility-contraction-pattern/)
- [TradingSim — VCP Pattern Guide 2026](https://www.tradingsim.com/blog/volatility-contraction-pattern)
- [QuantifiedStrategies — ATR Trading Strategy](https://www.quantifiedstrategies.com/average-true-range-trading-strategy/)
- [Volatility Box — ATR Comprehensive Guide](https://volatilitybox.com/research/atr-average-true-range/)

### 페이크아웃 / 호가창
- [PriceAction.com — False Breakout Trading](https://priceaction.com/price-action-university/strategies/false-break-out/)
- [Equiti — How to Identify and Trade Fakeouts](https://www.equiti.com/sc-en/news/trading-ideas/how-to-identify-and-trade-fakeouts-a-complete-traders-guide/)
- [Bookmap — Breakout or Fakeout: 3-Point Checklist](https://bookmap.com/blog/breakout-or-fakeout-the-3-point-checklist-for-confirmation/)

### VWAP / Anchored VWAP
- [TrendSpider — Anchored VWAP Strategies](https://trendspider.com/learning-center/anchored-vwap-trading-strategies/)
- [ChartMini — VWAP Institutional Trading Guide](https://chartmini.com/blog/vwap-trading-strategy)

### 한국 시장 자료
- [AlphaSquare — 볼린저밴드 원리와 박스권 활용](https://alphasquare.co.kr/home/insight/posts/2abbd8ab-cc12-448e-9b5e-2db04a939b1b)
- [박스권 매매 + 돌파 매매 — Teacherville](https://ssam.teacherville.co.kr/liforu/contents/20272.edu)
- [한국거래소 데이터 마켓플레이스](https://data.krx.co.kr/)
- [NXT 넥스트레이드 제도 안내](https://www.nextrade.co.kr/transactionSys/content.do)
- [매거진한경 — NXT 대체거래소 개장 (2025.03)](https://magazine.hankyung.com/money/article/202503132444c)
- [신한투자증권 — NXT 가이드](https://open.shinhansec.com/mobilealpha/html/CS/NXTPolicyGuide.html)