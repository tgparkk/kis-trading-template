"""회귀 동등성 — book_portfolio_multiverse 의 진입 필터 차원.

★보장★: --entry-filter 차원에 'none' 이 포함되면, 그 'none' row 의 모든 메트릭은
필터 차원이 ['none'] 단독일 때(=기존 동작)와 **바이트동일** 이어야 한다.
즉 필터 추가가 baseline 결과를 절대 바꾸지 않음을 증명한다.

DB 불필요(합성 데이터로 _eval_entry_daily 직접 호출). 워커 전역을 seq wrapper 로 세팅.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import scripts.book_portfolio_multiverse as M


def _make_df(seed: int, n: int = 160, drift: float = 0.001):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)
    lr = drift + rng.normal(0, 0.02, n)
    close = 10000 * np.exp(np.cumsum(lr))
    o = close * (1 - rng.uniform(0, 0.004, n))
    h = np.maximum(o, close) * 1.01
    l = np.minimum(o, close) * 0.99
    vol = rng.integers(1000, 5000, n)
    return pd.DataFrame({"datetime": dates, "open": o, "high": h, "low": l,
                         "close": close, "volume": vol})


class _AlwaysBuyRule:
    """warmup 이후 매 bar BUY 신호(필터 게이팅만 측정하기 위한 단순 룰)."""
    name = "always_buy"

    def __init__(self, **kw):
        pass


class _AlwaysBuyStrategy:
    def generate_signal(self, code, window, timeframe):
        from strategies.base import Signal, SignalType
        return Signal(signal_type=SignalType.BUY, stock_code=code, confidence=100)


def _patch_build_strategy(monkeypatch):
    monkeypatch.setattr(M, "_build_strategy", lambda rc, rn, ro: _AlwaysBuyStrategy())


def _run_daily(filters, kospi=None):
    data = {f"S{k:02d}": _make_df(seed=10 + k, drift=(0.002 if k % 2 == 0 else -0.001))
            for k in range(8)}
    turnover = {c: float((df["close"] * df["volume"]).sum()) for c, df in data.items()}
    exit_combos = [{"sl": 0.05, "tp": 0.10, "mh": 5}]
    return M._eval_entry_daily_seq(
        {}, _AlwaysBuyRule, "always_buy", 42, data, turnover, exit_combos,
        [3], 3_000_000.0, 10_000_000.0, ["none"], {},
        filters, 0.5, 60, kospi,
    )


def _make_kospi(n: int = 160):
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2023-01-02", periods=n)
    return pd.Series(2400 * np.exp(np.cumsum(0.0005 + rng.normal(0, 0.01, n))),
                     index=dates, name="close")


def test_filter_none_byte_identical_when_filters_added(monkeypatch):
    """'none' row 메트릭이 필터 차원 확장 여부와 무관하게 동일."""
    _patch_build_strategy(monkeypatch)
    base = _run_daily(["none"])
    expanded = _run_daily(["none", "adx", "ma_slope", "rs_rank"])

    base_none = [r for r in base if r["filter"] == "none"]
    exp_none = [r for r in expanded if r["filter"] == "none"]
    assert len(base_none) == 1 and len(exp_none) == 1
    b, e = base_none[0], exp_none[0]
    for key in ("n_trades", "sharpe", "pnl", "calmar", "hit", "max_dd",
                "max_concurrent", "n_skipped"):
        assert b[key] == pytest.approx(e[key], rel=1e-12, abs=1e-12), \
            f"filter=none 회귀 위반: {key} base={b[key]} expanded={e[key]}"


def test_filters_reduce_or_equal_trades(monkeypatch):
    """필터는 진입을 AND-게이팅 → 거래수는 none 이하여야(절대 늘지 않음)."""
    _patch_build_strategy(monkeypatch)
    rows = _run_daily(["none", "adx", "ma_slope", "rs_rank", "mkt_rs"], kospi=_make_kospi())
    by = {r["filter"]: r for r in rows}
    base_tr = by["none"]["n_trades"]
    for f in ("adx", "ma_slope", "rs_rank", "mkt_rs"):
        assert by[f]["n_trades"] <= base_tr, f"필터 {f} 가 거래수 증가({by[f]['n_trades']}>{base_tr})"
