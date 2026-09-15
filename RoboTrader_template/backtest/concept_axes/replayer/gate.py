"""재현 일치율 게이트 — 설계서 §4 · §7 V5·V6.

🔴 **문턱은 결과를 보기 «전»에 고정돼 있다**(`THRESHOLDS`). 결과를 보고 내리지 않는다.
🔴 불일치는 「몇 %」가 아니라 **집합 차분 «양방향»**(`live_only` / `replay_only`)으로 인쇄한다.
🔴 **V6 가 검증하는 것은 «라이브와 같은가»가 아니다** — 그 구간엔 대조할 원본이 0행이다.
   V6 가 검증하는 것은 ①재현기가 룰을 옳게 «계산»하는가 ②입력 데이터가 구간 간 «동질»한가 둘이다.
"""
from __future__ import annotations

import datetime as dt
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

# 🔒 §4-3 · §4-6 — 실행 «전» 동결. 내려서 통과시키지 않는다.
THRESHOLDS: Dict[str, float] = {
    "M1_pass": 0.98,
    "M1_conditional": 0.95,
    "M2_pass": 0.98,               # 리뷰 M-1 — 인쇄만 하고 판정에 안 쓰던 지표를 문턱에 연결
    "M3_pass": 0.95,
    "M4_pass": 0.99,
    "M1_exposed_floor": 0.90,      # v0.3 조건 ④
    "protected_min_days": 15,      # v0.3 조건 ⑤
}

TOP_K = 5                          # §4-3 M3 — 판정이 실제로 서는 자리
M4_REL_TOL = 1e-6

# §4-5 C1 서명 ② — 회수는 **거래일** 기준이다(리뷰 H-2).
# 달력 3일 판은 금요일 scan_date 를 전부 «지연» 으로 읽었다(주말이 사이에 끼어서).
C1_LATE_GRACE = dt.timedelta(hours=12)

# §4-4-c — 구간 분할 경계.
PROTECTED_FROM = "2026-09-03"      # 커밋 7abdc30 (W1_PAST_ROWS_INSERT_ONLY)
PREF_ONBOARD_FROM = "2026-08-05"   # 우선주 +67 일괄 등장
DAYTRADING_PARAMS_SWITCH = "2026-06-23"   # high_window 20 → 15

# §7 V5-a — 평일 09:00~09:20 KST 회피(09:00 장전 수집이 과거 ~103봉을 UPSERT).
BLOCKED_FROM = dt.time(9, 0)
BLOCKED_TO = dt.time(9, 20)

V6_HEADER = (
    "V6 가 검증하는 것은 «라이브와 같은가»가 아니다 — 그 구간엔 대조할 원본이 0행이다. "
    "V6 가 검증하는 것은 ①재현기가 룰을 옳게 «계산»하는가 ②입력 데이터가 구간 간 «동질»한가 둘이다."
)
C1_CAVEAT = "🔴 스냅샷 동결 «이전»에 일어난 값 변경은 어떤 컬럼으로도 판별할 수 없다."
NOT_BUYABLE_CAVEAT = (
    "🔴 후보 원장의 한 행은 「그날 살 수 있었던 종목」이 아니다 — 안전필터 «이전» 지점이다"
    "(라이브 실측 2026-08-10: 조회 71건 중 6건 ≈ 8.5% 가 등록 단계에서 배제). "
    "노출·보유·매수가능을 이 원장으로 계산하면 8~9% 를 과대계상한다."
)


@dataclass
class DayPair:
    """같은 `scan_date` 의 라이브 저장 집합 `L` 과 재현 상위 20 `R`."""
    scan_date: str
    live: List[str]
    replay: List[str]
    live_scores: Dict[str, float] = field(default_factory=dict)
    replay_scores: Dict[str, float] = field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────────────
# §7 V5-a — 실행 시간창
# ────────────────────────────────────────────────────────────────────────────
def time_window_ok(now: Optional[dt.datetime] = None) -> bool:
    """평일 09:00~09:20 KST 를 **포함하면 실행 불가**(경계 포함)."""
    now = now or dt.datetime.now()
    if now.weekday() >= 5:
        return True
    return not (BLOCKED_FROM <= now.time() <= BLOCKED_TO)


def require_time_window(now: Optional[dt.datetime] = None) -> None:
    if not time_window_ok(now):
        raise RuntimeError(
            "V5-a 위반 — 평일 09:00~09:20 KST 에는 실행하지 않는다"
            "(09:00 장전 수집이 종목당 과거 ~103봉을 UPSERT 한다). "
            "권장 창 = 07:00~08:40 또는 15:45~23:59.")


