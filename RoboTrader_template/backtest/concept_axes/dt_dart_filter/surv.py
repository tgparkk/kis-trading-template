"""생존자 누락률 — 스펙 §3-6 · 최종 리뷰 I1(관리자 판정).

공시 1건을 그 접수일 이후 첫 거래일 d 에 대응시켜 분류한다:
- `konex`         corp_cls N(코넥스) → 두 비율 모두에서 제외(코넥스는 `daily_prices` 에 원래 없다).
- `out_of_cal`    d 가 가격 달력 밖 → 제외.
- `later_listed`  종목이 `daily_prices` 에 d «뒤»에야 처음 나타남(상장 전 공시) → 제외.
- `present`       (종목, d) 가 `daily_prices` 에 있음.
- `absent_day`    d 이전에 나타났지만 그날 행이 없음 → 누락.
- `never_present` `daily_prices` 에 끝내 없음 → 누락.

(i) = 3태그 원공시 «공시 단위»(스펙 :94 «원공시 중») · 누락 = absent_day + never_present / (present + 누락).
(ii) = 정기공시(pblntf_ty A · 정정 제외)를 낸 회사 «회사 단위»(스펙 :94 «상장사 중») · 회사의 남은(제외 안 된) 정기공시 중
     하루라도 누락이면 그 회사 = 누락(보수적 — (ii) 를 키워 라벨 조건 (i) ≥ (ii) 를 어렵게 하는 방향).
     남은 공시가 없는 회사는 그 회사 공시의 분류(우선순위 konex > later_listed > out_of_cal)로 제외 칸에 센다.
한계(PREREG 명시): corp_cls 는 DART «현재» 값이라 과거 코넥스 → 이전상장 종목 소수가 잘못 빠질 수 있다.
"""
from __future__ import annotations

import bisect
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from . import tags as T

CLASSES = ("present", "absent_day", "never_present", "later_listed", "konex", "out_of_cal")
_MISSING = ("absent_day", "never_present")
_COUNTED = ("present",) + _MISSING
_LABEL = {"present": "있음", "absent_day": "그날만 없음", "never_present": "끝내 없음",
          "later_listed": "나중 상장 제외", "konex": "코넥스 제외", "out_of_cal": "달력 밖 제외"}


def classify(code: str, d: date, cls: str, cal: Sequence[date], px_keys: Set[Tuple[str, date]],
             first_seen: Mapping[str, date]) -> str:
    if str(cls or "").strip().upper() == "N":
        return "konex"
    j = bisect.bisect_left(cal, d)
    if j >= len(cal):
        return "out_of_cal"
    day = cal[j]
    if (code, day) in px_keys:
        return "present"
    first = first_seen.get(code)
    if first is None:
        return "never_present"
    return "later_listed" if first > day else "absent_day"


def _rate(counts: Dict[str, int]) -> Tuple[float, int]:
    n = sum(counts[c] for c in _COUNTED)
    m = sum(counts[c] for c in _MISSING)
    return (m / n if n else float("nan")), n


def survivorship(rows: Iterable[Tuple[str, date, str, str, str]], cal: Sequence[date],
                 px_keys: Set[Tuple[str, date]], first_seen: Mapping[str, date]) -> Dict[str, Any]:
    """rows = (stock_code, rcept_dt, report_nm, pblntf_ty, corp_cls)."""
    cal = list(cal)
    b_i = {c: 0 for c in CLASSES}
    per_co: Dict[str, List[str]] = {}
    for code, d, nm, ty, cls in rows:
        code = str(code)
        if T.is_lag0_tag(nm):
            b_i[classify(code, d, cls, cal, px_keys, first_seen)] += 1
        if ty == "A" and "정정" not in (nm or ""):
            per_co.setdefault(code, []).append(classify(code, d, cls, cal, px_keys, first_seen))
    b_ii = {c: 0 for c in CLASSES}
    for ks in per_co.values():
        kept = [k for k in ks if k in _COUNTED]
        if kept:
            k = ("never_present" if "never_present" in kept else
                 "absent_day" if "absent_day" in kept else "present")
        else:
            k = next(c for c in ("konex", "later_listed", "out_of_cal") if c in ks)
        b_ii[k] += 1
    si, ni = _rate(b_i)
    sii, nii = _rate(b_ii)
    return {"surv_i": si, "n_i": ni, "surv_ii": sii, "n_ii": nii, "breakdown_i": b_i, "breakdown_ii": b_ii}


def breakdown_text(s: Mapping[str, Any]) -> str:
    def one(b):
        return " · ".join(f"{_LABEL[c]} {int(b[c]):,}" for c in CLASSES)
    return (f"(i) 공시 단위: {one(s['breakdown_i'])}\n"
            f"(ii) 회사 단위: {one(s['breakdown_ii'])}")
