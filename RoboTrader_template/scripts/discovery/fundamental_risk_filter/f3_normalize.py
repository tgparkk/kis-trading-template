"""F(3) 원본 응답 → 표준 필드 + 접수일. DART 호출 0건.

🔴 결측은 None 이다. 0 으로 채우지 않는다.
🔴 이자보상배율의 입력인 이자비용(interest_expense)은 계정 가용성이 불확실하다.
   커버리지를 실측해 리포트에 남긴다 — 낮으면 그 축을 사전등록에서 뺀다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f3_normalize.py
"""
import gzip
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR  # noqa: E402
from f2_collect import RAW_GZ  # noqa: E402

NORM_JSONL = os.path.join(OUT_DIR, "f3_normalized.jsonl")
COVERAGE_TXT = os.path.join(OUT_DIR, "f3_coverage.txt")

_NUM_RE = re.compile(r"^-?[\d,]+$")

# (필드, sj_div 후보들, account_id 후보, 계정명 힌트)
# 🔴 손익 항목의 sj_div 는 ("IS","CIS") 둘 다 받아야 한다.
#    DART 의 sj_div 는 BS(재무상태표)·IS(손익계산서)·CIS(포괄손익계산서)·CF·SCE 인데,
#    한국 상장사 상당수가 «단일 포괄손익계산서»만 제출해 영업이익이 CIS 에만 있다.
#    "IS" 로만 찾으면 그 회사들의 operating_income 이 조용히 None 이 되고,
#    커버리지 표에서 「계정이 원래 없다」로 오독된다.
SPECS = (
    ("total_equity",       ("BS",),        ("ifrs-full_Equity",),
     ("자본총계",)),
    ("issued_capital",     ("BS",),        ("ifrs-full_IssuedCapital",),
     ("자본금",)),
    ("total_liabilities",  ("BS",),        ("ifrs-full_Liabilities",),
     ("부채총계",)),
    ("operating_income",   ("IS", "CIS"),  ("dart_OperatingIncomeLoss",),
     ("영업이익", "영업손실")),
    ("interest_expense",   ("IS", "CIS"),  ("ifrs-full_InterestExpense",),
     ("이자비용",)),
    # 🔑 2026-08-08 실측(국내 「rows 가 있는」 46건): `ifrs-full_InterestExpense` 는 **0.0%**.
    #    한국 상장사는 그 태그를 쓰지 않는다. 실제로 쓰는 것은 아래 둘이다.
    #    ⚠️ **계정 존재율과 값 확보율을 반드시 구분할 것** — DART 가 계정 행은 주면서
    #       `thstrm_amount` 를 **빈 문자열**로 주는 경우가 있다(예: 194480·024060).
    #       `parse_amount` 가 None 을 돌려주므로 결측이 되고, 그게 옳은 동작이다.
    #                                          계정 존재    값 파싱 가능
    #      ifrs-full_FinanceCosts(금융원가·CIS)   39/46 84.8%   **37/46 80.4%**
    #      ifrs-full_InterestPaid…(이자지급·CF)   42/46 91.3%   **37/46 80.4%**
    #    ⇒ 인용할 때는 **값 확보율(80.4%)** 을 쓴다. 계정 존재율은 상한일 뿐이다.
    #    🔑 계정명 힌트 폴백이 실제로 더 건진다(fc 37 → 44, paid 37 → 40 / 분모 50).
    #    ⇒ ***「계정이 없다」가 아니라 「없는 이름을 찾고 있었다」였다.***
    #    둘 다 담고 사전등록에서 고른다(재파생은 DART 호출 0건이라 공짜다).
    #    ⚠️ 금융원가는 이자 외에 환손실·파생손실을 포함해 분모를 **과대**하게 만든다
    #       ⇒ 이자보상배율을 **과소** 추정 ⇒ 배제 필터에서는 **보수적인 방향**이다.
    #    ⚠️ 이자지급(CF)은 현금주의라 발생주의 분자(영업이익)와 기준이 다르다.
    ("finance_costs",      ("IS", "CIS"),  ("ifrs-full_FinanceCosts",),
     ("금융원가", "금융비용")),
    ("interest_paid_cf",   ("CF",),
     ("ifrs-full_InterestPaidClassifiedAsOperatingActivities",),
     ("이자지급",)),
)


