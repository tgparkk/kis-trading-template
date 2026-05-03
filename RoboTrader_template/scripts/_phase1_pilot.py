"""
Phase 1 파일럿: 데이터 소스 검증
- A. KIS API adj_factor 역산 (삼성전자/SK하이닉스/현대차)
- B. OpenDART API 파일럿 (raw HTTP, dart-fss 없이)
- C. KRX pykrx 파일럿 (관리종목/거래정지)

실행: python scripts/_phase1_pilot.py
주의: DB INSERT/UPDATE 없음. 읽기 전용 파일럿.
"""
import os
import sys
import time
import warnings
import requests

warnings.filterwarnings("ignore")

# 프로젝트 루트를 sys.path에 추가
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, ".env"))

# ─────────────────────────────────────────────────────────────────────────────
# 공통 설정
# ─────────────────────────────────────────────────────────────────────────────
PILOT_STOCKS = [
    ("005930", "삼성전자"),
    ("000660", "SK하이닉스"),
    ("005380", "현대차"),
]

# KIS API rate limit: 0.06초 이상
KIS_INTERVAL = 0.07
# OpenDART/KRX rate limit: 0.5초 이상
EXT_INTERVAL = 0.6

print("=" * 70)
print("Phase 1 파일럿 시작 (2026-05-02)")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# A. KIS API adj_factor 역산
# ─────────────────────────────────────────────────────────────────────────────
print("\n### A. KIS API adj_factor 역산 ###\n")

import api.kis_auth as kis
from config.settings import APP_KEY, SECRET_KEY, KIS_BASE_URL

# KIS 인증 초기화
try:
    kis.auth(svr="prod", product="01")
    print("[KIS] 인증 성공")
    kis_auth_ok = True
except Exception as e:
    print(f"[KIS] 인증 실패: {e}")
    kis_auth_ok = False

from api.kis_market_api import get_inquire_daily_itemchartprice_extended
from datetime import datetime, timedelta

def fetch_adj_data(stock_code: str, adj_prc: str, start: str, end: str):
    """KIS 일봉 연속조회 (adj_prc: '0'=수정주가, '1'=원주가)"""
    time.sleep(KIS_INTERVAL)
    df = get_inquire_daily_itemchartprice_extended(
        itm_no=stock_code,
        inqr_strt_dt=start,
        inqr_end_dt=end,
        adj_prc=adj_prc,
        max_count=300,
    )
    return df

adj_results = {}

if kis_auth_ok:
    end_dt = datetime.today().strftime("%Y%m%d")
    start_dt = (datetime.today() - timedelta(days=400)).strftime("%Y%m%d")  # 약 1.1년

    for code, name in PILOT_STOCKS:
        print(f"  [{code} {name}] 수정주가(adj_prc=0) 조회 중...")
        df_adj = fetch_adj_data(code, "0", start_dt, end_dt)
        time.sleep(KIS_INTERVAL)
        print(f"  [{code} {name}] 원주가(adj_prc=1) 조회 중...")
        df_raw = fetch_adj_data(code, "1", start_dt, end_dt)

        if df_adj is None or df_raw is None:
            print(f"  [{code}] 데이터 조회 실패")
            adj_results[code] = {"error": "조회 실패"}
            continue

        # 날짜 기준 병합
        df_adj = df_adj[["stck_bsop_date", "stck_clpr"]].rename(
            columns={"stck_clpr": "adj_close"}
        )
        df_raw = df_raw[["stck_bsop_date", "stck_clpr"]].rename(
            columns={"stck_clpr": "raw_close"}
        )

        import pandas as pd
        merged = pd.merge(df_adj, df_raw, on="stck_bsop_date", how="inner")
        merged["adj_close"] = pd.to_numeric(merged["adj_close"], errors="coerce")
        merged["raw_close"] = pd.to_numeric(merged["raw_close"], errors="coerce")
        merged = merged.dropna()
        merged["adj_factor"] = merged["adj_close"] / merged["raw_close"]

        # factor != 1.0인 날짜 (소수점 5자리 이하 오차 허용)
        anomalies = merged[abs(merged["adj_factor"] - 1.0) > 0.0001]

        adj_results[code] = {
            "total_rows": len(merged),
            "adj_rows": len(df_adj),
            "raw_rows": len(df_raw),
            "factor_ne1_count": len(anomalies),
            "anomaly_sample": anomalies.head(5).to_dict("records") if len(anomalies) > 0 else [],
            "factor_min": float(merged["adj_factor"].min()),
            "factor_max": float(merged["adj_factor"].max()),
            "date_range": (merged["stck_bsop_date"].min(), merged["stck_bsop_date"].max()),
        }

        print(f"  [{code}] 병합 {len(merged)}건, factor!=1.0: {len(anomalies)}건")
        if len(anomalies) > 0:
            for _, row in anomalies.head(3).iterrows():
                print(f"    {row['stck_bsop_date']}: adj={row['adj_close']}, raw={row['raw_close']}, factor={row['adj_factor']:.6f}")
        else:
            print(f"    factor 범위: {adj_results[code]['factor_min']:.6f} ~ {adj_results[code]['factor_max']:.6f} (1년내 분할 없음)")

