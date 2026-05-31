import pandas as pd
import pytest
from scripts.exit_multiverse import data_loader

_START = "2024-01-01"
_END = "2024-12-31"


def test_load_top_volume_universe_returns_codes():
    codes = data_loader.load_top_volume_universe(_START, _END, top_n=10)
    assert isinstance(codes, list)
    assert len(codes) <= 10
    assert all(isinstance(c, str) for c in codes)


def test_load_daily_adj_shape():
    codes = data_loader.load_top_volume_universe(_START, _END, top_n=3)
    data = data_loader.load_daily_adj(codes, _START, _END)
    assert isinstance(data, dict)
    for code, df in data.items():
        assert list(df.columns) == ["datetime", "open", "high", "low", "close", "volume"]
        assert (df["close"] > 0).all()


def test_load_kospi_close_sorted():
    s = data_loader.load_kospi_close(_START, _END)
    assert isinstance(s, pd.Series)
    assert s.index.is_monotonic_increasing
    assert (s > 0).all()


def test_load_turnover_rank_positive():
    ranks = data_loader.load_turnover_rank(_START, _END)
    assert isinstance(ranks, dict)
    assert len(ranks) > 0
    assert all(isinstance(v, float) and v > 0 for v in ranks.values())
