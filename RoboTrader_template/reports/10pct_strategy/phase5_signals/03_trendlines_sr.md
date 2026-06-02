# 추세선/지지저항 시그널 카탈로그 (Phase 5 확장용)

> 작성일: 2026-05-25 | 조사자: document-specialist (Claude)
> 목적: Phase 5 시그널 패밀리 37 → 100+ 확장 — 추세선/지지저항 카테고리
> 수집 컨셉: **26개** (책 6개 + 외부 20개)

---

## 형식 설명

| 필드 | 설명 |
|---|---|
| **컨셉명** | 시그널 이름 (영문/한국어) |
| **정의/수식** | 계산 방법 및 조건 |
| **출처** | 1차 참고 문헌 및 URL |
| **Stage** | Entry / Exit / Filter (복수 가능) |
| **버킷** | 추세추종 / 평균회귀 / 돌파 / 모멘텀 |
| **한국 적용** | 직접 적용 / 제한적 / 한국 전용 |
| **PIT 안전도** | 안전 / 주의 / 위험 (Look-Ahead Bias 위험도) |
| **데이터 요건** | 필요 데이터 |
| **난이도** | 하 / 중 / 상 |

---

## A. 이동평균선 (Moving Average) 계열 — 9개

### A-01. SMA 정배열 (Bullish MA Alignment)
- **정의**: 단기 SMA가 장기 SMA 위에 순서대로 정렬 (정배열). 역순이면 역배열(Bearish).
- **수식**: `is_bullish_aligned = SMA5 > SMA20 > SMA60 > SMA120`
- **출처**: 책1 강창권 *단기 트레이딩의 정석* 2장 | https://product.kyobobook.co.kr/detail/S000217567051
- **Stage**: Filter
- **버킷**: 추세추종
- **한국 적용**: 직접 적용 — 국내 HTS 기본 지표. 한국 단타에서 "정배열 확인"은 표준 필터.
- **PIT 안전도**: 안전 — SMA는 현재 바 종가까지만 사용.
- **데이터 요건**: 일봉 종가 120일+
- **난이도**: 하
- **종합 평가**: 즉시 코드화 가능. 단독 사용보다 다른 시그널의 방향 필터로 사용. 정배열이면 BUY만 허용, 역배열이면 SELL/HOLD.

---

### A-02. 골든크로스 / 데드크로스 (Golden Cross / Dead Cross)
- **정의**: 단기 MA가 장기 MA를 상향 돌파(골든크로스) 또는 하향 돌파(데드크로스).
- **수식**:
  `golden_cross = (SMA5[-1] < SMA20[-1]) AND (SMA5[0] > SMA20[0])`
  `dead_cross   = (SMA5[-1] > SMA20[-1]) AND (SMA5[0] < SMA20[0])`
  중장기: SMA50×SMA200 조합도 표준
- **출처**: John Murphy *Technical Analysis of the Financial Markets* Ch.4 (McGraw-Hill, 1999); 책1 강창권 2장
- **Stage**: Entry
- **버킷**: 추세추종
- **한국 적용**: 직접 적용 — 5일/20일 크로스가 국내 단기 트레이딩 표준.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 200일+ (SMA200 기준)
- **난이도**: 하
- **종합 평가**: SampleStrategy 이미 구현. 추가로 SMA50×SMA200 중장기 크로스 버전 고려.

---

### A-03. EMA 정배열 눌림목 (EMA Pullback to Alignment)
- **정의**: EMA 단기>장기 정배열 상태에서 주가가 단기 EMA로 눌렸다가 반등 시 매수.
- **수식**:
  `bullish_trend = EMA9 > EMA21`
  `pullback = close[-1] <= EMA9[-1] AND close[0] > EMA9[0]`
  `entry = bullish_trend AND pullback`
- **출처**: 책3 Andrew Aziz *도박꾼이 아니라 트레이더가 되어라* 전략5 | https://product.kyobobook.co.kr/detail/S000001777389
- **Stage**: Entry
- **버킷**: 추세추종 + 평균회귀
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉/분봉 종가 21일+
- **난이도**: 하
- **종합 평가**: 즉시 코드화 가능. 기존 MomentumStrategy와 조합 시 눌림목 타이밍 정밀도 향상.

---

### A-04. 이격도 (Disparity Ratio)
- **정의**: 현재가와 이동평균선 사이의 이격 비율. 이격 과대 시 평균회귀 압력.
- **수식**:
  `disparity = (close / SMA20 - 1) * 100`
  매수 조건: `disparity < -5%`  매도 조건: `disparity > +10%`
- **출처**: 강창권 *단기 트레이딩의 정석* 2장; 한국 기술적 분석 교재 표준 지표
- **Stage**: Entry (역추세) / Filter
- **버킷**: 평균회귀
- **한국 적용**: 직접 적용 — 국내 HTS 기본 제공.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 20일
- **난이도**: 하
- **종합 평가**: MeanReversionStrategy 진입 조건으로 즉시 활용 가능. BBReversionStrategy와 상호 보완.

---

### A-05. HMA 전환점 (Hull Moving Average Turning Point)
- **정의**: HMA는 WMA로 lag을 대폭 감소. 방향 전환 시점이 신호.
- **수식**:
  `WMA_half = WMA(n/2, price); WMA_full = WMA(n, price)`
  `raw_HMA  = 2 * WMA_half - WMA_full`
  `HMA      = WMA(sqrt(n), raw_HMA)`
  `buy_signal  = HMA[0] > HMA[-1] AND HMA[-1] <= HMA[-2]`
  `sell_signal = HMA[0] < HMA[-1] AND HMA[-1] >= HMA[-2]`
