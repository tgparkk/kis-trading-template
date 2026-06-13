import pandas as pd
from scripts.feature_edge.timing.sell_rules import (
    vwap_break_exit, intraday_trail, time_exit, intraday_momentum_loss)


def _intra(c, h=None, l=None, v=None, a=None, times=None):
    n = len(c)
    h = h or c; l = l or c; v = v or [1]*n; a = a or [c[i]*v[i] for i in range(n)]
    times = times or [f"{900+i:04d}" for i in range(n)]
    return pd.DataFrame({"time": times, "open": c, "high": h, "low": l,
                         "close": c, "volume": v, "amount": a})


def test_vwap_break_exits_when_close_below_vwap():
    df = _intra(c=[10, 12, 8])
    x = vwap_break_exit(df, entry_price=10.0, params={})
    assert x is not None and x.reason == "vwap_break"


def test_intraday_trail_exits_on_drawdown_from_high():
    df = _intra(c=[10, 12, 11.5], h=[10, 12, 12])
    x = intraday_trail(df, entry_price=10.0, params={"trail_pct": 0.03})
    assert x is not None and x.reason == "intraday_trail"


def test_time_exit_triggers_at_or_after_time():
    df = _intra(c=[10, 11, 12], times=["1300", "1430", "1500"])
    x = time_exit(df, entry_price=10.0, params={"time_exit": "1430"})
    assert x is not None and x.bar_idx == 1


def test_momentum_loss_exits_on_negative_lookback():
    df = _intra(c=[10, 11, 10.5])
    x = intraday_momentum_loss(df, entry_price=10.0, params={"mom_min": 1})
    assert x is not None and x.reason == "mom_loss"
