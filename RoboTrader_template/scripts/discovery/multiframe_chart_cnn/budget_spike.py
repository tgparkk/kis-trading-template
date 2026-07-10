# scripts/discovery/multiframe_chart_cnn/budget_spike.py
"""예산 스파이크: 5거래일 슬라이스에서 표본 규모/라벨 도달률/캐시 용량을 실측한다.

TDD 아님 — 측정 스크립트. 출력 숫자로 표본 추출률과 캐시 설계를 확정한다.
결과는 사용자 리뷰 체크포인트에서 검토한다.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from scripts.discovery.intraday_rebound.db import MINUTE_DB, read_sql
from scripts.discovery.intraday_rebound.resample import resample_ohlcv
from scripts.discovery.intraday_rebound.universe import load_frozen_universe

_DAYS_SQL = """
SELECT DISTINCT trade_date FROM minute_candles
WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date
"""
_BARS_SQL = """
SELECT stock_code, datetime, open, high, low, close, volume, amount
FROM minute_candles
WHERE trade_date = %s AND stock_code = ANY(%s)
ORDER BY stock_code, datetime
"""
REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()
DECISION_START = pd.Timestamp("10:00:00").time()   # 09:00~10:00 룩백 부족 제외
LOOKBACK_BARS_15M = 60                              # 15분봉 60봉 = 가장 긴 룩백 요구


def spike(start: str, end: str) -> None:
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    print(f"universe={len(codes)} days={len(days)} ({days[0]}..{days[-1]})")

    total_candidate_points = 0
    total_stock_days = 0
    t0 = time.time()
    for day in days:
        raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
        if raw.empty:
            continue
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        t = raw["datetime"].dt.time
        raw = raw[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]
        for code, g in raw.groupby("stock_code", sort=False):
            bars3 = resample_ohlcv(g, 3)
            bars15 = resample_ohlcv(g, 15)
            # 15분봉 60봉을 채우려면 15*60=900분 룩백 필요 → 하루 안에선 불충분.
            # 여기서는 "하루 내 유효 3분봉 시점(10:00 이후, 15:30 마감 60분 전까지)" 만 센다.
            tt = bars3["datetime"].dt.time
            valid = bars3[(tt >= DECISION_START)]
            total_candidate_points += max(0, len(valid) - 20)  # 마감 근처 대략 20봉 제외
            total_stock_days += 1

    dt = time.time() - t0
    print(f"stock-days={total_stock_days} candidate_points(1day-approx)={total_candidate_points}")
    print(f"extract_time_5day={dt:.1f}s  -> full 356day est={dt/len(days)*356/60:.1f}min")
    # 6ch x 64x64 float32 = 6*64*64*4 = 98,304 bytes/image. int8 로 저장하면 1/4.
    bytes_per_img_f32 = 6 * 64 * 64 * 4
    bytes_per_img_i8 = 6 * 64 * 64 * 1
    full_est = total_candidate_points / len(days) * 356
    print(f"full_points_est={full_est:,.0f}")
    print(f"cache_f32={full_est*bytes_per_img_f32/1e9:.1f}GB  cache_i8={full_est*bytes_per_img_i8/1e9:.1f}GB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260601")
    ap.add_argument("--end", default="20260607")
    args = ap.parse_args()
    spike(args.start, args.end)