- **출처**: Alan Hull (2005) hullindicators.com/hma; StockCharts HMA | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/hull-moving-average-hma
- **Stage**: Entry / Exit
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 n일 (권장 n=20)
- **난이도**: 중 (WMA 직접 구현 필요 — ta-lib 미지원)
- **종합 평가**: EMA/SMA 대비 지연이 적어 단타에 유리. pandas로 WMA 직접 구현 필요.

---

### A-06. DEMA 크로스 (Double EMA Crossover)
- **정의**: DEMA = 2×EMA - EMA(EMA). EMA보다 훨씬 빠른 반응.
- **수식**:
  `EMA1 = EMA(n, price); EMA2 = EMA(n, EMA1); DEMA = 2*EMA1 - EMA2`
  `buy_signal  = DEMA20[0] > DEMA50[0] AND DEMA20[-1] <= DEMA50[-1]`
- **출처**: Patrick Mulloy (1994) *Smoothing Data with Faster Moving Averages* — TASC Magazine; StockCharts DEMA | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/double-exponential-moving-average-dema
- **Stage**: Entry
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 50일+
- **난이도**: 중
- **종합 평가**: 표준 EMA 크로스보다 신호 빠름. 노이즈 증가 위험. 필터와 조합 권장.

---

### A-07. TEMA 크로스 (Triple EMA Crossover)
- **정의**: TEMA = 3×EMA1 - 3×EMA2 + EMA3. DEMA보다 더 빠른 반응.
- **수식**:
  `EMA1=EMA(n,price); EMA2=EMA(n,EMA1); EMA3=EMA(n,EMA2)`
  `TEMA = 3*EMA1 - 3*EMA2 + EMA3`
  `buy_signal = TEMA20[0] > TEMA50[0] AND TEMA20[-1] <= TEMA50[-1]`
- **출처**: Patrick Mulloy (1994) — TASC Magazine; StockCharts TEMA | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/triple-exponential-moving-average-tema
- **Stage**: Entry
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 50일+
- **난이도**: 중
- **종합 평가**: DEMA보다 더 빠르지만 노이즈에 더 민감. 스캘핑/단타 전용 추천.

---

### A-08. CK480 분봉선 저항/지지 (Korea-Specific)
- **정의**: 240분봉·480분봉 이동평균선을 장중 중요 저항/지지선으로 활용. 직장인 점심시간대(11:30~13:00) 진입 전략.
- **수식**:
  `MA_240min = SMA(240, 1분봉_close)`
  `MA_480min = SMA(480, 1분봉_close)`
  저항: 주가가 MA_480min 아래에서 접근 → 매도 준비
  지지: 주가가 MA_240min 터치 후 반등 → 매수
- **출처**: 책1 강창권 *단기 트레이딩의 정석* 6장 | https://product.kyobobook.co.kr/detail/S000217567051
- **Stage**: Entry / Exit
- **버킷**: 지지저항
- **한국 적용**: 한국 전용 — 분봉 기반, 장 시간(09:00~15:30) 특화
- **PIT 안전도**: 안전
- **데이터 요건**: 1분봉 데이터 480개 (minute_candles 테이블)
- **난이도**: 중 (1분봉 인프라 필요)
- **종합 평가**: 한국 특화 고유 컨셉. minute_candles(1,347종목) 활용 시 즉시 적용 가능.

---

### A-09. 다중 MA 이격 수렴 (MA Compression / Fan Pattern)
- **정의**: 5·20·60·120일선이 한 점으로 수렴(에너지 축적) 후 확산 시 강한 방향성 시그널.
- **수식**:
  `spread = max(SMA5,SMA20,SMA60,SMA120) - min(SMA5,SMA20,SMA60,SMA120)`
  `spread_pct = spread / SMA20 * 100`
  `compression = spread_pct < 2%`
  `expansion_buy = compression[-1] AND SMA5[0] > SMA20[0] AND SMA5[-1] <= SMA20[-1]`
- **출처**: John Murphy *Technical Analysis of the Financial Markets* Ch.4 (MA Fan Pattern); 강창권 2장
- **Stage**: Entry (돌파 확인 후)
- **버킷**: 돌파
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 120일+
- **난이도**: 중
- **종합 평가**: BB Squeeze와 유사한 에너지 축적 개념. 신호 빈도 낮고 강도 높음.


---

## B. 추세선/채널 계열 — 4개

### B-01. 추세선 돌파 (Trendline Breakout)
- **정의**: 스윙 저점 연결 상승 추세선 / 스윙 고점 연결 하강 추세선. 가격이 추세선 이탈 시 신호.
- **수식**:
  PIT-safe 구현:
  `confirmed_swing_high[i] = (바[i+N] 완성 후) high[i] == max(high[i-N:i+N+1])`
  즉, swing_high[i]는 i+N 바가 완성된 시점(=현재 t=i+N)에서만 확정.
  `slope = (sw_low2.price - sw_low1.price) / (sw_low2.idx - sw_low1.idx)`
  `trendline_val = sw_low1.price + slope * (t - sw_low1.idx)`
  `breakout_up   = close[t] > trendline_val AND close[t-1] <= prev_trendline`
- **출처**: John Murphy *Technical Analysis of the Financial Markets* Ch.4; LuxAlgo Trendlines | https://www.luxalgo.com/blog/how-to-draw-trendlines-a-simple-guide-2/
- **Stage**: Entry / Exit
- **버킷**: 돌파
- **한국 적용**: 직접 적용
- **PIT 안전도**: **주의** — 스윙 포인트 확정에 N 바 지연 필수. 미구현 시 Look-Ahead 발생.
- **데이터 요건**: 일봉 고가·저가 60일+ (스윙 포인트 2개 이상)
- **난이도**: 상
- **종합 평가**: 개념 강력하나 자동화 구현 까다로움. PIT 함정 가장 위험한 시그널. `lookback_right` 지연 처리 강제.

---

