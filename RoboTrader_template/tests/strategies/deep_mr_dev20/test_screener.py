"""deep_mr_dev20 EOD 스크리너 어댑터 테스트."""
import numpy as np
import pandas as pd

from strategies.deep_mr_dev20.screener import DeepMrDev20ScreenerAdapter


def _df(last_close: float, n: int = 40):
    # 가격 스케일은 스크리너 min_price(1,000원) 필터 통과하도록 1만원대 사용
    close = np.full(n, 10_000.0)
    close[-3] = 9_000.0
    close[-2] = 8_000.0
    close[-1] = last_close
    return pd.DataFrame({
        "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": [100_000.0] * n,
    })


def test_match_deep_crash_scores_depth():
    adapter = DeepMrDev20ScreenerAdapter()
    res = adapter.match(_df(7_700.0), adapter.default_params())
    assert res is not None
    score, reason = res
    assert score > 0.20  # score = |이탈깊이| → 깊을수록 상위 후보
    assert "이탈" in reason


def test_match_none_on_normal():
    adapter = DeepMrDev20ScreenerAdapter()
    assert adapter.match(_df(9_500.0), adapter.default_params()) is None


def test_base_filter_liquidity():
    adapter = DeepMrDev20ScreenerAdapter()
    p = adapter.default_params()
    uni = [
        {"stock_code": "A", "trading_value": p["min_trading_value"] * 2},
        {"stock_code": "B", "trading_value": p["min_trading_value"] / 10},
    ]
    out = adapter.base_filter(uni)
    assert [u["stock_code"] for u in out] == ["A"]


def test_strategy_name_key():
    assert DeepMrDev20ScreenerAdapter.strategy_name == "deep_mr_dev20"
