# -*- coding: utf-8 -*-
"""합성 자료 생성기 — 시험(tests/)과 `--synthetic-demo` 전용. 실데이터 접근 0."""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence

import numpy as np

from ci_stats import (CostDay, DayLog, Dataset, PaperBuy, PaperSell, RealBuy, RealSell, round_to_tick, tick_size)


def weekdays(start: date, n: int) -> List[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class Builder:
    """하루·종목 단위로 페이퍼/실전 행과 실전 로그 사건을 손으로 쌓는 도구."""

    def __init__(self, days: Sequence[date]):
        self.days = list(days)
        self.pb: List[PaperBuy] = []
        self.ps: List[PaperSell] = []
        self.rb: List[RealBuy] = []
        self.rs: List[RealSell] = []
        self.logs: Dict[date, DayLog] = {}
        self.cost_days: Dict[date, CostDay] = {}
        self.cost_rows = {}
        self._id = 1000
        for d in self.days:
            self.logs[d] = DayLog(day=d, first_ts=datetime.combine(d, datetime.min.time()).replace(hour=7, minute=45),
                                  last_ts=datetime.combine(d, datetime.min.time()).replace(hour=15, minute=40))

    def nid(self) -> int:
        self._id += 1
        return self._id

    @staticmethod
    def at(d: date, h: int, m: int, s: int = 0) -> datetime:
        return datetime(d.year, d.month, d.day, h, m, s)

    def paper_buy(self, d, code, t, price, qty=10, sl=0.10) -> PaperBuy:
        p = PaperBuy(self.nid(), code, t, float(price), qty, sl)
        self.pb.append(p)
        return p

    def paper_sell(self, buy: PaperBuy, t, price, reason="익절 실행") -> PaperSell:
        s = PaperSell(self.nid(), buy.code, t, float(price), buy.qty, buy.id, reason)
        self.ps.append(s)
        return s

    def real_try(self, d, code, t, logged_price, qty=5, signal_lead_s: Optional[int] = 1):
        lg = self.logs[d]
        if signal_lead_s is not None:
            lg.signals.append((t - timedelta(seconds=signal_lead_s), code))
        lg.tries.append((t, code, qty, float(logged_price)))

    def real_buy(self, d, code, t, price, qty=5) -> RealBuy:
        r = RealBuy(self.nid(), code, t, float(price), qty)
        self.rb.append(r)
        return r

    def real_sell(self, buy: RealBuy, t, price, qty=None) -> RealSell:
        s = RealSell(self.nid(), buy.code, t, float(price), qty or buy.qty, buy.id)
        self.rs.append(s)
        return s

    def stop_log(self, d, code, t, trig_pct, thr=-10.0):
        self.logs[d].stops.append((t, code, float(trig_pct), float(thr)))

    def cost_day(self, d, buy_amt, sell_amt, fee, tax):
        self.cost_days[d] = CostDay(d, float(buy_amt), float(sell_amt), float(fee), float(tax))

    def build(self, kospi_sign: Optional[Dict[date, int]] = None, **kw) -> Dataset:
        ks = kospi_sign if kospi_sign is not None else {d: (1 if i % 2 == 0 else -1) for i, d in enumerate(self.days)}
        return Dataset(start=self.days[0], end=self.days[-1], paper_buys=self.pb, paper_sells=self.ps, real_buys=self.rb,
                       real_sells=self.rs, logs=self.logs, cost_days=self.cost_days, cost_rows=self.cost_rows,
                       kospi_sign=ks, trading_days=list(self.days), **kw)


def full_synthetic(seed: int = 7, n_days: int = 20, per_day: int = 3, start: date = date(2026, 10, 19)) -> Dataset:
    """모든 지표가 채워지는 합성 기간(데모·연기 시험용). 값은 무작위 — 실데이터와 무관."""
    rng = np.random.default_rng(seed)
    days = weekdays(start, n_days)
    b = Builder(days)
    k = 0
    for d in days:
        buy_sum = sell_sum = 0.0
        for j in range(per_day):
            k += 1
            code = f"{100000 + k:06d}"
            t0 = b.at(d, 9, 5 + 7 * j, 0)
            pp = float(round_to_tick(rng.uniform(3000, 30000)))
            pbuy = b.paper_buy(d, code, t0, pp)
            if rng.random() < 0.25:                      # ㉯ 페이퍼만(실전 시도 없음 또는 한도)
                if rng.random() < 0.5:
                    b.logs[d].caps.append((t0, code))
                continue
            tt = t0 + timedelta(seconds=int(rng.integers(2, 120)))
            logged = pp * (1 + rng.normal(0.001, 0.004))
            op = round_to_tick(logged)
            b.real_try(d, code, tt, logged, signal_lead_s=int(rng.integers(0, 3)))
            fp = op + tick_size(op) * int(rng.integers(0, 2))
            rbuy = b.real_buy(d, code, tt + timedelta(seconds=int(rng.integers(1, 40))), fp)
            buy_sum += fp * rbuy.qty
            if rng.random() < 0.6:                       # 같은 날 양쪽 손절
                tr = -10.0 - abs(rng.normal(0.3, 0.3))
                ts_ = b.at(d, 13, 0 + j)
                b.stop_log(d, code, ts_, tr)
                sp = round_to_tick(fp * (1 + tr / 100) * (1 + rng.normal(-0.001, 0.002)))
                rs = b.real_sell(rbuy, ts_ + timedelta(seconds=5), sp)
                sell_sum += sp * rs.qty
                b.cost_rows[(d, code, rs.qty)] = sp * rs.qty
                ptr = -10.0 - abs(rng.normal(0.3, 0.3))
                b.paper_sell(pbuy, ts_ + timedelta(seconds=30), round_to_tick(pp * (1 + ptr / 100)),
                             reason=f"손절 실행 ({ptr:.2f}% <= -10.00%)")
        fee = round(0.0000353 * (buy_sum + sell_sum))
        tax = round(0.0020 * sell_sum)
        b.cost_day(d, buy_sum, sell_sum, fee, tax)
    ks = {d: (1 if rng.random() < 0.5 else -1) for d in days}
    from ci_data import STRUCT_CHANGES
    return b.build(kospi_sign=ks, struct_changes=list(STRUCT_CHANGES), meta={"checks": {"자료": "합성(synthetic.full_synthetic)"}})