### B-02. 추세선 채널 (Trend Channel — Parallel Lines)
- **정의**: 상승 추세선(지지) + 평행 상단선(저항). 채널 하단 터치=매수, 상단 터치=매도, 이탈=추세 전환.
- **수식**:
  `support_line(t) = sw_low1.price + slope_s*(t-sw_low1.idx)`
  `channel_width = max_swing_high - support_line(at max_swing_high.idx)`
  `resistance_line(t) = support_line(t) + channel_width`
  `buy_at_support = close <= support_line(t)*1.005`
  `channel_break_up = close > resistance_line(t)  # 강한 매수`
- **출처**: John Murphy *Technical Analysis* Ch.4 (Channels); 책1 강창권 6장
- **Stage**: Entry / Exit / Filter
- **버킷**: 추세추종 + 평균회귀
- **한국 적용**: 직접 적용
- **PIT 안전도**: **주의** — B-01과 동일한 스윙 포인트 확정 지연 문제
- **데이터 요건**: 일봉 고가·저가 60일+
- **난이도**: 상
- **종합 평가**: 채널 내부 평균회귀 + 이탈 시 추세추종으로 이중 활용 가능.

---

### B-03. 도날치안 채널 돌파 (Donchian Channel Breakout)
- **정의**: N일 최고가(상단)·최저가(하단) 채널. 상단 돌파=매수, 하단 이탈=매도. 터틀 트레이딩 핵심.
- **수식**:
  `DC_upper = max(high, N);  DC_lower = min(low, N)`
  `entry_long  = close > DC_upper[-1]  # 직전 바 상단 돌파`
  `exit_long   = close < min(low, 10)[-1]  # 10일 채널 하단 이탈`
  표준: N=20 진입, N=10 청산
- **출처**: Richard Dennis & William Eckhardt (1983) 터틀 트레이딩; TradingView Donchian | https://www.tradingview.com/scripts/donchianchannels/; Altrady | https://www.altrady.com/blog/crypto-trading-strategies/donchian-channel-strategy
- **Stage**: Entry / Exit
- **버킷**: 돌파 + 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전 — max(high[-N:-1]) 형태로 현재 바 제외 가능
- **데이터 요건**: 일봉 고가·저가 N일 (표준: 20일)
- **난이도**: 하
- **종합 평가**: **즉시 코드화 Top 3.** 수식 단순, PIT 위험 없음. VolumeBreakoutStrategy와 결합 시 거래량 확인으로 신뢰도 향상.

---

### B-04. 켈트너 채널 (Keltner Channel)
- **정의**: EMA20 ± ATR×2 변동성 채널. 채널 이탈이 추세 강도 신호. BB와 유사하나 ATR 사용 → 덜 노이즈.
- **수식**:
  `KC_mid   = EMA(20, close)`
  `KC_upper = KC_mid + 2*ATR(10);  KC_lower = KC_mid - 2*ATR(10)`
  `buy_breakout  = close > KC_upper`
  `squeeze_on = BB_upper < KC_upper AND BB_lower > KC_lower  # BB-KC Squeeze`
- **출처**: Chester Keltner (1960) *How to Make Money in Commodities*; TrendSpider BB/KC Squeeze | https://trendspider.com/learning-center/bb-kc-squeeze-a-powerful-indicator-for-trading-range-breakouts/
- **Stage**: Entry / Filter
- **버킷**: 추세추종 + 돌파
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가·고가·저가 20일+
- **난이도**: 중
- **종합 평가**: BB와 함께 BB-KC Squeeze 조합 시 강력. BBReversionStrategy와 연계 추천.


---

## C. 피보나치 계열 — 3개

### C-01. 피보나치 되돌림 지지/저항 (Fibonacci Retracement S/R)
- **정의**: 스윙 고점·저점 간 거리에 피보나치 비율 적용. 되돌림 구간 지지/저항 예측.
- **수식**:
  `diff = swing_high - swing_low`
  `level_236 = swing_high - 0.236*diff`
  `level_382 = swing_high - 0.382*diff  # 핵심 지지`
  `level_618 = swing_high - 0.618*diff  # 황금비율 — 가장 강력`
  `level_786 = swing_high - 0.786*diff`
  `near_618 = abs(close - level_618)/level_618 < 0.005  # ±0.5% 이내`
  `buy_at_fib = near_618 AND reversal_candle  # 반전 캔들 확인 필수`
- **출처**: John Murphy *Technical Analysis* Ch.13; StockCharts Fibonacci | https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-annotation-tools/fibonacci-retracements; Britannica Money | https://www.britannica.com/money/fibonacci-trading-strategies
- **Stage**: Entry / Filter
- **버킷**: 평균회귀
- **한국 적용**: 직접 적용
- **PIT 안전도**: **주의** — 스윙 고점·저점 확정에 N 바 지연 필요. 동적 업데이트 시 repainting 위험. 고정 swing 사용 권장.
- **데이터 요건**: 일봉 고가·저가 60일+ (스윙 탐지용)
- **난이도**: 중
- **종합 평가**: 단독 진입 신호 부적합. 반드시 캔들 패턴·거래량 확인 보조. 38.2%~61.8% 구간이 핵심 Alert Zone.

---

### C-02. 피보나치 확장 목표가 (Fibonacci Extension Target)
- **정의**: 추세 지속 시 다음 저항 목표가 예측. 익절 목표 설정에 사용.
- **수식**:
  A(저점)→B(고점)→C(되돌림) 후 D(확장) 계산:
  `D_1272 = C + 1.272*(B-A)`
  `D_1618 = C + 1.618*(B-A)  # 황금비율 확장 — 주요 익절 목표`
  `D_2618 = C + 2.618*(B-A)`
