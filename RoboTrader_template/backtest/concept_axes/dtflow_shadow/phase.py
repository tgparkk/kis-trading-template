"""시험 → 봉인 전환 — 스펙 §4-1: 연속 10거래일 「후보 일치 100% ∧ 4종 가용률 ≥ 0.95(신용은 고정 시차 k)」.
k 가 동결되기 전(None)에는 전환하지 않는다. 한 번 봉인되면 계속 봉인(되돌리지 않음)."""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from . import settings as S


def _credit_avail(lags: List[Optional[int]], k: int) -> float:
    if not lags:
        return 0.0
    return sum(1 for v in lags if v is not None and v <= k) / len(lags)


def _canonical(runs: List[Dict], kind: str) -> Dict[date, Dict]:
    """(scan_date, run_kind)별 정본 행 = run_at 가장 이른 행(상태 무관 · 입력 순서 무관). 나중에 손으로 채운 ok 행은 무시."""
    out: Dict[date, Dict] = {}
    for r in runs:
        if r.get("run_kind") != kind:
            continue
        d = r["scan_date"]
        cur = out.get(d)
        if cur is None or _at(r) < _at(cur):
            out[d] = r
    return out


def _at(r: Dict):
    v = r.get("run_at")
    return (v is None, "" if v is None else str(v))


def seal_ready(trial_runs: List[Dict], trial_lags: Dict[date, List[Optional[int]]], scan_days_desc: List[date],
               k: Optional[int], credit_dropped: bool = False) -> Tuple[bool, str]:
    """`credit_dropped`(B-3 · S.CREDIT_DROPPED) = 신용 ④ 를 가족에서 뺐다 → k 없이, 신용 가용률 조건 없이 판정."""
    if k is None and not credit_dropped:
        return False, "신용 시차 k 미동결"
    need = scan_days_desc[:S.TRIAL_DAYS]
    if len(need) < S.TRIAL_DAYS:
        return False, "거래일 부족"
    rec = _canonical(trial_runs, "record")
    snap = _canonical(trial_runs, "snapshot_check")
    for d in need:
        r = rec.get(d)
        if r is None or r.get("status") != "ok":
            return False, f"{d} 기록 없음"
        if min(float(r.get(c) or 0.0) for c in ("avail_investor", "avail_program", "avail_short")) < S.AVAIL_MIN:
            return False, f"{d} 가용률 미달"
        if not credit_dropped and _credit_avail(trial_lags.get(d, []), k) < S.AVAIL_MIN:
            return False, f"{d} 신용 가용률 미달"
        if (snap.get(d) or {}).get("status") != "ok" or not snap[d].get("snapshot_match"):
            return False, f"{d} 스냅샷 불일치/없음"
    return True, "ok"


def choose_k_table(trial_lags: Dict[date, List[Optional[int]]], ks=range(1, 7)) -> List[Tuple[int, float, float]]:
    out = []
    for k in ks:
        v = [_credit_avail(lags, k) for lags in trial_lags.values()]
        out.append((k, min(v) if v else 0.0, sum(v) / len(v) if v else 0.0))
    return out


def decide(store, scan_days_desc: List[date], k: Optional[int], trial_lags) -> str:
    """한 방향 규칙: 봉인 run 행이 하나라도 있으면(상태 무관: ok·missed_token·late·missed_host…) 항상 "sealed".
    봉인 행이 없을 때만 시험 창 판정(seal_ready)으로 전환한다.
    `scan_days_desc` = «끝난» 스캔일 내림차순(지금 기록하는 D 제외 — 러너가 days_desc[1:1+TRIAL_DAYS] 를 넘긴다)."""
    if store.runs("sealed"):
        return "sealed"
    ready = seal_ready(store.runs("trial"), trial_lags, scan_days_desc, k, credit_dropped=S.CREDIT_DROPPED)[0]
    return "sealed" if ready else "trial"


def _snap_bad(r: Optional[Dict]) -> bool:
    """정본 snapshot_check 가 «나쁨» = 행 없음 · status ≠ ok(no_snapshot·error·no_record) · ok 인데 불일치."""
    return r is None or r.get("status") != "ok" or not r.get("snapshot_match")


def stop_check(sealed_runs: List[Dict], after: Optional[date] = None) -> Tuple[bool, Dict]:
    """B-1 봉인 단계 멈춤 규칙(사장님 10-10). 대상일 = 봉인 표의 정본 record(가장 이른 행)가 ok/late ∧ 후보 ≥ 1 인
    scan_date 중 `after`(이미 멈춤으로 넘긴 마지막 날) 뒤. 그날 정본 snapshot_check(가장 이른 행)가 «나쁨»이면 나쁜 날.
    멈춤 = 최근 STOP_STREAK 대상일이 모두 나쁨(streak) 또는 최근 STOP_WINDOW 대상일 중 나쁜 날 수 >
    STOP_WINDOW × STOP_WINDOW_FRAC(window). 대상 아닌 날(결측일·후보 0)은 세지도 끊지도 않는다."""
    rec = _canonical(sealed_runs, "record")
    snap = _canonical(sealed_runs, "snapshot_check")
    days = sorted(d for d, r in rec.items()
                  if r.get("status") in ("ok", "late") and (r.get("n_cands") or 0) >= 1 and (after is None or d > after))
    bad = {d for d in days if _snap_bad(snap.get(d))}
    window = days[-S.STOP_WINDOW:]
    n_bad = sum(1 for d in window if d in bad)
    info: Dict = {"reason": None, "n_days": len(window), "n_bad": n_bad,
                  "bad_days": [d.isoformat() for d in window if d in bad],
                  "through": days[-1].isoformat() if days else None}
    if len(days) >= S.STOP_STREAK and all(d in bad for d in days[-S.STOP_STREAK:]):
        info["reason"] = "streak"
    elif n_bad > S.STOP_WINDOW * S.STOP_WINDOW_FRAC:
        info["reason"] = "window"
    return info["reason"] is not None, info
