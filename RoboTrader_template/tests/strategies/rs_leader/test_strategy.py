import numpy as np
import pandas as pd

from strategies.rs_leader.strategy import RSLeaderStrategy


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def test_evaluate_entry_uptrend_true():
    closes = list(np.linspace(10000, 20000, 130))
    ok, reasons = RSLeaderStrategy.evaluate_entry(_df(closes), min_daily_bars=130)
    assert ok is True and reasons


def test_evaluate_entry_downtrend_false():
    closes = list(np.linspace(20000, 10000, 130))
    ok, reasons = RSLeaderStrategy.evaluate_entry(_df(closes), min_daily_bars=130)
    assert ok is False


def test_sell_stop_loss():
    closes = [10000] * 25 + [9000]
    should, reasons, code = RSLeaderStrategy.evaluate_sell_conditions(
        _df(closes), entry_price=10000.0, hold_days=1,
        stop_loss_pct=0.08, max_hold_days=30, trail_ma=20)
    assert should and code == "stop_loss"


def test_sell_ma20_break_unconditional():
    # 상승 후 MA20 아래로 마감 → ma_break (수익여부 무관, 검증 4-bis 정합)
    closes = list(range(10000, 10030)) + [10010]
    should, reasons, code = RSLeaderStrategy.evaluate_sell_conditions(
        _df(closes), entry_price=10010.0, hold_days=1,
        stop_loss_pct=0.08, max_hold_days=30, trail_ma=20)
    assert should and code == "ma_break"


def test_sell_hold_when_above_ma():
    closes = list(range(10000, 10040))
    should, reasons, code = RSLeaderStrategy.evaluate_sell_conditions(
        _df(closes), entry_price=10030.0, hold_days=1,
        stop_loss_pct=0.08, max_hold_days=30, trail_ma=20)
    assert should is False
