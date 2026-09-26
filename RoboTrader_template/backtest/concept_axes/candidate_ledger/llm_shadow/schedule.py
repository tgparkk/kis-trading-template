"""§3-2 · §3-3 채점 조건 · 상한 · 우선순위 · 이월 · 성수기 🔒 (순수 함수 · DB 없음).

- (A) 자료 변경 = 새 B·I 원공시 또는 새 기사(`inputs.new_item_codes`) · (A)면 그날 (B) 아님.
- (B) 순환 = 마지막 **ok** 채점 뒤 20거래일 · 가족 첫 20거래일은 조각 k = sha256("20261004:"+family+":"+code) mod 20
  번째 날(0부터) · 뒤에 들어온 종목(가족 첫날 U 에 없던 종목)은 U 에 처음 들어온 날 (B).
- 우선순위 = ① 전날 이월된 (A) ② 그날 (A) ③ (B)(가장 오래 밀린 순 → 조각 → 코드) · 상한 360.
  ①·② 가 넘치면 `default_rng([20261004, 87, yyyymmdd(D)])` 로 채운다(① 먼저, 남은 자리를 ② 에서).
  못 든 ② = `skipped_cap`(다음 날 1회 이월) · 이월된 날에도 못 든 ① = `dropped_carry`.
- 성수기 날 = ①+② ≥ 360 ⇒ 그날 (B) 정지((B) 는 제한 없이 밀린다 · 행을 쓰지 않는다).
- `skipped_cap`·`parse_error`·`timeout` 은 순환 시계를 리셋하지 않는다 — `last_ok_idx` 는 ok 만 넣는다(호출자 몫).
- 인덱스 = 가족 첫 D(=0)부터 센 KOSPI 거래일 순번.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set

import numpy as np

from . import settings as S


def yyyymmdd(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def rng_of(x: int, d: date) -> np.random.Generator:
    return np.random.default_rng([S.SEED_BASE, x, yyyymmdd(d)])


def slice_of(family: str, code: str) -> int:
    """조각 k(§3-2) — 난수 아님."""
    return int(hashlib.sha256(f"{S.SLICE_KEY}:{family}:{code}".encode("utf-8")).hexdigest(), 16) % S.ROTATION_TD


@dataclass
class Cell:
    code: str
    trigger: str                 # 'A' | 'B'
    carried: bool
    slice: int
    gap_td: Optional[int]        # 직전 ok 채점과의 거래일 간격(없으면 None)
    planned: str                 # 'call' | skipped_cap | dropped_carry
    due_since: Optional[int] = None


@dataclass
class Schedule:
    cells: List[Cell]
    peak_day: bool
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def called(self) -> List[Cell]:
        return [c for c in self.cells if c.planned == "call"]


def _pick(rng: np.random.Generator, codes: List[str], n: int) -> List[str]:
    """코드 정렬 목록에서 n 개 비복원(rng 순열 앞 n개)."""
    order = sorted(codes)
    if len(order) <= n:
        return order
    perm = rng.permutation(len(order))[:n]
    return [order[i] for i in perm]


def build_schedule(family: str, D: date, n: int, universe: List[str], a_today: Set[str], carried_in: Set[str],
                   last_ok_idx: Dict[str, int], first_seen_idx: Dict[str, int], rules: str,
                   cap: int = S.DAILY_CAP) -> Schedule:
    U = set(universe)
    c1_all = sorted(carried_in)
    c1 = [c for c in c1_all if c in U]
    c1_gone = [c for c in c1_all if c not in U]
    c2 = sorted((set(a_today) & U) - set(c1))
    peak = len(c1) + len(c2) >= cap
    rng = rng_of(S.SEED_A_FILL, D)
    sel1 = _pick(rng, c1, cap)
    sel2 = _pick(rng, c2, cap - len(sel1))

    def gap(code: str) -> Optional[int]:
        return (n - last_ok_idx[code]) if code in last_ok_idx else None

    cells: List[Cell] = []
    s1, s2 = set(sel1), set(sel2)
    for c in c1:
        cells.append(Cell(c, "A", True, slice_of(family, c), gap(c), "call" if c in s1 else S.ST_DROP))
    for c in c1_gone:
        cells.append(Cell(c, "A", True, slice_of(family, c), gap(c), S.ST_DROP))
    for c in c2:
        cells.append(Cell(c, "A", False, slice_of(family, c), gap(c), "call" if c in s2 else S.ST_SKIP))

    due: List[Cell] = []
    if rules != "A_only" and not peak:
        taken = set(c1) | set(c2)
        for c in U - taken:
            k = slice_of(family, c)
            if c in last_ok_idx:
                since = last_ok_idx[c] + S.ROTATION_TD
            else:
                fs = first_seen_idx.get(c, n)
                since = fs if fs > 0 else k          # 뒤에 들어온 종목 = 첫날 · 첫날 U 종목 = 조각 날
            if n >= since:
                due.append(Cell(c, "B", False, k, gap(c), "call", since))
        due.sort(key=lambda x: (x.due_since, x.slice, x.code))
        room = max(0, cap - len(sel1) - len(sel2))
        cells.extend(due[:room])
    counts = dict(n_u=len(U), n_a_today=len(set(a_today) & U), n_a_carried=len(c1_all), n_b_due=len(due),
                  n_sel_a=len(sel1) + len(sel2), n_sel_b=min(len(due), max(0, cap - len(sel1) - len(sel2))),
                  n_skipped_cap=len(c2) - len(sel2), n_dropped_carry=len(c1) - len(sel1) + len(c1_gone))
    return Schedule(cells=cells, peak_day=peak, counts=counts)
