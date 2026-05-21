# Research: 데이트레이딩 4대 주제 심층 자료조사 (2026-05-20)

> 5개 facet(스크리닝/Entry/Exit/Sizing/한국시장) × 4트랙(학술논문·실전트레이더·퀀트백테스트·한국사례) 병렬 조사 합성본.
> 총 출처 ~120건, 시장 무관 범용 원리 중심 + 한국 적용 노트.

---

## 0. 조사 메타

- **조사 일자**: 2026-05-20
- **조사 동기**: kis-template의 ORB v1 OOS 실패(2026-05-18) → ORB v2 96 시나리오 토너먼트 32/96 시점 중지(2026-05-20). intraday 전략 설계 근거를 처음부터 학술·실전 자료로 재정립할 필요. (관련: `changelog-2026-05-18-orb-oos-failure.md`, `changelog-2026-05-20-orb-v2-tournament-aborted.md`)
- **조사 방법**: 5개 document-specialist 에이전트 병렬 실행, WebSearch + WebFetch 결합. 모든 주장에 출처 URL, 검증 안 된 부분은 `[추정]` 명시.
- **우선순위**: 매수후보 선정 → Entry → Exit (사장님 지정), Sizing은 부록.
- **범위**: 시장 무관 범용 원리 + 한국 KOSPI/KOSDAQ 적용 가능성.

---

## 1. 핵심 종합 결론 — 8 명제

이 문서에서 단 하나만 가져가야 한다면 이 여덟 줄.

1. **"전략보다 사이징과 손절이 먼저 결과를 결정한다."** Kaminski-Lo(2014), Han-Zhou-Zhu(2016)은 stop-loss가 모멘텀 전략에서 Sharpe를 2배 개선함을 실증. Van Tharp/SMB는 사이징을 실패한 데이트레이더 1순위 원인으로 지목.
2. **"ORB는 단독으로는 죽었고, '촉매+상대거래량' 필터와만 부활한다."** Concretum(2024)이 7,000종목 2016~2023 백테스트에서 일반주식 ORB는 엣지가 사라지지만 "Stocks in Play"(RVOL≥100%)에 한정하면 Sharpe 2.81, 누적 +1,600%. Toby Crabel 본인도 "전통 ORB 단독은 비추천"으로 입장 수정.
3. **"장 첫 30분 방향이 마지막 30분을 예측한다 (Intraday Momentum)."** Gao-Han-Li-Zhou(2018) JFE 논문에서 1993~2013 SPY로 통계·경제적 유의 확인, 한국 KOSPI에서도 MDPI(2022) 재현. 변동성·거래량·거시지표일에 효과 강화.
4. **"매수 후보는 RVOL ≥ 2~5× + 갭 ≥ 4% + 촉매(뉴스/실적) 3중 교집합."** Ross Cameron 5 Pillars, SMB "Stock In Play" 기준, Qullamaggie EP 모두 동일 결론. "볼륨 없는 갭"은 70~80% 실패(Qullamaggie 실전 데이터).
5. **"직접 브레이크아웃 진입보다 첫 풀백 진입이 R/R 우월."** Al Brooks H2, Lance Beggs "must-not-miss", Adam Grimes 통계 분석 모두 동일 결론. 브레이크아웃 직접 진입은 false-break 비용이 크다.
6. **"VWAP은 단순 평균이 아니라 기관 벤치마크."** Madhavan(2002) 이후 모든 알고매매 표준. 따라서 "VWAP 위/아래"는 기관 매수/매도 우위 영역. VWAP reclaim/bounce는 실전과 학술 모두 지지.
7. **"부분익절은 기댓값을 희생하고 심리적 안정을 사는 거래."** Van Tharp는 "Golden Rule의 역행"이라 경고. 단, disposition effect(Odean 1998: 승자를 1.5배 빠르게 매도, 연 3~5% 손실)를 기계적 규칙으로 차단 못 하면 부분익절이 차선책.
8. **"한국시장 데이트레이딩은 EOD 청산이 사실상 의무."** 거래세 0.20%(매도) + 호가단위·VI·CB·동시호가·익일 갭 리스크 누적 → 손익분기 +1% 이상. 미국 ORB 통계의 단순 이식은 위험. 9:00~9:30 변동성 과다 구간 회피, 9:30~10:30이 entry 골든타임, 15:20 이전 전량 청산이 표준 운영.

---

## 2. Screening / 매수 후보 선정

### 2.1 후보 필터 12차원 매트릭스

| 차원 | 정의 | 권장 임계 | 근거 | 비고 |
|---|---|---|---|---|
| **갭 %** | 전일종가 대비 시가 변화율 | ≥4% 기본, ≥10% 고강도 | Plastun(2019), Cameron Warrior | 갭+볼륨 결합 필수 |
| **RVOL** | 당일 거래량 / N일 평균(N=10~30) | ≥2× 최소, ≥5× 우선 | QuantConnect 백테스트, Campbell-Grossman-Wang(1993) | "볼륨 없는 갭" 제거 핵심 |
| **Float** | 유통 주식수 | ≤20M(소형), ≤10M(고변동) | Cameron, Michaud float rotation | 작을수록 가격 탄성↑ |
| **ATR / ATR%** | 14일 평균진폭 | ATR ≥ \$0.50 또는 ATR% ≥ 2% | QuantConnect, CenterPoint | 비용 대비 이동범위 확보 |
| **주가** | 절대 가격대 | 미국 \$2~\$100, 한국 ≥3,000원 | Cameron 5 Pillars | 저가 = 스프레드 불리, 고가 = 탄성 부족 |
| **Dollar Volume** | 거래량×주가 | ≥\$1M/일 (한국: 100억원 이상) | Qullamaggie EP, SMB | 슬리피지 제어 |
| **촉매(Catalyst)** | 어닝/뉴스/FDA/계약/M&A | SMB 등급 8/10↑ | SMB, Qullamaggie MAGNA53 | 기술적 촉매(저항 돌파) 포함 |
| **시가총액** | 발행주식×주가 | \$100M~\$10B (중소형) | Qullamaggie CAP10×10 | 마이크로캡 = 조작 리스크 |
| **첫 30분 방향** | 09:00~09:30 수익률 부호 | 일치 시 추종, 반대면 보류 | Heston(2010), Gao(2018), Zarattini(2024) | Intraday Momentum 핵심 |
| **Short Interest** | Days-to-cover | ≥5일 | Qullamaggie EP | 숏스퀴즈 압력 |
| **섹터/테마** | 동업종 모멘텀 동시성 | 동업종 ≥2종목 강세 | Qullamaggie, SMB, Raschke | 트렌딩 섹터 후속매매 우월 |
| **가격 패턴** | VCP/ORB/Gap-and-Go | 변동성 수렴 후 돌파 | Minervini VCP, ORB 논문 | 손절 기준 명확화 |

