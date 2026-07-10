import numpy as np
import pandas as pd
import pytest

from scripts.discovery.multiframe_chart_cnn.scalars import vol_scalars


def _mk(prices, highs=None, lows=None):
    n = len(prices)
    base = pd.Timestamp("2026-06-01 09:00:00")
    dts = [base + pd.Timedelta(minutes=3 * i) for i in range(n)]
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"datetime": dts, "open": p,
                         "high": np.array(highs, float) if highs else p,
                         "low": np.array(lows, float) if lows else p,
                         "close": p, "volume": 1.0, "amount": p})


def test_range_pct():
    bars = _mk([100, 120, 90, 110], highs=[100, 120, 90, 110], lows=[100, 120, 90, 110])
    s = vol_scalars(bars, n_bars=60)
    assert s.shape == (2,)
    # range = 120-90=30, last_close=110 → 0.2727
    assert s[0] == pytest.approx(30 / 110)


def test_atr_pct():
    bars = _mk([100, 100], highs=[102, 104], lows=[98, 100])
    s = vol_scalars(bars, n_bars=60)
    # mean(high-low) = mean(4,4)=4, last_close=100 → 0.04
    assert s[1] == pytest.approx(0.04)


def test_empty_zero():
    empty = _mk([]).iloc[0:0]
    s = vol_scalars(empty)
    assert np.all(s == 0.0)
