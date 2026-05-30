# 트레이딩 책 10권 — 통합 리더보드

> 생성일: 2026-05-27  
> 설계서: [../../docs/superpowers/specs/2026-05-27-books-research-backtest-design.md](../../docs/superpowers/specs/2026-05-27-books-research-backtest-design.md)  
> 구현 계획: [../../docs/superpowers/plans/2026-05-27-books-research-plan-1-infra-and-aziz.md](../../docs/superpowers/plans/2026-05-27-books-research-plan-1-infra-and-aziz.md)

## 진행 상태

| # | Book ID | 책 | Status | Best PnL |
|---|---|---|---|---|
| 1 | aziz_day_trade | Andrew Aziz — How to Day Trade for a Living | ✅ 완료 | 복원 시 abcd 2025-10 **+9.49%** (top_volume:50, sl3%/tp5%/mh120) |
| 2 | bellafiore_playbook | Mike Bellafiore — One Good Trade / PlayBook | ✅ 완료 | **fade_vwap 평균 +1.74% Sharpe +0.37, 2025-10 +11.71% Sharpe 2.82** ⭐ |
| 3 | raschke_street_smarts | Linda Raschke — Street Smarts | ✅ Phase 1 | **anti 평균 +10.24%, 2025-10 +59% Calmar 7.59** ⭐ |
| 4 | oneil_canslim | William O'Neil — 최고의 주식 최적의 타이밍 | ✅ Phase A+B | Phase B 7거래 +7.04% 승률 71% (표본 작음) |
| 5 | minervini_vcp | Mark Minervini — 초수익 성장주 투자 | ✅ 완료 | **volume_dryup B Sharpe 1.41 Calmar 2.38** 153T (BULL 편향) |
| 6 | weinstein_stages | Stan Weinstein — Secrets for Profiting | ✅ 완료 | **ma30w_bounce B PnL +4.18% Sharpe 0.30 Calmar 1.92** 43T (BULL 편향) |
| 7 | elder_triple_screen | Alexander Elder — Trading for a Living | ✅ 완료 | **ema_pullback A PnL +23.76% Sharpe 1.22 Calmar 2.64** 134T (BULL 편향) |
| 8 | lynch_one_up | Peter Lynch — 월가의 영웅 | ✅ 완료 | **value_balance_sheet B per-trade +2.84% 승률 52.6%** 114T (데이터 제약 inconclusive) |
| 9 | greenblatt_magic_formula | Joel Greenblatt — Magic Formula | ✅ 완료 | **magic_formula_top B per-trade +4.88% 승률 61.4%** 197T (6개월 단일국면) |
| 10 | osullivan_what_works | James O'Shaughnessy — What Works on Wall Street | ✅ 완료 | **low_psr B per-trade +4.63% 승률 54.5%** 200T (6개월 단일국면) |
| 11 | moonbyungro_metric | 문병로 — 메트릭 스튜디오 (한국 저자 1호) | ✅ 완료 | **value_composite_kr K +13.68% Sharpe 0.09** 218T (다년 2021~2026, Sharpe 붕괴) |
| 12 | hongyongchan | 홍용찬 — 실전 퀀트투자 (한국 저자 2호) | ✅ 완료 | **value4_low K +12.87% Sharpe 0.11** 213T (게이트 무용·소형주20%>40% 발견) |
| 13 | systrader79 | systrader79 — 주식투자 ETF로 시작하라 (자산배분) | ✅ MVP | **평균모멘텀스코어 MDD 19.08%<KOSPI 21.84%** CAGR24.8% (MDD방어✓ Sharpe개선✗, 폭등장 노출제한) |

## 전체 백테스트 메트릭 (PnL 내림차순, 정렬)

> 1책(아지즈) × 8 single + 1 all_AND × 3기간(2025-10 / 2026-04 / 2026-05) = 27행

| Rank | Book | Rule/Combo | Mode | Period | n_stocks | n_trades | PnL % | Sharpe | Calmar | Hit Rate | MaxDD % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | aziz_day_trade | top_reversal | single | 2026-04 | 581 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | aziz_day_trade | all_AND | all_AND | 2026-04 | 581 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 3 | aziz_day_trade | top_reversal | single | 2025-10 | 555 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 4 | aziz_day_trade | all_AND | all_AND | 2026-05 | 503 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 5 | aziz_day_trade | top_reversal | single | 2026-05 | 503 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 | aziz_day_trade | all_AND | all_AND | 2025-10 | 555 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 7 | aziz_day_trade | bull_flag | single | 2026-05 | 503 | 23 | -0.02 | -0.07 | +0.01 | 0.022 | 0.12 |
| 8 | aziz_day_trade | bull_flag | single | 2026-04 | 581 | 38 | -0.02 | -0.09 | +0.50 | 0.023 | 0.14 |
| 9 | aziz_day_trade | bull_flag | single | 2025-10 | 555 | 35 | -0.07 | -0.17 | -0.02 | 0.016 | 0.13 |
| 10 | aziz_day_trade | vwap_reversal | single | 2026-05 | 503 | 3,986 | -2.68 | -2.71 | +0.00 | 0.379 | 7.86 |
| 11 | aziz_day_trade | vwap_reversal | single | 2026-04 | 581 | 5,683 | -3.89 | -2.42 | -0.16 | 0.400 | 9.20 |
| 12 | aziz_day_trade | vwap_reversal | single | 2025-10 | 555 | 8,409 | -6.54 | -2.99 | -0.19 | 0.412 | 10.72 |
| 13 | aziz_day_trade | support_resistance | single | 2026-04 | 581 | 36,994 | -11.66 | -3.83 | -0.39 | 0.410 | 20.50 |
| 14 | aziz_day_trade | ma_trend | single | 2026-05 | 503 | 14,446 | -11.90 | -7.18 | -0.60 | 0.311 | 16.34 |
| 15 | aziz_day_trade | orb | single | 2026-05 | 503 | 17,552 | -13.73 | -5.71 | -0.56 | 0.237 | 17.82 |
| 16 | aziz_day_trade | red_to_green | single | 2026-05 | 503 | 18,033 | -13.74 | -5.57 | -0.55 | 0.241 | 17.99 |
| 17 | aziz_day_trade | support_resistance | single | 2026-05 | 503 | 19,179 | -14.50 | -7.51 | -0.47 | 0.378 | 19.69 |
| 18 | aziz_day_trade | abcd | single | 2026-04 | 581 | 40,760 | -15.58 | -4.42 | -0.55 | 0.385 | 24.07 |
| 19 | aziz_day_trade | abcd | single | 2026-05 | 503 | 21,407 | -16.37 | -7.22 | -0.54 | 0.366 | 22.04 |
| 20 | aziz_day_trade | ma_trend | single | 2026-04 | 581 | 43,507 | -17.64 | -5.19 | -0.56 | 0.387 | 25.23 |
| 21 | aziz_day_trade | orb | single | 2026-04 | 581 | 47,894 | -19.50 | -5.44 | -0.63 | 0.367 | 26.68 |
| 22 | aziz_day_trade | red_to_green | single | 2026-04 | 581 | 48,706 | -19.75 | -5.33 | -0.65 | 0.369 | 26.98 |
| 23 | aziz_day_trade | support_resistance | single | 2025-10 | 555 | 45,039 | -22.02 | -6.87 | -0.69 | 0.381 | 26.82 |
| 24 | aziz_day_trade | red_to_green | single | 2025-10 | 555 | 43,248 | -24.18 | -6.94 | -0.76 | 0.299 | 28.19 |
| 25 | aziz_day_trade | orb | single | 2025-10 | 555 | 44,094 | -24.71 | -7.13 | -0.78 | 0.305 | 28.71 |
| 26 | aziz_day_trade | abcd | single | 2025-10 | 555 | 44,261 | -26.12 | -7.53 | -0.77 | 0.353 | 30.72 |
| 27 | aziz_day_trade | ma_trend | single | 2025-10 | 555 | 42,955 | -29.58 | -8.76 | -0.88 | 0.312 | 32.16 |