# ────────────────────────────────────────────────────────────────────────────
# §4-3 — M1~M4
# ────────────────────────────────────────────────────────────────────────────
def next_trading_day(cal: Sequence[Any], d: Any):
    """오름차순 거래일 목록 `cal` 에서 `d` «다음» 거래일. 없으면 `None`."""
    ks = list(cal or [])
    i = bisect_right(ks, pd.Timestamp(d))
    return ks[i] if i < len(ks) else None


def created_late(created_at: Any, scan_date: Any, cal: Sequence[Any]) -> bool:
    """§4-5 C1 서명 ② — `created_at > 다음 «거래일» + 12h`.

    🔴 구판 `created_at > scan_date + 3일(달력)` 은 **요일 탐지기**였다 —
    금요일은 다음 거래일이 사흘 뒤(월)라 일상적인 재수집도 전부 «지연» 으로
    읽혔고, 실측 발화일 15일 중 14일이 금요일이었다(판별력 ≈ 0).
    그래서 **거래일 달력**으로 재는다 — 09:00 장전 스캔 기준으로
    «다음 거래일 정오» 를 넘기면 그건 다음 세션의 재기록이다.
    """
    if created_at is None or created_at != created_at:
        return False
    nxt = next_trading_day(cal, scan_date)
    if nxt is None:
        return False          # 창 끝 — 다음 거래일을 모르면 C1 을 단정하지 않는다
    return pd.Timestamp(created_at) > pd.Timestamp(nxt) + C1_LATE_GRACE


def _spearman(a: Sequence[float], b: Sequence[float]) -> float:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    if np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def compute_metrics(days: Sequence[DayPair]) -> Dict[str, Any]:
    """M1(집합 Jaccard 마이크로) · M2(순위 Spearman 중앙값) · M3(top5) · M4(score).

    🔴 리뷰 M-3 — 예전의 `drop_codes`(라이브 집합에서 배제 종목을 «사후» 뺀다)는
    **제거했다**. 사후 제거는 배제로 비운 슬롯에 20위 밖이 밀려 올라온 효과를 되돌리지
    못해 M2·M3 를 «한쪽으로» 움직인다 ⇒ 보조 지표는 「랭킹 «전» 배제 없이 다시
    재현한 상위 20 vs 라이브」 변종으로 낸다(`run.replay(excluded=set())`).
    """
    inter_sum = union_sum = 0
    top_inter = top_den = 0
    m4_ok = m4_n = 0
    rhos: List[float] = []
    skipped = 0
    for d in days:
        L, R = list(d.live), list(d.replay)
        sL, sR = set(L), set(R)
        inter_sum += len(sL & sR)
        union_sum += len(sL | sR)

        tL, tR = set(L[:TOP_K]), set(R[:TOP_K])
        # 🔒 〖정의 동결〗 — 분모는 항상 `TOP_K`(=5) 이다. `min(TOP_K, len(L))` 은
        # 라이브가 5개 미만인 날 분모를 줄여 M3 를 «올려준다» — 구현을 따라 정의를
        # 바꾸지 않는다(리뷰 H-1). 라이브가 비었으면 그날은 분모에서 빠진다.
        den = TOP_K if L else 0
        if den:
            top_inter += len(tL & tR)
            top_den += den

        common = [c for c in L if c in sR]
        if len(common) >= 2:
            lr = {c: i for i, c in enumerate(L)}
            rr = {c: i for i, c in enumerate(R)}
            rho = _spearman([lr[c] for c in common], [rr[c] for c in common])
            if rho == rho:
                rhos.append(rho)
            else:
                skipped += 1
        else:
            skipped += 1

        for c in common:
            if c in d.live_scores and c in d.replay_scores:
                m4_n += 1
                lv = d.live_scores[c]
                if lv:
                    m4_ok += abs(d.replay_scores[c] / lv - 1.0) <= M4_REL_TOL
    return {
        "n_days": len(days),
        "M1": (inter_sum / union_sum) if union_sum else float("nan"),
        "M2": float(np.median(rhos)) if rhos else float("nan"),
        "M2_skipped_days": skipped,
        "M3": (top_inter / top_den) if top_den else float("nan"),
        "M4": (m4_ok / m4_n) if m4_n else float("nan"),
        "M4_n": m4_n,
        "n_live": sum(len(d.live) for d in days),
        "n_replay": sum(len(d.replay) for d in days),
        "n_inter": inter_sum,
        "n_union": union_sum,
    }


