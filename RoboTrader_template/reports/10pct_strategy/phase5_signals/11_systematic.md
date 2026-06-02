# 시스템/퀀트 트레이딩 책 5권 — 시그널 카탈로그 (Phase 5 확장용)

> 작성일: 2026-05-26 | 조사자: document-specialist (Claude Sonnet 4.6)
> 목적: Phase 5 시그널 패밀리 확장 — 시스템/퀀트 트레이딩 카테고리
> 수집 컨셉: **25개** (책 5권 × 5개 이상)
> 연관 아키텍처 권고: v2_diagnosis.md Section 3(b) — OBV ATR adaptive SL 재설계

---

## 형식 설명

| 필드 | 설명 |
|---|---|
| **컨셉명** | 시그널 이름 (영문/한국어) |
| **정의/수식** | 계산 방법 및 조건 |
| **출처** | 1차 참고 문헌 및 URL |
| **Stage** | Entry / Exit / Filter / Sizing (복수 가능) |
| **버킷** | 추세추종 / 평균회귀 / 돌파 / 모멘텀 / 포지션사이징 |
| **한국 적용** | 직접 적용 / 제한적 / 한국 전용 |
| **PIT 안전도** | 안전 / 주의 / 위험 (Look-Ahead Bias 위험도) |
| **데이터 요건** | 필요 데이터 |
| **난이도** | 하 / 중 / 상 |
| **ATR 연계** | OBV ATR adaptive SL 재설계 관련 여부 (architect 권고) |

---

## 발굴 책 5권 목록

| # | 저자 | 책 제목 | 출판 | 핵심 컨셉 |
|---|---|---|---|---|
| 1 | Andreas Clenow | *Stocks on the Move* (2015) | CreateSpace | 변동성 조정 모멘텀, ATR 포지션사이징 |
| 2 | Curtis Faith | *Way of the Turtle* (2007) | McGraw-Hill | Donchian breakout, ATR N-unit, 피라미딩 |
| 3 | Robert Carver | *Systematic Trading* (2015) | Harriman House | EWMAC, 변동성 타겟팅, 분산 배수 |
| 4 | Wesley R. Gray & Jack R. Vogel | *Quantitative Momentum* (2016) | Wiley Finance | 12-1 모멘텀, Frog-in-Pan, 모멘텀 품질 |
| 5 | Marcos Lopez de Prado | *Advances in Financial Machine Learning* (2018) | Wiley | Triple Barrier, Meta-Labeling, CUSUM, Bet Sizing |

---

## A. Andreas Clenow — *Stocks on the Move* (2015) — 5개

**서지**: Andreas F. Clenow, *Stocks on the Move: Beating the Market with Hedge Fund Momentum Strategies*, CreateSpace, 2015.
**공식 사이트**: https://www.followingthetrend.com/stocks-on-the-move/
**Amazon**: https://www.amazon.com/Stocks-Move-Beating-Momentum-Strategies/dp/1511466146

---

### A-01. Clenow 변동성 조정 모멘텀 스코어 (Volatility-Adjusted Momentum Score)

- **정의**: 90일 로그가격 지수회귀의 연율화 기울기 × R² 값. 추세 강도와 일관성을 동시 측정.
- **수식**:
  ```python
  log_prices = np.log(close[-90:])
  slope, _, r, _, _ = linregress(range(90), log_prices)
  annualized_slope = (1 + slope)**252 - 1   # 연율화
  momentum_score = annualized_slope * r**2  # R² 가중 — 변동성 조정
  ```
  해석: 추세가 강하더라도 R²가 낮으면(들쭉날쭉) 낮은 점수 → 일관된 추세만 선별
- **출처**: Clenow *Stocks on the Move* Ch.5; TeddyKoker 구현 | https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/; QuantConnect | https://www.quantconnect.com/forum/discussion/10493/
- **Stage**: Filter (종목 랭킹)
- **버킷**: 모멘텀
- **한국 적용**: 직접 적용 — KOSPI/KOSDAQ 전 종목 일봉 5.4년치로 계산 가능. S&P500 우주를 KOSPI200 또는 유동성 상위 500종목으로 대체 필요.
- **PIT 안전도**: 안전 — 과거 90일 종가만 사용
- **데이터 요건**: 일봉 종가 90일+ (daily_prices 테이블)
- **난이도**: 중 (scipy.stats.linregress 필요)
- **ATR 연계**: 간접 — R² 가중으로 들쭉날쭉 종목 걸러냄. OBV 시그널에도 동일 R² 필터 적용 시 신뢰도 향상 가능.
- **종합 평가**: **즉시 코드화 Top 3.** 수식 단순, 데이터 완비. 매주 종목 랭킹 갱신 + 상위 20% 편입. ATR 포지션사이징(A-02)과 반드시 함께 사용.

---

### A-02. ATR 기반 포지션 사이징 — Clenow 방식 (ATR Position Sizing)

- **정의**: 포지션 1단위의 1일 기대 변동(ATR20)이 계좌의 일정 비율(RiskFactor)이 되도록 주식수 계산. 변동성이 큰 종목은 자동으로 소량 보유.
- **수식**:
  ```python
  ATR_20 = average_true_range(high, low, close, period=20)
  risk_factor = 0.001   # 0.1% of portfolio per position (Clenow default)
  shares = int((account_value * risk_factor) / ATR_20)
  ```
  재밸런싱: 2주마다 ATR 업데이트 → 주식수 재계산
- **출처**: Clenow *Stocks on the Move* Ch.6; TuringTrader | https://www.turingtrader.com/portfolios/clenow-stocks-on-the-move/
- **Stage**: Sizing
- **버킷**: 포지션사이징
- **한국 적용**: 직접 적용 — 한국 거래비용(0.3%) 고려해 risk_factor를 0.0005~0.001로 조정 권장.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 고가·저가·종가 20일+
- **난이도**: 하
- **ATR 연계**: **핵심 연계** — architect 권고 OBV ATR adaptive SL의 포지션사이징 기반. `shares = floor(risk_budget / ATR_20)` 공식을 OBV 전략 PositionSizer에 직접 이식 가능. Signal.metadata['atr_shares'] 필드 추가로 즉시 적용.
- **종합 평가**: **즉시 코드화 Top 3.** 4줄 구현. 현재 고정 비율 포지션사이징을 이 방식으로 교체 시 변동성 적응형 사이징 달성.

---

### A-03. 200일 SMA 인덱스 필터 (Index Trend Filter)

- **정의**: 벤치마크 지수(KOSPI)가 200일 SMA 아래이면 신규 매수 중단. 하락장 노출 방지.
- **수식**:
  ```python
  kospi_sma200 = kospi_index_close.rolling(200).mean()
  index_filter = kospi_index_close.iloc[-1] > kospi_sma200.iloc[-1]
  # index_filter == False → 신규 매수 전면 금지
  ```
  TIGER200 ETF(069500)를 KOSPI 프록시로 활용 가능
