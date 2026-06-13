import pytest
from scripts.feature_edge.timing import intraday_loader as L


def test_functions_exist():
    assert hasattr(L, "load_intraday_by_date")
    assert hasattr(L, "load_intraday_supplier")
    assert hasattr(L, "covered_stock_dates")


@pytest.mark.integration
def test_load_intraday_real():
    m = L.load_intraday_by_date("005930", "2026-06-12")
    assert m is None or "close" in m.columns
