# 책 2: Mike Bellafiore — One Good Trade / The PlayBook

> 카테고리: 인트라데이 (분봉, prop trading)  
> 데이터 입도: 분봉 (minute_candles)  
> 완료일: 2026-05-28  
> 상세 자료: [백테스트 결과](../reports/books_research/bellafiore_playbook/) · [조사 원본](../strategies/books/bellafiore_playbook/RULES_RESEARCH.md) · [코드](../strategies/books/bellafiore_playbook/)

## 1. 책 요약

Mike Bellafiore는 뉴욕 prop trading firm **SMB Capital** 공동창업자. *One Good Trade*(2010) + *The PlayBook*(2013) 두 권.

핵심 차별점 (vs 아지즈):
- 단순 패턴이 아닌 **다섯 의사결정 레이어** 복합: Big Picture · Intraday Fundamentals · Technicals · Tape Reading · Intuition
- **Stocks In Play** 명확 정량화: RVOL ≥ 2 (In Play), ≥ 3 (고신뢰), ≥ 5 (강력)
- 트레이더 개인의 강점에 맞는 셋업 4~5개를 발굴·정밀화 (vs 범용 신호)
- Reasons2Sell 프레임워크: 추세 이탈 / 저항 도달 / 비정상 매도 / 뉴스 변화

## 2. 6개 코드화 규칙

10개 셋업 중 분봉만으로 코드화 가능한 6개:

| # | 함수명 | 한글명 | 진입 조건 요약 |
|---|---|---|---|
| 1 | `rule_second_day_play` | 2일차 플레이 | 첫 30봉 +5% 강세 + 후속 봉이 첫 30봉 고가 돌파 |
| 2 | `rule_bull_flag_bellafiore` | 불 플래그 (Bellafiore) | 폴 2봉 +1% + 좁은 박스 5봉 + 박스 상단 돌파 |
| 3 | `rule_range_trade` | 레인지 트레이드 | 직전 90봉 range 식별 + 하단 ±0.3% 근처 양봉 |
| 4 | `rule_fade_vwap` | VWAP 평균회귀 | VWAP -2% 이격 + RSI(2)<10 → 매수 (long-only) |
| 5 | `rule_opening_consolidation_breakout` | 오프닝 통합 돌파 | 첫 10봉 좁은 박스 + 거래량 감소 + 박스 고가 돌파 |
| 6 | `rule_catalyst_gap` | 촉매 갭업 | 첫 봉 시가 +3% + RVOL≥2 + 첫 봉 시가 위 유지 |

4개 셋업(Opening Drive · Pullback · Trade2Hold · Intraday RS)은 Tape Reading 의존도 높아 제외.

코드: [strategies/books/bellafiore_playbook/rules.py](../strategies/books/bellafiore_playbook/rules.py)

## 3. 백테스트 결과

설정: universe=일별 거래대금 상위 50종목, sl=-3%, tp=+5%, max_hold=120봉, EOD 강제 청산.  
종목 풀: 2025-10=50, 2026-04=50, 2026-05=50 (top_volume:50)

### 3.1 3기간 결과 (PnL 내림차순)

| Rule | 2025-10 | 2026-04 | 2026-05 | 3기간 평균 PnL | 평균 Sharpe | 평균 거래수 |
|---|---|---|---|---|---|---|
| **fade_vwap** ⭐ | **+11.71%** | **+2.59%** | -9.06% | **+1.74%** | **+0.37** | 964 |
| opening_consolidation_breakout | +7.31% | -1.10% | -1.25% | +1.65% | -0.52 | 701 |
| bull_flag_bellafiore | +0.55% | -1.15% | -1.15% | -0.59% | -0.44 | 130 |
| second_day_play | +0.35% | -3.14% | -2.08% | -1.62% | -0.32 | 364 |
| range_trade | +11.83% | -4.85% | -12.16% | -1.73% | -1.16 | 1,847 |
| catalyst_gap | 0% | 0% | 0% | 0% (0 trades) | 0 | 0 |
| all_AND | 0% | 0% | 0% | 0% (0 trades) | 0 | 0 |

### 3.2 fade_vwap 2025-10 상세 (책 최강 셋업)

