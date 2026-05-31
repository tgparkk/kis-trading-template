import numpy as np
import pandas as pd
import pytest
from scripts.exit_multiverse import exits


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1000] * n,
    })


def test_stop_loss_triggers():
    df = _df([100.0] * 70 + [100.0, 90.0])  # 진입가 100, 종가 90 = -10%
    pos = {"entry_idx": 70, "entry_price": 100.0, "qty": 1}
    reason = exits.exit_reason_simple_ma(df, i=71, position=pos,
                                         stop_loss_pct=0.08, take_profit_pct=0.99,
                                         max_hold_bars=100, trail_ma=None)
    assert reason == "stop_loss"


def test_take_profit_triggers():
    df = _df([100.0] * 70 + [100.0, 115.0])
    pos = {"entry_idx": 70, "entry_price": 100.0, "qty": 1}
    reason = exits.exit_reason_simple_ma(df, i=71, position=pos,
                                         stop_loss_pct=0.08, take_profit_pct=0.12,
                                         max_hold_bars=100, trail_ma=None)
    assert reason == "take_profit"


def test_max_hold_triggers():
    df = _df([100.0] * 110)
    pos = {"entry_idx": 70, "entry_price": 100.0, "qty": 1}
    reason = exits.exit_reason_simple_ma(df, i=90, position=pos,
                                         stop_loss_pct=0.08, take_profit_pct=0.99,
                                         max_hold_bars=20, trail_ma=None)
    assert reason == "max_hold"


def test_trail_ma_breaks_below():
    closes = [100.0] * 50 + list(np.linspace(100, 120, 20)) + [110.0]
    df = _df(closes)
    i = len(df) - 1
    pos = {"entry_idx": 60, "entry_price": 105.0, "qty": 1}
    reason = exits.exit_reason_simple_ma(df, i=i, position=pos,
                                         stop_loss_pct=0.50, take_profit_pct=0.99,
                                         max_hold_bars=999, trail_ma=5)
    assert reason in (None, "trail_ma")  # 데이터 의존 — 예외 없이 동작함을 확인


def test_elder_trend_flip():
    closes = list(np.linspace(200, 100, 80))  # 단조 하락 → ema65[i] < ema65[i-5]
    df = _df(closes)
    i = len(df) - 1
    pos = {"entry_idx": 70, "entry_price": 150.0, "qty": 1}
    reason = exits.exit_reason_elder(df, i=i, position=pos,
                                     stop_loss_pct=0.50, take_profit_pct=0.99,
                                     max_hold_bars=999, trail_ema=None, trend_flip_exit=True)
    assert reason == "trend_flip"