- **출처**: Clenow *Stocks on the Move* Ch.7; Quant-Investing 인터뷰 | https://www.quant-investing.com/blog/more-insights-from-andreas-clenow-author-of-stocks-on-the-move-beating-the-market-with-hedge-fund-momentum-strategies
- **Stage**: Filter
- **버킷**: 추세추종
- **한국 적용**: 직접 적용 — TIGER200 ETF 또는 KOSPI 지수 일봉 사용.
- **PIT 안전도**: 안전
- **데이터 요건**: 지수 또는 ETF 일봉 종가 200일+
- **난이도**: 하
- **ATR 연계**: 간접 — 지수 필터가 BEAR 국면에서 OBV 시그널 발동 자체를 차단.
- **종합 평가**: 단 2줄. 하락장 손실 방어 효과 검증됨. 현재 regime_filter(BULL/BEAR/SIDEWAYS)와 통합 시 더욱 정교화 가능.

---

### A-04. 100일 SMA 개별 종목 트렌드 필터 (Individual Stock Trend Filter)

- **정의**: 개별 종목이 100일 SMA 아래이면 해당 종목 매수 금지. 인덱스 필터보다 개별 주가 수준에서 추가 검증.
- **수식**:
  ```python
  sma100 = close.rolling(100).mean()
  stock_trend_ok = close.iloc[-1] > sma100.iloc[-1]
  # entry = momentum_rank_top20 AND index_filter AND stock_trend_ok
  ```
- **출처**: Clenow *Stocks on the Move* Ch.5 (Stock Selection Rules)
- **Stage**: Filter
- **버킷**: 추세추종
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 100일+
- **난이도**: 하
- **ATR 연계**: 없음
- **종합 평가**: A-01~A-03과 함께 4중 필터 구성. 이미 MomentumStrategy에 MA5>MA20 필터 존재 — 100일 필터 추가로 중장기 추세 기반 종목만 진입.

---

### A-05. 모멘텀 랭킹 기반 주간 리밸런싱 (Weekly Momentum Rebalancing)

- **정의**: 매주 수요일 종목별 모멘텀 스코어(A-01) 재산출 → 상위 N개 유지/진입, 하위 이탈 종목 청산.
- **수식**:
  ```python
  TOP_N = 20
  scores = {code: clenow_momentum(code) for code in universe}
  ranked = sorted(scores, key=scores.get, reverse=True)
  to_buy  = [c for c in ranked[:TOP_N] if c not in current_positions]
  to_sell = [c for c in current_positions if c not in ranked[:TOP_N]]
  # 추가 매도 트리거: 종목이 SMA100 아래로 이탈
  ```
- **출처**: Clenow *Stocks on the Move* Ch.8; QuantConnect | https://www.quantconnect.com/forum/discussion/16578/
- **Stage**: Entry / Exit
- **버킷**: 모멘텀
- **한국 적용**: 제한적 — 한국 시장 EOD 주문은 다음날 시가 실행. 거래비용 누적으로 격주 또는 월간 리밸런싱 권장.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 90일+ (전 종목)
- **난이도**: 중
- **ATR 연계**: 없음
- **종합 평가**: screener_snapshots 테이블 + Phase 2/3 스크리너 인프라와 통합 시 주간 리밸런싱 자동화 가능.


---

## B. Curtis Faith — *Way of the Turtle* (2007) — 5개

**서지**: Curtis Faith, *Way of the Turtle: The Secret Methods That Turned Ordinary People into Legendary Traders*, McGraw-Hill, 2007.
**참고**: https://www.altrady.com/blog/crypto-trading-strategies/turtle-trading-strategy-rules; https://alchemymarkets.com/education/strategies/turtle-trading-guide/

---

### B-01. 터틀 시스템 1 — 20일 돌파 진입 (Turtle System 1: 20-Day Breakout Entry)

- **정의**: 20일 최고가 돌파 시 매수 진입, 10일 최저가 이탈 시 청산. 단, 직전 20일 돌파 신호가 수익으로 종료되었다면 해당 신호 스킵(필터).
- **수식**:
  ```python
  DC20_upper = max(high[-21:-1])   # 직전 20일 최고가 (현재 바 제외 — PIT 안전)
  DC10_lower = min(low[-11:-1])    # 직전 10일 최저가
  entry_long  = close[-1] > DC20_upper
  exit_long   = close[-1] < DC10_lower
  # 필터: 직전 신호가 수익이면 이번 신호 무시
  ```
- **출처**: Faith *Way of the Turtle* Ch.5; Altrady | https://www.altrady.com/blog/crypto-trading-strategies/turtle-trading-strategy-rules; Alchemy Markets | https://alchemymarkets.com/education/strategies/turtle-trading-guide/
- **Stage**: Entry / Exit
- **버킷**: 돌파 + 추세추종
- **한국 적용**: 직접 적용 — 03_trendlines_sr.md B-03(도날치안 채널) 확장 버전. 스킵 필터가 핵심 차별점.
- **PIT 안전도**: 안전 — max(high[-21:-1]) 현재 바 제외
- **데이터 요건**: 일봉 고가·저가 20일+
- **난이도**: 하
- **ATR 연계**: 진입 신호. B-02(ATR 손절)·B-03(피라미딩)과 조합해 완전한 거북이 시스템 구성.
- **종합 평가**: 수식 단순, PIT 안전. VolumeBreakoutStrategy와 조합 시 거래량 확인으로 신뢰도 향상.

---

### B-02. ATR N-unit 손절 (Turtle ATR Stop Loss — 2N Stop)

- **정의**: 진입가로부터 2× ATR(=2N) 하락 시 손절. ATR을 "N"이라 부름. 포지션 유닛마다 동일한 ATR 단위 손실 위험.
- **수식**:
  ```python
  N = ATR(20)                            # 터틀의 N = 20일 ATR
  stop_long  = entry_price - 2 * N      # 롱 손절
  # 피라미딩 유닛이 추가될 때마다 stop을 0.5N씩 상향 조정
  # KOSPI 예: ATR=1500원, 진입가=50000원 → stop=47000원(-6%)
  signal.stop_loss = round_to_tick(entry_price - 2 * N)
  ```
- **출처**: Faith *Way of the Turtle* Ch.6; EBC Financial | https://www.ebc.com/forex/turtle-trading-strategy-explained-a-beginners-guide; Alchemy Markets | https://alchemymarkets.com/education/strategies/turtle-trading-guide/
- **Stage**: Exit
- **버킷**: 추세추종
- **한국 적용**: 직접 적용 — 한국 호가 단위 반올림 필요 (price_utils.round_to_tick()).
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 고가·저가·종가 20일+
- **난이도**: 하
- **ATR 연계**: **핵심 연계 — architect 권고 OBV ATR adaptive SL의 직접 원형.** v2_diagnosis.md Section 3(b) 재설계 권고와 정확히 일치. OBV 시그널 발동 시 `Signal.stop_loss = entry_price - 2 * ATR_20` 설정으로 즉시 이식 가능. SL Grid 재조정(P1 패치)에서 SL=-5/-7/-10%가 이 원리 반영.
- **종합 평가**: **즉시 코드화 Top 3. ATR adaptive SL 핵심 컨셉.** 고정 % 손절 대비 시장 변동성에 적응하는 동적 손절. Signal.stop_loss 필드에 `entry - 2*ATR` 값 주입으로 즉시 구현.

