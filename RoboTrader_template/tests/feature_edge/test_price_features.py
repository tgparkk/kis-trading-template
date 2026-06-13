import numpy as np
import pandas as pd
from scripts.feature_edge.price_features import compute_price_features


def _df(closes, vols=None):
    n = len(closes)
    vols = vols or [1000] * n
    return pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": vols,
    })


def test_returns_and_ma_dist_pit():
    closes = [100, 110, 121, 133.1, 146.41, 161.05]  # +10%/일
    out = compute_price_features(_df(closes))
    assert np.isclose(out["returns_5d"].iloc[-1], 161.05 / 100 - 1, atol=1e-6)
    assert np.isnan(out["ma20_dist"].iloc[-1])
    assert np.isnan(out["returns_5d"].iloc[4])


def test_volume_surge_ratio():
    closes = [100] * 25
    vols = [100] * 24 + [500]
    out = compute_price_features(_df(closes, vols))
    assert np.isclose(out["vol_surge"].iloc[-1], 5.0, atol=1e-6)


def test_no_lookahead_last_row_independent_of_future():
    closes = [100 + i for i in range(30)]
    full = compute_price_features(_df(closes))
    trunc = compute_price_features(_df(closes[:25]))
    for col in ["returns_5d", "returns_20d", "ma20_dist", "vol_surge"]:
        assert np.allclose(full[col].iloc[:25].fillna(-999),
                           trunc[col].fillna(-999), atol=1e-9)
