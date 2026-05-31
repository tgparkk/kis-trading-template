# 디노 급등주 투자법 — 국면(BULL/BEAR/SIDEWAYS)·연도 분해

국면 분류: KOSPI 20일 rolling 누적수익률, ±2% 임계 (Elder/Minervini/문병로 와 동일 라벨 `regime_label_5y.parquet`).

## 국면 분포 (window 이후 실제 분류 거래일)

| 국면 | 일수 | 비율 |
|---|---:|---:|
| BULL | 513 | 39.3% |
| BEAR | 382 | 29.3% |
| SIDEWAYS | 409 | 31.4% |
| **합계** | **1304** | 100% |

> per-trade pnl = sell행 pnl_pct(소수=비율). per-trade Sharpe proxy = pooled mean/std(연율화 안 함). 표본<20 은 ⚠표본부족 표기. 회전 철학상 hold 가 짧아 entry≈exit 국면 대체로 일치.

## ENTRY 기준 국면 분해표

| rule | 국면 | n | mean% | median% | 승률 | shp_px | hold(d) |
|---|---|---:|---:|---:|---:|---:|---:|
| B pullback_rebound | ALL | 55 | 3.130 | 2.148 | 56.4% | 0.318 | 14.2 |
| B pullback_rebound | BULL | 7 | 2.624 | -3.671 | 42.9% | 0.261 | 14.9 ⚠표본부족 |
| B pullback_rebound | BEAR | 39 | 3.588 | 2.977 | 61.5% | 0.357 | 13.9 |
| B pullback_rebound | SIDEWAYS | 9 | 1.539 | -1.054 | 44.4% | 0.182 | 15.0 ⚠표본부족 |
| C pullback+trend_exit | ALL | 56 | 0.633 | -0.392 | 46.4% | 0.117 | 1.7 |
| C pullback+trend_exit | BULL | 7 | 4.047 | -0.584 | 42.9% | 0.362 | 2.7 ⚠표본부족 |
| C pullback+trend_exit | BEAR | 40 | 0.029 | -0.776 | 42.5% | 0.008 | 1.7 |
| C pullback+trend_exit | SIDEWAYS | 9 | 0.661 | 1.135 | 66.7% | 0.261 | 1.2 ⚠표본부족 |
| A dino_test (fin) | ALL | 8 | 0.977 | -0.717 | 25.0% | 0.186 | 2.5 |
| A dino_test (fin) | BULL | 1 | 3.332 | 3.332 | 100.0% | 0.000 | 7.0 ⚠표본부족 |
| A dino_test (fin) | BEAR | 5 | 1.966 | -0.556 | 20.0% | 0.326 | 1.8 ⚠표본부족 |
| A dino_test (fin) | SIDEWAYS | 2 | -2.672 | -2.672 | 0.0% | -2.618 | 2.0 ⚠표본부족 |
| A dino_test (no-fin) | ALL | 135 | 0.527 | -0.200 | 48.1% | 0.099 | 4.1 |
| A dino_test (no-fin) | BULL | 25 | 2.562 | 0.449 | 64.0% | 0.444 | 3.7 |
| A dino_test (no-fin) | BEAR | 70 | 0.874 | 0.312 | 54.3% | 0.155 | 5.0 |
| A dino_test (no-fin) | SIDEWAYS | 40 | -1.351 | -1.120 | 27.5% | -0.361 | 2.8 |

## EXIT 기준 국면 분해표