---

### B-03. 거북이 피라미딩 (Turtle Pyramiding — Adding Units)

- **정의**: 진입 후 0.5N(ATR 절반) 상승마다 1유닛 추가 매수. 최대 4유닛까지 피라미딩. 추세 확인 후 베팅 증가.
- **수식**:
  ```python
  N = ATR(20)
  unit_size = int((account * 0.01) / N)   # 1유닛 = 계좌 1% / ATR
  # 피라미딩 레벨
  # unit 1: entry_price
  # unit 2: entry_price + 0.5*N  (stop → entry - 1.5*N)
  # unit 3: entry_price + 1.0*N  (stop → entry - 1.0*N)
  # unit 4: entry_price + 1.5*N  (stop → entry - 0.5*N)
  add_threshold = entry_price + 0.5 * N * current_unit_count
  max_units = 4
  ```
- **출처**: Faith *Way of the Turtle* Ch.7; EBC Financial | https://www.ebc.com/forex/turtle-trading-strategy-explained-a-beginners-guide
- **Stage**: Entry (추가 진입)
- **버킷**: 추세추종
- **한국 적용**: 제한적 — 한국 개인 투자자는 레버리지 없이 최대 2유닛으로 제한 권장.
- **PIT 안전도**: 안전
- **데이터 요건**: 실시간 가격 + ATR
- **난이도**: 중 (포지션 유닛 상태 추적 필요)
- **ATR 연계**: 연계 — OBV 시그널 강도(confidence)에 따른 단계별 포지션 증가에 적용 가능. confidence 80+ → 2유닛, 90+ → 3유닛으로 변형.
- **종합 평가**: 강한 추세에서 수익 극대화. B-01(진입) + B-02(손절)와 패키지로 구현해야 의미 있음.

---

### B-04. 거북이 시스템 2 — 55일 돌파 (Turtle System 2: 55-Day Breakout)

- **정의**: 55일 최고가 돌파 시 매수, 20일 최저가 이탈 시 청산. 시스템 1보다 느리지만 강한 신호. 스킵 필터 없음.
- **수식**:
  ```python
  DC55_upper = max(high[-56:-1])    # 55일 신고가
  DC20_lower = min(low[-21:-1])     # 20일 신저가
  entry_long  = close[-1] > DC55_upper
  exit_long   = close[-1] < DC20_lower
  ```
- **출처**: Faith *Way of the Turtle* Ch.5; Altrady | https://www.altrady.com/blog/crypto-trading-strategies/turtle-trading-strategy-rules
- **Stage**: Entry / Exit
- **버킷**: 돌파 + 추세추종
- **한국 적용**: 직접 적용 — 일봉 55일+ 필요. 5.4년치 데이터 충분.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 고가·저가 55일+
- **난이도**: 하
- **ATR 연계**: 없음 (B-02와 조합 시 완전한 시스템 2 구성)
- **종합 평가**: 시스템 1보다 신호 빈도 낮고 신뢰도 높음. 한국 시장 중장기 추세추종에 적합.

---

### B-05. 거북이 포지션 한도 — 상관관계 기반 분산 (Turtle Position Limits)

- **정의**: 동일 시장/섹터 내 최대 유닛 수 제한. 강한 상관관계 시장에서 합산 노출 제한.
- **수식**:
  ```python
  MAX_UNITS_PER_STOCK  = 4
  MAX_UNITS_PER_SECTOR = 6
  MAX_UNITS_TOTAL      = 12
  # 신규 유닛 추가 전 현재 유닛 합산 체크
  if current_sector_units >= MAX_UNITS_PER_SECTOR: skip_entry()
  ```
- **출처**: Faith *Way of the Turtle* Ch.8; Alchemy Markets | https://alchemymarkets.com/education/strategies/turtle-trading-guide/
- **Stage**: Filter (리스크 관리)
- **버킷**: 포지션사이징
- **한국 적용**: 직접 적용 — KRX 섹터 분류로 동일 섹터 집중 제한. DB에 섹터 정보 추가 필요.
- **PIT 안전도**: 안전
- **데이터 요건**: 섹터 분류 데이터
- **난이도**: 중
- **ATR 연계**: 없음
- **종합 평가**: 현재 TradingConfig.max_positions와 연계해 섹터별 분산 상한 추가 가능.


---

## C. Robert Carver — *Systematic Trading* (2015) — 5개

**서지**: Robert Carver, *Systematic Trading: A unique new method for designing trading and investing systems*, Harriman House, 2015.
**출판사**: https://www.harriman-house.com/systematic-trading
**저자 블로그**: https://qoppac.blogspot.com/

---

### C-01. EWMAC — 지수 이동평균 크로스오버 예측 (Exponentially Weighted MA Crossover Forecast)

- **정의**: 빠른 EWMA와 느린 EWMA의 차이를 변동성으로 나눈 표준화 예측값. +10이면 표준 매수, -10이면 표준 매도.
- **수식**:
  ```python
  # EWMAC(fast=16, slow=64) — Carver 기본 조합
  ewma_fast = close.ewm(span=16).mean()
  ewma_slow = close.ewm(span=64).mean()
  raw_forecast = ewma_fast - ewma_slow
  price_vol = close.pct_change().ewm(span=36).std() * close
  scaled_forecast = raw_forecast / price_vol
  forecast_scalar = 10 / scaled_forecast.abs().mean()   # 장기 평균이 10
  forecast = (scaled_forecast * forecast_scalar).clip(-20, 20)
  # forecast > 0: 매수, forecast > 10: 강한 매수
  ```
  다중 EWMAC: (2,8), (4,16), (8,32), (16,64), (32,128), (64,256) 조합 후 가중 평균
- **출처**: Carver *Systematic Trading* Ch.15; 7Circles | https://the7circles.uk/systematic-trading-3-frameworks-and-forecasts/; 저자 블로그 | https://qoppac.blogspot.com/2015/09/python-code-for-two-trading-rules-in.html
- **Stage**: Entry / Filter
- **버킷**: 추세추종
- **한국 적용**: 직접 적용 — forecast가 0~10 구간이면 confidence 50~80으로 매핑 가능.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 256일+ (EWMAC(64,256) 기준)
- **난이도**: 중
- **ATR 연계**: 간접 — forecast 값을 OBV confidence 스케일에 통합 가능. `confidence = min(90, 50 + forecast * 2)` 형태 매핑.
- **종합 평가**: 현재 SampleStrategy MA5/20 크로스 대비 더 정교한 버전. 복수 EWMAC 조합으로 노이즈 감소.

---

### C-02. 변동성 타겟팅 포지션사이징 (Volatility Targeting Position Sizing)

- **정의**: 포트폴리오 전체 변동성이 목표치(연 20%)가 되도록 포지션 크기를 역산. 고변동성 시장에서 자동 축소.
- **수식**:
  ```python
  annual_vol_target = 0.20           # 연 20% 변동성 목표
  daily_vol_target  = annual_vol_target / 16   # sqrt(256) = 16
  instrument_vol = close.pct_change().ewm(span=36).std()   # 일일 변동성
  capital_per_inst = account_value * daily_vol_target / instrument_vol.iloc[-1]
  shares = int(capital_per_inst / close.iloc[-1])
  # Half-Kelly: 백테스트 SR을 25% 할인 후 적용
  ```