## Bellafiore PlayBook 결과 (top_volume:50 + sl 3% / tp 5% / mh 120)

> 3기간 × 6 single + all_AND = 21행. 동일 universe·청산 룰로 아지즈와 직접 비교 가능.

### 3기간 평균 (PnL 내림차순)

| Rank | Rule | 평균 PnL | 평균 Sharpe | 평균 거래수 |
|---|---|---|---|---|
| 1 | fade_vwap ⭐ | **+1.74%** | **+0.37** | 964 |
| 2 | opening_consolidation_breakout | +1.65% | -0.52 | 701 |
| 3 | bull_flag_bellafiore | -0.59% | -0.44 | 130 |
| 4 | second_day_play | -1.62% | -0.32 | 364 |
| 5 | range_trade | -1.73% | -1.16 | 1,847 |
| 6 | catalyst_gap | 0% | 0 | 0 (조건 빡빡) |
| 7 | all_AND | 0% | 0 | 0 (동시 충족 불가) |

### 2025-10 단독 상위 (Bellafiore — 5개 양 PnL)

| Rank | Rule | PnL | Sharpe | Calmar | Hit Rate | 거래수 |
|---|---|---|---|---|---|---|
| 1 | range_trade | +11.83% | +0.89 | +2.03 | 52.3% | 1,858 |
| 2 | **fade_vwap** ⭐ | **+11.71%** | **+2.82** | **+3.22** | **60.3%** | 539 |
| 3 | opening_consolidation_breakout | +7.31% | -0.88 | +0.05 | 19.3% | 1,329 |
| 4 | bull_flag_bellafiore | +0.55% | +0.48 | +0.98 | 39.8% | 114 |
| 5 | second_day_play | +0.35% | +0.01 | +0.02 | 2.2% | 144 |

### 아지즈 vs Bellafiore 직접 비교

| 항목 | 아지즈 best | Bellafiore best |
|---|---|---|
| 3기간 평균 PnL | bull_flag -0.04% | **fade_vwap +1.74%** |
| 3기간 평균 Sharpe | 모두 음 | **fade_vwap +0.37** |
| 2025-10 PnL | abcd +9.49% | **fade_vwap +11.71%** |
| 2025-10 Sharpe | abcd -0.27 | **fade_vwap +2.82** |
| 2025-10 Calmar | abcd +0.38 | **fade_vwap +3.22** |
| 양 PnL 규칙 (평균) | 0 | 2 (fade_vwap, opening_consolidation) |

**결론**: Bellafiore의 RVOL 정량 기준이 한국 분봉 코드화에 더 적합. fade_vwap이 두 책 통틀어 가장 인상적인 결과.

## Raschke Street Smarts 결과 — Phase 1 분봉 5개 (top_volume:50 + sl 3% / tp 5% / mh 120)

> Phase 1 = 분봉 코드화 가능한 5셋업 (Holy Grail / Anti / Gimmee Bar / NR4 / Momentum Pinball).  
> 일봉 전용 5셋업(Turtle Soup, 80-20, ADX Gapper, 2-Period ROC, Turtle Soup +1)은 Phase 2 후속.

### 3기간 평균 (PnL 내림차순)

| Rank | Rule | 평균 PnL | 평균 Sharpe | 평균 Calmar | 거래수 평균 |
|---|---|---|---|---|---|
| 1 | **anti** ⭐ | **+10.24%** | -2.27 | **+2.21** | 1,860 |
| 2 | momentum_pinball | +2.60% | -0.24 | +0.04 | 439 |
| 3 | gimmee_bar | +1.39% | -0.86 | +0.23 | 1,515 |
| 4 | nr4_breakout | -4.12% | -1.70 | -0.10 | 2,333 |
| 5 | holy_grail | -6.87% | -1.62 | -0.07 | 2,153 |

### 2025-10 단독 상위 (4/5 양 PnL)

| Rank | Rule | PnL | Sharpe | Calmar | Hit | 거래수 |
|---|---|---|---|---|---|---|
| 1 | **anti** ⭐⭐ | **+59.05%** | **+0.48** | **+7.59** | 49.6% | 1,561 |
| 2 | nr4_breakout | +10.17% | -0.03 | +0.36 | 48.7% | 2,114 |
| 3 | momentum_pinball | +9.67% | -0.02 | +0.13 | 4.6% | 322 |
| 4 | gimmee_bar | +5.18% | -1.41 | +0.33 | 45.6% | 1,862 |
| 5 | holy_grail | -2.98% | -0.44 | +0.21 | 45.5% | 2,263 |

### 책 3권 베스트 비교

| 책 | 베스트 | 3기간 평균 PnL | 2025-10 PnL | 평균 Sharpe |
|---|---|---|---|---|
| 아지즈 | bull_flag | -0.04% | -0.07% | -0.11 |
| Bellafiore | fade_vwap | +1.74% (964T) | +11.71% (S=2.82) | **+0.37** ⭐ |
| Raschke | **anti** | **+10.24%** (1,860T) | **+59.05%** (C=7.59) | -2.27 |

**fade_vwap (Bellafiore)**: 안정 알파 + 평균 Sharpe 양  
**anti (Raschke)**: 절대 PnL 압도적 + 변동성 극도

### 핵심 관찰
- Anti가 3 책 통틀어 최대 절대 PnL (+10.24% 평균, +59.05% 2025-10)
- Calmar 7.59 (2025-10) — 위험 대비 보상 우수
- 그러나 평균 Sharpe -2.27 / 다른 기간 음 PnL → fade_vwap처럼 변동성·국면 필터 추가 검증 가치
- **Holy Grail은 부진 (-6.87%)** — Raschke 본인 추천이었지만 1분봉 부적합. 5분봉/일봉 재테스트 필요

---

## O'Neil CANSLIM 결과 — Phase A+B (일봉 + 재무 + RS, 단일 기간)

> 데이터 기간 한계: 2025-12-08 ~ 2026-02-03 (38거래일, quant_factors 가용 기간 제약).  
> 전 38일 BULL — 약세장 미검증.

### Phase A vs Phase B

| Phase | 거래 | 승률 | 평균 PnL | 수익:손실 | 누적 |
|---|---|---|---|---|---|
| A (스크리너만, 완화 버전) | 18 | 50.0% | +4.84% | 2.25 | +87.12% |
| **B (스크리너 + 패턴)** | **7** | **71.4%** | **+7.04%** | 1.75 | +49.26% |

