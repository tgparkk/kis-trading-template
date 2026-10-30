# lots_features.csv 열 사전 (1행 = 청산 로트 1 = SELL 1 ↔ BUY(buy_record_id) 1 · 1,273행 · UTF-8 BOM)

- 출처: `virtual_trading_records`(is_test) · `daily_prices`(2026-04-20~10-30) · `screener_snapshots` · `stock_info` — DB `kis_template` SELECT 만(`build_features.py`).
- 시각은 전부 KST(`timestamp at time zone 'Asia/Seoul'`). D-1 = 매수일 직전 거래일(KOSPI 의사티커 일봉 달력). d0 = 매수일.
- 🔴 «특징»(F열)은 전부 매수 시각 이전 값. «결과»·«해석용» 열은 특징으로 쓰지 않는다(누출 검사 결과 = `run_log.txt`).
- 수익·등락 단위 = % (0.05 가 아니라 5.0). 분위 = 그날 전 종목(의사티커 6 제외 · returns/변동성/거래대금은 volume>0 · 시총은 market_cap>0) 안 백분위 순위를 5등분, 1 = 낮음 · 5 = 높음.

## 로트 · 결과
| 열 | 뜻 |
|---|---|
| sell_id · buy_id | vtr id(SELL · BUY) |
| strategy · strat | 전략 원명 · 약칭(ma5 rs dt ma20 elder env minervini deep_mr) |
| stock_code | 종목 |
| buy_ts · buy_price · qty | 매수 시각 · 체결가 · 수량 |
| sell_ts · sell_price · sell_reason · sell_cat | 매도 시각 · 가격 · 사유 원문 · 분류(손절 = `손절%` · 익절 = `목표 익절%`/`익절%` · MA 이탈 = `MA20 이탈%`/`MA20×%` · trailing = 트레일링/EMA13/…trailing · EMA = EMA65 · 기간 = 보유기간/장기보유 · 기타) |
| profit_loss | gross 손익(원 · vtr 그대로) |
| buy_date · sell_date · d1_date | 매수일 · 매도일 · D-1 |
| gross_pct | profit_loss ÷ (buy_price × qty) × 100 |
| hold_hours · hold_tdays | 보유 시간(h) · 보유 거래일 수(매도일 순번 − 매수일 순번 · 당일 왕복 = 0) |
| y_loss | 결과 ① 패배 = profit_loss < 0 (0원 11건은 0) |
| y_stop | 결과 ② 손절 청산 = sell_reason 이 `손절` 로 시작 |
| mkt_med_pct | 같은 기간 전 종목 중앙값 수익률: 매수일≠매도일 → 매수일 close→매도일 close(양끝 volume>0 · close>0 · 의사티커 6 제외 = eq_median.py 규칙) · 당일 왕복 → 그날 returns_1d 중앙값(volume>0) |
| excess_pct | 결과 ③ 초과 = gross_pct − mkt_med_pct (%p) |
| excess_dm · loss_dm | 날 뺀 값 = excess_pct − 같은 매수일 로트 평균 · y_loss − 같은 매수일 평균 |
| kospi_d0_ret_pct | 해석용(급락일 표식 · 특징 아님): 매수일 KOSPI close/전일 close − 1 |

## 특징(F1~F15)
| F | 열 | 뜻 · 시점 |
|---|---|---|
| F1 | strat | 전략 |
| F2 | snap_rank · snap_n · snap_rank_pct · snap_created | `screener_snapshots` scan_date = D-1 · 같은 strategy · stock_code 의 rank_in_snapshot(최소) · 그날 그 전략 후보 수 · 순위÷후보 수 · 스냅샷 기록 시각(전부 매수 시각보다 앞 · 0건 위반). 없음 = NaN(4로트) |
| F3 | d1_market_cap · q_mcap | D-1 시가총액 · 그날 전 종목 5분위(Q5 대형) |
| F4 | d1_returns_1d · d1_returns_5d · d1_returns_20d · q_r1d · q_r5d · q_r20d | D-1 등락률(%) · 각 5분위 |
| F5 | d1_volatility_20d · q_vol20 | D-1 20일 변동성(%) · 5분위 |
| F6 | d1_close · d0_open · gap_pct | D-1 종가 · 당일 시가 · 갭 = d0_open/d1_close − 1(%) · 매수 시각 전부 ≥ 09:00:23 → 시가는 알려진 값 |
| F7 | px_vs_d1_pct | 매수 체결가/D-1 종가 − 1(%) |
| F8 | buy_hm | 매수 시각 HH:MM:SS(analyze.py 가 09:00~09:10 / 09:10~10:00 / 10:00~12:00 / 12:00~15:30 로 묶음) |
| F9 | idx_gap_pct | 종목 시장(stock_info.market)에 맞는 지수 의사티커(KOSPI·KOSDAQ) d0 open / D-1 close − 1(%) · 시장 모름 = NaN(179) · ② 장중 지수(분봉)는 `minute_candles` 에 지수 의사티커가 없어 없음 |
| F10 | d1_trading_value · q_tval | D-1 거래대금(원) · 5분위 |
| F11 | market · sector | stock_info 현재 스냅샷 시장 · 섹터(전부 NULL) · 시장 없음 = «없음» |
| F12 | rebuy · rebuy_prior · rebuy_same · rebuy_tdiff | 매수 전(SELL 시각 < 매수 시각) 같은 종목 SELL(어떤 전략이든)이 0~5거래일 안에 있으면 1 · 가장 최근 그 SELL 의 종류(익절/손절/이탈·기타) · 같은/다른 전략 · 거래일 차. 보고서 6장 정의와 같음(교차 = 10-23~10-30 BUY 36/98 일치) |
| F13 | cohold_other | 매수 시각에 다른 전략의 같은 종목 BUY 가 미청산(그 BUY 시각 < 매수 시각 · 그 SELL 없음 또는 SELL 시각 > 매수 시각)이면 1 |
| F14 | seq_day | 같은 날 같은 전략 BUY(미청산 로트 포함) 중 시각순 몇 번째(같은 시각 = id 순) |
| F15 | weekday · month | 매수일 요일(0 = 월) · 월 |
| 기타 | d1_volume · rebuy_prior 등 | 보조 |