### 2.2 학술 핵심 5편 (스크리닝 관련)

- **Heston-Korajczyk-Sadka (2010, JoF)** "Intraday Patterns in the Cross-Section of Stock Returns": 30분 단위 수익 지속성이 40 거래일 이상 지속, 거래량·스프레드로는 설명 불가. 동일 시간대 강세 종목 다음날 재강세.
- **Gao-Han-Li-Zhou (2018, JFE)** "Market Intraday Momentum": SPY 1993~2013, 첫 30분이 마지막 30분 예측. 단순 롱숏 연 6.67% Sharpe 1.08(BH 0.29). 변동성·거래량 높은 날 효과 강화.
- **Campbell-Grossman-Wang (1993, QJE)** "Trading Volume and Serial Correlation": 고거래량 + 하락은 반전, 저거래량 + 하락은 지속.
- **Plastun et al. (2019, JCR)** "Price Gap Anomaly": 갭 방향 드리프트의 통계적 유의성 확인. EMH 도전.
- **PMC 2023** "Opening Gaps & New Information": 긍정 갭 → 당일 드리프트(Russell2000 +0.58%/Nasdaq100 +0.50%/S&P500 +0.30%) 지속. 부정 갭은 시가에 빠르게 반영되어 기회 적음(비대칭).

### 2.3 실전 운영 룰 — 5인 비교

| 트레이더 | 갭% | RVOL | Float | Price | 추가 |
|---|---|---|---|---|---|
| **Ross Cameron** | ≥10% (min 4%) | ≥5× (flex 3×) | ≤20M (선호 ≤10M) | \$1~\$20 (최적 \$5~\$10) | 뉴스 catalyst 필수 |
| **SMB Capital** | ≥3% (프리마켓) | ≥3× | — | — | catalyst 8/10↑, ADV 2배 소화 예상 |
| **Qullamaggie EP** | ≥10% (최적 20~100%) | ≥2× (선호 3~5×) | — | — | MAGNA53 + CAP10×10 종합 |
| **Minervini VCP** | — | 돌파일 40~50%↑ | — | — | 50/150/200 SMA + RS≥70 + 2~6회 진폭수축 |
| **Linda Raschke** | — | ADX ≥30 | — | — | ADR 충분 + 20EMA 풀백 |

### 2.4 퀀트 검증

- **QuantConnect ORB "Stocks in Play"** (Zarattini 재현, 2016): 상위 1,000 유동성 + Price>\$5 + ATR>\$0.50 + 첫 5분 거래량 > 14일 평균 → 상위 20 RVOL → **Sharpe 2.396, Beta -0.042**. 파라미터 68%가 벤치마크 초과.
- **Zarattini SPY IM (2007~2024)**: 총수익 1,985% (비용 차감), 연 19.6%, Sharpe 1.33.

### 2.5 한국 적용

- **SNU·KAIST 실증**: KOSPI200·KOSDAQ150 선물에서 Gao(2018)와 동일한 intraday momentum 확인. 기관 순매수 비율 높을수록 효과↑.
- **수급 상관**: 외국인 순매수 vs 코스피 일간 수익 상관 **+0.54**, 기관 +0.35, **개인 -0.7** (역방향). 단타 시 개인이 사는 쪽은 불리.
- **실용 임계**:
  - 거래대금 ≥ 100억원/일 (미국 \$1M Dollar Volume 대응)
  - 주가 ≥ 3,000원 (호가단위 비용 통제)
  - RVOL ≥ 3× + 갭 ≥ 4% + 공시/뉴스 catalyst
  - KRX Data Marketplace + KIND 전자공시 API로 자동화 가능

### 2.6 즉시 적용 가능한 코드 규칙

```python
def is_intraday_candidate(symbol_features) -> bool:
    f = symbol_features
    return (
        f.gap_pct >= 0.04
        and f.rvol >= 2.0
        and f.atr_pct >= 0.02
        and f.price >= 3000          # 한국 호가단위 보정
        and f.dollar_volume >= 1e10  # 100억원
        and f.has_catalyst           # KIND 공시 또는 뉴스
        and not f.vi_active          # VI 발동 종목 제외
    )
```

---

## 3. Entry / 매수 타이밍

### 3.1 셋업 카탈로그 12종 (학술/실전 근거 강도 표시)

