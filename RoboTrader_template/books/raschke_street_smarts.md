# 책 3: Linda Raschke — Street Smarts: High Probability Short-Term Trading Strategies

> 카테고리: 단기 트레이딩 (인트라데이 + 스윙)  
> 데이터 입도: 분봉 (Phase 1) + 일봉 (Phase 2 예정)  
> Phase 1 완료: 2026-05-28  
> 상세 자료: [백테스트 결과](../reports/books_research/raschke_street_smarts/) · [조사 원본](../strategies/books/raschke_street_smarts/RULES_RESEARCH.md) · [코드](../strategies/books/raschke_street_smarts/)

## 1. 책 요약

Linda Bradford Raschke + Laurence Connors 공저 (1995/1996, ISBN 0-9650461-0-9). 미국 선물·주식 단기 트레이딩 셋업 플레이북.

특징 (vs 아지즈/Bellafiore):
- **일봉 기반 셋업 다수** — 분봉만 다룬 두 책과 차별
- **인디케이터 명확** — ADX, Stochastic, RSI, EMA, 볼린저밴드 정확한 파라미터
- 거짓 돌파 페이드 + 변동성 사이클 + 추세 풀백 세 축
- Raschke 본인이 "Holy Grail은 2010년대에도 여전히 유효" 명시 언급

## 2. Phase 1 — 분봉 5개 셋업

| # | 함수명 | 한글명 | 진입 조건 요약 |
|---|---|---|---|
| 1 | `rule_holy_grail` | Holy Grail | ADX(14)>30 상승 + 20EMA 첫 풀백 + 풀백봉 고가 돌파 |
| 2 | `rule_anti` | Anti | %K(7)/%D(10) 스토캐스틱 훅 + 20EMA 필터 + 임펄스 후 |
| 3 | `rule_gimmee_bar` | Gimmee Bar | 볼린저밴드 횡보 + 밴드 하단 터치 + 반전 양봉 |
| 4 | `rule_nr4_breakout` | NR4 Breakout (변형) | 직전 30봉 NR4 + 다음 봉 NR4 봉 고점 돌파 |
| 5 | `rule_momentum_pinball` | Momentum Pinball | 첫 60봉 LBR/RSI(3 of ROC 1) < 30 + 첫 60봉 고점 돌파 |

코드: [strategies/books/raschke_street_smarts/rules.py](../strategies/books/raschke_street_smarts/rules.py)

## 3. Phase 1 백테스트 결과

설정: universe = top_volume:50, sl 3% / tp 5% / max_hold 120봉.

### 3.1 3기간 결과 (PnL 내림차순)

| Rule | 2025-10 | 2026-04 | 2026-05 | 3기간 평균 PnL | 평균 Sharpe | 거래수 평균 |
|---|---|---|---|---|---|---|
| **anti** ⭐ | **+59.05%** | -11.31% | -17.01% | **+10.24%** | -2.27 | 1,860 |
| momentum_pinball | +9.67% | +0.14% | -2.01% | +2.60% | -0.24 | 439 |
| gimmee_bar | +5.18% | +1.09% | -2.10% | +1.39% | -0.86 | 1,515 |
| nr4_breakout | +10.17% | -6.72% | -15.83% | -4.12% | -1.70 | 2,333 |
| holy_grail | -2.98% | -4.58% | -13.04% | -6.87% | -1.62 | 2,153 |

### 3.2 Anti 2025-10 상세 (책 통틀어 최대 절대 PnL)

| 메트릭 | 값 |
|---|---|
| PnL | **+59.05%** ⭐ (3 책 통틀어 1위) |
| Sharpe | +0.48 |
| **Calmar** | **+7.59** (3 책 통틀어 1위) |
| Hit Rate | 49.6% |
| 거래수 | 1,561 |

**주의**: 다른 기간(-11.31%, -17.01%)이 큰 손실 → 시장 의존성 극도

### 3.3 Holy Grail 부진 (예상 외)

