import numpy as np
import pandas as pd
from scripts.feature_edge.timing.intraday_features import vwap, opening_range, gap_pct


def _intra(o, h, l, c, v, a):
    n = len(c)
    return pd.DataFrame({"time": [f"{900+i:04d}" for i in range(n)],
                         "open": o, "high": h, "low": l, "close": c,
                         "volume": v, "amount": a})


def test_vwap_cumulative_pit():
    df = _intra([10]*3,[10]*3,[10]*3,[10,20,30],[1,1,1],[10,20,30])
    w = vwap(df)
    assert np.isclose(w.iloc[0], 10.0)
    assert np.isclose(w.iloc[1], (10+20)/2)
    assert np.isclose(w.iloc[2], (10+20+30)/3)


def test_opening_range_first_n_bars():
    df = _intra(o=[5]*5, h=[5,7,6,9,4], l=[5,3,2,5,1], c=[5]*5, v=[1]*5, a=[5]*5)
    hi, lo = opening_range(df, n=3)
    assert hi == 7
    assert lo == 2


def test_gap_pct():
    assert np.isclose(gap_pct(d1_open=110.0, prev_close=100.0), 0.10)
