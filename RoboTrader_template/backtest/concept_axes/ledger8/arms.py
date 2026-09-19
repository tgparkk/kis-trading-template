"""세 arm 로트 엔진 — 순수(DB·전략 인스턴스 없음 · 청산은 주입된 탐침).

| arm | 무엇 | 로트 |
|---|---|---|
| A_actual | virtual_trading_records 실제 체결(진실값 · gross) | 실제 매수 1건 = 1 |
| A_sim | A_actual 매수를 B 와 «같은» 진입·청산 시뮬에 통과 — A vs B 비교는 시뮬 대 시뮬로만(스펙 §4-5) | 실제 매수 1건 = 1 |
| B1 | 서로 다른 계좌 — 같은 종목을 또 사면 별도 로트, 로트마다 자기 매입가로 손절·익절 | 체결 1건 = 1 |
| B2 | 한 계좌 — 또 사면 평단 합산, 합산 평단으로 손절·익절·trail · 보유기한은 첫 매수부터(D4-a) | (전략, 종목) 연속 보유 = 1 |

🔴 총자산·누적수익률·자본 대비 % 금지 — 건별 %, 원(정수), 명목 가중 수익률(Σ손익/Σ명목)만.
🔑 B2 는 B1 을 걸러서 못 만든다(평단이 바뀌면 손절·익절 시점 자체가 바뀐다) — 신호(Fill)는 공유, 시뮬은 두 벌.
🔑 같은 날 시간선은 B1·B2 가 같다 — 09:00 시가 단계(보유기간·갭 익절) 청산은 09:02 진입 «전», 데이터 청산·손절·
   터치는 «후»(B2 는 추가매수 뒤 판정 · B1 은 그 로트를 «열림»으로 센다). D3′ 해제 뒤 진입은 그날 청산을 전부 «전»으로 본다.
B2 하루 순서: 09:00 open_phase(기존 평단) → 09:02 추가매수(평단 갱신) → after_open(새 평단 · band_touch 추가면 그날 터치 생략).
            해제 뒤 추가매수(D3′)는 after_open(기존 평단) 먼저 → 살아 있으면 추가(그날 터치는 이미 봤다).
A3 상한 민감도(`basis=daily_upper_bound` · `exitsim8.lift_upper_bound`) — 해제 뒤 진입이라 시간선은 after_lift 와 같고,
   체결 시각 불명이라 진입일 터치는 안 쓴다(NO_D_TOUCH). 열린 B2 계좌에 붙으면 `FLAG_ADD_UNKNOWN`. 엔진은 tier 를 보지
   않는다 — 본 집계 분리(상한 체결은 main 밖 tier)는 호출자 몫. 가격 ≤ 0(·NaN) 체결은 포지션을 만들지 않는다(건너뜀+경고).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from backtest.concept_axes.minervini.cap_skip_ledger import tradecal as T
from backtest.concept_axes.minervini.cap_skip_ledger.classify import Trade

from . import exitsim8 as X
from . import registry as R

CLOCK_FIRST = "first"          # D4-a(적용) — 보유기한은 첫 매수부터
CLOCK_LAST_ADD = "last_add"    # D4-b(반대편 기록) — 추가매수마다 시계 리셋(라이브 on_order_filled 덮어쓰기와 같은 효과)

FLAG_ADD_UNKNOWN = "add_unknown(상한 체결이 그날 열린 계좌에 붙음 — 추가매수 여부·시각 불명)"   # A3 · 과제 10 분리 집계
_AFTER_LIFT = (X.BASIS_LIFT, X.BASIS_UPPER)   # 해제 뒤 진입 — 그날 청산을 전부 «전»으로 본다(B1 `_open_on` = B2 순서)

_log = logging.getLogger(__name__)

PathFn = Callable[[str, date], X.PathT]
ProbeFor = Callable[[str], X.Probe]
TimeFn = Callable[[date], datetime]


def _won(x: float) -> int:
    return int(round(x))


@dataclass(frozen=True)
class Fill:
    folder: str
    code: str
    d: date
    price: float
    basis: str                          # D_open | band_touch | actual | after_lift | daily_upper_bound(A3 상한)
    qty: int
    qty_basis: str                      # amount | one_share | actual
    tier: str = R.TIER_MAIN             # 엔진은 안 본다(main·ext·offlist·상한 전용 tier 등 — 분리 집계는 호출자)
    signal_basis: str = ""
    crash_blocked: bool = False
    other_holder_live: str = ""
    buy_id: Optional[int] = None        # A_sim — 원 체결 id
    entry_time: Optional[datetime] = None
    touch_bar: Optional[X.Bar] = None   # after_lift — 진입 뒤 분봉만 모은 봉
    lift_time: str = ""                 # after_lift — 체결 분봉 시각
    d5: str = ""                        # D5 — 라이브였다면 막혔을 속도 조절 규칙(쉼표 목록)


@dataclass
class Lot:
    lot_id: str
    fill: Fill
    exit: X.ExitOut
    is_repeat_while_open: bool = False
    open_lot_seq: int = 1
    days_since_open_lot: Optional[int] = None

    @property
    def notional_won(self) -> int:
        return _won(self.fill.price * self.fill.qty)

    @property
    def pnl_won(self) -> Optional[int]:
        return None if self.exit.price is None else _won((self.exit.price - self.fill.price) * self.fill.qty)


def _pos(f: Fill, t: datetime) -> X.Pos:
    return X.Pos(f.code, f.d, t, float(f.price), int(f.qty), f.basis, touch_bar=f.touch_bar)


def _priced(fills: Sequence[Fill]) -> List[Fill]:
    """가격 ≤ 0·NaN 체결은 포지션을 만들지 않는다(수익률·평단 0 나눗셈 — `lift_upper_bound` 에 0원 가드 없음)."""
    out: List[Fill] = []
    for f in fills:
        if f.price > 0:
            out.append(f)
        else:
            _log.warning("ledger8 arms: price %r fill skipped (%s %s %s basis=%s tier=%s)",
                         f.price, f.folder, f.code, f.d, f.basis, f.tier)
    return out


def _open_on(lot: Lot, d: date, after_lift: bool = False) -> bool:
    """날짜 d 의 새 진입 시각에 이 로트가 아직 열려 있었나 — B2 계좌와 같은 시간선."""
    e = lot.exit
    if not e.closed:
        return True
    if e.exit_date is None or e.exit_date < d:
        return False
    if e.exit_date > d:
        return True
    if after_lift:
        return False
    return e.phase != X.PHASE_OPEN


def run_lots(fills: Sequence[Fill], rules: Dict[str, X.ExitRules], path_fn: PathFn, probe_for: ProbeFor,
             cal: Sequence[date], time_fn: TimeFn, prefix: str) -> List[Lot]:
    """체결 1건 = 로트 1개(B1 · A_sim · 부록). 같은 (전략, 종목)에 열린 로트가 있으면 반복 플래그."""
    lots: List[Lot] = []
    by_key: Dict[Tuple[str, str], List[Lot]] = {}
    for i, f in enumerate(sorted(_priced(fills), key=lambda x: (x.d, x.folder, x.code, x.buy_id or 0))):
        ex = X.simulate_lot(_pos(f, f.entry_time or time_fn(f.d)), rules[f.folder], path_fn(f.code, f.d),
                            probe_for(f.folder))
        prev = [lot for lot in by_key.get((f.folder, f.code), []) if _open_on(lot, f.d, f.basis in _AFTER_LIFT)]
        since = (len(T.days_in_range(cal, min(lot.fill.d for lot in prev), f.d)) - 1) if prev else None
        lot = Lot(f"{prefix}-{i:04d}", f, ex, bool(prev), len(prev) + 1, since)
        by_key.setdefault((f.folder, f.code), []).append(lot)
        lots.append(lot)
    return lots


@dataclass
class Account:
    acct_id: str
    folder: str
    code: str
    fills: List[Fill]
    qty: int
    avg_price: float
    avg_path: List[float]
    exit: Optional[X.ExitOut] = None
    flags: List[str] = field(default_factory=list)
    hold_clock_reset_diff: str = ""
    avg_flip: str = ""

    @property
    def first_date(self) -> date:
        return self.fills[0].d

    @property
    def n_adds(self) -> int:
        return len(self.fills) - 1

    @property
    def notional_won(self) -> int:
        return _won(sum(f.price * f.qty for f in self.fills))

    @property
    def pnl_won(self) -> Optional[int]:
        if self.exit is None or self.exit.price is None:
            return None
        return _won((self.exit.price - self.avg_price) * self.qty)

    def add(self, f: Fill) -> None:
        self.avg_price = (self.avg_price * self.qty + f.price * f.qty) / (self.qty + f.qty)
        self.qty += f.qty
        self.fills.append(f)
        self.avg_path.append(self.avg_price)


def _simulate_account(fl: Sequence[Fill], i: int, rules: X.ExitRules, path_fn: PathFn, probe: X.Probe,
                      time_fn: TimeFn, clock: str, acct_id: str) -> Tuple[Account, int]:
    f0 = fl[i]
    i += 1
    acct = Account(acct_id, f0.folder, f0.code, [f0], int(f0.qty), float(f0.price), [float(f0.price)])
    clock_d, clock_t, k0 = f0.d, (f0.entry_time or time_fn(f0.d)), 0

    def pos(basis: str, touch: Optional[X.Bar] = None) -> X.Pos:
        return X.Pos(f0.code, clock_d, clock_t, acct.avg_price, acct.qty, basis, touch_bar=touch)

    path = list(path_fn(f0.code, f0.d))
    if not path:
        acct.exit = X.ExitOut("open", X.EXIT_OPEN, None, None, None, None, ["no_path"])
        return acct, i
    ex = X.entry_day(pos(f0.basis, f0.touch_bar), rules, path[0][2], probe)
    if ex is not None:
        acct.exit = ex
        return acct, i
    if f0.basis != X.BASIS_D_OPEN and f0.touch_bar is None:
        acct.flags.append(X.FLAG_NO_D_TOUCH)
    last: Optional[Tuple[int, date, X.Bar]] = (0, path[0][1], path[0][2]) if path[0][2] is not None else None
    pending = False
    for k, day, bar in path[1:]:
        kk = k - k0
        if bar is None:
            acct.flags.append(f"{X.FLAG_BAR_MISSING}:{day}")
            if kk >= rules.max_hold_days:
                pending = True
            continue
        ex = X.open_phase(pos(X.BASIS_D_OPEN), rules, kk, bar, pending)
        if ex is not None:                      # 같은 날 신호는 바깥 루프에서 새 계좌가 된다
            acct.exit = ex
            return acct, i
        add = fl[i] if (i < len(fl) and fl[i].d == day) else None
        if add is not None and add.basis in _AFTER_LIFT:
            ex = X.after_open(pos(X.BASIS_D_OPEN), rules, kk, day, bar, probe)     # 해제 전(기존 평단) 판정 먼저
            if ex is not None:
                acct.exit = ex
                return acct, i                                                   # 해제 뒤 체결은 새 계좌
            i += 1
            acct.add(add)
            acct.flags.append(f"{X.FLAG_LIFT_ADD if add.basis == X.BASIS_LIFT else FLAG_ADD_UNKNOWN}:{day}")
            if clock == CLOCK_LAST_ADD:
                clock_d, clock_t, k0, kk = day, (add.entry_time or time_fn(day)), k, 0
            last = (kk, day, bar)
            continue
        touches = True
        if add is not None:
            i += 1
            acct.add(add)
            if clock == CLOCK_LAST_ADD:
                clock_d, clock_t, k0, kk = day, (add.entry_time or time_fn(day)), k, 0
            if add.basis != X.BASIS_D_OPEN:
                touches = False
                acct.flags.append(f"{X.FLAG_TOUCH_SKIPPED_ADD}:{day}")
        ex = X.after_open(pos(X.BASIS_D_OPEN), rules, kk, day, bar, probe, touches=touches)
        if ex is not None:
            acct.exit = ex
            return acct, i
        last = (kk, day, bar)
    acct.exit = X.mark_to_market(pos(X.BASIS_D_OPEN), last, [])
    return acct, i


def run_accounts(fills: Sequence[Fill], rules: Dict[str, X.ExitRules], path_fn: PathFn, probe_for: ProbeFor,
                 time_fn: TimeFn, clock: str = CLOCK_FIRST) -> List[Account]:
    """(전략, 종목)별 한 계좌. 전량 청산 뒤 신호가 오면 새 계좌."""
    by_key: Dict[Tuple[str, str], List[Fill]] = {}
    for f in _priced(fills):
        by_key.setdefault((f.folder, f.code), []).append(f)
    tag = "B2r" if clock == CLOCK_LAST_ADD else "B2"
    out: List[Account] = []
    for key in sorted(by_key):
        fl = sorted(by_key[key], key=lambda x: x.d)
        i = 0
        while i < len(fl):
            acct, i = _simulate_account(fl, i, rules[key[0]], path_fn, probe_for(key[0]), time_fn, clock,
                                        f"{tag}-{len(out):04d}")
            out.append(acct)
    return out


def mark_clock_diff(first: Sequence[Account], reset: Sequence[Account]) -> None:
    """D4 반대편 기록 — 추가매수마다 시계를 리셋했으면 청산(사유·날짜)이 달라졌을 계좌."""
    by_start = {(a.folder, a.code, a.first_date): a for a in reset}
    for a in first:
        if a.n_adds == 0:
            a.hold_clock_reset_diff = "n/a(추가매수 없음)"
            continue
        b = by_start.get((a.folder, a.code, a.first_date))
        if b is None or a.exit is None or b.exit is None:
            a.hold_clock_reset_diff = "account_split_differs"
            continue
        same = (a.exit.reason, a.exit.exit_date) == (b.exit.reason, b.exit.exit_date)
        a.hold_clock_reset_diff = "same" if same else f"diff:{b.exit.reason}@{b.exit.exit_date}"


def mark_avg_flip(accounts: Sequence[Account], b1_lots: Sequence[Lot]) -> None:
    """평단 이동 효과 — 같은 첫 체결의 B1 로트와 B2 계좌의 청산 비교(same · date_only · reason:a→b)."""
    first_lot = {(lot.fill.folder, lot.fill.code, lot.fill.d): lot for lot in b1_lots}
    for a in accounts:
        if a.n_adds == 0:
            a.avg_flip = "n/a(추가매수 없음)"
            continue
        lot = first_lot.get((a.folder, a.code, a.first_date))
        if lot is None or a.exit is None:
            a.avg_flip = "no_b1_lot"
            continue
        r1, d1, r2, d2 = lot.exit.reason, lot.exit.exit_date, a.exit.reason, a.exit.exit_date
        if (r1, d1) == (r2, d2):
            a.avg_flip = "same"
        elif r1 == r2:
            a.avg_flip = "date_only"
        else:
            a.avg_flip = f"reason:{r1}→{r2}"


@dataclass
class ActualRow:
    trade: Trade
    folder: str
    qty: int
    exit_status: str                   # closed | open
    exit_reason: str                   # fidelity8.actual_reason 코드 | open
    exit_date: Optional[date]
    exit_price: Optional[float]        # 실제 매도가 | 마지막 종가(평가)

    @property
    def notional_won(self) -> int:
        return _won(self.trade.buy_price * self.qty)

    @property
    def pnl_won(self) -> Optional[int]:
        return None if self.exit_price is None else _won((self.exit_price - self.trade.buy_price) * self.qty)

    @property
    def ret_pct(self) -> Optional[float]:
        return None if self.exit_price is None else (self.exit_price / self.trade.buy_price - 1) * 100.0


def a_actual(trades_by_folder: Dict[str, Sequence[Trade]], qty_of: Callable[[int], int], days: Sequence[date],
             last_close: Callable[[str], Optional[Tuple[date, float]]],
             reason_code: Callable[[str], str]) -> List[ActualRow]:
    """창 안 실제 매수(전 전략). 미청산은 마지막 종가 평가(gross · 수수료·세금 없음)."""
    dayset = set(days)
    out: List[ActualRow] = []
    for folder in sorted(trades_by_folder):
        for t in trades_by_folder[folder]:
            if t.buy_ts.date() not in dayset:
                continue
            q = int(qty_of(t.buy_id))
            if t.sell_ts is not None:
                out.append(ActualRow(t, folder, q, "closed", reason_code(t.sell_reason), t.sell_ts.date(),
                                     float(t.sell_price)))
            else:
                lc = last_close(t.code)
                out.append(ActualRow(t, folder, q, "open", "open", lc[0] if lc else None, lc[1] if lc else None))
    return out
