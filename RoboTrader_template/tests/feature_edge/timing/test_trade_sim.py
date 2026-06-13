import numpy as np
import pandas as pd
from scripts.feature_edge.timing.trade_sim import FixedExitAdapter, simulate_trade


def _daily(closes):
    n = len(closes)
    return pd.DataFrame({"date": [f"2025-03-{i+1:02d}" for i in range(n)],
                         "open": closes, "high": [c*1.0 for c in closes],
                         "low": closes, "close": closes})


def test_fixed_exit_take_profit():
    adapter = FixedExitAdapter()
    params = {"stop_loss_pct": 0.10, "take_profit_pct": 0.10, "max_hold_bars": 10}
    daily = _daily([100, 100, 115])
    pos = {"entry_price": 100.0, "entry_idx": 1}
    assert adapter.exit_reason(daily, 2, pos, params) == "take_profit"


def test_baseline_trade_no_intraday_rules():
    daily = _daily([100, 100, 90])
    params = {"stop_loss_pct": 0.10, "take_profit_pct": 0.10, "max_hold_bars": 10}
    tr = simulate_trade(signal_idx=0, daily=daily, intraday_by_date={},
                        exit_adapter=FixedExitAdapter(), exit_params=params,
                        buy_rule=None, sell_rule=None, buy_params={}, sell_params={},
                        slippage=0.0)
    assert tr.filled is True
    assert np.isclose(tr.entry_price, 100.0)
    assert tr.exit_reason == "stop_loss"
    assert np.isclose(tr.ret_gross, -0.10, atol=1e-6)


def test_net_applies_slippage_both_sides():
    daily = _daily([100, 100, 110])
    params = {"stop_loss_pct": 0.10, "take_profit_pct": 0.10, "max_hold_bars": 10}
    tr = simulate_trade(0, daily, {}, FixedExitAdapter(), params,
                        None, None, {}, {}, slippage=0.01)
    assert tr.ret_net < tr.ret_gross


def test_buy_skip_yields_unfilled():
    daily = _daily([100, 100, 110])
    params = {"stop_loss_pct": 0.10, "take_profit_pct": 0.10, "max_hold_bars": 10}

    def always_skip(intra, base_open, p):
        return None
    tr = simulate_trade(0, daily, {}, FixedExitAdapter(), params,
                        buy_rule=always_skip, sell_rule=None, buy_params={}, sell_params={},
                        slippage=0.0)
    assert tr.filled is False
