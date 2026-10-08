from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.theme_rank import returns as RT

CAL = [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)]


def _px(rows):
    return pd.DataFrame(rows, columns=["stock_code", "date", "close"])


def test_daily_returns_needs_previous_calendar_day():
    px = _px([("1", "2026-01-02", 100.0), ("1", "2026-01-05", 110.0), ("1", "2026-01-06", 99.0),
              ("000002", "2026-01-02", 50.0), ("000002", "2026-01-05", 50.0)])
    r = RT.daily_returns(px, CAL)
    got = {(c, d): round(v, 10) for c, d, v in r.itertuples(index=False)}
    assert got == {("000001", date(2026, 1, 5)): 0.1, ("000001", date(2026, 1, 6)): -0.1,
                   ("000002", date(2026, 1, 5)): 0.0}


def test_daily_returns_drops_gap_after_suspension():
    """D−1 봉이 없으면(정지) D 수익률을 만들지 않는다 — 01-06 의 직전 봉이 01-02 라 제외."""
    px = _px([("000003", "2026-01-02", 100.0), ("000003", "2026-01-06", 130.0)])
    assert RT.daily_returns(px, CAL).empty


def test_daily_returns_drop_mask_removes_rows_before_pairing():
    px = _px([("000004", "2026-01-02", 100.0), ("000004", "2026-01-05", 100.0), ("000004", "2026-01-06", 120.0)])
    drop = np.array([False, True, False])            # 01-05 패딩봉 → 01-05·01-06 둘 다 수익률 없음
    assert RT.daily_returns(px, CAL, drop).empty


def test_excess_subtracts_equal_weight_market_mean():
    rets = pd.DataFrame({"stock_code": ["000001", "000002"], "date": [CAL[1], CAL[1]], "r": [0.10, 0.0]})
    ex = RT.excess_by_day(rets)
    assert ex[CAL[1]]["000001"] == pytest.approx(0.05)
    assert ex[CAL[1]]["000002"] == pytest.approx(-0.05)
    assert RT.raw_by_day(rets)[CAL[1]]["000001"] == pytest.approx(0.10)
