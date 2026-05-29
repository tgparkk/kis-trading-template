"""Minervini VCP rules — 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def trend_up_df():
    """200일 단조 상승 일봉 (TT 모든 조건 통과해야 함)."""
    n = 260
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = np.linspace(10_000, 30_000, n)
    high = close * 1.01
    low = close * 0.99
    volume = np.full(n, 1_000_000)
    return pd.DataFrame({
        "datetime": dates, "open": close, "high": high, "low": low,
        "close": close, "volume": volume,
    })


@pytest.fixture
def trend_down_df():
    """200일 단조 하락 (TT 통과 불가)."""
    n = 260
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = np.linspace(30_000, 10_000, n)
    return pd.DataFrame({
        "datetime": dates, "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": np.full(n, 1_000_000),
    })


def test_compute_rs_percentile_returns_0_to_99():
    from strategies.books.minervini_vcp.rules import compute_rs_percentile_12w

    n = 100
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    universe_df = pd.DataFrame({
        code: 10_000 * (1 + i * 0.001) ** np.arange(n)
        for i, code in enumerate([f"A{i:03d}" for i in range(20)])
    }, index=dates)
    rs = compute_rs_percentile_12w(universe_df)
    assert rs.shape == (n, 20)
    last = rs.iloc[-1].dropna()
    assert (last.min() >= 0) and (last.max() <= 99)
    # 가장 강한 종목(i=19) RS == 99
    assert last["A019"] == pytest.approx(99, abs=1)
