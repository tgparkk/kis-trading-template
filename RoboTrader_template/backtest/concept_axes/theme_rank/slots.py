"""자리 K=10 · 하루 5 기준선 경로와 빈 자리 고정 짝 비교(스펙 §5-4).

기준선 = 현재 순위(원장 rank) 순서 · 같은 종목 보유 중이면 건너뜀(`freq_scenarios.simulate_capped` 와 같은 규칙).
같은 날 테마 쪽은 «기준선이 그날 산 수 f_D» 만큼 S 순으로 고른다(경로가 갈라지지 않게 · 보유 중 제외).
자리 반환: exit_reason=open 은 창 끝까지, 그 밖은 청산 다음 거래일부터 빈다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

import pandas as pd


@dataclass(frozen=True)
class Lot:
    day: int
    code: str
    release: int
    ret: float
    base_rank: int
    sig: float
    main_theme: Optional[int]


def lots_from(df: pd.DataFrame, cal: Sequence[str]) -> Dict[int, List[Lot]]:
    idx = {d: i for i, d in enumerate(cal)}
    n = len(cal)
    out: Dict[int, List[Lot]] = {}
    for r in df.itertuples(index=False):
        if str(r.entry_date) not in idx:
            continue
        day = idx[str(r.entry_date)]
        rel = n if str(r.exit_reason) == "open" else idx[str(r.exit_date)] + 1
        t = None if pd.isna(r.main_theme) or r.main_theme == "" else int(float(r.main_theme))
        out.setdefault(day, []).append(Lot(day, str(r.stock_code), rel, float(r.ret_net), int(r.rank),
                                           float(r.s), t))
    return out


def baseline_path(lots_by_day: Mapping[int, Sequence[Lot]], n_days: int, n_cap: int = 5,
                  k_cap: int = 10) -> Tuple[Dict[int, List[Lot]], Dict[int, FrozenSet[str]]]:
    held: Dict[str, int] = {}
    buys: Dict[int, List[Lot]] = {}
    held_before: Dict[int, FrozenSet[str]] = {}
    for day in range(n_days):
        for c in [c for c, rel in held.items() if rel <= day]:
            del held[c]
        held_before[day] = frozenset(held)
        got: List[Lot] = []
        for lot in sorted(lots_by_day.get(day, ()), key=lambda x: x.base_rank):
            if lot.code in held or len(got) >= n_cap or len(held) >= k_cap:
                continue
            held[lot.code] = lot.release
            got.append(lot)
        buys[day] = got
    return buys, held_before


def pick(eligible: Sequence[Lot], f: int, descending: bool = True, cap_per_theme: Optional[int] = None) -> List[Lot]:
    order = sorted(eligible, key=lambda x: ((-x.sig if descending else x.sig), x.base_rank))
    out: List[Lot] = []
    per: Dict[int, int] = {}
    for lot in order:
        if len(out) >= f:
            break
        if cap_per_theme is not None and lot.main_theme is not None and per.get(lot.main_theme, 0) >= cap_per_theme:
            continue
        out.append(lot)
        if lot.main_theme is not None:
            per[lot.main_theme] = per.get(lot.main_theme, 0) + 1
    return out


@dataclass(frozen=True)
class DayCmp:
    day: int
    f: int
    base: float
    theme: float
    arena: float
    n_eligible: int
    max_same_theme: int


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def paired(lots_by_day: Mapping[int, Sequence[Lot]], buys: Mapping[int, Sequence[Lot]],
           held_before: Mapping[int, FrozenSet[str]], descending: bool = True,
           cap_per_theme: Optional[int] = None) -> List[DayCmp]:
    out: List[DayCmp] = []
    for day in sorted(buys):
        f = len(buys[day])
        eligible = [l for l in lots_by_day.get(day, ()) if l.code not in held_before[day]]
        if f == 0 or not eligible:
            continue
        th = pick(eligible, f, descending, cap_per_theme)
        cnt: Dict[int, int] = {}
        for l in th:
            if l.main_theme is not None:
                cnt[l.main_theme] = cnt.get(l.main_theme, 0) + 1
        out.append(DayCmp(day, f, _mean([l.ret for l in buys[day]]), _mean([l.ret for l in th]),
                          _mean([l.ret for l in eligible]), len(eligible), max(cnt.values(), default=0)))
    return out


def summarize(cmps: Sequence[DayCmp]) -> Dict[str, float]:
    w = sum(c.f for c in cmps)
    if not w:
        return dict(R_base=float("nan"), R_theme=float("nan"), R_arena=float("nan"), d_cur=float("nan"),
                    d_theme=float("nan"), n_days=0, n_lots=0, share_same_theme3=float("nan"))
    rb = sum(c.f * c.base for c in cmps) / w
    rt = sum(c.f * c.theme for c in cmps) / w
    ra = sum(c.f * c.arena for c in cmps) / w
    return dict(R_base=rb, R_theme=rt, R_arena=ra, d_cur=ra - rb, d_theme=rt - ra, n_days=len(cmps), n_lots=w,
                share_same_theme3=sum(1 for c in cmps if c.max_same_theme >= 3) / len(cmps))