### Phase B 청산
- take_profit 2 / stop_loss 2 / end_of_data 3
- 패턴: cup_handle 5, flat_base 2

### 책 4권 통합 비교

| 책 | 데이터 | 베스트 | 평균 PnL | 평균 Sharpe | 표본 |
|---|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | -0.11 | 32T |
| Bellafiore | 분봉 | fade_vwap | +1.74% | **+0.37** | 964T |
| Raschke | 분봉 | anti | +10.24% | -2.27 | 1,860T |
| **O'Neil** | **일봉+재무+RS** | **CANSLIM+패턴** | **+7.04%** | (미계산) | **7T** |

### 결론
- 방향성 양호 (승률 71%, 평균 +7%)
- 통계 신뢰도 가장 낮음 (표본 7건)
- 데이터 기간 확장 + 약세장 포함 재검증 필요
- CANSLIM은 CANDIDATE_ALPHAS 미등록 — 표본 부족으로 후보 자격 미달

---

## Minervini VCP 결과 — 일봉 (Book 5)

> daily_prices 실측 224일 (2025-07-01 ~ 2026-05-29). universe top_volume:50. RS universe 12주 백분위.

### Variant A vs B 베스트
- **A**: volume_dryup +18.17% Sharpe 1.12 Calmar 2.30 (444 trades, hit 54.2%, avg hold 4.7일)
- **B**: volume_dryup +20.27% Sharpe 1.41 Calmar 2.38 (153 trades, hit 62.0%, avg hold 9.0일) ⭐
- trend_template / all_AND: 표본 0 (220봉 guard + 데이터 224일 한계)
- vcp_breakout / tight_closes: 표본 2건 (통계 무의미)

### 책 5권 비교

| 책 | 데이터 | 베스트 | 평균 PnL | 평균 Sharpe | 표본 |
|---|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | -0.11 | 32T |
| Bellafiore | 분봉 | fade_vwap | +1.74% | +0.37 | 964T |
| Raschke | 분봉 | anti | +10.24% | -2.27 | 1,860T |
| O'Neil | 일봉+재무+RS | CANSLIM+패턴 | +7.04% | — | 7T |
| **Minervini** | **일봉+RS자체** | **volume_dryup B** | **+20.27%** | **+1.41** | **153T** |

### 결론
- Variant B(sl 8% / tp 12% / mh 20)가 A(sl 8% / tp 20% / mh 35)보다 Sharpe·hit 우세 → 한국 시장 빠른 익절 유리.
- volume_dryup B는 5권 통틀어 가장 인상적인 일봉 단독 룰 (Sharpe 1.41, hit 62%).
- 단일 BULL 구간(146/204=71.6%) 편향 위험 + BEAR 22일 표본 부족 → walk-forward 후 CANDIDATE_ALPHAS 등록 권장.

상세: [minervini_vcp/report.md](minervini_vcp/report.md)

---

## 책별 베스트

### aziz_day_trade (Andrew Aziz — How to Day Trade for a Living)
- **베스트 규칙**: `bull_flag` (3기간 평균 PnL -0.04%, 거래수 평균 32회 — 진입조건이 빡빡해 거래가 거의 안 일어남)
- **결론**: 미국식 인트라데이 모멘텀 셋업 8개 중 7개가 한국 분봉에서 손실(-3.9 ~ -29.6%), 1개만 break-even
- **자세히**: [aziz_day_trade/report.md](aziz_day_trade/report.md)

### bellafiore_playbook (Mike Bellafiore — One Good Trade / The PlayBook)
- **베스트 규칙**: `fade_vwap` (3기간 평균 PnL +1.74%, 평균 Sharpe +0.37 — 책 통틀어 유일한 양 Sharpe)
- **2025-10 단독**: PnL +11.71%, Sharpe 2.82, Calmar 3.22, Hit 60.3% (539 trades)
- **결론**: VWAP -2% 이격 + RSI(2)<10 평균회귀가 한국 분봉 시장에서 의미 있는 알파 시그널
- **자세히**: [bellafiore_playbook/](bellafiore_playbook/)

### raschke_street_smarts (Linda Raschke — Street Smarts)
- **베스트 규칙**: `anti` (3기간 평균 PnL **+10.24%**, 2025-10 **+59.05%** Calmar **7.59** — 책 3권 통틀어 최대 절대 PnL)
- **2025-10 단독**: PnL +59.05%, Sharpe +0.48, Calmar 7.59, Hit 49.6% (1,561 trades)
- **Anti = 임펄스 후 스토캐스틱 훅** — 한국 시장 단기 모멘텀 전환 강력 포착
- **주의**: 평균 Sharpe -2.27, 다른 기간 -11~-17% — 시장 의존성 큼. **변동성·국면 필터 추가 검증 필요**
- **Holy Grail 부진** — Raschke 본인 추천이었지만 1분봉 부적합
- **자세히**: [raschke_street_smarts/](raschke_street_smarts/) (Phase 1 분봉 5개), Phase 2 일봉 5개 후속

### minervini_vcp (Mark Minervini — 초수익 성장주 투자)
- **베스트 규칙**: `volume_dryup B` (sl 8% / tp 12% / mh 20일)
- **성과**: 153거래 +20.27% PnL, 62.0% hit, Sharpe 1.41, Calmar 2.38
- **결론**: 일봉 단독 룰 중 가장 인상적인 Sharpe (1.41) + 충분한 표본 (153거래)
- **한계**: BULL 편향 (71.6%), BEAR 22일 표본 부족
- **자세히**: [minervini_vcp/report.md](minervini_vcp/report.md)

### weinstein_stages (Stan Weinstein — Secrets for Profiting in Bull and Bear Markets)
- **베스트 규칙**: `ma30w_bounce B` (Stage 2 중 30W MA bounce, 주봉 기반)
- **성과**: 43거래 +4.18% PnL, 60.5% per-trade 승률, Sharpe 0.30, Calmar 1.92
  - Per-trade 통계: 평균 +5.08%, 중앙값 +9.09%
- **특성**: 주봉 추세 추종 (Minervini 일봉 단기 vs Weinstein 주봉 중기)
- **한계**: 주봉 32주 warmup 제약, Variant A 표본 0, BULL 편향 (73.5%), 약세장 미검증 (BEAR 19일)
- **결론**: 주봉 기반 단순 패턴의 양호한 per-trade 승률이지만, 표본 43건 + BULL 편향으로 인한 신뢰도 제약
- **자세히**: [weinstein_stages/report.md](weinstein_stages/report.md)

### elder_triple_screen (Alexander Elder — Trading for a Living)
- **베스트 규칙**: `triple_screen_ema_pullback` (Variant A: sl 8% / tp 30% / EMA13 trail + ema65 반전 / mh 100)
- **성과**: 134거래 **+23.76% PnL**, 56.4% hit, **Sharpe 1.22**, Calmar 2.64 — 7권 통틀어 일봉 최고 PnL
- **셋업**: EMA65(주봉 proxy) 상승 + 일봉 EMA13 터치 후 회복 → 전일 고가 돌파 진입
- **특성**: Screen 1 일봉 65일 EMA proxy(주봉 26주 대체), 지수 불필요(종목 자기완결), 롱 전용
- **역설적 발견**: 가장 단순한 셋업이 정통 다지표 Triple Screen(Force Index PnL +6%, Elder-Ray +8.7%, Sharpe 0.2~0.5)을 크게 압도
- **한계**: BULL 편향(평균 ~142봉 단일 상승), 표본 희소, 적응판(일봉 proxy), Screen 3 일봉 근사
- **자세히**: [elder_triple_screen/report.md](elder_triple_screen/report.md)

