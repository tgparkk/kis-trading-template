"""동등성 회귀: 신규 포트폴리오 시뮬(unconstrained)이 기존 simulate_one_stock 과
같은 거래를 생성하는지. minervini 단일종목으로 검증."""
import pandas as pd
import pytest
from scripts.exit_multiverse import data_loader, signals, adapters, portfolio_sim


@pytest.mark.slow
def test_minervini_single_stock_trade_count_matches_legacy():
    import scripts.run_minervini_vcp as legacy

    start, end = "2022-01-01", "2024-12-31"
    codes = data_loader.load_top_volume_universe(start, end, top_n=5)
    data = data_loader.load_daily_adj(codes, start, end)
    assert data, "no data loaded"
    code = next(iter(data))
    one = {code: data[code]}

    ad = adapters.ADAPTERS["minervini_volume_dryup"]
    strat = ad.build_strategy()
    ctx_fn = ad.make_extra_ctx_fn(data)   # RS는 전체 유니버스로 계산
    sig = signals.precompute_entry_signals(one, strat, ad.warmup_bars, ctx_fn)

    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12,
              "max_hold_bars": 20, "trail_ma": None}
    res = portfolio_sim.run_portfolio(
        data=one, signal_cache=sig, adapter=ad, params=params,
        turnover={code: 1.0}, initial_capital=10_000_000,
        max_positions=99, max_per_stock=10_000_000, unconstrained=True)

    from strategies.books.minervini_vcp.rules import compute_rs_percentile_12w
    rs = compute_rs_percentile_12w(pd.DataFrame(
        {c: data[c].set_index("datetime")["close"] for c in data}))
    legacy_res = legacy.simulate_one_stock(
        code=code, df=data[code], rs_series=rs[code] if code in rs.columns else None,
        strategy=strat, stop_loss_pct=0.08, take_profit_pct=0.12,
        max_hold_bars=20, trail_ma=None)

    new_sells = res["n_trades"]
    legacy_sells = sum(1 for t in legacy_res["trades"] if t["side"] == "sell")
    assert abs(new_sells - legacy_sells) <= 1, (
        f"trade count mismatch: new={new_sells} legacy={legacy_sells}")
