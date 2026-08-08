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
    # 🔑 2026-08-08 실측(국내 46건): `ifrs-full_InterestExpense` 는 **0.0%** 다.
    #    한국 상장사는 그 태그를 쓰지 않는다. 실제로 쓰는 것은 아래 둘이다 —
    #      ifrs-full_FinanceCosts(금융원가·CIS)                     39/46 = **84.8%**
    #      ifrs-full_InterestPaid...OperatingActivities(이자지급·CF) 42/46 = **91.3%**
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
        "rcept_dt": rcept_dt_from(rows),
        "fs_div": rec.get("fs_div"),
    }
    for field, sj_divs, aids, hints in SPECS:
        out[field] = pick_account(rows, sj_divs, aids, hints)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    total = 0
    have = {f[0]: 0 for f in SPECS}
    have["rcept_dt"] = 0
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
            total += 1
            for k in have:
                if norm.get(k) is not None:
                    have[k] += 1

    lines = [f"정규화 {total}행", ""]
    for k, n in have.items():
        pct = (100.0 * n / total) if total else 0.0
        lines.append(f"  {k:20s} {n:7d}  {pct:6.2f}%")
    lines.append("")
    lines.append("🔴 interest_expense 커버리지가 낮으면 이자보상배율 축을 "
                 "사전등록에서 제외할 것.")
    text = "\n".join(lines)
    with open(COVERAGE_TXT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
