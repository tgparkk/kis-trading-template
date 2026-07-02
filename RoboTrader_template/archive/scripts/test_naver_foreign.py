# -*- coding: utf-8 -*-
"""네이버 금융 투자자별 매매동향 API 테스트"""
import requests

# 네이버 금융 - 투자자별 매매동향 (외국인)
# https://finance.naver.com/sise/investorDealTrendDay.naver
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://finance.naver.com/",
})

print("=== 네이버 금융 투자자별 매매동향 (종목별) ===")
# 삼성전자 (005930) 외국인 매매동향
url = "https://finance.naver.com/item/frgn.naver"
params = {"code": "005930"}
try:
    r = session.get(url, params=params, timeout=10)
    print(f"Status: {r.status_code}, len={len(r.content)}")
    # HTML 파싱
    from io import StringIO
    import pandas as pd
    tables = pd.read_html(StringIO(r.text))
    print(f"Tables found: {len(tables)}")
    for i, t in enumerate(tables[:3]):
        print(f"  Table {i}: shape={t.shape}, cols={list(t.columns)[:5]}")
        print(f"    {t.head(3)}")
except Exception as e:
    print(f"Error: {e}")

print()
print("=== 네이버 금융 API 일별 외국인 순매수 ===")
# 일별 투자자 거래 현황 API
url2 = "https://finance.naver.com/sise/investorDealTrendDay.naver"
params2 = {"bizdate": "20240104", "sosok": "0"}  # sosok: 0=KOSPI
try:
    r2 = session.get(url2, params=params2, timeout=10)
    print(f"Status: {r2.status_code}, len={len(r2.content)}")
    print(f"Text (500): {r2.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

print()
print("=== pykrx stock.get_market_trading_value_and_volume_by_ticker ===")
try:
    from pykrx import stock
    import inspect
    print(inspect.signature(stock.get_market_trading_value_and_volume_by_ticker))
    # 이 함수는 종목별 투자자 거래량/대금 반환
    df = stock.get_market_trading_value_and_volume_by_ticker('20240104', '20240108', '005930')
    print("shape:", df.shape)
    print(df.head())
    print("columns:", list(df.columns))
except Exception as e:
    print(f"Error: {e}")