### lynch_one_up (Peter Lynch — 월가의 영웅 / One Up on Wall Street)
- **베스트 규칙**: `value_balance_sheet` (저PBR<1.0 + 저PER<12 + 저부채<50% — 자산주 발상의 가치 스크린)
- **성과 (per-trade)**: Variant B 114거래 승률 52.6% 평균 +2.84%/거래 (Variant A 34거래 평균 +11.51%)
- **특성**: 펀더멘털 GARP, point-in-time 재무 조인(105일 lag), universe=fundamentals:131 (top_volume:50 아님)
- **3회 연속 패턴**: 단순 가치 스크린이 복잡 GARP/고성장(fast_grower 3~6T, garp_combo) 압도 — Minervini·Elder와 동일
- **한계**: 연간 데이터·극소 N(per 79·≥120봉 46)·psr/dividend_yield 100% NULL·짧은 이력 → **inconclusive**, CANDIDATE 부적격
- **비교성 주의**: universe 단절(이전 7권 top_volume:50), 집계 PnL은 0거래 종목 희석 → per-trade로만 해석
- **자세히**: [lynch_one_up/report.md](lynch_one_up/report.md)

### greenblatt_magic_formula (Joel Greenblatt — Magic Formula)
- **베스트 규칙**: `magic_formula_top` (EBIT/EV + ROC 순위 합산 상위 20, Variant B)
- **성과 (per-trade)**: 197거래 승률 61.4% 평균 +4.88%/거래 — **펀더멘털 책 최고 표본·성과**
- **특성**: 횡단면 순위(Minervini RS식 주입) + PIT 재무조인(105일 lag). universe=magic:79(market_cap 6개월 창)
- **핵심 발견**: 순위(상대) 룰 작동 vs 절대 임계값 룰 전멸(ROC>25% 한국 대형주 도달불가 max 24.7%) → "Magic Formula 본질 = 상대 순위"
- **단위 버그**: market_cap(원) vs 재무(억원) 1e8배 불일치 발견·수정
- **한계**: 6개월 단일국면, EV 상향편향(현금無), 영업권 ROC 하향, 금융/유틸 제외불가, BULL. CANDIDATE 보류
- **자세히**: [greenblatt_magic_formula/report.md](greenblatt_magic_formula/report.md)

### osullivan_what_works (James O'Shaughnessy — What Works on Wall Street)
- **베스트 규칙**: `low_psr` (저PSR 단일 팩터, PSR=market_cap/1e8/revenue 재구성)
- **성과 (per-trade)**: Variant B 200거래 승률 54.5% 평균 +4.63%/거래 (집계 +6.67%, A +8.26%)
- **특성**: 다팩터 횡단면 순위(VC1식 4팩터 복합 + Trending Value + 단일 PSR). Greenblatt 인프라 확장. universe=factor:79(6개월 창)
- **핵심 발견**: 단일 저PSR이 4팩터 복합·Trending Value 압도 → O'Shaughnessy "PSR=가치 팩터의 왕" 한국 확인
- **한계**: 6개월 단일국면, 진짜 VC2/VC3 불가(주주수익률·P/CF·EBITDA 부재), 6개월 모멘텀 불가(3개월 대체), BULL. CANDIDATE 보류
- **자세히**: [osullivan_what_works/report.md](osullivan_what_works/report.md)

## 메모 — 시스템 구조

데이터 소스:
- 분봉: `minute_candles` 테이블 (1,347 종목 · 318일 · 5,116만행)
- 일봉: `daily_prices` 테이블
- 펀더멘털: `financial_statements` 테이블

백테스트 인프라:
- BookStrategy 베이스: `strategies/books/_base_book_strategy.py`
- BookBacktester: `backtest/book_backtester.py`
- CLI: `scripts/run_books_research.py --book {ID} --period {YYYY-MM} --all-modes`

평가지표:
- 1급: PnL, Sharpe
- 2급: Calmar, MaxDD, Sortino, Hit Rate, n_trades, avg_hold_bars

품질 게이트:
- ✅ No-lookahead (t+1 데이터 접근 금지)
- ✅ 거래비용 매수+매도+세금 = 왕복 ~0.21%
- ✅ 슬리피지 0.10% 단방향
- ✅ adj_factor 반영 (corp_events 백필 완료)

## 책 의도 복원 결과 (top_volume:50 + 청산 완화)

"책이 사기인가?"라는 질문에 답하기 위한 사후 실험. 책의 두 가지 핵심 가정 — 촉매·고RVOL 종목 집중 선별, R-multiple 기반 청산 — 을 부분 복원(거래대금 상위 50종목 + sl3%/tp5%/mh120)해 베이스라인과 비교했다. Float·RVOL·촉매 데이터를 직접 쓴 것이 아니라 거래대금 순위로 근사한 결과임에 유의한다.

### 규칙별 평균 PnL 비교 (3기간 평균)

| Rule | 베이스 평균 | 복원 평균 | Δ |
|---|---|---|---|
| abcd | -19.36% | -4.23% | +15.13 %p |
| orb | -19.31% | -4.64% | +14.67 %p |
| red_to_green | -19.22% | -4.90% | +14.32 %p |
| ma_trend | -19.71% | -10.43% | +9.28 %p |
| support_resistance | -16.06% | -6.33% | +9.73 %p |
| vwap_reversal | -4.37% | -1.93% | +2.44 %p |
| bull_flag | -0.04% | +0.06% | +0.10 %p |
| top_reversal | 0% | 0% | 0 |
| all_AND | 0% | 0% | 0 |

### 복원 풀런 27행 (PnL 내림차순)

> ✅ = 양의 PnL

