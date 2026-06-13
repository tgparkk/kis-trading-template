import numpy as np
import pandas as pd
from scripts.feature_edge.timing.cost_validation import (
    roundtrip_net, cost_sweep, breakeven_cost, decompose_timing_selection)


def test_roundtrip_net_subtracts_cost():
    s = pd.Series([0.10, 0.00, -0.05])
    out = roundtrip_net(s, 0.02)
    assert np.allclose(out.values, [0.08, -0.02, -0.07])


def test_cost_sweep_columns_and_breakeven_sign_flip():
    base = pd.Series([0.004] * 100)   # 거래당 +0.4% (baseline)
    alt = pd.Series([0.023] * 100)    # 거래당 +2.3% (first30)
    tbl = cost_sweep(base, alt, costs=(0.002, 0.005, 0.01))
    assert set(["cost", "base_net_mean", "alt_net_mean", "delta_mean"]).issubset(tbl.columns)
    # 비용 0.5%면 baseline 음전환(0.4%<0.5%), first30 여전히 양수
    row = tbl[np.isclose(tbl["cost"], 0.005)].iloc[0]
    assert row["base_net_mean"] < 0
    assert row["alt_net_mean"] > 0


def test_breakeven_cost_equals_mean_gross():
    g = pd.Series([0.01, 0.03, 0.02])
    assert np.isclose(breakeven_cost(g), 0.02)


def test_decompose_timing_selection_splits_total():
    # 신호 4개: baseline 전부 진입, first30은 강한 2개만 진입
    per = pd.DataFrame({
        "base_gross": [0.00, 0.00, 0.04, 0.06],          # 모든 신호의 baseline 결과
        "entered":    [False, False, True, True],         # first30 진입 여부
        "alt_gross":  [np.nan, np.nan, 0.05, 0.09],       # 진입분 first30 결과
    })
    d = decompose_timing_selection(per)
    # selection = mean(base[entered]) - mean(base[all]) = 0.05 - 0.025 = 0.025
    assert np.isclose(d["selection"], 0.025)
    # timing = mean(alt[entered] - base[entered]) = mean([0.01, 0.03]) = 0.02
    assert np.isclose(d["timing"], 0.02)
    # total = mean(alt[entered]) - mean(base[all]) = 0.07 - 0.025 = 0.045 = timing+selection
    assert np.isclose(d["total"], 0.045)
    assert np.isclose(d["timing"] + d["selection"], d["total"])
