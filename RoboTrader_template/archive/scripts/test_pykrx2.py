# -*- coding: utf-8 -*-
"""pykrx KRX API 직접 호출 테스트"""
import requests

# KRX API 직접 호출 테스트
url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}
# 투자자별 거래실적 - 종목별
payload = {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT02301",
    "locale": "ko_KR",
    "trdDd": "20240104",
    "share": "1",
    "money": "1",
    "csvxls_isNo": "false",
}
print("=== KRX API 직접 호출 테스트 ===")
try:
    resp = requests.post(url, data=payload, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type')}")
    data = resp.json()
    print(f"Keys: {list(data.keys())[:5]}")
    if 'OutBlock_1' in data:
        print(f"OutBlock_1 len: {len(data['OutBlock_1'])}")
        print("First row:", data['OutBlock_1'][0] if data['OutBlock_1'] else "empty")
    else:
        print("Response keys:", list(data.keys()))
        print(str(data)[:500])
except Exception as e:
    print(f"Error: {e}")

# 외국인 일별 순매수 bld
print()
print("=== 외국인 순매수 종목별 (MDCSTAT02401) ===")
payload2 = {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT02401",
    "locale": "ko_KR",
    "inqTpCd": "2",    # 외국인
    "trdDd": "20240104",
    "share": "1",
    "money": "1",
    "csvxls_isNo": "false",
}
try:
    resp2 = requests.post(url, data=payload2, headers=headers, timeout=10)
    print(f"Status: {resp2.status_code}")
    data2 = resp2.json()
    print(f"Keys: {list(data2.keys())[:5]}")
    if 'OutBlock_1' in data2:
        print(f"OutBlock_1 len: {len(data2['OutBlock_1'])}")
        print("First row:", data2['OutBlock_1'][0] if data2['OutBlock_1'] else "empty")
    else:
        print(str(data2)[:500])
except Exception as e:
    print(f"Error: {e}")