| Rank | Rule | Mode | Period | n_stocks | n_trades | PnL % | Sharpe | Calmar | Hit Rate | MaxDD % |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | abcd | single | 2025-10 | 50 | 2,612 | **+9.49** ✅ | -0.266 | 0.378 | 0.465 | 18.60 |
| 2 | orb | single | 2025-10 | 50 | 2,733 | **+7.14** ✅ | -1.016 | 0.173 | 0.415 | 19.15 |
| 3 | red_to_green | single | 2025-10 | 50 | 2,709 | **+6.56** ✅ | -1.359 | 0.128 | 0.419 | 19.65 |
| 4 | bull_flag | single | 2026-05 | 50 | 5 | +0.22 ✅ | 0.394 | 0.604 | 0.080 | 0.18 |
| 5 | bull_flag | single | 2025-10 | 50 | 7 | +0.09 ✅ | 0.046 | 0.034 | 0.050 | 0.20 |
| 6 | all_AND | all_AND | 2025-10 | 50 | 0 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |
| 7 | top_reversal | single | 2025-10 | 50 | 0 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |
| 8 | all_AND | all_AND | 2026-04 | 50 | 0 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |
| 9 | top_reversal | single | 2026-05 | 50 | 0 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |
| 10 | top_reversal | single | 2026-04 | 50 | 0 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |
| 11 | all_AND | all_AND | 2026-05 | 50 | 0 | 0.00 | 0.000 | 0.000 | 0.000 | 0.00 |
| 12 | bull_flag | single | 2026-04 | 50 | 8 | -0.14 | -0.271 | -0.016 | 0.020 | 0.57 |
| 13 | vwap_reversal | single | 2025-10 | 50 | 444 | -1.31 | -0.579 | 0.426 | 0.429 | 7.61 |
| 14 | vwap_reversal | single | 2026-05 | 50 | 407 | -1.56 | -0.805 | 0.326 | 0.423 | 9.78 |
| 15 | support_resistance | single | 2025-10 | 50 | 2,670 | -1.77 | -0.692 | 0.258 | 0.478 | 18.47 |
| 16 | vwap_reversal | single | 2026-04 | 50 | 397 | -2.92 | -1.694 | -0.032 | 0.407 | 10.54 |
| 17 | support_resistance | single | 2026-04 | 50 | 2,465 | -5.21 | -1.112 | -0.067 | 0.432 | 18.79 |
| 18 | abcd | single | 2026-04 | 50 | 2,795 | -6.63 | -1.067 | -0.092 | 0.418 | 20.86 |
| 19 | orb | single | 2026-04 | 50 | 3,274 | -7.25 | -1.858 | -0.106 | 0.426 | 24.60 |
| 20 | red_to_green | single | 2026-04 | 50 | 3,293 | -7.26 | -1.813 | -0.123 | 0.426 | 24.64 |
| 21 | ma_trend | single | 2026-04 | 50 | 2,811 | -9.25 | -2.469 | -0.168 | 0.409 | 23.50 |
| 22 | ma_trend | single | 2025-10 | 50 | 2,857 | -10.01 | -2.112 | -0.263 | 0.408 | 23.24 |
| 23 | support_resistance | single | 2026-05 | 50 | 2,250 | -12.02 | -2.894 | -0.358 | 0.419 | 26.62 |
| 24 | ma_trend | single | 2026-05 | 50 | 1,676 | -12.02 | -3.175 | -0.493 | 0.367 | 22.60 |
| 25 | orb | single | 2026-05 | 50 | 2,139 | -13.82 | -3.598 | -0.546 | 0.340 | 26.39 |
| 26 | red_to_green | single | 2026-05 | 50 | 2,172 | -14.00 | -3.755 | -0.552 | 0.335 | 26.61 |
| 27 | abcd | single | 2026-05 | 50 | 2,474 | -15.53 | -3.557 | -0.435 | 0.387 | 29.38 |

### 결론

책이 사기는 아님. 책의 가정 복원 시 abcd / orb / red_to_green이 2025-10 한국 시장에서 양의 PnL 가능. 모든 기간 일관 작동은 미확정 — 2026-04 / 2026-05에서는 개선되지만 손실이 지속된다. Sharpe는 양의 PnL 기간에도 음수이며 최대 낙폭 18~20%로 리스크 조정 후 평가는 미흡하다.

---

## Weinstein Stage Analysis 결과 — full-period (Book 6)

> 주봉 기반 Stage Analysis: 30W MA + Mansfield RS + 거래량 돌파  
> 데이터: 224 거래일 / ~32주 (warmup 제약으로 Variant A 표본 0)  
> 국면: BULL 150일(73.5%) / SIDEWAYS 35일(17.2%) / BEAR 19일(9.3%)

### Variant B 룰별 결과 (full-period)

| 룰 | 거래수 | PnL % | Per-Trade 승률 | Avg Trade PnL | Sharpe | Calmar |
|---|--------|---------|----------|---------|--------|--------|
| **ma30w_bounce** ⭐ | **43** | **+4.18%** | **60.5%** | **+5.08%** | **0.30** | **1.92** |
| stage2_continuation_pullback | 17 | +1.29% | 41.2% | +3.99% | -0.11 | 0.62 |
| stage2_initial_breakout | 7 | +0.38% | 57.1% | +2.91% | 0.03 | 0.16 |

### 핵심 발견
- **최고 룰**: ma30w_bounce (43거래, +4.18% PnL, Sharpe 0.30)
  - Stage 2 진행 중 30W MA 3% 이내 터치 후 양봉 회복
  - 60.5% per-trade 승률, +5.08% 평균 수익, 중앙값 +9.09%
- **Variant A**: 표본 0 (warmup 56주 > 데이터 32주) — 인프라 검증용
- **Variant Light**: 표본 1 (인프라 동작 검증용, 책 평가 제외)

### 국면 분석
- BULL 편향 심각 (73.5%) → BEAR 19일 표본 극소 (거래 2건) → 약세장 미검증
- **한계**: Weinstein 추세 추종 특성상 상승장에만 강함 확인

### 책 6권 통합 평가 (leaderboard 등록된 책)
- **PnL (일봉 기준)**: Minervini volume_dryup B (+20.27%) > Weinstein ma30w_bounce B (+4.18%)
- **Sharpe 비율**: Minervini (+1.41) > Weinstein (+0.30)
- **표본 신뢰도**: Minervini (153거래) > Weinstein (43거래)

### 결론
ma30w_bounce는 주봉 기반 단순 패턴이 한국 시장에서 양호한 per-trade 승률(60.5%) 시사. 다만 PnL은 Minervini 대비 4.8배 낮고, BULL 편향(73.5%) + 표본 부족(43거래) + BEAR 미검증으로 인한 신뢰도 제약 있음.

상세: [weinstein_stages/report.md](weinstein_stages/report.md)

---

## Elder Triple Screen 결과 — full-period (Book 7)

> 3중 시간프레임 필터: Screen 1(주봉 추세)=일봉 65일 EMA proxy, Screen 2(일봉 오실레이터)=4변형, Screen 3(진입)=전일 고가+1틱 매수스톱.
> **지수 불필요**(종목 자기완결) — Weinstein Mansfield RS 의존성 제거. universe top_volume:50(49종목). 롱 전용.

### Variant A 룰별 결과 (sl 8% / tp 30% / EMA13 trail + ema65 반전 / mh 100)

| 룰 | 거래 | PnL % | Sharpe | Calmar | MaxDD % | Hit | AvgHold |
|---|------|-------|--------|--------|---------|-----|---------|
| **triple_screen_ema_pullback** ⭐ | 134 | **+23.76** | **1.22** | 2.64 | 13.76 | 56.4% | 8.6 |
| triple_screen_stochastic | 43 | +9.32 | 0.91 | 6.95 | 5.21 | 41.7% | 5.0 |
| triple_screen_elder_ray | 73 | +8.66 | 0.25 | 1.01 | 10.00 | 34.5% | 6.5 |
| triple_screen_force_index | 48 | +6.05 | 0.54 | 1.26 | 7.86 | 35.3% | 5.7 |
| all_AND | 0 | — | — | — | — | — | — |

### Variant B (sl 8% / tp 12% / trail 없음 / mh 20) — ema_pullback 149T +17.72% Sharpe 1.20