- **출처**: Elliott Wave Forecast | https://elliottwave-forecast.com/trading/fibonacci-retracement-and-fibonacci-extension/; John Murphy *Technical Analysis* Ch.13
- **Stage**: Exit (목표가 설정)
- **버킷**: 모멘텀
- **한국 적용**: 직접 적용 — Signal.target_price 필드와 직접 연결 가능
- **PIT 안전도**: **주의** — C 지점(되돌림 완료) 확인 후에만 계산. 미확정 C 사용 금지.
- **데이터 요건**: 스윙 A·B·C 포인트 (일봉)
- **난이도**: 중
- **종합 평가**: Signal.target_price에 1.618 확장값 설정으로 활용. ABCD 패턴(책3)과 직접 연계.

---

### C-03. 피봇 포인트 — Floor/Camarilla/DeMark (Pivot Points)
- **정의**: 전일 고·저·종가로 당일 지지/저항 레벨 수학적 계산. 장 시작 전 PIT-safe 사전 계산 가능.
- **수식**:
  Floor Pivot:
  `PP = (H_prev+L_prev+C_prev)/3`
  `R1=2*PP-L_prev; S1=2*PP-H_prev`
  `R2=PP+(H_prev-L_prev); S2=PP-(H_prev-L_prev)`

  Camarilla (단기 매매 최적):
  `R1_cam = C_prev + (H_prev-L_prev)*1.1/12`
  `S1_cam = C_prev - (H_prev-L_prev)*1.1/12`
  `R3_cam = C_prev + (H_prev-L_prev)*1.1/4  # 주요 반전 구간`

  Fibonacci Pivot:
  `R1_fib = PP + 0.382*(H_prev-L_prev)`
  `R2_fib = PP + 0.618*(H_prev-L_prev)`

  DeMark:
  `if C_prev>O_prev: X=2*H_prev+L_prev+C_prev`
  `elif C_prev<O_prev: X=H_prev+2*L_prev+C_prev`
  `else: X=H_prev+L_prev+2*C_prev`
  `PP_demark=X/4; R1=X/2-L_prev; S1=X/2-H_prev`
- **출처**: market-bulls.com | https://market-bulls.com/pivot-point-calculator/; ForexTrainingGroup | https://forextraininggroup.com/comparing-different-types-pivot-points/; TradingPedia | https://www.tradingpedia.com/forex-trading-indicators/fibonacci-pivot-points-demark-calculation/
- **Stage**: Filter / Entry (레벨 근접 시) / Exit (목표가)
- **버킷**: 지지저항
- **한국 적용**: 직접 적용 — 전일 OHLC 데이터로 당일 장 시작 전 일괄 계산
- **PIT 안전도**: 안전 — 전일 데이터만 사용
- **데이터 요건**: 일봉 고가·저가·종가·시가 (전일)
- **난이도**: 하
- **종합 평가**: **즉시 코드화 Top 3.** 장 시작 전 당일 레벨 계산 → 매일 업데이트. 스크리너에 S2/R2 레벨 근접 필터로 즉시 활용 가능.


---

## D. 일목균형표 계열 — 5개

### D-01. 전환선/기준선 교차 (Tenkan-Kijun Cross)
- **정의**: 전환선(9기간 중간값)이 기준선(26기간 중간값)을 상향 돌파=매수(호전), 하향=매도(역호전).
- **수식**:
  `tenkan = (highest_high(9) + lowest_low(9)) / 2`
  `kijun  = (highest_high(26) + lowest_low(26)) / 2`
  `bullish_cross = tenkan[0]>kijun[0] AND tenkan[-1]<=kijun[-1]`
  구름대 위: 강한 호전 / 구름 내: 중립 / 구름 아래: 약한 호전
- **출처**: 호소다 고이치(細田悟一) 일목균형표 원전 (1968); Wikipedia Ichimoku | https://en.wikipedia.org/wiki/Ichimoku_Kink%C5%8D_Hy%C5%8D; OANDA | https://www.oanda.com/us-en/trade-tap-blog/analysis/technical/ichimoku-cloud-trading-guide-key-strategies/
- **Stage**: Entry
- **버킷**: 추세추종
- **한국 적용**: 직접 적용 — 한국 HTS 기본 제공
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 고가·저가 26일+
- **난이도**: 중
- **종합 평가**: 일목 5대 시그널 중 가장 반응 빠름. 단독 사용 시 false signal 많음. 구름대 필터 병행 필수.

---

### D-02. 구름대 돌파 (Kumo Breakout)
- **정의**: 가격이 구름대를 상향 돌파=강한 매수, 하향 이탈=강한 매도. 구름대 두께 = 지지/저항 강도.
- **수식**:
  `senkou_A = (tenkan+kijun)/2  # 26기간 앞에 표시`
  `senkou_B = (highest_high(52)+lowest_low(52))/2  # 26기간 앞에 표시`
  `kumo_top = max(senkou_A, senkou_B)`
  `kumo_bottom = min(senkou_A, senkou_B)`
  `cloud_breakout_up   = close>kumo_top AND close[-1]<=kumo_top[-1]`
  PIT 주의: senkou는 26기간 앞으로 그려지나, 현재 가격과 비교하는 kumo값은 26기간 전 데이터로 계산됨 → 안전
- **출처**: 호소다 고이치 일목균형표 원전; NAGA Academy | https://naga.com/en/academy/ichimoku
- **Stage**: Entry
- **버킷**: 돌파 + 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 고가·저가 52일+
- **난이도**: 중
- **종합 평가**: 추세 강도 확인에 유효. 구름 두께가 클수록 돌파 의미 강화.

---

### D-03. 후행스팬 확인 (Chikou Span Confirmation)
- **정의**: 후행스팬(현재 종가를 26기간 과거에 표시). 현재가가 26일 전 가격보다 높으면 매수 확인.
- **수식**:
  `chikou_bullish = close[0] > close[-26]  # 현재가 > 26일 전 가격`
  `chikou_bearish = close[0] < close[-26]`
