# Phase 2C 요약 — 매도 룰 그리드 결과

생성일: 2026-05-24
소요: 21.7분

## 처리 결과
- 전체 평가 셀: **6,000**
- 합격 셀: **279** (4.7%)
- 합격 기준: mean_pnl > 0 AND sharpe > 0.5 AND mdd > -0.2 AND IS > 0 AND OOS > 0 AND n ≥ 30

## 매도 룰 그리드
- 손절(SL): [-0.015, -0.02, -0.03, -0.04, -0.05]
- 익절(TP): [0.03, 0.05, 0.07, 0.1, 0.15]
- 시간만기(TM): [5, 10, 20, 30, 45, 60]일

## (Regime, Bucket) 커버리지
- 합격 조합: **4** / 18

| Regime × Bucket | 합격 셀 |
|-----------------|---------|
| BEAR_HIGH_VOL × swing | 135 |
| BULL_HIGH_VOL × swing | 55 |
| BULL_LOW_VOL × swing | 61 |
| SIDEWAYS_LOW_VOL × swing | 28 |

## BULL_HIGH_VOL × Position 최우수 매도 룰

_합격 없음_

## 전체 최우수 (필터, 시그널, 출구) 트리플 Top 10

| rank | regime | bucket | family | params | SL | TP | TM | mean_pnl | sharpe | n |
|------|--------|--------|--------|--------|----|----|----|----------|--------|---|
| 1 | BULL_LOW_VOL | swing | vol_spike_bullish | {'vol_mult': 3.0, 'body_q': 4} | -5.0% | 10% | 30d | 0.0419 | 9.1114 | 62 |
| 2 | BULL_LOW_VOL | swing | vol_spike_bullish | {'vol_mult': 3.0, 'body_q': 4} | -5.0% | 10% | 45d | 0.0419 | 9.1114 | 62 |
| 3 | BULL_LOW_VOL | swing | vol_spike_bullish | {'vol_mult': 3.0, 'body_q': 4} | -5.0% | 10% | 60d | 0.0419 | 9.1114 | 62 |
| 4 | BULL_LOW_VOL | swing | vol_spike_bullish | {'vol_mult': 3.0, 'body_q': 4} | -5.0% | 10% | 20d | 0.0411 | 8.9690 | 62 |
| 5 | BULL_LOW_VOL | swing | vol_spike_bullish | {'vol_mult': 3.0, 'body_q': 4} | -5.0% | 15% | 10d | 0.0408 | 7.2871 | 62 |
| 6 | BEAR_HIGH_VOL | swing | ma_pullback_reversal | {'ma_period': 5, 'pullback_pct': -0.05} | -3.0% | 15% | 30d | 0.0393 | 7.4975 | 144 |
| 7 | BEAR_HIGH_VOL | swing | ma_pullback_reversal | {'ma_period': 5, 'pullback_pct': -0.05} | -3.0% | 15% | 20d | 0.0375 | 7.5946 | 144 |
| 8 | BULL_LOW_VOL | swing | vol_spike_bullish | {'vol_mult': 3.0, 'body_q': 4} | -5.0% | 10% | 10d | 0.0337 | 7.6187 | 62 |
| 9 | BEAR_HIGH_VOL | swing | bb_reversion | {'period': 20, 'stddev': 2.5, 'rsi_thr': 35} | -3.0% | 15% | 20d | 0.0335 | 6.7759 | 78 |
| 10 | BULL_LOW_VOL | swing | vol_spike_bullish | {'vol_mult': 3.0, 'body_q': 4} | -5.0% | 15% | 5d | 0.0299 | 6.5930 | 62 |

## P3 진입 판단
- **NG** — 합격 셀 279개, (regime, bucket) 조합 커버 4/18

### 판정 기준
- OK: 합격 셀 ≥ 30 AND (regime, bucket) 조합 커버 ≥ 6/18
- NG: 기준 미달 → 합격선 완화 또는 매도 룰 그리드 확장 필요