### 핵심 발견
- **최고 룰**: ema_pullback A (134T, +23.76%, Sharpe 1.22, hit 56.4%) — 7권 통틀어 일봉 최고 PnL.
- **단순 셋업이 정통 다지표를 압도**: EMA65 상승 + EMA13 터치 반등이 Force Index·Elder-Ray confluence(PnL 3~9%, Sharpe 0.2~0.5)를 크게 앞섬. Minervini 단순 volume_dryup > trend_template와 동일 패턴.
- stochastic A는 Calmar 6.95(최고)·MaxDD 5%대로 가장 방어적이나 표본 적음(43T).
- all_AND = 0거래 (4셋업 상호 배타).

### 책 7권 통합 평가 (일봉 베스트)
- **PnL**: Elder ema_pullback A (+23.76%) > Minervini volume_dryup B (+20.27%) > Weinstein ma30w_bounce B (+4.18%)
- **Sharpe**: Minervini (+1.41) > Elder (+1.22) > Weinstein (+0.30)
- Elder는 지수 불필요·종목 자기완결로 구현 부담 최소이면서 PnL 최상위.

### 결론
Triple Screen의 핵심 사상(긴 추세 방향 짧은 눌림 매수)을 가장 단순히 구현한 ema_pullback이 일봉 최고 PnL 달성. 정통 다지표 셋업 부진 → "복잡할수록 좋지 않다"는 역설. BULL 편향(평균 ~142봉 단일 상승 구간)·표본 희소·적응판(일봉 proxy) 한계로 walk-forward·하락장 검증 후 CANDIDATE_ALPHAS 등록 검토.

상세: [elder_triple_screen/report.md](elder_triple_screen/report.md)

---

## Lynch One Up on Wall Street 결과 — full-period (Book 8)

> 펀더멘털 GARP: 6카테고리·PEG를 가용 재무 컬럼으로 매핑한 4룰. point-in-time 재무 조인(report_date+105일 lag).
> ⚠️ **universe = fundamentals:131** (top_volume:50 ∩ 재무 = 10종목이라 사용 불가, 사장님 승인). **이전 7권과 비교성 단절.**
> ⚠️ psr·dividend_yield 100% NULL → 자산주·PEGY 룰 제외(대체 구현).

### Per-Trade 결과 (집계 PnL은 0거래 종목 희석으로 무의미 → 거래 단위로만 해석)

| Variant | 룰 | 거래 | per-trade 승률 | 평균/거래 | 중앙값 |
|---|---|------|----------|---------|--------|
| B | **value_balance_sheet** ⭐ | 114 | 52.6% | +2.84% | +1.28% |
| B | garp_combo | 32 | 56.2% | +2.06% | +3.79% |
| A | value_balance_sheet | 34 | 50.0% | +11.51% | +0.84% |
| B | fast_grower | 6 | 83.3% | +5.84% | — |
| A/B | fast_grower/stalwart | 1~6 | (N 극소 무의미) | — | — |

### 핵심 발견
- **표본 견고한 유일 룰 = value_balance_sheet** (저PBR<1.0 + 저PER<12 + 저부채<50%). B 114거래 승률 52.6% 평균 +2.84%/거래.
- **단순 가치 스크린이 복잡 GARP/고성장(fast_grower/garp_combo) 압도** — Minervini·Elder에 이은 3회 연속 "단순 우위" 패턴.
- fast_grower/stalwart 1~6거래 통계 무의미. all_AND 0거래.

### 책 8권 통합 평가
- Lynch는 펀더멘털 단독 책 중 표본 확보(114거래) 성공, 단 per-trade +2.84%로 기술적 베스트(Elder +23.76%·Minervini +20.27%) 대비 약함.
- **데이터 제약(연간·극소 universe·NULL·짧은 이력)으로 Lynch 방법론 자체는 inconclusive.**

### 결론
단순 가치 스크린의 약한 양(+) 엣지 확인. 그러나 연간 데이터·극소 N·NULL 다수로 평가 미완. 분기 재무 + 배당/PSR 백필 + 종목 확대 후 재검증 필요. **CANDIDATE_ALPHAS 등록 부적격**(표본·데이터 신뢰도 미달).

상세: [lynch_one_up/report.md](lynch_one_up/report.md)

---

## Greenblatt Magic Formula 결과 — full-period (Book 9)

> EBIT/EV(이익수익률) + ROC(자본수익률) 횡단면 순위 합산. PIT 재무조인(105일 lag) + Minervini RS식 순위 주입.
> ⚠️ **universe = magic:79** (market_cap 보유 종목, **6개월 창** 2025-07-31~2026-02-02). 이전 8권과 기간·비교성 단절.

### Per-Trade 결과
| Variant | 룰 | 거래 | per-trade 승률 | 평균/거래 | 청산 |
|---|---|------|----------|---------|------|
| **B** | **magic_formula_top** ⭐ | 197 | 61.4% | +4.88% | TP79·SL47·mh43·forced28 |
| A | magic_formula_top | 38 | 84.2% | +32.29% | forced 31/38 (BULL buy&hold 과대) |
| A/B | threshold / high_roc_value / all_AND | 0 | (ROC max 0.247<0.25 — 절대임계값 사망) | — | — |

### 핵심 발견
- **순위(상대) 룰 작동, 절대 임계값 룰 사망**: magic_formula_top(순위) 197거래 양호. threshold(ROC>25%)·high_roc_value(ROC>40%)는 0거래 — Greenblatt 미국 기준이 한국 대형주(ROC max 24.7%)에 과도. **"Magic Formula 본질은 절대 기준이 아닌 상대 순위"** 입증.
- **펀더멘털 2책 비교**: Greenblatt magic_formula_top B(+4.88% 승률 61.4% 197T) > Lynch value_balance_sheet B(+2.84% 52.6% 114T). 횡단면 순위 우월.
- **단위 버그 수정**: market_cap(원) vs 재무(억원) 1e8배 불일치 발견·수정. 수정 전 EY≈0으로 순위가 ROC 단독이었음.

### 결론
Magic Formula 횡단면 순위는 한국 데이터에서 작동(펀더멘털 책 최고 표본·per-trade). 단 6개월 단일 국면(market_cap 창)·EV 상향편향·연간 데이터로 신뢰도 제약. **CANDIDATE 보류**(기간 부족). market_cap 전기간 백필 + 현금/섹터 컬럼 확보 후 재검증.

상세: [greenblatt_magic_formula/report.md](greenblatt_magic_formula/report.md)

---

## O'Shaughnessy What Works on Wall Street 결과 — full-period (Book 10, 최종)

> 다팩터 횡단면 순위. PSR 재구성(market_cap/1e8/revenue) + VC1식 4팩터 복합 + Trending Value. Greenblatt 인프라 확장.
> ⚠️ universe=factor:79 (market_cap 6개월 창). 진짜 VC2/VC3 불가(주주수익률·P/CF·EBITDA 부재).

### Per-Trade 결과 (Variant B)
| 룰 | 거래 | per-trade 승률 | 평균/거래 | 집계 PnL |
|---|------|----------|---------|--------|
| **low_psr** ⭐ | 200 | 54.5% | +4.63% | +6.67% |
| value_composite | 182 | 55.5% | +3.85% | +4.72% |
| trending_value | 138 | 53.6% | +3.89% | +3.54% |
| all_AND | 74 | — | — | +1.63% |

