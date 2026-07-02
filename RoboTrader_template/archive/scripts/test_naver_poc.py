# -*- coding: utf-8 -*-
"""네이버 frgn.naver PoC - 5종목, 속도/페이지 수 측정"""
import requests
import time
import pandas as pd
from io import StringIO

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
})

PILOT_CODES = ["005930", "000660", "005380", "035420", "051910"]

def fetch_foreign_naver(code: str, max_pages: int = 3) -> pd.DataFrame:
    """네이버 금융 외국인 순매수 데이터 수집 (종목별, 최대 N 페이지)"""
    all_rows = []
    for page in range(1, max_pages + 1):
        url = f"https://finance.naver.com/item/frgn.naver"
        params = {"code": code, "page": page}
        try:
            r = session.get(url, params=params, timeout=10)
            tables = pd.read_html(StringIO(r.text), encoding='utf-8')
            # Table 3 = 날짜별 외국인 순매수
            if len(tables) <= 3:
                break
            t = tables[3]
            # 멀티레벨 컬럼 처리
            if isinstance(t.columns, pd.MultiIndex):
                t.columns = ['_'.join(str(c) for c in col).strip('_') for col in t.columns]
            # 첫 행이 헤더 중복이면 제거
            t = t.dropna(how='all')
            # 날짜 컬럼 찾기
            date_col = [c for c in t.columns if '날짜' in str(c)]
            foreign_col = [c for c in t.columns if '외국인' in str(c) and '순매매' in str(c)]
            if not date_col or not foreign_col:
                # 컬럼명 직접 할당 시도
                if t.shape[1] >= 7:
                    t.columns = ['날짜','종가','전일비','등락률','거래량','기관_순매매량','외국인_순매매량','보유주수','보유율'][:t.shape[1]]
                    date_col = ['날짜']
                    foreign_col = ['외국인_순매매량']
                else:
                    print(f"  [{code}] p{page}: 컬럼 불명확 {list(t.columns)}")
                    break
            sub = t[[date_col[0], foreign_col[0]]].copy()
            sub.columns = ['date', 'foreign_net_vol']
            sub = sub.dropna(subset=['date'])
            sub = sub[sub['date'].astype(str).str.match(r'\d{4}\.\d{2}\.\d{2}')]
            all_rows.append(sub)
            if len(sub) < 10:  # 마지막 페이지
                break
            time.sleep(0.3)
        except Exception as e:
            print(f"  [{code}] p{page} Error: {e}")
            break
    if not all_rows:
        return pd.DataFrame(columns=['date', 'foreign_net_vol'])
    result = pd.concat(all_rows, ignore_index=True)
    return result

print("=== PoC: 5종목 외국인 순매수 수집 (페이지 3개씩) ===")
start = time.time()
for code in PILOT_CODES:
    t0 = time.time()
    df = fetch_foreign_naver(code, max_pages=3)
    elapsed = time.time() - t0
    print(f"  {code}: {len(df)}행, {elapsed:.1f}초")
    if not df.empty:
        print(f"    날짜범위: {df['date'].min()} ~ {df['date'].max()}")
        print(f"    샘플: {df.head(3).to_string(index=False)}")

total = time.time() - start
print(f"\n총 소요: {total:.1f}초 / 5종목 3페이지")
print(f"페이지당 약 20건이면 → 1종목 60건 = 약 3개월치")
print(f"5.4년치 = 페이지 약 33개 / 1종목 약 {33*0.3:.0f}초")
print(f"2600종목 전체 = 약 {2600*33*0.3/3600:.1f}시간 (너무 오래)")
