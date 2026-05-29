# Elder Triple Screen Trading System — 조사 노트

> Book: Alexander Elder — *Trading for a Living* (Wiley, 1993) / *The New Trading for a Living* (Wiley, 2014)
> 보조: *Come Into My Trading Room* (Wiley, 2002) — Impulse System, 2%/6% 자금관리 룰
> 조사 시작: 2026-05-29
> 설계: docs/superpowers/specs/2026-05-3x-elder-triple-screen-design.md (Phase 2에서 작성 예정)

---

## 1. 핵심 개념

**Triple Screen** = 서로 다른 3개의 시간프레임(주봉/일봉/장중)을 차례로 통과시키는 다중 필터 매매 시스템. Robert Rhea의 다우 이론 "조류(tide) / 파도(wave) / 잔물결(ripple)" 비유를 그대로 차용한다.

핵심 통찰: **단일 시간프레임은 함정**이다 — 같은 지표가 한 시간프레임에서는 매수, 다른 시간프레임에서는 매도를 동시에 가리키기 때문. 해결책은 **긴 시간프레임으로 추세를 정의하고 그 방향으로만 매매하되, 짧은 시간프레임에서 추세에 *역행하는* 되돌림이 나올 때 진입**하는 것 ("상승장에서는 눌림목을 사고, 하락장에서는 반등을 판다").

| 시간프레임 | 비유 | Triple Screen 역할 |
|-----------|------|-------------------|
| 긴 시간 (주봉) | 조류 (Tide) | Screen 1 — 추세 방향 결정 (매수만/매도만 허가) |
| 중간 시간 (일봉) | 파도 (Wave) | Screen 2 — 추세 역행 되돌림(오실레이터 과매도/과매수) 포착 |
| 짧은 시간 (장중) | 잔물결 (Ripple) | Screen 3 — 추세 재개 돌파 시 진입 (trailing stop) |

**Factor-of-5 규칙**: 각 시간프레임은 다음 프레임과 약 5배 관계. 매매 기준 프레임(일봉)을 정한 뒤 ×5 → Screen 1(주봉, 5거래일), ÷5 → Screen 3(약 1.5시간/장중). Elder는 "intermediate-first"로 설명: 중간 프레임을 먼저 고르고 위·아래로 5배씩 확장.

---

## 2. 세 화면(Screen) 정의

### Screen 1 — 추세 / 조류 (주봉)

| 판 | 지표 | "상승" 판정 (매수만 허가) | "하락" 판정 (매도만 허가) |
|----|------|--------------------------|--------------------------|
| **1993 (원전)** | 주봉 **MACD-Histogram 기울기** | `Hist[t] > Hist[t-1]` (직전 봉 대비 상승) | `Hist[t] < Hist[t-1]` |
| **2014 (개정)** | 주봉 **EMA 기울기 (26주/13주)** + **Impulse System** | EMA 상승 / Impulse 녹색·청색 | EMA 하락 / Impulse 적색 |

- **핵심 주의**: 1993판은 히스토그램의 *절대 부호*(0 위/아래)가 아니라 *기울기*(방향 변화)가 신호. 단 1봉의 방향 전환만으로 추세 판정이 뒤집힘 (다중봉 확인 불필요).
- 2014판에서 Elder는 주봉 MACD-Histogram이 "너무 민감(jittery)"하다며 **EMA 기울기**로 교체. 커뮤니티 다수가 26주(주력)·13주(보조) EMA 기울기 인용.
- 한국 적용 시: "하락" 판정 = 공매도 불가 → **관망/청산만** (매도 진입 없음).

### Screen 2 — 오실레이터 / 파도 (일봉)

Screen 1이 방향을 정하면, Screen 2는 일봉 오실레이터로 **추세 역행 되돌림**을 찾는다. Screen 1이 오실레이터 신호를 *검열*: 주봉 상승 시 매수 신호만 취하고 매도 신호는 무시.

| 오실레이터 | 매수 구간 (주봉 상승 시) | 등급 |
|-----------|------------------------|------|
| **Force Index (2일 EMA)** — Elder 선호 | 2일 FI가 **0 미만(음수)** 전환 | A |
| **Stochastic** | **30 미만**(과매도, 대안 20) + 반등 | A/B |
| **Elder-Ray** | **Bear Power 음수이나 상승 전환** (+ EMA13 상승) | A |
| **Williams %R** | **−80 미만**(과매도) | A/B |
| **RSI** | 과매도(예: <30) | A (임계값 C) |