### 핵심 발견
- **단일 저PSR이 4팩터 복합·Trending Value 압도** → O'Shaughnessy "PSR=가치 팩터의 왕" 한국 데이터 확인.
- Trending Value(플래그십)는 부진 — 6개월 모멘텀 불가(16종목)로 3개월 사용 + 단일 BULL 국면이라 모멘텀 틸트 무력.
- **진짜 VC2/VC3 불가**(주주수익률·P/CF·EBITDA 부재) — 4판 헤드라인 손실.

### 결론
저PSR이 한국에서도 최강 단일 가치 팩터 확인. 6개월 단일 국면·VC2 불가 한계로 **CANDIDATE 보류**(market_cap 전기간 백필 후 재검증).

상세: [osullivan_what_works/report.md](osullivan_what_works/report.md)

---

## 문병로 메트릭 스튜디오 결과 — 다년 다국면 (Book 11, 한국 저자 1호 · 2026-05-30)

> 5팩터(PBR·PER·PSR·POR·**PCR**) 횡단면 순위 + 소형주 틸트. O'Shaughnessy 인프라 확장.
> **펀더멘털 책 최초 다년(2021~2026, 1,241일) 검증** — market_cap 5년 백필 + PCR(영업현금흐름) Phase 0 DART 백필 덕. n_eligible median 52.

### 룰별 베스트 (variant K: sl17.5%/mh250)
| 룰 | 거래 | 집계 PnL | Sharpe | per-trade 승률 |
|---|---|---|---|---|
| **value_composite_kr** ⭐ | 218 | **+13.68%** | **0.09** | 40.4% |
| small_value | 213 | +6.99% | 0.06 | 39.0% |
| low_pbr (시그니처) | 166 | +3.29% | 0.04 | 36.7% |

### 핵심 발견
- **5팩터 복합이 베스트**(+13.68%), 저PBR 단독·소형주를 압도.
- **문병로 시그니처 "한국=저PBR 민감"은 다년 검증 시 약함(부분 반박)** — low_pbr 단독이 3룰 중 최하(+3.29%, 승률 36.7%). 가치는 복합으로만 의미.
- **Sharpe 0.01~0.09 붕괴** — Elder(0.68)·Minervini(0.64)에 크게 미달. per-trade 승률 40~47%(다년)로 6개월 펀더멘털 책(54~61%)보다 낮음 → 단일 BULL 거품 재확인.
- 장기보유(K/A) > 단기청산(B). 4월 게이트는 PnL 유지하며 회전율 절감.
- **CANDIDATE 부적격**(Sharpe 0.09) — 펀더멘털 4책째 동일 결론.

상세: [moonbyungro_metric/report.md](moonbyungro_metric/report.md) · Phase0: [moonbyungro_metric/phase0_ocf_backfill.md](moonbyungro_metric/phase0_ocf_backfill.md)

---

## 홍용찬 실전 퀀트투자 결과 — 다년 (Book 12, 한국 저자 2호 · 2026-05-30)

> 4선 저밸류(PER+PBR+PCR+PSR) + 소형주 하위 20% + 성장/마진/부채 게이트. 문병로 인프라 85% 재활용, universe 131 동일(직접 A/B). 배당 제외(사장님 방침).

### 룰별 (variant K: sl17.5%/mh250)
| 룰 | 거래 | 집계 PnL | Sharpe | 승률 |
|---|---|---|---|---|
| **value4_low**(4선) ⭐ | 213 | **+12.87%** | **0.11** | 42.7% |
| small_value4(소형주20%) | 129 | +12.53% | 0.06 | 41.1% |
| hong_combo(게이트) | 88 | +8.93% | 0.05 | 39.8% |

### 핵심 발견 (문병로와 직접 A/B)
- **4선 ≈ 5팩터**: 홍 value4_low(+12.87%/0.11) ≈ 문 value_composite_kr(+13.68%/0.09). 밸류 4개나 5개나 동급.
- **성장/마진 게이트가 알파 못 더함**: hong_combo(+8.93%)<순수 4선(+12.87%). 홍용찬 핵심 주장(게이트 결합) **부분 반박** → "단순>복잡" 재확인.
- **소형주 20% > 40%**: 홍 small_value4(+12.53%) > 문 small_value 40%(+6.99%). 강한 소형주 틸트 유효.
- **Sharpe 0.11 붕괴** — 펀더멘털 5책째 동일 결론. CANDIDATE 부적격.

상세: [hongyongchan/report.md](hongyongchan/report.md)

---

# 🏁 트레이딩 책 10권 시리즈 — 통합 요약 (2026-05-29 완료)

10권 전부 조사→코드화→백테스트→리포트 완주. 한국 시장(분봉/일봉/주봉/재무) 백테스트.

## 책별 베스트 한눈에

| # | 책 | 데이터 | 베스트 룰 | 성과 | 표본 |
|---|---|---|---|---|---|
| 1 | 아지즈 | 분봉 | bull_flag | -0.04% | 32T |
| 2 | Bellafiore | 분봉 | fade_vwap | +1.74% Sharpe +0.37 | 964T |
| 3 | Raschke | 분봉 | anti | +10.24% (2025-10 +59%) | 1,860T |
| 4 | O'Neil | 일봉+재무 | CANSLIM+패턴 | +7.04% 승률 71% | 7T |
| 5 | **Minervini** | 일봉 | volume_dryup B | **+20.27% Sharpe 1.41** | 153T |
| 6 | Weinstein | 주봉 | ma30w_bounce B | +4.18% | 43T |
| 7 | **Elder** | 일봉(주봉proxy) | ema_pullback A | **+23.76% Sharpe 1.22** | 134T |
| 8 | Lynch | 일봉+재무 | value_balance_sheet B | per-trade +2.84% | 114T |
| 9 | Greenblatt | 일봉+재무+순위 | magic_formula_top B | per-trade +4.88% 승률 61% | 197T |
| 10 | O'Shaughnessy | 일봉+다팩터순위 | low_psr B | per-trade +4.63% 승률 55% | 200T |

## 🔑 5대 교훈