- **출처**: Carver *Systematic Trading* Ch.11; 7Circles | https://the7circles.uk/systematic-trading-4-volatility-targeting-and-position-sizing/; TopTradersUnplugged | https://www.toptradersunplugged.com/podcast/when-position-sizing-saves-you-ft-rob-carver
- **Stage**: Sizing
- **버킷**: 포지션사이징
- **한국 적용**: 직접 적용 — 고변동성 기간(코로나, 금리충격) 자동 축소 효과.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 36일+
- **난이도**: 중
- **ATR 연계**: 연계 — ATR 기반 사이징(A-02)과 동일 철학의 변동성 정규화. 두 방법 중 하나 선택 또는 병행 가능. Carver 방식은 포트폴리오 전체 변동성 기준, Clenow 방식은 개별 종목 ATR 기준.
- **종합 평가**: FundManager 클래스 포지션 계산 로직을 이 방식으로 업그레이드하면 변동성 환경 적응형 자금관리 달성.

---

### C-03. 분산 배수 (Diversification Multiplier)

- **정의**: 비상관 전략/자산 조합 시 개별 변동성 합산보다 포트폴리오 변동성이 낮으므로 포지션을 배수만큼 늘림.
- **수식**:
  ```python
  # 두 전략 A, B (각 변동성 σ, 상관계수 ρ)
  portfolio_vol = np.sqrt(sA**2 + sB**2 + 2*rho*sA*sB)
  div_multiplier = (sA + sB) / portfolio_vol
  div_multiplier = min(div_multiplier, 2.5)   # Carver: 최대 2.5 cap
  # 실제 포지션 = 기본 포지션 × div_multiplier
  ```
  예: 상관계수 0.5, 각 10% 변동성 → 포트폴리오 8.66% → 배수 1.15
- **출처**: Carver *Systematic Trading* Ch.12; 7Circles | https://the7circles.uk/systematic-trading-4-volatility-targeting-and-position-sizing/
- **Stage**: Sizing (포트폴리오 레벨)
- **버킷**: 포지션사이징
- **한국 적용**: 직접 적용 — 다전략 병렬 실행(multiverse_paper) 시 전략 간 상관관계 계산 후 적용 가능.
- **PIT 안전도**: 안전
- **데이터 요건**: 전략 수익률 히스토리
- **난이도**: 상 (전략 간 상관관계 추적 인프라 필요)
- **ATR 연계**: 없음
- **종합 평가**: multiverse_paper 프레임워크에 전략 가중치로 통합 가능. 단순 균등 배분에서 상관관계 기반 배분으로 업그레이드 경로.

---

### C-04. 예측값 결합 (Combined Forecast — Weighted Average)

- **정의**: 복수 트레이딩 규칙의 예측값(각 -20~+20)을 가중 평균해 최종 포지션 방향 결정. 단일 규칙보다 안정적.
- **수식**:
  ```python
  forecast_ewmac = compute_ewmac(fast=16, slow=64)    # -20~+20
  forecast_carry = compute_carry_rule()               # -20~+20
  w_ewmac, w_carry = 0.5, 0.5
  combined = (w_ewmac * forecast_ewmac + w_carry * forecast_carry).clip(-20, 20)
  # combined > 0: 매수 방향, combined > 10: 강한 매수
  ```
- **출처**: Carver *Systematic Trading* Ch.14; 저자 블로그 | https://qoppac.blogspot.com/2017/06/some-more-trading-rules.html
- **Stage**: Filter / Entry
- **버킷**: 추세추종
- **한국 적용**: 직접 적용 — Phase 2b/2c 다중 시그널 조합 방식과 유사. Carver 방식으로 정형화 가능.
- **PIT 안전도**: 안전
- **데이터 요건**: 복수 시그널 계산 가능한 일봉 데이터
- **난이도**: 중
- **ATR 연계**: 간접 — combined forecast 양수이면 OBV 시그널 방향 확인, 음수이면 OBV 매수 시그널 억제.
- **종합 평가**: Phase 2c top_triples 조합 구조와 철학적으로 동일. Carver 방식의 명시적 예측값 스케일링 도입으로 시그널 강도 정량화 가능.

---

### C-05. Half-Kelly 포지션 크기 조정 (Half-Kelly Bet Sizing)

- **정의**: Kelly Criterion의 50% 적용. 과최적화된 백테스트 SR에서 25~33% 할인 후 포지션 크기 결정. 파산 위험 감소.
- **수식**:
  ```python
  conservative_sr = backtest_sharpe * 0.75   # SR 25% 할인
  kelly_fraction  = conservative_sr / annual_vol_target
  half_kelly      = kelly_fraction * 0.5
  position_size   = int(account_value * half_kelly / close.iloc[-1])
  ```
- **출처**: Carver *Systematic Trading* Ch.11; Wikipedia Kelly | https://en.wikipedia.org/wiki/Kelly_criterion
- **Stage**: Sizing
- **버킷**: 포지션사이징
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 전략 백테스트 수익률 (SR 계산용)
- **난이도**: 중
- **ATR 연계**: 간접 — OBV 전략 SR을 walk-forward로 추정 후 Half-Kelly로 실전 포지션 크기 결정 가능.
- **종합 평가**: Phase 3 walk-forward 결과에서 SR 추정 후 이 공식으로 실전 포지션 크기 계산 권장.


---

## D. Wesley R. Gray & Jack R. Vogel — *Quantitative Momentum* (2016) — 5개

**서지**: Wesley R. Gray & Jack R. Vogel, *Quantitative Momentum: A Practitioner's Guide to Building a Momentum-Based Stock Selection System*, Wiley Finance, 2016.
**알파아키텍트**: https://alphaarchitect.com/
**Wiley**: https://www.wiley.com/en-us/Quantitative+Momentum-p-9781119237198

---

### D-01. 12-1 모멘텀 팩터 (12-1 Momentum Factor — Skip-Last-Month)

- **정의**: 12개월 전 ~ 1개월 전의 수익률 계산. 단기 역전(1개월 평균회귀)을 제거한 중기 모멘텀 순수 측정.
- **수식**:
  ```python
  price_12m_ago = close.shift(252)      # 약 12개월 전 (252 거래일)
  price_1m_ago  = close.shift(21)       # 약 1개월 전  (21 거래일)
  momentum_12_1 = (price_1m_ago / price_12m_ago) - 1   # 12~1개월 수익률
  momentum_rank = momentum_12_1.rank(pct=True)
  entry_filter  = momentum_rank > 0.80  # 상위 20%
  ```
