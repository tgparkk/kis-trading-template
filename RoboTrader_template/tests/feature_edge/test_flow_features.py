import numpy as np
import pandas as pd
from scripts.feature_edge.flow_features import compute_flow_features


def test_shift1_and_normalization():
    dates = pd.date_range("2023-03-01", periods=25, freq="D")
    daily = pd.DataFrame({"date": dates, "volume": [100.0] * 25})
    flow = pd.DataFrame({"date": dates, "foreign_net_vol": [0.0] * 24 + [50.0]})
    out = compute_flow_features(daily, flow)
    assert out["flow_norm"].iloc[-1] == 0.0
    assert out["flow_norm"].iloc[-2] == 0.0


def test_streak_counts_consecutive_net_buy():
    dates = pd.date_range("2023-03-01", periods=6, freq="D")
    daily = pd.DataFrame({"date": dates, "volume": [100.0] * 6})
    flow = pd.DataFrame({"date": dates, "foreign_net_vol": [10, 10, -5, 10, 10, 10]})
    out = compute_flow_features(daily, flow)
    assert out["flow_streak"].iloc[-1] == 2.0


def test_missing_flow_yields_zero_not_nan():
    dates = pd.date_range("2023-03-01", periods=10, freq="D")
    daily = pd.DataFrame({"date": dates, "volume": [100.0] * 10})
    flow = pd.DataFrame({"date": [], "foreign_net_vol": []})
    out = compute_flow_features(daily, flow)
    assert (out["flow_norm"] == 0.0).all()