- Elder는 오실레이터를 *상호 교체 가능*으로 제시 — 1개를 강제하지 않음. **Force Index(2일 EMA)가 시연 기본값**, Stochastic이 커뮤니티 최다 선택.

### Screen 3 — 진입 / 잔물결 (장중→일봉 근사)

**Trailing buy-stop**: 추세 재개 돌파를 포착.
- **롱 진입** (주봉 상승 + 일봉 과매도): **전일 고가 +1틱**에 매수 스톱 설정.
  - 가격이 더 하락해 스톱 미체결 시, 다음날 스톱을 그날 (더 낮은) 고가 +1틱으로 **하향 추적**. 체결되거나(상승 돌파→롱) 주봉 추세 반전(주문 취소) 때까지 매일 추적.
- "1틱" = 종목 가격대의 KRX 최소 호가 단위.

---

## 3. 지표 공식 (Python/pandas 코드화 기준)

> 공통 주의: Elder 지표는 모두 EMA 기반이며 `α = 2/(N+1)`. pandas에서 **반드시 `ewm(span=N, adjust=False)`** 사용 (`adjust=True` 기본값은 차팅 패키지·Elder 값과 불일치). 히스토그램 의존 지표는 ~35봉+ warmup 후 신뢰.

### 3a. MACD / MACD-Histogram
```
MACD   = EMA(close,12) - EMA(close,26)
Signal = EMA(MACD, 9)
Hist   = MACD - Signal
기울기: Hist[t] > Hist[t-1] = 상승(강세) / < = 하락(약세)   ← Elder 핵심 신호
```
- 기본 (12,26,9). 다이버전스(가격 저점↓ + Hist 저점↑ = 강세)가 Elder가 꼽는 최강 신호.

### 3b. Force Index (Elder 고유)
```
FI(1)  = (close[t] - close[t-1]) * volume[t]          # raw, 첫 행 NaN
FI(2)  = EMA(FI(1), 2)    # 단기 — 진입 타이밍
FI(13) = EMA(FI(1), 13)   # 중기 추세
```
- 상승추세 中 **FI(2) < 0** = 눌림목 매수 구간. FI(13) 0선 교차·다이버전스 = 추세 신호. raw FI로 직접 매매 금지(항상 평활).

### 3c. Elder-Ray (Bull/Bear Power)
```
Bull Power = High - EMA(close,13)
Bear Power = Low  - EMA(close,13)
```
- **매수**: EMA13 상승 AND Bear Power < 0 AND Bear Power 상승(`BearPower[t] > BearPower[t-1]`). Bear Power 양수일 때는 매수 금지(되돌림 없음=과열).

### 3d. Impulse System (2002/2014)
```
ema_up   = EMA13[t] > EMA13[t-1];   ema_down = EMA13[t] < EMA13[t-1]
hist_up  = Hist[t]  > Hist[t-1];    hist_down = Hist[t] < Hist[t-1]
GREEN = ema_up AND hist_up      # 롱 허가, 숏 금지
RED   = ema_down AND hist_down  # 숏 허가, 롱 금지
BLUE  = 그 외(혼재)             # 양방향 허가
```
- **검열(censorship) 시스템**: 무엇을 *해서는 안 되는지*를 알려줌. 녹색→청색 전환 = 롱 익절 신호.

### 3e. Stochastic
```
%K_raw = 100*(close - LL(N)) / (HH(N) - LL(N))
%K     = SMA(%K_raw, 3);   %D = SMA(%K, 3)     # SMA 평활 (EMA 아님)
```
- 일반 기본 (5,3,3) 또는 (14,3,3). **Elder는 더 긴 기간(~7+) 선호**(5는 노이즈 과다). 과매수 ≥80 / 과매도 ≤20. `HH==LL` 0除 가드 필요.

### 3f. 자금관리 (2% / 6% 룰)
- **2% 룰**: 단일 거래 최대 손실 ≤ 계좌자본 2%. `max_shares = floor(0.02*equity / |entry-stop|)`. 상한(ceiling)이지 목표 아님.
- **6% 룰**: (월 실현손실 + 전 보유 포지션 open risk) ≥ 월초 자본 6% → 그 달 신규 진입 중단. 2%×3 ≈ 동시 3포지션.

