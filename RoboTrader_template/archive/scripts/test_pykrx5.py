# -*- coding: utf-8 -*-
"""pykrx 내부 클래스 직접 호출 테스트 - investor 코드 9000 사용"""
import sys
sys.path.insert(0, r"D:\GIT\kis-trading-template\RoboTrader_template")

from pykrx.website.krx.market.core import 투자자별_순매수상위종목
import pandas as pd

print("=== 투자자별_순매수상위종목 직접 호출 (외국인=9000) ===")
obj = 투자자별_순매수상위종목()
# strtDd, endDd, mktId (STK=KOSPI), invstTpCd (9000=외국인)
df = obj.fetch('20240104', '20240108', 'STK', 9000)
print("shape:", df.shape)
print(df.head())
print("columns:", list(df.columns))

print()
print("=== KOSDAQ (KSQ) ===")
df2 = obj.fetch('20240104', '20240108', 'KSQ', 9000)
print("shape:", df2.shape)
print(df2.head())