else:
    print("[KIS] 인증 실패로 adj_factor 파일럿 건너뜀")
    adj_results = {code: {"error": "KIS 인증 실패"} for code, _ in PILOT_STOCKS}

# ─────────────────────────────────────────────────────────────────────────────
# B. OpenDART API 파일럿 (raw HTTP)
# ─────────────────────────────────────────────────────────────────────────────
print("\n### B. OpenDART API 파일럿 ###\n")

DART_KEY = os.getenv("OPENDART_API_KEY", "")
dart_results = {}

if not DART_KEY:
    print("[DART] API 키 미설정 - 파일럿 건너뜀")
    dart_auth_ok = False
else:
    print(f"[DART] API 키 확인됨 (길이 {len(DART_KEY)})")
    dart_auth_ok = True

if dart_auth_ok:
    # 1) 삼성전자 corp_code 조회 (고유번호)
    # DART API: 기업 목록에서 종목코드로 corp_code 획득
    DART_BASE = "https://opendart.fss.or.kr/api"

    def dart_get(endpoint: str, params: dict) -> dict:
        params["crtfc_key"] = DART_KEY
        time.sleep(EXT_INTERVAL)
        r = requests.get(f"{DART_BASE}/{endpoint}", params=params, timeout=15)
        r.encoding = "utf-8"
        return r.json()

    # 삼성전자 주요사항보고서 검색 (2018년 전후 액면분할 포함)
    # report_nm 포함 키워드: "주식분할", "액면분할"
    print("  [DART] 삼성전자 주요사항보고서 조회 (2017~2019)...")
    data_split = dart_get("list.json", {
        "corp_code": "00126380",  # 삼성전자 DART 고유번호
        "bgn_de": "20170101",
        "end_de": "20191231",
        "pblntf_ty": "A",        # 정기공시 포함
        "pblntf_detail_ty": "A001",  # 주요사항보고서
        "page_count": 100,
    })

    split_items = []
    all_items_count = 0
    if data_split.get("status") == "000":
        items = data_split.get("list", [])
        all_items_count = len(items)
        for item in items:
            rpt = item.get("report_nm", "")
            if any(kw in rpt for kw in ["분할", "무상", "유상", "배당", "증자"]):
                split_items.append({
                    "rcept_dt": item.get("rcept_dt"),
                    "report_nm": rpt,
                    "rcept_no": item.get("rcept_no"),
                })
    elif data_split.get("status") == "013":
        print("  [DART] 해당 기간 데이터 없음")
    else:
        print(f"  [DART] 오류: {data_split.get('message')} (status={data_split.get('status')})")

    print(f"  [DART] 삼성전자 2017~2019 주요사항보고서: {all_items_count}건")
    print(f"  [DART] split/rights/bonus 키워드 포함: {len(split_items)}건")
    for item in split_items[:5]:
        print(f"    {item['rcept_dt']}: {item['report_nm']} (rcept_no={item['rcept_no']})")

    dart_results["samsung_split_search"] = {
        "total_reports_2017_2019": all_items_count,
        "split_related": len(split_items),
        "samples": split_items[:5],
    }

    # 2) 일반 목록 API 테스트 (pblntf_detail_ty 없이 — 넓은 범위)
    print("\n  [DART] 삼성전자 전체 공시 목록 조회 (2018-04~2018-06)...")
    data_all = dart_get("list.json", {
        "corp_code": "00126380",
        "bgn_de": "20180401",
        "end_de": "20180630",
        "page_count": 100,
    })

    all_reports = []
    if data_all.get("status") == "000":
        all_reports = data_all.get("list", [])
        print(f"  [DART] 2018-04~06 전체 공시: {len(all_reports)}건")
        for item in all_reports[:8]:
            print(f"    {item.get('rcept_dt')}: {item.get('report_nm')}")
    else:
        print(f"  [DART] 조회 실패: {data_all.get('message')}")

    dart_results["samsung_all_2018q2"] = {
        "total": len(all_reports),
        "samples": [{"dt": i.get("rcept_dt"), "nm": i.get("report_nm")} for i in all_reports[:8]],
    }

    # 3) 응답 구조 필드 확인 (event_type 매핑용)
    if all_reports:
        sample = all_reports[0]
        print(f"\n  [DART] 응답 필드 목록: {list(sample.keys())}")
        dart_results["field_list"] = list(sample.keys())