- **출처**: 호소다 고이치 원전; Algomantic Trading | https://www.algomatictrading.com/post/ichimoku-kinko-hyo
- **Stage**: Filter
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전 — 과거 종가만 비교
- **데이터 요건**: 일봉 종가 26일+
- **난이도**: 하
- **종합 평가**: 전환/기준선 크로스 후 추가 확인용. 구현 단순하나 일목 전체 시스템 맥락에서 의미.

---

### D-04. 선행스팬 교차 (Senkou Span Cross / Kumo Twist)
- **정의**: 선행스팬A가 선행스팬B를 상향 돌파(구름 녹색 전환) → 미래 추세 상승 신호.
- **수식**:
  `future_senkou_A = (tenkan+kijun)/2  # 26기간 앞 표시`
  `future_senkou_B = (highest_high(52)+lowest_low(52))/2`
  `kumo_twist_bull = future_senkou_A>future_senkou_B AND prev_A<=prev_B`
  계산 자체는 과거 데이터만 사용 → PIT 안전
- **출처**: Wikipedia Ichimoku; Swissquote | https://www.swissquote.com/en-ch/private/inspire/blog/technical-analysis/what-ichimoku-kinko-hyo-trading-method
- **Stage**: Filter (중장기 방향)
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 고가·저가 52일+
- **난이도**: 중
- **종합 평가**: 중장기 방향성 필터로 활용. 단기 매매 직접 사용은 지연이 큼.

---

### D-05. 일목 삼역 호전 (Triple Ichimoku Confirmation)
- **정의**: 일목균형표 5대 신호 중 3가지 이상 동시 충족 시 강한 매수.
- **수식**:
  `cond1 = tenkan > kijun                       # 전환선 > 기준선`
  `cond2 = close > max(senkou_A, senkou_B)      # 가격 > 구름 상단`
  `cond3 = close > close[-26]                  # 후행스팬 확인`
  `triple_buy  = cond1 AND cond2 AND cond3`
  `triple_sell = (tenkan<kijun) AND (close<min(senkou_A,senkou_B)) AND (close<close[-26])`
- **출처**: OANDA Ichimoku Trading Guide; Arongroups | https://arongroups.co/technical-analyze/ichimoku-indicator/
- **Stage**: Entry (고확신 신호)
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 고가·저가·종가 52일+
- **난이도**: 중
- **종합 평가**: **즉시 코드화 Top 3.** 3조건 동시 충족으로 false signal 대폭 감소. 신호 빈도 낮지만 신뢰도 높음. confidence 90+ 부여 적합.


---

## E. 변동성/채널 기반 — 4개

### E-01. 볼린저밴드 %B (Bollinger Bands %B)
- **정의**: 현재가가 볼린저밴드 내 어느 위치인지를 0~1로 표준화. 0 이하=과매도, 1 이상=과매수.
- **수식**:
  `BB_mid=SMA(20,close); BB_std=stdev(close,20)`
  `BB_upper=BB_mid+2*BB_std; BB_lower=BB_mid-2*BB_std`
  `percent_B = (close-BB_lower)/(BB_upper-BB_lower)`
  `oversold_signal  = percent_B < 0    # 하단 이탈`
  `overbought_signal= percent_B > 1    # 상단 이탈`
  추세 중 눌림목: 0.2 <= %B <= 0.4 에서 반등 확인
- **출처**: John Bollinger (2001) *Bollinger on Bollinger Bands*; StockCharts %B | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/b-indicator; TrendSpider | https://trendspider.com/learning-center/bollinger-band-width-and-b-an-overview/
- **Stage**: Entry (역추세) / Filter
- **버킷**: 평균회귀
- **한국 적용**: 직접 적용 — BBReversionStrategy 확장으로 즉시 활용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 20일+
- **난이도**: 하
- **종합 평가**: BBReversionStrategy에 %B 필터 추가로 즉시 개선 가능. percent_B < 0 AND 반전 캔들 = 강한 매수.

---

### E-02. 볼린저밴드 폭 스퀴즈 (BB Width Squeeze)
- **정의**: BB Width = (상단-하단)/중간선×100. Width가 역사적 저점 근처 → 변동성 수축 → 폭발적 움직임 임박.
- **수식**:
  `BB_width = (BB_upper-BB_lower)/BB_mid*100`
  `width_min_126 = min(BB_width, 126)  # 6개월 기준`
  `squeeze_signal = BB_width < width_min_126*1.1`
  `break_direction_up   = squeeze_signal[-1] AND close>BB_upper`
  `break_direction_down = squeeze_signal[-1] AND close<BB_lower`
- **출처**: John Bollinger Bollinger Band Squeeze; StockCharts BBW | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/bollinger-bandwidth; ThinCapital | https://www.thinkcapital.com/bollinger-bands-squeeze-strategy/
- **Stage**: Entry (방향 돌파 후) / Filter
- **버킷**: 돌파
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 146일+ (20일 BB + 126일 역사적 최저)
- **난이도**: 중
- **종합 평가**: 단독으로 방향 예측 불가 (스퀴즈만으로는 상/하 방향 모름). 방향은 첫 돌파 봉 확인 후 진입.

---

### E-03. 슈퍼트렌드 (SuperTrend)
- **정의**: ATR 기반 동적 추세 추종 지표. 주가 위에 있으면 하락추세(SELL), 아래이면 상승추세(BUY).
- **수식**:
  `median = (high+low)/2`
  `basic_upper = median + mult*ATR(10)  # 기본 mult=3`
  `basic_lower = median - mult*ATR(10)`
  최종 SuperTrend (래칫 로직):
  `if close>final_upper[-1]: final_upper=min(basic_upper, final_upper[-1])`
  `else: final_upper=basic_upper`
  `if close<final_lower[-1]: final_lower=max(basic_lower, final_lower[-1])`
  `else: final_lower=basic_lower`
  `if close>final_upper[-1]: signal=BUY  # 슈퍼트렌드 = final_lower`
  `if close<final_lower[-1]: signal=SELL # 슈퍼트렌드 = final_upper`
