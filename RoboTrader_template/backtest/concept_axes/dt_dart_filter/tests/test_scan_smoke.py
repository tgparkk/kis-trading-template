"""scan_window 스모크 — 합성 일봉 몇 종목 · 돌파 하루(최종 리뷰 «build 전 테스트»). DB 없음."""
import math

import pandas as pd

from backtest.concept_axes.dt_dart_filter import universe as U

DAYS = list(pd.bdate_range("2021-01-04", periods=40))
D = DAYS[30]


def _stock(code, price, vol, mcap, breakout_vol=None):
    rows = []
    for d in DAYS:
        o, h, lo, c, v = price, price * 1.01, price * 0.99, price, vol
        if breakout_vol is not None and d == D:
            o, h, lo, c, v = price, price * 1.06, price * 0.995, price * 1.05, breakout_vol
        rows.append(dict(date=d, stock_code=code, open=o, high=h, low=lo, close=c, volume=float(v), market_cap=mcap))
    return rows


def _px():
    rows = []
    rows += _stock("000010", 10_000.0, 200_000, float("nan"), breakout_vol=600_000)   # 시총 NaN · 점수 3
    rows += _stock("000020", 10_000.0, 200_000, 9e12, breakout_vol=1_000_000)         # 대형 · 점수 5
    rows += _stock("000030", 1_000.0, 200_000, 1e10, breakout_vol=600_000)            # 거래대금 6.3억 < 10억 → 탈락
    rows += _stock("000040", 10_000.0, 200_000, 1e11)                                  # 돌파 없음
    return pd.DataFrame(rows)


def test_scan_window_smoke_one_breakout_day():
    rows, diag = U.scan_window(_px(), DAYS[25:])
    assert diag == {"n_errors": 0, "n_days": 15, "n_rows": 2}
    assert [(r["scan_date"], r["stock_code"], r["rank"], r["n_passed"]) for r in rows] == [
        (D.date(), "000020", 1, 2), (D.date(), "000010", 2, 2)]
    by = {r["stock_code"]: r for r in rows}
    assert abs(by["000020"]["score"] - 5.0) < 1e-9 and abs(by["000010"]["score"] - 3.0) < 1e-9
    assert math.isnan(by["000010"]["market_cap"]) and by["000020"]["market_cap"] == 9e12
    assert abs(by["000010"]["trading_value"] - 10_500.0 * 600_000) < 1e-3