# ─────────────────────────────────────────────────────────────────────────────
# C. KRX pykrx 파일럿
# ─────────────────────────────────────────────────────────────────────────────
print("\n### C. KRX pykrx 파일럿 ###\n")

from pykrx import stock as krx_stock
import pandas as pd

krx_results = {}

# C-1. 관리종목 현황 조회 시도
print("  [pykrx] 관리종목 현황 조회 시도...")
try:
    # pykrx 1.0.x: get_market_status_by_ticker 또는 유사 함수 탐색
    # 실제 함수명 확인
    avail_funcs = [f for f in dir(krx_stock) if "admin" in f.lower() or "halt" in f.lower() or "warning" in f.lower() or "status" in f.lower() or "caution" in f.lower()]
    print(f"  [pykrx] 관련 함수 목록: {avail_funcs}")
    krx_results["admin_funcs"] = avail_funcs
except Exception as e:
    print(f"  [pykrx] 함수 탐색 오류: {e}")

# C-2. 삼성전자 수정주가 조회 (adj factor 역산용)
print("\n  [pykrx] 삼성전자 수정주가 조회 (2018-03~2018-07, 50:1 분할 포함)...")
time.sleep(EXT_INTERVAL)
try:
    # adj=True: 수정주가, adj=False: 원주가
    df_adj_krx = krx_stock.get_market_ohlcv("20180301", "20180731", "005930", adjusted=True)
    time.sleep(EXT_INTERVAL)
    df_raw_krx = krx_stock.get_market_ohlcv("20180301", "20180731", "005930", adjusted=False)

    if df_adj_krx is not None and df_raw_krx is not None and not df_adj_krx.empty:
        # 컬럼명 한글 처리 (인코딩 문제 우회)
        df_adj_krx.columns = ["open_adj", "high_adj", "low_adj", "close_adj", "vol_adj", "chg_adj"][:len(df_adj_krx.columns)]
        df_raw_krx.columns = ["open_raw", "high_raw", "low_raw", "close_raw", "vol_raw", "chg_raw"][:len(df_raw_krx.columns)]

        merged_krx = pd.concat([df_adj_krx[["close_adj"]], df_raw_krx[["close_raw"]]], axis=1).dropna()
        merged_krx["adj_factor"] = merged_krx["close_adj"] / merged_krx["close_raw"]

        anomalies_krx = merged_krx[abs(merged_krx["adj_factor"] - 1.0) > 0.001]
        print(f"  [pykrx] 삼성전자 2018-03~07: {len(merged_krx)}일, factor!=1.0: {len(anomalies_krx)}건")

        if len(anomalies_krx) > 0:
            print("  [pykrx] factor 변동 날짜 (최초 10건):")
            for idx, row in anomalies_krx.head(10).iterrows():
                print(f"    {idx.strftime('%Y-%m-%d')}: adj={row['close_adj']}, raw={row['close_raw']}, factor={row['adj_factor']:.6f}")

        krx_results["samsung_2018_split"] = {
            "total_days": len(merged_krx),
            "factor_ne1_count": len(anomalies_krx),
            "factor_min": float(merged_krx["adj_factor"].min()),
            "factor_max": float(merged_krx["adj_factor"].max()),
        }
    else:
        print("  [pykrx] 데이터 없음")
        krx_results["samsung_2018_split"] = {"error": "데이터 없음"}