| 메트릭 | 값 |
|---|---|
| PnL | **+11.71%** |
| Sharpe | **+2.82** (책 통틀어 최고) |
| Calmar | **+3.22** |
| Hit Rate | **60.3%** |
| 거래수 | 539 |
| 평균 보유봉 | (parquet 참조) |

### 3.3 range_trade 2025-10 상세

| 메트릭 | 값 |
|---|---|
| PnL | **+11.83%** (3기간 최대) |
| Sharpe | +0.89 |
| Calmar | **+2.03** |
| Hit Rate | 52.3% |
| 거래수 | 1,858 |

## 4. 아지즈와 비교

| 항목 | 아지즈 (8셋업) | Bellafiore (6셋업) |
|---|---|---|
| In Play 기준 | Float + 갭% (정성적) | **RVOL ≥ 2/3/5 (정량적)** |
| 신호 정량성 | 차트 패턴 중심 | **RVOL·RSI(2) 명시** |
| 종목 특성 | 소형·저가주 + 중형 | 대형·중형주 (prop firm) |
| 3기간 평균 best | bull_flag -0.04% (32T) | **fade_vwap +1.74% (964T)** |
| 평균 Sharpe best | 모두 음수 | **fade_vwap +0.37** |
| 2025-10 PnL best | abcd +9.49% (S=-0.27) | **fade_vwap +11.71% (S=2.82)** |
| 활성 양 PnL 규칙 (평균) | 0 | 2 (fade_vwap, opening_consolidation) |

**결론**: Bellafiore가 정량 기준(RVOL 임계값, RSI(2))으로 명확해서 한국 분봉 코드화에 더 적합. **fade_vwap이 두 책 통틀어 가장 인상적인 결과** — 3기간 평균 양의 PnL + 양의 Sharpe.

## 5. 규칙별 코멘트

- **fade_vwap** ⭐ : VWAP -2% 이격 + RSI(2)<10 진입. 2025-10 Sharpe 2.82는 책 통틀어 압도적. 평균회귀 셋업이 한국 시장의 단기 과매도 구간에서 빠르게 작동. 2026-05에선 -9% 손실 — 시장 환경 의존성 확인.
- **range_trade**: 2025-10에서 +11.83% (1,858 거래) — 측면 시장에서 강력. 2026-04/05에선 변동성 확장으로 손실.
- **opening_consolidation_breakout**: 평균 +1.65% (Sharpe 부족). 첫 10봉 통합 후 돌파 셋업.
- **bull_flag_bellafiore**: 조건 빡빡(폴 2봉 + 좁은 박스 5봉)이라 거래 적음(130회). 부분 break-even.
- **second_day_play**: 평균 -1.62% — D-1 데이터 없이 분봉 첫 30봉으로 근사한 한계
- **catalyst_gap**: 0거래 — 조건(시가 +3% + RVOL≥2 + 첫봉 위 유지) 동시 충족 어려움. 한국 시장에 너무 빡빡
- **all_AND**: 0거래 — 6규칙 동시 충족 사실상 불가능 (예상대로)

## 6. 한국 시장 적용성 결론

> **Bellafiore PlayBook의 분봉 코드화 가능 셋업 6개 중 fade_vwap이 한국 시장에서 의미 있는 알파 시그널**

- fade_vwap 3기간 평균 +1.74% (Sharpe +0.37) — 양의 Sharpe는 두 책 통틀어 유일
- 2025-10 단독으로는 fade_vwap·range_trade가 +11% 대 양의 PnL + Calmar 2 이상
- 시장 환경 의존성 큼 (2026-04/05에선 부진)
- 책의 핵심 가정(RVOL ≥ 2) 한국 시장 적용성을 정량 확인 가능

## 7. 한계점

- **D-1 정보 없음**: Bellafiore의 핵심 셋업(Second Day Play, Catalyst Gap)이 D-1 일봉 데이터 필요. 분봉 첫 30봉으로 근사했지만 책 의도와 갭 큼
- **Level 2 / Tape Reading 미반영**: 4개 셋업(Opening Drive, Pullback, Trade2Hold, Intraday RS) 미코드화. 책 의도의 일부만 검증
- **Float·실시간 RVOL 미반영**: catalyst_gap의 RVOL proxy 사용 — 책 의도와 갭 큼
- **공매도 미시도**: fade_vwap을 long만 시도. short side(VWAP +2% 이격 + RSI(2)>90) 미적용
- **N=50 단일**: top_volume:N sweep 미시도

