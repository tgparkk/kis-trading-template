import math

import pandas as pd

from backtest.concept_axes.dt_dart_filter import universe as U


def test_nocap_adapter_ignores_mcap():
    a = U.NoCapDaytradingAdapter()
    rows = [{"code": "1", "market_cap": 9e12, "trading_value": 2e9},
            {"code": "2", "market_cap": float("nan"), "trading_value": 2e9},
            {"code": "3", "market_cap": 1e11, "trading_value": 5e8}]
    assert [r["code"] for r in a.base_filter(rows)] == ["1", "2"]


def test_nocap_adapter_keeps_live_rule_params():
    p = U.NoCapDaytradingAdapter().default_params()
    assert p["high_window"] == 15 and p["vol_lookback"] == 20 and p["vol_mult"] == 2.0
    assert p["min_trading_value"] == 1_000_000_000


def test_build_universe_all_keeps_nan_mcap_rows():
    px = pd.DataFrame({"date": pd.to_datetime(["2021-02-01", "2021-02-01"]), "stock_code": ["1", "2"],
                       "market_cap": [float("nan"), 3e11], "close": [100.0, 10.0], "volume": [1e7, 1e6]})
    uni = U.build_universe_all(px)
    day = uni[pd.Timestamp("2021-02-01")]
    assert math.isnan(day["1"][0]) and day["1"][1] == 1e9
    assert day["2"] == (3e11, 1e7)