| # | 셋업 | 트리거 | 손절 | 학술 근거 | 백테스트 수치 | 강도 |
|---|---|---|---|---|---|---|
| 1 | **ORB (5/15/30분)** | OR 고점 종가 돌파 + 거래량 1.5× | OR 저점 | Crabel(1990), Concretum(2024) | Stocks in Play 한정 Sharpe 2.81, +1,600% | **A+** (필터 필수) |
| 2 | **Intraday Momentum** | 첫 30분 방향 추종 | OR 반대 끝 | Gao(2018), Heston(2010), KOSPI MIM(MDPI 2022) | SPY 2007~2024 Sharpe 1.33 연 19.6% | **A** |
| 3 | **VWAP Bounce/Reclaim** | VWAP 접촉 후 강세 캔들 → 직전 봉 고점 | VWAP -N틱 | Madhavan(2002) | Concretum QQQ 2018~2023 연 28%+ | **A** |
| 4 | **First Pullback (FPB)** | 돌파 후 1차 되돌림 지지 캔들 | 되돌림 저점 | Brooks H2, Beggs, Grimes | 독립 백테스트 없으나 다중 실전 검증 | **A** |
| 5 | **ABCD** | C 저점 확인 후 B 고점 돌파 | C 저점 | 직접 학술 없음; Heston(2010) 30분 패턴 연계 | [추정] win 55~65% | **B** |
| 6 | **Bull Flag** | 깃발 상단 돌파 + 거래량 재증가 | 깃발 저점 | SMB Catalyst+Setup | Warrior 내부 win 60~70% | **B** |
| 7 | **Red-to-Green** | 전일 종가 1분봉 상향 돌파 | 당일 저점 또는 VWAP | Edgeful 통계 74% | 11AM 이후 성공률 급감 | **B+** |
| 8 | **80-20 Reversal (Raschke)** | 전일 저점 하방 후 재상향 | 당일 신저점 | Raschke-Connors(1995) Street Smarts | 공개 백테스트 없음 | **B** |
| 9 | **NR7 / NR4 BO** | NR7 봉 고점 +1틱 돌파 | NR7 반대 끝 | Crabel(1990) | QuantifiedStrategies 양의 기대값 | **B+** |
| 10 | **ACD (Fisher)** | A-up 가격 터치 + 5분봉 종가 | OR 반대 끝(B-point) | Fisher(2002) 선물 실전 | 공개 학술 백테스트 없음 | **B** |
| 11 | **Gap-and-Go** | 첫 5분봉 고점 돌파 (갭업 기준) | 첫 5분봉 저점 | 갭 통계 4%+ 갭 72% 방향 지속 | jaenung 한국 갭 데이터와 일치 | **A-** |
| 12 | **Connors RSI-2** | 200일 MA 위 + RSI(2)<5 → 익일 시초가 | RSI(2)>65 청산 | Connors-Alvarez(2010) | S&P500 1990~2024 win 75%, 0.5%/거래 | **B+** (스윙 성격) |

> 강도: **A+** = 학술+퀀트 백테스트 동시 강함 / **A** = 학술 강 + 실전 폭넓음 / **B+** = 학술 부분, 실전 검증 풍부 / **B** = 실전 위주, 학술 약함.

### 3.2 학술 핵심 — 진입 타이밍

- **Gao-Han-Li-Zhou (2018)** 위에서 인용. MIM의 진입 함의: "장 시작 30분 방향을 당일 편향 필터로 사용. 14:30~15:00 사이 진입 후 종가 청산 패턴이 가장 표준."
- **Heston-Korajczyk-Sadka (2010)**: 30분 간격 수익 지속성 → 특정 종목이 특정 시간대에 일관되게 강세인 패턴 → 시간대 특이성을 entry filter로 활용.
- **Concretum / Zarattini (2024)** (2편): ORB가 일반주식에서 죽었지만 "Stocks in Play" + "Noise Area" + 동적 트레일링 결합 시 부활. 비용 차감 후 SPY 1,985%/Sharpe 1.33.
- **Madhavan (2002)** VWAP Strategies: 거래량 U자형 분포 정량화. VWAP을 "벤치마크"로 격상시킨 기초 문헌.
- **Crabel (1990)** Day Trading with Short Term Price Patterns: NR7·ORB·Stretch 통계적 기반. 본인 100년 후속 분석에서 단독 ORB 엣지 감소 인정 → 필터·컨텍스트 결합 강조.

### 3.3 실전 진입 5인 통합 체크리스트

Al Brooks / Lance Beggs / SMB / Linda Raschke / Mark Fisher 공통 항목 추출:

1. **Context** — 상위 타임프레임 추세 or 레인지 식별 (5분 → 15분 → 일봉)
2. **Catalyst** — 뉴스/실적/공시/기술적 이벤트 존재
3. **Level** — ORH, VWAP, 전일 고/저점, 이평선 등 의미 있는 가격 레벨 근처
4. **Trigger** — 정확한 캔들 신호 + 거래량 확인
5. **Risk** — 사전 정의된 손절 + R:R ≥ 1:2

추가: Brooks "H2(두 번째 풀백)" / Raschke "Anti(추세 중 첫 되돌림 재진입)" / Fisher "A-point는 OR 단순 돌파보다 보수적" — 모두 *직접 브레이크아웃 회피 → 1차 풀백 진입*에 수렴.

### 3.4 한국 시간대별 entry 권고

| 시간 | 특성 | 권장 행동 |
|---|---|---|
| 09:00~09:30 | 변동성 최대, 갭 + VI 빈발 | **관찰만**. ORB Range 측정. |
| 09:30~10:30 | 첫 트렌드, MIM 골든타임 | **ORB / FPB / MIM 진입 적기** |
| 10:30~11:30 | 1차 조정, VWAP 풀백 가능 | **VWAP Bounce / Bull Flag** |
| 11:30~13:00 | 저유동성 | **신규 진입 회피** (KOSPI MIM 논문도 이 구간 성과 미미) |
| 13:00~14:30 | 오후 재진입 | MIM 방향 재확인, 2차 진입 |
| 14:30~15:20 | 기관 종가 맞추기 | MIM 마지막 30분 패턴 |
| 15:20~15:30 | 동시호가 | **신규 진입 금지**, 청산만 |

---

## 4. Exit / 매도 타이밍

### 4.1 Exit 6차원 매트릭스

| 차원 | 트리거 | 권장 파라미터 | 학술/실증 근거 | 한국 노트 |
|---|---|---|---|---|
| **고정 손절** | 진입가 -% | 일중 -1~2%, 스윙 -7~8%(Minervini) | Lei-Li(2009) 리스크 감소, Kaminski-Lo(2014) 모멘텀 수익 개선 | 거래세 0.2% → 손절 -1.5% 미만은 비효율 |
| **고정 익절** | +R 도달 | 2:1~3:1 R/R (Cameron, Minervini) | 200만 백테스트 TP win 57% (vs TS 35%, SL 31%) | 목표가 호가단위 정수배 |
| **트레일링** | ATR 고점 하락 | Chandelier(22, 3×ATR) / Turtle 2N(=2×ATR20) | Han et al.(2016): 월수익 1.01%→1.73%, SD 6.07%→4.67% | VI 단일가 2분간 미발동 위험 |
| **시간 (EOD)** | N봉 경과 / 장 마감 | 15:20 이전 전량 청산 | López de Prado Triple Barrier | 동시호가 진입 금지, 익일 갭 회피 |
| **Signal Invalidation** | 진입 근거 무효 | 신호봉 저점 이탈(Brooks) | Brooks Price Action | 분봉 signal bar 명시 |
| **부분 익절** | 1R 도달 시 50% | breakeven 이동 | Tharp 경고: 기댓값 감소; 통계적으로 blended R 1.5R | 분할매도 수량 호가단위 보정 |

