# -*- coding: utf-8 -*-
"""pykrx 외국인 순매수 API 테스트"""
from pykrx import stock
import pandas as pd

# 테스트 1: 외국인 KOSPI 종목별 순매수
print("=== 테스트 1: get_market_net_purchases_of_equities_by_ticker ===")
df = stock.get_market_net_purchases_of_equities_by_ticker('20240104', '20240108', 'KOSPI', '외국인')
print("shape:", df.shape)
print(df.head())
print("columns:", list(df.columns))

print()
print("=== 테스트 2: KOSDAQ ===")
df2 = stock.get_market_net_purchases_of_equities_by_ticker('20240104', '20240108', 'KOSDAQ', '외국인')
print("shape:", df2.shape)
print(df2.head())

print()
print("=== 테스트 3: get_market_trading_value_by_date ===")
import inspect
print(inspect.signature(stock.get_market_trading_value_by_date))
# 일별 시장 전체 거래대금
df3 = stock.get_market_trading_value_by_date('20240104', '20240108', '005930')
print("shape:", df3.shape)
print(df3.head())
print("columns:", list(df3.columns))
print("index:", df3.index.tolist())
