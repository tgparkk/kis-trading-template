# Phase 2A: 국면별 Top 5 필터

## BULL_HIGH_VOL (n_cells=300, valid_n=5)
1. swing_lift=9.500 mid_lift=0.244 pos_lift=0.749 n=2012
   mcap_cutoff_top_n=1000 | min_trading_value=1000000000.0 | trading_value_lookback=60 | market=KOSPI | sector_exclude=financial+utility | min_price=1000 | min_liquidity_90d=0.8 | vol_quintile=5 | index_membership=all | candle_health=0.6 | candle_trend=nan
2. swing_lift=2.624 mid_lift=1.960 pos_lift=1.590 n=7888
   mcap_cutoff_top_n=500 | min_trading_value=5000000000.0 | trading_value_lookback=20 | market=KOSPI | sector_exclude=none | min_price=1000 | min_liquidity_90d=0.7 | vol_quintile=5 | index_membership=all | candle_health=0.4 | candle_trend=nan
3. swing_lift=1.820 mid_lift=0.362 pos_lift=1.006 n=8078
   mcap_cutoff_top_n=500 | min_trading_value=3000000000.0 | trading_value_lookback=20 | market=KOSPI | sector_exclude=none | min_price=1000 | min_liquidity_90d=0.9 | vol_quintile=0 | index_membership=all | candle_health=0.6 | candle_trend=nan
4. swing_lift=1.756 mid_lift=0.201 pos_lift=0.607 n=1148
   mcap_cutoff_top_n=1000 | min_trading_value=1000000000.0 | trading_value_lookback=20 | market=KOSDAQ | sector_exclude=none | min_price=1000 | min_liquidity_90d=0.8 | vol_quintile=2 | index_membership=all | candle_health=0.5 | candle_trend=4.0
5. swing_lift=1.641 mid_lift=0.167 pos_lift=0.762 n=8771
   mcap_cutoff_top_n=500 | min_trading_value=1000000000.0 | trading_value_lookback=20 | market=KOSPI | sector_exclude=utility | min_price=1000 | min_liquidity_90d=0.9 | vol_quintile=0 | index_membership=all | candle_health=0.6 | candle_trend=nan

## BULL_LOW_VOL (n_cells=300, valid_n=5)
1. swing_lift=2.814 mid_lift=3.294 pos_lift=2.245 n=1011
   mcap_cutoff_top_n=500 | min_trading_value=500000000.0 | trading_value_lookback=5 | market=KOSDAQ | sector_exclude=utility | min_price=5000 | min_liquidity_90d=0.7 | vol_quintile=5 | index_membership=all | candle_health=0.6 | candle_trend=4.0
2. swing_lift=2.698 mid_lift=2.163 pos_lift=2.027 n=1866
   mcap_cutoff_top_n=200 | min_trading_value=500000000.0 | trading_value_lookback=5 | market=KOSDAQ | sector_exclude=financial | min_price=1000 | min_liquidity_90d=0.7 | vol_quintile=0 | index_membership=all | candle_health=0.5 | candle_trend=4.0
3. swing_lift=2.532 mid_lift=3.954 pos_lift=1.906 n=1371
   mcap_cutoff_top_n=1000 | min_trading_value=10000000000.0 | trading_value_lookback=20 | market=KOSDAQ | sector_exclude=utility | min_price=5000 | min_liquidity_90d=0.7 | vol_quintile=5 | index_membership=all | candle_health=nan | candle_trend=4.0
4. swing_lift=2.188 mid_lift=1.962 pos_lift=2.537 n=1125
   mcap_cutoff_top_n=300 | min_trading_value=3000000000.0 | trading_value_lookback=20 | market=KOSDAQ | sector_exclude=utility | min_price=5000 | min_liquidity_90d=0.9 | vol_quintile=4 | index_membership=all | candle_health=nan | candle_trend=4.0
5. swing_lift=2.151 mid_lift=1.960 pos_lift=2.095 n=6500
   mcap_cutoff_top_n=2000 | min_trading_value=3000000000.0 | trading_value_lookback=60 | market=KOSDAQ | sector_exclude=utility | min_price=10000 | min_liquidity_90d=0.7 | vol_quintile=4 | index_membership=all | candle_health=0.5 | candle_trend=nan

