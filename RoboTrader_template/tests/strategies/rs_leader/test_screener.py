import numpy as np
import pandas as pd

from strategies.rs_leader.screener import RSLeaderScreenerAdapter


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def test_match_uptrend_returns_score_and_reason():
    closes = list(np.linspace(10000, 20000, 130))  # 단조상승·가격대 통과
    adapter = RSLeaderScreenerAdapter()
    res = adapter.match(_df(closes), adapter.default_params())
    assert res is not None
    score, reason = res
    assert score > 0 and isinstance(reason, str) and reason


def test_match_downtrend_returns_none():
    closes = list(np.linspace(20000, 10000, 130))
    adapter = RSLeaderScreenerAdapter()
    assert adapter.match(_df(closes), adapter.default_params()) is None


def test_match_too_short_returns_none():
    closes = list(np.linspace(10000, 11000, 40))
    adapter = RSLeaderScreenerAdapter()
    assert adapter.match(_df(closes), adapter.default_params()) is None


def test_base_filter_liquidity():
    adapter = RSLeaderScreenerAdapter()
    uni = [
        {"code": "A", "market_cap": 5e11, "trading_value": 2e9},
        {"code": "B", "market_cap": 5e11, "trading_value": 5e8},
    ]
    out = adapter.base_filter(uni)
    assert [u["code"] for u in out] == ["A"]
