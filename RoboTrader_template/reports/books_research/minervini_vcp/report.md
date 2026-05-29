# Minervini VCP — 백테스트 결과 (Book 5/10)

> 데이터: daily_prices (adj_factor 적용 수정주가)
> 기간: 2025-07-01 ~ 2026-05-29 = 224 거래일 (실측)
> universe: top_volume:50 (일평균 거래대금 상위 50)
> RS: universe 내부 12주 수익률 백분위
> 청산 Variant: A(sl 8% / tp 20% / mh 35 / 50MA trail) + B(sl 8% / tp 12% / mh 20)
> 워밍업: simulate 60봉 (RS 12주) + rule별 lookback (trend_template 220봉)
> 설계: [../../../docs/superpowers/specs/2026-05-29-minervini-vcp-design.md](../../../docs/superpowers/specs/2026-05-29-minervini-vcp-design.md)

## 1. 풀런 결과

### Variant A (Minervini 본인 룰 — sl 8% / tp 20% / mh 35 / 50MA trail)

| Rank | Rule | n_stocks | n_trades | PnL % | Sharpe | Calmar | Hit Rate | Avg Hold |
|---|---|---|---|---|---|---|---|---|
| 1 | volume_dryup | 50 | 444 | **+18.17** | **1.12** | **2.30** | 54.2% | 4.7일 |
| 2 | vcp_breakout | 50 | 2 | +0.33 | 0.07 | 0.06 | 4.1% | 0.14일 |
| 3 | tight_closes | 50 | 2 | +0.26 | -0.02 | -0.01 | 2.0% | 0.16일 |
| 4 | trend_template | 50 | 0 | 0.00 | 0.00 | 0.00 | — | — |
| 5 | all_AND | 50 | 0 | 0.00 | 0.00 | 0.00 | — | — |

### Variant B (책간 획일 — sl 8% / tp 12% / mh 20)

| Rank | Rule | n_stocks | n_trades | PnL % | Sharpe | Calmar | Hit Rate | Avg Hold |
|---|---|---|---|---|---|---|---|---|
| 1 | volume_dryup ⭐ | 50 | 153 | **+20.27** | **1.41** | **2.38** | 62.0% | 9.0일 |
| 2 | vcp_breakout | 50 | 2 | +0.33 | 0.07 | 0.06 | 4.1% | 0.14일 |
| 3 | tight_closes | 50 | 2 | +0.26 | -0.02 | -0.01 | 2.0% | 0.16일 |
| 4 | trend_template | 50 | 0 | 0.00 | 0.00 | 0.00 | — | — |
| 5 | all_AND | 50 | 0 | 0.00 | 0.00 | 0.00 | — | — |

## 2. 국면별 분해

KOSPI 미존재로 universe 중앙값 20일 수익률 ±2% 임계 사용.

### Regime 분포 (204일, warmup 20일 제외)

| Regime | 일수 | 비율 |
|---|---|---|
| BULL  | 146 | 71.6% |
| SIDEWAYS | 36 | 17.6% |
| BEAR | 22 | 10.8% |

→ 단일 BULL 우세 구간. BEAR 22일은 통계 표본 부족.

### volume_dryup 매도일 국면별 PnL

실 매도일을 regime 표와 join 한 결과. 표본은 volume_dryup B trades 사용.

| Regime   |   Trades | Mean PnL   |
|:---------|---------:|:-----------|
| BEAR     |       39 | -2.29%     |
| BULL     |       92 | +9.95%     |
| SIDEWAYS |       22 | +8.77%     |

→ BULL/SIDEWAYS 구간에서 양의 기대값, BEAR에서만 손실. BEAR 39 trades는 통계적으로 참고 수준.

## 3. 5권 비교

| 책 | 데이터 | 베스트 | 평균 PnL | 평균 Sharpe | 표본 |
|---|---|---|---|---|---|
| 아지즈 | 분봉 | bull_flag | -0.04% | -0.11 | 32T |
| Bellafiore | 분봉 | fade_vwap | +1.74% | +0.37 | 964T |
| Raschke | 분봉 | anti | +10.24% | -2.27 | 1,860T |
| O'Neil | 일봉+재무+RS | CANSLIM+패턴 | +7.04% | — | 7T |
| **Minervini** | **일봉+RS자체** | **volume_dryup B** | **+20.27%** (B) / +18.17% (A) | **+1.41** (B) / +1.12 (A) | **153T** (B) / 444T (A) |

→ 5권 통틀어 일봉 단독 룰 중 가장 인상적인 Sharpe·Calmar.

## 4. CANDIDATE_ALPHAS 자격 검토

| 기준 | 임계값 | volume_dryup A | volume_dryup B | 통과 |
|---|---|---|---|---|
| 표본 | ≥ 30 트레이드 | 444 | 153 | ✅ 둘 다 |
| Sharpe | > 0 | 1.12 | 1.41 | ✅ 둘 다 |
| Calmar | ≥ 1.0 | 2.30 | 2.38 | ✅ 둘 다 |

자격 통과 — Variant B 권장 등록 (Sharpe·Calmar 우세, hit 62%, avg hold 9일).

**경고**: 단일 BULL 우세 구간(146/204=71.6%) 표본 편향 위험 + BEAR 22일 표본 부족 → 사장님 결재 사항: 즉시 등록 vs walk-forward 후 등록.

## 5. 한계와 후속 검증 항목

- 데이터 224일 단일 구간 (BULL 71.6% 편향) → walk-forward 미수행
- trend_template 220봉 guard로 데이터 224일 종목 영구 False — 실질 검증 ~4일 한정
- vcp_breakout / tight_closes: 표본 2건 — 통계적 무의미
- RS 백분위 = universe 50종목 내부 비교 → 시장 전체 RS 미반영
- 거래량 dry-up 메커니즘 분석 미완 (회귀 vs 지속 패턴)
- BEAR 구간 22일만 → 약세장 성과 미확정 → 데이터 추가 누적 후 재검증 권장
- KOSPI(KS11) daily_prices 미존재로 regime fallback (universe 중앙값) 사용 — 진정 시장 국면과 미세 차이 가능
