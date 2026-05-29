# Weinstein Stage Analysis — 조사 노트

> Book: Stan Weinstein — *Secrets for Profiting in Bull and Bear Markets* (McGraw-Hill, 1988)
> 조사 시작: 2026-05-29
> 설계: [docs/superpowers/specs/2026-05-29-weinstein-stages-design.md](../../../docs/superpowers/specs/) (Phase 2에서 작성 예정)

---

## 1. 핵심 개념

**Stage Analysis** = 종목의 가격 사이클을 4단계(Stage 1~4)로 분류하고, 각 단계에서 최적의 행동(매수/보유/매도/공매도)을 정의하는 트렌드 추종 프레임워크.

핵심 전제: Weinstein은 "주식의 약 70%는 언제나 횡보 중이며, 추세가 확립된 나머지 30% 안에서만 트레이딩해야 한다"고 주장한다. Stage 분석은 현재 어느 단계에 있는지를 객관적으로 판단해 그 30%를 선별하는 수단이다.

도구: **30주 단순이동평균(30W SMA)** + **거래량** + **Mansfield Relative Strength(RS)**. 주봉 차트를 기본 단위로 사용한다.

---

## 2. 4 Stage 정의 (표 형식)

| Stage | 명칭 | 가격 vs 30W MA | 30W MA 기울기 | 거래량 패턴 | Mansfield RS 패턴 | 전형적 행동 |
|-------|------|----------------|--------------|------------|-------------------|------------|
| 1 | Basing (횡보) | 가격이 MA 위아래를 혼재 | 평탄 (하락→수평 전환) | 하락 추세 동안 축소; 베이스 후반 소폭 증가 가능 | 음수 또는 0 근처 — 시장 대비 부진 | 관망 (매수 대기) |
| 2 | Advancing (상승) | 가격 > 30W MA (일관) | 상승 | 돌파 시 폭증(평균의 2~3배); 조정 시 수축 | 0 초과 → 상승 추세 | **매수·보유** |
| 3 | Top / Distribution (천장) | 가격이 MA 위아래 혼재 (횡보) | 평탄 (상승→수평 전환) | 하락일 거래량 증가 / 상승일 거래량 감소 | 하락 전환 또는 0 근처 하향 | 매도·익절 |
| 4 | Declining (하락) | 가격 < 30W MA (일관) | 하락 | 반등 시 거래량 빈약; 하락 시 증가 가능 | 음수 — 시장 대비 현저 부진 | **매도·공매도** (한국 미적용) |

**단계 전이 순서**: Stage 1 → Stage 2 → Stage 3 → Stage 4 → Stage 1 (순환)

---

## 3. 30주 단순이동평균 (30W SMA)

### 정의
30주 종가의 단순평균. Weinstein은 **주봉 차트**를 기반으로 사용한다.

- 공식: `30W_SMA(t) = mean(close(t), close(t-1), ..., close(t-29))` (주봉 29봉 이전까지 포함, 총 30개)
- 일봉 환산: **150일 SMA** ≈ 30주 SMA (주당 약 5거래일 × 30주)
  - 정확한 week resampling 방법: 일봉을 주봉으로 resample(freq='W') 후 rolling(30).mean() — 영업일 수 변동(주당 4~5일) 자동 처리
  - 단순 근사: 일봉 rolling(150).mean() — 구현 단순, 오차 미미 (±1~2일)

### 기울기 계산 방법
Weinstein 본문 정의는 "최근 MA가 이전보다 높은가/낮은가"로 시각적으로 판단. 코드화 시 두 가지 후보:

| 방법 | 공식 | Weinstein 의도 부합도 |
|------|------|----------------------|
| 단기 차분 (권장) | `slope = MA(t) - MA(t-4)` (주봉 4주 = 일봉 약 20일) | 높음 (axlfi.com 인용) |
| 기울기 부호 | `slope = MA(t) - MA(t-1)` (주봉 1주) | 노이즈 민감 |

- `slope > 0`: MA 상승 (Stage 2 조건)
- `slope ≈ 0` (예: `|slope / MA| < 0.001`): MA 평탄 (Stage 1 또는 3 조건)
- `slope < 0`: MA 하락 (Stage 4 조건)

**코드화 권장**: `ma_slope_pct = (MA150(t) - MA150(t-20)) / MA150(t-20)` → 임계값 ±0.1%로 상승/평탄/하락 분류 (후속 설계서에서 확정)

---

## 4. Mansfield Relative Strength (RS)

### 공식 (stageanalysis.net 원본)

```
RP(t) = (stock_close(t) / index_close(t)) x 100          # 표준 상대강도
MRS(t) = (RP(t) / SMA(RP, n) - 1) x 100                  # Mansfield RS
```