def verdict(m: Dict[str, float]) -> str:
    """§4-3 문턱 적용. 🔴 **문턱을 내려서 통과시키지 않는다.**

    리뷰 M-1 — M2 도 문턱(`M2_pass`)에 연결한다. 재지 불가(nan = 교집합 원소 < 2 가
    전일)는 M4 와 같은 취급으로 **불통과 사유로 쓰지 않고**, 대신 분모 제외일 수를 인쇄한다.
    """
    m1, m2, m3, m4 = m.get("M1"), m.get("M2"), m.get("M3"), m.get("M4")
    if m1 is None or m1 != m1 or m1 < THRESHOLDS["M1_conditional"]:
        return "FAIL"
    ok2 = (m2 is None) or (m2 != m2) or m2 >= THRESHOLDS["M2_pass"]
    ok3 = (m3 == m3) and m3 >= THRESHOLDS["M3_pass"]
    ok4 = (m4 != m4) or m4 >= THRESHOLDS["M4_pass"]
    if m1 >= THRESHOLDS["M1_pass"] and ok2 and ok3 and ok4:
        return "PASS"
    return "조건부"


# ────────────────────────────────────────────────────────────────────────────
# §4-4-c — 구간 분할 (한 값으로 내지 않는다)
# ────────────────────────────────────────────────────────────────────────────
def split_windows(days: Sequence[DayPair]) -> Dict[str, List[DayPair]]:
    return {
        "노출(≤2026-09-02)": [d for d in days if d.scan_date < PROTECTED_FROM],
        "보호(≥2026-09-03)": [d for d in days if d.scan_date >= PROTECTED_FROM],
        "우선주 온보딩 전(≤2026-08-04)": [d for d in days if d.scan_date < PREF_ONBOARD_FROM],
        "우선주 온보딩 후(≥2026-08-05)": [d for d in days if d.scan_date >= PREF_ONBOARD_FROM],
    }


# ────────────────────────────────────────────────────────────────────────────
# §4-5 — 불일치 원인 분류 (라벨은 미리 지었다)
# ────────────────────────────────────────────────────────────────────────────
def classify_mismatch(*, code: str, side: str,
                      live_rank: Optional[int], replay_rank: Optional[int],
                      score_match: bool, created_late: bool, hash_changed: bool,
                      impossible_in_window: bool, at_params_boundary: bool,
                      set_swept: bool,
                      exclusion_promoted: bool = False) -> str:
    """서명 우선순위대로 라벨 하나를 돌려준다. 어디에도 안 걸리면 **C6 미상**.

    `exclusion_promoted` 는 **C7 «배제 승격»** — 같은 날 §1-2-b 배제 종목이
    라이브에만 있고(`live_only`) 그 수만큼 재현에만 있는 종목(`replay_only`)이 있을 때,
    그건 «모르는 불일치»가 아니라 **배제로 슬롯이 비어 20위 밖이 밀려 올라온** 것이다.
    🔴 C6(미상)과 같은 칸에 넣으면 «설명되지 않은 몫» 을 과대계상한다.
    """
    if set_swept:
        return "C2"          # 유니버스 일자 폴백 — 집합이 통째로 어긋난다
    if impossible_in_window:
        return "C3"          # 불가능봉 가드 차
    if at_params_boundary:
        return "C4"          # 룰 드리프트 — params_hash 경계에 몰림
    rank = live_rank if live_rank is not None else replay_rank
    if score_match and rank is not None and rank >= 19:
        return "C5"          # 동점 경계 (rank 19~20 · score 동일)
    # C1 데이터 갱신 — 🔴 `updated_at` 은 판별에 쓰지 않는다(전 행 단일 일자 = 판별력 0).
    # 🔑 M4 불일치는 «동반» 서명이지 «단독» 서명이 아니다 — 그것만으로는 C1 이 아니다.
    #    단독 판별 서명은 ②`created_at > 다음 «거래일» + 12h` ③스냅샷 대 현행 행 해시 차분이고,
    #    ④노출/보호 구간 대조는 집계 수준에서 따로 인쇄한다(§4-5 C1).
    if created_late or hash_changed:
        return "C1"
    if exclusion_promoted:
        return "C7"          # 배제 승격 — 빈 슬롯만큼 밀려 올라왔다(C6 에서 분리)
    return "C6"


MA20_WINDOW = 20


