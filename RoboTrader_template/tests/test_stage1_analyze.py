# RoboTrader_template/tests/test_stage1_analyze.py
import pandas as pd
from RoboTrader_template.scripts.stage1_analyze import (
    signal_count_histogram,
    zero_signal_param_analysis,
    compare_live_default,
)


def test_signal_count_histogram():
    df = pd.DataFrame({"total_trades": [0, 0, 3, 7, 15, 22, 50]})
    h = signal_count_histogram(df)
    assert h["0건"] == 2
    assert h["1~5건"] == 1   # 3
    assert h["6~20건"] == 2  # 7, 15
    assert h["21+건"] == 2   # 22, 50


def test_zero_signal_param_analysis_finds_concentration():
    """0건 셀들이 rsi_oversold=30에 집중 → 결과에 해당 파라미터 표시."""
    df = pd.DataFrame({
        "total_trades": [0, 0, 0, 0, 10],
        "parameters.rsi_oversold": [30, 30, 30, 30, 40],
        "parameters.bb_period": [20, 25, 20, 25, 20],
    })
    result = zero_signal_param_analysis(df)
    # rsi_oversold=30이 0건 셀에서 100% 점유
    assert result["parameters.rsi_oversold"][30] == 1.0
    # bb_period은 20/25 균등
    assert result["parameters.bb_period"][20] == 0.5


def test_compare_live_default():
    """라이브 default가 Top 50 안에 있는지 확인."""
    df = pd.DataFrame({
        "parameters.bb_period": [20, 25],
        "parameters.bb_std": [2.0, 2.0],
        "parameters.rsi_oversold": [40, 35],
        "total_return": [0.12, 0.08],
    })
    live_default = {
        "parameters.bb_period": 20,
        "parameters.bb_std": 2.0,
        "parameters.rsi_oversold": 40,
    }
    found = compare_live_default(df, live_default)
    assert found is not None
    assert found["total_return"] == 0.12