1. **"단순/단일/상대가 복잡/다지표/절대를 이긴다" (5책 연속)**: Minervini(단순 volume_dryup>8조건 trend_template), Elder(단순 ema_pullback>다지표 Triple Screen), Lynch(단순 value>GARP), Greenblatt(상대 순위>절대 임계값), O'Shaughnessy(단일 PSR>복합 VC).
2. **일봉 추세/가치가 분봉 인트라데이보다 한국 시장에 적합**: 분봉 4책(아지즈/Bellafiore/Raschke 일부/) 대부분 부진·고변동. 미국식 인트라데이 모멘텀 셋업이 한국 분봉에서 약함.
3. **최고 성과 = Elder(+23.76%)·Minervini(+20.27%)** — 둘 다 일봉 추세 추종, Sharpe 1.2~1.4, 충분한 표본.
4. **펀더멘털 3책(Lynch/Greenblatt/O'Shaughnessy)은 데이터 제약으로 inconclusive**: 연간 데이터·market_cap 6개월 창·NULL 다수·생존편향. 그래도 저PSR·Magic 순위는 양(+) 엣지 시사.
5. **전 책 공통 BULL 편향**: 데이터 기간이 단일 상승 구간 → 하락장 방어 미검증. walk-forward·약세장 검증이 CANDIDATE 등록 전제.

## CANDIDATE_ALPHAS 등록 우선순위
1. ✅ **Elder ema_pullback (variant A) — 등록 확정** (2026-05-30): 다년(2021~2026)·국면(BULL/BEAR/SIDEWAYS) 검증 통과. BEAR per-trade **+3.01%** ≈ BULL +3.15%, 약세장 무너짐 전무. 조건: **variant A 고정** + (선택) SIDEWAYS 회피 게이트. ⚠️ 약점은 SIDEWAYS(−0.71%).
2. (관찰) **Elder stochastic A** (BEAR 특화 +3.68%/hit57%, 표본 70) · **Minervini volume_dryup B** (분산 보조, 표본 424 but per-trade 약함, variant B 고정 필수 — A는 −19.6% 과매매)
3. (보류) Greenblatt/O'Shaughnessy 순위 — market_cap 전기간 백필 후

## 데이터 백필 + 다년 재검증 (2026-05-29 완료)
- 펀더멘털 일봉을 `strategy_analysis.daily_candles`로 **2021~2026 백필**(+142,467행, market_cap=yearly_fundamentals 연도매칭). 6개월 창 → 5년 다국면.
- **재검증 결과 — Sharpe 붕괴**: Greenblatt magic_formula_top A Sharpe 0.41→**0.12**, O'Shaughnessy low_psr A 0.36→**0.11**. per-trade 승률 84%→**~48%(동전)**. **6개월 숫자는 단일 BULL 거품이었음이 입증.**
- low_psr·magic_formula_top은 다년에서도 각 책 1위 유지(저PSR "왕" 재확인)이나 risk-adjusted 엣지 미미 → **펀더멘털 3책 CANDIDATE 부적격 재확인.**
- 상세: [changelog 2026-05-29 backfill-revalidation](../../memory/changelog-2026-05-29-fundamental-backfill-revalidation.md)
- 추가 백필 후보: 일별 시총 정밀화(상장주수×close)·분기재무·배당(DART)

## 🎯 강건성 교훈 (백필 + 다년 재검증이 입증)
- **단일 BULL 구간 백테스트는 Sharpe를 부풀린다**: 다년·다국면 검증 없이는 어떤 알파도 신뢰 불가.
- **검증 완료 (2026-05-30)**: 기술적 베스트 2책도 5년 재검증 시 Sharpe 붕괴 — Elder ema_pullback 1.22→0.68(**−44%**), Minervini volume_dryup 1.41→0.64(**−55%**). 단 펀더멘털(−75%)보다 견고하고 5년에도 양 PnL·Sharpe 0.6대 유지.
- **그러나 국면 분해는 다른 결론**: 추세추종의 약점은 하락장이 아니라 **횡보장(SIDEWAYS)**. Elder ema_pullback A는 BEAR(+3.01%)에서 BULL(+3.15%)과 동급 → "약세장에 약하다"는 통념이 데이터로 반박됨. 0.68은 상승장 운빨이 아니라 추세장 적응력의 산물.

## 인프라 (재사용 자산)
- BookStrategy/Rule/RuleResult 베이스 + 횡단면 순위 주입(Minervini RS→Greenblatt magic_rank→O'Shaughnessy vc/tv/psr) + PIT 재무조인(Lynch, 105일 lag) + 주봉 resample(Weinstein)
- 책별 run 스크립트 10개, leaderboard.parquet 140행, 결과 parquet 다수
- 품질 게이트: no-lookahead, 거래비용 왕복 0.41%, adj_factor, 단위 정합(market_cap 1e8)

---

## Elder·Minervini 다년 + 국면 재검증 (2026-05-30)
> 펀더멘털 백필이 daily_prices를 2021~2026(1,653일)으로 채워둔 덕에 기술적 베스트 2책도 추가 데이터 없이 5년 재검증 가능. 로더에서 OHLC≤0 결손행(671행/18종목, 백필 잔존)을 close로 보정(원본 불변). 상세: [changelog 2026-05-30](../../memory/changelog-2026-05-30-elder-minervini-multiyear-revalidation.md)

### 224일 BULL vs 5년 보정후
| 책 / 베스트룰 | PnL | Sharpe | 거래 | Hit | MaxDD | 붕괴율 |
|---|---|---|---|---|---|---|
| Elder ema_pullback A | +23.76%→+37.90% | 1.22→**0.68** | 134→925 | 56→50% | 13.8→33.1% | −44% |
| Minervini volume_dryup B | +20.27%→+17.70% | 1.41→**0.64** | 153→1190 | 62→56% | —→38.8% | −55% |
| (참고) 펀더멘털 3책 | — | ~0.4→~0.1 | — | — | — | −75% |

### 국면별 분해 (KOSPI 20일 ±2%; BULL 39%/BEAR 29%/SIDEWAYS 31%, 2022 약세장 검출)
| 룰 | BULL | BEAR | SIDEWAYS |
|---|---|---|---|
| Elder ema_pullback A | +3.15% (447T) | **+3.01% (169T)** | **−0.71%** (309T) |
| Elder stochastic A | +4.91% | **+3.68% (hit57%)** | −0.21% |
| Minervini volume_dryup B | +1.50% | +1.38% (424T) | −1.03% |
*(per-trade 평균. headline Sharpe 0.68은 종목별 equity 평균 정의 — 척도 다름, 정식 국면 Sharpe는 미산출)*

### 결론
- **추세추종 > 펀더멘털**(붕괴율 −44/−55% < −75%), 5년에도 양 PnL·Sharpe 0.6대 유지.
- **약세장 검증 통과**: 6개 룰 전부 BEAR per-trade 양수. Elder A는 BEAR≈BULL. 약점은 SIDEWAYS(휩쏘).
- **Elder ema_pullback A = CANDIDATE 등록 확정**(variant A 고정 + 선택 SIDEWAYS 게이트). Minervini는 variant B 고정 필수(A 과매매 −19.6%).

### 통합 포트폴리오 + KOSPI 알파 (2026-05-30 추가, `scripts/portfolio_sim_elder.py`)
> book_backtester는 종목당 독립계좌(자본효율 미반영)라 "+37.9%"는 룰 엣지 측정치일 뿐. 단일계좌 통합 시뮬로 실제 계좌수익률 측정.

| | Elder A K=20 | KOSPI b&h |
|---|---|---|
| CAGR | 13.06% | **20.39%** |
| Sharpe | **1.08** | 0.95 |
| MaxDD | **22.9%** | 34.8% |
| Beta | **0.15** | 1.0 |

- 통합운용은 **분산도 K에 극도로 민감**(K=5 −7.5% → K=20 +93.3%, MaxDD 68%→23%).
- **데이터 검증**: KOSPI 8476·삼성 305K는 오염 아님 — 2025.6~2026 **실제 대폭등장**(사장님 확인, raw도 동일). 2021~2025.5는 현실 일치.
- **재해석**: KOSPI +171%(연20%) 폭등장에서 손익절+현금보유 전략이 인덱스에 지는 건 당연. Elder = **beta 0.15 시장중립 방어형**(Sharpe·MaxDD·하락장 우위). 인덱스 대체재 ✗, **분산/방어 자산 ✓**.

---

*이 문서는 [leaderboard.parquet](leaderboard.parquet) 데이터를 기반으로 작성됨. 향후 자동 재생성 도구는 Plan 2 이후 검토.*
