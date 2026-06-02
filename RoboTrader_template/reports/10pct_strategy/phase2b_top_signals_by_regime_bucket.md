# Phase 2B — 국면 × 버킷 Top 시그널 매트릭스

생성일: 2026-05-24

전체 평가: 10,380 셀 | 합격: 271 셀


## BULL_HIGH_VOL × 스윙 (3d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | ma_pullback_reversal | {'ma_period': 20, 'pullback_pct': -0.05} | 12.933 | 0.9527 | 0.0275 | 63 | **PASS** |
| 2 | bb_reversion | {'period': 15, 'stddev': 2.5, 'rsi_thr': 35} | 9.896 | N/A | 0.0602 | 50 | - |
| 3 | ma_pullback_reversal | {'ma_period': 20, 'pullback_pct': -0.03} | 6.870 | 0.4516 | 0.0226 | 124 | **PASS** |
| 4 | marubozu_bull | {'vol_mult': 2.0} | 6.151 | 0.0201 | 0.0232 | 154 | **PASS** |
| 5 | marubozu_bull | {'vol_mult': 2.0} | 5.061 | 0.0371 | 0.0276 | 112 | **PASS** |

## BULL_HIGH_VOL × 미드 (20d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | golden_cross | {'fast_ma': 10, 'slow_ma': 30, 'vol_mult': 1.5} | 1.815 | 0.0925 | 0.0870 | 138 | **PASS** |
| 2 | golden_cross | {'fast_ma': 10, 'slow_ma': 30, 'vol_mult': 1.5} | 1.665 | 0.0590 | 0.0915 | 155 | **PASS** |
| 3 | golden_cross | {'fast_ma': 10, 'slow_ma': 30, 'vol_mult': 1.5} | 1.662 | 0.0932 | 0.0849 | 160 | **PASS** |
| 4 | long_candle_dist | {'bull_ratio_quintile': 4} | 1.575 | 0.0567 | 0.1759 | 7268 | - |
| 5 | breakout_marubozu | {'lookback': 5, 'vol_mult': 1.5} | 1.570 | -0.0067 | 0.0898 | 169 | - |

## BULL_HIGH_VOL × 포지션 (60d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | ema200_trend | {'hold_days': 20, 'slope_min': 0.001} | 2.106 | N/A | 0.4829 | 65 | - |
| 2 | ema200_trend | {'hold_days': 20, 'slope_min': 0.0} | 2.070 | N/A | 0.4745 | 66 | - |
| 3 | ema200_trend | {'hold_days': 60, 'slope_min': 0.001} | 1.929 | N/A | 0.4533 | 50 | - |
| 4 | ema200_trend | {'hold_days': 40, 'slope_min': 0.0} | 1.923 | N/A | 0.3645 | 770 | - |
| 5 | ema200_trend | {'hold_days': 40, 'slope_min': 0.001} | 1.919 | N/A | 0.3637 | 761 | - |

## BULL_LOW_VOL × 스윙 (3d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | inverted_hammer | {'vol_mult': 1.5} | 11.225 | 0.0029 | 0.0734 | 75 | - |
| 2 | vwap_pullback | {'pullback_pct': -0.05, 'vol_mult': 2.0} | 9.120 | 0.0067 | 0.0381 | 125 | - |
| 3 | vwap_pullback | {'pullback_pct': -0.05, 'vol_mult': 1.5} | 7.829 | -0.0004 | 0.0357 | 210 | - |
| 4 | marubozu_bull | {'vol_mult': 2.0} | 7.268 | -0.0023 | 0.0400 | 164 | - |
| 5 | bb_reversion | {'period': 25, 'stddev': 2.0, 'rsi_thr': 25} | 6.910 | 0.0242 | 0.0181 | 55 | **PASS** |

