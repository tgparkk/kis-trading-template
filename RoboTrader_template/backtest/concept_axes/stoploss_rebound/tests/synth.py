"""합성(가짜) 세계 — 달력·가격·이벤트·로트·대조. 실제 DB 값 0. 실제 청산은 ⓑ 시뮬 결과로 만들어 충실도가 통과하게 한다."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List

import numpy as np

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.minervini.cap_skip_ledger.sim import Bar
from backtest.concept_axes.stoploss_rebound import lots as LT
from backtest.concept_axes.stoploss_rebound import run as R

REASON_TEXT = {X.EXIT_TP: "목표 익절 도달 (+x%)", X.EXIT_SL: "손절 실행 (-x%)", X.EXIT_MAX_HOLD: "보유기간 9일 초과"}


def weekdays(a: date, b: date) -> List[date]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def never(_p, _d):
    return None


def world(seed: int = 7, n_codes: int = 40, n_lots: int = 160, n_events: int = 60) -> R.Data:
    rng = np.random.default_rng(seed)
    cal = weekdays(R.CAL_START, R.D_ASOF)
    codes = [f"{i:06d}" for i in range(1, n_codes + 1)]
    rows: Dict[str, LT.Rows] = {}
    for c in codes:
        px = 100.0 * float(np.exp(rng.normal(0, 0.3)))
        rr: LT.Rows = {}
        for d in cal:
            r = float(rng.normal(0, 0.025))
            o = px * (1 + float(rng.normal(0, 0.01)))
            cl = px * (1 + r)
            hi = max(o, cl) * (1 + abs(float(rng.normal(0, 0.01))))
            lo = min(o, cl) * (1 - abs(float(rng.normal(0, 0.01))))
            vol = 0.0 if rng.random() < 0.01 else 1000.0
            rr[d] = LT.DayRow(o, hi, lo, cl, vol, 0.02 + float(rng.random()) * 0.04)
            px = cl
        rows[c] = rr
    rows["KOSPI"] = {d: LT.DayRow(1.0, 1.0, 1.0, 1.0, 1.0) for d in cal}
    pos = {d: i for i, d in enumerate(cal)}
    i_asof = pos[R.D_ASOF]
    entry_days = [d for d in cal if R.START <= d and pos[d] + 20 <= i_asof]
    rules = {s: X.ExitRules(*R.EXPECT_RULES[s][:2], R.EXPECT_RULES[s][2], "synthetic") for s in R.STRATS}
    lots: List[LT.LotIn] = []
    minutes: Dict = {}
    for i in range(n_lots):
        s = R.STRATS[i % 4]
        c = codes[int(rng.integers(0, n_codes))]
        d0 = entry_days[int(rng.integers(0, len(entry_days)))]
        early = rng.random() < 0.4
        t = time(9, 3) if early else time(10, int(rng.integers(0, 59)), 20)
        bt = datetime.combine(d0, t)
        bp = rows[c][d0].open
        lots.append(LT.LotIn(1000 + i, s, c, bt, bp, 10))
        if not early and rng.random() < 0.6:
            mins = []
            for m in range(max(t.minute - 1, 0), min(t.minute + 30, 59)):
                o = bp * (1 + float(rng.normal(0, 0.005)))
                mins.append((f"10:{m:02d}:00", Bar(d0, o, o * 1.004, o * 0.996, o)))
            minutes[(c, d0)] = mins
    D = R.Data(cal, [], lots, rows, {}, {}, {}, minutes, rules, {s: never for s in R.STRATS})
    # 실제 SELL = ⓑ 전체 경로 시뮬(충실도 통과용) · 일부는 진입 당일 실제 청산(①)
    for k, lt in enumerate(lots):
        if k % 9 == 0:
            lt.sell_id, lt.sell_ts = 5000 + k, datetime.combine(lt.d0, time(11, 0))
            lt.sell_reason = REASON_TEXT[X.EXIT_SL] if k % 18 == 0 else REASON_TEXT[X.EXIT_TP]
            lt.sell_price = lt.buy_price * (0.97 if k % 18 == 0 else 1.10)
            continue
        p = R.lot_prep(D, lt)
        sim = LT.b_full(lt, rules[lt.strategy], p.path, never, p.basis, p.touch, D.aware)
        if sim.closed and sim.exit_date is not None and sim.exit_date != lt.d0:
            lt.sell_id, lt.sell_ts = 5000 + k, datetime.combine(sim.exit_date, time(11, 0))
            lt.sell_reason, lt.sell_price = REASON_TEXT.get(sim.reason, sim.reason), sim.price
    events: List[R.Event] = []
    ev_days = [d for d in cal if R.START <= d <= R.D_ASOF]
    for i in range(n_events):
        s = R.STRATS[i % 4]
        c = codes[int(rng.integers(0, n_codes))]
        d = ev_days[int(rng.integers(0, len(ev_days)))]
        brid = None if i == 3 else 9000 + i
        events.append(R.Event(100 + i, s, c, datetime.combine(d, time(10, 30)), brid))
    e0 = events[5]
    nxt = cal[min(pos[e0.d] + 2, i_asof)]
    events.append(R.Event(999, e0.strategy, e0.code, datetime.combine(nxt, time(10, 0)), 99999))   # X4 대상
    controls = {}
    for e in events:
        k = int(rng.integers(0, 6))
        controls[e.id] = sorted({x for x in rng.choice(codes, size=k, replace=False).tolist() if x != e.code})
    D.events = events
    D.lots_full = list(lots)
    D.controls = controls
    D.splits = {codes[0]: [entry_days[3]]}
    D.rights = {codes[1]: [entry_days[4]]}
    return D


def set_stop_prices(D: R.Data) -> None:
    """개봉 단계 흉내 — 이벤트 체결가(합성) 조인."""
    for e in D.events:
        e.stop_px = D.rows[e.code][e.d].close * 0.995
