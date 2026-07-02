# -*- coding: utf-8 -*-
"""FinanceDataReader 외국인 순매수 데이터 확인"""
import sys
sys.path.insert(0, r"D:\GIT\kis-trading-template\RoboTrader_template")

# 1. FinanceDataReader 테스트
print("=== FinanceDataReader 테스트 ===")
try:
    import FinanceDataReader as fdr
    # 삼성전자 일별 데이터
    df = fdr.DataReader('005930', '2024-01-04', '2024-01-10')
    print("shape:", df.shape)
    print("columns:", list(df.columns))
    print(df.head())
except Exception as e:
    print(f"FDR Error: {e}")

print()
# 2. KRX 세션 쿠키를 먼저 받아서 POST
print("=== KRX API 세션 방식 재시도 (다른 초기화 URL) ===")
import requests
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})
# KRX 첫 접속
try:
    r0 = session.get("http://data.krx.co.kr/", timeout=10)
    print(f"Root: {r0.status_code}, cookies: {dict(session.cookies)}")

    r1 = session.get(
        "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
        params={"menuId": "MDC0201020302"}, timeout=10)
    print(f"Menu: {r1.status_code}, cookies: {dict(session.cookies)}")

    session.headers.update({
        "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020302",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": "http://data.krx.co.kr",
    })

    payload = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT02401",
        "locale": "ko_KR",
        "strtDd": "20240104",
        "endDd": "20240108",
        "mktId": "STK",
        "invstTpCd": "9000",
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }
    r2 = session.post(
        "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
        data=payload, timeout=15)
    print(f"Data: {r2.status_code}, len={len(r2.content)}, text={r2.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
