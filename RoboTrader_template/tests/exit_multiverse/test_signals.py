import pandas as pd
from scripts.exit_multiverse import signals


class _StubStrategy:
    """i=72 에서만 BUY 신호."""
    def generate_signal_with_extra_ctx(self, code, window, tf, ctx):
        from strategies.base import Signal, SignalType
        if len(window) - 1 == 72:
            return Signal(signal_type=SignalType.BUY, stock_code=code, confidence=80,
                          reasons=["stub"])
        return None


def _df(n=100):
    import numpy as np
    return pd.DataFrame({
        "datetime": pd.date_range("2021-01-01", periods=n),
        "open": np.linspace(100, 120, n), "high": np.linspace(101, 121, n),
        "low": np.linspace(99, 119, n), "close": np.linspace(100, 120, n),
        "volume": [1000] * n,
    })


def test_precompute_entry_signals_finds_signal_bar():
    data = {"005930": _df(100)}
    strat = _StubStrategy()
    cache = signals.precompute_entry_signals(
        data, strat, warmup_bars=70, extra_ctx_fn=lambda code, dt: {})
    assert cache["005930"] == [72]


def test_precompute_respects_warmup():
    data = {"005930": _df(100)}
    strat = _StubStrategy()
    cache = signals.precompute_entry_signals(
        data, strat, warmup_bars=80, extra_ctx_fn=lambda code, dt: {})
    assert cache["005930"] == []  # 72 < warmup 80 → 평가 안 됨
