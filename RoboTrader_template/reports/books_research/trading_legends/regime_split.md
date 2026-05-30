# 트레이딩의 전설 (일봉 6룰) — 국면(BULL/BEAR/SIDEWAYS) 분해

국면 분류: KOSPI 20일 rolling 누적수익률, ±2% 임계 (Elder/Minervini/문병로 와 동일 라벨 `regime_label_5y.parquet`).

## 국면 분포 (window 이후 실제 분류 거래일)

| 국면 | 일수 | 비율 |
|---|---:|---:|
| BULL | 513 | 39.3% |
| BEAR | 382 | 29.3% |
| SIDEWAYS | 409 | 31.4% |
| **합계** | **1304** | 100% |

2022년(약세장 검증연도) 국면: BULL 55 / BEAR 129 / SIDEWAYS 62 (총 246일).

> **주의(trading_legends 룰 성격)**: 단기 추세추종/돌파/오버나이트 룰이라 hold가 짧다(O는 익일, A/B도 수~수십일). entry≈exit 국면이 대체로 일치하나, 일관성을 위해 **entry 기준**(그 국면에서 *진입*한 거래의 최종 결과)과 **exit 기준**(그 국면에서 *청산*된 거래의 성과)을 모두 보고한다. per-trade Sharpe proxy = pooled mean/std(연율화 안 함). 표본<20 은 (표본부족) 표기.

## ENTRY 기준 분해표

| rule | 국면 | n | mean% | median% | 승률 | shp_px | hold(d) |
|---|---|---:|---:|---:|---:|---:|---:|
| close_momentum_breakout O | ALL | 1456 | -0.122 | -1.020 | 41.7% | -0.014 | 3 |
| close_momentum_breakout O | BULL | 892 | 0.301 | -0.884 | 43.2% | 0.032 | 3 |
| close_momentum_breakout O | BEAR | 179 | -1.503 | -2.436 | 34.1% | -0.163 | 3 |
| close_momentum_breakout O | SIDEWAYS | 385 | -0.463 | -0.766 | 41.8% | -0.060 | 3 |
| close_momentum_breakout A | ALL | 1154 | 0.316 | -2.459 | 34.8% | 0.024 | 7 |
| close_momentum_breakout A | BULL | 688 | 1.218 | -2.230 | 37.8% | 0.083 | 7 |
| close_momentum_breakout A | BEAR | 147 | -0.741 | -3.234 | 28.6% | -0.054 | 7 |
| close_momentum_breakout A | SIDEWAYS | 319 | -1.141 | -2.418 | 31.3% | -0.126 | 6 |
| limit_up_follow O | ALL | 139 | 2.572 | -1.031 | 46.8% | 0.152 | 2 |
| limit_up_follow O | BULL | 90 | 4.215 | -0.037 | 50.0% | 0.230 | 2 |
| limit_up_follow O | BEAR | 18 | -2.112 | -5.912 | 27.8% | -0.186 | 2 ⚠표본부족 |
| limit_up_follow O | SIDEWAYS | 31 | 0.521 | -0.545 | 48.4% | 0.036 | 2 |
| new_high_breakout A | ALL | 607 | 1.254 | -4.500 | 32.5% | 0.062 | 19 |
| new_high_breakout A | BULL | 339 | 1.922 | -3.672 | 34.8% | 0.094 | 19 |
| new_high_breakout A | BEAR | 97 | 1.212 | -6.141 | 26.8% | 0.047 | 20 |
| new_high_breakout A | SIDEWAYS | 171 | -0.046 | -4.659 | 31.0% | -0.003 | 20 |
| prev_limitup_pullback A | ALL | 37 | 3.448 | -4.832 | 40.5% | 0.172 | 10 |
| prev_limitup_pullback A | BULL | 27 | 1.192 | -5.051 | 37.0% | 0.067 | 10 |
| prev_limitup_pullback A | BEAR | 2 | 2.186 | 2.186 | 50.0% | 0.786 | 12 ⚠표본부족 |
| prev_limitup_pullback A | SIDEWAYS | 8 | 11.380 | 2.398 | 50.0% | 0.424 | 11 ⚠표본부족 |
| ma5_pullback A | ALL | 3844 | 0.272 | -1.392 | 34.1% | 0.028 | 5 |
| ma5_pullback A | BULL | 1594 | 0.846 | -1.489 | 33.4% | 0.069 | 5 |
| ma5_pullback A | BEAR | 1164 | 0.126 | -1.223 | 36.3% | 0.015 | 6 |
| ma5_pullback A | SIDEWAYS | 1086 | -0.413 | -1.478 | 32.8% | -0.058 | 5 |
| ma5_pullback B | ALL | 2520 | 1.540 | -2.141 | 45.3% | 0.119 | 17 |
| ma5_pullback B | BULL | 1068 | 3.166 | -0.865 | 48.1% | 0.229 | 16 |
| ma5_pullback B | BEAR | 783 | 1.145 | -1.352 | 46.6% | 0.094 | 19 |
| ma5_pullback B | SIDEWAYS | 669 | -0.595 | -5.661 | 39.2% | -0.050 | 18 |
| bottom_first_bull A | ALL | 791 | 0.221 | -0.976 | 35.7% | 0.026 | 8 |
| bottom_first_bull A | BULL | 217 | -0.329 | -1.431 | 27.6% | -0.047 | 9 |
| bottom_first_bull A | BEAR | 328 | 0.812 | -0.725 | 40.5% | 0.074 | 7 |
| bottom_first_bull A | SIDEWAYS | 246 | -0.083 | -0.881 | 36.2% | -0.014 | 9 |