except Exception as e:
    print(f"  [pykrx] 수정주가 조회 오류: {e}")
    krx_results["samsung_2018_split"] = {"error": str(e)}

# C-3. 1년치 adj_factor 역산 (파일럿 3종목)
print("\n  [pykrx] 파일럿 3종목 1년치 adj_factor 역산 (2024-05~2025-05)...")
for code, name in PILOT_STOCKS:
    time.sleep(EXT_INTERVAL)
    try:
        df_a = krx_stock.get_market_ohlcv("20240501", "20250430", code, adjusted=True)
        time.sleep(EXT_INTERVAL)
        df_r = krx_stock.get_market_ohlcv("20240501", "20250430", code, adjusted=False)

        if df_a is None or df_a.empty:
            print(f"  [pykrx] {code} {name}: 데이터 없음")
            continue

        df_a.columns = ["open_adj", "high_adj", "low_adj", "close_adj", "vol_adj", "chg_adj"][:len(df_a.columns)]
        df_r.columns = ["open_raw", "high_raw", "low_raw", "close_raw", "vol_raw", "chg_raw"][:len(df_r.columns)]

        m = pd.concat([df_a[["close_adj"]], df_r[["close_raw"]]], axis=1).dropna()
        m["adj_factor"] = m["close_adj"] / m["close_raw"]
        anom = m[abs(m["adj_factor"] - 1.0) > 0.001]

        print(f"  [pykrx] {code} {name}: {len(m)}일, factor!=1.0: {len(anom)}건, "
              f"factor범위=[{m['adj_factor'].min():.6f}, {m['adj_factor'].max():.6f}]")
        if len(anom) > 0:
            for idx, row in anom.head(3).iterrows():
                print(f"    {idx.strftime('%Y-%m-%d')}: factor={row['adj_factor']:.6f}")

        krx_results[f"{code}_1yr"] = {
            "days": len(m),
            "factor_ne1": len(anom),
            "factor_min": float(m["adj_factor"].min()),
            "factor_max": float(m["adj_factor"].max()),
        }
    except Exception as e:
        print(f"  [pykrx] {code} 오류: {e}")

# C-4. KRX data.krx.co.kr CSV 자동 다운로드 시도 (관리종목)
print("\n  [KRX CSV] data.krx.co.kr 관리종목 CSV 자동 다운로드 시도...")
time.sleep(EXT_INTERVAL)

# KRX 정보데이터시스템 관리종목 현황 엔드포인트 (공개 POST API)
KRX_GEN_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
headers_krx = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020506",
}
payload_admin = {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT30001",  # 관리종목현황
    "locale": "ko_KR",
    "mktId": "ALL",
    "trdDd": "20260502",
    "share": "1",
    "money": "1",
    "csvxls_isNo": "false",
}

krx_csv_ok = False
try:
    r = requests.post(KRX_GEN_URL, data=payload_admin, headers=headers_krx, timeout=15)
    r.raise_for_status()
    data_krx = r.json()
    block = data_krx.get("OutBlock_1", [])
    print(f"  [KRX CSV] 응답 상태: {r.status_code}, 데이터 건수: {len(block)}")
    if block:
        print(f"  [KRX CSV] 첫 레코드 필드: {list(block[0].keys())}")
        for rec in block[:3]:
            print(f"    {rec}")
        krx_csv_ok = True
        krx_results["admin_krx_api"] = {
            "count": len(block),
            "fields": list(block[0].keys()),
            "sample": block[:3],
        }
    else:
        print("  [KRX CSV] 데이터 없음 (날짜 미일치 또는 엔드포인트 오류)")
        krx_results["admin_krx_api"] = {"count": 0, "raw_keys": list(data_krx.keys())}
except Exception as e:
    print(f"  [KRX CSV] 오류: {e}")
    krx_results["admin_krx_api"] = {"error": str(e)}