- **출처**: LiteFinance SuperTrend | https://www.litefinance.org/blog/for-beginners/best-technical-indicators/supertrend-indicator/; TrendSpider | https://trendspider.com/learning-center/supertrend-indicator-a-comprehensive-guide/
- **Stage**: Entry / Exit (트레일링 스톱 겸용)
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전 — 바 완성 후 신호 확정, 리페인팅 없음
- **데이터 요건**: 일봉 고가·저가·종가 10일+
- **난이도**: 중 (래칫 로직 구현 필요)
- **종합 평가**: 트레일링 스톱과 추세 방향 필터를 동시 제공. 상승장 포지션 유지 + 추세 전환 시 자동 청산에 적합.

---

### E-04. 샹들리에 이탈 (Chandelier Exit)
- **정의**: 최근 N일 최고가 - ATR×배수. 상승 추세에서 이 레벨 아래로 이탈 시 청산 신호. 트레일링 스톱 일종.
- **수식**:
  기본 설정: N=22, mult=3
  `CE_long  = highest_high(22) - 3*ATR(22)`
  `CE_short = lowest_low(22)   + 3*ATR(22)`
  `exit_long  = close < CE_long`
  `exit_short = close > CE_short`
  `enter_long = close > CE_long  # CE_long 위로 회복 = 상승 재개`
- **출처**: Charles Le Beau (원안); StockCharts Chandelier Exit | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/chandelier-exit; QuantifiedStrategies | https://www.quantifiedstrategies.com/chandelier-exit-strategy/
- **Stage**: Exit (손절/익절 주) / Entry (보조)
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전 (highest_high(22, offset=1) 사용 시 완전 안전)
- **데이터 요건**: 일봉 고가·저가·종가 22일+
- **난이도**: 중
- **종합 평가**: ATR Trailing Stop보다 정교. 고점 기준으로 스톱을 추적. Signal.stop_loss 계산에 활용 가능.


---

## F. VWAP 계열 — 3개

### F-01. 장중 VWAP 지지/저항 (Intraday VWAP S/R)
- **정의**: 장 시작부터 현재까지의 거래량 가중 평균가격. 기관 매매 기준선. VWAP 위=매수세 우위, 아래=매도세 우위.
- **수식**:
  `typical_price = (high+low+close)/3`
  `VWAP_t = cumsum(typical_price*volume) / cumsum(volume)  # 장 시작부터 누적`
  `cross_up   = close[0]>VWAP_t[0] AND close[-1]<=VWAP_t[-1]  # 상향 돌파`
  `cross_down = close[0]<VWAP_t[0] AND close[-1]>=VWAP_t[-1]  # 하향 이탈`
  VWAP Bands (±1σ, ±2σ):
  `cumvar = cumsum(volume*(typical-VWAP_t)**2)/cumsum(volume)`
  `VWAP_std = sqrt(cumvar)`
  `upper1=VWAP_t+VWAP_std; lower1=VWAP_t-VWAP_std`
- **출처**: TrendSpider VWAP Guide | https://trendspider.com/learning-center/vwap-indicator-a-comprehensive-guide-for-traders/; CMC Markets | https://www.cmcmarkets.com/en/technical-analysis/what-is-vwap-in-trading; 책3 Andrew Aziz 전략6
- **Stage**: Entry / Exit / Filter
- **버킷**: 추세추종 + 평균회귀
- **한국 적용**: 직접 적용 — minute_candles 테이블 활용. 일별 리셋 처리 필요.
- **PIT 안전도**: 안전
- **데이터 요건**: 분봉 데이터 (고·저·종·거래량) — minute_candles 테이블
- **난이도**: 중 (분봉 인프라 필요)
- **종합 평가**: 기관 매매 기준선으로 강력. minute_candles(1,347종목) 활용 시 즉시 구현 가능.

---

### F-02. Anchored VWAP (이벤트 기준 VWAP)
- **정의**: 특정 이벤트(어닝, 신고가, 갭 발생일) 시점부터 누적 VWAP. 이벤트 이후 매수/매도 세력 평균 단가.
- **수식**:
  `AVWAP_t = cumsum(typical*vol, from=t_anchor) / cumsum(vol, from=t_anchor)`
  복수 앵커: 52주 신고가일 기준 AVWAP + 최근 저점 기준 AVWAP
  `confluence = abs(AVWAP_high-AVWAP_low)/close < 0.01  # 1% 이내 수렴 = 강한 S/R`
- **출처**: StockCharts Anchored VWAP | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/anchored-vwap; ForexTester | https://forextester.com/blog/anchored-vwap/
- **Stage**: Filter / Entry
- **버킷**: 지지저항
- **한국 적용**: 직접 적용 — corp_events 테이블(분할·합병일)을 앵커로 활용 가능
- **PIT 안전도**: 안전 — 앵커 이후 데이터만 사용
- **데이터 요건**: 분봉 데이터 + 이벤트 날짜 (corp_events 테이블)
- **난이도**: 중상
- **종합 평가**: corp_events 테이블이 구축되어 있으므로 분할/합병 앵커 VWAP 즉시 계산 가능.

---

### F-03. 다일 VWAP (Multi-Day / Weekly VWAP)
- **정의**: 주간 VWAP = 월요일 장 시작부터 현재까지 누적 VWAP. 일(Daily)+주간(Weekly) 이중 지지/저항 활용.
- **수식**:
  `weekly_VWAP = cumsum(typical*vol, from=week_start) / cumsum(vol, from=week_start)`
  `double_support = abs(daily_VWAP-weekly_VWAP)/close < 0.005  # 0.5% 이내 수렴`
