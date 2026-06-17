import numpy as np
import pandas as pd

from scripts.dynamic_rr_multiverse import (
    evaluate_dynamic_gates,
    run_strategy_grid,
    MIN_TRADES,
    MAX_CLAMP_FRAC,
)


def _good():
    return {"delta_sharpe_train": 0.3, "sharpe_train": 0.5,
            "delta_sharpe_test": 0.2, "sharpe_test": 0.4,
            "boot_dsharpe_p05": 0.05, "delta_sharpe_cost": 0.1,
            "n_trades": 50, "clamp_frac": 0.05}


# --- Part A: pure gate function -------------------------------------------

def test_winner_passes_all_gates():
    ok, reason = evaluate_dynamic_gates(_good())
    assert ok is True and reason == "PASS"


def test_test_window_negative_fails():
    c = _good(); c["delta_sharpe_test"] = -0.1
    ok, reason = evaluate_dynamic_gates(c)
    assert ok is False and "test" in reason.lower()


def test_train_window_negative_fails():
    c = _good(); c["delta_sharpe_train"] = -0.1
    ok, reason = evaluate_dynamic_gates(c)
    assert ok is False and "train" in reason.lower()


def test_high_clamp_frac_excluded():
    c = _good(); c["clamp_frac"] = 0.30
    ok, reason = evaluate_dynamic_gates(c)
    assert ok is False and "clamp" in reason.lower()


def test_few_trades_fails():
    c = _good(); c["n_trades"] = 10
    ok, reason = evaluate_dynamic_gates(c)
    assert ok is False and "trade" in reason.lower()


def test_bootstrap_fail():
    c = _good(); c["boot_dsharpe_p05"] = -0.01
    ok, reason = evaluate_dynamic_gates(c)
    assert ok is False and "boot" in reason.lower()


def test_cost_stress_fail():
    c = _good(); c["delta_sharpe_cost"] = -0.01
    ok, reason = evaluate_dynamic_gates(c)
    assert ok is False and "cost" in reason.lower()


# --- Part B: integration ---------------------------------------------------

def _synthetic_data():
    """600 bars spanning 2022-2025 (calendar days) with a mild up-trend + noise."""
    n = 600
    dates = pd.date_range("2022-01-03", periods=n, freq="2D")  # ~600*2d ≈ 2022→2025
    rng = np.random.default_rng(7)
    close = 10000 * np.cumprod(1.0 + rng.normal(0.0003, 0.02, n))
    df = pd.DataFrame({
        "datetime": dates,
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.full(n, 1000),
    })
    return {"AAA": df}


def test_run_strategy_grid_adds_oos_keys_and_self_reference():
    data = _synthetic_data()
    # a couple of entry signals in both train (<=2024-06-30) and test windows
    df = data["AAA"]
    dt = pd.to_datetime(df["datetime"])
    train_idx = int(df.index[dt <= "2024-06-30"][10])
    test_idx = int(df.index[dt >= "2024-07-01"][10])
    signals = {"AAA": sorted({train_idx, train_idx + 20, test_idx, test_idx + 20})}
    base_params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12, "max_hold_bars": 20}
    grid = [
        {"ref_type": "fixed"},
        {"ref_type": "box", "n": 10, "sl_mult": 1.0, "rr": 2.0, "buffer": 0.0, "bb_k": 2.0},
    ]
    rows = run_strategy_grid("synth", data, signals, base_params, grid=grid,
                             boot_iters=50)
    assert len(rows) == 2
    new_keys = {"sharpe_train", "delta_sharpe_train", "sharpe_test",
                "delta_sharpe_test", "boot_dsharpe_p05", "delta_sharpe_cost",
                "gate_pass", "gate_reason"}
    for r in rows:
        assert new_keys.issubset(r.keys()), f"missing keys: {new_keys - r.keys()}"

    fixed = next(r for r in rows if r["ref_type"] == "fixed")
    # self-reference per window: fixed cell == baseline within each window → ΔSharpe ≈ 0
    assert abs(fixed["delta_sharpe_train"]) < 1e-9
    assert abs(fixed["delta_sharpe_test"]) < 1e-9
