"""로트·이벤트 단위 순수 계산 — 사전등록 §3(제외 규칙)·§4(창 지표)·§6(T3 두 arm·진입 당일·H 종료·판 L/M·데이터 처리).

DB 없음. 가격 행은 호출자(`run.py`)가 `DayRow` 로 넣는다(원시 OHLC · 🔴 adj_factor 를 곱하지 않는다).
- 유효 봉 = high·low·close 비결측 ∧ volume > 0(§3 X2). 경로 봉(`Bar`)은 시가까지 있어야 만든다 — 아니면 None(거래 불가 §6-7).
- 진입 당일(k=0) 기준 §6-2: ① DB SELL 일 = 매수일 → `day0_live_exit`(시뮬 없이 실제 사유·가격) · ② 체결 ≤ 09:05 →
  `BASIS_D_OPEN` · ③ 그 밖 → 체결 분봉 «뒤» 분봉이 있으면 그것만 모은 `touch_bar` · 없으면 `BASIS_ACTUAL`(+플래그).
- H 종료 평가(§6-1·§6-7): H 번째 봉 유효 → 그 종가 · 아니면 D_asof 안 첫 유효 봉 시가(정지 후 재개 · 판 하나) ·
  재개 없음(영구 끊김) → 판 L = 0 원(−100%) · 판 M = H 안 마지막 유효 종가.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Dict, List, Optional, Sequence, Set, Tuple

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import fidelity8 as F
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar

from . import author_exit as AE

H = 20                          # §6-1 관측 기간(거래일)
EARLY_FILL = time(9, 5, 0)      # §6-2 ② — ledger8 run.py:254 규약(≤ 09:05 면 진입일 고저)
LOOKBACK_BARS = 60              # §6-7 로트 구간 [진입 − 60봉, 진입 + H]
JUMP_LO, JUMP_HI = 0.69, 1.31   # §3 X3 (i) · §6-7
EPISODE_GAP = 5                 # §3 X4
BASIS_TOUCH = "after_fill_minutes"
DAY0_LIVE = "day0_live_exit"
FLAG_DAY0_LIVE = "day0_live_exit"
FLAG_DAY0_ACTUAL = "day0_actual_basis(진입일 터치 미반영)"
KIND_H_CLOSE, KIND_RESUME, KIND_CUT = "h_close", "resume_open", "cut"


@dataclass(frozen=True)
class DayRow:
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    vol20: Optional[float] = None

    def valid(self) -> bool:
        return (self.high is not None and self.low is not None and self.close is not None
                and self.volume is not None and self.volume > 0)


Rows = Dict[date, DayRow]
PathT = List[Tuple[int, date, Optional[Bar]]]


def to_bar(d: date, r: Optional[DayRow]) -> Optional[Bar]:
    if r is None or not r.valid() or r.open is None:
        return None
    return Bar(d, float(r.open), float(r.high), float(r.low), float(r.close))


def build_path(rows: Rows, cal: Sequence[date], i0: int, i1: int) -> PathT:
    """KOSPI 달력 i0(진입일 · k=0) ~ i1 → [(k, 날짜, Bar|None)] · None = 거래 불가(거래량 0·결측)."""
    return [(i - i0, cal[i], to_bar(cal[i], rows.get(cal[i]))) for i in range(i0, i1 + 1)]


def pre_closes(rows: Rows, d0: date) -> List[float]:
    """진입일 «전» 유효 봉 종가(오름차순) — SMA60 용."""
    return [float(rows[d].close) for d in sorted(rows) if d < d0 and rows[d].valid()]


def sma_first_date(rows: Rows, d0: date) -> Optional[date]:
    """부록 A5 — 진입일 SMA60 창(진입일까지 유효 봉 60개)의 첫 봉 날짜 · 60개 미만이면 가용 첫 유효 봉 · 없으면 None."""
    valid = [d for d in sorted(rows) if d <= d0 and rows[d].valid()]
    if not valid:
        return None
    return valid[-AE.SMA_N] if len(valid) >= AE.SMA_N else valid[0]


# ── 로트 입력 · 진입 당일 기준 ─────────────────────────────────────────────
@dataclass
class LotIn:
    buy_id: int
    strategy: str
    code: str
    buy_ts: datetime                  # KST naive
    buy_price: float
    qty: int
    sell_id: Optional[int] = None
    sell_ts: Optional[datetime] = None
    sell_reason: Optional[str] = None
    sell_price: Optional[float] = None

    @property
    def d0(self) -> date:
        return self.buy_ts.date()


def is_day0_live(lot: LotIn) -> bool:
    """§6-2 ① — DB SELL 일(KST) = 매수일."""
    return lot.sell_ts is not None and lot.sell_ts.date() == lot.d0


def touch_bar_after(d: date, minutes: Sequence[Tuple[str, Bar]], fill: time) -> Optional[Bar]:
    """§6-2 ③ — 체결 시각이 든 분봉 «뒤» 분봉만 모은 봉(시작 시각 > 체결 분 시작). 없으면 None."""
    cut = f"{fill.hour:02d}{fill.minute:02d}00"
    rest = [b for t, b in minutes if X._hhmmss(t) > cut]
    if not rest:
        return None
    return Bar(d, float(rest[0].open), max(float(b.high) for b in rest), min(float(b.low) for b in rest),
               float(rest[-1].close))


def day0_basis(lot: LotIn, minutes: Sequence[Tuple[str, Bar]]) -> Tuple[str, Optional[Bar]]:
    """§6-2 ②③ 기준(① 여부와 무관 — ① 손절 로트의 ⓐ 도 이 기준으로 진입 당일 익절 터치를 본다)."""
    if lot.buy_ts.time() <= EARLY_FILL:
        return X.BASIS_D_OPEN, None
    tb = touch_bar_after(lot.d0, minutes, lot.buy_ts.time())
    return (BASIS_TOUCH, tb) if tb is not None else (X.BASIS_ACTUAL, None)


def day0_class(lot: LotIn, basis: str) -> str:
    """봉인 인쇄용 ①②③ 분류."""
    return DAY0_LIVE if is_day0_live(lot) else basis


def make_pos(lot: LotIn, basis: str, touch: Optional[Bar], aware) -> X.Pos:
    return X.Pos(lot.code, lot.d0, aware(lot.buy_ts), float(lot.buy_price), int(lot.qty or 1), basis, touch)


# ── H 종료 평가 · arm 결과 ────────────────────────────────────────────────
@dataclass(frozen=True)
class Terminal:
    kind: str
    k: Optional[int]
    day: Optional[date]
    px_L: float
    px_M: float


def terminal(path_full: PathT, horizon: int, entry_price: float) -> Terminal:
    """남은 지분의 H 종료 값(§6-1·§6-7) — path_full 은 진입일 ~ D_asof."""
    if len(path_full) <= horizon:
        raise ValueError(f"경로가 H={horizon} 보다 짧다({len(path_full) - 1}) — 모집단 규칙(위치+20 ≤ D_asof) 위반")
    _, dh, bh = path_full[horizon]
    if bh is not None:
        return Terminal(KIND_H_CLOSE, horizon, dh, float(bh.close), float(bh.close))
    for k, d, b in path_full[horizon + 1:]:
        if b is not None:
            return Terminal(KIND_RESUME, k, d, float(b.open), float(b.open))
    before = [(k, d, b) for k, d, b in path_full[:horizon] if b is not None]
    if before:
        k, d, b = before[-1]
        return Terminal(KIND_CUT, k, d, 0.0, float(b.close))
    return Terminal(KIND_CUT, None, None, 0.0, float(entry_price))


@dataclass
class ArmOut:
    reason: str
    tranches: List[Tuple[int, float, float]]      # (k, 지분, 가격)
    remaining: float
    term: Optional[Terminal]
    ret_L: float
    ret_M: float
    hold: Optional[int]
    flags: List[str] = field(default_factory=list)
    triggers: Tuple[str, ...] = ()
    trigger_k: Optional[int] = None

    @property
    def cut(self) -> bool:
        return self.term is not None and self.term.kind == KIND_CUT and self.remaining > 0


def _value(entry: float, tranches: Sequence[Tuple[int, float, float]], remaining: float,
           term: Optional[Terminal]) -> Tuple[float, float]:
    real = sum(w * p for _, w, p in tranches)
    if remaining > 0 and term is None:
        raise ValueError("남은 지분이 있는데 H 종료 평가가 없다")
    vl = real + (remaining * term.px_L if remaining > 0 else 0.0)
    vm = real + (remaining * term.px_M if remaining > 0 else 0.0)
    return (vl / entry - 1.0) * 100.0, (vm / entry - 1.0) * 100.0


def _arm(entry: float, reason: str, tranches, remaining: float, path_full: PathT, horizon: int,
         flags: Sequence[str], triggers: Tuple[str, ...] = (), trigger_k: Optional[int] = None) -> ArmOut:
    term = terminal(path_full, horizon, entry) if remaining > 0 else None
    rl, rm = _value(entry, tranches, remaining, term)
    hold = (term.k if term is not None else (tranches[-1][0] if tranches else None))
    return ArmOut(reason, list(tranches), remaining, term, rl, rm, hold, list(flags), triggers, trigger_k)


def b_arm(lot: LotIn, rules: X.ExitRules, path_full: PathT, probe: X.Probe, basis: str, touch: Optional[Bar],
          aware, horizon: int = H) -> ArmOut:
    """ⓑ 현행 — ① 이면 DB SELL 실제 사유·가격 · 아니면 `exitsim8.simulate_lot`(H 로 자른 경로) + H 종료 평가."""
    entry = float(lot.buy_price)
    if is_day0_live(lot):
        return _arm(entry, F.actual_reason(lot.sell_reason), [(0, 1.0, float(lot.sell_price))], 0.0, path_full,
                    horizon, [FLAG_DAY0_LIVE])
    ex = X.simulate_lot(make_pos(lot, basis, touch, aware), rules, path_full[:horizon + 1], probe)
    flags = list(ex.flags) + ([FLAG_DAY0_ACTUAL] if basis == X.BASIS_ACTUAL else [])
    if ex.closed:
        return _arm(entry, ex.reason, [(int(ex.hold_days), 1.0, float(ex.price))], 0.0, path_full, horizon, flags)
    return _arm(entry, X.EXIT_OPEN, [], 1.0, path_full, horizon, flags)


def b_full(lot: LotIn, rules: X.ExitRules, path_full: PathT, probe: X.Probe, basis: str, touch: Optional[Bar],
           aware) -> X.ExitOut:
    """ⓑ 를 H 로 자르지 않은 경로(진입일 ~ D_asof) — 충실도(§6-8) 용. ① 은 호출자가 분모에서 뺀다."""
    return X.simulate_lot(make_pos(lot, basis, touch, aware), rules, path_full, probe)


def a_arm(lot: LotIn, rules: X.ExitRules, path_full: PathT, probe: X.Probe, basis: str, touch: Optional[Bar],
          aware, closes_before: Sequence[float], b_out: ArmOut, horizon: int = H,
          no_react_k: int = AE.NO_REACT_K) -> ArmOut:
    """ⓐ 저자식 — ① 이고 실제 사유가 손절이 아니면 ⓑ 와 같은 실제 청산(Δ=0). 그 밖은 `author_exit` + H 종료 평가."""
    entry = float(lot.buy_price)
    if is_day0_live(lot) and F.actual_reason(lot.sell_reason) != X.EXIT_SL:
        return ArmOut(b_out.reason, list(b_out.tranches), b_out.remaining, b_out.term, b_out.ret_L, b_out.ret_M,
                      b_out.hold, list(b_out.flags) + ["day0_live_exit(Δ=0)"])
    ao = AE.author_exit(make_pos(lot, basis, touch, aware), rules, path_full, probe, closes_before, horizon,
                        no_react_k)
    tr = [(t.k, t.weight, t.price) for t in ao.tranches]
    reason = ao.reason if ao.closed else X.EXIT_OPEN
    return _arm(entry, reason, tr, ao.remaining, path_full, horizon, ao.flags, ao.triggers, ao.trigger_k)


# ── 데이터 처리(§3 X3 · §6-7) ─────────────────────────────────────────────
def jump_in(rows: Rows, days: Sequence[date]) -> bool:
    """원시 종가 일간 비율(연속한 종가 있는 행끼리) ≤ 0.69 또는 ≥ 1.31 이 있나."""
    cs = [float(rows[d].close) for d in days if d in rows and rows[d].close is not None and rows[d].close > 0]
    return any(b / a <= JUMP_LO or b / a >= JUMP_HI for a, b in zip(cs, cs[1:]))


def any_date_in(dates: Sequence[date], lo: date, hi: date) -> bool:
    return any(lo <= d <= hi for d in dates)


def lot_exclusion(rows: Rows, cal: Sequence[date], i0: int, i_end: int, split_dates: Sequence[date],
                  rights_dates: Sequence[date], sma_first: Optional[date] = None) -> Tuple[Tuple[str, ...], bool]:
    """§6-7 — 로트 구간 [min(진입 − 60 KOSPI 거래일, SMA60 첫 봉)(부록 A5), i_end] → (제외 사유들, 유상증자 있음)."""
    if i0 - LOOKBACK_BARS < 0:
        raise ValueError("달력이 진입 − 60봉을 덮지 못한다 — 달력·봉 시작일을 앞당길 것")
    lo = cal[i0 - LOOKBACK_BARS] if sma_first is None else min(cal[i0 - LOOKBACK_BARS], sma_first)
    days = [d for d in cal[:i_end + 1] if d >= lo]
    why: List[str] = []
    if jump_in(rows, days):
        why.append("jump")
    if any_date_in(split_dates, days[0], days[-1]):
        why.append("split_bonus")
    return tuple(why), any_date_in(rights_dates, days[0], days[-1])


# ── T1/T2 창 지표(§4) ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class Win:
    complete: bool
    n_valid: int = 0
    x2: bool = False
    jump: bool = False
    corp: bool = False
    rights: bool = False
    hi: Optional[float] = None
    lo: Optional[float] = None

    @property
    def x3(self) -> bool:
        return self.jump or self.corp


def window(rows: Rows, cal: Sequence[date], i_t: int, h: int, i_asof: int, split_dates: Sequence[date],
           rights_dates: Sequence[date], extremes: bool = True) -> Win:
    """창 = t 다음 KOSPI 거래일부터 h 거래일(t 제외) · X1 완결 · X2 유효봉 < ⌈h/2⌉ · X3 창 [t, t+h] 점프·분할/무상.

    extremes=False 면 창 고가·저가를 계산하지 않는다(봉인 단계의 이벤트 팔 — R′/D′ 재료를 만들지 않는다).
    """
    if i_t + h > i_asof:
        return Win(False)
    days = cal[i_t + 1:i_t + h + 1]
    valid = [rows[d] for d in days if d in rows and rows[d].valid()]
    span = cal[i_t:i_t + h + 1]
    hi = max(float(r.high) for r in valid) if (valid and extremes) else None
    lo = min(float(r.low) for r in valid) if (valid and extremes) else None
    return Win(True, len(valid), len(valid) < math.ceil(h / 2), jump_in(rows, span),
               any_date_in(split_dates, span[0], span[-1]), any_date_in(rights_dates, span[0], span[-1]), hi, lo)


def rise(w: Win, base: float) -> Optional[float]:
    return None if w.hi is None or not base else w.hi / float(base) - 1.0


def fall(w: Win, base: float) -> Optional[float]:
    return None if w.lo is None or not base else w.lo / float(base) - 1.0


# ── 에피소드(§3 X4) · 블록(§7) ─────────────────────────────────────────────
def episode_keep(events: Sequence[Tuple[int, str, str, datetime]], pos_of: Dict[date, int]) -> Set[int]:
    """(id, 전략, 종목, 시각) → 남길 id. 같은 (전략, 종목)의 앞선 «포함» 이벤트로부터 ≤ 5 KOSPI 거래일이면 뺀다."""
    keep: Set[int] = set()
    last: Dict[Tuple[str, str], int] = {}
    for eid, strat, code, ts in sorted(events, key=lambda e: (e[1], e[2], e[3], e[0])):
        p = pos_of[ts.date()]
        key = (strat, code)
        if key in last and p - last[key] <= EPISODE_GAP:
            continue
        keep.add(eid)
        last[key] = p
    return keep


def episode_keep_chain(events: Sequence[Tuple[int, str, str, datetime]], pos_of: Dict[date, int]) -> Set[int]:
    """인쇄 비교용(부록 A4) — DART 식 «직전 이벤트(남김 여부 무관)부터 ≤ 5 거래일이면 뺀다» 연쇄 규칙."""
    keep: Set[int] = set()
    last: Dict[Tuple[str, str], int] = {}
    for eid, strat, code, ts in sorted(events, key=lambda e: (e[1], e[2], e[3], e[0])):
        p = pos_of[ts.date()]
        key = (strat, code)
        if not (key in last and p - last[key] <= EPISODE_GAP):
            keep.add(eid)
        last[key] = p
    return keep


def blocks_of(days: Sequence[date], size: int = 5) -> Dict[date, int]:
    """연속 거래일을 size 일씩 자른 블록 번호 — 마지막 블록이 size 일 미만이면 앞 블록에 합친다(§7)."""
    n = len(days)
    nb = max(1, n // size)
    return {d: min(i // size, nb - 1) for i, d in enumerate(days)}


def tdist(pos_of: Dict[date, int], a: date, b: date) -> int:
    return pos_of[b] - pos_of[a]
