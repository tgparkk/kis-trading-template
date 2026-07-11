import numpy as np
import pandas as pd

from scripts.discovery.intraday_rebound.resample import resample_ohlcv
from scripts.discovery.multiframe_chart_cnn.build_dataset import (
    build_sample, _build_hist_and_path,
)
from scripts.discovery.multiframe_chart_cnn.forward_path import build_forward_path
from scripts.discovery.multiframe_chart_cnn.label3d import label3d
from scripts.discovery.multiframe_chart_cnn.scalars import vol_scalars
from scripts.discovery.multiframe_chart_cnn.augment_cache import (
    build_sample_aux, parse_grid,
)


def _day_1m(date, start_price=100.0, n=390, drift=0.0):
    base = pd.Timestamp(f"{date[:4]}-{date[4:6]}-{date[6:]} 09:00:00")
    dts = [base + pd.Timedelta(minutes=i) for i in range(n)]
    p = start_price + drift * np.arange(n)
    return pd.DataFrame({"datetime": dts, "open": p, "high": p * 1.002,
                         "low": p * 0.998, "close": p, "volume": 100.0, "amount": p * 100})


def test_aux_scalars_and_3x3_label_match_build_sample():
    # 동일 합성 다일봉에서 build_sample_aux 의 스칼라·(0.03,0.03) 라벨이
    # build_sample 과 bit-identical 해야 한다(드리프트 방지 교차검증).
    day_bars = {
        "20260601": _day_1m("20260601", 100.0, 900, drift=0.0),
        "20260602": _day_1m("20260602", 100.0, 390, drift=0.05),
        "20260603": _day_1m("20260603", 120.0, 390, drift=0.0),
    }
    entry_dt = day_bars["20260601"]["datetime"].iloc[800]
    grid = [(0.03, 0.03), (0.03, 0.05)]

    s = build_sample(day_bars, "20260601", entry_dt, tp=0.03, sl=0.03, stock_code="000100")
    aux = build_sample_aux(day_bars, "20260601", entry_dt, grid, stock_code="000100")
    assert s is not None and aux is not None

    # 스칼라: build_sample 과 동일 + 독립 vol_scalars 재계산과도 동일.
    np.testing.assert_array_equal(aux["scalars"], s["scalars"])
    hist, _, _ = _build_hist_and_path(day_bars, "20260601", entry_dt)
    np.testing.assert_array_equal(aux["scalars"], vol_scalars(resample_ohlcv(hist, 3)))
    assert aux["scalars"].shape == (2,)
    assert aux["scalars"].dtype == np.float32

    # (0.03,0.03) 라벨: build_sample 의 outcome/realized 와 동일.
    assert aux["labels"][(0.03, 0.03)][0] == s["outcome"]
    assert aux["labels"][(0.03, 0.03)][1] == s["realized_ret"]

    # 메타 필드 전달.
    assert aux["stock_code"] == "000100"
    assert aux["trade_date"] == "20260601"
    assert aux["entry_time"] == pd.Timestamp(entry_dt)


def test_aux_grid_produces_both_keys_with_correct_label3d():
    # 진입 후 ~4% 하락: 3x3 은 sl(-0.03), 3x5 는 sl 아님(배리어 미도달).
    day_bars = {
        "20260601": _day_1m("20260601", 100.0, 900, drift=0.0),
        "20260602": _day_1m("20260602", 96.0, 390, drift=0.0),   # -4%
        "20260603": _day_1m("20260603", 96.0, 390, drift=0.0),
    }
    entry_dt = day_bars["20260601"]["datetime"].iloc[800]
    grid = [(0.03, 0.03), (0.03, 0.05)]
    aux = build_sample_aux(day_bars, "20260601", entry_dt, grid)
    assert aux is not None
    assert set(aux["labels"].keys()) == {(0.03, 0.03), (0.03, 0.05)}

    # 각 그리드 라벨은 동일 전방경로에 대한 label3d 와 정확히 일치해야 한다.
    fwd = build_forward_path(day_bars, "20260601", entry_dt, horizon_days=3)
    entry_open, fh, fl, fo, fc = fwd
    for tp, sl in grid:
        exp = label3d(entry_open, fh, fl, fo, fc, tp, sl)
        assert aux["labels"][(tp, sl)] == exp

    # 두 sl 이 실제로 갈라지는 시나리오인지 확인(그리드가 의미를 갖는다).
    assert aux["labels"][(0.03, 0.03)][0] == "sl"
    assert aux["labels"][(0.03, 0.05)][0] != "sl"


def test_aux_none_when_no_forward_path():
    day_bars = {"20260601": _day_1m("20260601", 100.0, 900)}
    entry_dt = day_bars["20260601"]["datetime"].iloc[-1]  # 마지막봉, 전방 없음
    aux = build_sample_aux(day_bars, "20260601", entry_dt, [(0.03, 0.03), (0.03, 0.05)])
    assert aux is None


def test_parse_grid():
    assert parse_grid("3x3,3x5") == [(0.03, 0.03), (0.03, 0.05)]
    assert parse_grid("3x3") == [(0.03, 0.03)]
