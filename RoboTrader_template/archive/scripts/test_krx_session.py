# -*- coding: utf-8 -*-
"""KRX API - 세션 쿠키 획득 후 데이터 요청"""
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
})

# 1단계: 메인 페이지 접속해서 세션 쿠키 획득
print("=== Step 1: KRX 메인 페이지 접속 ===")
try:
    r = session.get("http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020302", timeout=15)
    print(f"Status: {r.status_code}")
    print(f"Cookies: {dict(session.cookies)}")
except Exception as e:
    print(f"Error: {e}")

# 2단계: 데이터 요청
print()
print("=== Step 2: MDCSTAT02401 데이터 요청 ===")
session.headers.update({
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020302",
    "X-Requested-With": "XMLHttpRequest",
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
try:
    r2 = session.post("http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd", data=payload, timeout=15)
    print(f"Status: {r2.status_code}")
    print(f"Content-Length: {len(r2.content)}")
    print(f"Text (first 500): {r2.text[:500]}")
    if r2.status_code == 200 and r2.text.strip() and r2.text.strip() != 'LOGOUT':
        data = r2.json()
        print("Keys:", list(data.keys()))
        for k, v in data.items():
            if isinstance(v, list) and v:
                print(f"  {k}[0]: {v[0]}")
except Exception as e:
    print(f"Error: {e}")