- **출처**: Gray & Vogel *Quantitative Momentum* Ch.4; Jegadeesh & Titman (1993) "Returns to Buying Winners"; Validea | https://www.validea.com/wesley-gray; Bookey | https://www.bookey.app/book/quantitative-momentum
- **Stage**: Filter (종목 선별)
- **버킷**: 모멘텀
- **한국 적용**: 직접 적용 — 5.4년치 일봉 데이터로 12개월 모멘텀 계산 완전 가능. 한국 시장 모멘텀 이상현상(아노말리) 학술적 확인됨 (KOSPI200 서브유니버스, arXiv:1211.6517).
- **PIT 안전도**: 안전 — shift(252)와 shift(21) 모두 과거 데이터만 사용
- **데이터 요건**: 일봉 종가 273일+ (252+21)
- **난이도**: 하
- **ATR 연계**: 없음
- **종합 평가**: **즉시 코드화 Top 3.** 3줄 구현. Clenow A-01(복잡한 회귀 기반)의 단순화 대안. 월별 리밸런싱 스크리너에 즉시 통합 가능.

---

### D-02. Frog-in-Pan (FIP) — 일관성 기반 모멘텀 품질 (Momentum Quality Score)

- **정의**: 동일한 수익률이라도 서서히 꾸준히 오른 종목(지속적 정보)이 급등락 종목(불연속 정보)보다 미래 수익률 우수. FIP = 점진적 상승 정도 측정.
- **수식**:
  ```python
  # 방법 1: 부호 일관성 (Frog-in-Pan Index)
  daily_returns = close.pct_change()
  lookback_ret  = daily_returns.iloc[-252:-21]    # 12~1개월 구간
  pct_positive  = (lookback_ret > 0).mean()
  pct_negative  = (lookback_ret < 0).mean()
  FIP = np.sign(momentum_12_1) * (pct_negative - pct_positive)
  # FIP < 0 → 꾸준히 상승 (선호) | FIP > 0 → 들쭉날쭉 (비선호)

  # 방법 2: 수익률 / 평균 절대 일간 수익률
  FIP_v2 = momentum_12_1 / lookback_ret.abs().mean()
  # 높을수록 "조용한 상승" — 선호
  ```
- **출처**: Gray & Vogel *Quantitative Momentum* Ch.6; AlphaArchitect | https://alphaarchitect.com/frog-in-the-pan-identifying-the-highest-quality-momentum-stocks/; Medium FIP | https://medium.com/@alphaarchitect/frog-in-the-pan-momentum-international-evidence-233a19ad46b9
- **Stage**: Filter (모멘텀 품질 필터)
- **버킷**: 모멘텀
- **한국 적용**: 직접 적용 — 일봉 종가만 필요. 한국 시장에서 급등주(이슈 테마주) vs 꾸준한 실적주를 구분하는 데 유효.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 252일+
- **난이도**: 하
- **ATR 연계**: 간접 — FIP 높은 종목(꾸준한 상승)은 ATR 변동폭이 작아 ATR 기반 손절이 더 타이트하게 작동 → 위험/수익 개선.
- **종합 평가**: D-01(12-1 모멘텀) 후 품질 필터로 적용. "같은 수익률이면 꾸준히 오른 것을 택함"이라는 직관적 원칙. daily_prices 테이블로 즉시 계산 가능.

---

### D-03. 모멘텀 계절성 — 1월 효과 회피 (Momentum Seasonality — January Effect Avoidance)

- **정의**: 12-1 모멘텀은 1월에 역전(패자가 승자, 승자가 패자)되는 경향. 1월 포트폴리오 회전 자제 또는 12월에 미리 교체.
- **수식**:
  ```python
  from datetime import datetime
  current_month = datetime.now().month
  if current_month == 1:
      rebalance = False            # 1월 리밸런싱 자제
  elif current_month == 12:
      rebalance = True             # 12월 미리 교체 (1월 효과 선취)
  ```
- **출처**: Gray & Vogel *Quantitative Momentum* Ch.7; Jegadeesh & Titman (1993) JoF 원본
- **Stage**: Filter (리밸런싱 타이밍)
- **버킷**: 모멘텀
- **한국 적용**: 직접 적용 — 한국 시장에서도 1월 효과 존재 (소형주 중심). 07_calendar.md J-03 "1월 효과"와 연계.
- **PIT 안전도**: 안전
- **데이터 요건**: 없음 (날짜 조건만)
- **난이도**: 하
- **ATR 연계**: 없음
- **종합 평가**: 07_calendar.md와 교차 참조. 모멘텀 전략에 1월 예외 처리 2줄 추가로 즉시 적용.

---

### D-04. 모멘텀 + 밸류 결합 (Momentum + Value Combo — 50/50 Portfolio)

- **정의**: 모멘텀 포트폴리오(상위 20%)와 밸류 포트폴리오(PBR/PER 하위)를 50:50으로 결합. 각각의 부진 시기를 상호 보완.
- **수식**:
  ```python
  momentum_top = momentum_12_1.rank(pct=True) > 0.80
  value_top    = pbr.rank(pct=True) < 0.20          # PBR 하위 20%
  # 교집합 가중치 상향
  both_signals = momentum_top & value_top
  # 50/50 결합 포트폴리오
  weight_mom  = 0.5
  weight_val  = 0.5
  ```
- **출처**: Gray & Vogel *Quantitative Momentum* Ch.9; Wiley | https://www.wiley.com/en-us/Quantitative+Momentum-p-9781119237198
- **Stage**: Filter
- **버킷**: 모멘텀 + 평균회귀
- **한국 적용**: 직접 적용 — financial_data 테이블(PBR/PER) + daily_prices(모멘텀) 조합으로 구현. quant_factors 테이블 연계 가능.
- **PIT 안전도**: 안전
- **데이터 요건**: PBR/PER 재무 데이터 + 일봉 종가
- **난이도**: 중
- **ATR 연계**: 없음
- **종합 평가**: LynchStrategy/SawkamiStrategy의 가치 필터 + 모멘텀 결합. 06_fundamentals.md 재무 시그널과 통합 가능.

---

### D-05. 상대 모멘텀 — 섹터 조정 (Sector-Adjusted Relative Momentum)

- **정의**: 종목 모멘텀에서 섹터 평균 모멘텀을 차감. 섹터 전체 상승보다 섹터 내 초과 성과를 선별.
- **수식**:
  ```python
  # 섹터별 평균 모멘텀 계산
  sector_avg = df.groupby('sector')['momentum_12_1'].transform('mean')
  sector_adj_momentum = df['momentum_12_1'] - sector_avg
  # 섹터 조정 모멘텀 상위 20% 선택
  entry_filter = sector_adj_momentum.rank(pct=True) > 0.80
  ```
- **출처**: Gray & Vogel *Quantitative Momentum* Ch.5; AlphaArchitect | https://alphaarchitect.com/quantitative-momentum-a-guide-to-momentum-based-stock-selection/
- **Stage**: Filter
- **버킷**: 모멘텀
- **한국 적용**: 직접 적용 — KRX 섹터 분류 필요. 반도체 섹터 전체 상승 국면에서 섹터 대비 초과 종목만 선별.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉 종가 + 섹터 분류 데이터
- **난이도**: 중
- **ATR 연계**: 없음
- **종합 평가**: D-01보다 시장/섹터 베타 중립적. 2025~2026 AI/반도체 테마 랠리에서 섹터 내 진짜 강자 선별에 유효.


---

## E. Marcos Lopez de Prado — *Advances in Financial Machine Learning* (2018) — 5개

