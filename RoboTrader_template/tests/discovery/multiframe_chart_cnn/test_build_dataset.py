import numpy as np
import pandas as pd

from scripts.discovery.multiframe_chart_cnn.build_dataset import (
    iter_candidate_times, build_sample, eligible_entry_days,
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
    assert isinstance(s["trade_date"], str)


def test_build_sample_none_when_no_forward():
    day_bars = {"20260601": _day_1m("20260601", 100.0, 900)}
    entry_dt = day_bars["20260601"]["datetime"].iloc[-1]  # 마지막봉, 전방 없음
    s = build_sample(day_bars, "20260601", entry_dt, tp=0.03, sl=0.03)
    assert s is None


def test_build_dataset_excludes_boundary_entry_days():
    # 3거래일 전방 창을 온전히 갖춘 진입일만 남아야 한다(마지막 2거래일 제외).
    days = [f"d{i}" for i in range(1, 7)]  # d1..d6, 6거래일
    result = eligible_entry_days(days, sample_every_n_days=1)
    assert result == ["d1", "d2", "d3", "d4"]  # d5, d6은 3일 전방창 부족으로 제외

    result_stride2 = eligible_entry_days(days, sample_every_n_days=2)
    assert result_stride2 == ["d1", "d3"]  # 짝수 stride 중 전방창 온전한 것만


def test_build_sample_fills_15min_channel_with_prior_days():
    # Plan-1 addendum(Task 7): 15분봉 채널은 당일 데이터만으로는(하루 최대
    # ~27봉) 60봉 캔버스를 못 채운다 — 직전 거래일들을 이력에 포함해야 한다.
    day_bars = {
        "20260601": _day_1m("20260601", 100.0, 390),
        "20260602": _day_1m("20260602", 100.0, 390),
        "20260603": _day_1m("20260603", 100.0, 390),
    }
    entry_dt = day_bars["20260603"]["datetime"].iloc[60]  # 10:00 진입 (당일 61봉뿐)
    s = build_sample(day_bars, "20260603", entry_dt, tp=0.03, sl=0.03, lookback_days=3)
    assert s is not None
    filled_cols = int(np.sum(np.any(s["image"][4] != 0, axis=0)))
    assert filled_cols > 33  # 직전 2거래일 로드로 15분봉 채널이 넓게 채워짐

    # 대조: 당일 데이터만 있으면(직전일 로드 안 됨) 10:00 진입은 15분봉 ~5개뿐.
    same_day_only = {"20260603": day_bars["20260603"]}
    s_same_day = build_sample(same_day_only, "20260603", entry_dt, tp=0.03, sl=0.03,
                              lookback_days=3)
    assert s_same_day is not None
    filled_same_day = int(np.sum(np.any(s_same_day["image"][4] != 0, axis=0)))
    assert filled_same_day < 10
    assert filled_cols > filled_same_day


def test_build_sample_no_lookahead_multiday():
    # 진입일 이후(entry_dt 초과) 봉이 이미지에 절대 섞이면 안 된다 — 직전
    # 거래일을 이력에 추가한 뒤에도 이 불변식이 유지되는지 확인한다.
    day1 = _day_1m("20260601", 100.0, 390)
    day2 = _day_1m("20260602", 100.0, 390)
    day3_normal = _day_1m("20260603", 100.0, 390)
    entry_dt = day3_normal["datetime"].iloc[60]  # 10:00 진입

    # day3 변형: entry_dt 이후 봉만 가격을 100배로 스파이크시킨다(미래 정보).
    day3_spiked = day3_normal.copy()
    after_mask = pd.to_datetime(day3_spiked["datetime"]) > entry_dt
    day3_spiked.loc[after_mask, ["open", "high", "low", "close"]] *= 100.0

    day_bars_normal = {"20260601": day1, "20260602": day2, "20260603": day3_normal}
    day_bars_spiked = {"20260601": day1, "20260602": day2, "20260603": day3_spiked}

    s_normal = build_sample(day_bars_normal, "20260603", entry_dt, tp=0.03, sl=0.03,
                            lookback_days=3)
    s_spiked = build_sample(day_bars_spiked, "20260603", entry_dt, tp=0.03, sl=0.03,
                            lookback_days=3)
    assert s_normal is not None and s_spiked is not None
    # 이미지/스칼라는 entry_dt 이전 이력에만 의존해야 하므로 완전히 동일해야 한다.
    np.testing.assert_array_equal(s_normal["image"], s_spiked["image"])
    np.testing.assert_array_equal(s_normal["scalars"], s_spiked["scalars"])
