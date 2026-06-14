import numpy as np
import pandas as pd

from scripts.feature_edge.portfolio_backtest import (
    top_quantile_codes, illiquidity_pct, tiered_cost,
    build_periods, period_stats,
    benchmark_period_returns, alpha_beta,
    sqrt_impact, decile_stats,
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


def test_benchmark_period_returns_aligns_entry_exit():
    # 지수 일봉 6일: close 100,101,102,103,104,105. horizon=2.
    idx = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03",
                                "2024-01-04", "2024-01-05", "2024-01-08"]),
        "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]})
    # 리밸 날짜 d=0 → 진입 close[1]=101, 청산 close[1+2]=103 → 103/101-1
    r = benchmark_period_returns(idx, [pd.Timestamp("2024-01-01")], horizon=2)
    assert np.isclose(r[0], 103.0 / 101.0 - 1.0)
    # 끝부분(미래봉 부족) → NaN
    r2 = benchmark_period_returns(idx, [pd.Timestamp("2024-01-05")], horizon=2)
    assert np.isnan(r2[0])


def test_sqrt_impact_roundtrip_law():
    # 왕복충격 = 2·coef·√참여율. 참여율 0 → 0, 단조 증가.
    assert np.isclose(sqrt_impact(0.0, 0.1), 0.0)
    assert np.isclose(sqrt_impact(0.04, 0.1), 2 * 0.1 * 0.2)  # √0.04=0.2
    assert sqrt_impact(0.09, 0.1) > sqrt_impact(0.04, 0.1)


def test_build_periods_capacity_adds_impact():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    rows = []
    for d in dates:
        # HI 보유종목: 거래대금 1e8(=1억). fwd 0.05.
        rows.append({"date": d, "stock_code": "HI", "amihud": 9.0,
                     "fwd_2d": 0.05, "trading_value": 1e8})
        rows.append({"date": d, "stock_code": "LO", "amihud": 1.0,
                     "fwd_2d": 0.00, "trading_value": 1e8})
    merged = pd.DataFrame(rows)
    # 자본 1e7(=1천만) → 보유 1종목 → 종목당 1e7, 참여율 = 1e7/1e8 = 0.1
    per = build_periods(merged, feat="amihud", label="fwd_2d", top_pct=0.5,
                        horizon=2, fee_tax=0.0, slip_low=0.0, slip_high=0.0,
                        capital=1e7, impact_coef=0.2)
    expected_impact = 2 * 0.2 * np.sqrt(0.1)
    assert np.allclose(per["impact"].values, expected_impact)
    assert np.allclose(per["net"].values, 0.05 - expected_impact)
    # 자본 0(미지정) → 충격 0, 기존과 동일
    per0 = build_periods(merged, feat="amihud", label="fwd_2d", top_pct=0.5,
                         horizon=2, fee_tax=0.0, slip_low=0.0, slip_high=0.0)
    assert np.allclose(per0["net"].values, 0.05)


def test_decile_stats_monotone_signal():
    # amihud 1..100, fwd = amihud·0.001 (단조). 10분위 평균이 단조 증가해야.
    n = 1000
    merged = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01"] * n),
        "stock_code": [f"s{i}" for i in range(n)],
        "amihud": np.linspace(1, 100, n),
        "fwd_20d": np.linspace(1, 100, n) * 0.001,
    })
    ds = decile_stats(merged, "amihud", "fwd_20d", n_bins=10)
    assert len(ds) == 10
    assert ds["mean_label"].is_monotonic_increasing
    assert ds.iloc[-1]["mean_label"] > ds.iloc[0]["mean_label"]


def test_alpha_beta_recovers_known_coeffs():
    rng = np.random.RandomState(0)
    mkt = pd.Series(rng.normal(0.01, 0.02, 400))
    port = 0.6 * mkt + 0.005          # beta 0.6, alpha 0.005, 무잡음
    ab = alpha_beta(port, mkt, periods_per_year=12.0)
    assert np.isclose(ab["beta"], 0.6, atol=1e-6)
    assert np.isclose(ab["alpha"], 0.005, atol=1e-6)
    assert np.isclose(ab["alpha_ann"], 0.005 * 12.0, atol=1e-5)
    # port = 0.6*mkt+0.005, mkt 평균>0 → 초과수익 부호는 데이터 의존, win_rate∈[0,1]
    assert 0.0 <= ab["win_rate"] <= 1.0