def m4_lag_profile(days: Sequence[DayPair], vol_lookup,
                   max_lag: int = MA20_WINDOW) -> Dict[str, Any]:
    """M4 불일치의 **채널 프로파일** — k = 0..max_lag-1 각각에 대해
    「D−k 봉«만» 바뀌었다」고 «가정»했을 때의 함의값 비 `implied / stored` 분포.

    🔑 `score_ma20 = mean(volume[-20:])` 이므로 라이브 score 에서 한 봉의 함의값을
    역산할 수 있다: `implied_k = live_score × 20 − (Σ window − stored_k)`.
    🔴 **어느 봉이 바뀌는지는 데이터가 말해 주지 않는다** — 이 표는 가정별 함의값이지
    채널 판정이 아니다. 한 봉 채널이면 치우침이 k=0 에 몰리고, 창 전체가 미세하게
    커진 경우면 k 에 걸쳐 **평탄**하다 — 둘을 가르는 것은 이 모양뿐이다.

    `whole_window` 는 「창 20봉이 «균일하게» 바뀌었다」 가정의 함의 변화율
    `live/replay − 1`(%) 분포다 — 같은 M4 불일치를 «다른 채널» 로 읽은 값이다.
    🔴 이건 원인 인쇄이지 문턱 완화가 아니다 — M4 문턱 99% 는 그대로다.
    """
    per_lag: Dict[int, List[float]] = {k: [] for k in range(max_lag)}
    whole: List[float] = []
    n_rows = 0
    for dp in days:
        for c in dp.replay:
            if c not in dp.live_scores or c not in dp.replay_scores:
                continue
            lv, rv = dp.live_scores[c], dp.replay_scores[c]
            if not lv or abs(rv / lv - 1.0) <= M4_REL_TOL:
                continue
            v = vol_lookup(c, dp.scan_date)
            if v is None or len(v) < MA20_WINDOW:
                continue
            win = v[-MA20_WINDOW:]
            tot = float(win.sum())
            n_rows += 1
            if rv:
                whole.append((lv / rv - 1.0) * 100.0)
            for k in range(min(max_lag, MA20_WINDOW)):
                stored = float(win[-1 - k])
                if stored <= 0:
                    continue
                implied = lv * MA20_WINDOW - (tot - stored)
                per_lag[k].append(implied / stored)
    rows = []
    for k in range(max_lag):
        arr = np.asarray(per_lag[k], dtype=float)
        if not len(arr):
            continue
        rows.append({
            "k": k,
            "n": int(len(arr)),
            "median": float(np.median(arr)),
            "p05": float(np.percentile(arr, 5)),
            "p95": float(np.percentile(arr, 95)),
            "frac_below_1": float((arr < 1.0).mean()),
        })
    w = np.asarray(whole, dtype=float)
    return {
        "n": n_rows,
        "lags": rows,
        "whole_window": ({} if not len(w) else {
            "n": int(len(w)),
            "min_pct": float(w.min()),
            "max_pct": float(w.max()),
            "median_pct": float(np.median(w)),
        }),
    }


# ────────────────────────────────────────────────────────────────────────────
# §4-5-b G10 — 교체율 r̂ 은 «재현 원장에서» 다시 잰다
# ────────────────────────────────────────────────────────────────────────────
def replacement_rate(topk_a: Dict[Any, Sequence[str]],
                     topk_b: Dict[Any, Sequence[str]]) -> Dict[str, Any]:
    """`r̂ = ΣM_d / ΣN_d` — 두 정렬 키가 top-K 에서 «갈리는 슬롯 수».

    🔴 라이브 값을 수입하지 않는다(라이브 37.1% 는 안전필터 «이후» 값이라 단위가 다르다).
    """
    n = m = 0
    for d, a in topk_a.items():
        b = topk_b.get(d, [])
        n += len(a)
        m += len(set(a) - set(b))
    return {"N": n, "M": m, "r_hat": (m / n) if n else float("nan")}


# ────────────────────────────────────────────────────────────────────────────
# §7 V6 — 판정 창 전용 검사
# ────────────────────────────────────────────────────────────────────────────
def v6_3_continuity(diag: pd.DataFrame, cols=("n_universe", "n_eligible", "n_matched"),
                    window: int = 60, tol: float = 0.50) -> pd.DataFrame:
    """V6-3 연속성 — 60일 이동중앙값 대비 ±50% 이탈일을 **전수** 돌려준다."""
    out = []
    d = diag.sort_values("scan_date")
    for c in cols:
        if c not in d.columns:
            continue
        med = d[c].rolling(window, min_periods=max(5, window // 4)).median()
        dev = (d[c] - med).abs() / med.replace(0, np.nan)
        hit = d.loc[dev > tol, ["scan_date", c]].copy()
        hit["metric"] = c
        hit["median_60d"] = med[dev > tol].to_numpy()
        hit = hit.rename(columns={c: "value"})
        out.append(hit)
    return (pd.concat(out, ignore_index=True) if out
            else pd.DataFrame(columns=["scan_date", "value", "metric", "median_60d"]))


def v6_5_drift(year_agg: pd.DataFrame) -> Dict[str, Any]:
    """V6-5 측정기 드리프트 — 연도 간 「거래일당 패딩」 비가 2배를 넘으면 병기 의무."""
    s = year_agg["padding_per_day"].dropna()
    if s.empty:
        return {"ratio_max": float("nan"), "pooled_forbidden": False}
    ratio = float(s.max() / s.min()) if s.min() > 0 else float("inf")
    return {"ratio_max": ratio, "pooled_forbidden": ratio > 2.0,
            "by_year": s.to_dict()}