**서지**: Marcos Lopez de Prado, *Advances in Financial Machine Learning*, Wiley, 2018.
**공식 구현**: mlfinlab (Hudson & Thames) | https://hudsonthames.org/
**한국 시장 적용 논문**: https://arxiv.org/pdf/2504.02249

---

### E-01. Triple Barrier 라벨링 (Triple Barrier Method)

- **정의**: 각 진입 시점마다 3개 장벽(상단 TP, 하단 SL, 수평 시간 만료) 중 어느 것을 먼저 터치하는지로 레이블(-1/0/+1) 생성. 고정 보유기간 대신 변동성 적응형 라벨링.
- **수식**:
  ```python
  def triple_barrier_label(close, t0, atr, tp_mult=2.0, sl_mult=2.0, horizon=5):
      upper = close[t0] + tp_mult * atr[t0]   # TP 장벽
      lower = close[t0] - sl_mult * atr[t0]   # SL 장벽 (터틀 2N 손절과 동일)
      label = 0  # 기본: 시간 만료
      for t in range(t0+1, min(t0+horizon+1, len(close))):
          if close[t] >= upper: return +1   # TP 도달
          if close[t] <= lower: return -1   # SL 발동
      return label
  ```
  ATR 기반 장벽: `upper = entry + 2*ATR, lower = entry - 2*ATR, expiry = t0 + 5d`
- **출처**: Lopez de Prado *AFML* Ch.3; Quantreo | https://www.newsletter.quantreo.com/p/the-triple-barrier-labeling-of-marco; Hudson & Thames | https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/; 한국 시장 논문 | https://arxiv.org/pdf/2504.02249
- **Stage**: Exit (라벨 기반 청산 규칙)
- **버킷**: 추세추종
- **한국 적용**: 직접 적용 — 한국 시장 Triple Barrier 적용 논문 존재 (arXiv 2504.02249). OBV + daily_prices로 라벨 생성 가능.
- **PIT 안전도**: 안전 — t0 기준 장벽 설정, 실제 가격 경로로 판단. 미래 바 미참조.
- **데이터 요건**: 일봉 종가 + ATR (분봉으로 더 정확하나 일봉도 가능)
- **난이도**: 중
- **ATR 연계**: **핵심 연계 — ATR 기반 Triple Barrier가 architect 권고 OBV ATR adaptive SL의 완전한 구현체.** `lower = entry - 2*ATR` 구조가 v2_diagnosis.md P1 패치(SL=-5/-7/-10%)의 이론적 근거. OBV 시그널에 Triple Barrier 적용 시 고정 SL% 대신 변동성 기반 동적 SL 달성.
- **종합 평가**: **즉시 코드화 Top 3. OBV ATR adaptive SL 재설계의 핵심 구현 패턴.** v2 Stage A 평가 스크립트에서 SL_GRID를 고정값 대신 `2*ATR`로 교체하는 직접 근거 제공.

---

### E-02. CUSUM 이벤트 샘플링 (CUSUM Filter for Event-Based Sampling)

- **정의**: 누적합 통계로 가격이 기대값에서 유의미하게 이탈한 시점만 샘플링. 시간 기반(매일) 대신 사건 기반으로 시그널 생성.
- **수식**:
  ```python
  def cusum_filter(close, threshold):
      """threshold: 예) 1*ATR 또는 1*std"""
      S_plus, S_minus = 0.0, 0.0
      events = []
      for t in range(1, len(close)):
          delta = np.log(close[t]) - np.log(close[t-1])
          S_plus  = max(0, S_plus  + delta)
          S_minus = min(0, S_minus + delta)
          if S_plus  >= threshold:  events.append((t, +1)); S_plus  = 0
          if S_minus <= -threshold: events.append((t, -1)); S_minus = 0
      return events
  ```
- **출처**: Lopez de Prado *AFML* Ch.2; ReasonableDeviations | https://reasonabledeviations.com/notes/adv_fin_ml/; mlfinlab | https://mlfinpy.readthedocs.io/en/latest/Labelling.html
- **Stage**: Entry (진입 타이밍 선별)
- **버킷**: 추세추종
- **한국 적용**: 직접 적용 — CUSUM 이벤트를 OBV 시그널 확인 트리거로 활용. 매 9초 재계산 대신 의미 있는 가격 이탈 시에만 시그널 재계산.
- **PIT 안전도**: 안전
- **데이터 요건**: 일봉/분봉 종가
- **난이도**: 중
- **ATR 연계**: 간접 — threshold를 ATR로 설정 시 변동성 적응형 이벤트 샘플링. OBV slope 재계산 트리거를 CUSUM 이벤트 발생 시로 제한 가능.
- **종합 평가**: on_tick 루프에서 매 9초 OBV 재계산 대신 CUSUM 이벤트 발생 시에만 재계산 → 연산 최적화 + 노이즈 감소.

---

### E-03. 메타-라벨링 (Meta-Labeling)

- **정의**: 1차 모델(방향 예측, 높은 재현율)이 매수 신호를 내면 2차 이진 분류 모델이 "실제로 진입할지" 결정. 정밀도와 재현율 분리.
- **수식**:
  ```python
  # Stage 1: 기본 시그널 (OBV, MA크로스 등 — 높은 재현율)
  primary_signal = obv_strategy.generate_signal(stock_code, data)

  # Stage 2: 메타-모델 (기계학습 이진 분류기)
  if primary_signal and primary_signal.signal_type in [BUY, STRONG_BUY]:
      features = {
          'regime': current_regime,
          'atr_ratio': ATR_20 / close,
          'fip': compute_fip(close),
          'momentum_12_1': compute_momentum(close),
      }
      meta_prob = meta_clf.predict_proba([list(features.values())])[0][1]
      if meta_prob >= 0.6:
          execute_buy()   # 2차 모델 승인시만 실행
  ```
- **출처**: Lopez de Prado *AFML* Ch.3; Hudson & Thames | https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/; ReasonableDeviations | https://reasonabledeviations.com/notes/adv_fin_ml/
- **Stage**: Filter (2차 확인)
- **버킷**: 모멘텀
- **한국 적용**: 직접 적용 — OBV/VWAP 시그널을 1차 모델로, 레짐/ATR/FIP 등을 피처로 한 분류기를 2차 모델로 구성 가능.
- **PIT 안전도**: 주의 — 훈련 데이터 구성 시 Triple Barrier 라벨 사용 필수 (미래 라벨 사용 금지).
- **데이터 요건**: Triple Barrier 라벨 히스토리 + 피처 히스토리
- **난이도**: 상 (ML 파이프라인 필요)
- **ATR 연계**: 연계 — ATR, regime, FIP를 메타-모델 피처로 사용. 2차 모델이 "ATR 크면 SL 발동 위험 높음" 학습 가능.
- **종합 평가**: 장기 목표. Phase 2a 필터 조합이 자연스러운 1차 모델. scikit-learn LogisticRegression으로 빠른 프로토타입 가능.

---

### E-04. 분수 미분 (Fractional Differentiation — Memory-Preserving Stationarity)