## BEAR_HIGH_VOL (n_cells=300, valid_n=5)
1. swing_lift=1.983 mid_lift=1.009 pos_lift=1.601 n=1620
   mcap_cutoff_top_n=500 | min_trading_value=500000000.0 | trading_value_lookback=60 | market=both | sector_exclude=financial+utility | min_price=1000 | min_liquidity_90d=0.9 | vol_quintile=4 | index_membership=all | candle_health=0.6 | candle_trend=4.0
2. swing_lift=1.588 mid_lift=2.768 pos_lift=3.599 n=1214
   mcap_cutoff_top_n=2000 | min_trading_value=1000000000.0 | trading_value_lookback=60 | market=KOSPI | sector_exclude=none | min_price=10000 | min_liquidity_90d=0.7 | vol_quintile=4 | index_membership=all | candle_health=0.4 | candle_trend=5.0
3. swing_lift=1.492 mid_lift=1.349 pos_lift=2.702 n=3024
   mcap_cutoff_top_n=300 | min_trading_value=1000000000.0 | trading_value_lookback=5 | market=both | sector_exclude=financial | min_price=1000 | min_liquidity_90d=0.8 | vol_quintile=4 | index_membership=all | candle_health=0.4 | candle_trend=4.0
4. swing_lift=1.489 mid_lift=1.420 pos_lift=3.155 n=1079
   mcap_cutoff_top_n=200 | min_trading_value=1000000000.0 | trading_value_lookback=60 | market=KOSPI | sector_exclude=financial | min_price=5000 | min_liquidity_90d=0.9 | vol_quintile=4 | index_membership=all | candle_health=0.5 | candle_trend=4.0
5. swing_lift=1.409 mid_lift=1.425 pos_lift=2.493 n=1976
   mcap_cutoff_top_n=200 | min_trading_value=5000000000.0 | trading_value_lookback=60 | market=both | sector_exclude=none | min_price=1000 | min_liquidity_90d=0.9 | vol_quintile=4 | index_membership=all | candle_health=0.4 | candle_trend=4.0

## BEAR_LOW_VOL (n_cells=300, valid_n=5)
1. swing_lift=11.234 mid_lift=-0.592 pos_lift=1.170 n=1529
   mcap_cutoff_top_n=2000 | min_trading_value=1000000000.0 | trading_value_lookback=5 | market=both | sector_exclude=utility | min_price=1000 | min_liquidity_90d=0.7 | vol_quintile=2 | index_membership=all | candle_health=0.6 | candle_trend=5.0
2. swing_lift=11.112 mid_lift=-1.175 pos_lift=0.019 n=1087
   mcap_cutoff_top_n=2000 | min_trading_value=500000000.0 | trading_value_lookback=60 | market=KOSDAQ | sector_exclude=none | min_price=1000 | min_liquidity_90d=0.7 | vol_quintile=1 | index_membership=all | candle_health=0.6 | candle_trend=nan
3. swing_lift=5.855 mid_lift=0.200 pos_lift=0.811 n=1465
   mcap_cutoff_top_n=500 | min_trading_value=1000000000.0 | trading_value_lookback=20 | market=KOSPI | sector_exclude=financial+utility | min_price=5000 | min_liquidity_90d=0.9 | vol_quintile=4 | index_membership=all | candle_health=0.4 | candle_trend=4.0
4. swing_lift=5.702 mid_lift=0.900 pos_lift=1.203 n=1239
   mcap_cutoff_top_n=500 | min_trading_value=3000000000.0 | trading_value_lookback=20 | market=KOSPI | sector_exclude=none | min_price=1000 | min_liquidity_90d=0.7 | vol_quintile=4 | index_membership=all | candle_health=0.5 | candle_trend=4.0
5. swing_lift=4.741 mid_lift=0.898 pos_lift=1.168 n=1455
   mcap_cutoff_top_n=500 | min_trading_value=3000000000.0 | trading_value_lookback=60 | market=KOSPI | sector_exclude=financial | min_price=1000 | min_liquidity_90d=0.9 | vol_quintile=4 | index_membership=all | candle_health=0.4 | candle_trend=4.0

