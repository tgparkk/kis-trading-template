# -*- coding: utf-8 -*-
"""네이버 금융 외국인 순매수 데이터 파싱 상세 테스트"""
import requests
from io import StringIO
import pandas as pd

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.naver.com/",
})

# 1. 종목별 외국인 순매수 일별 데이터
print("=== 삼성전자 외국인 순매수 일별 ===")
url = "https://finance.naver.com/item/frgn.naver"
params = {"code": "005930"}
r = session.get(url, params=params, timeout=10)
tables = pd.read_html(StringIO(r.text), encoding='utf-8')
print(f"Tables: {len(tables)}")
for i, t in enumerate(tables):
    print(f"\n--- Table {i}: shape={t.shape} ---")
    print(t.head(5).to_string())

print()
print("=== 시장별 일별 외국인 투자자 순매수 ===")
# sosok: 0=KOSPI, 1=KOSDAQ
for sosok, mkt in [("0", "KOSPI"), ("1", "KOSDAQ")]:
    url2 = "https://finance.naver.com/sise/investorDealTrendDay.naver"
    params2 = {"bizdate": "20240104", "sosok": sosok}
    r2 = session.get(url2, params=params2, timeout=10)
    print(f"\n{mkt}: Status={r2.status_code}, len={len(r2.content)}")
    print(r2.text)