Raschke 본인이 "여전히 유효"라고 추천한 Holy Grail이 한국 분봉에서 -6.87% 평균 손실. 가능 원인:
- 분봉 ADX 노이즈가 큼 (일봉 ADX와 다른 특성)
- 풀백 조건이 너무 자주 충족 → 거래수 2,153회 → 거래비용 누적
- 20EMA 첫 풀백 정의의 모호성 — 한국 분봉의 짧은 풀백을 본 풀백으로 잘못 인식

원서는 일봉 또는 5분봉 권유 — 1분봉 적용이 적합하지 않을 수 있음.

## 4. 책 3권 베스트 비교

| 책 | 베스트 규칙 | 3기간 평균 PnL | 2025-10 PnL | 평균 Sharpe |
|---|---|---|---|---|
| 아지즈 | bull_flag | -0.04% | -0.07% | -0.11 |
| Bellafiore | fade_vwap | +1.74% (964T) | +11.71% (S=2.82) | **+0.37** ⭐ |
| Raschke | **anti** | **+10.24%** (1,860T) | **+59.05%** (C=7.59) | -2.27 |

**fade_vwap (Bellafiore)**: 안정 알파, 평균 Sharpe 양 — 책 통틀어 유일한 양 Sharpe  
**anti (Raschke)**: 절대 PnL 압도적 (+10.24%), 변동성 극도 — 시장 환경 의존성 큼

## 5. 규칙별 코멘트

- **anti** ⭐ : 임펄스 무브 후 스토캐스틱 훅. 2025-10 한국 시장의 단기 모멘텀 전환을 정확히 포착. Calmar 7.59는 위험 대비 보상 우수. 단 다른 기간은 -11~-17% → 시장 의존
- **momentum_pinball**: 거래수 적음(439), 부분 양 PnL. 첫 1시간봉 신호 — 한국 09:00~10:00 적용
- **gimmee_bar**: 볼린저 횡보장 반전. 3기간 평균 +1.39% (양). 거래수 보통
- **nr4_breakout**: 변동성 압축 후 돌파. 2025-10에서 +10% 양, 다른 기간 음 — 일관성 부족
- **holy_grail**: 부진 — 분봉 ADX 노이즈, 풀백 정의 문제, 거래 과다

## 6. 한국 시장 적용성

### Anti — 후보 알파 (with caveats)
- 2025-10 PnL +59% (Calmar 7.59) — 절대 수익 압도적
- 평균 Sharpe -2.27 — 변동성 큼, 안정성 부족
- 다른 기간 음 PnL — 시장 의존성 극도
- **Bellafiore fade_vwap과 유사하게 변동성 필터 + 국면 필터 검증 필요**

### Holy Grail — 한국 분봉 부적합
- Raschke 본인 권유에도 한국 1분봉에서 작동 안 함
- 일봉 또는 5분봉 리샘플 후 재테스트 필요
- Phase 2에서 일봉 백테스트로 재검증 가능

## 7. 한계점

- Phase 1 분봉 5개만 — 일봉 5개(Turtle Soup, Turtle Soup +1, 80-20, ADX Gapper, 2-Period ROC) 미실시
- Anti의 시장 의존성 미해결 — fade_vwap처럼 변동성·국면 필터 추가 검증 가능
- Holy Grail은 1분봉 부적합 — 5분봉 리샘플 또는 일봉 재테스트 필요
- 책 권유 파라미터 그대로 — 한국 시장 최적화 sweep 미실시

## 8. Anti 변동성·국면 필터 검증 (2026-05-28)

### 동기
Anti가 3기간 평균 +10.24% / 2025-10 +59% (Calmar 7.59) / 다른 기간 -11~-17%. fade_vwap 패턴으로 변동성·국면 필터 효과 정량화.

### 4분면 분포 (regime × volatility)

| quadrant | n_trades | pnl_mean | pnl_sum | hit_rate | sharpe |
|---|---|---|---|---|---|
| BULL_LOWVOL | 1,189 | +1.07% | +12.75 | 50.3% | **+1.03** |
| BULL_HIGHVOL | 65 | +0.37% | +0.24 | 43.1% | +1.90 (소표본) |
| SIDEWAYS_LOWVOL | 4,327 | **-0.16%** | -7.03 | 39.6% | -0.79 |