---

## 4. 진입 룰 (코드화 대상 — 롱 전용)

> 한국 개인투자자 공매도 제약 → 숏 셋업 전면 제외. "주봉"은 Screen 1 proxy(기본: 일봉 65일 EMA = 13주, §6 참조).

### Setup A — 정통 Triple Screen (MACD-Hist + Force Index)
| 화면 | 조건 |
|------|------|
| Screen 1 | 주봉/proxy **MACD-Histogram(6,13,5) 상승** (`hist[w] > hist[w-1]`) |
| Screen 2 | 일봉 **Force Index 2일 EMA < 0** (추세 역행 눌림) |
| Screen 3 | 다음날 `high[t+1] > high[t]+tick` 시 `high[t]+tick`에 체결 |

### Setup B — 주봉 EMA 상승 + 일봉 Stochastic 과매도
| 화면 | 조건 |
|------|------|
| Screen 1 | 주봉/proxy **EMA13 상승** (기울기 > 0) |
| Screen 2 | 일봉 **Stochastic %K(5,3) < 30** AND %K가 %D 상향 돌파 |
| Screen 3 | 동일 (Approx A) 또는 `open[t+1]` (Approx B) |

### Setup C — Impulse 비적색 + Elder-Ray Bear Power 상승
| 화면 | 조건 |
|------|------|
| Screen 1 | 주봉/proxy **Impulse NOT red** (녹색·청색 허가) |
| Screen 2 | 일봉 **Bear Power(=low−EMA13) < 0 AND 상승** AND 일봉 EMA13 상승 |
| Screen 3 | 다음날 고가 돌파 체결 |

### Setup D — 단순화 EMA 눌림 반등 (표본 최대화·견고성 검증)
| 화면 | 조건 |
|------|------|
| Screen 1 | 주봉/proxy **EMA13 상승** |
| Screen 2 | 일봉 **EMA13 터치** (`low[t] <= EMA13_d[t]*1.01` AND `close[t] > EMA13_d[t]`) |
| Screen 3 | `open[t+1]` 무조건 진입 (최단순·표본 최대) |

---

## 5. 청산 룰 (Variant A/B)

### Variant A (책 의도 — 추세 추종 + 오실레이터 익절)
Elder 의도: **오실레이터가 반대 극단(과매수)에 도달**하거나 **주봉 추세가 하락 반전**할 때 청산, SafeZone/ATR 스톱 + 2%/6% 자금관리.

| 항목 | 값 | 근거 |
|------|-----|------|
| sl | 0.08 (8%) 하드 플로어; 선호 동적 스톱 = SafeZone/ATR `entry - 2.5×ATR(10)` (더 타이트할 때만, 8%보다 느슨 금지) | Elder SafeZone(평균 하방침투×2~3); ATR 근사 |
| tp | 0.30 (30%) — Elder는 명시 익절 없음; 30%는 백스톱, 실질 청산은 오실레이터/추세 | Weinstein A와 정합 |
| trail | 일봉 **EMA13 이탈**(수익 후 `close < EMA13_d`) + **주봉 추세 반전**(주봉 EMA13 기울기 하향 OR 주봉 Hist 2봉 연속 하락) | "raise stops to MA" |
| oscillator exit | 진입 오실레이터 반대 극단 (Setup B: Stoch %K>80 등) | "exit fast" |
| mh | 100 거래일 | Weinstein A와 동일 |

> 2%/6%는 *포지션 사이징* 룰(진입 시 PositionSizer 적용)이지 청산 엔진 룰 아님.

### Variant B (책간 획일 기준)
| 항목 | 값 |
|------|-----|
| sl | 0.08 |
| tp | 0.12 |
| trail | 없음 |
| mh | 20 거래일 |

---

## 6. 한국 시장 적용 시 주의점

### 데이터 기간 제약 + Screen 1 warmup
- `daily_prices` 실측: 2025-07-01 ~ 2026-05-29 = **224 거래일 ≈ 44.8주**.

