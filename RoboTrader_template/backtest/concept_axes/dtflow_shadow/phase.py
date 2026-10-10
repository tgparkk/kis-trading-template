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
               k: Optional[int]) -> Tuple[bool, str]:
    if k is None:
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
        if _credit_avail(trial_lags.get(d, []), k) < S.AVAIL_MIN:
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
    return "sealed" if seal_ready(store.runs("trial"), trial_lags, scan_days_desc, k)[0] else "trial"