- **출처**: BingX VWAP | https://bingx.com/en/learn/article/vwap-explained-what-it-is-how-traders-use-it; Capital.com | https://capital.com/en-int/learn/technical-analysis/volume-weighted-average-price-vwap-indicator
- **Stage**: Filter
- **버킷**: 지지저항
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 분봉 데이터 (주 단위 리셋)
- **난이도**: 중
- **종합 평가**: F-01 구현 후 확장으로 추가. 독립 시그널보다 F-01의 강도 보강 용도.

---

## G. 파라볼릭/트레일링 스톱 계열 — 2개

### G-01. Parabolic SAR (포물선 추세 반전)
- **정의**: 가속 요소(AF)로 SAR 점 계산. 점이 주가 위=하락추세(SELL), 아래=상승추세(BUY).
- **수식**:
  상승 추세: `SAR[t] = SAR[t-1] + AF*(EP - SAR[t-1])`
  EP = 현재 상승 추세 중 최고가; AF 초기 0.02, 신고가 갱신마다 +0.02, 최대 0.20
  제약: `SAR[t] <= min(low[t-1], low[t-2])`
  하락 추세: `SAR[t] = SAR[t-1] - AF*(SAR[t-1] - EP)`
  제약: `SAR[t] >= max(high[t-1], high[t-2])`
  `flip_to_buy  = close > SAR_falling[t-1]`
  `flip_to_sell = close < SAR_rising[t-1]`
- **출처**: J. Welles Wilder (1978) *New Concepts in Technical Trading Systems*; StockCharts | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/parabolic-sar; LiteFinance | https://www.litefinance.org/blog/for-beginners/best-technical-indicators/parabolic-sar-indicator/
- **Stage**: Entry / Exit
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전 — 이전 바 값만 사용
- **데이터 요건**: 일봉 고가·저가·종가 (이전 바 데이터만)
- **난이도**: 중 (상태 변수 관리 필요)
- **종합 평가**: 횡보 구간에서 잦은 false signal. 추세 강도 필터(정배열 확인) 병행 필수. Signal.stop_loss를 SAR 값으로 설정 시 동적 손절 구현 가능.

---

### G-02. ATR 트레일링 스톱 (ATR Trailing Stop)
- **정의**: ATR×배수로 포지션 방향에 따라 동적 스톱 레벨 설정. 상승 추세에서 스톱은 올라가기만 함(래칫 효과).
- **수식**:
  `ATR_14 = ATR(14);  mult = 2.0`
  `trail_long[t]  = max(trail_long[t-1], close[t]-mult*ATR_14[t])`
  `trail_short[t] = min(trail_short[t-1], close[t]+mult*ATR_14[t])`
  `stop_hit_long  = close < trail_long`
  `stop_hit_short = close > trail_short`
- **출처**: John Murphy *Technical Analysis*; ForexTrainingGroup | https://forextraininggroup.com/protect-your-open-profits-with-trailing-stop-loss-strategies/
- **Stage**: Exit (동적 손절/익절)
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 고가·저가·종가 14일+
- **난이도**: 중 (래칫 로직 구현)
- **종합 평가**: Signal.stop_loss를 정적 값 대신 ATR 트레일링 스톱으로 교체 시 수익 구간 연장 효과.

---

## H. 가격 메모리/수평 S/R 계열 — 1개

### H-01. N일 고점/저점 빈도 가중 수평 지지저항 (Price Memory Horizontal S/R)
- **정의**: 과거 N일 내 특정 가격대 체류 빈도로 지지/저항 강도 산출. 고빈도 가격대 = 강한 S/R.
- **수식**:
  방법1 (종가 히스토그램):
  `price_bins = round(close/tick_size)*tick_size  # 호가 단위 반올림`
  `freq_map = Counter(price_bins[-N:])  # N일 종가 빈도 맵`
  `nearby = {p:f for p,f in freq_map.items() if abs(p-close)/close<0.02}`
  `top_sr = max(nearby, key=nearby.get)`

  방법2 (스윙 클러스터링):
  `swing_highs = detected_swing_highs[-N_bars:]`
  `# 0.5% 이내 클러스터 = 강한 수평 저항`
  `bounce_signal = abs(close-top_sr)/close<0.005 AND reversal_candle`
- **출처**: John Murphy *Technical Analysis* Ch.4 (S/R Price Memory); LuxAlgo Swing H/L | https://www.luxalgo.com/blog/swing-highs-and-lows-basics-for-traders/; Altrady | https://www.altrady.com/crypto-trading/smart-money-concept/how-to-identify-swing-highs-and-lows
- **Stage**: Filter / Entry (레벨 근접 + 반전 캔들)
- **버킷**: 지지저항
- **한국 적용**: 직접 적용 — daily_prices 테이블로 N일 고저가 히스토그램 계산 가능
- **PIT 안전도**: 안전 — 과거 N일 데이터만 사용 (N=60 권장)
- **데이터 요건**: 일봉 고가·저가·종가 N일 (60~120일)
- **난이도**: 중
- **종합 평가**: 피봇 포인트와 달리 전 가격 구간의 실제 체류 빈도 반영. 거래량 프로파일 없이도 근사 구현 가능. 한국 종목의 전고점/전저점 저항 개념과 직결.


---

## 종합 통계

| 카테고리 | 컨셉 수 | PIT 안전 | 주의 필요 |
|---|---|---|---|
| A. 이동평균선 | 9 | 9 | 0 |
| B. 추세선/채널 | 4 | 2 | 2 (B-01, B-02) |
| C. 피보나치 | 3 | 1 | 2 (C-01, C-02) |
| D. 일목균형표 | 5 | 5 | 0 |
| E. 변동성/채널 | 4 | 4 | 0 |
| F. VWAP | 3 | 3 | 0 |
| G. 파라볼릭/트레일링 | 2 | 2 | 0 |
| H. 가격 메모리 | 1 | 1 | 0 |
| **합계** | **26** | **24** | **2** |