## SIDEWAYS_HIGH_VOL (n_cells=300, valid_n=5)
1. swing_lift=4.149 mid_lift=6.667 pos_lift=-2.690 n=1072
   mcap_cutoff_top_n=500 | min_trading_value=5000000000.0 | trading_value_lookback=5 | market=KOSDAQ | sector_exclude=utility | min_price=1000 | min_liquidity_90d=0.9 | vol_quintile=5 | index_membership=all | candle_health=nan | candle_trend=4.0
2. swing_lift=3.612 mid_lift=6.652 pos_lift=-2.709 n=1815
   mcap_cutoff_top_n=100 | min_trading_value=1000000000.0 | trading_value_lookback=60 | market=KOSDAQ | sector_exclude=none | min_price=10000 | min_liquidity_90d=0.7 | vol_quintile=5 | index_membership=all | candle_health=nan | candle_trend=nan
3. swing_lift=2.691 mid_lift=6.159 pos_lift=-2.602 n=6987
   mcap_cutoff_top_n=200 | min_trading_value=10000000000.0 | trading_value_lookback=5 | market=both | sector_exclude=financial+utility | min_price=1000 | min_liquidity_90d=0.8 | vol_quintile=5 | index_membership=all | candle_health=0.4 | candle_trend=nan
4. swing_lift=2.656 mid_lift=4.491 pos_lift=-2.971 n=39592
   mcap_cutoff_top_n=2000 | min_trading_value=3000000000.0 | trading_value_lookback=5 | market=KOSDAQ | sector_exclude=financial+utility | min_price=1000 | min_liquidity_90d=0.7 | vol_quintile=0 | index_membership=all | candle_health=nan | candle_trend=nan
5. swing_lift=2.633 mid_lift=3.714 pos_lift=-2.261 n=17931
   mcap_cutoff_top_n=1000 | min_trading_value=1000000000.0 | trading_value_lookback=60 | market=both | sector_exclude=utility | min_price=10000 | min_liquidity_90d=0.9 | vol_quintile=5 | index_membership=all | candle_health=0.4 | candle_trend=nan

## SIDEWAYS_LOW_VOL (n_cells=300, valid_n=5)
1. swing_lift=6.705 mid_lift=59.221 pos_lift=0.310 n=1155
   mcap_cutoff_top_n=1000 | min_trading_value=5000000000.0 | trading_value_lookback=20 | market=KOSDAQ | sector_exclude=financial+utility | min_price=5000 | min_liquidity_90d=0.9 | vol_quintile=2 | index_membership=all | candle_health=0.5 | candle_trend=nan
2. swing_lift=5.773 mid_lift=27.944 pos_lift=-1.135 n=1187
   mcap_cutoff_top_n=300 | min_trading_value=10000000000.0 | trading_value_lookback=5 | market=both | sector_exclude=none | min_price=10000 | min_liquidity_90d=0.8 | vol_quintile=5 | index_membership=all | candle_health=0.4 | candle_trend=5.0
3. swing_lift=5.325 mid_lift=22.122 pos_lift=-4.248 n=1272
   mcap_cutoff_top_n=2000 | min_trading_value=10000000000.0 | trading_value_lookback=20 | market=both | sector_exclude=utility | min_price=10000 | min_liquidity_90d=0.9 | vol_quintile=5 | index_membership=all | candle_health=nan | candle_trend=5.0
4. swing_lift=5.325 mid_lift=94.301 pos_lift=-5.983 n=10471
   mcap_cutoff_top_n=100 | min_trading_value=1000000000.0 | trading_value_lookback=5 | market=KOSDAQ | sector_exclude=none | min_price=1000 | min_liquidity_90d=0.9 | vol_quintile=5 | index_membership=all | candle_health=nan | candle_trend=nan
5. swing_lift=5.068 mid_lift=20.305 pos_lift=-1.089 n=1493
   mcap_cutoff_top_n=500 | min_trading_value=3000000000.0 | trading_value_lookback=20 | market=KOSDAQ | sector_exclude=financial | min_price=5000 | min_liquidity_90d=0.9 | vol_quintile=4 | index_membership=all | candle_health=0.6 | candle_trend=4.0
