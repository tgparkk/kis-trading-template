# Changelog: P2 Stage C — 매도 룰 그리드 (2026-05-24)

## 작업 개요
Phase 2B 합격 271 시그널 중 (regime, bucket)별 Top 5 = 48개 시그널에
손절/익절/시간만기 3축 75 매도 룰 sparse 그리드 적용.

## 산출 스크립트
`RoboTrader_template/scripts/10pct_strategy/p2c_exit_grid.py`
- p2b_signal_multiverse.py에서 load_data, compute_signal_features, build_signal_catalog 등 전부 import 재사용
- prices_pivot (stock_code → date-indexed OHLC df) 빌드 후 simulate_exit()로 T+1 시가 매수 시뮬
- IS_CUTOFF 2025-01-01 기준 IS/OOS 분리
- 체크포인트 저장 (10 시그널마다)

## 처리 결과
- 전체 평가: **3,000 셀** (48 시그널 × 75 매도 룰 — 일부 pool 스킵으로 ≈3,000)
- 합격 셀: **145개** (4.8%)
- 소요: 10.7분

## 합격 기준
mean_pnl > 0 AND sharpe > 0.8 AND mdd > -0.2 AND IS_mean > 0 AND OOS_mean > 0 AND n ≥ 30

## (Regime, Bucket) 커버리지: 4/18
| Regime × Bucket | 합격 셀 |
|---|---|
| BEAR_HIGH_VOL × swing | 67 |
| BULL_LOW_VOL × swing | 31 |
| BULL_HIGH_VOL × swing | 28 |
| SIDEWAYS_LOW_VOL × swing | 19 |

- mid/position 버킷 전체 합격 없음 (20d/60d 청산 horizon의 엄격한 sharpe 조건 미달)

## 최우수 트리플 Top 5
| 순위 | regime | family | SL | TP | TM | mean_pnl | sharpe | n |
|---|---|---|---|---|---|---|---|---|
| 1 | BULL_LOW_VOL | vol_spike_bullish (vol×3, body_q≥4) | -5% | 10% | 60d | 4.19% | 9.11 | 62 |
| 2 | BULL_LOW_VOL | vol_spike_bullish (vol×3, body_q≥4) | -5% | 10% | 20d | 4.11% | 8.97 | 62 |
| 3 | BEAR_HIGH_VOL | ma_pullback_reversal (MA5, -5%) | -3% | 15% | 20d | 3.75% | 7.59 | 144 |
| 4 | BEAR_HIGH_VOL | bb_reversion (BB20, 2.5σ, RSI≤35) | -3% | 15% | 20d | 3.35% | 6.78 | 78 |
| 5 | BULL_LOW_VOL | vol_spike_bullish (vol×3, body_q≥4) | -5% | 15% | 5d | 2.99% | 6.59 | 62 |

## 구조적 패턴
- 스윙 시그널(3일 horizon)이 더 긴 TM(20d/60d)과 결합해도 합격 → 조기 TP 도달이 주요 청산 경로
- 손절 -3~-5%, 익절 +10~+15%, TM 20일 조합이 sharpe 최상
- BEAR_HIGH_VOL에서 ma_pullback_reversal + bb_reversion이 OOS 특히 강함 (OOS > IS)
- BULL_HIGH_VOL × position, 모든 mid/position 버킷은 n 또는 sharpe 미달로 합격 없음

## P3 진입 판단: NG
- 합격 셀 145개 (기준 ≥30 충족)
- 조합 커버 4/18 (기준 ≥6/18 미달)
- 원인: mid/position 버킷 합격 없음, BEAR_LOW_VOL/SIDEWAYS_HIGH_VOL 합격 없음

## 권장 조치 (P3 전 완화 옵션)
1. sharpe 합격선 0.8 → 0.5 완화 (mid/position 진입 가능성)
2. TM 그리드에 10d, 30d 추가 (5×5×5 = 125셀)
3. n 최소 기준 30 → 20 완화 (position 버킷 소표본 문제)
4. OOS 기준 완화: OOS_mean > -0.005 (소폭 음수 허용)

## 산출 파일
- `reports/10pct_strategy/phase2c_exit_grid_all.csv` (3,000 셀)
- `reports/10pct_strategy/phase2c_exit_passed.csv` (145 합격)
- `reports/10pct_strategy/phase2c_top_triples_by_regime_bucket.md`
- `reports/10pct_strategy/phase2c_summary.md`