- **정의**: 정수 차분(d=1)은 기억을 파괴하지만, 분수 차분(d=0.3~0.5)은 정상성을 달성하면서 예측 정보 보존. ML 피처 엔지니어링 전처리 기법.
- **수식**:
  ```python
  def frac_diff(series, d, thres=0.01):
      """d: 0~1 사이 분수, thres: 유효 가중치 최소값"""
      # 가중치 계산: w_k = -(d-k+1)/k * w_{k-1}, w_0=1
      w = [1.0]
      k = 1
      while abs(w[-1]) > thres:
          w.append(-w[-1] * (d - k + 1) / k)
          k += 1
      width = len(w)
      result = pd.Series(index=series.index, dtype=float)
      for i in range(width, len(series)):
          result.iloc[i] = sum(w[j] * series.iloc[i-j] for j in range(width))
      return result.dropna()
  # d를 ADF 테스트로 최소값 탐색 (stationarity 달성 최소 d)
  ```
- **출처**: Lopez de Prado *AFML* Ch.5; ReasonableDeviations | https://reasonabledeviations.com/notes/adv_fin_ml/; mlfinlab | https://mlfinpy.readthedocs.io/en/latest/Labelling.html
- **Stage**: Filter (피처 전처리)
- **버킷**: 평균회귀
- **한국 적용**: 직접 적용 — daily_prices 종가 시리즈에 적용 후 ML 피처로 활용.
- **PIT 안전도**: 안전 — 과거 가중합만 사용
- **데이터 요건**: 일봉 종가 시계열 (길수록 좋음)
- **난이도**: 상 (수학적 이해 + numpy 구현 필요)
- **ATR 연계**: 없음
- **종합 평가**: ML 파이프라인 도입 시 가격 피처 전처리 표준으로 채택. 단기보다 장기 목표.

---

### E-05. 사건 기반 Bet Sizing — Kelly 변형 (Event-Based Bet Sizing)

- **정의**: ML 분류기 출력(확률값)을 Kelly Criterion에 입력해 최적 포지션 크기 결정. 신뢰도 높은 신호에 더 큰 베팅.
- **수식**:
  ```python
  # 분류기 예측 확률 → 베팅 크기
  p = meta_clf.predict_proba(features)[0][1]   # 매수 확률
  # 이진 Kelly: f = 2p - 1
  kelly_f  = 2 * p - 1
  # Half-Kelly + clip
  bet_size = np.clip(kelly_f * 0.5, -1, 1)    # -1 ~ +1 스케일
  # 포지션 크기 = bet_size × ATR 기반 기준 포지션(A-02)
  position = int(bet_size * base_shares)

  # 단순화 버전 (E-03 없이도 즉시 사용):
  # OBV confidence(0~100) → bet_size
  bet_size_simple = (confidence / 100 * 2 - 1) * 0.5
  # confidence=80 → bet_size=0.3, confidence=90 → bet_size=0.4
  ```
- **출처**: Lopez de Prado *AFML* Ch.10; MQL5 베팅 사이징 | https://www.mql5.com/en/articles/21824; Wikipedia Kelly | https://en.wikipedia.org/wiki/Kelly_criterion
- **Stage**: Sizing
- **버킷**: 포지션사이징
- **한국 적용**: 직접 적용
- **PIT 안전도**: 안전
- **데이터 요건**: 메타-모델 예측 확률 또는 OBV confidence 값
- **난이도**: 중 (단순화 버전은 하)
- **ATR 연계**: **연계 — bet_size(확률 기반) × base_position(ATR 기반, A-02/C-02) 조합이 신뢰도×변동성 이중 조정 포지션사이징.** `position = bet_size * (risk_budget / ATR_20)` 형태로 통합.
- **종합 평가**: E-03(메타-라벨링) 없이도 OBV confidence를 p로 사용해 단순화 버전 즉시 적용 가능. confidence 90 → 포지션 40%, confidence 80 → 30%로 차등 배분.


---

## 종합 통계

| 카테고리 | 컨셉 수 | PIT 안전 | 주의/위험 | 즉시 코드화 |
|---|---|---|---|---|
| A. Clenow Stocks on the Move | 5 | 5 | 0 | 3 (A-01, A-02, A-03) |
| B. 거북이 Way of the Turtle | 5 | 5 | 0 | 3 (B-01, B-02, B-04) |
| C. Carver Systematic Trading | 5 | 5 | 0 | 2 (C-01, C-02) |
| D. Gray/Vogel Quant Momentum | 5 | 5 | 0 | 3 (D-01, D-02, D-03) |
| E. Lopez de Prado AFML | 5 | 4 | 1 (E-03 주의) | 1 (E-01) |
| **합계** | **25** | **24** | **1** | **12** |

---

## ATR Adaptive SL 연계 컨셉 요약 (architect 권고 대응)

> 참고: v2_diagnosis.md Section 3(b) — OBV ATR adaptive SL 재설계 권고

| 컨셉 | 연계 내용 | 우선순위 |
|---|---|---|
| **B-02. 터틀 2N 손절** | `stop = entry - 2*ATR_20` — architect 권고의 원형. Signal.stop_loss에 즉시 이식 가능 | **최고** |
| **E-01. Triple Barrier** | `lower = entry - 2*ATR` 구조가 v2 SL grid P1 패치의 이론적 근거. 동적 SL의 완전한 구현 | **높음** |
| **A-02. Clenow ATR 사이징** | `shares = risk_budget / ATR_20` — 포지션 크기 + SL 동시 결정. OBV PositionSizer 이식 대상 | **높음** |
| **C-02. 변동성 타겟팅** | ATR 기반 포지션사이징의 포트폴리오 레벨 버전. FundManager 업그레이드 경로 | 중 |
| **E-05. Bet Sizing** | OBV confidence → 베팅 크기 변환. `bet_size = (conf/100*2-1)*0.5` 간소화 즉시 적용 가능 | 중 |
| **A-01. Clenow 스코어** | R² 가중으로 들쭉날쭉 종목 제거 → ATR 손절 효율 개선 (노이즈 감소 효과) | 낮음 |

---

## 즉시 코드화 Top 3

1. **D-01. 12-1 모멘텀 팩터** — `(close.shift(21) / close.shift(252)) - 1`. 3줄 구현. screener_snapshots 기반 주간 스크리너에 즉시 통합. 신뢰도: 학술 검증 + 한국 시장 실증 (arXiv:1211.6517).

2. **B-02. 터틀 2N 손절 (ATR adaptive SL)** — `stop_loss = entry_price - 2 * ATR(20)`. Signal.stop_loss 필드에 직접 주입. v2_diagnosis.md SL grid 재조정(P1 패치)의 이론적 근거이자 OBV adaptive SL 재설계의 핵심 구현.

3. **A-02. Clenow ATR 포지션 사이징** — `shares = floor(account * 0.001 / ATR_20)`. PositionSizer 또는 FundManager에 4줄 추가. 현재 고정 비율 사이징을 변동성 적응형으로 즉시 교체 가능.

---

## Stage 분포

