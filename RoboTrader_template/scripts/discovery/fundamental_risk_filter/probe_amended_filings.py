"""F1 판정 — fnlttSinglAcntAll 이 「as-filed」인가 「as-last-amended」인가.

설계 스펙 §2.2 의 대전제를 검증한다. 전제가 틀리면 이 파이프라인이 만드는
테이블은 `_asfiled` 라는 이름으로 정정 오염을 그대로 담게 되고, 그건 우리가
quant_financial_ratio 를 기각한 바로 그 이유다.

판정 방법:
  1) list.json 으로 사업보고서(A001) 목록을 받아 「정정」이 붙은 건을 찾는다
     → 같은 bsns_year 에 원본 rcept_no 와 정정 rcept_no 가 둘 다 있는 케이스
  2) fnlttSinglAcntAll 을 그 bsns_year 로 부르고 돌아온 rcept_no 를 본다
     - 정정본의 rcept_no  → 값과 날짜가 «함께» 움직인다 = 안전
     - 원본의 rcept_no    → 정정된 값이 원본 날짜로 붙는다 = 치명적

읽기 전용. DB 쓰기 없음. 호출 수를 최소로 유지한다.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "discovery", "fundamental_risk_filter"))

import requests  # noqa: E402

from dart_client import DART_BASE, db_conn, load_dart_key  # noqa: E402

KEY = load_dart_key()
if not KEY:
    print("OPENDART_API_KEY 없음 — 중단")
    sys.exit(1)

S = requests.Session()
CALLS = [0]


def get(path, **params):
    time.sleep(0.34)
    params["crtfc_key"] = KEY
    r = S.get(f"{DART_BASE}/{path}", params=params, timeout=30)
    CALLS[0] += 1
    return r.json()


def corp_codes(n):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_code, corp_code, stock_name FROM stock_industry "
        "WHERE corp_code IS NOT NULL AND corp_code <> '' "
        "ORDER BY stock_code LIMIT %s", (n,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def main():
    found = []
    for stock, corp, name in corp_codes(40):
        js = get("list.json", corp_code=corp, bgn_de="20200101", end_de="20251231",
                 pblntf_detail_ty="A001", page_count=100)
        if js.get("status") != "000":
            continue
        items = js.get("list") or []
        amended = [i for i in items if "정정" in str(i.get("report_nm", ""))]
        if not amended:
            continue
        for a in amended:
            nm = a["report_nm"]
            # 「사업보고서 (2021.12)」 형태에서 연도 추출
            year = None
            for tok in nm.replace("(", " ").replace(")", " ").replace(".", " ").split():
                if tok.isdigit() and len(tok) == 4 and tok.startswith("20"):
                    year = tok
                    break
            if not year:
                continue
            originals = [i for i in items
                         if year in str(i.get("report_nm", ""))
                         and "정정" not in str(i.get("report_nm", ""))]
            if not originals:
                continue
            found.append({
                "stock": stock, "name": name, "corp": corp, "year": year,
                "amended_no": a["rcept_no"], "amended_dt": a["rcept_dt"],
                "amended_nm": nm,
                "orig_no": originals[0]["rcept_no"],
                "orig_dt": originals[0]["rcept_dt"],
                "orig_nm": originals[0]["report_nm"],
            })
            break
        if len(found) >= 3:
            break

    if not found:
        print(f"정정 사업보고서를 상위 40종목에서 못 찾음 (호출 {CALLS[0]}). "
              "표본을 넓혀야 한다.")
        return

    print(f"=== 정정 사례 {len(found)}건 발견 (호출 {CALLS[0]}) ===\n")
    for f in found:
        print(f"[{f['stock']} {f['name']}] 사업연도 {f['year']}")
        print(f"  원본 : {f['orig_no']}  접수 {f['orig_dt']}  {f['orig_nm'].strip()}")
        print(f"  정정 : {f['amended_no']}  접수 {f['amended_dt']}  {f['amended_nm'].strip()}")

        js = get("fnlttSinglAcntAll.json", corp_code=f["corp"], bsns_year=f["year"],
                 reprt_code="11011", fs_div="CFS")
        if js.get("status") != "000":
            js = get("fnlttSinglAcntAll.json", corp_code=f["corp"], bsns_year=f["year"],
                     reprt_code="11011", fs_div="OFS")
        rows = js.get("list") or []
        if not rows:
            print(f"  fnltt: status={js.get('status')} — 데이터 없음\n")
            continue
        got = str(rows[0].get("rcept_no") or "")
        if got == f["amended_no"]:
            verdict = "정정본 → 값과 날짜가 «함께» 움직인다 = 안전"
        elif got == f["orig_no"]:
            verdict = "🔴 원본 → 정정된 값이 원본 날짜로 붙는다 = 치명적"
        else:
            verdict = "제3의 접수번호 — 추가 조사 필요"
        print(f"  fnltt 반환 rcept_no: {got}")
        print(f"  ⇒ {verdict}\n")

    print(f"총 호출 {CALLS[0]}")


if __name__ == "__main__":
    main()
