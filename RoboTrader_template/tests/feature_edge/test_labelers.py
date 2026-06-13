import numpy as np
import pandas as pd
from scripts.feature_edge.labelers import label_forward_returns, label_triple_barrier


def _df(o, h, l, c):
    n = len(c)
    return pd.DataFrame({"date": pd.date_range("2021-01-01", periods=n, freq="D"),
                         "open": o, "high": h, "low": l, "close": c})


def test_forward_return_entry_next_open():
    c = [100, 100, 110, 120, 130, 140]
    df = _df(o=c, h=c, l=c, c=c)
    out = label_forward_returns(df, horizons=(2,))
    assert np.isclose(out["fwd_2d"].iloc[0], 120 / 100 - 1, atol=1e-6)
    assert np.isnan(out["fwd_2d"].iloc[-1])


def test_zero_open_yields_nan_not_inf():
    # 진입(T+1) 시가가 0이면 inf 수익률 대신 NaN 이어야 함 (데이터 오염 방지).
    c = [100, 0, 110, 120, 130, 140]   # idx1 시가/종가 0 → t=0 진입가 0
    df = _df(o=c, h=c, l=c, c=c)
    out = label_forward_returns(df, horizons=(2,))
    assert np.isnan(out["fwd_2d"].iloc[0])
    assert not np.isinf(out["fwd_2d"].to_numpy(dtype=float)).any()


def test_triple_barrier_up_hit_first():
    o = [100, 100, 100, 100, 100]
    h = [100, 100, 112, 100, 100]
    l = [100, 100, 100, 100, 100]
    c = [100, 100, 100, 100, 100]
    df = _df(o, h, l, c)
    out = label_triple_barrier(df, up=0.10, down=0.05, horizon=3)
    assert out["tb_up0.1_dn0.05_h3"].iloc[0] == 1


def test_triple_barrier_down_hit_first():
    o = [100, 100, 100, 100, 100]
    h = [100, 100, 100, 100, 100]
    l = [100, 94, 100, 100, 100]
    c = [100, 100, 100, 100, 100]
    df = _df(o, h, l, c)
    out = label_triple_barrier(df, up=0.10, down=0.05, horizon=3)
    assert out["tb_up0.1_dn0.05_h3"].iloc[0] == 0
