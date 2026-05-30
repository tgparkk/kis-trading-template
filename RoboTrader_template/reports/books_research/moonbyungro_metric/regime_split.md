# 문병로 메트릭 스튜디오 — 국면(BULL/BEAR/SIDEWAYS) 분해

국면 분류: KOSPI 20일 rolling 누적수익률, ±2% 임계 (Elder/Minervini 와 동일 라벨 `regime_label_5y.parquet`).

## 국면 분포 (window 이후 실제 분류 거래일)

| 국면 | 일수 | 비율 |
|---|---:|---:|
| BULL | 513 | 39.3% |
| BEAR | 382 | 29.3% |
| SIDEWAYS | 409 | 31.4% |
| **합계** | **1304** | 100% |

2022년(약세장 검증연도) 국면: BULL 55 / BEAR 129 / SIDEWAYS 62 (총 246일) — 2022가 BEAR 비중 높음을 확인.

> **주의(문병로 룰 특수성)**: 가치투자라 보유기간이 길다(median 176~210일). 한 거래가 여러 국면을 가로질러, 아래는 **entry 기준**(그 국면에서 *진입*한 거래의 최종 결과)과 **exit 기준**(그 국면에서 *청산*된 거래의 성과)을 모두 보고한다. per-trade Sharpe proxy = pooled mean/std(연율화 안 함). 표본<20 은 (표본부족) 표기.

## ENTRY 기준 분해표

| rule | 국면 | n | mean% | median% | 승률 | shp_px | hold(d) |
|---|---|---:|---:|---:|---:|---:|---:|
| value_composite_kr K | ALL | 218 | 9.972 | -9.697 | 40.4% | 0.236 | 215 |
| value_composite_kr K | BULL | 47 | 20.807 | 11.806 | 61.7% | 0.490 | 153 |
| value_composite_kr K | BEAR | 98 | 4.997 | -16.447 | 31.6% | 0.124 | 248 |
| value_composite_kr K | SIDEWAYS | 73 | 9.675 | -16.763 | 38.4% | 0.224 | 210 |
| value_composite_kr A | ALL | 301 | 5.975 | -2.130 | 46.8% | 0.201 | 145 |
| value_composite_kr A | BULL | 68 | 14.559 | 11.190 | 63.2% | 0.452 | 127 |
| value_composite_kr A | BEAR | 112 | -0.146 | -7.043 | 34.8% | -0.005 | 153 |
| value_composite_kr A | SIDEWAYS | 121 | 6.816 | -0.055 | 48.8% | 0.229 | 147 |
| low_pbr K | ALL | 166 | 5.650 | -14.874 | 36.7% | 0.153 | 229 |
| low_pbr K | BULL | 24 | 14.773 | -4.719 | 45.8% | 0.360 | 198 |
| low_pbr K | BEAR | 88 | 1.282 | -17.279 | 29.5% | 0.036 | 242 |
| low_pbr K | SIDEWAYS | 54 | 8.713 | -8.491 | 44.4% | 0.243 | 221 |
| low_pbr A | ALL | 250 | 3.191 | -1.625 | 46.4% | 0.122 | 150 |
| low_pbr A | BULL | 61 | 1.410 | -0.200 | 47.5% | 0.071 | 137 |
| low_pbr A | BEAR | 86 | -1.680 | -4.554 | 38.4% | -0.069 | 156 |
| low_pbr A | SIDEWAYS | 103 | 8.313 | 3.226 | 52.4% | 0.282 | 154 |
| small_value K | ALL | 213 | 8.862 | -16.609 | 39.0% | 0.202 | 204 |
| small_value K | BULL | 45 | 7.343 | -9.579 | 42.2% | 0.182 | 124 |
| small_value K | BEAR | 104 | 7.662 | -16.899 | 35.6% | 0.175 | 236 |
| small_value K | SIDEWAYS | 64 | 11.879 | -15.648 | 42.2% | 0.258 | 209 |
| small_value A | ALL | 289 | 5.588 | -3.310 | 46.0% | 0.171 | 141 |
| small_value A | BULL | 61 | 6.348 | -0.586 | 49.2% | 0.195 | 118 |
| small_value A | BEAR | 116 | 6.234 | -2.648 | 44.0% | 0.178 | 148 |
| small_value A | SIDEWAYS | 112 | 4.505 | -4.881 | 46.4% | 0.149 | 146 |

