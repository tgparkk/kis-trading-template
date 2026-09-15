"""일별 스캔 루프 — 설계서 §2(하이브리드) · §2-3(창) · §2-4(정렬·절단·동점).

🟢 **판정 경계는 라이브 어댑터를 import 해서 «그대로» 부른다.**
   `base_filter()` · `default_params()` · `match()` — 셋 다 DB 를 안 건드리고
   (`QuantDailyReader` 는 lazy) 순수하게 DataFrame 만 본다. 그래서 «룰 복제»가 없다
   ⇒ 설계서 §2 (b) 의 드리프트가 구조적으로 불가능하다.
🔴 재구현하는 것은 **스캔 루프·벌크 로드·창 자르기·정렬**뿐이다.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.data_sanity import describe_impossible_drop          # noqa: E402

# 🔒 `config/constants.py:200 MAX_CANDIDATES_PER_STRATEGY` — 라이브 실효값.
#    어댑터 `default_params()` 의 10 은 라이브 실효값이 «아니다»(§2-4).
from config.constants import MAX_CANDIDATES_PER_STRATEGY        # noqa: E402

LIVE_K = 5          # 라이브 동시 보유 한도(`config.yaml risk_management.max_positions`)


# ────────────────────────────────────────────────────────────────────────────
# §2-3 — 창 자르기 (라이브 `_load_daily(days=lookback)` + `<= D` 와 같은 창)
# ────────────────────────────────────────────────────────────────────────────
def window_slice(g: pd.DataFrame, i: int, lookback: int) -> pd.DataFrame:
    """`g` 의 `i` 번째 행을 마지막으로 하는 최대 `lookback` 봉 창.

    라이브는 `get_daily_prices(code, end_date=D, days=lookback)` 로 **D 이하 최근
    lookback 행**을 읽고, `_prepare_frame` 이 `<= D` 로 한 번 더 자른다(무연산).
    ⇒ 여기서 만드는 창이 «룰이 보는 창»이자 «위생 가드가 보는 창»이다
    (`sanity_window is None` ⇒ 로드한 일봉 전체).
    """
    return g.iloc[max(0, i + 1 - lookback):i + 1]


def is_impossible(win: pd.DataFrame) -> bool:
    """불가능봉 가드 — 라이브와 «같은 함수»·«같은 창»·«같은 문턱»(−35%)."""
    return bool(describe_impossible_drop(win))


# ────────────────────────────────────────────────────────────────────────────
# §1-2 — base_filter 를 날짜별로 «라이브 어댑터로» 적용
# ────────────────────────────────────────────────────────────────────────────
def eligible_by_date(uni: Dict[Any, Dict[str, Tuple[float, float]]],
                     adapter) -> Dict[Any, Set[str]]:
    """`{date: {code}}`. 🔴 시총 fail-closed·`max_inclusive` 차이를 어댑터가 판단한다."""
    out: Dict[Any, Set[str]] = {}
    for d, m in uni.items():
        out[d] = _filter_rows(m, adapter)
    return out


def _filter_rows(rows: Dict[str, Tuple[float, float]], adapter) -> Set[str]:
    recs = [{"code": c, "name": c, "market_cap": mc, "trading_value": tv}
            for c, (mc, tv) in rows.items()]
    return {r["code"] for r in adapter.base_filter(recs)}


def eligible_for_dates(uni: Dict[Any, Dict[str, Tuple[float, float]]],
                       adapter, scan_dates: Sequence[Any],
                       exclude: Optional[Set[str]] = None):
    """`scan_date` 로 키잉한 적격 집합 + 유니버스 진단.

    🔴 **유니버스 일자 폴백을 여기서 재현한다** — `scan_date` 당일 퀀트 적재가 안
    끝났으면 라이브도 직전 완전 퀀트일을 쓴다(§4-5 C2).
    🔴 **§1-2-b 배제는 원장 생성 «전»** 이다 — 사후 필터는 `rank` 를 밀어 M2·M3 를
    통째로 흔든다.
    """
    from backtest.concept_axes.replayer.loader import universe_snapshot
    excl = exclude or set()
    elig: Dict[Any, Set[str]] = {}
    info: Dict[Any, Dict[str, Any]] = {}
    for d in scan_dates:
        d = pd.Timestamp(d)
        snap = universe_snapshot(uni, d)
        rows = {c: v for c, v in snap["rows"].items() if c not in excl}
        elig[d] = _filter_rows(rows, adapter)
        info[d] = {"eff_date": snap["eff_date"],
                   "universe_fallback": bool(snap["eff_date"] is not None
                                             and snap["eff_date"] != d),
                   "n_universe": len(rows),
                   "n_universe_raw": len(snap["rows"]),
                   "n_eligible": len(elig[d])}
    return elig, info


# ────────────────────────────────────────────────────────────────────────────
# §2-4 — 정렬 · 절단 · 동점
# ────────────────────────────────────────────────────────────────────────────
def rank_and_truncate(scored: Sequence[Tuple[str, float]],
                      max_candidates: int = MAX_CANDIDATES_PER_STRATEGY,
                      count_boundary_tie: bool = False):
    """score 내림차순 · **동점은 `stock_code` 오름차순 안정정렬** 후 상위 N.

    🔴 라이브의 동점 tie-break 는 **비결정적**이다(`get_universe_snapshot` 이
    `ORDER BY` 없이 돌려준 순서가 그대로 `scored` 의 입력 순서가 된다).
    ⇒ 재현기는 코드 오름차순으로 «결정적»으로 깨고, **경계 동점 건수를 인쇄**한다.
    """
    ordered = sorted(scored, key=lambda t: (-t[1], t[0]))
    top = list(ordered[:max_candidates])
    if not count_boundary_tie:
        return top
    n_tie = 0
    if len(ordered) > max_candidates and top:
        edge = top[-1][1]
        # 리뷰 L-3 — **경계 밖 첫 종목이 경계값과 동점일 때만** «경계 동점» 이다.
        #   예전엔 상위 안에서만 동점이어도 세서 «자르기가 흔들렸다» 고 잎혀졌다.
        if ordered[max_candidates][1] != edge:
            n_tie = 0
        else:
            n_tie = sum(1 for _, s in ordered if s == edge)
    return top, n_tie


# ────────────────────────────────────────────────────────────────────────────
# 스캔 루프
# ────────────────────────────────────────────────────────────────────────────
def vintage_adjust_window(win: pd.DataFrame, sub: float) -> pd.DataFrame:
    """🖨️ **인쇄 전용** — 창의 **마지막 봉(D) 하나만** 거래량을 `sub` 만큼 줄인 사본.

    🔑 왜 마지막 봉만인가: 라이브는 D+1 09:00 에 창을 읽는데, 그 시점에
    `D−1` 이하 봉은 D 15:3x 의 7봉 UPSERT 로 **이미 시간외분이 합산돼 있고**
    `D` 봉만 정규장 값이다(`TRACE_M4_channel_2026-09-15.md` §3·§4 —
    delta 가 `overtime_daily.ovtm_vol` 하루치와 단위 주까지 일치한다).
    🔴 판정이 아니다 — 문턱·정렬·룰은 이 함수를 보지 않는다.
    """
    out = win.copy()
    j = out.columns.get_loc("volume")
    out.iloc[-1, j] = max(0.0, float(out.iloc[-1, j]) - float(sub))
    return out


def scan_strategy(px: pd.DataFrame,
                  elig: Dict[Any, Set[str]],
                  adapter,
                  params: Dict[str, Any],
                  lookback: int,
                  scan_dates: Optional[Iterable[Any]] = None,
                  max_candidates: int = MAX_CANDIDATES_PER_STRATEGY,
                  progress_every: int = 300,
                  vintage_vol: Optional[Dict[Tuple[str, Any], float]] = None,
                  vintage_stats: Optional[Dict[str, int]] = None):
    """`(rows, diag, impossible_codes)` — `rows` 는 발화 종목-일 전부(절단 «전»).

    🔑 **DB 왕복 0회** — 벌크 로드된 `px` 만 본다(종목×날짜 왕복 금지).
    🔴 절단은 여기서 하지 않는다 — `ledger.build_ledger` 가 날짜별로 정렬·절단한다.
    🖨️ `vintage_vol` 이 주어지면 **창의 마지막 봉만** 그만큼 줄여 「라이브 09:00 빈티지」를
       근사 복원한다 — **인쇄 전용 보조 판**이고 기본은 `None`(주 게이트 경로 불변).
       `vintage_stats` 를 주면 「보정 적용 / 대응 행 없음」 종목-일 수를 거기에 채운다.
    """
    want = None if scan_dates is None else {pd.Timestamp(d) for d in scan_dates}
    matched: List[Dict[str, Any]] = []
    diag: Dict[Any, Dict[str, int]] = {}
    # C3 판별용 — 「가드로 제외된 종목」을 날짜별로 남긴다(§4-5 C3).
    impossible_codes: Dict[Any, set] = {}
    for d, codes in elig.items():
        if want is None or pd.Timestamp(d) in want:
            diag[pd.Timestamp(d)] = {"n_universe": 0, "n_eligible": len(codes),
                                     "n_no_data": 0, "n_impossible": 0,
                                     "n_evaluated": 0, "n_matched": 0}

    t0 = time.perf_counter()
    total = px["stock_code"].nunique()
    done = 0
    n_vintage_applied = n_vintage_missing = 0
    for code, g in px.groupby("stock_code", sort=False):
        done += 1
        if progress_every and done % progress_every == 0:
            print("      ...{}/{} 종목 · 발화 {:,} · {:.0f}s".format(
                done, total, len(matched), time.perf_counter() - t0),
                file=sys.stderr, flush=True)
        # 🔑 index 를 리셋하지 «않는다» — 플래그 프레임과 행 단위로 조인해야 한다.
        dates = g["date"].to_numpy()
        for i in range(len(g)):
            d = pd.Timestamp(dates[i])
            if want is not None and d not in want:
                continue
            if code not in elig.get(d, ()):  # noqa: PLR6201 - set·dict 둘 다 받는다
                continue
            dg = diag.setdefault(d, {"n_universe": 0, "n_eligible": 0, "n_no_data": 0,
                                     "n_impossible": 0, "n_evaluated": 0, "n_matched": 0})
            win = window_slice(g, i, lookback)
            if vintage_vol is not None:
                _sub = vintage_vol.get((code, d))
                if _sub:
                    win = vintage_adjust_window(win, _sub)
                    n_vintage_applied += 1
                elif (code, d) in vintage_vol:
                    n_vintage_applied += 1          # ovtm_vol = 0 (보정 가능·증분 0)
                else:
                    n_vintage_missing += 1
            if is_impossible(win):
                dg["n_impossible"] += 1
                impossible_codes.setdefault(d, set()).add(code)
                continue
            dg["n_evaluated"] += 1
            verdict = adapter.match(win, params)
            if verdict is None:
                continue
            score, reason = verdict
            prev_close = float(win["close"].iloc[-1])
            if not (prev_close > 0):
                continue
            dg["n_matched"] += 1
            matched.append({
                "scan_date": d, "stock_code": code,
                "score": float(score), "reason": reason,
                "n_bars": int(len(win)), "row_idx": int(g.index[i]),
            })
    # 리뷰 L-2 — 「적격인데 그날 봉이 없어 평가도 못 한」 종목 수를 인쇄한다.
    #   «평가했는데 안 맞았다» 와 «아예 못 봤다» 를 같은 칸에 넣지 않는다.
    for dg in diag.values():
        dg["n_no_bar_at_d"] = max(
            0, dg.get("n_eligible", 0) - dg.get("n_impossible", 0)
            - dg.get("n_evaluated", 0))
    if vintage_stats is not None:
        # 🖨️ 「보정 가능 / 보정 불가」 — 평가한 종목-일 기준. 인쇄만 한다.
        vintage_stats["n_applied"] = n_vintage_applied
        vintage_stats["n_missing"] = n_vintage_missing
    return matched, diag, impossible_codes