| rule | 국면 | n | mean% | median% | 승률 | shp_px | hold(d) |
|---|---|---:|---:|---:|---:|---:|---:|
| B pullback_rebound | ALL | 55 | 3.130 | 2.148 | 56.4% | 0.318 | 14.2 |
| B pullback_rebound | BULL | 11 | 5.957 | 5.591 | 72.7% | 0.825 | 20.5 ⚠표본부족 |
| B pullback_rebound | BEAR | 29 | 0.648 | -5.205 | 44.8% | 0.070 | 10.7 |
| B pullback_rebound | SIDEWAYS | 15 | 5.855 | 2.977 | 66.7% | 0.525 | 16.5 ⚠표본부족 |
| C pullback+trend_exit | ALL | 56 | 0.633 | -0.392 | 46.4% | 0.117 | 1.7 |
| C pullback+trend_exit | BULL | 6 | 4.550 | -0.858 | 33.3% | 0.379 | 3.0 ⚠표본부족 |
| C pullback+trend_exit | BEAR | 40 | 0.029 | -0.776 | 42.5% | 0.008 | 1.7 |
| C pullback+trend_exit | SIDEWAYS | 10 | 0.697 | 1.082 | 70.0% | 0.290 | 1.2 ⚠표본부족 |
| A dino_test (fin) | ALL | 8 | 0.977 | -0.717 | 25.0% | 0.186 | 2.5 |
| A dino_test (fin) | BULL | 1 | 3.332 | 3.332 | 100.0% | 0.000 | 7.0 ⚠표본부족 |
| A dino_test (fin) | BEAR | 4 | -1.033 | -0.717 | 0.0% | -1.446 | 1.0 ⚠표본부족 |
| A dino_test (fin) | SIDEWAYS | 3 | 2.872 | -1.651 | 33.3% | 0.364 | 3.0 ⚠표본부족 |
| A dino_test (no-fin) | ALL | 135 | 0.527 | -0.200 | 48.1% | 0.099 | 4.1 |
| A dino_test (no-fin) | BULL | 26 | 2.594 | 0.532 | 65.4% | 0.478 | 3.8 |
| A dino_test (no-fin) | BEAR | 71 | 0.284 | 0.053 | 52.1% | 0.048 | 4.5 |
| A dino_test (no-fin) | SIDEWAYS | 38 | -0.432 | -0.838 | 28.9% | -0.120 | 3.6 |

## 연도별 분해 (exit 기준, per-trade)

| rule | 연도 | n | mean% | 승률 | shp_px |
|---|---|---:|---:|---:|---:|
| B pullback_rebound | 2021 | 10 | 2.152 | 50.0% | 0.242 ⚠ |
| B pullback_rebound | 2022 | 17 | 0.852 | 64.7% | 0.117 ⚠ |
| B pullback_rebound | 2023 | 8 | 9.523 | 62.5% | 0.701 ⚠ |
| B pullback_rebound | 2024 | 16 | 3.243 | 56.2% | 0.364 ⚠ |
| B pullback_rebound | 2025 | 3 | -4.018 | 0.0% | -1.407 ⚠ |
| B pullback_rebound | 2026 | 1 | 20.128 | 100.0% | 0.000 ⚠ |
| C pullback+trend_exit | 2021 | 11 | -0.128 | 36.4% | -0.039 ⚠ |
| C pullback+trend_exit | 2022 | 19 | -0.866 | 36.8% | -0.339 ⚠ |
| C pullback+trend_exit | 2023 | 6 | 0.988 | 50.0% | 0.240 ⚠ |
| C pullback+trend_exit | 2024 | 16 | 0.852 | 56.2% | 0.200 ⚠ |
| C pullback+trend_exit | 2025 | 3 | 0.837 | 66.7% | 0.310 ⚠ |
| C pullback+trend_exit | 2026 | 1 | 31.253 | 100.0% | 0.000 ⚠ |
| A dino_test (fin) | 2022 | 3 | 0.773 | 33.3% | 0.427 ⚠ |
| A dino_test (fin) | 2023 | 3 | 3.357 | 33.3% | 0.447 ⚠ |
| A dino_test (fin) | 2024 | 2 | -2.286 | 0.0% | -1.624 ⚠ |
| A dino_test (no-fin) | 2021 | 18 | 1.131 | 44.4% | 0.184 ⚠ |
| A dino_test (no-fin) | 2022 | 30 | 0.739 | 53.3% | 0.187 |
| A dino_test (no-fin) | 2023 | 15 | -0.306 | 26.7% | -0.065 ⚠ |
| A dino_test (no-fin) | 2024 | 35 | 0.200 | 54.3% | 0.033 |
| A dino_test (no-fin) | 2025 | 30 | -0.185 | 46.7% | -0.047 |
| A dino_test (no-fin) | 2026 | 7 | 4.539 | 57.1% | 0.548 ⚠ |

## 핵심 질문 — 회전형 +10% 익절이 약세장(BEAR)에서 방어가 되는가?

| rule | entry-BEAR mean% | n | exit-BEAR mean% | n |
|---|---:|---:|---:|---:|
| B pullback_rebound | 3.588 | 39 | 0.648 | 29 |
| C pullback+trend_exit | 0.029 | 40 | 0.029 | 40 |
| A dino_test (fin) | 1.966 | 5 | -1.033 | 4 |
| A dino_test (no-fin) | 0.874 | 70 | 0.284 | 71 |

- 비교 기준 — Elder ema_pullback A: BEAR per-trade **+3.01%** (CANDIDATE 등록 근거).