## BULL_LOW_VOL × 미드 (20d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | ema200_breakout | {'hold_days': 3, 'vol_mult': 2.0} | 6.336 | 0.2719 | 0.0258 | 198 | **PASS** |
| 2 | near_52w_high | {'within_pct': 0.03, 'vol_mult': 1.2} | 5.218 | 0.0099 | 0.0667 | 723 | - |
| 3 | near_52w_high | {'within_pct': 0.03, 'vol_mult': 1.5} | 4.989 | 0.0179 | 0.0615 | 549 | - |
| 4 | near_52w_high | {'within_pct': 0.05, 'vol_mult': 1.2} | 4.587 | -0.0023 | 0.0644 | 1190 | - |
| 5 | ema200_breakout | {'hold_days': 3, 'vol_mult': 1.5} | 4.327 | 0.1710 | 0.0308 | 320 | **PASS** |

## BULL_LOW_VOL × 포지션 (60d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | ema200_trend | {'hold_days': 60, 'slope_min': 0.001} | 5.391 | N/A | 0.3805 | 690 | - |
| 2 | ema200_trend | {'hold_days': 60, 'slope_min': 0.0} | 5.389 | N/A | 0.3803 | 699 | - |
| 3 | ema200_trend | {'hold_days': 40, 'slope_min': 0.001} | 3.512 | 0.0360 | 0.2598 | 1870 | - |
| 4 | ema200_trend | {'hold_days': 40, 'slope_min': 0.0} | 3.506 | 0.0348 | 0.2595 | 1891 | - |
| 5 | cup_handle | {'cup_depth_max': 0.2, 'vol_mult': 2.0} | 2.724 | 0.2986 | 0.0916 | 68 | **PASS** |

## BEAR_HIGH_VOL × 스윙 (3d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | bb_reversion | {'period': 15, 'stddev': 2.5, 'rsi_thr': 25} | 9.322 | 0.0269 | N/A | 94 | - |
| 2 | bb_reversion | {'period': 20, 'stddev': 1.5, 'rsi_thr': 25} | 8.967 | 0.0244 | 0.0966 | 1356 | - |
| 3 | bb_reversion | {'period': 25, 'stddev': 1.5, 'rsi_thr': 25} | 8.491 | 0.0239 | 0.0877 | 1556 | - |
| 4 | bb_reversion | {'period': 25, 'stddev': 2.0, 'rsi_thr': 25} | 8.171 | 0.0223 | 0.0810 | 635 | - |
| 5 | bb_reversion | {'period': 20, 'stddev': 1.5, 'rsi_thr': 30} | 8.066 | 0.0212 | 0.1077 | 2217 | - |

## BEAR_HIGH_VOL × 미드 (20d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | long_candle_dist | {'bull_ratio_quintile': 5} | 2.402 | 0.0736 | 0.1563 | 636 | - |
| 2 | ema200_breakout | {'hold_days': 10, 'vol_mult': 1.5} | 1.935 | 0.0793 | N/A | 56 | - |
| 3 | near_52w_high | {'within_pct': 0.03, 'vol_mult': 1.2} | 1.903 | 0.0257 | N/A | 177 | - |
| 4 | new_high_breakout | {'lookback': 10, 'vol_mult': 1.2} | 1.880 | 0.0230 | 0.4671 | 141 | - |
| 5 | long_candle_dist | {'bull_ratio_quintile': 4} | 1.876 | 0.0560 | 0.1378 | 1248 | - |

## BEAR_HIGH_VOL × 포지션 (60d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | ema200_trend | {'hold_days': 40, 'slope_min': 0.001} | 59.132 | 0.2224 | N/A | 184 | - |
| 2 | ema200_trend | {'hold_days': 40, 'slope_min': 0.0} | 57.995 | 0.2181 | N/A | 189 | - |
| 3 | ema200_trend | {'hold_days': 60, 'slope_min': 0.001} | 51.230 | 0.1927 | N/A | 108 | - |
| 4 | ema200_trend | {'hold_days': 60, 'slope_min': 0.0} | 50.850 | 0.1912 | N/A | 111 | - |
| 5 | ema200_trend | {'hold_days': 20, 'slope_min': 0.001} | 38.035 | 0.1437 | N/A | 389 | - |

