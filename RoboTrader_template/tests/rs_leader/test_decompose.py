import math
import pandas as pd

from scripts.rs_leader.decompose import (
    decompose_trades_by_regime, episode_stats, probabilistic_sharpe_ratio,
)


def _sell(entry_date, pnl):
    return {"side": "sell", "entry_date": entry_date, "pnl_pct": pnl}


def test_decompose_groups_by_regime():
    regime_map = {
        pd.Timestamp("2022-03-02"): "bear",
        pd.Timestamp("2025-05-02"): "sideways",
        pd.Timestamp("2025-06-02"): "bull",
    }
    trades = [
        _sell("2022-03-02 00:00:00", -0.05),
        _sell("2025-05-02 00:00:00", 0.04),
        _sell("2025-05-02 00:00:00", -0.01),
        _sell("2025-06-02 00:00:00", 0.10),
        {"side": "buy", "entry_date": "2025-06-02 00:00:00", "pnl_pct": 0.0},
    ]
    out = decompose_trades_by_regime(trades, regime_map)
    assert out["bear"]["n"] == 1
    assert out["sideways"]["n"] == 2
    assert out["bull"]["n"] == 1
    assert abs(out["sideways"]["mean_pnl"] - 0.015) < 1e-9
    assert abs(out["sideways"]["win_rate"] - 0.5) < 1e-9


def test_episode_stats_filters_date_range():
    trades = [
        _sell("2022-06-01 00:00:00", -0.02),
        _sell("2022-06-15 00:00:00", 0.03),
        _sell("2025-01-01 00:00:00", 0.5),
    ]
    s = episode_stats(trades, "2022-01-01", "2022-12-31")
    assert s["n"] == 2
    assert abs(s["mean_pnl"] - 0.005) < 1e-9


def test_psr_higher_for_longer_track():
    short = probabilistic_sharpe_ratio(sharpe=1.0, n=30, skew=0.0, kurt=3.0)
    long = probabilistic_sharpe_ratio(sharpe=1.0, n=300, skew=0.0, kurt=3.0)
    assert 0.0 <= short <= 1.0 and 0.0 <= long <= 1.0
    assert long > short
