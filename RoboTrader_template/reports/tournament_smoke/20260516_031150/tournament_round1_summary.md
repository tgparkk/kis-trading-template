# 분봉 데이트레이딩 10전략 토너먼트 1라운드

- 생성 일시: 2026-05-16 05:48:46
- 시나리오 수: 60
- 합격선: 일수익률 >= 0.3% AND 일승률 >= 50% AND MDD >= -15%
- 종합점수 = 0.4×z(일수익률) + 0.3×z(일승률) + 0.3×z(Calmar)

## 상위 10 시나리오

|   rank | strategy      | universe   |   max_positions |   avg_daily_return_pct |   win_rate_pct |   calmar |   mdd_pct | pass   |   composite_score |
|-------:|:--------------|:-----------|----------------:|-----------------------:|---------------:|---------:|----------:|:-------|------------------:|
|      1 | abcd_pattern  | screener   |               3 |                      0 |              0 |        0 |         0 | False  |          0.423974 |
|      2 | abcd_pattern  | screener   |               4 |                      0 |              0 |        0 |         0 | False  |          0.423974 |
|      3 | abcd_pattern  | screener   |               5 |                      0 |              0 |        0 |         0 | False  |          0.423974 |
|      4 | bull_flag     | screener   |               4 |                      0 |              0 |        0 |         0 | False  |          0.423974 |
|      5 | bull_flag     | screener   |               5 |                      0 |              0 |        0 |         0 | False  |          0.423974 |
|      6 | bull_flag     | screener   |               3 |                      0 |              0 |        0 |         0 | False  |          0.423974 |
|      7 | reversal_vwap | dynamic    |               4 |                      0 |              0 |        0 |         0 | False  |          0.423974 |
|      8 | reversal_vwap | screener   |               3 |                      0 |              0 |        0 |         0 | False  |          0.423974 |
|      9 | reversal_vwap | screener   |               4 |                      0 |              0 |        0 |         0 | False  |          0.423974 |
|     10 | reversal_rsi  | screener   |               5 |                      0 |              0 |        0 |         0 | False  |          0.423974 |

## 합격 시나리오 수: 0

## 전략별 평균 지표

| strategy           |   avg_daily_return_pct |   win_rate_pct |    calmar |   mdd_pct |
|:-------------------|-----------------------:|---------------:|----------:|----------:|
| abcd_pattern       |               -5.77754 |              0 | -1.27497  |  -19.6174 |
| bull_flag          |              -11.7228  |              0 | -0.756417 |  -33.0661 |
| ma_trend           |               -5.44167 |              0 | -1.3447   |  -18.6072 |
| orb                |              -11.0241  |              0 | -0.786    |  -31.8068 |
| pullback           |               -5.27933 |              0 | -1.38317  |  -18.0831 |
| red_to_green       |                0       |              0 |  0        |    0      |
| reversal_rsi       |               -5.3248  |              0 | -1.3735   |  -18.2157 |
| reversal_vwap      |                0       |              0 |  0        |    0      |
| support_resistance |                0       |              0 |  0        |    0      |
| vwap_trade         |                0       |              0 |  0        |    0      |

## universe별 평균 지표

| universe   |   avg_daily_return_pct |   win_rate_pct |   calmar |   mdd_pct |
|:-----------|-----------------------:|---------------:|---------:|----------:|
| dynamic    |               -8.91404 |              0 | -1.38375 |  -27.8792 |
| screener   |                0       |              0 |  0       |    0      |