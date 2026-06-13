import numpy as np
import pandas as pd
from scripts.feature_edge.market_features import compute_index_features


def test_index_trend_and_vol_percentile_pit():
    closes = [100 + i for i in range(300)]
    idx = pd.DataFrame({"date": pd.date_range("2021-01-01", periods=300, freq="D"),
                        "close": closes})
    out = compute_index_features(idx)
    assert out["mkt_above_ma20"].iloc[-1] == 1
    v = out["mkt_vol_pct"].iloc[-1]
    assert 0.0 <= v <= 1.0


def test_no_lookahead_index():
    closes = list(np.random.RandomState(0).randn(300).cumsum() + 100)
    idx = pd.DataFrame({"date": pd.date_range("2021-01-01", periods=300, freq="D"),
                        "close": closes})
    full = compute_index_features(idx)
    trunc = compute_index_features(idx.iloc[:250])
    assert np.allclose(full["mkt_ret20"].iloc[:250].fillna(-9),
                       trunc["mkt_ret20"].fillna(-9), atol=1e-9)