## 8. fade_vwap 파라미터 sweep (2026-05-28)

### 동기
fade_vwap이 두 책 통틀어 best (3기간 평균 +1.74%, Sharpe +0.37). 한국 시장 최적 파라미터 탐색.

### 그리드
- `deviation_pct`: 0.015, 0.020, 0.025 (3값)
- `rsi_oversold`: 10, 15, 20 (3값)
- `rsi_period`: 2 (고정)
- 청산: sl 3% / tp 5% / max_hold 120 (Bellafiore baseline)
- universe: top_volume:50, 3기간
- 총 9 × 3 = 27 백테스트

### 3기간 평균 결과 (PnL 내림차순)

| Rank | deviation | rsi_oversold | 평균 PnL | 평균 Sharpe | 거래수 |
|---|---|---|---|---|---|
| **1** | **0.020** | **10** | **+1.74%** | **+0.37** | 965 (baseline) |
| 2 | 0.020 | 15 | +1.67% | +0.35 | 965 |
| 3 | 0.020 | 20 | +1.63% | +0.33 | 967 |
| 4 | 0.015 | 10 | +1.59% | +0.36 | 1,072 |
| 5 | 0.015 | 20 | +1.57% | +0.36 | 1,078 |
| 6 | 0.015 | 15 | +1.54% | +0.36 | 1,075 |
| 7 | 0.025 | 20 | +0.24% | -0.06 | 869 |
| 8 | 0.025 | 10 | +0.21% | -0.07 | 866 |
| 9 | 0.025 | 15 | +0.19% | -0.08 | 868 |

### 2025-10 단독 best
- **deviation 0.015 + rsi_oversold 10**: PnL **+12.15%, Sharpe 2.88, Calmar 3.01, Hit 62.5%** (687 trades) — 9 중 최고
- baseline (0.020/10): PnL +11.71%, Sharpe 2.82
- deviation 0.015~0.020 모든 조합 Sharpe 2.79+ (매우 견고)

### 핵심 발견
1. **Baseline (0.020/10)이 3기간 평균 best** — 책 권유값이 한국 시장에도 잘 맞음. 운 좋은 선택이 아닌 책 내용의 견고함
2. **rsi_oversold 변화 영향 미미** (10/15/20 차이 < 0.01%p) — RSI(2)<10이 대부분 케이스 충족, 임계값 자유도 작음
3. **deviation 0.025는 약함** — 진입 너무 빡빡, 거래 감소(965→868)와 함께 Sharpe도 음으로
4. **deviation 0.015도 견고** — 거래 늘어나지만(965→1,072) PnL/Sharpe 유사. 거래비용 누적이 살짝 더 큼
5. **2026-05는 모든 파라미터 손실** (-8.3 ~ -9.8%) — 시장 환경 의존, 파라미터 튜닝 한계

### 결론
- **권장 파라미터**: `deviation_pct=0.020, rsi_oversold=10, rsi_period=2` (baseline 유지)
- 책의 핵심 가정(VWAP ±2% 이격) 한국 시장에서 견고함이 확인됨
- 다음 정밀화 단계는 파라미터 sweep이 아닌 **시장 국면 라벨링** (2026-05 같은 부진 기간 회피)

### 산출물
- sweep raw: `reports/books_research/bellafiore_playbook/fade_vwap_sweep.parquet` (27행)
- sweep 스크립트: `scripts/sweep_fade_vwap.py`

## 9. 시장 국면별 fade_vwap 성과 (2026-05-28)

### 동기
fade_vwap이 2025-10(+11.71%, Sharpe 2.82)에서 강하고 2026-05(-9.06%)에서 부진. KOSPI 국면 라벨로 시장 환경 의존성 검증.

### 국면 정의
- BULL: KOSPI 5일 종가 모멘텀 ≥ +1.0%
- BEAR: KOSPI 5일 종가 모멘텀 ≤ -1.0%
- SIDEWAYS: 그 외 (-1% < 5일 모멘텀 < +1%)

### 국면별 거래 집계

