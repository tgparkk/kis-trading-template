import pytest
from scripts.feature_edge import loaders


def test_loader_functions_exist():
    assert hasattr(loaders, "load_universe")
    assert hasattr(loaders, "load_daily_supplier")
    assert hasattr(loaders, "load_flow_supplier")
    assert hasattr(loaders, "load_event_supplier")
    assert hasattr(loaders, "load_index_df")


@pytest.mark.integration
def test_load_universe_returns_codes():
    codes = loaders.load_universe("2026-06-12")
    assert isinstance(codes, list) and len(codes) > 100
