import numpy as np
import pandas as pd
import pytest

from scripts.discovery.multiframe_chart_cnn.build_dataset import (
    iter_candidate_times, build_sample,
)


def _day_1m(date, start_price=100.0, n=390, drift=0.0):
    base = pd.Timestamp(f"{date[:4]}-{date[4:6]}-{date[6:]} 09:00:00")
    dts = [base + pd.Timedelta(minutes=i) for i in range(n)]
    p = start_price + drift * np.arange(n)
    return pd.DataFrame({"datetime": dts, "open": p, "high": p * 1.002,
                         "low": p * 0.998, "close": p, "volume": 100.0, "amount": p * 100})


def test_iter_candidate_times_excludes_open_hour_and_tail():
    from scripts.discovery.intraday_rebound.resample import resample_ohlcv
    bars3 = resample_ohlcv(_day_1m("20260601"), 3)
    times = iter_candidate_times(bars3, pd.Timestamp("10:00:00").time(), 20)
    assert all(t.time() >= pd.Timestamp("10:00:00").time() for t in times)
    # 마지막 20봉 제외 확인
    assert times[-1] < bars3["datetime"].iloc[-1]


def test_iter_candidate_times_stride():
    # OVERRIDE 1: stride 파라미터 — 15분 표본추출(3분봉 5개마다 1개)을 위해
    # decision_start/tail cutoff 필터링 이후 times[::stride] 만 남긴다.
    from scripts.discovery.intraday_rebound.resample import resample_ohlcv
    bars3 = resample_ohlcv(_day_1m("20260601"), 3)
    base_times = iter_candidate_times(bars3, pd.Timestamp("10:00:00").time(), 20)
    strided_times = iter_candidate_times(bars3, pd.Timestamp("10:00:00").time(), 20, stride=5)
    assert strided_times == base_times[::5]
    assert strided_times[0] == base_times[0]
    if len(strided_times) > 1:
        assert strided_times[1] == base_times[5]


def test_build_sample_produces_shapes_and_label():
    # 3거래일: 진입일 + 2일. 상승 드리프트 → tp 도달 기대
    day_bars = {
        "20260601": _day_1m("20260601", 100.0, 900, drift=0.0),   # 15분봉 60봉 확보
        "20260602": _day_1m("20260602", 100.0, 390, drift=0.05),  # 강한 상승
        "20260603": _day_1m("20260603", 120.0, 390, drift=0.0),
    }
    entry_dt = day_bars["20260601"]["datetime"].iloc[800]
    s = build_sample(day_bars, "20260601", entry_dt, tp=0.03, sl=0.03)
    assert s is not None
    assert s["image"].shape == (6, 64, 64)
    assert s["scalars"].shape == (2,)
    assert s["outcome"] in {"tp", "sl", "timeout"}
    assert s["stock_code"] is None or isinstance(s["trade_date"], str)


def test_build_sample_none_when_no_forward():
    day_bars = {"20260601": _day_1m("20260601", 100.0, 900)}
    entry_dt = day_bars["20260601"]["datetime"].iloc[-1]  # 마지막봉, 전방 없음
    s = build_sample(day_bars, "20260601", entry_dt, tp=0.03, sl=0.03)
    assert s is None