### 4.2 학술 핵심 — Exit

- **Kaminski-Lo (2014, JFM)** "When Do Stop-Loss Rules Stop Losses?": **랜덤워크에서 stop은 손실, 모멘텀 존재 시 stop이 수익 개선.** 1993~2011 선물 데이터로 +1.5%/월 + 변동성 감소. 정부채로 stop-out 자산 대체 시 월 50~100bp 추가 수익.
- **Lei-Li (2009)** "The Value of Stop Loss Strategies": NYSE/AMEX 1970~2005, stop이 **수익 향상이 아닌 리스크 감소**에 기여. 재투자처가 더 중요.
- **Han-Zhou-Zhu (2016)** "Taming Momentum Crashes": 월 10% stop 적용 시 모멘텀 최대 손실 -49.79%→-11.36%(EW), Sharpe 2배+. 2009 모멘텀 크래시(-65%) 완전 회피.
- **Odean (1998)** Disposition Effect: 1만 계좌, 승자를 패자보다 1.5배 빠르게 매도, 연 3~5% 손실. **기계적 exit 규칙만이 대안.**
- **MFE/MAE (Sweeney, Tharp)**: Exit Efficiency = 실현수익/MFE. 60%↓는 익절 과조기, 80%↑는 최적. MAE > MFE 구조면 entry 재설계.

### 4.3 실전 Exit 룰 6인

- **Van Tharp (R-multiple)**: 모든 exit을 R 단위로 설계. 스케일아웃은 "Golden Rule 역행"이라 명시적 반대. 9 stop 유형(ATR/MAE/시간/차트).
- **Curtis Faith (Turtle)**: N=ATR(20) EMA. 초기 stop -2N, trailing 최고가 -2N. 0.5N 상승마다 피라미딩 (최대 4유닛). 4×2N = 자본 2% 손실 상한.
- **Mark Minervini (SEPA)**: 최대 -8%(약세장 -5~6%), R:R ≥ 2:1, +20% 시 손절을 진입가로 이동("free trade").
- **Ross Cameron**: R:R ≥ 2:1, 1R 도달 시 50% 청산 + 잔여분 breakeven, 첫 음봉 시 잔여 청산, 수직급등 시 전량.
- **Al Brooks**: signal bar 저점 이탈 시 즉시 청산. measured move / 채널 반대편이 익절 목표.
- **SMB**: scaling out 적극 사용, "심리 안정 vs 기댓값" 트레이드오프 명시.

### 4.4 퀀트 핵심 — Exit

| 출처 | 비교 | 결과 |
|---|---|---|
| Polakow 200만 백테스트 | Fixed TP vs ATR Trailing vs Fixed SL | win rate 57% / 35% / 31% — TS는 win 낮지만 expectancy 0.19R |
| Davey 567K (40 선물, 10년) | 7종 exit 비교 | Stop&Reverse > Dollar Target > Breakeven > 기술지표 > Chandelier > Yo-Yo. **단순이 우월** |
| StratBase BTC 2020~2024 | Chandelier(22,3×ATR) vs Fixed 트레일 | PF 1.61 vs 1.28 (5% 트레일 1.09) — ATR 우월 |
| Han et al. 모멘텀+10% stop | 월별 통계 | 평균 +71%, SD -23%, MaxLoss -49.79→-11.36 |

> Davey의 "단순이 복잡함보다 우월"은 중요. 과적합 위험을 안고 복잡한 trailing logic을 만드는 것보다 명확한 Dollar Target + Breakeven 조합이 견고.

### 4.5 한국 Exit 룰 권고

```
손절: -2.0% (거래세 고려, 슬리피지 포함 손익분기 +1%↑)
익절1: +2.0% 도달 시 50% 청산 + 잔여 breakeven 이동
익절2: 첫 음봉 출현 시 잔여 청산 또는 trailing(2×ATR20)
시간: 15:20 강제 청산 (동시호가 진입 금지)
무효화: 신호봉 저점 -1틱 이탈 시 즉시 청산
VI 발동: 신규 진입 금지, 기존 포지션 2분 단일가 해제 후 평가
```

---

## 5. Sizing / 자본분배 (부록)

### 5.1 사이징 모델 비교

| 모델 | 공식 | 장점 | 단점 | 권장 |
|---|---|---|---|---|
| **고정비율** | 자본×r% / 주당리스크 | 단순 | 변동성 무시 | 초기 검증 |
| **1% Risk Rule** | 손실 = 자본×1% | 직관, 파산방지 | 종목간 차이 무시 | 범용 표준 |
| **Full Kelly** | f* = p/l − q/g | 장기 성장 최대 | 50%+ DD, 추정 민감 | 상한 기준선만 |
| **Half-Kelly** | 0.5×Kelly | 성장 75% + DD 50% | 심리 부담 여전 | 시스템 트레이더 |
| **Optimal-f (Vince)** | F×자본/MaxLoss/Price | 실거래 P&L 반영 | 최악 손실 과민 | 선물·레버리지 |
| **ATR 기반** | 손실$ / (ATR×n) | 변동성 자동 반영 | ATR 기간 주관 | **다종목 데이트레이딩 권장** |
| **Volatility Targeting** | 목표σ / 실현σ | Sharpe 개선 | 변동성군집 시 과소 | 중장기 팩터 |
| **ERC** | w_i × (Σw)_i 균등 | 상관 고려, 분산↑ | 공분산 필요 | **다전략 자본분배 권장** |
| **티어 (SMB)** | A+/B/Feeler 비율 | 셋업 품질 반영 | 주관적 등급 | 재량 트레이더 |
| **피라미딩** | 50/30/20 또는 1/0.5/0.25 | 추세 수익 극대화 | DD 심화 | 모멘텀 추세 |

