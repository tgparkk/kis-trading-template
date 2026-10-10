"""code issue 4 — 대형 포함(small_only=False) 표본에서 p_L NaN 행의 5분위가 쓰레기 정수가 되지 않는다."""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from backtest.concept_axes.dt_dart_filter import sample as SM

CAL = [date(2022, 1, 3) + timedelta(days=i) for i in range(10)]
IDX = {d: i for i, d in enumerate(CAL)}


def _led():
    pl = [0.1, 0.2, np.nan, 0.3, 0.45, 0.7, 0.9, np.nan, 0.05, 0.6, 0.15, 0.35]
    rows = [dict(stock_code=f"{i:06d}", scan_date=CAL[i % 3], status="filled", p_L=p, ret_sl=1.0, ret_tp=1.0)
            for i, p in enumerate(pl)]
    return pd.DataFrame(rows)


def test_quint_nullable_for_all_sizes_and_plain_int_for_small():
    big = SM.analysis_frame(_led(), set(), IDX, small_only=False)
    assert str(big["quint"].dtype) == "Int64"
    nan_rows = big["p_L"].isna().to_numpy()
    assert nan_rows.sum() == 2 and big["quint"][nan_rows].isna().all()
    assert big["quint"][~nan_rows].between(1, 5).all()
    small = SM.analysis_frame(_led(), set(), IDX)
    assert small["quint"].dtype.kind == "i" and small["quint"].between(1, 5).all()