> 주: 분석 기간(2025-10 ~ 2026-05) 전체가 BULL or SIDEWAYS — BEAR 거래 0건.  
> HIGHVOL 날은 5일뿐 (변동성 3% 이상 날이 거의 없음).

### 필터 시뮬레이션

| filter | n_trades | pnl_sum | pnl_mean | hit_rate | sharpe |
|---|---|---|---|---|---|
| baseline (모든 거래) | 5,581 | +5.96 | +0.11% | 41.9% | +0.21 |
| low_vol only (변동성<3%) | 5,516 | +5.72 | +0.10% | 41.9% | +0.20 |
| **BULL only** | **1,254** | **+12.99** | **+1.04%** | **49.9%** | **+1.02** |
| BULL + low_vol | 1,189 | +12.75 | +1.07% | 50.3% | **+1.03** |
| BULL+SIDEWAYS only (BEAR 회피) | 5,581 | +5.96 | +0.11% | 41.9% | +0.21 |
| BULL+SIDEWAYS + low_vol | 5,516 | +5.72 | +0.10% | 41.9% | +0.20 |

### 핵심 발견

1. **SIDEWAYS가 손실의 원인** — SIDEWAYS_LOWVOL(4,327건, -7.03 pnl_sum)이 BULL 수익을 잠식. 분석 기간에 BEAR가 없어 BULL 필터만으로 손실 원천 제거.
2. **BULL 필터가 최대 효과** — baseline Sharpe +0.21 → BULL only +1.02 (+5배). pnl_sum +5.96 → +12.99 (거래수는 1/4로 줄어 77% 감소). 집중도·효율성 모두 개선.
3. **변동성 필터 추가 효과 미미** — HIGHVOL 날이 5일뿐 (2%)이라 low_vol 필터 단독 효과 거의 없음 (-0.01 Sharpe). BULL 필터와 조합해도 marginal 개선에 그침.
4. **fade_vwap 비교** — fade_vwap은 저변동성 자체가 핵심 필터였으나, anti는 국면(BULL/SIDEWAYS 구분)이 결정적. 같은 필터가 다른 방식으로 작동.

### 결론

**권장 필터: BULL only (KOSPI 5일 모멘텀 ≥ +1%)** — 가장 단순하고 가장 효과적.  
거래수를 5,581 → 1,254 (22%)로 줄이면서 Sharpe +0.21 → +1.02, pnl_sum +5.96 → +12.99로 개선.  
변동성 필터는 현재 데이터에서 추가 가치 없음 (필요 시 BEAR 환경에서 재검증).

### 산출물

- `reports/books_research/raschke_street_smarts/anti_regime_quadrant_summary.parquet`
- `reports/books_research/raschke_street_smarts/anti_filter_simulation.parquet`
- `reports/books_research/raschke_street_smarts/anti_regime_by_period.parquet`
- `reports/books_research/raschke_street_smarts/anti_trades_with_regime.parquet`
- 분석 스크립트: `scripts/analyze_anti_regime.py`

## 9. Phase 2 계획 (후속)

- 일봉 5개 셋업: Turtle Soup / Turtle Soup +1 / 80-20 / ADX Gapper / 2-Period ROC
- 기존 `backtest/engine.py` 일봉 엔진 활용
- daily_prices 테이블 사용
- 별도 dispatch 예정

## 10. 산출물

| 종류 | 경로 |
|---|---|
| 코드 (전략) | `strategies/books/raschke_street_smarts/` (rules.py, strategy.py) |
| 코드 (테스트) | `tests/strategies/books/raschke_street_smarts/test_rules.py` (6 tests) |
| 조사 원본 | `strategies/books/raschke_street_smarts/RULES_RESEARCH.md` (10셋업) |
| 백테스트 결과 | `reports/books_research/raschke_street_smarts/results_*.parquet` |
| 통합 리더보드 | `reports/books_research/leaderboard.parquet` · `index.md` |
