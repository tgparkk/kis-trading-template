import numpy as np
import pandas as pd
import pytest

from scripts.discovery.multiframe_chart_cnn.forward_path import build_forward_path


def _mk_day(date: str, prices: list[float]) -> pd.DataFrame:
    # 09:00 부터 1분봉, open=high=low=close=price 로 단순화
    base = pd.Timestamp(f"{date[:4]}-{date[4:6]}-{date[6:]} 09:00:00")
    dts = [base + pd.Timedelta(minutes=i) for i in range(len(prices))]
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"datetime": dts, "open": p, "high": p, "low": p,
                         "close": p, "volume": 1.0, "amount": p})


def test_entry_fill_is_next_minute_open_same_day():
    d1 = _mk_day("20260601", [100, 101, 102, 103, 104])
    day_bars = {"20260601": d1}
    entry_dt = d1["datetime"].iloc[1]  # 09:01 결정 → 체결 = 09:02 시가 = 102
    res = build_forward_path(day_bars, "20260601", entry_dt, horizon_days=1)
    assert res is not None
    entry_open, fh, fl, fo, fc = res
    assert entry_open == pytest.approx(102.0)
    # fwd 는 체결봉(09:02) 다음(09:03)부터
    assert fo[0] == pytest.approx(103.0)
    assert len(fh) == 2  # 09:03, 09:04


def test_forward_crosses_into_next_trading_days():
    d1 = _mk_day("20260601", [100, 101])
    d2 = _mk_day("20260602", [110, 111])
    d3 = _mk_day("20260603", [120, 121])
    day_bars = {"20260601": d1, "20260602": d2, "20260603": d3}
    entry_dt = d1["datetime"].iloc[0]  # 09:00 결정 → 체결 09:01 = 101
    res = build_forward_path(day_bars, "20260601", entry_dt, horizon_days=3)
    entry_open, fh, fl, fo, fc = res
    assert entry_open == pytest.approx(101.0)
    # 다음날 시가 110 이 fwd_open 에 포함 → 갭 반영 확인
    assert 110.0 in fo
    assert 120.0 in fo


def test_entry_at_last_bar_fills_next_day_open():
    d1 = _mk_day("20260601", [100, 101])   # 마지막봉 09:01
    d2 = _mk_day("20260602", [110, 111])
    day_bars = {"20260601": d1, "20260602": d2}
    entry_dt = d1["datetime"].iloc[1]  # 09:01(그날 마지막) 결정 → 체결 = 다음날 첫봉 110
    res = build_forward_path(day_bars, "20260601", entry_dt, horizon_days=3)
    entry_open, fh, fl, fo, fc = res
    assert entry_open == pytest.approx(110.0)


def test_missing_fill_returns_none():
    d1 = _mk_day("20260601", [100])
    day_bars = {"20260601": d1}
    entry_dt = d1["datetime"].iloc[0]  # 그날 마지막봉이자 유일봉, 다음날 없음
    res = build_forward_path(day_bars, "20260601", entry_dt, horizon_days=3)
    assert res is None