def parse_amount(v):
    """'5,969,782,550' → 5969782550. 실패는 None (0 으로 뭉개지 말 것)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    if not _NUM_RE.match(s):
        return None
    try:
        return int(s.replace(",", ""))
    except ValueError:
        return None


def rcept_dt_from(rows):
    """rcept_no 앞 8자리 = 접수일. 'YYYY-MM-DD' 로 돌려준다."""
    for r in rows:
        no = str(r.get("rcept_no") or "")
        if len(no) >= 8 and no[:8].isdigit():
            return f"{no[0:4]}-{no[4:6]}-{no[6:8]}"
    return None


def pick_account(rows, sj_divs, account_ids, name_hints):
    """account_id 우선, 없으면 계정명 힌트. sj_divs 밖의 표는 보지 않는다.

    sj_divs 는 튜플이다 — 손익 항목은 ("IS","CIS") 처럼 둘 이상을 받는다.
    """
    # ⚠️ 문자열이 들어오면 `in` 이 «부분문자열» 매칭이 되어 조용히 오스코프된다
    #    (예: "BS" 를 주면 sj_div "B" 도 통과). 튜플로 승격해 그 경로를 없앤다.
    if isinstance(sj_divs, str):
        sj_divs = (sj_divs,)
    cand = [r for r in rows if str(r.get("sj_div") or "") in sj_divs]
    for aid in account_ids:
        for r in cand:
            if str(r.get("account_id") or "").strip() == aid:
                v = parse_amount(r.get("thstrm_amount"))
                if v is not None:
                    return v
    for hint in name_hints:
        for r in cand:
            nm = str(r.get("account_nm") or "").replace(" ", "")
            if nm == hint:
                v = parse_amount(r.get("thstrm_amount"))
                if v is not None:
                    return v
    return None


def normalize(rec):
    rows = rec.get("rows") or []
    out = {
        "stock_code": rec["stock_code"],
        "bsns_year": rec["bsns_year"],
        # 🔑 status 를 «끌고 간다». 이게 없으면 커버리지 표가
        #    「신고 자체가 없다(013·000_EMPTY)」와 「신고는 있는데 계정을 못 찾았다」를
        #    구분하지 못하고, 둘이 섞이면 매핑 오류가 결측으로 위장된다.
        #    실제로 2026-08-08 에 외국기업 표본이 이 구조로 판정을 속였다.
        "status": rec.get("status"),
        "rcept_dt": rcept_dt_from(rows),
        "fs_div": rec.get("fs_div"),
    }
    for field, sj_divs, aids, hints in SPECS:
        out[field] = pick_account(rows, sj_divs, aids, hints)
    return out


FIELDS = [f[0] for f in SPECS] + ["rcept_dt"]


def summarize(records):
    """커버리지를 «두 벌» 돌려준다 — (전체 기준, 신고 있는 레코드 기준).

    🔴 한 벌만 내면 안 된다. 신고가 아예 없는 종목·연도(013·000_EMPTY)가 섞이면
       모든 필드가 «나란히» 내려가고, 그러면 「매핑이 틀렸다」와 「신고가 없다」가
       같은 그림이 된다. 축 채택을 가르는 숫자라 이 구분이 판정을 바꾼다.
    반환: (n_all, cov_all, n_filed, cov_filed, status_counts)
    """
    filed = [r for r in records if r.get("status") == "000"]
    status_counts = {}
    for r in records:
        s = r.get("status")
        status_counts[s] = status_counts.get(s, 0) + 1

    def _cov(rs):
        return {f: sum(1 for r in rs if r.get(f) is not None) for f in FIELDS}

    return len(records), _cov(records), len(filed), _cov(filed), status_counts


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    records = []
    with gzip.open(RAW_GZ, "rt", encoding="utf-8") as src, \
            open(NORM_JSONL, "w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            norm = normalize(rec)
            dst.write(json.dumps(norm, ensure_ascii=False) + "\n")
            records.append(norm)

    n_all, cov_all, n_filed, cov_filed, status_counts = summarize(records)

    lines = [f"정규화 {n_all}행 · 그중 신고 있음(status=000) {n_filed}행", ""]
    lines.append(f"  status 분포: {status_counts}")
    lines.append("")
    lines.append(f"  {'field':20s} {'전체':>16s} {'신고분만':>16s}")
    for f in FIELDS:
        pa = (100.0 * cov_all[f] / n_all) if n_all else 0.0
        pf = (100.0 * cov_filed[f] / n_filed) if n_filed else 0.0
        lines.append(f"  {f:20s} {cov_all[f]:6d} {pa:6.2f}%  "
                     f"{cov_filed[f]:6d} {pf:6.2f}%")
    lines.append("")
    lines.append("🔑 게이트는 «신고분만» 열로 판정한다. 「전체」 열은 신고가 없는")
    lines.append("   종목·연도까지 분모에 넣기 때문에, 매핑 오류와 신고 부재가")
    lines.append("   같은 그림으로 보인다.")
    lines.append("🔴 커버리지로 축 채택을 판정하기 전에 «표본의 고유 종목 수»를 확인할 것.")
    lines.append("   작업목록은 종목당 7년이 연속이라 100행이 15종목도 안 될 수 있다.")
    text = "\n".join(lines)
    with open(COVERAGE_TXT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
