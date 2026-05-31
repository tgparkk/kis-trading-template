import pandas as pd
import pytest
from scripts.exit_multiverse import data_loader


def test_load_top_volume_universe_returns_codes():
    codes = data_loader.load_top_volume_universe("2024-01-01", "2024-12-31", top_n=10)
    assert isinstance(codes, list)
    assert len(codes) <= 10
    assert all(isinstance(c, str) for c in codes)


def test_load_daily_adj_shape():
    codes = data_loader.load_top_volume_universe("2024-01-01", "2024-12-31", top_n=3)
    data = data_loader.load_daily_adj(codes, "2024-01-01", "2024-12-31")
    assert isinstance(data, dict)
    for code, df in data.items():
        assert list(df.columns) == ["datetime", "open", "high", "low", "close", "volume"]
        assert (df["close"] > 0).all()


def test_load_kospi_close_sorted():
    s = data_loader.load_kospi_close("2024-01-01", "2024-12-31")
    assert isinstance(s, pd.Series)
    assert s.index.is_monotonic_increasing
    assert (s > 0).all()
