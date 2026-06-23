# tests/collectors/test_daily_adj.py
from datetime import date
from collectors.daily_adj import _adj_update_rows


def test_adj_update_rows_only_nonunity_factors():
    # compute 결과 {stock: {date: factor}} → (factor, stock, date) 중 factor!=1.0만
    adj_map = {"A": {"2022-01-03": 5.0, "2022-05-02": 1.0}}
    rows = _adj_update_rows(adj_map)
    assert rows == [(5.0, "A", "2022-01-03")]