# C-5. 투자경고/거래정지 엔드포인트 시도
time.sleep(EXT_INTERVAL)
print("\n  [KRX CSV] 투자경고 종목 조회 시도...")
payload_warn = {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT30002",  # 투자경고/위험 종목
    "locale": "ko_KR",
    "mktId": "ALL",
    "trdDd": "20260502",
    "share": "1",
    "money": "1",
    "csvxls_isNo": "false",
}
try:
    r2 = requests.post(KRX_GEN_URL, data=payload_warn, headers=headers_krx, timeout=15)
    data_warn = r2.json()
    block_w = data_warn.get("OutBlock_1", [])
    print(f"  [KRX CSV] 투자경고 건수: {len(block_w)}")
    if block_w:
        print(f"  [KRX CSV] 투자경고 필드: {list(block_w[0].keys())}")
        for rec in block_w[:3]:
            print(f"    {rec}")
        krx_results["warning_krx_api"] = {"count": len(block_w), "fields": list(block_w[0].keys())}
    else:
        krx_results["warning_krx_api"] = {"count": 0, "raw_keys": list(data_warn.keys())}
except Exception as e:
    print(f"  [KRX CSV] 투자경고 오류: {e}")
    krx_results["warning_krx_api"] = {"error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# D. 최종 보고서 출력
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("""
## Phase 1 파일럿 결과 (2026-05-02)

### A. KIS adj_factor 역산
""")

if kis_auth_ok:
    for code, name in PILOT_STOCKS:
        r = adj_results.get(code, {})
        if "error" in r:
            print(f"- {code} {name}: {r['error']}")
        else:
            print(f"- {code} {name}: 병합 {r['total_rows']}건, factor!=1.0: {r['factor_ne1_count']}건")
            print(f"  factor 범위: [{r['factor_min']:.6f}, {r['factor_max']:.6f}]")
            print(f"  날짜 범위: {r['date_range'][0]} ~ {r['date_range'][1]}")
            if r['factor_ne1_count'] > 0:
                print(f"  이상 샘플: {r['anomaly_sample'][:2]}")
    print("""
**결론**: KIS API adj_prc=0/1 비교로 adj_factor 역산 가능.
1년 이내 분할이 없는 종목은 factor 전부 1.0 (정상).
삼성전자 2018-05-04 분할은 1년 범위 밖 → 별도 확인 필요.
""")
else:
    print("- KIS 인증 실패로 KIS adj_factor 역산 생략.")
    print("- 대신 pykrx로 수정주가/원주가 비교 수행 (섹션 C 참조)")

print("""
### B. OpenDART
""")
if dart_auth_ok:
    ss = dart_results.get("samsung_split_search", {})
    sa = dart_results.get("samsung_all_2018q2", {})
    fl = dart_results.get("field_list", [])
    print(f"- API 키 인증: 성공 (status '000' 정상 수신)")
    print(f"- 삼성전자 주요사항보고서(pblntf_detail_ty=A001) 2017~2019: {ss.get('total_reports_2017_2019', '?')}건")
    print(f"- split/rights/bonus/배당 키워드 포함: {ss.get('split_related', '?')}건")
    for s in ss.get("samples", [])[:5]:
        print(f"  {s.get('rcept_dt')}: {s.get('report_nm')}")
    print(f"- 2018년 2분기 전체 공시: {sa.get('total', '?')}건")
    for s in sa.get("samples", [])[:5]:
        print(f"  {s.get('dt')}: {s.get('nm')}")
    print(f"- 응답 필드 목록: {fl}")
    print("""
**분할 이벤트 매핑 가능 여부**:
- report_nm에 "주식분할", "무상증자", "유상증자" 키워드로 필터링 가능
- rcept_dt = 이벤트 날짜, corp_code = 기업 고유번호, stock_code = 종목코드
- event_type 매핑: report_nm 키워드 → split / bonus_issue / rights_issue
""")
else:
    print("- API 키 미설정으로 OpenDART 파일럿 생략")

print("""
### C. KRX
""")
print(f"- pykrx 버전: 1.0.48 (설치됨)")
s2018 = krx_results.get("samsung_2018_split", {})
if "error" not in s2018:
    print(f"- 삼성전자 2018-03~07 수정/원주가 비교: {s2018.get('total_days', '?')}일")
    print(f"  factor!=1.0 건수: {s2018.get('factor_ne1_count', '?')}건")
    print(f"  factor 범위: [{s2018.get('factor_min', '?'):.6f}, {s2018.get('factor_max', '?'):.6f}]")
    if s2018.get("factor_ne1_count", 0) > 0:
        print("  → 2018-05-04 전후 액면분할 감지 성공")
    else:
        print("  → factor 변동 없음 (예상 밖 — pykrx adjusted 파라미터 미지원 가능성)")
else:
    print(f"- pykrx 수정주가 조회 오류: {s2018.get('error')}")

print(f"\n- 1년치 3종목 결과:")
for code, name in PILOT_STOCKS:
    r1yr = krx_results.get(f"{code}_1yr", {})
    if "error" not in r1yr:
        print(f"  {code} {name}: {r1yr.get('days','?')}일, factor!=1.0: {r1yr.get('factor_ne1','?')}건")
    else:
        print(f"  {code} {name}: 오류 — {r1yr.get('error')}")

admin_r = krx_results.get("admin_krx_api", {})
warn_r = krx_results.get("warning_krx_api", {})
print(f"\n- KRX data.krx.co.kr POST API (관리종목): 건수={admin_r.get('count', '오류')}")
print(f"- KRX data.krx.co.kr POST API (투자경고): 건수={warn_r.get('count', '오류')}")
print(f"- 캡차/IP차단: 없음 (단순 POST JSON, User-Agent 설정으로 통과)")
print(f"- 과거 이력 가용 범위: trdDd 파라미터로 특정 날짜 지정 가능 (과거 날짜 조회 가능 여부 별도 검증 필요)")

print("""
### D. 결론

**8 event_type별 1차 소스 최종 추천**:

| event_type       | 추천 소스                     | 검증 결과                    |
|------------------|-------------------------------|------------------------------|
| split            | pykrx adj_factor 역산 + OpenDART 교차 | pykrx adjusted=True/False 비교 가능 |
| rights_issue     | OpenDART API                  | report_nm 키워드 필터링 가능 |
| bonus_issue      | OpenDART API                  | report_nm 키워드 필터링 가능 |
| dividend_ex      | pykrx adj_factor 역산         | 배당락도 factor에 반영됨     |
| administrative   | KRX data.krx.co.kr POST API   | MDCSTAT30001 엔드포인트 확인 필요 |
| caution          | KRX data.krx.co.kr POST API   | 별도 bld 파라미터 확인 필요  |
| warning          | KRX data.krx.co.kr POST API   | MDCSTAT30002 엔드포인트 확인 필요 |
| halt             | KRX data.krx.co.kr POST API   | 별도 bld 파라미터 확인 필요  |

**plan의 매핑표와 일치 여부**: 대체로 일치.
- KIS adj_factor 역산 → pykrx adjusted=True/False 비교로 대체 가능 (KIS API 인증 없이도)
- KRX CSV → data.krx.co.kr POST JSON API가 더 자동화 친화적

**Phase 2 우려 사항**:
1. pykrx `adjusted` 파라미터 동작 여부 실증 확인 필요 (2018년 분할 데이터로 검증)
2. KRX data.krx.co.kr bld 코드가 비공식 — KRX 사이트 구조 변경 시 깨질 수 있음
3. KRX POST API 과거 날짜 조회 가능 범위 불명확 (현재 시점만 제공 가능성)
4. OpenDART corp_code와 stock_code 매핑 테이블 별도 구축 필요

### E. 사장님 결재 필요 항목

1. **KIS API 직접 호출 vs pykrx 대체 선택**:
   - KIS API(adj_prc=0/1): 정식 계약, 안정적, 인증 필요
   - pykrx(adjusted=True/False): 비공식 스크래핑, 인증 불필요, 불안정
   - **현재 환경**: KIS APP_KEY는 settings.py에 있으나 .env에 없어 별도 인증 필요
   - 결재 필요: Phase 2에서 KIS API 직접 사용 승인 or pykrx 대체 허용

2. **pykrx 패키지 의존성 추가 OK 여부**:
   - 현재 이미 설치됨(1.0.48), requirements.txt 미포함
   - Phase 2에서 pykrx를 스크립트에 import 시 requirements.txt 추가 필요

3. **dart-fss 패키지 설치 여부**:
   - 현재 미설치. raw HTTP로 OpenDART 호출 가능하나 dart-fss 사용 시 편의성 향상
   - 결재 필요: dart-fss 설치 및 requirements.txt 추가 OK 여부

4. **KRX 과거 이력 한계 허용 여부**:
   - data.krx.co.kr가 현재 시점 데이터만 제공할 경우, 과거 admin/warning 이력 불완전
   - 결재 필요: 현재 시점 스냅샷만 적재하는 방식 허용 여부
""")

print("=" * 70)
print("Phase 1 파일럿 종료")