| Stage | 컨셉 수 | 대표 컨셉 |
|---|---|---|
| Entry | 5 | B-01, B-03, B-04, C-01, E-02 |
| Exit | 3 | B-02, B-04, E-01 |
| Filter | 11 | A-01, A-03, A-04, A-05, C-04, D-01~D-05, E-03 |
| Sizing | 6 | A-02, B-03(파생), B-05, C-02, C-03, C-05, E-05 |

---

## 한국 시장 적용성 요약

| 적용 수준 | 컨셉 수 | 이유 |
|---|---|---|
| 직접 적용 | 21 | 수식이 가격/거래량/ATR 기반 — 시장 무관 |
| 제한적 | 3 | A-05(리밸런싱 비용), B-03(레버리지 제한), E-03(ML 데이터 구축 필요) |
| 한국 전용 | 0 | — |

**한국 시장 특이 주의사항**:
- S&P500 우주 → KOSPI200 또는 유동성 상위 500종목으로 대체 (A-01, A-05)
- 거래비용 0.3% 고려 — Clenow risk_factor를 0.0005로 보수적 설정 (A-02)
- 12-1 모멘텀 한국 유효성: KOSPI200 서브유니버스에서 확인됨, 대형주에서 모멘텀 효과 일부 약화 (arXiv:1211.6517)
- ATR 2N 손절: 한국 호가 단위 반올림 필수 (`price_utils.round_to_tick()`)

---

## 데이터 자산 매핑

| 컨셉 그룹 | 필요 데이터 | 현재 자산 |
|---|---|---|
| A-01~A-05 (Clenow) | 일봉 종가 90~200일+ | daily_prices — 5.4년치 충분 |
| B-01~B-05 (거북이) | 일봉 고가·저가·종가 20~55일+ | daily_prices 충분 |
| C-01~C-05 (Carver) | 일봉 종가 36~256일+ | daily_prices 충분 |
| D-01~D-05 (Quant Mom) | 일봉 종가 252일+ + 재무(PBR/PER) | daily_prices + financial_data 충분 |
| E-01~E-05 (AFML) | 일봉 종가 + ATR + ML 피처 | daily_prices 충분 (ML 인프라 추가 필요) |

---

## 참고 출처 URL 모음

| 문서/도구 | URL |
|---|---|
| Clenow Stocks on the Move (Amazon) | https://www.amazon.com/Stocks-Move-Beating-Momentum-Strategies/dp/1511466146 |
| Clenow 공식 사이트 | https://www.followingthetrend.com/stocks-on-the-move/ |
| TuringTrader Clenow 요약 | https://www.turingtrader.com/portfolios/clenow-stocks-on-the-move/ |
| Teddy Koker Clenow Python 구현 | https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/ |
| QuantConnect Clenow 포럼 | https://www.quantconnect.com/forum/discussion/10493/ |
| QuantConnect Clenow 전략 | https://www.quantconnect.com/forum/discussion/16578/ |
| Quant-Investing Clenow 인터뷰 | https://www.quant-investing.com/blog/more-insights-from-andreas-clenow-author-of-stocks-on-the-move-beating-the-market-with-hedge-fund-momentum-strategies |
| Bookey Stocks on the Move 요약 | https://www.bookey.app/book/stocks-on-the-move |
| Clenow Following the Trend 시스템 규칙 | https://www.followingthetrend.com/the-trading-system/trading-system-rules/ |
| Altrady 터틀 규칙 | https://www.altrady.com/blog/crypto-trading-strategies/turtle-trading-strategy-rules |
| Alchemy Markets 터틀 가이드 | https://alchemymarkets.com/education/strategies/turtle-trading-guide/ |
| EBC 터틀 전략 | https://www.ebc.com/forex/turtle-trading-strategy-explained-a-beginners-guide |
| Medium 터틀 규칙 해설 | https://medium.com/@trading.dude/discipline-over-prediction-why-the-turtle-trading-rules-still-matter-f0f1d400d58d |
| Carver 출판사 Harriman House | https://www.harriman-house.com/systematic-trading |
| 7Circles Carver 변동성 타겟팅 | https://the7circles.uk/systematic-trading-4-volatility-targeting-and-position-sizing/ |
| 7Circles Carver 예측 프레임워크 | https://the7circles.uk/systematic-trading-3-frameworks-and-forecasts/ |
| Carver 저자 블로그 (EWMAC Python) | https://qoppac.blogspot.com/2015/09/python-code-for-two-trading-rules-in.html |
| Carver 저자 블로그 (추가 규칙) | https://qoppac.blogspot.com/2017/06/some-more-trading-rules.html |
| TopTradersUnplugged Carver 팟캐스트 | https://www.toptradersunplugged.com/podcast/when-position-sizing-saves-you-ft-rob-carver |
| Wiley Quantitative Momentum | https://www.wiley.com/en-us/Quantitative+Momentum-p-9781119237198 |
| AlphaArchitect Quant Momentum 가이드 | https://alphaarchitect.com/quantitative-momentum-a-guide-to-momentum-based-stock-selection/ |
| AlphaArchitect FIP 논문 | https://alphaarchitect.com/frog-in-the-pan-identifying-the-highest-quality-momentum-stocks/ |
| AlphaArchitect FIP 최신 분석 | https://alphaarchitect.com/what-explains-the-momentum-factor-frog-in-the-pan-is-still-the-king/ |
| Medium FIP 국제 증거 | https://medium.com/@alphaarchitect/frog-in-the-pan-momentum-international-evidence-233a19ad46b9 |
| Validea Gray 전략 요약 | https://www.validea.com/wesley-gray |
| Bookey Quantitative Momentum 요약 | https://www.bookey.app/book/quantitative-momentum |
| KOSPI 모멘텀 우주 축소 논문 | https://arxiv.org/abs/1211.6517 |
| Lopez de Prado AFML Bonus PDF | https://gildan-bonus-content.s3.amazonaws.com/GIL2476_AdvancesFinancial/GIL2476_AdvancesFinancial_BonusPDF.pdf |
| ReasonableDeviations AFML 노트 | https://reasonabledeviations.com/notes/adv_fin_ml/ |
| Hudson & Thames Meta-Labeling 분석 | https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/ |
| Quantreo Triple Barrier 해설 | https://www.newsletter.quantreo.com/p/the-triple-barrier-labeling-of-marco |
| mlfinlab Labelling 문서 | https://mlfinpy.readthedocs.io/en/latest/Labelling.html |
| 한국 시장 Triple Barrier 논문 | https://arxiv.org/pdf/2504.02249 |
| Wikipedia Kelly Criterion | https://en.wikipedia.org/wiki/Kelly_criterion |
| MQL5 Bet Sizing 구현 | https://www.mql5.com/en/articles/21824 |
| LuxAlgo ATR Dynamic SL | https://www.luxalgo.com/blog/average-true-range-dynamic-stop-loss-levels/ |

---

*출력 파일*: `RoboTrader_template/reports/10pct_strategy/phase5_signals/11_systematic.md`
*연관 파일*: `03_trendlines_sr.md` (형식 기준), `v2_diagnosis.md` (ATR adaptive SL 재설계 컨텍스트), `07_calendar.md` (모멘텀 계절성 교차 참조), `06_fundamentals.md` (모멘텀+밸류 결합 교차 참조)
