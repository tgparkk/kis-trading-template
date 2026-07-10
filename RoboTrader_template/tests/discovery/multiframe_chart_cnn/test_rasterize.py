import numpy as np
import pandas as pd

from scripts.discovery.multiframe_chart_cnn.rasterize import render_frame, render_multiframe


def _mk_bars(prices, vols=None):
    n = len(prices)
    base = pd.Timestamp("2026-06-01 09:00:00")
    dts = [base + pd.Timedelta(minutes=i) for i in range(n)]
    p = np.array(prices, dtype=float)
    v = np.array(vols if vols is not None else [1.0] * n, dtype=float)
    # 단순화: high=price*1.001, low=price*0.999, open=close=price
    return pd.DataFrame({"datetime": dts, "open": p, "high": p * 1.001,
                         "low": p * 0.999, "close": p, "volume": v, "amount": p * v})


def test_render_frame_shape_and_range():
    bars = _mk_bars(list(range(100, 200)))
    img = render_frame(bars, n_bars=60, size=64)
    assert img.shape == (2, 64, 64)
    assert img.dtype == np.float32
    assert img.min() >= 0.0 and img.max() <= 1.0


def test_price_normalization_is_scale_invariant():
    # 같은 모양, 다른 절대가격 → 동일 이미지여야 한다(종목 정체성 소거).
    bars_a = _mk_bars([100, 110, 105, 120, 115] * 12)
    bars_b = _mk_bars([1000, 1100, 1050, 1200, 1150] * 12)
    img_a = render_frame(bars_a, n_bars=60, size=64)
    img_b = render_frame(bars_b, n_bars=60, size=64)
    np.testing.assert_allclose(img_a, img_b, atol=1e-6)


def test_volume_normalization_is_scale_invariant():
    shape = [100, 110, 105, 120, 115] * 12
    bars_a = _mk_bars(shape, vols=[10, 20, 15, 30, 25] * 12)
    bars_b = _mk_bars(shape, vols=[1000, 2000, 1500, 3000, 2500] * 12)
    img_a = render_frame(bars_a, n_bars=60, size=64)
    img_b = render_frame(bars_b, n_bars=60, size=64)
    np.testing.assert_allclose(img_a[1], img_b[1], atol=1e-6)


def test_empty_bars_all_zero():
    empty = _mk_bars([]).iloc[0:0]
    img = render_frame(empty, n_bars=60, size=64)
    assert img.shape == (2, 64, 64)
    assert np.all(img == 0.0)


def test_render_multiframe_six_channels():
    # 1분봉 900개(15분봉 60봉 확보) 필요
    bars1m = _mk_bars(list(np.linspace(100, 200, 900)))
    img = render_multiframe(bars1m, n_bars=60, size=64)
    assert img.shape == (6, 64, 64)
    assert img.dtype == np.float32
    assert img.min() >= 0.0 and img.max() <= 1.0


def test_render_multiframe_deterministic():
    bars1m = _mk_bars(list(np.linspace(100, 200, 900)))
    a = render_multiframe(bars1m)
    b = render_multiframe(bars1m)
    np.testing.assert_array_equal(a, b)


def test_render_frame_draws_most_recent_when_over_size():
    # 100개 오름차순 봉(가장 최근이 가장 높은 값) 중 size=64 보다 많음.
    bars = _mk_bars(list(range(100, 200)))
    img = render_frame(bars, n_bars=100, size=64)
    # 가장 오른쪽 칸(63)은 가장 최근 봉(=가장 높은 값)이어야 함 → 몸통이 상단(row 작음)에 위치.
    rows = np.where(img[0, :, 63] >= 0.6)[0]
    assert rows.size > 0
    assert rows.min() < 8


def test_volume_max_bar_reaches_top_row():
    prices = list(range(100, 110))
    vols = [10, 10, 10, 10, 10, 10, 10, 10, 10, 500]
    bars = _mk_bars(prices, vols=vols)
    img = render_frame(bars, n_bars=10, size=64)
    # 최대거래량 봉(마지막 봉 → 가장 오른쪽 칸 63)은 상단(row 0)까지 채워져야 함.
    assert img[1, 0, 63] > 0.0