### 5.2 학술 핵심 — Sizing

- **Kelly (1956)**: f* = (μ-r)/σ². 실험적으로 Full Kelly 참가자 28% 파산.
- **MacLean-Thorp-Ziemba (2011)**: Half-Kelly = 성장 75% + 분산 50% 감소. Full Kelly는 50%+ DD 확률 1/3.
- **Vince Optimal-f / Secure-f**: 실거래 P&L 기반 + DD 제약. Bootstrapped Optimal-f가 비-bootstrapped 대비 레버리지 50% 축소(QuantPedia).
- **Moreira-Muir (2017, JoF)**: Volatility-Managed Portfolios — 시장/가치/모멘텀/수익성/BAB 팩터 모두 변동성 역수 사이징으로 Sharpe 개선. 효용 65% 증가 (단, 2020 JFE 반론 있음).
- **Maillard-Roncalli-Teiletche (2010)** ERC: 최소분산-균등가중 사이의 균형점. ERC SD 2.78%/MDD -4.73% vs 균등가중 4.74%/-18.18%.

### 5.3 퀀트 검증 (Concretum, 40 선물 1980~)

| 사이징 | 수익률 | CAGR | MDD | Hit |
|---|---|---|---|---|
| Volatility Targeting | 16,828% | 11.46% | 25.65% | 60% |
| Volatility Parity | 30,014% | 12.83% | ~25% | 59% |
| VP + Pyramiding | 556,106% | 20.00% | 48.69% | 56% |

> 피라미딩은 수익을 폭증시키지만 DD가 거의 2배. 데이트레이딩 실전은 VT급 안정성이 현실적.

### 5.4 한국 적용 — ATR 기반 + 호가단위 보정

```python
def position_size_kr(equity, risk_pct, atr_price, atr_mult, entry_price):
    risk_amount = equity * risk_pct      # 자본 × 1%
    stop_distance = atr_price * atr_mult # 2~3 × ATR(14)
    raw_qty = risk_amount / stop_distance
    qty = max(1, int(raw_qty))
    # 손절가 호가단위 보정
    raw_stop = entry_price - stop_distance
    stop = round_to_tick_kr(raw_stop)
    return qty, stop

def round_to_tick_kr(p):
    # 2023.01.25 개정 호가단위
    if p < 2000:    return round(p)
    if p < 5000:    return round(p/5)*5
    if p < 20000:   return round(p/10)*10
    if p < 50000:   return round(p/50)*50
    if p < 200000:  return round(p/100)*100
    if p < 500000:  return round(p/500)*500
    return round(p/1000)*1000
```

종목당 한도: 자본의 10% 이하 (15% 절대 상한). 신용/미수 사용 시 Kelly에 레버리지 반영 필수.

### 5.5 다전략 자본분배 (kis-template 다전략 운영 시)

1. **ERC 가중치 (1차 권장)**: w_i ∝ 1/σ_i (전략 변동성 역수). 상관관계 추정 없이도 80% 효과.
2. **상관 한도**: 전략 쌍 상관 >0.7이면 합산 자본을 단일 전략 수준으로.
3. **"증명 기간" 룰 (SMB)**: 신규 전략 5%, 검증 후 정상, 성과 저하 시 자동 50% 축소.
4. **Portfolio Heat 상한**: 모든 전략 오픈 리스크 합 ≤ 자본의 6~10% (Van Tharp).

---

## 6. 한국 시장 특수성

### 6.1 구조적 제약 1페이지 요약

| 항목 | 내용 | 데이트레이딩 영향 |
|---|---|---|
| 거래시간 | 09:00~15:30 (정규), 점심 무휴장 | 09:00~09:30 변동성 최대, 11:30~13:00 저유동성 |
| 동시호가 | 개장 08:30~09:00, 마감 15:20~15:30 | 마감 동시호가 진입 금지 |
| 시간외 | 15:40~16:00(종가), 16:00~18:00(단일가) | "상한가 따라잡기" 활용 가능 |
| 호가단위 (2023.01.25 개정) | 1~1,000원 7단계 | 손절·익절 가격을 호가단위 정수배로 |
| 가격제한폭 | ±30% (2015.06.15~) | 손절 미설정 시 하루 -30% 가능 |
| 결제 | T+2 | 매도일 즉시 재매수 가능 (예수금 기준) |
| **VI (동적)** | KOSPI200 ±3% (마감전 ±2%), 일반/KOSDAQ ±6% (±4%) | **2분 단일가 → 신규 진입 금지** |
| **VI (정적)** | 전일 종가 ±10% | 매수 후 VI 발동 시 즉시 청산 불가 |
| **CB** | -8%/-15%/-20% (3단계) | 시장 전체 정지 |
| **사이드카** | 선물 ±5(KOSPI)/±6(KOSDAQ)% + 1분 | 프로그램매매만 정지, 개인 영향 X |
| **공매도** | 2025.03.31 전면 재개 (개인담보 105%, 상환 최장 12개월) | 급등주 단타 하방 압력 증가 |
| 거래세 (2026) | 매도 시 0.20% (코스피·코스닥) | **손익분기 +1% 이상 필요** |
| 위탁수수료 | ~0.015% (온라인) | 왕복 비용 0.43~0.50% [추정] |

### 6.2 KIS OpenAPI 운영 한계

| 항목 | 실전 | 모의 |
|---|---|---|
| REST TPS | 20건/초 | 5건/초 |
| WebSocket 구독 | 세션당 41종목 (H0STCNT0+H0STASP0 합산 20) | 동일 |
| 주문 유형 | 00 지정가 / 01 시장가 / 02 조건부지정가 | IOC/FOK 미지원 [추정] |

운영 노하우:
- 70 종목 동시 모니터링 = 초당 175건 → 동적 배치 필요
- 84종목 이상 = 다중 계좌(세션 2 × 41)
- 모의는 TPS 1/4 → 스크리닝 부적합

### 6.3 한국 단타 셋업