## EXIT 기준 분해표

| rule | 국면 | n | mean% | median% | 승률 | shp_px | hold(d) |
|---|---|---:|---:|---:|---:|---:|---:|
| value_composite_kr K | ALL | 218 | 9.972 | -9.697 | 40.4% | 0.236 | 215 |
| value_composite_kr K | BULL | 79 | 35.421 | 23.425 | 70.9% | 0.741 | 190 |
| value_composite_kr K | BEAR | 110 | -8.377 | -18.312 | 16.4% | -0.293 | 207 |
| value_composite_kr K | SIDEWAYS | 29 | 10.250 | -0.910 | 48.3% | 0.321 | 314 |
| value_composite_kr A | ALL | 301 | 5.975 | -2.130 | 46.8% | 0.201 | 145 |
| value_composite_kr A | BULL | 105 | 24.005 | 16.600 | 71.4% | 0.693 | 138 |
| value_composite_kr A | BEAR | 106 | -8.661 | -19.894 | 18.9% | -0.378 | 128 |
| value_composite_kr A | SIDEWAYS | 90 | 2.176 | 0.724 | 51.1% | 0.126 | 172 |
| low_pbr K | ALL | 166 | 5.650 | -14.874 | 36.7% | 0.153 | 229 |
| low_pbr K | BULL | 49 | 30.478 | 23.656 | 67.3% | 0.676 | 212 |
| low_pbr K | BEAR | 89 | -6.355 | -18.147 | 19.1% | -0.224 | 217 |
| low_pbr K | SIDEWAYS | 28 | 0.360 | -5.707 | 39.3% | 0.018 | 294 |
| low_pbr A | ALL | 250 | 3.191 | -1.625 | 46.4% | 0.122 | 150 |
| low_pbr A | BULL | 87 | 13.368 | 7.273 | 65.5% | 0.494 | 150 |
| low_pbr A | BEAR | 84 | -9.144 | -19.861 | 22.6% | -0.402 | 133 |
| low_pbr A | SIDEWAYS | 79 | 5.100 | 0.039 | 50.6% | 0.225 | 170 |
| small_value K | ALL | 213 | 8.862 | -16.609 | 39.0% | 0.202 | 204 |
| small_value K | BULL | 70 | 33.394 | 20.257 | 71.4% | 0.695 | 201 |
| small_value K | BEAR | 110 | -9.030 | -19.050 | 15.5% | -0.288 | 184 |
| small_value K | SIDEWAYS | 33 | 16.464 | -2.009 | 48.5% | 0.387 | 279 |
| small_value A | ALL | 289 | 5.588 | -3.310 | 46.0% | 0.171 | 141 |
| small_value A | BULL | 89 | 24.182 | 12.323 | 73.0% | 0.668 | 140 |
| small_value A | BEAR | 108 | -10.085 | -20.247 | 17.6% | -0.400 | 120 |
| small_value A | SIDEWAYS | 92 | 5.999 | 0.747 | 53.3% | 0.222 | 165 |

## 핵심 질문 — 저PBR/소형주가 약세장(BEAR)에서 방어가 되는가?

| rule | entry-BEAR mean% | n | exit-BEAR mean% | n |
|---|---:|---:|---:|---:|
| value_composite_kr K | 4.997 | 98 | -8.377 | 110 |
| value_composite_kr A | -0.146 | 112 | -8.661 | 106 |
| low_pbr K | 1.282 | 88 | -6.355 | 89 |
| low_pbr A | -1.680 | 86 | -9.144 | 84 |
| small_value K | 7.662 | 104 | -9.030 | 110 |
| small_value A | 6.234 | 116 | -10.085 | 108 |

- **entry-BEAR mean% > 0** → 약세장에서 *진입*한 가치/저PBR 거래가 결국 양수로 회복 = 약세장 진입 방어 성립.
- **exit-BEAR mean% < 0** → 약세장에 *청산*된 거래(주로 stop_loss)는 손실 = 약세장 한복판 청산의 비용.
- 비교 기준 — Elder ema_pullback A: BEAR per-trade **+3.01%** (CANDIDATE 등록 근거).
