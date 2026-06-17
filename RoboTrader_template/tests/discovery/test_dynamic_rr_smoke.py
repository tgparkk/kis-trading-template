import pandas as pd
import numpy as np
from scripts.exit_multiverse.portfolio_sim import run_portfolio
from scripts.book_portfolio_multiverse import _SLTPMHAdapter


def _data():
    close = np.array([10000, 10100, 10200, 9000, 9500, 10000, 10100, 10200, 10300, 10400], float)
    df = pd.DataFrame({
        "datetime": list(range(10)),
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": [1] * 10,
    })
    return {"AAA": df}


def test_dynamic_resolver_records_per_trade_sltp():
    data = _data()
    # signal bar 1 → fill bar 2 (open ~10200); bar3 close 9000 ≈ -12%
    signals = {"AAA": [1]}
    # fixed params: sl/tp 99% → fixed adapters would never stop-loss on normal moves
    params = {"stop_loss_pct": 0.99, "take_profit_pct": 0.99, "max_hold_bars": 99}
    # box n=2 over bars 0..1: box_high=10100*1.01≈10201, box_low=10000*0.99=9900
    # sl_level = box_low*(1-buffer) = 9900; entry_price ~= 10200*1.001 ~= 10210
    # sl_pct = (10210 - 9900) / 10210 ~= 3% → triggers on bar3 close 9000 (-12%)
    dyn = {"ref_type": "box", "n": 2, "sl_mult": 1.0, "rr": 2.0, "buffer": 0.0, "bb_k": 2.0}
    turnover = {"AAA": 1.0}
    res = run_portfolio(data, signals, _SLTPMHAdapter(), params, turnover, dyn=dyn)
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    # dynamic box sl is small (~3%) → bar3 -12% triggers stop_loss,
    # whereas fixed 99% would never exit intraday.
    assert any(t.get("reason") == "stop_loss" for t in sells), (
        f"expected stop_loss sell, got: {sells}"
    )


def test_dyn_none_is_baseline_no_dynamic_keys():
    data = _data()
    signals = {"AAA": [1]}
    params = {"stop_loss_pct": 0.99, "take_profit_pct": 0.99, "max_hold_bars": 99}
    turnover = {"AAA": 1.0}
    # dyn omitted → baseline: no stop_loss (sl 99%); only forced_close at end
    res = run_portfolio(data, signals, _SLTPMHAdapter(), params, turnover)
    sells = [t for t in res["trades"] if t["side"] == "sell"]
    assert all(t.get("reason") != "stop_loss" for t in sells), (
        f"baseline should have no stop_loss, got: {sells}"
    )


from scripts.dynamic_rr_multiverse import run_strategy_grid


def test_fixed_cell_matches_baseline_self_reference():
    data = _data()
    signals = {"AAA": [1]}
    base_params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 20}
    rows = run_strategy_grid("test_strat", data, signals, base_params, grid=[{"ref_type": "fixed"}])
    assert len(rows) == 1
    assert abs(rows[0]["delta_sharpe"]) < 1e-9   # fixed cell == baseline → ΔSharpe 0


def test_clamp_frac_nonzero_when_tp_clamped():
    # signal bar=1 → entry fill bar=2 (open ~10200*1.001=10210)
    # atr ref at i=1, n=2: ATR≈201; sl_pct=6*201/10210≈0.118; tp_pct=3*0.118=0.354 > TP_CAP(0.30) → clamped
    # With base sl/tp both 99% the position is never stopped by fixed params; forced_close at end
    # carries tp_clamped=True from position → clamp_frac must be > 0.
    from scripts.dynamic_rr_multiverse import _metrics_for
    data = _data()
    signals = {"AAA": [1]}
    base_params = {"stop_loss_pct": 0.99, "take_profit_pct": 0.99, "max_hold_bars": 99}
    # sl_mult=6.0, rr=3.0 → tp_pct≈0.354 > TP_CAP=0.30 → tp_clamped=True deterministically
    dyn = {"ref_type": "atr", "n": 2, "sl_mult": 6.0, "rr": 3.0, "buffer": 0.0, "bb_k": 2.0}
    m = _metrics_for(data, signals, base_params, dyn=dyn)
    assert m["n_trades"] >= 1, f"expected at least one sell trade, got n_trades={m['n_trades']}"
    assert m["clamp_frac"] > 0.0, (
        f"clamp_frac should be > 0 when tp_clamped is set on position, got {m['clamp_frac']}"
    )
