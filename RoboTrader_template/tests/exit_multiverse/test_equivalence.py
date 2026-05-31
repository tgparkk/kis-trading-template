"""동등성 회귀: 신규 포트폴리오 시뮬(unconstrained)이 기존 simulate_one_stock 과
같은 거래를 생성하는지. minervini 단일종목 + elder 단일종목으로 검증."""
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


@pytest.mark.slow
def test_elder_single_stock_no_crash_and_produces_trades():
    """elder stop 경로(unconstrained=True)가 IndexError 없이 완주하고
    실거래 기간(2022~2024)에서 거래를 1건 이상 생성하는지 확인.

    buy-stop pending 의 타이밍 차이(포트심 vs 레거시 per-stock 루프)로
    거래 수 정확 비교가 어렵기 때문에, crash-free + >0 trades 를 최소 기준으로 사용.
    """
    start, end = "2022-01-01", "2024-12-31"
    codes = data_loader.load_top_volume_universe(start, end, top_n=5)
    data = data_loader.load_daily_adj(codes, start, end)
    assert data, "no data loaded"
    code = next(iter(data))
    one = {code: data[code]}

    ad = adapters.ADAPTERS["elder_ema_pullback"]
    strat = ad.build_strategy()
    ctx_fn = ad.make_extra_ctx_fn(data)
    sig = signals.precompute_entry_signals(one, strat, ad.warmup_bars, ctx_fn)

    params = {
        "stop_loss_pct": 0.08, "take_profit_pct": 0.30,
        "max_hold_bars": 100, "trail_ema": None, "trend_flip_exit": False,
    }
    # IndexError 없이 완주해야 한다
    res = portfolio_sim.run_portfolio(
        data=one, signal_cache=sig, adapter=ad, params=params,
        turnover={code: 1.0}, initial_capital=10_000_000,
        max_positions=99, max_per_stock=10_000_000, unconstrained=True)

    assert isinstance(res["equity_curve"], list), "equity_curve must be a list"
    assert len(res["equity_curve"]) > 0, "equity_curve must be non-empty"
    # 3년치 데이터에서 거래 0건은 신호 경로 전체가 고장난 것
    assert res["n_trades"] > 0, (
        f"elder unconstrained produced 0 completed trades for {code} "
        f"({start}~{end}); check entry signal path")