1. **상한가 따라잡기**: 당일 상한가 종가/시간외 매수 → 익일 갭업. 강한 테마+수급 동반 시만 [추정]
2. **장대양봉 후 눌림목**: 거래량 급증 장대양봉 → 2~3일 조정 → 역망치/밑꼬리 시 재진입, MA20 이탈 손절. 한국 실전서 가장 빈번
3. **ORB (9:00~9:30)**: OR + 동시호가 갭 + 거래대금 상위. 한국 특화 학술 실증은 부재 [추정]
4. **거래량 폭증주 익일**: 전일 ≥5× → 갭업 후 단타. 테마/뉴스 동반 필수
5. **수급 추종**: 외국인+0.54, 기관+0.35, 개인 -0.7. 개인 매수 종목은 단타 회피
6. **테마주 모멘텀**: 정치·이벤트·실적·M&A. 알파스퀘어/인포스탁 실시간 테마. 테마 소멸 시 즉시 이탈

### 6.4 동학개미운동 통계 (2020~2021)

- 개인 거래회전율 **연 1,600%** (미국 상위 25% 개인 대비 ~6배)
- 신규 투자자 ~60% 손실 실현
- 6~8월 개인 순매수 상위 7종목 평균 수익 16.1% vs 외국인 85.7%
- 시사: **거래 빈도 ≠ 수익**. 데이트레이딩 시스템화의 첫 번째 가치는 "감정 빈도 거래" 차단

### 6.5 갭 통계 (한국 추정)

| 갭 크기 | 방향 유지 | 당일 갭필 | 5일 내 갭필 |
|---|---|---|---|
| 1~2% | 55% | 65% | — |
| 2~4% | 62% | 45% | ~50% |
| 4%+ | 72% | 30% | ~50% |

전체 갭의 70~80%가 결국 메워짐. 당일 갭필은 25~30%(주로 10~11시).

---

## 7. kis-template 기존 11 intraday 전략 매핑

현재 `RoboTrader_template/strategies/intraday/` 구조:
`abcd_pattern, bull_flag, ma_trend, orb, orb_v2, pullback, red_to_green, reversal_rsi, reversal_vwap, support_resistance, vwap_trade`

### 7.1 전략 ↔ 셋업 매핑 + 학술 근거 강도

| 전략 디렉토리 | 매핑 셋업 | 학술 근거 | 실전 근거 | 종합 | 비고 |
|---|---|---|---|---|---|
| `orb` | 셋업 1 ORB | **A+** (Crabel, Concretum) | **A+** | **A+** | 필터 미적용 시 죽음. v1 OOS 실패 원인일 가능성 |
| `orb_v2` | 셋업 1 ORB + 필터 | 동일 | 동일 | **A+** | Stocks in Play 필터 추가가 핵심 |
| `vwap_trade` | 셋업 3 VWAP | **A** (Madhavan) | A | **A** | 기관 벤치마크. 강한 근거 |
| `reversal_vwap` | 셋업 3 VWAP Reclaim | A | A | **A** | "VWAP 하회 후 재상향" 분기 |
| `pullback` | 셋업 4 FPB | B+ (Brooks H2, Grimes) | A | **A-** | 단독 학술 백테스트 부재하나 다중 실전 검증 |
| `ma_trend` | 셋업 4 변형 (20EMA H2) | B (Brooks) | B+ | **B+** | Adam Grimes 통계 분석과 정합 |
| `bull_flag` | 셋업 6 Bull Flag | B (SMB Catalyst+Setup) | A | **B+** | 학술 직접 검증 약함 |
| `abcd_pattern` | 셋업 5 ABCD | C (직접 학술 없음) | B | **B** | Heston(2010) 30분 패턴과 간접 연계뿐 |
| `red_to_green` | 셋업 7 R2G | B+ (Edgeful 74%) | A | **B+** | 11AM 이후 성공률 급감 — 시간 필터 권장 |
| `reversal_rsi` | 셋업 12 Connors RSI-2 | A (Connors-Alvarez) | A (75% win) | **A-** | 스윙 성격 강함, 데이트레이딩 분류 재검토 |
| `support_resistance` | 일반 level-based | C | B+ | **C+** | "지지/저항" 추상 개념 — 구체적 셋업으로 분해 필요 |

### 7.2 ORB OOS 실패의 학술적 해석

`changelog-2026-05-18-orb-oos-failure.md`와 `changelog-2026-05-20-orb-v2-tournament-aborted.md`의 ORB 실패는 학술 자료와 **정합한다**:

1. **Concretum(2024) 결론**: "일반 주식 ORB는 엣지가 사라졌다. Stocks in Play 한정 시에만 Sharpe 2.81." → 우리 ORB가 universe 필터 없이 돌면 OOS 실패가 정상.
2. **Crabel(1990 → 후속)**: 본인이 100년 데이터로 점진적 엣지 감소 인정. 전자거래 도입 후 유동성 분산이 OR의 정보가치를 희석.
3. **함의**: ORB의 universe를 (a) RVOL≥2×, (b) 갭≥4%, (c) catalyst, (d) ATR≥2%로 좁히지 않으면 OOS에서 통계적 우위 소멸이 *예상되는* 결과. v2 토너먼트가 96 시나리오 32회에서 중단된 것은 손실이 아니라 "필터 조합 자체가 부족했을 가능성"에 대한 증거.

### 7.3 전략별 우선순위 권고 (학술/실전 근거 강도 기준)

**Tier 1 (즉시 강화 가치 큼)**: `orb_v2` + `pullback` + `vwap_trade` + `reversal_vwap`
- 학술 근거 가장 강하고, 한국 시장 시간대 정합성도 가장 좋음
- 단, `orb_v2`는 "Stocks in Play" 필터(RVOL+갭+catalyst) 결합이 핵심

**Tier 2 (검증 필요)**: `red_to_green` + `reversal_rsi` + `ma_trend`
- `red_to_green`: 11AM 이후 성공률 급감 → 시간 필터 추가하면 격상
- `reversal_rsi`: 스윙 성격 → 데이트레이딩 단독 사용 부적합 가능, 분류 재검토
- `ma_trend`: Brooks H2와 정합하나 한국 ATR/이평선 파라미터 재튜닝