## BEAR_LOW_VOL × 스윙 (3d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | three_white_soldiers | {'vol_mult': 1.5} | 77.259 | 0.0202 | N/A | 125 | - |
| 2 | vol_spike_bullish | {'vol_mult': 3.0, 'body_q': 4} | 47.260 | 0.0124 | N/A | 85 | - |
| 3 | three_white_soldiers | {'vol_mult': 1.0} | 46.718 | 0.0122 | N/A | 201 | - |
| 4 | vol_spike_bullish | {'vol_mult': 3.0, 'body_q': 3} | 46.546 | 0.0122 | N/A | 89 | - |
| 5 | ma_pullback_reversal | {'ma_period': 20, 'pullback_pct': -0.05} | 40.750 | 0.0107 | N/A | 200 | - |

## BEAR_LOW_VOL × 미드 (20d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | new_high_breakout | {'lookback': 20, 'vol_mult': 1.2} | 50.153 | -0.0367 | N/A | 198 | - |
| 2 | new_high_breakout | {'lookback': 5, 'vol_mult': 1.5} | 48.051 | -0.0352 | N/A | 185 | - |
| 3 | golden_cross | {'fast_ma': 5, 'slow_ma': 20, 'vol_mult': 1.0} | 47.244 | -0.0346 | N/A | 67 | - |
| 4 | near_52w_high | {'within_pct': 0.03, 'vol_mult': 1.5} | 46.523 | -0.0341 | N/A | 79 | - |
| 5 | golden_cross | {'fast_ma': 20, 'slow_ma': 60, 'vol_mult': 1.0} | 46.207 | -0.0338 | N/A | 54 | - |

## BEAR_LOW_VOL × 포지션 (60d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | pos_three_soldiers_ema | {'vol_mult': 1.0} | 3240.670 | -0.0503 | N/A | 189 | - |
| 2 | cup_handle | {'cup_depth_max': 0.2, 'vol_mult': 2.0} | 2864.167 | -0.0444 | N/A | 60 | - |
| 3 | pbr_momentum | {'mcap_quintile_max': 2, 'ret60d_quintile_min': 4} | 2436.399 | -0.0378 | N/A | 275 | - |
| 4 | pos_three_soldiers_ema | {'vol_mult': 1.5} | 1688.947 | -0.0262 | N/A | 122 | - |
| 5 | cup_handle | {'cup_depth_max': 0.2, 'vol_mult': 1.5} | 1668.757 | -0.0259 | N/A | 153 | - |

## SIDEWAYS_HIGH_VOL × 스윙 (3d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | bb_reversion | {'period': 25, 'stddev': 2.0, 'rsi_thr': 30} | 16.122 | -0.0204 | -0.0306 | 77 | - |
| 2 | bb_reversion | {'period': 20, 'stddev': 1.5, 'rsi_thr': 25} | 15.769 | -0.0284 | -0.0381 | 101 | - |
| 3 | bb_reversion | {'period': 25, 'stddev': 2.0, 'rsi_thr': 35} | 15.651 | -0.0195 | -0.0307 | 101 | - |
| 4 | bb_reversion | {'period': 25, 'stddev': 1.5, 'rsi_thr': 25} | 15.197 | -0.0235 | -0.0409 | 104 | - |
| 5 | bb_reversion | {'period': 25, 'stddev': 2.0, 'rsi_thr': 25} | 14.971 | -0.0201 | -0.0260 | 51 | - |

## SIDEWAYS_HIGH_VOL × 미드 (20d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | near_52w_high | {'within_pct': 0.05, 'vol_mult': 1.2} | 19.023 | -0.0453 | 0.1857 | 63 | - |
| 2 | near_52w_high | {'within_pct': 0.1, 'vol_mult': 1.2} | 18.642 | -0.0345 | 0.1954 | 92 | - |
| 3 | near_52w_high | {'within_pct': 0.1, 'vol_mult': 1.5} | 15.941 | -0.0374 | 0.1851 | 55 | - |
| 4 | new_high_breakout | {'lookback': 20, 'vol_mult': 1.5} | 13.436 | -0.0397 | 0.1743 | 62 | - |
| 5 | new_high_breakout | {'lookback': 20, 'vol_mult': 1.2} | 12.602 | -0.0472 | 0.1620 | 86 | - |