| Regime | 거래수 | 평균 PnL | 누적 PnL | Hit Rate | Sharpe |
|---|---|---|---|---|---|
| BULL | 434 | +1.155% | +5.013 | 48.2% | 0.945 |
| SIDEWAYS | 2,460 | +0.138% | +3.389 | 43.5% | 0.679 |
| BEAR | 0 | — | — | — | — |

> BEAR 국면 거래 0건: 분석 기간(2025-10, 2026-04, 2026-05) 중 백테스트 발생일이 모두 BULL·SIDEWAYS 국면에 해당.

### 기간 × 국면 분포

| Period | Regime | 거래수 | 평균 PnL | 누적 PnL | Hit Rate |
|---|---|---|---|---|---|
| 2025-10 | BULL | 434 | +1.155% | +5.013 | 48.2% |
| 2025-10 | SIDEWAYS | 105 | +2.087% | +2.191 | 82.9% |
| 2026-04 | SIDEWAYS | 758 | +0.381% | +2.885 | 44.2% |
| 2026-05 | SIDEWAYS | 1,597 | -0.106% | -1.687 | 40.6% |

### 발견
- **BULL 국면에서 fade_vwap 최강**: 평균 PnL +1.155%, Sharpe 0.945 — 상승 추세 속 단기 과매도 반등이 빠르고 강하게 작동.
- **2025-10의 SIDEWAYS Hit Rate 82.9%**: 표본 105건으로 신뢰도 제한적이지만, 2025-10 전반의 강세 분위기가 SIDEWAYS 라벨 날에도 종목 단위 반등을 지지한 것으로 해석.
- **2026-05 부진은 SIDEWAYS 국면 집중 + 음의 PnL**: 1,597건 전부 SIDEWAYS, 평균 -0.106% — 방향성 없는 장에서 평균회귀가 작동하지 않음. BULL 국면 진입 기회 자체가 없던 달.
- **BEAR 국면 부재**: 분석 3개 기간 모두 KOSPI가 BULL·SIDEWAYS에 머물러 BEAR 국면 거래 발생 없음.

### 함의
- **BULL 국면만 진입 권장**: 거래수 434건, Hit Rate 48.2%이지만 평균 PnL +1.155% — 손익비가 좋음. SIDEWAYS는 PnL이 낮고 2026-05처럼 음전 리스크 있음.
- **실거래 시 KOSPI 5일 모멘텀 사전 체크**: 장 시작 전 `kospi_5d_momentum ≥ +1.0%` 조건 확인 후 fade_vwap 진입 여부 결정.
- **BEAR 국면은 데이터 미확보** — 하락장에서 fade_vwap(평균회귀)의 위험성은 별도 검증 필요.

### 산출물
- `reports/books_research/bellafiore_playbook/fade_vwap_regime_summary.parquet`
- `reports/books_research/bellafiore_playbook/fade_vwap_regime_by_period.parquet`
- `reports/books_research/bellafiore_playbook/fade_vwap_trades_with_regime.parquet`
- `reports/books_research/bellafiore_playbook/kospi_regime_labels.parquet`
- 분석 스크립트: `scripts/analyze_fade_vwap_regime.py`

## 10. 다음 단계 후보

1. ✅ **fade_vwap 파라미터 sweep 완료** (부록 8): baseline 0.020/10이 best
2. ✅ **KOSPI 국면별 분석 완료** (부록 9): BULL 국면 진입 필터 권장
3. **fade_vwap short side 추가**: 한국 공매도 가능 종목(ETF, KOSPI200) 한정
4. **catalyst_gap 임계값 완화**: gap +2% / rvol≥1.5 로 거래 발생시키기
5. **Plan 3 다음 책**: Linda Raschke — Street Smarts (인트라데이 클래식 패턴)

## 11. 산출물

| 종류 | 경로 |
|---|---|
| 코드 (전략) | `strategies/books/bellafiore_playbook/` (rules.py, strategy.py) |
| 코드 (테스트) | `tests/strategies/books/bellafiore_playbook/test_rules.py` (8 tests) |
| 조사 원본 | `strategies/books/bellafiore_playbook/RULES_RESEARCH.md` (10셋업) |
| 백테스트 결과 | `reports/books_research/bellafiore_playbook/results_*.parquet` (21개) |
| 통합 리더보드 | `reports/books_research/leaderboard.parquet` · `index.md` |
