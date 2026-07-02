# -*- coding: utf-8 -*-
"""KRX API 직접 HTTP 호출 테스트 - 정확한 파라미터"""
import requests

url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020302",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Origin": "http://data.krx.co.kr",
    "X-Requested-With": "XMLHttpRequest",
}

# MDCSTAT02401 - 투자자별 순매수상위종목
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

print("=== MDCSTAT02401 (투자자별 순매수상위) ===")
try:
    resp = requests.post(url, data=payload, headers=headers, timeout=15)
    print(f"Status: {resp.status_code}")
    print(f"Content-Length: {len(resp.content)}")
    print(f"Content-Type: {resp.headers.get('Content-Type','')}")
    print(f"Response text (first 500): {resp.text[:500]}")
    if resp.status_code == 200 and resp.text.strip():
        data = resp.json()
        print("Keys:", list(data.keys()))
        for k, v in data.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
                if v: print("  first:", v[0])
except Exception as e:
    print(f"Error: {e}")

print()
# 다른 bld - 투자자별 거래실적 일별추이
payload2 = {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT02303",
    "locale": "ko_KR",
    "trdDd": "20240104",
    "share": "1",
    "money": "1",
    "csvxls_isNo": "false",
}
print("=== MDCSTAT02303 테스트 ===")
try:
    resp2 = requests.post(url, data=payload2, headers=headers, timeout=15)
    print(f"Status: {resp2.status_code}, Len: {len(resp2.content)}")
    print(f"Text: {resp2.text[:300]}")
except Exception as e:
    print(f"Error: {e}")