---

## 출처 비율

| 출처 구분 | 컨셉 수 | 비율 |
|---|---|---|
| 책 3권 (교보문고) | 6 | 23% |
| John Murphy *Technical Analysis of the Financial Markets* | 5 | 19% |
| StockCharts ChartSchool | 7 | 27% |
| 일목 원전 (호소다 고이치) | 5 | 19% |
| 기타 공식 문서 (TrendSpider, LiteFinance 등) | 3 | 12% |

---

## 즉시 코드화 Top 3 추천

1. **D-05. 일목 삼역 호전** — 조건 3개 AND 조합. 수식 단순, 데이터 52일 일봉만 필요. 신호 신뢰도 최고. confidence 90+ 부여. `generate_signal()` 직접 구현 가능.

2. **C-03. 피봇 포인트 (Floor/Camarilla)** — 전일 OHLC만으로 당일 레벨 사전 계산. PIT 완전 안전. 스크리너 필터 + Signal.target_price/stop_loss에 즉시 활용.

3. **B-03. 도날치안 채널 돌파** — 수식 2줄. `max(high, N)` 돌파=진입, `min(low, 10)` 이탈=청산. VolumeBreakoutStrategy와 결합 시 즉시 배포 가능.

---

## PIT 위험 경고 — 추세선/피보나치 자동화 주의

**B-01, B-02 (자동 추세선) 및 C-01, C-02 (피보나치 되돌림)의 Look-Ahead Bias 함정:**

스윙 고점/저점 확정은 해당 바로부터 최소 `lookback_right(=N)` 바 이후에야 가능하다.
예: N=5이면 swing_high[i]는 바[i+5]가 완성된 시점에서만 확정.

```python
# 잘못된 구현 (Look-Ahead 위험)
is_swing_high = high[i] == max(high[i-5:i+6])  # i+5 미래 참조!

# 올바른 구현 (PIT-safe)
# 현재 바 t에서, 스윙 고점은 t-lookback_right 이전만 확정 가능
confirmed_idx = t - lookback_right  # 예: t-5
is_swing_high = (high[confirmed_idx] == max(high[confirmed_idx-5:confirmed_idx+1]))
# 오직 과거 데이터만 사용
```

---

## 참고 출처 URL 모음

| 문서/도구 | URL |
|---|---|
| StockCharts HMA | https://chartschool.stockcharts.com/.../hull-moving-average-hma |
| StockCharts DEMA | https://chartschool.stockcharts.com/.../double-exponential-moving-average-dema |
| StockCharts TEMA | https://chartschool.stockcharts.com/.../triple-exponential-moving-average-tema |
| StockCharts Parabolic SAR | https://chartschool.stockcharts.com/.../parabolic-sar |
| StockCharts Chandelier Exit | https://chartschool.stockcharts.com/.../chandelier-exit |
| StockCharts %B | https://chartschool.stockcharts.com/.../b-indicator |
| StockCharts BBW | https://chartschool.stockcharts.com/.../bollinger-bandwidth |
| StockCharts Anchored VWAP | https://chartschool.stockcharts.com/.../anchored-vwap |
| StockCharts Fibonacci | https://chartschool.stockcharts.com/.../fibonacci-retracements |
| Wikipedia Ichimoku | https://en.wikipedia.org/wiki/Ichimoku_Kink%C5%8D_Hy%C5%8D |
| OANDA Ichimoku Guide | https://www.oanda.com/us-en/trade-tap-blog/analysis/technical/ichimoku-cloud-trading-guide-key-strategies/ |
| TrendSpider SuperTrend | https://trendspider.com/learning-center/supertrend-indicator-a-comprehensive-guide/ |
| TrendSpider VWAP | https://trendspider.com/learning-center/vwap-indicator-a-comprehensive-guide-for-traders/ |
| TrendSpider BB/KC Squeeze | https://trendspider.com/learning-center/bb-kc-squeeze-a-powerful-indicator-for-trading-range-breakouts/ |
| TradingView Donchian | https://www.tradingview.com/scripts/donchianchannels/ |
| LiteFinance SuperTrend | https://www.litefinance.org/blog/for-beginners/best-technical-indicators/supertrend-indicator/ |
| LiteFinance Parabolic SAR | https://www.litefinance.org/blog/for-beginners/best-technical-indicators/parabolic-sar-indicator/ |
| ForexTester Anchored VWAP | https://forextester.com/blog/anchored-vwap/ |
| Elliott Wave Fibonacci Ext | https://elliottwave-forecast.com/trading/fibonacci-retracement-and-fibonacci-extension/ |
| Britannica Fibonacci | https://www.britannica.com/money/fibonacci-trading-strategies |
| market-bulls.com Pivot | https://market-bulls.com/pivot-point-calculator/ |
| TradingPedia DeMark Pivot | https://www.tradingpedia.com/forex-trading-indicators/fibonacci-pivot-points-demark-calculation/ |
| ForexTrainingGroup Pivots | https://forextraininggroup.com/comparing-different-types-pivot-points/ |
| LuxAlgo Swing H/L | https://www.luxalgo.com/blog/swing-highs-and-lows-basics-for-traders/ |
| 책1 강창권 교보 | https://product.kyobobook.co.kr/detail/S000217567051 |
| 책3 Andrew Aziz 교보 | https://product.kyobobook.co.kr/detail/S000001777389 |

---

*출력 파일*: `RoboTrader_template/reports/10pct_strategy/phase5_signals/03_trendlines_sr.md`
*연관 파일*: `00_kyobo_books.md` (책 3권 원천 컨셉 추출)