## SIDEWAYS_HIGH_VOL × 포지션 (60d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | pbr_momentum | {'mcap_quintile_max': 1, 'ret60d_quintile_min': 4} | 6.836 | -0.0866 | 0.0031 | 798 | - |
| 2 | pbr_momentum | {'mcap_quintile_max': 1, 'ret60d_quintile_min': 5} | 5.969 | -0.0710 | -0.0054 | 668 | - |
| 3 | ema200_trend | {'hold_days': 20, 'slope_min': 0.001} | 5.872 | -0.0168 | 0.2365 | 254 | - |
| 4 | ema200_trend | {'hold_days': 20, 'slope_min': 0.0} | 5.860 | -0.0168 | 0.2356 | 255 | - |
| 5 | ema200_trend | {'hold_days': 20, 'slope_min': 0.001} | 4.598 | 0.0462 | 0.3873 | 115 | - |

## SIDEWAYS_LOW_VOL × 스윙 (3d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | bb_reversion | {'period': 25, 'stddev': 2.5, 'rsi_thr': 25} | 43.061 | 0.0126 | N/A | 87 | - |
| 2 | bullish_engulfing | {'body_ratio': 1.5, 'vol_mult': 1.5} | 40.379 | 0.0154 | N/A | 63 | - |
| 3 | bb_reversion | {'period': 20, 'stddev': 2.5, 'rsi_thr': 25} | 40.287 | 0.0128 | N/A | 52 | - |
| 4 | bullish_engulfing | {'body_ratio': 1.0, 'vol_mult': 1.5} | 38.579 | 0.0142 | N/A | 68 | - |
| 5 | bb_reversion | {'period': 15, 'stddev': 2.0, 'rsi_thr': 25} | 35.489 | 0.0086 | 0.0524 | 160 | - |

## SIDEWAYS_LOW_VOL × 미드 (20d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | golden_cross | {'fast_ma': 5, 'slow_ma': 20, 'vol_mult': 1.5} | 9.484 | -0.0292 | -0.0338 | 225 | - |
| 2 | breakout_marubozu | {'lookback': 5, 'vol_mult': 2.0} | 7.491 | -0.0209 | -0.0357 | 111 | - |
| 3 | breakout_marubozu | {'lookback': 20, 'vol_mult': 2.0} | 6.921 | -0.0109 | -0.0692 | 88 | - |
| 4 | breakout_marubozu | {'lookback': 10, 'vol_mult': 2.0} | 6.313 | -0.0067 | -0.0743 | 100 | - |
| 5 | golden_cross | {'fast_ma': 5, 'slow_ma': 20, 'vol_mult': 1.0} | 6.309 | -0.0286 | 0.0045 | 314 | - |

## SIDEWAYS_LOW_VOL × 포지션 (60d 청산)

| rank | family | params | lift | IS_mean | OOS_mean | n | PASS |
|------|--------|--------|------|---------|----------|---|------|
| 1 | ema200_trend | {'hold_days': 40, 'slope_min': 0.001} | 263.037 | 0.0433 | 0.1451 | 739 | - |
| 2 | ema200_trend | {'hold_days': 40, 'slope_min': 0.0} | 262.674 | 0.0439 | 0.1435 | 744 | - |
| 3 | ema200_trend | {'hold_days': 20, 'slope_min': 0.001} | 256.934 | 0.0278 | 0.1804 | 1896 | - |
| 4 | ema200_trend | {'hold_days': 20, 'slope_min': 0.0} | 255.693 | 0.0274 | 0.1800 | 1914 | - |
| 5 | pos_three_soldiers_ema | {'vol_mult': 1.5} | 241.981 | 0.0861 | 0.0021 | 345 | **PASS** |