| 주봉 EMA | warmup | 사용가능 주봉 | 비율 |
|---------|--------|--------------|------|
| 26주 (Elder 정통) | 26 | ~18.8 | 42% ← **비현실적** |
| 13주 (권장) | 13 | ~31.8 | 71% |
| 8주 (공격적) | 8 | ~36.8 | 82% |

- **결론**: 26주 EMA + 주봉 MACD(12,26,9)는 데이터 전체를 warmup으로 소진 → 사실상 신호 0. 두 가지 완화:
  - **1안(권장·기본): 일봉 해상도 proxy.** Screen 1을 **일봉 65일 EMA(=13주×5)** 또는 130일 EMA(=26주) 기울기로 계산 → "조류"를 일봉 일수로 warmup. 65일 proxy: **159 사용가능일**, 130일: 94일.
  - **2안(진짜 주봉 유지): 13주 EMA + 주봉 MACD(6,13,5)** → ~31 사용가능 주봉.

### 시장 지수 불필요 (구조적 이점)
- Triple Screen Screen 1은 **종목 자신의 주봉 추세** 사용 → Weinstein의 Mansfield RS와 달리 **KOSPI/KOSDAQ 지수 불필요**. `daily_prices` 지수 부재 문제 완전 회피. 종목별 자기완결적 → Weinstein보다 구현 용이.

### Screen 3 일봉 해상도 근사 (no-lookahead)
- **Approx A (매수 스톱 시뮬, 권장)**: 신호일 t 다음날 t+1에서 `high[t+1] > high[t]+tick`이면 `high[t]+tick`에 체결. `open[t+1]`이 스톱 위로 갭상승 시 `open[t+1]`에 체결(현실적 갭). 미체결 시 N=2~3일 추적 후 취소. t+1 OHLC만 사용 → no-lookahead 준수.
- **Approx B (단순 대안)**: 신호일 t 다음날 `open[t+1]` 무조건 진입. 돌파 확인 필터 상실하나 무편향·단순.
- **minute_candles로 정밀 체결?** 1차 패스에서는 불필요 — Approx A가 ~1틱 오차로 매수스톱 의미 재현, 분봉은 엔진 복잡도·런타임 급증, 신뢰도 병목은 표본 크기지 체결 정밀도 아님. **최우수 룰 1개에 한해 선택적 정밀 업그레이드.**

### 공매도 셋업 제외
- Screen 1 "하락" + Screen 2 과매수 = 숏 구간 → 한국 개인 공매도 제약으로 전면 제외. 매수 셋업 4개(A/B/C/D)만 코드화.

### Universe 표준화
- `top_volume:50` (일봉 거래대금 상위 50종목) — 이전 6권과 동일 기준.

### 단일 BULL 구간 편향 (최대 리스크)
- 224일 윈도가 사실상 단일 방향 → 롱 전용 추세추종이 *인위적으로 좋아 보임*. Screen 1이 대부분 "상승"이라 주봉 필터가 거의 게이팅 안 함. 하락장 방어 검증 불가 → 모든 메트릭에 이 경고 전면 표기.

---

## 7. 셋업 카탈로그 (표)

| # | 셋업 | 코드화 | 비고 |
|---|------|--------|------|
| 1 | Setup A — MACD-Hist 상승 + Force Index(2)<0 + 고가 돌파 | O | 정통 Triple Screen |
| 2 | Setup B — 주봉 EMA13 상승 + Stochastic<30 + 돌파 | O | 커뮤니티 최다 변형 |
| 3 | Setup C — Impulse 비적색 + Bear Power 상승 + 돌파 | O | Elder-Ray 정통 트리거 |
| 4 | Setup D — 주봉 EMA13 상승 + 일봉 EMA13 터치 + open 진입 | O | 표본 최대·견고성 베이스라인 |
| 5 | 숏 셋업 (주봉 하락 + 과매수 + 저가 이탈) | X | 한국 공매도 제약 — 제외 |

**본 plan 코드화 대상 (O): 셋업 #1~#4 (총 4개)**

---

## 8. 참고 자료

### 1차 출처
- Elder, Alexander. *Trading for a Living*. Wiley, 1993. — Triple Screen 원전, MACD-Histogram·Force Index·Elder-Ray·Stochastic
- Elder, Alexander. *Come Into My Trading Room*. Wiley, 2002. — Impulse System, SafeZone, 2%/6% 룰
- Elder, Alexander. *The New Trading for a Living*. Wiley, 2014. — Screen 1 EMA 기울기 전환, Impulse System 재정리

