"""1층 후보 스크린 게이트(분봉) 순수함수 단위테스트 — Book 19 『트레이딩 전략서』.

DB 불필요. _eligible_dates_from_signals(윈도우 확장)·_filter_cache_candidate(날짜 게이팅)만 검증.
"""
import datetime as dt

import pandas as pd

from scripts.book_portfolio_multiverse import (
    _eligible_dates_from_signals,
    _filter_cache_candidate,
)


def test_eligible_dates_window_expansion():
    dates = [dt.date(2025, 10, d) for d in (1, 2, 3, 6, 7, 8)]  # 6 거래일
    # 신호 인덱스 0(10/1) → window3 → 10/2,10/3,10/6 유효
    e = _eligible_dates_from_signals([0], dates, 3)
    assert e == {dt.date(2025, 10, 2), dt.date(2025, 10, 3), dt.date(2025, 10, 6)}


def test_eligible_dates_window_truncates_at_end():
    dates = [dt.date(2025, 10, 1), dt.date(2025, 10, 2)]
    e = _eligible_dates_from_signals([0], dates, 3)  # 1만 가능
    assert e == {dt.date(2025, 10, 2)}
    assert _eligible_dates_from_signals([1], dates, 3) == set()  # 마지막 신호=이후봉 없음


def test_eligible_dates_multiple_signals_union():
    dates = [dt.date(2025, 10, d) for d in (1, 2, 3, 6, 7)]
    e = _eligible_dates_from_signals([0, 2], dates, 1)  # 0→10/2, 2→10/6
    assert e == {dt.date(2025, 10, 2), dt.date(2025, 10, 6)}


def _mkmin(code_dates_vols):
    # helper: build minute df with datetime spanning given dates
    rows = []
    for d, n in code_dates_vols:
        for k in range(n):
            rows.append(pd.Timestamp(d) + pd.Timedelta(minutes=k))
    return pd.DataFrame({"datetime": rows, "open": 1.0, "high": 1.0, "low": 1.0,
                         "close": 1.0, "volume": 1.0})


def test_filter_cache_candidate_keeps_only_eligible_dates():
    # 종목 A 분봉: 10/1 3봉(idx0-2), 10/2 3봉(idx3-5). 유효일=10/2만 → idx 3,4,5만 남음
    df = _mkmin([(dt.date(2025, 10, 1), 3), (dt.date(2025, 10, 2), 3)])
    data = {"A": df}
    cache = {"A": [0, 1, 2, 3, 4, 5]}
    elig = {"A": {dt.date(2025, 10, 2)}}
    out = _filter_cache_candidate(cache, data, elig)
    assert out["A"] == [3, 4, 5]


def test_filter_cache_candidate_stock_not_candidate_empty():
    df = _mkmin([(dt.date(2025, 10, 1), 3)])
    out = _filter_cache_candidate({"A": [0, 1, 2]}, {"A": df}, {})  # A 후보 아님
    assert out["A"] == []
