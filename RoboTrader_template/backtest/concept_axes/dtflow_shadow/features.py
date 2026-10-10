"""응답 → 특징 — 스펙 §4-3. D 행은 «날짜 필드 == D» 로만 고른다(첫 행 금지).

단위: investor 금액 = 백만원(×1e6) · program/short 금액 = 원 · 분모 거래대금 = 같은 아침 program `acml_tr_pbmn`.
신용 = deal_date 기준 · ④ = deal_date == cal[D−k] 행 · k 미정이면 None(시험 단계에서는 `credit_lag` 만 기록).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from . import settings as S


def rows_of(kind: str, body: dict) -> List[dict]:
    out = (body or {}).get("output2" if kind == "short" else "output")
    if isinstance(out, list):
        return [r for r in out if isinstance(r, dict)]
    return [out] if isinstance(out, dict) and out else []


def num(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "+"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def pick(rows: List[dict], field: str, ymd: str) -> Optional[dict]:
    for r in rows:
        if str(r.get(field, "")).strip() == ymd:
            return r
    return None


def compute(D: date, bodies: Dict[str, dict], cal: List[date], k: Optional[int]) -> Dict[str, Any]:
    ymd = D.strftime("%Y%m%d")
    inv_rows = rows_of("investor", bodies.get("investor") or {})
    prog_rows = rows_of("program", bodies.get("program") or {})
    inv = pick(inv_rows, "stck_bsop_date", ymd)
    prog = pick(prog_rows, "stck_bsop_date", ymd)
    sh = pick(rows_of("short", bodies.get("short") or {}), "stck_bsop_date", ymd)
    cr_rows = rows_of("credit", bodies.get("credit") or {})

    tv = num(prog.get("acml_tr_pbmn")) if prog else None
    ok_tv = tv is not None and tv > 0

    def ratio(v: Optional[float], unit: float = 1.0) -> Optional[float]:
        return (v * unit / tv) if (v is not None and ok_tv) else None

    f1 = ratio(num(inv.get("orgn_ntby_tr_pbmn")) if inv else None, S.INVESTOR_AMT_UNIT)
    f2 = ratio(num(prog.get("whol_smtn_ntby_tr_pbmn")) if prog else None)
    f3 = num(sh.get("ssts_vol_rlim")) if sh else None

    deal = sorted({str(r.get("deal_date", "")).strip() for r in cr_rows
                   if len(str(r.get("deal_date", "")).strip()) == 8 and str(r.get("deal_date", "")).strip() <= ymd},
                  reverse=True)
    latest = deal[0] if deal else None
    lag = None
    if latest and D in cal:
        ld = date(int(latest[:4]), int(latest[4:6]), int(latest[6:]))
        if ld in cal:
            lag = cal.index(D) - cal.index(ld)
    f4 = None
    gvrt = None
    if k is not None and D in cal and cal.index(D) - k >= 0:
        row = pick(cr_rows, "deal_date", cal[cal.index(D) - k].strftime("%Y%m%d"))
        if row:
            f4 = num(row.get("whol_loan_rmnd_rate"))
            gvrt = num(row.get("whol_loan_gvrt"))

    inv5 = sorted([r for r in inv_rows if str(r.get("stck_bsop_date", "")).strip() <= ymd],
                  key=lambda r: str(r.get("stck_bsop_date")), reverse=True)[:5]
    days5 = {str(r.get("stck_bsop_date")).strip() for r in inv5}
    tv5 = sum(num(r.get("acml_tr_pbmn")) or 0.0 for r in prog_rows if str(r.get("stck_bsop_date", "")).strip() in days5)
    o5 = [num(r.get("orgn_ntby_tr_pbmn")) for r in inv5]
    x_orgn5 = (sum(v for v in o5 if v is not None) * S.INVESTOR_AMT_UNIT / tv5) if (tv5 > 0 and len(inv5) == 5) else None

    return {"f1_orgn": f1, "f2_prog": f2, "f3_short": f3, "f4_credit": f4,
            "credit_deal_date": latest, "credit_lag": lag, "acml_tr_pbmn": tv,
            "has_investor": f1 is not None, "has_program": f2 is not None, "has_short": f3 is not None,
            "has_credit": f4 is not None,
            "x_frgn": ratio(num(inv.get("frgn_ntby_tr_pbmn")) if inv else None, S.INVESTOR_AMT_UNIT),
            "x_prsn": ratio(num(inv.get("prsn_ntby_tr_pbmn")) if inv else None, S.INVESTOR_AMT_UNIT),
            "x_orgn5": x_orgn5, "x_loan_gvrt": gvrt,
            "x_ssts_amt_rlim": num(sh.get("ssts_tr_pbmn_rlim")) if sh else None}