### 2차 출처

| 제목 | URL | 주요 내용 |
|------|-----|-----------|
| QuantifiedStrategies — Triple Screen | https://www.quantifiedstrategies.com/alexander-elder-triple-screen-strategy/ | 3화면 메커니즘, 1993→2014 차이 |
| StockCharts — Elder Impulse System | https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-types/elder-impulse-system | Impulse 녹/적/청 룰 (Elder 공동 개발) |
| StockCharts — Force Index | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/force-index | FI 공식, 2일/13일 해석 |
| StockCharts — MACD-Histogram | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/macd-histogram | 기울기·다이버전스 |
| StockCharts — Chandelier Exit | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/chandelier-exit | High22−ATR22×3 (LeBeau, Elder 대중화) |
| TradingView — Bull/Bear Power | https://www.tradingview.com/support/solutions/43000717955-bull-bear-power/ | Elder-Ray 공식·해석 |
| eLearnMarkets — Triple Screen | https://blog.elearnmarkets.com/triple-screen-trading-method-alexander-elder-way-trading/ | 3화면 개요 |
| RoboForex — Triple Screen how-to | https://blog.roboforex.com/blog/2020/02/18/triple-screen-trading-system-how-to/ | Force Index/Stochastic 실전, 스톱 배치 |
| spreadsheetml — SafeZone | https://www.spreadsheetml.com/technicalindicators/SafeZone.shtml | SafeZone 공식 (lookback 10~20, 계수 2~3) |
| IncredibleCharts — 6% Rule | https://www.incrediblecharts.com/trading/6_percent_rule.php | 6% 룰 메커니즘 |
| the7circles — Trading for a Living #5 | https://the7circles.uk/trading-for-a-living-5-market-indicators-and-trading-systems/ | 1993→2014 비교 |

---

## 부록: 모호한 기준 — 코드화 임계값 후보

> Elder 원본이 명시 수치를 제시하지 않아 Phase 2 설계서에서 최종 확정 필요.

| 항목 | 책 본문 표현 | 코드화 후보 | 결정 Phase |
|------|------------|------------|-----------|
| Screen 1 판 선택 | "EMA slope... MACD too sensitive" | 양쪽 구현, 기본 = 일봉 65일 EMA proxy(2014 정신) | Phase 2 |
| Screen 1 MACD-Hist 파라미터 | "weekly MACD-Histogram" | (6,13,5) 주봉 (warmup 절감) 또는 (12,26,9) | Phase 2 |
| Screen 1 EMA 기간 | "26-/13-week EMA slope" | 일봉 65일(=13주) proxy 기본 | Phase 2 |
| Screen 1 "평탄/관망" | 미정의 | EMA 기울기 \|Δ\|<0.1% → 관망 | **C — 책 수치 없음** |
| Screen 2 기본 오실레이터 | "FI, Stochastic, Elder-Ray, %R, RSI" (교체가능) | Force Index 2일 EMA (Elder 기본) | A; 선택은 C |
| Force Index 매수 트리거 | "2-day FI turns negative" | FI(2) < 0 (상승추세 中) | A/B |
| Stochastic 임계값 | "oversold/overbought" | 30/70 (대안 20/80), %K 5~7 | B/C |
| Screen 3 "1 tick" | "one tick above prior high" | KRX 호가단위 1틱 | A; 호가표 필요 |
| Screen 3 해상도 | 장중 암시 (factor-5) | 일봉 Approx A (전일 고가 돌파) | B/C |
| 초기 스톱 | "below 2-day low" | 1틱 below 2일 저가 (또는 8%/ATR) | A/B |
| SafeZone lookback | "10~20일" | 15 (중간값) | A |
| SafeZone 계수 | "start with 2" | 2.0 (범위 2~3); ATR(10)×2.5 근사 | A |
| 청산 트리거 | "exit fast / 과매수" | Stoch>80 OR 추세 반전 OR EMA13 이탈 | A/B |

---

*Phase 1 (조사) 완료. 다음 단계: Phase 2 설계서 작성 (Screen 1 판 확정, 4개 셋업 파라미터 잠금, 백테스트 파이프라인 정의).*
