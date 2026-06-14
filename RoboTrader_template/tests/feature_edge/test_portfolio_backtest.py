import numpy as np
import pandas as pd

from scripts.feature_edge.portfolio_backtest import (
    top_quantile_codes, illiquidity_pct, tiered_cost,
    build_periods, period_stats,
)


def _day(codes, amihud):
    return pd.DataFrame({"stock_code": codes, "amihud": amihud})


def test_top_quantile_picks_highest_fraction():
    day = _day(list("abcdefghij"), list(range(10)))  # j 최고, a 최저
    top = top_quantile_codes(day, "amihud", top_pct=0.3)
    assert set(top) == {"h", "i", "j"}  # 상위 30% = 최고 3종목


def test_top_quantile_drops_nan():
    day = pd.DataFrame({"stock_code": ["a", "b", "c", "d"],
                        "amihud": [np.nan, 1.0, 2.0, 3.0]})
    top = top_quantile_codes(day, "amihud", top_pct=0.5)
    # NaN 제외 3종목 중 상위 50%(올림) → 최고 2종목
    assert set(top) == {"c", "d"}


def test_illiquidity_pct_is_within_day_rank():
    day = _day(["a", "b", "c", "d"], [1.0, 2.0, 3.0, 4.0])
    p = illiquidity_pct(day, "amihud")
    assert p["a"] < p["d"]                  # 비유동 클수록 pct 큼
    assert np.isclose(p["d"], 1.0)          # 최고 amihud = 1.0
    assert (p.values >= 0).all() and (p.values <= 1).all()


def test_tiered_cost_monotone_endpoints():
    # illiq_pct=0 → fee_tax+slip_low, =1 → fee_tax+slip_high
    assert np.isclose(tiered_cost(0.0, fee_tax=0.002, slip_low=0.001, slip_high=0.01), 0.003)
    assert np.isclose(tiered_cost(1.0, fee_tax=0.002, slip_low=0.001, slip_high=0.01), 0.012)
    # 단조 증가
    lo = tiered_cost(0.2, fee_tax=0.002, slip_low=0.001, slip_high=0.01)
    hi = tiered_cost(0.8, fee_tax=0.002, slip_low=0.001, slip_high=0.01)
    assert hi > lo


def test_build_periods_nonoverlapping_and_equal_weight():
    # 6 거래일, horizon=2 step → 리밸 날짜 0,2,4. 각 날 상위 50% 롱.
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03",
                            "2024-01-04", "2024-01-05", "2024-01-08"])
    rows = []
    for i, d in enumerate(dates):
        # 2종목: high(amihud=2)·low(amihud=1). high 종목 fwd=0.10, low=0.00
        rows.append({"date": d, "stock_code": "HI", "amihud": 2.0, "fwd_2d": 0.10})
        rows.append({"date": d, "stock_code": "LO", "amihud": 1.0, "fwd_2d": 0.00})
    merged = pd.DataFrame(rows)
    per = build_periods(merged, feat="amihud", label="fwd_2d", top_pct=0.5,
                        horizon=2, fee_tax=0.0, slip_low=0.0, slip_high=0.0)
    # 비중첩: 날짜 3개(0,2,4) 리밸
    assert len(per) == 3
    # 상위 50% = HI 종목만 보유 → gross = 0.10
    assert np.allclose(per["gross"].values, 0.10)
    assert (per["n_held"] == 1).all()


def test_build_periods_applies_tiered_cost():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    rows = []
    for d in dates:
        rows.append({"date": d, "stock_code": "HI", "amihud": 9.0, "fwd_2d": 0.05})
        rows.append({"date": d, "stock_code": "LO", "amihud": 1.0, "fwd_2d": 0.00})
    merged = pd.DataFrame(rows)
    per = build_periods(merged, feat="amihud", label="fwd_2d", top_pct=0.5,
                        horizon=2, fee_tax=0.002, slip_low=0.001, slip_high=0.01)
    # 보유 HI는 within-day illiq_pct=1.0 → cost = 0.002+0.01 = 0.012
    assert np.allclose(per["cost"].values, 0.012)
    assert np.allclose(per["net"].values, 0.05 - 0.012)


def test_period_stats_sharpe_and_annualization():
    net = pd.Series([0.01, 0.02, 0.00, 0.03, -0.01])
    st = period_stats(net, periods_per_year=12.0)
    assert np.isclose(st["mean_net"], net.mean())
    expected_sharpe = net.mean() / net.std(ddof=1) * np.sqrt(12.0)
    assert np.isclose(st["sharpe"], expected_sharpe)
    assert np.isclose(st["ann_return"], net.mean() * 12.0)
    assert st["n_periods"] == 5