**Tier 3 (재정의 필요)**: `bull_flag` + `abcd_pattern` + `support_resistance`
- 학술 직접 근거 약함. 한국 실증 데이터로 자체 검증 우선
- `support_resistance`는 추상 개념 → "전일 고/저", "VWAP", "ORH/ORL" 등 구체 level로 분해

### 7.4 신규 추가 권고 셋업 (현재 미구현)

| 추가 후보 | 셋업 | 근거 |
|---|---|---|
| **Intraday Momentum 방향 필터** | 셋업 2 | KOSPI 실증(MDPI 2022) + Gao(2018). 단독 전략보다 **모든 전략에 공통 entry gate**로 적용 권장 |
| **NR7 Breakout** | 셋업 9 | Crabel 통계, 한국 KOSPI 대형주에 적합 |
| **80-20 Reversal** | 셋업 8 | Raschke, 한국 ±30% range 환경에 임계값 재튜닝 후 |
| **Gap-and-Go** | 셋업 11 | 한국 갭 통계와 정합 (4%+ 갭 72% 방향지속) |

---

## 8. 다음 액션 후보

### 8.1 즉시 적용 (1주 이내)

1. **`orb_v2`에 Stocks in Play 필터 결합** — `is_intraday_candidate()` (§2.6) 구현 후 universe 적용 → 재토너먼트
2. **모든 entry 직전에 MIM 방향 게이트** — 09:00~09:30 코스피 지수 수익 부호와 individual signal 부호 일치 시만 진입
3. **EOD 강제 청산 (15:20)** — Tier 1 전략 전체에 hard rule
4. **VI 발동 감지 + 진입 차단** — KIS API VI TR 활용 (또는 호가 정지 신호)
5. **호가단위 보정 함수 `round_to_tick_kr()`** — 모든 손절/익절 가격 산정에 일괄 적용

### 8.2 단기 추가 조사 (1~2주)

1. **한국 KOSPI/KOSDAQ ORB 자체 실증** — `minute_candles` 318일 × 1,347종목 데이터로 Concretum 방법론 재현, Stocks in Play 필터 효과 정량화
2. **MIM 한국 실증 재현** — KOSPI 5/15/30분 데이터로 Gao(2018) 재현, kis-template 백테스트 엔진으로 검증
3. **ATR 기반 사이징 vs 고정수량 A/B** — `BacktestEngine`에 사이징 파라미터화, `run_oos_split`로 비교
4. **부분익절 vs 단일익절 통계** — 동일 전략에서 expectancy 차이 측정 → Tharp 주장 검증

### 8.3 중기 시스템 개선 (1개월+)

1. **Multi-strategy ERC 자본분배** — `multiverse_paper`에 전략별 변동성 역수 가중 추가
2. **MFE/MAE 추적 인프라** — 각 거래에 MFE/MAE 기록, exit efficiency 60% 기준 익절 최적화 루프
3. **KIND 공시 + 뉴스 catalyst 자동 수집** — KRX Data Marketplace + 공시 API 파이프라인, screener에 catalyst 차원 추가
4. **시간대별 전략 활성화 매핑** — Tier 1 전략을 §3.4 시간대별 권고에 따라 자동 on/off

### 8.4 보류/재검토

- `reversal_rsi`의 데이트레이딩 카테고리 분류 — Connors는 명시적 스윙 전략(2~4일 보유). 현 카테고리 유지 여부 결정 필요
- `support_resistance`의 구체화 — "어떤 S/R인가"(전일 고/저, VWAP, 이평선, ORH/ORL, 피보나치 등) 분해 후 별도 전략으로 분리할지

---

## 9. 출처 통합 (Bibliography)

### 9.1 학술 논문 (핵심)

- Heston, Korajczyk, Sadka (2010) "Intraday Patterns in the Cross-Section of Stock Returns", *Journal of Finance* 65(4) — https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2010.01573.x
- Gao, Han, Li, Zhou (2018) "Market Intraday Momentum", *Journal of Financial Economics* 129(2) — https://www.sciencedirect.com/science/article/abs/pii/S0304405X18301351
- Campbell, Grossman, Wang (1993) "Trading Volume and Serial Correlation in Stock Returns", *QJE* 108(4) — https://web.mit.edu/wangj/www/pap/CampbellGrossmanWang93.pdf
- Plastun et al. (2019) "Price Gap Anomaly in the US Stock Market" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3461283
- Zarattini, Aziz, Barbon (2024) "Beat the Market: SPY Intraday Momentum" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172
- Zarattini, Barbon, Aziz (2024) "A Profitable Day Trading Strategy for the U.S. Equity Market" (Concretum) — https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/
- Madhavan (2002) "VWAP Strategies", *Transactions & Performance* — https://www.smallake.kr/wp-content/uploads/2014/07/TP_Spring_2002_Madhavan.pdf
- Kaminski, Lo (2014) "When Do Stop-Loss Rules Stop Losses?", *JFM* — https://dspace.mit.edu/bitstream/handle/1721.1/114876/Lo_When%20Do%20Stop-Loss.pdf
- Lei, Li (2009) "The Value of Stop Loss Strategies" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1214737
- Han, Zhou, Zhu (2016) "Taming Momentum Crashes" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2407199
- Odean (1998) "Are Investors Reluctant to Realize Their Losses?", *JoF* — https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00072
- Kelly (1956) "A New Interpretation of Information Rate", *Bell Sys Tech J* — https://en.wikipedia.org/wiki/Kelly_criterion
- MacLean, Thorp, Ziemba (2011) "The Kelly Capital Growth Investment Criterion" — https://www.financialwisdomtv.com/post/kelly-criterion-ed-thorp-optimal-position-sizing-for-stock-trading
- Moreira, Muir (2017) "Volatility-Managed Portfolios", *JoF* — https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12513
- Maillard, Roncalli, Teiletche (2010) ERC — http://www.thierry-roncalli.com/download/erc.pdf
- KOSPI MIM (MDPI JRFM 2022) — https://www.mdpi.com/1911-8074/15/11/523
- SNU Intraday Momentum 석사논문 — https://s-space.snu.ac.kr/handle/10371/166309
- KAIST 일중 모멘텀 — https://koasas.kaist.ac.kr/handle/10203/202579 / https://koasas.kaist.ac.kr/handle/10203/307602
- 박정식 "당일매매와 변동성" — https://s-space.snu.ac.kr/bitstream/10371/44416/1/02%EB%B0%95%EC%A0%95%EC%8B%9D-%EC%9E%AC.pdf
- Kakushadze, Serur (2018) "151 Trading Strategies" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3247865

