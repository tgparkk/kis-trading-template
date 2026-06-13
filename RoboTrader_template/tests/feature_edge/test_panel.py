import numpy as np
import pandas as pd
from scripts.feature_edge.panel import assemble_panel


def _stock_df(seed):
    rng = np.random.RandomState(seed)
    c = (rng.randn(80).cumsum() + 200).clip(min=10)
    dates = pd.date_range("2021-01-01", periods=80, freq="D")
    return pd.DataFrame({"date": dates, "open": c, "high": c*1.01,
                         "low": c*0.99, "close": c, "volume": rng.randint(1e3,1e4,80)})


def test_assemble_panel_shape_and_relative_strength():
    codes = ["A", "B", "C"]
    daily = {k: _stock_df(i) for i, k in enumerate(codes)}
    index_df = pd.DataFrame({"date": daily["A"]["date"],
                             "close": np.linspace(300, 400, 80)})
    panel = assemble_panel(codes, daily, index_df, flow_supplier={}, event_supplier={})
    assert {"date", "stock_code", "returns_20d", "mkt_ret20",
            "rel_strength", "breadth"}.issubset(panel.columns)
    row = panel[(panel["stock_code"] == "A")].dropna(subset=["rel_strength"]).iloc[-1]
    assert np.isclose(row["rel_strength"], row["returns_20d"] - row["mkt_ret20"], atol=1e-9)


def test_breadth_is_cross_sectional_fraction():
    codes = ["A", "B", "C"]
    daily = {k: _stock_df(i) for i, k in enumerate(codes)}
    index_df = pd.DataFrame({"date": daily["A"]["date"], "close": np.ones(80)*300})
    panel = assemble_panel(codes, daily, index_df, flow_supplier={}, event_supplier={})
    b = panel.dropna(subset=["breadth"])["breadth"]
    assert ((b >= 0) & (b <= 1)).all()
