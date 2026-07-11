# scripts/discovery/multiframe_chart_cnn/label_scan.py
"""전체 구간 3거래일 TP/SL 도달률 실측 (라벨 전용, 이미지 없음).

계획2 준비: TP/SL 값을 고르기 전에, 199종목 전 구간에서 여러 (TP,SL) 후보의
무조건 진입 기저율(tp/sl/timeout)과 무조건 gross 기대값을 실측한다. 이미지·CUDA·
28GB 캐시가 필요 없는 가벼운 패스다.

효율: 각 거래일을 딱 1회만 DB에서 조회(슬라이딩 윈도우 캐시). 각 진입 시점마다
전방경로를 1회 조립하고, 그 위에서 TP/SL 그리드 전체를 평가한다(경로 재사용).

이것은 백테스트가 아니라 기저율 측정이다 — 선별(CNN) 전의 base rate.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict

import numpy as np
import pandas as pd

from scripts.discovery.intraday_rebound.db import MINUTE_DB, read_sql
from scripts.discovery.intraday_rebound.resample import resample_ohlcv
from scripts.discovery.intraday_rebound.universe import load_frozen_universe
from .build_dataset import (
    DECISION_START, REGULAR_CLOSE, REGULAR_OPEN, iter_candidate_times,
)
from .forward_path import build_forward_path
from .label3d import label3d

ROUND_TRIP_COST = 0.0021

_DAYS_SQL = """
SELECT DISTINCT trade_date FROM minute_candles
WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date
"""
_BARS_SQL = """
SELECT stock_code, datetime, open, high, low, close, volume, amount
FROM minute_candles WHERE trade_date = %s AND stock_code = ANY(%s)
ORDER BY stock_code, datetime
"""


def parse_grid(spec: str) -> list[tuple[float, float]]:
    """"3x3,3x5,5x5,..." → [(0.03,0.03),(0.03,0.05),...]. 값은 % (3 = 3%)."""
    out: list[tuple[float, float]] = []
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        tp_s, sl_s = tok.lower().split("x")
        out.append((float(tp_s) / 100.0, float(sl_s) / 100.0))
    return out


def _load_day(day: str, codes: list[str]) -> dict:
    """한 거래일의 정규장 1분봉을 종목별 DataFrame dict로."""
    raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
    if raw.empty:
        return {}
    raw["datetime"] = pd.to_datetime(raw["datetime"])
    t = raw["datetime"].dt.time
    raw = raw[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]
    return {code: g.reset_index(drop=True) for code, g in raw.groupby("stock_code", sort=False)}


class _Accum:
    """(tp,sl) 별 누적 카운트/실현수익 합."""

    def __init__(self, grid: list[tuple[float, float]]):
        self.grid = grid
        self.n = {g: 0 for g in grid}
        self.tp = {g: 0 for g in grid}
        self.sl = {g: 0 for g in grid}
        self.to = {g: 0 for g in grid}
        self.ret_sum = {g: 0.0 for g in grid}

    def add(self, g, outcome: str, realized: float):
        self.n[g] += 1
        self.ret_sum[g] += realized
        if outcome == "tp":
            self.tp[g] += 1
        elif outcome == "sl":
            self.sl[g] += 1
        else:
            self.to[g] += 1

    def to_frame(self) -> pd.DataFrame:
        rows = []
        for g in self.grid:
            tp, sl = g
            n = self.n[g]
            if n == 0:
                continue
            gross = self.ret_sum[g] / n
            rows.append({
                "tp_pct": round(tp * 100, 2), "sl_pct": round(sl * 100, 2),
                "n": n,
                "pct_tp": round(100 * self.tp[g] / n, 2),
                "pct_sl": round(100 * self.sl[g] / n, 2),
                "pct_timeout": round(100 * self.to[g] / n, 2),
                "gross_uncond_pct": round(gross * 100, 4),
                "net_uncond_pct": round((gross - ROUND_TRIP_COST) * 100, 4),
            })
        return pd.DataFrame(rows)


def scan(start: str, end: str, grid: list[tuple[float, float]],
         time_stride: int = 10, cutoff_from_end_bars: int = 20,
         lookback_unused: int = 0) -> pd.DataFrame:
    """day 순회(각 날 1회 fetch, 3일 윈도우 캐시). 각 시점서 grid 전체 평가."""
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    acc = _Accum(grid)

    cache: "OrderedDict[str, dict]" = OrderedDict()

    def ensure(day: str):
        if day not in cache:
            cache[day] = _load_day(day, codes)
            # 4일치만 유지
            while len(cache) > 4:
                cache.popitem(last=False)

    n_days = len(days)
    for i in range(n_days):
        entry_day = days[i]
        # 3거래일 전방창이 완전히 있어야 진입일 자격 (Task6 eligible_entry_days 와 동일).
        if i + 3 > n_days:
            break
        window = days[i:i + 3]
        for d in window:
            ensure(d)
        day_bars = {d: cache[d] for d in window}

        entry_stocks = day_bars[entry_day]
        for code, bars1m in entry_stocks.items():
            bars3 = resample_ohlcv(bars1m, 3)
            times = iter_candidate_times(bars3, DECISION_START, cutoff_from_end_bars,
                                         stride=time_stride)
            # 종목별 3일 윈도우 dict
            per_stock = {d: cache[d][code] for d in window if code in cache[d]}
            for entry_dt in times:
                fwd = build_forward_path(per_stock, entry_day, entry_dt, horizon_days=3)
                if fwd is None:
                    continue
                entry_open, fh, fl, fo, fc = fwd
                for g in grid:
                    tp, sl = g
                    outcome, realized = label3d(entry_open, fh, fl, fo, fc, tp, sl)
                    acc.add(g, outcome, realized)
        if (i + 1) % 20 == 0:
            done = acc.n[grid[0]]
            print(f"day {i + 1}/{n_days} {entry_day} samples/grid0={done}", flush=True)

    return acc.to_frame()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20250401")
    ap.add_argument("--end", default="20260630")
    ap.add_argument("--grid", default="3x3,3x5,5x3,5x5,5x7,7x5,7x7,10x5,10x7,10x10")
    ap.add_argument("--stride", type=int, default=10, help="3분봉 stride (10=30분 간격)")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    grid = parse_grid(args.grid)
    df = scan(args.start, args.end, grid, time_stride=args.stride)
    print(df.to_string(index=False))
    if args.out:
        df.to_csv(args.out, index=False)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