### 9.2 실전 트레이더 자료

- Toby Crabel 후속 분석 — https://tobycrabel.substack.com/p/the-evolution-of-the-opening-range
- Warrior Trading (Cameron) — https://www.warriortrading.com/momentum-day-trading-strategy/ , https://www.warriortrading.com/low-float-stocks/
- SMB Capital — https://www.scribd.com/document/261794661/SMBU-How-to-Find-and-Trade-Stocks-in-Play-pdf , https://www.smbtraining.com/blog/14-keys-to-proper-position-sizing-to-grow-your-trading-account
- Qullamaggie Episodic Pivot — https://www.finermarketpoints.com/post/episodic-pivot-trading-complete-guide
- Minervini SEPA/VCP — https://www.finermarketpoints.com/post/mark-minervini-s-sepa-methodology-complete-framework-explained
- Linda Raschke 80-20 / Holy Grail — https://www.scribd.com/document/194332066/80-20-S-from-Street-Smarts-High-Probability-Short-Term-Trading-Strategies-Raschke , https://tradersmastermind.com/linda-raschke-trading-strategy/
- Al Brooks Price Action — https://www.brookstradingcourse.com/ask-al/pullbacks-entering/
- Lance Beggs First Pullback — https://yourtradingcoach.com/trading-process-and-strategy/first-pullback-in-a-new-directional-trend/
- Mark Fisher ACD — https://nexusfi.com/a/strategies/acd-trading-method
- Van Tharp Institute — https://vantharpinstitute.com/product/trade-your-way-to-financial-freedom/
- Curtis Faith Turtle — https://www.tradingblox.com/Manuals/UsersGuideHTML/turtlesystem.htm
- Tim Sykes — https://www.timothysykes.com/blog/how-to-use-stock-scanners/

### 9.3 퀀트 백테스트 / 자료

- QuantConnect ORB Stocks in Play — https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/
- QuantConnect ETF Intraday Momentum — https://www.quantconnect.com/research/15348/intraday-etf-momentum/
- Concretum Group Papers — https://concretumgroup.com/papers/
- QuantifiedStrategies (RSI-2, NR7, MFE/MAE) — https://www.quantifiedstrategies.com/
- KJTradingSystems 567K Backtests — https://kjtradingsystems.com/algo-trading-exits.html
- DataDriven Investor 200만 Backtests — https://medium.datadriveninvestor.com/stop-loss-trailing-stop-or-take-profit-2-million-backtests-shed-light-dde23bda40be
- ChartMill Qullamaggie Screener — https://www.chartmill.com/documentation/stock-screener/technical-analysis-trading-strategies/494-Mastering-the-Qullamaggie-Episodic-Pivot-Setup-A-Flexible-Stock-Screening-Approach

### 9.4 한국 시장 자료

- KIS Developers — https://apiportal.koreainvestment.com/intro , https://github.com/koreainvestment/open-trading-api
- hky035 KIS API 분석 — https://hky035.github.io/web/kis-api-throttling/ , https://hky035.github.io/web/refact-kis-websocket/
- tgparkk 70종목 문제 — https://tgparkk.github.io/robotrader/2025/10/09/robotrader-1-70stocks-problem.html
- KRX Data Marketplace — https://data.krx.co.kr/
- KRX VI 현황 — http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC02021501
- 가격제한폭 — https://ko.wikipedia.org/wiki/%EA%B0%80%EA%B2%A9%EC%A0%9C%ED%95%9C%ED%8F%AD
- VI 가이드 — https://glasswallet.com/blog/vi-volatility-interruption-guide/ , https://kbthink.com/stock/vi.html
- 사이드카 — https://kbthink.com/stock/sidecar.html
- 거래시간/동시호가 — https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1701&ccfNo=2&cciNo=1&cnpClsNo=2 , https://namu.wiki/w/%EB%8F%99%EC%8B%9C%ED%98%B8%EA%B0%80
- 호가단위 변경 2023 — https://www.sisajournal-e.com/news/articleView.html?idxno=296263
- 2026 증권거래세 — https://glasswallet.com/blog/stock-transaction-tax-guide/
- 공매도 재개 — https://www.tossbank.com/articles/re-shortselling , https://www.fsc.go.kr/no010101/84216
- 자본시장연구원 — https://www.kcmi.re.kr/report/report_view?report_no=1481
- jaenung.net 한국 갭/시간대 통계 — https://www.jaenung.net/tree/42481 , https://www.jaenung.net/tree/19594
- 한국 단타기법 — https://namu.wiki/w/%EC%A3%BC%EC%8B%9D%ED%88%AC%EC%9E%90/%EB%8B%A8%ED%83%80%EB%A7%A4%EB%A7%A4%20%EA%B8%B0%EB%B2%95
- 한국 피라미딩 — https://brunch.co.kr/@00b68069c88e4c0/161
- DBpia 한국 데이트레이딩 수익성 (2007) — https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE07228072
- KISTI 호가잔량 BSI 데이트레이딩 (2019) — https://scienceon.kisti.re.kr/srch/selectPORSrchArticle.do?cn=JAKO201922441756714

---

## 10. 부록 — 한 줄 요약 (사장님 의사결정 보조용)

> **"우리 ORB가 OOS에서 실패한 건 학술적으로 예측 가능한 결과다. 단독 ORB는 죽었고, 'Stocks in Play' 필터(RVOL≥2×·갭≥4%·catalyst·ATR%≥2%)와만 살아난다는 것이 Concretum(2024)의 결론. 다음 토너먼트는 이 필터를 universe로 적용한 뒤 돌리자. 동시에 모든 전략에 'MIM 방향 게이트(09:00~09:30 코스피 부호)'와 '15:20 EOD 청산'을 하드 룰로 박는 게 비용 대비 가장 빠른 개선."**

— END —