## EXIT 기준 분해표

| rule | 국면 | n | mean% | median% | 승률 | shp_px | hold(d) |
|---|---|---:|---:|---:|---:|---:|---:|
| close_momentum_breakout O | ALL | 1456 | -0.122 | -1.020 | 41.7% | -0.014 | 3 |
| close_momentum_breakout O | BULL | 890 | 0.426 | -0.843 | 43.8% | 0.046 | 3 |
| close_momentum_breakout O | BEAR | 220 | -1.767 | -2.209 | 33.2% | -0.201 | 3 |
| close_momentum_breakout O | SIDEWAYS | 346 | -0.489 | -0.785 | 41.6% | -0.061 | 3 |
| close_momentum_breakout A | ALL | 1154 | 0.316 | -2.459 | 34.8% | 0.024 | 7 |
| close_momentum_breakout A | BULL | 672 | 1.441 | -1.794 | 39.9% | 0.098 | 7 |
| close_momentum_breakout A | BEAR | 193 | -1.938 | -3.303 | 26.4% | -0.208 | 6 |
| close_momentum_breakout A | SIDEWAYS | 289 | -0.795 | -2.770 | 28.7% | -0.069 | 7 |
| limit_up_follow O | ALL | 139 | 2.572 | -1.031 | 46.8% | 0.152 | 2 |
| limit_up_follow O | BULL | 85 | 4.521 | 0.244 | 51.8% | 0.256 | 2 |
| limit_up_follow O | BEAR | 23 | -3.858 | -5.446 | 30.4% | -0.502 | 2 |
| limit_up_follow O | SIDEWAYS | 31 | 1.999 | -2.769 | 45.2% | 0.107 | 2 |
| new_high_breakout A | ALL | 607 | 1.254 | -4.500 | 32.5% | 0.062 | 19 |
| new_high_breakout A | BULL | 304 | 2.942 | -3.355 | 37.8% | 0.138 | 19 |
| new_high_breakout A | BEAR | 143 | -1.374 | -5.787 | 27.3% | -0.087 | 20 |
| new_high_breakout A | SIDEWAYS | 160 | 0.396 | -5.159 | 26.9% | 0.018 | 19 |
| prev_limitup_pullback A | ALL | 37 | 3.448 | -4.832 | 40.5% | 0.172 | 10 |
| prev_limitup_pullback A | BULL | 25 | 1.936 | -4.832 | 40.0% | 0.109 | 9 |
| prev_limitup_pullback A | BEAR | 3 | -8.149 | -6.966 | 0.0% | -1.216 | 8 ⚠표본부족 |
| prev_limitup_pullback A | SIDEWAYS | 9 | 11.515 | 1.931 | 55.6% | 0.453 | 13 ⚠표본부족 |
| ma5_pullback A | ALL | 3844 | 0.272 | -1.392 | 34.1% | 0.028 | 5 |
| ma5_pullback A | BULL | 1649 | 1.492 | -1.222 | 37.4% | 0.118 | 6 |
| ma5_pullback A | BEAR | 1134 | -1.009 | -1.741 | 31.0% | -0.139 | 5 |
| ma5_pullback A | SIDEWAYS | 1061 | -0.253 | -1.345 | 32.2% | -0.039 | 5 |
| ma5_pullback B | ALL | 2520 | 1.540 | -2.141 | 45.3% | 0.119 | 17 |
| ma5_pullback B | BULL | 1143 | 5.222 | 4.229 | 57.8% | 0.393 | 17 |
| ma5_pullback B | BEAR | 673 | -4.185 | -8.744 | 24.2% | -0.368 | 16 |
| ma5_pullback B | SIDEWAYS | 704 | 1.033 | -1.890 | 45.0% | 0.089 | 19 |
| bottom_first_bull A | ALL | 791 | 0.221 | -0.976 | 35.7% | 0.026 | 8 |
| bottom_first_bull A | BULL | 215 | 0.560 | -0.987 | 34.0% | 0.058 | 11 |
| bottom_first_bull A | BEAR | 352 | 0.056 | -0.994 | 36.6% | 0.006 | 7 |
| bottom_first_bull A | SIDEWAYS | 224 | 0.155 | -0.952 | 35.7% | 0.027 | 8 |

## 핵심 질문 — 어떤 룰이 약세장(BEAR)에서도 per-trade 양수인가?

| rule | entry-BEAR mean% | n | exit-BEAR mean% | n |
|---|---:|---:|---:|---:|
| close_momentum_breakout O | -1.503 | 179 | -1.767 | 220 |
| close_momentum_breakout A | -0.741 | 147 | -1.938 | 193 |
| limit_up_follow O | -2.112 | 18 | -3.858 | 23 |
| new_high_breakout A | 1.212 | 97 | -1.374 | 143 |
| prev_limitup_pullback A | 2.186 | 2 | -8.149 | 3 |
| ma5_pullback A | 0.126 | 1164 | -1.009 | 1134 |
| ma5_pullback B | 1.145 | 783 | -4.185 | 673 |
| bottom_first_bull A | 0.812 | 328 | 0.056 | 352 |

- **entry-BEAR mean% > 0** → 약세장에서 *진입*한 거래가 결국 양수 = 약세장 진입 방어 성립.
- **exit-BEAR mean% < 0** → 약세장에 *청산*된 거래(주로 stop_loss)는 손실.
- 비교 기준 — Elder ema_pullback A: BEAR per-trade **+3.01%** (CANDIDATE 등록 근거).
