import numpy as np
import pandas as pd
import pytest
from scripts.exit_multiverse import portfolio_sim
from scripts.exit_multiverse import adapters


def _flat_then_drop(n=80):
    closes = [100.0] * 72 + [100.0, 100.0, 100.0, 100.0, 100.0, 90.0, 90.0, 90.0]
    closes = (closes + [90.0] * n)[:n]
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1000] * n,
    })


def test_max_positions_caps_holdings():
    data = {f"{i:06d}": _flat_then_drop() for i in range(5)}
    signal_cache = {code: [72] for code in data}  # 모두 i=72 신호
    ad = adapters.ADAPTERS["book_pullback_ma5"]
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.99, "max_hold_bars": 999, "trail_ma": None}
    res = portfolio_sim.run_portfolio(
        data=data, signal_cache=signal_cache, adapter=ad, params=params,
        turnover={code: float(i) for i, code in enumerate(data)},
        initial_capital=10_000_000, max_positions=2, max_per_stock=3_000_000,
        unconstrained=False)
    assert res["max_concurrent_positions"] <= 2
    assert res["n_skipped"] >= 1


def test_equity_curve_nonempty():
    data = {"000001": _flat_then_drop()}
    signal_cache = {"000001": [72]}
    ad = adapters.ADAPTERS["book_pullback_ma5"]
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.99, "max_hold_bars": 999, "trail_ma": None}
    res = portfolio_sim.run_portfolio(
        data=data, signal_cache=signal_cache, adapter=ad, params=params,
        turnover={"000001": 1.0}, initial_capital=10_000_000,
        max_positions=5, max_per_stock=3_000_000, unconstrained=False)
    assert len(res["equity_curve"]) > 0
    assert "daily_returns" in res
    assert isinstance(res["daily_returns"], pd.Series)