- `n = 52` (주봉 차트 기준)
- `n = 200` (일봉 차트 기준)
- 출처: [stageanalysis.net — Mansfield RS 생성 방법](https://www.stageanalysis.net/blog/4266/how-to-create-the-mansfield-relative-performance-indicator)

### 해석
- **MRS > 0**: 종목이 지수를 상회 (52주 이동평균 대비 현재 RP가 높음)
- **MRS < 0**: 종목이 지수를 하회
- **MRS = 0**: 지수 대비 정확히 평균 수준 (zero line)
- Stage 2 진입 조건: MRS >= 0 이고 상승 중이어야 함
- 출처: [ChartMill — Mansfield RS](https://www.chartmill.com/documentation/technical-analysis/indicators/35-Mansfield-Relative-Strength)

### 단순 근사 버전 (코드화 대안)
Mansfield RS가 계산 복잡할 경우 26주(130일) 수익률 비율로 근사 가능:

```
RS_simple(t) = stock_return_26W(t) / index_return_26W(t)
```

- `RS_simple > 1.0`: 종목이 시장 초과 수익
- Minervini 시리즈에서 사용한 12주 백분위 방식과 호환 가능

### 한국 시장 대체지수
**KOSPI200 또는 KOSPI 일봉**이 이상적이나, 현재 `daily_prices` 테이블에 KOSPI/KOSDAQ 지수 자체가 **포함되어 있지 않음** (확인: 2026-05-29 기준 321 종목, 지수 코드 없음).

대안 (우선순위 순):
1. `daily_prices`에 KOSPI 지수 데이터 별도 적재 후 활용 (Phase 2 설계서에서 결정)
2. universe top_volume:50 동일가중 평균수익률을 대체지수로 사용 (자체 생성)
3. Minervini 방식(universe 내 RS 백분위)으로 대체 (정밀도 저하, 허용 범위)

---

## 5. 진입 룰

### A. Stage 2 Initial Breakout (Stage 1→2 전환 돌파)

**룰 이름**: `weinstein_stage2_breakout`

| 요소 | 조건 | 출처 |
|------|------|------|
| Stage 조건 | Stage 1 → Stage 2 전환: MA150 기울기가 평탄→상승으로 전환 | Weinstein(1988) Ch.3 |
| 가격 조건 1 | 종가 > MA150 (150일 SMA) | 책 본문 |
| 가격 조건 2 | 종가 > Stage 1 박스 저항선 (최근 150일 최고가) | stageanalysis.net checklist |
| 거래량 조건 | 돌파일 거래량 >= 20일 평균의 2배; 주봉 기준 4주 평균의 2배 | stageanalysis.net checklist |
| RS 조건 | Mansfield RS >= 0 (또는 상승 전환) | Weinstein(1988) |

**stageanalysis.net 체크리스트 추가 조건**:
- 50일 MA 상승 중
- 가격이 MA150 위에서 형성된 최근 swing high 돌파
- 돌파 전 변동성 수축(VCP 유사 패턴) 확인 시 품질 상승
- 출처: [stageanalysis.net Breakout Quality Checklist](https://www.stageanalysis.net/blog/4372/stage-analysis-breakout-quality-checklist)

---

### B. Stage 2 Continuation Pullback (Stage 2 중 MA150 되돌림 후 재진입)

**룰 이름**: `weinstein_stage2_pullback`

| 요소 | 조건 | 출처 |
|------|------|------|
| Stage 조건 | Stage 2 진행 중 (MA150 일관 상승) | Weinstein(1988) Ch.4 |
| 가격 조건 | MA150 5% 이내 되돌림: `(close - MA150) / MA150 <= 0.05` | stageanalysis.net |
| 가격 확인 | 되돌림 후 종가가 직전 swing high 재돌파 | stageanalysis.net |
| 거래량 조건 | 되돌림 기간 거래량 수축; 재진입 시 20일 평균 이상 (배수 Weinstein 미명시 — 1.5배 후보) | stageanalysis.net |
| RS 조건 | Mansfield RS zero line 위에서 유지 | stageanalysis.net checklist |

**주의**: Weinstein 본문은 "30W MA 근처에서 기다려라"고 언급하나 정확한 % 범위는 미명시. 코드화 시 5% 임계값은 외부 커뮤니티(stageanalysis.net) 해석 기준임.

---

### C. Stage 4 Initial Breakdown (공매도 — 한국 시장 미적용)

**룰 이름**: `weinstein_stage4_breakdown` (코드화 제외)

| 요소 | 조건 |
|------|------|
| Stage 조건 | Stage 3 → Stage 4 전환: MA150 평탄→하락 전환 |
| 가격 조건 | 종가 < Stage 3 박스 지지선 돌파 |
| 거래량 조건 | 필수 아님 (short는 약한 거래량에도 진입 가능 — Weinstein 명시) |
| RS 조건 | Mansfield RS < 0 (섹터 내 약세 종목 우선) |

**한국 시장 적용 불가 근거**: 한국 주식시장의 공매도는 기관·외국인 위주로 제한되며, 개인투자자의 공매도는 증거금 요건·대차 조달 어려움으로 사실상 불가. 본 백테스트 시리즈에서 short 셋업 전면 제외.

---

### D. Stage 4 Continuation Bounce (공매도 — 한국 시장 미적용)

**룰 이름**: `weinstein_stage4_bounce` (코드화 제외)

| 요소 | 조건 |
|------|------|
| Stage 조건 | Stage 4 하락 진행 중 |
| 가격 조건 | 반등 후 MA150 또는 이전 지지선(현재 저항선) 아래에서 재하락 |
| 거래량 조건 | 반등 거래량 빈약; 재하락 시 증가 |
| 스톱 배치 | 초기: 직전 고점 위. 8% 반등 후 이전 저점 복귀 시 스톱을 MA150 위로 이동 |

동상 이유로 한국 시장 적용 제외.

---

## 6. 청산 룰 (Variant A/B)

### Variant A (책 의도 — Stage 추세 추종)

| 항목 | 값 | 근거 |
|------|-----|------|
| sl | 0.08 (8%) — 초기 스톱: 돌파 기준점 바로 아래, 최대 15% 미만 | Weinstein(1988): "stop just below the breakout level" |
| tp | 0.30 (30%) — Weinstein 원본은 명시적 목표 없음; Stage 3 진입까지 보유 의도 | 장기 추세 추종 가정 해석 |
| trail | MA150 이탈: 종가 < MA150 | Weinstein(1988): "raise stops to just below the 30-week MA" |
| mh | 100 거래일 (≈ 20주) | 주봉 기준 20주 = 일봉 100봉 |

**트레일링 스톱 상세 (Weinstein 원문)**:
- Stage 2 진행 중: 조정→회복 반복 시 스톱을 MA150 바로 아래로 단계적으로 올림
- Stage 3 진입 신호(MA 평탄화 + 거래량 역전) 시: 절반 청산 후 잔량은 첫 번째 되돌림 저점 아래 스톱
- 출처: [FinancialWisdomTV — Sell Rules](https://www.financialwisdomtv.com/post/stan-weinstein-sell-rules)

### Variant B (책간 획일 기준)

| 항목 | 값 |
|------|-----|
| sl | 0.08 |
| tp | 0.12 |
| trail | 없음 |
| mh | 20 거래일 |

### 본 plan 구현 파라미터 요약

| Variant | sl | tp | trail | mh |
|---------|-----|-----|-------|-----|
| A | 0.08 | 0.30 | MA150 이탈 (종가 < MA150) | 100 거래일 |
| B | 0.08 | 0.12 | 없음 | 20 거래일 |

---

## 7. 한국 시장 적용 시 주의점

### 데이터 기간 제약 (핵심 리스크)
- `daily_prices` 실측: 2025-07-01 ~ 2026-05-29 = **224 거래일** (약 44.8주)
- MA150 계산 가능 시작: 데이터 시작 후 150일 → 실질 백테스트 가능 기간 **약 74일**
- MA 기울기 계산(20일 차분) 추가 소모: 실질 약 54일
- Mansfield RS (일봉 n=200) 요구 시: 데이터 전체 224일도 부족 → RS 계산에 n=130(26주) 축소 사용 권장
- **결론**: Stage Analysis의 장기 추세 추종 특성상 224일 데이터는 매우 제한적. 표본 수 극소화 위험 — walk-forward보다 단일 full-period 백테스트로 접근 필요

### 30W MA → 150일 SMA 일봉 환산
- 주봉 resample 없이 일봉 rolling(150).mean() 적용 (근사 오차 ±2일 이내)
- MA 기울기: `(MA150(t) - MA150(t-20)) / MA150(t-20)` (20일 = 약 4주)

### KOSPI 지수 부재
- `daily_prices` 테이블에 KOSPI/KOSDAQ 지수 코드 없음 (2026-05-29 확인, 321 종목)
- Mansfield RS 원본 공식 적용 불가 → 대안:
  - **1안**: KODEX200 ETF(069500) 또는 TIGER200(102110) 일봉 데이터를 daily_prices에 적재 (권장)
  - **2안**: universe top_volume:50 동일가중 수익률을 시장 프록시로 사용
  - **3안**: Minervini 방식(universe 내 RS 백분위)으로 대체
- Phase 2 설계서에서 최종 결정 필요

### 공매도 셋업 제외
- Stage 4 Initial Breakdown / Continuation Bounce: 한국 개인투자자 공매도 제약으로 전면 제외
- 코드화 대상은 매수 셋업(A/B/보조) 총 3개만

### Universe 표준화
- `top_volume:50` (일봉 거래대금 상위 50종목) — 유동성 확보 + 이전 5권과 동일 기준

### 단일 BULL 구간 편향
- 224일 전체가 사실상 단일 방향성 구간 (KOSPI 2025-07~2026-05) → BEAR 구간 미검증
- 국면별 분해(BULL/BEAR/SIDEWAYS, KOSPI 대리지수 기준) 병행 분석 권장

---

## 8. 셋업 카탈로그 (표)

| # | 셋업 | 코드화 | 비고 |
|---|------|--------|------|
| 1 | Stage 2 Initial Breakout (Stage 1→2 전환 돌파) | O | 핵심 셋업 — MA150 위 저항선 돌파 + 거래량 2배+ |
| 2 | Stage 2 Continuation Pullback (MA150 되돌림 재진입) | O | 보조 셋업 — MA 5% 이내 되돌림 후 회복 |
| 3 | Stage 4 Initial Breakdown (공매도) | X | 한국 공매도 제약 — 제외 |
| 4 | Stage 4 Continuation Bounce (공매도) | X | 동상 — 제외 |
| 5 | Stage 1B Late Base (베이스 후반 거래량 증가) | △ | 표본 부족 가능 — Phase 2에서 결정 |
| 6 | MA150 Bounce (Stage 2 중 MA 접촉 후 재상승) | O | #2 Pullback의 단순화 버전 (swing high 돌파 조건 완화) |

**본 plan 코드화 대상 (O 표시): 셋업 #1 + #2 + #6 (총 3개)**

---

## 9. 참고 자료

### 1차 출처
- Weinstein, Stan. *Secrets for Profiting in Bull and Bear Markets*. McGraw-Hill, 1988. — Stage 정의·30W MA·거래량·매도 룰 원본

### 2차 출처

| 제목 | URL | 주요 내용 |
|------|-----|-----------|
| Mansfield RS 생성 방법 | https://www.stageanalysis.net/blog/4266/how-to-create-the-mansfield-relative-performance-indicator | MRS 공식 원본 (MRP = (RP/SMA(RP,52)-1)×100), n=52(주봉)/200(일봉) |
| Stage 2 Breakout Quality Checklist | https://www.stageanalysis.net/blog/4372/stage-analysis-breakout-quality-checklist | 체크리스트 전체 (거래량 >=2배, 10W MA 상승, RS zero line 상회 등) |
| ChartMill — Mansfield RS | https://www.chartmill.com/documentation/technical-analysis/indicators/35-Mansfield-Relative-Strength | MRS 해석 (zero line 상회/하회) |
| TraderLion — Stage Analysis Guide | https://traderlion.com/trading-strategies/stage-analysis/ | 4단계 개요, Stage 2 거래량 2~3배 기준 |
| AXLFI — Stage Analysis | https://axlfi.com/blog/weinstein-stage-analysis | MA 기울기 공식: slope = MA(t) - MA(t-4) (주봉 4주) |
| Deepvue — Stage Analysis | https://deepvue.com/indicators/stan-weinstein-stage-analysis-when-to-buy/ | 각 Stage 가격·MA·거래량 정성 정의 |
| FinancialWisdomTV — Sell Rules | https://www.financialwisdomtv.com/post/stan-weinstein-sell-rules | 매도 룰: 스톱 30W MA 아래, Stage 3 절반 청산 |
| 7 Circles — Selling & Shorting | https://the7circles.uk/stan-weinsteins-stage-system-3-selling-shorting/ | 공매도 규칙, short 스톱 배치 (8% 반등 기준) |

---

## 부록: 모호한 기준 — 코드화 임계값 후보

다음 기준은 Weinstein 원본이 명시적 수치를 제시하지 않아 설계서에서 최종 확정 필요:

| 항목 | 책 본문 표현 | 코드화 후보 | 결정 Phase |
|------|------------|------------|-----------|
| MA150 기울기 "상승" 판단 | "MA turns higher" | `(MA150(t)-MA150(t-20))/MA150(t-20) > 0.001` | Phase 2 설계 |
| MA150 기울기 "평탄" 판단 | "MA flattens out" | `abs(기울기) < 0.001` | Phase 2 설계 |
| 돌파 거래량 임계값 | "big increase in volume" / "2~3x average" | `volume > mean(vol,20) * 2.0` | Phase 2 설계 |
| Continuation pullback 범위 | "near the MA" | `(close-MA150)/MA150 <= 0.05` | Phase 2 설계 |
| Stage 1 박스 저항선 | "base period 최고가" | `max(close, 150일)` | Phase 2 설계 |
| Mansfield RS 대체지수 | S&P500 (원본) | KODEX200(069500) 또는 universe 동일가중 | Phase 2 설계 |
| Mansfield RS n 파라미터 | n=200 (일봉) | n=130 (26주, 데이터 224일 제약 반영) | Phase 2 설계 |